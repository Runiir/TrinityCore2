"""Laya opens the named flight master and selects the public route's taxi node."""
import math
import time
from . import runtime, inputs, interact, action_queue,native_approach
from .observe import observe
from .decisions import choose
from .farm_actions import stationary,click_choice
from .smooth_move import walk,descend
from tools.client_compatibility import travel_policy


def origin_names(row,origin):
    known='Doras' if origin.get('id')==23 else origin.get('master_name')
    if known:return {known}
    ui=row['farm_ui'];soft=ui.get('soft_interact') or {}
    world=row['archaeology']['world'];target=origin['point']
    if (soft.get('exists') and soft.get('name') and world['instance']==target['instance']
            and math.hypot(world['north']-target['north'],world['west']-target['west'])<=2):
        return {soft['name']}
    raise RuntimeError('no named flight master candidate at the addon origin')


def native_approach_available(row,origin):
    known='Doras' if origin.get('id')==23 else origin.get('master_name')
    return bool(known and interact.native_approach_available(row,{known}))


def wait_menu(folder,before,*,native_target=None,interaction=None):
    """Return as soon as fresh public gossip/taxi feedback confirms interaction."""
    world=before['archaeology'].get('world');approach=0
    if native_target and world and world['instance']==native_target['instance']:
        distance=math.hypot(world['north']-native_target['north'],world['west']-native_target['west'])
        speed=(before['farm_ui'].get('move_speeds') or {}).get('run') or 7
        approach=distance/max(.1,speed)+3
    deadline=time.monotonic()+2+approach
    feedback=native_approach.Feedback(before,interaction)
    while time.monotonic()<deadline:
        row=observe(folder/'menu_feedback.png')
        action_queue.validate(row,before)
        if (row['movement']['in_combat'] or row['archaeology']['casting']
                or row['farm_ui'].get('gossip') or row['farm_ui'].get('taxi')):return row
        if native_target and feedback.refused(row):return row
        time.sleep(.05)
    return row


def run(folder,origin,destination):
    folder.mkdir(parents=True,exist_ok=False)
    result={'origin':origin,'destination':destination,'phases':[],'completed':False}
    for index in range(10):
        row=observe(folder/f'phase_{index:02d}.png');m,a=row['movement'],row['archaeology'];world=a['world']
        if not row.get('farm_ui'):raise RuntimeError('taxi public UI feed is unavailable: '+str(row.get('farm_ui_error')))
        target=origin['point'];end=destination['point']
        arrived=world['instance']==end['instance'] and math.hypot(world['north']-end['north'],world['west']-end['west'])<30
        native_available=world['instance']==target['instance'] and native_approach_available(row,origin)
        nearby=world['instance']==target['instance'] and (math.hypot(world['north']-target['north'],world['west']-target['west'])<20 or native_available)
        if not arrived and not nearby and not m['on_taxi']:raise RuntimeError('taxi phase is not at flight master or destination')
        flags={'mode':'taxi','available':m['in_world'] and m['health_percent']>0 and not (m['dead'] or m['in_combat']),
           'casting':a['casting'],'on_taxi':m['on_taxi'],'mounted':a['mounted'],'flying':a['flying'],
           'falling':a['falling'],'at_route_height':False,'near_destination':nearby,
           'destination_reached':arrived,'taxi_map_open':bool(row['farm_ui'].get('taxi'))}
        action,model,request,response=choose(travel_policy.model_state(flags),'travel',physical_state=flags)
        phase={'action':action,'before':row,'model':model,'request':request,'response':response}
        result['phases'].append(phase);runtime.write(folder/'taxi.json',result)
        if action=='arrived':result.update(completed=True,after=row);break
        if action=='land':
            # The taxi phase can begin while the previous approach is still
            # airborne. Honor the model's landing command here rather than
            # bouncing through root recovery until another activity lands.
            phase['landing']=descend(folder,world)
        elif action=='dismount':
            if not a['mounted'] or a['flying'] or a['falling']:
                raise RuntimeError('taxi dismount requires a grounded mounted character')
            phase['dismount']=action_queue.run(folder/f'dismount_{index:02d}',row,'dismount',
                lambda fresh:inputs.execute('World of Warcraft','key',
                    {'key':'shift+space','hold':inputs.key_hold(fresh)}),
                lambda fresh:not fresh['archaeology']['mounted'],observe,
                allowed=lambda fresh:fresh['archaeology']['mounted'] and not any(
                    fresh['archaeology'].get(k) for k in ('flying','falling')),
                uses_gcd=False,failure='taxi dismount did not confirm unmounted state')
        elif action=='interact' and row['farm_ui'].get('gossip'):
            selected=click_choice(folder/f'gossip_{index:02d}',row,['gossip'],'Show the flight destinations available from this flight master')
            if not selected['executed']:raise RuntimeError('Laya waited at flight master ride option')
            phase['gossip_choice']=selected
        elif action=='interact':
            # This route names Orgrimmar's Horde flight master; other origins
            # use the confirmed public soft target or tooltip name supplied later.
            known='Doras' if origin['id']==23 else origin.get('master_name')
            soft=row['farm_ui'].get('soft_interact') or {}
            if native_available:
                approached=row
                phase['approach']={'source':'fresh named flight master with client click-to-move enabled',
                    'exact_coordinate_required':False,'client_owns_approach_and_interaction':True}
            elif known and soft.get('name')==known and soft.get('enabled')=='3':
                approached=row
                phase['approach']={'source':'confirmed public named flight master',
                    'exact_coordinate_required':False}
            else:
                phase['approach']=walk(folder,target,tolerance=.5,
                    guidance={'source':'public flight-master approach'},
                    approved_intent=(action,model,request,response))
                approached=observe(folder/f'approached_{index:02d}.png')
            names=origin_names(approached,origin)
            phase['public_origin_candidate']=sorted(names)
            if native_available:
                phase['interaction']=interact.use(folder/f'interaction_{index:02d}',approached,names,
                    maximum=1,native_right_click=True)
                phase['menu_feedback']=wait_menu(folder,approached,native_target=target,interaction=phase['interaction'])
            else:
                phase['interaction']=interact.use(folder/f'interaction_{index:02d}',approached,names)
                phase['menu_feedback']=wait_menu(folder,approached)
        elif action=='taxi':
            nodes=row['farm_ui']['taxi'];button=next((n for n in nodes if n['id']==destination['id']),None)
            if not button or not button['enabled'] or button['state']!=1:
                raise RuntimeError('requested route taxi destination is unavailable')
            fresh=observe(folder/f'precheck_{index:02d}.png');stationary(row,fresh)
            if button not in fresh['farm_ui']['taxi']:raise RuntimeError('taxi destination changed before selection')
            phase['selected']=button
            phase['input']=inputs.execute('World of Warcraft','click',{'x':round(button['x']*runtime.WIDTH),'y':round(button['y']*runtime.HEIGHT),'button':1})
            for attempt in range(60):
                time.sleep(.4)
                try:after=observe(folder/'transit.png')
                except RuntimeError as e:
                    if str(e).startswith(('live public observer is unavailable','direct public addon feed unavailable',
                            'local public tiles unavailable')):continue
                    raise
                w=after['archaeology']['world']
                if not after['movement']['on_taxi'] and w and w['instance']==end['instance'] and math.hypot(w['north']-end['north'],w['west']-end['west'])<30:
                    phase['after']=after;break
            else:raise RuntimeError('instant taxi did not confirm requested arrival')
        elif action=='observe':time.sleep(.5)
        else:raise RuntimeError('unexpected action at a grounded flight master')
    runtime.write(folder/'taxi.json',result)
    if not result['completed']:raise RuntimeError('taxi phases did not finish')
    return result

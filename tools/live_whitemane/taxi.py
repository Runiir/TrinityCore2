"""Laya opens the named flight master and selects the public route's taxi node."""
import math
import time
from . import runtime, inputs, interact
from .observe import observe
from .decisions import choose
from .farm_actions import stationary,click_choice
from .smooth_move import walk
from tools.client_compatibility import travel_policy


def run(folder,origin,destination):
    folder.mkdir(parents=True,exist_ok=False)
    result={'origin':origin,'destination':destination,'phases':[],'completed':False}
    for index in range(10):
        row=observe(folder/f'phase_{index:02d}.png');m,a=row['movement'],row['archaeology'];world=a['world']
        if not row.get('farm_ui'):raise RuntimeError('taxi public UI feed is unavailable: '+str(row.get('farm_ui_error')))
        target=origin['point'];end=destination['point']
        arrived=world['instance']==end['instance'] and math.hypot(world['north']-end['north'],world['west']-end['west'])<30
        nearby=world['instance']==target['instance'] and math.hypot(world['north']-target['north'],world['west']-target['west'])<20
        if not arrived and not nearby and not m['on_taxi']:raise RuntimeError('taxi phase is not at flight master or destination')
        flags={'mode':'taxi','available':m['in_world'] and m['health_percent']>0 and not (m['dead'] or m['in_combat']),
           'casting':a['casting'],'on_taxi':m['on_taxi'],'mounted':a['mounted'],'flying':a['flying'],
           'falling':a['falling'],'at_route_height':False,'near_destination':nearby,
           'destination_reached':arrived,'taxi_map_open':bool(row['farm_ui']['taxi'])}
        action,model,request,response=choose(travel_policy.model_state(flags),'travel',physical_state=flags)
        phase={'action':action,'before':row,'model':model,'request':request,'response':response}
        result['phases'].append(phase);runtime.write(folder/'taxi.json',result)
        if action=='arrived':result.update(completed=True,after=row);break
        if action=='interact' and row['farm_ui'].get('gossip'):
            selected=click_choice(folder/f'gossip_{index:02d}',row,['gossip'],'I need a ride',{'label':'I need a ride.'})
            if not selected['executed']:raise RuntimeError('Laya waited at flight master ride option')
            phase['gossip_choice']=selected
        elif action=='interact':
            # This route names Orgrimmar's Horde flight master; other origins
            # use the confirmed public soft target or tooltip name supplied later.
            names={'Doras'} if origin['id']==23 else {origin.get('master_name','')}
            phase['approach']=walk(folder,target,tolerance=2)
            approached=observe(folder/f'approached_{index:02d}.png')
            phase['interaction']=interact.use(folder/f'interaction_{index:02d}',approached,names)
            time.sleep(.5)
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
                    if str(e).startswith(('live public observer is unavailable','direct public addon feed unavailable')):continue
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

"""Laya chooses each phase of a flight to the public addon line endpoint."""
import math
import time
from . import inputs, runtime, action_queue
from .observe import observe
from .decisions import choose
from .smooth_move import walk, descend, ascend, GroundContact
from . import clearance
from . import farm_graph,pending_find
from pathlib import Path
from tools.client_compatibility import travel_policy


def fly(folder, row, arrow, step, *, combat_landing=False):
    receipts=[]; phases=[]; at_height=False; previous_phase=None
    contacts=[]; height_plan=None
    step['travel_decisions']=phases
    target=arrow['endpoint']
    arrival_tolerance=arrow.get('arrival_tolerance_yards',6)
    if combat_landing and math.hypot(target['north']-row['archaeology']['world']['north'],
                                    target['west']-row['archaeology']['world']['west'])>.15:
        raise RuntimeError('combat landing must stay at the observed current position')
    graph=Path(step['graph_path']) if step.get('graph_path') else None
    if graph:
        import json
        state=json.loads(graph.read_text());current=state.get('last_action_node',state['current'])
        if current!='flight':farm_graph.transition(graph,'flight',row,pending=pending_find.load(row),target=target)
    def key(name,hold):
        return inputs.execute('World of Warcraft','key',{'key':name,'hold':hold})
    for index in range(32):
        if (runtime.ROOT/'run/stop_dig').exists(): raise RuntimeError('supervisor stop requested')
        row=observe(folder/f'travel_{index:02d}.png')
        m,a=row['movement'],row['archaeology']; world=a['world']
        if not world or world['instance']!=target['instance']:
            raise RuntimeError('flight observation or world instance changed')
        remaining=math.hypot(target['north']-world['north'],target['west']-world['west'])
        if combat_landing and remaining>6:raise RuntimeError('combat landing drifted from its current-position target')
        maximum_distance=750 if arrow.get('site_id') else 1500
        if remaining>maximum_distance: raise RuntimeError('addon endpoint exceeds bounded flight range')
        if remaining>arrival_tolerance and not row.get('owned_pose'):
            from .navigation import seed_height
            phase_folder=folder/f'height_refresh_{time.time_ns()}'
            refresh=seed_height(phase_folder,row)
            step.setdefault('height_refreshes',[]).append(refresh)
            row=refresh['after'];m,a=row['movement'],row['archaeology'];world=a['world']
        if remaining>arrival_tolerance and height_plan is None:
            height_plan=clearance.plan(row,target,maximum_distance=maximum_distance,arrival_tolerance=arrival_tolerance)
            step['height_plan']=height_plan
        if height_plan:
            pose=row.get('owned_pose')
            at_height=bool(a['flying'] and pose and pose['height_yards']>=height_plan['ceiling_yards']-.5)
        flags={'mode':'flight','available':m['in_world'] and m['health_percent']>0 and not m['dead'] and (not m['in_combat'] or combat_landing),
               'casting':a['casting'],'on_taxi':m['on_taxi'],'mounted':a['mounted'],
               'flying':a['flying'],'falling':a['falling'],'at_route_height':at_height,
               'near_destination':remaining<=arrival_tolerance,'destination_reached':remaining<=arrival_tolerance,'taxi_map_open':False}
        if not flags['available']: raise RuntimeError('character became unavailable during flight')
        error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
        state=travel_policy.model_state(flags)
        action,model,request,response=choose(state,'travel',physical_state=flags)
        if combat_landing and action not in ('land','dismount','arrived','observe'):
            raise RuntimeError('combat landing cannot mount, ascend, or travel horizontally')
        phase={'observed_at':row['observed_at'],'flags':flags,'state':state,'model':model,
               'request':request,'response':response,'action':action,'remaining_yards':remaining,
               'heading_error_radians':error,'observed_public_state':row,'inputs':[]}
        phases.append(phase)
        if action=='arrived': return receipts
        if graph and action!='observe':phase['graph_transition']=farm_graph.transition(graph,action,row,pending=pending_find.load(row))
        queued=None
        if action=='mount':
            if a['mounted']:raise RuntimeError('mount toggle requires an unmounted character')
            queued=action_queue.run(folder/f'command_{index:02d}',row,'mount',
                lambda _:key('shift+space',.15),lambda r:r['archaeology']['mounted'],observe,
                allowed=lambda r:not r['movement']['in_combat'] and r['movement'].get('speed',0)==0
                    and not any(r['archaeology'].get(k) for k in ('mounted','flying','falling')),
                failure='mount input did not produce mounted state')
            phase['inputs'].extend(queued['inputs'])
        elif action=='takeoff':
            phase['smooth_ascent']=ascend(folder,height_plan['ceiling_yards'],site_id=arrow.get('site_id'))
            phase['height_basis']='calculated reference corridor clearance and authenticated owned climb feedback'
        elif action=='cruise':
            try:
                phase['smooth_approach']=walk(folder,target,flying=True,site_id=arrow.get('site_id'),guidance=arrow,
                    tolerance=arrival_tolerance,
                    approved_intent=(action,model,request,response))
            except GroundContact as contact:
                landed=contact.observation['archaeology']['world']
                contacts.append(landed)
                phase.update(outcome='terrain_contact_reobserve',
                             after=contact.observation,inputs_released=True)
                at_height=False
                height_plan=None
                if len(contacts)>=3 and all(math.hypot(p['north']-landed['north'],p['west']-landed['west'])<3
                                            for p in contacts[-3:]):
                    raise RuntimeError('repeated terrain contact without route progress')
                # The next model request sees mounted ground, remaining route
                # distance and availability. Laya chooses takeoff or landing.
                if graph:farm_graph.transition(graph,'flight',contact.observation,pending=pending_find.load(contact.observation))
                continue
        elif action=='land':
            descent_options={'site_id':arrow.get('site_id')}
            if combat_landing:descent_options['allow_combat']=True
            phase['smooth_descent']=descend(folder,target,**descent_options)
        elif action=='dismount':
            if not a['mounted'] or a['flying']:raise RuntimeError('dismount toggle requires a grounded mounted character')
            queued=action_queue.run(folder/f'command_{index:02d}',row,'dismount',
                lambda _:key('shift+space',.15),lambda r:not r['archaeology']['mounted'],observe,
                allowed=lambda r:r['archaeology']['mounted'] and not any(
                    r['archaeology'].get(k) for k in ('flying','falling')),uses_gcd=False,
                failure='dismount input did not produce unmounted state')
            phase['inputs'].extend(queued['inputs'])
        elif action=='observe':
            time.sleep(.5)
        else: raise RuntimeError('unexpected travel action for a flight route')
        receipts.extend(phase['inputs'])
        if queued:
            phase['command_queue']=queued;after=queued['after']
        else:
            time.sleep(.3)
            after=observe(folder/f'travel_{index:02d}_after.png')
        phase['after']=after
        if graph and action!='observe':farm_graph.transition(graph,'flight',after,pending=pending_find.load(after))
        if action=='mount' and not after['archaeology']['mounted']:
            raise RuntimeError('mount input did not produce mounted state')
        if action=='dismount' and after['archaeology']['mounted']:
            raise RuntimeError('dismount input did not produce unmounted state')
        if action=='takeoff' and not after['archaeology']['flying']:
            raise RuntimeError('takeoff did not produce flying state')
        if action=='cruise' and abs(error)<=.18:
            moved=math.hypot(after['archaeology']['world']['north']-world['north'],after['archaeology']['world']['west']-world['west'])
            phase['moved_yards']=moved
            if moved<.25: raise RuntimeError('flight cruise was blocked')
        if action==previous_phase=='mount': raise RuntimeError('repeated mount phase')
        previous_phase=action
    raise RuntimeError('flight repeated phases without reaching the addon endpoint')

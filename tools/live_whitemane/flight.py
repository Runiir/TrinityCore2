"""Laya chooses each phase of a flight to the public addon line endpoint."""
import math
import time
from . import inputs, runtime
from .observe import observe
from .decisions import choose
from .smooth_move import walk, descend
from tools.client_compatibility import travel_policy


def fly(folder, row, arrow, step):
    receipts=[]; phases=[]; at_height=False; previous_phase=None
    step['travel_decisions']=phases
    target=arrow['endpoint']
    def click_mount():
        from .archaeology_probe import command
        return command('/cast Blue Wind Rider')
    def key(name,hold):
        return inputs.execute('World of Warcraft','key',{'key':name,'hold':hold})
    for index in range(32):
        if (runtime.ROOT/'run/stop_dig').exists(): raise RuntimeError('supervisor stop requested')
        row=observe(folder/f'travel_{index:02d}.png')
        m,a=row['movement'],row['archaeology']; world=a['world']
        if not world or world['instance']!=target['instance']:
            raise RuntimeError('flight observation or world instance changed')
        remaining=math.hypot(target['north']-world['north'],target['west']-world['west'])
        if remaining>750: raise RuntimeError('addon line endpoint exceeds local digsite range')
        flags={'mode':'flight','available':m['in_world'] and m['health_percent']>=90 and not (m['dead'] or m['in_combat']),
               'casting':a['casting'],'on_taxi':m['on_taxi'],'mounted':a['mounted'],
               'flying':a['flying'],'falling':a['falling'],'at_route_height':at_height,
               'near_destination':remaining<=6,'destination_reached':remaining<=6,'taxi_map_open':False}
        if not flags['available']: raise RuntimeError('character became unavailable during flight')
        error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
        state=travel_policy.model_state(flags)
        action,model,request,response=choose(state,'travel',physical_state=flags)
        phase={'observed_at':row['observed_at'],'flags':flags,'state':state,'model':model,
               'request':request,'response':response,'action':action,'remaining_yards':remaining,
               'heading_error_radians':error,'observed_public_state':row,'inputs':[]}
        phases.append(phase)
        if action=='arrived': return receipts
        if action=='mount':
            phase['inputs'].extend(click_mount());time.sleep(2.5)
        elif action=='takeoff':
            phase['inputs'].append(key('space',1));at_height=True
            phase['height_basis']='bounded ascent then public IsFlying confirmation; absolute altitude unavailable'
        elif action=='cruise':
            phase['smooth_approach']=walk(folder,target,flying=True,site_id=arrow.get('site_id'))
        elif action=='land':
            phase['smooth_descent']=descend(folder,target,site_id=arrow.get('site_id'))
        elif action=='dismount':
            from .archaeology_probe import command
            phase['inputs'].extend(command('/dismount'));time.sleep(.5)
        elif action=='observe':
            time.sleep(.5)
        else: raise RuntimeError('unexpected travel action for a flight route')
        receipts.extend(phase['inputs'])
        time.sleep(.3)
        after=observe(folder/f'travel_{index:02d}_after.png')
        phase['after']=after
        if action=='mount' and not after['archaeology']['mounted']:
            raise RuntimeError('mount input did not produce mounted state')
        if action=='takeoff' and not after['archaeology']['flying']:
            raise RuntimeError('takeoff did not produce flying state')
        if action=='cruise' and abs(error)<=.18:
            moved=math.hypot(after['archaeology']['world']['north']-world['north'],after['archaeology']['world']['west']-world['west'])
            phase['moved_yards']=moved
            if moved<.25: raise RuntimeError('flight cruise was blocked')
        if action==previous_phase=='mount': raise RuntimeError('repeated mount phase')
        previous_phase=action
    raise RuntimeError('flight repeated phases without reaching the addon endpoint')

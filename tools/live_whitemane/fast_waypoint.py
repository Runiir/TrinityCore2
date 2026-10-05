"""Ten Hz Laya decisions over public addon facts, with persistent owned input."""
import fcntl
import json
import math
import time
from collections import deque
from . import runtime, inputs, native_control, guide
from .observe import observe
from .decisions import choose
from .motion import turn_duration
from .boundaries import check_point
from .sticky_input import StickyInput
from tools.client_compatibility import travel_policy
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def decision(row,target,distance,error,flying,site_id,tolerance):
    m,a=row['movement'],row['archaeology']
    direction='aligned' if abs(error)<=.18 else 'left' if error>0 else 'right'
    if site_id is not None and not flying:
        waypoint={'color':'green' if distance<=40 else 'yellow' if distance<=80 else 'red',
            'distance_yards':round(distance,2),'heading_relative_to_player':direction,'arrived':distance<=tolerance}
        state=guide.model_state(row,waypoint,(row.get('farm_ui') or {}).get('soft_interact',{}).get('name') in FIND_NAMES)
        return choose(state)
    flags={'mode':'flight' if flying else 'portal','available':True,'casting':a['casting'],
        'on_taxi':m['on_taxi'],'mounted':a['mounted'],'flying':a['flying'],'falling':a['falling'],
        'at_route_height':flying,'near_destination':distance<=tolerance,
        'destination_reached':distance<=tolerance,'taxi_map_open':False}
    return choose(travel_policy.model_state(flags),'travel',physical_state=flags)


def walk(folder,target,*,flying=False,site_id=None,tolerance=None):
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    from .smooth_move import GroundContact
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    tolerance=(6 if flying else 4) if tolerance is None else tolerance
    from .resources import DEFAULTS,limits,check
    check()
    receipts=deque(maxlen=(limits() or DEFAULTS)['movement_history']);started=time.time();turns=[]
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft');sender=native_input_adapter.Input()
        sticky=StickyInput(sender);last_sequence=None;last_progress=time.monotonic()
        previous=None;deadline=None;index=0;decision_count=0
        try:
            while True:
                cycle=time.monotonic();row=observe(folder/f'approach_{index%8:02d}.png')
                m,a=row['movement'],row['archaeology'];world=a['world']
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                    or m['in_combat'] or m['on_taxi'] or a['casting'] or m['health_percent']<90
                    or not world or world['instance']!=target['instance'] or a['falling'] or a.get('swimming')):
                    raise RuntimeError('character or owned feed unavailable during continuous approach')
                if site_id is not None:check_point(site_id,world)
                if a['flying']!=flying:
                    if flying and a['mounted'] and a['grounded']:raise GroundContact(row)
                    raise RuntimeError('unexpected movement mode during continuous approach')
                if sticky.interrupted:raise RuntimeError(sticky.interrupted)
                if m['sequence']==last_sequence:
                    time.sleep(.01);continue
                last_sequence=m['sequence']
                distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
                if distance>(1500 if flying and site_id is None else 750):
                    raise RuntimeError('waypoint exceeds its bounded route range')
                speed=m['speed'] if m['speed']>.5 else 32 if flying else 7
                if deadline is None:deadline=cycle+10+3*distance/speed
                if cycle>deadline:raise RuntimeError('continuous waypoint exceeded its calculated emergency bound')
                error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
                action,model,request,response=decision(row,target,distance,error,flying,site_id,tolerance)
                receipt={'observed_at':row['observed_at'],'distance_yards':distance,'heading_error':error,
                    'altitude_yards':a.get('altitude_yards'),'grounded':a['grounded'],
                    'model':model,'request':request,'response':response,'action':action,
                    'channel_ages':row['channel_ages']}
                receipts.append(receipt)
                decision_count+=1
                with (folder/'movement_decisions.jsonl').open('a') as audit:audit.write(json.dumps(receipt)+'\n')
                if distance<=tolerance or action in ('survey','loot','arrived','land'):return list(receipts)
                if action not in ('forward_short','forward_long','turn_left','turn_right','cruise','portal'):
                    raise RuntimeError('Laya interrupted continuous waypoint movement with '+action)
                sticky.renew()
                if previous is None or distance<previous-.15:last_progress=cycle
                elif 'Up' in sticky.held and cycle-last_progress>2:
                    raise RuntimeError('continuous waypoint movement is blocked')
                previous=distance
                if abs(error)>.18:
                    sticky.hold('Up',False)
                    duration,receipt['turn_calibration']=turn_duration(error,turns)
                    sticky.hold('Left',error>0,duration);sticky.hold('Right',error<0,duration)
                else:
                    sticky.hold('Left',False);sticky.hold('Right',False)
                    # Predict the travel during the measured feed delay. Near
                    # arrival, a calculated pulse ends independently of the
                    # next observation or model request.
                    age=row['channel_ages']['M']
                    remaining=(distance-tolerance-m['speed']*age)/speed
                    if m['speed']==0:remaining=max(1/30,remaining)
                    sticky.hold('Up',remaining>0,remaining if remaining<.25 else None)
                    receipt['calculated_forward_seconds']=max(0,remaining)
                index+=1;time.sleep(max(0,.1-(time.monotonic()-cycle)))
        finally:
            sticky.close()
            runtime.write(folder/'smooth_walk.json',{'identity':identity,'sender':sender.initialization,
                'started_at':started,'finished_at':time.time(),'observations':list(receipts),'decision_count':decision_count,
                'transport':'addon_relay','decision_period_seconds':.1,'input_lease_seconds':sticky.lease})

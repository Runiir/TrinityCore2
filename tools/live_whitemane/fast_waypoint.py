"""Ten Hz public feedback with retained Laya intent and owned mouse steering."""
import fcntl
import json
import math
import statistics
import time
from collections import deque
from . import runtime, inputs, native_control, guide
from .observe import observe
from .decisions import choose
from .camera_steering import CameraSteering
from .boundaries import check_point
from .sticky_input import StickyInput,observation_lease
from tools.client_compatibility import travel_policy
from tools.client_compatibility.archaeology_inputs import FIND_NAMES


def decision(row,target,distance,error,flying,site_id,tolerance,*,approaching_find=False,guidance=None):
    m,a=row['movement'],row['archaeology']
    direction='aligned' if abs(error)<=.18 else 'left' if error>0 else 'right'
    if site_id is not None and not flying:
        waypoint={'color':'green' if distance<=40 else 'yellow' if distance<=80 else 'red',
            'distance_yards':round(distance,2),'heading_relative_to_player':direction,'arrived':distance<=tolerance}
        from .survey_find import in_range
        named=(row.get('farm_ui') or {}).get('soft_interact',{}).get('name') in FIND_NAMES
        artifact=in_range(row) if row.get('visible_find') else named and not approaching_find
        state=guide.model_state(row,waypoint,artifact)
        state['guidance_source']=(guidance or {}).get('source','selected waypoint')
        state['Survey_generation']=a.get('successful_surveys')
        return choose(state)
    flags={'mode':'flight' if flying else 'portal','available':True,'casting':a['casting'],
        'on_taxi':m['on_taxi'],'mounted':a['mounted'],'flying':a['flying'],'falling':a['falling'],
        'at_route_height':flying,'near_destination':distance<=tolerance,
        'destination_reached':distance<=tolerance,'taxi_map_open':False}
    state=travel_policy.model_state(flags)
    state['guidance']={'source':(guidance or {}).get('source','selected waypoint'),
        'distance_yards':round(distance,2),'bearing_error_degrees':round(math.degrees(error),1),
        'Survey_generation':a.get('successful_surveys')}
    return choose(state,'travel',physical_state=flags)


def walk(folder,target,*,flying=False,site_id=None,tolerance=None,approaching_find=False,guidance=None,approved_intent=None):
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    from .smooth_move import GroundContact
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    tolerance=(6 if flying else 4) if tolerance is None else tolerance
    route=list((guidance or {}).get('ground_route') or [])
    if route and (flying or any(p['instance']!=target['instance'] for p in route)):
        raise ValueError('ground route requires one grounded world instance')
    if route:target=route[0]
    from .resources import DEFAULTS,limits,check
    check()
    receipts=deque(maxlen=(limits() or DEFAULTS)['movement_history']);started=time.time()
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        from .camera_input import Input
        identity=inputs.focus('World of Warcraft');sender=Input()
        sticky=StickyInput(sender);last_sequence=None;last_progress=time.monotonic()
        previous=None;deadline=None;index=0;decision_count=0;retained_decisions=0;last_pulse=None
        sample_periods=deque(maxlen=8);last_sample=None;row=None
        steering=CameraSteering();current_decision=None;look_sequence=None
        pitch_steering=CameraSteering(minimum_deadband=.01,maximum_deadband=.03)
        survey_generation=None;artifact_before=None;forward_started=False;terrain_wait=False
        swimming_mode=None
        try:
            while True:
                cycle=time.monotonic();row=observe(folder/f'approach_{index%8:02d}.png')
                m,a=row['movement'],row['archaeology'];world=a['world']
                if a['falling'] and flying:
                    raise RuntimeError('terrain falling interrupted the continuous approach')
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                    or m['in_combat'] or m['on_taxi'] or a['casting'] or m['health_percent']<=0
                    or not world or world['instance']!=target['instance']):
                    raise RuntimeError('character or owned feed unavailable during continuous approach')
                if site_id is not None:check_point(site_id,world)
                if a['flying']!=flying:
                    if flying and (a['grounded'] or a.get('swimming')):raise GroundContact(row)
                    raise RuntimeError('unexpected movement mode during continuous approach')
                if not flying:
                    current_swimming=bool(a.get('swimming'))
                    if swimming_mode is None:swimming_mode=current_swimming
                    elif current_swimming!=swimming_mode:
                        receipts.append({'observed_at':row['observed_at'],
                            'outcome':'water_mode_changed','swimming_before':swimming_mode,
                            'swimming_now':current_swimming,'retained_destination':target})
                        raise RuntimeError('unexpected movement mode during continuous approach: swimming changed')
                if sticky.interrupted:raise RuntimeError(sticky.interrupted)
                # Rendering can be slower than the local control tick. An
                # unchanged but still-valid public frame retains the accepted
                # command; observe() rejects frames after their freshness bound.
                sticky.lease=observation_lease(row)
                sticky.renew()
                if m['sequence']==last_sequence:
                    time.sleep(.01);continue
                last_sequence=m['sequence']
                if a['falling']:
                    # Normal on-foot terrain steps can briefly fall. Retain
                    # the selected destination, release forward, and resume
                    # from fresh grounded facts instead of restarting Laya.
                    sticky.hold('Up',False);sticky.renew();terrain_wait=True
                    receipts.append({'observed_at':row['observed_at'],'outcome':'awaiting_ground',
                        'model_decision_reused':True,'altitude_yards':a.get('altitude_yards')})
                    if deadline is not None and cycle>deadline:
                        raise RuntimeError('terrain falling interrupted the continuous approach')
                    index+=1;time.sleep(.1);continue
                if terrain_wait:last_progress=cycle;terrain_wait=False
                if last_sample is not None:
                    elapsed=((m['client_uptime_ms']-last_sample)%2**32)/1000
                    if 0<elapsed<=.5:sample_periods.append(elapsed)
                last_sample=m['client_uptime_ms']
                distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
                while len(route)>1 and distance<=tolerance:
                    route.pop(0);target=route[0];distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
                    previous=None;last_progress=cycle
                if distance>(1500 if flying and site_id is None else 750):
                    raise RuntimeError('waypoint exceeds its bounded route range')
                speeds=(row.get('farm_ui') or {}).get('move_speeds') or {}
                swimming=bool(a.get('swimming'))
                speed=m['speed'] if m['speed']>.5 else (speeds.get('swim' if swimming else 'flight' if flying else 'run') or (5 if swimming else 32 if flying else 7))
                if deadline is None:
                    route_length=distance+sum(math.hypot(b['north']-a['north'],b['west']-a['west']) for a,b in zip(route,route[1:]))
                    deadline=cycle+10+3*route_length/speed
                if cycle>deadline:raise RuntimeError('continuous waypoint exceeded its calculated emergency bound')
                error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
                if survey_generation is None:survey_generation=a.get('successful_surveys')
                elif a.get('successful_surveys')!=survey_generation:
                    raise RuntimeError('new Survey replaced the active telescope route')
                artifact=(row.get('farm_ui') or {}).get('soft_interact',{}).get('name') in FIND_NAMES
                changed_artifact=artifact_before is not None and artifact!=artifact_before
                artifact_before=artifact
                if distance<=tolerance:
                    receipts.append({'observed_at':row['observed_at'],'distance_yards':distance,
                        'heading_error':error,'outcome':'waypoint_arrived','model_decision_reused':True})
                    return list(receipts)
                new_decision=current_decision is None or changed_artifact
                retained=False
                if new_decision:
                    sticky.hold('Up',False)
                    if current_decision is None and approved_intent:
                        current_decision=approved_intent;retained=True;retained_decisions+=1
                    else:
                        current_decision=decision(row,target,distance,error,flying,site_id,tolerance,
                            approaching_find=approaching_find,guidance=guidance)
                        decision_count+=1
                action,model,request,response=current_decision
                receipt={'observed_at':row['observed_at'],'distance_yards':distance,'heading_error':error,
                    'camera_input':(row.get('farm_ui') or {}).get('camera_input'),
                    'altitude_yards':a.get('altitude_yards'),'grounded':a['grounded'],
                    'model':model,'request':request,'response':response,'action':action,
                    'channel_ages':row['channel_ages'],'model_decision_reused':not new_decision or retained,
                    'decision_source':'selected_movement_intent' if retained else 'waypoint_feedback',
                    'guidance_source':(guidance or {}).get('source','selected waypoint')}
                receipt['swimming']=swimming
                receipts.append(receipt)
                if new_decision:
                    with (folder/'movement_decisions.jsonl').open('a') as audit:audit.write(json.dumps(receipt)+'\n')
                if action in ('survey','loot','arrived','land'):return list(receipts)
                if action not in ('forward_short','forward_long','turn_left','turn_right','cruise','portal',
                        'follow_detour','step_left','step_right','step_back','step_forward','interact'):
                    raise RuntimeError('Laya interrupted continuous waypoint movement with '+action)
                sticky.renew()
                if previous is None or distance<previous-.15:last_progress=cycle
                elif 'Up' in sticky.held and cycle-last_progress>2:
                    raise RuntimeError('continuous waypoint movement is blocked')
                previous=distance
                if look_sequence is None:
                    sender.move(640,150);sticky.button(3,True);look_sequence=m['sequence']
                    index+=1;time.sleep(.1);continue
                if m['sequence']<=look_sequence:continue
                pixels,receipt['camera_steering']=steering.update(m['facing_radians'],m['client_uptime_ms'],
                    error,distance,tolerance)
                vertical=0;pitch_ready=True
                if flying or swimming:
                    pose=row.get('owned_pose');pitch_ready=False
                    if pose and pose.get('pitch_radians') is not None:
                        pitch=pose['pitch_radians']
                        desired_pitch=0
                        if (guidance or {}).get('flight_path'):
                            from .flight_path import aim
                            receipt['flight_aim']=aim(guidance['flight_path'],world,pose['height_yards'],speed,
                                max(row['channel_ages'].values()))
                            desired_pitch=receipt['flight_aim']['pitch_radians']
                        vertical,receipt['pitch_steering']=pitch_steering.update(pitch,m['client_uptime_ms'],
                            desired_pitch-pitch,distance,4)
                        pitch_ready=abs(desired_pitch-pitch)<math.pi/2
                        speed*=max(.01,math.cos(pitch))
                if vertical and not pixels:
                    # A stationary aircraft may not send a new movement-pitch
                    # packet for camera tilt alone. A one-pixel yaw component
                    # requests that normal client update with the same aim
                    # delta; it does not restart the movement/model decision.
                    pixels=1 if index%2 else -1
                    receipt['pitch_feedback_yaw_pixels']=pixels
                if pixels or vertical:sticky.relative(pixels,vertical)
                # Forward motion remains productive throughout a correcting
                # arc while facing into the destination's half-plane.
                alignment_limit=.18 if distance<=max(4,speed*.3) else math.pi/2
                if abs(error)>=alignment_limit or not pitch_ready:
                    sticky.hold('Up',False)
                else:
                    # Predict the travel during the measured feed delay. Near
                    # arrival, a calculated pulse ends independently of the
                    # next observation or model request.
                    age=max(row['channel_ages']['M'],row['channel_ages'].get('A',0))
                    remaining=(distance-tolerance-m['speed']*age)/speed
                    # A pulse shorter than one observed client update can be
                    # pressed and released without the game seeing movement.
                    # Quantize close pulses to the measured sampling interval.
                    interval=statistics.median(sample_periods) if sample_periods else age
                    frame_rate=(row.get('farm_ui') or {}).get('frame_rate')
                    input_period=1/frame_rate if frame_rate and frame_rate>0 else interval
                    if m['speed']==0:remaining=max(interval,remaining)
                    if m['speed']==0:remaining=max(input_period,(distance-tolerance)/speed)
                    pulse=max(input_period,remaining) if remaining<.5 else None
                    receipt['calculated_pulse_seconds']=pulse
                    stale_position=bool(last_pulse and 'Up' not in sticky.held and
                        math.hypot(last_pulse['world']['north']-world['north'],last_pulse['world']['west']-world['west'])<.15
                        and (m['speed']>0 or a['sequence']<=last_pulse['sequence']+1))
                    if not stale_position:
                        newly_pressed='Up' not in sticky.held
                        if newly_pressed and remaining>0 and not forward_started:
                            last_progress=cycle;forward_started=True
                        sticky.hold('Up',remaining>0,pulse)
                        if newly_pressed and pulse is not None:last_pulse={'world':dict(world),'sequence':a['sequence']}
                    receipt['calculated_forward_seconds']=max(0,remaining)
                index+=1;time.sleep(max(0,.1-(time.monotonic()-cycle)))
        finally:
            sticky.close()
            runtime.write(folder/'smooth_walk.json',{'identity':identity,'sender':sender.initialization,
                'started_at':started,'finished_at':time.time(),'observations':list(receipts),'decision_count':decision_count,
                'retained_decisions':retained_decisions,
                'transport':row['source'] if row else None,'decision_period_seconds':.1,'input_lease_seconds':sticky.lease,
                'steering':'right_button_relative_mouselook','yaw_samples':list(steering.samples),
                'pitch_samples':list(pitch_steering.samples)})

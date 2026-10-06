"""Keep the owned input sender alive while approaching one displayed marker."""
import fcntl
import math
import time
from . import inputs,runtime,native_control
from .observe import observe
from .boundaries import check_point


class GroundContact(RuntimeError):
    """A flying route reached terrain; release input and ask Laya again."""
    def __init__(self, row):
        super().__init__('flight reached terrain')
        self.observation = row


def walk(folder,target,*,flying=False,site_id=None,tolerance=None,approaching_find=False,guidance=None,approved_intent=None):
    mode=runtime.ROOT/'run/observation_mode.json'
    if mode.exists():
        import json
        if json.loads(mode.read_text()).get('transport') in ('addon_relay','local_tiles'):
            from .fast_waypoint import walk as continuous
            return continuous(folder,target,flying=flying,site_id=site_id,tolerance=tolerance,
                approaching_find=approaching_find,guidance=guidance,approved_intent=approved_intent)
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft'); sender=native_input_adapter.Input()
        held=set(); receipts=[]; started=time.time()
        def hold(name,on):
            code,_=sender._keycode(sender.XK.string_to_keysym(name))
            if on and name not in held:
                sender._send(sender.X.KeyPress,code);held.add(name)
            elif not on and name in held:
                sender._send(sender.X.KeyRelease,code);held.remove(name)
        try:
            stalled=0;previous=None
            for index in range(120 if flying and site_id is None else 60):
                row=observe(folder/f'approach_{index:02d}.png')
                m,a=row['movement'],row['archaeology']; world=a['world']
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                        or m['in_combat'] or m['on_taxi'] or a['casting'] or m['health_percent']<=0
                        or not world or world['instance']!=target['instance']
                        or a['falling'] or a.get('swimming')):
                    raise RuntimeError('supervisor interruption or unavailable character during marker approach')
                if site_id is not None:check_point(site_id,world)
                if a['flying'] != flying:
                    if flying and a['mounted'] and a['grounded']:
                        raise GroundContact(row)
                    raise RuntimeError('unexpected movement mode during marker approach')
                distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
                error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
                receipts.append({'observed_at':row['observed_at'],'distance_yards':distance,'heading_error':error,
                                 'altitude_yards':a.get('altitude_yards'),'grounded':a.get('grounded')})
                tolerance=(6 if flying else 4) if tolerance is None else tolerance
                if distance<=tolerance: break
                if distance>(1500 if flying and site_id is None else 750): raise RuntimeError('waypoint exceeds its bounded route range')
                if previous is not None and 'Up' in held:
                    stalled=stalled+1 if distance>=previous-.15 else 0
                    if stalled>=5: raise RuntimeError('waypoint movement is blocked')
                previous=distance
                speed=max(m['speed'],32 if flying else 7)
                if distance<=tolerance+speed*1.5:
                    # Public map readings lag movement. Brake before the stale
                    # position reaches the waypoint, then settle between final
                    # short corrections while retaining the same sender.
                    hold('Up',False)
                    if abs(error)>.18:
                        name='Left' if error>0 else 'Right'
                        hold(name,True);time.sleep(.05);hold(name,False)
                    else:
                        hold('Up',True)
                        time.sleep(max(.05,min(.4,(distance-tolerance)/speed*.65)))
                        hold('Up',False)
                    time.sleep(.9)
                    continue
                hold('Up',abs(error)<.25)
                hold('Left',error>.18);hold('Right',error<-.18)
                time.sleep(.05)
                hold('Left',False);hold('Right',False)
            else: raise RuntimeError('marker approach did not reach its waypoint')
        finally:
            for name in list(held): hold(name,False)
            sender.close()
            runtime.write(folder/'smooth_walk.json',{'identity':identity,'sender':sender.initialization,
                'started_at':started,'finished_at':time.time(),'observations':receipts})
        return receipts


def descend(folder,target,*,site_id=None,allow_combat=False):
    """Hold descent through fresh observations, releasing on confirmed ground.

    UnitPosition Z, when provided by the client, is altitude rather than height
    above terrain. Landing uses two successive public grounded observations.
    """
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft');sender=native_input_adapter.Input()
        code,_=sender._keycode(sender.XK.string_to_keysym('x'))
        held=False;rows=[];ground_samples=0;started=time.time()
        try:
            for index in range(60):
                row=observe(folder/f'descent_{index:02d}.png')
                m,a=row['movement'],row['archaeology'];world=a['world']
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead'] or (m['in_combat'] and not allow_combat)
                        or m['on_taxi'] or a['casting'] or m['health_percent']<=0 or not world
                        or world['instance']!=target['instance'] or a.get('swimming')):
                    raise RuntimeError('character unavailable during descent')
                if site_id is not None:check_point(site_id,world)
                remaining=math.hypot(target['north']-world['north'],target['west']-world['west'])
                if remaining>12: raise RuntimeError('character drifted away from landing destination')
                grounded=not a['flying'] and not a['falling']
                altitude=a.get('altitude_yards');vertical=None
                if rows and altitude is not None and rows[-1]['altitude_yards'] is not None:
                    delta=row['observed_at']-rows[-1]['observed_at']
                    if delta>0:vertical=(altitude-rows[-1]['altitude_yards'])/delta
                rows.append({'observed_at':row['observed_at'],'grounded':grounded,
                             'altitude_yards':altitude,'vertical_yards_per_second':vertical,
                             'height_above_ground_yards':None,'remaining_yards':remaining})
                if grounded:
                    if held:sender._send(sender.X.KeyRelease,code);held=False
                    ground_samples+=1
                    if ground_samples>=2:return rows
                else:
                    ground_samples=0
                    if a['flying'] and not held:sender._send(sender.X.KeyPress,code);held=True
                time.sleep(.15)
            raise RuntimeError('descent did not confirm landing')
        finally:
            if held:sender._send(sender.X.KeyRelease,code)
            sender.close()
            runtime.write(folder/'smooth_descent.json',{'identity':identity,'sender':sender.initialization,
                'started_at':started,'finished_at':time.time(),'observations':rows,
                'ground_confirmed':ground_samples>=2})


def ascend(folder, ceiling, *, site_id=None):
    """Hold ascent until live height and measured climb rate predict clearance."""
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    from .clearance import remaining_seconds
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft');sender=native_input_adapter.Input()
        code,_=sender._keycode(sender.XK.string_to_keysym('space'))
        held=False;rows=[];started=time.time();last_height=None;stalled=0;last_pose_tick=None
        observation_seconds=[];missing_height=0
        try:
            for index in range(150):
                observation_started=time.monotonic()
                row=observe(folder/f'ascent_{time.time_ns()}.png')
                observation_seconds.append(time.monotonic()-observation_started)
                m,a=row['movement'],row['archaeology'];pose=row.get('owned_pose')
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                        or m['in_combat'] or m['on_taxi'] or m['health_percent']<=0 or a['casting']
                        or not a['mounted'] or a['falling'] or a['swimming']):
                    raise RuntimeError('calculated ascent lost a healthy owned height observation')
                if not pose:
                    # The public flight flag can precede its captured movement
                    # packet. Release immediately and wait for the real height.
                    if held:sender._send(sender.X.KeyRelease,code);held=False
                    missing_height+=1
                    if missing_height>=6:raise RuntimeError('calculated ascent lost a healthy owned height observation')
                    time.sleep(.1);continue
                missing_height=0
                if site_id is not None:check_point(site_id,a['world'])
                if time.time()-started>15:raise RuntimeError('calculated ascent exceeded its emergency bound')
                seconds=remaining_seconds(pose,ceiling)
                gap=ceiling-pose['height_yards']
                rows.append({'observed_at':row['observed_at'],'pose':pose,
                             'height_gap_yards':gap,'calculated_seconds_remaining':seconds})
                # Stop before the observed position reaches the target when
                # measured velocity predicts the remaining telemetry delay.
                if a['flying'] and gap<=.5:
                    return rows
                if held and a['flying'] and seconds is not None:
                    # A screenshot takes longer than the last few yards of a
                    # climb. Release at the predicted arrival before starting
                    # another expensive snapshot, then verify actual height.
                    remaining=max(0,seconds-pose['age_seconds'])
                    cycle=max(observation_seconds[-3:])+.1
                    if remaining<=cycle:
                        rows[-1]['calculated_final_hold_seconds']=remaining
                        if remaining:time.sleep(remaining)
                        sender._send(sender.X.KeyRelease,code);held=False
                        time.sleep(.15)
                        continue
                pose_tick=pose.get('client_uptime_ms',pose.get('observed_at',row['observed_at']))
                new_pose=pose_tick!=last_pose_tick
                if held and last_height is not None and new_pose:
                    stalled=stalled+1 if pose['height_yards']<=last_height+.1 else 0
                    if stalled>=6:raise RuntimeError('calculated ascent made no height progress')
                if new_pose:last_height=pose['height_yards'];last_pose_tick=pose_tick
                if not held:sender._send(sender.X.KeyPress,code);held=True
                time.sleep(.1)
            raise RuntimeError('calculated ascent did not reach route clearance')
        finally:
            if held:sender._send(sender.X.KeyRelease,code)
            sender.close()
            runtime.write(folder/f'smooth_ascent_{time.time_ns()}.json',{
                'identity':identity,'sender':sender.initialization,'started_at':started,
                'finished_at':time.time(),'ceiling_yards':ceiling,'observations':rows,
                'fixed_ascent_duration':None})

"""Keep the owned input sender alive while approaching one displayed marker."""
import fcntl
import math
import time
from . import inputs,runtime,native_control
from .observe import observe
from .boundaries import check_point


def walk(folder,target,*,flying=False,site_id=None):
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
            for index in range(60):
                row=observe(folder/f'approach_{index:02d}.png')
                m,a=row['movement'],row['archaeology']; world=a['world']
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                        or m['in_combat'] or m['on_taxi'] or a['casting'] or m['health_percent']<90
                        or not world or world['instance']!=target['instance']
                        or a['flying']!=flying or a['falling'] or a.get('swimming')):
                    raise RuntimeError('supervisor interruption or unavailable character during marker approach')
                if site_id is not None:check_point(site_id,world)
                distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
                error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
                receipts.append({'observed_at':row['observed_at'],'distance_yards':distance,'heading_error':error,
                                 'altitude_yards':a.get('altitude_yards'),'grounded':a.get('grounded')})
                tolerance=6 if flying else 4
                if distance<=tolerance: break
                if distance>750: raise RuntimeError('waypoint exceeds a local digsite route')
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


def descend(folder,target,*,site_id=None):
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
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead'] or m['in_combat']
                        or m['on_taxi'] or a['casting'] or m['health_percent']<90 or not world
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

"""Keep the owned input sender alive while approaching one displayed marker."""
import fcntl
import math
import time
from . import inputs,runtime,native_control
from .observe import observe


def walk(folder,target):
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
            for index in range(18):
                row=observe(folder/f'walk_{index:02d}.png')
                m,a=row['movement'],row['archaeology']; world=a['world']
                if ((runtime.ROOT/'run/stop_dig').exists() or not m['in_world'] or m['dead']
                        or m['in_combat'] or m['on_taxi'] or a['casting'] or m['health_percent']<90):
                    raise RuntimeError('supervisor interruption or unavailable character during marker approach')
                distance=math.hypot(target['north']-world['north'],target['west']-world['west'])
                error=(math.atan2(target['west']-world['west'],target['north']-world['north'])-m['facing_radians']+math.pi)%math.tau-math.pi
                receipts.append({'observed_at':row['observed_at'],'distance_yards':distance,'heading_error':error})
                if distance<=3: break
                hold('Up',abs(error)<.35)
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

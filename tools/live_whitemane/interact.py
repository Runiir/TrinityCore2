"""Use an ordinary interact binding or a rechecked named game tooltip."""
import time
from . import runtime, inputs, native_control
from .observe import observe
from .farm_actions import stationary


def search_points(maximum):
    # Small finds near the character's feet can lie between 40-pixel rows.
    # Interleave a denser local scan with the broader ground search.
    center=[(640,y) for y in range(260,621,24)]
    fine=[(x,y) for x in range(520,761,20) for y in range(400,621,20)]
    broad=[(x,y) for x in range(380,781,40) for y in range(220,661,40)]
    fine.sort(key=lambda p:(p[0]-640)**2+(p[1]-500)**2)
    broad.sort(key=lambda p:(p[0]-640)**2+(p[1]-430)**2)
    interleaved=[point for pair in zip(fine,broad) for point in pair]
    return list(dict.fromkeys(center+interleaved))[:maximum]


def use(folder,before,names,*,maximum=100):
    folder.mkdir(parents=True,exist_ok=False)
    ui=before['farm_ui'];soft=ui['soft_interact'];keys=ui['bindings']['INTERACTTARGET']
    # Game objects have a valid public softinteract name but UnitExists is false.
    if soft.get('name') in names and soft.get('enabled')=='3' and keys:
        fresh=observe(folder/'key_precheck.png');stationary(before,fresh)
        if fresh['farm_ui']['soft_interact'].get('name')!=soft['name']:
            raise RuntimeError('soft interact target changed before selected interaction')
        result={'source':'confirmed public soft interact name','name':soft['name'],
                'input':inputs.execute('World of Warcraft','key',{'key':keys[0],'hold':.15})}
        runtime.write(folder/'interaction.json',result);return result
    from tools.second_client import ctl
    from tools.client_compatibility import native_input_adapter
    import fcntl
    ctl._launcher_env=runtime.client_environment
    native_input_adapter.lab=runtime;native_input_adapter.control=native_control
    points=search_points(maximum)
    with (runtime.ROOT/'run/input.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        identity=inputs.focus('World of Warcraft');sender=native_input_adapter.Input()
        probes=[]
        try:
            for x,y in points:
                if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
                sender.move(x,y);time.sleep(.15)
                row=observe(folder/'hover.png');stationary(before,row)
                name=row['farm_ui'].get('tooltip');probes.append({'x':x,'y':y,'tooltip':name})
                if name not in names:continue
                sender.move(1000,750);time.sleep(.35)
                if observe(folder/'cleared.png')['farm_ui'].get('tooltip') in names:continue
                sender.move(x,y);time.sleep(.35)
                confirmed=observe(folder/'confirmed.png');stationary(before,confirmed)
                if confirmed['farm_ui'].get('tooltip')!=name:continue
                sender._send(sender.X.ButtonPress,3)
                try:time.sleep(.2)
                finally:sender._send(sender.X.ButtonRelease,3)
                result={'source':'rechecked public game tooltip','name':name,'point':[x,y],'identity':identity}
                runtime.write(folder/'interaction.json',result);return result
            raise RuntimeError('no matching public tooltip in bounded interaction search')
        finally:
            sender.close();runtime.write(folder/'probes.json',probes)

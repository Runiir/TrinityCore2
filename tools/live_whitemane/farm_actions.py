"""Recorded Laya UI choices with fresh public control and ownership checks."""
import math
import time
from . import runtime, inputs, laya_ui
from .observe import observe
from .archaeology_probe import command, ready


def stationary(before, fresh):
    if (runtime.ROOT/'run/stop_dig').exists():raise RuntimeError('supervisor stop requested')
    if not ready(fresh) or fresh['archaeology']['casting'] or before['runtime']!=fresh['runtime']:
        raise RuntimeError('character or owned client unavailable for UI input')
    a,b=before['archaeology']['world'],fresh['archaeology']['world']
    if not a or not b or a['instance']!=b['instance'] or math.hypot(a['north']-b['north'],a['west']-b['west'])>.2:
        raise RuntimeError('supervisor moved before selected UI input')


def click_choice(folder, before, collection, goal, expected=None):
    """Collection path names only visible controls; every control remains a choice."""
    folder.mkdir(parents=True,exist_ok=False)
    def rows(row):
        value=row['farm_ui']
        for part in collection:value=value.get(part,{})
        return (value if isinstance(value,list) else [value] if value.get('x') is not None else [])
    controls=rows(before)
    candidates={f'button_{i}':f"Click {c['label']}" for i,c in enumerate(controls) if c['enabled']}
    candidates['wait']='Wait without input'
    state={'goal':goal,'interface':'stationary, healthy, not casting',
           'buttons':{key:value for key,value in candidates.items() if key!='wait'}}
    choice,request,response=laya_ui.choose(state,'Select the visible button matching the goal. Otherwise wait.',candidates)
    record={'before':before,'choice':choice,'request':request,'response':response,'executed':False}
    runtime.write(folder/'decision.json',record)
    if choice=='wait':return record
    selected=controls[int(choice.split('_')[1])]
    if expected and any(selected.get(k)!=v for k,v in expected.items()):
        raise RuntimeError('Laya selected a control inconsistent with the requested goal')
    fresh=observe(folder/'precheck.png');stationary(before,fresh)
    if selected not in rows(fresh):raise RuntimeError('visible selected control changed before click')
    record['input']=inputs.execute('World of Warcraft','click',
        {'x':round(selected['x']*runtime.WIDTH),'y':round(selected['y']*runtime.HEIGHT),'button':1})
    time.sleep(.5)
    record.update(executed=True,selected=selected,after=observe(folder/'after.png'))
    runtime.write(folder/'decision.json',record)
    return record


def command_choice(folder, before, text, goal, description):
    folder.mkdir(parents=True,exist_ok=False)
    choice,request,response=laya_ui.choose({'goal':goal,'ready':ready(before),'command':text},
        'Choose the command when it fulfils the goal and the player is ready.',
        {'command':description,'wait':'Wait without input'})
    record={'before':before,'choice':choice,'request':request,'response':response,'executed':False}
    runtime.write(folder/'decision.json',record)
    if choice=='command':
        if before.get('setup_only'):
            from .observe import setup_movement
            if text!='/reload':raise RuntimeError('movement-only setup can only reload the observer')
            fresh=setup_movement(folder/'precheck.png')
            if (not ready(fresh) or before['runtime']!=fresh['runtime'] or
                    before['movement']['position']!=fresh['movement']['position'] or
                    (runtime.ROOT/'run/stop_dig').exists()):
                raise RuntimeError('owned stationary player changed before observer repair reload')
        else:
            fresh=observe(folder/'precheck.png');stationary(before,fresh)
        record['inputs']=command(text)
        record['executed']=True
        time.sleep(2)
    runtime.write(folder/'decision.json',record)
    return record

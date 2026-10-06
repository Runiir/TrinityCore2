"""Measured client camera zoom for an already selected Laya camera action."""
import json
import math
import time
from . import runtime,inputs
from .observe import observe


def goal(row):
    path=runtime.ROOT/'run/camera_zoom_preference.json'
    if not path.exists():return None
    value=json.loads(path.read_text())
    return value['zoom'] if value.get('runtime')==row.get('runtime') else None


def safe(before,after):
    a,m=after['archaeology'],after['movement']
    camera=(after.get('farm_ui') or {}).get('camera_input') or {}
    return (not (runtime.ROOT/'run/stop_dig').exists() and after.get('runtime')==before.get('runtime')
        and m.get('in_world') and not m.get('dead') and not m.get('in_combat')
        and not m.get('on_taxi') and m.get('speed',0)==0 and not a.get('casting')
        and not a.get('falling') and not camera.get('right_down') and not camera.get('mouselooking'))


def restore(folder,row,desired,*,save_preset=None):
    """Calibrate native wheel increments against fresh public zoom feedback."""
    current=(row.get('farm_ui') or {}).get('camera_zoom')
    result={'before_zoom':current,'desired_zoom':desired,'inputs':[],'confirmed':False,
        'method':'native mouse wheel; no chat or saved-view commands'}
    if (current is None or desired is None or not math.isfinite(desired) or not 0<=desired<=50):return result
    if abs(current-desired)<=1:
        result.update(confirmed=True,after_zoom=current);return result
    if not safe(row,row):return result
    folder.mkdir(parents=True,exist_ok=False)
    deadline=time.monotonic()+4;gain=None;after=row
    while time.monotonic()<deadline:
        fresh=observe(folder/'precheck.png')
        if not safe(row,fresh):
            result['interrupted']=True;break
        current=(fresh.get('farm_ui') or {}).get('camera_zoom')
        if current is None:break
        result['after_zoom']=current
        error=desired-current
        if abs(error)<=1:result['confirmed']=True;break
        # The first notch measures this client's wheel scale. Later batches
        # approach the target using that observed scale rather than assuming it.
        count=1 if gain is None else max(1,min(8,math.floor(abs(error)/gain)))
        steps=count if error>0 else -count
        period=1/max(1,fresh['farm_ui'].get('frame_rate') or 30)
        result['inputs'].append(inputs.execute('World of Warcraft','scroll',{
            'steps':steps,'frame_period_seconds':period}))
        last_zoom=current;last_sequence=fresh['farm_ui'].get('sequence');stable=0
        settle=min(deadline,time.monotonic()+1)
        changed=False
        while time.monotonic()<settle:
            after=observe(folder/'feedback.png')
            if not safe(row,after):result['interrupted']=True;break
            zoom=(after.get('farm_ui') or {}).get('camera_zoom')
            sequence=after['farm_ui'].get('sequence')
            result['after_zoom']=zoom
            if zoom is not None:
                changed=changed or abs(zoom-current)>.05
                if abs(zoom-desired)<=1:result['confirmed']=True;break
                if sequence!=last_sequence:
                    stable=stable+1 if abs(zoom-last_zoom)<.05 else 0
                    last_sequence=sequence;last_zoom=zoom
                    if changed and stable>=2:break
            time.sleep(.05)
        if result['confirmed'] or result.get('interrupted'):break
        if not changed:
            result['reason']='wheel produced no zoom progress; possible camera collision or zoom limit';break
        change=result['after_zoom']-current
        if change*steps<=0:
            result['reason']='camera zoom changed against the selected wheel direction';break
        gain=abs(change/steps);result['measured_yards_per_notch']=gain
        # Avoid repeatedly reversing the wheel around an unreachable target.
        if (desired-result['after_zoom'])*error<0:
            result['reason']='wheel crossed the zoom target';break
    runtime.write(folder/'zoom.json',result)
    return result


def choose_restore(folder,row,desired):
    """Choose a native zoom adjustment or wait, without a text-command option."""
    from . import laya_ui
    folder.mkdir(parents=True,exist_ok=False)
    choice,request,response=laya_ui.choose({'goal':'Restore the archaeology camera field of view',
        'camera_zoom':row.get('farm_ui',{}).get('camera_zoom'),'desired_zoom':desired},
        'Adjust the camera with the mouse wheel when ready, or wait.',
        {'zoom':'Use the mouse wheel to reach the requested zoom','wait':'Wait without input'})
    result={'choice':choice,'request':request,'response':response,'executed':False}
    if choice=='zoom':
        result['zoom']=restore(folder/'wheel',row,desired)
        result['executed']=bool(result['zoom']['inputs'])
    runtime.write(folder/'decision.json',result);return result

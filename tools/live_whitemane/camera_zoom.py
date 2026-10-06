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


def restore(folder,row,desired,*,save_preset=None):
    current=(row.get('farm_ui') or {}).get('camera_zoom')
    result={'before_zoom':current,'desired_zoom':desired,'inputs':[],'confirmed':False}
    if (current is None or desired is None or not math.isfinite(desired) or not 0<=desired<=50):return result
    if abs(current-desired)<=1:
        result.update(confirmed=True,after_zoom=current);return result
    a,m=row['archaeology'],row['movement']
    if (not m.get('in_world') or m.get('dead') or m.get('in_combat') or m.get('speed',0)>0
            or a.get('casting') or a.get('falling')):return result
    folder.mkdir(parents=True,exist_ok=False)
    period=1/max(1,(row.get('farm_ui') or {}).get('frame_rate') or 30)
    fn='CameraZoomOut' if desired>current else 'CameraZoomIn'
    result['inputs'].append(inputs.execute('World of Warcraft','command',{
        'text':f'/run {fn}({abs(desired-current):.2f})','frame_period_seconds':period}))
    deadline=time.monotonic()+3
    while time.monotonic()<deadline:
        after=observe(folder/'feedback.png')
        result['after_zoom']=(after.get('farm_ui') or {}).get('camera_zoom')
        if (after['runtime']!=row['runtime'] or after['movement'].get('in_combat')
                or after['movement'].get('speed',0)>0 or after['archaeology'].get('casting')):break
        if result['after_zoom'] is not None and abs(result['after_zoom']-desired)<=1:
            result['confirmed']=True;break
        time.sleep(.1)
    if result['confirmed'] and save_preset is not None:
        result['inputs'].append(inputs.execute('World of Warcraft','command',{
            'text':f'/run if SaveView then SaveView({save_preset}) end','frame_period_seconds':period}))
    runtime.write(folder/'zoom.json',result)
    return result

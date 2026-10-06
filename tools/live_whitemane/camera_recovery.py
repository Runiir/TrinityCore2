"""Activate the installed camera macro; the actor cannot edit or type commands."""
import json
import time
from pathlib import Path
from . import runtime,camera_zoom
from .observe import observe
from .farm_actions import click_choice

NAME='ArchaeologyView'
PRESET=3
ZOOM=20
BODY='/run MouselookStop();ResetView(3);SetView(3)\n/run CameraZoomOut(20)'


def use(folder,row):
    installed=((row.get('farm_ui') or {}).get('macro') or {}).get('installed') or {}
    if installed.get('name')!=NAME or installed.get('body')!=BODY:
        raise RuntimeError('selected client action invalidated: installed ArchaeologyView macro changed')
    result=click_choice(folder,row,('camera_macros',),
        'Click ArchaeologyView to recover a poor camera angle and restore a wide view',
        expected={'label':NAME},matching_only=True)
    if result['executed']:
        # A separate reset invalidates any portal retry's retained camera pose.
        (runtime.ROOT/'run/camera_presets.json').unlink(missing_ok=True)
    return result


def apply_request(folder,row):
    path=runtime.ROOT/'run/camera_macro_request.json'
    if not path.exists():return False
    request=json.loads(path.read_text());a,m=row['archaeology'],row['movement']
    if request.get('runtime')!=row.get('runtime'):return False
    if (not m['in_world'] or m['dead'] or m['in_combat'] or m.get('speed',0)>0
            or any(a.get(k) for k in ('casting','flying','falling'))):return False
    if time.time()-request.get('last_attempt',0)<.5:return False
    request['last_attempt']=time.time()
    installed=(row['farm_ui'].get('macro') or {}).get('installed') or {}
    bars=row['farm_ui'].get('camera_macros') or []
    if installed.get('name')!=NAME or installed.get('body')!=BODY or not bars:
        request.update(completed=False,reason='Existing ArchaeologyView macro required; text-box input is disabled')
        runtime.write(Path(request['receipt']),request);runtime.write(path,request)
        return False
    try:
        selection=use(folder/'camera_macro_reset',row)
        request['selection']=selection
        if selection['executed']:
            fresh=observe(folder/'camera_macro_feedback.png')
            request['zoom_feedback']=camera_zoom.restore(folder/'camera_macro_zoom',fresh,ZOOM)
            request['completed']=request['zoom_feedback']['confirmed']
            request['macro_confirmed']=installed;request['bar_confirmed']=bars
    except RuntimeError as error:
        request['retry_reason']=str(error);selection={'executed':False}
    runtime.write(Path(request['receipt']),request)
    if request.get('completed'):path.unlink(missing_ok=True)
    else:runtime.write(path,request)
    return selection['executed']

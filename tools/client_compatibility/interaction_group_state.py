"""Read-only group contents and visible unit-frame validation on owned clients."""
import argparse
from contextlib import redirect_stdout
from io import StringIO
import json
from pathlib import Path
import time
from PIL import Image
from . import lab_runtime as lab
from .interaction_trial import Trial
from .interaction_social import actor
from .observation.interactions import decode_image


def capture(trial,label):
    from tools.second_client import ctl
    state,state_frame=trial.observe(label+'_state')
    path=trial.out/(label+'_units.png');deadline=time.monotonic()+28
    while True:
        with redirect_stdout(StringIO()):ctl.shot(str(path))
        with Image.open(path) as image:data=decode_image(image)
        if data.get('mode')=='group':break
        if time.monotonic()>deadline:raise RuntimeError('group observation deadline exceeded')
        time.sleep(.1)
    if data.get('guid')!=trial.guid or data.get('build')!=60895:
        raise RuntimeError('group observation belongs to another client')
    frame={'file':path.name,'sha256':lab.sha256(path),'monitor':state_frame['monitor']}
    units=data.get('units') or [];frames=data.get('frames') or []
    expected={'Harnessone','Harnesstwo'}
    valid=len(units)==2 and {u.get('name') for u in units}==expected and all(
        u.get('exists') and u.get('connected') and u.get('class')=='WARRIOR' and u.get('level',0)>0
        and 0<u.get('health',0)<=u.get('max_health',0) for u in units)
    rendered=bool(frames) and all(f.get('health_bar') and f.get('high',0)>0
        and f.get('value',0)>0 for f in frames)
    facts={'state':state,'group':data,'state_frame':state_frame,'frame':frame,
        'unit_contents_valid':valid,'visible_health_bars_valid':rendered}
    lab.private_write(trial.out/(label+'.json'),json.dumps(facts,indent=2)+'\n')
    return facts


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--require-pass',action='store_true');args=p.parse_args()
    args.output.mkdir(parents=True,exist_ok=False,mode=0o700)
    summary={'schema':'client442_group_display_v1','started_at':time.time(),'actors':{},'completed':False,'failure':None}
    try:
        for name in ['primary','scout']:
            with actor(name):
                trial=Trial(args.output/name)
                try:
                    trial.clean_panels();facts=capture(trial,'group_display')
                    summary['actors'][name]={key:facts[key] for key in ['unit_contents_valid','visible_health_bars_valid']}
                    trial.receipt['group_display']=facts;trial.receipt['completed']=True
                finally:trial.receipt['finished_at']=time.time();trial.persist()
        summary['completed']=all(all(a.values()) for a in summary['actors'].values())
        if args.require_pass and not summary['completed']:raise RuntimeError('group contents or visible health bars are invalid')
    except BaseException as e:summary['failure']=f'{type(e).__name__}: {e}';raise
    finally:
        summary['finished_at']=time.time();lab.private_write(args.output/'cohort.json',json.dumps(summary,indent=2)+'\n')
        print(json.dumps(summary))


if __name__=='__main__':main()

"""One real artifact regression through the native bridge, using code decisions."""
import argparse
import json
from pathlib import Path
import subprocess
import time
from PIL import Image
from . import lab_runtime as lab,owned_input,archaeology_inputs as inputs,archaeology_policy as policy
from . import site_boundaries
from .collision_recovery import Recovery
from .observation.archaeology import Observer,collected


def run(out,maximum_steps):
    if subprocess.check_output(['git','status','--porcelain'],cwd=lab.REPO,text=True):
        raise RuntimeError('commit experiment code/configs before the native archaeology probe')
    bridge=lab.owned_process('modern_world')
    if not bridge or bridge.get('engine')!='cpp':raise RuntimeError('owned C++ bridge is required')
    if not 1<=maximum_steps<=120:raise ValueError('invalid archaeology probe step bound')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    observer=Observer();recovery=Recovery();history=[];finds=[];latest=out/'latest.png'
    receipt={'schema':'client442_native_archaeology_probe_v1','started_at':time.time(),
        'controller':'deterministic_code_regression','model_called':False,
        'actor':{'name':lab.actor_name(),'guid':observer.guid,'session':observer.session},
        'bridge':bridge,'monitor':owned_input.focus(),'steps':history,'finds':finds,
        'private_next_find_coordinates_used':False,'mounted_moves':False,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'completed':False,'failure':None,'frames':[]}
    try:
        for index in range(maximum_steps):
            movement,extra=inputs.screenshot(latest);tcp=observer.poll(movement['facing_radians'])
            if not movement['in_world'] or movement['health_percent']<50 or any(
                movement[k] for k in ['dead','in_combat','on_taxi']):raise RuntimeError('unsafe regression state')
            if any(extra[k] for k in ['mounted','flying','falling','swimming']):
                raise RuntimeError('artifact regression requires dry grounded feet')
            site=site_boundaries.active_site(extra['world_map'],tcp['player']['position'],extra['digsite_ids'])
            if not all(site_boundaries.contains(site['polygon'],f['position']) for f in tcp['finds']):
                raise RuntimeError('visible artifact is outside its assigned public boundary')
            state=policy.observed_state(movement,extra,tcp,history);action=policy.label(state)
            if len(history)>=3 and action=='survey' and all(s['action']=='survey' for s in history[-3:]):
                raise RuntimeError('three surveys without a fresh instrument or artifact')
            if len(history)>=2 and action=='loot' and all(s['action']=='loot' for s in history[-2:]):
                raise RuntimeError('two clicks without confirmed native collection')
            recovery.update(history,tcp)
            frame=out/f'step_{index:03d}.webp'
            with Image.open(latest) as image:image.save(frame,lossless=True)
            receipt['frames'].append({'file':frame.name,'sha256':lab.sha256(frame)})
            step={'index':index,'started_at':time.time(),'session':tcp['session'],'site':site['id'],
                'action':action,'state':state,'tcp':tcp,'execution_status':'started'}
            history.append(step);lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
            if action=='survey':
                owned_input.Inputs().key('2');time.sleep(.25)
                cast_path=out/f'survey_cast_{index:03d}.png'
                _,cast=inputs.screenshot(cast_path)
                step['input']={'key':'2','cast_bar_addon_seen':cast['casting'],'frame':cast_path.name,
                    'frame_sha256':lab.sha256(cast_path)}
                time.sleep(2)
            else:
                step['input']=inputs.execute(action,tcp,latest,recovery.for_action(action),
                    mounted_moves=False,object_observer=observer)
            step.update(execution_status='completed',finished_at=time.time())
            if action=='loot':
                confirmation=collected(observer.session,step['started_at'])
                if confirmation:
                    finds.append(confirmation);receipt['completed']=True;break
            lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
            print(json.dumps({'step':index,'action':action,'finds':len(finds)}),flush=True)
        if not receipt['completed']:raise RuntimeError('step budget exhausted without native fragment collection')
    except (Exception,KeyboardInterrupt) as error:
        receipt['failure']=f'{type(error).__name__}: {error}'
    finally:
        receipt['finished_at']=time.time();lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
        latest.unlink(missing_ok=True)
        print(json.dumps({'completed':receipt['completed'],'failure':receipt['failure']}),flush=True)
    return receipt


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--maximum-steps',type=int,default=80)
    args=parser.parse_args();run(args.output.resolve(),args.maximum_steps)


if __name__=='__main__':main()

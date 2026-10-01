"""A restartable, bounded live trial of Laya's adapted archaeology decisions."""
import argparse
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from PIL import Image
from . import lab_runtime as lab,archaeology_policy as policy,archaeology_inputs as inputs,owned_input
from .archaeology_model_service import ENDPOINT,PORT
from .observation.archaeology import Observer,collected


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--finds',type=int,default=1);parser.add_argument('--maximum-steps',type=int,default=120)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    monitor=json.loads((lab.ROOT/'evidence/client_monitor.json').read_text())
    client=lab.owned_process('client')
    if not client or not monitor['second_monitor_verified'] or monitor['pid']!=client['pid']:raise RuntimeError('owned client monitor unverified')
    owned_input.focus()
    with urllib.request.urlopen(f'http://127.0.0.1:{PORT}/health',timeout=5) as r:identity=json.load(r)
    observer=Observer();history=[];finds=[];started=time.time();latest=out/'latest.png';failure=None
    receipt={'schema':'client442_laya_live_archaeology_v2','model':identity,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'started_at':started,'teacher_mouse_annotations':0,'manual_gameplay_interventions':0,
        'private_next_find_coordinates_used':False,'frames':[],'finds':finds,'steps':history}
    try:
        for index in range(args.maximum_steps):
            movement,extra=inputs.screenshot(latest);tcp=observer.poll(movement['facing_radians'])
            if not movement['in_world'] or any(movement[k] for k in ['dead','in_combat','on_taxi']):raise RuntimeError('character unavailable')
            if extra['mounted'] or extra['flying']:raise RuntimeError('archaeology trial requires landing and dismounting')
            state=policy.observed_state(movement,extra,tcp,history)
            if len(history)>=3 and all(s['action']=='survey' for s in history[-3:]):raise RuntimeError('Survey produced no fresh instrument or find three times')
            if len(history)>=2 and all(s['action']=='loot' for s in history[-2:]):raise RuntimeError('two physical loot attempts produced no collection')
            if history and len(history)>=4 and all(s['action']=='observe' for s in history[-4:]):raise RuntimeError('repeated waiting without progress')
            request={'model':identity['model'],'state':state}
            req=urllib.request.Request(ENDPOINT,data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=15) as r:response=json.load(r)
            if response['revision']!=identity['revision'] or response['model']!=identity['model']:raise ValueError('decision model identity changed')
            action=response['answers']['action']['choice']
            if action not in policy.ACTIONS or any(b['truncated_fields'] for b in response['token_budget'].values()):raise ValueError('invalid model decision')
            frame=out/f'step_{index:03d}.webp'
            with Image.open(latest) as img:img.save(frame,lossless=True)
            receipt['frames'].append({'file':frame.name,'sha256':lab.sha256(frame)})
            begin=time.time();executed=inputs.execute(action,tcp,latest)
            step={'index':index,'started_at':begin,'time':time.time(),'session':tcp['session'],
                'movement':movement,'travel':extra,'tcp':tcp,'state':state,'request':request,'response':response,
                'action':action,'policy_match':action==policy.label(state),'input':executed}
            history.append(step)
            if action=='loot':
                confirmation=collected(tcp['session'],begin)
                if confirmation:
                    finds.append({**confirmation,'step':index,'world_position':extra['world_position'],
                        'digsite_ids':extra['digsite_ids'],'mouse_localization':'ordinary_game_tooltip_hover'})
            lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
            print(json.dumps({'step':index,'action':action,'finds':len(finds),'policy_match':step['policy_match']}),flush=True)
            if len(finds)>=args.finds:break
        if len(finds)<args.finds:raise RuntimeError('action budget ended before the requested find count')
    except (Exception,KeyboardInterrupt) as error:
        failure=f'{type(error).__name__}: {error}'
        print(failure,flush=True)
    receipt.update(finished_at=time.time(),completed=len(finds)>=args.finds,failure=failure,
        live_action_agreement=sum(s['policy_match'] for s in history)/len(history) if history else None)
    lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
    latest.unlink(missing_ok=True)
    print(json.dumps({k:receipt[k] for k in ['completed','failure','live_action_agreement']},indent=2),flush=True)


if __name__=='__main__':main()

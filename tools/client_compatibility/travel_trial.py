"""Execute an attributable public route using Laya and physical client inputs."""
import argparse
import json
from pathlib import Path
import math
import subprocess
import time
import urllib.request
from . import lab_runtime as lab,owned_input,travel_policy as policy
from .observation import taxi
from .observation.transport import Observer

ENDPOINT='http://127.0.0.1:8003/v1/systemone'


def state(leg,movement,extra,facts,ui):
    distance=math.dist(facts['position'][:2],leg['position'][:2]) if leg.get('position') else None
    reached=facts['map']==leg['destination_map'] if leg['mode']=='portal' else (
        facts['map']==leg['map'] and distance is not None and distance<12 and
        abs(facts['position'][2]-leg['position'][2])<8)
    return {'mode':leg['mode'],'available':movement['in_world'] and not facts['transferring'] and
            not any(movement[k] for k in ['dead','in_combat']),
        'casting':extra['casting'],'on_taxi':movement['on_taxi'],
        'mounted':extra['mounted'],'flying':extra['flying'],'falling':extra['falling'],
        'at_route_height':facts['position'][2]>=leg.get('ceiling',float('inf'))-3,
        'near_destination':distance is not None and distance<leg.get('arrival_radius',5),'destination_reached':reached,
        'taxi_map_open':bool(ui['nodes'])}


def run(plan,out,maximum_steps=180):
    from PIL import Image
    from . import travel_inputs,archaeology_inputs
    out.mkdir(parents=True,exist_ok=False);owned_input.focus()
    with urllib.request.urlopen('http://127.0.0.1:8003/health') as r:identity=json.load(r)
    observer=Observer();history=[];finished=[];latest=out/'latest.png';failure=None
    receipt={'schema':'client442_laya_travel_v1','started_at':time.time(),'model':identity,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'plan':plan,'steps':history,'legs_completed':finished,'frames':[],
        'manual_gameplay_interventions':0,'teacher_mouse_annotations':0,'private_next_find_coordinates_used':False}
    leg_index=0;stalled=0;last_metric=None
    try:
        for index in range(maximum_steps):
            leg=plan['legs'][leg_index]
            deadline=time.monotonic()+20
            while True:
                facts=observer.poll()
                try:movement,extra=archaeology_inputs.screenshot(latest);break
                except ValueError:
                    if not facts['transferring'] or time.monotonic()>deadline:raise
                    time.sleep(.25)
            with Image.open(latest) as image:ui=taxi.decode_image(image)
            s=state(leg,movement,extra,facts,ui)
            if movement['dead'] or movement['in_combat']:raise RuntimeError('unsafe travel state')
            request={'model':identity['model'],'state':policy.model_state(s)}
            req=urllib.request.Request(ENDPOINT,data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=15) as r:response=json.load(r)
            if response['model']!=identity['model'] or response['revision']!=identity['revision']:raise RuntimeError('travel model identity changed')
            action=response['answers']['action']['choice']
            if action not in policy.ACTIONS or any(v['truncated_fields'] for v in response['token_budget'].values()):raise RuntimeError('invalid travel decision')
            frame=out/f'step_{index:03d}.webp'
            with Image.open(latest) as image:image.save(frame,lossless=True)
            receipt['frames'].append({'file':frame.name,'sha256':lab.sha256(frame)})
            if action=='arrived' and (policy.label(s)!='arrived' or not s['destination_reached']):
                raise RuntimeError('model claimed arrival before public observations confirmed it')
            input_receipt=travel_inputs.execute(action,leg,facts,extra,observer,latest)
            history.append({'index':index,'time':time.time(),'leg':leg_index,'state':s,'movement':movement,
                'travel':extra,'facts':facts,'ui':ui,'request':request,'response':response,'action':action,
                'policy_match':action==policy.label(s),'input':input_receipt})
            print(json.dumps({'step':index,'leg':leg_index,'action':action,'position':facts['position'][:3]}),flush=True)
            if action=='arrived':
                finished.append({'leg':leg_index,'name':leg['id'],'time':time.time(),'facts':facts})
                leg_index+=1;stalled=0;last_metric=None
                if leg_index==len(plan['legs']):break
            else:
                metric=(tuple(round(v) for v in facts['position'][:3]),extra['mounted'],extra['flying'],s['taxi_map_open'],facts['map'],facts['transferring'])
                stalled=stalled+1 if metric==last_metric else 0;last_metric=metric
                if stalled>=8:raise RuntimeError('travel made no observable progress for eight decisions')
            lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
        if leg_index<len(plan['legs']):raise RuntimeError('travel action budget exhausted')
    except (Exception,KeyboardInterrupt) as e:failure=f'{type(e).__name__}: {e}'
    receipt.update(finished_at=time.time(),completed=leg_index==len(plan['legs']),failure=failure)
    lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'completed':receipt['completed'],'failure':failure}),flush=True)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--maximum-steps',type=int,default=180)
    args=p.parse_args();run(json.loads(args.plan.read_text()),args.output.resolve(),args.maximum_steps)


if __name__=='__main__':main()

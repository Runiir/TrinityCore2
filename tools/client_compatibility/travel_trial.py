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


def progress_metric(action,leg,facts,extra,s):
    """Measure progress toward the phase goal; unrelated XY jitter is no progress."""
    if action=='takeoff':return action,max(0,leg['ceiling']-facts['position'][2])
    if action=='land':return action,max(0,facts['position'][2]-leg['position'][2])
    if action in ['cruise','portal']:return action,math.dist(facts['position'][:2],leg['position'][:2])
    return (action,facts['map'],extra['mounted'],extra['flying'],extra['casting'],s['taxi_map_open']),None


def state(leg,movement,extra,facts,ui):
    distance=math.dist(facts['position'][:2],leg['position'][:2]) if leg.get('position') else None
    transfer_goal='destination_map' in leg
    reached=facts['map']==leg['destination_map'] if transfer_goal else (
        facts['map']==leg['map'] and distance is not None and distance<leg.get('arrival_radius',12) and
        abs(facts['position'][2]-leg['position'][2])<leg.get('landing_height_tolerance',8))
    airborne=extra['flying'] or extra['falling']
    near=bool(reached) or distance is not None and distance<leg.get('arrival_radius',5)
    if leg['mode']=='flight' and (transfer_goal or not airborne):near=bool(reached)
    return {'mode':leg['mode'],'available':movement['in_world'] and not facts['transferring'] and
            not any(movement[k] for k in ['dead','in_combat']),
        'casting':extra['casting'],'on_taxi':movement['on_taxi'],
        'mounted':extra['mounted'],'flying':extra['flying'],'falling':extra['falling'],
        'at_route_height':facts['position'][2]>=leg.get('ceiling',float('inf'))-3,
        'near_destination':near,'destination_reached':reached,
        'taxi_map_open':bool(ui['nodes'])}


def run(plan,out,maximum_steps=180):
    from PIL import Image
    from . import travel_inputs,archaeology_inputs
    out.mkdir(parents=True,exist_ok=False);owned_input.focus()
    with urllib.request.urlopen('http://127.0.0.1:8003/health') as r:identity=json.load(r)
    observer=Observer();history=[];finished=[];latest=out/'latest.png';failure=None
    receipt={'schema':'client442_laya_travel_v1','started_at':time.time(),'model':identity,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'plan':plan,'steps':history,'legs_completed':finished,'frames':[],'safety_recoveries':[],
        'rejected_decisions':[],
        'manual_gameplay_interventions':0,'teacher_mouse_annotations':0,'private_next_find_coordinates_used':False}
    leg_index=0;stalled=0;last_metric=None;landing_cycles=0;landing_started=False
    try:
        for index in range(maximum_steps):
            leg=plan['legs'][leg_index]
            deadline=time.monotonic()+20
            while True:
                facts=observer.poll()
                recent_transfer=any(e['time']>time.time()-20 for e in facts['transfer_events'][-4:])
                try:
                    movement,extra=archaeology_inputs.screenshot(latest)
                    if extra['world_position_available'] and extra['world_map']!=facts['map']:
                        raise ValueError('addon has not loaded the native destination map')
                    break
                except ValueError:
                    if not (facts['transferring'] or recent_transfer) or time.monotonic()>deadline:raise
                    time.sleep(.25)
            with Image.open(latest) as image:ui=taxi.decode_image(image)
            if movement['in_combat']:
                from .combat_recovery import withdraw
                receipt['safety_recoveries'].append(withdraw(movement,extra,facts,observer,latest))
                continue
            if leg['mode']=='flight' and not leg.get('trigger'):
                from .client_floor_probe import needed as needs_client_floor,verify as verify_client_floor
                if needs_client_floor(facts,extra,leg):
                    receipt['safety_recoveries'].append(verify_client_floor(leg,observer,latest))
                    landing_started=False
                    continue
                from .ground_landing import needed,finish
                if needed(facts,extra,leg):
                    from tools.second_client import ctl
                    ctl._launcher_env=lab.client_environment
                    receipt['safety_recoveries'].append(finish(ctl.Input(),leg,observer,latest))
                    landing_started=False
                    continue
                from .landing_recovery import wrong_floor,nudge
                if wrong_floor(facts,extra,leg) and extra['mounted']:
                    from tools.second_client import ctl
                    ctl._launcher_env=lab.client_environment
                    receipt['safety_recoveries'].append(nudge(ctl.Input(),leg,observer,latest,extra))
                    landing_started=False
                    continue
            if (leg['mode']=='flight' and not leg.get('trigger') and extra['flying']
                and not leg.get('landing_avoidance_frozen') and facts['position'][2]>leg['position'][2]+15
                and math.dist(facts['position'][:2],leg['position'][:2])<60):
                from .hostile_avoidance import landing
                goal,avoidance=landing(facts['map'],leg['position'],facts['visible_hostiles'],extra['digsite_ids'],facts['position'],
                    progress=leg.get('survey_progress'),player_level=observer.player_level,
                    healthy=movement['health_percent']>=80)
                if avoidance:
                    leg.setdefault('landing_avoidance',[]).append(avoidance);leg['position']=goal
            s=state(leg,movement,extra,facts,ui)
            if movement['dead'] or movement['in_combat']:raise RuntimeError('unsafe travel state')
            request={'model':identity['model'],'state':policy.model_state(s)}
            req=urllib.request.Request(ENDPOINT,data=json.dumps(request).encode(),headers={'Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=15) as r:response=json.load(r)
            if response['model']!=identity['model'] or response['revision']!=identity['revision']:raise RuntimeError('travel model identity changed')
            action=response['answers']['action']['choice']
            if action not in policy.ACTIONS or any(v['truncated_fields'] for v in response['token_budget'].values()):raise RuntimeError('invalid travel decision')
            if action!=policy.label(s):
                receipt['rejected_decisions'].append({'index':index,'time':time.time(),'leg':leg_index,
                    'state':s,'movement':movement,'travel':extra,'facts':facts,'request':request,
                    'response':response,'expected':policy.label(s)})
                raise RuntimeError(f'model selected {action} against the observed travel preconditions')
            if action=='land':landing_started=True
            elif action=='takeoff' and landing_started:
                landing_cycles+=1;landing_started=False
                if landing_cycles>=3:raise RuntimeError('three failed landings returned to ascent without arrival')
            frame=out/f'step_{index:03d}.webp'
            with Image.open(latest) as image:image.save(frame,lossless=True)
            receipt['frames'].append({'file':frame.name,'sha256':lab.sha256(frame)})
            if action=='arrived' and (policy.label(s)!='arrived' or not s['destination_reached']):
                raise RuntimeError('model claimed arrival before public observations confirmed it')
            step={'index':index,'time':time.time(),'leg':leg_index,'state':s,'movement':movement,
                'travel':extra,'facts':facts,'ui':ui,'request':request,'response':response,'action':action,
                'policy_match':action==policy.label(s),'input':None,'execution_status':'started'}
            history.append(step);lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
            if action in ['land','dismount']:leg['landing_avoidance_frozen']=True
            step.update(input=travel_inputs.execute(action,leg,facts,extra,observer,latest,
                intersite=plan.get('schema')=='client442_public_site_route_v1'),execution_status='completed')
            print(json.dumps({'step':index,'leg':leg_index,'action':action,'position':facts['position'][:3]}),flush=True)
            if action=='arrived':
                finished.append({'leg':leg_index,'name':leg['id'],'time':time.time(),'facts':facts})
                leg_index+=1;stalled=0;last_metric=None;landing_cycles=0;landing_started=False
                if leg_index==len(plan['legs']):break
            else:
                metric=progress_metric(action,leg,facts,extra,s)
                improving=last_metric is None or metric[0]!=last_metric[0] or (
                    metric[1] is not None and metric[1]<last_metric[1]-.5)
                # An explicitly bounded collision escape may move sideways
                # before climbing. Its own limit prevents indefinite detours.
                improving=improving or bool((step['input'].get('collision_recovery') or {}).get('horizontal_progress',0)>=1.5)
                stalled=0 if improving else stalled+1
                if improving:last_metric=metric
                if stalled>=8:raise RuntimeError('travel made no observable progress for eight decisions')
            lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
        if leg_index<len(plan['legs']):raise RuntimeError('travel action budget exhausted')
    except (Exception,KeyboardInterrupt) as e:failure=f'{type(e).__name__}: {e}'
    if failure and history and history[-1]['execution_status']=='started':
        history[-1].update(execution_status='failed',input_error=failure)
    receipt.update(finished_at=time.time(),completed=leg_index==len(plan['legs']),failure=failure)
    lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
    print(json.dumps({'completed':receipt['completed'],'failure':failure}),flush=True)
    return receipt


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True);p.add_argument('--maximum-steps',type=int,default=180)
    args=p.parse_args();run(json.loads(args.plan.read_text()),args.output.resolve(),args.maximum_steps)


if __name__=='__main__':main()

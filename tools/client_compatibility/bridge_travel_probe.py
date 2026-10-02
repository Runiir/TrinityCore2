"""Bounded code flight for native-bridge regression, without model endpoints."""
import json
import subprocess
import time
from PIL import Image
from . import archaeology_inputs,lab_runtime as lab,owned_input,travel_inputs,travel_policy
from .observation import taxi
from .observation.transport import Observer
from .travel_trial import state,progress_metric


def run(plan,out,maximum_steps=30):
    from . import green_flight,ground_landing,client_floor_probe,landing_recovery
    if not 1<=maximum_steps<=60 or not plan.get('green_terrain_recovery') or len(plan['legs'])!=1:
        raise ValueError('diagnostic flight requires one bounded green recovery leg')
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    observer=Observer();leg=plan['legs'][0];leg['site_id']=plan['green_terrain_recovery']['site_id']
    latest=out/'latest.png';steps=[];frames=[];stalled=0;last_metric=None;landing_started=False
    receipt={'schema':'client442_code_flight_regression_v1','started_at':time.time(),
        'controller':'deterministic_code_regression','model_called':False,'plan':plan,
        'code_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=lab.REPO,text=True).strip(),
        'actor':{'name':lab.actor_name(),'guid':observer.guid,'session':observer.session},
        'monitor':owned_input.focus(),'bridge':lab.owned_process('modern_world'),
        'steps':steps,'frames':frames,'completed':False,'failure':None,
        'private_next_find_coordinates_used':False}
    if not receipt['bridge'] or receipt['bridge']['engine']!='cpp':
        raise RuntimeError('diagnostic flight requires the owned native bridge')
    try:
        for index in range(maximum_steps):
            movement,extra=archaeology_inputs.screenshot(latest);facts=observer.poll()
            green_flight.check_position(plan['green_terrain_recovery'],facts['position'],facts['map'])
            if not movement['in_world'] or movement['health_percent']<50 or any(
                movement[k] for k in ['dead','in_combat','on_taxi']):
                raise RuntimeError('diagnostic recovery flight interrupted by unsafe state')
            with Image.open(latest) as image:
                ui=taxi.decode_image(image);frame=out/f'step_{index:03d}.webp';image.save(frame,lossless=True)
            frames.append({'file':frame.name,'sha256':lab.sha256(frame)})
            current=state(leg,movement,extra,facts,ui);action=travel_policy.label(current)
            if action=='land':landing_started=True
            step={'index':index,'time':time.time(),'facts':facts,'state':current,'action':action,
                'execution_status':'started'};steps.append(step)
            lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
            if landing_started and client_floor_probe.needed(facts,extra,leg):
                step['input']=client_floor_probe.verify(leg,observer,latest)
            elif landing_started and ground_landing.needed(facts,extra,leg):
                step['input']=ground_landing.finish(owned_input.Inputs(),leg,observer,latest)
            elif landing_started and extra['mounted'] and landing_recovery.wrong_floor(facts,extra,leg):
                step['input']=landing_recovery.nudge(owned_input.Inputs(),leg,observer,latest,extra)
            else:step['input']=travel_inputs.execute(action,leg,facts,extra,observer,latest)
            step['execution_status']='completed';after=observer.poll()
            green_flight.check_position(plan['green_terrain_recovery'],after['position'],after['map'])
            if action=='arrived':
                receipt['completed']=True;break
            metric=progress_metric(action,leg,after,extra,current)
            improving=last_metric is None or metric[0]!=last_metric[0] or (
                metric[1] is not None and metric[1]<last_metric[1]-.5)
            stalled=0 if improving else stalled+1
            if improving:last_metric=metric
            if stalled>=4:raise RuntimeError('four recovery flight decisions without phase progress')
            print(json.dumps({'flight_step':index,'action':action}),flush=True)
        if not receipt['completed']:raise RuntimeError('recovery flight action budget exhausted')
    except (Exception,KeyboardInterrupt) as error:
        receipt['failure']=f'{type(error).__name__}: {error}'
        if steps and steps[-1]['execution_status']=='started':
            steps[-1].update(execution_status='failed',input_error=receipt['failure'])
    finally:
        receipt['finished_at']=time.time();lab.private_write(out/'episode.json',json.dumps(receipt,indent=2)+'\n')
        latest.unlink(missing_ok=True)
    return receipt

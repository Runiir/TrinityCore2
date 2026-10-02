"""Verify a client terrain contact with a real Survey before accepting it."""
import math
import json
import time
from tools.second_client import ctl
from . import lab_runtime as lab,site_boundaries,ground_navigation,owned_input


def needed(facts,extra,leg):
    if not leg.get('site_id') or facts['map']!=leg['map'] or not extra['mounted'] or any(
        extra[k] for k in ['flying','falling','swimming']):return False
    gap=abs(facts['position'][2]-leg['position'][2])
    return 2<gap<=25 and math.dist(facts['position'][:2],leg['position'][:2])<=12 and (
        site_boundaries.contains(site_boundaries.sites()[leg['site_id']]['polygon'],facts['position']))


def verify(leg,observer,path):
    trace={'decision_origin':'physical_client_floor_guard','reason':'stable client contact differs from legacy mapped elevation',
        'site_id':leg['site_id'],'original_goal':leg['position'][:],'physical_keys':[],'observations':[],
        'private_next_find_coordinates_used':False,'started_at':time.time(),'completed':False,'failure':None}
    receipt=path.parent/f'client_floor_probe_{time.time_ns()}.json'
    try:
        _verify(leg,observer,path,trace);trace['completed']=True;return trace
    except BaseException as error:trace['failure']=f'{type(error).__name__}: {error}';raise
    finally:
        trace['finished_at']=time.time();lab.private_write(receipt,json.dumps(trace,indent=2)+'\n')


def _verify(leg,observer,path,trace):
    from .archaeology_inputs import screenshot
    from .observation.archaeology import Observer as ArchaeologyObserver
    ctl._launcher_env=lab.client_environment;inputs=owned_input.Inputs();objects=ArchaeologyObserver()
    site=site_boundaries.sites()[leg['site_id']];before=observer.poll();anchor=before['position']
    trace['before']=before
    def observe(allow_settling=False):
        movement,extra=screenshot(path);facts=observer.poll();position=facts['position']
        trace['observations'].append({'facts':facts,'movement':movement,'travel':extra})
        if facts['map']!=before['map'] or not movement['in_world'] or movement['health_percent']<50 or any(
            movement[k] for k in ['dead','in_combat','on_taxi']) or any(extra[k] for k in ['flying','swimming']) or (
            extra['falling'] and not allow_settling):
            raise RuntimeError('client floor verification interrupted by unsafe state')
        if not site_boundaries.contains(site['polygon'],position) or not site_boundaries.inside_segment(site['polygon'],anchor,position):
            raise RuntimeError('client floor verification left the assigned polygon')
        if ground_navigation.water_at(facts['map'],position)['water_above_feet']:
            raise RuntimeError('client floor verification cannot Survey while feet are submerged')
        if allow_settling and abs(position[2]-anchor[2])>2:
            raise RuntimeError('client floor dismount changed elevation unexpectedly')
        return facts,extra
    for _ in range(3):
        facts,extra=observe()
        if math.dist(anchor[:2],facts['position'][:2])>.5 or abs(anchor[2]-facts['position'][2])>.3:
            raise RuntimeError('client ground contact did not remain stable')
        time.sleep(.4)
    inputs.key('3');trace['physical_keys'].append({'key':'3','purpose':'dismount on verified stable contact'})
    deadline=time.monotonic()+6
    while True:
        time.sleep(.3);facts,extra=observe(allow_settling=True)
        if not extra['mounted'] and not extra['falling']:break
        if time.monotonic()>deadline:raise RuntimeError('client floor dismount was not confirmed')
    cast=time.time();trace['survey_started_at']=cast
    inputs.key('2');trace['physical_keys'].append({'key':'2','purpose':'ordinary Survey floor capability probe'})
    time.sleep(2.5);facts,extra=observe();seen=objects.poll(0)
    fresh=[o for o in [seen['tool'],*seen['finds']] if o and o.get('visible') and o['seen_at']>=cast and o['map']==facts['map']]
    if not fresh:raise RuntimeError('client terrain contact produced no fresh owned Survey instrument or find')
    trace.update(after=facts,normal_survey_response=fresh,finished_at=time.time())
    leg.update(position=facts['position'][:3],verified_client_floor=True,ground_connection_origin=facts['position'][:3])
    # Let the ordinary Survey cooldown finish before the next archaeology step.
    time.sleep(max(0,6-(time.time()-cast)))

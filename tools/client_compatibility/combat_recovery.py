"""Recorded physical safety withdrawal; this is not a learned combat policy."""
import math
import time
from . import lab_runtime as lab,archaeology_inputs,site_boundaries,ground_navigation
from tools.second_client import ctl


def withdraw(movement,extra,facts,observer,path):
    if not movement['in_combat']:return None
    if movement['dead'] or movement['health_percent']<50:raise RuntimeError('combat withdrawal requires a living healthy character')
    if not extra['mounted']:
        from .combat_clear import run
        return run(movement, extra, facts, observer, path)
    from .travel_inputs import face
    ctl._launcher_env=lab.client_environment;inputs=ctl.Input();keys=[]
    start=facts['position'];site=site_boundaries.active_site(facts['map'],start,extra['digsite_ids'])
    if extra['mounted']:
        inputs.key('space',hold=2.5);keys.append({'key':'space','hold':2.5})
    heading=math.atan2(site['center'][1]-start[1],site['center'][0]-start[0])
    choices=[]
    for i in range(16):
        angle=heading+math.tau*i/16
        distance=site_boundaries.clip_distance(site['polygon'],start,angle,45 if extra['mounted'] else 60)
        goal=[start[0]+math.cos(angle)*distance,start[1]+math.sin(angle)*distance,start[2]]
        if distance>8:
            if not extra['mounted']:
                try:route=ground_navigation.route(facts['map'],start,goal)
                except RuntimeError:continue
                corridor=[start,*route['points']]
                if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):continue
                if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>100:continue
                goal=route['points'][-1]
            else:route=None
            separation=min((math.dist(goal[:2],h['position'][:2]) for h in facts['visible_hostiles']),default=100)
            choices.append((separation,goal,route))
    if not choices:raise RuntimeError('no bounded in-site combat withdrawal path')
    _,goal,route=max(choices,key=lambda c:c[0])
    if extra['mounted']:
        keys.extend(face(inputs,observer,goal));hold=math.dist(start[:2],goal[:2])/28.7
        inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold})
    else:
        for _ in range(8):
            facts_now=observer.poll();current=facts_now['position']
            route_now=ground_navigation.route(facts_now['map'],current,goal)
            target=next((p for p in route_now['points'] if math.dist(p[:2],current[:2])>1),None)
            if target is None:break
            keys.extend(face(inputs,observer,target))
            hold=min(2,math.dist(current[:2],target[:2])/7)
            inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold});time.sleep(.3)
            movement,extra=archaeology_inputs.screenshot(path)
            if movement['dead'] or movement['health_percent']<50:raise RuntimeError('combat withdrawal lost safe health')
            if not site_boundaries.contains(site['polygon'],observer.poll()['position']):raise RuntimeError('combat withdrawal left the digsite')
            if not movement['in_combat']:break
    deadline=time.monotonic()+15
    while time.monotonic()<deadline:
        movement,extra=archaeology_inputs.screenshot(path);after=observer.poll()
        if movement['dead'] or movement['health_percent']<50:raise RuntimeError('combat withdrawal lost safe health')
        if not movement['in_combat']:
            return {'decision_origin':'physical_safety_guard','reason':'combat observed','before':facts,
                'after':after,'physical_keys':keys,'public_ground_route':route,'time':time.time(),'still_mounted':extra['mounted']}
        time.sleep(.5)
    raise RuntimeError('bounded combat withdrawal did not clear combat')

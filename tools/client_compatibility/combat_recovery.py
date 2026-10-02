"""Recorded physical safety withdrawal; this is not a learned combat policy."""
import math
import time
from . import lab_runtime as lab,archaeology_inputs,site_boundaries,ground_navigation,model_collision,owned_input
from tools.second_client import ctl


def ascend(inputs,movement,extra,facts,observer,path,site):
    # The private lab's ordinary continent leash is 90 yards from home.
    # The former 72-yard ascent plus 45-yard retreat could remain within it.
    target=[*facts['position'][:2],facts['position'][2]+120]
    if not model_collision.clear_body_segment(facts['map'],facts['position'],target):
        raise RuntimeError('combat escape ascent has a public collision obstruction')
    keys=[];observations=[];deadline=time.monotonic()+20
    for _ in range(8):
        movement,extra=archaeology_inputs.screenshot(path);now=observer.poll()
        observations.append({'facts':now,'movement':movement,'travel':extra})
        if time.monotonic()>deadline or now['map']!=facts['map'] or movement['dead'] or movement['health_percent']<50 or (
            not extra['mounted'] or extra['falling'] or extra['swimming'] or
            not site_boundaries.contains(site['polygon'],now['position'])):
            raise RuntimeError('combat escape ascent lost a bounded safe state')
        remaining=target[2]-now['position'][2]
        if remaining<=2:return keys,observations
        hold=min(1.5,max(.1,remaining/28.7));before=now['position'][2]
        inputs.key('space',hold=hold);keys.append({'key':'space','hold':hold});time.sleep(.4)
        if observer.poll()['position'][2]<before+.3:raise RuntimeError('combat escape ascent made no vertical progress')
    raise RuntimeError('combat escape ascent exhausted its input budget')


def withdraw(movement,extra,facts,observer,path):
    if not movement['in_combat']:return None
    if movement['dead'] or movement['health_percent']<50:raise RuntimeError('combat withdrawal requires a living healthy character')
    if not extra['mounted']:
        from .combat_clear import run
        return run(movement, extra, facts, observer, path)
    from . import combat_landing
    if not extra['flying'] and combat_landing.permitted(movement,extra,facts,observer.player_level):
        return combat_landing.run(movement,extra,facts,observer,path)
    from .travel_inputs import face
    ctl._launcher_env=lab.client_environment;inputs=owned_input.Inputs();keys=[]
    start=facts['position'];site=site_boundaries.active_site(facts['map'],start,extra['digsite_ids'])
    ascent_observations=[]
    if extra['mounted']:
        ascent_keys,ascent_observations=ascend(inputs,movement,extra,facts,observer,path,site)
        keys.extend(ascent_keys)
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
                'after':after,'physical_keys':keys,'public_ground_route':route,'time':time.time(),'still_mounted':extra['mounted'],
                'ascent_observations':ascent_observations,'escape_height_yards':120}
        time.sleep(.5)
    raise RuntimeError('bounded combat withdrawal did not clear combat')

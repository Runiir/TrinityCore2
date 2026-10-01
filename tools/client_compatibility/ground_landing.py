"""Finish a near landing on the correct floor using bounded physical walking."""
import math
import time
from . import ground_navigation,site_boundaries


def needed(facts,extra,leg):
    distance=math.dist(facts['position'][:2],leg['position'][:2])
    return leg.get('landing_avoidance_frozen') and facts['map']==leg['map'] and extra['mounted'] and (
        not any(extra[k] for k in ['flying','falling','swimming'])) and (
        leg.get('arrival_radius',12)<=distance<=12) and (
        abs(facts['position'][2]-leg['position'][2])<leg.get('landing_height_tolerance',8))


def finish(inputs,leg,observer,path):
    from .archaeology_inputs import screenshot
    from .travel_inputs import face
    before=observer.poll();start=before['position'];goal=leg['position']
    _,extra=screenshot(path)
    if not needed(before,extra,leg):raise RuntimeError('ground landing adjustment preconditions changed')
    sites=[s for sid,s in site_boundaries.sites().items() if sid in extra['digsite_ids'] and
        s['map']==before['map'] and site_boundaries.contains(s['polygon'],start)]
    route=ground_navigation.route(before['map'],start,goal);points=[p[:] for p in route['points']]
    corridor=[start,*points]
    if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>16:
        raise RuntimeError('ground landing adjustment exceeds short corridor')
    if abs(points[0][2]-start[2])>2 or abs(points[-1][2]-goal[2])>2:
        raise RuntimeError('ground landing corridor is on a different floor')
    if any(not site_boundaries.inside_segment(s['polygon'],a,b) for s in sites for a,b in zip(corridor,corridor[1:])):
        raise RuntimeError('ground landing corridor leaves the assigned site')
    keys=[];observations=[];blocked=0
    for _ in range(16):
        movement,extra=screenshot(path);facts=observer.poll();position=facts['position']
        observations.append(position)
        if facts['map']!=before['map'] or not movement['in_world'] or movement['health_percent']<50 or any(
            movement[k] for k in ['dead','in_combat','on_taxi']) or not extra['mounted'] or any(
            extra[k] for k in ['flying','falling','swimming']):
            raise RuntimeError('ground landing adjustment interrupted by unsafe state')
        if any(not site_boundaries.contains(s['polygon'],position) for s in sites):
            raise RuntimeError('ground landing adjustment left the assigned site')
        if math.dist(position[:2],goal[:2])<leg.get('arrival_radius',12) and abs(
            position[2]-goal[2])<leg.get('landing_height_tolerance',8):
            return {'decision_origin':'physical_landing_ground_guard','reason':'correct floor beyond arrival radius',
                'before':before,'after':facts,'public_ground_route':route,'physical_keys':keys,
                'observed_positions':observations,'time':time.time()}
        while len(points)>1 and math.dist(position[:2],points[0][:2])<=.75:points.pop(0)
        target=points[0];keys.extend(face(inputs,observer,target))
        hold=min(.3,max(.08,math.dist(position[:2],target[:2])/14))
        inputs.key('w',hold=hold);time.sleep(.35);keys.append({'key':'w','hold':hold})
        after=observer.poll()['position']
        blocked=blocked+1 if math.dist(position[:2],after[:2])<.1 else 0
        if blocked>=2:raise RuntimeError('ground landing adjustment is blocked')
    raise RuntimeError('ground landing adjustment exhausted its short movement budget')

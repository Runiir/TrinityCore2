"""Move a licensed flying mount off a blocked descent using public terrain."""
import math
import time
from . import ground_navigation,site_boundaries


def alternative(facts,extra,leg):
    start=facts['position'];goal=leg['position']
    sites=[s for sid,s in site_boundaries.sites().items() if sid in extra['digsite_ids'] and
        s['map']==facts['map'] and site_boundaries.contains(s['polygon'],start)]
    heading=math.atan2(goal[1]-start[1],goal[0]-start[0])+math.pi/2
    origin=leg.get('ground_connection_origin',goal)
    for radius in [6,10,15]:
        for i in range(8):
            angle=heading+math.tau*i/8
            requested=[start[0]+radius*math.cos(angle),start[1]+radius*math.sin(angle),goal[2]]
            if any(not site_boundaries.inside_segment(s['polygon'],start,requested) for s in sites):continue
            try:point=ground_navigation.landing_point(facts['map'],requested,radius=3,start=origin)
            except RuntimeError:continue
            if math.dist(point[:2],start[:2])<4:continue
            if any(not site_boundaries.inside_segment(s['polygon'],start,point) for s in sites):continue
            if not sites and math.dist(point[:2],goal[:2])>7:continue
            return point,sites
    raise RuntimeError('no connected alternative to the blocked landing')


def nudge(inputs,leg,observer,path,extra):
    from .travel_inputs import face
    from . import archaeology_inputs
    if not extra['mounted'] or not extra['flying'] or extra['falling']:
        raise RuntimeError('landing collision escape requires licensed mounted flight')
    count=leg.get('landing_collision_escapes',0)
    if count>=3:raise RuntimeError('three alternative landing probes were blocked')
    before=observer.poll();point,sites=alternative(before,extra,leg)
    inputs.key('space',hold=.4);keys=[{'key':'space','hold':.4}]
    keys.extend(face(inputs,observer,point))
    hold=math.dist(observer.poll()['position'][:2],point[:2])/28.7
    inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold});time.sleep(.3)
    movement,extra=archaeology_inputs.screenshot(path);after=observer.poll()
    if movement['dead'] or movement['in_combat'] or not extra['mounted'] or before['map']!=after['map']:
        raise RuntimeError('unsafe state during a landing collision escape')
    if any(not site_boundaries.contains(s['polygon'],after['position']) for s in sites):
        raise RuntimeError('landing collision escape left the assigned polygon')
    leg.update(position=point,landing_collision_escapes=count+1)
    return {'decision_origin':'physical_collision_guard','reason':'descent blocked above mapped walking floor',
        'before':before,'after':after,'public_ground_goal':point,'physical_keys':keys,
        'horizontal_progress':math.dist(before['position'][:2],after['position'][:2]),'time':time.time()}

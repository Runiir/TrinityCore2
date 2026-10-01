"""A physical collision guard for a mounted climb blocked under an overhang."""
import math
import time
from . import ground_navigation,site_boundaries


def waypoint(facts,extra,goal):
    start=facts['position'];heading=math.atan2(start[1]-goal[1],start[0]-goal[0])
    sites=[s for sid,s in site_boundaries.sites().items() if sid in extra['digsite_ids'] and
           s['map']==facts['map'] and site_boundaries.contains(s['polygon'],start)]
    for angle in [heading,heading+math.pi/2,heading-math.pi/2]:
        distance=min([12.,*[site_boundaries.clip_distance(s['polygon'],start,angle,12.) for s in sites]])
        if distance<3:continue
        xy=[start[0]+math.cos(angle)*distance,start[1]+math.sin(angle)*distance]
        try:
            ground=[ground_navigation.ground_point(facts['map'],[
                start[i]+(xy[i]-start[i])*t for i in range(2)]) for t in [.5,1.]]
        except RuntimeError:continue
        if max(p[2] for p in ground)>start[2]-10:continue
        return [*xy,start[2]],ground,[s['id'] for s in sites]
    raise RuntimeError('no bounded terrain-cleared escape from the blocked climb')


def nudge(inputs,leg,observer,path,extra):
    from .travel_inputs import face
    from . import archaeology_inputs
    before=observer.poll()
    if not extra['mounted'] or not extra['flying']:raise RuntimeError('blocked-climb escape requires mounted flight')
    goal,ground,sites=waypoint(before,extra,leg['position'])
    keys=face(inputs,observer,goal);hold=math.dist(before['position'][:2],goal[:2])/28.7
    inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold});time.sleep(.4)
    movement,after_extra=archaeology_inputs.screenshot(path);after=observer.poll()
    moved=math.dist(before['position'][:2],after['position'][:2])
    if movement['dead'] or movement['in_combat'] or not after_extra['mounted']:
        raise RuntimeError('unsafe state after the blocked-climb escape')
    if moved<3:raise RuntimeError('blocked-climb escape also encountered a horizontal obstruction')
    if any(not site_boundaries.contains(site_boundaries.sites()[sid]['polygon'],after['position']) for sid in sites):
        raise RuntimeError('blocked-climb escape crossed the observed digsite boundary')
    return {'decision_origin':'physical_collision_guard','reason':'no vertical progress during mounted ascent',
        'before':before,'after':after,'public_waypoint':goal,'ground_columns':ground,
        'constrained_sites':sites,'physical_keys':keys,'horizontal_progress':moved,'time':time.time()}

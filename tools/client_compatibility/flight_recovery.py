"""A physical collision guard for a mounted climb blocked under an overhang."""
import math
import time
from . import ground_navigation,site_boundaries


def waypoint(facts,extra,goal):
    start=facts['position'];heading=math.atan2(start[1]-goal[1],start[0]-goal[0])
    sites=[s for sid,s in site_boundaries.sites().items() if sid in extra['digsite_ids'] and
           s['map']==facts['map'] and site_boundaries.contains(s['polygon'],start)]
    floor=ground_navigation.ground_point(facts['map'],start,maximum_height=start[2]-10)
    for radius in [12.,24.,40.,60.]:
        for angle in [heading,heading+math.pi/2,heading-math.pi/2]:
            distance=min([radius,*[site_boundaries.clip_distance(s['polygon'],start,angle,radius) for s in sites]])
            if distance<3:continue
            xy=[start[0]+math.cos(angle)*distance,start[1]+math.sin(angle)*distance]
            try:
                # A column whose highest ground is below us permits resuming
                # the climb without the roof that blocked the original column.
                ground=ground_navigation.ground_point(facts['map'],xy)
                if ground[2]>start[2]-10:continue
                corridor=ground_navigation.route(facts['map'],floor,ground)
            except RuntimeError:continue
            points=[floor,*corridor['points']]
            if len(points)>12 or sum(math.dist(a[:2],b[:2]) for a,b in zip(points,points[1:]))>120:continue
            if any(not site_boundaries.inside_segment(s['polygon'],a,b) for s in sites for a,b in zip(points,points[1:])):continue
            highest=max(p[2] for p in points)
            altitude=max(highest+10,min(start[2]-10,highest+60))
            if altitude>start[2]-5:continue
            return [*ground[:2],altitude],corridor,[s['id'] for s in sites]
    raise RuntimeError('no bounded terrain-cleared escape from the blocked climb')


def nudge(inputs,leg,observer,path,extra):
    from .travel_inputs import face
    from . import archaeology_inputs
    before=observer.poll()
    if not extra['mounted'] or not extra['flying']:raise RuntimeError('blocked-climb escape requires mounted flight')
    goal,corridor,sites=waypoint(before,extra,leg['position']);keys=[]
    # Descend into the free space above the public walking corridor, then
    # follow its corners rather than flying through the underside of the arch.
    for _ in range(3):
        current=observer.poll()['position']
        if current[2]<=goal[2]+2:break
        hold=min(3,(current[2]-goal[2])/28.7)
        inputs.key('x',hold=hold);keys.append({'key':'x','hold':hold});time.sleep(.3)
    else:raise RuntimeError('blocked-climb escape could not descend below the overhang')
    for point in corridor['points']:
        for _ in range(4):
            current=observer.poll()['position'];distance=math.dist(current[:2],point[:2])
            if distance<1.5:break
            keys.extend(face(inputs,observer,point));hold=min(40,distance)/28.7
            inputs.key('w',hold=hold);keys.append({'key':'w','hold':hold});time.sleep(.3)
            if math.dist(current[:2],observer.poll()['position'][:2])<min(1,distance*.2):
                raise RuntimeError('blocked-climb escape encountered a ground-corridor obstruction')
        else:raise RuntimeError('blocked-climb escape did not reach its corridor corner')
    movement,after_extra=archaeology_inputs.screenshot(path);after=observer.poll()
    moved=math.dist(before['position'][:2],after['position'][:2])
    if movement['dead'] or movement['in_combat'] or not after_extra['mounted']:
        raise RuntimeError('unsafe state after the blocked-climb escape')
    if moved<3:raise RuntimeError('blocked-climb escape also encountered a horizontal obstruction')
    if any(not site_boundaries.contains(site_boundaries.sites()[sid]['polygon'],after['position']) for sid in sites):
        raise RuntimeError('blocked-climb escape crossed the observed digsite boundary')
    return {'decision_origin':'physical_collision_guard','reason':'no vertical progress during mounted ascent',
        'before':before,'after':after,'public_waypoint':goal,'public_ground_corridor':corridor,
        'constrained_sites':sites,'physical_keys':keys,'horizontal_progress':moved,'time':time.time()}

"""A physical collision guard for a mounted climb blocked under an overhang."""
import math
import time
from . import ground_navigation,site_boundaries


def candidate(facts,extra,angle):
    start=facts['position']
    sites=[s for sid,s in site_boundaries.sites().items() if sid in extra['digsite_ids'] and
        s['map']==facts['map'] and site_boundaries.contains(s['polygon'],start)]
    distance=min([45.,*[site_boundaries.clip_distance(s['polygon'],start,angle,45.) for s in sites]])
    if distance<3:raise RuntimeError('no useful in-site collision escape')
    goal=[start[0]+math.cos(angle)*distance,start[1]+math.sin(angle)*distance,start[2]]
    floor=ground_navigation.ground_point(facts['map'],goal,maximum_height=start[2]-10)
    if floor[2]>start[2]-10:raise RuntimeError('insufficient public floor clearance')
    return goal,floor,sites


def nudge(inputs,leg,observer,path,extra):
    if not extra['mounted'] or not extra['flyable_area']:
        raise RuntimeError('blocked-climb escape requires a mount in a flyable area')
    return grounded_escape(inputs,leg,observer,path,extra)


def grounded_escape(inputs,leg,observer,path,extra):
    """Probe sideways liftoff when collision immediately clears IsFlying.

    A roof contact can end flight while the player is still high above the
    mapped walking floor. Keep Space held during the small lateral move so
    reaching an edge resumes licensed flight instead of an unmounted fall.
    """
    from .travel_inputs import face
    from . import archaeology_inputs
    attempts=[];before=observer.poll();heading=math.atan2(leg['position'][1]-before['position'][1],leg['position'][0]-before['position'][0])
    previous=leg.get('climb_escape_heading')
    angles=[heading-math.pi/2,heading+math.pi/2,heading+math.pi] if previous is None else [previous,previous+math.pi/2,previous-math.pi/2]
    for angle in angles:
        facts=observer.poll();start=facts['position']
        try:goal,floor,sites=candidate(facts,extra,angle)
        except RuntimeError:continue
        distance=math.dist(start[:2],goal[:2])
        keys=face(inputs,observer,goal);hold=distance/28.7
        codes=[inputs._keycode(inputs.XK.string_to_keysym(k))[0] for k in ['space','w']]
        inputs._tap(codes,hold);keys.append({'keys':['space','w'],'hold':hold});time.sleep(.4)
        movement,after_extra=archaeology_inputs.screenshot(path);after=observer.poll()
        moved=math.dist(start[:2],after['position'][:2])
        attempts.append({'before':facts,'after':after,'public_waypoint':goal,'public_floor':floor,'physical_keys':keys})
        if movement['dead'] or movement['in_combat'] or not after_extra['mounted']:
            raise RuntimeError('unsafe state during the bounded sideways liftoff')
        if any(not site_boundaries.contains(s['polygon'],after['position']) for s in sites):
            raise RuntimeError('sideways liftoff crossed the observed digsite boundary')
        if moved>=1.5:
            leg['climb_escape_heading']=angle
            return {'decision_origin':'physical_collision_guard','reason':'blocked mounted climb; bounded lateral liftoff',
                'before':before,'after':after,'attempts':attempts,'horizontal_progress':moved,'time':time.time()}
    raise RuntimeError('three bounded sideways liftoff probes made no useful progress')

"""Choose a nearby dry interaction stance from an already visible find."""
import math
import time
from . import ground_navigation,site_boundaries
from .travel_inputs import face


def plan(map_id,start,find,polygon):
    candidates=[]
    for index in range(16):
        heading=start[3]+math.pi+index*math.tau/16
        goal=[find[0]+math.cos(heading)*3.5,find[1]+math.sin(heading)*3.5,find[2]]
        try:route=ground_navigation.route(map_id,start,goal,allow_swimming=True)
        except RuntimeError:continue
        endpoint=route['points'][-1];corridor=[start,*route['points']]
        length=sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))
        if route['water_polygons'] or not 2.5<math.dist(endpoint[:2],find[:2])<4.2:continue
        if math.dist(endpoint[:3],find[:3])>4.75 or abs(endpoint[2]-find[2])>1.25 or length>8:continue
        if not all(site_boundaries.inside_segment(polygon,a,b) for a,b in zip(corridor,corridor[1:])):continue
        candidates.append((abs(endpoint[2]-find[2])*3+length,route))
    if not candidates:raise RuntimeError('visible find has no short dry interaction stance at its elevation')
    return min(candidates,key=lambda c:c[0])[1]


def approach(inputs,observer,find,site,path):
    from .archaeology_inputs import screenshot
    from .swim_navigation import available
    start=observer.poll()['position'];route=plan(site['map'],start,find['position'],site['polygon']);keys=[]
    for target in route['points']:
        for _ in range(3):
            current=observer.poll()['position'];distance=math.dist(current[:2],target[:2])
            if distance<=.5:break
            keys.extend(face(inputs,observer,target))
            hold=min(1.,distance/7);inputs.key('w',hold=hold);time.sleep(.35)
            keys.append({'key':'w','hold':hold})
            movement,extra=screenshot(path);after=observer.poll()['position']
            available(movement,extra,after,site['polygon'])
            if extra['swimming']:raise RuntimeError('interaction stance unexpectedly entered water')
            if math.dist(current[:2],after[:2])<.1:raise RuntimeError('interaction stance movement blocked')
        else:raise RuntimeError('interaction stance waypoint did not settle')
    after=observer.poll()['position']
    if not 2.3<math.dist(after[:3],find['position'])<=5:
        raise RuntimeError('actual interaction stance is outside safe find reach')
    keys.extend(face(inputs,observer,find['position']));time.sleep(.4)
    return {'source':'ordinary visible find and dry public navigation heights','before':start,'after':after,
        'public_ground_route':route,'physical_keys':keys,'observed_after_inside':True}

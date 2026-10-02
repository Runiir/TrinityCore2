"""Bounded on-foot probes when a survey bearing has no connected dry route."""
import json
import math
import time
from . import ground_navigation as ground,site_boundaries,lab_runtime as lab


class TerrainBlocked(RuntimeError):
    """Public ground routes and bounded physical probes were exhausted."""


def candidates(tcp,site,obstructions=()):
    start=tcp['player']['position'];heading=tcp['tool']['heading_radians'];result=[]
    for offset in [-math.pi/2,math.pi/2,math.pi,-3*math.pi/4,3*math.pi/4]:
        angle=heading+offset;distance=site_boundaries.clip_distance(site['polygon'],start,angle,4)
        if distance<1.5:continue
        goal=[start[0]+math.cos(angle)*distance,start[1]+math.sin(angle)*distance,start[2]]
        try:route=ground.route(site['map'],start,goal,obstructions,allow_swimming=True)
        except RuntimeError:continue
        endpoint=route['points'][-1];corridor=[start,*route['points']]
        if route['water_polygons'] or math.dist(endpoint[:2],start[:2])<1.5:continue
        # A continuous four-yard slope can rise more than a jump threshold.
        # Match the measured-height guard for the short walking probe below.
        if abs(endpoint[2]-start[2])>1.5:continue
        if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>8:continue
        if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):continue
        distance=math.dist(start[:2],endpoint[:2]);ratio=min(1,1.4/distance)
        probe=[start[i]+(endpoint[i]-start[i])*ratio for i in range(3)]
        try:route['walking_surface']=ground.safe_walk_segment(site['map'],start,probe)
        except RuntimeError:continue
        result.append(route)
    if not result:
        # A telescope base cannot override a known slippery hillside. Only
        # unavailable/unknown or normally walkable starting terrain qualifies.
        try:surface=ground.probe_surface(site['map'],start)
        except RuntimeError:surface=None
        if surface and surface['detail_slope_degrees']>35:return []
        # The old mesh can omit a grounded client patch. A recently observed
        # telescope base is an ordinary ground sample, not the hidden find.
        tool=tcp['tool'];point=tool.get('position');age=time.time()-tool.get('seen_at',0)
        if point and 0<=age<=20 and 1<=math.dist(start[:2],point[:2])<=3 and abs(point[2]-start[2])<=.75:
            if site_boundaries.inside_segment(site['polygon'],start,point) and not ground.water_at(site['map'],point)['water_above_feet']:
                result.append({'schema':'observed_telescope_ground_sample_v1','points':[start[:3],point[:3]],
                    'ground_only':True,'water_polygons':0,'observed_ground_sample':True,
                    'sample_seen_at':tool['seen_at'],'sample_maximum_age_seconds':20,
                    'source':'ordinary owned telescope base and grounded player; no private find coordinates'})
    return result[:4]


def execute(inputs,tcp,observed_ids,path,obstructions=()):
    from .archaeology_inputs import screenshot
    from .observation.transport import Observer
    from .travel_inputs import face
    site=site_boundaries.active_site(tcp['tool']['map'],tcp['player']['position'],observed_ids)
    observer=Observer();before=observer.poll()['position'];routes=candidates(tcp,site,obstructions)
    trace={'schema':'public_ground_escape_v1','started_at':time.time(),
        'site_id':site['id'],
        'reason':'no connected forward survey corridor','decision_origin':'physical_navigation_adapter',
        'before':before,'probes':[],'completed':False,'failure':None}
    receipt=path.parent/f'ground_escape_{time.time_ns()}.json'
    try:
        for route in routes:
            current=observer.poll()['position'];target=route['points'][-1]
            distance=math.dist(current[:2],target[:2])
            if distance<.1:continue
            # The start may lie just outside the mesh. Probe its nearby dry
            # corridor endpoint rather than repeatedly pushing at one snap point.
            segment=[current,[current[i]+(target[i]-current[i])*min(1,1.4/distance) for i in range(3)]]
            if not site_boundaries.inside_segment(site['polygon'],*segment):continue
            keys=face(inputs,observer,target);hold=min(.2,math.dist(current[:2],target[:2])/7)
            inputs.key('w',hold=hold);time.sleep(.35);keys.append({'key':'w','hold':hold})
            movement,extra=screenshot(path);after=observer.poll()['position']
            observations=[{'position':after,'movement':movement,'travel':extra}]
            deadline=time.monotonic()+2.5
            while extra['falling'] and time.monotonic()<deadline and abs(after[2]-current[2])<=1.5:
                time.sleep(.2);movement,extra=screenshot(path);after=observer.poll()['position']
                observations.append({'position':after,'movement':movement,'travel':extra})
            probe={'before':current,'after':after,'route':route,'physical_keys':keys,'observations':observations}
            trace['probes'].append(probe);lab.private_write(receipt,json.dumps(trace,indent=2)+'\n')
            if not movement['in_world'] or movement['health_percent']<50 or any(movement[k] for k in ['dead','in_combat','on_taxi']):
                raise RuntimeError('ground escape interrupted by unavailable character')
            if any(extra[k] for k in ['mounted','flying','falling','swimming']):
                raise RuntimeError('ground escape must stay unmounted on dry ground')
            if not site_boundaries.contains(site['polygon'],after) or not site_boundaries.inside_segment(site['polygon'],current,after):
                raise RuntimeError('ground escape left the assigned site')
            if abs(after[2]-current[2])>1.5:raise RuntimeError('ground escape changed floor unexpectedly')
            if math.dist(current[:2],after[:2])>=.5:
                trace['completed']=True
                return hold,{**route,'start':before,'after':after,
                    'remaining_ground_points':[] if route.get('observed_ground_sample') else route['points'][1:],
                    'detour_committed':not route.get('observed_ground_sample'),
                    'goal_source':'public survey bearing and nearby dry recovery corridors',
                    'ground_escape_receipt':receipt.name,'physical_navigation_recovery':True,
                    'boundary_guard':{'site_id':site['id'],'observed_after_inside':True,'whole_corridor_inside':True,'source':site['source']}}
        raise TerrainBlocked('no accepted dry recovery corridor' if not routes else
            'four bounded on-foot probes could not leave the navigation corner')
    except BaseException as error:trace['failure']=f'{type(error).__name__}: {error}';raise
    finally:
        trace['finished_at']=time.time();lab.private_write(receipt,json.dumps(trace,indent=2)+'\n')

"""Walk out from a mapped overhead obstruction before mounting for flight."""
import json
import math
import time
from . import ground_navigation as ground,model_collision,site_boundaries,lab_runtime as lab


def physical_floor(map_id,point):
    from .terrain_geometry import height
    terrain=height(map_id,point);model=model_collision.column(map_id,point)
    surfaces=[h for h in [terrain,model['support_height']] if h is not None and h<=point[2]+1.25]
    if not surfaces or abs(max(surfaces)-point[2])>1.25:raise RuntimeError('indoor exit has no nearby supporting floor')
    return {'position':[*point[:2],max(surfaces)],'physical_surface':{'terrain_height':terrain,'model':model}}


def outdoor_floor_patch(map_id,point,radius=2.5):
    """Walking outside may pass beneath an outdoor awning, unlike landing."""
    samples=[]
    for requested in [point,*[[point[0]+radius*math.cos(i*math.tau/8),
        point[1]+radius*math.sin(i*math.tau/8),point[2]] for i in range(8)]]:
        sample=physical_floor(map_id,requested);position=sample['position']
        if abs(position[2]-point[2])>1.25 or not model_collision.mapped_outdoors(map_id,position) or (
            ground.water_at(map_id,position)['water_above_feet']):
            raise RuntimeError('exit lacks a supported dry outdoor walking patch')
        samples.append(sample)
    return {'radius_yards':radius,'samples':samples,'source':'public supported outdoor WMO floor, possibly beneath an awning'}


def direct_indoor_route(map_id,start,point):
    if math.dist(start[:2],point[:2])>24:raise RuntimeError('direct indoor exit exceeds 24 yards')
    distance=math.dist(start[:2],point[:2]);samples=[]
    for index in range(math.ceil(distance/.7)+1):
        ratio=min(1,index*.7/max(.01,distance));requested=[start[i]+(point[i]-start[i])*ratio for i in range(3)]
        sample=physical_floor(map_id,requested);samples.append(sample)
    for a,b in zip([start,*[s['position'] for s in samples]], [s['position'] for s in samples]):
        if abs(a[2]-b[2])>max(.25,math.dist(a[:2],b[:2])*math.tan(math.radians(35))):
            raise RuntimeError('direct indoor exit has a steep step or floor discontinuity')
        if not model_collision.clear_body_segment(map_id,a,b):raise RuntimeError('direct indoor exit intersects body collision')
    return {'points':[start[:3],point],'complete':True,'physical_floor_samples':samples,
        'source':'continuous sampled public MAPS/VMAP floor and clear body rays; disconnected MMAP doorway'}


def needed(facts,extra):
    indoors=extra.get('indoors',False)
    if not (extra['mounted'] or indoors) or any(extra[k] for k in ['falling','swimming']):return False
    try:surface=ground.probe_surface(facts['map'],facts['position'])
    except RuntimeError:return False
    difference=facts['position'][2]-surface['position'][2]
    if not -2<=difference<=(12 if extra['flying'] else 2) or surface['detail_slope_degrees']>35:return False
    if indoors and not extra['flying']:return True
    from .terrain_geometry import height
    terrain=height(facts['map'],facts['position'])
    if terrain is None or abs(terrain-surface['position'][2])>1.5:return False
    collision=model_collision.column(facts['map'],facts['position'])['collision_height']
    return collision is not None and collision>facts['position'][2]+1


def select(facts,extra):
    start=facts['position'];site=site_boundaries.active_site(facts['map'],start,extra['digsite_ids'])
    attempts=[]
    indoor=extra.get('indoors',False);angles=16 if indoor else 8
    for radius in [4,8,12,20,35]:
        for index in range(angles):
            angle=index*math.tau/angles;goal=[start[0]+radius*math.cos(angle),start[1]+radius*math.sin(angle),start[2]]
            if not site_boundaries.inside_segment(site['polygon'],start,goal):continue
            try:
                point=physical_floor(facts['map'],goal)['position'] if indoor else ground.landing_point(facts['map'],goal,radius=3,start=start)
                patch=(outdoor_floor_patch if indoor else ground.site_ground_patch)(facts['map'],point,radius=1.5 if indoor else 2.5)
                try:route=ground.route(facts['map'],start,point)
                except RuntimeError:
                    if not indoor:raise
                    route=direct_indoor_route(facts['map'],start,point)
                corridor=[start,*route['points']]
                if abs(corridor[1][2]-start[2])>2 or math.dist(start[:2],point[:2])<3:continue
                if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>60:continue
                if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):continue
                for a,b in zip(corridor,corridor[1:]):
                    if route.get('physical_floor_samples'):direct_indoor_route(facts['map'],a,b)
                    else:ground.safe_walk_segment(facts['map'],a,b)
                    if not model_collision.clear_body_segment(facts['map'],a,b):raise RuntimeError('exit corridor intersects static body collision')
            except RuntimeError as error:
                attempts.append({'requested':goal,'failure':str(error)});continue
            return {'site_id':site['id'],'point':point,'route':route,'safe_patch':patch,'attempts':attempts,'indoor_exit':indoor,
                    'source':'public continuous floor and body-height VMAP collision; no private find coordinates'}
    error=RuntimeError('no bounded connected exit from overhead collision');error.attempts=attempts
    raise error


def available(movement,extra,facts,map_id,site,*,allow_descent=False):
    if facts['map']!=map_id or not movement['in_world'] or movement['health_percent']<50 or any(
        movement[k] for k in ['dead','in_combat','on_taxi']):raise RuntimeError('takeoff ground exit interrupted by unavailable character')
    if extra['falling'] or extra['swimming'] or extra['flying'] and not allow_descent:
        raise RuntimeError('takeoff exit requires dry settled ground')
    if not site_boundaries.contains(site['polygon'],facts['position']):raise RuntimeError('takeoff exit left the assigned digsite')


def escape(inputs,observer,path,extra):
    from .archaeology_inputs import screenshot
    from .travel_inputs import face
    before=observer.poll();site=site_boundaries.active_site(before['map'],before['position'],extra['digsite_ids'])
    receipt={'schema':'public_takeoff_ground_exit_v1','started_at':time.time(),'site_id':site['id'],
        'decision_origin':'physical_collision_guard','reason':'indoors' if extra.get('indoors') else 'near ground under static overhead collision',
        'before':before,'public_plan':None,'physical_keys':[],'observations':[],
        'completed':False,'failure':None}
    file=path.parent/f'takeoff_exit_{time.time_ns()}.json'
    try:
        movement,fresh=screenshot(path);available(movement,fresh,observer.poll(),before['map'],site,allow_descent=True)
        if not needed(before,fresh):raise RuntimeError('takeoff exit preconditions changed')
        if fresh['flying']:
            floor=ground.probe_surface(before['map'],before['position'])['position']
            floor=[*before['position'][:2],floor[2]]
            if ground.water_at(before['map'],floor)['water_above_feet'] or not model_collision.clear_body_segment(
                before['map'],before['position'],floor):raise RuntimeError('overhang descent lacks a clear dry floor')
            hold=min(.6,(before['position'][2]-floor[2]+1)/28.7)
            inputs.key('x',hold=hold);receipt['physical_keys'].append({'key':'x','hold':hold})
            deadline=time.monotonic()+3
            while time.monotonic()<deadline:
                time.sleep(.2);movement,fresh=screenshot(path);facts=observer.poll()
                available(movement,fresh,facts,before['map'],site,allow_descent=True)
                receipt['observations'].append({'facts':facts,'movement':movement,'travel':fresh})
                if not fresh['flying'] and abs(facts['position'][2]-floor[2])<2:break
            else:raise RuntimeError('overhang descent did not settle on the mapped floor')
        planned=select(observer.poll(),fresh);receipt['public_plan']=planned
        points=[p[:] for p in planned['route']['points']]
        if fresh['mounted']:
            inputs.key('3');receipt['physical_keys'].append({'key':'3'});time.sleep(1)
        blocked=0
        for _ in range(90):
            if time.time()-receipt['started_at']>120:raise RuntimeError('takeoff exit exceeded its local time budget')
            movement,fresh=screenshot(path);facts=observer.poll();position=facts['position']
            available(movement,fresh,facts,before['map'],site)
            receipt['observations'].append({'facts':facts,'movement':movement,'travel':fresh})
            lab.private_write(file,json.dumps(receipt,indent=2)+'\n')
            if fresh['mounted']:raise RuntimeError('takeoff exit did not dismount')
            if math.dist(position[:2],planned['point'][:2])<(.35 if planned['indoor_exit'] else 1) and not fresh.get('indoors'):
                try:(outdoor_floor_patch if planned['indoor_exit'] else ground.site_ground_patch)(facts['map'],position,radius=1 if planned['indoor_exit'] else 1.5)
                except RuntimeError:pass
                else:
                    receipt.update(completed=True,after=facts);return receipt
            while len(points)>1 and math.dist(position[:2],points[0][:2])<=.75:points.pop(0)
            target=points[0];distance=math.dist(position[:2],target[:2]);ratio=min(1,1.4/max(.01,distance))
            endpoint=[position[i]+(target[i]-position[i])*ratio for i in range(3)]
            if planned['route'].get('physical_floor_samples'):direct_indoor_route(facts['map'],position,endpoint)
            else:ground.safe_walk_segment(facts['map'],position,endpoint)
            if not model_collision.clear_body_segment(facts['map'],position,endpoint):raise RuntimeError('takeoff exit body corridor became blocked')
            if not site_boundaries.inside_segment(site['polygon'],position,endpoint):raise RuntimeError('takeoff exit segment crosses site boundary')
            receipt['physical_keys'].extend(face(inputs,observer,target));hold=min(.2,distance/7)
            inputs.key('w',hold=hold);time.sleep(.35);receipt['physical_keys'].append({'key':'w','hold':hold})
            after=observer.poll()['position'];blocked=blocked+1 if math.dist(position[:2],after[:2])<.1 else 0
            if blocked>=2:raise RuntimeError('two bounded takeoff ground advances were blocked')
        raise RuntimeError('takeoff exit exhausted its local walking budget')
    except BaseException as error:receipt['failure']=f'{type(error).__name__}: {error}';raise
    finally:
        receipt['finished_at']=time.time();lab.private_write(file,json.dumps(receipt,indent=2)+'\n')

"""Walk out from a mapped overhead obstruction before mounting for flight."""
import json
import math
import time
from . import ground_navigation as ground,model_collision,site_boundaries,lab_runtime as lab


def needed(facts,extra):
    if not extra['mounted'] or any(extra[k] for k in ['falling','swimming']):return False
    try:surface=ground.probe_surface(facts['map'],facts['position'])
    except RuntimeError:return False
    difference=facts['position'][2]-surface['position'][2]
    if not -2<=difference<=(12 if extra['flying'] else 2) or surface['detail_slope_degrees']>35:return False
    from .terrain_geometry import height
    terrain=height(facts['map'],facts['position'])
    if terrain is None or abs(terrain-surface['position'][2])>1.5:return False
    collision=model_collision.column(facts['map'],facts['position'])['collision_height']
    return collision is not None and collision>facts['position'][2]+1


def select(facts,extra):
    start=facts['position'];site=site_boundaries.active_site(facts['map'],start,extra['digsite_ids'])
    attempts=[]
    for radius in [4,8,12,20]:
        for index in range(8):
            angle=index*math.tau/8;goal=[start[0]+radius*math.cos(angle),start[1]+radius*math.sin(angle),start[2]]
            if not site_boundaries.inside_segment(site['polygon'],start,goal):continue
            try:
                point=ground.landing_point(facts['map'],goal,radius=3,start=start)
                patch=ground.site_ground_patch(facts['map'],point,radius=2.5)
                route=ground.route(facts['map'],start,point);corridor=[start,*route['points']]
                if abs(corridor[1][2]-start[2])>2 or math.dist(start[:2],point[:2])<3:continue
                if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>24:continue
                if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):continue
                for a,b in zip(corridor,corridor[1:]):
                    ground.safe_walk_segment(facts['map'],a,b)
                    if not model_collision.clear_body_segment(facts['map'],a,b):raise RuntimeError('exit corridor intersects static body collision')
            except RuntimeError as error:
                attempts.append({'requested':goal,'failure':str(error)});continue
            return {'site_id':site['id'],'point':point,'route':route,'safe_patch':patch,'attempts':attempts,
                'source':'public connected terrain and body-height VMAP collision; no private find coordinates'}
    raise RuntimeError('no bounded connected exit from overhead collision')


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
        'decision_origin':'physical_collision_guard','reason':'grounded under static overhead collision',
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
        inputs.key('3');receipt['physical_keys'].append({'key':'3'});time.sleep(1)
        blocked=0
        for _ in range(28):
            movement,fresh=screenshot(path);facts=observer.poll();position=facts['position']
            available(movement,fresh,facts,before['map'],site)
            receipt['observations'].append({'facts':facts,'movement':movement,'travel':fresh})
            lab.private_write(file,json.dumps(receipt,indent=2)+'\n')
            if fresh['mounted']:raise RuntimeError('takeoff exit did not dismount')
            if math.dist(position[:2],planned['point'][:2])<1:
                try:ground.site_ground_patch(facts['map'],position)
                except RuntimeError:pass
                else:
                    receipt.update(completed=True,after=facts);return receipt
            while len(points)>1 and math.dist(position[:2],points[0][:2])<=.75:points.pop(0)
            target=points[0];distance=math.dist(position[:2],target[:2]);ratio=min(1,1.4/max(.01,distance))
            endpoint=[position[i]+(target[i]-position[i])*ratio for i in range(3)]
            ground.safe_walk_segment(facts['map'],position,endpoint)
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

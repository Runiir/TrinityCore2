"""Local walkable detours from static MMAP data and public survey headings."""
import json
import math
import subprocess
from . import lab_runtime as lab,site_boundaries


def binary():
    source=lab.REPO/'tools/client_compatibility/navmesh_probe.cpp'
    target=lab.ROOT/'bin/navmesh_probe'
    if not target.exists() or target.stat().st_mtime<source.stat().st_mtime:
        subprocess.run(['c++','-std=c++20','-O2','-I'+str(lab.REPO/'dep/recastnavigation/Detour/Include'),
            str(source),str(lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a'),'-o',str(target)],check=True)
    return target


def route(map_id,start,goal,obstructions=(),*,allow_swimming=False):
    if len(obstructions)>8:raise ValueError('observed ground obstruction budget exceeded')
    command=[str(binary()),str(lab.BASE/'data/mmaps'),str(map_id),
        *(['--walk-swim'] if allow_swimming else []),*map(str,start[:3]),*map(str,goal[:3]),
        *(str(v) for point in obstructions for v in point[:3])]
    result=subprocess.run(command,capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('ground routing: '+result.stderr.strip())
    return json.loads(result.stdout)


def ground_point(map_id,xy,maximum_height=None):
    mode='--ground' if maximum_height is None else '--ground-below'
    args=[] if maximum_height is None else [str(maximum_height)]
    result=subprocess.run([str(binary()),str(lab.BASE/'data/mmaps'),str(map_id),mode,*map(str,xy[:2]),*args],
                          capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('public landing ground: '+result.stderr.strip())
    return json.loads(result.stdout)['position']


def landing_point(map_id,position,radius=30,start=None):
    result=subprocess.run([str(binary()),str(lab.BASE/'data/mmaps'),str(map_id),'--landing',
        *map(str,position[:3]),str(radius),*map(str,start[:3] if start is not None else [])],capture_output=True,text=True,timeout=10)
    if result.returncode:raise RuntimeError('public flat landing: '+result.stderr.strip())
    return json.loads(result.stdout)['position']


def survey_ray(tcp,distance,digsite_ids):
    """An in-site public bearing, independent of whether the slope is walkable."""
    start=tcp['player']['position'];heading=tcp['tool']['heading_radians']
    site=site_boundaries.active_site(tcp['tool'].get('map',0),start,digsite_ids)
    requested=distance
    distance=site_boundaries.clip_distance(site['polygon'],start,heading,distance)
    recovery=False
    if distance<1.5:
        # At an edge the noisy telescope can point outward. Take a short
        # inward step using the public polygon, then survey again.
        heading=math.atan2(site['center'][1]-start[1],site['center'][0]-start[0])
        distance=site_boundaries.clip_distance(site['polygon'],start,heading,min(requested,7.))
        recovery=True
    if distance<1.5:raise RuntimeError('no useful in-site survey step')
    goal=[start[0]+math.cos(heading)*distance,start[1]+math.sin(heading)*distance,start[2]]
    # The waypoint is inferred from the ordinary telescope, never a hidden find.
    if not site_boundaries.inside_segment(site['polygon'],start,goal):
        raise RuntimeError('public survey ray leaves the observed active digsite')
    return {'schema':'public_survey_ray_v1','start':start[:3],'requested_goal':goal,
            'points':[start[:3],goal],'heading_radians':heading,'ground_only':False,
            'goal_source':'public_survey_heading_and_color',
            'boundary_guard':{'site_id':site['id'],'requested_distance':requested,
                'clipped_distance':distance,'inward_recovery':recovery,
                'whole_corridor_inside':True,'source':site['source']}}


def survey_detour(tcp,distance,digsite_ids,obstructions=(),*,allow_swimming=False):
    ray=survey_ray(tcp,distance,digsite_ids)
    start=ray['start'];goal=ray['requested_goal']
    site=site_boundaries.sites()[ray['boundary_guard']['site_id']]
    if allow_swimming:
        return swimming_detour(tcp,ray,site,obstructions)
    result=route(tcp['tool'].get('map',0),start,goal,obstructions) if obstructions else route(tcp['tool'].get('map',0),start,goal)
    corridor=[start,*result['points']]
    if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):
        raise RuntimeError('ground corridor leaves the observed active digsite')
    result.update(start=start,requested_goal=goal,goal_source=ray['goal_source'],
                  boundary_guard=ray['boundary_guard'])
    return result


def swimming_detour(tcp,ray,site,obstructions):
    """Extend the public bearing only as far as a reachable dry shore."""
    start=ray['start'];heading=ray['heading_radians'];attempts=[]
    for distance in [ray['boundary_guard']['clipped_distance'],7,14,21,35,56]:
        distance=site_boundaries.clip_distance(site['polygon'],start,heading,distance)
        goal=[start[0]+math.cos(heading)*distance,start[1]+math.sin(heading)*distance,start[2]]
        try:result=route(site['map'],start,goal,obstructions,allow_swimming=True)
        except RuntimeError as error:
            attempts.append({'goal':goal,'failure':str(error)});continue
        corridor=[start,*result['points']]
        if math.dist(start[:2],corridor[-1][:2])<1.5:continue
        if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):continue
        # A dry bank behind the player is not progress along this bearing.
        progress=(corridor[-1][0]-start[0])*math.cos(heading)+(corridor[-1][1]-start[1])*math.sin(heading)
        if progress<1.5:continue
        if sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))>140:continue
        result.update(start=start,requested_goal=goal,goal_source=ray['goal_source'],
            dry_goal_attempts=attempts,boundary_guard=ray['boundary_guard'])
        return result
    raise RuntimeError('no bounded in-site walk/swim corridor to dry ground along the public survey bearing')


def walk_plan(tcp,distance,digsite_ids,recovery=None,*,allow_swimming=False):
    start=tcp['player']['position'];pending=(recovery or {}).get('pending_ground_route')
    if pending:
        site=site_boundaries.active_site(tcp['tool'].get('map',0),start,digsite_ids)
        remaining=[p[:] for p in pending['remaining_ground_points']]
        while remaining and math.dist(start[:2],remaining[0][:2])<=.75:remaining.pop(0)
        if remaining and site['id']==pending['boundary_guard']['site_id']:
            corridor=[start,*remaining]
            if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):
                raise RuntimeError('retained ground detour leaves the observed active digsite')
            return {**pending,'start':start[:3],'points':remaining,
                'remaining_ground_points':remaining,'detour_committed':True,
                'retained_survey_detour':True,'boundary_guard':{**pending['boundary_guard']}}
    obstructions=(recovery or {}).get('ground_obstructions',[])
    planned=survey_detour(tcp,distance,digsite_ids,obstructions,allow_swimming=allow_swimming)
    corridor=[start,*planned['points']]
    length=sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))
    planned['detour_committed']=length>max(distance*1.5,distance+2)
    return planned


def low_step_hop(current,target,recovery,grounded=True):
    rise=target[2]-current[2]
    if grounded and (recovery or {}).get('attempt') and .5<rise<=1.25 and math.dist(current[:2],target[:2])<=4:
        return {'observed_feet':current[:3],'public_ground_waypoint':target,
            'predicted_rise':rise,'maximum_rise':1.25,'source':'public navmesh height and failed physical displacement'}
    return None


def dry_cast_plan(tcp,extra):
    """Shallow water may report not-swimming while the feet remain submerged."""
    start=tcp['player']['position'];map_id=extra['world_map']
    try:near=route(map_id,start,start,allow_swimming=True)
    except RuntimeError:near=None
    if not extra['swimming'] and near and math.dist(start[:3],near['points'][-1])<=1.25:
        return None
    site=site_boundaries.active_site(map_id,start,extra['digsite_ids']);choices=[]
    for index in range(16):
        heading=start[3]+index*math.tau/16
        for distance in [7,14,21,35,56]:
            distance=site_boundaries.clip_distance(site['polygon'],start,heading,distance)
            goal=[start[0]+math.cos(heading)*distance,start[1]+math.sin(heading)*distance,start[2]]
            try:planned=route(map_id,start,goal,allow_swimming=True)
            except RuntimeError:continue
            corridor=[start,*planned['points']]
            if math.dist(start[:2],corridor[-1][:2])<1.5:continue
            if not all(site_boundaries.inside_segment(site['polygon'],a,b) for a,b in zip(corridor,corridor[1:])):continue
            length=sum(math.dist(a[:2],b[:2]) for a,b in zip(corridor,corridor[1:]))
            if length>140:continue
            planned.update(start=start[:3],requested_goal=goal,goal_source='public_player_facing_and_site_polygon',
                boundary_guard={'site_id':site['id'],'whole_corridor_inside':True,'source':site['source']})
            choices.append((length,planned));break
    if not choices:raise RuntimeError('no bounded dry Survey stance inside the public digsite')
    return min(choices,key=lambda c:c[0])[1]


def walk(inputs,tcp,distance,digsite_ids,recovery=None,grounded=True,path=None):
    import time
    from .observation.archaeology import Observer,angle_error
    planned=walk_plan(tcp,distance,digsite_ids,recovery,allow_swimming=True);observer=Observer();executed=[]
    if planned.get('water_polygons'):
        from .swim_navigation import cross
        return cross(inputs,observer,planned,path)
    # Walk a bounded section of the ground corridor, then survey again. The
    # mesh defines walkable slopes and holes around static solid obstacles.
    target=next((p for p in planned['points'] if math.dist(p[:2],planned['start'][:2])>.15),None)
    if not target:
        planned=walk_plan(tcp,max(10,distance*2),digsite_ids,recovery)
        target=next((p for p in planned['points'] if math.dist(p[:2],planned['start'][:2])>.15),None)
    if not target:raise RuntimeError('navigation mesh provides no useful ground displacement')
    for _ in range(8):
        current=observer.poll(0)['player']['position']
        heading=math.atan2(target[1]-current[1],target[0]-current[0])
        error=angle_error(heading,current[3])
        if abs(error)<=.12:break
        hold=min(.55,max(.04,abs(error)/math.pi))
        inputs.key('a' if error>0 else 'd',hold=hold);time.sleep(.25)
        executed.append({'key':'a' if error>0 else 'd','hold':hold})
    else:raise RuntimeError('could not face the walkable ground waypoint')
    hold=min(distance/7,math.dist(current[:2],target[:2])/7,2.)
    planned['walking_goal']=target
    if hold<.02:raise RuntimeError('ground waypoint is too close for a useful walk')
    hop=low_step_hop(current,target,recovery,grounded)
    if hop:
        inputs.key('space',hold=.15);executed.append({'key':'space','hold':.15})
    inputs.key('w',hold=hold);time.sleep(.3)
    if hop:time.sleep(.7)
    executed.append({'key':'w','hold':hold})
    planned.update(physical_inputs=executed,low_step_hop=hop,after=observer.poll(0)['player']['position'],
                   steering_source='public_static_ground_navigation_mesh')
    remaining=[p[:] for p in planned['points']]
    while remaining and math.dist(remaining[0][:2],planned['start'][:2])<=.15:remaining.pop(0)
    while remaining and math.dist(remaining[0][:2],planned['after'][:2])<=.75:remaining.pop(0)
    planned['remaining_ground_points']=remaining if planned['detour_committed'] else []
    planned['boundary_guard']['observed_after_inside']=site_boundaries.contains(
        site_boundaries.sites()[planned['boundary_guard']['site_id']]['polygon'],planned['after'])
    return hold,planned

"""Compute flight height from public route surfaces and live departure height."""
import math
import statistics
from tools.client_compatibility import terrain_geometry, model_collision
from . import flight_path


def plan(row, target, *, maximum_distance=750,near_ground=None,arrival_tolerance=0):
    pose=row.get('owned_pose')
    if not pose:raise RuntimeError('calculated ascent requires authenticated owned height telemetry')
    world=row['archaeology']['world'];map_id=world['instance']
    start=[world['north'],world['west'],pose['height_yards']]
    end=[target['north'],target['west'],start[2]]
    distance=math.dist(start[:2],end[:2])
    near_ground=row['archaeology'].get('can_survey',False) if near_ground is None else near_ground
    if distance>maximum_distance:raise RuntimeError('flight clearance route exceeds its bounded route range')
    route_distance=max(0,distance-arrival_tolerance)
    if distance>0:
        end=[start[i]+(end[i]-start[i])*route_distance/distance for i in range(3)]
    distance=route_distance
    surface=model_collision.supporting_surface(map_id,start)
    # Legacy geometry is a reference, never an authoritative live terrain API.
    if row['archaeology']['grounded']:
        nearby=[z for z in (surface['terrain_height'],model_collision.column(map_id,start)['support_height'])
                if z is not None and abs(z-start[2])<=2.5]
        if not nearby:raise RuntimeError('reference terrain does not match the observed departure floor')
    columns=[]
    for index in range(math.ceil(distance/5)+1):
        fraction=min(1,index*5/max(distance,.01))
        point=[start[i]+(end[i]-start[i])*fraction for i in range(3)]
        column=model_collision.supporting_surface(map_id,point)
        if column['highest_surface'] is None or not math.isfinite(column['highest_surface']):
            raise RuntimeError('flight corridor has no finite reference surface')
        if near_ground:column['support_height']=model_collision.column(map_id,point).get('support_height')
        columns.append({'north':point[0],'west':point[1],**column})
    # Reserve a body and sampling margin. Duration follows the height gap and
    # measured velocity; this margin is in yards, not a fixed key-hold time.
    ceiling=max(start[2],max(c['highest_surface'] for c in columns)+8)
    margin=8;low_route_clear=None
    path=flight_path.envelope(columns,start,8)
    if near_ground:
        low_path=flight_path.envelope(columns,start,3,local_floor=True)
        low_route_clear=flight_path.checked(low_path,start,map_id,model_collision.clear_body_segment)
        if low_route_clear:path=low_path;margin=3;ceiling=max(p['height_yards'] for p in path)
    return {'ceiling_yards':ceiling,'departure_height_yards':start[2],
            'required_climb_yards':ceiling-start[2],'surface_margin_yards':margin,
            'near_ground_requested':near_ground,'near_ground_route_clear':low_route_clear,
            'planned_horizontal_yards':distance,'arrival_tolerance_yards':arrival_tolerance,
            'flight_profile':'above_local_floor' if near_ground and low_route_clear else 'above_corridor_obstacles',
            'path':path,'takeoff_height_yards':path[0]['height_yards'],
            'path_basis':'shortest upper envelope in the direct route vertical plane',
            'columns':columns,'source':'legacy public MAPS/VMAP corridor, departure checked against live height',
            'live_client_terrain_asset_match_verified':False}


def vertical_speed(pose):
    rates=[]
    samples=pose.get('samples',[])
    for a,b in zip(samples,samples[1:]):
        elapsed=((b['client_uptime_ms']-a['client_uptime_ms'])%2**32)/1000
        stationary=math.hypot(a.get('north',0)-b.get('north',0),a.get('west',0)-b.get('west',0))<.75
        if .05<=elapsed<=2 and stationary:
            rate=(b['height_yards']-a['height_yards'])/elapsed
            if 1<rate<100:rates.append(rate)
    return statistics.median(rates[-6:]) if rates else None


def remaining_seconds(pose, ceiling, *, flight_speed=None):
    speed=vertical_speed(pose)
    # A takeoff packet precedes the first periodic height heartbeat. During
    # this owned, vertical-only ascent, the public flight speed supplies its
    # rate until two captured positions can measure it directly.
    if speed is None and pose.get('flying') and pose.get('ascending'):
        if isinstance(flight_speed,(int,float)) and math.isfinite(flight_speed) and 0<flight_speed<100:
            speed=flight_speed
    gap=max(0,ceiling-pose['height_yards'])
    return gap/speed if speed else None

"""Compute flight height from public route surfaces and live departure height."""
import math
import statistics
from tools.client_compatibility import terrain_geometry, model_collision


def plan(row, target):
    pose=row.get('owned_pose')
    if not pose:raise RuntimeError('calculated ascent requires authenticated owned height telemetry')
    world=row['archaeology']['world'];map_id=world['instance']
    start=[world['north'],world['west'],pose['height_yards']]
    end=[target['north'],target['west'],start[2]]
    distance=math.dist(start[:2],end[:2])
    if distance>750:raise RuntimeError('flight clearance route exceeds the digsite range')
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
        if column['highest_surface'] is None:raise RuntimeError('flight corridor has no reference surface')
        columns.append({'north':point[0],'west':point[1],**column})
    # Reserve a body and sampling margin. Duration follows the height gap and
    # measured velocity; this margin is in yards, not a fixed key-hold time.
    ceiling=max(start[2],max(c['highest_surface'] for c in columns)+8)
    if ceiling-start[2]>100:raise RuntimeError('reference corridor requires excessive climb')
    return {'ceiling_yards':ceiling,'departure_height_yards':start[2],
            'required_climb_yards':ceiling-start[2],'surface_margin_yards':8,
            'columns':columns,'source':'legacy public MAPS/VMAP corridor, departure checked against live height',
            'live_client_terrain_asset_match_verified':False}


def vertical_speed(pose):
    rates=[]
    samples=pose.get('samples',[])
    for a,b in zip(samples,samples[1:]):
        elapsed=((b['client_uptime_ms']-a['client_uptime_ms'])%2**32)/1000
        if .05<=elapsed<=2 and a['ascending'] and b['ascending']:
            rate=(b['height_yards']-a['height_yards'])/elapsed
            if 1<rate<100:rates.append(rate)
    return statistics.median(rates[-6:]) if rates else None


def remaining_seconds(pose, ceiling):
    speed=vertical_speed(pose)
    gap=max(0,ceiling-pose['height_yards'])
    return gap/speed if speed else None

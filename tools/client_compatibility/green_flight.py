"""User-authorized, short terrain recovery; ordinary green movement stays on foot."""
import math
import time
from . import model_collision,site_boundaries,survey_landing,ground_navigation

MAX_DISTANCE=21
MAX_HEIGHT=40
MAX_RECOVERIES=2


def plan(tcp,movement,extra,recovery,reason):
    if not movement['in_world'] or movement['health_percent']<50 or any(
        movement[k] for k in ['dead','in_combat','on_taxi']):
        raise RuntimeError('green terrain flight requires an available healthy character')
    if any(extra[k] for k in ['mounted','flying','falling','swimming','indoors','casting']):
        raise RuntimeError('green terrain flight requires grounded outdoor feet')
    tool=tcp.get('tool') or {}
    if tool.get('color')!='green' or not tool.get('visible',False) or not 0<=time.time()-tool.get('seen_at',0)<=20:
        raise RuntimeError('green terrain flight requires a fresh public green telescope')
    if (recovery or {}).get('green_flights_used',0)>=MAX_RECOVERIES:
        raise RuntimeError('two green terrain flights exhausted this find trial')
    start=tcp['player']['position'][:3]
    site=site_boundaries.active_site(tool['map'],start,extra['digsite_ids'])
    if ground_navigation.water_at(site['map'],start)['water_above_feet']:
        raise RuntimeError('green terrain flight cannot start with submerged feet')
    heading=tool['heading_radians']
    goal,landing=survey_landing.select(site,start,heading,7,maximum_distance=MAX_DISTANCE)
    heights=[]
    for index in range(13):
        point=[start[i]+(goal[i]-start[i])*index/12 for i in range(3)]
        surface=model_collision.supporting_surface(site['map'],point)['highest_surface']
        if surface is None:raise RuntimeError('green flight has an unknown public collision column')
        heights.append(surface)
    ceiling=max(*heights,start[2],goal[2])+8
    if ceiling-start[2]>MAX_HEIGHT or abs(goal[2]-start[2])>MAX_HEIGHT:
        raise RuntimeError('green obstacle exceeds the short flight height budget')
    elevated_start=[*start[:2],ceiling];elevated_goal=[*goal[:2],ceiling]
    if not all(model_collision.clear_body_segment(site['map'],a,b) for a,b in
        [(start,elevated_start),(elevated_start,elevated_goal),(elevated_goal,goal)]):
        raise RuntimeError('green recovery flight corridor intersects public model collision')
    guard={'schema':'green_terrain_recovery_v1','reason':reason,'start':start,
        'site_id':site['id'],'maximum_distance':MAX_DISTANCE,'maximum_height':MAX_HEIGHT,
        'green_flights_used':(recovery or {}).get('green_flights_used',0),
        'ground_recovery':recovery,'public_landing':landing}
    return {'schema':'public_survey_mounted_move_v1','green_terrain_recovery':guard,'legs':[
        {'id':'green_terrain_recovery','mode':'flight','map':site['map'],'position':goal,
         'ceiling':ceiling,'arrival_radius':1.5,'landing_height_tolerance':2,
         'landing_avoidance_frozen':True,'ground_connection_origin':start,
         'survey_progress':{'start':start,'heading_radians':heading,'minimum_bearing_progress':1.5}}]}


def check_position(guard,position,map_id=None):
    start=guard['start'];site=site_boundaries.sites()[guard['site_id']]
    if (map_id is not None and map_id!=site['map'] or
        math.dist(start[:2],position[:2])>MAX_DISTANCE+2 or
        abs(position[2]-start[2])>MAX_HEIGHT+2 or
        not site_boundaries.inside_segment(site['polygon'],start,position)):
        raise RuntimeError('green recovery exceeded its short in-site flight envelope')


def execute(tcp,path,recovery,reason):
    from . import archaeology_inputs,travel_trial,ground_navigation
    from .observation.archaeology import Observer
    tcp=Observer().poll(0)
    movement,extra=archaeology_inputs.screenshot(path)
    route=plan(tcp,movement,extra,recovery,reason)
    directory=path.parent/f'mounted_move_{time.time_ns()}'
    result=travel_trial.run(route,directory,maximum_steps=30)
    if not result['completed']:raise RuntimeError('green terrain flight failed: '+str(result['failure']))
    movement,after=archaeology_inputs.screenshot(path)
    position=Observer().poll(0)['player']['position']
    check_position(route['green_terrain_recovery'],position)
    if any(after[k] for k in ['mounted','flying','falling','swimming']):
        raise RuntimeError('green recovery did not restore unmounted dry-ground movement')
    if ground_navigation.water_at(route['legs'][0]['map'],position)['water_above_feet']:
        raise RuntimeError('green recovery landed with submerged feet')
    return None,{'green_terrain_recovery':route['green_terrain_recovery'],
        'mounted_travel_episode':directory.name,'remaining_ground_points':[],
        'after':position,'dry_unmounted_arrival':True,
        'boundary_guard':{'site_id':route['green_terrain_recovery']['site_id'],
            'observed_after_inside':True,'whole_corridor_inside':True}}

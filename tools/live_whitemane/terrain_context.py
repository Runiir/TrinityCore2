"""Reference obstacle facts and bounded ground detours; never chooses inputs."""
import math
from tools.client_compatibility import model_collision,terrain_geometry,ground_navigation
from . import boundaries


def facts(row,target=None,*,climb_yards=8):
    pose=row.get('owned_pose') or {};world=row['archaeology'].get('world')
    result={'source':'extracted reference MAPS/VMAP geometry',
        'live_asset_match_verified':False,'available':False}
    if not world or pose.get('height_yards') is None:return result
    point=[world['north'],world['west'],pose['height_yards']];map_id=world['instance']
    try:
        column=model_collision.column(map_id,point);terrain=terrain_geometry.height(map_id,point)
        floors=[h for h in (terrain,column.get('support_height')) if h is not None and h<=point[2]+2.5]
        floor=max(floors) if floors else None
        result.update(available=True,origin=world,height_yards=point[2],
            reference_floor_height_yards=floor,
            observed_height_above_reference_floor_yards=point[2]-floor if floor is not None else None,
            departure_floor_agrees=bool(floor is not None and abs(point[2]-floor)<=2.5),
            reference_roof_column_height_yards=column.get('collision_height'))
        area=column.get('area')
        result['reference_WMO_indoors']=not bool(area['mogp_flags']&8) if area else None
        result['reference_climb_clear']=model_collision.clear_body_segment(map_id,point,
            [point[0],point[1],point[2]+max(0,climb_yards)])
        if target and target.get('instance')==map_id:
            distance=math.hypot(target['north']-point[0],target['west']-point[1])
            ratio=min(1,8/max(.01,distance))
            endpoint=[point[0]+ratio*(target['north']-point[0]),point[1]+ratio*(target['west']-point[1]),point[2]]
            result['reference_forward_clear']=model_collision.clear_body_segment(map_id,point,endpoint)
            result['forward_probe_yards']=min(distance,8)
    except (RuntimeError,OSError,ValueError) as error:
        result['reference_error']=str(error)
    return result


def detour(row,target,*,maximum_yards=24):
    """Return a connected, checked prefix toward the retained original target."""
    a=row['archaeology'];pose=row.get('owned_pose') or {};world=a.get('world')
    result={'available':False,'live_asset_match_verified':False,
        'source':'reference MMAP ground path checked against VMAP body collision'}
    if (not world or not target or target.get('instance')!=world['instance']
            or a.get('swimming') or a.get('flying') or pose.get('height_yards') is None):return result
    start=[world['north'],world['west'],pose['height_yards']]
    if math.hypot(target['north']-start[0],target['west']-start[1])>150:return result
    try:
        route=ground_navigation.route(world['instance'],start,[target['north'],target['west'],start[2]])
        points=route.get('points') or []
        if not route.get('complete') or not route.get('ground_only') or not points:
            raise RuntimeError('reference ground path is incomplete')
        if math.dist(start[:2],points[0][:2])>2 or abs(start[2]-points[0][2])>2.5:
            raise RuntimeError('reference path projects the player to a different floor')
        accepted=[start];length=0
        site=boundaries.sites().get(str(a.get('site_id'))) if a.get('can_survey') else None
        if a.get('can_survey') and (not site or site['map']!=world['instance']):
            raise RuntimeError('reference detour has no active site perimeter')
        for goal in points:
            previous=accepted[-1];distance=math.dist(previous[:2],goal[:2])
            if distance<.25:continue
            ratio=min(1,(maximum_yards-length)/distance)
            endpoint=[x+ratio*(y-x) for x,y in zip(previous,goal)]
            if site and not boundaries.inside_segment(site['polygon'],previous,endpoint):
                raise RuntimeError('reference detour crosses the digsite perimeter')
            # Check shorter body rays along sloped/long navigation edges.
            count=max(1,math.ceil(math.dist(previous,endpoint)/8))
            for index in range(count):
                p=[x+(y-x)*index/count for x,y in zip(previous,endpoint)]
                q=[x+(y-x)*(index+1)/count for x,y in zip(previous,endpoint)]
                if not model_collision.clear_body_segment(world['instance'],p,q):
                    raise RuntimeError('reference detour intersects a wall or ceiling')
            accepted.append(endpoint);length+=distance*ratio
            if length>=maximum_yards-.01:break
        if len(accepted)<2:raise RuntimeError('reference detour has no useful displacement')
        result.update(available=True,points=[{'instance':world['instance'],'north':p[0],
            'west':p[1],'height_yards':p[2]} for p in accepted[1:]],
            length_yards=length,original_destination=target,reference_path_complete=True,
            prefix_reaches_original_destination=math.dist(accepted[-1][:2],[target['north'],target['west']])<=1)
    except (RuntimeError,OSError,ValueError) as error:result['reference_error']=str(error)
    return result


def move(folder,row,selected,request,response,alternatives,route):
    from .fast_waypoint import walk
    from . import laya_ui
    if selected=='follow_detour':
        points=route['points'];target=points[-1]
        guidance={'source':'Laya-selected reference ground detour','ground_route':points}
    else:
        target=alternatives[selected]['target'];guidance={'source':'Laya-selected short obstacle recovery'}
    return walk(folder,target,flying=row['archaeology']['flying'],tolerance=.5,
        site_id=row['archaeology'].get('site_id') if row['archaeology'].get('can_survey') else None,
        guidance=guidance,approved_intent=(selected,{'model':laya_ui.MODEL,'revision':laya_ui.REVISION},request,response))

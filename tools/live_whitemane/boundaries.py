"""Guard the owned local route with public map perimeters and an inward margin."""
import json
import math
import heapq
from functools import lru_cache
from . import runtime
from tools.client_compatibility.site_boundaries import contains, inside_segment, clip_distance


@lru_cache(maxsize=1)
def sites():
    return json.loads((runtime.ROOT/'evidence/boundary_data/polygons.json').read_text())


def edge_distance(point,a,b):
    delta=[b[i]-a[i] for i in range(2)];length=sum(x*x for x in delta)
    fraction=max(0,min(1,sum((point[i]-a[i])*delta[i] for i in range(2))/length)) if length else 0
    return math.dist(point,[a[i]+fraction*delta[i] for i in range(2)])


def interior_route(polygon,start,end,*,margin=8):
    """Shortest visible-corner route, with inward clearance at concavities."""
    if not contains(polygon,start) or not contains(polygon,end):return None
    if inside_segment(polygon,start,end):return [end]
    area=sum(a[0]*b[1]-b[0]*a[1] for a,b in zip(polygon,polygon[1:]+polygon[:1]))
    orientation=1 if area>0 else -1
    points=[start,end]
    for index,vertex in enumerate(polygon):
        previous=polygon[index-1];following=polygon[(index+1)%len(polygon)]
        before=[vertex[i]-previous[i] for i in range(2)]
        after=[following[i]-vertex[i] for i in range(2)]
        if orientation*(before[0]*after[1]-before[1]*after[0])>=0:continue
        before=[x/math.hypot(*before) for x in before]
        after=[x/math.hypot(*after) for x in after]
        left=[-orientation*before[1],orientation*before[0]]
        right=[-orientation*after[1],orientation*after[0]]
        divisor=1+sum(a*b for a,b in zip(left,right))
        if divisor<1e-6:continue
        corner=[vertex[i]+margin*(left[i]+right[i])/divisor for i in range(2)]
        clearance=min(edge_distance(corner,a,b) for a,b in zip(polygon,polygon[1:]+polygon[:1]))
        if contains(polygon,corner) and clearance>=margin-1e-6:points.append(corner)
    queue=[(0,0)];cost={0:0};parent={}
    while queue:
        distance,index=heapq.heappop(queue)
        if distance!=cost[index]:continue
        if index==1:
            result=[]
            while index:
                result.append(points[index]);index=parent[index]
            return result[::-1]
        for other,point in enumerate(points):
            if other==index or not inside_segment(polygon,points[index],point):continue
            length=distance+math.dist(points[index],point)
            if length<cost.get(other,math.inf):
                cost[other]=length;parent[other]=index;heapq.heappush(queue,(length,other))
    return None


def constrain(row, guide,*,site_id=None):
    if not guide:return guide
    a=row['archaeology'];world=a['world']
    site_id=a['site_id'] if site_id is None else site_id
    site=sites().get(str(site_id))
    start=[world['north'],world['west']]
    if not site or site['map']!=world['instance'] or not contains(site['polygon'],start):
        raise RuntimeError('current point does not match the active public digsite perimeter')
    target=guide['world'];end=[target['north'],target['west']]
    distance=math.dist(start,end);angle=math.atan2(end[1]-start[1],end[0]-start[0])
    # An inside endpoint can lie in a different arm of a concave site. Keep
    # a recorded marker as the goal, but approach the next interior corner.
    # An uncertain telescope ray still stops at its first boundary exit.
    if guide['source']=='GatherMate marker' and not inside_segment(site['polygon'],start,end):
        route=interior_route(site['polygon'],start,end)
        if route:
            corner=route[0];length=math.dist(start,corner)
            error=(math.atan2(corner[1]-start[1],corner[0]-start[0])-
                row['movement']['facing_radians']+math.pi)%math.tau-math.pi
            return {**guide,'world':{'instance':world['instance'],'north':corner[0],'west':corner[1]},
                'unclipped_world':target,'distance_yards':round(length,2),'arrived':False,
                'color':'green' if length<=40 else 'yellow' if length<=80 else 'red',
                'heading_relative_to_player':'aligned' if abs(error)<=.18 else 'left' if error>0 else 'right',
                'arrival_tolerance_yards':.5,'boundary_route':route,
                'boundary_route_source':'public polygon interior corners; all segments checked',
                'boundary_site_id':int(site_id),'original_marker_arrival_confirmed':False}
    length=clip_distance(site['polygon'],start,angle,distance)
    if length<distance:
        length=max(0,length-7) # shared helper reserves one yard, totaling eight
        target={'instance':world['instance'],'north':start[0]+math.cos(angle)*length,
                'west':start[1]+math.sin(angle)*length}
        guide={**guide,'world':target,'unclipped_world':guide['world'],
               'distance_yards':round(length,2),'arrived':length<=5,'boundary_clipped':True}
    tolerance=guide.get('arrival_tolerance_yards',5)
    return {**guide,'arrived':guide.get('arrived',False) or guide['distance_yards']<=tolerance,
        'boundary_site_id':int(site_id)}


def check_point(site_id, world):
    site=sites().get(str(site_id))
    if not site or site['map']!=world['instance'] or not contains(site['polygon'],[world['north'],world['west']]):
        raise RuntimeError('movement reached the digsite boundary')

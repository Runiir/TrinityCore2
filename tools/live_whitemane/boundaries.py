"""Guard the owned local route with public map perimeters and an inward margin."""
import json
import math
from functools import lru_cache
from . import runtime
from tools.client_compatibility.site_boundaries import contains, inside_segment, clip_distance


@lru_cache(maxsize=1)
def sites():
    return json.loads((runtime.ROOT/'evidence/boundary_data/polygons.json').read_text())


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
    length=clip_distance(site['polygon'],start,angle,distance)
    if length<distance:
        length=max(0,length-7) # shared helper reserves one yard, totaling eight
        target={'instance':world['instance'],'north':start[0]+math.cos(angle)*length,
                'west':start[1]+math.sin(angle)*length}
        guide={**guide,'world':target,'unclipped_world':guide['world'],
               'distance_yards':round(length,2),'arrived':length<=5,'boundary_clipped':True}
    return {**guide,'boundary_site_id':int(site_id)}


def check_point(site_id, world):
    site=sites().get(str(site_id))
    if not site or site['map']!=world['instance'] or not contains(site['polygon'],[world['north'],world['west']]):
        raise RuntimeError('movement reached the digsite boundary')

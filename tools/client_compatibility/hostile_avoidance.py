"""Conservative aggro clearance from ordinary visible units and public factions."""
from functools import lru_cache
import math
from .observation.map_data import table,floating
from .world.objects import INDEX
from . import site_boundaries,ground_navigation


@lru_cache(maxsize=1)
def factions():return {r[0]:r for r in table('FactionTemplate')[0]}


def visible_hostiles(units,map_id,player_faction,player_level):
    f=factions();player=f.get(player_faction);result=[]
    if not player:return result
    for guid,unit in units.items():
        values=unit['fields'];enemy=f.get(values.get(INDEX['UNIT_FIELD_FACTIONTEMPLATE'],0))
        if unit['map']!=map_id or not enemy or not values.get(INDEX['UNIT_FIELD_HEALTH'],0):continue
        hostile=enemy[0]!=player[0] and (player[1] in enemy[6:10] or bool(enemy[3]&player[5]) or
            bool(enemy[2]&0x2000 and not (player[1] in enemy[10:14] or enemy[3]&player[4])))
        if not hostile:continue
        level=values.get(INDEX['UNIT_FIELD_LEVEL'],player_level)
        reach=floating(values.get(INDEX['UNIT_FIELD_COMBATREACH'],0))
        radius=max(5,min(45,20+level-player_level))+max(1.5,reach)+3
        result.append({'guid':guid,'position':list(unit['movement']['position'][:3]),
            'level':level,'clearance_radius':radius,'source':'ordinary visible native creature create/update'})
    return result


def clear(point,hostiles):
    return all(abs(point[2]-h['position'][2])>18 or math.dist(point[:2],h['position'][:2])>h['clearance_radius'] for h in hostiles)


def landing(map_id,goal,hostiles,observed_ids,start=None):
    if clear(goal,hostiles):return goal,None
    sites=[s for sid,s in site_boundaries.sites().items() if sid in observed_ids and s['map']==map_id and site_boundaries.contains(s['polygon'],goal)]
    candidates=[]
    for radius in [3,6,10,15,22]:
        for i in range(16):
            angle=math.tau*i/16;xy=[goal[0]+math.cos(angle)*radius,goal[1]+math.sin(angle)*radius]
            if sites and not site_boundaries.contains(sites[0]['polygon'],xy):continue
            if sites and start and site_boundaries.contains(sites[0]['polygon'],start) and not site_boundaries.inside_segment(sites[0]['polygon'],start,xy):continue
            try:
                point=ground_navigation.ground_point(map_id,xy)
                point=ground_navigation.landing_point(map_id,point,radius=3,start=goal)
                if sites:ground_navigation.site_ground_patch(map_id,point)
            except RuntimeError:continue
            if sites and (not site_boundaries.contains(sites[0]['polygon'],point) or
                start and site_boundaries.contains(sites[0]['polygon'],start) and
                not site_boundaries.inside_segment(sites[0]['polygon'],start,point)):continue
            if clear(point,hostiles):candidates.append(point)
        if candidates:break
    if not candidates:raise RuntimeError('no safe public landing point near visible hostiles')
    point=min(candidates,key=lambda p:math.dist(p,goal[:3]))
    return point,{'requested_position':goal,'position':point,'visible_hostiles':hostiles,
        'source':'ordinary visible creatures and public faction/level aggro clearance'}

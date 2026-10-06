"""Bounded portal view hints learned only from confirmed named interactions."""
import json
import math
import time
from . import runtime


def read(portal,row):
    path=runtime.ROOT/'run/portal_views.json'
    saved=json.loads(path.read_text()) if path.exists() else {}
    hint=saved.get(portal.get('key',portal['destination']))
    world=row['archaeology'].get('world')
    if (not hint or hint.get('runtime')!=row.get('runtime') or not world
            or hint['world']['instance']!=world['instance']
            or math.hypot(hint['world']['north']-portal['from']['north'],
                hint['world']['west']-portal['from']['west'])>30):return None
    return hint


def remember(portal,row,interaction,after,*,evidence=None):
    names={'Portal to '+portal['destination']}
    if portal.get('key')=='org-uldum':names.add('Portal to Uldum')
    ui=row.get('farm_ui') or {};soft=ui.get('soft_interact') or {}
    name=interaction.get('name') or soft.get('name') or ui.get('tooltip')
    start=row['archaeology'].get('world');end=after['archaeology'].get('world')
    dest=portal['to'];facing=row['movement'].get('facing_radians')
    if (name not in names or not start or not end or facing is None
            or start['instance']!=portal['from']['instance'] or end['instance']!=dest['instance']
            or math.hypot(end['north']-dest['north'],end['west']-dest['west'])>=100):return False
    path=runtime.ROOT/'run/portal_views.json'
    saved=json.loads(path.read_text()) if path.exists() else {}
    saved[portal.get('key',portal['destination'])]={'runtime':row.get('runtime'),
        'world':start,'facing_radians':facing,'zoom':ui.get('camera_zoom'),
        'name':name,'at':time.time(),'source':'named public interaction with confirmed destination arrival',
        'evidence':evidence}
    cursor=interaction.get('cursor')
    if not cursor and interaction.get('point'):
        cursor={'x':interaction['point'][0]/runtime.WIDTH,'y':interaction['point'][1]/runtime.HEIGHT}
    if cursor and all(isinstance(cursor.get(k),(int,float)) and 0<=cursor[k]<1 for k in ('x','y')):
        saved[portal.get('key',portal['destination'])].update(cursor=cursor,
            viewport=[runtime.WIDTH,runtime.HEIGHT],view_preset=2)
    runtime.write(path,dict(sorted(saved.items(),key=lambda item:item[1]['at'],reverse=True)[:8]))
    return True


def search_point(hint,row):
    """A verified prior mouseover is only the first probe, never a blind click."""
    if not hint or not hint.get('cursor') or hint.get('viewport')!=[runtime.WIDTH,runtime.HEIGHT]:return None
    world=row['archaeology'].get('world');old=hint['world'];zoom=row['farm_ui'].get('camera_zoom')
    facing=row['movement'].get('facing_radians')
    if (hint.get('runtime')!=row.get('runtime') or not world or world['instance']!=old['instance']
            or math.hypot(world['north']-old['north'],world['west']-old['west'])>1
            or facing is None or abs((facing-hint['facing_radians']+math.pi)%math.tau-math.pi)>.18
            or zoom is None or hint.get('zoom') is None or abs(zoom-hint['zoom'])>1
            or hint.get('view_preset')!=2):return None
    point=hint['cursor']
    return round(point['x']*runtime.WIDTH),round(point['y']*runtime.HEIGHT)


def aim(hint,row):
    world=row['archaeology']['world'];heading=hint['facing_radians']
    return {**world,'north':world['north']+8*math.cos(heading),
        'west':world['west']+8*math.sin(heading)}

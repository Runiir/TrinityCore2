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
    runtime.write(path,dict(sorted(saved.items(),key=lambda item:item[1]['at'],reverse=True)[:8]))
    return True


def aim(hint,row):
    world=row['archaeology']['world'];heading=hint['facing_radians']
    return {**world,'north':world['north']+8*math.cos(heading),
        'west':world['west']+8*math.sin(heading)}

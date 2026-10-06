"""Bounded local tooltip-search progress across Laya's interaction attempts."""
import hashlib
import json
import math
import time
from . import runtime


def resume(row,names,points):
    path=runtime.ROOT/'run/interaction_search.json'
    saved=json.loads(path.read_text()) if path.exists() else {}
    key=hashlib.sha256('\n'.join(sorted(names)).encode()).hexdigest()[:16]
    a=row['archaeology'];m=row['movement'];world=a.get('world')
    stamp={'runtime':row.get('runtime'),'world':world,'facing':m.get('facing_radians'),
        'zoom':row['farm_ui'].get('camera_zoom'),
        'guid':(row.get('visible_find') or {}).get('guid')}
    old=saved.get(key) or {};start=old.get('stamp') or {};p=start.get('world')
    same=(start.get('runtime')==stamp['runtime'] and start.get('guid')==stamp['guid']
        and start.get('zoom')==stamp['zoom'] and time.time()-old.get('at',0)<300)
    if world and p:
        same=same and world['instance']==p['instance'] and math.hypot(
            world['north']-p['north'],world['west']-p['west'])<=2
    elif world or p:same=False
    facing=m.get('facing_radians');old_facing=start.get('facing')
    if facing is not None and old_facing is not None:
        same=same and abs((facing-old_facing+math.pi)%math.tau-math.pi)<=.18
    # Point order can change if a real mouseover becomes visible.
    signature=hashlib.sha256(json.dumps(points).encode()).hexdigest()
    same=same and old.get('points_sha256')==signature
    index=old.get('index',0) if same else 0
    return {'path':path,'saved':saved,'key':key,'stamp':stamp,
        'points_sha256':signature,'index':index if index<len(points) else 0}


def save(search,index,*,completed=False):
    saved=search['saved'];key=search['key']
    if completed:saved.pop(key,None)
    else:saved[key]={'stamp':search['stamp'],'index':index,'at':time.time(),
        'points_sha256':search['points_sha256']}
    retained=dict(sorted(saved.items(),key=lambda item:item[1]['at'],reverse=True)[:8])
    runtime.write(search['path'],retained)

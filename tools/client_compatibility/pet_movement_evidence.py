"""Attribute native owned-pet splines and their independently decoded client packets."""
import math
from types import SimpleNamespace
from .world.buffer import Reader
from .world.native_objects import guid as native_guid
from .world import creature_movement


def xyz(position):
    if not position.get('available'):raise ValueError('public unit position is unavailable')
    values=[position[k] for k in ('x','y','z')]
    if not all(isinstance(v,(int,float)) and math.isfinite(v) and abs(v)<=17067 for v in values):
        raise ValueError('public unit position is invalid')
    return values


def movement_pairs(packets,session,guid,map_id,since,until):
    rows=[p for p in packets if p.get('session')==session and since<=p.get('time',0)<=until
        and p.get('name')=='SMSG_ON_MONSTER_MOVE']
    pairs=[]
    for row in rows:
        if row.get('direction')!='from_native':continue
        body=bytes.fromhex(row['body'])
        if native_guid(Reader(body))!=guid:continue
        spline=creature_movement.parse(body)
        if spline is None:
            pairs.append({'native':row,'spline':None,'client':None,'unsupported':True});continue
        owner=SimpleNamespace(visible_units={guid:{'map':map_id,'movement':{'position':[0,0,0,0]}}})
        expected=creature_movement.response(owner,'SMSG_ON_MONSTER_MOVE',body)[1].hex()
        matches=[p for p in rows if p.get('direction')=='to_client' and p.get('body')==expected
            and 0<=p['time']-row['time']<2]
        endpoint=(spline['points'][-1] if spline['flags']&0x400000 else spline['points'][0]) if spline['points'] else spline['position']
        pairs.append({'native':row,'client':matches[0] if len(matches)==1 else None,
            'spline':{k:v for k,v in spline.items() if k!='deltas'},'endpoint':endpoint,
            'deltas_hex':spline['deltas'].hex(),'unsupported':False})
    return pairs


def following_paths(pairs):
    return [p for p in pairs if p.get('spline') and p['spline']['face']!=1
        and p['spline']['duration']>0 and math.dist(p['spline']['position'],p['endpoint'])>1]


def follow_motion_checks(pairs,public_before,public_after,owner_position):
    paths=following_paths(pairs);before,after=xyz(public_before),xyz(public_after)
    return {'owned_native_moving_path':bool(paths),'all_owned_splines_supported':all(not p['unsupported'] for p in pairs),
        'all_owned_splines_delivered':bool(pairs) and all(p['client'] is not None for p in pairs),
        'native_endpoint_near_owner':bool(paths) and math.dist(paths[-1]['endpoint'],owner_position)<4,
        'public_pet_displaced':math.dist(before,after)>3,
        'public_pet_near_native_endpoint':bool(paths) and math.dist(after,paths[-1]['endpoint'])<.3,
        'public_pet_near_owner':math.dist(after,owner_position)<4}

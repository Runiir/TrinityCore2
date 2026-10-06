"""Independent pinned wire oracle for attributable native owner swing results."""
import math
from .world.buffer import Reader,Writer
from .world.native_objects import guid
from .world.gameobjects import modern_guid


def translated(body,map_id):
    r=Reader(body);flags,=r.unpack('I');attacker,victim=guid(r),guid(r)
    damage,overkill=r.unpack('ii');count,=r.unpack('B')
    if flags&~0x01870216 or damage<0 or overkill< -1 or count>1:raise ValueError('unsupported native melee header')
    w=Writer().pack('I',flags).guid(*modern_guid(attacker,map_id)).guid(*modern_guid(victim,map_id))
    w.pack('iiiB',damage,0,overkill,count)
    if count:
        school,amount,subdamage=r.unpack('ifi')
        if school!=1 or not math.isfinite(amount) or amount<0 or subdamage!=damage or amount!=float(subdamage):
            raise ValueError('unsupported native melee subdamage')
        w.pack('ifi',school,amount,subdamage)
    elif damage:raise ValueError('native melee damage lacks subdamage')
    state,attacker_state,spell=r.unpack('BII')
    if state>8 or attacker_state or spell or flags&0x10 and damage:raise ValueError('unsupported native melee state')
    w.pack('BII',state,attacker_state,spell)
    if flags&0x800000:
        rage,=r.unpack('i')
        if rage<0:raise ValueError('negative native rage gain')
        w.pack('i',rage)
    r.end();round=w.raw(bytes(14)).finish()
    return {'attacker':attacker,'victim':victim,'hit_info':flags,'damage':damage,'overkill':overkill,
        'body':Writer().bits(0,1).pack('I',len(round)).raw(round).finish().hex()}


def pairs(packets,owner,victim,map_id):
    delivered=[p for p in packets if p.get('name')=='SMSG_ATTACKER_STATE_UPDATE' and p.get('direction')=='to_client']
    used=set();matched=[]
    for p in packets:
        if p.get('name')!='SMSG_ATTACKER_STATE_UPDATE' or p.get('direction')!='from_native':continue
        body=bytes.fromhex(p['body']);r=Reader(body);r.unpack('I')
        if (guid(r),guid(r))!=(owner,victim):continue
        result=translated(body,map_id)
        index=next((i for i,c in enumerate(delivered) if i not in used and c['body']==result['body'] and
            0<=c['time']-p['time']<2),None)
        if index is not None:used.add(index)
        matched.append({'native':p,'expected':result,'client':delivered[index] if index is not None else None})
    return matched,[p for i,p in enumerate(delivered) if i not in used]


def public_events(probe,before_sequence,matched,source,destination):
    return [v for v in probe.get('events',[]) if v.get('sequence',0)>before_sequence and
        v.get('event')=='SWING_DAMAGE' and v.get('source_guid')==source and
        v.get('destination_guid')==destination and any(p['client'] and
            v.get('amount')==p['expected']['damage']>0 and v.get('school')==1 and
            v.get('overkill')==p['expected']['overkill'] and
            isinstance(v.get('timestamp'),(int,float)) and
            abs(v['timestamp']-p['native']['time'])<2 and
            all(bool(v.get(name))==bool(p['expected']['hit_info']&flag) for name,flag in
                (('critical',0x200),('offhand',4),('glancing',0x10000),('crushing',0x20000)))
            for p in matched)]


def health_checks(before,after,matched,public_health,foreign_hits,*,allow_death=False,public_death=False):
    damage=sum(p['expected']['damage']-max(0,p['expected'].get('overkill',-1)) for p in matched)
    return {'positive_owned_damage':damage>0,
        'all_owned_results_delivered':bool(matched) and all(p['client'] for p in matched),
        'target_health_outcome':(0<=after<before if allow_death else 0<after<before),
        'exact_native_health_loss':before-after==damage,
        'exact_public_health':public_health==after or allow_death and after==0 and public_death,
        'no_foreign_target_hits':not foreign_hits}


def stop_request_contract(modern_count,native_count,stops,pre_submit_at):
    if modern_count==native_count==1:return True
    if modern_count or native_count:return False
    return any(p.get('client') and p['native']['time']<=p['client']['time']<pre_submit_at for p in stops)

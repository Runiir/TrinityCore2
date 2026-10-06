"""Match captured native Firebolts to independently decoded client delivery."""
from .world.buffer import Reader
from .world.native_objects import guid
from .world.gameobjects import modern_guid
from .world.pet_casts import decode


def native_cast(name,body):
    r=Reader(body);caster,unit=guid(r),guid(r)
    counter,spell,flags,extra,duration=r.unpack('BIIII');hits=[]
    if name=='SMSG_SPELL_GO':
        count,=r.unpack('B')
        if count>8:raise ValueError('unbounded native hits')
        hits=[r.unpack('Q')[0] for _ in range(count)]
        if r.unpack('B')[0]:raise ValueError('native misses outside this trial')
    target_flags,=r.unpack('I');target=guid(r) if target_flags&2 else 0
    remaining,=r.unpack('I');r.end()
    return {'caster':caster,'unit':unit,'counter':counter,'spell':spell,'flags':flags,
        'extra':extra,'duration':duration,'hits':hits,'target_flags':target_flags,
        'target':target,'remaining':remaining}


def firebolt_checks(packets,session,since,until,pet,target):
    names={'SMSG_SPELL_START','SMSG_SPELL_GO'};pg=modern_guid(pet['guid'],pet['map']);tg=modern_guid(target['guid'],target['map'])
    rows=[p for p in packets if p.get('session')==session and since<=p.get('time',0)<=until and p.get('name') in names]
    native=[];client=[];malformed=False
    for p in rows:
        try:
            body=bytes.fromhex(p['body'])
            if p.get('direction')=='from_native':
                r=Reader(body);caster=guid(r)
                if caster!=pet['guid']:continue
                d=native_cast(p['name'],body)
                if d['spell']==3110:native.append((p,d))
            elif p.get('direction')=='to_client':
                r=Reader(body);caster=r.guid()
                if caster!=pg:continue
                d=decode(p['name'],body)
                if d['spell']==3110:client.append((p,d))
        except (ValueError,KeyError,TypeError):malformed=True
    pairs=[];used=set();active=None;identities=set();lifetime=True;completed=0;authority=True
    for p,n in native:
        authority=authority and n['caster']==n['unit']==pet['guid'] and n['counter']==0 and n['target_flags']==2 and n['target']==target['guid']
        expected={'caster':pg,'unit':pg,'spell':3110,'visual':238900,'flags':n['flags']&~0x40000,
            'extra':n['extra'],'duration':n['duration'],'target_flags':2,'target':tg,
            'hits':[modern_guid(g,pet['map']) for g in n['hits']],'remaining':[(0,n['remaining'])]}
        matches=[(i,c,d) for i,(c,d) in enumerate(client) if c['name']==p['name'] and
            0<=c['time']-p['time']<2 and all(d[k]==v for k,v in expected.items())]
        delivered=matches[0] if len(matches)==1 and matches[0][0] not in used else None
        if delivered:
            i,c,d=delivered;used.add(i);identity=d['cast'];high=identity[1]
            lifetime=lifetime and high>>58==47 and (high>>29)&0x1fff==pet['map'] and (high>>6)&0x7fffff==3110
            if p['name']=='SMSG_SPELL_START':
                lifetime=lifetime and active is None and identity not in identities
                identities.add(identity);active=identity
            else:
                lifetime=lifetime and active==identity;active=None;completed+=1
        pairs.append({'native':p,'decoded_native':n,'client':delivered[1] if delivered else None,
            'decoded_client':delivered[2] if delivered else None})
    checks={'native_firebolt_start':any(p['native']['name']=='SMSG_SPELL_START' for p in pairs),
        'native_firebolt_completion':any(p['native']['name']=='SMSG_SPELL_GO' for p in pairs),
        'firebolt_delivered':bool(pairs) and all(p['client'] for p in pairs),
        'firebolt_cast_lifetime':completed>0 and lifetime,
        'firebolt_native_victim':bool(pairs) and authority and all(n['hits']==[target['guid']] for p,n in native if p['name']=='SMSG_SPELL_GO'),
        'no_unmatched_pet_cast_delivery':len(used)==len(client) and not malformed}
    return checks,pairs

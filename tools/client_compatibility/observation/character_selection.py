"""Read the pinned build60895 character enumeration, including all visual slots."""
from ..world.buffer import Reader


def characters(body):
    r=Reader(body);r.bits(9);head=r.unpack('IIiIIIII')
    if head[0]>50:raise ValueError('character enumeration exceeds its observation bound')
    rows=[]
    for _ in range(head[0]):
        guid=r.guid();realm,slot,race,sex,cls,spec,custom=r.unpack('IBBBBhI')
        if custom:raise ValueError('customized character-list observation is unsupported')
        level,map_id,zone,x,y,z,club=r.unpack('Bii3fQ');guild=r.guid()
        flags=r.unpack('IIIBIII');gear=[r.unpack('IBIBiII') for _ in range(19)]
        tail=r.unpack('iQi5iIIiI');length=r.bits(6);first=r.bits(1);name=r.raw(length).decode()
        r.bits(3);r.unpack('III')
        if tail[2]!=60895:raise ValueError('character enumeration has an unexpected client build')
        rows.append({'guid':list(guid),'name':name,'flags':flags[0],
            'equipment':[v[5] for v in gear],'level':level,'slot':slot,'realm':realm})
    r.unpack('i');r.bits(1);r.bits(1);r.bits(3);r.end();return rows

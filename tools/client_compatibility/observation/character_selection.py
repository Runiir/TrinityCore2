"""Read the pinned build60895 character enumeration, including all visual slots."""
from ..world.buffer import Reader


def characters(body):
    r=Reader(body)
    if r.bits(9)!=0x122:raise ValueError('unexpected character enumeration header')
    head=r.unpack('IIiIIIII')
    if head[0]>50:raise ValueError('character enumeration exceeds its observation bound')
    if head[3]>255:raise ValueError('race-unlock enumeration exceeds its observation bound')
    if head[1]!=0 or any(head[4:]):raise ValueError('unsupported character enumeration sections')
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
    races=set()
    for _ in range(head[3]):
        race=r.unpack('i')[0];expansion=r.bits(1);achievement=r.bits(1);reserved=r.bits(3)
        if not 0<race<=255 or race in races or (expansion,achievement,reserved)!=(1,1,0):
            raise ValueError('unsupported native race-unlock entry')
        races.add(race)
    r.end();return rows

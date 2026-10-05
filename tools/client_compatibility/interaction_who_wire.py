"""Independent public Who packet decoding for the owned live oracle."""
import struct
from .world.buffer import Reader

HIGH=(2<<58)|(1<<42)


def modern_request(body):
    r=Reader(body);areas,addon=r.bits(4),r.bits(1)
    minimum,maximum,race,klass=r.unpack('iiqi')
    lengths=[r.bits(n) for n in (6,9,7,9)];count=r.bits(3)
    enemies,arena,exact,server=[r.bits(1) for _ in range(4)];r.align()
    words=[]
    for _ in range(count):words.append(r.raw(r.bits(7)).decode());r.align()
    name,realm,guild,guild_realm=[r.raw(n).decode() for n in lengths]
    info=r.unpack('iiI') if server else None
    id,origin=r.unpack('IB');zones=[r.unpack('i')[0] for _ in range(areas)];r.end()
    return dict(minimum=minimum,maximum=maximum,race=race,klass=klass,name=name,realm=realm,
        guild=guild,guild_realm=guild_realm,words=words,zones=zones,addon=addon,enemies=enemies,
        arena=arena,exact=exact,server=info,id=id,origin=origin)


def native_request(row):
    out=struct.pack('<ii',row['minimum'],row['maximum'])+row['name'].encode()+b'\0'+row['guild'].encode()+b'\0'
    out+=struct.pack('<iiI',-1,row['klass'],len(row['zones']))
    for area in row['zones']:out+=struct.pack('<i',area)
    out+=struct.pack('<I',len(row['words']))
    for word in row['words']:out+=word.encode()+b'\0'
    return out


def cstring(r):
    value=bytearray()
    while True:
        char=r.raw(1)
        if char==b'\0':return value.decode()
        value.extend(char)


def native_response(body):
    r=Reader(body);count,total=r.unpack('II');rows=[]
    if count>50:raise ValueError('native Who count exceeds50')
    for _ in range(count):
        name,guild=cstring(r),cstring(r);level,klass,race,gender,area=r.unpack('IIIBI')
        rows.append(dict(name=name,guild=guild,level=level,klass=klass,race=race,gender=gender,area=area))
    r.end();return count,total,rows


def modern_response(body):
    r=Reader(body);id,=r.unpack('I');count=r.bits(6);rows=[]
    for _ in range(count):
        deleted=r.bits(1);name_length=r.bits(6);declined=[r.bits(7) for _ in range(5)]
        declines=[r.raw(n).decode() for n in declined]
        account,bnet,guid=r.guid(),r.guid(),r.guid()
        club,realm,race,gender,klass,level,unused,season=r.unpack('QI5Bi');name=r.raw(name_length).decode()
        guild_guid=r.guid();guild_realm,area=r.unpack('Ii');gl=r.bits(7);gm=r.bits(1);guild=r.raw(gl).decode()
        rows.append(dict(deleted=deleted,declines=declines,account=account,bnet=bnet,guid=guid,
            club=club,realm=realm,race=race,gender=gender,klass=klass,level=level,unused=unused,season=season,
            name=name,guild_guid=guild_guid,guild_realm=guild_realm,area=area,gm=gm,guild=guild))
    r.end();return id,rows


def checks(rows):
    def bodies(name,direction):
        return [bytes.fromhex(r['body']) for r in rows if r['name']==name and r['direction']==direction]
    requests=bodies('CMSG_WHO','from_client');native=bodies('CMSG_WHO','to_native')
    replies=bodies('SMSG_WHO','from_native');modern=bodies('SMSG_WHO','to_client')
    counts={'one_modern_request':len(requests)==1,'one_native_request':len(native)==1,
        'one_native_reply':len(replies)==1,'one_modern_reply':len(modern)==1}
    detail={'packet_counts':{k:len(v) for k,v in zip(('modern_request','native_request','native_reply','modern_reply'),
        (requests,native,replies,modern))}}
    if not all(counts.values()):return counts,detail
    request=modern_request(requests[0]);count,total,players=native_response(replies[0]);id,public=modern_response(modern[0])
    detail.update(request=request,native_rows=players,modern_rows=public)
    counts.update(owned_name_query=request['name']=='Harnessone' and request['realm'] in ('','Client442Lab') and
        not request['guild'] and not request['guild_realm'] and not request['words'] and not request['zones'] and
        request['race'] in (-1,0) and request['klass']==-1 and request['origin']==1 and
        not request['addon'] and not request['enemies'] and not request['arena'] and
        request['minimum']<=85<=request['maximum'],exact_native_request=native==[native_request(request)],
        exact_native_owned_row=count==total==1 and len(players)==1 and players[0]['name']=='Harnessone' and
        players[0]['level']==85 and players[0]['klass']==1 and players[0]['race']==1 and
        players[0]['gender']==0 and players[0]['guild']=='',request_id_echo=id==request['id'])
    if players:
        expected=dict(deleted=0,declines=['']*5,account=(0,0),bnet=(0,0),guid=(1,HIGH),club=0,
            realm=1,race=1,gender=0,klass=1,level=85,unused=0,season=0,name='Harnessone',
            guild_guid=(0,0),guild_realm=0,area=players[0]['area'],gm=0,guild='')
        counts['exact_modern_owned_row']=public==[expected]
    else:counts['exact_modern_owned_row']=False
    return counts,detail

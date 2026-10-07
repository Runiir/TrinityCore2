"""Check captured Tame delivery against the stock client's passive stable cache."""
import struct
from .world.buffer import Reader,player_high


def require(value,message):
    if not value:raise ValueError(message)


def stable_update(body):
    """Read the pinned owner-only complete StableInfo update, without guessing masks."""
    r=Reader(bytes.fromhex(body))
    require(r.unpack('HI')==(0,1) and r.bits(1)==1 and r.bits(1)==0,'stable object header')
    length,=r.unpack('I');outer=Reader(r.raw(length));r.end()
    require(outer.unpack('B')==(0,) and outer.guid()==(6,player_high()),'stable owner')
    length,=outer.unpack('I');f=Reader(outer.raw(length));outer.end()
    require(f.unpack('BBBI')==(1,0,3,128) and f.unpack('I')==(24,) and
        f.bits(14)==0 and f.bits(32)==64 and f.bits(32)==6,'stable field masks')
    slots,=f.unpack('B');require(f.bits(1)==1,'stable optional field');f.align()
    require(f.bits(3)==7,'stable nested mask');count=f.bits(32)
    require(count<=205 and f.bits(count)==(1<<count)-1,'stable list mask');f.align();pets=[]
    for _ in range(count):
        require(f.bits(9)==511,'stable pet mask');f.align()
        values=f.unpack('5IBB');size=f.bits(8);name=f.raw(size).decode()
        pets.append((*values,name))
    master=f.guid();f.end();return pets,master,slots


def public_rows(probe):
    require(probe.get('visible') is False and probe.get('interacting') is False,
        'Tame must not open a stable interaction')
    return sorted((p.get('slot'),p.get('name'),p.get('level'),p.get('display_id'))
        for p in probe.get('pets',[]))


def prove(cast,before,after):
    number=cast['native_pet_after']['fields']['69']
    expected=[(5,4,42717,903,10,3,0,'Harnesswolf'),(0,number,299,18156,10,1,0,'Wolf')]
    require(public_rows(before)==[(6,'Harnesswolf',10,903)],'stable baseline differs')
    require(public_rows(after)==[(1,'Wolf',10,18156),(6,'Harnesswolf',10,903)] and
        after.get('stable_slots')==before.get('stable_slots')==16,'public stable outcome differs')
    added=[p for p in cast['capture_packets'] if (p['direction'],p['name'])==('from_native','SMSG_PET_ADDED')]
    require(len(added)==1 and added[0]['session']==cast['native_session'] and
        cast.get('cast_started_at',0)<=added[0]['time']<=cast['finished_at'],
        'single attributable captured native Added required')
    r=Reader(bytes.fromhex(added[0]['body']))
    require(r.unpack('iiBii')==(1,0,1,299,number) and r.bits(8)==4 and
        r.raw(4)==b'Wolf' and r.unpack('B')==(0,),'native Added differs');r.end()
    delivered=[]
    for p in cast['cast_packets']:
        if (p['direction'],p['name'])!=('to_client','SMSG_UPDATE_OBJECT'):continue
        try:decoded=stable_update(p['body'])
        except (ValueError,IndexError,UnicodeError,struct.error):continue
        if decoded==(expected,(0,0),16):delivered.append(p)
    require(len(delivered)==1 and delivered[0]['session']==cast['native_session'] and
        added[0]['time']<=delivered[0]['time']<=cast['finished_at'],
        'one attributable modern stable delivery required')
    return {'native_added':added[0],'modern_stable_update':delivered[0],
        'pets':expected,'stable_master':[0,0],'stable_slots':16}

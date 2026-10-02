"""Independent pinned-wire checks for group UI state and incremental updates."""
import struct
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


def run(codec,actions):
    return result(codec,op='stateful',character={'guid':1,'name':'Harnessone'},snapshot=None,
        gameobjects=[],units=[],actions=[{'fn':'party_state','name':name,'body':body.hex()} for name,body in actions])


def native(mask,fields=b'',full=True):
    return (b'\0' if full else b'')+b'\x01\x02'+struct.pack('<I',mask)+fields


def base():
    # Status, health, power, level, zone, signed world coordinates.
    mask=0x3ff
    fields=struct.pack('<HiiB5H3h',1,77,120,1,15,100,85,3,7,-9400,40,67)
    return native(mask,fields)


def decode(reply):
    assert reply[0]=='SMSG_PARTY_MEMBER_FULL_STATE'
    r=Reader(bytes.fromhex(reply[1]));assert r.bits(1)==0;r.align()
    values=r.unpack('2BHBHii4H2HI3hiI')
    assert r.unpack('II')==(0,0);assert r.guid()==(0,0);assert r.raw(12)==bytes(12)
    return r,values


def test_full_and_partial_preserve_other_fields(codec):
    replies=run(codec,[('SMSG_PARTY_MEMBER_FULL_STATE',base()),
        ('SMSG_PARTY_MEMBER_STATE',native(2,struct.pack('<i',61),False)),
        ('SMSG_PARTY_MEMBER_STATE',native(512,struct.pack('<3h',-9401,44,68),False))])
    for i,reply in enumerate(replies):
        r,v=decode(reply)
        assert v[:5]==(1,0,1,1,0)
        assert v[5:13]==((77 if i==0 else 61),120,15,100,85,0,3,7)
        assert v[14:17]==((-9401,44,68) if i==2 else (-9400,40,67))
        assert r.bits(1)==0;assert r.guid()==(2,(2<<58)|(1<<42));r.end()


def test_first_delta_requests_full_once_and_offline_resets(codec):
    replies=run(codec,[('SMSG_PARTY_MEMBER_STATE',native(2,struct.pack('<i',61),False)),
        ('SMSG_PARTY_MEMBER_STATE',native(2,struct.pack('<i',60),False)),
        ('SMSG_PARTY_MEMBER_FULL_STATE',base()),
        ('SMSG_PARTY_MEMBER_FULL_STATE',native(1,struct.pack('<H',0)))])
    assert replies[0]==['CMSG_REQUEST_PARTY_MEMBER_STATS',struct.pack('<Q',2).hex()]
    # An uninitialized snapshot is never published as fabricated zero health.
    assert replies[1] is None
    assert replies[2] is None
    _,online=decode(replies[3]);_,offline=decode(replies[4])
    assert online[2]==1 and online[5:7]==(77,120)
    assert offline[2]==0 and offline[5:7]==(0,0)


def test_group_aura_points_removal_and_phase_conversion(codec):
    aura=struct.pack('<BQI',1,1<<3,64)+struct.pack('<iH3i',6673,0x51,10,20,30)
    phase=struct.pack('<II2H',1,2,169,170)
    packet=native(0x200400,aura+phase)
    replies=run(codec,[('SMSG_PARTY_MEMBER_FULL_STATE',packet),
        ('SMSG_PARTY_MEMBER_STATE',native(0x400,struct.pack('<BQI',0,1<<3,64)+struct.pack('<iH',0,0),False))])
    r=Reader(bytes.fromhex(replies[0][1]));r.bits(1);r.align()
    v=r.unpack('2BHBHii4H2HI3hiI');assert v[-1]==1
    assert r.unpack('II')==(1,2);assert r.guid()==(0,0)
    assert r.unpack('IHIH')==(0,169,0,170);assert r.raw(12)==bytes(12)
    assert r.unpack('iHII')==(6673,0x10a,1,1);assert r.unpack('f')==(10.,)
    assert r.bits(1)==0;assert r.guid()==(2,(2<<58)|(1<<42));r.end()
    r=Reader(bytes.fromhex(replies[1][1]));r.bits(1);r.align()
    assert r.unpack('2BHBHii4H2HI3hiI')[-1]==0


def test_party_state_rejects_lengths_and_trailing_bytes(codec):
    for packet in [base()[:-1],base()+b'x',native(0x400,struct.pack('<BQI',1,1<<63,2)),
        native(0x200000,struct.pack('<II',0,257))]:
        assert 'error' in run(codec,[('SMSG_PARTY_MEMBER_FULL_STATE',packet)])[0]


def test_pet_health_and_name_translate_without_power_layout(codec):
    pet=struct.pack('<Q',0xf140000000000004)+b'OwnedPet\0'+struct.pack('<HiiB2H',123,20,40,2,30,100)
    replies=run(codec,[('SMSG_PARTY_MEMBER_FULL_STATE',native(0x7f800,pet))])
    r,v=decode(replies[0]);assert v[-1]==0;assert r.bits(1)==1
    assert r.guid()==(4,(10<<58)|(1<<42));assert r.unpack('iiiI')==(123,20,40,0)
    assert r.bits(8)==8;assert r.raw(8)==b'OwnedPet'
    assert r.guid()==(2,(2<<58)|(1<<42));r.end()

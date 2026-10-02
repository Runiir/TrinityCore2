"""Pinned modern/native interaction contracts, including rejection boundaries."""
import struct
from tools.client_compatibility.world.buffer import Writer,Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

HIGH=(2<<58)|(1<<42)


def call(codec,fn,name,body,**kwargs):
    return result(codec,op='stateful',character={'guid':1,'name':'Harnessone'},snapshot=None,
        gameobjects=[],units=[],actions=[{'fn':fn,'name':name,'body':body.hex()}],**kwargs)[0]


def test_social_request_name_note_and_owned_guid(codec):
    name=b'Harnesstwo';note=b'Owned fixture'
    modern=Writer().bits(len(name),9).bits(len(note),9).raw(name).raw(note).finish()
    assert call(codec,'social_request','CMSG_ADD_FRIEND',modern)==['CMSG_ADD_FRIEND',(name+b'\0'+note+b'\0').hex()]
    delete=Writer().pack('I',1).guid(2,HIGH).finish()
    assert call(codec,'social_request','CMSG_DEL_FRIEND',delete)==['CMSG_DEL_FRIEND',struct.pack('<Q',2).hex()]
    assert 'error' in call(codec,'social_request','CMSG_DEL_FRIEND',Writer().pack('I',2).guid(2,HIGH).finish())
    assert 'error' in call(codec,'social_request','CMSG_DEL_FRIEND',Writer().pack('I',1).guid(2,11<<58).finish())
    assert 'error' in call(codec,'social_request','CMSG_SEND_CONTACT_LIST',struct.pack('<I',8))
    assert 'error' in call(codec,'social_request','CMSG_ADD_FRIEND',modern+b'x')


def test_social_online_and_offline_native_contacts(codec):
    native=struct.pack('<IIQI',3,2,2,1)+b'note\0'+struct.pack('<BIII',1,12,1,1)+struct.pack('<QI',3,2)+b'\0'
    expected=Writer().pack('I',3).bits(2,8)
    expected.guid(2,HIGH).guid().pack('IIIBIII',1,1,1,1,12,1,1).bits(4,10).raw(b'note')
    expected.guid(3,HIGH).guid().pack('IIIBIII',1,1,2,0,0,0,0).bits(0,10)
    assert call(codec,'social_response','SMSG_CONTACT_LIST',native)==['SMSG_CONTACT_LIST',expected.finish().hex()]
    offline=struct.pack('<BQ',7,2)+b'hello\0'
    expected=Writer().pack('B',7).guid(2,HIGH).guid().pack('IBIII',1,0,0,0,0).bits(5,10).raw(b'hello').finish()
    assert call(codec,'social_response','SMSG_FRIEND_STATUS',offline)==['SMSG_FRIEND_STATUS',expected.hex()]
    assert 'error' in call(codec,'social_response','SMSG_CONTACT_LIST',native[:-1])


def test_reputation_sparse_indices_signed_standing_and_flags(codec):
    factions=[{'index':0,'id':72},{'index':2,'id':47}]
    native=struct.pack('<I',3)+struct.pack('<Bi',17,-9000)+struct.pack('<Bi',0,0)+struct.pack('<Bi',1,500)
    expected=struct.pack('<IIiHiiHi',2,0,72,17,-9000,47,1,500)
    assert call(codec,'reputation','SMSG_INITIALIZE_FACTIONS',native,factions=factions)==['SMSG_INITIALIZE_FACTIONS',expected.hex()]
    update=struct.pack('<fBIIi',0.,1,1,2,-300)
    expected=struct.pack('<fIiiiB',0.,1,2,-300,47,128)
    assert call(codec,'reputation','SMSG_SET_FACTION_STANDING',update,factions=factions)==['SMSG_SET_FACTION_STANDING',expected.hex()]
    unmapped=struct.pack('<I',2)+struct.pack('<Bi',1,0)*2
    assert 'error' in call(codec,'reputation','SMSG_INITIALIZE_FACTIONS',unmapped,factions=factions)
    assert 'error' in call(codec,'reputation','SMSG_SET_FACTION_STANDING',update+b'\0',factions=factions)


def test_party_invite_name_and_accept_bit_order(codec):
    name=b'Harnesstwo'
    modern=Writer().bits(0,1).flush().bits(len(name),9).bits(0,9).pack('I',0).guid().raw(name).finish()
    expected=Writer().pack('II',0,0).bits(0,1).bits(0,1).bits(0,9).bits(0,1).bits(len(name),10)
    for _ in range(5):expected.bits(0,1)
    expected.raw(name)
    assert call(codec,'party_request','CMSG_PARTY_INVITE',modern)==['CMSG_PARTY_INVITE',expected.finish().hex()]
    accept=Writer().bits(0,1).bits(1,1).bits(1,1).pack('I',4).finish()
    assert call(codec,'party_request','CMSG_PARTY_INVITE_RESPONSE',accept)==['CMSG_PARTY_INVITE_RESPONSE',Writer().bits(1,1).bits(1,1).pack('I',4).finish().hex()]
    assert 'error' in call(codec,'party_request','CMSG_PARTY_INVITE_RESPONSE',Writer().bits(0,1).bits(1,1).bits(1,1).pack('I',8).finish())


def test_party_leave_raid_ready_and_leader(codec):
    for name,native in [('CMSG_LEAVE_GROUP','CMSG_GROUP_DISBAND'),('CMSG_DO_READY_CHECK','MSG_RAID_READY_CHECK')]:
        assert call(codec,'party_request',name,b'\0')==[native,'']
        assert 'error' in call(codec,'party_request',name,Writer().bits(1,1).pack('B',1).finish())
    assert call(codec,'party_request','CMSG_CONVERT_RAID',b'\x80')==['CMSG_GROUP_RAID_CONVERT','01']
    assert call(codec,'party_request','CMSG_READY_CHECK_RESPONSE',b'\x80')==['MSG_RAID_READY_CHECK','01']
    leader=Writer().bits(0,1).guid(2,HIGH).finish()
    assert call(codec,'party_request','CMSG_SET_PARTY_LEADER',leader)==['CMSG_GROUP_SET_LEADER',struct.pack('<Q',2).hex()]


def test_party_roster_includes_self_and_native_difficulties(codec):
    native=struct.pack('<4BQII',2,0,0,4,0x1f50000000000009,3,1)+b'Harnesstwo\0'+struct.pack('<Q4B',2,1,0,0,4)
    native+=struct.pack('<QBQB2B',1,1,0,2,1,2)
    response=call(codec,'party_response','SMSG_PARTY_UPDATE',native,identities=[{'guid':1,'race':1,'class':1},{'guid':2,'race':4,'class':11}])
    assert response[0]=='SMSG_PARTY_UPDATE'
    r=Reader(bytes.fromhex(response[1]));assert r.unpack('HBBi')==(2,0,1,0)
    assert r.guid()==(9,27<<58);assert r.unpack('I')==(3,);assert r.guid()==(1,HIGH)
    assert r.unpack('BiI')==(1,0,2)
    assert [r.bits(1) for _ in range(3)]==[0,1,1]
    r.align()
    for guid,name,cls in [(1,b'Harnessone',1),(2,b'Harnesstwo',11)]:
        assert r.bits(6)==len(name);assert r.bits(6)==1
        assert [r.bits(1) for _ in range(3)]==[1,0,0]
        assert r.guid()==(guid,HIGH);assert r.unpack('5B')[3:]==(cls,1);assert r.raw(len(name))==name
    assert r.unpack('B')==(1,);assert r.guid()==(0,0);assert r.unpack('BIII')==(2,2,5,5)
    r.end()
    assert 'error' in call(codec,'party_response','SMSG_PARTY_UPDATE',native,identities=[])


def test_player_names_present_and_missing(codec):
    body=result(codec,op='player_names',requested=[[2,HIGH],[3,HIGH]],rows=[{'guid':2,'name':'Harnesstwo','race':1,'gender':0,'class':1,'level':1}])
    r=Reader(bytes.fromhex(body));assert r.unpack('I')==(2,);assert r.unpack('B')==(0,);assert r.guid()==(2,HIGH)
    assert [r.bits(1) for _ in range(2)]==[1,0];r.align();assert r.bits(1)==0;assert r.bits(6)==10
    assert [r.bits(7) for _ in range(5)]==[0]*5
    assert r.guid()==(0,0);assert r.guid()==(0,0);assert r.guid()==(2,HIGH)
    assert r.unpack('QI5Bi')==(0,1,1,0,1,1,0,0);assert r.raw(10)==b'Harnesstwo'
    assert r.unpack('B')==(1,);assert r.guid()==(3,HIGH);assert [r.bits(1) for _ in range(2)]==[0,0]

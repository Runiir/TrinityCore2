"""Classic 4.x status semantics with the pinned 4.4.2 GUID and uint64 layout."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_quest_requests import GIVER,GUID

OBJECT_GUID=(0xf11<<52)|(35<<32)|53
OBJECT={'guid':OBJECT_GUID,'kind':5,'map':0,'fields':{str(INDEX['GAMEOBJECT_BYTES_1']):2<<8}}


def call(codec,name,body,units=None,objects=None,fn='quest_response'):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        units=[GIVER] if units is None else units,gameobjects=[OBJECT] if objects is None else objects,
        actions=[{'fn':fn,'name':name,'body':body.hex()}])[0]


def test_status_requests_validate_native_visible_creature_and_object(codec):
    for guid in [GUID,OBJECT_GUID]:
        body=Writer().guid(*modern_guid(guid,0)).finish()
        assert call(codec,'CMSG_QUEST_GIVER_STATUS_QUERY',body,fn='quest_request')==[
            'CMSG_QUEST_GIVER_STATUS_QUERY',struct.pack('<Q',guid).hex()]
        assert 'error' in call(codec,'CMSG_QUEST_GIVER_STATUS_QUERY',body,[],[],fn='quest_request')
        for n in range(len(body)):
            assert 'error' in call(codec,'CMSG_QUEST_GIVER_STATUS_QUERY',body[:n],fn='quest_request')
        assert 'error' in call(codec,'CMSG_QUEST_GIVER_STATUS_QUERY',body+b'x',fn='quest_request')
    assert call(codec,'CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY',b'',fn='quest_request')==[
        'CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY','']
    assert 'error' in call(codec,'CMSG_QUEST_GIVER_STATUS_MULTIPLE_QUERY',b'x',fn='quest_request')


def test_all_native_classic_status_bits_are_preserved_as_uint64(codec):
    for guid in [GUID,OBJECT_GUID]:
        for status in [0,1,2,4,8,16,32,64,128,256,512,1024,0x600,0x7ff]:
            reply=call(codec,'SMSG_QUEST_GIVER_STATUS',struct.pack('<QI',guid,status))
            r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(guid,0)
            assert r.unpack('Q')==(status,);r.end()


def test_multiple_filters_retired_givers_and_rewrites_the_count(codec):
    body=struct.pack('<I',3)+b''.join(struct.pack('<QI',guid,status) for guid,status in
        [(GUID,4),(OBJECT_GUID,1024),(GUID+1,256)])
    reply=call(codec,'SMSG_QUEST_GIVER_STATUS_MULTIPLE',body)
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('I')==(2,)
    assert r.guid()==modern_guid(GUID,0) and r.unpack('Q')==(4,)
    assert r.guid()==modern_guid(OBJECT_GUID,0) and r.unpack('Q')==(1024,);r.end()
    for n in range(len(body)):assert 'error' in call(codec,'SMSG_QUEST_GIVER_STATUS_MULTIPLE',body[:n])
    assert 'error' in call(codec,'SMSG_QUEST_GIVER_STATUS_MULTIPLE',body+b'x')
    assert call(codec,'SMSG_QUEST_GIVER_STATUS',struct.pack('<QI',GUID+1,256)) is None


def test_status_rejects_foreign_flags_unknown_bits_duplicate_and_excessive_rows(codec):
    body=Writer().guid(*modern_guid(GUID,0)).finish()
    invalid={**GIVER,'fields':{str(INDEX['UNIT_NPC_FLAGS']):1}}
    assert 'error' in call(codec,'CMSG_QUEST_GIVER_STATUS_QUERY',body,[invalid],fn='quest_request')
    for status in [0x800,0xffffffff]:
        assert 'error' in call(codec,'SMSG_QUEST_GIVER_STATUS',struct.pack('<QI',GUID,status))
    for body in [struct.pack('<I',1001),struct.pack('<I',2)+struct.pack('<QI',GUID,4)*2]:
        assert 'error' in call(codec,'SMSG_QUEST_GIVER_STATUS_MULTIPLE',body)

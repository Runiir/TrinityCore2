"""Pinned modern questgiver reads preserve native identity and bool widths."""
import struct
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT

GIVER={**UNIT,'fields':{str(INDEX['UNIT_NPC_FLAGS']):3}}


def call(codec,name,body,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        gameobjects=[],units=[GIVER] if units is None else units,
        actions=[{'fn':'quest_request','name':name,'body':body.hex()}])[0]


def test_questgiver_hello_requires_visible_service(codec):
    body=Writer().guid(*modern_guid(GUID,0)).finish()
    assert call(codec,'CMSG_QUEST_GIVER_HELLO',body)==['CMSG_QUEST_GIVER_HELLO',struct.pack('<Q',GUID).hex()]
    for units in [[],[UNIT],[{**GIVER,'kind':4}]]:assert 'error' in call(codec,'CMSG_QUEST_GIVER_HELLO',body,units)
    for n in range(len(body)):assert 'error' in call(codec,'CMSG_QUEST_GIVER_HELLO',body[:n])
    assert 'error' in call(codec,'CMSG_QUEST_GIVER_HELLO',body+b'x')


def test_questgiver_query_translates_bit_to_native_bool(codec):
    for respond in [0,1]:
        body=Writer().guid(*modern_guid(GUID,0)).pack('i',26389).bits(respond,1).finish()
        assert call(codec,'CMSG_QUEST_GIVER_QUERY_QUEST',body)==['CMSG_QUEST_GIVER_QUERY_QUEST',struct.pack('<QIB',GUID,26389,respond).hex()]
        for n in range(len(body)):assert 'error' in call(codec,'CMSG_QUEST_GIVER_QUERY_QUEST',body[:n])
        assert 'error' in call(codec,'CMSG_QUEST_GIVER_QUERY_QUEST',body+b'x')
    for id in [0,-1]:
        body=Writer().guid(*modern_guid(GUID,0)).pack('i',id).bits(1,1).finish()
        assert 'error' in call(codec,'CMSG_QUEST_GIVER_QUERY_QUEST',body)


def test_public_quest_info_query_retains_id_and_drops_modern_only_giver(codec):
    for giver in [(0,0),modern_guid(GUID,0)]:
        body=Writer().pack('i',26389).guid(*giver).finish()
        assert call(codec,'CMSG_QUERY_QUEST_INFO',body,[])==['CMSG_QUERY_QUEST_INFO',struct.pack('<I',26389).hex()]
        for n in range(len(body)):assert 'error' in call(codec,'CMSG_QUERY_QUEST_INFO',body[:n])
        assert 'error' in call(codec,'CMSG_QUERY_QUEST_INFO',body+b'x')
    for id in [0,-1]:assert 'error' in call(codec,'CMSG_QUERY_QUEST_INFO',Writer().pack('i',id).guid(0,0).finish())

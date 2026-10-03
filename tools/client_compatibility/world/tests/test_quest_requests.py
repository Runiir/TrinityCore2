"""Pinned modern questgiver reads preserve native identity and bool widths."""
import struct
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT

GIVER={**UNIT,'fields':{str(INDEX['UNIT_NPC_FLAGS']):3}}


def call(codec,name,body,units=None,fields=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':fields or {}},
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


def test_accept_widens_modern_cheat_bit_to_native_uint32(codec):
    for cheat in [0,1]:
        body=Writer().guid(*modern_guid(GUID,0)).pack('i',26389).bits(cheat,1).finish()
        assert call(codec,'CMSG_QUEST_GIVER_ACCEPT_QUEST',body)==['CMSG_QUEST_GIVER_ACCEPT_QUEST',struct.pack('<QII',GUID,26389,cheat).hex()]
        for n in range(len(body)):assert 'error' in call(codec,'CMSG_QUEST_GIVER_ACCEPT_QUEST',body[:n])
        assert 'error' in call(codec,'CMSG_QUEST_GIVER_ACCEPT_QUEST',body+b'x')
        for units in [[],[UNIT],[{**GIVER,'kind':4}]]:
            assert 'error' in call(codec,'CMSG_QUEST_GIVER_ACCEPT_QUEST',body,units)
    for id in [0,-1]:
        body=Writer().guid(*modern_guid(GUID,0)).pack('i',id).bits(0,1).finish()
        assert 'error' in call(codec,'CMSG_QUEST_GIVER_ACCEPT_QUEST',body)


def test_captured_guard_thomas_accept_has_complete_native_reader_fields(codec):
    # UI23 trial 06 reached enabled Accept. Its 13-byte native request raised a
    # ByteBufferException: QuestPackets.h declares StartCheat as uint32, not bool.
    body=bytes.fromhex('03a3e325404104203400000000')
    guid=int.from_bytes(bytes.fromhex('e3250000050130f1'),'little')
    response=call(codec,'CMSG_QUEST_GIVER_ACCEPT_QUEST',body,[{**GIVER,'guid':guid}])
    assert response[0]=='CMSG_QUEST_GIVER_ACCEPT_QUEST'
    native=bytes.fromhex(response[1])
    assert len(native)==16
    assert struct.unpack('<QII',native)==(guid,52,0)


def test_abandon_requires_an_active_owned_native_slot_and_exact_byte(codec):
    fields={INDEX['PLAYER_QUEST_LOG_1_1']+24*5:28766}
    assert call(codec,'CMSG_QUEST_LOG_REMOVE_QUEST',b'\x18',fields=fields)==['CMSG_QUEST_LOG_REMOVE_QUEST','18']
    for body in [b'',b'\x18x',b'\x00',b'\x19',b'\xff']:
        assert 'error' in call(codec,'CMSG_QUEST_LOG_REMOVE_QUEST',body,fields=fields)

"""Native-authorized auction opening; independent pinned 4.4.2 wire oracle."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

# Runtime GUID captured from Fitch's live gossip exchange, not his DB spawn ID.
GUID=0xf130220f0000523b
UNIT={'guid':GUID,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):2097155}}
IDENTITY=Writer().guid(*modern_guid(GUID,0)).finish()


def call(codec,fn,name,body,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,gameobjects=[],
        units=[UNIT] if units is None else units,actions=[{'fn':fn,'name':name,'body':body.hex()}])[0]


@pytest.mark.parametrize('house,enabled',[(1,1),(6,1),(7,0)])
def test_opening_preserves_native_house_enablement_and_visible_guid(codec,house,enabled):
    native=struct.pack('<QIB',GUID,house,enabled)
    reply=call(codec,'auction_response','MSG_AUCTION_HELLO',native)
    assert reply[0]=='SMSG_AUCTION_HELLO_RESPONSE'
    r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(GUID,0)
    # Purchased and cancelled item mail have no delay in the native handlers.
    assert r.unpack('IIi')==(0,0,house);assert r.bits(1)==enabled;r.end()


def test_direct_open_preserves_native_guid_and_validates_service_flag(codec):
    assert call(codec,'auction_request','CMSG_AUCTION_HELLO_REQUEST',IDENTITY)==['MSG_AUCTION_HELLO',struct.pack('<Q',GUID).hex()]
    assert 'error' in call(codec,'auction_request','CMSG_AUCTION_HELLO_REQUEST',IDENTITY,[])
    for kind,flags in [(4,2097155),(3,1)]:
        unit={**UNIT,'kind':kind,'fields':{str(INDEX['UNIT_NPC_FLAGS']):flags}}
        assert 'error' in call(codec,'auction_request','CMSG_AUCTION_HELLO_REQUEST',IDENTITY,[unit])


def test_native_open_cannot_create_an_unseen_or_wrong_service_npc(codec):
    native=struct.pack('<QIB',GUID,1,1)
    assert call(codec,'auction_response','MSG_AUCTION_HELLO',native,[]) is None
    for kind,flags in [(4,2097155),(3,1)]:
        unit={**UNIT,'kind':kind,'fields':{str(INDEX['UNIT_NPC_FLAGS']):flags}}
        assert call(codec,'auction_response','MSG_AUCTION_HELLO',native,[unit]) is None


@pytest.mark.parametrize('house,enabled',[(0,1),(0x80000000,1),(1,2),(1,255)])
def test_invalid_native_opening_is_rejected(codec,house,enabled):
    assert 'error' in call(codec,'auction_response','MSG_AUCTION_HELLO',struct.pack('<QIB',GUID,house,enabled))


def test_both_opening_formats_reject_every_truncated_prefix_and_trailing_data(codec):
    for fn,name,body in [('auction_request','CMSG_AUCTION_HELLO_REQUEST',IDENTITY),
                         ('auction_response','MSG_AUCTION_HELLO',struct.pack('<QIB',GUID,1,1))]:
        for size in range(len(body)):
            assert 'error' in call(codec,fn,name,body[:size])
        assert 'error' in call(codec,fn,name,body+b'x')


def test_unrelated_packets_are_untouched(codec):
    assert call(codec,'auction_request','CMSG_SEND_MAIL',b'') is None
    assert call(codec,'auction_response','SMSG_SEND_MAIL_RESULT',b'') is None


def test_live_fitch_opening_matches_captured_modern_packet(codec):
    native=bytes.fromhex('3a7600000f2230f10200000001')
    guid=struct.unpack_from('<Q',native)[0]
    unit={**UNIT,'guid':guid}
    assert call(codec,'auction_response','MSG_AUCTION_HELLO',native,[unit])==[
        'SMSG_AUCTION_HELLO_RESPONSE','03a73a76c08308042000000000000000000200000080']

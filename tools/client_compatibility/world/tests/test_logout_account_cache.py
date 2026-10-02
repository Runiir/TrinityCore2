"""Final settings after native logout retain owned identity without active gameplay."""
import pytest
from tools.client_compatibility.world.buffer import Reader, Writer, player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, action, result


def update(guid=2, size=0):
    return Writer().pack('qI',123,size).guid(guid,player_high()).pack('iI',3,0).finish()


def test_final_character_cache_write_after_logout_translates_for_last_owned_guid(codec):
    encoded=result(codec,op='stateful',character=None,last_logout_guid=2,
                   actions=[action('account_request','CMSG_UPDATE_ACCOUNT_DATA',update())])[0]
    assert encoded[0]=='CMSG_UPDATE_ACCOUNT_DATA'
    r=Reader(bytes.fromhex(encoded[1]));assert r.unpack('III')==(3,123,0);r.end()
    assert 'error' in codec(op='stateful',character=None,last_logout_guid=2,
        actions=[action('account_request','CMSG_UPDATE_ACCOUNT_DATA',update(3))])


@pytest.mark.parametrize('character,last_guid',[ (None,0), ({'guid':1},2) ])
def test_cache_write_does_not_authorize_unknown_or_previous_character_during_new_login(codec,character,last_guid):
    assert 'error' in codec(op='stateful',character=character,last_logout_guid=last_guid,
        actions=[action('account_request','CMSG_UPDATE_ACCOUNT_DATA',update())])


def test_final_cache_read_response_after_logout_keeps_owned_guid(codec):
    native=Writer().pack('QIII',2,3,123,0).finish()
    encoded=result(codec,op='stateful',character=None,last_logout_guid=2,
        actions=[action('account_response','SMSG_UPDATE_ACCOUNT_DATA',native)])[0]
    r=Reader(bytes.fromhex(encoded[1]));assert r.unpack('qI')==(123,0)
    assert r.guid()==(2,player_high()) and r.unpack('iI')==(3,0);r.end()

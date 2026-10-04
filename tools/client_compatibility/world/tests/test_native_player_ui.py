"""The live one-byte action-bar request maps to native bytes with world guards."""
import pytest
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result


@pytest.mark.parametrize('body',['00','01','0f','ff'])
def test_actionbar_toggle_retains_byte_and_native_opcode(codec,body):
    assert result(codec,op='actionbar_toggle_request',body=body,in_world=True)==['CMSG_SET_ACTIONBAR_TOGGLES',body]


@pytest.mark.parametrize('body',['','0001','01000000'])
def test_actionbar_toggle_rejects_truncated_or_trailing_data(codec,body):
    assert 'error' in codec(op='actionbar_toggle_request',body=body,in_world=True)


def test_actionbar_toggle_ignores_only_harmless_preworld_zero(codec):
    assert result(codec,op='actionbar_toggle_request',body='00',in_world=False) is None
    assert 'error' in codec(op='actionbar_toggle_request',body='01',in_world=False)


@pytest.mark.parametrize('state',[0,1,3,8])
def test_stand_request_expands_public_byte_to_native_uint32(codec,state):
    body=bytes([state]).hex()
    assert result(codec,op='stand_state_request',body=body,in_world=True)==[
        'CMSG_STANDSTATECHANGE',state.to_bytes(4,'little').hex()]


@pytest.mark.parametrize('body',['','0001','01000000','02','04','07','ff'])
def test_stand_request_rejects_malformed_or_disallowed_player_states(codec,body):
    assert 'error' in codec(op='stand_state_request',body=body,in_world=True)


def test_stand_request_never_operates_before_world_entry(codec):
    assert 'error' in codec(op='stand_state_request',body='00',in_world=False)


@pytest.mark.parametrize('state',[0,1,2,9])
def test_stand_update_preserves_native_state_and_adds_neutral_animation_kit(codec,state):
    body=bytes([state]).hex()
    assert result(codec,op='stand_state_update',body=body)==['SMSG_STAND_STATE_UPDATE',body+'00000000']


@pytest.mark.parametrize('body',['','0100','ff'])
def test_stand_update_rejects_invalid_native_records(codec,body):
    assert 'error' in codec(op='stand_state_update',body=body)


@pytest.mark.parametrize('state',[0,1,2])
@pytest.mark.parametrize('animate',[0,128])
def test_sheath_request_preserves_native_state_without_modern_animation_bit(codec,state,animate):
    body=(state.to_bytes(4,'little')+bytes([animate])).hex()
    assert result(codec,op='sheath_request',body=body,in_world=True)==[
        'CMSG_SET_SHEATHED',state.to_bytes(4,'little').hex()]


@pytest.mark.parametrize('body',['','00','00000000','000000000000','0300000000',
    'ffffffff80','0100000001','0100000081'])
def test_sheath_request_rejects_bad_size_state_or_nonzero_padding(codec,body):
    assert 'error' in codec(op='sheath_request',body=body,in_world=True)


def test_sheath_request_requires_an_owned_world(codec):
    assert 'error' in codec(op='sheath_request',body='0000000000',in_world=False)

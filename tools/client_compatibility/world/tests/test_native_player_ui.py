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

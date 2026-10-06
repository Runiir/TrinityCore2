"""Native range/facing feedback must reach the pinned modern3-bit error packet."""
import pytest
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

ERRORS={'SMSG_ATTACKSWING_NOTINRANGE':0,'SMSG_ATTACKSWING_BADFACING':1,
    'SMSG_ATTACKSWING_CANT_ATTACK':2,'SMSG_ATTACKSWING_DEADTARGET':3}


def feedback(codec,name,body=''):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1},
        units=[],gameobjects=[],actions=[{'fn':'combat_response','name':name,'body':body}])[0]


@pytest.mark.parametrize('name,reason',ERRORS.items())
def test_native_empty_error_maps_to_exact_modern_reason(codec,name,reason):
    packet=feedback(codec,name)
    assert packet is not None and packet[0]=='SMSG_ATTACK_SWING_ERROR'
    reader=Reader(bytes.fromhex(packet[1]));assert reader.bits(3)==reason;reader.end()


@pytest.mark.parametrize('name',ERRORS)
def test_error_with_unexpected_body_is_rejected(codec,name):
    packet=feedback(codec,name,'00')
    assert isinstance(packet,dict) and packet.get('error')

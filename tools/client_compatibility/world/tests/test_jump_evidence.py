"""Captured 60895 ascent uses a negative vertical-speed field."""
from copy import deepcopy
from tools.client_compatibility.interaction_ground_jump import airborne
from tools.client_compatibility.world.movement import parse

BODY='01a0010408000800000002000000000000801e54115c640bc61f45eec2d763a44200000000000000000000000000000000000000002000000000d893fec0800000803f0000000000000000'


def evidence():
    jump=parse(bytes.fromhex(BODY),1)
    peer=deepcopy(jump);peer['position']=list(peer['position'])
    peer['position'][2]=83.76138305664062;peer['fall_time']=500
    return [{'movement':jump}],[{'movement':peer}]


def test_captured_negative_speed_with_peer_ascent_passes():
    jumps,peer=evidence()
    assert jumps[0]['movement']['zspeed']<0
    assert airborne(jumps,peer,82.195)


def test_jump_request_without_observed_peer_height_gain_fails():
    jumps,_=evidence()
    assert not airborne(jumps,jumps,82.195)
    assert not airborne(jumps,[],82.195)


def test_nonphysical_vertical_speed_fails_even_with_peer_height():
    jumps,peer=evidence()
    for value in [0,float('nan'),float('inf')]:
        jumps[0]['movement']['zspeed']=value
        assert not airborne(jumps,peer,82.195)

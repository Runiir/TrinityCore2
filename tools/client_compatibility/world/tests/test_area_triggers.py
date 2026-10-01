import pytest
from tools.client_compatibility.world import area_triggers, gameobjects
from tools.client_compatibility.world.buffer import Writer
from types import SimpleNamespace


def test_enter_only_and_strict_packet_length():
    assert area_triggers.request(Writer().pack('I',4354).bits(3,2).finish()) == ('CMSG_AREATRIGGER', b'\x02\x11\0\0')
    for bits in [0,1,2]:
        assert area_triggers.request(Writer().pack('I',4354).bits(bits,2).finish()) is None
    with pytest.raises(ValueError): area_triggers.request(b'\x02\x11\0\0\xc0extra')


def test_destroy_flightmaster_invalidates_owned_menu():
    guid=(0xF13<<52)|(2409<<32)|123
    owner=SimpleNamespace(visible_units={guid:{'map':0}},taxi_menu={'vendor':guid},gossip_menu={'guid':guid})
    assert gameobjects.destroy(owner,Writer().pack('QB',guid,0).finish())
    assert not owner.visible_units and owner.taxi_menu is None and owner.gossip_menu is None

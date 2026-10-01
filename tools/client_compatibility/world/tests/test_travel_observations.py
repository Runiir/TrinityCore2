"""Captured 60895 addon telemetry and archaeology map refresh regressions."""
import pytest
from tools.client_compatibility.observation import travel
from tools.client_compatibility.world import research_updates,gameobjects
from tools.client_compatibility.world.buffer import Reader,player_high


def test_captured_60895_travel_observation():
    data=bytes.fromhex('54434132000010ae008aef9600000000ffefeb98ffff5e4800000000c010009000a300ab00bf00c100cb00eb013901570165016d018301a901ab01ad01b700000005af000000bb3f')
    observation=travel.decode_packet(data)
    assert observation['world_position'][:2]==[-10538,-414]
    assert observation['world_map']==0 and observation['flyable_area']
    assert observation['digsite_ids']==[144,163,171,191,193,203,235,313,343,357,365,387,425,427,429,439]
    assert observation['camera_zoom']==14.55
    assert not observation['casting'] and not observation['mounted']
    damaged=bytearray(data);damaged[20]^=1
    with pytest.raises(ValueError):travel.decode_packet(bytes(damaged))


def test_replacing_digsites_sends_complete_dynamic_mask_without_relogin():
    r=Reader(research_updates.block(1,[163,171,193],[203]))
    assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    length,=r.unpack('I');fields=Reader(r.raw(length));r.end()
    assert fields.unpack('BBBI')==(1,0,3,128)
    assert fields.unpack('I')==(1,) and fields.bits(14)==0
    assert fields.bits(32)==(1<<23)|(1<<24)|(1<<27)|(1<<28)
    assert fields.bits(32)==3 and fields.bits(3)==7
    assert fields.bits(32)==1 and fields.bits(1)==1
    assert fields.unpack('3H')==(163,171,193)
    assert fields.unpack('h')==(203,);fields.end()


def test_creature_guid_keeps_entry_map_and_counter_separate():
    native=(0xF13<<52)|(2409<<32)|123
    assert gameobjects.modern_guid(native,0)==(123,(8<<58)|(1<<42)|(2409<<6))
    assert gameobjects.modern_guid(native,530)[1]!=(8<<58)|(1<<42)|(2409<<6)

from types import SimpleNamespace
import struct
import pytest
from tools.client_compatibility.world import combat, casting, player_updates
from tools.client_compatibility.world.buffer import Reader, Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX

GUID = (0xF13<<52)|(17401<<32)|123


def test_duplicate_drake_names_and_failed_exact_selection_use_enemy_cycling():
    from tools.client_compatibility.combat_clear import named_target_command
    facts={'visible_unit_names':{11:'Enslaved Netherwing Drake',12:'Enslaved Netherwing Drake'}}
    assert named_target_command(facts,'Enslaved Netherwing Drake',1) is None
    facts['visible_unit_names'].pop(12)
    assert named_target_command(facts,'Enslaved Netherwing Drake',1)=='/targetexact Enslaved Netherwing Drake'
    assert named_target_command(facts,'Enslaved Netherwing Drake',3) is None


def test_indoor_enemy_cycling_can_try_ambiguous_name_twice_without_an_unbounded_loop():
    from tools.client_compatibility.combat_clear import named_target_command
    facts={'visible_unit_names':{11:'Dragonmaw Shaman',12:'Dragonmaw Shaman'}}
    assert named_target_command(facts,'Dragonmaw Shaman',1) is None
    assert named_target_command(facts,'Dragonmaw Shaman',2,allow_ambiguous=True)=='/targetexact Dragonmaw Shaman'
    assert named_target_command(facts,'Dragonmaw Shaman',3,allow_ambiguous=True) is None


def owner():
    return SimpleNamespace(character={'map':530,'guid':1,'name':'Harnessone','gender':0},
        visible_units={GUID:{'map':530}})


def test_client_selection_and_attack_use_native_full_guid_and_visible_ownership():
    o=owner();body=Writer().guid(*modern_guid(GUID,530)).finish()
    assert combat.request(o,'CMSG_SET_SELECTION',body)==('CMSG_SET_SELECTION',struct.pack('<Q',GUID))
    assert combat.request(o,'CMSG_ATTACK_SWING',body)==('CMSG_ATTACK_SWING',struct.pack('<Q',GUID))
    assert combat.request(o,'CMSG_SET_SELECTION',Writer().guid().finish())[1]==bytes(8)
    assert combat.request(o,'CMSG_ATTACK_STOP',b'')==('CMSG_ATTACK_STOP',b'')
    assert combat.request(o,'CMSG_ATTACK_SWING',Writer().guid(*modern_guid(GUID+1,530)).finish()) is None
    with pytest.raises(ValueError):combat.request(o,'CMSG_ATTACK_SWING',body+b'\0')


def test_native_attack_start_stop_preserve_identities_and_death_bit():
    o=owner();name,body=combat.response(o,'SMSG_ATTACK_START',struct.pack('<QQ',1,GUID));r=Reader(body)
    assert name=='SMSG_ATTACK_START' and r.guid()==modern_guid(1,530) and r.guid()==modern_guid(GUID,530);r.end()
    native=casting.packed(casting.packed(Writer(),1),GUID).pack('I',1).finish()
    name,body=combat.response(o,'SMSG_ATTACK_STOP',native);r=Reader(body)
    assert name=='SMSG_ATTACK_STOP' and r.guid()==modern_guid(1,530) and r.guid()==modern_guid(GUID,530)
    assert r.bits(1)==1;r.end()


def test_creature_health_update_preserves_native_zero_and_nonowner_visibility():
    snapshot={'guid':GUID,'map':530,'fields':{INDEX['UNIT_FIELD_HEALTH']:0}}
    r=Reader(player_updates.scalar_block(snapshot,owner().character,{INDEX['UNIT_FIELD_HEALTH']:0}))
    assert r.unpack('B')==(0,) and r.guid()==modern_guid(GUID,530)
    length,=r.unpack('I');fields=Reader(r.raw(length));r.end()
    assert fields.unpack('BBBI')==(0,0,3,1<<5)
    assert fields.bits(8)==1 and fields.bits(32)==(1<<5)|1
    assert fields.unpack('q')==(0,);fields.end()

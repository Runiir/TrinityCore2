"""Independent pinned 4.4.2 ranged and crit fields, including sparse resets.

WPP28fc3d1 UpdateFieldsHandler442: Unit ranged scalar46 plus its valid third
attack-array entry175; Active crit50/51/52/54 under32, schools under281.
"""
import struct
import pytest
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import read_block,mask

SCALARS=[('PLAYER_CRIT_PERCENTAGE','CritPercentage',50,12.75),
    ('PLAYER_RANGED_CRIT_PERCENTAGE','RangedCritPercentage',51,8.25),
    ('PLAYER_OFFHAND_CRIT_PERCENTAGE','OffhandCritPercentage',52,0.0),
    ('PLAYER_SHIELD_BLOCK_CRIT_PERCENTAGE','ShieldBlockCritPercentage',54,7.0)]


def bits(x):return struct.unpack('<I',struct.pack('<f',x))[0]


def values():
    out={INDEX[n]:bits(v) for n,_,_,v in SCALARS}
    out.update({INDEX['PLAYER_SPELL_CRIT_PERCENTAGE1']+i:bits(i*1.5) for i in range(7)})
    return out


@pytest.mark.parametrize('native,modern,index,value',SCALARS)
def test_native_crit_creation_preserves_each_percentage(codec,native,modern,index,value):
    active=result(codec,op='object_values',snapshot={'guid':1,'fields':values()},character={})['ActivePlayerData']
    assert active.get(modern)==value


def test_native_spell_crit_creation_preserves_all_schools(codec):
    active=result(codec,op='object_values',snapshot={'guid':1,'fields':values()},character={})['ActivePlayerData']
    assert active.get('SpellCritPercentage')==[i*1.5 for i in range(7)]


def test_ranged_creation_keeps_the_three_array_times_and_separate_scalar(codec):
    fields={INDEX['UNIT_FIELD_BASEATTACKTIME']:3487,INDEX['UNIT_FIELD_BASEATTACKTIME']+1:1937,
        INDEX['UNIT_FIELD_RANGEDATTACKTIME']:2034}
    unit=result(codec,op='object_values',snapshot={'guid':1,'fields':fields},character={})['UnitData']
    assert unit['AttackRoundBaseTime']==[3487,1937,2034]
    assert unit.get('RangedAttackRoundBaseTime')==2034


@pytest.mark.parametrize('visibility',[0,1])
def test_ranged_sparse_change_updates_both_public_time_fields(codec,visibility):
    fields={INDEX['UNIT_FIELD_RANGEDATTACKTIME']:2034}
    body=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},character={},changed=fields,visibility=visibility)
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,) and r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos and r.unpack('BBBI')==(visibility,0,3,1<<5)
    assert mask(r,8)=={32,46,172,175};r.align();assert r.unpack('II')==(2034,2034);r.end()


def test_crit_sparse_values_include_zero_reset_and_school_parent(codec):
    fields=values();body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=1)
    assert body,'native crit change was silently dropped'
    r=read_block(body,(1,player_high()),1<<7)
    assert mask(r,46,True)=={32,50,51,52,54,281,*range(282,289)};r.align()
    assert r.unpack('4f')==tuple(v for _,_,_,v in SCALARS)
    assert r.unpack('7f')==tuple(i*1.5 for i in range(7));r.end()


def test_combined_ranged_and_mount_scalars_keep_wire_order(codec):
    fields={INDEX['UNIT_FIELD_RANGEDATTACKTIME']:2034,INDEX['UNIT_FIELD_MOUNTDISPLAYID']:16085}
    body=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},character={},changed=fields,visibility=1)
    r=read_block(body,(1,player_high()),1<<5)
    assert mask(r,8)=={32,46,52,172,175};r.align()
    assert r.unpack('IiI')==(2034,16085,2034);r.end()


def test_schools_interleave_crit_and_damage_with_the_actual_parent_gate(codec):
    fields={INDEX['PLAYER_SPELL_CRIT_PERCENTAGE1']:bits(5.5),
        INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_PCT']:bits(1.25),
        INDEX['PLAYER_SPELL_CRIT_PERCENTAGE1']+2:bits(0.0),
        INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_POS']+2:20,INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_NEG']+2:(-2)&0xffffffff}
    r=read_block(result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=1),(1,player_high()),1<<7)
    assert mask(r,46,True)=={281,282,284,303,291,298};r.align()
    assert r.unpack('3f')==(5.5,1.25,0.0);assert r.unpack('2i')==(20,-2);r.end()


def test_crit_does_not_leak_to_peer_or_unchanged_updates(codec):
    for visibility,changed in [(0,values()),(1,{})]:
        assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':values()},changed=changed,visibility=visibility)==''

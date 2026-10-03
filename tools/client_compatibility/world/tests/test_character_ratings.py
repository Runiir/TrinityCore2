"""Pinned WPP: active scalars under38, ratings345/346+i, unit haste64/68..70."""
import struct
import pytest
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import read_block,mask

SCALARS=[('PLAYER_EXPERTISE','MainhandExpertise',41,27,False),
    ('PLAYER_OFFHAND_EXPERTISE','OffhandExpertise',42,24,False),
    ('PLAYER_BLOCK_PERCENTAGE','BlockPercentage',45,5.0,True),
    ('PLAYER_DODGE_PERCENTAGE','DodgePercentage',46,5.0,True),
    ('PLAYER_PARRY_PERCENTAGE','ParryPercentage',48,13.75,True),
    ('PLAYER_SHIELD_BLOCK','ShieldBlock',53,30,False),
    ('PLAYER_MASTERY','Mastery',55,19.5,True)]
HASTE=[('PLAYER_FIELD_MOD_HASTE','ModHaste',68),
    ('PLAYER_FIELD_MOD_RANGED_HASTE','ModRangedHaste',69),
    ('PLAYER_FIELD_MOD_HASTE_REGEN','ModHasteRegen',70)]
# Native0/1/11/12/13/16/20/21/22/24 are obsolete or repurposed.
SUPPORTED={*range(2,11),14,15,17,18,19,23,25}


def bits(n):return struct.unpack('<I',struct.pack('<f',n))[0]


@pytest.mark.parametrize('native,modern,index,value,floating',SCALARS)
def test_stat_creation_respects_native_integer_and_float_types(codec,native,modern,index,value,floating):
    fields={INDEX[native]:bits(value) if floating else value}
    active=result(codec,op='object_values',snapshot={'guid':1,'fields':fields},character={})['ActivePlayerData']
    assert active.get(modern)==value


@pytest.mark.parametrize('native,modern,index',HASTE)
def test_haste_creation_preserves_the_native_multiplier(codec,native,modern,index):
    unit=result(codec,op='object_values',snapshot={'guid':1,'fields':{INDEX[native]:bits(.875)}},character={})['UnitData']
    assert unit.get(modern)==.875


def test_absent_private_haste_fields_have_neutral_peer_defaults(codec):
    unit=result(codec,op='object_values',snapshot={'guid':1,'fields':{}},character={})['UnitData']
    assert [unit.get(modern) for _,modern,_ in HASTE]==[1.0]*3


def test_ratings_creation_does_not_relabel_obsolete_indices(codec):
    fields={INDEX['PLAYER_FIELD_COMBAT_RATING_1']+i:100+i for i in range(26)}
    active=result(codec,op='object_values',snapshot={'guid':1,'fields':fields},character={})['ActivePlayerData']
    assert active.get('CombatRatings')==[100+i if i in SUPPORTED else 0 for i in range(32)]


def test_sparse_haste_preserves_zero_and_the_actual_unit_parent(codec):
    fields={INDEX[n]:bits(v) for (n,_,_),v in zip(HASTE,[.875,1.25,0.0])}
    body=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},character={},changed=fields,visibility=1)
    assert body,'haste updates were dropped'
    r=read_block(body,(1,player_high()),1<<5)
    assert mask(r,8)=={64,68,69,70};r.align();assert r.unpack('3f')==(.875,1.25,0.0);r.end()
    assert result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},character={},changed=fields,visibility=0)==''


def test_combined_crit_defense_inventory_and_ratings_keep_parser_order(codec):
    fields={INDEX[n]:bits(v) if floating else v for n,_,_,v,floating in SCALARS}
    fields[INDEX['PLAYER_CRIT_PERCENTAGE']]=bits(12.75)
    fields.update({INDEX['PLAYER_FIELD_COMBAT_RATING_1']+i:v for i,v in [(3,1706),(17,412),(25,2070)]})
    fields[INDEX['PLAYER_FIELD_INV_SLOT_HEAD']]=12
    fields[INDEX['PLAYER_FIELD_INV_SLOT_HEAD']+1]=0x40000000
    body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=1)
    r=read_block(body,(1,player_high()),1<<7)
    assert mask(r,46,True)=={38,41,42,45,46,48,50,53,55,131,132,345,349,363,371};r.align()
    assert r.unpack('6f')==(27.0,24.0,5.0,5.0,13.75,12.75)
    assert r.unpack('if')==(30,19.5)
    assert r.guid()==(12,(3<<58)|(1<<42))
    assert r.unpack('3i')==(1706,412,2070);r.end()


def test_ratings_resets_and_signed_words_are_retained(codec):
    fields={INDEX['PLAYER_MASTERY']:bits(0),INDEX['PLAYER_EXPERTISE']:0,
        INDEX['PLAYER_FIELD_COMBAT_RATING_1']+25:0,INDEX['PLAYER_FIELD_COMBAT_RATING_1']+3:(-7)&0xffffffff}
    r=read_block(result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=1),(1,player_high()),1<<7)
    assert mask(r,46,True)=={38,41,55,345,349,371};r.align()
    assert r.unpack('2f2i')==(0.0,0.0,-7,0);r.end()


def test_ratings_private_unchanged_and_obsolete_changes_emit_nothing(codec):
    for visibility,changed in [(0,{INDEX['PLAYER_MASTERY']:bits(8)}),(1,{}),
        (1,{INDEX['PLAYER_FIELD_COMBAT_RATING_1']+11:123})]:
        assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':changed},changed=changed,visibility=visibility)==''

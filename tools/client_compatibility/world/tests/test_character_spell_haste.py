"""Pinned WPP442 UnitData gate64: public cast speed66 and spell haste67."""
import struct
import pytest
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import Reader,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]


def read_block(value,visibility):
    r=Reader(bytes.fromhex(value));assert r.unpack('B')==(0,);assert r.guid()==(1,player_high())
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(visibility,0,3,1<<5)
    return r


@pytest.mark.parametrize('name,modern',[('UNIT_MOD_CAST_SPEED','ModCastingSpeed'),
    ('UNIT_MOD_CAST_HASTE','ModSpellHaste')])
def test_cast_multiplier_creation_retains_native_float(codec,name,modern):
    fields={INDEX[name]:bits(.875)}
    assert result(codec,op='object_values',snapshot={'guid':1,'fields':fields},character={})['UnitData'][modern]==.875


@pytest.mark.parametrize('visibility',[0,1])
@pytest.mark.parametrize('values',[(.875,1.25),(1.0,0.0)])
def test_public_cast_multipliers_update_and_reset_under_the_actual_gate(codec,visibility,values):
    fields={INDEX[name]:bits(value) for name,value in zip(['UNIT_MOD_CAST_SPEED','UNIT_MOD_CAST_HASTE'],values)}
    body=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},
        character={},changed=fields,visibility=visibility)
    assert body,'public cast multipliers were dropped'
    r=read_block(body,visibility)
    assert mask(r,8)=={64,66,67};r.align();assert r.unpack('2f')==values;r.end()


@pytest.mark.parametrize('visibility',[0,1])
def test_cast_and_private_haste_payloads_keep_parser_order(codec,visibility):
    fields={INDEX['UNIT_FIELD_HEALTH']:123,INDEX['UNIT_FIELD_BYTES_1']:3<<24,
        INDEX['UNIT_MOD_CAST_SPEED']:bits(.875),INDEX['UNIT_MOD_CAST_HASTE']:bits(.75),
        INDEX['PLAYER_FIELD_MOD_HASTE']:bits(.5),INDEX['PLAYER_FIELD_MOD_RANGED_HASTE']:bits(.625),
        INDEX['PLAYER_FIELD_MOD_HASTE_REGEN']:bits(1.0),INDEX['UNIT_FIELD_BYTES_2']:1}
    body=result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},
        character={},changed=fields,visibility=visibility)
    r=read_block(body,visibility)
    expected={0,5,32,57,59,60,64,66,67,78,79,81}
    if visibility:expected|={68,69,70}
    assert mask(r,8)==expected;r.align();assert r.unpack('q3B')==(123,0,0,3)
    assert r.unpack('2f')==(.875,.75)
    if visibility:assert r.unpack('3f')==(.5,.625,1.0)
    assert r.unpack('3B')==(1,0,0);r.end()


def test_unrelated_cast_snapshot_does_not_emit_a_change(codec):
    fields={INDEX['UNIT_MOD_CAST_SPEED']:bits(.875),INDEX['UNIT_MOD_CAST_HASTE']:bits(.75)}
    assert result(codec,op='unit_update',snapshot={'guid':1,'map':0,'fields':fields},
        character={},changed={},visibility=1)==''

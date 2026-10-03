"""Pinned school-damage fields must retain native modifiers in create and updates."""
import struct
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import read_block,mask


def bits(value):return struct.unpack('<I',struct.pack('<f',value))[0]


def values():
    fields={}
    for i in range(7):
        fields[INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_POS']+i]=i*10
        fields[INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_NEG']+i]=(-i)&0xffffffff
        fields[INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_PCT']+i]=bits(1.2936 if i==0 else 1.155)
    return fields


def test_create_preserves_signed_native_buffs_and_nonzero_damage_percent(codec):
    fields=values();active=result(codec,op='object_values',snapshot={'guid':1,'fields':fields},character={})['ActivePlayerData']
    assert active['ModDamageDonePos']==[i*10 for i in range(7)]
    assert active['ModDamageDoneNeg']==[-i for i in range(7)]
    assert active['ModDamageDonePercent']==[struct.unpack('<f',struct.pack('<I',fields[INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_PCT']+i]))[0] for i in range(7)]


def test_sparse_native_school_modifiers_interleave_by_school(codec):
    fields=values();changed={INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_PCT']:fields[INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_PCT']],
        INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_POS']+2:20,INDEX['PLAYER_FIELD_MOD_DAMAGE_DONE_NEG']+2:(-2)&0xffffffff}
    body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=changed,visibility=1)
    r=read_block(body,(1,player_high()),1<<7)
    assert mask(r,46,True)=={288,303,291,298};r.align()
    assert abs(r.unpack('f')[0]-1.2936)<1e-6
    assert r.unpack('2i')==(20,-2);r.end()


def test_damage_modifiers_do_not_leak_to_public_player_updates(codec):
    fields=values()
    assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed=fields,visibility=0)==''


def test_unchanged_damage_fields_do_not_create_a_sparse_reply(codec):
    assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':values()},changed={},visibility=1)==''

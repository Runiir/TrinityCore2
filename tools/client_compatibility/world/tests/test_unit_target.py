"""Pinned 4.4.2 UnitData.Target GUID creation and public sparse updates."""
import pytest
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import read_block,mask

TARGET=INDEX['UNIT_FIELD_TARGET']
CREATURE=(0xf13<<52)|(1234<<32)|28


def snapshot(target):
    return {'guid':2,'kind':4,'map':0,
        'fields':{TARGET:target&0xffffffff,TARGET+1:target>>32}}


def identity(target):
    if not target:return [0,0]
    if target==CREATURE:return [28,(8<<58)|(1<<42)|(1234<<6)]
    return [target,player_high()]


@pytest.mark.parametrize('target',[0,1,CREATURE])
def test_create_target_retains_zero_player_and_creature_identity(codec,target):
    unit=result(codec,op='object_values',snapshot=snapshot(target),character={})['UnitData']
    assert unit.get('Target')==identity(target)


@pytest.mark.parametrize('visibility',[0,1])
@pytest.mark.parametrize('target,word',[(1,0),(0,0),(CREATURE,1)])
def test_target_guid_is_public_and_either_native_word_triggers_update(codec,visibility,target,word):
    s=snapshot(target)
    body=result(codec,op='unit_update',snapshot=s,character={},
        changed={TARGET+word:s['fields'][TARGET+word]},visibility=visibility)
    assert body,'native target GUID update was dropped'
    r=read_block(body,(2,player_high()),1<<5)
    assert mask(r,8)=={0,21};r.align()
    assert list(r.guid())==identity(target);r.end()


def test_target_guid_keeps_pinned_order_between_display_and_flags(codec):
    s=snapshot(1)
    s['fields'].update({INDEX['UNIT_FIELD_DISPLAYID']:49,INDEX['UNIT_FIELD_FLAGS']:8,
        INDEX['UNIT_FIELD_HEALTH']:100})
    body=result(codec,op='unit_update',snapshot=s,character={},changed=s['fields'],visibility=0)
    r=read_block(body,(2,player_high()),1<<5)
    assert mask(r,8)=={0,5,7,21,32,41};r.align()
    assert r.unpack('qi')==(100,49)
    assert list(r.guid())==identity(1)
    assert r.unpack('I')==(8,);r.end()


def test_unchanged_target_does_not_emit_an_update(codec):
    assert result(codec,op='unit_update',snapshot=snapshot(1),character={},changed={},visibility=0)==''

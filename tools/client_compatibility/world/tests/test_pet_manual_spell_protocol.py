"""The actual idle Blood Pact shape cannot authorize another spell, target or pet."""
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action,snapshot,unit

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_manual_spell_ui131.json').read_text())
PET=FIXTURE['native_pet_guid'];IDENTITY=FIXTURE['request']['decoded']['guid']
CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])


def request(word=0xc08018a3,identity=IDENTITY,target=(0,0),position=(0.,0.,0.)):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def translate(body):return action('translate_pet_action','',body)


def controlled(codec,actions,units=None,player=None,catalog=CATALOG):
    return result(codec,op='stateful',character=FIXTURE['character'],snapshot=player or snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)] if units is None else units,gameobjects=[],
        actions=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])+actions)


def expected():
    return {'packet':['CMSG_PET_ACTION',struct.pack('<QIQfff',PET,0xc10018a3,0,0.,0.,0.).hex()],'rejection':''}


def test_actual_capture_preserves_current_pet_and_enabled_native_blood_pact(codec):
    body=bytes.fromhex(FIXTURE['request']['packet']['body']);assert body==request() and len(body)==24
    rows=controlled(codec,[translate(body)]);assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[1]==expected()


@pytest.mark.parametrize('body',[request(word=0xc0800c26),request(word=0x808018a3),
    request(word=0x008018a3),request(word=0xff8018a3),request(word=0xc0800000),
    request(identity=(0,0)),request(identity=(IDENTITY[0]+1,IDENTITY[1])),
    request(target=(5,player_high())),request(target=IDENTITY),
    request(position=(1.,0.,0.)),request(position=(0.,1.,0.)),request(position=(0.,0.,1.)),
    request(position=(float('nan'),0.,0.)),request()[:-1],request()+b'x',request()+request(),b''])
def test_uncaptured_spell_flag_target_position_or_body_is_healthy_rejection(codec,body):
    rows=controlled(codec,[translate(body),translate(request())])
    assert rows[1]['packet'] is None and rows[1]['rejection'];assert rows[2]==expected()


@pytest.mark.parametrize('fault',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind'])
def test_manual_spell_cannot_borrow_another_native_pet_or_owner_authority(codec,fault):
    pet=unit(owner=6 if fault=='foreign_owner' else 5,guid=PET,number=0 if fault=='unnumbered' else 2)
    if fault=='wrong_kind':pet['kind']=4
    rows=controlled(codec,[translate(request())],units=[] if fault=='unseen' else [pet],
        player=snapshot(guid=5,pet=PET+1 if fault=='wrong_summon' else PET))
    assert rows[0] is None and rows[1]['packet'] is None and rows[1]['rejection']


@pytest.mark.parametrize('fault',['wrong_bar_spell','disabled_bar','passive_bar','absent_learned_autocast'])
def test_enabled_current_native_bar_and_learned_spell_both_authorize_manual_blood_pact(codec,fault):
    body=bytearray(CATALOG)
    if fault=='wrong_bar_spell':struct.pack_into('<I',body,18+4*4,0xc1000c26)
    elif fault=='disabled_bar':struct.pack_into('<I',body,18+4*4,0x810018a3)
    elif fault=='passive_bar':struct.pack_into('<I',body,18+4*4,0x010018a3)
    else:struct.pack_into('<I',body,59+2*4,0x010018a3)
    rows=controlled(codec,[translate(request())],catalog=bytes(body))
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and rows[1]['packet'] is None and rows[1]['rejection']


def test_manual_spell_requires_actual_catalog_release_and_recovers_after_release(codec):
    rows=controlled(codec,[translate(request()),action('pet_response','SMSG_PET_SPELLS',CATALOG),
        translate(request())],catalog=None)
    assert rows[0]['packet'] is None and rows[0]['rejection'];assert rows[2]==expected()


@pytest.mark.parametrize('catalog',[struct.pack('<Q',0),struct.pack('<Q',PET+1)+CATALOG[8:],CATALOG[:-1]])
def test_new_empty_unreleased_or_failed_catalog_revokes_manual_spell_authority(codec,catalog):
    rows=controlled(codec,[action('pet_response','SMSG_PET_SPELLS',catalog),translate(request()),
        action('pet_response','SMSG_PET_SPELLS',CATALOG),translate(request())])
    assert rows[2]['packet'] is None and rows[2]['rejection'];assert rows[4]==expected()


def test_native_pet_removal_revokes_manual_spell_authority(codec):
    rows=controlled(codec,[action('destroy','',struct.pack('<QB',PET,0)),translate(request())])
    assert rows[2]['packet'] is None and rows[2]['rejection']

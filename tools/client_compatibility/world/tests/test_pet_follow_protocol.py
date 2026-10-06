"""Actual Follow wire and rejection recovery under native pet authority."""
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action,snapshot,unit

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_follow_ui123.json').read_text())
PET=FIXTURE['native_pet_guid'];IDENTITY=FIXTURE['modern_request']['pet_guid']
CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])
CAPTURED=bytes.fromhex(FIXTURE['modern_request']['packet']['body'])


def request(identity=IDENTITY,word=0x03800001,target=(0,0),position=(0,0,0)):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def controlled(codec,actions,units=None,player=None):
    return result(codec,op='stateful',character=FIXTURE['character'],
        snapshot=player or snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)] if units is None else units,gameobjects=[],
        actions=[action('pet_response','SMSG_PET_SPELLS',CATALOG),*actions])


def expected():
    return ['CMSG_PET_ACTION',struct.pack('<QIQfff',PET,0x07000001,0,0,0,0).hex()]


def test_actual_trained_imp_follow_preserves_guid_and_native_command(codec):
    assert request()==CAPTURED
    rows=controlled(codec,[action('pet_request','CMSG_PET_ACTION',CAPTURED)])
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[1]==expected()


@pytest.mark.parametrize('body',[request(word=0x03800004),request(word=0x03800002),
    request(word=0x03000001),request(word=0x01800003),request(target=(5,1)),
    request(position=(1,0,0)),request(position=(0,float('nan'),0)),
    request(position=(0,0,float('inf'))),request(identity=(0,0)),
    request(identity=(IDENTITY[0]+1,IDENTITY[1])),CAPTURED[:-1],CAPTURED+b'x',b''])
def test_rejection_sends_no_packet_and_preserves_authority_for_next_valid_follow(codec,body):
    rows=controlled(codec,[action('translate_pet_action','',body),
        action('translate_pet_action','',CAPTURED)])
    assert rows[1]['packet'] is None and rows[1]['rejection']
    assert rows[2]=={'packet':expected(),'rejection':''}


@pytest.mark.parametrize('change',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind'])
def test_follow_requires_owned_visible_numbered_pet_and_matching_summon(codec,change):
    pet=unit(owner=6 if change=='foreign_owner' else 5,guid=PET,number=0 if change=='unnumbered' else 2)
    if change=='wrong_kind':pet['kind']=4
    player=snapshot(guid=5,pet=PET+1 if change=='wrong_summon' else PET)
    rows=controlled(codec,[action('translate_pet_action','',CAPTURED)],
        units=[] if change=='unseen' else [pet],player=player)
    assert rows[0] is None
    assert rows[1]['packet'] is None and rows[1]['rejection']


def test_follow_without_native_catalog_is_rejected_without_granting_authority(codec):
    rows=result(codec,op='stateful',character=FIXTURE['character'],snapshot=snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)],gameobjects=[],
        actions=[action('translate_pet_action','',CAPTURED),
            action('pet_response','SMSG_PET_SPELLS',CATALOG),action('translate_pet_action','',CAPTURED)])
    assert rows[0]['packet'] is None and rows[0]['rejection']
    assert rows[1][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[2]=={'packet':expected(),'rejection':''}

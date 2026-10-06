"""Actual Stay capture under the same native owner/catalog authority as Follow."""
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action,snapshot,unit

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_stay_ui124.json').read_text())
PET=FIXTURE['native_pet_guid'];IDENTITY=FIXTURE['modern_request']['pet_guid']
CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])
CAPTURED=bytes.fromhex(FIXTURE['modern_request']['packet']['body'])


def request(identity=IDENTITY,word=0x03800000,target=(0,0),position=(0,0,0)):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def controlled(codec,body=CAPTURED,units=None,player=None,catalog=True):
    actions=([action('pet_response','SMSG_PET_SPELLS',CATALOG)] if catalog else [])
    return result(codec,op='stateful',character=FIXTURE['character'],
        snapshot=player or snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)] if units is None else units,gameobjects=[],
        actions=[*actions,action('translate_pet_action','',body)])


def test_actual_trained_imp_stay_preserves_submitted_guid_and_native_idle_command(codec):
    assert request()==CAPTURED
    rows=controlled(codec)
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[1]=={'packet':['CMSG_PET_ACTION',
        struct.pack('<QIQfff',PET,0x07000000,0,0,0,0).hex()],'rejection':''}


@pytest.mark.parametrize('body',[request(word=0x03800002),request(word=0x03800004),
    request(word=0x03000000),request(word=0x01800000),request(target=(5,1)),
    request(position=(1,0,0)),request(position=(0,float('nan'),0)),
    request(position=(0,0,float('inf'))),request(identity=(0,0)),
    request(identity=(IDENTITY[0]+1,IDENTITY[1])),CAPTURED[:-1],CAPTURED+b'x',b''])
def test_unsupported_stay_shapes_send_no_native_packet(codec,body):
    row=controlled(codec,body)[1]
    assert row['packet'] is None and row['rejection']


@pytest.mark.parametrize('change',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind'])
def test_stay_requires_current_owned_numbered_visible_pet(codec,change):
    pet=unit(owner=6 if change=='foreign_owner' else 5,guid=PET,number=0 if change=='unnumbered' else 2)
    if change=='wrong_kind':pet['kind']=4
    player=snapshot(guid=5,pet=PET+1 if change=='wrong_summon' else PET)
    rows=controlled(codec,units=[] if change=='unseen' else [pet],player=player)
    assert rows[0] is None
    assert rows[1]['packet'] is None and rows[1]['rejection']


def test_stay_without_released_native_catalog_cannot_grant_authority(codec):
    row=controlled(codec,catalog=False)[0]
    assert row['packet'] is None and row['rejection']

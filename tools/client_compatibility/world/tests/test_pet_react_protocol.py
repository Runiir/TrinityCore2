"""Actual Passive/Assist captures retain the same catalog and native owner gates."""
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action,snapshot,unit

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_react_ui126.json').read_text())
PET=FIXTURE['native_pet_guid'];IDENTITY=FIXTURE['modern_decoded']['passive']['guid']
CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])


def request(word=0x03000000,identity=IDENTITY,target=(0,0),position=(0,0,0)):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def controlled(codec,body,units=None,player=None,catalog=True):
    return result(codec,op='stateful',character=FIXTURE['character'],snapshot=player or snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)] if units is None else units,gameobjects=[],
        actions=([action('pet_response','SMSG_PET_SPELLS',CATALOG)] if catalog else [])+
            [action('translate_pet_action','',body)])


@pytest.mark.parametrize('name,value',[('passive',0),('assist',3)])
def test_actual_owned_reaction_preserves_guid_and_native_reaction_type(codec,name,value):
    body=bytes.fromhex(FIXTURE['modern_requests'][name]['body']);assert body==request(0x03000000|value)
    rows=controlled(codec,body);assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[1]=={'packet':['CMSG_PET_ACTION',struct.pack('<QIQfff',PET,0x06000000|value,0,0,0,0).hex()],'rejection':''}


@pytest.mark.parametrize('body',[request(0x03000001),request(0x03000002),request(0x03000004),
    request(0x03800002),request(0x01800000),request(target=(5,1)),request(position=(1,0,0)),
    request(position=(0,float('nan'),0)),request(position=(0,0,float('inf'))),request(identity=(0,0)),
    request(identity=(IDENTITY[0]+1,IDENTITY[1])),request()[:-1],request()+b'x',b''])
def test_uncaptured_or_changed_reaction_sends_no_native_action(codec,body):
    row=controlled(codec,body)[1];assert row['packet'] is None and row['rejection']


@pytest.mark.parametrize('fault',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind'])
def test_reaction_requires_current_owned_visible_numbered_pet(codec,fault):
    pet=unit(owner=6 if fault=='foreign_owner' else 5,guid=PET,number=0 if fault=='unnumbered' else 2)
    if fault=='wrong_kind':pet['kind']=4
    rows=controlled(codec,request(),units=[] if fault=='unseen' else [pet],
        player=snapshot(guid=5,pet=PET+1 if fault=='wrong_summon' else PET))
    assert rows[0] is None and rows[1]['packet'] is None and rows[1]['rejection']


def test_reaction_without_released_control_catalog_cannot_grant_authority(codec):
    rows=controlled(codec,request(),catalog=False);assert rows[0]['packet'] is None and rows[0]['rejection']

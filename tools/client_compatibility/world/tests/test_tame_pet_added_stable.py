"""Replay the actual UI160 Added and delayed native owner/pet updates.

The 60895 opcode table has no SMSG_PET_ADDED. Its existing StableInfo
update-field writer supplies the new pet only after native ownership agrees.
"""
from copy import deepcopy
import json
from pathlib import Path
import pytest
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action
from tools.client_compatibility.world.tests.test_hunter_stable_protocol import OWNER,SNAPSHOT,catalog,reply,decode_update

SOURCE=json.loads((Path(__file__).parent/'fixtures/tame_pet_added_ui160.json').read_text())
BODY=bytes.fromhex(SOURCE['body'])
MODEL={'id':4,'owner':6,'entry':42717,'modelid':903,'PetType':1}
TARGET={'guid':SOURCE['target_guid'],'map':0,'kind':3}


def add(body=BODY):return action('tame_pet_added_response','SMSG_PET_ADDED',body)
def ready():return action('tame_pet_added_ready','',b'')
def cast():return action('cast_request','CMSG_CAST_SPELL',bytes.fromhex(SOURCE['request']))
def go():return action('cast_response','SMSG_SPELL_GO',bytes.fromhex(SOURCE['go']))
def baseline():return reply(catalog(guid=0,slot=5,last=20),[MODEL])


def owned(codec,actions,pet=None,snapshot=None,character=OWNER):
    snapshot=deepcopy(SNAPSHOT) if snapshot is None else snapshot
    snapshot['fields'][INDEX['UNIT_FIELD_LEVEL']]=10
    snapshot['fields'][INDEX['UNIT_FIELD_HEALTH']]=209
    units=[TARGET]
    if pet:
        units.append(pet);guid=pet['guid'];index=INDEX['UNIT_FIELD_SUMMON']
        snapshot['fields'][index]=guid&0xffffffff;snapshot['fields'][index+1]=guid>>32
    return result(codec,op='stateful',character=character,snapshot=snapshot,units=units,gameobjects=[],actions=actions)


def expected():
    return [(5,4,42717,903,10,3,0,'Harnesswolf'),(0,10,299,18156,10,1,0,'Wolf')],(0,0)


def test_actual_added_waits_for_later_native_links_and_delivers_canonical_level10(codec):
    actions=[baseline(),cast(),go(),add()]
    for packet in SOURCE['updates']:
        actions.extend([action('object_updates','SMSG_UPDATE_OBJECT',bytes.fromhex(packet['body'])),ready()])
    rows=owned(codec,actions)
    assert decode_update(rows[0])==([expected()[0][0]],(0,0))
    assert rows[1][0]=='CMSG_CAST_SPELL' and rows[2][0]=='SMSG_SPELL_GO'
    assert rows[3] is None
    releases=[row for command,row in zip(actions,rows) if command['fn']=='tame_pet_added_ready' and row is not None]
    assert len(releases)==1 and decode_update(releases[0])==expected()


def test_current_owned_pet_can_release_added_once_without_replaying_a_native_request(codec):
    rows=owned(codec,[baseline(),cast(),go(),add(),add(),ready()],deepcopy(SOURCE['pet_after']))
    assert decode_update(rows[0])==([expected()[0][0]],(0,0))
    assert rows[1][0]=='CMSG_CAST_SPELL' and rows[2][0]=='SMSG_SPELL_GO'
    assert decode_update(rows[3])==expected() and rows[4] is rows[5] is None


@pytest.mark.parametrize('fault',['no_go','no_local_request','warlock','no_catalog','foreign_owner',
    'foreign_creator','wrong_number','wrong_entry','wrong_map','no_display','dead','ambiguous'])
def test_added_requires_current_native_cast_catalog_and_unambiguous_owned_pet(codec,fault):
    pet=deepcopy(SOURCE['pet_after']);owner=deepcopy(OWNER);actions=[baseline(),cast(),go(),add()]
    if fault=='no_go':actions.pop(2)
    elif fault=='no_local_request':actions.pop(1)
    elif fault=='warlock':owner['class']=9
    elif fault=='no_catalog':actions.pop(0)
    elif fault=='foreign_owner':pet['fields'][str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=7
    elif fault=='foreign_creator':pet['fields'][str(INDEX['UNIT_FIELD_CREATEDBY'])]=7
    elif fault=='wrong_number':pet['fields'][str(INDEX['UNIT_FIELD_PETNUMBER'])]=11
    elif fault=='wrong_entry':pet['fields'][str(INDEX['OBJECT_FIELD_ENTRY'])]=42717
    elif fault=='wrong_map':pet['map']=1
    elif fault=='no_display':pet['fields'][str(INDEX['UNIT_FIELD_DISPLAYID'])]=0
    elif fault=='dead':pet['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    else:
        # A native catalog that already occupies the new slot cannot be replaced.
        actions[0]=reply(catalog(guid=0,slot=0,last=20),[MODEL])
    row=owned(codec,actions,pet,character=owner)[-1]
    assert row is None or isinstance(row,dict) and 'error' in row


@pytest.mark.parametrize('body',[b'',BODY[:-1],BODY+b'x',BODY[:-1]+b'x',BODY[:8]+b'\3'+BODY[9:],
    (0).to_bytes(4,'little')+BODY[4:],BODY[:4]+(5).to_bytes(4,'little')+BODY[8:]])
def test_bad_added_cannot_consume_a_later_valid_native_outcome(codec,body):
    rows=owned(codec,[baseline(),cast(),go(),add(body),add()],deepcopy(SOURCE['pet_after']))
    assert isinstance(rows[3],dict) and 'error' in rows[3]
    assert decode_update(rows[4])==expected()

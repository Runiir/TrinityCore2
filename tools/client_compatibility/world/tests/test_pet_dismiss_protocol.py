"""Actual trained-Imp Dismiss request, ownership gates and authority lifetime."""
import json
import struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_inventory_oracle_lifecycle import packet
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action,snapshot,unit

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_dismiss_ui120.json').read_text())
PET=FIXTURE['native_pet_guid']
IDENTITY=FIXTURE['modern_request']['pet_guid']
CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])
CAPTURED=bytes.fromhex(FIXTURE['modern_request']['packet']['body'])


def request(identity=IDENTITY,word=0x03800003,target=(0,0),position=(0,0,0)):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def run_owned(codec,actions,units=None,player=None):
    return result(codec,op='stateful',character=FIXTURE['character'],
        snapshot=player or snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)] if units is None else units,
        gameobjects=[],actions=actions)


def controlled(codec,body=CAPTURED,**kwargs):
    return run_owned(codec,[action('pet_response','SMSG_PET_SPELLS',CATALOG),
        action('pet_request','CMSG_PET_ACTION',body)],**kwargs)


def test_actual_trained_imp_dismiss_preserves_submitted_guid_and_native_command(codec):
    assert request()==CAPTURED,'fixture must retain the actual client wire shape'
    rows=controlled(codec)
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    expected=struct.pack('<QIQfff',PET,0x07000003,0,0,0,0).hex()
    assert rows[1]==['CMSG_PET_ACTION',expected],rows[1]


def test_visible_owned_pet_without_released_catalog_has_no_dismiss_authority(codec):
    rows=run_owned(codec,[action('pet_request','CMSG_PET_ACTION',CAPTURED)])
    assert 'error' in rows[0]


@pytest.mark.parametrize('change',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind'])
def test_dismiss_requires_current_native_owner_summon_number_and_pet_kind(codec,change):
    pet=unit(owner=6 if change=='foreign_owner' else 5,guid=PET,number=0 if change=='unnumbered' else 2)
    if change=='wrong_kind':pet['kind']=4
    player=snapshot(guid=5,pet=PET+1 if change=='wrong_summon' else PET)
    rows=controlled(codec,units=[] if change=='unseen' else [pet],player=player)
    assert rows[0] is None and 'error' in rows[1]


@pytest.mark.parametrize('change',['owner','number','summon'])
def test_native_sparse_changes_are_rechecked_after_catalog_release(codec,change):
    guid=5 if change=='summon' else PET
    field={'owner':'UNIT_FIELD_SUMMONEDBY','number':'UNIT_FIELD_PETNUMBER','summon':'UNIT_FIELD_SUMMON'}[change]
    fields={INDEX[field]:6 if change=='owner' else 0}
    if change!='number':fields[INDEX[field]+1]=0
    rows=run_owned(codec,[action('pet_response','SMSG_PET_SPELLS',CATALOG),
        action('object_updates','SMSG_UPDATE_OBJECT',bytes.fromhex(packet(guid,fields))),
        action('pet_request','CMSG_PET_ACTION',CAPTURED)])
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and 'error' not in (rows[1] or {})
    assert 'error' in rows[2]


@pytest.mark.parametrize('body',[
    request(identity=(0,0)),request(identity=(IDENTITY[0]+1,IDENTITY[1])),
    request(identity=(IDENTITY[0],IDENTITY[1]^(1<<29))),
    request(word=0x03800002),request(word=0x03000003),request(word=0x80800c26),
    request(target=(5,1)),request(position=(1,0,0)),request(position=(0,float('nan'),0)),
    request(position=(0,0,float('inf'))),CAPTURED[:-1],CAPTURED+b'x',b'',
])
def test_unobserved_or_malformed_dismiss_shapes_never_reach_native(codec,body):
    rows=controlled(codec,body)
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and 'error' in rows[1]


@pytest.mark.parametrize('clear',['empty_catalog','replacement_pending','destroy','logout'])
def test_catalog_clear_replacement_removal_and_logout_revoke_dismiss(codec,clear):
    if clear=='empty_catalog':revoke=action('pet_response','SMSG_PET_SPELLS',struct.pack('<Q',0))
    elif clear=='replacement_pending':
        replacement=bytearray(CATALOG);struct.pack_into('<Q',replacement,0,PET+1)
        revoke=action('pet_response','SMSG_PET_SPELLS',replacement)
    elif clear=='destroy':revoke=action('destroy','SMSG_DESTROY_OBJECT',struct.pack('<QB',PET,0))
    else:revoke=action('logout_complete','')
    rows=run_owned(codec,[action('pet_response','SMSG_PET_SPELLS',CATALOG),revoke,
        action('pet_request','CMSG_PET_ACTION',CAPTURED)])
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and 'error' in rows[2]

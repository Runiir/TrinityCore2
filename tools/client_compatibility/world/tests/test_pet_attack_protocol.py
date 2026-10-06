"""Reviewed actual Attack bytes require a live owned pet and selected native victim."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action

F=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_attack_ui137.json').read_text())
PET=F['native_pet_guid'];VICTIM=F['native_target_create']['guid'];D=F['request']['decoded']
CAPTURED=bytes.fromhex(F['request']['packet']['body']);CATALOG=bytes.fromhex(F['native_catalog_packet']['body'])


def request(word=D['word'],identity=D['guid'],target=D['target'],position=(0,0,0)):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def translated(body):return action('translate_pet_action','',body)


def controlled(codec,actions,pet=None,target=None,player=None,units=None,catalog=CATALOG):
    return result(codec,op='stateful',character=F['character'],
        snapshot=F['native_owner_snapshot'] if player is None else player,
        units=units if units is not None else [pet or F['native_pet_create'],target or F['native_target_create']],
        gameobjects=[],actions=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])+actions)


def expected():
    return {'packet':['CMSG_PET_ACTION',struct.pack('<QIQfff',PET,0x07000002,VICTIM,0,0,0).hex()],
        'rejection':''}


def test_actual_attack_preserves_both_reviewed_guids_and_native_command(codec):
    assert request()==CAPTURED and len(CAPTURED)==31 and (D['action_type'],D['action_value'])==(7,2)
    rows=controlled(codec,[translated(CAPTURED)])
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and rows[1]==expected()


@pytest.mark.parametrize('body',[request(target=(0,0)),request(target=D['guid']),request(target=(5,1)),
    request(target=(D['target'][0]+1,D['target'][1])),request(identity=(0,0)),
    request(identity=(D['guid'][0]+1,D['guid'][1])),request(word=0x03000002),request(word=0x01800002),
    request(word=0x03800000),request(word=0x03800001),request(word=0x03800003),request(word=0x03800004),
    request(position=(1,0,0)),request(position=(0,float('nan'),0)),request(position=(0,0,float('inf'))),
    CAPTURED[:-1],CAPTURED+b'x',CAPTURED+CAPTURED,b''])
def test_rejected_attack_sends_no_command_and_recovers_on_actual_request(codec,body):
    rows=controlled(codec,[translated(body),translated(CAPTURED)])
    assert rows[1]['packet'] is None and rows[1]['rejection'] and rows[2]==expected()


@pytest.mark.parametrize('fault',['unseen_pet','unseen_target','foreign_owner','wrong_summon','unnumbered',
    'pet_kind','target_kind','dead_pet','dead_owner','dead_target','pet_map','target_map','stale_selection'])
def test_attack_requires_current_native_ownership_selection_health_and_map(codec,fault):
    pet=copy.deepcopy(F['native_pet_create']);target=copy.deepcopy(F['native_target_create'])
    player=copy.deepcopy(F['native_owner_snapshot'])
    if fault=='foreign_owner':pet['fields'][str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=6
    elif fault=='wrong_summon':player['fields'][str(INDEX['UNIT_FIELD_SUMMON'])]=(PET+1)&0xffffffff
    elif fault=='unnumbered':pet['fields'][str(INDEX['UNIT_FIELD_PETNUMBER'])]=0
    elif fault=='pet_kind':pet['kind']=4
    elif fault=='target_kind':target['kind']=4
    elif fault=='dead_pet':pet['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    elif fault=='dead_owner':player['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    elif fault=='dead_target':target['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    elif fault=='pet_map':pet['map']=1
    elif fault=='target_map':target['map']=1
    elif fault=='stale_selection':player['fields'][str(INDEX['UNIT_FIELD_TARGET'])]=0
    units=[u for u in [pet,target] if not (fault=='unseen_pet' and u is pet or fault=='unseen_target' and u is target)]
    rows=controlled(codec,[translated(CAPTURED)],player=player,units=units)
    assert rows[-1]['packet'] is None and rows[-1]['rejection']


@pytest.mark.parametrize('word',[0x07000000,0x07000001,0x07000004,0x01000002])
def test_attack_requires_the_released_native_attack_slot(codec,word):
    catalog=bytearray(CATALOG);struct.pack_into('<I',catalog,18,word)
    rows=controlled(codec,[translated(CAPTURED)],catalog=bytes(catalog))
    assert rows[1]['packet'] is None and rows[1]['rejection']


def test_attack_without_released_catalog_recovers_after_current_catalog(codec):
    rows=controlled(codec,[translated(CAPTURED),action('pet_response','SMSG_PET_SPELLS',CATALOG),
        translated(CAPTURED)],catalog=None)
    assert rows[0]['packet'] is None and rows[0]['rejection'] and rows[2]==expected()


@pytest.mark.parametrize('guid',[PET,VICTIM])
def test_removing_pet_or_victim_revokes_attack_authority(codec,guid):
    rows=controlled(codec,[action('destroy','',struct.pack('<QB',guid,0)),translated(CAPTURED)])
    assert rows[2]['packet'] is None and rows[2]['rejection']

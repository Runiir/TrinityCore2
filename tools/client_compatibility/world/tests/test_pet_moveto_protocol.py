"""Actual owned Move To ground bytes retain native authority and destination."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action

F=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_moveto_ui135.json').read_text())
PET=F['native_pet_guid'];D=F['request']['decoded'];CAPTURED=bytes.fromhex(F['request']['packet']['body'])
CATALOG=bytes.fromhex(F['native_catalog_packet']['body'])


def request(word=D['word'],identity=D['guid'],target=(0,0),position=D['position']):
    return Writer().guid(*identity).pack('I',word).guid(*target).pack('3f',*position).finish()


def controlled(codec,actions,units=None,player=None,catalog=CATALOG):
    return result(codec,op='stateful',character=F['character'],
        snapshot=player if player is not None else F['native_owner_snapshot'],
        units=units if units is not None else [F['native_pet_create']],gameobjects=[],
        actions=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])+actions)


def translated(body):return action('translate_pet_action','',body)


def expected():
    return {'packet':['CMSG_PET_ACTION',struct.pack('<QIQfff',PET,0x07000004,0,*D['position']).hex()],
        'rejection':''}


def test_actual_reviewed_move_to_preserves_guid_empty_target_and_destination(codec):
    assert request()==CAPTURED and len(CAPTURED)==24 and (D['action_type'],D['action_value'])==(7,4)
    rows=controlled(codec,[translated(CAPTURED)])
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and rows[1]==expected()


@pytest.mark.parametrize('body',[request(word=0x03800002),request(word=0x03000002),
    request(word=0x01800004),request(target=D['guid']),request(target=(5,1)),
    request(identity=(0,0)),request(identity=(D['guid'][0]+1,D['guid'][1])),
    request(position=(0,0,0)),request(position=(float('nan'),0,1)),
    request(position=(0,float('inf'),1)),request(position=(0,1,-float('inf'))),
    request(position=(17068,1,1)),request(position=(1,-17068,1)),request(position=(1,1,17068)),
    CAPTURED[:-1],CAPTURED+b'x',CAPTURED+CAPTURED,b''])
def test_move_to_rejects_uncaptured_shape_and_recovers_on_the_exact_valid_request(codec,body):
    rows=controlled(codec,[translated(body),translated(CAPTURED)])
    assert rows[1]['packet'] is None and rows[1]['rejection']
    assert rows[2]==expected()


@pytest.mark.parametrize('fault',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind',
    'dead_pet','dead_owner','other_map'])
def test_move_to_requires_the_current_visible_live_owned_pet(codec,fault):
    pet=copy.deepcopy(F['native_pet_create']);player=copy.deepcopy(F['native_owner_snapshot'])
    if fault=='foreign_owner':pet['fields'][str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=6
    elif fault=='wrong_summon':player['fields'][str(INDEX['UNIT_FIELD_SUMMON'])]=PET+1 & 0xffffffff
    elif fault=='unnumbered':pet['fields'][str(INDEX['UNIT_FIELD_PETNUMBER'])]=0
    elif fault=='wrong_kind':pet['kind']=4
    elif fault=='dead_pet':pet['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    elif fault=='dead_owner':player['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    elif fault=='other_map':pet['map']=1
    rows=controlled(codec,[translated(CAPTURED)],units=[] if fault=='unseen' else [pet],player=player)
    assert rows[1]['packet'] is None and rows[1]['rejection']


@pytest.mark.parametrize('word',[0x07000000,0x07000001,0x07000002,0x01000004])
def test_move_to_cannot_borrow_a_different_native_bar_command(codec,word):
    catalog=bytearray(CATALOG);struct.pack_into('<I',catalog,18+2*4,word)
    rows=controlled(codec,[translated(CAPTURED)],catalog=bytes(catalog))
    assert rows[1]['packet'] is None and rows[1]['rejection']


def test_move_to_without_a_released_catalog_is_rejected_then_recovers(codec):
    rows=controlled(codec,[translated(CAPTURED),action('pet_response','SMSG_PET_SPELLS',CATALOG),
        translated(CAPTURED)],catalog=None)
    assert rows[0]['packet'] is None and rows[0]['rejection'] and rows[2]==expected()


@pytest.mark.parametrize('catalog',[struct.pack('<Q',0),struct.pack('<Q',PET+1)+CATALOG[8:],CATALOG[:-1]])
def test_catalog_clear_replacement_or_parse_failure_revokes_move_to_authority(codec,catalog):
    rows=controlled(codec,[action('pet_response','SMSG_PET_SPELLS',catalog),translated(CAPTURED),
        action('pet_response','SMSG_PET_SPELLS',CATALOG),translated(CAPTURED)])
    assert rows[2]['packet'] is None and rows[2]['rejection'] and rows[4]==expected()


def test_pet_removal_revokes_move_to_authority(codec):
    rows=controlled(codec,[action('destroy','',struct.pack('<QB',PET,0)),translated(CAPTURED)])
    assert rows[2]['packet'] is None and rows[2]['rejection']

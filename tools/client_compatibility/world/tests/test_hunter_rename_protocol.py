"""Captured stock Rename preserves identity and current one-time authority."""
from copy import deepcopy
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_inventory_oracle_lifecycle import packet
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action

F=json.loads((Path(__file__).parent/'fixtures/native_owned_hunter_rename_ui143.json').read_text())
PET=F['native_pet_create']['guid'];D=F['request']['decoded']
CAPTURED=bytes.fromhex(F['request']['packet']['body']);CATALOG=bytes.fromhex(F['native_catalog_packet']['body'])


def request(name='Harnesswolf',number=4,guid=D['guid'],declined=0,padding=0):
    return (Writer().guid(*guid).pack('i',number).bits(len(name),8).bits(declined,1).bits(padding,7)
        .raw(name.encode()).finish())


def rename(body=CAPTURED):return action('translate_pet_rename','CMSG_PET_RENAME',body)


def owned(codec,actions,pet=None,player=None,units=None,catalog=CATALOG):
    return result(codec,op='stateful',character=F['character'],gameobjects=[],
        snapshot=F['native_owner_snapshot'] if player is None else player,
        units=units if units is not None else [pet or F['native_pet_create']],
        actions=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])+actions)


def expected(name='Harnesswolf'):
    return {'packet':['CMSG_PET_RENAME',(struct.pack('<Q',PET)+name.encode()+b'\0\0').hex()],'rejection':''}


def test_actual_yes_confirmation_preserves_native_pet_and_exact_name(codec):
    assert request()==CAPTURED and len(CAPTURED)==25
    rows=owned(codec,[rename()]);assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and rows[1]==expected()


@pytest.mark.parametrize('body',[request(number=0),request(number=-1),request(number=2),
    request(guid=(0,0)),request(guid=(D['guid'][0]+1,D['guid'][1])),request(guid=(D['guid'][0],D['guid'][1]^(1<<29))),
    request(declined=1),request(padding=1),request(name='A'),request(name='Harnesswolfxxx'),
    request(name='Harness wolf'),request(name='Harness1'),request(name='Harness\0wolf'),
    CAPTURED[:-1],CAPTURED+b'x',CAPTURED+CAPTURED,b''])
def test_foreign_or_unreviewed_shape_is_rejected_without_losing_session(codec,body):
    rows=owned(codec,[rename(body),rename()])
    assert rows[1]['packet'] is None and rows[1]['rejection'] and rows[2]==expected()


@pytest.mark.parametrize('fault',('unseen','foreign_owner','wrong_summon','wrong_number','wrong_kind','wrong_map',
    'warlock','no_rename','pvp_bit_only'))
def test_rename_requires_current_owned_hunter_and_permission(codec,fault):
    pet=deepcopy(F['native_pet_create']);player=deepcopy(F['native_owner_snapshot'])
    fields=pet['fields'];self_fields=player['fields']
    if fault=='foreign_owner':fields[str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=5
    elif fault=='wrong_summon':self_fields[str(INDEX['UNIT_FIELD_SUMMON'])]=(PET+1)&0xffffffff
    elif fault=='wrong_number':fields[str(INDEX['UNIT_FIELD_PETNUMBER'])]=2
    elif fault=='wrong_kind':pet['kind']=4
    elif fault=='wrong_map':pet['map']=1
    elif fault=='warlock':self_fields[str(INDEX['UNIT_FIELD_BYTES_0'])]=1|(9<<8)
    elif fault=='no_rename':fields[str(INDEX['UNIT_FIELD_BYTES_2'])]=2<<16
    elif fault=='pvp_bit_only':fields[str(INDEX['UNIT_FIELD_BYTES_2'])]=1<<8
    rows=owned(codec,[rename()],pet=pet,player=player,units=[] if fault=='unseen' else None)
    assert rows[-1]['packet'] is None and rows[-1]['rejection']


def test_visible_pet_needs_released_native_catalog(codec):
    rows=owned(codec,[rename(),action('pet_response','SMSG_PET_SPELLS',CATALOG),rename()],catalog=None)
    assert rows[0]['packet'] is None and rows[0]['rejection'] and rows[2]==expected()


@pytest.mark.parametrize('change',('rename_permission','owner','number','summon','class'))
def test_sparse_native_revocation_is_rechecked_for_every_submission(codec,change):
    guid=6 if change in ('summon','class') else PET
    field={'rename_permission':'UNIT_FIELD_BYTES_2','owner':'UNIT_FIELD_SUMMONEDBY',
        'number':'UNIT_FIELD_PETNUMBER','summon':'UNIT_FIELD_SUMMON','class':'UNIT_FIELD_BYTES_0'}[change]
    value={'rename_permission':2<<16,'owner':5,'number':0,'summon':0,'class':1|(9<<8)}[change]
    fields={INDEX[field]:value}
    if change in ('owner','summon'):fields[INDEX[field]+1]=0
    rows=owned(codec,[rename(),action('object_updates','SMSG_UPDATE_OBJECT',bytes.fromhex(packet(guid,fields))),rename()])
    assert rows[1]==expected() and rows[-1]['packet'] is None and rows[-1]['rejection']


@pytest.mark.parametrize('clear',('catalog','destroy','logout'))
def test_lifecycle_clear_revokes_rename_authority(codec,clear):
    revoke=(action('pet_response','SMSG_PET_SPELLS',struct.pack('<Q',0)) if clear=='catalog' else
        action('destroy','SMSG_DESTROY_OBJECT',struct.pack('<QB',PET,0)) if clear=='destroy' else action('logout_complete',''))
    rows=owned(codec,[revoke,rename()]);assert rows[-1]['packet'] is None and rows[-1]['rejection']

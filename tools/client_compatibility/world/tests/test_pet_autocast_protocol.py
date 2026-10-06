"""Actual stock autocast forms cannot move bars, borrow spells or stale pet authority."""
import json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action,snapshot,unit

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_autocast_ui130.json').read_text())
PET=FIXTURE['native_pet_guid'];IDENTITY=FIXTURE['requests'][0]['decoded']['guid']
CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])


def request(slot=3,spell=3110,enabled=False,identity=IDENTITY,tail=0):
    return Writer().guid(*identity).pack('IIB',slot,(0x181 if enabled else 0x101)<<23|spell,tail).finish()


def translate(body):return action('translate_pet_set_action','',body)


def controlled(codec,actions,units=None,player=None,catalog=CATALOG):
    return result(codec,op='stateful',character=FIXTURE['character'],snapshot=player or snapshot(guid=5,pet=PET),
        units=[unit(owner=5,guid=PET,number=2)] if units is None else units,gameobjects=[],
        actions=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])+actions)


def expected(slot=3,spell=3110,enabled=False):
    return {'packet':['CMSG_PET_SET_ACTION',struct.pack('<QII',PET,slot,
        (0xc1 if enabled else 0x81)<<24|spell).hex()],'rejection':''}


@pytest.mark.parametrize('captured',FIXTURE['requests'],ids=lambda c:c['case'])
def test_actual_autocast_preserves_guid_slot_spell_and_native_flag(codec,captured):
    d=captured['decoded'];body=bytes.fromhex(captured['packet']['body']);wanted=captured['local_enabled']
    assert body==request(d['slot'],d['spell'],wanted)
    rows=controlled(codec,[translate(body)]);assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[1]==expected(d['slot'],d['spell'],wanted)


@pytest.mark.parametrize('body',[request(slot=0),request(slot=4),request(slot=10),request(slot=0xffffffff),
    request(spell=6307),request(spell=0),request(spell=91702),request(tail=1),request(tail=128),
    request(identity=(0,0)),request(identity=(IDENTITY[0]+1,IDENTITY[1])),
    request()[:-1],request()+b'x',request()+request(),b'',
    Writer().guid(*IDENTITY).pack('IIB',3,0x03800001,0).finish(),
    Writer().guid(*IDENTITY).pack('IIB',3,0x00800c26,0).finish(),
    Writer().guid(*IDENTITY).pack('IIB',3,0xff800c26,0).finish()])
def test_changed_or_uncaptured_autocast_shape_has_no_native_effect_and_preserves_recovery(codec,body):
    rows=controlled(codec,[translate(body),translate(request())]);assert rows[1]['packet'] is None and rows[1]['rejection']
    assert rows[2]==expected()


@pytest.mark.parametrize('fault',['unseen','foreign_owner','wrong_summon','unnumbered','wrong_kind'])
def test_autocast_cannot_borrow_visible_pet_or_released_catalog_from_another_owner(codec,fault):
    pet=unit(owner=6 if fault=='foreign_owner' else 5,guid=PET,number=0 if fault=='unnumbered' else 2)
    if fault=='wrong_kind':pet['kind']=4
    rows=controlled(codec,[translate(request())],units=[] if fault=='unseen' else [pet],
        player=snapshot(guid=5,pet=PET+1 if fault=='wrong_summon' else PET))
    assert rows[0] is None and rows[1]['packet'] is None and rows[1]['rejection']


@pytest.mark.parametrize('fault',['wrong_bar_spell','passive_bar','absent_autocast_spell'])
def test_current_native_bar_and_learned_autocast_spell_must_both_authorize_request(codec,fault):
    body=bytearray(CATALOG)
    if fault=='wrong_bar_spell':struct.pack_into('<I',body,18+3*4,0xc10018a3)
    elif fault=='passive_bar':struct.pack_into('<I',body,18+3*4,0x01000c26)
    else:struct.pack_into('<I',body,59+3*4,0x01000c26)
    rows=controlled(codec,[translate(request())],catalog=bytes(body))
    assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE' and rows[1]['packet'] is None and rows[1]['rejection']


def test_no_autocast_authority_before_catalog_release_and_valid_catalog_recovers(codec):
    rows=controlled(codec,[translate(request()),action('pet_response','SMSG_PET_SPELLS',CATALOG),
        translate(request())],catalog=None)
    assert rows[0]['packet'] is None and rows[0]['rejection'];assert rows[2]==expected()


@pytest.mark.parametrize('catalog',[struct.pack('<Q',0),struct.pack('<Q',PET+1)+CATALOG[8:],CATALOG[:-1]])
def test_empty_unreleased_or_failed_new_native_catalog_revokes_old_autocast_authority(codec,catalog):
    rows=controlled(codec,[action('pet_response','SMSG_PET_SPELLS',catalog),translate(request()),
        action('pet_response','SMSG_PET_SPELLS',CATALOG),translate(request())])
    assert rows[2]['packet'] is None and rows[2]['rejection'];assert rows[4]==expected()


def test_native_pet_destruction_revokes_autocast_without_borrowing_old_catalog(codec):
    rows=controlled(codec,[action('destroy','',struct.pack('<QB',PET,0)),translate(request())])
    assert rows[2]['packet'] is None and rows[2]['rejection']

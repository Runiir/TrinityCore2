"""Captured owner cancellation can reach only its currently owned native Imp aura."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Writer,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action

FIXTURE=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_aura_cancel_ui133.json').read_text())
PET=FIXTURE['native_pet_guid'];CATALOG=bytes.fromhex(FIXTURE['native_catalog_packet']['body'])
REQUEST=bytes.fromhex(FIXTURE['modern_request']['body'])
AURA=bytes.fromhex(FIXTURE['native_aura_packet']['body'])


def packed(guid):
    raw=struct.pack('<Q',guid)
    return bytes([sum(1<<i for i,b in enumerate(raw) if b)])+bytes(b for b in raw if b)


def aura(*,caster=PET,flags=81,spell=6307,slot=0):
    return packed(5)+struct.pack('<BiHBB',slot,spell,flags,10,0)+packed(caster)+struct.pack('<i',11)


def request(spell=6307,caster=(5,player_high())):
    return Writer().pack('I',spell).guid(*caster).finish()


def cancel(body=REQUEST):return action('aura_cancel','CMSG_CANCEL_AURA',body)


def controlled(codec,actions,*,pet=None,player=None,catalog=CATALOG,buff=AURA):
    initial=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])
    if buff is not None:initial.append(action('aura_response','SMSG_AURA_UPDATE',buff))
    return result(codec,op='stateful',character=FIXTURE['character'],
        snapshot=FIXTURE['native_owner_snapshot'] if player is None else player,
        units=[FIXTURE['native_pet_create'] if pet is None else pet],gameobjects=[],actions=initial+actions)


def expected():return ['CMSG_PET_CANCEL_AURA',struct.pack('<QI',PET,6307).hex()]


def test_actual_stock_owner_cancel_resolves_exact_owned_native_area_aura(codec):
    assert REQUEST==request() and len(REQUEST)==9 and AURA==aura()
    rows=controlled(codec,[cancel()]);assert rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    assert rows[1][0]=='SMSG_AURA_UPDATE' and rows[2]==expected()


@pytest.mark.parametrize('body',[b'',REQUEST[:-1],REQUEST+b'x',REQUEST+REQUEST,
    request(caster=(0,0)),request(caster=(6,player_high())),
    request(caster=(PET,player_high())),request(caster=(35,(10<<58)|(1<<42)|(416<<6))),
    bytes.fromhex('a318000003a005000408'),request(spell=3110),request(spell=0)])
def test_changed_body_has_no_native_effect_and_valid_cancellation_remains_available(codec,body):
    rows=controlled(codec,[cancel(body),cancel()]);assert rows[2].get('error')
    assert rows[3]==expected()


@pytest.mark.parametrize('fault',['foreign_owner','unnumbered','dead','wrong_kind','wrong_summon'])
def test_owner_and_current_live_numbered_pet_links_cannot_be_borrowed(codec,fault):
    pet=copy.deepcopy(FIXTURE['native_pet_create']);player=copy.deepcopy(FIXTURE['native_owner_snapshot'])
    if fault=='foreign_owner':pet['fields'][str(INDEX['UNIT_FIELD_SUMMONEDBY'])]=6
    elif fault=='unnumbered':pet['fields'][str(INDEX['UNIT_FIELD_PETNUMBER'])]=0
    elif fault=='dead':pet['fields'][str(INDEX['UNIT_FIELD_HEALTH'])]=0
    elif fault=='wrong_kind':pet['kind']=4
    else:player['fields'][str(INDEX['UNIT_FIELD_SUMMON'])]+=1
    rows=controlled(codec,[cancel()],pet=pet,player=player);assert rows[2].get('error')


@pytest.mark.parametrize('buff',[aura(caster=PET+1),aura(caster=6),aura(flags=65),
    aura()+aura(slot=1)[2:],packed(5)+struct.pack('<Bi',0,0)])
def test_only_one_current_positive_native_pet_caster_aura_can_authorize_cancel(codec,buff):
    rows=controlled(codec,[cancel()],buff=buff);assert rows[2].get('error')


@pytest.mark.parametrize('fault',['wrong_bar_spell','disabled_bar','passive_bar','absent_learned_autocast'])
def test_native_released_bar_and_learned_spell_authority_are_required(codec,fault):
    body=bytearray(CATALOG)
    if fault=='wrong_bar_spell':struct.pack_into('<I',body,18+4*4,0xc1000c26)
    elif fault=='disabled_bar':struct.pack_into('<I',body,18+4*4,0x810018a3)
    elif fault=='passive_bar':struct.pack_into('<I',body,18+4*4,0x010018a3)
    else:struct.pack_into('<I',body,59+2*4,0x010018a3)
    rows=controlled(codec,[cancel()],catalog=bytes(body));assert rows[2].get('error')


def test_current_aura_cannot_replace_a_missing_control_catalog(codec):
    rows=controlled(codec,[cancel(),action('pet_response','SMSG_PET_SPELLS',CATALOG),cancel()],catalog=None)
    assert rows[1].get('error') and rows[3]==expected()


@pytest.mark.parametrize('catalog',[struct.pack('<Q',0),struct.pack('<Q',PET+1)+CATALOG[8:],CATALOG[:-1]])
def test_empty_unreleased_or_malformed_catalog_revokes_old_cancel_authority(codec,catalog):
    rows=controlled(codec,[action('pet_response','SMSG_PET_SPELLS',catalog),cancel(),
        action('pet_response','SMSG_PET_SPELLS',CATALOG),cancel()])
    assert rows[3].get('error') and rows[5]==expected()


def test_pet_destruction_revokes_cancel_authority(codec):
    rows=controlled(codec,[action('destroy','',struct.pack('<QB',PET,0)),cancel()])
    assert rows[3].get('error')


def test_existing_player_owned_aura_still_uses_native_player_cancel(codec):
    body=packed(5)+struct.pack('<BiHBB',0,32235,24,10,0)
    rows=controlled(codec,[cancel(request(spell=32235))],buff=body)
    assert rows[2]==['CMSG_CANCEL_AURA',struct.pack('<I',32235).hex()]

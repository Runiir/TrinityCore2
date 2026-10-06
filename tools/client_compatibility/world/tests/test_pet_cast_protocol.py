"""Reviewed native pet casts preserve caster/victim, visual, mana and cast lifetime."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.world.pet_casts import decode
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.native_objects import guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_pet_protocol import action
F=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_casts_ui138.json').read_text())
PET=F['native_pet']['guid'];TARGET=F['native_target']['guid'];CAT=bytes.fromhex(F['native_catalog_packet']['body'])
CASTS=F['casts'];START=CASTS[2]['packet'];GO=CASTS[3]['packet']


def mutated_header(packet,field,value):
    body=bytearray.fromhex(packet['body'])
    # Native packed GUID widths depend on the actual bytes, not a fixed offset.
    prefix=Reader(body);guid(prefix);guid(prefix)
    offset=prefix.pos
    if field=='counter':body[offset]=value
    elif field=='spell':struct.pack_into('<I',body,offset+1,value)
    else:raise ValueError(field)
    return {**packet,'body':body.hex()}


def request(packet):return action('translate_pet_cast',packet['name'],bytes.fromhex(packet['body']))


def controlled(codec,actions,pet=None,target=None,player=None,catalog=CAT,units=None):
    return result(codec,op='stateful',character=F['character'],snapshot=player or F['native_owner_snapshot'],
        units=units if units is not None else [pet or F['native_pet'],target or F['native_target']],gameobjects=[],
        actions=([action('pet_response','SMSG_PET_SPELLS',catalog)] if catalog is not None else [])+actions)


def test_actual_native_pet_casts_are_delivered_with_independent_pinned_decode(codec):
    rows=controlled(codec,[request(c['packet']) for c in CASTS]);active=None;identities=[]
    for row,capture in zip(rows[1:],CASTS):
        assert row['rejection']=='' and row['packet'] is not None
        name,body=row['packet'];d=decode(name,bytes.fromhex(body));native=capture['decoded']
        assert d['caster']==d['unit']==modern_guid(PET,0)
        assert d['spell']==native['spell'] and d['visual']=={3110:238900,6307:240306}[native['spell']]
        assert d['flags']==native['flags']&~0x40000 and d['extra']==native['extra'] and d['duration']==native['duration']
        assert d['target_flags']==native['target_flags'] and d['target']==modern_guid(native['target'],0)
        assert d['hits']==[modern_guid(g,0) for g in native['hits']] and d['remaining']==[(0,native['remaining'])]
        assert d['cast'][1]>>58==47 and (d['cast'][1]>>6)&0x7fffff==native['spell']
        if name=='SMSG_SPELL_START':active=d['cast'];identities.append(active)
        else:assert d['cast']==active;active=None
    assert len(set(identities))==len(identities)==5


@pytest.mark.parametrize('fault',['no_catalog','missing_pet','missing_target','foreign_owner','wrong_summon',
    'unnumbered','dead_pet','dead_owner','dead_target','pet_map','target_map','pet_kind','target_kind',
    'stale_selection','wrong_spell_slot','wrong_power'])
def test_pet_caster_and_target_require_current_released_native_authority(codec,fault):
    pet=copy.deepcopy(F['native_pet']);target=copy.deepcopy(F['native_target']);player=copy.deepcopy(F['native_owner_snapshot']);catalog=CAT
    key=lambda name:str(INDEX[name])
    if fault=='foreign_owner':pet['fields'][key('UNIT_FIELD_SUMMONEDBY')]=6
    elif fault=='wrong_summon':player['fields'][key('UNIT_FIELD_SUMMON')]=(PET+1)&0xffffffff
    elif fault=='unnumbered':pet['fields'][key('UNIT_FIELD_PETNUMBER')]=0
    elif fault=='dead_pet':pet['fields'][key('UNIT_FIELD_HEALTH')]=0
    elif fault=='dead_owner':player['fields'][key('UNIT_FIELD_HEALTH')]=0
    elif fault=='dead_target':target['fields'][key('UNIT_FIELD_HEALTH')]=0
    elif fault=='pet_map':pet['map']=1
    elif fault=='target_map':target['map']=1
    elif fault=='pet_kind':pet['kind']=4
    elif fault=='target_kind':target['kind']=4
    elif fault=='stale_selection':player['fields'][key('UNIT_FIELD_TARGET')]=0
    elif fault=='wrong_power':pet['fields'][key('UNIT_FIELD_BYTES_0')]=1<<24
    elif fault=='wrong_spell_slot':
        catalog=bytearray(catalog);struct.pack_into('<I',catalog,18+3*4,0xc10018a3)
    elif fault=='no_catalog':catalog=None
    units=[u for u in [pet,target] if not (fault=='missing_pet' and u is pet or fault=='missing_target' and u is target)]
    row=controlled(codec,[request(START)],pet=pet,target=target,player=player,catalog=catalog,units=units)[-1]
    assert row['packet'] is None


@pytest.mark.parametrize('body',[START['body'][:-2],START['body']+'00','',START['body'][:26]])
def test_malformed_native_cast_keeps_session_and_next_valid_cast_works(codec,body):
    bad={**START,'body':body};rows=controlled(codec,[request(bad),request(START),request(GO)])
    assert rows[1]['packet'] is None and rows[1]['rejection']
    assert rows[2]['packet'] and rows[3]['packet'] and rows[2]['rejection']==rows[3]['rejection']==''


@pytest.mark.parametrize('packet',[{**START,'body':START['body'].replace('f12f','f130',2)},
    mutated_header(START,'counter',1),mutated_header(START,'spell',6307)])
def test_foreign_caster_counter_or_spell_is_not_delivered(codec,packet):
    assert controlled(codec,[request(packet)])[-1]['packet'] is None


def test_completion_requires_matching_start_and_is_consumed_once(codec):
    rows=controlled(codec,[request(GO),request(START),request(GO),request(GO)])
    assert rows[1]['packet'] is None and rows[2]['packet'] and rows[3]['packet'] and rows[4]['packet'] is None


def test_pet_removal_revokes_pending_cast(codec):
    rows=controlled(codec,[request(START),action('destroy','',struct.pack('<QB',PET,0)),request(GO)])
    assert rows[1]['packet'] and rows[-1]['packet'] is None


def test_same_current_catalog_refresh_keeps_cast_completion_identity(codec):
    rows=controlled(codec,[request(START),action('pet_response','SMSG_PET_SPELLS',CAT),request(GO)])
    assert rows[1]['packet'] and rows[-1]['packet']
    assert decode(rows[1]['packet'][0],bytes.fromhex(rows[1]['packet'][1]))['cast']==decode(
        rows[-1]['packet'][0],bytes.fromhex(rows[-1]['packet'][1]))['cast']


@pytest.mark.parametrize('bad',[{**GO,'body':GO['body']+'00'},mutated_header(GO,'counter',1),mutated_header(GO,'spell',6307)])
def test_invalid_completion_preserves_pending_valid_cast(codec,bad):
    rows=controlled(codec,[request(START),request(bad),request(GO)])
    assert rows[1]['packet'] and rows[2]['packet'] is None and rows[3]['packet']


def test_catalog_clear_revokes_pending_cast(codec):
    rows=controlled(codec,[request(START),action('pet_response','SMSG_PET_SPELLS',bytes(8)),request(GO)])
    assert rows[1]['packet'] and rows[-1]['packet'] is None


def test_native_interruption_reuses_started_pet_cast_and_duplicate_is_ignored(codec):
    rows=controlled(codec,[request(START)]+[request(p) for p in F['interruptions']]+[request(F['interruptions'][0]),request(GO)])
    started=decode(*[rows[1]['packet'][0],bytes.fromhex(rows[1]['packet'][1])])
    for row,native in zip(rows[2:4],F['interruptions']):
        assert row['packet'][0]==native['name'];r=Reader(bytes.fromhex(row['packet'][1]))
        assert r.guid()==modern_guid(PET,0) and r.guid()==started['cast'];assert r.unpack('iI')==(3110,238900)
        assert r.unpack('H' if native['name']=='SMSG_SPELL_FAILURE' else 'B')==(0,);r.end()
    assert rows[4]['packet'] is None and rows[5]['packet'] is None

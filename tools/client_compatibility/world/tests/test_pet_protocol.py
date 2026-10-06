"""Pinned pet visibility, ownership, read authority and native packet conversion."""
import struct
import json
from pathlib import Path
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_inventory_packets import mask

PET=(0xf14<<52)|(416<<32)|1
OTHER=(0xf14<<52)|(416<<32)|2
IDENTITY=[1,(10<<58)|(1<<42)|(416<<6)]


def snapshot(guid=4,pet=PET):
    return {'guid':guid,'kind':4,'map':0,'fields':{
        INDEX['UNIT_FIELD_SUMMON']:pet&0xffffffff,
        INDEX['UNIT_FIELD_SUMMON']+1:pet>>32}}


def unit(owner=4,guid=PET,number=1):
    return {'guid':guid,'kind':3,'map':0,'fields':{
        INDEX['UNIT_FIELD_SUMMONEDBY']:owner,
        INDEX['UNIT_FIELD_PETNUMBER']:number}}


def action(fn,name,body=b''):
    return {'fn':fn,'name':name,'body':body.hex()}


def run(codec,actions,units=None,s=None):
    return result(codec,op='stateful',character={'guid':4,'map':0},snapshot=s or snapshot(),
        units=[unit()] if units is None else units,gameobjects=[],actions=actions)


def spells(guid=PET):
    return (struct.pack('<QHIBBH',guid,23,1000,2,1,0)+
        struct.pack('<10I',*range(10))+struct.pack('<B2IBIHII',2,3110,6307,1,3110,7,900,800))


def test_pet_guid_create_values_preserve_owner_and_native_pet_number(codec):
    u=result(codec,op='object_values',snapshot=unit(),character={})['UnitData']
    assert u.get('SummonedBy')==[4,player_high()]
    assert u.get('PetNumber')==1
    assert result(codec,op='object_values',snapshot=snapshot(),character={})['UnitData'].get('Summon')==IDENTITY


@pytest.mark.parametrize('field,index,value,fmt',[
    ('UNIT_FIELD_SUMMON',14,PET,'g'),('UNIT_FIELD_SUMMONEDBY',17,4,'g'),
    ('UNIT_FIELD_CREATEDBY',18,4,'g'),('UNIT_FIELD_PETNUMBER',61,1,'I'),
    ('UNIT_FIELD_PET_NAME_TIMESTAMP',62,1234,'I')])
@pytest.mark.parametrize('clear',[False,True])
def test_pet_sparse_fields_include_public_zero_resets(codec,field,index,value,fmt,clear):
    value=0 if clear else value
    fields={INDEX[field]:value&0xffffffff}
    if fmt=='g':fields[INDEX[field]+1]=value>>32
    s={'guid':4,'kind':4,'map':0,'fields':fields}
    body=result(codec,op='unit_update',snapshot=s,character={},changed=fields,visibility=0)
    assert body,'pet ownership scalar was dropped'
    r=Reader(bytes.fromhex(body));assert r.unpack('B')==(0,)
    assert r.guid()==(4,player_high());assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(0,0,3,1<<5)
    assert mask(r,8)=={index,(index//32)*32};r.align()
    if fmt=='g':assert list(r.guid())==([0,0] if not value else IDENTITY if value==PET else [value,player_high()])
    else:assert r.unpack('I')==(value,)
    r.end()


def test_native_pet_spells_preserve_actions_and_convert_cooldown_widths(codec):
    rows=run(codec,[action('pet_response','SMSG_PET_SPELLS',spells())])
    assert rows[0] and rows[0][0]=='SMSG_PET_SPELLS_MESSAGE'
    r=Reader(bytes.fromhex(rows[0][1]));assert list(r.guid())==IDENTITY
    assert r.unpack('HHIBBB')==(23,0,1000,1,0,2)
    assert r.unpack('10I')==tuple(range(10))
    assert r.unpack('3I')==(2,1,0) and r.unpack('2I')==(3110,6307)
    assert r.unpack('iiifH')==(3110,900,800,1.0,7);r.end()


def test_captured_pet_creation_and_later_owner_link_release_deferred_native_catalog(codec):
    golden=json.loads((Path(__file__).parent/'fixtures/native_pet_ui110.json').read_text())
    packets=golden['packets']
    rows=run(codec,[action('pet_response','SMSG_PET_SPELLS',spells()),
        action('object_updates','SMSG_UPDATE_OBJECT',bytes.fromhex(packets[0]['packet']['body'])),
        action('pet_ready',''),
        action('object_updates','SMSG_UPDATE_OBJECT',bytes.fromhex(packets[1]['packet']['body'])),
        action('pet_ready','')],units=[],s=snapshot(pet=0))
    assert rows[0] is None
    assert rows[1] and rows[1][0]=='SMSG_UPDATE_OBJECT','captured native Pet create was dropped'
    r=Reader(bytes.fromhex(rows[1][1]));assert r.unpack('HI')==(0,1)
    assert (r.bits(1),r.bits(1))==(0,0)
    block=Reader(r.raw(r.unpack('I')[0]));assert block.unpack('B')==(1,)
    assert list(block.guid())==IDENTITY and block.unpack('B')==(5,)
    assert rows[2] is None and rows[3][0]=='SMSG_UPDATE_OBJECT'
    assert rows[4][0]=='SMSG_PET_SPELLS_MESSAGE'


def test_pet_spell_clear_has_exact_modern_empty_shape(codec):
    rows=run(codec,[action('pet_response','SMSG_PET_SPELLS',struct.pack('<Q',0))])
    r=Reader(bytes.fromhex(rows[0][1]));assert r.guid()==(0,0)
    assert r.unpack('HHIBBB10I3I')==(0,)*19;r.end()


@pytest.mark.parametrize('change',['wrong_owner','unseen','wrong_summon','wrong_number'])
def test_pet_spells_never_forward_without_visible_owner_agreement(codec,change):
    units=[] if change=='unseen' else [unit(owner=5 if change=='wrong_owner' else 4,number=0 if change=='wrong_number' else 1)]
    rows=run(codec,[action('pet_response','SMSG_PET_SPELLS',spells()),action('pet_ready','')],
        units=units,s=snapshot(pet=OTHER if change=='wrong_summon' else PET))
    assert rows==[None,None]


def test_empty_request_reads_native_pet_info_without_local_spell_fabrication(codec):
    rows=run(codec,[action('pet_request','CMSG_REQUEST_PET_INFO'),
        action('pet_request','CMSG_REQUEST_PET_INFO',b'x')])
    assert rows[0]==['CMSG_REQUEST_PET_INFO',''] and 'error' in rows[1]


def test_pet_name_read_is_bound_to_visible_guid_number_and_native_reply(codec):
    query=action('pet_request','CMSG_QUERY_PET_NAME',Writer().guid(*IDENTITY).finish())
    native=struct.pack('<I',1)+b'Pip\0'+struct.pack('<IB',123,1)+b'a\0b\0c\0d\0e\0'
    rows=run(codec,[query,action('pet_response','SMSG_PET_NAME_QUERY_RESPONSE',native),
        action('pet_response','SMSG_PET_NAME_QUERY_RESPONSE',native)])
    assert rows[0]==['CMSG_PET_NAME_QUERY',struct.pack('<IQ',1,PET).hex()]
    r=Reader(bytes.fromhex(rows[1][1]));assert list(r.guid())==IDENTITY
    assert r.bits(1)==1 and r.bits(8)==3 and r.bits(1)==1
    assert [r.bits(7) for _ in range(5)]==[1]*5
    assert bytes(r.raw(5))==b'abcde' and r.unpack('I')==(123,) and bytes(r.raw(3))==b'Pip';r.end()
    assert rows[2] is None


@pytest.mark.parametrize('change',['unseen','forged','no_number','extra'])
def test_pet_name_query_rejects_unattributable_identity(codec,change):
    identity=[*IDENTITY]
    if change=='forged':identity[1]^=1<<29
    body=Writer().guid(*identity).finish()+(b'x' if change=='extra' else b'')
    rows=run(codec,[action('pet_request','CMSG_QUERY_PET_NAME',body)],
        units=[] if change=='unseen' else [unit(number=0 if change=='no_number' else 1)])
    assert 'error' in rows[0]


def test_readonly_name_query_can_reach_another_visible_pet(codec):
    rows=run(codec,[action('pet_request','CMSG_QUERY_PET_NAME',Writer().guid(*IDENTITY).finish())],units=[unit(owner=5)])
    assert rows[0][0]=='CMSG_PET_NAME_QUERY'


def test_removed_pet_has_no_name_response_or_future_query_authority(codec):
    query=action('pet_request','CMSG_QUERY_PET_NAME',Writer().guid(*IDENTITY).finish())
    native=struct.pack('<I',1)+b'Pip\0'+struct.pack('<IB',123,0)
    rows=run(codec,[query,action('destroy_object','SMSG_DESTROY_OBJECT',struct.pack('<QB',PET,0)),
        action('pet_response','SMSG_PET_NAME_QUERY_RESPONSE',native),query])
    assert rows[0][0]=='CMSG_PET_NAME_QUERY' and rows[1][0]=='SMSG_UPDATE_OBJECT'
    assert rows[2] is None and 'not visible' in rows[3]['error']


def test_logout_revokes_pending_catalog_name_and_read_authority(codec):
    rows=run(codec,[action('pet_response','SMSG_PET_SPELLS',spells()),
        action('logout_complete',''),action('pet_ready',''),action('pet_request','CMSG_REQUEST_PET_INFO')],units=[])
    assert rows[:3]==[None,None,None] and 'without owned character' in rows[3]['error']


@pytest.mark.parametrize('body',[b'',b'123',spells()[:-1],spells()+b'x',struct.pack('<Q',0)+b'x'])
def test_pet_spell_response_rejects_truncation_and_trailing_bytes(codec,body):
    assert 'error' in run(codec,[action('pet_response','SMSG_PET_SPELLS',body)])[0]

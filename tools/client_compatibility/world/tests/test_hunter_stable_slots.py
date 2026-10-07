"""Native Handler/PetSlotUpdated and pinned 4.4.2 request/result contract."""
from copy import deepcopy
import struct
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,action
from tools.client_compatibility.world.tests.test_hunter_stable_protocol import (
    MASTER,OWNER,SNAPSHOT,UNIT,MODEL,catalog,reply,owned,decode_update)


def request(number=4,slot=5,master=MASTER,body=None):
    return action('stable_slot_request','CMSG_SET_PET_SLOT',
        Writer().pack('IB',number,slot).guid(*modern_guid(master,0)).finish() if body is None else body)


def update(number=4,slot=5,swap=0,old=0,body=None):
    return action('stable_slot_response','SMSG_PET_SLOT_UPDATED',
        struct.pack('<4I',number,slot,swap,old) if body is None else body)


def outcome(value=8,body=None):
    return action('stable_slot_response','SMSG_STABLE_RESULT',bytes([value]) if body is None else body)


def cache():return action('stable_slot_cache','',b'')


def test_owned_roundtrip_preserves_native_guid_layout_and_only_native_reply_changes_cache(codec):
    rows=owned(codec,[reply(),request(),cache(),update(),outcome(),request(slot=0),update(slot=0,old=5),outcome()])
    # Native NPCHandler::HandleSetPetSlot consumes uint32, uint8, then these
    # exact legacy GUID masks/XOR octets. This literal is independent of Writer.
    # MASTER octets are 77 15 03 00 5d 1a 30 f1, mask7f and XOR
    # order [5,3,1,7,4,0,6,2] yields 1b 14 f0 5c 76 31 02.
    assert rows[1]==['CMSG_SET_PET_SLOT','04000000057f1b14f05c763102']
    assert decode_update(rows[2])[0][0][0]==0
    assert decode_update(rows[3])[0]==[(5,4,42717,2404,10,3,0,'Harnesswolf')]
    assert rows[4]==['SMSG_PET_STABLE_RESULT','08']
    assert decode_update(rows[6])[0]==[(0,4,42717,2404,10,1,0,'Harnesswolf')]
    assert rows[7]==['SMSG_PET_STABLE_RESULT','08']


@pytest.mark.parametrize('bad',[request(number=0),request(number=7),request(slot=21),request(slot=255),
    request(master=MASTER+1),request(body=b''),request(body=bytes(5)),
    request(body=Writer().pack('IB',4,5).guid(*modern_guid(MASTER,1)).finish()),
    request(body=Writer().pack('IB',4,5).guid(*modern_guid(MASTER,0)).finish()+b'x')])
def test_bad_request_leaves_native_owned_catalog_and_next_valid_request_healthy(codec,bad):
    rows=owned(codec,[reply(),bad,cache(),request()]);assert 'error' in rows[1]
    assert rows[0]==rows[2] and rows[3][0]=='CMSG_SET_PET_SLOT'


@pytest.mark.parametrize('fault',['unseen','wrong_map','not_stable','warlock','not_created','no_owner','closed','zero_master'])
def test_slot_mutation_requires_current_hunter_and_open_owned_native_stable(codec,fault):
    unit=deepcopy(UNIT);snapshot=deepcopy(SNAPSHOT);character=deepcopy(OWNER);actions=[reply()]
    if fault=='unseen':unit=None;actions=[]
    elif fault=='wrong_map':unit['map']=1;actions=[]
    elif fault=='not_stable':unit['fields']={};actions=[]
    elif fault=='warlock':snapshot['fields']={};actions=[]
    elif fault=='not_created':snapshot=None
    elif fault=='no_owner':character['guid']=0
    elif fault=='closed':actions.append(action('bank_close','CMSG_CLOSE_INTERACTION',Writer().guid(*modern_guid(MASTER,0)).finish()))
    elif fault=='zero_master':actions=[reply(catalog(guid=0))]
    assert 'error' in owned(codec,actions+[request()],unit,snapshot,character)[-1]


@pytest.mark.parametrize('bad',[update(number=7),update(slot=6),update(swap=9),update(old=1),
    update(body=b''),update(body=struct.pack('<4I',4,5,0,0)[:-1]),
    update(body=struct.pack('<4I',4,5,0,0)+b'x')])
def test_unmatched_or_incomplete_native_slot_reply_cannot_poison_pending_catalog(codec,bad):
    rows=owned(codec,[reply(),request(),bad,cache(),update(),outcome()])
    assert 'error' in rows[2] and rows[0]==rows[3]
    assert decode_update(rows[4])[0][0][0]==5 and rows[5]==['SMSG_PET_STABLE_RESULT','08']


@pytest.mark.parametrize('value',[1,3,11,12])
def test_native_failure_keeps_original_slot_and_releases_only_pending_move(codec,value):
    rows=owned(codec,[reply(),request(),outcome(value),cache(),request()])
    assert rows[2]==['SMSG_PET_STABLE_RESULT',bytes([value]).hex()]
    assert rows[0]==rows[3] and rows[4][0]=='CMSG_SET_PET_SLOT'


@pytest.mark.parametrize('bad',[outcome(0),outcome(10),outcome(body=b''),outcome(body=b'\x08x'),outcome()])
def test_unknown_malformed_or_premature_success_keeps_pending_move(codec,bad):
    rows=owned(codec,[reply(),request(),bad,cache(),update(),outcome()])
    assert 'error' in rows[2] and rows[0]==rows[3] and rows[-1]==['SMSG_PET_STABLE_RESULT','08']


def test_unsolicited_duplicate_and_parallel_requests_are_refused(codec):
    rows=owned(codec,[reply(),update(),outcome(),request(),request(),update(),update(),outcome(),outcome()])
    assert all('error' in rows[i] for i in (1,2,4,6,8))
    assert rows[3][0]=='CMSG_SET_PET_SLOT' and rows[7]==['SMSG_PET_STABLE_RESULT','08']


def test_authoritative_swap_preserves_both_owned_identities_and_models(codec):
    second=catalog(slot=5,number=7,name='Otherwolf')[10:]
    native=bytearray(catalog());native[8]=2;native+=second
    model={**MODEL,'id':7,'modelid':903}
    rows=owned(codec,[reply(bytes(native),[MODEL,model]),request(),update(swap=7),outcome()])
    assert decode_update(rows[2])[0]==[(5,4,42717,2404,10,3,0,'Harnesswolf'),(0,7,42717,903,10,1,0,'Otherwolf')]


def test_close_during_native_move_keeps_cache_result_and_forbids_more_mutation(codec):
    close=action('bank_close','CMSG_CLOSE_INTERACTION',Writer().guid(*modern_guid(MASTER,0)).finish())
    rows=owned(codec,[reply(),request(),close,update(),outcome(),request()])
    assert decode_update(rows[3])[0][0][0]==5 and rows[4]==['SMSG_PET_STABLE_RESULT','08']
    assert 'error' in rows[5]


def test_same_master_catalog_refresh_preserves_pending_move(codec):
    rows=owned(codec,[reply(),request(),reply(),update(),outcome()])
    assert decode_update(rows[3])[0][0][0]==5 and rows[4]==['SMSG_PET_STABLE_RESULT','08']


def test_private_slot_capture_requires_explicit_exact_owner_pet_session_master_and_roundtrip(codec,tmp_path):
    from tools.client_compatibility.world.tests.test_owned_stable_request_probe import config,probe
    c=config();c.update(native_master_guid=MASTER,modern_master_guid=list(modern_guid(MASTER,0)))
    body=bytes.fromhex(request()['body'])
    assert not probe(codec,tmp_path,c,body,name='CMSG_SET_PET_SLOT')
    c['slot_roundtrip']={'pet_number':4,'slots':[0,5]}
    assert probe(codec,tmp_path,c,body,name='CMSG_SET_PET_SLOT')
    assert probe(codec,tmp_path,c,bytes.fromhex('04000000057f1b14f05c763102'),name='CMSG_SET_PET_SLOT',direction='to_native')
    assert probe(codec,tmp_path,c,struct.pack('<4I',4,5,0,0),name='SMSG_PET_SLOT_UPDATED',direction='from_native')
    assert probe(codec,tmp_path,c,b'\x08',name='SMSG_STABLE_RESULT',direction='from_native')
    assert probe(codec,tmp_path,c,b'\x08',name='SMSG_PET_STABLE_RESULT',direction='to_client')
    assert not probe(codec,tmp_path,c,body,name='CMSG_SET_PET_SLOT',session='foreign')
    assert not probe(codec,tmp_path,c,body+b'x',name='CMSG_SET_PET_SLOT')
    assert not probe(codec,tmp_path,c,bytes.fromhex(request(number=7)['body']),name='CMSG_SET_PET_SLOT')
    assert not probe(codec,tmp_path,c,bytes.fromhex(request(slot=6)['body']),name='CMSG_SET_PET_SLOT')
    assert not probe(codec,tmp_path,c,bytes.fromhex(request(master=MASTER+1)['body']),name='CMSG_SET_PET_SLOT')
    assert not probe(codec,tmp_path,c,struct.pack('<4I',4,5,7,0),name='SMSG_PET_SLOT_UPDATED',direction='from_native')
    assert not probe(codec,tmp_path,c,b'\x08x',name='SMSG_STABLE_RESULT',direction='from_native')
    assert not probe(codec,tmp_path,c,b'\x08',name='SMSG_AUTH_RESPONSE',direction='from_native')
    c['slot_roundtrip']['pet_number']=7
    assert not probe(codec,tmp_path,c,body,name='CMSG_SET_PET_SLOT')

"""The new private scope binds only retained Harnesswolf4 and native test Wolf6."""
import struct
import pytest
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_owned_stable_request_probe import config,probe
from tools.client_compatibility.world.tests.test_hunter_stable_protocol import MASTER
from tools.client_compatibility.world.tests.test_hunter_stable_slots import request
from tools.client_compatibility.world.gameobjects import modern_guid


def scoped():
    c=config();c.update(native_master_guid=MASTER,modern_master_guid=list(modern_guid(MASTER,0)),
        slot_swap={'pet_numbers':[4,6],'slots':[0,5]})
    return c


@pytest.mark.parametrize('number,other',[(4,6),(6,4)])
@pytest.mark.parametrize('source,destination',[(0,5),(5,0)])
def test_exact_pair_swap_requests_and_native_updates_are_captured(codec,tmp_path,number,other,source,destination):
    c=scoped();assert probe(codec,tmp_path,c,bytes.fromhex(request(number,destination)['body']),name='CMSG_SET_PET_SLOT')
    assert probe(codec,tmp_path,c,struct.pack('<4I',number,destination,other,source),
        name='SMSG_PET_SLOT_UPDATED',direction='from_native')
    assert probe(codec,tmp_path,c,b'\x08',name='SMSG_STABLE_RESULT',direction='from_native')


@pytest.mark.parametrize('number,destination,other,source',[(4,0,0,5),(6,5,0,0),(4,0,7,5),
    (7,5,4,0),(4,5,6,5),(4,6,6,0)])
def test_other_or_empty_slot_outcomes_do_not_enter_pair_scope(codec,tmp_path,number,destination,other,source):
    assert not probe(codec,tmp_path,scoped(),struct.pack('<4I',number,destination,other,source),
        name='SMSG_PET_SLOT_UPDATED',direction='from_native')


@pytest.mark.parametrize('scope',[{'pet_numbers':[4,7],'slots':[0,5]},
    {'pet_numbers':[6,4],'slots':[0,5]},{'pet_numbers':[4,6],'slots':[0,6]}])
def test_scope_is_an_explicit_exact_pair(codec,tmp_path,scope):
    c=scoped();c['slot_swap']=scope
    assert not probe(codec,tmp_path,c,bytes.fromhex(request()['body']),name='CMSG_SET_PET_SLOT')


def test_foreign_request_ambiguous_scope_and_packet_suffixes_are_excluded(codec,tmp_path):
    c=scoped()
    for body in (bytes.fromhex(request(number=7)['body']),bytes.fromhex(request(slot=6)['body']),
        bytes.fromhex(request(master=MASTER+1)['body']),bytes.fromhex(request()['body'])+b'x'):
        assert not probe(codec,tmp_path,c,body,name='CMSG_SET_PET_SLOT')
    c['slot_roundtrip']={'pet_number':4,'slots':[0,5]}
    assert not probe(codec,tmp_path,c,bytes.fromhex(request()['body']),name='CMSG_SET_PET_SLOT')

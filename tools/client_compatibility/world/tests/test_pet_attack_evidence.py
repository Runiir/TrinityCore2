"""Attack acceptance needs exact native commands and independently delivered combat."""
import copy,json,struct
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility.pet_attack_evidence import request_checks,combat_pairs
from tools.client_compatibility.world import combat,casting
from tools.client_compatibility.world.buffer import Writer

F=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_attack_ui137.json').read_text())
PET=F['native_pet_create'];TARGET=F['native_target_create'];SESSION='owned-test'


def packet(name,body,direction,time=11):
    return {'name':name,'body':body.hex(),'direction':direction,'time':time,'session':SESSION}


def requests():
    return [packet('CMSG_PET_ACTION',bytes.fromhex(F['request']['packet']['body']),'from_client'),
        packet('CMSG_PET_ACTION',struct.pack('<QIQfff',PET['guid'],0x07000002,TARGET['guid'],0,0,0),'to_native',11.1)]


@pytest.mark.parametrize('fault',['none','missing_native','wrong_victim','wrong_pet','extra','late','other_session'])
def test_exact_owned_request_and_native_victim_are_required(fault):
    rows=requests()
    if fault=='missing_native':rows.pop()
    elif fault in ('wrong_victim','wrong_pet'):
        rows[1]['body']=struct.pack('<QIQfff',PET['guid']+(fault=='wrong_pet'),0x07000002,
            TARGET['guid']+(fault=='wrong_victim'),0,0,0).hex()
    elif fault=='extra':rows.append(packet('CMSG_CAST_SPELL',b'','to_native'))
    elif fault=='late':rows[1]['time']=15
    elif fault=='other_session':rows[1]['session']='other'
    checks,_=request_checks(rows,SESSION,10,20,PET,TARGET)
    assert all(checks.values()) is (fault=='none')


@pytest.mark.parametrize('name',['SMSG_ATTACK_START','SMSG_ATTACK_STOP'])
@pytest.mark.parametrize('fault',['none','missing_delivery','wrong_delivery','duplicate_delivery','late_delivery','foreign_pet','foreign_victim','other_session'])
def test_combat_pair_requires_same_pet_victim_and_exact_independent_delivery(name,fault):
    pet=PET['guid']+(fault=='foreign_pet');victim=TARGET['guid']+(fault=='foreign_victim')
    body=struct.pack('<QQ',pet,victim) if name=='SMSG_ATTACK_START' else casting.packed(casting.packed(Writer(),pet),victim).pack('I',0).finish()
    expected=combat.response(SimpleNamespace(character={'map':0}),name,body)[1]
    rows=[packet(name,body,'from_native'),packet(name,expected,'to_client',11.1)]
    if fault=='missing_delivery':rows.pop()
    elif fault=='wrong_delivery':rows[1]['body']+='00'
    elif fault=='duplicate_delivery':rows.append(copy.deepcopy(rows[1]))
    elif fault=='late_delivery':rows[1]['time']=15
    elif fault=='other_session':rows[0]['session']='other'
    pairs=combat_pairs(rows,SESSION,10,20,PET,TARGET,name)
    assert (bool(pairs) and all(p['client'] is not None for p in pairs)) is (fault=='none')

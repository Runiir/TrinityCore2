import copy
import pytest
from tools.client_compatibility.pet_defensive_capture_evidence import button,request_checks
from tools.client_compatibility.world.tests.test_pet_react_evidence import PET,values
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid


@pytest.mark.parametrize('fault',['foreign_owner','foreign_pet','hidden','disabled','wrong_button','duplicate','edge'])
def test_defensive_capture_refuses_unowned_or_unusable_stock_geometry(fault):
    _,sample,_=copy.deepcopy(values());p=sample['probe'];row=p['actions'][1]
    if fault=='foreign_owner':p['owner_guid']='Player-1-00000004'
    elif fault=='foreign_pet':p['pet_guid']+='1'
    elif fault=='hidden':row['frame']['visible']=False
    elif fault=='disabled':row['frame']['enabled']=False
    elif fault=='wrong_button':row['frame']['button']='ActionButton9'
    elif fault=='duplicate':p['actions'].append(copy.deepcopy(row))
    else:row['frame']['x']=65535
    with pytest.raises(RuntimeError):button(p,PET)


@pytest.mark.parametrize('fault',['native_delivery','foreign_guid','assist','target','coords','duplicate','abandon'])
def test_rejected_capture_cannot_claim_native_admission_or_another_request(fault):
    guid=modern_guid(PET['guid']+(fault=='foreign_guid'),0)
    body=Writer().guid(*guid).pack('I',0x03000003 if fault=='assist' else 0x03000001)
    body.guid(*(modern_guid(PET['guid'],0) if fault=='target' else (0,0)))
    packet={'name':'CMSG_PET_ACTION','direction':'from_client','body':body.pack('3f',1 if fault=='coords' else 0,0,0).finish().hex()}
    rows=[packet]
    if fault=='native_delivery':rows.append({**packet,'direction':'to_native'})
    elif fault=='duplicate':rows.append(dict(packet))
    elif fault=='abandon':rows.append({'name':'CMSG_PET_ABANDON','direction':'from_client'})
    checks,_=request_checks(rows,PET);assert not all(checks.values())


def test_readable_owned_button_and_rejected_packet_preserve_identity():
    _,sample,_=values();row,point=button(sample['probe'],PET);assert row['slot']==9 and point==[480,653]
    packet={'name':'CMSG_PET_ACTION','direction':'from_client','body':Writer().guid(*modern_guid(PET['guid'],0))
        .pack('I',0x03000001).guid().pack('3f',0,0,0).finish().hex()}
    checks,decoded=request_checks([packet],PET);assert all(checks.values()) and decoded['action_value']==1

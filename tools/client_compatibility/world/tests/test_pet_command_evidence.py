"""Command forwarding alone cannot pass Stay/Follow behavior challenges."""
import struct
import pytest
from tools.client_compatibility.pet_command_evidence import command_checks,range_state,stay_motion_checks,follow_range_checks
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid

PET={'guid':0xf14001a000000017,'map':0}


def request_rows(command=0):
    body=Writer().guid(*modern_guid(PET['guid'],0)).pack('I',0x03800000|command).guid().pack('3f',0,0,0).finish()
    return [{'name':'CMSG_PET_ACTION','direction':'from_client','body':body.hex(),'time':1},
        {'name':'CMSG_PET_ACTION','direction':'to_native','body':struct.pack('<QIQfff',PET['guid'],0x07000000|command,0,0,0,0).hex(),'time':1.1}]


def ranges(near):return {'interaction_ranges':[{'index':i,'available':True,'in_range':near} for i in (2,3)]}


@pytest.mark.parametrize('command',[0,1])
def test_exact_owned_command_pair(command):assert all(command_checks(request_rows(command),PET,command).values())


@pytest.mark.parametrize('fault',['missing_native','wrong_command','wrong_guid','duplicate','late','abandon'])
def test_command_pair_rejects_missing_changed_duplicate_and_late_evidence(fault):
    rows=request_rows()
    if fault=='missing_native':rows.pop()
    elif fault=='wrong_command':rows[1]['body']=request_rows(1)[1]['body']
    elif fault=='wrong_guid':rows[1]['body']=struct.pack('<QIQfff',PET['guid']+1,0x07000000,0,0,0,0).hex()
    elif fault=='duplicate':rows.append(dict(rows[1]))
    elif fault=='late':rows[1]['time']=4
    else:rows.append({'name':'CMSG_PET_ABANDON','direction':'to_native'})
    assert not all(command_checks(rows,PET,0).values())


@pytest.mark.parametrize('fault',['unavailable','missing','duplicate','wrong_range'])
def test_missing_or_ambiguous_public_range_cannot_establish_separation(fault):
    probe=ranges(False)
    if fault=='unavailable':probe['interaction_ranges'][0]['available']=False
    elif fault=='missing':probe['interaction_ranges'].pop()
    elif fault=='duplicate':probe['interaction_ranges'].append(dict(probe['interaction_ranges'][0]))
    else:probe['interaction_ranges'][0]['in_range']=True
    assert not range_state(probe,False)


def path():return {'unsupported':False,'client':{'time':1},'endpoint':[13,0,50],
    'spline':{'face':0,'duration':1000,'position':[0,0,50]}}


def test_stay_requires_real_owner_separation_range_change_and_no_pet_follow_path():
    assert all(stay_motion_checks([],ranges(True),ranges(False),[0,0,50],[14,0,50]).values())
    assert not all(stay_motion_checks([],ranges(True),ranges(True),[0,0,50],[14,0,50]).values())
    assert not all(stay_motion_checks([],ranges(True),ranges(False),[0,0,50],[0,0,50]).values())
    assert not all(stay_motion_checks([path()],ranges(True),ranges(False),[0,0,50],[14,0,50]).values())


@pytest.mark.parametrize('fault',['none','missing_path','missing_delivery','unsupported','far_endpoint','no_range_change'])
def test_follow_requires_delivered_native_path_to_owner_and_public_return(fault):
    pairs=[path()];far,near=ranges(False),ranges(True)
    if fault=='missing_path':pairs=[]
    elif fault=='missing_delivery':pairs[0]['client']=None
    elif fault=='unsupported':pairs[0]['unsupported']=True
    elif fault=='far_endpoint':pairs[0]['endpoint']=[50,0,50]
    elif fault=='no_range_change':near=ranges(False)
    assert all(follow_range_checks(pairs,far,near,[14,0,50]).values())==(fault=='none')

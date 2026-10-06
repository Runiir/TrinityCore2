"""A command, local highlight, stale path or undelivered path cannot prove Move To."""
import copy,json,struct
from pathlib import Path
import pytest
from tools.client_compatibility.pet_moveto_evidence import request_checks,motion_checks
from tools.client_compatibility.world.buffer import Writer

F=json.loads((Path(__file__).parent/'fixtures/native_owned_pet_moveto_ui135.json').read_text())
PET=F['native_pet_create'];D=F['request']['decoded']


def rows():
    return [{'session':'owned','time':10,'name':'CMSG_PET_ACTION','direction':'from_client',
        'body':F['request']['packet']['body']},
        {'session':'owned','time':10.1,'name':'CMSG_PET_ACTION','direction':'to_native',
        'body':struct.pack('<QIQfff',PET['guid'],0x07000004,0,*D['position']).hex()}]


def test_actual_owned_ground_request_requires_the_exact_native_guid_target_and_destination():
    checks,requests=request_checks(rows(),'owned',9,11,PET)
    assert all(checks.values()) and requests['decoded']==D


@pytest.mark.parametrize('fault',['foreign_modern','foreign_native','stale','late','missing_native','duplicate_modern',
    'duplicate_native','wrong_pet','native_target','native_destination','native_word','abandon','owner_cast',
    'truncated','trailing','zero_destination','nan_destination','outside_destination','modern_target','modern_word'])
def test_uncaptured_wrong_stale_or_extra_commands_cannot_qualify_move_to(fault):
    packets=rows();pet=copy.deepcopy(PET)
    if fault=='foreign_modern':packets[0]['session']='foreign'
    elif fault=='foreign_native':packets[1]['session']='foreign'
    elif fault=='stale':packets[0]['time']=8
    elif fault=='late':packets[1]['time']=12.1
    elif fault=='missing_native':packets.pop()
    elif fault=='duplicate_modern':packets.append(copy.deepcopy(packets[0]))
    elif fault=='duplicate_native':packets.append(copy.deepcopy(packets[1]))
    elif fault=='wrong_pet':pet['guid']+=1
    elif fault in ('abandon','owner_cast'):
        packets.append(dict(packets[0],name='CMSG_PET_ABANDON' if fault=='abandon' else 'CMSG_CAST_SPELL'))
    elif fault.startswith('native_'):
        values=[PET['guid'],0x07000004,0,*D['position']]
        values[{'native_target':2,'native_destination':3,'native_word':1}[fault]]+=1
        packets[1]['body']=struct.pack('<QIQfff',*values).hex()
    elif fault=='truncated':packets[0]['body']=packets[0]['body'][:-2]
    elif fault=='trailing':packets[0]['body']+='00'
    else:
        position=list(D['position']);target=(0,0);word=D['word']
        if fault=='zero_destination':position=[0,0,0]
        elif fault=='nan_destination':position[0]=float('nan')
        elif fault=='outside_destination':position[0]=17068
        elif fault=='modern_target':target=D['guid']
        else:word=0x03800001
        packets[0]['body']=Writer().guid(*D['guid']).pack('I',word).guid(*target).pack('3f',*position).finish().hex()
    checks,_=request_checks(packets,'owned',9,13,pet)
    assert not all(checks.values())


def paths():
    return [{'native':{'time':10.2},'client':{'time':10.3},'unsupported':False,
        'spline':{'face':0,'duration':700,'position':[D['position'][0]-4,*D['position'][1:]]},
        'endpoint':list(D['position'])}]


def test_delivered_owned_path_after_native_command_must_end_at_the_submitted_destination():
    _,requests=request_checks(rows(),'owned',9,11,PET)
    assert all(motion_checks(paths(),requests).values())


@pytest.mark.parametrize('fault',['no_path','stale_path','different_destination','missing_delivery','unsupported',
    'stationary','instant','duplicate_path','missing_request','missing_native'])
def test_missing_stale_wrong_undelivered_or_stationary_motion_cannot_qualify(fault):
    _,requests=request_checks(rows(),'owned',9,11,PET);pairs=paths()
    if fault=='no_path':pairs=[]
    elif fault=='stale_path':pairs[0]['native']['time']=10
    elif fault=='different_destination':pairs[0]['endpoint'][0]+=1
    elif fault=='missing_delivery':pairs[0]['client']=None
    elif fault=='unsupported':pairs[0]['unsupported']=True;pairs[0]['spline']=None
    elif fault=='stationary':pairs[0]['spline']['position']=list(pairs[0]['endpoint'])
    elif fault=='instant':pairs[0]['spline']['duration']=0
    elif fault=='duplicate_path':pairs.append(copy.deepcopy(pairs[0]))
    elif fault=='missing_request':requests['decoded']=None
    else:requests['native']=[]
    assert not all(motion_checks(pairs,requests).values())

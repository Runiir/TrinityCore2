"""Never retire a client when native login, saved changes or another lifetime intervened."""
from copy import deepcopy
import pytest
from tools.client_compatibility.reentry_no_login_boundary import validate


def data():
    runtime={'client':3,'worldserver':1,'modern_world':2};prep={'sha256':'prep'};ref={'sha256':'stage'}
    current={str(i):{'native':{'online':0},'pets':[]} for i in range(1,7)}
    stage={'completed':True,'failure':None,'phase':'await_owned_reentry_review','finished_at':1,
        'checks':dict.fromkeys(range(14),True),'runtime':runtime,'fixture_source':prep,'actor':{'guid':2},
        'model':None,'custom_script_permission':'blocked_by_user','all_offline_snapshot':current}
    c={'schema':'client442_owned_entry_request_probe_v1','owner':6,'account_id':2,'session':'owned',
        'runtime':runtime,'created_at':2,'expires_at':122}
    f={'completed':False,'failure':'RuntimeError: UI state observation deadline exceeded','started_at':2,
        'finished_at':130,'runtime':runtime,'source':ref,'fixture_source':prep,'input_sent':True,
        'capture_disarmed':True,'qualification_added':False,'model':None,'custom_script_permission':'blocked_by_user',
        'ordinary_input':{'kind':'reviewed_lobby_click','point':[640,660]},'native_login_requests':[],
        'actor':{'guid':6,'account_id':2,'class':3,'level':10},'capture_config':c,'capture_packets':[
            {'session':'owned','direction':'from_client','name':'CMSG_GET_ACCOUNT_CHARACTER_LIST',
                'body':'0000000000','time':5}]}
    return deepcopy((stage,f,current,runtime,ref,prep))


def test_only_the_closed_offline_no_login_attempt_is_eligible():validate(*data())


@pytest.mark.parametrize('fault',['successful','open','wrong_failure','native_login','armed','input',
    'source','preparation','runtime','stage_checks','stage_script','model','script','actor','lease',
    'session','packet_secret','packet_width','packet_time','saved_change','online','order'])
def test_unclosed_changed_or_unbound_attempt_cannot_retire_the_scout(fault):
    p,f,current,r,ref,prep=data()
    if fault=='successful':f['completed']=True
    elif fault=='open':f['finished_at']=None
    elif fault=='wrong_failure':f['failure']='other'
    elif fault=='native_login':f['native_login_requests']=[{'name':'CMSG_PLAYER_LOGIN'}]
    elif fault=='armed':f['capture_disarmed']=False
    elif fault=='input':f['input_sent']=False
    elif fault=='source':f['source']={}
    elif fault=='preparation':f['fixture_source']={}
    elif fault=='runtime':f['runtime']={'client':99}
    elif fault=='stage_checks':p['checks'].pop(0)
    elif fault=='stage_script':p['custom_script_permission']='enabled'
    elif fault=='model':f['model']='retired'
    elif fault=='script':f['custom_script_permission']='enabled'
    elif fault=='actor':f['actor']['guid']=1
    elif fault=='lease':f['capture_config']['expires_at']=123
    elif fault=='session':f['capture_packets'][0]['session']='foreign'
    elif fault=='packet_secret':f['capture_packets'][0]['name']='CMSG_AUTH_SESSION'
    elif fault=='packet_width':f['capture_packets'][0]['body']='00'
    elif fault=='packet_time':f['capture_packets'][0]['time']=123
    elif fault=='saved_change':current={**current,'6':{'native':{'online':0},'pets':[{'id':4}]}}
    elif fault=='online':current={**current,'6':{'native':{'online':1},'pets':[]}}
    else:f['started_at']=0
    with pytest.raises(RuntimeError):validate(p,f,current,r,ref,prep)

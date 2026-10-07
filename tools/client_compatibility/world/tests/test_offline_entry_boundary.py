"""Stopping a failed re-entry requires six unchanged offline actors and no login."""
from copy import deepcopy
import pytest
from tools.client_compatibility.offline_entry_boundary import validate


def data():
    runtime={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    origin={'guid':2};fixture={'guid':6};ref={'path':'prepare/episode.json','sha256':'prepared'}
    current={str(i):{'native':{'online':0},'saved':{'health':100},'pets':[]} for i in range(1,7)}
    boundary={'completed':True,'failure':None,'phase':'owned_abandon_parked_boundary',
        'checks':dict.fromkeys(range(19),True),'runtime':runtime,'actor':origin,'finished_at':1,
        'all_offline_snapshot':current}
    preparation={'completed':True,'origin_actor':origin,'class_actor':fixture,'runtime':runtime,
        'phase':'await_owned_class_lobby_review','started_at':2,'finished_at':3}
    failed={'completed':False,'actor':fixture,'runtime':runtime,'fixture_source':ref,
        'phase':'owned_class_entry_started','failure':'RuntimeError: UI observation did not become decodable',
        'started_at':4,'finished_at':5}
    events=[{'name':'CMSG_LOADING_SCREEN_NOTIFY','direction':'from_client'},
        {'event':'unmapped_client_packet','name':'CMSG_GET_ACCOUNT_CHARACTER_LIST'}]
    return boundary,preparation,failed,runtime,current,events,ref,fixture


def test_closed_no_login_failure_allows_only_unchanged_offline_cleanup():validate(*data())


@pytest.mark.parametrize('fault',['open','successful','wrong_failure','login','created','online','saved','pet',
    'missing_actor','bad_boundary','bad_check','wrong_runtime','wrong_actor','wrong_preparation','order',
    'no_loading','no_account_request'])
def test_online_changed_unbound_or_unobserved_entry_cannot_stop(fault):
    b,p,f,r,c,e,ref,fixture=deepcopy(data())
    if fault=='open':f['finished_at']=None
    elif fault=='successful':f['completed']=True
    elif fault=='wrong_failure':f['failure']='other'
    elif fault=='login':e.append({'name':'CMSG_PLAYER_LOGIN'})
    elif fault=='created':e.append({'event':'native_player_created'})
    elif fault=='online':c['6']['native']['online']=1
    elif fault=='saved':c={**c,'6':{**c['6'],'saved':{'health':1}}}
    elif fault=='pet':c={**c,'6':{**c['6'],'pets':[{'id':9}]}}
    elif fault=='missing_actor':c={k:v for k,v in c.items() if k!='6'}
    elif fault=='bad_boundary':b['phase']='other'
    elif fault=='bad_check':b['checks'][0]=False
    elif fault=='wrong_runtime':f['runtime']={}
    elif fault=='wrong_actor':f['actor']={'guid':1}
    elif fault=='wrong_preparation':f['fixture_source']={}
    elif fault=='order':f['started_at']=2
    elif fault=='no_loading':e.pop(0)
    else:e.pop(1)
    with pytest.raises((RuntimeError,TypeError)):validate(b,p,f,r,c,e,ref,fixture)

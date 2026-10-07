"""A later closure must carry the exact offline replacement and restoration."""
from copy import deepcopy
import pytest
from tools.client_compatibility.scout_relaunch_lineage import transition,RELAUNCH_SCHEMA,SINGLE_SCHEMA


def data():
    runtime={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':4}}
    before={**runtime,'client':{'pid':3}};origin={'guid':2}
    baseline={str(i):{'native':{'online':0},'saved':{'health':100}} for i in range(1,7)}
    refs={'deployment':{'path':'deployment.json','sha256':'deployment'},
        'restoration':{'path':'restore/episode.json','sha256':'restored'}}
    primary={'path':'primary/episode.json','sha256':'primary'}
    d={'schema':SINGLE_SCHEMA,'native':runtime['worldserver'],'after':runtime['modern_world'],
        'scout_lifetime':before['client'],'offline_baselines':baseline,'primary_stop_source':primary,'finished_at':1}
    r={'schema':RELAUNCH_SCHEMA,'completed':True,'installed':True,'finished_at':5,'started_at':2,
        'checks':dict.fromkeys(range(9),True),'before_runtime':before,'after_runtime':runtime,
        'offline_baselines':baseline,'origin_actor':origin,'input_sent':False,
        'deployment_source':refs['deployment'],'primary_stop_source':primary,'restoration_source':refs['restoration']}
    restored={'completed':True,'failure':None,'phase':'owned_no_login_scout_restored','actor':origin,
        'runtime':runtime,'input_sent':False,'session':'fresh','restoration_checks':dict.fromkeys(range(7),True),
        'started_at':3,'finished_at':4}
    return r,runtime,d,restored,refs


def test_proven_offline_replacement_keeps_native_and_bridge_lifetimes():
    before=transition(*data());assert before['client']=={'pid':3}


@pytest.mark.parametrize('fault',['open','uninstalled','check_count','failed_check','old_native','old_bridge',
    'same_client','current_client','deployment_client','deployment_native','deployment_bridge','deployment_ref',
    'primary_ref','restore_ref','missing_actor','online_actor','changed_saved','restore_failed','restore_open',
    'restore_check_count','restore_check_failed','restore_runtime','restore_actor','restore_phase','no_session',
    'input','restore_input','order','schema','other_deployment'])
def test_unbound_or_partial_replacement_cannot_close_later_gameplay(fault):
    r,runtime,d,s,refs=deepcopy(data())
    if fault=='open':r['finished_at']=None
    elif fault=='uninstalled':r['installed']=False
    elif fault=='check_count':r['checks'].pop(0)
    elif fault=='failed_check':r['checks'][0]=False
    elif fault=='old_native':r['before_runtime']['worldserver']={'pid':99}
    elif fault=='old_bridge':r['before_runtime']['modern_world']={'pid':99}
    elif fault=='same_client':r['before_runtime']['client']=runtime['client']
    elif fault=='current_client':runtime={**runtime,'client':{'pid':99}}
    elif fault=='deployment_client':d['scout_lifetime']={'pid':99}
    elif fault=='deployment_native':d['native']={'pid':99}
    elif fault=='deployment_bridge':d['after']={'pid':99}
    elif fault=='deployment_ref':r['deployment_source']={}
    elif fault=='primary_ref':r['primary_stop_source']={}
    elif fault=='restore_ref':r['restoration_source']={}
    elif fault=='missing_actor':r['offline_baselines']={k:v for k,v in r['offline_baselines'].items() if k!='6'}
    elif fault=='online_actor':r['offline_baselines']['6']['native']['online']=1
    elif fault=='changed_saved':r['offline_baselines']={}
    elif fault=='restore_failed':s['completed']=False
    elif fault=='restore_open':s['finished_at']=None
    elif fault=='restore_check_count':s['restoration_checks'].pop(0)
    elif fault=='restore_check_failed':s['restoration_checks'][0]=False
    elif fault=='restore_runtime':s['runtime']={}
    elif fault=='restore_actor':s['actor']={'guid':6}
    elif fault=='restore_phase':s['phase']='other'
    elif fault=='no_session':s['session']=''
    elif fault=='input':r['input_sent']=True
    elif fault=='restore_input':s['input_sent']=True
    elif fault=='order':s['started_at']=1
    elif fault=='schema':r['schema']='other'
    else:d['schema']='client442_bridge_deployment_v1'
    with pytest.raises((RuntimeError,TypeError)):transition(r,runtime,d,s,refs)

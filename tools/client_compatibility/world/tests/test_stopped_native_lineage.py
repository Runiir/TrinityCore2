"""Only a fully preserved native replacement may authorize the new scout lifetime."""
from copy import deepcopy
import pytest
from tools.client_compatibility.stopped_native_lineage import transition,SCHEMA


def data():
    before={'worldserver':{'pid':1},'modern_world':{'pid':2,'build':{}},'client':{'pid':3}}
    runtime={**before,'worldserver':{'pid':4},'client':{'pid':5}}
    base={str(i):{'native':{'online':0},'pets':[]} for i in range(1,7)}
    refs={'pause':{'path':'pause','sha256':'p'},'restoration':{'path':'restore','sha256':'r'}}
    pause={'completed':True,'failure':None,'phase':'parked_scout_resource_paused','runtime':before,
        'checks':dict.fromkeys(range(8),True),'before':base,'after':base,'actor':{'guid':2},
        'primary_stop_source':{'sha256':'primary'},'finished_at':2}
    restored={'completed':True,'failure':None,'phase':'single_scout_parked_reconnected','runtime':runtime,
        'actor':pause['actor'],'all_offline_snapshot':base,'restoration_checks':dict.fromkeys(range(7),True),
        'session':'owned','started_at':5,'finished_at':6}
    d={'schema':SCHEMA,'completed':True,'installed':True,'failure':None,'native_restarted':True,
        'bridge_unchanged':True,'primary_stopped':True,'parked_scout':True,'input_sent':False,
        'installation_checks':dict.fromkeys(range(9),True),'source':refs['pause'],'native_before':before['worldserver'],
        'native':runtime['worldserver'],'before':before['modern_world'],'after':before['modern_world'],'build':{},
        'previous_scout':before['client'],'scout_lifetime':runtime['client'],'offline_baselines':base,
        'primary_stop_source':pause['primary_stop_source'],'origin_actor':pause['actor'],
        'staged_at':3,'started_at':4,'finished_at':7,'parked_reconnect_attempt':{'scout':{
            'completed':True,'failure':None,'episode':'restore','sha256':'r','session':'owned'}}}
    return deepcopy((d,runtime,pause,restored,refs))


def test_complete_stopped_native_transition_preserves_bridge_and_saved_state():
    d,r,p,s,refs=data();assert transition(d,r,p,s,refs)==p['runtime']


@pytest.mark.parametrize('fault',['failed','unfinished','not_installed','not_restarted','primary','input','check',
    'source','old_native','wrong_native','same_native','changed_bridge','old_scout','wrong_scout','saved',
    'online','pause_check','pause_saved','primary_source','foreign_actor','restore_failed','restore_runtime',
    'restore_saved','restore_check','order','two_clients','restore_digest','session'])
def test_unbound_changed_or_unfinished_native_transition_is_refused(fault):
    d,r,p,s,refs=data()
    if fault=='failed':d['failure']='failed'
    elif fault=='unfinished':d['finished_at']=None
    elif fault=='not_installed':d['installed']=False
    elif fault=='not_restarted':d['native_restarted']=False
    elif fault=='primary':d['primary_stopped']=False
    elif fault=='input':d['input_sent']=True
    elif fault=='check':d['installation_checks'][0]=False
    elif fault=='source':d['source']={}
    elif fault=='old_native':d['native_before']={'pid':99}
    elif fault=='wrong_native':d['native']={'pid':99}
    elif fault=='same_native':d['native']=p['runtime']['worldserver'];r['worldserver']=d['native']
    elif fault=='changed_bridge':d['after']={'pid':99}
    elif fault=='old_scout':d['scout_lifetime']=d['previous_scout'];r['client']=d['previous_scout']
    elif fault=='wrong_scout':d['scout_lifetime']={'pid':99}
    elif fault=='saved':d['offline_baselines']={}
    elif fault=='online':p['after']['1']['native']['online']=1
    elif fault=='pause_check':p['checks'][0]=False
    elif fault=='pause_saved':p['before']={}
    elif fault=='primary_source':d['primary_stop_source']={}
    elif fault=='foreign_actor':s['actor']={'guid':6}
    elif fault=='restore_failed':s['completed']=False
    elif fault=='restore_runtime':s['runtime']={}
    elif fault=='restore_saved':s['all_offline_snapshot']={}
    elif fault=='restore_check':s['restoration_checks'][0]=False
    elif fault=='order':d['started_at']=1
    elif fault=='two_clients':d['parked_reconnect_attempt']['primary']={}
    elif fault=='restore_digest':d['parked_reconnect_attempt']['scout']['sha256']='other'
    else:s['session']=''
    with pytest.raises(RuntimeError):transition(d,r,p,s,refs)

"""Every bridge replacement must retain its actual pause, never the first bridge."""
from copy import deepcopy
import pytest
from tools.client_compatibility.scout_pause_lineage import transition,SCHEMA


def data():
    native={'pid':1};before={'pid':2};build={'source':'candidate'};after={'pid':5,'build':build}
    old={'pid':3};new={'pid':4};origin={'guid':2};runtime={'worldserver':native,'modern_world':after,'client':new}
    baseline={str(i):{'native':{'online':0},'saved':{'health':100}} for i in range(1,7)}
    refs={'pause':{'path':'pause/episode.json','sha256':'paused'},'restoration':{'path':'restore/episode.json','sha256':'restored'}}
    primary={'path':'primary/episode.json','sha256':'primary'}
    pause={'completed':True,'phase':'parked_scout_resource_paused','checks':dict.fromkeys(range(8),True),
        'before':baseline,'after':baseline,'actor':origin,'primary_stop_source':primary,'finished_at':1,
        'runtime':{'worldserver':native,'modern_world':before,'client':old}}
    attempt={'scout':{'completed':True,'failure':None,'episode':refs['restoration']['path'],
        'sha256':refs['restoration']['sha256'],'session':'fresh'}}
    report={'schema':SCHEMA,'completed':True,'installed':True,'native_unchanged':True,'primary_stopped':True,
        'parked_scout':True,'installation_checks':dict.fromkeys(range(4),True),'source':refs['pause'],
        'primary_stop_source':primary,'offline_baselines':baseline,'origin_actor':origin,'native':native,
        'before':before,'after':after,'build':build,'previous_scout':old,'scout_lifetime':new,
        'parked_reconnect_attempt':attempt,'started_at':2,'finished_at':7}
    restored={'completed':True,'phase':'single_scout_parked_reconnected','runtime':runtime,'actor':origin,
        'all_offline_snapshot':baseline,'session':'fresh','restoration_checks':dict.fromkeys(range(7),True),
        'started_at':4,'finished_at':6}
    return report,runtime,pause,restored,refs


def test_second_bridge_replacement_uses_its_actual_closed_pause():
    before=transition(*data());assert before['modern_world']=={'pid':2} and before['client']=={'pid':3}


@pytest.mark.parametrize('fault',['open','installation','pause_count','pause_failed','pause_changed','saved',
    'online','missing_actor','native','bridge','old_bridge','same_bridge','build','old_client','new_client',
    'same_client','pause_ref','primary_ref','fake_primary','restore_ref','restore_count','restore_failed',
    'restore_runtime','restore_session','restore_snapshot','order'])
def test_partial_unbound_or_invented_replacement_is_refused(fault):
    d,r,p,s,refs=deepcopy(data())
    if fault=='open':d['finished_at']=None
    elif fault=='installation':d['installation_checks'][0]=False
    elif fault=='pause_count':p['checks'].pop(0)
    elif fault=='pause_failed':p['completed']=False
    elif fault=='pause_changed':p['before']={}
    elif fault=='saved':d['offline_baselines']={}
    elif fault=='online':p['after']['6']['native']['online']=1
    elif fault=='missing_actor':p['after']={k:v for k,v in p['after'].items() if k!='6'}
    elif fault=='native':r={**r,'worldserver':{'pid':99}}
    elif fault=='bridge':r={**r,'modern_world':{'pid':99}}
    elif fault=='old_bridge':d['before']={'pid':99}
    elif fault=='same_bridge':d['before']=d['after']
    elif fault=='build':d['build']={}
    elif fault=='old_client':d['previous_scout']={'pid':99}
    elif fault=='new_client':d['scout_lifetime']={'pid':99}
    elif fault=='same_client':d['previous_scout']=d['scout_lifetime']
    elif fault=='pause_ref':d['source']={}
    elif fault=='primary_ref':d['primary_stop_source']={}
    elif fault=='fake_primary':d['parked_reconnect_attempt']['primary']={'completed':True}
    elif fault=='restore_ref':d['parked_reconnect_attempt']['scout']['sha256']='wrong'
    elif fault=='restore_count':s['restoration_checks'].pop(0)
    elif fault=='restore_failed':s['completed']=False
    elif fault=='restore_runtime':s['runtime']={}
    elif fault=='restore_session':s['session']='wrong'
    elif fault=='restore_snapshot':s['all_offline_snapshot']={}
    else:s['started_at']=1
    with pytest.raises((RuntimeError,TypeError)):transition(d,r,p,s,refs)

"""A resource pause permits exactly one bound scout replacement, preserving all actors."""
import copy
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_resource_paused_class_fixture import continuity
from tools.client_compatibility.interaction_paused_scout_bridge_deploy import SCHEMA


def data():
    origin={'guid':2,'account_id':2}
    hunter={'guid':6,'character_name':'Harnesshunt','race':1,'class':3,'level':10,'account_id':2}
    previous={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    now={**previous,'modern_world':{'pid':4},'client':{'pid':5}}
    old={'phase':'await_owned_class_lobby_review','actor':origin,'origin_actor':origin,
        'class_actor':hunter,'runtime':previous,'finished_at':1,'origin_native':{'offline':True},'origin_saved':{'spells':[1]}}
    park={'actor':hunter,'runtime':previous,'phase':'await_original_selection_review','fixture_source':{'sha256':'source'},
        'checks':dict.fromkeys(range(4),True),'started_at':2,'finished_at':3,
        'retained_class_fixture':{'offline':True},'retained_class_saved':{'spells':[883,1515]},
        'retained_class_pets':[{'id':4,'name':'Harnesswolf'},{'id':6,'name':'Wolf'}]}
    finish={'actor':origin,'runtime':previous,'fixture_source':{'sha256':'source'},
        'checks':dict.fromkeys(range(5),True),'started_at':4,'finished_at':5}
    baseline={'2':{'native':old['origin_native'],'saved':old['origin_saved']},
        '6':{'native':park['retained_class_fixture'],'saved':park['retained_class_saved'],'pets':park['retained_class_pets']}}
    stop={'path':'primary/episode.json','sha256':'stopped'}
    pause={'runtime':previous,'phase':'parked_scout_resource_paused','checks':dict.fromkeys(range(8),True),
        'before':baseline,'after':baseline,'primary_stop_source':stop,'started_at':6}
    deployment={'schema':SCHEMA,'completed':True,'finished_at':8,'native_unchanged':True,
        'primary_stopped':True,'parked_scout':True,'native':previous['worldserver'],'before':previous['modern_world'],
        'after':now['modern_world'],'previous_scout':previous['client'],'scout_lifetime':now['client'],
        'offline_baselines':baseline,'primary_stop_source':stop,'parked_reconnect_attempt':{'scout':{'completed':True}}}
    return SimpleNamespace(fixture=origin,receipt={'runtime':now}),old,park,finish,pause,deployment


def test_resource_pause_binds_new_scout_and_bridge_without_restarting_primary():
    continuity(*data(),'source')


@pytest.mark.parametrize('change',['native','unchanged_scout','wrong_scout','unchanged_bridge','wrong_bridge',
    'unbound_primary','primary_running','fake_two_client_completion','failed_scout','failed_pause','unfinished',
    'wrong_source','wrong_hunter','bad_parking','bad_origin_finish','out_of_order','changed_pet','changed_origin',
    'wrong_pause_baseline','before_bridge','previous_scout','wrong_schema'])
def test_unbound_or_incomplete_resource_pause_is_refused(change):
    t,old,park,finish,pause,d=copy.deepcopy(data())
    if change=='native':t.receipt['runtime']['worldserver']={'pid':99}
    elif change=='unchanged_scout':t.receipt['runtime']['client']=old['runtime']['client']
    elif change=='wrong_scout':d['scout_lifetime']={'pid':99}
    elif change=='unchanged_bridge':t.receipt['runtime']['modern_world']=old['runtime']['modern_world']
    elif change=='wrong_bridge':d['after']={'pid':99}
    elif change=='unbound_primary':d['primary_stop_source']={'path':'other','sha256':'other'}
    elif change=='primary_running':d['primary_stopped']=False
    elif change=='fake_two_client_completion':d['parked_reconnect_attempt']['primary']={'completed':True}
    elif change=='failed_scout':d['parked_reconnect_attempt']['scout']['completed']=False
    elif change=='failed_pause':pause['checks'][0]=False
    elif change=='unfinished':d['completed']=False
    elif change=='wrong_source':park['fixture_source']['sha256']='other'
    elif change=='wrong_hunter':old['class_actor']={**old['class_actor'],'guid':5}
    elif change=='bad_parking':park['checks'][0]=False
    elif change=='bad_origin_finish':finish['checks'].pop(0)
    elif change=='out_of_order':pause['started_at']=4
    elif change=='changed_pet':park['retained_class_pets']=[{'id':4,'name':'Changed'}]
    elif change=='changed_origin':old['origin_saved']={'spells':[]}
    elif change=='wrong_pause_baseline':pause['after']={}
    elif change=='before_bridge':d['before']={'pid':99}
    elif change=='previous_scout':d['previous_scout']={'pid':99}
    else:d['schema']='client442_bridge_deployment_v1'
    with pytest.raises(RuntimeError):continuity(t,old,park,finish,pause,d,'source')

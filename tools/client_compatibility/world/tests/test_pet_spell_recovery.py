"""Closed-failure provenance is required before any ordinary recovery input."""
import copy
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_pet_spell_recovery import eligible,bridge_eligible
from tools.client_compatibility.interaction_owned_class_fixture import SCRIPT_BOUNDARY


def source():
    actor={'guid':5};runtime={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    t=SimpleNamespace(fixture=actor,receipt={'runtime':runtime})
    d={'completed':False,'finished_at':1,
        'execution_failure':'RuntimeError: ordinary pet spell cleanup differs from original state',
        'failure':'RuntimeError: native pet reaction-mode restoration differs','actor':copy.deepcopy(actor),
        'runtime':copy.deepcopy(runtime),'sources':[{'sha256':'a'},{'sha256':'b'}],
        'cases':[{'id':'pets.spell_cast','status':'owned_native_pet_spell_pass',
            'oracle':{'checks':{str(i):True for i in range(22)}}}],
        'custom_script_permission':'blocked_by_user','softTargetInteract':copy.deepcopy(SCRIPT_BOUNDARY),
        'spell_baseline':{'auras':{},'public_buffs':[]},
        'baseline':{'money':9354,'saved':{'spells':[[80388,1,0]]},'pet':{'id':2}}}
    return d,t


def test_exact_closed_restoration_failure_is_eligible_without_qualifying_it():
    d,t=source();assert eligible(d,t,['a','b']) is d


@pytest.mark.parametrize('fault',['completed','unfinished','other_execution_failure','other_failure','actor',
    'runtime','sources','duplicate_cast','cast_failure','missing_check','failed_check','scripts',
    'cvar','native_aura','public_buff','money','parent_spell','pet_number'])
def test_wrong_or_open_failure_provenance_is_rejected(fault):
    d,t=source()
    if fault=='completed':d['completed']=True
    elif fault=='unfinished':d['finished_at']=None
    elif fault=='other_execution_failure':d['execution_failure']='unrelated'
    elif fault=='other_failure':d['failure']='unrelated'
    elif fault=='actor':d['actor']['guid']=4
    elif fault=='runtime':d['runtime']['client']['pid']=4
    elif fault=='sources':d['sources'].reverse()
    elif fault=='duplicate_cast':d['cases'].append(copy.deepcopy(d['cases'][0]))
    elif fault=='cast_failure':d['cases'][0]['status']='client_or_protocol_failure'
    elif fault=='missing_check':d['cases'][0]['oracle']['checks'].pop('0')
    elif fault=='failed_check':d['cases'][0]['oracle']['checks']['0']=False
    elif fault=='scripts':d['custom_script_permission']='enabled'
    elif fault=='cvar':d['softTargetInteract']['original_restored']=True
    elif fault=='native_aura':d['spell_baseline']['auras']={'0':{'spell':6307}}
    elif fault=='public_buff':d['spell_baseline']['public_buffs']=[6307]
    elif fault=='money':d['baseline']['money']=10000
    elif fault=='parent_spell':d['baseline']['saved']['spells']=[]
    else:d['baseline']['pet']['id']=1
    with pytest.raises(RuntimeError):eligible(d,t,['a','b'])


def bridge_source():
    d,t=source();prior=copy.deepcopy(t.receipt['runtime']);t.receipt['runtime']['modern_world']={'pid':9}
    old={'sources':[{'sha256':'x'} for _ in range(4)],'natural_saved':d['baseline']['saved'],
        'natural_native':{'money':9354},'class_actor':d['actor'],'retained_class_pets':[{'id':2}]}
    previous={'runtime':prior,'sources':[{'sha256':'a'},{'sha256':'p'},{'sha256':'f'}]}
    deployment={'completed':True,'finished_at':1,'native_unchanged':True,'parked_scout':True,
        'native':prior['worldserver'],'before':prior['modern_world'],'after':t.receipt['runtime']['modern_world']}
    return d,t,old,previous,deployment


def test_closed_new_bridge_can_restore_original_failure_without_replaying_cast():
    args=bridge_source();assert bridge_eligible(*args,['a','b']) is args[0]


@pytest.mark.parametrize('fault',['previous_runtime','previous_source','empty_previous_sources','current_sources',
    'open_deployment','unfinished_deployment','world_changed','client_changed','same_bridge','foreign_before',
    'foreign_after','not_parked','saved','money','actor','pet'])
def test_new_bridge_recovery_refuses_unbound_or_changed_historical_fixture(fault):
    d,t,old,previous,deployment=bridge_source()
    if fault=='previous_runtime':previous['runtime']['worldserver']={'pid':8}
    elif fault=='previous_source':previous['sources'][0]['sha256']='wrong'
    elif fault=='empty_previous_sources':previous['sources']=[]
    elif fault=='current_sources':old['sources'].pop()
    elif fault=='open_deployment':deployment['completed']=False
    elif fault=='unfinished_deployment':deployment['finished_at']=None
    elif fault=='world_changed':t.receipt['runtime']['worldserver']={'pid':8}
    elif fault=='client_changed':t.receipt['runtime']['client']={'pid':8}
    elif fault=='same_bridge':t.receipt['runtime']['modern_world']=d['runtime']['modern_world']
    elif fault=='foreign_before':deployment['before']={'pid':8}
    elif fault=='foreign_after':deployment['after']={'pid':8}
    elif fault=='not_parked':deployment['parked_scout']=False
    elif fault=='saved':old['natural_saved']={}
    elif fault=='money':old['natural_native']['money']=10000
    elif fault=='actor':old['class_actor']={'guid':4}
    else:old['retained_class_pets'][0]['id']=1
    with pytest.raises(RuntimeError):bridge_eligible(d,t,old,previous,deployment,['a','b'])

"""The separate Hunter fixture cannot authorize another actor or class entry."""
import copy
import pytest
from tools.client_compatibility.interaction_hunter_fixture import created_identity,preparation_contract
from tools.client_compatibility.interaction_owned_class_fixture import entry_identity


def fixture(level=1):
    return {'actor':'scout','guid':6,'account_id':2,'character_name':'Harnesshunt','race':1,'class':3,'level':level}


def test_new_normal_account_hunter_and_exact_prepared_entry():
    assert created_identity(fixture())
    assert entry_identity(fixture(10))
    assert not entry_identity(fixture())


@pytest.mark.parametrize('key,value',[('actor','primary'),('guid',5),('account_id',1),
    ('character_name','Someoneelse'),('race',2),('class',9),('level',85)])
def test_creation_refuses_another_actor_identity_or_level(key,value):
    row=fixture();row[key]=value;assert not created_identity(row)


@pytest.mark.parametrize('key,value',[('actor','primary'),('guid',5),('account_id',1),('character_name','Someoneelse'),
    ('race',2),('class',9),('level',1)])
def test_prepared_hunter_entry_cannot_borrow_warlock_or_other_account_acceptance(key,value):
    row=fixture(10);row[key]=value;assert not entry_identity(row)


def boundaries():
    runtime={'worldserver':1,'modern_world':2,'client':3}
    before={str(g):{'native':{'guid':g,'online':0},'saved':{},'pets':[],'inventory':[]} for g in range(1,6)}
    origin={'actor':{'schema':'client442_actor_v1','actor':'scout','guid':2,'account_id':2,
        'character_name':'Harnesstwo','race':1,'class':1,'level':1},'runtime':runtime,
        'qualified_scope':'Read-only owned offline scout preflight; no gameplay qualification.',
        'parked_native':before['2']['native']}
    park={'actor':{'guid':5},'runtime':runtime,'phase':'await_original_selection_review',
        'checks':{str(i):True for i in range(4)},'retained_class_fixture':before['5']['native'],
        'retained_class_saved':before['5']['saved'],'retained_class_pets':before['5']['pets']}
    primary={'actor':{'guid':1},'runtime':{**runtime,'client':4},'parked_snapshot':before['1']}
    return copy.deepcopy((origin,runtime,park,primary,before))


def test_frozen_original_retained_and_primary_boundaries_admit_only_offline_preparation():
    preparation_contract(*boundaries())


@pytest.mark.parametrize('fault',['origin_actor','origin_native','client_lifetime','park_actor','park_phase',
    'missing_checks','failed_check','retained_saved','retained_pets','primary_actor','primary_world',
    'primary_inventory','active_prior_actor'])
def test_hunter_preparation_refuses_stale_or_changed_protected_sources(fault):
    origin,current,park,primary,before=boundaries()
    if fault=='origin_actor':origin['actor']['guid']=5
    elif fault=='origin_native':origin['parked_native']={'guid':2,'online':1}
    elif fault=='client_lifetime':current['client']=30
    elif fault=='park_actor':park['actor']['guid']=4
    elif fault=='park_phase':park['phase']='active'
    elif fault=='missing_checks':park['checks'].pop('0')
    elif fault=='failed_check':park['checks']['0']=False
    elif fault=='retained_saved':park['retained_class_saved']={'spells':[1515]}
    elif fault=='retained_pets':park['retained_class_pets']=[{'id':99}]
    elif fault=='primary_actor':primary['actor']['guid']=2
    elif fault=='primary_world':primary['runtime']['worldserver']=10
    elif fault=='primary_inventory':primary['parked_snapshot']={**primary['parked_snapshot'],'inventory':[99]}
    else:before['3']['native']['online']=1
    with pytest.raises(RuntimeError):preparation_contract(origin,current,park,primary,before)

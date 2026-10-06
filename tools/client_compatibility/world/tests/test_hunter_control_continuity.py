"""A new bridge cannot borrow an incomplete or foreign paid Hunter purchase."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import pytest
from tools.client_compatibility import interaction_hunter_control_continuity as module
from tools.client_compatibility.interaction_hunter_control_continuity import validate,validate_next


def chain():
    actor={'guid':6,'character_name':'Harnesshunt','class':3,'level':10,'account_id':2,'race':1}
    runtime={'worldserver':{'pid':1},'client':{'pid':2},'modern_world':{'pid':3}}
    current={**deepcopy(runtime),'modern_world':{'pid':4}}
    saved={'spells':[[1515,1,0],[79682,1,0]],'skills':[]}
    keys={'original_character','original_saved_rows','native_worldserver','class_offline',
        'retained_character','retained_saved_rows','retained_pets','origin_registration'}|{
            f'actor_{g}_unchanged' for g in range(1,6)}
    prep={'class_actor':actor,'sources':[{'sha256':'previous'}],'runtime':deepcopy(current),
        'natural_saved':deepcopy(saved),'checks':dict.fromkeys(keys,True)}
    purchase={'actor':deepcopy(actor),'phase':'control_pet_trained','completed':True,'failure':None,
        'finished_at':2,'runtime':deepcopy(runtime),'fixture_source':{'sha256':'previous'},
        'purchase_checks':dict.fromkeys(range(9),True),
        'protected_checks':dict.fromkeys((f'actor_{g}_unchanged' for g in range(1,6)),True)}
    prior={'runtime':deepcopy(runtime)}
    park={'runtime':deepcopy(runtime),'started_at':3,'finished_at':4,'retained_class_saved':deepcopy(saved)}
    finish={'started_at':5}
    deploy={'completed':True,'finished_at':6,'parked_primary':True,'parked_scout':True,
        'before':deepcopy(runtime['modern_world']),'after':deepcopy(current['modern_world']),
        'native':deepcopy(current['worldserver'])}
    return [prep,purchase,prior,park,finish,deploy,current]


def test_paid_control_is_retained_without_a_second_purchase():
    assert validate(*chain()) is None


@pytest.mark.parametrize('fault',('foreign_actor','failed_purchase','partial_purchase','false_purchase',
    'lost_protected_actor','wrong_previous_source','overlapping_park','missing_saved_lesson',
    'changed_saved_rows','unfinished_deployment','online_primary','wrong_before','wrong_after',
    'restarted_world','same_bridge','false_retained_check'))
def test_retained_control_requires_the_entire_owned_deployment_boundary(fault):
    c=chain();prep,purchase,prior,park,finish,deploy,current=c
    if fault=='foreign_actor':purchase['actor']['guid']=5
    elif fault=='failed_purchase':purchase['completed']=False
    elif fault=='partial_purchase':purchase['purchase_checks'].pop(8)
    elif fault=='false_purchase':purchase['purchase_checks'][8]=False
    elif fault=='lost_protected_actor':purchase['protected_checks'].pop('actor_1_unchanged')
    elif fault=='wrong_previous_source':purchase['fixture_source']['sha256']='foreign'
    elif fault=='overlapping_park':park['started_at']=1
    elif fault=='missing_saved_lesson':park['retained_class_saved']['spells'].pop()
    elif fault=='changed_saved_rows':prep['natural_saved']['skills']=[1]
    elif fault=='unfinished_deployment':deploy['completed']=False
    elif fault=='online_primary':deploy['parked_primary']=False
    elif fault=='wrong_before':deploy['before']={'pid':9}
    elif fault=='wrong_after':deploy['after']={'pid':9}
    elif fault=='restarted_world':current['worldserver']={'pid':9}
    elif fault=='same_bridge':current['modern_world']=deepcopy(purchase['runtime']['modern_world'])
    elif fault=='false_retained_check':prep['checks']['actor_1_unchanged']=False
    with pytest.raises(RuntimeError):validate(*c)


def second_chain():
    previous,purchase,first,first_park,first_finish,first_deploy,runtime=chain()
    origin={'guid':2,'account_id':2};fixture=deepcopy(previous['class_actor'])
    previous.update(actor=origin,origin_actor=origin,phase='await_owned_class_lobby_review',
        started_at=6.5,finished_at=7)
    current={**deepcopy(runtime),'modern_world':{'pid':5}}
    prep={'class_actor':fixture,'runtime':deepcopy(current),'started_at':14,
        'sources':[{'sha256':'second'}],'natural_saved':deepcopy(previous['natural_saved']),
        'checks':deepcopy(previous['checks'])}
    park={'actor':fixture,'runtime':deepcopy(runtime),'phase':'await_original_selection_review',
        'fixture_source':{'sha256':'second'},'checks':dict.fromkeys(range(4),True),
        'started_at':8,'finished_at':9,'retained_class_saved':deepcopy(previous['natural_saved'])}
    finish={'actor':origin,'runtime':deepcopy(runtime),'fixture_source':{'sha256':'second'},
        'checks':dict.fromkeys(range(5),True),'started_at':10,'finished_at':11}
    deploy={'completed':True,'started_at':12,'finished_at':13,'parked_primary':True,'parked_scout':True,
        'native_unchanged':True,'before':deepcopy(runtime['modern_world']),'after':deepcopy(current['modern_world']),
        'native':deepcopy(current['worldserver']),
        'reconnected':{'primary':{'completed':True},'scout':{'completed':True,'parked':True}}}
    return [prep,previous,park,finish,deploy,current],[purchase,first,first_park,first_finish,first_deploy]


@pytest.mark.parametrize('fault',('none','lost_paid_lesson','changed_saved_rows','false_retained_check',
    'wrong_old_fixture','foreign_park_source','world_restart','client_restart','online_primary',
    'overlapping_park','overlapping_deployment','stale_preparation'))
def test_every_later_deployment_preserves_the_original_paid_knowledge(fault):
    c,_=second_chain();prep,previous,park,finish,deploy,current=c
    if fault=='lost_paid_lesson':previous['natural_saved']['spells'].pop()
    elif fault=='changed_saved_rows':park['retained_class_saved']['skills']=[1]
    elif fault=='false_retained_check':prep['checks']['actor_1_unchanged']=False
    elif fault=='wrong_old_fixture':previous['class_actor']['guid']=5
    elif fault=='foreign_park_source':park['fixture_source']['sha256']='foreign'
    elif fault=='world_restart':current['worldserver']={'pid':9}
    elif fault=='client_restart':current['client']={'pid':9}
    elif fault=='online_primary':deploy['parked_primary']=False
    elif fault=='overlapping_park':park['started_at']=6
    elif fault=='overlapping_deployment':deploy['started_at']=10
    elif fault=='stale_preparation':prep['started_at']=12
    if fault=='none':assert validate_next(*c) is None
    else:
        with pytest.raises(RuntimeError):validate_next(*c)


def test_two_verified_changes_retain_the_exact_purchase_without_replay(monkeypatch):
    c,root=second_chain();prep,previous,park,finish,deploy,current=c
    purchase,first,first_park,first_finish,first_deploy=root
    previous['sources'].extend([{'sha256':'park_one'},{'sha256':'finish_one'},{'sha256':'deployment_one'}])
    prep['sources'].extend([{'sha256':'park_two'},{'sha256':'finish_two'},{'sha256':'deployment_two'}])
    monkeypatch.setattr(module,'closed',lambda path:purchase)
    monkeypatch.setattr(module.lab,'sha256',lambda path:'purchase_digest')
    monkeypatch.setattr(module,'source_chain',lambda sources:(previous,park,finish,deploy)
        if sources[0]['sha256']=='second' else (first,first_park,first_finish,first_deploy))
    t=SimpleNamespace(receipt={'runtime':current})
    assert module.retained_source(t,prep,Path('episode.json'))==purchase
    proof=t.receipt['retained_paid_control_source']
    assert proof['purchase_replayed'] is False and proof['deployments']==[
        {'sha256':'deployment_one'},{'sha256':'deployment_two'}]

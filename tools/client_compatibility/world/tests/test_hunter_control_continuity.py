"""A new bridge cannot borrow an incomplete or foreign paid Hunter purchase."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_hunter_control_continuity import validate


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

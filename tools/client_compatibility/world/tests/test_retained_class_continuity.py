"""A retained fixture can cross only the verified bridge change, never a new client or server."""
import copy
from types import SimpleNamespace
import pytest
from tools.client_compatibility.interaction_retained_class_fixture import continuity


def data():
    origin={'guid':2,'account_id':2};fixture={'guid':4,'account_id':2}
    previous={'worldserver':{'pid':1},'modern_world':{'pid':2},'client':{'pid':3}}
    current={**previous,'modern_world':{'pid':4}}
    old={'phase':'await_owned_class_lobby_review','origin_actor':origin,'class_actor':fixture,
        'actor':origin,'runtime':previous}
    park={'actor':fixture,'runtime':previous,'phase':'await_original_selection_review',
        'fixture_source':{'sha256':'source'},'checks':dict.fromkeys(range(4),True)}
    finish={'actor':origin,'runtime':previous,'fixture_source':{'sha256':'source'},'checks':dict.fromkeys(range(5),True)}
    deployment={'completed':True,'finished_at':42,'native_unchanged':True,'parked_scout':True,
        'native':previous['worldserver'],'before':previous['modern_world'],'after':current['modern_world'],
        'reconnected':{'primary':{'completed':True},'scout':{'completed':True,'parked':True}}}
    return SimpleNamespace(fixture=origin,receipt={'runtime':current}),old,park,finish,deployment


def test_only_verified_bridge_replacement_preserves_fixture_continuity():
    t,old,park,finish,d=data()
    continuity(t,old,park,finish,d,'source')


@pytest.mark.parametrize('change',['none','name','race','class','level','account','guid'])
def test_eligible_fixture_crosses_only_with_its_exact_identity(change):
    t,old,park,finish,d=data()
    fixture={'guid':5,'account_id':2,'character_name':'Harnessctrl','race':1,'class':9,'level':10}
    if change!='none':
        key={'name':'character_name','account':'account_id'}.get(change,change)
        fixture[key]='Harnessone' if key=='character_name' else 99
    old['class_actor']=fixture;park['actor']=fixture
    if change=='none':continuity(t,old,park,finish,d,'source')
    else:
        with pytest.raises(RuntimeError):continuity(t,old,park,finish,d,'source')


@pytest.mark.parametrize('change',['class_actor','origin_actor','park_actor','park_source','finish_source',
    'park_phase','park_checks','finish_checks','new_native','new_client','before_bridge','after_bridge',
    'unchanged_bridge','unfinished_deployment','failed_primary','scout_world_entry','missing_actor'])
def test_unbound_actor_source_lifetime_or_incomplete_restoration_is_refused(change):
    t,old,park,finish,d=data()
    if change=='class_actor':old['class_actor']={'guid':5,'account_id':2}
    elif change=='origin_actor':old['origin_actor']={'guid':3,'account_id':2}
    elif change=='park_actor':park['actor']={'guid':5,'account_id':2}
    elif change=='park_source':park['fixture_source']['sha256']='other'
    elif change=='finish_source':finish['fixture_source']['sha256']='other'
    elif change=='park_phase':park['phase']='unfinished'
    elif change=='park_checks':park['checks'][0]=False
    elif change=='finish_checks':finish['checks'].pop(0)
    elif change=='new_native':t.receipt['runtime']['worldserver']={'pid':5}
    elif change=='new_client':t.receipt['runtime']['client']={'pid':5}
    elif change=='before_bridge':d['before']={'pid':5}
    elif change=='after_bridge':d['after']={'pid':5}
    elif change=='unchanged_bridge':t.receipt['runtime']['modern_world']=copy.deepcopy(old['runtime']['modern_world'])
    elif change=='unfinished_deployment':d.pop('finished_at')
    elif change=='failed_primary':d['reconnected']['primary']['completed']=False
    elif change=='scout_world_entry':d['reconnected']['scout']['parked']=False
    else:d['reconnected'].pop('primary')
    with pytest.raises(RuntimeError):continuity(t,old,park,finish,d,'source')

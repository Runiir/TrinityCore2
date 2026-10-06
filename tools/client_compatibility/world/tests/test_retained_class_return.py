"""A new trial must retain the exact closed actor, runtime and restoration chain."""
import copy
import pytest
from tools.client_compatibility.interaction_retained_class_return import continuity


def sources():
    origin={'guid':2};trained={'guid':5,'account_id':2,'character_name':'Harnessctrl','race':1,'class':9,'level':10}
    runtime={'worldserver':1,'modern_world':2,'client':3}
    old={'actor':origin,'origin_actor':origin,'class_actor':trained,'runtime':runtime,'phase':'await_owned_class_lobby_review'}
    park={'actor':trained,'runtime':runtime,'phase':'await_original_selection_review','fixture_source':{'sha256':'abc'},
        'checks':{str(i):True for i in range(4)},'retained_class_fixture':{'online':0}}
    finish={'actor':origin,'runtime':runtime,'fixture_source':{'sha256':'abc'},'checks':{str(i):True for i in range(5)}}
    return runtime,origin,old,park,finish


def test_exact_closed_same_runtime_chain():continuity(*sources(),'abc')


@pytest.mark.parametrize('fault',['origin','trained','old_runtime','park_runtime','finish_runtime','park_actor',
    'finish_actor','park_phase','preparation','failed_park','failed_finish','online'])
def test_different_actor_lifetime_or_incomplete_restoration_cannot_reenter(fault):
    runtime,origin,old,park,finish=copy.deepcopy(sources())
    if fault=='origin':origin['guid']=1
    elif fault=='trained':old['class_actor']['level']=1
    elif fault=='old_runtime':old['runtime']={'client':4}
    elif fault=='park_runtime':park['runtime']={'client':4}
    elif fault=='finish_runtime':finish['runtime']={'client':4}
    elif fault=='park_actor':park['actor']={'guid':4}
    elif fault=='finish_actor':finish['actor']={'guid':1}
    elif fault=='park_phase':park['phase']='open'
    elif fault=='preparation':finish['fixture_source']['sha256']='different'
    elif fault=='failed_park':park['checks']['0']=False
    elif fault=='failed_finish':finish['checks']['0']=False
    else:park['retained_class_fixture']['online']=1
    with pytest.raises(RuntimeError):continuity(runtime,origin,old,park,finish,'abc')

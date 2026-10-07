import copy
import pytest
from tools.client_compatibility.interaction_retained_native_class_fixture import continuity


@pytest.fixture
def chain():
    before={'worldserver':{'pid':1,'start_ticks':'1'},
            'modern_world':{'pid':2,'start_ticks':'2'},'client':{'pid':3,'start_ticks':'3'}}
    current={**before,'worldserver':{'pid':4,'start_ticks':'4'}}
    origin={'guid':2};hunter={'guid':6}
    old={'phase':'await_owned_class_lobby_review','runtime':before,
         'origin_actor':origin,'class_actor':hunter}
    park={'runtime':before,'actor':hunter,'phase':'await_original_selection_review',
          'checks':dict.fromkeys(['a','b','c','d'],True)}
    finish={'runtime':before,'actor':origin,'checks':dict.fromkeys(range(5),True)}
    d={'schema':'client442_offline_native_feedback_deployment_v1','kind':'pet_slot',
       'completed':True,'finished_at':1,'native_restarted':True,'bridge_unchanged':True,
       'config_unchanged':True,'native_before':before['worldserver'],'native':current['worldserver'],
       'before':before['modern_world'],'after':current['modern_world'],
       'client_lifetimes':{'scout':current['client']},'parked_primary':True,'parked_scout':True,
       'reconnected':{name:{'completed':True,'parked':True} for name in ('primary','scout')}}
    return old,park,finish,d,current


def test_exact_native_only_hunter_chain(chain):
    continuity(*chain)


@pytest.mark.parametrize('field,value',[
    ('kind','melee_feedback'),('completed',False),('finished_at',None),
    ('native_restarted',False),('bridge_unchanged',False),('config_unchanged',False),
    ('native_before',{'pid':99}),('native',{'pid':99}),('before',{'pid':99}),
    ('after',{'pid':99}),('client_lifetimes',{'scout':{'pid':99}}),
    ('parked_primary',False),('parked_scout',False),('reconnected',{'scout':{'completed':True}})])
def test_changed_native_deployment_authority_refused(chain,field,value):
    chain[3][field]=value
    with pytest.raises(RuntimeError):continuity(*chain)


def test_same_native_lifetime_is_not_a_deployment(chain):
    old,park,finish,d,current=copy.deepcopy(chain)
    current['worldserver']=old['runtime']['worldserver'];d['native']=current['worldserver']
    with pytest.raises(RuntimeError):continuity(old,park,finish,d,current)


@pytest.mark.parametrize('index',[1,2])
def test_failed_original_restoration_refused(chain,index):
    chain[index]['checks'][next(iter(chain[index]['checks']))]=False
    with pytest.raises(RuntimeError):continuity(*chain)

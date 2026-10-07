"""Already-stored continuity cannot substitute a different pet, entry or runtime."""
import copy
import pytest
from tools.client_compatibility.interaction_hunter_stored_tame_boundary import stored_boundary


def data():
    return {'runtime':{'client':1,'worldserver':2,'modern_world':3},'actor':{'guid':6},'native_session':'owned',
        'phase':'owned_existing_stored_pet_boundary','fixture_source':{'sha256':'prep'},'entry_source':{'sha256':'entry'},
        'pet_command_sent':False,'checks':dict.fromkeys(range(15),True),
        'baseline_pets':[{'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,'slot':5,'active':0}]}


def accepted(v):return stored_boundary(v,{'guid':6},{'client':1,'worldserver':2,'modern_world':3},'owned',{'sha256':'prep'},{'sha256':'entry'})


def test_only_the_source_bound_already_stored_named_pet_is_eligible():assert accepted(data())


@pytest.mark.parametrize('change',['runtime','actor','session','phase','preparation','entry','pet_command','failed_check',
    'missing_check','test_pet','foreign_owner','wrong_entry','name','renamed','active_slot','active','extra_pet'])
def test_unbound_or_changed_stored_boundary_is_refused(change):
    v=copy.deepcopy(data())
    if change=='runtime':v['runtime']['client']=99
    elif change=='actor':v['actor']={'guid':5}
    elif change=='session':v['native_session']='other'
    elif change=='phase':v['phase']='unverified'
    elif change=='preparation':v['fixture_source']={'sha256':'other'}
    elif change=='entry':v['entry_source']={'sha256':'other'}
    elif change=='pet_command':v['pet_command_sent']=True
    elif change=='failed_check':v['checks'][0]=False
    elif change=='missing_check':v['checks'].pop(0)
    elif change=='test_pet':v['baseline_pets'][0]['id']=6
    elif change=='foreign_owner':v['baseline_pets'][0]['owner']=5
    elif change=='wrong_entry':v['baseline_pets'][0]['entry']=299
    elif change=='name':v['baseline_pets'][0]['name']='Wolf'
    elif change=='renamed':v['baseline_pets'][0]['renamed']=0
    elif change=='active_slot':v['baseline_pets'][0]['slot']=0
    elif change=='active':v['baseline_pets'][0]['active']=1
    else:v['baseline_pets'].append({'id':6})
    assert not accepted(v)

"""Only the two established owned Imp fixtures may enter the pet lifecycle harness."""
import copy
import pytest
from tools.client_compatibility.interaction_pet_target import retained_imp


@pytest.mark.parametrize('guid,name,level,number,petname',[(4,'Harnesslock',1,1,'Volrot'),
    (5,'Harnessctrl',10,2,'Yaztog')])
def test_original_and_trained_fixture_keep_distinct_native_pet_numbers(guid,name,level,number,petname):
    actor=dict(guid=guid,character_name=name,race=1,**{'class':9},level=level,account_id=2)
    pet=dict(id=number,entry=416,owner=guid,name=petname)
    assert retained_imp(actor,[pet])==pet


@pytest.mark.parametrize('change',['guid','name','race','class','level','account','number','entry','owner','petname','duplicate','absent'])
def test_fixture_resolution_refuses_foreign_or_crossed_pet_identity(change):
    actor=dict(guid=5,character_name='Harnessctrl',race=1,**{'class':9},level=10,account_id=2)
    rows=[dict(id=2,entry=416,owner=5,name='Yaztog')]
    if change in ['guid','race','class','level']:actor[change]+=1
    elif change=='name':actor['character_name']='Harnesslock'
    elif change=='account':actor['account_id']=1
    elif change in ['number','entry','owner']:rows[0][{'number':'id'}.get(change,change)]+=1
    elif change=='petname':rows[0]['name']='Volrot'
    elif change=='duplicate':rows.append(copy.deepcopy(rows[0]))
    elif change=='absent':rows=[]
    with pytest.raises(RuntimeError):retained_imp(actor,rows)

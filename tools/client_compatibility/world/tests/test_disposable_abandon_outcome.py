"""Abandon acceptance needs one exact request pair and the unchanged named pet."""
import copy,struct,time
import pytest
from tools.client_compatibility.hunter_abandon_identity import named_preserved,exact_requests
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid


def pet():
    return {'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,'slot':5,'active':0,
        'savetime':time.time()-5,'level':10,'modelid':903,'CreatedBySpell':883,'curhealth':278,'Reactstate':3}


def test_disposable_removal_preserves_every_named_pet_field_except_monotonic_save_clock():
    old=pet();new={**old,'savetime':time.time()-1}
    assert named_preserved([old,{'id':6}],[new])


@pytest.mark.parametrize('change',['named_deleted','test_retained','renamed','owner','slot','active','health','spell','old_clock','extra_field'])
def test_named_pet_or_other_row_mutations_are_refused(change):
    old=pet();after=[copy.deepcopy(old)]
    if change=='named_deleted':after=[]
    elif change=='test_retained':after.append({'id':6})
    elif change=='renamed':after[0]['name']='Wolf'
    elif change=='owner':after[0]['owner']=5
    elif change=='slot':after[0]['slot']=0
    elif change=='active':after[0]['active']=1
    elif change=='health':after[0]['curhealth']=1
    elif change=='spell':after[0]['CreatedBySpell']=1515
    elif change=='old_clock':after[0]['savetime']-=1
    else:after[0]['new_field']=1
    assert not named_preserved([old,{'id':6}],after)


def test_abandon_outcome_refuses_missing_duplicate_or_foreign_requests():
    guid=(0xf14<<52)|(299<<32)|4
    packets=[{'name':'CMSG_PET_ABANDON','direction':'from_client','body':Writer().guid(*modern_guid(guid,0)).finish().hex()},
        {'name':'CMSG_PET_ABANDON','direction':'to_native','body':struct.pack('<Q',guid).hex()}]
    assert all(exact_requests(packets,guid).values())
    assert not all(exact_requests(packets[:1],guid).values())
    assert not all(exact_requests(packets+packets,guid).values())
    assert not all(exact_requests(packets,guid+1).values())

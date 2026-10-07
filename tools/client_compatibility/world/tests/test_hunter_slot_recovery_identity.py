"""The native summon changes only its spell metadata and save clock."""
import copy,time
import pytest
from tools.client_compatibility.interaction_hunter_stable_slots import summoned_identity


def pet():
    return [{'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,
        'CreatedBySpell':79597,'active':1,'slot':0,'curhealth':278,'curmana':0,
        'savetime':int(time.time())-10}]


@pytest.mark.parametrize('old_spell',[79597,883])
def test_native_call_pet_metadata(old_spell):
    before=pet();before[0]['CreatedBySpell']=old_spell;after=copy.deepcopy(before)
    after[0].update(CreatedBySpell=883,savetime=int(time.time()))
    assert summoned_identity(before,after)
    assert before[0]['CreatedBySpell']==old_spell


@pytest.mark.parametrize('field,value',[
    ('id',5),('owner',2),('entry',1),('name','Wolf'),('renamed',0),
    ('CreatedBySpell',79597),('active',0),('slot',5),('curhealth',1),('curmana',1),
    ('savetime',0),('savetime',int(time.time())+10000)])
def test_reject_other_changes(field,value):
    before=pet();after=copy.deepcopy(before);after[0]['CreatedBySpell']=883
    after[0][field]=value
    assert not summoned_identity(before,after)


def test_reject_unknown_original_spell():
    before=pet();before[0]['CreatedBySpell']=1;after=copy.deepcopy(before)
    after[0]['CreatedBySpell']=883
    assert not summoned_identity(before,after)

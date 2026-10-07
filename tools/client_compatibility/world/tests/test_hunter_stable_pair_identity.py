"""Occupied-slot evidence must preserve each native pet independently."""
from copy import deepcopy
import pytest
from tools.client_compatibility.interaction_hunter_stable_pair import identities


BEFORE=[{'id':4,'owner':6,'entry':42717,'name':'Harnesswolf','renamed':1,'slot':5,'active':0,
    'savetime':100,'CreatedBySpell':883,'level':10,'curhealth':278},
    {'id':6,'owner':6,'entry':299,'name':'Wolf','renamed':0,'slot':0,'active':1,
    'savetime':100,'CreatedBySpell':13481,'level':10,'curhealth':278}]


def test_normal_native_swap_and_call_pet_metadata_preserve_both_identities():
    after=deepcopy(BEFORE)
    for row in after:row.update(slot=0 if row['id']==4 else 5,active=0,savetime=101)
    assert identities(BEFORE,after,{4:0,6:5},{4:0,6:0})
    called=deepcopy(after);called[0].update(active=1,savetime=102)
    assert identities(after,called,{4:0,6:5},{4:1,6:0},4)
    # The test wolf's actual native Call Pet replaces its Tame trigger metadata.
    returned=deepcopy(BEFORE);returned[1].update(CreatedBySpell=883,savetime=102)
    assert identities(BEFORE,returned,{4:5,6:0},{4:0,6:1},6)


@pytest.mark.parametrize('number,key,value',[(4,'id',7),(6,'id',4),(4,'owner',5),(6,'owner',5),
    (4,'name','Wolf'),(6,'name','Harnesswolf'),(4,'entry',299),(6,'entry',42717),
    (4,'renamed',0),(6,'level',9),(4,'curhealth',1),(6,'CreatedBySpell',1515),
    (4,'savetime',99),(6,'slot',5),(4,'active',1)])
def test_changed_identity_health_slots_or_unexplained_metadata_are_rejected(number,key,value):
    after=deepcopy(BEFORE);next(r for r in after if r['id']==number)[key]=value
    assert not identities(BEFORE,after)


def test_missing_duplicate_or_extra_pet_is_never_admitted():
    assert not identities(BEFORE,BEFORE[:1])
    assert not identities(BEFORE,[BEFORE[0],BEFORE[0]])
    assert not identities(BEFORE,BEFORE+[BEFORE[0]])

"""Hunter menu diagnostics admit only the native-created owned starting Wolf."""
import pytest
from tools.client_compatibility.interaction_hunter_pet_recon import starting_wolf


def pet():
    return {'id':4,'entry':42717,'owner':6,'CreatedBySpell':79597,'PetType':1,
        'level':10,'name':'Wolf','renamed':0,'slot':0}


def test_exact_retained_starting_pet_is_not_a_tame_or_imp_fixture():
    assert starting_wolf([pet()],6)
    assert not starting_wolf([pet()],5)
    assert not starting_wolf([],6)
    assert not starting_wolf([pet(),pet()],6)


@pytest.mark.parametrize('key,value',[('id',2),('entry',416),('owner',5),('CreatedBySpell',1515),
    ('PetType',0),('level',1),('name','Yaztog'),('renamed',1),('slot',1)])
def test_another_pet_owner_type_tame_name_or_slot_cannot_borrow_starting_wolf_acceptance(key,value):
    row=pet();row[key]=value;assert not starting_wolf([row],6)

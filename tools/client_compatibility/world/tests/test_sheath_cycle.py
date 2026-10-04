"""The observed ranged fixture must visit state 2 before returning to unarmed."""
import pytest
from tools.client_compatibility.interaction_sheath import cycle


@pytest.mark.parametrize('original,ranged,expected',[
    (0,False,[1,0]),(1,False,[0,1]),(0,True,[1,2,0]),
    (1,True,[2,0,1]),(2,True,[0,1,2])])
def test_owned_weapon_cycle(original,ranged,expected):
    assert cycle(original,ranged)==expected


@pytest.mark.parametrize('original,ranged',[(2,False),(3,True),(-1,False)])
def test_cycle_rejects_an_inconsistent_fixture(original,ranged):
    with pytest.raises(ValueError):cycle(original,ranged)

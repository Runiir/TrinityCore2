"""Reject unsafe actor/pet fixtures and any restoration beyond a save clock."""
from copy import deepcopy
import pytest
from tools.client_compatibility.hunter_revive_fixture import dead_snapshot, restored_pets


@pytest.fixture
def baseline():
    named = dict(id=4, owner=6, entry=42717, name='Harnesswolf', renamed=1, slot=5, active=0,
                 curhealth=278, savetime=100, CreatedBySpell=883, PetType=1, level=10)
    disposable = dict(id=16, owner=6, entry=299, name='Wolf', renamed=0, slot=0, active=1,
                      curhealth=278, savetime=200, CreatedBySpell=13481, PetType=1, level=10)
    result = {str(n): {'native': {'online': 0}, 'pets': [], 'saved': {'spells': []}} for n in range(1, 7)}
    result['6']['native'].update(guid=6, account=2, name='Harnesshunt', race=1, **{'class': 3}, level=10)
    result['6']['pets'] = [named, disposable]
    return result


def test_only_disposable_health_changes_and_source_is_immutable(baseline):
    original = deepcopy(baseline)
    changed = dead_snapshot(baseline)
    assert baseline == original
    changed['6']['pets'][1]['curhealth'] = 278
    assert changed == original


@pytest.mark.parametrize('actor,column,value', [('1', 'online', 1), ('6', 'online', 1),
    ('6', 'guid', 7), ('6', 'account', 1), ('6', 'name', 'UserHunter'), ('6', 'class', 9),
    ('6', 'race', 2), ('6', 'level', 11)])
def test_wrong_or_online_character_is_rejected(baseline, actor, column, value):
    baseline[actor]['native'][column] = value
    with pytest.raises(RuntimeError): dead_snapshot(baseline)


@pytest.mark.parametrize('pet,column,value', [(0, 'slot', 0), (0, 'curhealth', 277),
    (0, 'owner', 1), (0, 'name', 'OtherPet'), (1, 'id', 4), (1, 'owner', 1),
    (1, 'entry', 42717), (1, 'CreatedBySpell', 883), (1, 'slot', 5), (1, 'active', 0),
    (1, 'curhealth', 0), (1, 'PetType', 0), (1, 'level', 9)])
def test_protected_or_wrong_disposable_pet_is_rejected(baseline, pet, column, value):
    baseline['6']['pets'][pet][column] = value
    with pytest.raises(RuntimeError): dead_snapshot(baseline)


def test_restoration_allows_only_monotonic_disposable_save_clock(baseline):
    before = baseline['6']['pets']
    after = deepcopy(before)
    after[1]['savetime'] += 1
    assert restored_pets(before, after)
    after[0]['savetime'] += 1
    assert not restored_pets(before, after)


@pytest.mark.parametrize('column,value', [('curhealth', 0), ('slot', 5), ('CreatedBySpell', 982),
    ('owner', 1), ('savetime', 199)])
def test_dead_changed_or_backward_saved_pet_is_not_restored(baseline, column, value):
    before = baseline['6']['pets']
    after = deepcopy(before)
    after[1][column] = value
    assert not restored_pets(before, after)

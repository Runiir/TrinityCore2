import pytest
from tools.client_compatibility import swim_navigation,archaeology_trial


def test_only_healthy_in_bounds_combat_is_recoverable():
    movement={'in_world':True,'dead':False,'on_taxi':False,'in_combat':True,'health_percent':97}
    extra={'mounted':False,'flying':False}
    polygon=[[0,0],[10,0],[10,10],[0,10]]
    with pytest.raises(swim_navigation.CombatInterrupted):
        swim_navigation.available(movement,extra,[5,5,0],polygon)
    for health,position in [(49,[5,5,0]),(97,[11,5,0])]:
        with pytest.raises(RuntimeError) as error:
            swim_navigation.available({**movement,'health_percent':health},extra,position,polygon)
        assert not isinstance(error.value,swim_navigation.CombatInterrupted)


def test_aborted_approach_is_not_counted_as_a_failed_collection_click():
    completed={'action':'loot','execution_status':'completed'}
    interrupted={'action':'loot','execution_status':'interrupted_by_combat'}
    assert archaeology_trial.repeated_completed([completed,completed],'loot',2)
    assert not archaeology_trial.repeated_completed([completed,interrupted],'loot',2)
    assert not archaeology_trial.repeated_completed([interrupted,completed],'loot',2)

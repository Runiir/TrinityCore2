from copy import deepcopy

import pytest

from tools.raid_program.shared_instance_observation import InstanceExpectation, validate_pair


def snapshot(cohort, instance, group, guids):
    raid = dict(server_epoch=123, attempt_id=1, map_id=669, map_difficulty=2,
                instance_id=instance, group_guid=group, bot_actions_enabled=True,
                roster_complete=True, difficulty_readback_complete=True, difficulty_matches=True)
    status = dict(ok=True, cohort_id=cohort, server_epoch=123, attempt_id=1,
                  active=True, lease_count=len(guids), raid_runtime=raid)
    bots = [dict(identity=dict(bot_guid=guid), snapshot=dict(validation_cohort=dict(
        locked=True, in_world=True, matches_cohort=True, violation=False,
        current_map_id=669, current_instance_id=instance))) for guid in guids]
    diagnosis = dict(ok=True, cohort_id=cohort, raid_runtime=deepcopy(raid), bots=bots)
    return dict(status=status, diagnosis=diagnosis)


@pytest.fixture
def pair():
    return [snapshot("a", 10, 100, {1, 2}), InstanceExpectation("a", 669, 2, frozenset({1, 2})),
            snapshot("b", 20, 200, {3, 4}), InstanceExpectation("b", 669, 2, frozenset({3, 4}))]


def test_same_map_distinct_native_instances(pair):
    assert [row["instance_id"] for row in validate_pair(*pair)] == [10, 20]


@pytest.mark.parametrize("field,value", [("server_epoch", 321), ("server_epoch", True),
                                          ("attempt_id", 2), ("map_difficulty", 3),
                                          ("instance_id", 10), ("group_guid", 100)])
def test_reject_identity_drift_or_shared_ownership(pair, field, value):
    pair[2]["status"]["raid_runtime"][field] = value
    pair[2]["diagnosis"]["raid_runtime"][field] = value
    with pytest.raises(ValueError):
        validate_pair(*pair)


def test_reject_current_instance_drift_despite_unchanged_admission(pair):
    pair[2]["diagnosis"]["bots"][0]["snapshot"]["validation_cohort"]["current_instance_id"] = 10
    with pytest.raises(ValueError, match="outside"):
        validate_pair(*pair)


def test_reject_missing_or_duplicate_members(pair):
    pair[2]["diagnosis"]["bots"][1] = deepcopy(pair[2]["diagnosis"]["bots"][0])
    with pytest.raises(ValueError, match="roster"):
        validate_pair(*pair)


@pytest.mark.parametrize("size", [10, 25])
def test_roster_size_is_declared_not_hardcoded(size):
    a, b = frozenset(range(1, size + 1)), frozenset(range(100, 100 + size))
    result = validate_pair(snapshot("a", 10, 100, a), InstanceExpectation("a", 669, 2, a),
                           snapshot("b", 20, 200, b), InstanceExpectation("b", 669, 2, b))
    assert len(result[0]["roster_guids"]) == size

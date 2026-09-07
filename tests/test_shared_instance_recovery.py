"""Replay the actual first shared-canary rejection; mutate ownership negatives."""
import json
from pathlib import Path

import pytest

from tools.raid_program.shared_instance_observation import InstanceExpectation, validate_instance


@pytest.fixture
def captured():
    payload = json.loads((Path(__file__).parent / "fixtures/shared_instance_recovery_06996cc142.json").read_text())
    return payload["observation"]


EXPECTED = InstanceExpectation("bwd_omnotron_diagnostic_10n", 669, 0, frozenset(range(30101, 30111)))


def test_actual_non_atomic_death_recovery_preserves_owned_instance(captured):
    identity = validate_instance(captured, EXPECTED)
    assert identity["instance_id"] == 2
    assert identity["roster_guids"] == list(range(30101, 30111))


@pytest.mark.parametrize("field,value", [
    ("alive", True), ("ghost", False), ("has_corpse", False),
    ("in_world", False), ("locked", False), ("matches_cohort", False),
    ("violation", True), ("instance_id", 13), ("map_id", 1),
])
def test_recovery_never_waives_foreign_or_missing_corpse_authority(captured, field, value):
    captured["diagnosis"]["bots"][-1]["snapshot"]["validation_cohort"][field] = value
    with pytest.raises(ValueError):
        validate_instance(captured, EXPECTED)


@pytest.mark.parametrize("field,value", [("attempt_id", 2), ("attempt_id", True), ("phase", "terminal"), ("phase", "completed")])
def test_recovery_requires_current_active_episode(captured, field, value):
    captured["diagnosis"]["bots"][-1]["snapshot"]["native_recovery_episode"][field] = value
    with pytest.raises(ValueError):
        validate_instance(captured, EXPECTED)


@pytest.mark.parametrize("field,value", [("difficulty_matching_member_count", 7), ("group_difficulty", 2), ("difficulty_member_count", 0)])
def test_recovery_does_not_mask_wrong_difficulty_or_unexplained_deficit(captured, field, value):
    captured["status"]["raid_runtime"][field] = value
    with pytest.raises(ValueError):
        validate_instance(captured, EXPECTED)


def test_incomplete_difficulty_without_outside_recovery_remains_rejected(captured):
    for bot in captured["diagnosis"]["bots"]:
        bot["snapshot"]["validation_cohort"].update(current_map_id=669, current_instance_id=2)
    with pytest.raises(ValueError, match="difficulty"):
        validate_instance(captured, EXPECTED)


def test_live_member_in_foreign_instance_is_rejected(captured):
    captured["diagnosis"]["bots"][0]["snapshot"]["validation_cohort"]["current_instance_id"] = 13
    with pytest.raises(ValueError):
        validate_instance(captured, EXPECTED)

"""Replay the actual first shared-canary rejection; mutate ownership negatives."""
import json
from pathlib import Path
from types import SimpleNamespace

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


def test_incomplete_difficulty_without_recovery_remains_rejected(captured):
    for bot in captured["diagnosis"]["bots"]:
        bot["snapshot"]["validation_cohort"].update(current_map_id=669, current_instance_id=2, alive=True, ghost=False)
    with pytest.raises(ValueError, match="difficulty"):
        validate_instance(captured, EXPECTED)


def test_live_member_in_foreign_instance_is_rejected(captured):
    captured["diagnosis"]["bots"][0]["snapshot"]["validation_cohort"]["current_instance_id"] = 13
    with pytest.raises(ValueError):
        validate_instance(captured, EXPECTED)


@pytest.fixture
def transferring():
    return json.loads((Path(__file__).parent / "fixtures/shared_instance_recovery_3490069d1c.json").read_text())["observation"]


def test_actual_release_worldport_snapshot_preserves_identity(transferring):
    assert validate_instance(transferring, EXPECTED)["instance_id"] == 2


@pytest.mark.parametrize("field,value", [("alive", True), ("ghost", False), ("has_corpse", False),
                                        ("matches_cohort", False), ("in_world", None), ("instance_id", 13)])
def test_transfer_requires_exact_native_authority(transferring, field, value):
    transferring["diagnosis"]["bots"][1]["snapshot"]["validation_cohort"][field] = value
    with pytest.raises(ValueError):
        validate_instance(transferring, EXPECTED)


def test_release_runback_reentry_reclaim_and_stable_sequence(transferring):
    # State transitions use native Recovery.cpp phase names. The two archived
    # snapshots above are live evidence; this sequence is deterministic coverage.
    states = [("released_ghost_observed", False, 669, 2),
              ("moving_to_entrance", True, 0, 0),
              ("entrance_submitted", False, 0, 0),
              ("entrance_worldport_pending", False, 669, 2),
              ("moving_to_corpse", True, 669, 2),
              ("reclaim_delay_pending", True, 669, 2)]
    for phase, in_world, map_id, instance_id in states:
        for bot in transferring["diagnosis"]["bots"]:
            bot["snapshot"]["validation_cohort"].update(in_world=in_world, current_map_id=map_id, current_instance_id=instance_id)
            bot["snapshot"]["native_recovery_episode"]["phase"] = phase
        assert validate_instance(transferring, EXPECTED)["instance_id"] == 2
    # A newer complete diagnosis can close an earlier incomplete status sample.
    for bot in transferring["diagnosis"]["bots"]:
        bot["snapshot"]["validation_cohort"].update(alive=True, ghost=False, has_corpse=False)
        bot["snapshot"]["native_recovery_episode"]["phase"] = "completed"
    transferring["diagnosis"]["raid_runtime"].update(difficulty_readback_complete=True, difficulty_matches=True,
                                                   difficulty_member_count=10, difficulty_matching_member_count=10)
    assert validate_instance(transferring, EXPECTED)["instance_id"] == 2


@pytest.mark.parametrize("before_transfer,after_transfer,advances", [(False, False, True), (True, False, False), (False, True, False)])
def test_transfer_boundary_does_not_certify_native_progress(before_transfer, after_transfer, advances):
    from tools.raid_program.shared_instance_validation import _advanced

    before = {"identity": SimpleNamespace(roster_guids=(1,)), "event_count": 0, "decisions": 1,
              "combat": {"event_count": 0, "recent_events_dropped": 0, "recent_events": [], "validated_outgoing_amount": 0},
              "transferring_guids": [1] if before_transfer else []}
    after = {"event_count": 1, "decisions": 2, "trace_entry_count": 1,
             "combat": {"event_count": 1, "recent_events_dropped": 0, "validated_outgoing_amount": 5,
                        "recent_events": [{"kind": "damage", "actor_guid": 1, "source_guid": 1,
                                           "source_entry": 0, "source_is_pet": False, "originated_amount": 5}]},
             "transferring_guids": [1] if after_transfer else []}
    assert _advanced(before, after) is advances

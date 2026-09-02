from __future__ import annotations

import copy

import pytest

from tools.raid_program.capture_checkpoint_controller import (
    PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION,
    PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND,
    checkpoint_controller_dialect,
    observe_profile_combat_range_checkpoint_row,
    profile_combat_range_checkpoint_arm_command,
    profile_combat_range_checkpoint_terminal_rejections,
)
from tools.raid_program.recurrence_checkpoint_seals import (
    PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
)


ACTOR = 30007
TARGET = 99001
CASE = "generic_min_range_correlation_v1"
SEAL = "a" * 64
SOURCE = "b" * 40


def _admission() -> dict[str, object]:
    return {
        "valid": True,
        "purpose": "fixture_expansion_replay",
        "fixture_expansion_target_ids": [
            PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        ],
        "fixture_expansion_requests": [],
        "pending_fixture_ids": [PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID],
        "checkpoint_fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "checkpoint_case_id": CASE,
        "checkpoint_seal_sha256": SEAL,
        "source_commit": SOURCE,
        "checkpoint_actor_guid": ACTOR,
        "checkpoint_target_guid": TARGET,
    }


def _row() -> dict[str, object]:
    return {
        "ok": True,
        "action": PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION,
        "authority": PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
        "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "case_id": CASE,
        "seal_sha256": SEAL,
        "source_commit": SOURCE,
        "stage": "completed",
        "terminal": True,
        "outcome": "profile_combat_range_checkpoint_boundary_observed",
        "failure_reason": "",
        "checkpoint_generation": 1,
        "actor_guid": ACTOR,
        "target_guid": TARGET,
        "attempt_id": 7,
        "wipe_generation": 0,
        "route_generation": 1,
        "scope_bound": True,
        "target_map_id": 669,
        "target_instance_id": 123,
        "decision_timestamp_ms": 1000,
        "candidate_trace_index": 0,
        "candidate_key": "world.profile_combat_range",
        "candidate_status": "attempted",
        "candidate_reason": "profile_combat_min_range_reconciled",
        "movement_receipt_id": 812,
        "native_motion_type": 8,
        "native_spline_id": 77,
        "movement_committed": True,
        "movement_native_submitted": True,
        "range_diagnostic_target_guid": TARGET,
        "range_intent_fingerprint": "1a",
        "range_receipt_correlated": True,
        "progress_sample_count": 4,
        "movement_progress_observed": True,
        "range_progress_observed_at_ms": 1200,
        "hazard_candidate_key": "shared_hazard_movement:generic_hazard_exit:12:3",
        "hazard_candidate_source": "shared_hazard_movement",
        "hazard_candidate_status": "attempted",
        "hazard_trace_index": 1,
        "hazard_decision_timestamp_ms": 800,
        "hazard_movement_receipt_id": 811,
        "hazard_intent_fingerprint": "2b",
        "hazard_progress_sample_count": 3,
        "hazard_native_submitted": True,
        "hazard_progress_observed": True,
        "hazard_progress_observed_at_ms": 900,
        "hazard_preempted_range": True,
        "cast_spell_id": 12345,
        "cast_target_guid": TARGET,
        "cast_retry_observed": True,
        "cast_recorded_at_ms": 1300,
        "cast_before_progress_observed": False,
    }


def test_authenticated_arm_command_and_status_command() -> None:
    assert profile_combat_range_checkpoint_arm_command(
        _admission(), ACTOR, TARGET,
    ) == (
        "botautoprofilecombatrangecheckpoint arm "
        f"{ACTOR} {TARGET} {CASE} {SEAL} {SOURCE}"
    )
    assert profile_combat_range_checkpoint_arm_command(None, None, None) is None
    assert PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND.endswith(" status")


def test_checkpoint_dialect_wires_authenticated_scheduler_observer() -> None:
    dialect = checkpoint_controller_dialect(_admission(), ACTOR)
    assert dialect == {
        "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "arm_command": (
            "botautoprofilecombatrangecheckpoint arm "
            f"{ACTOR} {TARGET} {CASE} {SEAL} {SOURCE}"
        ),
        "scheduler_kwargs": dialect["scheduler_kwargs"],
    }
    kwargs = dialect["scheduler_kwargs"]
    assert kwargs["checkpoint_action"] == PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION
    assert kwargs["checkpoint_terminal_status_command"] == (
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    )
    assert kwargs["checkpoint_terminal_from_status"] is False
    assert callable(kwargs["checkpoint_observer"])

    missing_target = _admission()
    del missing_target["checkpoint_target_guid"]
    with pytest.raises(ValueError, match="verified_admission_invalid"):
        checkpoint_controller_dialect(missing_target, ACTOR)

    wrong_fixture = _admission()
    wrong_fixture["checkpoint_fixture_id"] = "unsupported_fixture"
    with pytest.raises(ValueError, match="checkpoint_controller_fixture_unsupported"):
        checkpoint_controller_dialect(wrong_fixture, ACTOR)


@pytest.mark.parametrize(
    "actor,target,field",
    [
        (30008, TARGET, "actor"),
        (ACTOR, 99002, "target"),
    ],
)
def test_arm_rejects_identity_drift(
    actor: int, target: int, field: str,
) -> None:
    with pytest.raises(ValueError, match="verified_admission_invalid"):
        profile_combat_range_checkpoint_arm_command(_admission(), actor, target)


@pytest.mark.parametrize(
    "field, value, expected",
    [
        ("seal_sha256", "c" * 64, "identity"),
        ("fixture_id", "wrong_fixture", "identity"),
        ("target_guid", TARGET + 1, "identity"),
        ("checkpoint_generation", 2, "scope"),
        ("candidate_key", "stale.range", "range"),
        ("movement_receipt_id", 0, "range"),
        ("range_receipt_correlated", False, "range"),
        ("range_diagnostic_target_guid", TARGET + 1, "range"),
        ("hazard_candidate_key", "", "hazard"),
        ("hazard_movement_receipt_id", 812, "hazard"),
        ("hazard_native_submitted", False, "hazard"),
        ("hazard_progress_observed", False, "hazard"),
        ("hazard_preempted_range", False, "hazard"),
        ("hazard_decision_timestamp_ms", 1100, "hazard"),
        ("hazard_progress_observed_at_ms", 1000, "hazard"),
        ("movement_progress_observed", False, "range"),
        ("cast_target_guid", TARGET + 1, "cast"),
        ("cast_recorded_at_ms", 1200, "cast"),
        ("cast_before_progress_observed", True, "cast"),
        ("stage", "armed", "terminal"),
    ],
)
def test_terminal_consumer_rejects_first_broken_edge(
    field: str, value: object, expected: str,
) -> None:
    row = _row()
    row[field] = value
    reasons = profile_combat_range_checkpoint_terminal_rejections(
        row, actor_guid=ACTOR, target_guid=TARGET, case_id=CASE,
        seal_sha256=SEAL, source_commit=SOURCE, checkpoint_generation=1,
    )
    expected_reasons = {
        "identity": "profile_combat_range_checkpoint_status_identity_invalid",
        "scope": "profile_combat_range_checkpoint_status_scope_invalid",
        "range": "profile_combat_range_checkpoint_range_correlation_invalid",
        "hazard": "profile_combat_range_checkpoint_hazard_correlation_invalid",
        "cast": "profile_combat_range_checkpoint_later_cast_invalid",
        "terminal": "profile_combat_range_checkpoint_status_terminal_invalid",
    }
    assert reasons == [expected_reasons[expected]]


def test_terminal_consumer_rejects_unavailable_or_malformed_status() -> None:
    assert observe_profile_combat_range_checkpoint_row(
        None, actor_guid=ACTOR, target_guid=TARGET, case_id=CASE,
        seal_sha256=SEAL, source_commit=SOURCE,
    ) == ["profile_combat_range_checkpoint_status_unavailable"]
    malformed = copy.deepcopy(_row())
    malformed["action"] = "botauto_status"
    assert observe_profile_combat_range_checkpoint_row(
        malformed, actor_guid=ACTOR, target_guid=TARGET, case_id=CASE,
        seal_sha256=SEAL, source_commit=SOURCE,
    ) == ["profile_combat_range_checkpoint_status_action_invalid"]


def test_terminal_consumer_accepts_exact_join() -> None:
    assert profile_combat_range_checkpoint_terminal_rejections(
        _row(), actor_guid=ACTOR, target_guid=TARGET, case_id=CASE,
        seal_sha256=SEAL, source_commit=SOURCE, checkpoint_generation=1,
        attempt_id=7, wipe_generation=0, route_generation=1,
        target_map_id=669, target_instance_id=123,
    ) == []

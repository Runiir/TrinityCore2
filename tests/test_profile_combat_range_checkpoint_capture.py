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
from tools.raid_program.controller_route_hold import (
    ControllerRouteHoldLaunchIdentity,
    ControllerRouteHoldScheduler,
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


def _scheduler_identity() -> ControllerRouteHoldLaunchIdentity:
    return ControllerRouteHoldLaunchIdentity(
        scenario_id="blackwing_descent_10n_magmaw_diagnostic",
        runtime_profile="blackwing_descent_10n_magmaw_diagnostic",
        pool_tag="blackwing_descent_10n_magmaw_diagnostic",
        route_manifest_sha256="c" * 64,
        route_node_id="bwd.entry.regroup",
        actor_guid=ACTOR,
        fixture_id=PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        seal_sha256=SEAL,
        source_commit=SOURCE,
    )


def _scheduler() -> ControllerRouteHoldScheduler:
    dialect = checkpoint_controller_dialect(_admission(), ACTOR)
    assert isinstance(dialect, dict)
    return ControllerRouteHoldScheduler(
        _scheduler_identity(), **dialect["scheduler_kwargs"],
    )


def _hold(*, phase: str = "held", terminal: bool = False) -> dict:
    return {
        "ok": True,
        "phase": phase,
        "cohort_id": "default",
        "server_epoch": 91,
        "attempt_id": 7,
        "scenario_id": _scheduler_identity().scenario_id,
        "runtime_profile": _scheduler_identity().runtime_profile,
        "route_manifest_sha256": _scheduler_identity().route_manifest_sha256,
        "route_generation": 1,
        "route_node_id": _scheduler_identity().route_node_id,
        "actor_guid": ACTOR,
        "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "seal_sha256": SEAL,
        "source_commit": SOURCE,
        "acquire_count": 1,
        "arm_ack_count": 1 if phase in {"armed", "checkpoint_terminal"} else 0,
        "checkpoint_stage": "completed" if terminal else "",
        "checkpoint_terminal": terminal,
        "checkpoint_identity_preserved": terminal,
        "release_count": 0,
    }


def _status(*, phase: str = "held") -> dict:
    return {
        "ok": True,
        "action": "botauto_status",
        "cohort_id": "default",
        "active_profile": _scheduler_identity().runtime_profile,
        "validation_route": {"generation": 1},
        "raid_runtime": {
            "active": True,
            "server_epoch": 91,
            "attempt_id": 7,
            "wipe_generation": 0,
            "instance_id": 123,
            "route_progress": {"generation": 1},
            "controller_route_hold": _hold(phase=phase),
        },
    }


def _profile_row(*, stage: str = "armed", terminal: bool = False) -> dict:
    row = copy.deepcopy(_row())
    row.update({
        "stage": stage,
        "terminal": terminal,
        "outcome": (
            "profile_combat_range_checkpoint_boundary_observed"
            if terminal else "profile_combat_range_checkpoint_progress_observed"
        ),
    })
    return row


def _profile_arm_ack() -> dict:
    row = _profile_row()
    row["action"] = PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION
    row["terminal"] = False
    return row


def _advance_scheduler_to_arm_ack(
    scheduler: ControllerRouteHoldScheduler,
) -> None:
    assert scheduler.start() == [
        "botautochaincheckpoint start-held "
        f"{ACTOR} {PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID} {SEAL} {SOURCE}"
    ]
    assert scheduler.observe(_hold()) == ["botauto status"]
    assert scheduler.observe(_status()) == ["botauto status"]
    assert scheduler.observe(_status()) == [
        profile_combat_range_checkpoint_arm_command(_admission(), ACTOR, TARGET)
    ]
    assert scheduler.phase == "awaiting_arm_ack"


def test_profile_scheduler_executes_exact_arm_poll_terminal_protocol() -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    assert scheduler.observe(_profile_arm_ack()) == [
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ]
    assert scheduler.observe(_profile_row(stage="progress_observed")) == [
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ]
    assert scheduler.observe(_profile_row(
        stage="completed", terminal=True,
    )) == []

    receipt = scheduler.receipt()
    assert receipt["gate_passed"] is True
    assert receipt["phase"] == "complete"
    assert receipt["failure_reason"] is None
    assert receipt["start_ack_count"] == 1
    assert receipt["held_status_count"] == 2
    assert receipt["arm_ack_count"] == 1
    assert receipt["checkpoint_terminal_count"] == 1
    assert receipt["checkpoint_terminal_stage"] == "completed"
    assert receipt["command_counts"] == {
        "start_held": 1, "status": 2, "arm": 1, "release": 0,
    }
    assert receipt["command_transcript"] == [
        "botautochaincheckpoint start-held "
        f"{ACTOR} {PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID} {SEAL} {SOURCE}",
        "botauto status",
        "botauto status",
        profile_combat_range_checkpoint_arm_command(
            _admission(), ACTOR, TARGET,
        ),
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND,
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND,
    ]
    assert receipt["command_transcript"].count(
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ) == 2
    assert receipt["checkpoint_terminal_observation"]["terminal"] is True


def test_profile_scheduler_rejects_duplicate_active_arm_without_poll() -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    assert scheduler.observe(_profile_arm_ack()) == [
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ]
    transcript = list(scheduler.command_transcript)
    assert scheduler.observe(_profile_arm_ack()) == []
    assert scheduler.failure_reason == (
        "profile_combat_range_checkpoint_duplicate_or_stale_receipt"
    )
    assert scheduler.command_transcript == transcript


@pytest.mark.parametrize(
    "accepted_stage,stale_stage",
    [
        ("range_observed", "range_observed"),
        ("progress_observed", "progress_observed"),
        ("progress_observed", "range_observed"),
        ("progress_observed", "armed"),
    ],
)
def test_profile_scheduler_rejects_duplicate_or_regressive_active_stage(
    accepted_stage: str, stale_stage: str,
) -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    scheduler.observe(_profile_arm_ack())
    assert scheduler.observe(_profile_row(stage=accepted_stage)) == [
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ]
    transcript = list(scheduler.command_transcript)
    assert scheduler.observe(_profile_row(stage=stale_stage)) == []
    assert scheduler.failure_reason == (
        "profile_combat_range_checkpoint_duplicate_or_stale_receipt"
    )
    assert scheduler.command_transcript == transcript


@pytest.mark.parametrize(
    "mutation",
    [
        "malformed_arm",
        "unavailable_status",
        "stale_generation",
        "wrong_actor",
        "wrong_target",
        "wrong_case",
        "wrong_seal",
        "wrong_source",
        "wrong_scope",
        "missing_terminal",
    ],
)
def test_profile_scheduler_protocol_negatives_fail_closed(
    mutation: str,
) -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    if mutation == "malformed_arm":
        row = _profile_arm_ack()
        row.pop("target_guid")
        scheduler.observe(row)
        assert scheduler.failure_reason == (
            "profile_combat_range_checkpoint_status_identity_invalid"
        )
        return
    if mutation == "unavailable_status":
        scheduler = _scheduler()
        scheduler.start()
        scheduler.observe({"action": "botauto_status"})
        assert scheduler.failure_reason == "controller_route_hold_status_receipt_missing"
        return
    if mutation == "missing_terminal":
        scheduler.observe(_profile_arm_ack())
        scheduler.finish()
        assert scheduler.failure_reason == (
            "controller_route_hold_checkpoint_lifecycle_missing"
        )
        return
    if mutation == "stale_generation":
        scheduler.observe(_profile_arm_ack())
        row = _profile_row(stage="armed")
        row["checkpoint_generation"] = 2
        scheduler.observe(row)
        assert scheduler.failure_reason == (
            "profile_combat_range_checkpoint_status_scope_invalid"
        )
        return

    row = _profile_arm_ack()
    if mutation == "wrong_actor":
        row["actor_guid"] = ACTOR + 1
    elif mutation == "wrong_target":
        row["target_guid"] = TARGET + 1
    elif mutation == "wrong_case":
        row["case_id"] = CASE + ".stale"
    elif mutation == "wrong_seal":
        row["seal_sha256"] = "c" * 64
    elif mutation == "wrong_source":
        row["source_commit"] = "d" * 40
    elif mutation == "wrong_scope":
        row["attempt_id"] = 8
    scheduler.observe(row)
    assert scheduler.failed is True
    assert scheduler.failure_reason in {
        "profile_combat_range_checkpoint_status_identity_invalid",
        "profile_combat_range_checkpoint_status_scope_invalid",
    }


def test_profile_scheduler_duplicate_terminal_receipt_is_ignored_after_success() -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    scheduler.observe(_profile_arm_ack())
    scheduler.observe(_profile_row(stage="progress_observed"))
    terminal = _profile_row(stage="completed", terminal=True)
    assert scheduler.observe(terminal) == []
    first = scheduler.receipt()
    assert scheduler.observe(copy.deepcopy(terminal)) == []
    second = scheduler.receipt()
    assert second["checkpoint_terminal_count"] == 1
    assert second["checkpoint_terminal_observation"] == (
        first["checkpoint_terminal_observation"]
    )

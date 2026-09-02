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
    CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
    PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
    PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
)


ACTOR = 30007
TARGET = 99001
TARGET_SPAWN = 250051
TARGET_ENTRY = 41570
TARGET_MAP = 669
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
        "checkpoint_runtime_target_guid": TARGET,
        "checkpoint_target_spawn_id": TARGET_SPAWN,
        "checkpoint_target_entry": TARGET_ENTRY,
        "checkpoint_target_map_id": TARGET_MAP,
        "checkpoint_target_identity": {
            "runtime_target_guid": TARGET,
            "target_spawn_id": TARGET_SPAWN,
            "target_entry": TARGET_ENTRY,
            "target_map_id": TARGET_MAP,
        },
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
        "runtime_target_guid": TARGET,
        "target_spawn_id": TARGET_SPAWN,
        "target_entry": TARGET_ENTRY,
        "attempt_id": 7,
        "wipe_generation": 0,
        "route_generation": 1,
        "scope_bound": True,
        "target_map_id": TARGET_MAP,
        "target_instance_id": 123,
        "runtime_target_guid_matched": True,
        "target_spawn_id_matched": True,
        "target_entry_matched": True,
        "target_map_id_matched": True,
        "positive_instance_matched": True,
        "same_instance_matched": True,
        "attempt_scope_matched": True,
        "wipe_scope_matched": True,
        "route_scope_matched": True,
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
    del missing_target["checkpoint_runtime_target_guid"]
    with pytest.raises(ValueError, match="verified_admission_invalid"):
        checkpoint_controller_dialect(missing_target, ACTOR)

    legacy_target_only = _admission()
    for field in (
        "checkpoint_runtime_target_guid", "checkpoint_target_spawn_id",
        "checkpoint_target_entry", "checkpoint_target_map_id",
        "checkpoint_target_identity",
    ):
        del legacy_target_only[field]
    with pytest.raises(ValueError, match="verified_admission_invalid"):
        profile_combat_range_checkpoint_arm_command(
            legacy_target_only, ACTOR, TARGET,
        )

    wrong_fixture = _admission()
    wrong_fixture["checkpoint_fixture_id"] = "unsupported_fixture"
    with pytest.raises(ValueError, match="checkpoint_controller_fixture_unsupported"):
        checkpoint_controller_dialect(wrong_fixture, ACTOR)


def test_checkpoint_dialect_dispatches_from_explicit_selection() -> None:
    admission = _admission()
    admission["fixture_expansion_target_ids"] = [
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
    ]
    admission["pending_fixture_ids"] = [
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
    ]

    dialect = checkpoint_controller_dialect(admission, ACTOR)

    assert dialect is not None
    assert dialect["fixture_id"] == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
    assert dialect["arm_command"].startswith(
        "botautoprofilecombatrangecheckpoint arm "
    )


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
        ("runtime_target_guid", TARGET + 1, "identity"),
        ("target_spawn_id", TARGET_SPAWN + 1, "target_identity"),
        ("target_entry", TARGET_ENTRY + 1, "target_identity"),
        ("target_map_id", TARGET_MAP + 1, "target_identity"),
        ("runtime_target_guid_matched", False, "target_identity"),
        ("target_spawn_id_matched", False, "target_identity"),
        ("target_entry_matched", False, "target_identity"),
        ("target_map_id_matched", False, "target_identity"),
        ("target_instance_id", 0, "scope"),
        ("positive_instance_matched", False, "scope"),
        ("same_instance_matched", False, "scope"),
        ("attempt_scope_matched", False, "scope"),
        ("wipe_scope_matched", False, "scope"),
        ("route_scope_matched", False, "scope"),
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
        row, actor_guid=ACTOR, runtime_target_guid=TARGET,
        target_spawn_id=TARGET_SPAWN, target_entry=TARGET_ENTRY,
        target_map_id=TARGET_MAP, case_id=CASE, seal_sha256=SEAL,
        source_commit=SOURCE, checkpoint_generation=1,
    )
    expected_reasons = {
        "identity": "profile_combat_range_checkpoint_status_identity_invalid",
        "target_identity": (
            "profile_combat_range_checkpoint_target_identity_invalid"
        ),
        "scope": "profile_combat_range_checkpoint_status_scope_invalid",
        "range": "profile_combat_range_checkpoint_range_correlation_invalid",
        "hazard": "profile_combat_range_checkpoint_hazard_correlation_invalid",
        "cast": "profile_combat_range_checkpoint_later_cast_invalid",
        "terminal": "profile_combat_range_checkpoint_status_terminal_invalid",
    }
    assert reasons == [expected_reasons[expected]]


def test_terminal_consumer_rejects_unavailable_or_malformed_status() -> None:
    assert observe_profile_combat_range_checkpoint_row(
        None, actor_guid=ACTOR, runtime_target_guid=TARGET,
        target_spawn_id=TARGET_SPAWN, target_entry=TARGET_ENTRY,
        target_map_id=TARGET_MAP, case_id=CASE, seal_sha256=SEAL,
        source_commit=SOURCE,
    ) == ["profile_combat_range_checkpoint_status_unavailable"]
    malformed = copy.deepcopy(_row())
    malformed["action"] = "botauto_status"
    assert observe_profile_combat_range_checkpoint_row(
        malformed, actor_guid=ACTOR, runtime_target_guid=TARGET,
        target_spawn_id=TARGET_SPAWN, target_entry=TARGET_ENTRY,
        target_map_id=TARGET_MAP, case_id=CASE, seal_sha256=SEAL,
        source_commit=SOURCE,
    ) == ["profile_combat_range_checkpoint_status_action_invalid"]


def test_terminal_consumer_accepts_exact_join() -> None:
    assert profile_combat_range_checkpoint_terminal_rejections(
        _row(), actor_guid=ACTOR, runtime_target_guid=TARGET,
        target_spawn_id=TARGET_SPAWN, target_entry=TARGET_ENTRY,
        target_map_id=TARGET_MAP, case_id=CASE, seal_sha256=SEAL,
        source_commit=SOURCE, checkpoint_generation=1,
        attempt_id=7, wipe_generation=0, route_generation=1,
        target_instance_id=123,
    ) == []


def test_terminal_consumer_rejects_boolean_bound_instance() -> None:
    row = _row()
    row["target_instance_id"] = 1

    assert profile_combat_range_checkpoint_terminal_rejections(
        row, actor_guid=ACTOR, runtime_target_guid=TARGET,
        target_spawn_id=TARGET_SPAWN, target_entry=TARGET_ENTRY,
        target_map_id=TARGET_MAP, case_id=CASE, seal_sha256=SEAL,
        source_commit=SOURCE, checkpoint_generation=1,
        attempt_id=7, wipe_generation=0, route_generation=1,
        target_instance_id=True,
    ) == ["profile_combat_range_checkpoint_status_scope_invalid"]


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


def _status(*, phase: str = "held", instance_id: int = 123) -> dict:
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
            "instance_id": instance_id,
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
    # ArmProfileCombatRangeCheckpointForCohort serializes before the first
    # live target observation, so no target instance or match outcome is bound.
    return {
        "ok": True,
        "action": PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION,
        "authority": PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
        "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "case_id": CASE,
        "seal_sha256": SEAL,
        "source_commit": SOURCE,
        "stage": "armed",
        "terminal": False,
        "outcome": "profile_combat_range_checkpoint_armed",
        "failure_reason": "",
        "checkpoint_generation": 1,
        "actor_guid": ACTOR,
        "runtime_target_guid": TARGET,
        "target_spawn_id": TARGET_SPAWN,
        "target_entry": TARGET_ENTRY,
        "attempt_id": 7,
        "wipe_generation": 0,
        "route_generation": 1,
        "scope_bound": False,
        "target_map_id": TARGET_MAP,
        "target_instance_id": 0,
        "runtime_target_guid_matched": False,
        "target_spawn_id_matched": False,
        "target_entry_matched": False,
        "target_map_id_matched": False,
        "positive_instance_matched": False,
        "same_instance_matched": False,
        "attempt_scope_matched": False,
        "wipe_scope_matched": False,
        "route_scope_matched": False,
        "decision_timestamp_ms": 0,
        "candidate_trace_index": 0,
        "candidate_key": "",
        "candidate_status": "",
        "candidate_reason": "",
        "movement_receipt_id": 0,
        "native_motion_type": 0,
        "native_spline_id": 0,
        "movement_committed": False,
        "movement_native_submitted": False,
        "range_diagnostic_target_guid": 0,
        "range_intent_fingerprint": "0",
        "range_receipt_correlated": False,
        "progress_sample_count": 0,
        "movement_progress_observed": False,
        "range_progress_observed_at_ms": 0,
        "hazard_candidate_key": "",
        "hazard_candidate_source": "",
        "hazard_candidate_status": "",
        "hazard_trace_index": 0,
        "hazard_decision_timestamp_ms": 0,
        "hazard_movement_receipt_id": 0,
        "hazard_intent_fingerprint": "0",
        "hazard_progress_sample_count": 0,
        "hazard_native_submitted": False,
        "hazard_progress_observed": False,
        "hazard_progress_observed_at_ms": 0,
        "hazard_preempted_range": False,
        "cast_spell_id": 0,
        "cast_target_guid": 0,
        "cast_retry_observed": False,
        "cast_recorded_at_ms": 0,
        "cast_before_progress_observed": False,
    }


def _advance_scheduler_to_arm_ack(
    scheduler: ControllerRouteHoldScheduler, *, instance_id: int = 123,
) -> None:
    assert scheduler.start() == [
        "botautochaincheckpoint start-held "
        f"{ACTOR} {PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID} {SEAL} {SOURCE}"
    ]
    assert scheduler.observe(_hold()) == ["botauto status"]
    assert scheduler.observe(_status(instance_id=instance_id)) == [
        "botauto status"
    ]
    assert scheduler.observe(_status(instance_id=instance_id)) == [
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


def test_profile_arm_ack_uses_independent_native_armed_defaults() -> None:
    row = _profile_arm_ack()

    assert set(row) == set(_row())
    assert row["stage"] == "armed"
    assert row["terminal"] is False
    assert row["scope_bound"] is False
    assert type(row["target_instance_id"]) is int
    assert row["target_instance_id"] == 0
    assert all(
        row[field] is False
        for field in (
            "runtime_target_guid_matched",
            "target_spawn_id_matched",
            "target_entry_matched",
            "target_map_id_matched",
            "positive_instance_matched",
            "same_instance_matched",
            "attempt_scope_matched",
            "wipe_scope_matched",
            "route_scope_matched",
        )
    )


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
    "field,value",
    [
        ("target_instance_id", 123),
        ("target_instance_id", True),
        ("target_instance_id", False),
        ("target_instance_id", None),
        ("scope_bound", True),
        ("runtime_target_guid_matched", True),
        ("target_spawn_id_matched", True),
        ("target_entry_matched", True),
        ("target_map_id_matched", True),
        ("positive_instance_matched", True),
        ("same_instance_matched", True),
        ("attempt_scope_matched", True),
        ("wipe_scope_matched", True),
        ("route_scope_matched", True),
        ("terminal", True),
    ],
)
def test_profile_scheduler_rejects_inconsistent_unbound_arm_ack(
    field: str, value: object,
) -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    row = _profile_arm_ack()
    row[field] = value

    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == (
        "profile_combat_range_checkpoint_status_arm_ack_invalid"
    )


def test_profile_scheduler_rejects_omitted_unbound_arm_instance() -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    row = _profile_arm_ack()
    del row["target_instance_id"]

    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == (
        "profile_combat_range_checkpoint_status_arm_ack_invalid"
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("scope_bound", False),
        ("target_instance_id", 0),
        ("target_instance_id", 124),
        ("runtime_target_guid_matched", False),
        ("target_spawn_id_matched", False),
        ("target_entry_matched", False),
        ("target_map_id_matched", False),
        ("positive_instance_matched", False),
        ("same_instance_matched", False),
        ("attempt_scope_matched", False),
        ("wipe_scope_matched", False),
        ("route_scope_matched", False),
    ],
)
@pytest.mark.parametrize("terminal", [False, True])
def test_profile_scheduler_requires_exact_bound_scope_after_arm(
    field: str, value: object, terminal: bool,
) -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler)
    assert scheduler.observe(_profile_arm_ack()) == [
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ]
    row = _profile_row(
        stage="completed" if terminal else "progress_observed",
        terminal=terminal,
    )
    row[field] = value

    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == (
        "profile_combat_range_checkpoint_status_scope_invalid"
    )


@pytest.mark.parametrize("terminal", [False, True])
@pytest.mark.parametrize(
    "instance_value",
    [
        pytest.param(True, id="true"),
        pytest.param(False, id="false"),
        pytest.param(None, id="none"),
        pytest.param(0, id="default-zero"),
        pytest.param("omitted", id="omitted"),
    ],
)
def test_profile_scheduler_rejects_non_integer_bound_instance_at_one(
    instance_value: object, terminal: bool,
) -> None:
    scheduler = _scheduler()
    _advance_scheduler_to_arm_ack(scheduler, instance_id=1)
    assert scheduler.observe(_profile_arm_ack()) == [
        PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
    ]
    row = _profile_row(
        stage="completed" if terminal else "progress_observed",
        terminal=terminal,
    )
    if instance_value == "omitted":
        del row["target_instance_id"]
    else:
        row["target_instance_id"] = instance_value
    transcript = list(scheduler.command_transcript)

    assert scheduler.observe(row) == []
    assert scheduler.failure_reason == (
        "profile_combat_range_checkpoint_status_scope_invalid"
    )
    assert scheduler._profile_checkpoint_state["active_stage"] == "armed"
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
        "wrong_spawn",
        "wrong_entry",
        "wrong_map",
        "wrong_case",
        "wrong_seal",
        "wrong_source",
        "wrong_scope",
        "wrong_wipe_scope",
        "wrong_wipe_scope_type",
        "wrong_route_scope",
        "wrong_route_scope_type",
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
        row.pop("runtime_target_guid")
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
        row["runtime_target_guid"] = TARGET + 1
    elif mutation == "wrong_spawn":
        row["target_spawn_id"] = TARGET_SPAWN + 1
    elif mutation == "wrong_entry":
        row["target_entry"] = TARGET_ENTRY + 1
    elif mutation == "wrong_map":
        row["target_map_id"] = TARGET_MAP + 1
    elif mutation == "wrong_case":
        row["case_id"] = CASE + ".stale"
    elif mutation == "wrong_seal":
        row["seal_sha256"] = "c" * 64
    elif mutation == "wrong_source":
        row["source_commit"] = "d" * 40
    elif mutation == "wrong_scope":
        row["attempt_id"] = 8
    elif mutation == "wrong_wipe_scope":
        row["wipe_generation"] = 1
    elif mutation == "wrong_wipe_scope_type":
        row["wipe_generation"] = False
    elif mutation == "wrong_route_scope":
        row["route_generation"] = 2
    elif mutation == "wrong_route_scope_type":
        row["route_generation"] = True
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

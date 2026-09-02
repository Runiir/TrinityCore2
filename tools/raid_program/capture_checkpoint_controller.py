from __future__ import annotations

import copy
import math
import re
from typing import Any

try:
    from tools.raid_program.capture_runtime_acceptance import _roster_rejections
    from tools.raid_program.capture_runtime_identity import (
        IDENTITY_FIELDS,
        _roster_binding_identity,
    )
    from tools.raid_program.capture_value_types import (
        _canonical_object_sha256,
        _positive_int,
    )
    from tools.raid_program.capture_watchdog import _watchdog_scope_rejections
    from tools.raid_program.recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
        MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
        MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
        PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        RecurrenceAdmissionError,
        _fixture_expansion_contract,
        _magmaw_transfer_checkpoint_contract,
        _native_path_checkpoint_request_contract,
        _profile_combat_range_checkpoint_contract,
    )
except ModuleNotFoundError:
    from capture_runtime_acceptance import _roster_rejections
    from capture_runtime_identity import IDENTITY_FIELDS, _roster_binding_identity
    from capture_value_types import _canonical_object_sha256, _positive_int
    from capture_watchdog import _watchdog_scope_rejections
    from recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
        MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
        MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
        NATIVE_PATH_CHECKPOINT_FIXTURE_ID,
        PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
        PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        RecurrenceAdmissionError,
        _fixture_expansion_contract,
        _magmaw_transfer_checkpoint_contract,
        _native_path_checkpoint_request_contract,
        _profile_combat_range_checkpoint_contract,
    )


def _verified_checkpoint_target_contract(
    recurrence_admission: dict[str, Any],
) -> bool:
    """Require a verified auxiliary checkpoint and expansion requests."""

    try:
        requests = _fixture_expansion_contract(
            recurrence_admission, label="checkpoint_verified_admission"
        )
    except RecurrenceAdmissionError:
        return False
    revisions = recurrence_admission.get("fixture_revisions")
    if (
        recurrence_admission.get("checkpoint_fixture_id")
        != CHAINWIELDER_CHECKPOINT_FIXTURE_ID
        or not isinstance(revisions, dict)
    ):
        return False
    return all(
        revisions.get(request["fixture_id"]) == request["from_revision"]
        for request in requests
    )


def chainwielder_checkpoint_arm_command(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
) -> str | None:
    """Build the exact post-admission arm command, or fail closed."""

    seal = recurrence_admission.get("checkpoint_seal_sha256") \
        if isinstance(recurrence_admission, dict) else None
    if seal is None:
        if actor_guid is not None:
            raise ValueError("checkpoint_actor_without_verified_seal")
        return None
    admission_sha256 = recurrence_admission.get("admission_sha256")
    source_commit = recurrence_admission.get("source_commit")
    if (
        recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != FIXTURE_EXPANSION_PURPOSE
        or not _verified_checkpoint_target_contract(recurrence_admission)
        or not isinstance(admission_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", admission_sha256)
    ):
        raise ValueError("checkpoint_verified_admission_invalid")
    if (
        not isinstance(actor_guid, int)
        or isinstance(actor_guid, bool)
        or actor_guid <= 0
    ):
        raise ValueError("checkpoint_actor_guid_required")
    if not isinstance(seal, str) or not re.fullmatch(r"[0-9a-f]{64}", seal):
        raise ValueError("checkpoint_verified_seal_invalid")
    if not isinstance(source_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("checkpoint_verified_source_invalid")
    return f"botautochaincheckpoint arm {actor_guid} {seal} {source_commit}"


def native_path_checkpoint_arm_command(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
) -> str | None:
    """Build the fixed-case arm command from verified admission only."""

    if recurrence_admission is None and actor_guid is None:
        return None
    if not isinstance(recurrence_admission, dict):
        raise ValueError("native_path_checkpoint_verified_admission_missing")
    try:
        _native_path_checkpoint_request_contract(
            recurrence_admission, label="native_path_checkpoint_verified_admission"
        )
    except RecurrenceAdmissionError as error:
        raise ValueError(
            "native_path_checkpoint_verified_admission_invalid"
        ) from error
    seal = recurrence_admission.get("checkpoint_seal_sha256")
    case_id = recurrence_admission.get("checkpoint_case_id")
    source = recurrence_admission.get("source_commit")
    if (
        recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != FIXTURE_EXPANSION_PURPOSE
        or recurrence_admission.get("checkpoint_fixture_id")
            != NATIVE_PATH_CHECKPOINT_FIXTURE_ID
        or not isinstance(actor_guid, int) or isinstance(actor_guid, bool)
        or actor_guid <= 0
        or not isinstance(case_id, str) or not case_id
        or not isinstance(seal, str) or not re.fullmatch(r"[0-9a-f]{64}", seal)
        or not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source)
    ):
        raise ValueError("native_path_checkpoint_verified_admission_invalid")
    return (
        f"botautonativepathcheckpoint arm {actor_guid} {case_id} "
        f"{seal} {source}"
    )


PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION = (
    "botauto_profile_combat_range_checkpoint"
)
PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND = (
    "botautoprofilecombatrangecheckpoint status"
)
PROFILE_COMBAT_RANGE_HAZARD_SOURCES = frozenset({
    "adaptive_raid_trash",
    "shared_hazard_movement",
})


def profile_combat_range_checkpoint_arm_command(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
    target_guid: int | None,
) -> str | None:
    """Build the authenticated arm command for the generic range fixture."""

    if recurrence_admission is None and actor_guid is None and target_guid is None:
        return None
    if not isinstance(recurrence_admission, dict):
        raise ValueError(
            "profile_combat_range_checkpoint_verified_admission_missing"
        )
    try:
        _profile_combat_range_checkpoint_contract(
            recurrence_admission,
            label="profile_combat_range_checkpoint_verified_admission",
        )
    except RecurrenceAdmissionError as error:
        raise ValueError(
            "profile_combat_range_checkpoint_verified_admission_invalid"
        ) from error
    seal = recurrence_admission.get("checkpoint_seal_sha256")
    case_id = recurrence_admission.get("checkpoint_case_id")
    source = recurrence_admission.get("source_commit")
    admitted_actor = recurrence_admission.get("checkpoint_actor_guid")
    admitted_target = recurrence_admission.get("checkpoint_target_guid")
    if (
        recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != FIXTURE_EXPANSION_PURPOSE
        or recurrence_admission.get("checkpoint_fixture_id")
            != PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
        or not isinstance(case_id, str) or not case_id
        or not isinstance(actor_guid, int) or isinstance(actor_guid, bool)
        or actor_guid <= 0
        or admitted_actor != actor_guid
        or not isinstance(target_guid, int) or isinstance(target_guid, bool)
        or target_guid <= 0
        or admitted_target != target_guid
        or not isinstance(seal, str) or not re.fullmatch(r"[0-9a-f]{64}", seal)
        or not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source)
    ):
        raise ValueError(
            "profile_combat_range_checkpoint_verified_admission_invalid"
        )
    return (
        "botautoprofilecombatrangecheckpoint arm "
        f"{actor_guid} {target_guid} {case_id} {seal} {source}"
    )


def _profile_checkpoint_nonzero_hex(value: object) -> bool:
    return (
        isinstance(value, str)
        and re.fullmatch(r"[0-9a-f]+", value) is not None
        and int(value, 16) != 0
    )


def _profile_checkpoint_nonnegative_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def profile_combat_range_checkpoint_terminal_rejections(
    row: object, *, actor_guid: int, target_guid: int, case_id: str,
    seal_sha256: str, source_commit: str,
    checkpoint_generation: int | None = None,
    attempt_id: int | None = None, wipe_generation: int | None = None,
    route_generation: int | None = None, target_map_id: int | None = None,
    target_instance_id: int | None = None,
) -> list[str]:
    """Validate one authenticated terminal status projection fail-closed."""

    if not isinstance(row, dict):
        return ["profile_combat_range_checkpoint_status_unavailable"]
    if row.get("action") != PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION:
        return ["profile_combat_range_checkpoint_status_action_invalid"]
    identity = (
        row.get("authority") == PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY
        and row.get("fixture_id") == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID
        and row.get("case_id") == case_id
        and row.get("seal_sha256") == seal_sha256
        and row.get("source_commit") == source_commit
        and row.get("actor_guid") == actor_guid
        and row.get("target_guid") == target_guid
    )
    if not identity:
        return ["profile_combat_range_checkpoint_status_identity_invalid"]
    if (
        not isinstance(case_id, str) or not case_id
        or not isinstance(seal_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", seal_sha256) is None
        or not isinstance(source_commit, str)
        or re.fullmatch(r"[0-9a-f]{40}", source_commit) is None
    ):
        return ["profile_combat_range_checkpoint_status_identity_invalid"]
    expected_scoped = (
        ("checkpoint_generation", checkpoint_generation),
        ("attempt_id", attempt_id),
        ("wipe_generation", wipe_generation),
        ("route_generation", route_generation),
        ("target_map_id", target_map_id),
        ("target_instance_id", target_instance_id),
    )
    for field, expected in expected_scoped:
        if expected is not None and row.get(field) != expected:
            return ["profile_combat_range_checkpoint_status_scope_invalid"]
    if (
        not _positive_int(row.get("checkpoint_generation"))
        or not _positive_int(row.get("attempt_id"))
        or not isinstance(row.get("wipe_generation"), int)
        or isinstance(row.get("wipe_generation"), bool)
        or row["wipe_generation"] < 0
        or not _profile_checkpoint_nonnegative_int(
            row.get("route_generation")
        )
        or not _profile_checkpoint_nonnegative_int(row.get("target_map_id"))
        or not _profile_checkpoint_nonnegative_int(
            row.get("target_instance_id")
        )
        or row.get("scope_bound") is not True
    ):
        return ["profile_combat_range_checkpoint_status_scope_invalid"]
    if (
        row.get("ok") is not True
        or row.get("stage") != "completed"
        or row.get("terminal") is not True
        or row.get("outcome")
            != "profile_combat_range_checkpoint_boundary_observed"
        or row.get("failure_reason") not in {None, ""}
    ):
        return ["profile_combat_range_checkpoint_status_terminal_invalid"]
    if (
        row.get("candidate_key") != "world.profile_combat_range"
        or row.get("candidate_status") != "attempted"
        or row.get("candidate_reason")
            != "profile_combat_min_range_reconciled"
        or not _profile_checkpoint_nonnegative_int(
            row.get("candidate_trace_index")
        )
        or not _positive_int(row.get("movement_receipt_id"))
        or row.get("movement_committed") is not True
        or row.get("movement_native_submitted") is not True
        or row.get("range_receipt_correlated") is not True
        or row.get("range_diagnostic_target_guid") != target_guid
        or not _positive_int(row.get("decision_timestamp_ms"))
        or not _profile_checkpoint_nonzero_hex(
            row.get("range_intent_fingerprint")
        )
        or not _positive_int(row.get("native_motion_type"))
        or not _positive_int(row.get("native_spline_id"))
        or not _positive_int(row.get("progress_sample_count"))
        or row["progress_sample_count"] < 2
        or row.get("movement_progress_observed") is not True
        or not _positive_int(row.get("range_progress_observed_at_ms"))
        or row["range_progress_observed_at_ms"]
            <= row["decision_timestamp_ms"]
    ):
        return ["profile_combat_range_checkpoint_range_correlation_invalid"]
    if (
        not isinstance(row.get("hazard_candidate_key"), str)
        or not row["hazard_candidate_key"]
        or row["hazard_candidate_key"] == "world.profile_combat_range"
        or not isinstance(row.get("hazard_candidate_source"), str)
        or not row["hazard_candidate_source"]
        or row["hazard_candidate_source"]
            not in PROFILE_COMBAT_RANGE_HAZARD_SOURCES
        or row.get("hazard_candidate_status") != "attempted"
        or not _profile_checkpoint_nonnegative_int(
            row.get("hazard_trace_index")
        )
        or not _positive_int(row.get("hazard_decision_timestamp_ms"))
        or not _positive_int(row.get("hazard_movement_receipt_id"))
        or row["hazard_movement_receipt_id"] == row["movement_receipt_id"]
        or not _profile_checkpoint_nonzero_hex(
            row.get("hazard_intent_fingerprint")
        )
        or not _positive_int(row.get("hazard_progress_sample_count"))
        or row["hazard_progress_sample_count"] < 2
        or row.get("hazard_native_submitted") is not True
        or row.get("hazard_progress_observed") is not True
        or not _positive_int(row.get("hazard_progress_observed_at_ms"))
        or row["hazard_progress_observed_at_ms"]
            <= row["hazard_decision_timestamp_ms"]
        or row["hazard_progress_observed_at_ms"]
            >= row["decision_timestamp_ms"]
        or row["hazard_decision_timestamp_ms"]
            >= row["decision_timestamp_ms"]
        or row.get("hazard_preempted_range") is not True
    ):
        return ["profile_combat_range_checkpoint_hazard_correlation_invalid"]
    if (
        not _positive_int(row.get("cast_spell_id"))
        or row.get("cast_target_guid") != target_guid
        or row.get("cast_retry_observed") is not True
        or not _positive_int(row.get("cast_recorded_at_ms"))
        or row["cast_recorded_at_ms"]
            <= row["range_progress_observed_at_ms"]
        or row.get("cast_before_progress_observed") is not False
    ):
        return ["profile_combat_range_checkpoint_later_cast_invalid"]
    return []


def observe_profile_combat_range_checkpoint_row(
    row: object, **kwargs: Any,
) -> list[str]:
    """Capture-side consumer for the profile checkpoint status command."""

    return profile_combat_range_checkpoint_terminal_rejections(row, **kwargs)


def _observe_profile_combat_range_checkpoint_scheduler_row(
    scheduler: Any, row: dict[str, Any], *, target_guid: int, case_id: str,
) -> list[str]:
    """Consume profile arm/status rows through the generic hold scheduler."""

    def next_status_command() -> list[str]:
        scheduler.command_transcript.append(
            PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
        )
        return [PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND]

    expected = {
        "action": PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION,
        "authority": PROFILE_COMBAT_RANGE_CHECKPOINT_AUTHORITY,
        "fixture_id": PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID,
        "case_id": case_id,
        "seal_sha256": scheduler.identity.seal_sha256,
        "source_commit": scheduler.identity.source_commit,
        "actor_guid": scheduler.identity.actor_guid,
        "target_guid": target_guid,
    }
    if not isinstance(row, dict) or any(
        row.get(field) != value for field, value in expected.items()
    ):
        return scheduler._fail(
            "profile_combat_range_checkpoint_status_identity_invalid"
        )

    state = getattr(scheduler, "_profile_checkpoint_state", None)
    if not isinstance(state, dict):
        state = {"checkpoint_generation": None, "target_map_id": None}
        scheduler._profile_checkpoint_state = state
    generation = row.get("checkpoint_generation")
    if not _positive_int(generation):
        return scheduler._fail(
            "profile_combat_range_checkpoint_status_scope_invalid"
        )
    expected_generation = state.get("checkpoint_generation")
    if expected_generation is None:
        state["checkpoint_generation"] = generation
    elif generation != expected_generation:
        return scheduler._fail(
            "profile_combat_range_checkpoint_status_scope_invalid"
        )

    native_scope = scheduler._native_scope or {}
    runtime_scope = scheduler.runtime_scope
    scope_pairs = (
        ("attempt_id", native_scope.get("attempt_id")),
        ("route_generation", scheduler.identity.route_generation),
        ("wipe_generation", (
            runtime_scope.wipe_generation if runtime_scope is not None else None
        )),
        ("target_instance_id", (
            runtime_scope.instance_id if runtime_scope is not None else None
        )),
    )
    if any(expected is not None and row.get(field) != expected
           for field, expected in scope_pairs):
        return scheduler._fail(
            "profile_combat_range_checkpoint_status_scope_invalid"
        )
    target_map_id = row.get("target_map_id")
    if row.get("scope_bound") is True:
        if not _profile_checkpoint_nonnegative_int(target_map_id) or not target_map_id:
            return scheduler._fail(
                "profile_combat_range_checkpoint_status_scope_invalid"
            )
        prior_map = state.get("target_map_id")
        if prior_map is None:
            state["target_map_id"] = target_map_id
        elif prior_map != target_map_id:
            return scheduler._fail(
                "profile_combat_range_checkpoint_status_scope_invalid"
            )

    if scheduler.phase == "awaiting_arm_ack":
        if (
            row.get("ok") is not True
            or row.get("stage") != "armed"
            or row.get("terminal") is not False
            or row.get("failure_reason") not in {None, ""}
        ):
            return scheduler._fail(
                "profile_combat_range_checkpoint_status_arm_ack_invalid"
            )
        scheduler._arm_ack_count = 1
        scheduler._record("arm_ack", row, {})
        scheduler.phase = "awaiting_terminal"
        return next_status_command()

    if scheduler.phase != "awaiting_terminal":
        return scheduler._fail(
            "profile_combat_range_checkpoint_duplicate_or_stale_receipt"
        )
    if row.get("terminal") is not True:
        if (
            row.get("ok") is not True
            or row.get("stage") not in {
                "armed", "range_observed", "progress_observed",
            }
            or row.get("failure_reason") not in {None, ""}
        ):
            return scheduler._fail(
                "profile_combat_range_checkpoint_status_progress_invalid"
            )
        return next_status_command()

    rejections = observe_profile_combat_range_checkpoint_row(
        row,
        actor_guid=scheduler.identity.actor_guid,
        target_guid=target_guid,
        case_id=case_id,
        seal_sha256=scheduler.identity.seal_sha256,
        source_commit=scheduler.identity.source_commit,
        checkpoint_generation=expected_generation,
        attempt_id=native_scope.get("attempt_id"),
        wipe_generation=(
            runtime_scope.wipe_generation if runtime_scope is not None else None
        ),
        route_generation=scheduler.identity.route_generation,
        target_map_id=state.get("target_map_id"),
        target_instance_id=(
            runtime_scope.instance_id if runtime_scope is not None else None
        ),
    )
    if rejections:
        return scheduler._fail(rejections[0])
    scheduler._terminal_count = 1
    scheduler._terminal_stage = row["stage"]
    scheduler._terminal_observation = copy.deepcopy(row)
    scheduler.receipt_transcript.append({
        "kind": "checkpoint_terminal_success",
        "phase": "completed",
        "checkpoint_stage": row.get("stage"),
        "checkpoint_generation": row.get("checkpoint_generation"),
        "payload_sha256": _canonical_object_sha256(row),
    })
    scheduler.phase = "complete"
    return []


def magmaw_transfer_checkpoint_arm_command(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
) -> str | None:
    """Build the coordinate-free command for the one sealed map-bound case."""

    if recurrence_admission is None and actor_guid is None:
        return None
    if not isinstance(recurrence_admission, dict):
        raise ValueError("magmaw_transfer_checkpoint_verified_admission_missing")
    try:
        _magmaw_transfer_checkpoint_contract(
            recurrence_admission,
            label="magmaw_transfer_checkpoint_verified_admission",
        )
    except RecurrenceAdmissionError as error:
        raise ValueError(
            "magmaw_transfer_checkpoint_verified_admission_invalid"
        ) from error
    seal = recurrence_admission.get("checkpoint_seal_sha256")
    source = recurrence_admission.get("source_commit")
    if (
        recurrence_admission.get("valid") is not True
        or recurrence_admission.get("purpose") != FIXTURE_EXPANSION_PURPOSE
        or recurrence_admission.get("checkpoint_fixture_id")
            != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or recurrence_admission.get("checkpoint_case_id")
            != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or actor_guid != MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        or isinstance(actor_guid, bool)
        or not isinstance(seal, str) or not re.fullmatch(r"[0-9a-f]{64}", seal)
        or not isinstance(source, str) or not re.fullmatch(r"[0-9a-f]{40}", source)
    ):
        raise ValueError("magmaw_transfer_checkpoint_verified_admission_invalid")
    return (
        "botautomagmawtransfercheckpoint arm "
        f"{actor_guid} {MAGMAW_TRANSFER_CHECKPOINT_CASE_ID} {seal} {source}"
    )


NATIVE_PATH_CHECKPOINT_TERMINAL_OUTCOMES = {
    "native_path_checkpoint_no_launch_verified",
    "native_path_checkpoint_launch_progress_verified",
}
NATIVE_PATH_CHECKPOINT_TERMINAL_FAILURE_SHAPES = {
    "native_path_checkpoint_scope_or_timeout": {
        (0, 0, False, False),
        (1, 0, True, False),
        (1, 1, True, True),
    },
    "native_path_checkpoint_stage_submit_failed": {
        (1, 0, False, False),
    },
    "native_path_checkpoint_stage_receipt_missing": {
        (1, 0, False, False),
        (1, 0, True, False),
    },
    "native_path_checkpoint_stage_identity_failed": {
        (1, 0, True, False),
    },
    "native_path_checkpoint_hazard_identity_failed": {
        (1, 1, True, False),
        (1, 1, True, True),
    },
    "native_path_checkpoint_outcome_mismatch": {
        (1, 1, True, True),
    },
    "native_path_checkpoint_launch_progress_failed": {
        (1, 1, True, True),
    },
}
NATIVE_PATH_CHECKPOINT_AUTHORITY = (
    "sealed_compiled_map669_native_path_observation_only"
)


def native_path_checkpoint_lifecycle_rejections(
    hold: dict[str, Any], *, case_id: str,
) -> list[str]:
    """Validate the terminal native checkpoint projection exactly."""

    lifecycle = hold.get("checkpoint_lifecycle")
    if not isinstance(lifecycle, dict):
        return ["controller_route_hold_checkpoint_lifecycle_missing"]
    if (
        lifecycle.get("stage") != "completed"
        or lifecycle.get("terminal") is not True
        or lifecycle.get("case_id") != case_id
        or lifecycle.get("stage_submit_count") != 1
        or lifecycle.get("hazard_submit_count") != 1
        or not _positive_int(lifecycle.get("stage_receipt_id"))
        or not _positive_int(lifecycle.get("hazard_receipt_id"))
        or lifecycle.get("outcome")
            not in NATIVE_PATH_CHECKPOINT_TERMINAL_OUTCOMES
    ):
        return ["controller_route_hold_checkpoint_lifecycle_invalid"]
    return []


def _native_path_checkpoint_terminal_failure_rejections(
    scheduler: Any,
    row: dict[str, Any],
    hold: dict[str, Any],
    lifecycle: dict[str, Any],
    *,
    case_id: str,
) -> list[str]:
    """Validate a native failed terminal without treating it as success."""

    hold_rejections = scheduler._hold_rejections(hold)
    stage_count = lifecycle.get("stage_submit_count")
    hazard_count = lifecycle.get("hazard_submit_count")
    stage_receipt = lifecycle.get("stage_receipt_id")
    hazard_receipt = lifecycle.get("hazard_receipt_id")
    values = (stage_count, hazard_count, stage_receipt, hazard_receipt)
    if (
        row.get("ok") is not False
        or scheduler.phase != "awaiting_terminal"
        or hold.get("phase") != "checkpoint_terminal"
        or hold.get("checkpoint_terminal") is not True
        or hold.get("checkpoint_identity_preserved") is not True
        or hold.get("checkpoint_stage") != "failed"
        or hold_rejections
        or lifecycle.get("stage") != "failed"
        or lifecycle.get("terminal") is not True
        or lifecycle.get("case_id") != case_id
        or any(
            not isinstance(value, int) or isinstance(value, bool) or value < 0
            for value in values
        )
    ):
        return ["controller_route_hold_checkpoint_lifecycle_invalid"]
    shape = (
        stage_count, hazard_count,
        bool(stage_receipt), bool(hazard_receipt),
    )
    allowed_shapes = NATIVE_PATH_CHECKPOINT_TERMINAL_FAILURE_SHAPES.get(
        lifecycle.get("outcome")
    )
    if allowed_shapes is None or shape not in allowed_shapes:
        return ["controller_route_hold_checkpoint_lifecycle_invalid"]
    planner = row.get("movement_planner")
    planner_result = planner.get("planner") if isinstance(planner, dict) else None
    if (
        not isinstance(planner_result, dict)
        or not isinstance(planner.get("available"), bool)
    ):
        return ["controller_route_hold_checkpoint_planner_missing"]
    if stage_count and (
        planner.get("available") is not True
        or any(
                not isinstance(planner_result.get(field), str)
                or not planner_result.get(field)
                for field in ("gate", "result", "reason")
        )
    ):
        return ["controller_route_hold_checkpoint_planner_missing"]
    return []


def observe_native_path_checkpoint_row(
    scheduler: Any, row: dict[str, Any],
) -> list[str]:
    """Consume native arm/status rows through the generic hold lifecycle."""

    hold = scheduler._hold_from_checkpoint(row)
    if hold is None:
        return scheduler._fail(
            "controller_route_hold_checkpoint_receipt_missing"
        )
    lifecycle = hold.get("checkpoint_lifecycle")
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    mirrored_fields = (
        "stage", "terminal", "stage_submit_count", "hazard_submit_count",
        "stage_receipt_id", "hazard_receipt_id", "outcome",
    )
    if (
        row.get("authority") != NATIVE_PATH_CHECKPOINT_AUTHORITY
        or row.get("actor_guid") != scheduler.identity.actor_guid
        or row.get("fixture_id") != scheduler.identity.fixture_id
        or row.get(scheduler._checkpoint_receipt_field)
            != scheduler._checkpoint_receipt_value
        or any(row.get(field) != lifecycle.get(field)
               for field in mirrored_fields)
    ):
        return scheduler._fail(
            "controller_route_hold_checkpoint_receipt_identity_invalid"
        )
    if scheduler.phase == "awaiting_arm_ack":
        commands = scheduler._observe_arm_ack(row)
    elif scheduler.phase == "awaiting_terminal":
        if row.get("ok") is False:
            rejections = _native_path_checkpoint_terminal_failure_rejections(
                scheduler, row, hold, lifecycle,
                case_id=scheduler._checkpoint_receipt_value,
            )
            if rejections:
                return scheduler._fail(rejections[0])
            observation = {
                "ok": row.get("ok"),
                "stage": row.get("stage"),
                "terminal": row.get("terminal"),
                "outcome": row.get("outcome"),
                "movement_planner": row.get("movement_planner"),
            }
            scheduler._terminal_count = 1
            scheduler._terminal_stage = hold["checkpoint_stage"]
            scheduler._terminal_lifecycle = copy.deepcopy(lifecycle)
            scheduler._terminal_observation = copy.deepcopy(observation)
            scheduler._record("checkpoint_terminal_failure", observation, hold)
            scheduler.phase = "checkpoint_terminal_failed"
            commands = []
        elif row.get("ok") is not True:
            return scheduler._fail(
                "controller_route_hold_checkpoint_lifecycle_invalid"
            )
        elif hold.get("phase") == "armed":
            commands = []
        else:
            commands = scheduler._observe_checkpoint_terminal(hold)
    else:
        return scheduler._observe_arm_ack(row)
    if (
        scheduler.phase == "awaiting_terminal"
        and not scheduler.failed
        and not commands
    ):
        command = scheduler._checkpoint_terminal_status_command
        scheduler.command_transcript.append(command)
        return [command]
    return commands


MAGMAW_TRANSFER_START = (-345.872009, -224.343994, 193.126999)
MAGMAW_TRANSFER_DESTINATION = (-345.872009, -218.343994, 193.126999)
MAGMAW_TRANSFER_EPISODE_GENERATION = 17
MAGMAW_TRANSFER_TASK_GENERATION = 31
MAGMAW_TRANSFER_LEGACY_GENERATION = 43
MAGMAW_TRANSFER_MAX_PROGRESS_SAMPLES = 300
MAGMAW_TRANSFER_ARRIVAL_TOLERANCE = 4.0
MAGMAW_TRANSFER_ARRIVAL_TOLERANCE_Z = 0.5
MAGMAW_TRANSFER_FLOOR_TOLERANCE = 4.0


def _exact_position(value: object, expected: tuple[float, float, float]) -> bool:
    if not isinstance(value, dict) or set(value) != {"x", "y", "z"}:
        return False
    return all(
        isinstance(value.get(axis), (int, float))
        and not isinstance(value.get(axis), bool)
        and math.isfinite(float(value[axis]))
        and math.isclose(float(value[axis]), target, abs_tol=0.0001)
        for axis, target in zip(("x", "y", "z"), expected)
    )


def _exact_magmaw_scope_key(
    scheduler: Any, row: dict[str, Any], hold: dict[str, Any],
) -> bool:
    """Bind the compiled task scope to the preserved controller attempt."""

    value = row.get("scope_key")
    if not isinstance(value, str):
        return False
    parts = value.split(":")
    if len(parts) != 8:
        return False
    runtime_scope = scheduler.runtime_scope
    if runtime_scope is None:
        return False
    expected = (
        f"{hold.get('cohort_id')}:{hold.get('attempt_id')}:"
        f"{runtime_scope.wipe_generation}:{hold.get('route_generation')}:"
        f"{hold.get('route_node_id')}:669:{runtime_scope.instance_id}:"
        "magmaw_transfer_lane_checkpoint"
    )
    return value == expected


def _exact_same_floor_arrival(value: object) -> bool:
    """Require the final same-floor sample to prove logical task arrival."""

    if not isinstance(value, dict) or set(value) != {"x", "y", "z", "floor_z"}:
        return False
    coordinates = [value.get(axis) for axis in ("x", "y", "z", "floor_z")]
    if any(
        not isinstance(item, (int, float))
        or isinstance(item, bool)
        or not math.isfinite(float(item))
        for item in coordinates
    ):
        return False
    x, y, z, floor_z = (float(item) for item in coordinates)
    destination_x, destination_y, destination_z = MAGMAW_TRANSFER_DESTINATION
    return (
        math.hypot(x - destination_x, y - destination_y)
        <= MAGMAW_TRANSFER_ARRIVAL_TOLERANCE
        and abs(z - destination_z) <= MAGMAW_TRANSFER_ARRIVAL_TOLERANCE_Z
        and abs(floor_z - z) <= MAGMAW_TRANSFER_FLOOR_TOLERANCE
    )


def _magmaw_transfer_checkpoint_identity_rejections(
    scheduler: Any, row: dict[str, Any], hold: dict[str, Any],
) -> list[str]:
    lifecycle = hold.get("checkpoint_lifecycle")
    comparison = hold.get("config_identity_comparison")
    reasons = scheduler._hold_rejections(hold)
    exact_config_bools = (
        "accepted", "fixture_configured_present", "fixture_requested_present",
        "fixture_matches", "seal_configured_present", "seal_requested_present",
        "seal_matches", "source_configured_present", "source_requested_present",
        "source_matches", "binary_revision_present",
        "binary_revision_format_valid", "binary_revision_matches_source",
    )
    if (
        row.get("action") != "botauto_magmaw_transfer_lane_checkpoint"
        or row.get("terminal_kind") != "fixture_checkpoint"
        or row.get("certifies_gameplay_success") is not False
        or row.get("certifies_boss_fidelity") is not False
        or row.get("authority") != MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY
        or row.get("fixture_id") != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or row.get("case_id") != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or row.get("actor_guid") != MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        or row.get("task_authority_enabled") is not False
        or row.get("episode_generation")
            != MAGMAW_TRANSFER_EPISODE_GENERATION
        or row.get("task_generation") != MAGMAW_TRANSFER_TASK_GENERATION
        or row.get("legacy_generation") != MAGMAW_TRANSFER_LEGACY_GENERATION
        or not isinstance(lifecycle, dict)
        or lifecycle.get("case_id") != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or not isinstance(comparison, dict)
        or comparison.get("failure_field") != "none"
        or any(comparison.get(field) is not True for field in exact_config_bools)
        or comparison.get("configured_source_length") != 40
        or comparison.get("requested_source_length") != 40
        or comparison.get("binary_revision_length") not in {12, 40}
    ):
        reasons.append("magmaw_transfer_checkpoint_identity_invalid")
    return list(dict.fromkeys(reasons))


def _magmaw_transfer_checkpoint_terminal_rejections(
    scheduler: Any, row: dict[str, Any], hold: dict[str, Any],
) -> list[str]:
    reasons = _magmaw_transfer_checkpoint_identity_rejections(
        scheduler, row, hold,
    )
    lifecycle = hold.get("checkpoint_lifecycle")
    lifecycle = lifecycle if isinstance(lifecycle, dict) else {}
    stage = row.get("stage")
    mirrored = (
        "stage", "terminal", "queue_count", "candidate_attempt_count",
        "native_submission_count", "planner_receipt_id", "progress_samples",
        "outcome",
    )
    if (
        row.get("terminal") is not True
        or stage not in {"completed", "failed"}
        or hold.get("phase") != "checkpoint_terminal"
        or hold.get("checkpoint_terminal") is not True
        or hold.get("checkpoint_identity_preserved") is not True
        or hold.get("checkpoint_stage") != stage
        or any(row.get(field) != lifecycle.get(field) for field in mirrored)
    ):
        reasons.append("magmaw_transfer_checkpoint_terminal_lifecycle_invalid")
        return list(dict.fromkeys(reasons))
    if stage == "completed":
        progress_samples = row.get("progress_samples")
        decreasing_samples = row.get("decreasing_progress_samples")
        wrong_floor_samples = row.get("wrong_floor_samples")
        counts_are_ints = all(
            isinstance(value, int) and not isinstance(value, bool)
            for value in (
                progress_samples, decreasing_samples, wrong_floor_samples,
            )
        )
        same_floor_samples = (
            progress_samples - wrong_floor_samples if counts_are_ints else -1
        )
        if (
            row.get("ok") is not True
            or row.get("fixture_gate_passed") is not True
            or row.get("queue_count") != 1
            or row.get("candidate_attempt_count") != 1
            or row.get("native_submission_count") != 1
            or not _positive_int(row.get("planner_receipt_id"))
            or not _positive_int(row.get("spline_id"))
            or row.get("motion_master_slot") != 1
            or row.get("motion_master_generator_type") != 8
            or not isinstance(row.get("candidate_key"), str)
            or not row["candidate_key"]
            or row.get("candidate_key") != row.get("planner_candidate_key")
            or not _exact_magmaw_scope_key(scheduler, row, hold)
            or not counts_are_ints
            or progress_samples < 2
            or progress_samples > MAGMAW_TRANSFER_MAX_PROGRESS_SAMPLES
            or wrong_floor_samples < 0
            or wrong_floor_samples > progress_samples
            or decreasing_samples < 2
            or decreasing_samples > same_floor_samples
            or row.get("task_state") != "succeeded"
            or row.get("outcome") != "magmaw_transfer_checkpoint_completed"
            or not _exact_position(
                row.get("requested_destination"), MAGMAW_TRANSFER_DESTINATION,
            )
            or not _exact_position(row.get("actor_start"), MAGMAW_TRANSFER_START)
            or not _exact_same_floor_arrival(row.get("actor_last_same_floor"))
        ):
            reasons.append("magmaw_transfer_checkpoint_success_payload_invalid")
    else:
        counts = (
            row.get("queue_count"), row.get("candidate_attempt_count"),
            row.get("native_submission_count"), row.get("planner_receipt_id"),
            row.get("progress_samples"),
            row.get("decreasing_progress_samples"),
            row.get("wrong_floor_samples"),
        )
        if (
            row.get("ok") is not False
            or row.get("fixture_gate_passed") is not False
            or any(
                not isinstance(value, int) or isinstance(value, bool) or value < 0
                for value in counts
            )
            or not isinstance(row.get("outcome"), str)
            or not row["outcome"]
            or row.get("outcome") == "magmaw_transfer_checkpoint_completed"
        ):
            reasons.append("magmaw_transfer_checkpoint_failure_payload_invalid")
    return list(dict.fromkeys(reasons))


def observe_magmaw_transfer_checkpoint_row(
    scheduler: Any, row: dict[str, Any],
) -> list[str]:
    """Consume only the dedicated map-bound checkpoint response."""

    hold = scheduler._hold_from_checkpoint(row)
    if hold is None:
        return scheduler._fail(
            "controller_route_hold_checkpoint_receipt_missing"
        )
    if scheduler.phase == "awaiting_arm_ack":
        rejections = _magmaw_transfer_checkpoint_identity_rejections(
            scheduler, row, hold,
        )
        if (
            row.get("ok") is not True
            or row.get("terminal") is not False
            or row.get("stage") != "armed"
            or row.get("fixture_gate_passed") is not False
        ):
            rejections.append("magmaw_transfer_checkpoint_arm_ack_invalid")
        commands = scheduler._fail(rejections[0]) if rejections \
            else scheduler._observe_arm_ack(row)
    elif scheduler.phase == "awaiting_terminal":
        if row.get("terminal") is not True:
            if (
                row.get("ok") is not True
                or row.get("stage") not in {
                    "armed", "queued", "native_submitted", "progressing",
                }
                or _magmaw_transfer_checkpoint_identity_rejections(
                    scheduler, row, hold,
                )
            ):
                return scheduler._fail(
                    "magmaw_transfer_checkpoint_progress_payload_invalid"
                )
            commands = []
        else:
            rejections = _magmaw_transfer_checkpoint_terminal_rejections(
                scheduler, row, hold,
            )
            if rejections:
                return scheduler._fail(rejections[0])
            scheduler._terminal_count = 1
            scheduler._terminal_stage = row["stage"]
            scheduler._terminal_lifecycle = copy.deepcopy(
                hold["checkpoint_lifecycle"]
            )
            scheduler._terminal_observation = copy.deepcopy(row)
            scheduler._record(
                "checkpoint_terminal_success"
                if row["stage"] == "completed"
                else "checkpoint_terminal_failure",
                row, hold,
            )
            scheduler.phase = (
                "complete" if row["stage"] == "completed"
                else "checkpoint_terminal_failed"
            )
            commands = []
    else:
        return scheduler._fail(
            "magmaw_transfer_checkpoint_duplicate_or_stale_receipt"
        )
    if (
        scheduler.phase == "awaiting_terminal"
        and not scheduler.failed
        and not commands
    ):
        command = scheduler._checkpoint_terminal_status_command
        scheduler.command_transcript.append(command)
        return [command]
    return commands


def checkpoint_controller_dialect(
    recurrence_admission: dict[str, Any] | None,
    actor_guid: int | None,
) -> dict[str, Any] | None:
    """Select one verified fixture-expansion checkpoint dialect."""

    if recurrence_admission is None and actor_guid is None:
        return None
    if not isinstance(recurrence_admission, dict):
        raise ValueError("checkpoint_controller_verified_admission_missing")
    fixture_id = recurrence_admission.get("checkpoint_fixture_id")
    if fixture_id is None:
        try:
            requests = _fixture_expansion_contract(
                recurrence_admission,
                label="checkpoint_free_fixture_expansion",
            )
        except RecurrenceAdmissionError as error:
            raise ValueError(
                "checkpoint_free_fixture_expansion_invalid"
            ) from error
        if (
            recurrence_admission.get("valid") is not True
            or recurrence_admission.get("purpose")
                != FIXTURE_EXPANSION_PURPOSE
            or not requests
            or actor_guid is not None
            or recurrence_admission.get("checkpoint_seal_sha256") is not None
            or recurrence_admission.get("checkpoint_case_id") is not None
        ):
            raise ValueError("checkpoint_free_fixture_expansion_invalid")
        return None
    if fixture_id == CHAINWIELDER_CHECKPOINT_FIXTURE_ID:
        return {
            "fixture_id": fixture_id,
            "arm_command": chainwielder_checkpoint_arm_command(
                recurrence_admission, actor_guid,
            ),
            "scheduler_kwargs": {},
        }
    if fixture_id == MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID:
        arm_command = magmaw_transfer_checkpoint_arm_command(
            recurrence_admission, actor_guid,
        )
        return {
            "fixture_id": fixture_id,
            "arm_command": arm_command,
            "scheduler_kwargs": {
                "checkpoint_action": (
                    "botauto_magmaw_transfer_lane_checkpoint"
                ),
                "checkpoint_arm_command": arm_command,
                "checkpoint_receipt_field": "case_id",
                "checkpoint_receipt_value": MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
                "lifecycle_rejections": lambda _hold: [],
                "checkpoint_observer": observe_magmaw_transfer_checkpoint_row,
                "checkpoint_terminal_status_command": (
                    "botautomagmawtransfercheckpoint status"
                ),
                "release_after_terminal": False,
                "checkpoint_terminal_from_status": False,
                "runtime_scope_required": True,
            },
        }
    if fixture_id == PROFILE_COMBAT_RANGE_CHECKPOINT_FIXTURE_ID:
        target_guid = recurrence_admission.get("checkpoint_target_guid")
        arm_command = profile_combat_range_checkpoint_arm_command(
            recurrence_admission, actor_guid, target_guid,
        )
        case_id = recurrence_admission.get("checkpoint_case_id")
        return {
            "fixture_id": fixture_id,
            "arm_command": arm_command,
            "scheduler_kwargs": {
                "checkpoint_action": PROFILE_COMBAT_RANGE_CHECKPOINT_ACTION,
                "checkpoint_arm_command": arm_command,
                "checkpoint_receipt_field": "fixture_id",
                "checkpoint_receipt_value": fixture_id,
                "checkpoint_observer": (
                    lambda scheduler, row: (
                        _observe_profile_combat_range_checkpoint_scheduler_row(
                            scheduler, row, target_guid=target_guid,
                            case_id=case_id,
                        )
                    )
                ),
                "checkpoint_terminal_status_command": (
                    PROFILE_COMBAT_RANGE_CHECKPOINT_STATUS_COMMAND
                ),
                "release_after_terminal": False,
                "checkpoint_terminal_from_status": False,
                "runtime_scope_required": True,
            },
        }
    if fixture_id == NATIVE_PATH_CHECKPOINT_FIXTURE_ID:
        arm_command = native_path_checkpoint_arm_command(
            recurrence_admission, actor_guid,
        )
        case_id = recurrence_admission.get("checkpoint_case_id")
        return {
            "fixture_id": fixture_id,
            "arm_command": arm_command,
            "scheduler_kwargs": {
                "checkpoint_action": "botauto_native_path_checkpoint",
                "checkpoint_arm_command": arm_command,
                "checkpoint_receipt_field": "case_id",
                "checkpoint_receipt_value": case_id,
                "lifecycle_rejections": lambda hold: (
                    native_path_checkpoint_lifecycle_rejections(
                        hold, case_id=case_id,
                    )
                ),
                "checkpoint_observer": observe_native_path_checkpoint_row,
                "checkpoint_terminal_status_command": (
                    "botautonativepathcheckpoint status"
                ),
                "release_after_terminal": False,
            },
        }
    raise ValueError("checkpoint_controller_fixture_unsupported")


def chainwielder_checkpoint_pre_route_readiness(
    status: dict[str, Any],
    *,
    recurrence_admission: dict[str, Any] | None,
    checkpoint_arm_command: str | None,
    actor_guid: int | None,
    profile_name: str,
    scenario_id: str,
    expected_route_manifest_sha256: str | None,
) -> tuple[bool, list[str], dict[str, Any]]:
    """Validate the immutable admission boundary before route generation two."""

    reasons: list[str] = []
    try:
        expected_command = chainwielder_checkpoint_arm_command(
            recurrence_admission, actor_guid,
        )
    except ValueError as error:
        reasons.append(str(error))
        expected_command = None
    if expected_command is None or checkpoint_arm_command != expected_command:
        reasons.append("checkpoint_arm_command_identity_mismatch")
    runtime = status.get("raid_runtime")
    if not isinstance(runtime, dict):
        reasons.append("checkpoint_runtime_missing")
        return False, reasons, {"accepted": False, "identity_sha256": None}
    receipt = runtime.get("admission_receipt")
    receipt = receipt if isinstance(receipt, dict) else {}
    roster = runtime.get("roster") if isinstance(runtime.get("roster"), list) else []
    roster_rows = [row for row in roster if isinstance(row, dict)]
    route_progress = runtime.get("route_progress")
    route_progress = route_progress if isinstance(route_progress, dict) else {}
    actor_rows = [row for row in roster_rows if row.get("guid") == actor_guid]
    reasons.extend(_watchdog_scope_rejections(status, profile_name=profile_name))
    reasons.extend(f"checkpoint_{reason}" for reason in _roster_rejections(runtime, profile_name))
    expected_receipt = {
        "attempt_id": runtime.get("attempt_id"),
        "server_epoch": runtime.get("server_epoch"),
        "group_guid": runtime.get("group_guid"),
        "instance_id": runtime.get("instance_id"),
        "scenario_id": scenario_id,
        "runtime_profile": profile_name,
        "route_manifest_sha256": expected_route_manifest_sha256,
        "entrance_map_id": runtime.get("map_id"),
        "profile_generation": runtime.get("profile_generation"),
        "profile_content_hash": runtime.get("profile_content_hash"),
        "leader_guid": runtime.get("leader_guid"),
    }
    if (
        runtime.get("admission_phase") != "active"
        or runtime.get("server_provisioning_complete") is not True
        or runtime.get("bot_actions_enabled") is not True
    ):
        reasons.append("checkpoint_admission_not_active")
    if route_progress.get("generation") != 1:
        reasons.append("checkpoint_route_not_pre_generation_two")
    if (
        not _positive_int(receipt.get("committed_at_ms"))
        or receipt.get("bot_actions_enabled_at_commit") is not True
        or receipt.get("all_current_gear_matches_admission") is not True
        or any(receipt.get(key) != value for key, value in expected_receipt.items())
        or not isinstance(expected_route_manifest_sha256, str)
        or not re.fullmatch(r"[0-9a-f]{64}", expected_route_manifest_sha256)
    ):
        reasons.append("checkpoint_admission_identity_mismatch")
    if len(actor_rows) != 1:
        reasons.append("checkpoint_actor_identity_missing")

    identity_projection = {
        "cohort_id": status.get("cohort_id"),
        "active_profile": status.get("active_profile"),
        "runtime_identity": {field: runtime.get(field) for field in IDENTITY_FIELDS},
        "roster_identity": _roster_binding_identity(roster_rows),
        "admission_receipt": receipt,
        "actor_guid": actor_guid,
    }
    identity_sha256 = _canonical_object_sha256(identity_projection) if not reasons else None
    facts = {
        "accepted": not reasons,
        "actor_guid": actor_guid,
        "route_generation": route_progress.get("generation"),
        "evidence_sequence": runtime.get("evidence_sequence"),
        "identity_sha256": identity_sha256,
    }
    return not reasons, list(dict.fromkeys(reasons)), facts


def _initialize_chainwielder_checkpoint_arm_gate(
    state: dict[str, Any],
) -> None:
    defaults = {
        "schema": "chainwielder_checkpoint_pre_route_arm_gate_v1",
        "required_stable_statuses": 2,
        "consecutive_stable_statuses": 0,
        "last_identity_sha256": None,
        "last_readiness": None,
        "pre_route_probe_batches": 0,
        "pre_route_probe_command_count": 0,
        "gate_open": False,
        "command_sent": False,
        "emission_count": 0,
        "emission": None,
    }
    for key, value in defaults.items():
        state.setdefault(key, value)


def observe_chainwielder_checkpoint_arm_gate(
    state: dict[str, Any],
    status: dict[str, Any],
    *,
    process: Any,
    recurrence_admission: dict[str, Any] | None,
    checkpoint_arm_command: str,
    actor_guid: int,
    profile_name: str,
    scenario_id: str,
    expected_route_manifest_sha256: str | None,
) -> dict[str, Any]:
    """Observe two stable pre-route statuses and emit the arm command once."""

    _initialize_chainwielder_checkpoint_arm_gate(state)
    ready, rejections, facts = chainwielder_checkpoint_pre_route_readiness(
        status,
        recurrence_admission=recurrence_admission,
        checkpoint_arm_command=checkpoint_arm_command,
        actor_guid=actor_guid,
        profile_name=profile_name,
        scenario_id=scenario_id,
        expected_route_manifest_sha256=expected_route_manifest_sha256,
    )
    if ready:
        if facts["identity_sha256"] == state["last_identity_sha256"]:
            state["consecutive_stable_statuses"] += 1
        else:
            state["consecutive_stable_statuses"] = 1
        state["last_identity_sha256"] = facts["identity_sha256"]
    else:
        state["consecutive_stable_statuses"] = 0
        state["last_identity_sha256"] = None
    state["last_readiness"] = {**facts, "rejections": rejections}
    state["gate_open"] = (
        ready
        and state["consecutive_stable_statuses"]
        >= state["required_stable_statuses"]
    )
    if state["gate_open"] and state["emission_count"] == 0:
        process.stdin.write((checkpoint_arm_command + "\n").encode())
        process.stdin.flush()
        state["emission_count"] = 1
        state["command_sent"] = True
        state["emission"] = {
            "actor_guid": actor_guid,
            "admission_sha256": recurrence_admission.get("admission_sha256")
                if isinstance(recurrence_admission, dict) else None,
            "identity_sha256": facts["identity_sha256"],
            "evidence_sequence": facts["evidence_sequence"],
            "route_generation": facts["route_generation"],
        }
    return state


def chainwielder_checkpoint_monitor_commands(
    scheduled_commands: list[str],
    *,
    checkpoint_arm_command: str | None,
    checkpoint_arm_gate: dict[str, Any],
) -> list[str]:
    """Add one adjacent status probe while the pre-route arm gate is pending.

    The normal five-second heartbeat allowed the validation route to advance
    from generation one to generation two between the two identity receipts
    required by the arm gate. In fixture-expansion mode, issue the second
    status in the same console batch as the scheduled heartbeat. The existing
    readiness gate still validates both responses independently and remains
    the only authority that can emit the sealed arm command.
    """

    commands = list(scheduled_commands)
    if (
        checkpoint_arm_command is None
        or checkpoint_arm_gate.get("command_sent") is True
        or "botauto status" not in commands
    ):
        return commands
    _initialize_chainwielder_checkpoint_arm_gate(checkpoint_arm_gate)
    status_index = commands.index("botauto status")
    commands.insert(status_index + 1, "botauto status")
    checkpoint_arm_gate["pre_route_probe_batches"] = int(
        checkpoint_arm_gate.get("pre_route_probe_batches") or 0
    ) + 1
    checkpoint_arm_gate["pre_route_probe_command_count"] = int(
        checkpoint_arm_gate.get("pre_route_probe_command_count") or 0
    ) + 1
    return commands

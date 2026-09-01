"""Fail-closed demux binding for the Magmaw transfer checkpoint fixture."""

from __future__ import annotations

import re
from typing import Any

try:
    from tools.raid_program.capture_checkpoint_controller import (
        MAGMAW_TRANSFER_DESTINATION,
        MAGMAW_TRANSFER_EPISODE_GENERATION,
        MAGMAW_TRANSFER_LEGACY_GENERATION,
        MAGMAW_TRANSFER_MAX_PROGRESS_SAMPLES,
        MAGMAW_TRANSFER_START,
        MAGMAW_TRANSFER_TASK_GENERATION,
        _exact_position,
        _exact_same_floor_arrival,
    )
    from tools.raid_program.capture_value_types import _nonnegative_int, _positive_int
    from tools.raid_program.recurrence_checkpoint_seals import (
        MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
        MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
        MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
    )
except ModuleNotFoundError:
    from capture_checkpoint_controller import (
        MAGMAW_TRANSFER_DESTINATION,
        MAGMAW_TRANSFER_EPISODE_GENERATION,
        MAGMAW_TRANSFER_LEGACY_GENERATION,
        MAGMAW_TRANSFER_MAX_PROGRESS_SAMPLES,
        MAGMAW_TRANSFER_START,
        MAGMAW_TRANSFER_TASK_GENERATION,
        _exact_position,
        _exact_same_floor_arrival,
    )
    from capture_value_types import _nonnegative_int, _positive_int
    from recurrence_checkpoint_seals import (
        MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID,
        MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY,
        MAGMAW_TRANSFER_CHECKPOINT_CASE_ID,
        MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID,
    )


MAGMAW_TRANSFER_CHECKPOINT_ACTION = "botauto_magmaw_transfer_lane_checkpoint"
_STAGE_ORDER = {
    "armed": 0, "queued": 1, "native_submitted": 2,
    "progressing": 3, "completed": 4,
}
_MIRRORED_FIELDS = (
    "stage", "terminal", "queue_count", "candidate_attempt_count",
    "native_submission_count", "planner_receipt_id", "progress_samples",
    "outcome",
)
_HOLD_IDENTITY_FIELDS = (
    "cohort_id", "server_epoch", "attempt_id", "scenario_id",
    "runtime_profile", "route_manifest_sha256", "route_generation",
    "route_node_id", "actor_guid", "fixture_id", "seal_sha256",
    "source_commit",
)
_CONFIG_TRUE_FIELDS = (
    "accepted", "fixture_configured_present", "fixture_requested_present",
    "fixture_matches", "seal_configured_present", "seal_requested_present",
    "seal_matches", "source_configured_present", "source_requested_present",
    "source_matches", "binary_revision_present",
    "binary_revision_format_valid", "binary_revision_matches_source",
)
_EXPECTED_IDENTITY_FIELDS = (
    "actor_guid", "fixture_id", "case_id", "runtime_profile", "scenario_id",
    "route_manifest_sha256", "seal_sha256", "source_commit",
)


def _fixed_hex(value: Any, length: int) -> bool:
    return isinstance(value, str) and re.fullmatch(
        rf"[0-9a-fA-F]{{{length}}}", value,
    ) is not None


def _typed_terminal_rejections(terminal: Any) -> list[str]:
    if not isinstance(terminal, dict):
        return ["evidence_demux_fixture_terminal_missing"]
    forced = terminal.get("final_forced_evidence_report")
    if (
        terminal.get("detected") is not True
        or terminal.get("classification") != "fixture_terminal_observation"
        or terminal.get("terminal_kind")
            != "magmaw_transfer_lane_checkpoint_terminal"
        or terminal.get("scheduler_phase") != "complete"
        or terminal.get("stage") != "completed"
        or terminal.get("outcome") != "magmaw_transfer_checkpoint_completed"
        or terminal.get("success") is not False
        or terminal.get("gate_passed") is not False
        or terminal.get("fixture_gate_passed") is not True
        or terminal.get("final_forced_evidence") is not True
        or not isinstance(forced, dict)
        or forced.get("gate_passed") is not True
        or not isinstance(terminal.get("checkpoint_response"), dict)
    ):
        return ["evidence_demux_fixture_terminal_invalid"]
    return []


def _retained_terminal_context(
    terminal: dict[str, Any], rows: list[dict[str, Any]],
    checkpoint_rows: list[dict[str, Any]], *, canonical_active_sequence: int,
) -> tuple[dict[str, Any], dict[str, Any], list[int], list[str]]:
    response = terminal["checkpoint_response"]
    reasons: list[str] = []
    matches = [row for row in checkpoint_rows if row.get("payload") == response]
    terminal_sequence = matches[0].get("capture_sequence") if len(matches) == 1 else None
    if len(matches) != 1:
        reasons.append("evidence_demux_fixture_terminal_response_unretained")
    stop_sequences = [
        int(row["capture_sequence"]) for row in rows
        if isinstance(row.get("payload"), dict)
        and row["payload"].get("action") == "botauto_stop"
        and isinstance(row.get("capture_sequence"), int)
    ]
    if (
        not isinstance(terminal_sequence, int)
        or terminal_sequence <= canonical_active_sequence
        or (stop_sequences and terminal_sequence >= min(stop_sequences))
    ):
        reasons.append("evidence_demux_fixture_terminal_order_invalid")
    direct_holds = [
        row for row in rows
        if isinstance(row.get("payload"), dict)
        and row["payload"].get("action") == "botauto_controller_route_hold"
        and row["payload"].get("phase") == "held"
    ]
    terminal_hold = response.get("controller_route_hold")
    launch_hold = direct_holds[0]["payload"] if len(direct_holds) == 1 else None
    if not isinstance(terminal_hold, dict) or not isinstance(launch_hold, dict):
        reasons.append("evidence_demux_fixture_hold_identity_missing")
        return {}, {}, stop_sequences, reasons
    if any(terminal_hold.get(field) != launch_hold.get(field) for field in _HOLD_IDENTITY_FIELDS):
        reasons.append("evidence_demux_fixture_hold_launch_mismatch")
    launch_sequence = direct_holds[0].get("capture_sequence")
    first_checkpoint_sequence = checkpoint_rows[0].get("capture_sequence") if checkpoint_rows else None
    if (
        not isinstance(launch_sequence, int)
        or not isinstance(first_checkpoint_sequence, int)
        or launch_sequence >= first_checkpoint_sequence
    ):
        reasons.append("evidence_demux_fixture_hold_order_invalid")
    return response, terminal_hold, stop_sequences, reasons


def _runtime_identity_rejections(
    terminal: dict[str, Any], response: dict[str, Any], hold: dict[str, Any],
    *, canonical_identity: tuple[Any, ...], canonical_roster_guids: set[int],
    canonical_cohort: str, profile_name: str,
    expected_identity: dict[str, Any] | None,
) -> list[str]:
    reasons: list[str] = []
    actor = response.get("actor_guid")
    expected_scope = (
        f"{canonical_cohort}:{canonical_identity[10]}:0:"
        f"{hold.get('route_generation')}:{hold.get('route_node_id')}:"
        f"{canonical_identity[6]}:{canonical_identity[7]}:"
        "magmaw_transfer_lane_checkpoint"
    )
    expected_candidate = (
        f"{expected_scope}:adaptive_magmaw:pillar_bait_switch:GUID Full: "
        f"0x{MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID:016X} Type: Player Low: "
        f"{MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID}:"
        f"{MAGMAW_TRANSFER_LEGACY_GENERATION}"
    )
    if (
        actor != MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        or actor not in canonical_roster_guids
        or terminal.get("actor_guid") != actor
        or terminal.get("fixture_id") != response.get("fixture_id")
        or terminal.get("case_id") != response.get("case_id")
        or response.get("scope_key") != expected_scope
        or response.get("candidate_key") != expected_candidate
        or response.get("planner_candidate_key") != expected_candidate
        or response.get("episode_generation") != MAGMAW_TRANSFER_EPISODE_GENERATION
        or response.get("task_generation") != MAGMAW_TRANSFER_TASK_GENERATION
        or response.get("legacy_generation") != MAGMAW_TRANSFER_LEGACY_GENERATION
    ):
        reasons.append("evidence_demux_fixture_terminal_identity_mismatch")
    if (
        not isinstance(expected_identity, dict)
        or any(field not in expected_identity for field in _EXPECTED_IDENTITY_FIELDS)
        or expected_identity.get("actor_guid") != MAGMAW_TRANSFER_CHECKPOINT_ACTOR_GUID
        or expected_identity.get("fixture_id") != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or expected_identity.get("case_id") != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or expected_identity.get("runtime_profile") != profile_name
        or expected_identity.get("actor_guid") != actor
        or expected_identity.get("fixture_id") != response.get("fixture_id")
        or expected_identity.get("case_id") != response.get("case_id")
        or any(
            expected_identity.get(field) != hold.get(field)
            for field in (
                "runtime_profile", "scenario_id", "route_manifest_sha256",
                "seal_sha256", "source_commit",
            )
        )
    ):
        reasons.append("evidence_demux_fixture_expected_identity_mismatch")
    if (
        hold.get("cohort_id") != canonical_cohort
        or hold.get("server_epoch") != canonical_identity[9]
        or hold.get("attempt_id") != canonical_identity[10]
        or hold.get("runtime_profile") != profile_name
        or hold.get("fixture_id") != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or response.get("fixture_id") != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or response.get("case_id") != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or response.get("authority") != MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY
        or response.get("task_authority_enabled") is not False
        or not _fixed_hex(hold.get("route_manifest_sha256"), 64)
        or not _fixed_hex(hold.get("seal_sha256"), 64)
        or not _fixed_hex(hold.get("source_commit"), 40)
        or not _positive_int(hold.get("route_generation"))
        or not isinstance(hold.get("route_node_id"), str)
        or not hold.get("route_node_id")
        or not isinstance(hold.get("scenario_id"), str)
        or not hold.get("scenario_id")
    ):
        reasons.append("evidence_demux_fixture_terminal_runtime_identity_invalid")
    return reasons


def _checkpoint_row_rejections(
    row: dict[str, Any], response: dict[str, Any], terminal_hold: dict[str, Any],
    *, actor: Any, canonical_roster_guids: set[int], previous_stage: int,
    previous_counts: tuple[int, ...], canonical_active_sequence: int,
    stop_sequences: list[int], terminal_seen: bool,
) -> tuple[list[str], int, tuple[int, ...], bool]:
    reasons: list[str] = []
    sequence = row.get("capture_sequence")
    payload = row["payload"]
    hold = payload.get("controller_route_hold")
    lifecycle = hold.get("checkpoint_lifecycle") if isinstance(hold, dict) else None
    stage = payload.get("stage")
    stage_order = _STAGE_ORDER.get(stage, -1)
    if (
        not isinstance(sequence, int)
        or sequence <= canonical_active_sequence
        or terminal_seen
        or (stop_sequences and sequence >= min(stop_sequences))
    ):
        reasons.append("evidence_demux_fixture_checkpoint_after_terminal_or_cleanup")
    if (
        payload.get("ok") is not True
        or payload.get("terminal_kind") != "fixture_checkpoint"
        or payload.get("certifies_gameplay_success") is not False
        or payload.get("certifies_boss_fidelity") is not False
        or payload.get("authority") != MAGMAW_TRANSFER_CHECKPOINT_AUTHORITY
        or payload.get("fixture_id") != MAGMAW_TRANSFER_CHECKPOINT_FIXTURE_ID
        or payload.get("case_id") != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or payload.get("actor_guid") != actor
        or actor not in canonical_roster_guids
        or payload.get("task_authority_enabled") is not False
        or not isinstance(hold, dict)
        or not isinstance(lifecycle, dict)
    ):
        return [*reasons, "evidence_demux_fixture_checkpoint_identity_invalid"], previous_stage, previous_counts, terminal_seen
    if any(hold.get(field) != terminal_hold.get(field) for field in _HOLD_IDENTITY_FIELDS):
        reasons.append("evidence_demux_fixture_checkpoint_cross_identity")
    comparison = hold.get("config_identity_comparison")
    if (
        hold.get("ok") is not True
        or hold.get("actor_guid") != actor
        or not isinstance(comparison, dict)
        or comparison.get("failure_field") != "none"
        or any(comparison.get(field) is not True for field in _CONFIG_TRUE_FIELDS)
        or comparison.get("configured_source_length") != 40
        or comparison.get("requested_source_length") != 40
        or comparison.get("binary_revision_length") not in {12, 40}
        or any(payload.get(field) != response.get(field) for field in (
            "episode_generation", "task_generation", "legacy_generation",
        ))
    ):
        reasons.append("evidence_demux_fixture_checkpoint_embedded_hold_invalid")
    candidate_key = payload.get("candidate_key")
    planner_candidate_key = payload.get("planner_candidate_key")
    scope_key = payload.get("scope_key")
    terminal_candidate = response.get("candidate_key")
    terminal_scope = response.get("scope_key")
    has_candidate = stage != "armed"
    if (
        not isinstance(terminal_candidate, str)
        or not terminal_candidate
        or response.get("planner_candidate_key") != terminal_candidate
        or not isinstance(terminal_scope, str)
        or not terminal_scope
        or not terminal_candidate.startswith(terminal_scope + ":")
        or (has_candidate and candidate_key != terminal_candidate)
        or (has_candidate and scope_key != terminal_scope)
        or (has_candidate and planner_candidate_key not in {"", terminal_candidate})
        or (not has_candidate and candidate_key not in {"", terminal_candidate})
        or (not has_candidate and scope_key not in {"", terminal_scope})
    ):
        reasons.append("evidence_demux_fixture_checkpoint_candidate_identity_invalid")
    if (
        lifecycle.get("case_id") != MAGMAW_TRANSFER_CHECKPOINT_CASE_ID
        or any(payload.get(field) != lifecycle.get(field) for field in _MIRRORED_FIELDS)
        or stage_order < previous_stage
        or stage_order < 0
    ):
        reasons.append("evidence_demux_fixture_checkpoint_lifecycle_invalid")
    counts = tuple(payload.get(field) for field in (
        "queue_count", "candidate_attempt_count", "native_submission_count",
        "planner_receipt_id", "progress_samples",
    ))
    if (
        any(not _nonnegative_int(value) for value in counts)
        or any(current < previous for current, previous in zip(counts, previous_counts))
    ):
        reasons.append("evidence_demux_fixture_checkpoint_lifecycle_nonmonotonic")
    else:
        previous_counts = tuple(int(value) for value in counts)
    if (
        (stage == "armed" and counts != (0, 0, 0, 0, 0))
        or (stage == "queued" and counts != (1, 1, 1, 0, 0))
        or (
            stage == "completed"
            and (
                counts[:3] != (1, 1, 1)
                or not _positive_int(counts[3])
                or not _nonnegative_int(counts[4])
                or int(counts[4]) < 2
            )
        )
    ):
        reasons.append("evidence_demux_fixture_checkpoint_stage_counts_invalid")
    previous_stage = max(previous_stage, stage_order)
    if payload.get("terminal") is True:
        terminal_seen = True
        progress = payload.get("progress_samples")
        decreasing = payload.get("decreasing_progress_samples")
        wrong_floor = payload.get("wrong_floor_samples")
        if (
            payload != response
            or stage != "completed"
            or payload.get("fixture_gate_passed") is not True
            or payload.get("queue_count") != 1
            or payload.get("candidate_attempt_count") != 1
            or payload.get("native_submission_count") != 1
            or not _positive_int(payload.get("planner_receipt_id"))
            or not _positive_int(payload.get("spline_id"))
            or payload.get("motion_master_slot") != 1
            or payload.get("motion_master_generator_type") != 8
            or not all(_nonnegative_int(value) for value in (progress, decreasing, wrong_floor))
            or int(progress) < 2
            or int(progress) > MAGMAW_TRANSFER_MAX_PROGRESS_SAMPLES
            or int(decreasing) < 2
            or int(decreasing) > int(progress) - int(wrong_floor)
            or payload.get("task_state") != "succeeded"
            or not _exact_position(payload.get("requested_destination"), MAGMAW_TRANSFER_DESTINATION)
            or not _exact_position(payload.get("actor_start"), MAGMAW_TRANSFER_START)
            or not _exact_same_floor_arrival(payload.get("actor_last_same_floor"))
            or hold.get("phase") != "checkpoint_terminal"
            or hold.get("checkpoint_terminal") is not True
            or hold.get("checkpoint_identity_preserved") is not True
            or hold.get("checkpoint_stage") != "completed"
        ):
            reasons.append("evidence_demux_fixture_checkpoint_terminal_invalid")
    elif (
        payload.get("fixture_gate_passed") is not False
        or hold.get("phase") != "armed"
        or hold.get("checkpoint_terminal") is not False
    ):
        reasons.append("evidence_demux_fixture_checkpoint_progress_invalid")
    return reasons, previous_stage, previous_counts, terminal_seen


def fixture_terminal_binding(
    fixture_terminal: dict[str, Any] | None, rows: list[dict[str, Any]], *,
    canonical_identity: tuple[Any, ...], canonical_roster_guids: set[int],
    canonical_cohort: str, canonical_active_sequence: int, profile_name: str,
    expected_identity: dict[str, Any] | None,
) -> tuple[bool, list[str], dict[int, list[str]]]:
    checkpoint_rows = [
        row for row in rows if isinstance(row.get("payload"), dict)
        and row["payload"].get("action") == MAGMAW_TRANSFER_CHECKPOINT_ACTION
    ]
    if not checkpoint_rows and fixture_terminal is None:
        return False, [], {}
    reasons = _typed_terminal_rejections(fixture_terminal)
    if reasons:
        return False, reasons, {}
    assert isinstance(fixture_terminal, dict)
    response, terminal_hold, stops, retained_rejections = _retained_terminal_context(
        fixture_terminal, rows, checkpoint_rows,
        canonical_active_sequence=canonical_active_sequence,
    )
    reasons.extend(retained_rejections)
    reasons.extend(_runtime_identity_rejections(
        fixture_terminal, response, terminal_hold,
        canonical_identity=canonical_identity,
        canonical_roster_guids=canonical_roster_guids,
        canonical_cohort=canonical_cohort,
        profile_name=profile_name,
        expected_identity=expected_identity,
    ))
    row_rejections: dict[int, list[str]] = {}
    stage = -1
    counts: tuple[int, ...] = (0, 0, 0, 0, 0)
    terminal_seen = False
    for row in checkpoint_rows:
        found, stage, counts, terminal_seen = _checkpoint_row_rejections(
            row, response, terminal_hold,
            actor=response.get("actor_guid"),
            canonical_roster_guids=canonical_roster_guids,
            previous_stage=stage,
            previous_counts=counts,
            canonical_active_sequence=canonical_active_sequence,
            stop_sequences=stops,
            terminal_seen=terminal_seen,
        )
        if found:
            sequence = row.get("capture_sequence")
            if isinstance(sequence, int):
                row_rejections[sequence] = list(dict.fromkeys(found))
            reasons.extend(found)
    if not terminal_seen:
        reasons.append("evidence_demux_fixture_checkpoint_terminal_missing")
    unique = list(dict.fromkeys(reasons))
    return not unique, unique, row_rejections

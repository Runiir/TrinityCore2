from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
import hashlib
import json
from math import hypot, isfinite
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import tempfile
import time
from typing import Any

try:
    from tools.bot_ml.analyze_combat_log import analyze_combat_log
    from tools.bot_ml.run_live_bot_validation import (
        combined_combat_log,
        combat_log_transport_status,
        trinity_config_bool,
        trinity_config_string,
    )
    from tools.raid_program.capture_no_bots_baseline import process_sample as _baseline_process_sample
    from tools.raid_program.controller_route_hold import (
        ControllerRouteHoldLaunchIdentity,
        ControllerRouteHoldScheduler,
        controller_route_hold_launch_identity,
    )
    from tools.raid_program.capture_progress import (
        observe_monotonic_semantic_progress,
        ready_for_native_readycheck,
        semantic_progress_signature,
    )
    from tools.raid_program.capture_evidence_demux import (
        _required_telemetry_envelope_report,
        _trace_actor_transport_rejections,
        evidence_demux_report as _evidence_demux_report_impl,
        normalized_batch_payload as _normalized_batch_payload_impl,
    )
    from tools.raid_program.capture_drudge_contract import accepted_drudge_contract
    from tools.raid_program.capture_drudge_geometry import (
        _frozen_drudge_member_anchors,
        _validate_drudge_observation_geometry,
    )
    from tools.raid_program.capture_environment_validation import (
        EXPECTED_BWD_ROUTE_IDENTITY,
        EXPECTED_BWD_ROUTE_PARTITION_COUNTS,
        _dvc_status_is_clean,
        _process_arguments,
        _protected_process_matches,
        _utc_timestamp,
        build_policy_path_for_receipt,
        git_identity,
        preflight_runtime_exclusions,
        sha256_file,
        validate_build_receipt,
        validate_runtime_profile_assets,
    )
    from tools.raid_program.capture_telemetry_transport import (
        TRACE_PRESSURE_INTERVAL_SEC,
        TRACE_PRESSURE_WATERMARK,
        TRACE_RING_CAPACITY,
        JsonLogCursor,
        JsonLogObservation,
        TelemetryScheduler,
        TelemetryTransportLedger,
        _json_row_from_log_line,
        action_payloads,
        collect_log_observations,
        json_actions,
        json_rows,
        material_status_signature,
        observe_telemetry_freshness,
    )
    from tools.raid_program.capture_runtime_identity import (
        IDENTITY_FIELDS,
        ROSTER_BINDING_ID_FIELDS,
        ROSTER_ID_FIELDS,
        STRATEGY_FIELD,
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _route_advancement_marker,
        _runtime_identity,
    )
    from tools.raid_program.capture_runtime_acceptance import (
        _canonical_int_list,
        _compact_trailing_zero_gems,
        _expected_identity_by_slot,
        _identity_manifest_rejections,
        _provisioned_bwd_10n_bots,
        _provisioned_bwd_bots,
        _roster_identity,
        _roster_rejections,
        _runtime_gear_manifest,
        accepted_foundation_status,
        accepted_native_recovery,
        expected_bwd_10n_roster,
        native_readycheck_request_identity,
        terminal_preflight_failure_reason,
        terminal_runtime_failure_reason,
    )
    from tools.raid_program.capture_value_types import (
        _canonical_object_sha256,
        _nonnegative_int,
        _positive_int,
        _uint64_int,
    )
    from tools.raid_program.capture_watchdog import (
        DEFAULT_MAX_DEATH_LOOPS,
        DEFAULT_MAX_REPEATED_DECISIONS,
        _CONTROLLER_TERMINAL_FAILURE_REASONS,
        observe_capture_watchdog,
    )
    from tools.raid_program.probe_drudge_navmesh_recovery import run_probe as _drudge_navmesh_probe
    from tools.raid_program.recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        GAMEPLAY_CANARY_PURPOSE,
        RecurrenceAdmissionError,
        verify_recurrence_admission,
    )
    from tools.raid_program import trace_transport_smoke
except ModuleNotFoundError:
    # Direct execution places tools/raid_program, not the repository root, on
    # sys.path. Keep the CLI and imported test/module paths on the same sampler.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from tools.bot_ml.analyze_combat_log import analyze_combat_log
    from tools.bot_ml.run_live_bot_validation import (
        combined_combat_log,
        combat_log_transport_status,
        trinity_config_bool,
        trinity_config_string,
    )
    from capture_no_bots_baseline import process_sample as _baseline_process_sample
    from controller_route_hold import (
        ControllerRouteHoldLaunchIdentity,
        ControllerRouteHoldScheduler,
        controller_route_hold_launch_identity,
    )
    from capture_progress import (
        observe_monotonic_semantic_progress,
        ready_for_native_readycheck,
        semantic_progress_signature,
    )
    from capture_evidence_demux import (
        _required_telemetry_envelope_report,
        _trace_actor_transport_rejections,
        evidence_demux_report as _evidence_demux_report_impl,
        normalized_batch_payload as _normalized_batch_payload_impl,
    )
    from capture_drudge_contract import accepted_drudge_contract
    from capture_drudge_geometry import (
        _frozen_drudge_member_anchors,
        _validate_drudge_observation_geometry,
    )
    from capture_environment_validation import (
        EXPECTED_BWD_ROUTE_IDENTITY,
        EXPECTED_BWD_ROUTE_PARTITION_COUNTS,
        _dvc_status_is_clean,
        _process_arguments,
        _protected_process_matches,
        _utc_timestamp,
        build_policy_path_for_receipt,
        git_identity,
        preflight_runtime_exclusions,
        sha256_file,
        validate_build_receipt,
        validate_runtime_profile_assets,
    )
    from capture_telemetry_transport import (
        TRACE_PRESSURE_INTERVAL_SEC,
        TRACE_PRESSURE_WATERMARK,
        TRACE_RING_CAPACITY,
        JsonLogCursor,
        JsonLogObservation,
        TelemetryScheduler,
        TelemetryTransportLedger,
        _json_row_from_log_line,
        action_payloads,
        collect_log_observations,
        json_actions,
        json_rows,
        material_status_signature,
        observe_telemetry_freshness,
    )
    from capture_runtime_identity import (
        IDENTITY_FIELDS,
        ROSTER_BINDING_ID_FIELDS,
        ROSTER_ID_FIELDS,
        STRATEGY_FIELD,
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _route_advancement_marker,
        _runtime_identity,
    )
    from capture_runtime_acceptance import (
        _canonical_int_list,
        _compact_trailing_zero_gems,
        _expected_identity_by_slot,
        _identity_manifest_rejections,
        _provisioned_bwd_10n_bots,
        _provisioned_bwd_bots,
        _roster_identity,
        _roster_rejections,
        _runtime_gear_manifest,
        accepted_foundation_status,
        accepted_native_recovery,
        expected_bwd_10n_roster,
        native_readycheck_request_identity,
        terminal_preflight_failure_reason,
        terminal_runtime_failure_reason,
    )
    from capture_value_types import (
        _canonical_object_sha256,
        _nonnegative_int,
        _positive_int,
        _uint64_int,
    )
    from capture_watchdog import (
        DEFAULT_MAX_DEATH_LOOPS,
        DEFAULT_MAX_REPEATED_DECISIONS,
        _CONTROLLER_TERMINAL_FAILURE_REASONS,
        observe_capture_watchdog,
    )
    from probe_drudge_navmesh_recovery import run_probe as _drudge_navmesh_probe
    from recurrence_admission import (
        CHAINWIELDER_CHECKPOINT_FIXTURE_ID,
        FIXTURE_EXPANSION_PURPOSE,
        GAMEPLAY_CANARY_PURPOSE,
        RecurrenceAdmissionError,
        verify_recurrence_admission,
    )
    import trace_transport_smoke


ROOT = Path(__file__).resolve().parents[2]

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
        or recurrence_admission.get("fixture_expansion_target_ids")
        != [CHAINWIELDER_CHECKPOINT_FIXTURE_ID]
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


def _primary_gameplay_terminal(*terminals: dict[str, Any] | None) -> bool:
    """Return whether a controller/native terminal established gameplay failure.

    Evidence-integrity failures that occur while collecting the terminal bundle
    must not erase this primary outcome.  The integrity gates still reject the
    capture; this predicate only preserves the causal classification.
    """

    return any(
        isinstance(terminal, dict)
        and terminal.get("detected") is True
        and terminal.get("classification") == "gameplay_failure"
        for terminal in terminals
    )


def _terminal_evidence_incomplete(
    *,
    primary_gameplay_failure: bool,
    forced_evidence_report: dict[str, Any],
    telemetry_abort: dict[str, Any],
    telemetry_envelopes: dict[str, Any],
    demux_rejections: list[str],
) -> bool:
    """Expose incomplete terminal evidence without making it an acceptance.

    Only a known gameplay terminal gets this causal annotation.  Other
    incomplete captures remain infrastructure/incomplete evidence as before.
    """

    if not primary_gameplay_failure:
        return False
    return bool(
        forced_evidence_report.get("gate_passed") is not True
        or telemetry_abort.get("detected") is True
        or telemetry_envelopes.get("gate_passed") is not True
        or demux_rejections
    )


def _capture_classification(
    *,
    success: bool,
    forbidden_entries: list[Any],
    primary_gameplay_failure: bool,
    operational_infrastructure_abort: bool,
    evidence_incomplete: bool,
) -> str:
    """Classify a capture without letting evidence gaps erase causality.

    Evidence gates remain independent from this label through ``success``.
    An operational abort still takes precedence; otherwise a retained primary
    gameplay terminal takes precedence over incomplete terminal evidence.
    """

    if success:
        return "success"
    if forbidden_entries:
        return "diagnostic_only"
    if operational_infrastructure_abort:
        return "infrastructure_abort"
    if primary_gameplay_failure:
        return "gameplay_failure"
    if evidence_incomplete:
        return "infrastructure_abort"
    return "incomplete_evidence"


def process_resource_sample(
    pid: int,
    *,
    sample_sequence: int,
    scenario_id: str,
    runtime_profile: str,
    status: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Retain a compact, identity-bound worldserver resource sample.

    The baseline sampler is the source of truth for `/proc` parsing and CPU
    tick/RSS units.  Only those process fields are retained here; host load,
    memory pressure, and other baseline diagnostics are intentionally not
    copied into the raid telemetry stream.  Runtime identity is attached to
    every row so a later report cannot accidentally join samples from another
    cohort or attempt.
    """
    baseline = _baseline_process_sample(pid)
    runtime = status.get("raid_runtime") if isinstance(status, dict) else None
    runtime = runtime if isinstance(runtime, dict) else {}
    identity: dict[str, Any] = {
        "scenario_id": scenario_id,
        "runtime_profile": runtime_profile,
    }
    if isinstance(status, dict) and status.get("cohort_id") is not None:
        identity["cohort_id"] = status["cohort_id"]
    for field in (
        "server_epoch", "attempt_id", "profile_generation", "profile_content_hash",
        "assignment_generation", "group_guid", "leader_guid", "instance_id",
        "lockout_save_id",
    ):
        value = runtime.get(field)
        if value is not None:
            identity[field] = value
    return {
        "sample_sequence": sample_sequence,
        "process_pid": pid,
        "monotonic_sec": baseline["monotonic_sec"],
        "process_cpu_ticks": baseline["process_cpu_ticks"],
        "process_rss_bytes": baseline["process_rss_bytes"],
        "run_identity": identity,
    }


def summarize_process_resource_samples(
    samples: list[dict[str, Any]], *, tick_rate: int | None = None,
    sampling_errors: list[str] | None = None,
    sampling_error_count: int | None = None,
) -> dict[str, Any]:
    """Summarize retained process samples without copying them into telemetry.

    CPU percentage intentionally matches ``capture_no_bots_baseline``:
    process CPU time divided by wall time, expressed as a percentage of one
    logical core.  A mixed-PID sample set fails closed for CPU delta rather
    than attributing a reused PID to the raid.
    """
    errors = sampling_errors or []
    error_count = len(errors) if sampling_error_count is None else sampling_error_count
    if not samples:
        return {
            "sample_count": 0,
            "process_pid": None,
            "pid_consistent": False,
            "elapsed_seconds": 0.0,
            "cpu_ticks_delta": None,
            "tick_rate": tick_rate,
            "mean_cpu_percent_one_core": None,
            "maximum_rss_bytes": None,
            "minimum_rss_bytes": None,
            "sampling_error_count": error_count,
        }
    pids = [int(row["process_pid"]) for row in samples]
    pid_consistent = len(set(pids)) == 1
    first_time = float(samples[0]["monotonic_sec"])
    last_time = float(samples[-1]["monotonic_sec"])
    elapsed = max(0.0, last_time - first_time)
    ticks_delta = None
    mean_cpu = None
    if pid_consistent and len(samples) > 1:
        ticks_delta = int(samples[-1]["process_cpu_ticks"]) - int(samples[0]["process_cpu_ticks"])
        if tick_rate and tick_rate > 0 and elapsed > 0:
            mean_cpu = round((ticks_delta / tick_rate) / elapsed * 100, 3)
    rss_values = [int(row["process_rss_bytes"]) for row in samples]
    return {
        "sample_count": len(samples),
        "process_pid": pids[0] if pid_consistent else None,
        "pid_consistent": pid_consistent,
        "first_monotonic_sec": round(first_time, 6),
        "last_monotonic_sec": round(last_time, 6),
        "elapsed_seconds": round(elapsed, 3),
        "cpu_ticks_delta": ticks_delta,
        "tick_rate": tick_rate,
        "mean_cpu_percent_one_core": mean_cpu,
        "maximum_rss_bytes": max(rss_values),
        "minimum_rss_bytes": min(rss_values),
        "sampling_error_count": error_count,
    }



FORBIDDEN_ASSISTANCE_FIELDS = (
    "forbidden_completion_assists",
    "forbidden_assistance",
    "teacher_assisted",
    "encounter_state_injection",
    "forced_kill",
    "direct_resurrection",
    "combat_teleport",
    "door_unlock",
    "npc_spawn_assist",
    "direct_resurrect",
    "admin_resurrection",
    "forced_resurrection",
    "forced_teleport",
    "fallback_action",
    "fallback_result",
    "soap_command",
    "operator_command",
    "publisher_command",
    "dvc_push",
)

# These markers are forbidden even when they occur in an otherwise innocuous
# trace row.  A status field such as ``recovery_state`` is not a command/event
# marker and is therefore intentionally not included in this scan.
FORBIDDEN_MARKER_FIELDS = {
    "action", "event", "event_name", "result", "result_code", "command",
    "command_name", "failure_reason", "mode", "recovery_mode", "source",
    "operator", "publisher", "transport", "assistance_mode",
}
FORBIDDEN_MARKER_RE = re.compile(
    r"(?:direct[ _-]*resurrect|admin[ _-]*(?:resurrect|revive)|"
    r"forced[ _-]*(?:resurrect|revive|teleport|move|kill|wipe|reset)|"
    r"(?:^|[ _-])teleport(?:$|[ _-])|(?:^|[ _-])fallback(?:$|[ _-])|"
    r"(?:^|[ _-])(?:soap|console|operator|publisher)(?:$|[ _-])|"
    r"dvc[ _-]*push)",
    re.IGNORECASE,
)































































def wait_for_prompt(process: subprocess.Popen[bytes], log_path: Path, timeout_sec: int) -> None:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"worldserver exited before readiness with code {process.returncode}")
        if log_path.exists() and b"TC>" in log_path.read_bytes()[-65536:]:
            return
        time.sleep(0.25)
    raise RuntimeError("worldserver readiness prompt timed out")










def validate_forced_evidence_bundle(
    observations: list[tuple[dict[str, Any], float]],
    expected_status: dict[str, Any] | None,
    *,
    requested_at_monotonic: float,
    freshness_timeout_seconds: float,
) -> dict[str, Any]:
    """Validate the diagnose/trace responses to one explicit final request.

    The worldserver console is asynchronous.  A one-second sleep after
    writing commands is not evidence that either command ran, and a forged
    ``ok`` bit or a response from another cohort must not satisfy the final
    stall bundle.  Callers pass each newly observed row with the monotonic
    time at which it was read; this function therefore enforces both request
    ordering and a bounded freshness window without trusting producer-side
    timestamps.
    """

    required_channels = ("diagnosis", "trace")
    action_by_channel = {
        "diagnosis": "botauto_diagnose",
        "trace": "botauto_trace",
    }
    channels: dict[str, dict[str, Any]] = {
        channel: {
            "action": action,
            "observed": 0,
            "valid": False,
            "rejections": [],
        }
        for channel, action in action_by_channel.items()
    }
    expected_runtime = (
        expected_status.get("raid_runtime")
        if isinstance(expected_status, dict)
        else None
    )
    expected_identity = (
        _runtime_identity(expected_runtime, include_strategy=False)
        if isinstance(expected_runtime, dict)
        else None
    )
    expected_roster = (
        _roster_binding_identity(expected_runtime.get("roster"))
        if isinstance(expected_runtime, dict)
        and isinstance(expected_runtime.get("roster"), list)
        else None
    )
    expected_cohort = (
        expected_status.get("cohort_id")
        if isinstance(expected_status, dict)
        else None
    )
    expected_guids = {
        int(member[3])
        for member in expected_roster or ()
        if _positive_int(member[3])
    }
    expected_binding_missing = []
    if expected_identity is None:
        expected_binding_missing.append("forced_expected_runtime_identity_missing")
    if expected_roster is None or len(expected_guids) != 10:
        expected_binding_missing.append("forced_expected_roster_identity_missing")
    if not isinstance(expected_cohort, str) or not expected_cohort:
        expected_binding_missing.append("forced_expected_cohort_missing")

    def reject(channel: str, reason: str) -> None:
        reasons = channels[channel]["rejections"]
        if reason not in reasons:
            reasons.append(reason)

    for row, observed_at in observations:
        if not isinstance(row, dict):
            continue
        action = row.get("action")
        channel = next(
            (name for name, expected_action in action_by_channel.items()
             if expected_action == action),
            None,
        )
        if channel is None:
            continue
        channels[channel]["observed"] += 1
        if not isinstance(observed_at, (int, float)) or not isfinite(float(observed_at)):
            reject(channel, "forced_response_observation_time_invalid")
            continue
        if observed_at < requested_at_monotonic:
            reject(channel, "forced_response_before_request")
        elif observed_at - requested_at_monotonic > freshness_timeout_seconds:
            reject(channel, "forced_response_stale")
        if row.get("ok") is not True:
            reject(channel, "forced_response_envelope_not_ok")
        if expected_binding_missing:
            for reason in expected_binding_missing:
                reject(channel, reason)
            continue
        runtime = row.get("raid_runtime")
        roster = runtime.get("roster") if isinstance(runtime, dict) else None
        if (
            not isinstance(runtime, dict)
            or _runtime_identity(runtime, include_strategy=False) != expected_identity
            or _roster_binding_identity(roster) != expected_roster
            or row.get("cohort_id") != expected_cohort
        ):
            reject(channel, "forced_response_runtime_identity_unbound")
        if _roster_binding_lifecycle_rejections(roster):
            reject(channel, "forced_response_roster_lifecycle_invalid")
        bot_rows = row.get("bots")
        if not isinstance(bot_rows, list):
            reject(channel, "forced_response_bot_rows_missing")
            continue
        observed_guids: list[int] = []
        for bot_row in bot_rows:
            if not isinstance(bot_row, dict):
                reject(channel, "forced_response_bot_row_invalid")
                continue
            if channel == "trace" and bot_row.get("gap") is True:
                reject(channel, "forced_response_trace_delta_gap")
            identity = bot_row.get("identity")
            guid = identity.get("bot_guid") if isinstance(identity, dict) else bot_row.get("bot_guid")
            if not _positive_int(guid):
                reject(channel, "forced_response_bot_guid_invalid")
                continue
            observed_guids.append(int(guid))
        if len(observed_guids) != 10:
            reject(channel, "forced_response_bot_row_count_invalid")
        if len(set(observed_guids)) != len(observed_guids):
            reject(channel, "forced_response_duplicate_bot_guid")
        if set(observed_guids) != expected_guids:
            reject(channel, "forced_response_roster_incomplete_or_unbound")
        if not channels[channel]["rejections"]:
            channels[channel]["valid"] = True
            channels[channel]["observed_at_monotonic"] = float(observed_at)

    missing_channels = [
        channel for channel in required_channels
        if not channels[channel]["valid"]
    ]
    rejections = [
        f"{channel}:{reason}"
        for channel in required_channels
        for reason in channels[channel]["rejections"]
    ]
    return {
        "requested_at_monotonic": requested_at_monotonic,
        "freshness_timeout_seconds": freshness_timeout_seconds,
        "required_channels": list(required_channels),
        "missing_channels": missing_channels,
        "channels": channels,
        "rejections": rejections,
        "gate_passed": not missing_channels and not rejections,
    }


def validate_forced_combat_log_bundle(
    rows: list[dict[str, Any]], expected_cohort: str | None,
) -> dict[str, Any]:
    """Require one complete, contiguous bounded combat-log export."""

    chunks = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("action") == "botauto_combatlog_chunk"
    ]
    completions = [
        row for row in rows
        if isinstance(row, dict)
        and row.get("action") == "botauto_combatlog_complete"
    ]
    completion = completions[-1] if completions else {}
    expected_chunks = int(completion.get("chunk_count") or 0)
    sequences = {
        int(row.get("sequence"))
        for row in chunks
        if isinstance(row.get("sequence"), int)
        and int(row.get("chunk_count") or 0) == expected_chunks
    }
    rejections: list[str] = []
    if len(completions) != 1:
        rejections.append("forced_combat_log_complete_marker_invalid")
    if not expected_cohort or any(
        row.get("cohort_id") != expected_cohort
        for row in [*chunks, *completions]
    ):
        rejections.append("forced_combat_log_cohort_mismatch")
    if completion.get("ok") is not True:
        rejections.append("forced_combat_log_complete_not_ok")
    if expected_chunks <= 0 or sequences != set(range(expected_chunks)):
        rejections.append("forced_combat_log_chunks_incomplete")
    if any(
        row.get("ok") is not True
        or row.get("encoding") != "base64"
        or not isinstance(row.get("data"), str)
        or not row.get("data")
        for row in chunks
    ):
        rejections.append("forced_combat_log_chunk_invalid")
    if int(completion.get("total_bytes") or 0) <= 0:
        rejections.append("forced_combat_log_empty")
    return {
        "requested": True,
        "complete_marker_count": len(completions),
        "expected_chunks": expected_chunks,
        "received_chunks": len(sequences),
        "total_bytes": int(completion.get("total_bytes") or 0),
        "rejections": rejections,
        "gate_passed": not rejections,
    }


def normalized_batch_payload(
    log_bytes: bytes, *, profile_name: str = "blackwing_descent_10n",
) -> list[dict[str, Any]]:
    """Return an immutable, replayable JSONL representation of parsed evidence."""

    return _normalized_batch_payload_impl(
        log_bytes,
        profile_name=profile_name,
        json_row_parser=json_rows,
        evidence_reporter=evidence_demux_report,
    )


def evidence_demux_report(
    rows: list[dict[str, Any]], *, profile_name: str = "blackwing_descent_10n",
    controller_terminal: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Independently bind every retained JSON row to one raid lifecycle."""

    return _evidence_demux_report_impl(
        rows,
        profile_name=profile_name,
        controller_terminal=controller_terminal,
        terminal_failure_validator=terminal_runtime_failure_reason,
    )
def evidence_demux_rejections(rows: list[dict[str, Any]]) -> list[str]:
    return evidence_demux_report(rows)["rejections"]


def write_normalized_batch(path: Path, rows: list[dict[str, Any]]) -> tuple[str, int]:
    if path.exists():
        raise RuntimeError("raw normalized batch output already exists; artifacts are immutable")
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with path.open("xb") as handle:
        for row in rows:
            encoded = (json.dumps(row, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
            handle.write(encoded)
            digest.update(encoded)
    return digest.hexdigest(), len(rows)


def _forbidden_assistance_entries(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []

    def visit(value: Any, path: str) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                if key in FORBIDDEN_ASSISTANCE_FIELDS and child not in (None, False, [], {}, "", 0):
                    found.append({"path": f"{path}.{key}", "value": child})
                # This diagnostic means that no fallback was available or
                # executed; its wording must not invert the evidence.
                negative_fallback_marker = child == "blocked_no_fallback"
                if (key in FORBIDDEN_MARKER_FIELDS and isinstance(child, str)
                        and not negative_fallback_marker and FORBIDDEN_MARKER_RE.search(child)):
                    found.append({"path": f"{path}.{key}", "value": child, "kind": "forbidden_event_marker"})
                visit(child, f"{path}.{key}")
        elif isinstance(value, list):
            for index, child in enumerate(value):
                visit(child, f"{path}[{index}]")

    for row in rows:
        visit(row, "evidence")
    return found












def _artifact_record(path: Path, kind: str) -> dict[str, Any]:
    if not path.is_file():
        raise RuntimeError(f"immutable artifact missing: {path}")
    return {
        "kind": kind,
        "path": str(path),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "immutable": True,
    }


def bounded_native_shutdown(
    process: subprocess.Popen[bytes], wait_seconds: float,
) -> dict[str, Any]:
    """Request native cleanup and wait for the child within a hard budget.

    The caller still owns process-group escalation after this function
    returns.  Keeping the native request separate makes the operator-abort
    path testable without starting a worldserver and ensures repeated Ctrl-C
    cannot turn cleanup into an uncaught traceback.
    """
    result: dict[str, Any] = {
        "commands_sent": False,
        "operator_interrupted": False,
        "error": None,
        "exited": process.poll() is not None,
        "wait_seconds": wait_seconds,
    }
    if result["exited"]:
        return result
    if process.stdin is None:
        result["error"] = "native_shutdown_stdin_unavailable"
        return result
    try:
        process.stdin.write(b"botauto stop\nbotauto status\nserver exit\n")
        process.stdin.flush()
        result["commands_sent"] = True
    except (BrokenPipeError, OSError) as error:
        result["error"] = f"native_shutdown_write:{type(error).__name__}:{error}"
        return result
    deadline = time.monotonic() + wait_seconds
    while process.poll() is None and time.monotonic() < deadline:
        try:
            process.wait(timeout=min(0.25, max(0.01, deadline - time.monotonic())))
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            result["operator_interrupted"] = True
            continue
    result["exited"] = process.poll() is not None
    if not result["exited"]:
        result["error"] = f"native_shutdown_timeout:{wait_seconds:g}s"
    return result


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--binary", type=Path, required=True)
    parser.add_argument("--config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--raw-output", type=Path, default=None)
    parser.add_argument("--server-log-output", type=Path, default=None)
    parser.add_argument("--build-receipt", type=Path, required=True)
    parser.add_argument("--recurrence-admission", type=Path)
    parser.add_argument("--recurrence-admission-sha256")
    parser.add_argument("--chainwielder-checkpoint-actor-guid", type=int)
    parser.add_argument(
        "--fixture-expansion-replay",
        action="store_true",
        help=(
            "admit one evidence-only fixture expansion while the ordinary "
            "gameplay canary gate remains closed"
        ),
    )
    parser.add_argument(
        "--trace-transport-smoke",
        action="store_true",
        help=(
            "run the typed ten-actor production trace-transport lane; this "
            "mode can never admit route, gameplay, fixture, or acceptance claims"
        ),
    )
    parser.add_argument("--build-attestation", type=Path, default=None)
    parser.add_argument("--worktree", type=Path, default=ROOT)
    parser.add_argument(
        "--scenario-id", default=None,
        help="exact validation scenario partition to execute; defaults to --runtime-profile",
    )
    parser.add_argument(
        "--runtime-profile", default=None,
        help="exact runtime profile to select; defaults to blackwing_descent_10n",
    )
    parser.add_argument(
        "--pool-tag", default=None,
        help="optional exact pool tag; must match the selected runtime profile",
    )
    parser.add_argument(
        "--observe-sec", type=int, default=0,
        help=(
            "optional diagnostic wall-clock limit; 0 (the canonical default) "
            "runs until the terminal acceptance gates are satisfied"
        ),
    )
    parser.add_argument("--startup-timeout-sec", type=int, default=180)
    parser.add_argument("--required-stable-statuses", type=int, default=3)
    parser.add_argument("--semantic-stall-sec", type=int, default=300)
    parser.add_argument("--semantic-stall-min-samples", type=int, default=12)
    parser.add_argument(
        "--max-repeated-decision-count", type=int,
        default=DEFAULT_MAX_REPEATED_DECISIONS,
        help="controller terminal threshold for one scoped failed decision fingerprint",
    )
    parser.add_argument(
        "--max-death-loop-count", type=int,
        default=DEFAULT_MAX_DEATH_LOOPS,
        help="controller terminal threshold for scoped death/recovery events",
    )
    parser.add_argument("--telemetry-timeout-sec", type=int, default=60)
    parser.add_argument(
        "--status-interval-sec", type=float, default=5.0,
        help="status heartbeat cadence; must remain below telemetry timeout",
    )
    parser.add_argument(
        "--diagnose-interval-sec", type=float, default=30.0,
        help="steady-state full semantic diagnosis cadence",
    )
    parser.add_argument(
        "--trace-interval-sec", type=float, default=10.0,
        help="append-only trace-delta export cadence",
    )
    parser.add_argument(
        "--resource-sample-interval-sec", type=float, default=5.0,
        help="low-cost worldserver /proc CPU-tick and RSS sampling cadence",
    )
    args = parser.parse_args()

    binary = args.binary.resolve()
    config = args.config.resolve()
    output = args.output.resolve()
    worktree = args.worktree.resolve()
    profile_name = args.runtime_profile or args.scenario_id or "blackwing_descent_10n"
    scenario_id = args.scenario_id or profile_name
    if args.runtime_profile and args.scenario_id and args.runtime_profile != args.scenario_id:
        raise SystemExit("runtime profile and scenario ID must identify the same partition")
    raw_output = (args.raw_output or output.with_name(f"{output.stem}.raw.jsonl")).resolve()
    server_log_output = (
        args.server_log_output or output.with_name(f"{output.stem}.worldserver.log")
    ).resolve()
    if output.exists():
        raise SystemExit("output already exists; phase1 artifacts are immutable")
    if raw_output.exists():
        raise SystemExit("raw output already exists; phase1 artifacts are immutable")
    if server_log_output.exists():
        raise SystemExit("server log output already exists; phase1 artifacts are immutable")
    if not binary.is_file() or not config.is_file():
        raise SystemExit("binary and config must exist")
    trace_transport_admission_rejections = trace_transport_smoke.admission_rejections(
        profile=profile_name,
        scenario=scenario_id,
        pool_tag=args.pool_tag,
        recurrence_supplied=(
            args.recurrence_admission is not None
            or bool(args.recurrence_admission_sha256)
        ),
        fixture_expansion=args.fixture_expansion_replay,
        observe_seconds=args.observe_sec,
    ) if args.trace_transport_smoke else []
    if trace_transport_admission_rejections:
        raise SystemExit(
            "capture preflight rejected: "
            + ",".join(trace_transport_admission_rejections)
        )
    recurrence_admission: dict[str, Any] | None = None
    recurrence_required = scenario_id == "blackwing_descent_10n_magmaw_diagnostic"
    if args.fixture_expansion_replay and not recurrence_required:
        raise SystemExit(
            "capture preflight rejected: fixture_expansion_route_mismatch"
        )
    if recurrence_required and (
        args.recurrence_admission is None or not args.recurrence_admission_sha256
    ):
        raise SystemExit(
            "capture preflight rejected: magmaw_recurrence_admission_required"
        )
    if args.recurrence_admission is not None or args.recurrence_admission_sha256:
        if args.recurrence_admission is None or not args.recurrence_admission_sha256:
            raise SystemExit(
                "capture preflight rejected: incomplete_recurrence_admission_binding"
            )
        try:
            recurrence_admission = verify_recurrence_admission(
                admission_path=args.recurrence_admission,
                expected_sha256=args.recurrence_admission_sha256,
                worktree=worktree,
                binary=binary,
                build_receipt=args.build_receipt.resolve(),
                runtime_config=config,
                required_purpose=(
                    FIXTURE_EXPANSION_PURPOSE
                    if args.fixture_expansion_replay
                    else GAMEPLAY_CANARY_PURPOSE
                ),
            )
        except RecurrenceAdmissionError as error:
            raise SystemExit(
                f"capture preflight rejected: recurrence_admission:{error}"
            ) from error
    try:
        checkpoint_arm_command = chainwielder_checkpoint_arm_command(
            recurrence_admission,
            args.chainwielder_checkpoint_actor_guid,
        )
    except ValueError as error:
        raise SystemExit(
            f"capture preflight rejected: checkpoint_arm:{error}"
        ) from error
    # This controller owns the single explicit native start command.  A
    # prepare-only runner hands us a config, but must not leave worldserver
    # AutoStart enabled: the resulting duplicate profile selection tears down
    # the first cohort while the server is still completing startup and can
    # dereference invalid lifecycle state.  Reject the mismatch before a
    # process is spawned so a stale preparation fails deterministically.
    if trinity_config_bool(config, "BotWorld.AutoStart", False):
        raise SystemExit(
            "capture preflight rejected: config_autostart_enabled; "
            "phase1 capture owns the single botauto start command"
        )
    if (
        args.observe_sec < 0
        or 0 < args.observe_sec < 30
        or args.required_stable_statuses < 2
        or args.max_repeated_decision_count <= 0
        or args.max_death_loop_count <= 0
    ):
        raise SystemExit(
            "observation must be uncapped (0) or at least 30 seconds, require at least two stable statuses, and use positive watchdog thresholds"
        )
    if args.semantic_stall_sec < 60 or args.semantic_stall_min_samples < 3:
        raise SystemExit("semantic stall detection requires at least 60 seconds and three samples")
    if args.telemetry_timeout_sec < 15:
        raise SystemExit("telemetry freshness timeout must be at least 15 seconds")
    if any(interval <= 0 for interval in (
        args.status_interval_sec, args.diagnose_interval_sec, args.trace_interval_sec,
        args.resource_sample_interval_sec,
    )):
        raise SystemExit("telemetry intervals must be positive")
    if any(interval >= args.telemetry_timeout_sec for interval in (
        args.status_interval_sec, args.diagnose_interval_sec, args.trace_interval_sec,
    )):
        raise SystemExit("telemetry intervals must be shorter than the freshness timeout")
    preflight = preflight_runtime_exclusions(worktree)
    if not preflight["passed"]:
        raise SystemExit("capture preflight rejected: " + ",".join(preflight["reasons"]))

    identity_before = git_identity(worktree)
    if not identity_before["clean"]:
        raise SystemExit("canonical phase1 capture requires a clean worktree")
    runtime_assets = (
        trace_transport_smoke.validate_profile_assets(worktree)
        if args.trace_transport_smoke
        else validate_runtime_profile_assets(
            worktree,
            profile_name=profile_name,
            scenario_id=scenario_id,
            pool_tag=args.pool_tag,
        )
    )
    if not runtime_assets["passed"]:
        raise SystemExit("runtime profile assets rejected: " + ",".join(runtime_assets["reasons"]))
    route_manifest = runtime_assets.get("route_manifest")
    controller_route_hold_scheduler: ControllerRouteHoldScheduler | None = None
    if args.fixture_expansion_replay:
        try:
            controller_hold_identity = controller_route_hold_launch_identity(
                recurrence_admission=recurrence_admission,
                required_purpose=FIXTURE_EXPANSION_PURPOSE,
                actor_guid=args.chainwielder_checkpoint_actor_guid,
                scenario_id=scenario_id,
                runtime_profile=profile_name,
                pool_tag=str(runtime_assets.get("pool_tag_filter") or ""),
                route_manifest_sha256=runtime_assets.get("route_sha256"),
                route_node_id=trinity_config_string(
                    config, "BotWorld.ValidationRoute.NodeId",
                ),
            )
        except ValueError as error:
            raise SystemExit(
                f"capture preflight rejected: controller_route_hold:{error}"
            ) from error
        if controller_hold_identity is None:
            raise SystemExit(
                "capture preflight rejected: controller_route_hold_identity_missing"
            )
        controller_route_hold_scheduler = ControllerRouteHoldScheduler(
            controller_hold_identity,
        )
    drudge_observed = not args.trace_transport_smoke and (
        profile_name == "blackwing_descent_10n"
        or profile_name.endswith("_magmaw_diagnostic")
    )
    # The exact lane/re-separation contract is retained as diagnostic evidence.
    # Trash acceptance is outcome-based: the route must clear the pack and
    # recover without a wipe, semantic stall, or forbidden assistance.
    drudge_required = False
    drudge_navmesh_preflight: dict[str, Any] = {
        "required": drudge_observed,
        "all_passed": None,
    }
    if drudge_observed:
        try:
            drudge_navmesh_preflight = {
                "required": True,
                **_drudge_navmesh_probe(worktree),
            }
        except (OSError, RuntimeError, subprocess.SubprocessError) as exc:
            raise SystemExit(f"drudge navmesh preflight rejected: {exc}") from exc
    drudge_frozen_anchors = _frozen_drudge_member_anchors(
        Path(route_manifest) if isinstance(route_manifest, str) else None
    )
    if (profile_name == "blackwing_descent_10n" or profile_name.endswith("_magmaw_diagnostic")) \
            and set(drudge_frozen_anchors) != set(range(1, 11)):
        raise SystemExit("runtime profile assets rejected: drudge_frozen_member_anchors_missing")
    try:
        build_policy_path = build_policy_path_for_receipt(
            args.build_receipt.resolve(), worktree,
        )
    except RuntimeError as error:
        raise SystemExit(f"build receipt rejected: {error}") from error
    build_provenance = validate_build_receipt(
        args.build_receipt.resolve(),
        build_policy_path,
        worktree, binary, config,
        args.build_attestation.resolve() if args.build_attestation is not None else None,
    )
    if not build_provenance.get("valid"):
        raise SystemExit("build receipt rejected: " + ",".join(build_provenance.get("rejections", [])))

    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    recovery_required = (
        profile_name == "blackwing_descent_10n"
        and not args.trace_transport_smoke
    )
    stable: list[dict[str, Any]] = []
    last_rejections: list[str] = ["no_status_observed"]
    startup_error: str | None = None
    process: subprocess.Popen[bytes] | None = None
    telemetry_scheduler: TelemetryScheduler | None = None
    telemetry_transport_ledger = TelemetryTransportLedger()
    telemetry_command_counts = {
        "status": 0, "diagnose": 0, "trace": 0, "trace_pressure": 0,
        "combat_log": 0,
    }
    trace_transport_pressure_gate = trace_transport_smoke.pressure_receipt_report([])
    operator_interrupt = False
    shutdown_error: str | None = None
    stop_commands_sent = False
    checkpoint_arm_command_sent = False
    checkpoint_arm_gate: dict[str, Any] = {
        "schema": "chainwielder_checkpoint_pre_route_arm_gate_v1",
        "required": checkpoint_arm_command is not None,
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
    resource_samples: list[dict[str, Any]] = []
    resource_sampling_errors: list[str] = []
    resource_sampling_error_count = 0
    resource_sample_sequence = 0
    try:
        resource_tick_rate = int(os.sysconf(os.sysconf_names["SC_CLK_TCK"]))
    except (AttributeError, KeyError, OSError, ValueError):
        resource_tick_rate = None
    forced_evidence_report: dict[str, Any] = {
        "requested": False,
        "gate_passed": False,
        "missing_channels": ["diagnosis", "trace"],
        "rejections": ["forced_bundle_not_requested"],
    }
    terminal_failure: dict[str, Any] = {"detected": False}
    flush_forced_evidence_callback: Any = None

    def request_final_evidence(reason: str) -> dict[str, Any]:
        nonlocal operator_interrupt
        if forced_evidence_report.get("requested") is True:
            return forced_evidence_report
        if flush_forced_evidence_callback is None or process is None or process.poll() is not None:
            return {
                "requested": False,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": ["forced_bundle_process_unavailable"],
                "reason": reason,
            }
        try:
            report = flush_forced_evidence_callback()
            report["reason"] = reason
            return report
        except KeyboardInterrupt:
            operator_interrupt = True
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            return {
                "requested": True,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": ["forced_bundle_operator_interrupted"],
                "reason": reason,
            }
        except BaseException as error:
            return {
                "requested": True,
                "gate_passed": False,
                "missing_channels": ["diagnosis", "trace"],
                "rejections": [f"forced_bundle_error:{type(error).__name__}:{error}"],
                "reason": reason,
            }
    server_log_output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        prefix=".raid-phase1-worldserver-", suffix=".log.tmp", dir=server_log_output.parent, delete=False
    ) as log:
        log_path = Path(log.name)
        process = subprocess.Popen(
            [str(binary), "--config", str(config)], cwd=worktree, stdin=subprocess.PIPE,
            stdout=log, stderr=subprocess.STDOUT, start_new_session=True,
        )

        try:
            wait_for_prompt(process, log_path, args.startup_timeout_sec)
            assert process.stdin is not None
            log_cursor = JsonLogCursor(log_path)
            controller_hold_bootstrap_statuses: list[dict[str, Any]] = []
            # Bind the run to the explicitly selected frozen runtime profile.
            # The test worldserver configuration deliberately has AutoStart
            # disabled, so an explicit native operator command is required;
            # omitting it would only poll an inactive default cohort forever.
            if controller_route_hold_scheduler is not None:
                bootstrap_commands = controller_route_hold_scheduler.start()
                process.stdin.write(
                    ("\n".join(bootstrap_commands) + "\n").encode()
                )
                process.stdin.flush()
                bootstrap_deadline = time.monotonic() + args.telemetry_timeout_sec
                while (
                    controller_route_hold_scheduler.phase
                    != "awaiting_terminal"
                    and not controller_route_hold_scheduler.failed
                    and time.monotonic() < bootstrap_deadline
                ):
                    if process.poll() is not None:
                        controller_route_hold_scheduler._fail(
                            "controller_route_hold_worldserver_exited_during_bootstrap"
                        )
                        break
                    observations = collect_log_observations(
                        log_cursor, duration_seconds=0.25,
                    )
                    for observation in observations:
                        row = observation.row
                        if row.get("action") == "botauto_status":
                            controller_hold_bootstrap_statuses.append(row)
                        next_commands = controller_route_hold_scheduler.observe(row)
                        if next_commands:
                            process.stdin.write(
                                ("\n".join(next_commands) + "\n").encode()
                            )
                            process.stdin.flush()
                        if controller_route_hold_scheduler.failed:
                            break
                if controller_route_hold_scheduler.phase != "awaiting_terminal":
                    controller_route_hold_scheduler.finish()
                    raise RuntimeError(
                        "controller route hold bootstrap rejected: "
                        + str(controller_route_hold_scheduler.failure_reason)
                    )
                checkpoint_arm_command_sent = (
                    controller_route_hold_scheduler.command_counts["arm"] == 1
                )
            elif profile_name == "blackwing_descent_10n":
                process.stdin.write(b"botauto start blackwing_descent_10n\n")
                process.stdin.flush()
            else:
                process.stdin.write((f"botauto start {profile_name}\n").encode())
                process.stdin.flush()
            if controller_route_hold_scheduler is None:
                time.sleep(1.0)
            if args.trace_transport_smoke:
                # Produce one bounded native decision-history backlog before
                # the unchanged production scheduler begins polling, then use
                # the attempt-latched telemetry-only writer exactly once. The
                # first normal delta must expose the real ring discontinuity.
                time.sleep(trace_transport_smoke.PRESSURE_WARMUP_SECONDS)
                process.stdin.write(
                    (trace_transport_smoke.PRESSURE_COMMAND + "\n").encode()
                )
                process.stdin.flush()
                telemetry_command_counts["trace_pressure"] += 1
                pressure_observations = collect_log_observations(
                    log_cursor, duration_seconds=1.0,
                )
                trace_transport_pressure_gate = (
                    trace_transport_smoke.pressure_receipt_report(
                        [observation.row for observation in pressure_observations]
                    )
                )
                if trace_transport_pressure_gate["gate_passed"] is not True:
                    raise RuntimeError(
                        "trace transport pressure rejected: "
                        + ",".join(trace_transport_pressure_gate["rejections"])
                    )
            # Canonical raid validation is terminal-gate driven. Raid and boss
            # duration alone must never end an otherwise healthy run. A
            # positive limit remains available only for explicitly bounded
            # diagnostics and tests; zero is deliberately uncapped.
            deadline = time.monotonic() + args.observe_sec if args.observe_sec else None
            telemetry_scheduler = TelemetryScheduler(
                status_interval_sec=args.status_interval_sec,
                diagnose_interval_sec=args.diagnose_interval_sec,
                trace_interval_sec=args.trace_interval_sec,
            )
            monitor_statuses: list[dict[str, Any]] = list(
                controller_hold_bootstrap_statuses
            )
            for bootstrap_status in monitor_statuses:
                telemetry_scheduler.observe_status(bootstrap_status)
            diagnosis_count = 0
            trace_count = 0
            latest_diagnosis: dict[str, Any] | None = None
            recovery_accepted = not recovery_required
            drudge_accepted = not drudge_required
            readycheck_requested_for: tuple[Any, ...] | None = None
            semantic_progress_state: dict[str, Any] = {}
            last_semantic_progress_at = time.monotonic()
            unchanged_semantic_samples = 0
            semantic_stall: dict[str, Any] = {"detected": False}
            controller_watchdog_state: dict[str, Any] = {}
            controller_watchdog: dict[str, Any] = {
                "detected": False,
                "classification": None,
                "failure_reason": None,
                "max_repeated_decisions": args.max_repeated_decision_count,
                "max_death_loops": args.max_death_loop_count,
                "repeated_decision_count": 0,
                "death_loop_count": 0,
                "rejections": [],
            }
            monitor_started_at = time.monotonic()
            telemetry_freshness: dict[str, dict[str, float | int]] = {}
            telemetry_abort: dict[str, Any] = {"detected": False}
            trace_transport_gate = trace_transport_smoke.evaluate([])

            next_resource_sample_at = monitor_started_at

            def record_process_resource_sample(*, force: bool = False) -> None:
                nonlocal next_resource_sample_at, resource_sample_sequence
                nonlocal resource_sampling_error_count
                now = time.monotonic()
                if not force and now < next_resource_sample_at:
                    return
                if process.poll() is not None:
                    return
                try:
                    resource_samples.append(process_resource_sample(
                        process.pid,
                        sample_sequence=resource_sample_sequence,
                        scenario_id=scenario_id,
                        runtime_profile=profile_name,
                        status=monitor_statuses[-1] if monitor_statuses else None,
                    ))
                    resource_sample_sequence += 1
                except (OSError, IndexError, KeyError, TypeError, ValueError) as error:
                    resource_sampling_error_count += 1
                    # Preserve a bounded diagnostic prefix; a persistent
                    # /proc race must not make a long-run report grow without
                    # limit. The summary retains the exact total count.
                    if len(resource_sampling_errors) < 8:
                        resource_sampling_errors.append(f"{type(error).__name__}:{error}")
                finally:
                    next_resource_sample_at = now + args.resource_sample_interval_sec

            # Start the resource series as soon as the worldserver is ready;
            # later rows gain cohort/attempt identity once status is observed.
            record_process_resource_sample(force=True)

            def flush_forced_evidence() -> dict[str, Any]:
                """Retain and independently validate a final evidence bundle.

                Console commands are asynchronous.  Wait for the exact
                identity-bound responses to this request, bounded by the
                telemetry freshness budget, rather than treating a fixed
                sleep as proof that the commands ran.
                """
                nonlocal diagnosis_count, trace_count, latest_diagnosis
                telemetry_scheduler.force_diagnosis(include_trace=True)
                request_started = time.monotonic()
                commands = telemetry_scheduler.commands_due(request_started)
                trace_command = (
                    "botauto trace all 128"
                    if "botauto trace all 128" in commands
                    else "botauto trace all 128 delta"
                )
                required_commands = {
                    "botauto diagnose all", trace_command,
                }
                if not required_commands.issubset(commands):
                    return {
                        "requested": False,
                        "gate_passed": False,
                        "missing_channels": [
                            channel for channel in ("diagnosis", "trace")
                            if {
                                "diagnosis": "botauto diagnose all",
                                "trace": trace_command,
                            }[channel] not in commands
                        ],
                        "rejections": ["forced_request_commands_not_scheduled"],
                        "commands": commands,
                    }
                for command in commands:
                    if command == "botauto status":
                        telemetry_command_counts["status"] += 1
                    elif command == "botauto diagnose all":
                        telemetry_command_counts["diagnose"] += 1
                    elif command in {
                        "botauto trace all 128",
                        "botauto trace all 128 delta",
                    }:
                        telemetry_command_counts["trace"] += 1
                process.stdin.write(("\n".join(commands) + "\n").encode())
                process.stdin.flush()
                observations: list[tuple[dict[str, Any], float]] = []
                expected_status = monitor_statuses[-1] if monitor_statuses else None
                deadline = request_started + args.telemetry_timeout_sec
                report: dict[str, Any] = {
                    "requested": True,
                    "gate_passed": False,
                    "missing_channels": ["diagnosis", "trace"],
                    "rejections": ["forced_responses_not_observed"],
                    "commands": commands,
                }
                while time.monotonic() < deadline:
                    time.sleep(min(0.25, max(0.0, deadline - time.monotonic())))
                    record_process_resource_sample()
                    observed_at = time.monotonic()
                    for row in log_cursor.read_new_rows():
                        action = row.get("action")
                        if action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            observations.append((row, observed_at))
                        elif action == "botauto_trace":
                            trace_count += 1
                            observations.append((row, observed_at))
                    report = validate_forced_evidence_bundle(
                        observations,
                        expected_status,
                        requested_at_monotonic=request_started,
                        freshness_timeout_seconds=args.telemetry_timeout_sec,
                    )
                    report["requested"] = True
                    report["commands"] = commands
                    if report["gate_passed"]:
                        break
                combat_log_started = time.monotonic()
                process.stdin.write(b"botauto combatlog\n")
                process.stdin.flush()
                telemetry_command_counts["combat_log"] += 1
                combat_log_rows: list[dict[str, Any]] = []
                combat_log_deadline = combat_log_started + min(
                    15.0, float(args.telemetry_timeout_sec)
                )
                combat_log_report = validate_forced_combat_log_bundle(
                    combat_log_rows,
                    expected_status.get("cohort_id")
                    if isinstance(expected_status, dict) else None,
                )
                while time.monotonic() < combat_log_deadline:
                    time.sleep(min(
                        0.25,
                        max(0.0, combat_log_deadline - time.monotonic()),
                    ))
                    observed_at = time.monotonic()
                    for row in log_cursor.read_new_rows():
                        action = row.get("action")
                        if action in {
                            "botauto_combatlog_chunk",
                            "botauto_combatlog_complete",
                        }:
                            combat_log_rows.append(row)
                        elif action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            observations.append((row, observed_at))
                        elif action == "botauto_trace":
                            trace_count += 1
                            observations.append((row, observed_at))
                    combat_log_report = validate_forced_combat_log_bundle(
                        combat_log_rows,
                        expected_status.get("cohort_id")
                        if isinstance(expected_status, dict) else None,
                    )
                    if combat_log_report["gate_passed"]:
                        break
                report["combat_log"] = combat_log_report
                if combat_log_report["gate_passed"] is not True:
                    report["gate_passed"] = False
                    report.setdefault("missing_channels", []).append(
                        "combat_log"
                    )
                    report.setdefault("rejections", []).extend(
                        f"combat_log:{reason}"
                        for reason in combat_log_report["rejections"]
                    )
                report["response_wait_seconds"] = round(time.monotonic() - request_started, 3)
                return report

            flush_forced_evidence_callback = flush_forced_evidence

            while (deadline is None or time.monotonic() < deadline) and not (
                trace_transport_gate.get("terminal") is True
                if args.trace_transport_smoke
                else (
                    len(stable) >= args.required_stable_statuses
                    and recovery_accepted and drudge_accepted
                    and (
                        controller_route_hold_scheduler is None
                        or controller_route_hold_scheduler.complete
                    )
                )
            ):
                if process.poll() is not None:
                    break
                record_process_resource_sample()
                due_commands = telemetry_scheduler.commands_due(time.monotonic())
                if due_commands:
                    if controller_route_hold_scheduler is None:
                        due_commands = chainwielder_checkpoint_monitor_commands(
                            due_commands,
                            checkpoint_arm_command=checkpoint_arm_command,
                            checkpoint_arm_gate=checkpoint_arm_gate,
                        )
                    # A diagnosis is a point-in-time snapshot, not durable
                    # state. Only the diagnosis observed in this poll may
                    # drive the watchdog. Retain latest_diagnosis separately
                    # for the final report and semantic summaries.
                    fresh_diagnosis: dict[str, Any] | None = None
                    # Diagnosis carries the exact current decision per bot;
                    # trace is an incremental export so a long raid does not
                    # replay each bot's cumulative 128-entry history every
                    # five seconds. The server cursor retains every edge
                    # unless its bounded in-memory history was overrun.
                    for command in due_commands:
                        if command == "botauto status":
                            telemetry_command_counts["status"] += 1
                        elif command == "botauto diagnose all":
                            telemetry_command_counts["diagnose"] += 1
                        elif command in {
                            "botauto trace all 128",
                            "botauto trace all 128 delta",
                        }:
                            telemetry_command_counts["trace"] += 1
                    process.stdin.write(("\n".join(due_commands) + "\n").encode())
                    process.stdin.flush()
                    command_sent_at = time.monotonic()
                    telemetry_transport_ledger.command_sent(
                        due_commands,
                        sent_at_monotonic=command_sent_at,
                        scheduler_state=telemetry_scheduler.state(),
                    )
                    observations = collect_log_observations(
                        log_cursor, duration_seconds=1.0,
                    )
                    new_statuses: list[dict[str, Any]] = []
                    new_trace_rows: list[dict[str, Any]] = []
                    trace_receipt_indexes: list[int] = []
                    for observation in observations:
                        row = observation.row
                        if controller_route_hold_scheduler is not None:
                            hold_commands = controller_route_hold_scheduler.observe(
                                row
                            )
                            if hold_commands:
                                process.stdin.write(
                                    ("\n".join(hold_commands) + "\n").encode()
                                )
                                process.stdin.flush()
                            checkpoint_arm_command_sent = (
                                controller_route_hold_scheduler.command_counts[
                                    "arm"
                                ] == 1
                            )
                            if controller_route_hold_scheduler.failed:
                                raise RuntimeError(
                                    "controller route hold protocol rejected: "
                                    + str(
                                        controller_route_hold_scheduler
                                        .failure_reason
                                    )
                                )
                        action = row.get("action")
                        if action == "botauto_status":
                            new_statuses.append(row)
                        elif action == "botauto_diagnose":
                            diagnosis_count += 1
                            latest_diagnosis = row
                            fresh_diagnosis = row
                        elif action == "botauto_trace":
                            trace_count += 1
                            new_trace_rows.append(row)
                            receipt_index = telemetry_transport_ledger.observe(
                                observation
                            )
                            if receipt_index is not None:
                                trace_receipt_indexes.append(receipt_index)
                    telemetry_scheduler.observe_trace(
                        new_trace_rows, observed_at=time.monotonic(),
                    )
                    telemetry_transport_ledger.finalize_responses(
                        trace_receipt_indexes, telemetry_scheduler.state(),
                    )
                    if args.trace_transport_smoke:
                        trace_transport_gate = trace_transport_smoke.evaluate(
                            telemetry_transport_ledger.receipts()
                        )
                    monitor_statuses.extend(new_statuses)
                    for status in new_statuses:
                        telemetry_scheduler.observe_status(status)
                        if args.trace_transport_smoke:
                            continue
                        preflight_failure_reason, preflight_rejections = (
                            terminal_preflight_failure_reason(
                                status, profile_name=profile_name,
                            )
                        )
                        if preflight_failure_reason is not None:
                            forced_evidence_report = request_final_evidence(
                                "terminal_preflight_failure"
                            )
                            terminal_failure = {
                                "detected": True,
                                "classification": "infrastructure_abort",
                                "failure_reason": preflight_failure_reason,
                                "terminal_kind": "admission_preflight",
                                "terminal_status": status,
                                "status_rejections": preflight_rejections,
                                "route": status.get("validation_route"),
                                "raid_runtime": status.get("raid_runtime"),
                                "elapsed_seconds": round(
                                    time.monotonic() - monitor_started_at, 3
                                ),
                                "final_forced_evidence": forced_evidence_report.get(
                                    "gate_passed"
                                ) is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "terminal_failure_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get(
                                        "missing_channels", []
                                    ),
                                    "rejections": forced_evidence_report.get(
                                        "rejections", []
                                    ),
                                    "elapsed_seconds": round(
                                        time.monotonic() - monitor_started_at, 3
                                    ),
                                }
                            break
                        if (
                            checkpoint_arm_command is not None
                            and controller_route_hold_scheduler is None
                        ):
                            observe_chainwielder_checkpoint_arm_gate(
                                checkpoint_arm_gate,
                                status,
                                process=process,
                                recurrence_admission=recurrence_admission,
                                checkpoint_arm_command=checkpoint_arm_command,
                                actor_guid=args.chainwielder_checkpoint_actor_guid,
                                profile_name=profile_name,
                                scenario_id=scenario_id,
                                expected_route_manifest_sha256=runtime_assets.get(
                                    "route_sha256"
                                ),
                            )
                            checkpoint_arm_command_sent = (
                                checkpoint_arm_gate["command_sent"] is True
                            )
                        accepted, rejections = accepted_foundation_status(
                            status,
                            profile_name=profile_name,
                            route_partition=runtime_assets.get("route_partition"),
                        )
                        last_rejections = rejections
                        if accepted:
                            stable.append(status)
                        else:
                            stable.clear()
                        failure_reason, failure_rejections = terminal_runtime_failure_reason(
                            status, profile_name=profile_name,
                        )
                        if failure_reason is not None:
                            forced_evidence_report = request_final_evidence(
                                "terminal_runtime_failure"
                            )
                            terminal_failure = {
                                "detected": True,
                                "classification": "gameplay_failure",
                                "failure_reason": failure_reason,
                                "terminal_status": status,
                                "status_rejections": failure_rejections,
                                "route": status.get("validation_route"),
                                "raid_runtime": status.get("raid_runtime"),
                                "elapsed_seconds": round(
                                    time.monotonic() - monitor_started_at, 3
                                ),
                                "final_forced_evidence":
                                    forced_evidence_report.get("gate_passed") is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "terminal_failure_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get(
                                        "missing_channels", []
                                    ),
                                    "rejections": forced_evidence_report.get(
                                        "rejections", []
                                    ),
                                    "elapsed_seconds": round(
                                        time.monotonic() - monitor_started_at, 3
                                    ),
                                }
                            break
                    if terminal_failure.get("detected") is True:
                        break
                    if monitor_statuses and not args.trace_transport_smoke:
                        controller_watchdog = observe_capture_watchdog(
                            controller_watchdog_state,
                            monitor_statuses[-1],
                            fresh_diagnosis,
                            new_trace_rows,
                            profile_name=profile_name,
                            max_repeated_decisions=args.max_repeated_decision_count,
                            max_death_loops=args.max_death_loop_count,
                        )
                        if controller_watchdog.get("detected") is True:
                            forced_evidence_report = request_final_evidence(
                                "controller_watchdog_failure"
                            )
                            terminal_failure = {
                                "detected": True,
                                "classification": "gameplay_failure",
                                "failure_reason": controller_watchdog.get(
                                    "failure_reason"
                                ),
                                "terminal_status": monitor_statuses[-1],
                                "watchdog": controller_watchdog,
                                "route": monitor_statuses[-1].get("validation_route"),
                                "raid_runtime": monitor_statuses[-1].get("raid_runtime"),
                                "elapsed_seconds": round(
                                    time.monotonic() - monitor_started_at, 3
                                ),
                                "final_forced_evidence": forced_evidence_report.get(
                                    "gate_passed"
                                ) is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "terminal_failure_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get(
                                        "missing_channels", []
                                    ),
                                    "rejections": forced_evidence_report.get(
                                        "rejections", []
                                    ),
                                    "elapsed_seconds": round(
                                        time.monotonic() - monitor_started_at, 3
                                    ),
                                }
                            break
                    telemetry_now = time.monotonic()
                    stale_channels = observe_telemetry_freshness(
                        telemetry_freshness,
                        {
                            "status": len(monitor_statuses),
                            "diagnosis": diagnosis_count,
                            "trace": trace_count,
                        },
                        telemetry_now,
                        args.telemetry_timeout_sec,
                    )
                    if stale_channels:
                        forced_evidence_report = request_final_evidence(
                            "telemetry_channel_stale"
                        )
                        telemetry_abort = {
                            "detected": True,
                            "classification": "infrastructure_abort",
                            "reason": "telemetry_channel_stale",
                            "stale_channels": stale_channels,
                            "timeout_seconds": args.telemetry_timeout_sec,
                            "elapsed_seconds": round(telemetry_now - monitor_started_at, 3),
                            "channel_state": telemetry_freshness,
                        }
                        break
                    if monitor_statuses and not args.trace_transport_smoke:
                        signature = semantic_progress_signature(
                            monitor_statuses[-1], latest_diagnosis,
                        )
                        if observe_monotonic_semantic_progress(
                            semantic_progress_state,
                            monitor_statuses[-1], latest_diagnosis,
                        ):
                            last_semantic_progress_at = time.monotonic()
                            unchanged_semantic_samples = 1
                        else:
                            unchanged_semantic_samples += 1
                        stalled_for = time.monotonic() - last_semantic_progress_at
                        if (unchanged_semantic_samples >= args.semantic_stall_min_samples
                                and stalled_for >= args.semantic_stall_sec):
                            forced_evidence_report = flush_forced_evidence()
                            semantic_stall = {
                                "detected": True,
                                "classification": "gameplay_failure",
                                "failure_reason": "semantic_stall",
                                "terminal_status": monitor_statuses[-1],
                                "stalled_for_seconds": round(stalled_for, 3),
                                "unchanged_samples": unchanged_semantic_samples,
                                "semantic_signature": signature,
                                "monotonic_progress_state": semantic_progress_state,
                                "route": monitor_statuses[-1].get("validation_route"),
                                "raid_runtime": monitor_statuses[-1].get("raid_runtime"),
                                "diagnosis_rows": diagnosis_count,
                                "trace_rows": trace_count,
                                "final_forced_evidence": forced_evidence_report.get("gate_passed") is True,
                                "final_forced_evidence_report": forced_evidence_report,
                            }
                            if forced_evidence_report.get("gate_passed") is not True:
                                telemetry_abort = {
                                    "detected": True,
                                    "classification": "infrastructure_abort",
                                    "reason": "final_forced_evidence_incomplete",
                                    "missing_channels": forced_evidence_report.get("missing_channels", []),
                                    "rejections": forced_evidence_report.get("rejections", []),
                                    "elapsed_seconds": round(time.monotonic() - monitor_started_at, 3),
                                }
                            break
                    if recovery_required:
                        recovery_accepted, _ = accepted_native_recovery(
                            monitor_statuses,
                            profile_name=profile_name,
                        )
                    if drudge_observed:
                        drudge_accepted, _ = accepted_drudge_contract(
                            monitor_statuses, frozen_anchors=drudge_frozen_anchors,
                        )
                    if monitor_statuses and not args.trace_transport_smoke:
                        runtime = monitor_statuses[-1].get("raid_runtime") or {}
                        status = monitor_statuses[-1]
                        request_identity = native_readycheck_request_identity(status)
                        ready_for_native_check = ready_for_native_readycheck(status)
                        if ready_for_native_check and readycheck_requested_for != request_identity:
                            # This invokes only the native Group ready-check packet path.
                            # It cannot alter encounter, death, movement, or resurrection state.
                            process.stdin.write(b"botauto readycheck\n")
                            process.stdin.flush()
                            readycheck_requested_for = request_identity
                time.sleep(0.25)

            if (
                controller_route_hold_scheduler is not None
                and not controller_route_hold_scheduler.complete
            ):
                controller_route_hold_scheduler.finish()
                raise RuntimeError(
                    "controller route hold protocol incomplete: "
                    + str(controller_route_hold_scheduler.failure_reason)
                )

            # Capture one last live process sample before native shutdown so
            # the final CPU/RSS interval includes the terminal polling work.
            record_process_resource_sample(force=True)
            if (
                not args.trace_transport_smoke
                and forced_evidence_report.get("requested") is not True
            ):
                forced_evidence_report = request_final_evidence(
                    "terminal_gate_or_process_exit"
                )
            shutdown = bounded_native_shutdown(process, 60.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
            if shutdown["operator_interrupted"]:
                operator_interrupt = True
                startup_error = "KeyboardInterrupt:operator_interrupt"
                signal.signal(signal.SIGINT, signal.SIG_IGN)
        except KeyboardInterrupt:
            # Do not let an operator abort become a Python traceback.  Keep
            # the already captured bytes, issue the native cleanup sequence,
            # and let the immutable report classify this as an infrastructure
            # abort with an explicit operator reason.
            operator_interrupt = True
            startup_error = "KeyboardInterrupt:operator_interrupt"
            signal.signal(signal.SIGINT, signal.SIG_IGN)
            forced_evidence_report = request_final_evidence("operator_interrupt")
            shutdown = bounded_native_shutdown(process, 20.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
        except Exception as error:  # captured as infrastructure evidence below
            startup_error = f"{type(error).__name__}:{error}"
            forced_evidence_report = request_final_evidence("capture_exception")
            shutdown = bounded_native_shutdown(process, 20.0)
            stop_commands_sent = bool(shutdown["commands_sent"])
            shutdown_error = shutdown["error"]
        finally:
            # Once capture teardown begins, a further SIGINT must not tear
            # through raw-log normalization or immutable report publication.
            # Record the request without raising, finish bounded cleanup, and
            # classify the run as an operator infrastructure abort below.
            def defer_post_capture_interrupt(_signum: int, _frame: Any) -> None:
                nonlocal operator_interrupt, startup_error
                operator_interrupt = True
                startup_error = "KeyboardInterrupt:operator_interrupt"

            signal.signal(signal.SIGINT, defer_post_capture_interrupt)
            if process is not None and process.poll() is None:
                try:
                    os.killpg(process.pid, 15)
                    process.wait(timeout=10)
                except (subprocess.TimeoutExpired, KeyboardInterrupt):
                    try:
                        os.killpg(process.pid, 9)
                        process.wait(timeout=10)
                    except (OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
                        pass
                except OSError:
                    pass
        # Move the captured file into its caller-selected immutable location;
        # do not delete the raw worldserver log after capture.
        os.replace(log_path, server_log_output)
        log_bytes = server_log_output.read_bytes()

    normalized_rows = normalized_batch_payload(log_bytes, profile_name=profile_name)
    telemetry_envelopes = _required_telemetry_envelope_report(
        normalized_rows, profile_name=profile_name,
    )
    raw_payload_sha256, raw_payload_rows = write_normalized_batch(raw_output, normalized_rows)
    # The complete log was decoded once into normalized_rows above.  Project
    # final action channels from those parsed payloads instead of decoding the
    # complete log five more times after every uncapped capture.
    statuses = action_payloads(normalized_rows, "botauto_status")
    active_statuses = [
        status for status in statuses
        if isinstance(status.get("raid_runtime"), dict)
        and status["raid_runtime"].get("active") is True
    ]
    diagnoses = action_payloads(normalized_rows, "botauto_diagnose")
    traces = action_payloads(normalized_rows, "botauto_trace")
    combat_log_payloads = [
        row["payload"] for row in normalized_rows
        if row.get("action") in {
            "botauto_combatlog_chunk", "botauto_combatlog_complete",
        }
        and isinstance(row.get("payload"), dict)
    ]
    combat_log_transport = combat_log_transport_status(combat_log_payloads)
    combat_log = combined_combat_log(combat_log_payloads)
    combat_analysis = analyze_combat_log(combat_log) if combat_log else {}
    combat_log_transport["gate_passed"] = bool(
        combat_log_transport.get("complete_marker")
        and combat_log_transport.get("reassembled")
        and combat_log
        and combat_analysis
    )
    profiles = action_payloads(normalized_rows, "botauto_profile")
    stop_rows = action_payloads(normalized_rows, "botauto_stop")
    recovery_accepted, recovery_rejections = (
        accepted_native_recovery(active_statuses, profile_name=profile_name) if recovery_required
        else (True, ["native_recovery_not_required_for_diagnostic_partition"])
    )
    drudge_accepted, drudge_rejections = (
        accepted_drudge_contract(active_statuses, frozen_anchors=drudge_frozen_anchors)
        if drudge_observed
        else (True, ["drudge_contract_not_required_for_diagnostic_partition"])
    )
    cleanup_status = statuses[-1] if statuses else {}
    cleanup_ok = cleanup_status.get("bots") == 0 and cleanup_status.get("lease_count") == 0
    postflight = preflight_runtime_exclusions(worktree)
    process_absent = not postflight["process_overlap"]
    forbidden_entries = _forbidden_assistance_entries(normalized_rows)
    identity_after = git_identity(worktree)
    identity_stable = identity_before == identity_after
    process_return_code = process.returncode if process is not None else None
    semantic_stall = locals().get("semantic_stall", {"detected": False})
    controller_watchdog = locals().get(
        "controller_watchdog",
        {
            "detected": False,
            "classification": None,
            "failure_reason": None,
            "max_repeated_decisions": args.max_repeated_decision_count,
            "max_death_loops": args.max_death_loop_count,
            "repeated_decision_count": 0,
            "death_loop_count": 0,
            "rejections": ["controller_watchdog_not_started"],
        },
    )
    controller_terminal = None
    if (
        isinstance(terminal_failure, dict)
        and terminal_failure.get("detected") is True
        and terminal_failure.get("failure_reason") in _CONTROLLER_TERMINAL_FAILURE_REASONS
    ):
        controller_terminal = terminal_failure
    elif isinstance(semantic_stall, dict) and semantic_stall.get("detected") is True:
        controller_terminal = semantic_stall
    demux_report = evidence_demux_report(
        normalized_rows,
        profile_name=profile_name,
        controller_terminal=controller_terminal,
    )
    demux_rejections = demux_report["rejections"]
    trace_transport_gate = locals().get(
        "trace_transport_gate", trace_transport_smoke.evaluate([]),
    )
    trace_transport_demux = trace_transport_smoke.demux_report(
        normalized_rows, trace_transport_gate,
    ) if args.trace_transport_smoke else {
        "gate_passed": None,
        "rejections": ["trace_transport_smoke_not_requested"],
    }
    telemetry_abort = locals().get("telemetry_abort", {"detected": False})
    primary_gameplay_failure = _primary_gameplay_terminal(
        terminal_failure, semantic_stall,
    )
    terminal_evidence_incomplete = False if args.trace_transport_smoke else _terminal_evidence_incomplete(
        primary_gameplay_failure=primary_gameplay_failure,
        forced_evidence_report=forced_evidence_report,
        telemetry_abort=telemetry_abort,
        telemetry_envelopes=telemetry_envelopes,
        demux_rejections=demux_rejections,
    )
    resource_summary = summarize_process_resource_samples(
        resource_samples,
        tick_rate=resource_tick_rate,
        sampling_errors=resource_sampling_errors,
        sampling_error_count=resource_sampling_error_count,
    )
    # From this point through the two immutable output writes, ignore another
    # interrupt. Any prior deferred interrupt is already reflected in the
    # variables used to construct the report and success classification.
    signal.signal(signal.SIGINT, signal.SIG_IGN)
    controller_route_hold_receipt = (
        controller_route_hold_scheduler.receipt()
        if controller_route_hold_scheduler is not None
        else {
            "schema": "generic_controller_route_hold_scheduler_v1",
            "enabled": False,
            "phase": "not_requested",
            "gate_passed": None,
            "failure_reason": None,
        }
    )
    profile_selection_accepted = bool(
        (
            len(profiles) == 1
            and profiles[0].get("ok") is True
            and profiles[0].get("cohort_id") == "default"
            and profiles[0].get("active_profile") == profile_name
        )
        or (
            controller_route_hold_scheduler is not None
            and controller_route_hold_receipt.get("start_ack_count") == 1
            and (
                controller_route_hold_receipt.get("native_scope") or {}
            ).get("runtime_profile") == profile_name
        )
    )
    common_success = (
        startup_error is None
        and operator_interrupt is False
        and process_return_code == 0
        and cleanup_ok
        and bool(stop_rows and stop_rows[-1].get("ok") is True)
        and process_absent
        and postflight["passed"]
        and not forbidden_entries
        and profile_selection_accepted
        and identity_stable
        and terminal_failure.get("detected") is not True
        and telemetry_abort.get("detected") is not True
        and bool(diagnoses)
        and bool(traces)
    )
    success = common_success and (
        (
            trace_transport_gate.get("gate_passed") is True
            and trace_transport_demux.get("gate_passed") is True
            and recurrence_admission is None
        )
        if args.trace_transport_smoke
        else (
            len(stable) >= args.required_stable_statuses
            and recovery_accepted
            and (not drudge_required or drudge_accepted)
            and telemetry_envelopes["gate_passed"]
            and not demux_rejections
            and semantic_stall.get("detected") is not True
            and forced_evidence_report.get("gate_passed") is True
            and combat_log_transport["gate_passed"] is True
            and (
                controller_route_hold_scheduler is None
                or controller_route_hold_receipt.get("gate_passed") is True
            )
        )
    )
    evidence_incomplete = bool(
        telemetry_abort.get("detected") is True
        or (
            not args.trace_transport_smoke
            and telemetry_envelopes.get("gate_passed") is not True
        )
        or (
            trace_transport_gate.get("gate_passed") is not True
            or trace_transport_demux.get("gate_passed") is not True
            if args.trace_transport_smoke
            else (
                bool(demux_rejections)
                or forced_evidence_report.get("gate_passed") is not True
                or combat_log_transport.get("gate_passed") is not True
            )
        )
    )
    operational_infrastructure_abort = bool(
        startup_error
        or operator_interrupt
        or process_return_code != 0
        or not process_absent
        or not postflight["passed"]
        or not cleanup_ok
        or not identity_stable
        or terminal_failure.get("classification") == "infrastructure_abort"
    )
    if args.trace_transport_smoke:
        if success:
            capture_classification = "trace_transport_smoke_passed"
        elif operational_infrastructure_abort:
            capture_classification = "trace_transport_smoke_infrastructure_abort"
        elif trace_transport_gate.get("terminal") is True:
            capture_classification = "trace_transport_smoke_failed_verification"
        else:
            capture_classification = "trace_transport_smoke_noncompletion"
    else:
        capture_classification = _capture_classification(
            success=success,
            forbidden_entries=forbidden_entries,
            primary_gameplay_failure=primary_gameplay_failure,
            operational_infrastructure_abort=operational_infrastructure_abort,
            evidence_incomplete=evidence_incomplete,
        )
    report = {
        "schema_version": 1,
        "capture_id": f"cata_raid_phase1_{profile_name}_v1",
        "classification": capture_classification,
        "claim_scope": {
            **trace_transport_smoke.claim_scope(),
            "transport_admitted": (
                success if args.trace_transport_smoke else None
            ),
        } if args.trace_transport_smoke else None,
        "trace_transport_smoke": {
            "requested": args.trace_transport_smoke,
            "pressure_warmup_seconds": (
                trace_transport_smoke.PRESSURE_WARMUP_SECONDS
                if args.trace_transport_smoke else None
            ),
            "transport_gate": trace_transport_gate,
            "controller_demux_gate": trace_transport_demux,
            "pressure_receipt_gate": trace_transport_pressure_gate,
            "pressure_command_count": telemetry_command_counts["trace_pressure"],
            "one_start_owned_by_capture": True,
        },
        "terminal_evidence_incomplete": terminal_evidence_incomplete,
        "started_at_utc": started_utc,
        "identity": identity_before,
        "scenario_id": scenario_id,
        "runtime_profile": profile_name,
        "pool_tag_filter": runtime_assets.get("pool_tag_filter"),
        "identity_stable_during_run": identity_stable,
        "recurrence_admission": recurrence_admission,
        "chainwielder_checkpoint_arm": {
            "required": checkpoint_arm_command is not None,
            "actor_guid": args.chainwielder_checkpoint_actor_guid,
            "seal_sha256": (
                recurrence_admission.get("checkpoint_seal_sha256")
                if isinstance(recurrence_admission, dict) else None
            ),
            "command_sent": checkpoint_arm_command_sent,
            "gate": checkpoint_arm_gate,
        },
        "controller_route_hold": controller_route_hold_receipt,
        "build_provenance": build_provenance,
        "runtime_profile_assets": runtime_assets,
        "drudge_navmesh_preflight": drudge_navmesh_preflight,
        "binary_sha256": build_provenance.get("binary_sha256"),
        "config_sha256": sha256_file(config),
        "worldserver_exit_code": process_return_code,
        "startup_error": startup_error,
        "operator_interrupt": operator_interrupt,
        "shutdown_error": shutdown_error,
        "native_shutdown": {
            "commands_sent": stop_commands_sent,
            "bounded_wait_seconds": 20 if operator_interrupt else 60,
            "operator_reason": "operator_interrupt" if operator_interrupt else None,
        },
        "resource_sampling": {
            "source": "proc_pid_stat_and_proc_pid_status_via_capture_no_bots_baseline",
            "interval_seconds": args.resource_sample_interval_sec,
            "samples_retained": True,
            "summary": resource_summary,
            "samples": resource_samples,
            "sampling_errors": resource_sampling_errors,
        },
        "required_stable_statuses": args.required_stable_statuses,
        "accepted_stable_statuses": len(stable),
        "last_foundation_rejections": last_rejections,
        "native_recovery_accepted": recovery_accepted,
        "native_recovery_required": recovery_required,
        "native_recovery_rejections": recovery_rejections,
        "drudge_contract_accepted": drudge_accepted,
        "drudge_contract_required": drudge_required,
        "drudge_contract_rejections": drudge_rejections,
        "terminal_failure": terminal_failure,
        "semantic_stall": semantic_stall,
        "telemetry_abort": telemetry_abort,
        "telemetry_schedule": {
            "status_interval_seconds": args.status_interval_sec,
            "diagnose_interval_seconds": args.diagnose_interval_sec,
            "trace_interval_seconds": args.trace_interval_sec,
            "commands_sent": telemetry_command_counts,
            "scheduler_state": telemetry_scheduler.state() if telemetry_scheduler is not None else None,
            "trace_transport_receipts": telemetry_transport_ledger.receipts(),
            "material_status_diagnosis": "immediate",
            "stall_bundle": (
                "forced_diagnose_trace_delta_and_bounded_combat_log_before_termination"
            ),
            "final_forced_evidence": forced_evidence_report,
        },
        "accepted_raid_runtime": (
            None if args.trace_transport_smoke
            else (stable[-1].get("raid_runtime") if stable else None)
        ),
        "diagnose_observed": bool(diagnoses),
        "trace_observed": bool(traces),
        "combat_log_transport": combat_log_transport,
        "combat_analysis": combat_analysis,
        "required_telemetry_envelopes": telemetry_envelopes,
        "profile_selection_observed": profile_selection_accepted,
        "stop_observed": bool(stop_rows),
        "native_event_evidence": {
            "source": "botauto_status.raid_runtime",
            "ordered_transition_reconstruction": recovery_accepted,
            "rejections": recovery_rejections,
            "synthetic_wipe_or_encounter_command_sent": False,
        },
        "drudge_contract_evidence": {
            "source": "botauto_status.raid_runtime.drudge_charge",
            "acceptance_role": "diagnostic_only",
            "independently_reconstructed": drudge_accepted,
            "rejections": drudge_rejections,
            "requirements": "two delivered native Rushes per exact source; one non-early 20000ms interval per source; exact-roster reseparation; exact native tank ownership; any recorded taunts are successful tank casts; tank health-sync hold; all seven offensive slots use trained single-target profiles",
        },
        "forbidden_assistance": {
            "observed": bool(forbidden_entries),
            "entries": forbidden_entries,
            "gate_passed": not forbidden_entries,
            "policy": "native encounter events only; no forced state, teleport, spawn, kill, resurrection, or aura assistance",
        },
        "watchdog": {
            "policy": "capture-process-heartbeat-terminal-gate-driven",
            "controller_policy": "scoped-repeated-decision-or-death-loop-terminal",
            "heartbeat_rows": len(statuses) + len(diagnoses) + len(traces),
            "wall_clock_mode": "uncapped" if args.observe_sec == 0 else "bounded_diagnostic",
            "observe_window_seconds": args.observe_sec if args.observe_sec else None,
            "startup_timeout_seconds": args.startup_timeout_sec,
            "semantic_stall_seconds": args.semantic_stall_sec,
            "semantic_stall_min_samples": args.semantic_stall_min_samples,
            "max_repeated_decisions": args.max_repeated_decision_count,
            "max_death_loops": args.max_death_loop_count,
            "max_repeated_decision_count": args.max_repeated_decision_count,
            "max_death_loop_count": args.max_death_loop_count,
            "controller_terminal": controller_watchdog,
            "telemetry_timeout_seconds": args.telemetry_timeout_sec,
            "telemetry_intervals_seconds": {
                "status": args.status_interval_sec,
                "diagnose": args.diagnose_interval_sec,
                "trace": args.trace_interval_sec,
            },
            "telemetry_commands_sent": telemetry_command_counts,
            "required_channels": [
                "status", "diagnosis", "trace", "combat_log",
            ],
            "healthy": (
                startup_error is None
                and operator_interrupt is False
                and telemetry_abort.get("detected") is not True
                and forced_evidence_report.get("gate_passed") is True
                and bool(statuses) and bool(diagnoses) and bool(traces)
                and process_return_code == 0 and process_absent
            ),
        },
        "preflight": preflight,
        "postflight": postflight,
        "cleanup": {
            "zero_bots": cleanup_status.get("bots") == 0,
            "zero_leases": cleanup_status.get("lease_count") == 0,
            "stop_observed": bool(stop_rows),
            "stop_ok": bool(stop_rows and stop_rows[-1].get("ok") is True),
            "worldserver_process_absent": process_absent,
            "gate_passed": cleanup_ok and process_absent and bool(stop_rows and stop_rows[-1].get("ok") is True),
        },
        "cleanup_zero_bots_and_leases": cleanup_ok,
        "log_sha256": hashlib.sha256(log_bytes).hexdigest(),
        "log_bytes": len(log_bytes),
        "raw_log_retained": True,
        "raw_server_log": {
            "path": str(server_log_output),
            "sha256": hashlib.sha256(log_bytes).hexdigest(),
            "bytes": len(log_bytes),
            "immutable": True,
        },
        "raw_normalized_batch": {
            "path": str(raw_output),
            "sha256": raw_payload_sha256,
            "row_count": raw_payload_rows,
            "immutable": True,
        },
        "evidence_demux": {
            "normalized_schema_version": 2,
            "retained_rows": demux_report["retained_rows"],
            "bound_rows": demux_report["bound_rows"],
            "rejected_rows": demux_report["rejected_rows"],
            "unchecked_rows": demux_report["unchecked_rows"],
            "canonical_identity_sha256": demux_report["canonical_identity_sha256"],
            "canonical_roster_sha256": demux_report["canonical_roster_sha256"],
            "required_telemetry_envelopes": demux_report["required_telemetry_envelopes"],
            "actor_binding_counts": demux_report["actor_binding_counts"],
            "trace_discontinuities": demux_report["trace_discontinuities"],
            "channels": dict(Counter(str(row.get("evidence_channel")) for row in normalized_rows)),
            "every_retained_row_demuxed": (
                demux_report["bound_rows"] == demux_report["retained_rows"]
                and demux_report["unchecked_rows"] == 0
            ),
            "identity_rejections": demux_rejections,
            "gate_passed": demux_report["gate_passed"],
        },
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    report["artifact_inventory"] = [
        _artifact_record(raw_output, "raw_normalized_jsonl"),
        _artifact_record(server_log_output, "raw_worldserver_log"),
    ]
    # The report entry is a deliberate self-reference.  Its digest is the
    # canonical report hash after nulling both self-reference fields; this is
    # stable and independently reproducible without a circular hash.
    report["artifact_inventory"].append(
        {
            "kind": "capture_report",
            "path": str(output),
            "sha256": None,
            "bytes": 0,
            "immutable": True,
            "hash_basis": "canonical_report_with_report_sha256_and_self_inventory_sha256_null",
        }
    )
    for _ in range(8):
        encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        report["artifact_inventory"][-1]["bytes"] = len(encoded)
        hash_payload = json.loads(json.dumps(report))
        hash_payload["report_sha256"] = None
        hash_payload["artifact_inventory"][-1]["sha256"] = None
        report_hash = hashlib.sha256(
            json.dumps(hash_payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        report["artifact_inventory"][-1]["sha256"] = report_hash
        report["report_sha256"] = report_hash
        final_encoded = (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")
        if report["artifact_inventory"][-1]["bytes"] == len(final_encoded):
            break
    output.write_bytes(final_encoded)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if success else 2


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

from math import isfinite
import re
from typing import Any

try:
    from tools.raid_program.capture_runtime_identity import (
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _runtime_identity,
    )
    from tools.raid_program.capture_value_types import _positive_int
except ModuleNotFoundError:
    from capture_runtime_identity import (
        _roster_binding_identity,
        _roster_binding_lifecycle_rejections,
        _runtime_identity,
    )
    from capture_value_types import _positive_int


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

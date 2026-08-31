#!/usr/bin/env python3
"""Fail-closed verifier for the Magmaw transfer-lane shadow episode."""

from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


SCHEMA = "magmaw_shadow_observation_gate_v1"
EXIT_CODES = {"pass": 0, "fail": 1, "not_exercised": 2}
CHANNEL_BY_ACTION = {
    "botauto_controller_route_hold": "controller_protocol",
    "botauto_chainwielder_checkpoint": "controller_protocol",
    "botauto_status": "status",
    "botauto_diagnose": "diagnosis",
    "botauto_trace": "trace",
    "botauto_combatlog_chunk": "combat_log",
    "botauto_combatlog_complete": "combat_log",
    "botauto_profile": "profile_selection",
    "botauto_readycheck": "native_action",
    "botauto_stop": "cleanup",
}


class EvidenceError(ValueError):
    pass


class NotExercised(EvidenceError):
    pass


@dataclass(frozen=True)
class Scope:
    key: str
    cohort_id: str
    attempt_id: int
    wipe_generation: int
    route_generation: int
    node_id: str
    map_id: int
    instance_id: int
    encounter_id: str


@dataclass(frozen=True)
class ActiveAssignment:
    scope_key: str
    episode_generation: int
    fire_mage_guid: int
    hunter_guid: int
    destination: tuple[float, float, float]


def _integer(value: Any, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise EvidenceError(f"invalid_{name}")
    return value


def _positive_integer(value: Any, name: str) -> int:
    parsed = _integer(value, name)
    if parsed <= 0:
        raise EvidenceError(f"invalid_{name}")
    return parsed


def _finite(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) \
            or not math.isfinite(value):
        raise EvidenceError(f"invalid_{name}")
    return float(value)


def _actor_guid(bot: Any) -> int:
    if not isinstance(bot, dict):
        raise EvidenceError("invalid_telemetry_actor")
    identity = bot.get("identity")
    value = identity.get("bot_guid") if isinstance(identity, dict) else bot.get("bot_guid")
    return _positive_integer(value, "telemetry_actor_guid")


def _parse_scope(key: Any) -> Scope:
    if not isinstance(key, str) or not key:
        raise EvidenceError("invalid_scope_key")
    parts = key.split(":", 7)
    if len(parts) != 8 or not parts[0] or not parts[4] or not parts[7]:
        raise EvidenceError("invalid_scope_key")
    try:
        scope = Scope(key, parts[0], int(parts[1]), int(parts[2]), int(parts[3]),
                      parts[4], int(parts[5]), int(parts[6]), parts[7])
    except ValueError as exc:
        raise EvidenceError("invalid_scope_key") from exc
    if scope.attempt_id <= 0 or scope.wipe_generation < 0 \
            or scope.route_generation <= 0 or scope.map_id != 669 \
            or scope.instance_id <= 0 \
            or scope.node_id != "bwd.magmaw.encounter" \
            or scope.encounter_id != "blackwing_descent.magmaw":
        raise EvidenceError("invalid_magmaw_lifecycle_scope")
    return scope


def _validate_actor_binding(
    bot: Any, *, action: str, sequence: int, canonical_identity: str,
    roster_identity: str, cohort_id: str,
) -> None:
    actor = _actor_guid(bot)
    binding = bot.get("identity_binding")
    if not isinstance(binding, dict) or binding.get("state") != "bound" \
            or binding.get("scope") != "telemetry_actor":
        raise EvidenceError(f"unbound_{action}_actor")
    if (binding.get("canonical_identity_sha256"), binding.get("roster_sha256")) \
            != (canonical_identity, roster_identity):
        raise EvidenceError(f"{action}_actor_identity_mismatch")
    correlation = binding.get("correlation")
    if not isinstance(correlation, dict):
        raise EvidenceError(f"invalid_{action}_actor_correlation")
    expected = {
        "capture_sequence": sequence,
        "telemetry_channel": action,
        "bot_guid": actor,
        "cohort_id": cohort_id,
    }
    if any(correlation.get(name) != value for name, value in expected.items()):
        raise EvidenceError(f"{action}_actor_correlation_mismatch")
    for name in ("scenario", "runtime_profile_hash"):
        if not isinstance(correlation.get(name), str) or not correlation[name]:
            raise EvidenceError(f"invalid_{action}_actor_correlation")
    for name in ("server_epoch", "attempt_id", "runtime_profile_generation",
                 "assignment_generation", "route_generation"):
        _positive_integer(correlation.get(name), f"{action}_{name}")
    wipe = _integer(correlation.get("wipe_generation"), f"{action}_wipe_generation")
    if wipe < 0:
        raise EvidenceError(f"invalid_{action}_wipe_generation")
    if binding.get("reasons") not in (None, []):
        raise EvidenceError(f"rejected_{action}_actor_reasons")
    if action == "trace":
        transport = binding.get("trace_transport")
        if not isinstance(transport, dict) \
                or transport.get("mode") not in ("delta", "bounded_full_snapshot"):
            raise EvidenceError("invalid_trace_actor_transport")
        if any(name in transport for name in (
                "missing_sequence_start", "missing_sequence_end",
                "discontinuity_explicit", "discontinuity_epoch_id")):
            raise EvidenceError("trace_actor_delta_gap")
        entries = bot.get("entries")
        if not isinstance(entries, list) \
                or transport.get("entry_count") != len(entries):
            raise EvidenceError("trace_actor_transport_count_mismatch")


def _rows(paths: Iterable[Path]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    last_sequence = -1
    canonical_identity = ""
    roster_identity = ""
    canonical_cohort = ""
    canonical_actor_context: tuple[Any, ...] | None = None
    for path in paths:
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except OSError as exc:
            raise EvidenceError(f"unreadable_input:{path}") from exc
        for line_number, line in enumerate(lines, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise EvidenceError(f"malformed_json:{path}:{line_number}") from exc
            if not isinstance(row, dict) or row.get("normalized_schema_version") != 2:
                raise EvidenceError("unsupported_normalized_schema")
            payload = row.get("payload")
            binding = row.get("identity_binding")
            if not isinstance(payload, dict) or payload.get("action") != row.get("action"):
                raise EvidenceError("invalid_normalized_payload")
            expected_channel = CHANNEL_BY_ACTION.get(str(row.get("action")), "other")
            if row.get("evidence_channel") != expected_channel:
                raise EvidenceError("normalized_evidence_channel_mismatch")
            if not isinstance(binding, dict) or binding.get("state") != "bound":
                raise EvidenceError("unbound_normalized_row")
            sequence = _positive_integer(row.get("capture_sequence"), "capture_sequence")
            if sequence <= last_sequence:
                raise EvidenceError("non_monotonic_capture_sequence")
            last_sequence = sequence
            row_identity = binding.get("canonical_identity_sha256")
            row_roster = binding.get("roster_sha256")
            row_cohort = binding.get("cohort_id")
            if not isinstance(row_identity, str) or not row_identity \
                    or not isinstance(row_roster, str) or not row_roster \
                    or not isinstance(row_cohort, str) or not row_cohort:
                raise EvidenceError("missing_canonical_evidence_identity")
            if not canonical_identity:
                canonical_identity, roster_identity, canonical_cohort = (
                    row_identity, row_roster, row_cohort)
            elif (row_identity, row_roster, row_cohort) != (
                    canonical_identity, roster_identity, canonical_cohort):
                raise EvidenceError("mixed_canonical_evidence_identity")
            if payload.get("action") in ("botauto_diagnose", "botauto_trace"):
                channel = CHANNEL_BY_ACTION[payload["action"]]
                bots = payload.get("bots")
                if not isinstance(bots, list):
                    raise EvidenceError(f"invalid_{channel}_bots")
                for bot in bots:
                    _validate_actor_binding(
                        bot, action=channel, sequence=sequence,
                        canonical_identity=canonical_identity,
                        roster_identity=roster_identity,
                        cohort_id=canonical_cohort)
                    correlation = bot["identity_binding"]["correlation"]
                    actor_context = tuple(correlation.get(name) for name in (
                        "scenario", "cohort_id", "server_epoch", "attempt_id",
                        "runtime_profile_generation", "runtime_profile_hash",
                    ))
                    if canonical_actor_context is None:
                        canonical_actor_context = actor_context
                    elif actor_context != canonical_actor_context:
                        raise EvidenceError("mixed_telemetry_actor_correlation")
            rows.append(row)
    if not rows:
        raise EvidenceError("empty_input")
    return rows


def _actions(rows: list[dict[str, Any]], action: str) -> list[dict[str, Any]]:
    return [row["payload"] for row in rows if row["payload"].get("action") == action]


def _task_identity(task: dict[str, Any]) -> tuple[str, int, int, int]:
    return (
        str(task.get("lifecycle_scope", "")),
        _positive_integer(task.get("episode_generation"), "episode_generation"),
        _positive_integer(task.get("actor_guid"), "actor_guid"),
        _positive_integer(task.get("task_generation"), "task_generation"),
    )


def _summary_identity(summary: dict[str, Any]) -> tuple[str, int, int, int]:
    return (
        str(summary.get("scope_key", "")),
        _positive_integer(summary.get("episode_generation"), "episode_generation"),
        _positive_integer(summary.get("actor_guid"), "actor_guid"),
        _positive_integer(summary.get("task_generation"), "task_generation"),
    )


def _summary_rows(accumulator: Any) -> list[dict[str, Any]]:
    if not isinstance(accumulator, dict):
        raise EvidenceError("invalid_episode_accumulator")
    summaries: list[dict[str, Any]] = []
    active = accumulator.get("active")
    if active is not None:
        if not isinstance(active, dict):
            raise EvidenceError("invalid_active_episode_summary")
        summaries.append(active)
    retired = accumulator.get("retired")
    if not isinstance(retired, list):
        raise EvidenceError("invalid_retired_episode_summaries")
    if any(not isinstance(item, dict) for item in retired):
        raise EvidenceError("invalid_retired_episode_summary")
    summaries.extend(retired)
    return summaries


def _destination(value: Any, name: str, *, available: bool = False) \
        -> tuple[float, float, float]:
    if not isinstance(value, dict) or (available and value.get("available") is not True):
        raise EvidenceError(f"missing_{name}")
    return tuple(_finite(value.get(axis), f"{name}_{axis}") for axis in ("x", "y", "z"))


def _collect_status(statuses: list[dict[str, Any]]) -> tuple[
    list[ActiveAssignment],
    dict[tuple[str, int, int, int], list[dict[str, Any]]],
    dict[tuple[str, int, int, int], list[dict[str, Any]]],
]:
    assignments: list[ActiveAssignment] = []
    summaries: dict[tuple[str, int, int, int], list[dict[str, Any]]] = {}
    tasks: dict[tuple[str, int, int, int], list[dict[str, Any]]] = {}
    for payload in statuses:
        shadow = payload.get("magmaw_transfer_lane_shadow")
        if not isinstance(shadow, dict):
            raise EvidenceError("missing_magmaw_transfer_lane_shadow")
        if shadow.get("active") is True:
            scope = _parse_scope(shadow.get("lifecycle_scope"))
            episode = _positive_integer(
                shadow.get("episode_generation"), "episode_generation")
            fire_mage = _integer(shadow.get("fire_mage_guid"), "fire_mage_guid")
            hunter = _integer(shadow.get("hunter_guid"), "hunter_guid")
            destination = _destination(
                shadow.get("immutable_destination"), "immutable_destination")
            assignments.append(ActiveAssignment(
                scope.key, episode, fire_mage, hunter, destination))
        for key in ("tasks", "retired_tasks"):
            values = shadow.get(key)
            if not isinstance(values, list):
                raise EvidenceError(f"invalid_{key}")
            for value in values:
                task = value.get("task") if key == "retired_tasks" and isinstance(value, dict) else value
                if not isinstance(task, dict):
                    raise EvidenceError("invalid_task_row")
                identity = _task_identity(task)
                _parse_scope(identity[0])
                tasks.setdefault(identity, []).append(task)
        actors = shadow.get("intent_comparisons")
        if not isinstance(actors, list):
            raise EvidenceError("invalid_intent_comparisons")
        for actor in actors:
            if not isinstance(actor, dict):
                raise EvidenceError("invalid_actor_comparison")
            actor_guid = _integer(actor.get("actor_guid"), "actor_guid")
            for summary in _summary_rows(actor.get("episode_accumulator")):
                identity = _summary_identity(summary)
                if identity[2] != actor_guid:
                    raise EvidenceError("accumulator_actor_mismatch")
                _parse_scope(identity[0])
                summaries.setdefault(identity, []).append(summary)
    return assignments, summaries, tasks


def _latest_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    count_names = (
        "observed", "equivalent", "divergent", "ambiguous",
        "shadow_only", "legacy_only",
    )
    change_names = (
        "shadow_key_change_count", "legacy_key_change_count",
        "shadow_destination_change_count", "legacy_destination_change_count",
    )
    previous = {name: -1 for name in (*count_names, *change_names)}
    stable_keys: tuple[str, str] | None = None
    stable_destinations: tuple[tuple[float, float, float], ...] | None = None
    failure_observed = False
    latest: dict[str, Any] | None = None
    for sample in samples:
        counts = sample.get("counts")
        if not isinstance(counts, dict):
            raise EvidenceError("invalid_comparison_counts")
        current = {
            name: _integer(counts.get(name), f"{name}_count")
            for name in count_names
        }
        current.update({
            name: _integer(sample.get(name), name) for name in change_names
        })
        if any(value < 0 for value in current.values()) \
                or any(current[name] < previous[name] for name in current):
            raise EvidenceError("non_monotonic_comparison_counts")
        previous = current
        keys = (sample.get("stable_shadow_candidate_key"),
                sample.get("stable_legacy_candidate_key"))
        if any(not isinstance(key, str) or not key for key in keys):
            raise EvidenceError("missing_stable_candidate_key")
        destinations = (
            _destination(sample.get("stable_shadow_destination"),
                         "stable_shadow_destination", available=True),
            _destination(sample.get("stable_legacy_destination"),
                         "stable_legacy_destination", available=True),
        )
        if stable_keys is None:
            stable_keys, stable_destinations = keys, destinations
        elif keys != stable_keys or destinations != stable_destinations:
            raise EvidenceError("unstable_retained_candidate_identity")
        has_failure = sample.get("first_failing_comparison") is not None
        if failure_observed and not has_failure:
            raise EvidenceError("retained_first_failure_disappeared")
        failure_observed = failure_observed or has_failure
        latest = sample
    if latest is None:
        raise EvidenceError("missing_episode_summary")
    return latest


def _check_summary(summary: dict[str, Any]) -> tuple[dict[str, int], str, dict[str, Any]]:
    counts = summary.get("counts")
    if not isinstance(counts, dict):
        raise EvidenceError("invalid_comparison_counts")
    names = ("observed", "equivalent", "divergent", "ambiguous", "shadow_only", "legacy_only")
    parsed = {name: _integer(counts.get(name), f"{name}_count") for name in names}
    if parsed["observed"] <= 0:
        raise NotExercised("zero_eligible_comparisons")
    if parsed["equivalent"] != parsed["observed"] or any(
        parsed[name] for name in ("divergent", "ambiguous", "shadow_only", "legacy_only")
    ):
        raise EvidenceError("comparison_not_fully_equivalent")
    for name in (
        "shadow_key_change_count", "legacy_key_change_count",
        "shadow_destination_change_count", "legacy_destination_change_count",
    ):
        if _integer(summary.get(name), name) != 0:
            raise EvidenceError("unstable_candidate_or_destination")
    shadow_key = summary.get("stable_shadow_candidate_key")
    legacy_key = summary.get("stable_legacy_candidate_key")
    if not isinstance(shadow_key, str) or not shadow_key or not isinstance(legacy_key, str) or not legacy_key:
        raise EvidenceError("missing_stable_candidate_key")
    if summary.get("first_failing_comparison") is not None:
        raise EvidenceError("retained_first_failure")
    destinations: dict[str, Any] = {}
    for name in ("stable_shadow_destination", "stable_legacy_destination"):
        coordinates = _destination(summary.get(name), name, available=True)
        destinations[name] = dict(zip(("x", "y", "z"), coordinates))
    if destinations["stable_shadow_destination"] != destinations["stable_legacy_destination"]:
        raise EvidenceError("shadow_legacy_destination_mismatch")
    return parsed, legacy_key, destinations


def _task_progress(samples: list[dict[str, Any]], expected_destination: dict[str, Any]) -> dict[str, Any]:
    running_at: int | None = None
    succeeded_at: int | None = None
    improved_at: int | None = None
    best: float | None = None
    destinations: set[tuple[float, float, float]] = set()
    for index, sample in enumerate(samples):
        state = sample.get("state")
        if state not in ("running", "suspended", "succeeded", "failed", "aborted"):
            raise EvidenceError("invalid_task_state")
        if state in ("failed", "aborted"):
            raise EvidenceError("failed_or_aborted_task_history")
        if succeeded_at is not None and state != "succeeded":
            raise EvidenceError("task_state_regressed_after_success")
        if state == "running" and running_at is None:
            running_at = index
        if state == "succeeded" and succeeded_at is None:
            succeeded_at = index
        initial = _finite(sample.get("initial_distance"), "task_initial_distance")
        distance = _finite(sample.get("best_distance"), "task_best_distance")
        progress_samples = _integer(sample.get("progress_samples"), "task_progress_samples")
        if progress_samples < 0:
            raise EvidenceError("invalid_task_progress_samples")
        if progress_samples > 0 and distance < initial:
            if improved_at is None:
                improved_at = index
            best = distance if best is None else min(best, distance)
        coordinates = _destination(sample.get("destination"), "task_destination")
        destinations.add(coordinates)
    if running_at is None:
        raise EvidenceError("task_running_not_observed")
    if improved_at is None:
        raise EvidenceError("semantic_progress_not_observed")
    if succeeded_at is None:
        raise EvidenceError("task_arrival_not_observed")
    if not running_at <= improved_at <= succeeded_at:
        raise EvidenceError("invalid_task_progress_order")
    expected = tuple(expected_destination[axis] for axis in ("x", "y", "z"))
    if destinations != {expected}:
        raise EvidenceError("task_destination_mismatch")
    return {"running_observed": True, "semantic_progress": True,
            "task_succeeded": True, "best_distance": best}


def _receipt_scope_matches(scope: Scope, value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    expected = {
        "attempt_id": scope.attempt_id,
        "wipe_generation": scope.wipe_generation,
        "route_generation": scope.route_generation,
        "map": scope.map_id,
        "instance": scope.instance_id,
    }
    return all(not isinstance(value.get(name), bool)
               and value.get(name) == expected_value
               for name, expected_value in expected.items())


def _receipt_progress(
    receipt: dict[str, Any], actor: int, scope: Scope,
) -> dict[str, Any] | None:
    receipt_id = _positive_integer(receipt.get("id"), "receipt_id")
    launches = receipt.get("launches")
    if not isinstance(launches, list):
        return None
    spline = any(
        isinstance(item, dict)
        and isinstance(item.get("spline_launch"), dict)
        and item["spline_launch"].get("succeeded") is True
        for item in launches
    )
    progress = receipt.get("progress")
    if not isinstance(progress, dict) or progress.get("available") is not True:
        return None
    if progress.get("receipt_id") != receipt_id \
            or progress.get("bot_guid") != actor \
            or progress.get("map") != scope.map_id \
            or progress.get("instance") != scope.instance_id \
            or not _receipt_scope_matches(scope, {
                **(progress.get("scope") if isinstance(progress.get("scope"), dict) else {}),
                "map": progress.get("map"), "instance": progress.get("instance"),
            }):
        raise EvidenceError("native_receipt_progress_identity_mismatch")
    launched = progress.get("launched_spline")
    launch_proven = spline or (
        isinstance(launched, dict) and launched.get("initialized") is True
    )
    samples = progress.get("samples")
    if not launch_proven or not isinstance(samples, list):
        return None
    armed_at = _integer(progress.get("armed_at_ms"), "receipt_armed_at_ms")
    times: list[int] = []
    endpoint_distances: list[float] = []
    numeric_progress = False
    for sample in samples:
        if not isinstance(sample, dict) or sample.get("receipt_id") != receipt_id:
            raise EvidenceError("native_progress_sample_receipt_mismatch")
        observed_at = _integer(sample.get("observed_at_ms"), "progress_observed_at_ms")
        if observed_at <= armed_at or (times and observed_at <= times[-1]):
            raise EvidenceError("invalid_native_progress_sample_order")
        times.append(observed_at)
        actor_state = sample.get("actor")
        if not isinstance(actor_state, dict) \
                or actor_state.get("available") is not True \
                or actor_state.get("in_world") is not True \
                or actor_state.get("alive") is not True \
                or actor_state.get("map") != scope.map_id \
                or actor_state.get("instance") != scope.instance_id:
            raise EvidenceError("invalid_native_progress_actor_state")
        for axis in ("x", "y", "z"):
            _finite(actor_state.get(axis), f"progress_actor_{axis}")
        endpoint = sample.get("endpoint_progress")
        if not isinstance(endpoint, dict):
            raise EvidenceError("missing_native_endpoint_progress")
        for name in ("horizontal_distance", "vertical_distance", "distance"):
            _finite(endpoint.get(name), f"endpoint_{name}")
        if not isinstance(endpoint.get("improved"), bool) \
                or not isinstance(endpoint.get("reached"), bool):
            raise EvidenceError("invalid_native_endpoint_progress_flags")
        distance = float(endpoint["distance"])
        if endpoint_distances and distance < min(endpoint_distances) \
                and endpoint["improved"]:
            numeric_progress = True
        endpoint_distances.append(distance)
    if len(times) < 2 or times[-1] <= times[0] or not numeric_progress:
        return None
    return {"receipt_id": receipt_id, "launch_proven": True,
            "progress_sample_count": len(samples), "multi_tick_progress": True}


def _receipts(traces: list[dict[str, Any]]) -> list[tuple[int, dict[str, Any]]]:
    result: list[tuple[int, dict[str, Any]]] = []
    for trace in traces:
        bots = trace.get("bots")
        if not isinstance(bots, list):
            raise EvidenceError("invalid_trace_bots")
        for bot in bots:
            if not isinstance(bot, dict) or not isinstance(bot.get("entries"), list):
                raise EvidenceError("invalid_trace_bot")
            actor = _integer(bot.get("bot_guid"), "trace_bot_guid")
            for entry in bot["entries"]:
                planner = entry.get("movement_planner") if isinstance(entry, dict) else None
                receipt = planner.get("launch_receipt") if isinstance(planner, dict) else None
                if isinstance(receipt, dict) and receipt.get("id"):
                    result.append((actor, receipt))
    return result


def _join_receipt(actor: int, key: str, scope: Scope,
                  receipts: list[tuple[int, dict[str, Any]]]) -> dict[str, Any]:
    matches: list[dict[str, Any]] = []
    for trace_actor, receipt in receipts:
        identity = receipt.get("identity")
        if not isinstance(identity, dict):
            continue
        if trace_actor != actor or identity.get("bot_guid") != actor:
            continue
        if identity.get("diagnostic_candidate_key") != key:
            continue
        if isinstance(identity.get("map"), bool) \
                or identity.get("map") != scope.map_id:
            continue
        if not _receipt_scope_matches(scope, identity.get("scope")):
            continue
        progress = _receipt_progress(receipt, actor, scope)
        if progress:
            matches.append(progress)
    if not matches:
        raise EvidenceError("missing_exact_native_receipt_progress_join")
    matches.sort(key=lambda item: int(item.get("receipt_id") or 0))
    return matches[0]


def _require_diagnosis_envelopes(
    rows: list[dict[str, Any]], actors: list[int], scope: Scope,
) -> None:
    seen: set[int] = set()
    for row in rows:
        payload = row["payload"]
        if payload.get("action") != "botauto_diagnose":
            continue
        for bot in payload.get("bots", []):
            actor = _actor_guid(bot)
            if actor not in actors:
                continue
            correlation = bot["identity_binding"]["correlation"]
            if correlation.get("attempt_id") == scope.attempt_id \
                    and correlation.get("wipe_generation") == scope.wipe_generation \
                    and correlation.get("route_generation") == scope.route_generation:
                seen.add(actor)
    if seen != set(actors):
        raise EvidenceError("missing_baiter_diagnosis_envelope")


def _require_trace_scope(
    rows: list[dict[str, Any]], actors: list[int], scope: Scope,
) -> None:
    seen: set[int] = set()
    for row in rows:
        payload = row["payload"]
        if payload.get("action") != "botauto_trace":
            continue
        for bot in payload.get("bots", []):
            actor = _actor_guid(bot)
            if actor not in actors:
                continue
            correlation = bot["identity_binding"]["correlation"]
            if correlation.get("attempt_id") == scope.attempt_id \
                    and correlation.get("wipe_generation") == scope.wipe_generation \
                    and correlation.get("route_generation") == scope.route_generation:
                seen.add(actor)
    if seen != set(actors):
        raise EvidenceError("missing_baiter_trace_envelope")


def _result(verdict: str, reason: str, *, scope_key: str = "",
            episode_generation: int = 0, actors: list[int] | None = None,
            counts: dict[str, Any] | None = None,
            joins: list[dict[str, Any]] | None = None,
            progress: list[dict[str, Any]] | None = None,
            failure: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema": SCHEMA,
        "verdict": verdict,
        "reason": reason,
        "scope_key": scope_key,
        "episode_generation": episode_generation,
        "baiter_actor_guids": actors or [],
        "comparison_counts": counts or {},
        "receipt_joins": joins or [],
        "progress_summary": progress or [],
        "first_failure": failure,
    }


def verify(paths: Iterable[Path]) -> dict[str, Any]:
    try:
        rows = _rows(paths)
        statuses = _actions(rows, "botauto_status")
        diagnoses = _actions(rows, "botauto_diagnose")
        traces = _actions(rows, "botauto_trace")
        if not statuses or not diagnoses or not traces:
            raise EvidenceError("missing_required_evidence_stream")
        assignments, summaries, tasks = _collect_status(statuses)
        if not assignments:
            return _result("not_exercised", "no_transfer_lane_episode")
        complete_assignments = [
            assignment for assignment in assignments
            if assignment.fire_mage_guid > 0 and assignment.hunter_guid > 0
            and assignment.fire_mage_guid != assignment.hunter_guid
        ]
        if not complete_assignments:
            assignment = assignments[0]
            actors = sorted({assignment.fire_mage_guid, assignment.hunter_guid} - {0})
            return _result("not_exercised", "incomplete_baiter_assignment",
                           scope_key=assignment.scope_key,
                           episode_generation=assignment.episode_generation,
                           actors=actors)
        if len(complete_assignments) != len(assignments):
            raise EvidenceError("incomplete_assignment_during_active_episode")
        assignment_identities = set(complete_assignments)
        if len(assignment_identities) != 1:
            raise EvidenceError("mixed_transfer_lane_episodes")
        assignment = complete_assignments[0]
        scope_key, episode = assignment.scope_key, assignment.episode_generation
        assigned = {assignment.fire_mage_guid, assignment.hunter_guid}
        scope = _parse_scope(scope_key)
        if scope.cohort_id != rows[0]["identity_binding"]["cohort_id"]:
            raise EvidenceError("scope_cohort_identity_mismatch")
        actors = sorted(assigned)
        _require_diagnosis_envelopes(rows, actors, scope)
        _require_trace_scope(rows, actors, scope)
        actor_counts: dict[str, Any] = {}
        joins: list[dict[str, Any]] = []
        progress: list[dict[str, Any]] = []
        all_receipts = _receipts(traces)
        for actor in actors:
            identities = [identity for identity in summaries
                          if identity[:3] == (scope_key, episode, actor)]
            if len(identities) != 1:
                return _result("not_exercised", "incomplete_two_baiter_episode",
                               scope_key=scope_key, episode_generation=episode,
                               actors=actors)
            identity = identities[0]
            summary = _latest_summary(summaries[identity])
            parsed_counts, legacy_key, destinations = _check_summary(summary)
            expected_destination = dict(zip(
                ("x", "y", "z"), assignment.destination))
            if destinations["stable_shadow_destination"] != expected_destination:
                raise EvidenceError("episode_immutable_destination_mismatch")
            if identity not in tasks:
                raise EvidenceError("missing_exact_task_evidence")
            task_progress = _task_progress(
                tasks[identity], expected_destination)
            receipt = _join_receipt(actor, legacy_key, scope, all_receipts)
            actor_counts[str(actor)] = parsed_counts
            joins.append({"actor_guid": actor, "candidate_key": legacy_key,
                          **receipt})
            progress.append({"actor_guid": actor, **task_progress,
                             "destinations": destinations})
        return _result("pass", "complete_two_baiter_episode_verified",
                       scope_key=scope_key, episode_generation=episode,
                       actors=actors, counts=actor_counts, joins=joins,
                       progress=progress)
    except NotExercised as exc:
        return _result("not_exercised", str(exc))
    except EvidenceError as exc:
        return _result("fail", str(exc), failure={"code": str(exc)})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    result = verify(args.inputs)
    encoded = json.dumps(result, sort_keys=True, separators=(",", ":")) + "\n"
    if args.output:
        args.output.write_text(encoded, encoding="utf-8")
    else:
        print(encoded, end="")
    return EXIT_CODES[result["verdict"]]


if __name__ == "__main__":
    raise SystemExit(main())

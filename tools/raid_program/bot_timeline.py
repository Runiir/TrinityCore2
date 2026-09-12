#!/usr/bin/env python3
"""Join bound raid trace and combat evidence into an attributable bot timeline."""

from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import tarfile
from typing import Any, Iterable

from tools.bot_ml.combat_log_event_stream import combat_log_identity, combat_log_profile_context
from tools.bot_ml.run_live_bot_validation import combined_combat_log
from tools.raid_program.encounter_damage_targets import load_encounter_damage_targets
from tools.raid_program.bot_timeline_incoming import incoming_damage
from tools.raid_program.bot_timeline_melee import melee_resolutions
from tools.raid_program.tactical_replay_lite import _combined_trace, _load_rows


SCHEMA = "cata_raid_bot_timeline_v1"
SUMMARY_SCHEMA = "cata_raid_bot_timeline_summary_v1"
LEGACY_WARNING = (
    "Trace action_category, role_goal, balance, saturation, mechanic, responsibility, "
    "next-action, and movement fields without immutable trace context are export-time "
    "state and are not historical observations."
)


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sha256(path: Path | None) -> str | None:
    if path is None or not path.exists():
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _report_source(report: dict[str, Any]) -> tuple[dict[str, Any], str]:
    """Hash stable pre-finalization identity fields without a report/self-hash cycle."""
    runtime = report.get("accepted_raid_runtime") or {}
    projection = {
        "schema_version": report.get("schema_version"),
        "capture_id": report.get("capture_id"),
        "scenario_id": report.get("scenario_id"),
        "started_at_utc": report.get("started_at_utc"),
        "source_identity": report.get("identity"),
        "binary_sha256": report.get("binary_sha256"),
        "config_sha256": report.get("config_sha256"),
        "runtime_profile": report.get("runtime_profile"),
        "runtime_identity": {key: runtime.get(key) for key in (
            "server_epoch", "attempt_id", "wipe_generation", "profile_generation",
            "profile_content_hash", "map_id", "instance_id", "group_guid",
            "expected_size", "expected_difficulty", "strategy_id",
        )},
        "accepted_boss_identity": (report.get("development_run") or {}).get("accepted_boss_identity"),
        "raw_normalized_batch": {key: (report.get("raw_normalized_batch") or {}).get(key) for key in ("sha256", "row_count")},
    }
    encoded = json.dumps(projection, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return projection, hashlib.sha256(encoded).hexdigest()


def _runtime(payload: dict[str, Any]) -> dict[str, Any]:
    value = payload.get("raid_runtime")
    return value if isinstance(value, dict) else payload


def _identity(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = _runtime(payload)
    return {
        "cohort_id": payload.get("cohort_id", runtime.get("cohort_id")),
        "server_epoch": payload.get("server_epoch", runtime.get("server_epoch")),
        "attempt_id": payload.get("attempt_id", runtime.get("attempt_id")),
    }


def _identity_matches(value: dict[str, Any], expected: dict[str, Any]) -> bool:
    actual = _identity(value)
    required = [key for key in expected if expected.get(key) is not None]
    populated = [key for key in required if actual.get(key) is not None]
    return len(populated) == len(required) and all(actual[key] == expected[key] for key in required)


def _verified_payloads(rows: Iterable[dict[str, Any]], channel: str,
                       expected: dict[str, Any], binding_sha256: str | None) -> list[dict[str, Any]]:
    """Retain normalized binding provenance for nested legacy trace entries."""
    payloads: list[dict[str, Any]] = []
    for row in rows:
        if row.get("evidence_channel") != channel or (row.get("identity_binding") or {}).get("state") != "bound":
            continue
        payload = row.get("payload")
        if not isinstance(payload, dict):
            continue
        value = dict(payload)
        binding_hash = (row.get("identity_binding") or {}).get("canonical_identity_sha256")
        verified = bool(binding_sha256 and binding_hash == binding_sha256)
        if verified:
            actual = _identity(value)
            if all(actual.get(key) in (None, expected.get(key)) for key in expected):
                for key, expected_value in expected.items():
                    if expected_value is not None and actual.get(key) is None:
                        value[key] = expected_value
        value["_normalized_identity_verified"] = verified
        payloads.append(value)
    return payloads


def _canonical_identity(report: dict[str, Any], payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    stream = report.get("combat_log_event_stream") or {}
    candidate = stream.get("identity") or {}
    if all(candidate.get(k) is not None for k in ("cohort_id", "server_epoch", "attempt_id")):
        return {k: candidate.get(k) for k in ("cohort_id", "server_epoch", "attempt_id")}
    runtime = report.get("accepted_raid_runtime") or {}
    candidate = _identity(runtime)
    if any(candidate.values()):
        return candidate
    for payload in payloads:
        candidate = _identity(payload)
        if any(candidate.values()):
            return candidate
    return {"cohort_id": None, "server_epoch": None, "attempt_id": None}


def _timestamp(row: dict[str, Any]) -> int:
    return _int(row.get("timestamp_ms") or row.get("observed_at_ms") or row.get("recorded_at_ms"))


def _attack_origin(row: dict[str, Any]) -> str:
    if row.get("source_is_pet") is True:
        return "owned_source"
    value = str(row.get("attack_origin") or row.get("damage_origin") or "").lower()
    if value in {"periodic", "dot", "tick"}:
        return "periodic"
    if value in {"direct", "fresh", "impact"}:
        return "direct"
    if isinstance(row.get("is_periodic"), bool):
        return "periodic" if row["is_periodic"] else "direct"
    effect_type = row.get("damage_type", row.get("effect_type"))
    if isinstance(effect_type, int) and not isinstance(effect_type, bool):
        if effect_type == 2:  # DamageEffectType::DOT
            return "periodic"
        if effect_type in {0, 1}:  # DIRECT_DAMAGE / SPELL_DIRECT_DAMAGE
            return "direct"
    return "unknown"


def _hostile_damage(row: dict[str, Any]) -> bool:
    return row.get("kind") == "damage" and _int(row.get("originated_amount")) > 0 and row.get("_perspective") == "damage_done"


def _attach_perspectives(combat: dict[str, Any], events: list[dict[str, Any]]) -> None:
    by_key: dict[tuple[int, ...], set[str]] = defaultdict(set)
    for row in combat.get("abilities") or []:
        if not isinstance(row, dict):
            continue
        key = tuple(_int(row.get(field)) for field in ("route_generation", "actor_guid", "source_entry", "spell_id", "target_entry", "effect_type"))
        by_key[key].add(str(row.get("perspective") or ""))
    actor_guids = {_int(row.get("actor_guid")) for row in events if _int(row.get("actor_guid"))}
    owned_guids = set(actor_guids)
    owned_guids.update(_int(row.get("source_guid")) for row in events if row.get("source_is_pet") is True and _int(row.get("source_guid")))
    for row in events:
        actor = _int(row.get("actor_guid"))
        source_owned = _int(row.get("source_guid")) == actor or row.get("source_is_pet") is True
        target_owned = _int(row.get("target_guid")) in owned_guids
        if row.get("kind") == "heal":
            row["_perspective"] = "healing_done" if source_owned else ("healing_received" if target_owned else "unknown")
            continue
        if source_owned and target_owned:
            row["_perspective"] = "friendly_damage_done"
            continue
        if not source_owned:
            row["_perspective"] = "damage_taken"
            continue
        key = tuple(_int(row.get(field)) for field in ("route_generation", "actor_guid", "source_entry", "spell_id", "target_entry", "effect_type"))
        perspectives = by_key.get(key, set())
        row["_perspective"] = next(iter(perspectives)) if len(perspectives) == 1 else "unknown"


def _event(kind: str, at_ms: int, actor_guid: int, **fields: Any) -> dict[str, Any]:
    return {"kind": kind, "at_ms": at_ms, "actor_guid": actor_guid, **fields}


def _native_death_ms(statuses: list[dict[str, Any]], trace: list[dict[str, Any]], report: dict[str, Any], combat_events: list[dict[str, Any]]) -> tuple[int | None, str]:
    accepted = (report.get("development_run") or {}).get("accepted_boss_identity") or {}
    wanted = _int(accepted.get("target_entry"))
    accepted_target_guids: set[int] = set()
    for status in reversed(statuses):
        for row in ((_runtime(status).get("validation_route") or status.get("validation_route") or {}).get("boss_death_evidence") or []):
            if isinstance(row, dict) and row.get("result") == "confirmed_unit_death" and (not wanted or _int(row.get("target_entry")) == wanted):
                if _int(row.get("target_id")):
                    accepted_target_guids.add(_int(row.get("target_id")))
                at = _timestamp(row)
                if at:
                    return at, "native_boss_death_evidence"
    for row in reversed(trace):
        accepted_generation = _int(accepted.get("route_generation"))
        accepted_node = str(accepted.get("route_node_id") or "")
        observed_target = _int((row.get("event_target") or {}).get("entry") or (row.get("target") or {}).get("entry"))
        observed_guid = _int((row.get("event_target") or {}).get("guid") or (row.get("target") or {}).get("guid") or row.get("target_id"))
        scoped_entries = {_int(event.get("target_entry")) for event in combat_events
                          if observed_guid and _int(event.get("target_guid")) == observed_guid
                          and (not accepted_generation or _int(event.get("route_generation")) == accepted_generation)
                          and (not accepted_node or event.get("route_node_id") == accepted_node)
                          and event.get("_perspective") == "damage_done"}
        target_matches = not wanted or observed_target == wanted or wanted in scoped_entries or (observed_guid and observed_guid in accepted_target_guids)
        scope_matches = (not accepted_generation or _int(row.get("route_generation")) == accepted_generation) and (not accepted_node or row.get("route_node_id") == accepted_node)
        if row.get("action") == "boss_killed" and row.get("result") == "confirmed_unit_death" and target_matches and scope_matches:
            if _timestamp(row):
                return _timestamp(row), "native_trace_boss_death"
    return None, "missing_native_timestamp"


def _intervals(points: list[int], gap_ms: int = 1500) -> list[dict[str, Any]]:
    if not points:
        return []
    runs: list[dict[str, Any]] = []
    start = previous = points[0]
    for point in points[1:]:
        if point - previous > gap_ms:
            runs.append({"start_ms": start, "end_ms": previous, "boundary_provenance": "observed_events"})
            start = point
        previous = point
    runs.append({"start_ms": start, "end_ms": previous, "boundary_provenance": "observed_events"})
    return runs


def _phase_name(value: str) -> str:
    return {"true": "head_exposed", "false": "body_or_not_exposed",
            "unknown": "unknown"}.get(value.lower(), value)


def _phase_intervals(trace: list[dict[str, Any]], diagnosis_events: list[dict[str, Any]],
                     window_start: int | None, window_end: int | None) -> list[dict[str, Any]]:
    samples: dict[int, dict[int, set[str]]] = defaultdict(lambda: defaultdict(set))
    target_return_times: set[tuple[int, int]] = set()
    for row in trace:
        actor = _int(row.get("bot_guid") or (row.get("actor") or {}).get("guid"))
        target_return = row.get("target_return") or {}
        observation = target_return.get("observation") or {}
        phase = str(row.get("encounter_phase") or (row.get("decision_context") or {}).get("encounter_phase") or observation.get("head_fact") or "")
        observed = _int(target_return.get("observed_at_ms")) or _timestamp(row)
        if phase and observed and actor:
            samples[actor][observed].add(_phase_name(phase))
            if target_return.get("current_at_record") is True:
                target_return_times.add((actor, observed))
    for event in diagnosis_events:
        if event.get("kind") != "target_return_observation" or not event.get("head_fact"):
            continue
        samples[_int(event.get("actor_guid"))][_int(event.get("at_ms"))].add(_phase_name(str(event["head_fact"])))
    result: list[dict[str, Any]] = []
    global_phases: dict[int, set[str]] = defaultdict(set)
    for actor_samples in samples.values():
        for at, phases in actor_samples.items():
            global_phases[at].update(phases)
    for actor, actor_samples in sorted(samples.items()):
        actor_rows: list[dict[str, Any]] = []
        for at, phases in sorted(actor_samples.items()):
            for phase in sorted(phases):
                provenance = "observed_target_return" if (actor, at) in target_return_times else "historical_diagnosis_observed_at"
                conflict = len(phases) > 1 or len(global_phases[at]) > 1
                if actor_rows and actor_rows[-1]["phase"] == phase and actor_rows[-1]["conflict"] is False and not conflict:
                    actor_rows[-1]["end_ms"] = at
                else:
                    if actor_rows:
                        actor_rows[-1]["end_ms"] = at
                    actor_rows.append({"actor_guid": actor, "phase": phase, "start_ms": at, "end_ms": at, "boundary_provenance": provenance, "conflict": conflict})
        for row in actor_rows:
            if ((window_start is not None and row["end_ms"] < window_start)
                    or (window_end is not None and row["start_ms"] > window_end)):
                continue
            if window_start is not None and row["start_ms"] < window_start:
                row["start_ms"] = window_start
                row["start_boundary_provenance"] = "window_clip_from_prior_observation"
            else:
                row["start_boundary_provenance"] = row["boundary_provenance"]
            if window_end is not None and row["end_ms"] > window_end:
                row["end_ms"] = window_end
                row["end_boundary_provenance"] = "native_window_end_clip"
            else:
                row["end_boundary_provenance"] = row["boundary_provenance"]
            result.append(row)
    return result


def _diagnosis_events(payloads: list[dict[str, Any]]) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    seen_returns: set[tuple[Any, ...]] = set()
    last_decision_context: dict[int, str] = {}
    last_movement_context: dict[int, str] = {}
    for payload in payloads:
        for bot in payload.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            actor = _int((bot.get("identity") or {}).get("bot_guid"))
            if not actor:
                continue
            diagnosis = bot.get("diagnosis") or {}
            snapshot = bot.get("snapshot") or {}
            target_return = diagnosis.get("magmaw_target_return") or {}
            observed = _int(target_return.get("observed_at_ms"))
            if target_return.get("evaluated") is True and observed:
                key = (actor, _int(target_return.get("attempt_id")), _int(target_return.get("route_generation")), str(target_return.get("route_node_id") or ""), observed)
                if key not in seen_returns:
                    seen_returns.add(key)
                    events.append(_event("target_return_observation", observed, actor,
                        attempt_id=key[1], route_generation=key[2], route_node_id=key[3],
                        head_fact=target_return.get("head_fact"), phase=_phase_name(str(target_return.get("head_fact") or "unknown")), body=target_return.get("body"),
                        head=target_return.get("head"), binding={field: target_return.get(field) for field in (
                            "valid", "owns_node", "proposed_target_guid", "proposed_native_present",
                            "proposed_native_alive", "proposed_native_valid_attack_target",
                            "before_state_target_guid", "before_context_target_guid",
                            "desired_melee_target_guid", "after_state_target_guid",
                            "after_context_target_guid", "bind_result", "snapshot_revision")},
                        stale_relative_to_export=target_return.get("current") is not True,
                        provenance="historical_diagnosis_observed_at"))
            runtime = snapshot.get("runtime") or {}
            last_tick = _int(runtime.get("last_decision_tick_ms"))
            policy = snapshot.get("policy") or {}
            kernel = policy.get("decision_kernel") or diagnosis.get("decision_kernel") or {}
            if last_tick:
                candidates = [{field: row.get(field) for field in ("key", "phase", "status", "reason", "resources")}
                              for row in kernel.get("candidates") or [] if isinstance(row, dict)]
                mask = policy.get("valid_action_mask_json") if isinstance(policy.get("valid_action_mask_json"), dict) else {}
                mask_evaluation = mask.get("evaluation") if isinstance(mask.get("evaluation"), dict) else {}
                compact_mask = {
                    "schema": mask.get("schema"),
                    "evaluation": {field: mask_evaluation.get(field) for field in ("actor_guid", "scope", "selector", "selector_filters", "target_entry", "target_guid")},
                    "actions": [{field: action.get(field) for field in (
                        "action_id", "spell_id", "resolved_spell_id", "action_category",
                        "target_guid", "target_entry", "target_selector", "valid",
                        "reject_reason", "score", "priority_bucket", "mechanic_tags")}
                        for action in mask.get("actions") or [] if isinstance(action, dict)],
                    "role_goal": mask.get("role_goal"),
                    "role_saturation_state": mask.get("role_saturation_state") if isinstance(mask.get("role_saturation_state"), dict) else {},
                }
                context_at = _int(mask_evaluation.get("started_at_ms")) or last_tick
                decision_context = {
                    "candidates": candidates,
                    "committed_candidates": kernel.get("committed_candidates") if isinstance(kernel.get("committed_candidates"), list) else [],
                    "valid_action_mask": compact_mask,
                    "class_spec_profile": policy.get("class_spec_profile") if isinstance(policy.get("class_spec_profile"), dict) else {},
                }
                decision_key = json.dumps(decision_context, sort_keys=True, separators=(",", ":"))
                if last_decision_context.get(actor) != decision_key:
                    last_decision_context[actor] = decision_key
                    events.append(_event("diagnosis_decision_context", context_at, actor,
                        **decision_context, provenance="diagnosis_last_decision_tick",
                        stale_relative_to_export=True))
                movement = snapshot.get("movement") or {}
                planner = snapshot.get("movement_planner") or {}
                progress = snapshot.get("movement_receipt_progress") or {}
                movement_context = {
                    "movement": {field: movement.get(field) for field in (
                            "is_moving", "active_path_target_guid", "native_current_motion_type",
                            "native_active_motion_type", "native_spline_finalized", "stuck_timer_ms")},
                    "planner": {field: planner.get(field) for field in (
                            "available", "bot_guid", "owner", "gate", "result", "reason",
                            "intent_reason", "final_traversal_mode", "flags")},
                    "receipt_progress": {field: progress.get(field) for field in (
                            "available", "active_receipt_id", "payload_complete", "retained_receipt_count",
                            "published_receipt_count", "published_sample_count", "dropped_sample_count",
                            "omitted_receipt_count", "receipts_truncated")},
                }
                movement_key = json.dumps(movement_context, sort_keys=True, separators=(",", ":"))
                if last_movement_context.get(actor) == movement_key:
                    continue
                last_movement_context[actor] = movement_key
                events.append(_event("movement_diagnosis", last_tick, actor,
                    **movement_context,
                    provenance="diagnosis_last_decision_tick", stale_relative_to_export=True))
    return sorted(events, key=lambda row: (row["at_ms"], row["actor_guid"], row["kind"]))


def _trace_events(trace: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[int, list[tuple[int, int]]]]:
    events: list[dict[str, Any]] = []
    switches: dict[int, list[tuple[int, int]]] = defaultdict(list)
    last_target: dict[int, int] = {}
    seen_attempts: set[tuple[Any, ...]] = set()
    seen_finishes: set[tuple[Any, ...]] = set()
    for row in trace:
        at = _timestamp(row)
        actor = _int(row.get("bot_guid") or (row.get("actor") or {}).get("guid") or (row.get("identity") or {}).get("actor_guid"))
        if not at or not actor:
            continue
        immutable = bool(row.get("server_epoch") and (row.get("event_target") is not None or row.get("native_actor") is not None))
        target_return = row.get("target_return")
        observation_quality = {
            "target_return": "missing" if not isinstance(target_return, dict) else ("stale" if target_return.get("stale") is True else ("observed" if target_return.get("current_at_record") is True else "missing")),
            "native_actor": "observed" if isinstance(row.get("native_actor"), dict) else "missing",
            "native_selected_target": "observed" if isinstance(row.get("native_selected_target"), dict) else "missing",
        }
        head_fact = str(((target_return or {}).get("observation") or {}).get("head_fact") or "") if isinstance(target_return, dict) and target_return.get("current_at_record") is True else ""
        events.append(_event("decision", at, actor, sequence=_int(row.get("sequence")), decision_sequence=_int(row.get("decision_sequence")), policy_observed_at_ms=_int(row.get("policy_observed_at_ms")) or None, actor_context=row.get("actor") if immutable else None, action=row.get("action"), action_category=row.get("action_category") if immutable else None, result=row.get("result"), reason_code=row.get("reason_code"), route_node_id=row.get("route_node_id"), route_generation=_int(row.get("route_generation")), phase=row.get("encounter_phase") or (_phase_name(head_fact) if head_fact else None), action_phase=(row.get("combat_attempt") or {}).get("phase"), event_target=row.get("event_target") if immutable else None, native_selected_target=row.get("native_selected_target") if immutable else None, state_bound_target=row.get("state_bound_target") if immutable else None, native_actor=row.get("native_actor") if immutable else None, target_return=target_return if immutable else None, observation_quality=observation_quality, provenance="observed_record_time" if immutable else "observed_core_fields_only", historical_metadata="immutable" if immutable else "legacy_export_time_stale"))
        selected = row.get("native_selected_target")
        if isinstance(selected, dict):
            target = _int(selected.get("guid"))
            if actor in last_target and last_target[actor] != target:
                events.append(_event("target_transition", at, actor, from_target_guid=last_target[actor], target_guid=target, provenance="observed_record_time"))
                if target:
                    switches[actor].append((at, target))
            last_target[actor] = target
        attempt = row.get("combat_attempt") or {}
        action = attempt.get("action") or {}
        recorded = _int(attempt.get("recorded_at_ms"))
        spell = _int(action.get("spell_id"))
        key = (actor, recorded, spell, _int(action.get("target_guid")), str(attempt.get("phase") or ""))
        if recorded and spell and key not in seen_attempts:
            seen_attempts.add(key)
            failure = attempt.get("failure") or {}
            accepted = failure.get("result") == "ok"
            events.append(_event("native_submission" if accepted else "native_attempt_rejected", recorded, actor, route_generation=_int(row.get("route_generation")), spell_id=spell, action_type=action.get("action_type"), debug_name=action.get("debug_name"), target_guid=_int(action.get("target_guid")), target_entry=_int(action.get("target_entry")), action_phase=attempt.get("phase"), result=failure.get("result"), reason=failure.get("reason"), gates=failure.get("gates") if isinstance(failure.get("gates"), dict) else {}, detail=attempt.get("detail") if isinstance(attempt.get("detail"), dict) else {}, provenance="observed_native_combat_attempt", cast_correlation="unavailable"))
        finish = row.get("native_spell_finish")
        if isinstance(finish, dict):
            observed = _int(finish.get("observed_at_ms"))
            key = (actor, observed, _int(finish.get("spell_id")), finish.get("success"))
            if observed and key not in seen_finishes:
                seen_finishes.add(key)
                events.append(_event("native_finish", observed, actor, route_generation=_int(finish.get("route_generation") or row.get("route_generation")), spell_id=_int(finish.get("spell_id")), success=finish.get("success"), provenance="observed_native_callback", cast_correlation="unavailable"))
        actor_state = row.get("native_actor")
        if isinstance(actor_state, dict):
            events.append(_event("movement", at, actor, moving=actor_state.get("moving"), position=actor_state.get("position"), spline=actor_state.get("spline"), planner=row.get("movement_planner") if immutable else None, provenance="observed_record_time"))
        words = " ".join(str(row.get(k) or "") for k in ("action", "result", "reason_code")).lower()
        if any(word in words for word in ("idle", "backoff", "wait")):
            events.append(_event("idle_backoff", at, actor, action=row.get("action"), result=row.get("result"), provenance="observed_decision"))
    return events, switches


def build_timeline_from_rows(
    normalized_rows: Iterable[dict[str, Any]],
    report_metadata: dict[str, Any] | None = None,
    *,
    raw_sha256: str | None = None,
    report_sha256: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build artifacts before report finalization, without reading or duplicating raw data."""
    report = report_metadata or {}
    rows = list(normalized_rows)
    raw_payloads = [row.get("payload") for row in rows if isinstance(row.get("payload"), dict)]
    expected = _canonical_identity(report, raw_payloads)
    binding_sha256 = (report.get("evidence_demux") or {}).get("canonical_identity_sha256")
    if not binding_sha256:
        binding_sha256 = next((str((row.get("identity_binding") or {}).get("canonical_identity_sha256"))
                               for row in rows if (row.get("identity_binding") or {}).get("canonical_identity_sha256")), None)
    verified = {channel: _verified_payloads(rows, channel, expected, binding_sha256) for channel in ("status", "trace", "diagnosis", "combat_log")}
    rejected: list[dict[str, Any]] = []
    channels: dict[str, list[dict[str, Any]]] = {}
    for channel in ("status", "trace", "diagnosis", "combat_log"):
        values = []
        for payload in verified[channel]:
            binding_matches = not binding_sha256 or payload.get("_normalized_identity_verified") is True
            if binding_matches and _identity_matches(payload, expected):
                values.append(payload)
            else:
                rejected.append({"channel": channel, "identity": _identity(payload),
                                 "normalized_binding_matches": binding_matches})
        channels[channel] = values
    trace = []
    for row in _combined_trace(channels["trace"]):
        has_row_identity = isinstance(row.get("identity"), dict) or any(row.get(key) is not None for key in ("cohort_id", "server_epoch", "attempt_id"))
        if not has_row_identity or _identity_matches(row, expected):
            trace.append(row)
    status = channels["status"][-1] if channels["status"] else None
    combat = combined_combat_log(channels["combat_log"], expected_status=status) if channels["combat_log"] else {}
    combat_events = [dict(row) for row in combat.get("recent_events") or [] if isinstance(row, dict)]
    _attach_perspectives(combat, combat_events)
    death_ms, death_basis = _native_death_ms(channels["status"], trace, report, combat_events)
    accepted_scope = (report.get("development_run") or {}).get("accepted_boss_identity") or {}
    accepted_generation = _int(accepted_scope.get("route_generation"))
    scoped_combat_events = [row for row in combat_events if not accepted_generation or _int(row.get("route_generation")) == accepted_generation]
    eligible = [row for row in scoped_combat_events if _hostile_damage(row) and _int(row.get("spell_id")) != 79010]
    first_hostile = min((_timestamp(row) for row in eligible if _timestamp(row)), default=0) or None
    window_events = [row for row in scoped_combat_events if first_hostile and _timestamp(row) >= first_hostile and (death_ms is None or _timestamp(row) <= death_ms)]
    trace_events, switches = _trace_events(trace)
    diagnosis_events = _diagnosis_events(channels["diagnosis"])
    timeline_events = [*trace_events, *diagnosis_events]
    incoming_rows = [row for row in scoped_combat_events
                     if death_ms is None or _timestamp(row) <= death_ms]
    incoming_events, incoming_summary = incoming_damage(incoming_rows)
    timeline_events.extend(incoming_events)
    melee_events, melee_summary = melee_resolutions(incoming_rows)
    timeline_events.extend(melee_events)
    actors: dict[int, dict[str, Any]] = {}
    actor_points: dict[int, list[int]] = defaultdict(list)
    fresh: dict[int, dict[str, list[int]]] = defaultdict(lambda: defaultdict(list))
    masking: dict[int, dict[str, list[tuple[int, int]]]] = defaultdict(lambda: defaultdict(list))
    target_damage: dict[int, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    target_names: dict[str, str] = {}
    accounting = defaultdict(int)
    pre_window_healing_by_actor: dict[int, int] = defaultdict(int)
    typed = False
    runtime = report.get("accepted_raid_runtime") or {}
    receipt = runtime.get("admission_receipt") or {}
    receipt_identity_matches = all(
        expected.get(key) is None or receipt.get(key) == expected.get(key)
        for key in ("server_epoch", "attempt_id")
    )
    admitted_members = receipt.get("members") or [] if receipt_identity_matches else []
    for member in admitted_members:
        if not isinstance(member, dict) or not _int(member.get("guid")):
            continue
        actor = _int(member.get("guid"))
        actors[actor] = {"actor_guid": actor, "name": member.get("name") or "",
                         "role": member.get("role") or "", "class_id": member.get("class_id"),
                         "class_spec": member.get("class_spec"),
                         "role_provenance": "accepted_raid_runtime.admission_receipt.members",
                         "damage": defaultdict(int)}
    for member in runtime.get("roster") or []:
        if not isinstance(member, dict) or not _int(member.get("guid")):
            continue
        actor = _int(member.get("guid"))
        data = actors.setdefault(actor, {"actor_guid": actor, "name": "", "role": "",
                                         "class_id": None, "damage": defaultdict(int)})
        data["name"] = data.get("name") or member.get("name") or member.get("character_name") or ""
    for row in trace:
        actor = _int(row.get("bot_guid") or (row.get("actor") or {}).get("guid"))
        if actor:
            actor_context = row.get("actor") or {}
            actors.setdefault(actor, {"actor_guid": actor, "name": row.get("bot_name") or "", "role": actor_context.get("role") or "", "class_id": None, "damage": defaultdict(int)})
    for row in incoming_rows:
        if row.get("kind") != "melee_resolution" and (row.get("kind") != "damage" or row.get("_perspective") != "damage_taken"):
            continue
        actor = _int(row.get("actor_guid"))
        if actor:
            data = actors.setdefault(actor, {"actor_guid": actor, "name": "", "role": "",
                                             "class_id": None, "damage": defaultdict(int)})
            data["name"] = data.get("name") or row.get("actor_name") or ""
            data["role"] = data.get("role") or row.get("actor_role") or ""
            data["class_id"] = data.get("class_id") or row.get("actor_class_id")
    if first_hostile:
        for row in scoped_combat_events:
            if _timestamp(row) >= first_hostile or row.get("kind") != "heal" or row.get("_perspective") != "healing_done":
                continue
            amount = _int(row.get("originated_amount"))
            if amount > 0:
                accounting["pre_window_effective_healing"] += amount
                pre_window_healing_by_actor[_int(row.get("actor_guid"))] += amount
    for row in window_events:
        actor = _int(row.get("actor_guid"))
        if not actor:
            continue
        at = _timestamp(row)
        origin = _attack_origin(row)
        typed |= origin in {"direct", "periodic"}
        amount = _int(row.get("originated_amount"))
        if row.get("kind") == "heal" and row.get("_perspective") == "healing_done" and amount > 0:
            accounting["effective_healing"] += amount
            data = actors.setdefault(actor, {"actor_guid": actor, "name": row.get("actor_name") or "", "role": row.get("actor_role") or "", "class_id": row.get("actor_class_id"), "damage": defaultdict(int)})
            data["name"] = data.get("name") or row.get("actor_name") or ""
            data["role"] = data.get("role") or row.get("actor_role") or ""
            data["class_id"] = data.get("class_id") or row.get("actor_class_id")
            data.setdefault("role_provenance", "native_combat_event" if data.get("role") else "missing")
            data["effective_healing"] = _int(data.get("effective_healing")) + amount
            actor_points[actor].append(at)
            timeline_events.append(_event("healing_landed", at, actor, spell_id=_int(row.get("spell_id")), spell_name=row.get("spell_name"), target_guid=_int(row.get("target_guid")), amount=amount, provenance="observed_combat_event", cast_correlation="unavailable"))
            continue
        friendly = row.get("_perspective") == "friendly_damage_done"
        mirror = _int(row.get("spell_id")) == 79010
        if friendly:
            accounting["excluded_friendly_damage"] += amount
        if mirror:
            accounting["excluded_spell_79010_damage"] += amount
            accounting["excluded_spell_79010_raw_damage"] += _int(row.get("amount"))
        if row.get("kind") != "damage" or amount <= 0 or row.get("_perspective") != "damage_done" or friendly or mirror:
            continue
        accounting["hostile_originated_damage"] += amount
        if row.get("source_is_pet") is True:
            accounting["owned_source_damage"] += amount
        elif _int(row.get("source_guid")) == actor:
            accounting["owner_damage"] += amount
        else:
            accounting["unknown_source_damage"] += amount
        data = actors.setdefault(actor, {"actor_guid": actor, "name": row.get("actor_name") or "", "role": row.get("actor_role") or "", "class_id": row.get("actor_class_id"), "damage": defaultdict(int)})
        data["name"] = data.get("name") or row.get("actor_name") or ""
        data["role"] = data.get("role") or row.get("actor_role") or ""
        data["class_id"] = data.get("class_id") or row.get("actor_class_id")
        data.setdefault("role_provenance", "native_combat_event" if data.get("role") else "missing")
        data["damage"]["hostile_originated"] += amount
        data["damage"][origin] += amount
        actor_points[actor].append(at)
        target_key = f"{_int(row.get('target_entry'))}:{_int(row.get('target_guid'))}"
        target_damage[actor][target_key] += amount
        target_names[target_key] = str(row.get("target_name") or "")
        timeline_events.append(_event("landed", at, actor, spell_id=_int(row.get("spell_id")), spell_name=row.get("spell_name"), target_guid=_int(row.get("target_guid")), target_entry=_int(row.get("target_entry")), amount=amount, attack_origin=origin, source_guid=_int(row.get("source_guid")), source_is_pet=row.get("source_is_pet") is True, provenance="observed_combat_event", cast_correlation="unavailable"))
        if origin == "direct":
            fresh[actor]["landed"].append(at)
        elif origin in {"periodic", "owned_source"}:
            masking[actor][origin].append((at, amount))
    for event in trace_events:
        if not first_hostile or event["at_ms"] < first_hostile or (death_ms and event["at_ms"] > death_ms):
            continue
        if accepted_generation and _int(event.get("route_generation")) != accepted_generation:
            continue
        if event["kind"] == "native_submission":
            fresh[event["actor_guid"]]["submission"].append(event["at_ms"])
        elif event["kind"] == "native_finish" and event.get("success") is True:
            fresh[event["actor_guid"]]["finish"].append(event["at_ms"])
    elapsed = ((death_ms - first_hostile) / 1000.0) if death_ms and first_hostile and death_ms > first_hostile else None
    boss_entry = _int(((report.get("development_run") or {}).get("accepted_boss_identity") or {}).get("target_entry"))
    target_taxonomy = load_encounter_damage_targets(boss_entry)
    boss_entries = set(target_taxonomy["boss_entries"])
    add_entries = set(target_taxonomy["add_entries"])
    clear_accepted = bool(report.get("classification") == "success" and (report.get("development_run") or {}).get("native_boss_death_accepted") is True and (report.get("terminal_failure") or {}).get("detected") is not True)
    closed_all_alive = bool(clear_accepted and _int(runtime.get("alive_size")) == len(actors) and _int(runtime.get("active_size")) == len(actors))
    trace_by_actor: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in trace:
        trace_by_actor[_int(row.get("bot_guid") or (row.get("actor") or {}).get("guid"))].append(row)
    for actor, data in actors.items():
        points = sorted(set(actor_points[actor]))
        all_fresh = sorted(set(fresh[actor]["landed"]))
        submissions = sorted(set(fresh[actor]["submission"]))
        direct_boundaries = list(all_fresh)
        if first_hostile and death_ms and data.get("role") != "healer" and (all_fresh or masking[actor]["periodic"] or masking[actor]["owned_source"]):
            direct_boundaries = [first_hostile, *all_fresh, death_ms]
        gaps = [(a, b) for a, b in zip(direct_boundaries, direct_boundaries[1:]) if b - a >= 5000]
        submission_gaps = [(a, b) for a, b in zip(submissions, submissions[1:])]
        longest = max(gaps, key=lambda pair: pair[1] - pair[0], default=None)
        longest_submission = max(submission_gaps, key=lambda pair: pair[1] - pair[0], default=None)
        periodic_mask = pet_mask = 0
        if longest:
            periodic_mask = sum(amount for at, amount in masking[actor]["periodic"] if longest[0] < at < longest[1])
            pet_mask = sum(amount for at, amount in masking[actor]["owned_source"] if longest[0] < at < longest[1])
        allocations = [
            {"target_entry": _int(key.split(":", 1)[0]), "target_guid": _int(key.split(":", 1)[1]),
             "target_name": target_names.get(key, ""),
             "target_class": "boss" if _int(key.split(":", 1)[0]) in boss_entries else ("add" if _int(key.split(":", 1)[0]) in add_entries else target_taxonomy["unlisted_target_class"]),
             "target_class_provenance": target_taxonomy["basis"] if _int(key.split(":", 1)[0]) in boss_entries | add_entries else "unclassified",
             "hostile_originated_damage": value}
            for key, value in sorted(target_damage[actor].items())
        ]
        data["damage"] = dict(data["damage"])
        hostile_total = data["damage"].get("hostile_originated", 0)
        data["damage"]["hostile_originated"] = hostile_total
        data["damage"]["dps"] = hostile_total / elapsed if elapsed else None
        data["target_allocations"] = allocations
        boss_damage = sum(row["hostile_originated_damage"] for row in allocations if row["target_class"] == "boss") if boss_entry else None
        add_damage = sum(row["hostile_originated_damage"] for row in allocations if row["target_class"] == "add") if add_entries else None
        unknown_damage = sum(row["hostile_originated_damage"] for row in allocations if row["target_class"] == target_taxonomy["unlisted_target_class"])
        data["target_damage"] = {"boss": boss_damage, "add": add_damage, "other_hostile": unknown_damage}
        no_gap_value = 0 if all_fresh and elapsed and typed else None
        data["activity"] = {"intervals": _intervals(points), "active_seconds": len(set(point // 1000 for point in points)), "active_seconds_basis": "occupied_absolute_second_buckets_with_hostile_damage_or_effective_healing", "fresh_attack_active_seconds": len(set(point // 1000 for point in fresh[actor]["landed"])), "fresh_attack_active_seconds_basis": "occupied_absolute_second_buckets_with_owner_direct_hostile_damage", "first_native_submission_at_ms": min(fresh[actor]["submission"], default=None), "last_native_submission_at_ms": max(fresh[actor]["submission"], default=None), "native_submission_offensive_correlation": "unavailable", "first_native_finish_at_ms": min(fresh[actor]["finish"], default=None), "last_native_finish_at_ms": max(fresh[actor]["finish"], default=None), "native_finish_offensive_correlation": "unavailable", "first_fresh_landed_at_ms": min(fresh[actor]["landed"], default=None), "last_fresh_landed_at_ms": max(fresh[actor]["landed"], default=None), "longest_fresh_attack_outage_ms": longest[1] - longest[0] if longest else no_gap_value, "fresh_attack_outage_basis": "observed_direct_landed_boundaries", "longest_native_submission_gap_ms": longest_submission[1] - longest_submission[0] if longest_submission else (0 if submissions and elapsed else None), "native_submission_gap_basis": "observed_accepted_combat_attempt_boundaries_general_activity", "outage_boundaries": {"start_ms": longest[0], "end_ms": longest[1], "provenance": "observed_direct_landed_events"} if longest else None, "outage_masked_periodic_damage": periodic_mask, "outage_masked_owned_source_damage": pet_mask, "metric_scope": "landed_damage_and_healing_activity_with_separate_direct_attack_outages"}
        data["target_switch_latency_ms"] = []
        for switched_at, target in switches.get(actor, []):
            if not first_hostile or switched_at < first_hostile or (death_ms and switched_at > death_ms):
                continue
            landed = min((event["at_ms"] for event in timeline_events if event["kind"] == "landed" and event["actor_guid"] == actor and event.get("target_guid") == target and event.get("attack_origin") == "direct" and event.get("source_is_pet") is not True and event["at_ms"] >= switched_at), default=None)
            if landed is not None:
                data["target_switch_latency_ms"].append({"start_ms": switched_at, "end_ms": landed, "latency_ms": landed - switched_at, "boundary_provenance": "observed_target_transition_to_observed_landed"})
        death_at = min((_timestamp(row) for row in trace_by_actor[actor] if row.get("action") in {"death", "bot_died", "native_death"} and first_hostile and _timestamp(row) >= first_hostile), default=None)
        data["survival"] = {"first_activity_at_ms": min(points, default=None), "last_activity_at_ms": max(points, default=None), "death_observed": False if closed_all_alive else (True if death_at else None), "death_observed_at_ms": death_at, "alive_at_end": True if closed_all_alive else (False if death_at else None)}
        immutable_rows = [row for row in trace_by_actor[actor] if row.get("server_epoch") and isinstance(row.get("native_selected_target"), dict)]
        data["target_switch_observation_complete"] = bool(trace_by_actor[actor]) and len(immutable_rows) == len(trace_by_actor[actor])
        data["effective_healing"] = _int(data.get("effective_healing"))
        data["effective_hps"] = data["effective_healing"] / elapsed if elapsed else None
        data["pre_window_effective_healing"] = pre_window_healing_by_actor[actor]
        data["effective_healing_through_death"] = data["effective_healing"] + data["pre_window_effective_healing"]
        data["native_elapsed_hps_through_death"] = data["effective_healing_through_death"] / elapsed if elapsed else None
        data["movement_event_count"] = sum(event["kind"] == "movement" and event["actor_guid"] == actor for event in trace_events)
        data["idle_backoff_event_count"] = sum(event["kind"] == "idle_backoff" and event["actor_guid"] == actor for event in trace_events)
    stream_receipt = combat.get("event_stream_receipt") or report.get("combat_log_event_stream") or {}
    terminal = report.get("terminal_failure") or {}
    trace_times = [_timestamp(row) for row in trace if _timestamp(row)]
    absent_pre_failure = bool(terminal.get("detected") is True and not trace_times)
    profile = combat_log_profile_context(combat) if combat else (stream_receipt.get("profile_context") or {})
    report_source, report_source_sha256 = _report_source(report)
    identity = {**expected, "combat_log_epoch": (combat_log_identity(combat).get("combat_log_epoch") if combat else (stream_receipt.get("identity") or {}).get("combat_log_epoch")), **profile, "scenario_id": report.get("scenario_id"), "capture_id": report.get("capture_id"), "source": {"raw_sha256": raw_sha256, "report_sha256": report_sha256, "report_source": report_source, "report_source_sha256": report_source_sha256}}
    immutable_rows = [row for row in trace if row.get("server_epoch") and isinstance(row.get("actor"), dict)]
    record_target_rows = [row for row in immutable_rows if isinstance(row.get("native_selected_target"), dict) and isinstance(row.get("state_bound_target"), dict)]
    record_movement_rows = [row for row in immutable_rows if isinstance(row.get("native_actor"), dict)]
    missing_checks = (("raw", bool(rows)), ("trace", bool(trace)), ("combat_events", bool(combat_events)), ("native_boss_death_timestamp", death_ms is not None), ("immutable_decision_context", bool(immutable_rows)), ("record_time_target_context", bool(record_target_rows)), ("record_time_movement_context", bool(record_movement_rows)))
    diagnosis_target_count = sum(event.get("kind") == "target_return_observation" for event in diagnosis_events)
    completeness = {"raw_available": bool(rows), "report_available": bool(report), "trace_entry_count": len(trace), "diagnosis_event_count": len(diagnosis_events), "historical_target_return_observation_count": diagnosis_target_count, "combat_event_count": len(combat_events), "trace_gaps": (report.get("evidence_demux") or {}).get("trace_discontinuities", []), "combat_gaps": stream_receipt.get("gap_ranges", []), "identity_rejections": rejected, "legacy_historical_metadata_warning": LEGACY_WARNING if len(immutable_rows) != len(trace) else None, "typed_attack_origin_available": typed, "absent_pre_failure_trace": absent_pre_failure, "missing_observations": [name for name, present in missing_checks if not present], "unavailable_correlations": ["submission_to_finish_or_landed_cast_instance"]}
    window = {"first_hostile_at_ms": first_hostile, "native_boss_death_at_ms": death_ms, "elapsed_seconds": elapsed, "complete": bool(first_hostile and death_ms and death_ms > first_hostile), "basis": death_basis}
    accounting_out = {key: accounting[key] for key in ("hostile_originated_damage", "effective_healing", "pre_window_effective_healing", "excluded_friendly_damage", "excluded_spell_79010_damage", "excluded_spell_79010_raw_damage", "owner_damage", "owned_source_damage", "unknown_source_damage")}
    accounting_out["exact_party_dps"] = accounting["hostile_originated_damage"] / elapsed if elapsed else None
    accounting_out["exact_party_hps"] = accounting["effective_healing"] / elapsed if elapsed else None
    accounting_out["effective_healing_through_death"] = accounting["effective_healing"] + accounting["pre_window_effective_healing"]
    accounting_out["native_elapsed_hps_through_death"] = accounting_out["effective_healing_through_death"] / elapsed if elapsed else None
    phase_intervals = _phase_intervals(trace, diagnosis_events, first_hostile, death_ms)
    phases_by_actor: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for interval in phase_intervals:
        phases_by_actor[_int(interval.get("actor_guid"))].append(interval)
    for event in timeline_events:
        if event.get("phase"):
            event.setdefault("phase_provenance", event.get("provenance"))
            continue
        matches = [row for row in phases_by_actor[_int(event.get("actor_guid"))]
                   if row["start_ms"] <= event["at_ms"] <= row["end_ms"]]
        candidates = sorted({row["phase"] for row in matches})
        if len(candidates) == 1 and not any(row.get("conflict") for row in matches):
            event["phase"] = candidates[0]
            event["phase_provenance"] = "joined_actor_phase_interval"
        elif candidates:
            event["phase"] = "conflict"
            event["phase_candidates"] = candidates
            event["phase_provenance"] = "conflicting_actor_phase_intervals"
    summary = {"schema": SUMMARY_SCHEMA, "clear_accepted": clear_accepted, "clear_acceptance_source": "report.classification+development_run.native_boss_death_accepted+terminal_failure", "identity": identity, "window": window, "target_taxonomy": target_taxonomy, "accounting": accounting_out, "actors": {str(k): v for k, v in sorted(actors.items())}, "phase_intervals": phase_intervals, "completeness": completeness}
    model = {"schema": SCHEMA, "identity": identity, "window": window, "target_taxonomy": target_taxonomy, "phase_intervals": summary["phase_intervals"], "actors": summary["actors"], "events": sorted(timeline_events, key=lambda event: (event["at_ms"], event["actor_guid"], event["kind"])), "completeness": completeness, "summary": summary}
    summary["incoming_damage"] = incoming_summary
    summary["melee_resolutions"] = melee_summary
    return model, summary


def build_timeline(*, raw_path: Path | None = None, report_path: Path | None = None,
                   raw_archive: Path | None = None, raw_member: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    if raw_path is not None and raw_archive is not None:
        raise ValueError("Choose raw_path or raw_archive")
    if bool(raw_archive) != bool(raw_member):
        raise ValueError("raw_archive and raw_member must be supplied together")
    if raw_path is None and report_path is None and raw_archive is None:
        raise ValueError("raw_path or report_path is required")
    report = json.loads(report_path.read_text()) if report_path else {}
    rows = _load_rows(raw_path) if raw_path else []
    raw_hash = _sha256(raw_path)
    if raw_archive:
        digest = hashlib.sha256()
        with tarfile.open(raw_archive) as archive:
            member = archive.getmember(raw_member)
            if not member.isfile():
                raise ValueError("Raw archive member must be a regular normalized JSONL file")
            with archive.extractfile(member) as handle:
                for line in handle:
                    digest.update(line)
                    if line.strip():
                        rows.append(json.loads(line))
        raw_hash = digest.hexdigest()
    return build_timeline_from_rows(rows, report, raw_sha256=raw_hash, report_sha256=_sha256(report_path))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    raw_group = parser.add_mutually_exclusive_group()
    raw_group.add_argument("--raw", type=Path)
    raw_group.add_argument("--raw-archive", type=Path, help="Read normalized JSONL directly from a retained tar archive")
    parser.add_argument("--raw-member", help="Exact regular-file member in --raw-archive")
    parser.add_argument("--report", type=Path)
    parser.add_argument("--output", type=Path, help="Optional full JSON model; HTML already embeds the complete model")
    parser.add_argument("--summary", type=Path)
    parser.add_argument("--html", type=Path)
    args = parser.parse_args()
    if not any((args.output, args.summary, args.html)):
        parser.error("Choose at least one of --output, --summary or --html")
    model, summary = build_timeline(raw_path=args.raw, report_path=args.report,
                                    raw_archive=args.raw_archive, raw_member=args.raw_member)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(model, sort_keys=True, separators=(",", ":")) + "\n")
    if args.summary:
        args.summary.parent.mkdir(parents=True, exist_ok=True)
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n")
    if args.html:
        from tools.raid_program.bot_timeline_html import render_timeline_html
        args.html.parent.mkdir(parents=True, exist_ok=True)
        args.html.write_text(render_timeline_html(model), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Reduce immutable raid evidence to one bounded causal replay window."""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable

from tools.raid_program.tactical_replay_metrics import (
    causal_assessment,
    dps_hps,
    mechanic_signals,
    movement_diagnostics,
    output_idle_proxy,
    target_distribution,
)


SCHEMA = "cata_raid_tactical_replay_lite_v1"
SUMMARY_SCHEMA = "cata_raid_tactical_replay_lite_summary_v1"


def _integer(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            value = json.loads(line)
            if not isinstance(value, dict):
                raise ValueError(f"row {line_number} is not an object")
            rows.append(value)
    return rows


def _bound_payloads(
    rows: Iterable[dict[str, Any]], channel: str
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for row in rows:
        if row.get("evidence_channel") != channel:
            continue
        binding = row.get("identity_binding") or {}
        if binding and binding.get("state") != "bound":
            continue
        payload = row.get("payload")
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def _combined_trace(payloads: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for payload in payloads:
        groups = [payload]
        groups.extend(row for row in payload.get("bots") or [] if isinstance(row, dict))
        for group in groups:
            bot_guid = group.get("bot_guid")
            bot_name = group.get("bot_name")
            for slot, source in enumerate(group.get("entries") or []):
                if not isinstance(source, dict):
                    continue
                row = dict(source)
                row.setdefault("bot_guid", bot_guid)
                row.setdefault("bot_name", bot_name)
                key = (
                    row.get("bot_guid"),
                    row.get("sequence"),
                    row.get("timestamp_ms"),
                    row.get("action"),
                    row.get("situation"),
                    row.get("result"),
                    row.get("target_id"),
                    slot if row.get("sequence") is None else None,
                )
                if key not in seen:
                    seen.add(key)
                    entries.append(row)
    return sorted(
        entries,
        key=lambda row: (
            _integer(row.get("timestamp_ms")),
            _integer(row.get("bot_guid")),
            _integer(row.get("sequence")),
        ),
    )


def _combined_combat_log(payloads: Iterable[dict[str, Any]]) -> dict[str, Any]:
    payloads = list(payloads)
    direct = next(
        (
            row
            for row in reversed(payloads)
            if row.get("action") == "botauto_combatlog"
            or row.get("combat_log_schema_version")
        ),
        None,
    )
    if direct:
        return direct

    chunks: list[dict[str, Any]] = []
    attempts: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
    for row in payloads:
        if row.get("action") == "botauto_combatlog_chunk":
            chunks.append(row)
        elif row.get("action") == "botauto_combatlog_complete":
            attempts.append((chunks, row))
            chunks = []
    for attempt, completion in reversed(attempts):
        expected = _integer(completion.get("chunk_count"))
        by_sequence = {
            _integer(row.get("sequence")): row
            for row in attempt
            if row.get("encoding") == "base64"
        }
        if expected <= 0 or set(by_sequence) != set(range(expected)):
            continue
        try:
            raw = b"".join(
                base64.b64decode(by_sequence[index]["data"], validate=True)
                for index in range(expected)
            )
            value = json.loads(raw)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if len(raw) == _integer(completion.get("total_bytes")) and isinstance(value, dict):
            return value
    return {}


def _terminal_anchor_ms(report: dict[str, Any], trace: list[dict[str, Any]]) -> int:
    terminal = report.get("terminal_failure") or {}
    runtime = terminal.get("raid_runtime") or {}
    admitted = _integer((runtime.get("admission_receipt") or {}).get("committed_at_ms"))
    elapsed = _number(terminal.get("elapsed_seconds"))
    if admitted > 0 and elapsed > 0:
        return admitted + round(elapsed * 1000)
    return max((_integer(row.get("timestamp_ms")) for row in trace), default=0)


def _point(value: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(value, dict) or value.get("available") is False:
        return None
    xyz = [value.get(axis) for axis in ("x", "y", "z")]
    if any(item is None for item in xyz):
        return None
    return {"x": _number(xyz[0]), "y": _number(xyz[1]), "z": _number(xyz[2])}


def _compact_combat_attempt(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict) or not value:
        return None
    action = value.get("action") or {}
    failure = value.get("failure") or {}
    return {
        "recorded_at_ms": _integer(value.get("recorded_at_ms")),
        "phase": str(value.get("phase") or ""),
        "action_type": str(action.get("action_type") or ""),
        "debug_name": str(action.get("debug_name") or ""),
        "spell_id": _integer(action.get("spell_id")),
        "target_guid": _integer(action.get("target_guid")),
        "target_entry": _integer(action.get("target_entry")),
        "result": str(failure.get("result") or ""),
        "reason": str(failure.get("reason") or ""),
        "gates": failure.get("gates") if isinstance(failure.get("gates"), dict) else {},
    }


def _compact_decision(row: dict[str, Any]) -> dict[str, Any]:
    target = row.get("target") or {}
    destination = row.get("destination") or {}
    return {
        "timestamp_ms": _integer(row.get("timestamp_ms")),
        "bot_guid": _integer(row.get("bot_guid")),
        "bot_name": str(row.get("bot_name") or ""),
        "sequence": _integer(row.get("sequence")),
        "action": str(row.get("action") or ""),
        "category": str(row.get("action_category") or ""),
        "situation": str(row.get("situation") or ""),
        "result": str(row.get("result") or ""),
        "reason_code": str(row.get("reason_code") or ""),
        "target": {
            "guid": _integer(row.get("target_id") or target.get("guid")),
            "entry": _integer(target.get("entry")),
            "hp_pct": _number(target.get("hp_pct")),
        },
        "destination": {
            "map": _integer(destination.get("map")),
            "x": _number(destination.get("x")),
            "y": _number(destination.get("y")),
            "z": _number(destination.get("z")),
        },
        "mechanic_family": str(row.get("mechanic_family") or ""),
        "consecutive_same_decision_count": _integer(
            row.get("consecutive_same_decision_count")
        ),
        "fingerprint_hash": _integer(row.get("fingerprint_hash")),
        "combat_attempt": _compact_combat_attempt(row.get("combat_attempt")),
    }


def _receipt_richness(receipt: dict[str, Any]) -> tuple[int, int, int]:
    progress = receipt.get("progress") or {}
    return (
        len(progress.get("samples") or []),
        len(receipt.get("launches") or []),
        1 if progress.get("terminal") else 0,
    )


def _collect_receipts(
    trace: list[dict[str, Any]], diagnosis_payloads: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    found: dict[
        tuple[int, int], tuple[dict[str, Any], dict[str, Any], int, str, str]
    ] = {}

    def consider(
        bot_guid: int,
        timestamp_ms: int,
        timestamp_basis: str,
        action: str,
        movement_planner: Any,
    ) -> None:
        if not isinstance(movement_planner, dict):
            return
        receipt = movement_planner.get("launch_receipt") or {}
        if not isinstance(receipt, dict):
            return
        receipt_id = _integer(receipt.get("id"))
        if not receipt_id or not (start_ms <= timestamp_ms <= end_ms):
            return
        key = (bot_guid, receipt_id)
        current = found.get(key)
        if current is None or _receipt_richness(receipt) > _receipt_richness(current[0]):
            found[key] = (
                receipt,
                movement_planner,
                timestamp_ms,
                timestamp_basis,
                action,
            )

    for row in trace:
        timestamp_ms = _integer(row.get("timestamp_ms"))
        consider(
            _integer(row.get("bot_guid")),
            timestamp_ms,
            "trace_entry",
            str(row.get("action") or ""),
            row.get("movement_planner"),
        )

    for payload in diagnosis_payloads:
        for bot in payload.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            snapshot = bot.get("snapshot") or {}
            timestamp_ms = _integer((snapshot.get("combat_attempt") or {}).get("recorded_at_ms"))
            consider(
                _integer((bot.get("identity") or {}).get("bot_guid")),
                timestamp_ms,
                "diagnosis_last_native_combat_attempt",
                str((snapshot.get("decision") or {}).get("action") or ""),
                snapshot.get("movement_planner"),
            )

    compact: list[dict[str, Any]] = []
    for (bot_guid, receipt_id), (
        receipt,
        movement_planner,
        observed_at_ms,
        timestamp_basis,
        action,
    ) in found.items():
        identity = receipt.get("identity") or {}
        planner = receipt.get("planner_path") or {}
        progress = receipt.get("progress") or {}
        launches = receipt.get("launches") or []
        launch = launches[-1] if launches else {}
        spline = launch.get("spline_launch") or {}
        native_samples = []
        for sample in progress.get("samples") or []:
            actor = sample.get("actor") or {}
            floor = sample.get("floor") or {}
            motion = sample.get("native_motion") or {}
            native_samples.append(
                {
                    "timestamp_ms": _integer(sample.get("observed_at_ms")),
                    "position": _point(actor),
                    "alive": actor.get("alive"),
                    "floor_z": floor.get("z"),
                    "floor_valid": floor.get("valid"),
                    "platform_compatible": floor.get("selected_platform_compatible"),
                    "spline_id": _integer(motion.get("spline_id")),
                    "spline_matches": motion.get("matches_launched_spline"),
                    "moving": motion.get("moving"),
                    "outcome": str(sample.get("outcome") or ""),
                    "terminal": bool(sample.get("terminal")),
                }
            )
        first_sample_ms = min(
            (_integer(row.get("timestamp_ms")) for row in native_samples if row.get("timestamp_ms")),
            default=0,
        )
        armed_at_ms = _integer(progress.get("armed_at_ms"))
        compact.append(
            {
                "receipt_id": receipt_id,
                "bot_guid": bot_guid,
                "observed_at_ms": observed_at_ms,
                "observed_at_basis": timestamp_basis,
                "decision_action": action,
                "intent_reason": str(identity.get("intent_reason") or ""),
                "owner": str(identity.get("owner") or ""),
                "scope": identity.get("scope") or {},
                "actor_before_planning": _point(receipt.get("actor_before_planning")),
                "request": _point((receipt.get("executor") or {}).get("requested")),
                "selected_endpoint": _point(planner.get("selected_endpoint")),
                "planner": {
                    "calculated": bool(planner.get("calculated")),
                    "complete": bool(planner.get("complete")),
                    "path_type": _integer(planner.get("type")),
                    "control_count": _integer((planner.get("controls") or {}).get("count")),
                    "control_fingerprint": str(
                        (planner.get("controls") or {}).get("fingerprint") or ""
                    ),
                    "floor_observation_conflict": bool(
                        planner.get("floor_observation_conflict")
                    ),
                    "floor_observation": planner.get("floor_observation") or {},
                },
                "admission": {
                    "gate": str(movement_planner.get("gate") or ""),
                    "result": str(movement_planner.get("result") or ""),
                    "reason": str(movement_planner.get("reason") or ""),
                    "planner": movement_planner.get("planner") or {},
                },
                "executor": {
                    "generate_path": bool((receipt.get("executor") or {}).get("generate_path")),
                    "submission_position": _point(
                        (receipt.get("executor") or {}).get("actor_before_submission")
                    ),
                    "launch_attempts": len(launches),
                    "spline_launch_attempted": bool(spline.get("attempted")),
                    "spline_launch_succeeded": bool(spline.get("succeeded")),
                    "spline_id": _integer(spline.get("spline_id")),
                    "spline_control_count": _integer(
                        (spline.get("controls") or {}).get("count")
                    ),
                    "spline_control_fingerprint": str(
                        (spline.get("controls") or {}).get("fingerprint") or ""
                    ),
                },
                "progress": {
                    "available": bool(progress.get("available")),
                    "armed_at_ms": armed_at_ms,
                    "first_sample_at_ms": first_sample_ms,
                    "submission_to_first_progress_latency_ms": (
                        first_sample_ms - armed_at_ms
                        if first_sample_ms and armed_at_ms
                        else None
                    ),
                    "last_observed_at_ms": _integer(progress.get("last_observed_at_ms")),
                    "sample_count": len(native_samples),
                    "dropped_sample_count": _integer(progress.get("dropped_sample_count")),
                    "terminal": bool(progress.get("terminal")),
                    "terminal_outcome": str(progress.get("terminal_outcome") or ""),
                    "samples": native_samples,
                },
            }
        )
    return sorted(compact, key=lambda row: (row["observed_at_ms"], row["bot_guid"], row["receipt_id"]))


def _evidence_map(diagnosis: dict[str, Any]) -> dict[str, Any]:
    return {
        str(row.get("name")): row.get("value")
        for row in diagnosis.get("evidence") or []
        if isinstance(row, dict) and row.get("name")
    }


def _diagnosis_frames(
    payloads: list[dict[str, Any]], start_ms: int, end_ms: int
) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    seen: set[tuple[int, int, str, int]] = set()
    for payload in payloads:
        for bot in payload.get("bots") or []:
            if not isinstance(bot, dict):
                continue
            identity = bot.get("identity") or {}
            diagnosis = bot.get("diagnosis") or {}
            snapshot = bot.get("snapshot") or {}
            attempt = snapshot.get("combat_attempt") or {}
            timestamp_ms = _integer(attempt.get("recorded_at_ms"))
            bot_guid = _integer(identity.get("bot_guid"))
            decision = snapshot.get("decision") or {}
            key = (
                timestamp_ms,
                bot_guid,
                str(decision.get("action") or ""),
                _integer(decision.get("consecutive_same_decision_count")),
            )
            if not (start_ms <= timestamp_ms <= end_ms) or key in seen:
                continue
            seen.add(key)
            evidence = _evidence_map(diagnosis)
            kernel = diagnosis.get("decision_kernel") or {}
            movement = snapshot.get("movement") or {}
            frames.append(
                {
                    "timestamp_ms": timestamp_ms,
                    "timestamp_basis": "last_native_combat_attempt",
                    "bot_guid": bot_guid,
                    "bot_name": str(identity.get("bot_name") or ""),
                    "alive": evidence.get("alive"),
                    "health_pct": None,
                    "current_action": str(diagnosis.get("current_action") or ""),
                    "diagnosis_code": str(diagnosis.get("diagnosis_code") or ""),
                    "blocker": str(diagnosis.get("blocker") or ""),
                    "decision": decision,
                    "movement": {
                        "is_moving": movement.get("is_moving"),
                        "distance_moved_since_last_decision": movement.get(
                            "distance_moved_since_last_decision"
                        ),
                        "time_since_last_progress_ms": movement.get(
                            "time_since_last_progress_ms"
                        ),
                        "time_since_last_path_change_ms": movement.get(
                            "time_since_last_path_change_ms"
                        ),
                        "native_current_motion_type": movement.get(
                            "native_current_motion_type"
                        ),
                        "native_active_motion_type": movement.get(
                            "native_active_motion_type"
                        ),
                    },
                    "combat_attempt": _compact_combat_attempt(attempt),
                    "candidates": [
                        {
                            key: candidate.get(key)
                            for key in (
                                "key",
                                "source",
                                "priority",
                                "score",
                                "resources",
                                "phase",
                                "status",
                                "reason",
                            )
                        }
                        for candidate in kernel.get("candidates") or []
                        if isinstance(candidate, dict)
                    ],
                    "committed_candidates": kernel.get("committed_candidates") or [],
                }
            )
    return sorted(frames, key=lambda row: (row["timestamp_ms"], row["bot_guid"]))


def _compact_combat_event(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "timestamp_ms": _integer(row.get("timestamp_ms")),
        "kind": str(row.get("kind") or ""),
        "actor_guid": _integer(row.get("actor_guid")),
        "actor_name": str(row.get("actor_name") or ""),
        "actor_role": str(row.get("actor_role") or ""),
        "source_guid": _integer(row.get("source_guid")),
        "source_entry": _integer(row.get("source_entry")),
        "source_name": str(row.get("source_name") or ""),
        "source_is_pet": bool(row.get("source_is_pet")),
        "target_guid": _integer(row.get("target_guid")),
        "target_entry": _integer(row.get("target_entry")),
        "target_name": str(row.get("target_name") or ""),
        "spell_id": _integer(row.get("spell_id")),
        "spell_name": str(row.get("spell_name") or ""),
        "amount": _integer(row.get("amount")),
        "originated_amount": _integer(
            row.get("originated_amount")
            if "originated_amount" in row
            else row.get("amount")
        ),
        "absorbed_amount": _integer(row.get("absorbed_amount")),
        "source_position": {
            "x": _number(row.get("source_x")),
            "y": _number(row.get("source_y")),
            "z": _number(row.get("source_z")),
        },
        "target_position": {
            "x": _number(row.get("target_x")),
            "y": _number(row.get("target_y")),
            "z": _number(row.get("target_z")),
        },
        "distance": _number(row.get("distance")),
        "source_moving": bool(row.get("source_moving")),
    }


def _position_samples(
    combat: list[dict[str, Any]], receipts: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    samples: dict[tuple[int, int, str], dict[str, Any]] = {}
    for event in combat:
        if event["source_guid"] != event["actor_guid"] or event["source_is_pet"]:
            continue
        key = (event["actor_guid"], event["timestamp_ms"] // 1000, "combat_event")
        samples[key] = {
            "timestamp_ms": event["timestamp_ms"],
            "bot_guid": event["actor_guid"],
            "position": event["source_position"],
            "floor_z": None,
            "spline_id": None,
            "receipt_id": None,
            "basis": "landed_combat_event",
        }
    for receipt in receipts:
        actor_before = receipt.get("actor_before_planning")
        if actor_before is not None:
            key = (
                receipt["bot_guid"],
                receipt["observed_at_ms"],
                f"receipt_actor:{receipt['receipt_id']}",
            )
            samples[key] = {
                "timestamp_ms": receipt["observed_at_ms"],
                "bot_guid": receipt["bot_guid"],
                "position": actor_before,
                "floor_z": None,
                "spline_id": None,
                "receipt_id": receipt["receipt_id"],
                "basis": "receipt_actor_before_planning",
            }
        for sample in receipt["progress"]["samples"]:
            if sample.get("position") is None:
                continue
            key = (
                receipt["bot_guid"],
                _integer(sample.get("timestamp_ms")),
                f"receipt:{receipt['receipt_id']}",
            )
            samples[key] = {
                "timestamp_ms": _integer(sample.get("timestamp_ms")),
                "bot_guid": receipt["bot_guid"],
                "position": sample["position"],
                "floor_z": sample.get("floor_z"),
                "spline_id": sample.get("spline_id"),
                "receipt_id": receipt["receipt_id"],
                "basis": "receipt_tagged_native_progress",
            }
    return sorted(samples.values(), key=lambda row: (row["timestamp_ms"], row["bot_guid"], row["basis"]))


def build_replay(
    raw_path: Path,
    report_path: Path,
    *,
    before_seconds: float = 30.0,
    after_seconds: float = 1.0,
) -> tuple[dict[str, Any], dict[str, Any]]:
    rows = _load_rows(raw_path)
    report = json.loads(report_path.read_text(encoding="utf-8"))
    trace_payloads = _bound_payloads(rows, "trace")
    diagnosis_payloads = _bound_payloads(rows, "diagnosis")
    combat_payloads = _bound_payloads(rows, "combat_log")
    trace = _combined_trace(trace_payloads)
    combat_log = _combined_combat_log(combat_payloads)
    terminal_ms = _terminal_anchor_ms(report, trace)
    if terminal_ms <= 0:
        raise ValueError("terminal timestamp cannot be reconstructed")
    start_ms = terminal_ms - round(before_seconds * 1000)
    end_ms = terminal_ms + round(after_seconds * 1000)
    trace_window = [
        row for row in trace if start_ms <= _integer(row.get("timestamp_ms")) <= end_ms
    ]
    combat_recent = [
        row
        for row in combat_log.get("recent_events") or []
        if isinstance(row, dict)
    ]
    combat_window = [
        _compact_combat_event(row)
        for row in combat_recent
        if start_ms <= _integer(row.get("timestamp_ms")) <= end_ms
    ]
    decisions = [_compact_decision(row) for row in trace_window]
    receipts = _collect_receipts(trace, diagnosis_payloads, start_ms, end_ms)
    diagnoses = _diagnosis_frames(diagnosis_payloads, start_ms, end_ms)
    positions = _position_samples(combat_window, receipts)
    movement = movement_diagnostics(positions, receipts)
    duration_seconds = round((end_ms - start_ms) / 1000.0, 3)
    observed_target_distribution = target_distribution(combat_window)
    deaths = [
        row
        for row in decisions
        if row["action"] == "death" or row["result"] == "dead"
    ]
    earliest_combat_ms = min(
        (_integer(row.get("timestamp_ms")) for row in combat_recent), default=0
    )
    latest_combat_ms = max(
        (_integer(row.get("timestamp_ms")) for row in combat_recent), default=0
    )
    transport = report.get("combat_log_transport") or {}
    completeness = {
        "identity_bound_raw_rows": sum(
            1 for row in rows if (row.get("identity_binding") or {}).get("state") == "bound"
        ),
        "identity_rejected_raw_rows": sum(
            1 for row in rows if (row.get("identity_binding") or {}).get("state") == "rejected"
        ),
        "trace_entry_timestamps": "available",
        "trace_delta_gap_observed": bool(
            ((report.get("telemetry_schedule") or {}).get("scheduler_state") or {}).get(
                "trace_gap_observed"
            )
        ),
        "candidate_sets": "periodic_diagnosis_only_not_every_tick",
        "combat_transport_complete": bool(
            transport.get("complete_marker") and transport.get("reassembled")
        ),
        "combat_recent_events_dropped_before_window": _integer(
            combat_log.get("recent_events_dropped")
        ),
        "combat_window_raw_events_complete": bool(
            earliest_combat_ms and earliest_combat_ms <= start_ms and latest_combat_ms >= terminal_ms
        ),
        "combat_aggregates_complete": True,
        "positions": "sparse_receipt_samples_and_landed_combat_coordinates",
        "floor": "receipt_samples_only",
        "alive": "periodic_diagnosis_only",
        "health": "missing",
        "death_events": "trace_events",
        "cast_lifecycle": "missing",
        "aura_lifecycle": "missing",
        "boss_phase_and_hp": "missing",
        "boss_and_add_lifecycle": "missing",
        "hazard_activation_and_detection": "missing",
        "threat": "missing",
    }
    derived = {
        "dps_hps": dps_hps(combat_window, duration_seconds),
        "movement": movement,
        "target_correctness": {
            "status": "unavailable",
            "reason": "phase_aware_expected_target_contract_and_target_lifecycle_missing",
            "observed_damage_distribution": observed_target_distribution,
        },
        "hazard_reaction": {
            "status": "unavailable",
            "reason": "hazard_activation_or_detection_timestamp_missing",
        },
        "cast_downtime": {
            "status": "unavailable",
            "reason": "cast_start_success_interrupt_and_cancel_lifecycle_missing",
            "output_idle_proxy": output_idle_proxy(
                decisions, combat_window, start_ms, end_ms
            ),
        },
        "deaths": {"count": len(deaths), "events": deaths},
    }
    causal = causal_assessment(movement, receipts, diagnoses)
    replay = {
        "schema": SCHEMA,
        "source": {
            "raw_sha256": _sha256(raw_path),
            "report_sha256": _sha256(report_path),
            "source_commit": str((report.get("identity") or {}).get("head") or ""),
            "capture_id": report.get("capture_id"),
            "canonical_identity_sha256": (
                (report.get("evidence_demux") or {}).get("canonical_identity_sha256")
            ),
            "canonical_roster_sha256": (
                (report.get("evidence_demux") or {}).get("canonical_roster_sha256")
            ),
        },
        "window": {
            "anchor": "repeated_decision_watchdog",
            "terminal_at_ms": terminal_ms,
            "start_ms": start_ms,
            "end_ms": end_ms,
            "before_seconds": before_seconds,
            "after_seconds": after_seconds,
            "duration_seconds": duration_seconds,
        },
        "completeness": completeness,
        "decisions": decisions,
        "diagnosis_frames": diagnoses,
        "movement_receipts": receipts,
        "position_samples": positions,
        "combat_events": combat_window,
        "mechanic_signals": mechanic_signals(combat_window),
        "cast_events": [],
        "aura_events": [],
        "derived": derived,
        "causal_assessment": causal,
    }
    summary = {
        "schema": SUMMARY_SCHEMA,
        "source": replay["source"],
        "window": replay["window"],
        "row_counts": {
            "decisions": len(decisions),
            "diagnosis_frames": len(diagnoses),
            "movement_receipts": len(receipts),
            "position_samples": len(positions),
            "combat_events": len(combat_window),
            "mechanic_signals": len(replay["mechanic_signals"]),
        },
        "party_dps": derived["dps_hps"]["party_dps"],
        "party_hps": derived["dps_hps"]["party_hps"],
        "deaths": derived["deaths"]["count"],
        "movement_reversals": movement["oscillation"]["reversal_count"],
        "vertical_discontinuities": len(movement["vertical_discontinuities"]),
        "target_correctness": derived["target_correctness"]["status"],
        "hazard_reaction": derived["hazard_reaction"]["status"],
        "cast_downtime": derived["cast_downtime"]["status"],
        "causal_assessment": causal,
        "missing_field_ledger": {
            key: value
            for key, value in completeness.items()
            if value in {"missing", "periodic_diagnosis_only_not_every_tick"}
            or (isinstance(value, str) and value.startswith("sparse_"))
        },
    }
    return replay, summary


def _write_json(path: Path, value: dict[str, Any], *, compact: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if compact:
        rendered = json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n"
    else:
        rendered = json.dumps(value, indent=2, sort_keys=True) + "\n"
    path.write_text(rendered, encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--before-seconds", type=float, default=30.0)
    parser.add_argument("--after-seconds", type=float, default=1.0)
    args = parser.parse_args()
    replay, summary = build_replay(
        args.raw,
        args.report,
        before_seconds=args.before_seconds,
        after_seconds=args.after_seconds,
    )
    _write_json(args.output, replay, compact=True)
    summary["replay_path"] = str(args.output)
    summary["replay_sha256"] = _sha256(args.output)
    summary["replay_size_bytes"] = args.output.stat().st_size
    _write_json(args.summary, summary, compact=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

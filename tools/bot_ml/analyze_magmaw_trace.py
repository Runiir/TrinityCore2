"""Analyze a Magmaw canary trace with deterministic facts plus Jev judgments.

Jev is deliberately used at the evidence boundary.  It classifies the compact
trace summary and compares it with the expected route, but it never submits a
bot action or mutates native gameplay state.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


JEV_URL = "https://api.typesafe.ai/v1/systemone"
JEV_MODEL = "jev-latest"
JEV_CONFIDENCE_FLOOR = 0.60
DEFAULT_EXPECTED_ROUTE = (
    "bwd.magmaw.chainwielder",
    "bwd.magmaw.drudges",
    "bwd.magmaw.encounter",
)
DEFAULT_BOSS_ROUTE = ("bwd.magmaw.encounter",)
MAGMAW_ROUTE_PREFIX = "bwd.magmaw."
REPEATED_DECISION_LIMIT = 20
SAME_DECISION_LIMIT = 10
IDLE_DECISION_LIMIT = 10
TARGET_CHURN_LIMIT = 8


class JevError(RuntimeError):
    """Raised when the mandatory Jev evidence judgment cannot be obtained."""


def _as_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _payload(row: Any) -> dict[str, Any]:
    if not isinstance(row, dict):
        return {}
    value = row.get("payload")
    return value if isinstance(value, dict) else row


def _load_jsonl(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid JSON on line {line_number} of {path}") from exc
            if isinstance(row, dict):
                rows.append(row)
    return rows


def _load_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON in {path}") from exc


def _input_files(input_path: Path) -> tuple[Path | None, Path | None, Path | None]:
    if input_path.is_dir():
        raw = input_path / "raw.jsonl"
        report = input_path / "report.json"
        analysis = input_path / "combat_analysis.json"
        return raw if raw.exists() else None, report if report.exists() else None, analysis if analysis.exists() else None
    if input_path.suffix.lower() == ".jsonl":
        return input_path, None, None
    if input_path.suffix.lower() == ".json":
        return None, input_path, None
    return input_path, None, None


def _report_rows(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Adapt a closed live-validation report to the trace-row shape."""
    rows: list[dict[str, Any]] = []
    trace = report.get("trace")
    if isinstance(trace, dict) and isinstance(trace.get("entries"), list):
        entries = [entry for entry in trace["entries"] if isinstance(entry, dict)]
        if entries:
            grouped: defaultdict[tuple[int, str], list[dict[str, Any]]] = defaultdict(list)
            for entry in entries:
                grouped[(_as_int(entry.get("bot_guid")), str(entry.get("bot_name") or ""))].append(entry)
            rows.append({
                "payload": {
                    "action": "botauto_trace",
                    "bots": [
                        {"bot_guid": bot_guid, "bot_name": bot_name, "entries": bot_entries}
                        for (bot_guid, bot_name), bot_entries in sorted(grouped.items())
                    ],
                }
            })

    diagnosis = report.get("diagnosis")
    if isinstance(diagnosis, dict):
        rows.append({"payload": diagnosis})

    status: dict[str, Any] = {"action": "botauto_status"}
    for key in (
        "active_bots",
        "target_bots",
        "completion_reason",
        "failure_reason",
        "acceptable_final_evidence",
        "passed",
        "all_passed",
        "watchdog_state",
    ):
        if key in report:
            status[key] = report[key]
    summary = report.get("summary")
    if isinstance(summary, dict):
        for key in ("bots", "decisions", "raid_boss_kills", "deaths", "stuck_events"):
            if key in summary:
                status[key] = summary[key]
    if isinstance(diagnosis, dict):
        if isinstance(diagnosis.get("raid_runtime"), dict):
            status["raid_runtime"] = diagnosis["raid_runtime"]
        if isinstance(diagnosis.get("combat_metrics"), dict):
            status["combat_metrics"] = diagnosis["combat_metrics"]
    evidence = report.get("evidence")
    if isinstance(evidence, dict):
        compact_evidence = _compact_evidence(evidence)
        if compact_evidence:
            status["evidence"] = compact_evidence
        for key in ("route_terminal_evidence", "manifest_completion_evidence"):
            if isinstance(compact_evidence.get(key), list):
                status[key] = compact_evidence[key]
        for key in ("boss_kill_evidence", "boss_engagement_actions", "kills", "trash_pulls"):
            if key in compact_evidence:
                status[key] = compact_evidence[key]
    progress_counters = report.get("progress_counters")
    if isinstance(progress_counters, dict):
        status["progress_counters"] = {
            key: progress_counters[key]
            for key in (
                "boss_kill_evidence",
                "boss_engagement_actions",
                "decisions",
                "kills",
                "repeated_decisions",
                "stuck_events",
                "validation_route_terminal_evidence",
            )
            if key in progress_counters
        }
    validation_context = report.get("validation_context")
    if isinstance(validation_context, dict):
        status["route_node_id"] = validation_context.get("route_node_id", "")
        status["route_progress"] = {
            "generation": validation_context.get("route_generation", 0),
            "node_id": validation_context.get("route_node_id", ""),
        }
    rows.append({"payload": status})
    return rows


def _compact_live_report(report: dict[str, Any]) -> dict[str, Any]:
    """Keep lifecycle/admission facts when native trace rows are absent."""
    result: dict[str, Any] = {}
    for key in (
        "completion_reason",
        "failure_reason",
        "failure_labels",
        "passed",
        "all_passed",
        "acceptable_final_evidence",
        "active_bots",
        "target_bots",
        "trace_entries",
        "diagnosis_count",
    ):
        if key in report:
            result[key] = report[key]
    context = report.get("validation_context")
    if isinstance(context, dict):
        result["validation_context"] = {
            key: context[key]
            for key in (
                "scenario_id",
                "segment_id",
                "route_node_id",
                "route_label",
                "route_kind",
                "route_generation",
                "mechanic_profile",
            )
            if key in context
        }
    diagnosis = report.get("diagnosis")
    if isinstance(diagnosis, dict):
        result["diagnosis"] = {
            "failure_reason": diagnosis.get("failure_reason"),
            "combat_metrics": _compact_metrics(diagnosis.get("combat_metrics")),
            "raid_runtime": _compact_status(diagnosis),
        }
    evidence = report.get("evidence")
    if isinstance(evidence, dict):
        result["evidence"] = _compact_evidence(evidence)
    preparation = report.get("preparation")
    if isinstance(preparation, dict):
        compact_preparation: dict[str, Any] = {}
        for name, value in preparation.items():
            if not isinstance(value, dict):
                continue
            compact_preparation[name] = {
                key: value[key]
                for key in ("applied", "statement_count", "executed_statements", "action_gate_state")
                if key in value
            }
        result["preparation"] = compact_preparation
    return result


def _compact_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    """Retain native route terminals without copying a closed report blob."""
    result: dict[str, Any] = {}
    for key in (
        "boss_kill_evidence",
        "boss_engagement_actions",
        "kills",
        "trash_pulls",
        "stuck_events",
        "repeated_decisions",
        "unresolved_route_stuck_events",
        "unresolved_route_death_loop_events",
    ):
        if key in evidence:
            result[key] = evidence[key]
    for key in ("route_terminal_evidence", "manifest_completion_evidence"):
        value = evidence.get(key)
        if not isinstance(value, list):
            continue
        result[key] = [
            {
                field: item[field]
                for field in ("route_node_id", "route_generation")
                if field in item
            }
            for item in value
            if isinstance(item, dict) and item.get("route_node_id")
        ]
    diagnosis_codes = evidence.get("diagnosis_codes")
    if isinstance(diagnosis_codes, dict):
        result["diagnosis_codes"] = diagnosis_codes
    return result


def _trace_rows(rows: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for row in rows:
        payload = _payload(row)
        bots = payload.get("bots")
        if not isinstance(bots, list):
            continue
        for bot in bots:
            if not isinstance(bot, dict):
                continue
            bot_guid = _as_int(bot.get("bot_guid"))
            bot_name = str(bot.get("bot_name") or "")
            bot_entries = bot.get("entries")
            if not isinstance(bot_entries, list):
                bot_entries = bot.get("trace")
            if not isinstance(bot_entries, list):
                continue
            for entry in bot_entries:
                if not isinstance(entry, dict):
                    continue
                item = dict(entry)
                item["_bot_guid"] = bot_guid
                item["_bot_name"] = bot_name
                entries.append(item)
    entries.sort(key=lambda item: (_as_int(item.get("timestamp_ms")),
                                   _as_int(item.get("sequence"))))
    return entries


def _route_in_scope(route: str, scope_route_prefix: str) -> bool:
    if not route or not scope_route_prefix:
        return False
    if scope_route_prefix.endswith("."):
        return route.startswith(scope_route_prefix)
    return route == scope_route_prefix


def _path_for_entry(
    entry: dict[str, Any],
    scope_route_prefix: str = MAGMAW_ROUTE_PREFIX,
) -> str:
    route = str(entry.get("route_node_id") or "")
    if not _route_in_scope(route, scope_route_prefix):
        return "none"
    explicit = str(entry.get("encounter_path") or "")
    if explicit.startswith("magmaw."):
        return explicit
    text = "|".join(
        str(entry.get(key) or "")
        for key in (
            "situation",
            "action",
            "reason_code",
            "mechanic_family",
            "encounter_role_responsibility",
            "recovery_mode",
            "loop_guardrail_reason",
        )
    ).lower()
    if any(token in text for token in ("recovery", "dead", "wipe")):
        return "magmaw.recovery"
    if "parasite" in text:
        return "magmaw.parasite_escape"
    if "transfer" in text or "lane" in text:
        return "magmaw.transfer_lane"
    if any(token in text for token in ("hook", "vehicle", "mangle")):
        return "magmaw.hook"
    if any(token in text for token in ("head", "body_return", "target_return")):
        return "magmaw.head_return"
    if "formation" in text or "anchor" in text:
        return "magmaw.formation"
    if route in {"bwd.magmaw.chainwielder", "bwd.magmaw.drudges"}:
        return "magmaw.trash"
    if any(token in text for token in ("suppress", "prepull", "contract_fail_closed")):
        return "magmaw.suppression"
    if route == "bwd.magmaw.encounter":
        action = str(entry.get("action") or "")
        return "magmaw.wait" if action == "wait" or action.startswith("wait_") else "magmaw.damage"
    return "magmaw.route"


def _entry_stuck_flags(entry: dict[str, Any]) -> list[tuple[str, str]]:
    flags: list[tuple[str, str]] = []
    repeated = _as_int(entry.get("fingerprint_repeat_count"))
    if repeated >= REPEATED_DECISION_LIMIT:
        flags.append(("repeated_decision_loop", f"fingerprint_repeat_count={repeated}"))
    same = _as_int(entry.get("consecutive_same_decision_count"))
    if same >= SAME_DECISION_LIMIT:
        flags.append(("same_decision_loop", f"consecutive_same_decision_count={same}"))
    idle = _as_int(entry.get("idle_decision_repeat_count"))
    if idle >= IDLE_DECISION_LIMIT:
        flags.append(("idle_loop_guardrail", f"idle_decision_repeat_count={idle}"))
    churn = _as_int(entry.get("target_churn_count"))
    if churn >= TARGET_CHURN_LIMIT:
        flags.append(("target_churn_loop", f"target_churn_count={churn}"))
    if entry.get("loop_guardrail_action") or entry.get("loop_guardrail_reason"):
        flags.append((
            "loop_guardrail",
            f"{entry.get('loop_guardrail_action') or 'none'}:{entry.get('loop_guardrail_reason') or 'none'}",
        ))
    if _as_int(entry.get("blocked_episode_id")):
        flags.append((
            "blocked_episode",
            str(entry.get("blocked_current_reason") or entry.get("blocked_first_reason") or "unknown"),
        ))
    reason = str(entry.get("reason_code") or "")
    if reason in {"decision_failure", "event_failure", "native_action_failure"}:
        flags.append(("action_or_event_failure", reason))
    if entry.get("recovery_mode") and entry.get("recovery_mode") != "none":
        flags.append(("recovery_active", str(entry.get("recovery_mode"))))
    return flags


def _compact_status(payload: dict[str, Any]) -> dict[str, Any]:
    runtime = payload.get("raid_runtime")
    runtime = runtime if isinstance(runtime, dict) else {}
    allowed = (
        "active",
        "active_profile",
        "deaths",
        "decisions",
        "duration_seconds",
        "failures",
        "kills",
        "raid_boss_kills",
        "failure_reason",
        "completion_reason",
        "watchdog_state",
        "acceptable_final_evidence",
        "clear_complete",
    )
    result = {key: payload[key] for key in allowed if key in payload}
    for key in (
        "attempt_id",
        "alive_size",
        "active_size",
        "encounter_in_progress",
        "encounter_phase",
        "wipe_generation",
        "wipe_state",
        "bot_actions_enabled",
        "native_hostile_activity_active",
    ):
        if key in runtime:
            result[f"raid_{key}"] = runtime[key]
    route_progress = runtime.get("route_progress")
    if isinstance(route_progress, dict):
        result["route_progress"] = {
            key: route_progress[key]
            for key in ("generation", "node_index", "node_id", "target", "no_progress")
            if key in route_progress
        }
    return result


def _compact_actor(actor: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "bot_guid",
        "bot_name",
        "role",
        "damage",
        "dps",
        "healing",
        "hps",
        "pet_damage",
        "pet_damage_share",
        "uptime_seconds",
        "cast_movement_seconds",
        "range_seconds",
    )
    return {key: actor[key] for key in keys if key in actor}


def _compact_metrics(metrics: Any) -> dict[str, Any]:
    if not isinstance(metrics, dict):
        return {"available": False}
    result = {
        key: metrics[key]
        for key in (
            "schema",
            "available",
            "party_damage",
            "party_dps",
            "party_healing",
            "party_hps",
            "combat_seconds",
            "active_party_damage_seconds",
            "originated_damage_seconds",
            "raw_event_damage",
            "raw_event_dps",
            "route_generation",
            "route_node_id",
        )
        if key in metrics
    }
    actors = metrics.get("actors")
    if isinstance(actors, list):
        result["actors"] = [
            _compact_actor(actor)
            for actor in actors
            if isinstance(actor, dict)
        ]
    return result


def _diagnosis_facts(rows: Iterable[dict[str, Any]]) -> tuple[Counter[str], Counter[str]]:
    codes: Counter[str] = Counter()
    transfer_outcomes: Counter[str] = Counter()
    for row in rows:
        payload = _payload(row)
        if payload.get("action") != "botauto_diagnose":
            continue
        bots = payload.get("bots")
        if not isinstance(bots, list):
            continue
        for bot in bots:
            if not isinstance(bot, dict):
                continue
            diagnosis = bot.get("diagnosis")
            if not isinstance(diagnosis, dict):
                continue
            code = str(diagnosis.get("diagnosis_code") or "none")
            codes[code] += 1
            comparison = diagnosis.get("magmaw_transfer_lane_intent_comparison")
            if isinstance(comparison, dict):
                outcome = str(comparison.get("outcome") or "unknown")
                transfer_outcomes[outcome] += 1
    return codes, transfer_outcomes


def _progress_summary(
    entries: list[dict[str, Any]],
    expected_route: tuple[str, ...],
    rows: list[dict[str, Any]],
    scope_route_prefix: str = MAGMAW_ROUTE_PREFIX,
) -> dict[str, Any]:
    path_counts: Counter[str] = Counter()
    route_counts: Counter[str] = Counter()
    transitions: Counter[str] = Counter()
    stuck_counts: Counter[str] = Counter()
    stuck_records: dict[tuple[str, str], dict[str, Any]] = {}
    stuck_events: list[tuple[dict[str, Any], str, str, str]] = []
    bot_paths: defaultdict[int, Counter[str]] = defaultdict(Counter)
    bot_last_path: dict[int, str] = {}
    timestamps: list[int] = []
    route_order: list[str] = []
    path_order: list[str] = []
    seen_routes: set[str] = set()
    seen_paths: set[str] = set()
    route_generation_sequence: list[tuple[int, str]] = []
    route_generations: defaultdict[str, set[int]] = defaultdict(set)

    for entry in entries:
        route = str(entry.get("route_node_id") or "")
        path = _path_for_entry(entry, scope_route_prefix)
        if _route_in_scope(route, scope_route_prefix):
            timestamp = _as_int(entry.get("timestamp_ms"))
            if timestamp:
                timestamps.append(timestamp)
            route_counts[route] += 1
            generation = _as_int(entry.get("route_generation"))
            route_generations[route].add(generation)
            route_pair = (generation, route)
            if not route_generation_sequence or route_generation_sequence[-1] != route_pair:
                route_generation_sequence.append(route_pair)
            if route not in seen_routes:
                route_order.append(route)
                seen_routes.add(route)
        if path.startswith("magmaw."):
            path_counts[path] += 1
            if path not in seen_paths:
                path_order.append(path)
                seen_paths.add(path)
            bot_guid = _as_int(entry.get("_bot_guid"))
            bot_paths[bot_guid][path] += 1
            previous = bot_last_path.get(bot_guid)
            if previous and previous != path:
                transitions[f"{previous}->{path}"] += 1
            bot_last_path[bot_guid] = path
            for kind, detail in _entry_stuck_flags(entry):
                stuck_counts[kind] += 1
                stuck_events.append((entry, path, kind, detail))
                key = (kind, path)
                record = stuck_records.setdefault(
                    key,
                    {
                        "behavior": kind,
                        "path": path,
                        "count": 0,
                        "bot_guids": set(),
                        "first_sequence": _as_int(entry.get("sequence")),
                        "last_sequence": _as_int(entry.get("sequence")),
                        "evidence": [],
                    },
                )
                record["count"] += 1
                record["bot_guids"].add(bot_guid)
                record["first_sequence"] = min(
                    record["first_sequence"], _as_int(entry.get("sequence"))
                )
                record["last_sequence"] = max(
                    record["last_sequence"], _as_int(entry.get("sequence"))
                )
                if len(record["evidence"]) < 4:
                    record["evidence"].append(detail)

    expected_index = {node: index for index, node in enumerate(expected_route)}
    observed_indices = [expected_index[node] for node in route_order if node in expected_index]
    monotonic = observed_indices == sorted(observed_indices)
    unexpected = [node for node in route_order if node not in expected_index]
    repeated_route_nodes = sorted(
        node for node, generations in route_generations.items()
        if len(generations - {0}) > 1
    )

    terminal_route_nodes: list[str] = []
    terminal_generations: dict[str, int] = {}
    for row in rows:
        payload = _payload(row)
        for key in ("route_terminal_evidence", "manifest_completion_evidence"):
            values = payload.get(key)
            if not isinstance(values, list):
                continue
            for value in values:
                if not isinstance(value, dict):
                    continue
                node = str(value.get("route_node_id") or "")
                if not _route_in_scope(node, scope_route_prefix):
                    continue
                if node not in terminal_route_nodes:
                    terminal_route_nodes.append(node)
                terminal_generations[node] = max(
                    terminal_generations.get(node, 0),
                    _as_int(value.get("route_generation")),
                )

    def add_stuck_record(
        records: dict[tuple[str, str], dict[str, Any]],
        entry: dict[str, Any],
        path: str,
        kind: str,
        detail: str,
    ) -> None:
        key = (kind, path)
        record = records.setdefault(
            key,
            {
                "behavior": kind,
                "path": path,
                "count": 0,
                "bot_guids": set(),
                "first_sequence": _as_int(entry.get("sequence")),
                "last_sequence": _as_int(entry.get("sequence")),
                "evidence": [],
            },
        )
        record["count"] += 1
        record["bot_guids"].add(_as_int(entry.get("_bot_guid")))
        record["first_sequence"] = min(
            record["first_sequence"], _as_int(entry.get("sequence"))
        )
        record["last_sequence"] = max(
            record["last_sequence"], _as_int(entry.get("sequence"))
        )
        if len(record["evidence"]) < 4:
            record["evidence"].append(detail)

    active_route_pair = route_generation_sequence[-1] if route_generation_sequence else None
    active_stuck_counts: Counter[str] = Counter()
    active_stuck_records: dict[tuple[str, str], dict[str, Any]] = {}
    for entry, path, kind, detail in stuck_events:
        route = str(entry.get("route_node_id") or "")
        route_pair = (_as_int(entry.get("route_generation")), route)
        terminal_generation = terminal_generations.get(route)
        if (
            active_route_pair is not None
            and route_pair == active_route_pair
            and (
                terminal_generation is None
                or terminal_generation < route_pair[0]
            )
        ):
            active_stuck_counts[kind] += 1
            add_stuck_record(active_stuck_records, entry, path, kind, detail)

    observed_or_terminal = set(route_order) | set(terminal_route_nodes)
    missing = [node for node in expected_route if node not in observed_or_terminal]
    terminal_complete = not missing and all(
        node in terminal_route_nodes for node in expected_route
    )
    if not monotonic or unexpected or repeated_route_nodes:
        route_status = "loop_or_unexpected"
    elif not route_order:
        route_status = "complete" if terminal_complete else "no_magmaw_route_observed"
    elif not missing:
        route_status = "complete"
    else:
        route_status = "ordered_prefix_or_segment"

    stuck_behaviors = []
    for record in sorted(
        stuck_records.values(), key=lambda item: (-item["count"], item["behavior"], item["path"])
    ):
        record = dict(record)
        record["bot_guids"] = sorted(record["bot_guids"])
        stuck_behaviors.append(record)

    active_stuck_behaviors = []
    for record in sorted(
        active_stuck_records.values(),
        key=lambda item: (-item["count"], item["behavior"], item["path"]),
    ):
        record = dict(record)
        record["bot_guids"] = sorted(record["bot_guids"])
        active_stuck_behaviors.append(record)

    resolved_stuck_counts = Counter(stuck_counts)
    resolved_stuck_counts.subtract(active_stuck_counts)
    resolved_stuck_counts = Counter({
        key: value for key, value in resolved_stuck_counts.items() if value > 0
    })

    duration_seconds = 0.0
    if timestamps:
        duration_seconds = max(0.0, (max(timestamps) - min(timestamps)) / 1000.0)
    latest_status: dict[str, Any] = {}
    latest_scoped_status: dict[str, Any] = {}
    latest_metrics: dict[str, Any] = {"available": False}
    metrics_seen = 0
    for row in rows:
        payload = _payload(row)
        action = str(payload.get("action") or row.get("action") or "")
        if action == "botauto_status":
            compact_status = _compact_status(payload)
            latest_status = compact_status
            route_progress = compact_status.get("route_progress")
            if isinstance(route_progress, dict) and _route_in_scope(
                str(route_progress.get("node_id") or ""), scope_route_prefix
            ):
                latest_scoped_status = compact_status
        if isinstance(payload.get("combat_metrics"), dict):
            compact = _compact_metrics(payload["combat_metrics"])
            metric_route = str(compact.get("route_node_id") or "")
            row_route = str(payload.get("route_node_id") or "")
            if not row_route:
                row_progress = payload.get("route_progress")
                if isinstance(row_progress, dict):
                    row_route = str(row_progress.get("node_id") or "")
            route_matches = (
                _route_in_scope(metric_route or row_route, scope_route_prefix)
                if metric_route or row_route
                else True
            )
            if route_matches and compact.get("available"):
                metrics_seen += 1
                latest_metrics = compact

    diagnosis_codes, transfer_outcomes = _diagnosis_facts(rows)
    return {
        "trace_rows": len(entries),
        "magmaw_trace_rows": sum(
            1 for entry in entries
            if _path_for_entry(entry, scope_route_prefix).startswith("magmaw.")
        ),
        "bot_guids": sorted({
            _as_int(entry.get("_bot_guid"))
            for entry in entries
            if _as_int(entry.get("_bot_guid"))
            and _route_in_scope(
                str(entry.get("route_node_id") or ""), scope_route_prefix
            )
        }),
        "duration_seconds": duration_seconds,
        "route_nodes_observed": route_order,
        "route_terminal_nodes": terminal_route_nodes,
        "route_generation_sequence": [
            {"generation": generation, "route_node_id": node}
            for generation, node in route_generation_sequence
        ],
        "route_terminal_generations": terminal_generations,
        "route_node_counts": dict(sorted(route_counts.items())),
        "route_status": route_status,
        "route_missing_expected": missing,
        "route_unexpected": unexpected,
        "route_repeated_nodes": repeated_route_nodes,
        "paths_observed": path_order,
        "path_counts": dict(sorted(path_counts.items())),
        "path_transitions": dict(sorted(transitions.items())),
        "bot_path_counts": {
            str(guid): dict(sorted(counts.items()))
            for guid, counts in sorted(bot_paths.items())
        },
        "stuck_behavior_counts": dict(sorted(stuck_counts.items())),
        "stuck_behaviors": stuck_behaviors,
        "active_route_generation": (
            active_route_pair[0] if active_route_pair is not None else None
        ),
        "active_route_node_id": (
            active_route_pair[1] if active_route_pair is not None else None
        ),
        "active_stuck_behavior_counts": dict(sorted(active_stuck_counts.items())),
        "active_stuck_behaviors": active_stuck_behaviors,
        "resolved_stuck_behavior_counts": dict(sorted(resolved_stuck_counts.items())),
        "diagnosis_codes": dict(sorted(diagnosis_codes.items())),
        "transfer_lane_outcomes": dict(sorted(transfer_outcomes.items())),
        "scope_route_prefix": scope_route_prefix,
        "latest_status": latest_status,
        "latest_scoped_status": latest_scoped_status,
        "combat_metrics_observations": metrics_seen,
        "latest_combat_metrics": latest_metrics,
    }


def _analysis_metrics(analysis: Any, scope_route_prefix: str) -> dict[str, Any] | None:
    if not isinstance(analysis, dict):
        return None
    extracted = analysis.get("combat_metrics") or analysis.get("metrics")
    if isinstance(extracted, dict):
        route = str(extracted.get("route_node_id") or "")
        if (not route or _route_in_scope(route, scope_route_prefix)) and (
            extracted.get("available") or "party_dps" in extracted
        ):
            return _compact_metrics(extracted)
    encounters = analysis.get("encounters")
    if not isinstance(encounters, list):
        return None
    scoped = [
        encounter
        for encounter in encounters
        if isinstance(encounter, dict)
        and _route_in_scope(
            str(encounter.get("route_node_id") or ""), scope_route_prefix
        )
    ]
    if not scoped:
        return None
    metrics = dict(scoped[-1])
    metrics["available"] = True
    return _compact_metrics(metrics)


def _analysis_diagnostics(analysis: Any, scope_route_prefix: str) -> list[dict[str, Any]]:
    if not isinstance(analysis, dict) or not isinstance(analysis.get("diagnostics"), list):
        return []
    allowed = (
        "actor_guid",
        "actor_name",
        "amount",
        "distance_avg",
        "kind",
        "route_generation",
        "route_node_id",
        "severity",
    )
    result: list[dict[str, Any]] = []
    for diagnostic in analysis["diagnostics"]:
        if not isinstance(diagnostic, dict):
            continue
        route = str(diagnostic.get("route_node_id") or "")
        if route and not _route_in_scope(route, scope_route_prefix):
            continue
        result.append({key: diagnostic[key] for key in allowed if key in diagnostic})
    return result


def _compact_baseline(path: Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    data = _load_json(path)
    if not isinstance(data, dict):
        return None
    deterministic = data.get("deterministic")
    deterministic = deterministic if isinstance(deterministic, dict) else {}
    metrics = deterministic.get("latest_combat_metrics")
    metrics = metrics if isinstance(metrics, dict) else {}
    return {
        "run_id": data.get("run_id"),
        "change_id": (data.get("change") or {}).get("id") if isinstance(data.get("change"), dict) else None,
        "route_status": deterministic.get("route_status"),
        "path_counts": deterministic.get("path_counts", {}),
        "stuck_behavior_counts": deterministic.get("stuck_behavior_counts", {}),
        "active_stuck_behavior_counts": deterministic.get("active_stuck_behavior_counts", {}),
        "resolved_stuck_behavior_counts": deterministic.get("resolved_stuck_behavior_counts", {}),
        "combat_diagnostics": deterministic.get("combat_diagnostics", []),
        "party_dps": metrics.get("party_dps"),
        "combat_seconds": metrics.get("combat_seconds"),
    }


def _jev_questions(has_baseline: bool) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {
        "path_consistency": {
            "type": "choice",
            "instructions": "Classify whether the observed Magmaw route and encounter paths match the expected ordered path. Use route generations and native terminal evidence: many decisions within one generation are normal and are not route repetition. If route_status is complete, route_repeated_nodes is empty, and every expected node has native terminal evidence, choose aligned unless there is a separate unexplained route reversal or gap. Treat an ordered prefix as acceptable for a segment canary. If the live report has zero active bots or zero native trace rows, choose insufficient_evidence.",
            "criteria": {
                "aligned": "Observed route is ordered and the current segment has no unexplained loop or gap.",
                "ordered_segment": "The trace is an ordered, intentionally partial segment and is not enough to judge a full clear.",
                "loop_or_gap": "The trace shows repeated decisions, route reversal, missing expected handoff, or unexplained path churn.",
                "insufficient_evidence": "There are too few native trace rows to compare the path safely.",
            },
        },
        "stuck_behavior": {
            "type": "choice",
            "instructions": "Identify the primary currently-unresolved stuck behavior. Prefer active_stuck_behavior_counts and active_stuck_behaviors, which are restricted to the latest non-terminal route generation. Treat raw stuck_behavior_counts and resolved_stuck_behavior_counts as historical progress evidence, not an active blocker, when native route terminal evidence proves that node completed. When active_bots is zero and the report says admission failed or the pool was underfilled, choose lifecycle. Choose none when the run admitted bots, the active stuck set is empty, and no native unresolved route event remains.",
            "criteria": {
                "none": "No repeated, blocked, churn, failure, or recovery pattern is evidenced.",
                "movement": "Movement or formation progress is the dominant blocker.",
                "target": "Target churn, stale target return, or target lease conflict is dominant.",
                "native_action": "Candidate/action submission or native outcome failures are dominant.",
                "mechanic": "Encounter mechanic or assigned transfer/hook/parasite path is dominant.",
                "lifecycle": "Death, recovery, readiness, or route lifecycle is dominant.",
            },
        },
        "dps_loss_area": {
            "type": "choice",
            "instructions": "Classify the most actionable DPS loss area from the trace, combat metrics, and compact combat_diagnostics. Prefer an attributable execution loss over a generic rotation explanation. Use active_stuck_behavior_counts for current blockers; historical resolved counters alone do not prove current action rejection. If active_bots is zero or combat metrics are unavailable, choose insufficient_data and never infer action_rejection.",
            "criteria": {
                "no_material_loss": "DPS is available and the trace shows no material execution blocker.",
                "uptime": "The dominant loss is idle time, repeated waits, or failed action cadence.",
                "movement": "The dominant loss is movement, formation, hazard, or range downtime.",
                "targeting": "The dominant loss is target churn, stale targets, or wrong target return.",
                "action_rejection": "The dominant loss is candidate rejection, native submission failure, or repeated backoff.",
                "mechanic_downtime": "The dominant loss is a required encounter mechanic or recovery assignment.",
                "insufficient_data": "Combat metrics or attributable trace evidence are insufficient.",
            },
        },
        "next_fix": {
            "type": "choice",
            "instructions": "Choose one bounded next engineering action. Keep gameplay authority native and use the smallest fix that addresses the evidenced failure. If admission or lifecycle prevented bots from starting, choose admission_lifecycle. If repeated no_valid_profile_action or native candidate rejection dominates after admission, prefer shared_arbitration or rotation_profile over movement_recovery unless movement is the direct blocker.",
            "criteria": {
                "collect_more_canaries": "Evidence is insufficient or the behavior is not reproducible yet.",
                "admission_lifecycle": "Repair the run admission, exact roster, or lifecycle contract before judging gameplay.",
                "movement_recovery": "Repair or tune movement arbitration/recovery using the trace evidence.",
                "target_lease": "Repair target ownership, target return, or target churn handling.",
                "shared_arbitration": "Repair a shared candidate arbitration/submission edge.",
                "encounter_assignment": "Repair the encounter mechanic assignment or transfer/hook/parasite contract.",
                "rotation_profile": "Repair a class/spec priority, resource, cooldown, or target gate.",
                "native_mechanics": "Repair a native spell, aura, pet, or outcome mismatch.",
            },
        },
        "canary_safe_to_promote": {
            "type": "noul",
            "instructions": "Is this evidence safe to treat as a successful Magmaw canary result?",
            "criteria": {
                "true": "The watchdog/completion evidence is attributable, the route is complete or explicitly accepted as a segment, no death/repetition guardrail fired, and the observed outcome is consistent.",
                "false": "The run is incomplete, has a material loop/recovery failure, lacks attributable native outcome evidence, or is only a timeout/smoke observation.",
            },
        },
    }
    if has_baseline:
        questions["change_effect"] = {
            "type": "choice",
            "instructions": "Compare the current canary with the supplied baseline and classify the effect of the branch change.",
            "criteria": {
                "improved": "The current run materially reduces stuck behavior or improves attributable DPS/progress without a new regression.",
                "unchanged": "The current run is materially equivalent to the baseline.",
                "regressed": "The current run introduces a new failure or materially worsens stuck behavior, progress, or DPS.",
                "not_comparable": "The runs differ in route, roster, evidence completeness, or runtime identity enough that effect cannot be judged.",
            },
        }
    return questions


def _read_env_value(path: Path, name: str) -> str | None:
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() != name:
                continue
            value = value.strip()
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            return value
    return None


def _jev_key(env_file: Path) -> str:
    value = os.environ.get("JEV") or _read_env_value(env_file, "JEV")
    if not value:
        raise JevError(f"mandatory JEV key is missing from {env_file} or the environment")
    return value


def _call_jev(state: dict[str, Any], api_key: str, questions: dict[str, dict[str, Any]]) -> dict[str, Any]:
    body = json.dumps(
        {"state": state, "model": JEV_MODEL, "questions": questions},
        separators=(",", ":"),
        sort_keys=True,
    ).encode()
    request = Request(
        JEV_URL,
        data=body,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    last_error: Exception | None = None
    for attempt in range(3):
        try:
            with urlopen(request, timeout=45) as response:
                result = json.loads(response.read().decode("utf-8"))
            if not isinstance(result, dict) or not isinstance(result.get("answers"), dict):
                raise JevError("JEV returned no typed answers")
            missing = sorted(set(questions) - set(result["answers"]))
            if missing:
                raise JevError(f"JEV omitted typed answers: {', '.join(missing)}")
            _validate_typed_answers(result["answers"], questions)
            return result
        except HTTPError as exc:
            last_error = exc
            if exc.code not in {429, 529} or attempt == 2:
                raise JevError(f"JEV request failed with HTTP {exc.code}") from exc
        except (URLError, TimeoutError, json.JSONDecodeError) as exc:
            last_error = exc
            if attempt == 2:
                raise JevError("JEV request failed before producing typed answers") from exc
        if attempt < 2:
            time.sleep(2 ** attempt)
    raise JevError("JEV request failed before producing typed answers") from last_error


def _validate_typed_answers(
    answers: dict[str, Any],
    questions: dict[str, dict[str, Any]],
) -> None:
    for question_id, question in questions.items():
        answer = answers.get(question_id)
        if not isinstance(answer, dict):
            raise JevError(f"JEV answer is not typed for {question_id}")
        expected_type = question.get("type")
        if answer.get("type") != expected_type:
            raise JevError(
                f"JEV returned type {answer.get('type')!r} for {question_id}; "
                f"expected {expected_type!r}"
            )
        if expected_type == "choice":
            choice = answer.get("choice")
            criteria = question.get("criteria")
            if not isinstance(criteria, dict) or choice not in criteria:
                raise JevError(f"JEV returned an invalid choice for {question_id}")
            confidence = answer.get("confidence")
            if not isinstance(confidence, (int, float)) or not 0.0 <= float(confidence) <= 1.0:
                raise JevError(f"JEV returned invalid confidence for {question_id}")
            if not isinstance(answer.get("probabilities"), dict):
                raise JevError(f"JEV returned no probability map for {question_id}")
        elif expected_type == "noul":
            noul = answer.get("noul")
            if not isinstance(noul, (int, float)) or not 0.0 <= float(noul) <= 1.0:
                raise JevError(f"JEV returned invalid noul value for {question_id}")


def _answer_summary(response: dict[str, Any]) -> dict[str, Any]:
    answers = response.get("answers")
    if not isinstance(answers, dict):
        return {}
    result: dict[str, Any] = {}
    for key, answer in answers.items():
        if not isinstance(answer, dict):
            continue
        compact = {"type": answer.get("type")}
        for field in ("choice", "confidence", "noul", "score", "probabilities"):
            if field in answer:
                compact[field] = answer[field]
        result[key] = compact
    return result


def _git_identity() -> dict[str, Any]:
    try:
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], stderr=subprocess.DEVNULL, text=True
        ).strip()
        dirty = bool(subprocess.check_output(
            ["git", "status", "--porcelain"], stderr=subprocess.DEVNULL, text=True
        ).strip())
        return {"commit": commit, "dirty": dirty}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": "unknown", "dirty": True}


def _ledger_record(report: dict[str, Any]) -> dict[str, Any]:
    deterministic = report["deterministic"]
    metrics = deterministic.get("latest_combat_metrics", {})
    return {
        "run_id": report.get("run_id"),
        "recorded_at": report.get("recorded_at"),
        "change": report.get("change"),
        "source_sha256": report.get("source_sha256"),
        "route_status": deterministic.get("route_status"),
        "route_nodes_observed": deterministic.get("route_nodes_observed", []),
        "path_counts": deterministic.get("path_counts", {}),
        "stuck_behavior_counts": deterministic.get("stuck_behavior_counts", {}),
        "active_stuck_behavior_counts": deterministic.get("active_stuck_behavior_counts", {}),
        "resolved_stuck_behavior_counts": deterministic.get("resolved_stuck_behavior_counts", {}),
        "combat_diagnostics": deterministic.get("combat_diagnostics", []),
        "party_dps": metrics.get("party_dps"),
        "combat_seconds": metrics.get("combat_seconds"),
        "jev": report.get("jev", {}).get("answers", {}),
    }


def _append_ledger(path: Path, report: dict[str, Any]) -> None:
    if path.exists():
        existing = _load_json(path)
    else:
        existing = {"schema_version": 1, "runs": []}
    if not isinstance(existing, dict) or not isinstance(existing.get("runs"), list):
        raise ValueError(f"ledger must be an object with a runs list: {path}")
    existing["runs"].append(_ledger_record(report))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(existing, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def analyze(
    input_path: Path,
    *,
    env_file: Path,
    expected_route: tuple[str, ...],
    run_id: str,
    segment_id: str,
    change_id: str,
    change_note: str,
    baseline_path: Path | None,
    combat_analysis_path: Path | None,
    scope_route_prefix: str = MAGMAW_ROUTE_PREFIX,
) -> dict[str, Any]:
    raw_path, report_path, discovered_analysis = _input_files(input_path)
    live_report: dict[str, Any] | None = None
    if raw_path is not None and raw_path.exists():
        source_path = raw_path
        rows = _load_jsonl(raw_path)
    elif report_path is not None and report_path.exists():
        source_path = report_path
        loaded_report = _load_json(report_path)
        if not isinstance(loaded_report, dict):
            raise ValueError(f"live-validation report must be an object: {report_path}")
        live_report = loaded_report
        rows = _report_rows(loaded_report)
    else:
        missing_path = raw_path or report_path or input_path
        raise ValueError(f"trace input does not exist: {missing_path}")
    entries = _trace_rows(rows)
    deterministic = _progress_summary(
        entries,
        expected_route,
        rows,
        scope_route_prefix=scope_route_prefix,
    )
    baseline = _compact_baseline(baseline_path)
    analysis_path = combat_analysis_path or discovered_analysis
    if analysis_path and analysis_path.exists():
        analysis = _load_json(analysis_path)
        extracted = _analysis_metrics(analysis, scope_route_prefix)
        if extracted is not None:
            deterministic["latest_combat_metrics"] = extracted
        deterministic["combat_diagnostics"] = _analysis_diagnostics(
            analysis, scope_route_prefix
        )
    if live_report is not None:
        deterministic["live_report"] = _compact_live_report(live_report)
        diagnosis = live_report.get("diagnosis")
        diagnosis = diagnosis if isinstance(diagnosis, dict) else {}
        failure_reason = str(
            live_report.get("failure_reason")
            or diagnosis.get("failure_reason")
            or ""
        )
        if int(live_report.get("active_bots") or 0) == 0 and failure_reason:
            deterministic["stuck_behavior_counts"]["lifecycle_admission_failure"] = 1
            lifecycle_record = {
                "behavior": "lifecycle_admission_failure",
                "path": "magmaw.lifecycle",
                "count": 1,
                "bot_guids": [],
                "first_sequence": 0,
                "last_sequence": 0,
                "evidence": [failure_reason],
            }
            deterministic["stuck_behaviors"].append(lifecycle_record)
            deterministic["active_stuck_behavior_counts"]["lifecycle_admission_failure"] = 1
            deterministic["active_stuck_behaviors"].append(lifecycle_record)
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    identity = _git_identity()
    run_id = run_id or f"magmaw-jev-{source_sha256[:12]}"
    change_id = change_id or identity["commit"]
    state = {
        "task": "Magmaw 10N bot canary evidence review",
        "authority": "native TrinityCore bot runtime; Jev is shadow analysis only",
        "run_id": run_id,
        "segment_id": segment_id,
        "change": {"id": change_id, "note": change_note},
        "expected_route_nodes": list(expected_route),
        "scope_route_prefix": scope_route_prefix,
        "deterministic": deterministic,
        "baseline": baseline,
    }
    questions = _jev_questions(baseline is not None)
    response = _call_jev(state, _jev_key(env_file), questions)
    answers = _answer_summary(response)
    confidences = [
        _as_float(answer.get("confidence"))
        for answer in answers.values()
        if isinstance(answer, dict) and "confidence" in answer
    ]
    low_confidence = sorted(
        key for key, answer in answers.items()
        if isinstance(answer, dict)
        and "confidence" in answer
        and _as_float(answer.get("confidence")) < JEV_CONFIDENCE_FLOOR
    )
    report = {
        "schema_version": 1,
        "tool": "magmaw_jev_trace_analyzer",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "segment_id": segment_id,
        "source": {"path": str(source_path), "report_path": str(report_path) if report_path else None},
        "source_sha256": source_sha256,
        "change": {"id": change_id, "note": change_note, "git": identity},
        "native_authority": "native_runtime_only",
        "jev": {
            "model": response.get("model", JEV_MODEL),
            "answers": answers,
            "usage": response.get("usage", {}),
            "question_ids": sorted(questions),
            "confidence_floor": JEV_CONFIDENCE_FLOOR,
            "low_confidence_questions": low_confidence,
            "minimum_confidence": min(confidences) if confidences else None,
        },
        "deterministic": deterministic,
        "baseline": baseline,
        "progress": {
            "stuck_behaviors_observed": deterministic["stuck_behaviors"],
            "active_stuck_behaviors": deterministic["active_stuck_behaviors"],
            "resolved_stuck_behavior_counts": deterministic["resolved_stuck_behavior_counts"],
            "fix_tracking": {
                "change_id": change_id,
                "change_note": change_note,
                "jev_change_effect": answers.get("change_effect"),
            },
            "advisory_gate": "human_review_required" if low_confidence else "typed_shadow_judgment_available",
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True, help="raw.jsonl or a live-validation directory")
    parser.add_argument("--output", type=Path, required=True, help="compact JEV evidence report")
    parser.add_argument("--ledger", type=Path, help="optional append-only compact progress ledger")
    parser.add_argument("--baseline-report", type=Path, help="previous analyzer report for change-effect comparison")
    parser.add_argument("--combat-analysis", type=Path, help="optional combat_analysis.json")
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="file containing the mandatory JEV key")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--segment-id", default="04_magmaw")
    parser.add_argument("--change-id", default="")
    parser.add_argument("--change-note", default="")
    parser.add_argument(
        "--scope-route-prefix",
        default="bwd.magmaw.encounter",
        help="exact route node or dotted prefix (for example bwd.magmaw.) to attribute to this report",
    )
    parser.add_argument("--expected-route-node", action="append", dest="expected_route")
    args = parser.parse_args()

    expected_route = tuple(args.expected_route or (
        DEFAULT_BOSS_ROUTE
        if args.scope_route_prefix == "bwd.magmaw.encounter"
        else DEFAULT_EXPECTED_ROUTE
    ))
    try:
        report = analyze(
            args.input,
            env_file=args.env_file,
            expected_route=expected_route,
            run_id=args.run_id,
            segment_id=args.segment_id,
            change_id=args.change_id,
            change_note=args.change_note,
            baseline_path=args.baseline_report,
            combat_analysis_path=args.combat_analysis,
            scope_route_prefix=args.scope_route_prefix,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        if args.ledger:
            _append_ledger(args.ledger, report)
    except (JevError, OSError, ValueError) as exc:
        print(f"magmaw JEV analysis failed: {exc}", file=sys.stderr)
        return 2

    answers = report["jev"]["answers"]
    path = answers.get("path_consistency", {}).get("choice", "unknown")
    stuck = answers.get("stuck_behavior", {}).get("choice", "unknown")
    dps = answers.get("dps_loss_area", {}).get("choice", "unknown")
    print(f"JEV path={path} stuck={stuck} dps_loss={dps} report={args.output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

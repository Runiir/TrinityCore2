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
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping
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
DEFAULT_WCL_REFERENCE = Path(
    "experiments/configs/cata_raid_encounters/blackwing_descent/"
    "magmaw_wcl_dps_reference_v1.json"
)

# Candidate rows are emitted only when every profile candidate was rejected.
# Most of those rows describe an expected wait (cast in flight, GCD, resource,
# aura, target, or encounter-policy gate), not a failed native submission. Keep
# that distinction explicit at the JEV boundary so the model cannot turn a
# large candidate-search denominator into a false DPS-loss verdict.
EXPECTED_PROFILE_WAIT_REASONS = frozenset({
    "already_casting",
    "global_cooldown",
    "cooldown",
    "cooldown_not_ready",
    "mana_gate",
    "primary_power_gate",
    "insufficient_resource",
    "insufficient_soul_shards",
    "missing_required_self_aura",
    "missing_required_target_aura",
    "missing_required_owned_target_aura",
    "missing_self_aura",
    "missing_target_aura",
    "forbidden_self_aura",
    "forbidden_target_aura",
    "forbidden_owned_target_aura_active",
    "maintain_aura_active",
    "maintain_owned_aura_active",
    "insufficient_self_aura_charges",
    "hostile_target_health_gate",
    "target_health_gate",
    "enemy_count_too_low",
    "enemy_count_too_high",
    "declarative_area_damage_forbidden",
    "declarative_area_damage_semantics_forbidden",
    "future_encounter_splash_forbidden",
    "target_not_interruptible",
    "target_purpose_excluded",
    "pet_forbidden",
    "requires_ally_target",
    "temporarily_suppressed",
    "combustion_not_ready",
    "combustion_dot_window_not_ready",
    "solar_mushrooms_not_ready",
    "eclipse_dot_direction",
    "prepull_only",
    "target_immune",
})

# These are still useful for diagnosing a profile, but a candidate being
# filtered by one is normal while the surrounding state is true. They are not
# native submission failures and should not be promoted to JEV's short
# actionable-gate list.
NON_FAILURE_PROFILE_GATE_REASONS = frozenset({
    "movement_gate",
    "movement_requires_instant_action",
    "missing_or_depleted_item",
    "forbidden_self_aura_active",
    "forbidden_target_aura_active",
    "forbidden_owned_target_aura_active",
    "declarative_area_damage_forbidden",
    "declarative_area_damage_semantics_forbidden",
    "future_encounter_splash_forbidden",
    "pet_forbidden",
    "requires_ally_target",
    "owned_target_aura_duration_too_low",
})

# Magmaw can place a bot in a native controlled state during encounter
# mechanics. The resolver records every candidate rejected while that state is
# active, but those rows are mechanic downtime rather than failed submissions.
# Keep them visible in the JEV packet without allowing their volume to create a
# false rotation or movement signal.
MECHANIC_WAIT_REASONS = frozenset({
    "caster_controlled",
})

NATIVE_ACTIONABLE_FAILURE_OUTCOMES = frozenset({
    "no_action",
    "cast_failed",
    "no_line_of_sight",
    "out_of_range",
})
MOVEMENT_SIGNAL_REASONS = frozenset({
    "max_range_exceeded",
    "no_line_of_sight",
    "no_movement_blocked_lava_burst",
    "out_of_range",
    "ranged_range_required",
})
TARGET_SIGNAL_REASONS = frozenset({
    "target_not_interruptible",
    "target_purpose_excluded",
    "hostile_target_health_gate",
    "target_health_gate",
    "missing_required_target_aura",
    "missing_required_owned_target_aura",
    "forbidden_target_aura_active",
})
PROFILE_POLICY_SIGNAL_REASONS = frozenset({
    "declarative_area_damage_forbidden",
    "declarative_area_damage_semantics_forbidden",
    "future_encounter_splash_forbidden",
    "enemy_count_too_low",
    "enemy_count_too_high",
    "eclipse_dot_direction",
    "solar_mushrooms_not_ready",
    "temporarily_suppressed",
    "prepull_only",
    "target_immune",
    "pet_forbidden",
    "requires_ally_target",
})
RESOURCE_SIGNAL_REASONS = frozenset({
    "mana_gate",
    "primary_power_gate",
    "insufficient_resource",
    "insufficient_soul_shards",
    "insufficient_self_aura_charges",
    "cooldown_not_ready",
    "cooldown",
})

MAGMAW_BOSS_TARGET_ENTRIES = frozenset({41570, 42347, 48270})
MAGMAW_MECHANIC_TARGET_ENTRIES = frozenset({41806, 42321})
MAGMAW_BALANCE_MUSHROOM_SPEC = "balance_druid"
MAGMAW_BALANCE_MUSHROOM_PLACEMENT_SPELL = 88747
MAGMAW_BALANCE_MUSHROOM_DETONATE_SPELL = 88751
MAGMAW_BALANCE_MUSHROOM_DAMAGE_SPELL = 78777
MAGMAW_FIXED_BAITER_SPECS = frozenset({
    "fire_mage",
    "marksmanship_hunter",
    "survival_hunter",
})
# A small amount of parasite damage is expected from incidental target
# selection and native splash.  Only treat the target work as a required duty
# when it is material for the actor, otherwise it hides an independently
# attributable boss-uptime signal from Jev.
MAGMAW_MATERIAL_DUTY_DAMAGE = 250000.0
MAGMAW_MATERIAL_DUTY_SHARE = 0.05


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


def _discovered_combat_log_path(input_path: Path) -> Path | None:
    """Find the bounded combat-log export next to a live canary input."""
    if input_path.is_dir():
        candidate = input_path / "combat_log.json"
    elif input_path.name in {"raw.jsonl", "report.json", "combat_analysis.json"}:
        candidate = input_path.parent / "combat_log.json"
    else:
        return None
    return candidate if candidate.exists() else None


def _discovered_native_log_path(input_path: Path) -> Path | None:
    """Find the bounded worldserver log used for native encounter diagnostics."""
    if input_path.is_dir():
        candidates = (
            input_path / "native_mushroom.log",
            input_path / "worldserver_output.log",
        )
    elif input_path.name in {"raw.jsonl", "report.json", "combat_analysis.json"}:
        candidates = (
            input_path.parent / "native_mushroom.log",
            input_path.parent / "worldserver_output.log",
        )
    else:
        return None
    return next((candidate for candidate in candidates if candidate.exists()), None)


_MAGMAW_MUSHROOM_DETONATE_LOG = re.compile(
    r"MagmawWildMushroomNative event=detonate "
    r"caster=(?P<caster>.*?) expected_entry=(?P<entry>\d+) "
    r"mushroom_count=(?P<count>\d+)"
)
_MAGMAW_MUSHROOM_DAMAGE_LOG = re.compile(
    r"MagmawWildMushroomNative event=damage_cast "
    r"caster=(?P<caster>.*?) mushroom=(?P<mushroom>.*?) "
    r"entry=(?P<entry>\d+) position=(?P<x>-?\d+(?:\.\d+)?),"
    r"(?P<y>-?\d+(?:\.\d+)?),(?P<z>-?\d+(?:\.\d+)?) "
    r"result=(?P<result>\d+)"
)
_MAGMAW_MUSHROOM_TARGETS_LOG = re.compile(
    r"MagmawWildMushroomNative event=damage_targets "
    r"caster=(?P<caster>.*?) caster_entry=(?P<caster_entry>\d+) "
    r"destination=(?P<x>-?\d+(?:\.\d+)?),(?P<y>-?\d+(?:\.\d+)?),"
    r"(?P<z>-?\d+(?:\.\d+)?) target_count=(?P<count>\d+)"
)
_MAGMAW_MUSHROOM_NEARBY_TARGETS_LOG = re.compile(
    r"MagmawWildMushroomNative event=nearby_targets "
    r"destination=(?P<x>-?\d+(?:\.\d+)?),(?P<y>-?\d+(?:\.\d+)?),"
    r"(?P<z>-?\d+(?:\.\d+)?) (?:radius|probe_radius)=(?P<radius>\d+(?:\.\d+)?) "
    r"(?:native_radius=(?P<native_radius>\d+(?:\.\d+)?) )?"
    r"(?:effective_radius=\d+(?:\.\d+)? )?"
    r"target_count=(?P<count>\d+)"
)
_MAGMAW_MUSHROOM_TARGET_LOG = re.compile(
    r"MagmawWildMushroomNative event=damage_target "
    r"caster=(?P<caster>.*?) target=(?P<target>.*?) "
    r"entry=(?P<entry>\d+) position=(?P<x>-?\d+(?:\.\d+)?),"
    r"(?P<y>-?\d+(?:\.\d+)?),(?P<z>-?\d+(?:\.\d+)?)"
)
_MAGMAW_MUSHROOM_NEARBY_TARGET_LOG = re.compile(
    r"MagmawWildMushroomNative event=nearby_target target=(?P<target>.*?) "
    r"entry=(?P<entry>\d+) position=(?P<x>-?\d+(?:\.\d+)?),"
    r"(?P<y>-?\d+(?:\.\d+)?),(?P<z>-?\d+(?:\.\d+)?) "
    r"distance_2d=(?P<distance_2d>\d+(?:\.\d+)?) "
    r"distance_3d=(?P<distance_3d>\d+(?:\.\d+)?)"
)


def _native_mushroom_diagnostics(path: Path | None) -> list[dict[str, Any]]:
    """Parse only the compact bot-scoped native mushroom events."""
    if path is None or not path.exists():
        return []
    result: list[dict[str, Any]] = []
    with path.open(encoding="utf-8", errors="replace") as handle:
        for line in handle:
            match = _MAGMAW_MUSHROOM_DETONATE_LOG.search(line)
            if match:
                result.append({
                    "event": "detonate",
                    "caster": match.group("caster"),
                    "expected_entry": int(match.group("entry")),
                    "mushroom_count": int(match.group("count")),
                })
                continue
            match = _MAGMAW_MUSHROOM_DAMAGE_LOG.search(line)
            if match:
                result.append({
                    "event": "damage_cast",
                    "caster": match.group("caster"),
                    "mushroom": match.group("mushroom"),
                    "entry": int(match.group("entry")),
                    "position": {
                        "x": float(match.group("x")),
                        "y": float(match.group("y")),
                        "z": float(match.group("z")),
                    },
                    "result": int(match.group("result")),
                })
                continue
            match = _MAGMAW_MUSHROOM_TARGETS_LOG.search(line)
            if match:
                result.append({
                    "event": "damage_targets",
                    "caster": match.group("caster"),
                    "caster_entry": int(match.group("caster_entry")),
                    "destination": {
                        "x": float(match.group("x")),
                        "y": float(match.group("y")),
                        "z": float(match.group("z")),
                    },
                    "target_count": int(match.group("count")),
                })
                continue
            match = _MAGMAW_MUSHROOM_NEARBY_TARGETS_LOG.search(line)
            if match:
                result.append({
                    "event": "nearby_targets",
                    "destination": {
                        "x": float(match.group("x")),
                        "y": float(match.group("y")),
                        "z": float(match.group("z")),
                    },
                    "radius": float(match.group("radius")),
                    **({"native_radius": float(match.group("native_radius"))}
                       if match.group("native_radius") else {}),
                    "target_count": int(match.group("count")),
                })
                continue
            match = _MAGMAW_MUSHROOM_TARGET_LOG.search(line)
            if match:
                result.append({
                    "event": "damage_target",
                    "caster": match.group("caster"),
                    "target": match.group("target"),
                    "entry": int(match.group("entry")),
                    "position": {
                        "x": float(match.group("x")),
                        "y": float(match.group("y")),
                        "z": float(match.group("z")),
                    },
                })
                continue
            match = _MAGMAW_MUSHROOM_NEARBY_TARGET_LOG.search(line)
            if match:
                result.append({
                    "event": "nearby_target",
                    "target": match.group("target"),
                    "entry": int(match.group("entry")),
                    "position": {
                        "x": float(match.group("x")),
                        "y": float(match.group("y")),
                        "z": float(match.group("z")),
                    },
                    "distance_2d": float(match.group("distance_2d")),
                    "distance_3d": float(match.group("distance_3d")),
                })
    return result[-64:]


def _compact_jev_native_mushroom_diagnostics(
    rows: Any,
) -> dict[str, Any]:
    """Send JEV the mushroom geometry signal without repeating raw log rows."""
    if not isinstance(rows, list) or not rows:
        return {
            "available": False,
            "reason": "native_mushroom_diagnostics_unavailable",
        }

    event_counts: Counter[str] = Counter()
    detonation_counts: Counter[str] = Counter()
    damage_cast_results: Counter[str] = Counter()
    core_target_counts: Counter[str] = Counter()
    core_target_entries: Counter[str] = Counter()
    snapshots: list[dict[str, Any]] = []
    snapshot: dict[str, Any] | None = None

    def finish_snapshot() -> None:
        nonlocal snapshot
        if snapshot is None:
            return
        distances_2d = snapshot.pop("_distances_2d", [])
        distances_3d = snapshot.pop("_distances_3d", [])
        entries = snapshot.pop("_entries", Counter())
        snapshot["observed_target_count"] = len(distances_2d)
        snapshot["entry_counts"] = dict(sorted(entries.items()))
        snapshot["within_5_yards_2d"] = sum(
            distance <= 5.0 for distance in distances_2d
        )
        snapshot["min_distance_2d"] = round(min(distances_2d), 3) if distances_2d else None
        snapshot["min_distance_3d"] = round(min(distances_3d), 3) if distances_3d else None
        snapshot["max_distance_2d"] = round(max(distances_2d), 3) if distances_2d else None
        snapshots.append(snapshot)
        snapshot = None

    for row in rows:
        if not isinstance(row, dict):
            continue
        event = str(row.get("event") or "unknown")
        event_counts[event] += 1
        if event == "detonate":
            detonation_counts[str(_as_int(row.get("mushroom_count")))] += 1
        elif event == "damage_cast":
            damage_cast_results[str(_as_int(row.get("result")))] += 1
        elif event == "damage_targets":
            core_target_counts[str(_as_int(row.get("target_count")))] += 1
        elif event == "damage_target":
            core_target_entries[str(_as_int(row.get("entry")))] += 1
        elif event == "nearby_targets":
            finish_snapshot()
            snapshot = {
                "destination": row.get("destination"),
                "radius": row.get("radius"),
                "scan_target_count": _as_int(row.get("target_count")),
                "_distances_2d": [],
                "_distances_3d": [],
                "_entries": Counter(),
            }
        elif event == "nearby_target" and snapshot is not None:
            distance_2d = row.get("distance_2d")
            distance_3d = row.get("distance_3d")
            if isinstance(distance_2d, (int, float)):
                snapshot["_distances_2d"].append(float(distance_2d))
            if isinstance(distance_3d, (int, float)):
                snapshot["_distances_3d"].append(float(distance_3d))
            snapshot["_entries"][str(_as_int(row.get("entry")))] += 1
    finish_snapshot()

    all_distances = [
        distance
        for item in snapshots
        for distance in (
            item.get("min_distance_2d"),
            item.get("max_distance_2d"),
        )
        if isinstance(distance, (int, float))
    ]
    return {
        "available": True,
        "event_counts": dict(sorted(event_counts.items())),
        "detonation_count": sum(detonation_counts.values()),
        "mushroom_count_values": dict(sorted(detonation_counts.items())),
        "damage_cast_count": sum(damage_cast_results.values()),
        "damage_cast_result_values": dict(sorted(damage_cast_results.items())),
        "core_target_selection": {
            "snapshot_count": sum(core_target_counts.values()),
            "target_count_values": dict(sorted(core_target_counts.items())),
            "selected_target_event_count": sum(core_target_entries.values()),
            "selected_target_entry_values": dict(sorted(core_target_entries.items())),
        },
        "nearby_target_snapshots": snapshots,
        "nearby_target_summary": {
            "snapshot_count": len(snapshots),
            "observed_target_count": sum(
                _as_int(item.get("observed_target_count")) for item in snapshots
            ),
            "minimum_distance_2d": round(min(all_distances), 3)
            if all_distances
            else None,
            "within_5_yards_snapshot_count": sum(
                _as_int(item.get("within_5_yards_2d")) > 0 for item in snapshots
            ),
        },
    }


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
        for key in (
            "route_terminal_evidence",
            "manifest_completion_evidence",
            "real_boss_kill_evidence",
        ):
            if isinstance(compact_evidence.get(key), list):
                status[key] = compact_evidence[key]
        for key in ("boss_kill_evidence", "boss_engagement_actions", "kills", "trash_pulls"):
            if key in compact_evidence:
                status[key] = compact_evidence[key]
    validation_route = report.get("validation_route")
    if not isinstance(validation_route, dict):
        report_status = report.get("status")
        validation_route = (
            report_status.get("validation_route")
            if isinstance(report_status, dict)
            else None
        )
    if isinstance(validation_route, dict):
        boss_death_evidence = _compact_route_evidence(
            validation_route.get("boss_death_evidence")
        )
        if boss_death_evidence:
            status["boss_death_evidence"] = boss_death_evidence
            status.setdefault("evidence", {})["boss_death_evidence"] = boss_death_evidence
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
    status["native_gameplay_outcome"] = _native_gameplay_outcome(report)
    rows.append({"payload": status})
    return rows


def _compact_live_report(report: dict[str, Any]) -> dict[str, Any]:
    """Keep lifecycle/admission facts when native trace rows are absent."""
    result: dict[str, Any] = {}
    result["native_gameplay_outcome"] = _native_gameplay_outcome(report)
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
    validation_route = report.get("validation_route")
    if not isinstance(validation_route, dict):
        report_status = report.get("status")
        validation_route = (
            report_status.get("validation_route")
            if isinstance(report_status, dict)
            else None
        )
    if isinstance(validation_route, dict):
        boss_death_evidence = _compact_route_evidence(
            validation_route.get("boss_death_evidence")
        )
        if boss_death_evidence:
            result["boss_death_evidence"] = boss_death_evidence
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
    for key in (
        "route_terminal_evidence",
        "manifest_completion_evidence",
        "real_boss_kill_evidence",
    ):
        value = evidence.get(key)
        compact = _compact_route_evidence(value)
        if compact:
            result[key] = compact
    diagnosis_codes = evidence.get("diagnosis_codes")
    if isinstance(diagnosis_codes, dict):
        result["diagnosis_codes"] = diagnosis_codes
    return result


def _compact_route_evidence(value: Any) -> list[dict[str, Any]]:
    """Keep only the identity needed to close a native route generation."""
    if not isinstance(value, list):
        return []
    return [
        {
            field: item[field]
            for field in ("route_node_id", "route_generation")
            if field in item
        }
        for item in value
        if isinstance(item, dict) and item.get("route_node_id")
    ]


def _native_gameplay_outcome(report: Mapping[str, Any] | None) -> dict[str, Any]:
    """Separate native gameplay outcome from the certification/identity gate."""
    if not isinstance(report, Mapping):
        return {
            "schema": "magmaw_native_gameplay_outcome_v1",
            "status": "no_report",
            "native_clear": False,
            "certification_status": "unknown",
            "certification_rejections": [],
        }

    from tools.bot_ml.closed_capture_inputs import is_canonical_capture
    if is_canonical_capture(report):
        development = report.get("development_run") or {}
        clear = development.get("native_boss_death_accepted") is True
        return {
            "schema": "magmaw_native_gameplay_outcome_v1",
            "status": "clear" if clear else "incomplete",
            "native_clear": clear,
            "native_reason": "canonical_development_native_death_receipt" if clear else "native_clear_not_proven",
            "certification_status": "uncertified",
            "certification_rejections": ["development_run_not_qualification"],
            "capture_success": report.get("capture_success"),
        }

    evidence = report.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    watchdog = report.get("watchdog_state")
    watchdog = watchdog if isinstance(watchdog, Mapping) else {}
    acceptance = report.get("acceptance_verification")
    acceptance = acceptance if isinstance(acceptance, Mapping) else {}
    completion_reason = str(report.get("completion_reason") or "")
    manifest_completion = _compact_route_evidence(
        evidence.get("manifest_completion_evidence")
    )
    boss_kills = _compact_route_evidence(evidence.get("real_boss_kill_evidence"))
    all_dead_wiped = bool(
        evidence.get("cohort_all_dead_wiped") or watchdog.get("all_dead_wiped")
    )
    death_loop = bool(watchdog.get("death_loop")) or bool(
        _as_int(evidence.get("unresolved_route_death_loop_events"))
    )
    repeated_decision_loop = bool(watchdog.get("repeated_decision_loop"))
    no_progress = bool(watchdog.get("no_progress"))
    native_clear = bool(
        completion_reason == "validation_route_manifest_complete"
        and manifest_completion
        and boss_kills
        and not all_dead_wiped
        and not death_loop
        and not repeated_decision_loop
        and not no_progress
    )
    if native_clear:
        status = "clear"
        native_reason = "native_route_manifest_and_boss_death"
    elif all_dead_wiped:
        status = "wipe"
        native_reason = "native_cohort_all_dead"
    elif death_loop:
        status = "death_loop"
        native_reason = "native_death_loop_guardrail"
    elif repeated_decision_loop or no_progress:
        status = "stalled"
        native_reason = "native_watchdog_guardrail"
    elif _as_int(report.get("active_bots")) <= 0 and str(
        report.get("failure_reason") or ""
    ):
        status = "admission_failure"
        native_reason = "native_admission_failure"
    else:
        status = "incomplete"
        native_reason = "native_clear_not_proven"

    rejection_values = acceptance.get("rejections")
    if not isinstance(rejection_values, list):
        rejection_values = report.get("final_evidence_rejections")
    certification_rejections = sorted(
        {str(value) for value in (rejection_values or []) if value}
    )
    certification_accepted = bool(
        acceptance.get("accepted") is True
        and report.get("acceptable_final_evidence") is True
        and not certification_rejections
    )
    return {
        "schema": "magmaw_native_gameplay_outcome_v1",
        "status": status,
        "native_clear": native_clear,
        "native_reason": native_reason,
        "completion_reason": completion_reason,
        "manifest_completion_evidence": manifest_completion,
        "real_boss_kill_evidence": boss_kills,
        "watchdog": {
            "all_dead_wiped": all_dead_wiped,
            "death_loop": death_loop,
            "no_progress": no_progress,
            "repeated_decision_loop": repeated_decision_loop,
        },
        "certification_status": "accepted" if certification_accepted else (
            "uncertified" if native_clear else "rejected"
        ),
        "certification_rejections": certification_rejections,
    }


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


def _actor_identity(report: Any) -> dict[str, dict[str, Any]]:
    """Extract only stable identity fields needed to join combat metrics."""
    identities: dict[str, dict[str, Any]] = {}

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 5:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
            return
        if not isinstance(value, dict):
            return
        guid = 0
        for key in ("bot_guid", "guid", "actor_guid", "unit_guid"):
            guid = _as_int(value.get(key))
            if guid:
                break
        if guid:
            fields: dict[str, Any] = {}
            for target, keys in {
                "bot_name": ("bot_name", "character_name", "actor_name", "name"),
                "role": ("role", "actor_role"),
                "class_spec": ("class_spec", "spec", "actor_spec", "bot_spec"),
                "class_name": ("class_name", "class"),
            }.items():
                for key in keys:
                    if value.get(key) not in (None, ""):
                        fields[target] = value[key]
                        break
            if fields:
                identities[str(guid)] = {**identities.get(str(guid), {}), **fields}
        for key in ("diagnosis", "status", "raid_runtime", "accepted_raid_runtime", "roster", "members", "bots", "admission_receipt"):
            nested = value.get(key)
            if isinstance(nested, (dict, list)):
                visit(nested, depth + 1)

    visit(report)
    return identities


def _compact_ability(ability: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "spell_id",
        "spell_name",
        "events",
        "casts",
        "damage",
        "originated_damage",
        "damage_share",
        "originated_damage_share",
        "moving_fraction",
        "distance_avg",
        "source_is_pet",
    )
    return {key: ability[key] for key in keys if key in ability}


def _compact_actor(
    actor: dict[str, Any],
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    guid = _as_int(actor.get("bot_guid") or actor.get("actor_guid"))
    identity = (actor_identity or {}).get(str(guid), {})
    result: dict[str, Any] = {}
    aliases = {
        "bot_guid": ("bot_guid", "actor_guid"),
        "bot_name": ("bot_name", "actor_name"),
        "role": ("role", "actor_role"),
        "damage": ("damage",),
        "dps": ("dps",),
        "active_dps": ("active_dps",),
        "elapsed_dps": ("elapsed_dps",),
        "encounter_window_dps": ("encounter_window_dps",),
        "encounter_window_dps_basis": ("encounter_window_dps_basis",),
        "active_seconds": ("active_seconds",),
        "damage_uptime": ("damage_uptime",),
        "distance_avg": ("distance_avg",),
        "moving_fraction": ("moving_fraction",),
        "healing": ("healing",),
        "hps": ("hps",),
        "pet_damage": ("pet_damage",),
        "pet_damage_share": ("pet_damage_share",),
        "uptime_seconds": ("uptime_seconds",),
        "cast_movement_seconds": ("cast_movement_seconds",),
        "range_seconds": ("range_seconds",),
    }
    for target, keys in aliases.items():
        for key in keys:
            if key in actor:
                result[target] = actor[key]
                break
    if guid:
        result["bot_guid"] = guid
    for key in ("bot_name", "role"):
        if key not in result and identity.get(key) not in (None, ""):
            result[key] = identity[key]
    class_spec = identity.get("class_spec") or actor.get("class_spec") or actor.get("spec")
    if class_spec:
        result["class_spec"] = class_spec
    class_name = identity.get("class_name") or actor.get("class_name") or actor.get("class")
    if class_name:
        result["class_name"] = class_name
    abilities = actor.get("abilities")
    if isinstance(abilities, list):
        result["abilities"] = [
            _compact_ability(ability)
            for ability in abilities[:6]
            if isinstance(ability, dict)
        ]
    return result


def _compact_native_action_outcomes(
    rows: Any,
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
    focus_roles: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize the native full-window action ledger for JEV."""
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        guid = _as_int(row.get("actor_guid") or row.get("bot_guid"))
        identity = (actor_identity or {}).get(str(guid), {})
        role = str(row.get("actor_role") or identity.get("role") or "")
        if focus_roles and role and role not in focus_roles:
            continue
        item: dict[str, Any] = {
            "bot_guid": guid,
            "class_spec": str(identity.get("class_spec") or row.get("class_spec") or ""),
            "route_node_id": str(row.get("route_node_id") or ""),
            "phase": str(row.get("phase") or ""),
            # Accept both raw combat-analysis keys and the already compacted
            # native ledger. The analyzer calls this normalizer at both
            # boundaries; dropping result here silently turned every native
            # outcome into "unknown" and made JEV over-trust candidate gates.
            "action_category": str(
                row.get("action_type") or row.get("action_category") or "unknown"
            ),
            "action_name": str(row.get("action_name") or "unknown"),
            "outcome": str(row.get("result") or row.get("outcome") or "unknown"),
            "count": max(1, _as_int(row.get("count"))),
        }
        bot_name = str(row.get("actor_name") or identity.get("bot_name") or "")
        if bot_name:
            item["bot_name"] = bot_name
        if role:
            item["role"] = role
        class_id = _as_int(row.get("actor_class_id"))
        if class_id:
            item["actor_class_id"] = class_id
        spell_id = _as_int(row.get("spell_id"))
        if spell_id:
            item["spell_id"] = spell_id
        target_entry = _as_int(row.get("target_entry"))
        if target_entry:
            item["target_entry"] = target_entry
        for source, target in (
            ("reason", "reason_code"),
            ("reason_code", "reason_code"),
            ("retry_reason", "retry_reason"),
            ("first_at_ms", "first_at_ms"),
            ("last_at_ms", "last_at_ms"),
        ):
            if row.get(source) not in (None, ""):
                item[target] = row[source]
        result.append(item)
    return sorted(
        result,
        key=lambda row: (
            -int(row.get("count") or 0),
            int(row.get("bot_guid") or 0),
            str(row.get("phase") or ""),
            str(row.get("action_name") or ""),
        ),
    )


def _compact_jev_action_outcomes(rows: Any) -> list[dict[str, Any]]:
    """Keep the full-window action ledger useful without repeating identity noise."""
    if not isinstance(rows, list):
        return []
    allowed = (
        "bot_guid",
        "class_spec",
        "phase",
        "action_category",
        "action_name",
        "outcome",
        "count",
        "spell_id",
        "target_entry",
        "reason_code",
        "retry_reason",
        "first_at_ms",
        "last_at_ms",
    )
    return [
        {key: row[key] for key in allowed if key in row}
        for row in rows
        if isinstance(row, dict)
    ]


def _jev_action_outcome_slice(rows: Any) -> list[dict[str, Any]]:
    """Send direct native failures to Jev, not the expected wait ledger."""
    if not isinstance(rows, list):
        return []
    selected = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        outcome = str(row.get("outcome") or row.get("result") or "unknown")
        reason = str(row.get("reason_code") or row.get("reason") or "")
        if outcome in NATIVE_ACTIONABLE_FAILURE_OUTCOMES or reason in {
            "no_line_of_sight",
            "out_of_range",
        }:
            selected.append(row)
    return _compact_jev_action_outcomes(selected)


def _magmaw_target_class(row: Mapping[str, Any]) -> str:
    entry = _as_int(row.get("target_entry"))
    name = str(row.get("target_name") or "").lower()
    if entry in MAGMAW_MECHANIC_TARGET_ENTRIES or "parasite" in name:
        return "mechanic_target"
    if entry in MAGMAW_BOSS_TARGET_ENTRIES or "magmaw" in name or "exposed head" in name:
        return "boss_or_head"
    return "other"


def _balance_mushroom_assignment(
    class_spec: str,
    actor_abilities: list[dict[str, Any]],
    native_action_outcomes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Describe the native Balance add-duty contract without inferring casts.

    The action ledger records decision outcomes, not guaranteed landed casts.
    A successful detonation plus landed Wild Mushroom damage is therefore the
    strongest compact evidence that a duty cycle produced an effect. Placement
    rows remain attempts and are reported separately.
    """
    if class_spec != MAGMAW_BALANCE_MUSHROOM_SPEC:
        return {
            "required_assignment_active": False,
            "assignment_id": None,
            "assignment_status": "not_required",
            "assignment_counterfactual_status": "eligible",
        }

    placement_rows = [
        row
        for row in native_action_outcomes
        if _as_int(row.get("spell_id")) == MAGMAW_BALANCE_MUSHROOM_PLACEMENT_SPELL
    ]
    detonation_rows = [
        row
        for row in native_action_outcomes
        if _as_int(row.get("spell_id")) == MAGMAW_BALANCE_MUSHROOM_DETONATE_SPELL
    ]

    def row_count(rows: list[dict[str, Any]]) -> int:
        return sum(max(1, _as_int(row.get("count"))) for row in rows)

    def failure_count(rows: list[dict[str, Any]]) -> int:
        return sum(
            max(1, _as_int(row.get("count")))
            for row in rows
            if str(row.get("outcome") or row.get("result") or "")
            in NATIVE_ACTIONABLE_FAILURE_OUTCOMES
            or str(row.get("reason_code") or row.get("reason") or "")
            in {"no_line_of_sight", "out_of_range"}
        )

    mushroom_damage_rows = [
        row
        for row in actor_abilities
        if _as_int(row.get("spell_id")) == MAGMAW_BALANCE_MUSHROOM_DAMAGE_SPELL
        and _magmaw_target_class(row) == "mechanic_target"
    ]
    mushroom_damage_events = sum(
        max(0, _as_int(row.get("event_count"))) for row in mushroom_damage_rows
    )
    mushroom_damage = sum(
        max(
            0.0,
            _as_float(
                row.get("originated_damage")
                or row.get("damage")
                or row.get("raw_amount")
            ),
        )
        for row in mushroom_damage_rows
    )
    detonation_count = sum(
        max(1, _as_int(row.get("count")))
        for row in detonation_rows
        if str(row.get("outcome") or row.get("result") or "")
        not in NATIVE_ACTIONABLE_FAILURE_OUTCOMES
    )
    placement_decision_count = row_count(placement_rows)
    placement_failure_count = failure_count(placement_rows)
    placement_wait_count = sum(
        max(1, _as_int(row.get("count")))
        for row in placement_rows
        if str(row.get("outcome") or row.get("result") or "")
        in {"casting", "global_cooldown"}
        or str(row.get("reason_code") or row.get("reason") or "")
        in EXPECTED_PROFILE_WAIT_REASONS
    )

    if detonation_count and mushroom_damage_events:
        status = "executed"
        status_reason = "native_detonation_and_landed_mushroom_damage"
        counterfactual_status = "required_assignment_observed"
    elif placement_decision_count or detonation_count or mushroom_damage_events:
        status = "incomplete"
        status_reason = "assignment_evidence_without_complete_landed_cycle"
        counterfactual_status = "required_assignment_incomplete"
    else:
        status = "unobserved"
        status_reason = "no_assignment_action_or_landed_effect_observed"
        counterfactual_status = "required_assignment_unobserved"

    return {
        "required_assignment_active": True,
        "assignment_id": "magmaw_balance_mushroom_add_control",
        "assignment_contract_source": "native_balance_mushroom_duty",
        "assignment_contract": {
            "placement_spell_id": MAGMAW_BALANCE_MUSHROOM_PLACEMENT_SPELL,
            "detonate_spell_id": MAGMAW_BALANCE_MUSHROOM_DETONATE_SPELL,
            "landed_damage_spell_id": MAGMAW_BALANCE_MUSHROOM_DAMAGE_SPELL,
            "placements_per_cycle": 3,
            "detonate_after_third": True,
            "target": "lava_parasite",
        },
        "assignment_status": status,
        "assignment_status_reason": status_reason,
        "assignment_counterfactual_status": counterfactual_status,
        "assignment_detonation_count": detonation_count,
        "assignment_placement_decision_count": placement_decision_count,
        "assignment_placement_failure_count": placement_failure_count,
        "assignment_placement_wait_count": placement_wait_count,
        "assignment_damage_event_count": mushroom_damage_events,
        "assignment_landed_damage": round(mushroom_damage),
        "assignment_observation": (
            "landed_effect_and_native_detonation_are observed; placement rows "
            "are decision attempts, not proof of three legal placements"
        ),
        "assignment_failure_reasons": sorted({
            str(row.get("reason_code") or row.get("reason") or "unknown")
            for row in placement_rows
            if str(row.get("outcome") or row.get("result") or "")
            in NATIVE_ACTIONABLE_FAILURE_OUTCOMES
            or str(row.get("reason_code") or row.get("reason") or "")
            in {"no_line_of_sight", "out_of_range"}
        }),
    }


def _fixed_baiter_assignment(
    class_spec: str,
    bot_guid: int,
    actors: list[dict[str, Any]],
) -> dict[str, Any]:
    """Expose the native fixed-bait identity used by Magmaw's lane policy."""
    if class_spec not in MAGMAW_FIXED_BAITER_SPECS:
        return {
            "required_assignment_active": False,
            "assignment_id": None,
            "assignment_status": "not_required",
            "assignment_counterfactual_status": "eligible",
        }
    if class_spec == "fire_mage":
        pool_specs = {"fire_mage"}
        assignment_role = "fire_mage_pillar_baiter"
    else:
        pool_specs = {"marksmanship_hunter", "survival_hunter"}
        assignment_role = "hunter_pillar_baiter"
    pool = sorted(
        _as_int(actor.get("bot_guid") or actor.get("actor_guid"))
        for actor in actors
        if isinstance(actor, dict)
        and str(actor.get("role") or "") == "dps"
        and str(actor.get("class_spec") or actor.get("spec") or "") in pool_specs
        and _as_int(actor.get("bot_guid") or actor.get("actor_guid"))
    )
    if not pool or bot_guid != pool[0]:
        return {
            "required_assignment_active": False,
            "assignment_id": None,
            "assignment_status": "not_required",
            "assignment_counterfactual_status": "eligible",
        }
    return {
        "required_assignment_active": True,
        "assignment_id": "magmaw_fixed_pillar_baiter",
        "assignment_role": assignment_role,
        "assignment_contract_source": "BotAdaptiveMagmawParasitePolicy::ResolveFixedBaiters",
        "assignment_contract": {
            "selection": "lowest_guid_per_class_family_from_frozen_roster",
            "fire_mage_guid": pool[0] if class_spec == "fire_mage" else None,
            "hunter_guid": pool[0] if class_spec != "fire_mage" else None,
            "duty": "retain_fixed_pillar_lane_and_bait_pillar_of_flame",
        },
        "assignment_status": "identity_assigned",
        "assignment_status_reason": "native_fixed_bait_identity_matches_frozen_roster",
        "assignment_counterfactual_status": "required_assignment_unobserved",
        "assignment_observation": (
            "native roster identity is known; retained trace does not prove the "
            "full bait movement episode"
        ),
    }


MAGMAW_VEHICLE_CONTROL_PROXIMITY_MS = 1_000


def _magmaw_vehicle_control_receipts(
    live_report: dict[str, Any] | None,
) -> dict[int, list[dict[str, Any]]]:
    """Extract attributable Mangle/vehicle-exit control receipts.

    The combat log records the resulting damage cadence, while the native
    report records the vehicle-exit receipt in the final per-bot snapshot.
    Keeping this overlay separate from target damage prevents a mechanic
    receipt from being mistaken for an ordinary rotation gap. A short
    pre-arm proximity window handles the final damage gap immediately before
    the server arms the landing receipt without claiming the whole encounter
    was controlled.
    """
    if not isinstance(live_report, dict):
        return {}
    diagnosis = live_report.get("diagnosis")
    if not isinstance(diagnosis, dict):
        return {}
    bots = diagnosis.get("bots")
    if not isinstance(bots, list):
        return {}

    receipts_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for bot in bots:
        if not isinstance(bot, dict):
            continue
        identity = bot.get("identity")
        snapshot = bot.get("snapshot")
        if not isinstance(identity, dict) or not isinstance(snapshot, dict):
            continue
        guid = _as_int(identity.get("bot_guid"))
        if not guid:
            continue
        landing = snapshot.get("server_vehicle_exit_landing")
        if not isinstance(landing, dict):
            continue
        receipt = landing.get("movement_receipt")
        if not isinstance(receipt, dict) or not bool(receipt.get("available")):
            continue
        if _as_int(receipt.get("bot_guid")) != guid:
            continue
        armed_at_ms = _as_int(receipt.get("armed_at_ms"))
        if not armed_at_ms:
            continue
        last_evaluation = landing.get("last_evaluation")
        last_evaluation_at_ms = (
            _as_int(last_evaluation.get("timestamp_ms"))
            if isinstance(last_evaluation, dict)
            else 0
        )
        terminal_at_ms = max(
            armed_at_ms,
            _as_int(receipt.get("terminal_at_ms")),
            _as_int(receipt.get("last_observed_at_ms")),
            last_evaluation_at_ms,
        )
        receipts_by_guid[guid].append({
            "kind": "mangle_vehicle_exit",
            "receipt_id": _as_int(receipt.get("receipt_id")),
            "armed_at_ms": armed_at_ms,
            "terminal_at_ms": terminal_at_ms,
            "terminal_outcome": str(receipt.get("terminal_outcome") or ""),
            "vehicle_observed": bool(landing.get("vehicle_observed")),
        })
    return dict(receipts_by_guid)


def _target_duty_context(
    combat_log: dict[str, Any] | None,
    metrics: dict[str, Any] | None,
    native_action_outcomes: Any,
    live_report: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a compact target/duty overlay without sending raw events to Jev.

    The combat log has full-window target aggregates but only a bounded recent
    event ring.  Keep those evidence scopes separate: target attribution can be
    complete even when movement samples are partial.  A repair is not
    counterfactual-ready when this distinction is lost.
    """
    if not isinstance(combat_log, dict) or not isinstance(metrics, dict):
        return {
            "available": False,
            "reason": "combat_log_or_boss_metrics_unavailable",
            "actors": [],
        }

    actors = metrics.get("actors")
    if not isinstance(actors, list):
        return {
            "available": False,
            "reason": "boss_actor_metrics_unavailable",
            "actors": [],
        }
    dps_guids = {
        _as_int(actor.get("bot_guid") or actor.get("actor_guid"))
        for actor in actors
        if isinstance(actor, dict) and str(actor.get("role") or "") == "dps"
    }
    dps_guids.discard(0)
    vehicle_control_by_guid = _magmaw_vehicle_control_receipts(live_report)

    abilities_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in combat_log.get("abilities") or []:
        if not isinstance(row, dict):
            continue
        guid = _as_int(row.get("actor_guid") or row.get("bot_guid"))
        if (
            guid in dps_guids
            and str(row.get("route_node_id") or "") == DEFAULT_BOSS_ROUTE[0]
            and str(row.get("perspective") or "") in {"", "damage_done"}
        ):
            abilities_by_guid[guid].append(row)

    recent_events_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in combat_log.get("recent_events") or []:
        if not isinstance(row, dict) or str(row.get("kind") or "") != "damage":
            continue
        guid = _as_int(row.get("source_guid") or row.get("actor_guid"))
        if (
            guid in dps_guids
            and str(row.get("route_node_id") or "") == DEFAULT_BOSS_ROUTE[0]
        ):
            recent_events_by_guid[guid].append(row)

    failure_rows_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    native_rows_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in native_action_outcomes if isinstance(native_action_outcomes, list) else []:
        if not isinstance(row, dict):
            continue
        guid = _as_int(row.get("bot_guid") or row.get("actor_guid"))
        if guid in dps_guids:
            native_rows_by_guid[guid].append(row)
        outcome = str(row.get("outcome") or row.get("result") or "")
        reason = str(row.get("reason_code") or row.get("reason") or "")
        if (
            guid in dps_guids
            and (
                outcome in NATIVE_ACTIONABLE_FAILURE_OUTCOMES
                or reason in {"no_line_of_sight", "out_of_range"}
            )
        ):
            failure_rows_by_guid[guid].append(row)

    recent_events_dropped = max(0, _as_int(combat_log.get("recent_events_dropped")))
    recent_event_capacity = max(0, _as_int(combat_log.get("recent_event_capacity")))
    actor_contexts: list[dict[str, Any]] = []

    def row_amount(row: Mapping[str, Any], field: str) -> float:
        if field == "originated_damage" and "originated_amount" in row:
            return max(0.0, _as_float(row.get("originated_amount")))
        return max(
            0.0,
            _as_float(row.get("amount") or row.get("raw_amount")),
        )

    def interval_overlaps(
        first_at_ms: int,
        last_at_ms: int,
        other_first_at_ms: int,
        other_last_at_ms: int,
    ) -> bool:
        if not first_at_ms or not last_at_ms or not other_first_at_ms or not other_last_at_ms:
            return False
        return max(first_at_ms, other_first_at_ms) <= min(last_at_ms, other_last_at_ms)

    for guid in sorted(dps_guids):
        actor = next(
            (
                value
                for value in actors
                if isinstance(value, dict)
                and _as_int(value.get("bot_guid") or value.get("actor_guid")) == guid
            ),
            {},
        )
        class_spec = str(actor.get("class_spec") or actor.get("spec") or "")
        actor_abilities = abilities_by_guid.get(guid, [])
        assignment = _balance_mushroom_assignment(
            class_spec,
            actor_abilities,
            native_rows_by_guid.get(guid, []),
        )
        if not assignment.get("required_assignment_active"):
            assignment = _fixed_baiter_assignment(class_spec, guid, actors)
        category_totals: defaultdict[str, dict[str, Any]] = defaultdict(
            lambda: {
                "event_count": 0,
                "raw_damage": 0.0,
                "originated_damage": 0.0,
                "first_at_ms": 0,
                "last_at_ms": 0,
            }
        )
        for row in actor_abilities:
            category = _magmaw_target_class(row)
            summary = category_totals[category]
            summary["event_count"] += max(0, _as_int(row.get("event_count")))
            summary["raw_damage"] += row_amount(row, "raw_damage")
            summary["originated_damage"] += row_amount(row, "originated_damage")
            first_at_ms = _as_int(row.get("first_at_ms"))
            last_at_ms = _as_int(row.get("last_at_ms"))
            if first_at_ms:
                summary["first_at_ms"] = min(
                    first_at_ms,
                    summary["first_at_ms"] or first_at_ms,
                )
            if last_at_ms:
                summary["last_at_ms"] = max(summary["last_at_ms"], last_at_ms)

        total_originated = sum(
            float(summary["originated_damage"])
            for summary in category_totals.values()
        )
        if total_originated <= 0.0:
            total_originated = sum(
                float(summary["raw_damage"])
                for summary in category_totals.values()
            )
        mechanic = category_totals.get("mechanic_target", {})
        mechanic_damage = float(mechanic.get("originated_damage") or 0.0)
        if mechanic_damage <= 0.0:
            mechanic_damage = float(mechanic.get("raw_damage") or 0.0)
        mechanic_share = round(mechanic_damage / max(1.0, total_originated), 6)

        recent_events = recent_events_by_guid.get(guid, [])
        damage_timestamps = sorted({
            _as_int(row.get("timestamp_ms"))
            for row in recent_events
            if _as_int(row.get("timestamp_ms"))
        })
        damage_gaps = [
            (later - earlier) / 1000.0
            for earlier, later in zip(damage_timestamps, damage_timestamps[1:])
            if later > earlier
        ]
        damage_gap_intervals = [
            (earlier, later, (later - earlier) / 1000.0)
            for earlier, later in zip(damage_timestamps, damage_timestamps[1:])
            if later > earlier
        ]
        damage_gaps_ge_3 = [gap for gap in damage_gaps if gap >= 3.0]
        damage_gaps_ge_5 = [gap for gap in damage_gaps if gap >= 5.0]
        moving_timestamps = [
            _as_int(row.get("timestamp_ms"))
            for row in recent_events
            if bool(row.get("source_moving")) and _as_int(row.get("timestamp_ms"))
        ]
        mechanic_intervals = [
            (
                _as_int(row.get("first_at_ms")),
                _as_int(row.get("last_at_ms")),
            )
            for row in actor_abilities
            if _magmaw_target_class(row) == "mechanic_target"
            and _as_int(row.get("first_at_ms"))
            and _as_int(row.get("last_at_ms"))
        ]
        vehicle_control_receipts = vehicle_control_by_guid.get(guid, [])
        vehicle_control_intervals = [
            (
                _as_int(receipt.get("armed_at_ms")),
                _as_int(receipt.get("terminal_at_ms")),
            )
            for receipt in vehicle_control_receipts
            if _as_int(receipt.get("armed_at_ms"))
            and _as_int(receipt.get("terminal_at_ms"))
        ]

        def interval_overlap_seconds(
            first_at_ms: int,
            last_at_ms: int,
            other_first_at_ms: int,
            other_last_at_ms: int,
        ) -> float:
            if not first_at_ms or not last_at_ms or not other_first_at_ms or not other_last_at_ms:
                return 0.0
            overlap_ms = min(last_at_ms, other_last_at_ms) - max(
                first_at_ms,
                other_first_at_ms,
            )
            return max(0.0, overlap_ms / 1000.0)

        control_gap_count = 0
        control_gap_overlap_seconds = 0.0
        proximate_control_gap_count = 0
        proximate_control_gap_seconds = 0.0
        for gap_first_at_ms, gap_last_at_ms, gap_seconds in damage_gap_intervals:
            direct_overlap = sum(
                interval_overlap_seconds(
                    gap_first_at_ms,
                    gap_last_at_ms,
                    control_first_at_ms,
                    control_last_at_ms,
                )
                for control_first_at_ms, control_last_at_ms in vehicle_control_intervals
            )
            if direct_overlap > 0.0:
                control_gap_count += 1
                control_gap_overlap_seconds += min(gap_seconds, direct_overlap)
                continue
            if any(
                0 <= control_first_at_ms - gap_last_at_ms
                <= MAGMAW_VEHICLE_CONTROL_PROXIMITY_MS
                and gap_first_at_ms < control_first_at_ms
                for control_first_at_ms, _ in vehicle_control_intervals
            ):
                proximate_control_gap_count += 1
                proximate_control_gap_seconds += gap_seconds

        vehicle_control_seconds = sum(
            max(0.0, (last_at_ms - first_at_ms) / 1000.0)
            for first_at_ms, last_at_ms in vehicle_control_intervals
        )

        def timestamp_in_intervals(timestamp_ms: int,
            intervals: list[tuple[int, int]]) -> bool:
            return any(
                first_at_ms <= timestamp_ms <= last_at_ms
                for first_at_ms, last_at_ms in intervals
                if first_at_ms and last_at_ms
            )

        duty_moving_timestamps = [
            timestamp_ms
            for timestamp_ms in moving_timestamps
            if timestamp_in_intervals(timestamp_ms, mechanic_intervals)
        ]
        recent_mechanic_event_count = sum(
            1
            for row in recent_events
            if _magmaw_target_class(row) == "mechanic_target"
        )
        correlated_failures = 0
        failure_windows: list[dict[str, Any]] = []
        for row in failure_rows_by_guid.get(guid, []):
            first_at_ms = _as_int(row.get("first_at_ms"))
            last_at_ms = _as_int(row.get("last_at_ms"))
            failure_target_entry = _as_int(row.get("target_entry"))
            failure_target_category = _magmaw_target_class({
                "target_entry": failure_target_entry,
            }) if failure_target_entry else ""
            mechanic_overlap = any(
                interval_overlaps(first_at_ms, last_at_ms, duty_first, duty_last)
                for duty_first, duty_last in mechanic_intervals
            )
            # An aggregate failure now carries the target entry captured at
            # RecordCombatAttempt time.  If the failed action was explicitly
            # aimed at Magmaw/head, an overlapping parasite damage event is
            # not evidence that the failed cast itself was mechanic duty.
            if failure_target_category in {"boss_or_head", "other"}:
                mechanic_overlap = False
            movement_overlap = any(
                first_at_ms <= timestamp <= last_at_ms
                for timestamp in moving_timestamps
                if first_at_ms and last_at_ms
            )
            if mechanic_overlap or movement_overlap:
                correlated_failures += 1
                failure_window = {
                    "action_name": str(row.get("action_name") or "unknown"),
                    "outcome": str(row.get("outcome") or row.get("result") or "unknown"),
                    "reason_code": str(row.get("reason_code") or row.get("reason") or ""),
                    "overlap": [
                        label
                        for label, enabled in (
                            ("mechanic_target", mechanic_overlap),
                            ("moving_damage_event", movement_overlap),
                        )
                        if enabled
                    ],
                }
                if failure_target_entry:
                    failure_window["target_entry"] = failure_target_entry
                    failure_window["target_category"] = failure_target_category
                failure_windows.append(failure_window)

        meaningful_mechanic_duty = (
            mechanic_damage >= MAGMAW_MATERIAL_DUTY_DAMAGE
            or mechanic_share >= MAGMAW_MATERIAL_DUTY_SHARE
        )
        required_assignment_active = bool(
            assignment.get("required_assignment_active")
        )
        assignment_explains_idle = bool(
            required_assignment_active
            and assignment.get("assignment_status") == "executed"
        )
        duty_explains_idle = bool(
            assignment_explains_idle
            or (
                meaningful_mechanic_duty
                and (correlated_failures > 0 or bool(duty_moving_timestamps))
            )
            or control_gap_count > 0
            or proximate_control_gap_count > 0
        )
        if actor_abilities:
            counterfactual_status = str(
                assignment.get("assignment_counterfactual_status")
                if required_assignment_active
                else (
                    "mangle_vehicle_control_observed"
                    if vehicle_control_receipts
                    else (
                        "partial_recent_capture"
                        if recent_events_dropped > 0
                        else "unavailable" if not recent_events else "eligible"
                    )
                )
            )
        else:
            counterfactual_status = (
                str(assignment.get("assignment_counterfactual_status"))
                if required_assignment_active
                else (
                    "mangle_vehicle_control_observed"
                    if vehicle_control_receipts
                    else "unavailable"
                )
            )
        target_categories = []
        for category in ("boss_or_head", "mechanic_target", "other"):
            summary = category_totals.get(category)
            if not summary or not summary["event_count"]:
                continue
            target_categories.append({
                "category": category,
                "event_count": int(summary["event_count"]),
                "originated_damage": round(float(summary["originated_damage"])),
            })
        actor_contexts.append({
            "bot_guid": guid,
            "target_categories": target_categories,
            "boss_or_head_originated_damage_share": round(
                float(category_totals.get("boss_or_head", {}).get("originated_damage") or 0.0)
                / max(1.0, total_originated),
                6,
            ),
            "mechanic_target_originated_damage": round(mechanic_damage),
            "mechanic_target_originated_damage_share": mechanic_share,
            "mechanic_target_window_count": len(mechanic_intervals),
            "mechanic_duty_scope": (
                "required_assignment"
                if required_assignment_active
                else (
                    "mangle_vehicle"
                    if vehicle_control_receipts
                    else ("material" if meaningful_mechanic_duty else "incidental")
                )
            ),
            **assignment,
            "magmaw_control_receipt_count": len(vehicle_control_receipts),
            "magmaw_control_seconds": round(vehicle_control_seconds, 3),
            "magmaw_control_gap_count": control_gap_count,
            "magmaw_control_gap_overlap_seconds": round(
                control_gap_overlap_seconds,
                3,
            ),
            "magmaw_proximate_control_gap_count": proximate_control_gap_count,
            "magmaw_proximate_control_gap_seconds": round(
                proximate_control_gap_seconds,
                3,
            ),
            "magmaw_control_receipts": [
                {
                    key: receipt[key]
                    for key in (
                        "kind",
                        "receipt_id",
                        "armed_at_ms",
                        "terminal_at_ms",
                        "terminal_outcome",
                        "vehicle_observed",
                    )
                    if key in receipt
                }
                for receipt in vehicle_control_receipts[:4]
            ],
            "recent_damage_event_count": len(recent_events),
            "damage_cadence_capture": (
                "unavailable" if not recent_events else "full_window_no_drops" if recent_events_dropped == 0
                else "partial_recent_capture"
            ),
            "damage_event_first_at_ms": min(damage_timestamps, default=0),
            "damage_event_last_at_ms": max(damage_timestamps, default=0),
            "damage_gap_max_seconds": round(max(damage_gaps, default=0.0), 3) if recent_events else None,
            "damage_gap_count_ge_3_seconds": len(damage_gaps_ge_3) if recent_events else None,
            "damage_gap_count_ge_5_seconds": len(damage_gaps_ge_5) if recent_events else None,
            "damage_gap_seconds_ge_3_total": round(sum(damage_gaps_ge_3), 3) if recent_events else None,
            "recent_mechanic_damage_event_count": recent_mechanic_event_count,
            "recent_moving_damage_event_count": len(moving_timestamps),
            "recent_moving_damage_event_fraction": round(
                len(moving_timestamps) / max(1, len(recent_events)),
                6,
            ),
            "duty_moving_damage_event_count": len(duty_moving_timestamps),
            "duty_moving_damage_event_fraction": round(
                len(duty_moving_timestamps) / max(1, len(moving_timestamps)),
                6,
            ),
            "native_failure_window_count": len(failure_rows_by_guid.get(guid, [])),
            "duty_correlated_native_failure_window_count": correlated_failures,
            "duty_correlated_native_failures": failure_windows[:8],
            "duty_explains_idle": duty_explains_idle,
            "counterfactual_status": counterfactual_status,
            "counterfactual_eligible": (
                counterfactual_status == "eligible"
                and not required_assignment_active
            ),
        })

    return {
        "available": bool(actor_contexts),
        "scope_route_node": DEFAULT_BOSS_ROUTE[0],
        "full_window_target_aggregate": bool(abilities_by_guid),
        "recent_event_capture": {
            "capacity": recent_event_capacity,
            "dropped": recent_events_dropped,
            "partial": recent_events_dropped > 0,
        },
        "causal_action_gate": (
            "authorize only when counterfactual_eligible is true and "
            "duty_explains_idle is false; native Mangle/vehicle receipts are "
            "mechanic downtime; otherwise keep the result advisory"
        ),
        "actors": actor_contexts,
    }


def _compact_jev_target_duty_context(
    context: dict[str, Any] | None,
    actor_guids: set[int] | None = None,
) -> dict[str, Any]:
    """Keep the causal duty gate without repeating assignment metadata.

    The deterministic report retains the complete target-duty overlay.  Jev
    needs the per-actor causal facts, not the repeated contract prose and raw
    failure-window rows that are already represented by the native outcome
    view and actor loss signals.
    """
    if not isinstance(context, dict):
        return {
            "available": False,
            "reason": "target_duty_context_unavailable",
            "actors": [],
        }
    result = {
        key: context[key]
        for key in (
            "available",
            "scope_route_node",
            "full_window_target_aggregate",
            "recent_event_capture",
            "causal_action_gate",
        )
        if key in context
    }
    recent_capture = result.get("recent_event_capture")
    if isinstance(recent_capture, dict):
        result["recent_event_capture"] = {
            key: recent_capture[key]
            for key in ("capacity", "dropped", "partial")
            if key in recent_capture
        }
    actor_keys = (
        "bot_guid",
        "target_categories",
        "boss_or_head_originated_damage_share",
        "mechanic_target_originated_damage",
        "mechanic_target_originated_damage_share",
        "mechanic_target_window_count",
        "mechanic_duty_scope",
        "magmaw_control_receipt_count",
        "magmaw_control_seconds",
        "magmaw_control_gap_count",
        "magmaw_control_gap_overlap_seconds",
        "magmaw_proximate_control_gap_count",
        "magmaw_proximate_control_gap_seconds",
        "magmaw_control_receipts",
        "required_assignment_active",
        "assignment_id",
        "assignment_role",
        "assignment_status",
        "assignment_counterfactual_status",
        "assignment_detonation_count",
        "assignment_placement_decision_count",
        "assignment_placement_failure_count",
        "assignment_damage_event_count",
        "assignment_landed_damage",
        "recent_damage_event_count",
        "damage_cadence_capture",
        "damage_gap_max_seconds",
        "damage_gap_count_ge_3_seconds",
        "damage_gap_count_ge_5_seconds",
        "damage_gap_seconds_ge_3_total",
        "recent_mechanic_damage_event_count",
        "recent_moving_damage_event_count",
        "recent_moving_damage_event_fraction",
        "duty_moving_damage_event_count",
        "duty_moving_damage_event_fraction",
        "native_failure_window_count",
        "duty_correlated_native_failure_window_count",
        "duty_explains_idle",
        "counterfactual_status",
        "counterfactual_eligible",
    )
    result["actors"] = [
        {
            key: actor[key]
            for key in actor_keys
            if key in actor
        }
        for actor in context.get("actors", [])
        if isinstance(actor, dict)
        and (
            actor_guids is None
            or _as_int(actor.get("bot_guid")) in actor_guids
        )
    ]
    return result


def _compact_jev_candidate_signal(signal: dict[str, Any]) -> dict[str, Any]:
    """Drop duplicated candidate rows while retaining native gate counts."""
    return {
        key: signal[key]
        for key in (
            "interpretation",
            "candidate_scan_count",
            "expected_profile_wait_count",
            "expected_profile_wait_reasons",
            "mechanic_wait_count",
            "mechanic_wait_reasons",
            "non_failure_profile_gate_count",
            "non_failure_profile_gate_reasons",
            "actionable_candidate_count",
            "actionable_candidate_reasons",
        )
        if key in signal
    }


def _summarize_jev_action_outcomes(rows: Any) -> list[dict[str, Any]]:
    """Summarize native outcomes by actor without losing failure semantics."""
    if not isinstance(rows, list):
        return []
    grouped: dict[tuple[int, str], dict[str, Any]] = {}
    actionable_failures = {"no_action", "cast_failed", "no_line_of_sight", "out_of_range"}
    expected_waits = {"casting", "global_cooldown"}
    for row in rows:
        if not isinstance(row, dict):
            continue
        guid = _as_int(row.get("bot_guid") or row.get("actor_guid"))
        class_spec = str(row.get("class_spec") or "")
        key = (guid, class_spec)
        item = grouped.setdefault(
            key,
            {
                "bot_guid": guid,
                "class_spec": class_spec,
                "outcome_counts": Counter(),
                "actionable_failure_count": 0,
                "expected_wait_count": 0,
            },
        )
        outcome = str(row.get("outcome") or row.get("result") or "unknown")
        count = max(1, _as_int(row.get("count")))
        item["outcome_counts"][outcome] += count
        if outcome in actionable_failures:
            item["actionable_failure_count"] += count
        if outcome in expected_waits:
            item["expected_wait_count"] += count
    result = []
    for item in grouped.values():
        result.append(
            {
                "bot_guid": item["bot_guid"],
                "class_spec": item["class_spec"],
                "outcome_counts": dict(
                    sorted(item["outcome_counts"].items(), key=lambda pair: (-pair[1], pair[0]))
                ),
                "outcome_count": sum(item["outcome_counts"].values()),
                "actionable_failure_count": item["actionable_failure_count"],
                "actionable_failure_ratio": round(
                    item["actionable_failure_count"]
                    / max(1, sum(item["outcome_counts"].values())),
                    6,
                ),
                "expected_wait_count": item["expected_wait_count"],
            }
        )
    return sorted(result, key=lambda row: int(row.get("bot_guid") or 0))


def _summarize_jev_failure_action_outcomes(
    rows: Any,
    limit: int = 16,
) -> list[dict[str, Any]]:
    """Keep direct native failures attributable without sending every row."""
    if not isinstance(rows, list):
        return []
    grouped: dict[tuple[int, str, str, str, str, int], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (
            _as_int(row.get("bot_guid") or row.get("actor_guid")),
            str(row.get("class_spec") or ""),
            str(row.get("action_name") or "unknown"),
            str(row.get("outcome") or row.get("result") or "unknown"),
            str(row.get("reason_code") or row.get("retry_reason") or ""),
            _as_int(row.get("target_entry")),
        )
        item = grouped.setdefault(key, {"count": 0, "first_at_ms": 0, "last_at_ms": 0})
        item["count"] += max(1, _as_int(row.get("count")))
        first_at_ms = _as_int(row.get("first_at_ms"))
        last_at_ms = _as_int(row.get("last_at_ms"))
        if first_at_ms:
            item["first_at_ms"] = min(
                first_at_ms,
                int(item["first_at_ms"] or first_at_ms),
            )
        if last_at_ms:
            item["last_at_ms"] = max(int(item["last_at_ms"]), last_at_ms)

    result = []
    for (guid, class_spec, action_name, outcome, reason_code, target_entry), summary in sorted(
        grouped.items(), key=lambda item: (-int(item[1]["count"]), item[0])
    )[:limit]:
        item: dict[str, Any] = {
            "bot_guid": guid,
            "class_spec": class_spec,
            "action_name": action_name,
            "outcome": outcome,
            "count": int(summary["count"]),
        }
        if reason_code:
            item["reason_code"] = reason_code
        if target_entry:
            item["target_entry"] = target_entry
        if summary["first_at_ms"] and summary["last_at_ms"]:
            item["first_at_ms"] = int(summary["first_at_ms"])
            item["last_at_ms"] = int(summary["last_at_ms"])
        result.append(item)
    return result


def _compact_native_candidate_rejections(
    rows: Any,
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
    focus_roles: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Normalize full-window profile-gate counts for JEV attribution."""
    if not isinstance(rows, list):
        return []
    result: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        guid = _as_int(row.get("actor_guid") or row.get("bot_guid"))
        identity = (actor_identity or {}).get(str(guid), {})
        role = str(row.get("actor_role") or identity.get("role") or "")
        if focus_roles and role and role not in focus_roles:
            continue
        item: dict[str, Any] = {
            "bot_guid": guid,
            "class_spec": str(identity.get("class_spec") or row.get("class_spec") or ""),
            "spell_id": _as_int(row.get("spell_id")),
            "action_category": str(row.get("action_category") or "unknown"),
            "reason": str(row.get("reason") or "unknown"),
            "count": max(1, _as_int(row.get("count"))),
        }
        first_at_ms = _as_int(row.get("first_at_ms"))
        last_at_ms = _as_int(row.get("last_at_ms"))
        if first_at_ms:
            item["first_at_ms"] = first_at_ms
        if last_at_ms:
            item["last_at_ms"] = last_at_ms
        phase = str(row.get("phase") or "")
        if phase:
            item["phase"] = phase
        result.append(item)
    return sorted(
        result,
        key=lambda row: (
            -int(row.get("count") or 0),
            int(row.get("bot_guid") or 0),
            str(row.get("reason") or ""),
            int(row.get("spell_id") or 0),
        ),
    )


def _summarize_jev_candidate_rejections(rows: Any) -> list[dict[str, Any]]:
    """Group native gates for JEV without sending one row per spell/category."""
    if not isinstance(rows, list):
        return []
    grouped: dict[tuple[int, str, str], dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = (
            _as_int(row.get("bot_guid")),
            str(row.get("class_spec") or ""),
            str(row.get("reason") or "unknown"),
        )
        item = grouped.setdefault(
            key,
            {
                "bot_guid": key[0],
                "class_spec": key[1],
                "reason": key[2],
                "count": 0,
                "action_categories": set(),
                "spell_ids": set(),
            },
        )
        item["count"] += max(1, _as_int(row.get("count")))
        first_at_ms = _as_int(row.get("first_at_ms"))
        last_at_ms = _as_int(row.get("last_at_ms"))
        if first_at_ms:
            item["first_at_ms"] = min(
                first_at_ms,
                int(item.get("first_at_ms") or first_at_ms),
            )
        if last_at_ms:
            item["last_at_ms"] = max(int(item.get("last_at_ms") or 0), last_at_ms)
        action_category = str(row.get("action_category") or "unknown")
        item["action_categories"].add(action_category)
        spell_id = _as_int(row.get("spell_id"))
        if spell_id:
            item["spell_ids"].add(spell_id)
    important_reasons = {
        "movement_gate",
        "movement_requires_instant_action",
        "max_range_exceeded",
        "no_movement_blocked_lava_burst",
        "missing_required_self_aura",
        "missing_required_target_aura",
        "missing_required_owned_target_aura",
        "primary_power_gate",
    }
    by_actor: dict[int, list[dict[str, Any]]] = {}
    for item in grouped.values():
        by_actor.setdefault(int(item["bot_guid"]), []).append(item)
    result = []
    for actor_rows in by_actor.values():
        actor_rows.sort(key=lambda item: -int(item["count"]))
        selected = actor_rows[:12]
        selected_keys = {(item["bot_guid"], item["reason"]) for item in selected}
        selected.extend(
            item
            for item in actor_rows[12:]
            if item["reason"] in important_reasons
            and (item["bot_guid"], item["reason"]) not in selected_keys
        )
        for item in selected:
            summary = {
                "bot_guid": item["bot_guid"],
                "class_spec": item["class_spec"],
                "reason": item["reason"],
                "count": item["count"],
                "action_categories": sorted(item["action_categories"]),
                "spell_ids": sorted(item["spell_ids"])[:4],
            }
            if item.get("first_at_ms") and item.get("last_at_ms"):
                summary["first_at_ms"] = int(item["first_at_ms"])
                summary["last_at_ms"] = int(item["last_at_ms"])
            result.append(summary)
    return sorted(
        result,
        key=lambda row: (
            int(row.get("bot_guid") or 0),
            -int(row.get("count") or 0),
            str(row.get("reason") or ""),
        ),
    )


def _candidate_rejection_signal(rows: Any) -> dict[str, Any]:
    """Separate expected profile waits from candidate gates worth reviewing."""
    if not isinstance(rows, list):
        rows = []
    expected_rows: list[dict[str, Any]] = []
    mechanic_wait_rows: list[dict[str, Any]] = []
    non_failure_rows: list[dict[str, Any]] = []
    actionable_rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    expected_count = 0
    mechanic_wait_count = 0
    non_failure_count = 0
    actionable_count = 0
    for row in rows:
        if not isinstance(row, dict):
            continue
        reason = str(row.get("reason") or "unknown")
        count = max(1, _as_int(row.get("count")))
        reason_counts[reason] += count
        if reason in EXPECTED_PROFILE_WAIT_REASONS:
            expected_rows.append(row)
            expected_count += count
        elif reason in MECHANIC_WAIT_REASONS:
            mechanic_wait_rows.append(row)
            mechanic_wait_count += count
        elif reason in NON_FAILURE_PROFILE_GATE_REASONS:
            non_failure_rows.append(row)
            non_failure_count += count
        else:
            actionable_rows.append(row)
            actionable_count += count

    def reason_summary(selected: list[dict[str, Any]]) -> list[dict[str, Any]]:
        counts: Counter[str] = Counter()
        for row in selected:
            counts[str(row.get("reason") or "unknown")] += max(1, _as_int(row.get("count")))
        return [
            {"reason": reason, "count": count}
            for reason, count in sorted(counts.items(), key=lambda pair: (-pair[1], pair[0]))[:16]
        ]

    return {
        "interpretation": (
            "candidate_scan_counts_are_not_native_failures; expected waits and "
            "conditional profile gates must not be used as DPS loss without "
            "corroborating native outcomes"
        ),
        "candidate_scan_count": (
            expected_count
            + mechanic_wait_count
            + non_failure_count
            + actionable_count
        ),
        "expected_profile_wait_count": expected_count,
        "expected_profile_wait_reasons": reason_summary(expected_rows),
        "mechanic_wait_count": mechanic_wait_count,
        "mechanic_wait_reasons": reason_summary(mechanic_wait_rows),
        "non_failure_profile_gate_count": non_failure_count,
        "non_failure_profile_gate_reasons": reason_summary(non_failure_rows),
        "actionable_candidate_count": actionable_count,
        "actionable_candidate_reasons": reason_summary(actionable_rows),
        "actionable_candidate_groups": _summarize_jev_candidate_rejections(actionable_rows),
        "all_candidate_reasons": [
            {"reason": reason, "count": count}
            for reason, count in sorted(reason_counts.items(), key=lambda pair: (-pair[1], pair[0]))
        ],
    }


def _actor_loss_signals(
    metrics: dict[str, Any] | None,
    native_outcome_summary: list[dict[str, Any]],
    candidate_rows: list[dict[str, Any]],
    target_duty_context: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Build small, attributable loss budgets for each DPS actor.

    Jev should judge the semantic cause, but it should not have to reconstruct
    denominators or decide whether a candidate scan count is a failure.  This
    packet makes those deterministic facts explicit and includes contradictions
    so a large policy-gate count cannot manufacture a confident action.
    """
    if not isinstance(metrics, dict):
        return []
    summary_by_guid = {
        _as_int(row.get("bot_guid")): row
        for row in native_outcome_summary
        if isinstance(row, dict)
    }
    target_context_by_guid = {
        _as_int(row.get("bot_guid")): row
        for row in (target_duty_context or {}).get("actors", [])
        if isinstance(row, dict)
    }
    rows_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rows:
        if isinstance(row, dict):
            rows_by_guid[_as_int(row.get("bot_guid"))].append(row)

    def bucket_for(reason: str) -> str:
        if reason in MECHANIC_WAIT_REASONS:
            return "mechanic_wait"
        if reason in MOVEMENT_SIGNAL_REASONS:
            return "movement_or_range"
        # Target-aura, target-health, interruptibility, and purpose gates are
        # normal profile eligibility checks. They are not target-lease loss
        # unless a future native row emits an explicit churn/lease failure.
        if (
            reason in TARGET_SIGNAL_REASONS
            and reason not in EXPECTED_PROFILE_WAIT_REASONS
            and reason not in NON_FAILURE_PROFILE_GATE_REASONS
        ):
            return "targeting"
        if reason in PROFILE_POLICY_SIGNAL_REASONS:
            return "profile_policy"
        if reason in RESOURCE_SIGNAL_REASONS:
            return "resource_or_cooldown"
        if reason in EXPECTED_PROFILE_WAIT_REASONS:
            return "profile_wait"
        if reason in NON_FAILURE_PROFILE_GATE_REASONS:
            return "conditional_gate"
        return "other"

    actor_signals: list[dict[str, Any]] = []
    actors = metrics.get("actors")
    if not isinstance(actors, list):
        return []
    combat_seconds = max(1.0, _as_float(metrics.get("combat_duration_sec")))
    for actor in actors:
        if not isinstance(actor, dict) or str(actor.get("role") or "") != "dps":
            continue
        guid = _as_int(actor.get("bot_guid"))
        native = summary_by_guid.get(guid, {})
        outcome_counts = native.get("outcome_counts")
        outcome_counts = outcome_counts if isinstance(outcome_counts, dict) else {}
        outcome_count = max(0, _as_int(native.get("outcome_count")))
        failure_count = max(0, _as_int(native.get("actionable_failure_count")))
        failure_ratio = round(
            failure_count / max(1, outcome_count),
            6,
        )
        reason_counts: Counter[str] = Counter()
        bucket_counts: Counter[str] = Counter()
        for row in rows_by_guid.get(guid, []):
            reason = str(row.get("reason") or "unknown")
            count = max(1, _as_int(row.get("count")))
            reason_counts[reason] += count
            bucket_counts[bucket_for(reason)] += count

        active_seconds = max(0.0, _as_float(actor.get("active_seconds")))
        damage_uptime = _as_float(actor.get("damage_uptime"))
        moving_fraction = _as_float(actor.get("moving_fraction"))
        idle_fraction = round(max(0.0, 1.0 - damage_uptime), 6)
        wcl_observed = actor.get("wcl_observed_dps")
        combat_dps_value = actor.get("dps")
        active_dps = _as_float(actor.get("active_dps"))
        elapsed_dps = _as_float(actor.get("elapsed_dps"))
        window_dps_value = actor.get("wcl_window_dps")
        window_dps_basis = "wcl_window_dps"
        if not isinstance(window_dps_value, (int, float)):
            window_dps_value = actor.get("encounter_window_dps")
            window_dps_basis = "encounter_window_dps"
        if not isinstance(window_dps_value, (int, float)):
            # Reports captured before the explicit field was introduced use
            # `elapsed_dps` for damage over the encounter event window.
            window_dps_value = actor.get("elapsed_dps")
            window_dps_basis = "legacy_elapsed_dps"
        if not isinstance(window_dps_value, (int, float)):
            duration_seconds = max(1.0, _as_float(metrics.get("duration_sec")))
            damage = actor.get("damage")
            if isinstance(damage, (int, float)):
                window_dps_value = _as_float(damage) / duration_seconds
                window_dps_basis = "derived_damage_over_duration_sec"
        if isinstance(window_dps_value, (int, float)):
            encounter_dps = _as_float(window_dps_value)
        elif isinstance(combat_dps_value, (int, float)):
            # Minimal legacy/unit-test packets may contain only active-combat
            # DPS. Keep them readable, but mark the fallback so it cannot be
            # mistaken for a WCL-equivalent live measurement.
            encounter_dps = _as_float(combat_dps_value)
            window_dps_basis = "legacy_active_combat_fallback"
        else:
            encounter_dps = active_dps
            window_dps_basis = "legacy_active_actor_fallback"
        active_dps_gap = (
            isinstance(wcl_observed, (int, float))
            and active_dps < _as_float(wcl_observed) * 0.95
        )
        encounter_dps_gap = (
            isinstance(wcl_observed, (int, float))
            and encounter_dps < _as_float(wcl_observed) * 0.95
        )
        elapsed_dps_gap = (
            isinstance(wcl_observed, (int, float))
            and elapsed_dps < _as_float(wcl_observed) * 0.95
        )
        # WCL Summary DPS is damage over the selected encounter window.  The
        # local legacy `dps` field uses active-combat seconds and active_dps
        # uses actor damage-bearing seconds, so neither is the comparator.
        material_gap = encounter_dps_gap
        candidate_scan_count = sum(reason_counts.values())
        profile_policy_count = bucket_counts["profile_policy"]
        movement_count = bucket_counts["movement_or_range"]
        target_count = bucket_counts["targeting"]
        target_context = target_context_by_guid.get(guid, {})
        required_assignment_active = bool(
            target_context.get("required_assignment_active")
        )
        assignment_id = target_context.get("assignment_id")
        assignment_status = str(
            target_context.get("assignment_status") or "not_required"
        )
        duty_explains_idle = bool(target_context.get("duty_explains_idle"))
        counterfactual_status = str(
            target_context.get("counterfactual_status") or "unavailable"
        )
        causal_context_available = bool(
            (target_duty_context or {}).get("available") and target_context
        )
        candidates: list[dict[str, Any]] = []
        policy_hypotheses: list[dict[str, Any]] = []

        def add_candidate(
            action: str,
            evidence: list[str],
            contradictions: list[str],
            strength: str,
        ) -> None:
            candidates.append({
                "action": action,
                "evidence": evidence,
                "contradictions": contradictions,
                "evidence_strength": strength,
            })

        if required_assignment_active and assignment_status == "incomplete":
            add_candidate(
                "encounter_assignment",
                [
                    "required_assignment_observed",
                    "required_assignment_landed_cycle_incomplete",
                ],
                ["rotation_and_movement_are_not_counterfactual_clean"],
                "direct_assignment",
            )
        if failure_ratio >= 0.10:
            add_candidate(
                "shared_arbitration",
                ["native_actionable_failure_rate_material"],
                [],
                "direct_native",
            )
        movement_direct = (
            (moving_fraction >= 0.08 and damage_uptime < 0.80)
            or (movement_count >= 20 and moving_fraction >= 0.05)
        )
        if (
            (material_gap and movement_direct)
            or (not isinstance(wcl_observed, (int, float)) and moving_fraction >= 0.15 and damage_uptime < 0.80)
        ) and not duty_explains_idle and not required_assignment_active:
            add_candidate(
                "movement_recovery",
                [
                    key
                    for key, enabled in (
                        ("moving_fraction_material", moving_fraction >= 0.08),
                        ("movement_or_range_gates_observed", movement_count >= 20),
                        ("ranged_idle_window", damage_uptime < 0.80),
                    )
                    if enabled
                ],
                ["moving_fraction_low"] if moving_fraction < 0.05 else [],
                "attributable_movement",
            )
        if (
            idle_fraction >= 0.25
            and moving_fraction < 0.08
            and failure_ratio < 0.05
            and (material_gap or not isinstance(wcl_observed, (int, float)))
            and not duty_explains_idle
            and not required_assignment_active
            and (
                not causal_context_available
                or counterfactual_status == "eligible"
            )
        ):
            add_candidate(
                "uptime_cadence",
                [
                    "idle_fraction_material",
                    "moving_fraction_low",
                    "native_failure_rate_low",
                ],
                [],
                "attributable_idle",
            )
        if (
            active_dps_gap
            and encounter_dps_gap
            and not required_assignment_active
            and profile_policy_count >= max(100, int(candidate_scan_count * 0.03))
        ):
            policy_hypotheses.append({
                "action": "rotation_profile",
                "evidence": [
                    "profile_policy_gate_volume_material",
                    "active_dps_below_wcl_context",
                ],
                "caveat": "policy gates are not native failures; require a targeted counterfactual canary",
                "evidence_strength": "profile_hypothesis",
            })
        if material_gap and target_count >= 20 and not required_assignment_active:
            add_candidate(
                "target_lease",
                ["target_gate_volume_material"],
                [],
                "attributable_targeting",
            )
        if not candidates:
            evidence = ["no_single_causal_signal_clears_the_screen"]
            contradictions: list[str] = []
            if duty_explains_idle:
                evidence.append("required_target_duty_overlaps_loss_window")
                contradictions.append("idle_or_movement_is_not_counterfactual_clean")
            if required_assignment_active:
                evidence.append(
                    f"required_assignment_active:{assignment_id or 'unknown'}"
                )
                if assignment_status == "unobserved":
                    evidence.append("required_assignment_not_observed")
                elif assignment_status == "identity_assigned":
                    evidence.append("required_assignment_execution_unobserved")
                contradictions.append("assignment_control_is_not_counterfactual_clean")
            if causal_context_available and counterfactual_status != "eligible":
                evidence.append("counterfactual_context_is_partial_or_unavailable")
                contradictions.append("target_or_movement_capture_is_incomplete")
            candidates.append({
                "action": "collect_more_canaries",
                "evidence": evidence,
                "contradictions": contradictions,
                "evidence_strength": "insufficient",
            })

        top_abilities = []
        abilities = actor.get("abilities")
        if isinstance(abilities, list):
            for ability in abilities[:8]:
                if not isinstance(ability, dict):
                    continue
                top_abilities.append({
                    key: ability[key]
                    for key in ("spell_id", "spell_name", "events", "damage_share")
                    if key in ability
                })
        actor_signals.append({
            "bot_guid": guid,
            "class_spec": str(actor.get("class_spec") or ""),
            "encounter_dps": encounter_dps,
            "encounter_dps_basis": window_dps_basis,
            "combat_dps": _as_float(combat_dps_value),
            "active_dps": active_dps,
            "elapsed_dps": _as_float(actor.get("elapsed_dps")),
            "wcl_window_dps": encounter_dps,
            "wcl_observed_dps": wcl_observed,
            "dps_delta_vs_wcl": actor.get("dps_delta_vs_wcl"),
            "active_dps_delta_vs_wcl": actor.get("active_dps_delta_vs_wcl"),
            "elapsed_dps_delta_vs_wcl": actor.get("elapsed_dps_delta_vs_wcl"),
            "encounter_dps_gap_vs_wcl": encounter_dps_gap,
            "wcl_window_dps_gap_vs_wcl": encounter_dps_gap,
            "active_dps_gap_vs_wcl": active_dps_gap,
            "elapsed_dps_gap_vs_wcl": elapsed_dps_gap,
            "wall_clock_dps_gap_vs_wcl": elapsed_dps_gap,
            "combat_seconds": round(combat_seconds, 3),
            "active_seconds": round(active_seconds, 3),
            "damage_uptime": damage_uptime,
            "idle_fraction": idle_fraction,
            "moving_fraction": moving_fraction,
            "distance_avg": actor.get("distance_avg"),
            "native_outcome_count": outcome_count,
            "native_actionable_failure_count": failure_count,
            "native_actionable_failure_ratio": failure_ratio,
            "native_outcome_counts": dict(sorted(outcome_counts.items())),
            "duty_explains_idle": duty_explains_idle,
            "required_assignment_active": required_assignment_active,
            "assignment_id": assignment_id,
            "assignment_status": assignment_status,
            "assignment_counterfactual_status": str(
                target_context.get("assignment_counterfactual_status") or "eligible"
            ),
            "assignment_detonation_count": _as_int(
                target_context.get("assignment_detonation_count")
            ),
            "assignment_placement_decision_count": _as_int(
                target_context.get("assignment_placement_decision_count")
            ),
            "assignment_placement_failure_count": _as_int(
                target_context.get("assignment_placement_failure_count")
            ),
            "assignment_damage_event_count": _as_int(
                target_context.get("assignment_damage_event_count")
            ),
            "assignment_landed_damage": _as_float(
                target_context.get("assignment_landed_damage")
            ),
            "mechanic_duty_scope": str(
                target_context.get("mechanic_duty_scope") or "unknown"
            ),
            "mechanic_target_originated_damage_share": _as_float(
                target_context.get("mechanic_target_originated_damage_share")
            ),
            "duty_moving_damage_event_fraction": _as_float(
                target_context.get("duty_moving_damage_event_fraction")
            ),
            "damage_cadence_capture": str(
                target_context.get("damage_cadence_capture") or "unavailable"
            ),
            "damage_gap_max_seconds": target_context.get("damage_gap_max_seconds"),
            "damage_gap_count_ge_3_seconds": target_context.get("damage_gap_count_ge_3_seconds"),
            "damage_gap_count_ge_5_seconds": target_context.get("damage_gap_count_ge_5_seconds"),
            "damage_gap_seconds_ge_3_total": target_context.get("damage_gap_seconds_ge_3_total"),
            "counterfactual_status": counterfactual_status,
            "candidate_scan_count": candidate_scan_count,
            "candidate_gate_counts": dict(sorted(bucket_counts.items())),
            "top_candidate_reasons": [
                {"reason": reason, "count": count}
                for reason, count in reason_counts.most_common(8)
            ],
            "top_abilities": top_abilities,
            "sample_quality": {
                "enough_native_outcomes": outcome_count >= 30,
                "enough_damage_window": active_seconds >= 30,
                "wcl_is_context_only": True,
            },
            "candidate_actions": candidates,
            "policy_hypotheses": policy_hypotheses,
        })
    return sorted(actor_signals, key=lambda row: int(row.get("bot_guid") or 0))


def _compact_metrics(
    metrics: Any,
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
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
            "combat_duration_sec",
            "duration_sec",
            "capture_first_at_ms",
            "capture_last_at_ms",
            "capture_duration_sec",
            "encounter_window_boundary_basis",
            "elapsed_party_dps",
            "elapsed_party_hps",
            "encounter_window_party_dps",
            "encounter_window_party_dps_basis",
            "active_party_damage_seconds",
            "originated_damage_seconds",
            "raw_event_damage",
            "raw_event_dps",
            "route_generation",
            "route_node_id",
            "first_at_ms",
            "last_at_ms",
            "action_outcome_count",
            "candidate_rejection_count",
        )
        if key in metrics
    }
    actors = metrics.get("actors")
    if isinstance(actors, list):
        result["actors"] = [
            _compact_actor(actor, actor_identity)
            for actor in actors
            if isinstance(actor, dict)
        ]
    if isinstance(metrics.get("action_outcomes"), list):
        result["action_outcomes"] = _compact_native_action_outcomes(
            metrics["action_outcomes"], actor_identity
        )
        result["action_outcome_count"] = len(result["action_outcomes"])
    if isinstance(metrics.get("candidate_rejections"), list):
        result["candidate_rejections"] = _compact_native_candidate_rejections(
            metrics["candidate_rejections"], actor_identity
        )
        result["candidate_rejection_count"] = len(result["candidate_rejections"])
    if "party_dps" in result:
        result["party_dps_basis"] = "active_damage_seconds"
    if "elapsed_party_dps" in result:
        # `elapsed_*` is a legacy name for the selected encounter event
        # window.  It is not the route's entrance-to-kill wall clock.
        result["elapsed_party_dps_basis"] = "encounter_event_window_seconds"
    if "encounter_window_party_dps" in result:
        result["encounter_window_party_dps_basis"] = result.get(
            "encounter_window_party_dps_basis",
            "originated_damage_over_duration_sec",
        )
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
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
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
        for key in (
            "route_terminal_evidence",
            "manifest_completion_evidence",
            "real_boss_kill_evidence",
            "boss_death_evidence",
        ):
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
            compact = _compact_metrics(payload["combat_metrics"], actor_identity)
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


def _analysis_metrics(
    analysis: Any,
    scope_route_prefix: str,
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(analysis, dict):
        return None
    extracted = analysis.get("combat_metrics") or analysis.get("metrics")
    if isinstance(extracted, dict):
        route = str(extracted.get("route_node_id") or "")
        if (not route or _route_in_scope(route, scope_route_prefix)) and (
            extracted.get("available") or "party_dps" in extracted
        ):
            return _compact_metrics(extracted, actor_identity)
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
    return _compact_metrics(metrics, actor_identity)


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


def _compact_action_outcomes(
    entries: Iterable[dict[str, Any]],
    scope_route_prefix: str,
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
    focus_roles: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Aggregate attributable action outcomes without retaining raw trace text."""
    counts: Counter[tuple[str, str, str, str, str, str, str]] = Counter()
    names: dict[tuple[str, str, str, str, str, str, str], str] = {}
    for entry in entries:
        route = str(entry.get("route_node_id") or "")
        if not _route_in_scope(route, scope_route_prefix):
            continue
        attempt = entry.get("combat_attempt")
        attempt = attempt if isinstance(attempt, dict) else {}
        action = attempt.get("action")
        action = action if isinstance(action, dict) else {}
        has_outcome = bool(attempt) or any(
            key in entry
            for key in (
                "action_result",
                "candidate_result",
                "native_action_result",
                "action_rejection_reason",
                "result",
                "outcome_reason",
            )
        )
        if not has_outcome:
            continue
        guid = _as_int(entry.get("_bot_guid") or entry.get("bot_guid"))
        identity = (actor_identity or {}).get(str(guid), {})
        role = str(identity.get("role") or entry.get("role") or "")
        if focus_roles and role and role not in focus_roles:
            continue
        spec = str(identity.get("class_spec") or entry.get("class_spec") or "")
        category = str(
            action.get("action_category")
            or attempt.get("action_category")
            or entry.get("action_category")
            or action.get("action_type")
            or attempt.get("action_type")
            or entry.get("action")
            or entry.get("reason_type")
            or "unknown"
        )
        spell_id = _as_int(
            action.get("spell_id")
            or attempt.get("spell_id")
            or entry.get("spell_id")
        )
        action_name = str(
            action.get("spell_name")
            or action.get("debug_name")
            or attempt.get("debug_name")
            or entry.get("spell_name")
            or category
        )
        outcome = str(
            action.get("result")
            or attempt.get("result")
            or entry.get("action_result")
            or entry.get("candidate_result")
            or entry.get("native_action_result")
            or entry.get("result")
            or "unknown"
        )
        reason = str(
            action.get("reason_code")
            or attempt.get("reason_code")
            or entry.get("action_rejection_reason")
            or entry.get("reason_code")
            or entry.get("outcome_reason")
            or ""
        )
        key = (
            str(guid),
            spec,
            route,
            category,
            str(spell_id) if spell_id else "",
            outcome,
            reason,
        )
        counts[key] += max(1, _as_int(entry.get("_outcome_count")))
        names[key] = action_name
    result: list[dict[str, Any]] = []
    for key, count in counts.most_common(100):
        guid, spec, route, category, spell_id, outcome, reason = key
        item = {
            "bot_guid": _as_int(guid),
            "class_spec": spec,
            "route_node_id": route,
            "action_category": category,
            "outcome": outcome,
            "count": count,
            "action_name": names[key],
        }
        if spell_id:
            item["spell_id"] = _as_int(spell_id)
        if reason:
            item["reason_code"] = reason
        result.append(item)
    return result


def _compact_decision_receipts(
    report: dict[str, Any] | None,
    scope_route_prefix: str,
    actor_identity: Mapping[str, dict[str, Any]] | None = None,
    focus_roles: set[str] | None = None,
    *,
    window_start_ms: int = 0,
    window_end_ms: int = 0,
    terminal_at_ms: int = 0,
) -> list[dict[str, Any]]:
    """Summarize live decision receipts when they contain native outcomes."""
    if not isinstance(report, dict) or not isinstance(report.get("decision_receipts"), list):
        return []
    entries: list[dict[str, Any]] = []
    for receipt in report["decision_receipts"]:
        if not isinstance(receipt, dict):
            continue
        entry = dict(receipt)
        route = str(entry.get("route_node_id") or entry.get("route") or "")
        if route:
            entry["route_node_id"] = route
        first_timestamp = _as_int(
            entry.get("first_timestamp_ms") or entry.get("timestamp_ms")
        )
        last_timestamp = _as_int(
            entry.get("last_timestamp_ms") or entry.get("timestamp_ms") or first_timestamp
        )
        if terminal_at_ms and first_timestamp and first_timestamp > terminal_at_ms:
            continue
        if window_end_ms and first_timestamp and first_timestamp > window_end_ms:
            continue
        if window_start_ms and last_timestamp and last_timestamp < window_start_ms:
            continue
        if "bot_guid" in entry or "actor_guid" in entry:
            entry["_bot_guid"] = _as_int(
                entry.get("bot_guid") or entry.get("actor_guid")
            )
        if "count" in entry:
            entry["_outcome_count"] = max(1, _as_int(entry.get("count")))
        entry["action_result"] = entry.get("result") or "unknown"
        entry["action_rejection_reason"] = entry.get("outcome_reason") or ""
        entry["action_category"] = entry.get("reason_type") or entry.get("gate") or "decision"
        entry["action"] = entry.get("reason") or entry.get("action_category") or "decision"
        entry["reason_code"] = entry.get("outcome_reason") or ""
        attempt = entry.get("attempt") or entry.get("combat_attempt")
        if isinstance(attempt, dict):
            entry["combat_attempt"] = attempt
        entries.append(entry)
    return _compact_action_outcomes(
        entries,
        scope_route_prefix,
        actor_identity,
        focus_roles,
    )


def _entry_timestamp_ms(entry: dict[str, Any]) -> int:
    attempt = entry.get("combat_attempt")
    attempt = attempt if isinstance(attempt, dict) else {}
    return max(
        _as_int(entry.get("timestamp_ms")),
        _as_int(entry.get("recorded_at_ms")),
        _as_int(attempt.get("recorded_at_ms")),
    )


def _entry_outcome_tokens(entry: dict[str, Any]) -> list[str]:
    attempt = entry.get("combat_attempt")
    attempt = attempt if isinstance(attempt, dict) else {}
    failure = attempt.get("failure")
    failure = failure if isinstance(failure, dict) else {}
    values = (
        entry.get("reason_code"),
        entry.get("action_rejection_reason"),
        entry.get("action_result"),
        entry.get("candidate_result"),
        entry.get("native_action_result"),
        entry.get("result"),
        entry.get("outcome_reason"),
        failure.get("reason"),
        failure.get("retry_reason"),
    )
    return [str(value) for value in values if value not in (None, "")]


def _boss_trace_window(
    entries: list[dict[str, Any]],
    metrics: dict[str, Any] | None,
    scope_route_prefix: str = DEFAULT_BOSS_ROUTE[0],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Restrict retained trace rows to the active boss window.

    Closed reports retain only a tail of the native trace.  The combat analysis
    supplies the full encounter timestamps, while the explicit boss-killed row
    marks the point after which callback and teardown rows must not influence a
    DPS judgment.
    """
    scoped = [
        entry
        for entry in entries
        if _route_in_scope(str(entry.get("route_node_id") or ""), scope_route_prefix)
    ]
    metric_start = _as_int((metrics or {}).get("first_at_ms"))
    metric_end = _as_int((metrics or {}).get("last_at_ms"))
    timestamps = [_entry_timestamp_ms(entry) for entry in scoped]
    observed_start = min((value for value in timestamps if value), default=0)
    observed_end = max((value for value in timestamps if value), default=0)
    terminal_actions = {
        "boss_killed",
        "validation_route_terminal",
        "validation_route_manifest_complete",
    }
    terminal_timestamps = [
        _entry_timestamp_ms(entry)
        for entry in scoped
        if str(entry.get("action") or "") in terminal_actions
        and _entry_timestamp_ms(entry)
    ]
    terminal_at = min(terminal_timestamps, default=0)
    window_start = metric_start or observed_start
    window_end = metric_end or observed_end
    if terminal_at:
        window_end = min(value for value in (window_end, terminal_at) if value)

    in_window: list[dict[str, Any]] = []
    excluded_after_terminal = 0
    excluded_outside_window = 0
    excluded_terminal_rows = 0
    excluded_teardown_reasons: Counter[str] = Counter()
    for entry in scoped:
        timestamp = _entry_timestamp_ms(entry)
        if timestamp and not (window_start <= timestamp <= window_end):
            if terminal_at and timestamp > terminal_at:
                excluded_after_terminal += 1
            else:
                excluded_outside_window += 1
            continue
        if str(entry.get("action") or "") in terminal_actions:
            excluded_terminal_rows += 1
            continue
        tokens = _entry_outcome_tokens(entry)
        teardown = [token for token in tokens if "callback_instance_unavailable" in token]
        if teardown:
            for token in teardown:
                excluded_teardown_reasons[token] += 1
            continue
        in_window.append(entry)

    capture = {
        "combat_window_start_ms": window_start or None,
        "combat_window_end_ms": window_end or None,
        "combat_metrics_window_available": bool(metric_start and metric_end),
        "terminal_at_ms": terminal_at or None,
        "retained_trace_first_ms": observed_start or None,
        "retained_trace_last_ms": observed_end or None,
        "retained_trace_rows": len(scoped),
        "trace_rows_in_window": len(in_window),
        "trace_is_retained_tail": bool(
            metric_start and observed_start and observed_start > metric_start
        ),
        "excluded_after_terminal_rows": excluded_after_terminal,
        "excluded_outside_window_rows": excluded_outside_window,
        "excluded_terminal_rows": excluded_terminal_rows,
        "excluded_teardown_reason_counts": dict(sorted(excluded_teardown_reasons.items())),
        "interpretation": (
            "retained_trace_is_tail_capture; missing action outcomes are not proof "
            "of no rejection"
        ),
    }
    return in_window, capture


def _compact_wcl_reference(data: Any) -> dict[str, Any] | None:
    if not isinstance(data, dict):
        return None
    references = data.get("references")
    if not isinstance(references, list):
        return None
    compact: list[dict[str, Any]] = []
    for reference in references[:3]:
        if not isinstance(reference, dict):
            continue
        item = {
            key: reference[key]
            for key in (
                "id",
                "url",
                "mode",
                "duration_sec",
                "raid_dps",
                "average_item_level",
                "target_scope",
                "reference_class",
                "limitations",
            )
            if key in reference
        }
        actor_dps = reference.get("actor_dps")
        if isinstance(actor_dps, dict):
            item["actor_dps"] = {
                str(key): _as_float(value)
                for key, value in actor_dps.items()
                if isinstance(value, (int, float))
            }
        compact.append(item)
    if not compact:
        return None
    return {
        "schema": data.get("schema", "magmaw_wcl_dps_reference_v1"),
        "primary": compact[0],
        "supplemental": compact[1:],
    }


def _annotate_wcl_deltas(
    metrics: dict[str, Any] | None,
    reference: dict[str, Any] | None,
) -> dict[str, Any] | None:
    if not isinstance(metrics, dict):
        return metrics
    result = json.loads(json.dumps(metrics))
    primary = reference.get("primary") if isinstance(reference, dict) else None
    actor_dps = primary.get("actor_dps") if isinstance(primary, dict) else None
    if not isinstance(actor_dps, dict):
        return result
    for actor in result.get("actors", []):
        if not isinstance(actor, dict):
            continue
        spec = str(actor.get("class_spec") or "")
        observed = actor_dps.get(spec)
        if not isinstance(observed, (int, float)):
            continue
        actor["wcl_observed_dps"] = observed
        elapsed = actor.get("elapsed_dps")
        active = actor.get("active_dps")
        encounter_window = actor.get("encounter_window_dps")
        if not isinstance(encounter_window, (int, float)):
            # Pre-contract reports already carried this arithmetic under
            # `elapsed_dps`. Keep those reports replayable while exposing the
            # WCL denominator explicitly for new evidence.
            encounter_window = elapsed
        if isinstance(encounter_window, (int, float)):
            actor["wcl_window_dps"] = float(encounter_window)
            actor["wcl_window_dps_basis"] = (
                "originated_damage_over_duration_sec"
            )
            actor["wcl_window_dps_delta_vs_wcl"] = (
                float(encounter_window) - float(observed)
            )
            actor["wcl_window_dps_gap_vs_wcl"] = (
                float(encounter_window) < float(observed) * 0.95
            )
        if isinstance(elapsed, (int, float)):
            actor["elapsed_dps_delta_vs_wcl"] = float(elapsed) - float(observed)
        if isinstance(active, (int, float)):
            actor["active_dps_delta_vs_wcl"] = float(active) - float(observed)
        combat = actor.get("dps")
        if isinstance(combat, (int, float)):
            actor["dps_delta_vs_wcl"] = float(combat) - float(observed)
    return result


def _compact_actor_identity(
    actor_identity: Mapping[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for guid, identity in sorted((actor_identity or {}).items(), key=lambda item: _as_int(item[0])):
        item = {"bot_guid": _as_int(guid)}
        for key in ("bot_name", "role", "class_spec", "class_name"):
            if identity.get(key) not in (None, ""):
                item[key] = identity[key]
        result.append(item)
    return result


def _dps_review_metrics(
    metrics: dict[str, Any] | None,
    wcl_reference: dict[str, Any] | None,
) -> dict[str, Any]:
    annotated = _annotate_wcl_deltas(metrics, wcl_reference)
    if not isinstance(annotated, dict):
        return {"available": False, "actor_scope": "dps_only"}
    result = dict(annotated)
    # The authoritative ledger is sent once as boss_dps_review.action_outcomes.
    # Keeping it nested under combat_metrics doubled the JEV request without
    # adding evidence.
    result.pop("action_outcomes", None)
    result.pop("candidate_rejections", None)
    actors = annotated.get("actors")
    dps_actors: list[dict[str, Any]] = []
    support_actors: list[dict[str, Any]] = []
    if isinstance(actors, list):
        for actor in actors:
            if not isinstance(actor, dict):
                continue
            if str(actor.get("role") or "") == "dps":
                dps_actors.append(actor)
                continue
            support = {
                key: actor[key]
                for key in (
                    "bot_guid",
                    "bot_name",
                    "class_spec",
                    "role",
                    "damage",
                    "dps",
                    "active_dps",
                    "elapsed_dps",
                    "encounter_window_dps",
                    "wcl_window_dps",
                    "active_seconds",
                    "damage_uptime",
                    "wcl_observed_dps",
                    "dps_delta_vs_wcl",
                    "wcl_window_dps_delta_vs_wcl",
                    "elapsed_dps_delta_vs_wcl",
                )
                if key in actor
            }
            support_actors.append(support)
    result["actors"] = dps_actors
    result["support_actors"] = support_actors
    result["actor_scope"] = "dps_only"
    return result


def _jev_combat_metrics(metrics: dict[str, Any]) -> dict[str, Any]:
    """Remove repeated ability detail already present in actor_loss_signals."""
    result = {
        key: value
        for key, value in metrics.items()
        if key not in {"actors", "support_actors"}
    }
    compact_actors: list[dict[str, Any]] = []
    for actor in metrics.get("actors", []):
        if not isinstance(actor, dict):
            continue
        compact_actors.append({
            key: actor[key]
            for key in (
                "bot_guid",
                "bot_name",
                "class_spec",
                "role",
                "damage",
                "dps",
                "active_dps",
                "elapsed_dps",
                "encounter_window_dps",
                "wcl_window_dps",
                "active_seconds",
                "damage_uptime",
                "distance_avg",
                "moving_fraction",
                "wcl_observed_dps",
                "dps_delta_vs_wcl",
                "wcl_window_dps_delta_vs_wcl",
                "wcl_window_dps_gap_vs_wcl",
                "active_dps_delta_vs_wcl",
                "elapsed_dps_delta_vs_wcl",
                "cast_movement_seconds",
                "range_seconds",
            )
            if key in actor
        })
    result["actors"] = compact_actors
    result["actor_scope"] = "dps_only"
    return result


def _dps_diagnostics(
    diagnostics: list[dict[str, Any]],
    actor_identity: Mapping[str, dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for diagnostic in diagnostics:
        guid = _as_int(diagnostic.get("actor_guid"))
        role = (actor_identity or {}).get(str(guid), {}).get("role")
        if role and role != "dps":
            continue
        result.append(diagnostic)
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
    actors = metrics.get("actors", [])
    compact_actors = []
    if isinstance(actors, list):
        for actor in actors:
            if not isinstance(actor, dict):
                continue
            compact_actors.append(
                {
                    key: actor[key]
                    for key in (
                        "bot_guid",
                        "bot_name",
                        "class_spec",
                        "role",
                        "damage",
                        "dps",
                        "active_dps",
                        "elapsed_dps",
                        "active_seconds",
                        "damage_uptime",
                        "distance_avg",
                        "moving_fraction",
                    )
                    if key in actor
                }
            )
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
        "elapsed_party_dps": metrics.get("elapsed_party_dps"),
        "combat_seconds": metrics.get("combat_seconds"),
        "duration_sec": metrics.get("duration_sec"),
        "actors": compact_actors,
    }


def _compact_run_gate(report: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(report, dict):
        return {}
    result = {
        key: report[key]
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
        )
        if key in report
    }
    result["native_gameplay_outcome"] = _native_gameplay_outcome(report)
    context = report.get("validation_context")
    if isinstance(context, dict):
        result["validation_context"] = {
            key: context[key]
            for key in (
                "scenario_id",
                "segment_id",
                "route_node_id",
                "route_kind",
                "route_generation",
            )
            if key in context
        }
    evidence = report.get("evidence")
    if isinstance(evidence, dict):
        compact = _compact_evidence(evidence)
        result["route_terminal_evidence"] = compact.get("route_terminal_evidence", [])
        result["manifest_completion_evidence"] = compact.get(
            "manifest_completion_evidence", []
        )
        result["real_boss_kill_evidence"] = compact.get(
            "real_boss_kill_evidence", []
        )
    validation_route = report.get("validation_route")
    if not isinstance(validation_route, dict):
        report_status = report.get("status")
        validation_route = (
            report_status.get("validation_route")
            if isinstance(report_status, dict)
            else None
        )
    if isinstance(validation_route, dict):
        result["boss_death_evidence"] = _compact_route_evidence(
            validation_route.get("boss_death_evidence")
        )
    return result


def _route_review(
    deterministic: dict[str, Any],
    expected_route: tuple[str, ...],
    live_report: dict[str, Any] | None,
) -> dict[str, Any]:
    historical = []
    for record in deterministic.get("stuck_behaviors", []):
        if not isinstance(record, dict):
            continue
        historical.append({
            "behavior": record.get("behavior"),
            "path": record.get("path"),
            "count": record.get("count", 0),
            "bot_count": len(record.get("bot_guids", [])),
        })
    historical.sort(key=lambda item: (-_as_int(item.get("count")), str(item.get("behavior"))))
    return {
        "expected_route_nodes": list(expected_route),
        "scope_route_prefix": deterministic.get("scope_route_prefix"),
        "trace_rows": deterministic.get("trace_rows"),
        "magmaw_trace_rows": deterministic.get("magmaw_trace_rows"),
        "bot_guids": deterministic.get("bot_guids", []),
        "duration_seconds": deterministic.get("duration_seconds"),
        "route_status": deterministic.get("route_status"),
        "route_acceptance": {
            "complete_native_terminal_evidence": not deterministic.get("route_missing_expected")
            and all(
                node in deterministic.get("route_terminal_nodes", [])
                for node in expected_route
            ),
            "observed_order_monotonic": not deterministic.get("route_unexpected")
            and not deterministic.get("route_repeated_nodes"),
        },
        "route_nodes_observed": deterministic.get("route_nodes_observed", []),
        "route_terminal_nodes": deterministic.get("route_terminal_nodes", []),
        "route_generation_sequence": deterministic.get("route_generation_sequence", []),
        "route_terminal_generations": deterministic.get("route_terminal_generations", {}),
        "route_missing_expected": deterministic.get("route_missing_expected", []),
        "route_unexpected": deterministic.get("route_unexpected", []),
        "route_repeated_nodes": deterministic.get("route_repeated_nodes", []),
        "path_counts": deterministic.get("path_counts", {}),
        "path_transitions": deterministic.get("path_transitions", {}),
        "bot_path_counts": deterministic.get("bot_path_counts", {}),
        "active_route_generation": deterministic.get("active_route_generation"),
        "active_route_node_id": deterministic.get("active_route_node_id"),
        "stuck_behavior_counts": deterministic.get("stuck_behavior_counts", {}),
        "historical_stuck_behavior_summary": historical[:12],
        "active_stuck_behavior_counts": deterministic.get(
            "active_stuck_behavior_counts", {}
        ),
        "active_stuck_behaviors": deterministic.get("active_stuck_behaviors", []),
        "resolved_stuck_behavior_counts": deterministic.get(
            "resolved_stuck_behavior_counts", {}
        ),
        "diagnosis_codes": deterministic.get("diagnosis_codes", {}),
        "transfer_lane_outcomes": deterministic.get("transfer_lane_outcomes", {}),
        "run_gate": _compact_run_gate(live_report),
    }


def _compact_timeline_comparison(value: Any) -> dict[str, Any] | None:
    """Keep the all-actor timeline signal small enough for the JEV request."""
    if not isinstance(value, dict):
        return None
    compact_actors: list[dict[str, Any]] = []
    for actor in value.get("actors", []):
        if not isinstance(actor, dict):
            continue
        wcl = actor.get("wcl")
        wcl = wcl if isinstance(wcl, dict) else None
        bot = actor.get("bot")
        bot = bot if isinstance(bot, dict) else {}
        diffs = [
            row
            for row in actor.get("ability_diffs", [])
            if isinstance(row, dict)
        ]
        matched_diffs = [
            row
            for row in diffs
            if _as_int(row.get("wcl_completed_casts")) > 0
            and _as_int(row.get("bot_landed_damage_events")) > 0
        ][:10]
        wcl_only = [
            {
                "ability": row.get("ability"),
                "wcl_completed_casts": _as_int(row.get("wcl_completed_casts")),
            }
            for row in diffs
            if _as_int(row.get("wcl_completed_casts")) > 0
            and _as_int(row.get("bot_landed_damage_events")) == 0
        ][:8]
        bot_only = [
            {
                "ability": row.get("ability"),
                "bot_landed_damage_events": _as_int(
                    row.get("bot_landed_damage_events")
                ),
            }
            for row in diffs
            if _as_int(row.get("wcl_completed_casts")) == 0
            and _as_int(row.get("bot_landed_damage_events")) > 0
        ][:8]
        compact_actors.append({
            key: actor[key]
            for key in (
                "bot_guid",
                "bot_name",
                "role",
                "class_spec",
                "comparison_status",
                "bot_event_input_status",
                "reference_actor_id",
                "reference_source_name",
                "reference_reuse_index",
                "reference_reused_for_duplicate_local_actor",
                "wcl_observed_dps",
                "wcl_observed_dps_window_sec",
                "wcl_common_window_dps",
                "dps_comparison_status",
                "bot_encounter_window_dps",
                "bot_native_encounter_window_dps",
                "bot_common_window_damage",
                "bot_common_window_dps",
                "bot_common_window_dps_basis",
                "bot_active_dps",
                "bot_damage_uptime",
                "bot_moving_fraction",
                "bot_active_seconds",
                "bot_damage",
            )
            if key in actor
        })
        compact_actors[-1]["wcl_completed_cast_cadence"] = (
            wcl.get("cadence") if wcl else None
        )
        compact_actors[-1]["bot_landed_damage_cadence"] = bot.get("cadence")
        compact_actors[-1]["bot_direct_or_unknown_cadence"] = bot.get(
            "direct_or_unknown_cadence"
        )
        for field in ("owner_direct_cadence", "owner_unknown_cadence", "damage_classification_counts", "gap_basis", "event_input_status"):
            compact_actors[-1][field] = bot.get(field)
        compact_actors[-1]["bot_largest_direct_gaps"] = (
            bot.get("largest_gaps", [])[:6]
            if isinstance(bot.get("largest_gaps"), list)
            else []
        )
        compact_actors[-1]["matched_ability_diffs"] = matched_diffs
        compact_actors[-1]["wcl_only_abilities"] = wcl_only
        compact_actors[-1]["bot_only_abilities"] = bot_only
        compact_actors[-1]["comparison_limitations"] = list(
            actor.get("comparison_limitations", [])
        )[:4]
    return {
        key: value[key]
        for key in (
            "schema",
            "reference",
            "scope",
            "comparison_window",
            "bot_run",
            "bot_event_input",
            "signal_contract",
        )
        if key in value
    } | {"actors": compact_actors}


def _timeline_actor_signal(
    timeline_comparison: dict[str, Any] | None,
) -> dict[int, dict[str, Any]]:
    """Build small per-actor timeline facts for the causal actor questions."""
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(timeline_comparison, dict):
        return result
    for actor in timeline_comparison.get("actors", []):
        if not isinstance(actor, dict):
            continue
        guid = _as_int(actor.get("bot_guid"))
        if not guid:
            continue
        wcl = actor.get("wcl_completed_cast_cadence")
        wcl = wcl if isinstance(wcl, dict) else {}
        bot = actor.get("bot_landed_damage_cadence")
        bot = bot if isinstance(bot, dict) else {}
        direct = actor.get("bot_direct_or_unknown_cadence")
        direct = direct if isinstance(direct, dict) else {}
        gaps = actor.get("bot_largest_direct_gaps")
        gaps = gaps if isinstance(gaps, list) else []
        diffs = actor.get("matched_ability_diffs")
        diffs = diffs if isinstance(diffs, list) else []
        wcl_only = actor.get("wcl_only_abilities")
        wcl_only = wcl_only if isinstance(wcl_only, list) else []
        bot_only = actor.get("bot_only_abilities")
        bot_only = bot_only if isinstance(bot_only, list) else []
        wcl_dps = actor.get("wcl_common_window_dps")
        common_dps = actor.get("bot_common_window_dps")
        denominator_matched_delta = None
        denominator_matched_ratio = None
        if actor.get("dps_comparison_status") == "timestamped_common_window" and isinstance(wcl_dps, (int, float)) and isinstance(common_dps, (int, float)):
            denominator_matched_delta = round(float(common_dps) - float(wcl_dps), 3)
            denominator_matched_ratio = round(
                float(common_dps) / max(1.0, float(wcl_dps)),
                6,
            )
        result[guid] = {
            "comparison_status": actor.get("comparison_status"),
            "reference_actor_id": actor.get("reference_actor_id"),
            "wcl_observed_dps": actor.get("wcl_observed_dps"),
            "wcl_common_window_dps": wcl_dps,
            "dps_comparison_status": actor.get("dps_comparison_status", "unmatched"),
            "bot_common_window_damage": actor.get("bot_common_window_damage"),
            "bot_common_window_dps": actor.get("bot_common_window_dps"),
            "bot_common_window_dps_basis": actor.get(
                "bot_common_window_dps_basis"
            ),
            "bot_common_window_dps_delta_vs_wcl": denominator_matched_delta,
            "bot_common_window_dps_ratio_vs_wcl": denominator_matched_ratio,
            "bot_native_encounter_window_dps": actor.get(
                "bot_native_encounter_window_dps",
                actor.get("bot_encounter_window_dps"),
            ),
            "wcl_completed_casts": wcl.get("event_count"),
            "wcl_max_gap_sec": wcl.get("max_gap_sec"),
            "bot_landed_damage_events": bot.get("event_count"),
            "bot_direct_or_unknown_events": direct.get("event_count"),
            "bot_direct_max_gap_sec": direct.get("max_gap_sec"),
            "largest_direct_gap": gaps[0] if gaps else None,
            "bot_event_input_status": actor.get("bot_event_input_status"),
            "gap_basis": actor.get("gap_basis"),
            "owner_direct_cadence": actor.get("owner_direct_cadence"),
            "owner_unknown_cadence": actor.get("owner_unknown_cadence"),
            "damage_classification_counts": actor.get("damage_classification_counts"),
            "comparison_limitations": actor.get("comparison_limitations", []),
            "matched_ability_diffs": [
                {
                    key: row[key]
                    for key in (
                        "ability",
                        "wcl_completed_casts",
                        "bot_landed_damage_events",
                    )
                    if key in row
                }
                for row in diffs[:4]
                if isinstance(row, dict)
            ],
            "wcl_only_abilities": wcl_only[:8],
            "bot_only_abilities": bot_only[:8],
        }
    return result


def _timeline_gap_overlap_evidence(
    timeline_comparison: dict[str, Any] | None,
    native_action_outcomes: Any,
    native_candidate_rejections: Any,
    encounter_first_at_ms: int,
    *,
    gap_limit: int = 3,
    overlap_row_limit: int = 8,
) -> dict[int, dict[str, Any]]:
    """Join actor damage gaps to timestamped native evidence.

    Timeline gaps are relative to the first encounter event, while native
    action and candidate rows use absolute timestamps.  Aggregate native rows
    are first/last envelopes, not continuous observations. Only an envelope
    fully contained in the gap has an exact in-gap count. Partial overlap is
    possible context, never proof that any event occurred inside the gap.
    """
    result: dict[int, dict[str, Any]] = {}
    if not isinstance(timeline_comparison, dict):
        return result

    def interval(row: Any) -> tuple[int, int] | None:
        if not isinstance(row, dict):
            return None
        first_at_ms = _as_int(row.get("first_at_ms"))
        last_at_ms = _as_int(row.get("last_at_ms"))
        if not first_at_ms or not last_at_ms or last_at_ms < first_at_ms:
            return None
        return first_at_ms, last_at_ms

    def overlap_ms(
        left_first_at_ms: int,
        left_last_at_ms: int,
        right_first_at_ms: int,
        right_last_at_ms: int,
    ) -> int | None:
        first_at_ms = max(left_first_at_ms, right_first_at_ms)
        last_at_ms = min(left_last_at_ms, right_last_at_ms)
        if first_at_ms > last_at_ms:
            return None
        return max(0, last_at_ms - first_at_ms)

    actions_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in native_action_outcomes if isinstance(native_action_outcomes, list) else []:
        if isinstance(row, dict):
            actions_by_guid[_as_int(row.get("bot_guid") or row.get("actor_guid"))].append(row)
    candidates_by_guid: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in (
        native_candidate_rejections
        if isinstance(native_candidate_rejections, list)
        else []
    ):
        if isinstance(row, dict):
            candidates_by_guid[_as_int(row.get("bot_guid") or row.get("actor_guid"))].append(row)

    for actor in timeline_comparison.get("actors", []):
        if not isinstance(actor, dict):
            continue
        guid = _as_int(actor.get("bot_guid"))
        if not guid:
            continue
        gaps = actor.get("bot_largest_direct_gaps")
        gaps = gaps if isinstance(gaps, list) else []
        if actor.get("bot_event_input_status") == "incomplete":
            result[guid] = {"status": "unavailable", "reason": "incomplete_damage_event_input", "gaps_considered": []}
            continue
        if not encounter_first_at_ms:
            result[guid] = {
                "status": "unavailable",
                "reason": "encounter_first_at_ms_missing",
                "gaps_considered": [],
            }
            continue

        timestamped_actions = [
            row for row in actions_by_guid.get(guid, []) if interval(row) is not None
        ]
        timestamped_candidates = [
            row for row in candidates_by_guid.get(guid, []) if interval(row) is not None
        ]
        gap_rows: list[dict[str, Any]] = []
        for gap in gaps[:gap_limit]:
            if not isinstance(gap, dict):
                continue
            try:
                from_t = float(gap.get("from_t"))
                to_t = float(gap.get("to_t"))
            except (TypeError, ValueError):
                continue
            if to_t < from_t:
                from_t, to_t = to_t, from_t
            gap_first_at_ms = encounter_first_at_ms + round(from_t * 1000.0)
            gap_last_at_ms = encounter_first_at_ms + round(to_t * 1000.0)
            action_overlaps: list[dict[str, Any]] = []
            candidate_overlaps: list[dict[str, Any]] = []
            for row in timestamped_actions:
                row_interval = interval(row)
                assert row_interval is not None
                row_first_at_ms, row_last_at_ms = row_interval
                row_overlap_ms = overlap_ms(
                    gap_first_at_ms,
                    gap_last_at_ms,
                    row_first_at_ms,
                    row_last_at_ms,
                )
                if row_overlap_ms is None:
                    continue
                outcome = str(row.get("outcome") or row.get("result") or "unknown")
                reason = str(row.get("reason_code") or row.get("reason") or "")
                action_row = {
                    "source": "native_action_outcome",
                    "action_name": str(row.get("action_name") or "unknown"),
                    "outcome": outcome,
                    "count": max(1, _as_int(row.get("count"))),
                    "first_at_ms": row_first_at_ms,
                    "last_at_ms": row_last_at_ms,
                    "overlap_seconds": round(row_overlap_ms / 1000.0, 3),
                    "in_gap_count": (max(1, _as_int(row.get("count")))
                        if gap_first_at_ms <= row_first_at_ms <= row_last_at_ms <= gap_last_at_ms
                        else None),
                    "actionable_failure": (
                        outcome in NATIVE_ACTIONABLE_FAILURE_OUTCOMES
                        or reason in {"no_line_of_sight", "out_of_range"}
                    ),
                }
                if reason:
                    action_row["reason_code"] = reason
                action_overlaps.append(action_row)
            for row in timestamped_candidates:
                row_interval = interval(row)
                assert row_interval is not None
                row_first_at_ms, row_last_at_ms = row_interval
                row_overlap_ms = overlap_ms(
                    gap_first_at_ms,
                    gap_last_at_ms,
                    row_first_at_ms,
                    row_last_at_ms,
                )
                if row_overlap_ms is None:
                    continue
                reason = str(row.get("reason") or "unknown")
                candidate_row = {
                    "source": "native_candidate_rejection",
                    "reason": reason,
                    "action_category": str(row.get("action_category") or "unknown"),
                    "count": max(1, _as_int(row.get("count"))),
                    "first_at_ms": row_first_at_ms,
                    "last_at_ms": row_last_at_ms,
                    "overlap_seconds": round(row_overlap_ms / 1000.0, 3),
                    "in_gap_count": (max(1, _as_int(row.get("count")))
                        if gap_first_at_ms <= row_first_at_ms <= row_last_at_ms <= gap_last_at_ms
                        else None),
                    "movement_or_range": reason in MOVEMENT_SIGNAL_REASONS,
                }
                spell_id = _as_int(row.get("spell_id"))
                if spell_id:
                    candidate_row["spell_id"] = spell_id
                candidate_overlaps.append(candidate_row)

            overlap_rows = [*action_overlaps, *candidate_overlaps]
            overlap_rows.sort(
                key=lambda row: (
                    -int(bool(row.get("actionable_failure") or row.get("movement_or_range"))),
                    -float(row.get("overlap_seconds") or 0.0),
                    -int(row.get("count") or 0),
                )
            )
            gap_rows.append({
                "gap_sec": round(to_t - from_t, 3),
                "from_t": round(from_t, 3),
                "to_t": round(to_t, 3),
                "from_at_ms": gap_first_at_ms,
                "to_at_ms": gap_last_at_ms,
                "from_ability": gap.get("from_ability"),
                "to_ability": gap.get("to_ability"),
                "action_overlap_count": len(action_overlaps),
                "candidate_overlap_count": len(candidate_overlaps),
                "actionable_failure_count": sum(
                    int(row["in_gap_count"] or 0)
                    for row in action_overlaps
                    if row.get("actionable_failure")
                ),
                "movement_or_range_rejection_count": sum(
                    int(row["in_gap_count"] or 0)
                    for row in candidate_overlaps
                    if row.get("movement_or_range")
                ),
                "count_basis": "known_contained_aggregate_counts_only; partial_overlap_count_unknown",
                "partial_overlap_row_count": sum(row["in_gap_count"] is None for row in overlap_rows),
                "overlap_reasons": sorted({
                    str(row.get("reason_code") or row.get("reason") or row.get("outcome"))
                    for row in overlap_rows
                    if row.get("reason_code") or row.get("reason") or row.get("outcome")
                }),
                "overlap_rows": overlap_rows[:overlap_row_limit],
                "evidence_precision": (
                    "native_aggregate_first_last_interval"
                    if overlap_rows
                    else "none"
                ),
            })

        has_overlap = any(
            row.get("action_overlap_count") or row.get("candidate_overlap_count")
            for row in gap_rows
        )
        if any(row["actionable_failure_count"] or row["movement_or_range_rejection_count"] for row in gap_rows):
            status = "corroborated"
            reason = "native_failure_envelope_contained_in_gap; causation_not_established"
        elif has_overlap:
            status = "possible_overlap"
            reason = "aggregate_envelope_overlap_does_not_locate_events"
        elif timestamped_actions or timestamped_candidates:
            status = "no_timestamped_overlap"
            reason = "timestamped_native_rows_do_not_overlap_damage_gap"
        else:
            status = "unavailable"
            reason = "native_rows_have_no_timestamped_intervals"
        result[guid] = {
            "status": status,
            "reason": reason,
            "evidence_precision": (
                "native_aggregate_first_last_interval" if has_overlap else "none"
            ),
            "encounter_first_at_ms": encounter_first_at_ms,
            "timestamped_action_row_count": len(timestamped_actions),
            "timestamped_candidate_row_count": len(timestamped_candidates),
            "gaps_considered": gap_rows,
        }
    return result


def _compact_group_timeline(
    timeline_comparison: dict[str, Any] | None,
) -> dict[str, Any]:
    """Reduce the full comparison to the group-coherence signal."""
    if not isinstance(timeline_comparison, dict):
        return {
            "available": False,
            "reason": "timeline_comparison_unavailable",
            "actors": [],
        }
    actors: list[dict[str, Any]] = []
    for actor in timeline_comparison.get("actors", []):
        if not isinstance(actor, dict):
            continue
        wcl = actor.get("wcl_completed_cast_cadence")
        wcl = wcl if isinstance(wcl, dict) else {}
        bot = actor.get("bot_landed_damage_cadence")
        bot = bot if isinstance(bot, dict) else {}
        direct = actor.get("bot_direct_or_unknown_cadence")
        direct = direct if isinstance(direct, dict) else {}
        gaps = actor.get("bot_largest_direct_gaps")
        gaps = gaps if isinstance(gaps, list) else []
        actors.append({
            key: actor[key]
            for key in (
                "bot_guid",
                "bot_name",
                "role",
                "class_spec",
                "comparison_status",
                "bot_event_input_status",
                "reference_actor_id",
                "wcl_observed_dps",
                "wcl_observed_dps_window_sec",
                "wcl_common_window_dps",
                "dps_comparison_status",
                "bot_encounter_window_dps",
                "bot_native_encounter_window_dps",
                "bot_common_window_damage",
                "bot_common_window_dps",
                "bot_common_window_dps_basis",
                "bot_damage_uptime",
                "bot_moving_fraction",
            )
            if key in actor
        } | {
            "wcl_cast_count": wcl.get("event_count"),
            "wcl_max_gap_sec": wcl.get("max_gap_sec"),
            "bot_landed_event_count": bot.get("event_count"),
            "bot_max_gap_sec": bot.get("max_gap_sec"),
            "bot_direct_event_count": direct.get("event_count"),
            "bot_direct_max_gap_sec": direct.get("max_gap_sec"),
            "largest_direct_gap": gaps[0] if gaps else None,
            "bot_event_input_status": actor.get("bot_event_input_status"),
            "gap_basis": actor.get("gap_basis"),
            "owner_direct_cadence": actor.get("owner_direct_cadence"),
            "owner_unknown_cadence": actor.get("owner_unknown_cadence"),
            "damage_classification_counts": actor.get("damage_classification_counts"),
            "comparison_limitations": actor.get("comparison_limitations", []),
            "largest_direct_gap_sec": (
                gaps[0].get("gap_sec")
                if gaps and isinstance(gaps[0], dict)
                else None
            ),
        })
    return {
        "available": True,
        "reference": timeline_comparison.get("reference"),
        "scope": timeline_comparison.get("scope"),
        "comparison_window": timeline_comparison.get("comparison_window"),
        "actors": actors,
        "signal_contract": timeline_comparison.get("signal_contract"),
    }


def _group_jev_state(state: dict[str, Any]) -> dict[str, Any]:
    """Build the small shared packet used for route and group coherence."""
    boss = state.get("boss_dps_review")
    boss = boss if isinstance(boss, dict) else {}
    actor_rows: list[dict[str, Any]] = []
    for actor in boss.get("actor_loss_signals", []):
        if not isinstance(actor, dict):
            continue
        actor_rows.append({
            key: actor[key]
            for key in (
                "bot_guid",
                "class_spec",
                "encounter_dps",
                "wcl_observed_dps",
                "encounter_dps_gap_vs_wcl",
                "active_dps_gap_vs_wcl",
                "damage_uptime",
                "moving_fraction",
                "native_actionable_failure_ratio",
                "duty_explains_idle",
                "required_assignment_active",
                "assignment_status",
                "counterfactual_status",
                "timeline_signal",
            )
            if key in actor
        })
    compact_boss = {
        key: boss[key]
        for key in (
            "scope_route_node",
            "wcl_dps_contract",
            "combat_metrics",
            "action_outcomes",
            "action_outcome_view",
            "native_outcome_signal",
            "candidate_rejection_summary",
            "native_mushroom_diagnostics",
            "candidate_rejection_count",
            "candidate_rejection_groups",
            "actor_identity",
            "trace_capture",
            "wcl_reference",
            "timeline_gap_overlap_evidence",
        )
        if key in boss
    }
    compact_boss["actor_loss_signals"] = actor_rows
    compact_boss["timeline_comparison"] = _compact_group_timeline(
        boss.get("timeline_comparison")
    )
    return {
        "task": state.get("task"),
        "authority": state.get("authority"),
        "run_id": state.get("run_id"),
        "segment_id": state.get("segment_id"),
        "change": state.get("change"),
        "expected_route_nodes": state.get("expected_route_nodes"),
        "scope_route_prefix": state.get("scope_route_prefix"),
        "route_review": state.get("route_review"),
        "boss_dps_review": compact_boss,
        "native_gameplay_outcome": state.get("native_gameplay_outcome"),
        "baseline": state.get("baseline"),
    }


def _actor_jev_state(
    state: dict[str, Any],
    actor: dict[str, Any],
    timeline_actor: dict[str, Any] | None,
) -> dict[str, Any]:
    """Build one isolated packet for one DPS actor."""
    boss = state.get("boss_dps_review")
    boss = boss if isinstance(boss, dict) else {}
    timeline = boss.get("timeline_comparison")
    timeline = timeline if isinstance(timeline, dict) else {}
    return {
        "task": "Magmaw 10N individual DPS actor review",
        "authority": state.get("authority"),
        "run_id": state.get("run_id"),
        "segment_id": state.get("segment_id"),
        "change": state.get("change"),
        "native_gameplay_outcome": state.get("native_gameplay_outcome"),
        "wcl_dps_contract": boss.get("wcl_dps_contract"),
        "actor_review": actor,
        "timeline_comparison": {
            "reference": timeline.get("reference"),
            "comparison_window": timeline.get("comparison_window"),
            "signal_contract": timeline.get("signal_contract"),
            "actor": timeline_actor or {
                "bot_guid": actor.get("bot_guid"),
                "comparison_status": "missing_actor_timeline",
            },
        },
    }


def _boss_dps_review(
    deterministic: dict[str, Any],
    entries: list[dict[str, Any]],
    live_report: dict[str, Any] | None,
    actor_identity: Mapping[str, dict[str, Any]] | None,
    wcl_reference: dict[str, Any] | None,
    target_duty_context: dict[str, Any] | None = None,
    timeline_comparison: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metrics = deterministic.get("boss_combat_metrics")
    if not isinstance(metrics, dict):
        metrics = deterministic.get("latest_combat_metrics", {"available": False})
    metrics = _dps_review_metrics(metrics, wcl_reference)
    _, trace_capture = _boss_trace_window(
        entries,
        deterministic.get("boss_combat_metrics"),
        DEFAULT_BOSS_ROUTE[0],
    )
    decision_outcomes = _compact_decision_receipts(
        live_report,
        DEFAULT_BOSS_ROUTE[0],
        actor_identity,
        {"dps"},
        window_start_ms=_as_int(trace_capture.get("combat_window_start_ms")),
        window_end_ms=_as_int(trace_capture.get("combat_window_end_ms")),
        terminal_at_ms=_as_int(trace_capture.get("terminal_at_ms")),
    )
    scoped_entries = [
        entry
        for entry in entries
        if _route_in_scope(str(entry.get("route_node_id") or ""), DEFAULT_BOSS_ROUTE[0])
    ]
    scoped_entries, trace_capture = _boss_trace_window(
        scoped_entries,
        deterministic.get("boss_combat_metrics"),
        DEFAULT_BOSS_ROUTE[0],
    )
    dps_entries = [
        entry
        for entry in scoped_entries
        if (
            (actor_identity or {}).get(str(_as_int(entry.get("_bot_guid"))), {}).get("role")
            in {None, "dps"}
        )
    ]
    native_action_outcomes = deterministic.get("boss_action_outcomes", [])
    native_candidate_rejections = deterministic.get("boss_candidate_rejections", [])
    candidate_signal = _candidate_rejection_signal(native_candidate_rejections)
    native_outcome_summary = _summarize_jev_action_outcomes(native_action_outcomes)
    native_outcome_count = sum(
        int(row.get("outcome_count") or 0) for row in native_outcome_summary
    )
    native_failure_count = sum(
        int(row.get("actionable_failure_count") or 0) for row in native_outcome_summary
    )
    actor_loss_signals = _actor_loss_signals(
        metrics,
        native_outcome_summary,
        native_candidate_rejections,
        target_duty_context,
    )
    timeline_actor_signals = _timeline_actor_signal(timeline_comparison)
    boss_metrics = deterministic.get("boss_combat_metrics")
    boss_metrics = boss_metrics if isinstance(boss_metrics, dict) else {}
    encounter_first_at_ms = _as_int(boss_metrics.get("first_at_ms"))
    if not encounter_first_at_ms:
        encounter_first_at_ms = _as_int(trace_capture.get("combat_window_start_ms"))
    timeline_gap_overlap = _timeline_gap_overlap_evidence(
        timeline_comparison,
        native_action_outcomes,
        native_candidate_rejections,
        encounter_first_at_ms,
    )
    for actor in actor_loss_signals:
        if not isinstance(actor, dict):
            continue
        bot_guid = _as_int(actor.get("bot_guid"))
        timeline_signal = timeline_actor_signals.get(bot_guid)
        if timeline_signal is not None:
            timeline_signal = dict(timeline_signal)
            timeline_signal["gap_overlap_evidence"] = timeline_gap_overlap.get(
                bot_guid,
                {
                    "status": "unavailable",
                    "reason": "actor_timeline_gap_join_missing",
                    "gaps_considered": [],
                },
            )
            actor["timeline_signal"] = timeline_signal
    failure_action_outcomes = _jev_action_outcome_slice(native_action_outcomes)
    failure_action_summary = _summarize_jev_failure_action_outcomes(
        failure_action_outcomes
    )
    dps_actor_guids = {
        _as_int(actor.get("bot_guid"))
        for actor in actor_loss_signals
        if isinstance(actor, dict) and _as_int(actor.get("bot_guid"))
    }
    jev_combat_metrics = _jev_combat_metrics(metrics)
    # actor_loss_signals is the attributable per-DPS view. Sending another
    # actor array with the same DPS/ability fields only increases the JEV
    # packet and makes the typed judgment less reliable on long canaries.
    jev_combat_metrics.pop("actors", None)
    jev_combat_metrics["actor_metrics_source"] = "actor_loss_signals"
    return {
        "scope_route_node": DEFAULT_BOSS_ROUTE[0],
        "wcl_dps_contract": {
            "comparison_metric": "wcl_window_dps",
            "formula": "originated_damage_over_duration_sec",
            "duration_field": "duration_sec",
            "duration_basis": "first_to_last_positive_originated_damage_done",
            "capture_duration_field": "capture_duration_sec",
            "local_source_field": "encounter_window_dps",
            "legacy_alias": "elapsed_dps",
            "excluded_diagnostics": {
                "dps": "active_combat_seconds",
                "active_dps": "actor_damage_bearing_seconds",
                "elapsed_party_dps": "not_route_wall_clock; encounter event window only",
            },
            "interpretation": (
                "Use only the selected Magmaw encounter window for WCL Summary DPS; "
                "route entrance/recovery wall clock is a separate progress metric."
            ),
        },
        "combat_metrics": jev_combat_metrics,
        "combat_diagnostics": deterministic.get("boss_combat_diagnostics", []),
        "action_outcomes": failure_action_summary,
        "action_outcome_view": "grouped_direct_native_failures",
        "native_outcome_summary": native_outcome_summary,
        "target_duty_context": _compact_jev_target_duty_context(
            target_duty_context,
            dps_actor_guids,
        ),
        "native_mushroom_diagnostics": _compact_jev_native_mushroom_diagnostics(
            deterministic.get("native_mushroom_diagnostics", [])
        ),
        "causal_signal_view": (
            "full_window_target_overlay_failure_window_and_timeline_gap_overlap"
        ),
        "native_outcome_signal": {
            "outcome_count": native_outcome_count,
            "actionable_failure_count": native_failure_count,
            "actionable_failure_ratio": round(
                native_failure_count / max(1, native_outcome_count), 6
            ),
            "interpretation": (
                "native action rejection is not the dominant loss when this ratio is low "
                "and the active stuck set is empty"
            ),
        },
        "actor_loss_signals": actor_loss_signals,
        "timeline_comparison": timeline_comparison,
        "timeline_gap_overlap_evidence": {
            str(bot_guid): evidence
            for bot_guid, evidence in timeline_gap_overlap.items()
        },
        # Only gates outside the expected profile-wait set are sent as the
        # short candidate list. The complete native rows remain in the
        # deterministic report for local audit and replay.
        "candidate_rejections": candidate_signal["actionable_candidate_groups"],
        "candidate_rejection_summary": _compact_jev_candidate_signal(
            candidate_signal
        ),
        "candidate_rejection_rows": len(native_candidate_rejections),
        "candidate_rejection_groups": len(candidate_signal["actionable_candidate_groups"]),
        "candidate_rejection_count": sum(
            int(row.get("count") or 0)
            for row in native_candidate_rejections
            if isinstance(row, dict)
        ),
        "decision_outcomes": decision_outcomes,
        "action_outcome_coverage": {
            "boss_trace_rows": len(scoped_entries),
            "dps_trace_rows": len(dps_entries),
            "attributable_dps_action_outcomes": len(
                native_action_outcomes
            ),
            "jev_action_outcome_rows": len(failure_action_summary),
            "omitted_expected_wait_rows": max(
                0,
                len(native_action_outcomes) - len(failure_action_outcomes),
            ),
            "attributable_dps_candidate_rejections": len(
                native_candidate_rejections
            ),
            "source": deterministic.get(
                "boss_action_outcome_source", "retained_trace_tail"
            ),
            "full_window_action_outcome_count": int(
                (deterministic.get("boss_combat_metrics") or {}).get(
                    "action_outcome_count", 0
                )
                or 0
            ),
            "attributable_dps_decision_outcomes": len(decision_outcomes),
            "timeline_gap_overlap_actor_count": len(timeline_gap_overlap),
            "timeline_gap_overlap_corroborated_actor_count": sum(
                1
                for evidence in timeline_gap_overlap.values()
                if evidence.get("status") == "corroborated"
            ),
            "trace_capture": trace_capture,
            "interpretation": (
                "full_window_native_aggregate_is_authoritative_when_present; "
                "retained_tail_is_missing_capture_not_proof_of_no_rejection; "
                "timeline_gap_overlap_is_aggregate_interval_corroboration_only"
            ),
        },
        "trace_capture": trace_capture,
        "wcl_reference": wcl_reference,
    }


def _jev_questions(
    has_baseline: bool,
    *,
    include_next_fix: bool = True,
    actor_specs: list[dict[str, Any]] | None = None,
    include_timeline: bool = True,
    include_assignment: bool = True,
) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {
        "path_consistency": {
            "type": "choice",
            "instructions": "Classify route_review only. Use native terminal evidence and route generations; repeated decisions within one generation are not a route loop. A sampled node gap is acceptable after a native terminal. Choose loop_or_gap only for route reversal, repeated generation, unexpected node, missing terminal evidence, or an active unresolved event. Use native_gameplay_outcome as authority; uncertified is not a wipe. Choose insufficient_evidence for zero active bots or trace rows.",
            "criteria": {
                "aligned": "Observed route is ordered and the current segment has no unexplained loop or gap.",
                "ordered_segment": "The trace is an ordered, intentionally partial segment and is not enough to judge a full clear.",
                "loop_or_gap": "The trace shows repeated decisions, route reversal, missing expected handoff, or unexplained path churn.",
                "insufficient_evidence": "There are too few native trace rows to compare the path safely.",
            },
        },
        "stuck_behavior": {
            "type": "choice",
            "instructions": "Classify the currently-unresolved behavior from route_review. Prefer active_stuck_* for the latest non-terminal generation; raw/resolved counts are historical after native terminal evidence. Choose lifecycle for admission failure/underfill, none for an admitted run with no active stuck event, and never call an uncertified clear a wipe.",
            "criteria": {
                "none": "No repeated, blocked, churn, failure, or recovery pattern is evidenced.",
                "movement": "Movement or formation progress is the dominant blocker.",
                "target": "Target churn, stale target return, or target lease conflict is dominant.",
                "native_action": "Candidate/action submission or native outcome failures are dominant.",
                "mechanic": "Encounter mechanic or assigned transfer/hook/parasite path is dominant.",
                "lifecycle": "Death, recovery, readiness, or route lifecycle is dominant.",
            },
        },
        "timeline_consistency": {
            "type": "choice",
            "instructions": (
                "Use boss_dps_review.timeline_comparison as the primary DPS signal for every local actor. "
                "Compare normalized WCL completed-cast cadence with bot landed-damage "
                "cadence and largest direct gaps. These event types are intentionally "
                "different: periodic ticks and multi-target rows can outnumber casts. "
                "Use matched ability timing and actor-level gaps, not raw count equality. "
                "A missing WCL reference is an explicit not_comparable result, never a "
                "passing or failing inference. A gap-overlap causal claim is admissible "
                "only when the actor's timeline_signal.gap_overlap_evidence.status is "
                "corroborated. possible_overlap, no_timestamped_overlap and unavailable are insufficient. "
                "native_aggregate_first_last_interval is corroboration, not event-level "
                "proof, so do not treat it as high-confidence by itself."
            ),
            "criteria": {
                "aligned": "Comparable actors show broadly aligned normalized cadence with no material unexplained gap.",
                "cadence_gap": "One or more comparable actors show a repeated material bot gap against the WCL cadence.",
                "mechanic_gap": "The largest gap overlaps a documented mechanic, assignment, or native control window.",
                "not_comparable": "The actor lacks a WCL timeline or the windows/identity cannot be aligned.",
            },
        },
        "dps_loss_area": {
            "type": "choice",
            "instructions": "Classify the actionable DPS loss from boss_dps_review. Use native full-fight DPS as descriptive context. bot_common_window_dps is a clipped native window, not a phase-matched comparison. Compare it numerically only to wcl_common_window_dps when dps_comparison_status=timestamped_common_window; otherwise WCL whole-fight DPS is unmatched context. The timeline lists WCL-only abilities, but those are observation gaps only: do not call one a missing damage action unless its name identifies a damage action and native action outcomes or an attributable damage gap corroborate it. Proc, aura, utility, and pet-state rows such as Lava Surge, Master of the Elements, or Earth Elemental Totem are context, not cast deficits. The aggregate wcl_window_dps contract remains originated damage divided by the first-to-last positive hostile damage_done window in duration_sec. Treat capture_duration_sec as telemetry lifetime only. Treat legacy `dps` as active-combat DPS and `active_dps` as actor damage-bearing cadence context; do not use either as the WCL denominator. Keep route entrance/recovery wall clock separate from the Magmaw encounter window. Candidate scans are not failures: require material native no_action/cast_failed/LOS/range evidence. Low native failure plus no active stuck event rules out action_rejection. A material denominator-matched DPS deficit with low movement and failure can be uptime; use the full-window damage-gap fields to distinguish repeated cadence gaps from one missing trace segment. A required assignment is a separate causal branch: use its assignment_status and landed-effect evidence before labeling the actor's rotation. Do not call low uptime cadence loss when duty_explains_idle is true, required_assignment_active is true, magmaw_control_receipt_count is nonzero, or failure windows overlap material mechanic work. A native Mangle/vehicle receipt or proximate damage gap is mechanic downtime, not proof of a rotation defect. Require counterfactual_status=eligible for an actor repair; partial/unavailable/required-assignment/mechanic-control statuses mean insufficient_data or collect_more_canaries. For movement, range, or action-rejection claims, require timeline_signal.gap_overlap_evidence.status=corroborated; possible_overlap, no_timestamped_overlap or unavailable means insufficient_data. Even corroborated native_aggregate_first_last_interval evidence is only interval-level support, not event-level proof. WCL is comparison context, not an acceptance floor.",
            "criteria": {
                "no_material_loss": "DPS is available and the trace shows no material execution blocker.",
                "uptime": "Idle/cadence loss remains after duty overlap is ruled out.",
                "movement": "The dominant loss is movement, formation, hazard, or range downtime.",
                "targeting": "The dominant loss is target churn, stale targets, or wrong target return.",
                "action_rejection": "The dominant loss is candidate rejection, native submission failure, or repeated backoff.",
                "mechanic_downtime": "The dominant loss is a required encounter mechanic or recovery assignment.",
                "insufficient_data": "Combat, duty, or counterfactual evidence is insufficient.",
            },
        },
        "canary_safe_to_promote": {
            "type": "noul",
            "instructions": "Is this Magmaw canary safe to promote? Use native_gameplay_outcome first. An uncertified clear is diagnostic only, not a wipe and not promotable.",
            "criteria": {
                "true": "native_gameplay_outcome.status is clear, certification_status is accepted, the route evidence is attributable, and no death/repetition guardrail fired.",
                "false": "The native outcome is incomplete, wiped, stalled, or clear only with certification_status=uncertified. An uncertified clear is not a wipe.",
            },
        },
    }
    if not include_timeline:
        questions.pop("timeline_consistency", None)
    for actor in actor_specs or []:
        if not isinstance(actor, dict):
            continue
        guid = _as_int(actor.get("bot_guid"))
        if not guid:
            continue
        class_spec = str(actor.get("class_spec") or "unknown")
        question_id = f"actor_action_{guid}"
        questions[question_id] = {
            "type": "choice",
            "instructions": (
                f"For {class_spec} bot_guid {guid}, choose one bounded action from "
                "actor_review and its matching timeline_comparison.actor. Read the normalized "
                "WCL-cast versus bot-landed cadence, WCL-only abilities, and largest direct "
                "gaps. WCL-only abilities are not automatically missing casts: require a "
                "native action or attributable damage-gap join, and ignore proc/state/utility "
                "rows as direct deficits. Treat bot_common_window_dps as clipped native context unless dps_comparison_status=timestamped_common_window; "
                "bot_native_encounter_window_dps is diagnostic when the local window is "
                "longer than WCL. Use uptime, movement/range, native "
                "failure ratio, candidate gates, duty context, assignment status, control "
                "receipts, damage gaps, gap_overlap_evidence, and counterfactual_status. "
                "WCL is context only. Do not authorize actor repair when duty_explains_idle, "
                "required_assignment_active, or counterfactual_status != eligible. Incomplete "
                "required duty means encounter_assignment; otherwise mixed or sparse evidence "
                "means collect_more_canaries. Treat gap_overlap_evidence.status=corroborated "
                "as aggregate corroboration only; native_aggregate_first_last_interval is "
                "not event-level proof. no_timestamped_overlap or unavailable cannot support "
                "a high-confidence movement/range/action-rejection choice."
            ),
            "criteria": {
                "no_material_action": "No attributable material gap.",
                "movement_recovery": "Movement, range, LOS, or uptime facts align with the loss.",
                "uptime_cadence": "Eligible counterfactual; low uptime with low movement/failures.",
                "rotation_profile": "Profile priority, cooldown, resource, or policy is the edge.",
                "target_lease": "Target ownership, return, or churn is material.",
                "shared_arbitration": "Native submission failures are attributable.",
                "encounter_assignment": "A required duty is incomplete; review its observed execution.",
                "collect_more_canaries": "Evidence is mixed, sparse, or not reproducible.",
            },
        }
        if (
            include_assignment
            and actor.get("assignment_id") == "magmaw_balance_mushroom_add_control"
        ):
            questions[f"actor_assignment_{guid}"] = {
                "type": "choice",
                "instructions": (
                    f"For the required Magmaw assignment {actor.get('assignment_id') or 'unknown'} "
                    f"on {class_spec} bot_guid {guid}, classify execution from the deterministic "
                    "assignment contract, native action outcomes, and landed effect evidence. "
                    "Do not treat placement decision rows as landed casts."
                ),
                "criteria": {
                    "assignment_executed": "A native detonation and the assignment's landed damage effect are both observed.",
                    "assignment_incomplete": "Some assignment evidence is observed, but no complete landed cycle is proven.",
                    "assignment_unobserved": "The required assignment is declared, but no attributable action or landed effect is observed.",
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
    if include_next_fix:
        questions["next_fix"] = _next_fix_question()
    return questions


def _next_fix_question() -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": "Choose one bounded next action from the typed judgments. Native evidence is authoritative. Use admission_lifecycle for admission failure; encounter_assignment only for incomplete required duty; collect_more_canaries for executed, unobserved, mixed, or sparse duty evidence. If duty_explains_idle, a control receipt, or ineligible counterfactual_status is present, do not choose uptime_cadence or movement_recovery. Use uptime_cadence only for an eligible material encounter-window DPS gap with low movement/failure; movement_recovery only when movement/range facts align. Require a corroborated timeline_signal.gap_overlap_evidence.status for movement/range/action-rejection claims; native_aggregate_first_last_interval remains interval-level support, not event-level proof. Require direct evidence for shared_arbitration, rotation_profile, or native_mechanics.",
        "criteria": {
            "collect_more_canaries": "Evidence is insufficient or not reproducible.",
            "admission_lifecycle": "Repair run admission, roster, or lifecycle first.",
            "movement_recovery": "Movement, range, or recovery is the first broken edge.",
            "uptime_cadence": "Eligible clean counterfactual has material window-DPS loss.",
            "target_lease": "Target ownership, return, or churn is material.",
            "shared_arbitration": "Shared native candidate/submission edge is material.",
            "encounter_assignment": "Required encounter assignment is incomplete.",
            "rotation_profile": "Class priority, resource, or cooldown gate is material.",
            "native_mechanics": "Native spell, aura, pet, or outcome mismatch is material.",
        },
    }


def _group_coherence_question() -> dict[str, Any]:
    """Ask one small group-level question after actor reviews are isolated."""
    return {
        "type": "choice",
        "instructions": (
            "Classify group coherence from route_review, native_gameplay_outcome, and "
            "boss_dps_review.timeline_comparison. Use the actor rows only to decide "
            "whether the group has one shared cadence/mechanic pattern or whether the "
            "loss is actor-specific. WCL completed casts and bot landed events are "
            "different event types; periodic and multi-target rows must not be counted "
            "as casts. Missing WCL references are not failures."
        ),
        "criteria": {
            "coherent": (
                "Comparable actors have broadly aligned cadence and no shared unresolved "
                "gap; any remaining loss is actor-specific."
            ),
            "actor_divergence": (
                "The group is live, but one or more actors materially diverge while "
                "others do not; use individual actor judgments for action."
            ),
            "mechanic_aligned_gap": (
                "The largest common gap aligns with an encounter mechanic, assignment, "
                "or native control window."
            ),
            "insufficient_data": (
                "The run, actor identity, or comparable timeline evidence is insufficient "
                "to judge group coherence."
            ),
        },
    }


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
        sort_keys=False,
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
                detail = ""
                try:
                    detail = exc.read().decode("utf-8", errors="replace").strip()
                except OSError:
                    pass
                if len(detail) > 500:
                    detail = detail[:500] + "..."
                suffix = f": {detail}" if detail else ""
                raise JevError(f"JEV request failed with HTTP {exc.code}{suffix}") from exc
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
            if not isinstance(criteria, dict) or not isinstance(choice, str) or choice not in criteria:
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


def _actor_action_gate(answers: dict[str, Any]) -> dict[str, Any]:
    """Expose per-actor confidence without turning Jev into an executor."""
    result: dict[str, Any] = {}
    for question_id, answer in answers.items():
        if not question_id.startswith("actor_action_") or not isinstance(answer, dict):
            continue
        choice = str(answer.get("choice") or "")
        confidence = _as_float(answer.get("confidence"), 0.0)
        if confidence < JEV_CONFIDENCE_FLOOR:
            status = "review_required"
        elif choice == "collect_more_canaries":
            status = "advisory_collect_more"
        elif choice == "no_material_action":
            status = "advisory_no_change"
        else:
            status = "advisory_action"
        result[question_id] = {
            "choice": choice,
            "confidence": confidence,
            "status": status,
        }
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
        "elapsed_party_dps": metrics.get("elapsed_party_dps"),
        "combat_seconds": metrics.get("combat_seconds"),
        "duration_sec": metrics.get("duration_sec"),
        "boss_dps_review": report.get("jev_input", {}).get("state", {}).get(
            "boss_dps_review", {}
        ),
        "timeline_comparison": report.get("jev_input", {}).get("state", {}).get(
            "boss_dps_review", {}
        ).get("timeline_comparison"),
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


def _validate_timeline_identity(timeline: dict[str, Any], report_path: Path | None) -> None:
    source = timeline.get("bot_run") or {}
    if report_path is None or not report_path.is_file():
        raise ValueError("timeline join requires the original closed report")
    actual = hashlib.sha256(report_path.read_bytes()).hexdigest()
    if source.get("report_sha256") != actual:
        raise ValueError("timeline/report identity missing or mismatched; regenerate timeline")


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
    combat_log_path: Path | None = None,
    native_log_path: Path | None = None,
    scope_route_prefix: str = MAGMAW_ROUTE_PREFIX,
    wcl_reference_path: Path | None = None,
    timeline_comparison_path: Path | None = None,
    prepare_only: bool = False,
) -> dict[str, Any]:
    raw_path, report_path, discovered_analysis = _input_files(input_path)
    live_report: dict[str, Any] | None = None
    canonical = None
    if report_path is not None and report_path.exists():
        live_report = _load_json(report_path)
        if not isinstance(live_report, dict):
            raise ValueError(f"live-validation report must be an object: {report_path}")
        from tools.bot_ml.closed_capture_inputs import is_canonical_capture, load_canonical_capture
        if is_canonical_capture(live_report):
            canonical = load_canonical_capture(report_path.parent, live_report)
    if canonical is not None:
        source_path = report_path
        rows = canonical["rows"]
    elif raw_path is not None and raw_path.exists():
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
    actor_identity = _actor_identity([live_report, *[_payload(row) for row in rows]])
    deterministic = _progress_summary(
        entries,
        expected_route,
        rows,
        scope_route_prefix=scope_route_prefix,
        actor_identity=actor_identity,
    )
    baseline = _compact_baseline(baseline_path)
    wcl_reference: dict[str, Any] | None = None
    if wcl_reference_path is not None and wcl_reference_path.exists():
        wcl_reference = _compact_wcl_reference(_load_json(wcl_reference_path))
    timeline_comparison: dict[str, Any] | None = None
    if timeline_comparison_path is not None and timeline_comparison_path.exists():
        raw_timeline = _load_json(timeline_comparison_path)
        _validate_timeline_identity(raw_timeline, report_path)
        timeline_comparison = _compact_timeline_comparison(raw_timeline)
    analysis_path = combat_analysis_path or discovered_analysis
    if (analysis_path and analysis_path.exists()) or canonical is not None:
        analysis = _load_json(analysis_path) if analysis_path and analysis_path.exists() else canonical["combat_analysis"]
        extracted = _analysis_metrics(analysis, scope_route_prefix, actor_identity)
        if extracted is not None:
            deterministic["latest_combat_metrics"] = extracted
        deterministic["combat_diagnostics"] = _analysis_diagnostics(
            analysis, scope_route_prefix
        )
        boss_metrics = _analysis_metrics(
            analysis,
            DEFAULT_BOSS_ROUTE[0],
            actor_identity,
        )
        if boss_metrics is not None:
            deterministic["boss_combat_metrics"] = boss_metrics
        deterministic["boss_combat_diagnostics"] = _analysis_diagnostics(
            analysis,
            DEFAULT_BOSS_ROUTE[0],
        )
    resolved_combat_log_path = combat_log_path or _discovered_combat_log_path(input_path)
    combat_log: dict[str, Any] | None = canonical["combat_log"] if canonical is not None else None
    if resolved_combat_log_path and resolved_combat_log_path.exists():
        loaded_combat_log = _load_json(resolved_combat_log_path)
        if not isinstance(loaded_combat_log, dict):
            raise ValueError(
                f"combat log must be an object: {resolved_combat_log_path}"
            )
        combat_log = loaded_combat_log
    resolved_native_log_path = native_log_path or _discovered_native_log_path(input_path)
    deterministic["native_mushroom_diagnostics"] = _native_mushroom_diagnostics(
        resolved_native_log_path
    )
    boss_trace_entries, boss_trace_capture = _boss_trace_window(
        entries,
        deterministic.get("boss_combat_metrics"),
        DEFAULT_BOSS_ROUTE[0],
    )
    deterministic["boss_trace_capture"] = boss_trace_capture
    native_boss_action_outcomes = _compact_native_action_outcomes(
        (deterministic.get("boss_combat_metrics") or {}).get("action_outcomes"),
        actor_identity,
        {"dps"},
    )
    if native_boss_action_outcomes:
        deterministic["boss_action_outcomes"] = native_boss_action_outcomes
        deterministic["boss_action_outcome_source"] = "full_window_native_aggregate"
    else:
        deterministic["boss_action_outcomes"] = _compact_action_outcomes(
            boss_trace_entries,
            DEFAULT_BOSS_ROUTE[0],
            actor_identity,
            {"dps"},
        )
        deterministic["boss_action_outcome_source"] = "retained_trace_tail"
    deterministic["boss_candidate_rejections"] = _compact_native_candidate_rejections(
        (deterministic.get("boss_combat_metrics") or {}).get(
            "candidate_rejections"
        ),
        actor_identity,
        {"dps"},
    )
    deterministic["boss_candidate_rejection_source"] = (
        "full_window_native_aggregate"
        if deterministic["boss_candidate_rejections"]
        else "unavailable"
    )
    deterministic["boss_target_duty_context"] = _target_duty_context(
        combat_log,
        deterministic.get("boss_combat_metrics"),
        deterministic.get("boss_action_outcomes", []),
        live_report,
    )
    deterministic["boss_combat_diagnostics"] = _dps_diagnostics(
        deterministic.get("boss_combat_diagnostics", []),
        actor_identity,
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
    native_gameplay_outcome = _native_gameplay_outcome(live_report)
    deterministic["native_gameplay_outcome"] = native_gameplay_outcome
    source_sha256 = hashlib.sha256(source_path.read_bytes()).hexdigest()
    identity = _git_identity()
    run_id = run_id or f"magmaw-jev-{source_sha256[:12]}"
    change_id = change_id or identity["commit"]
    route_review = _route_review(deterministic, expected_route, live_report)
    boss_dps_review = _boss_dps_review(
        deterministic,
        entries,
        live_report,
        actor_identity,
        wcl_reference,
        deterministic["boss_target_duty_context"],
        timeline_comparison,
    )
    boss_dps_review["actor_identity"] = _compact_actor_identity(actor_identity)
    state = {
        "task": "Magmaw 10N bot canary evidence review",
        "authority": "native TrinityCore bot runtime; Jev is shadow analysis only",
        "run_id": run_id,
        "segment_id": segment_id,
        "change": {"id": change_id, "note": change_note},
        "expected_route_nodes": list(expected_route),
        "scope_route_prefix": scope_route_prefix,
        "route_review": route_review,
        "boss_dps_review": boss_dps_review,
        "native_gameplay_outcome": native_gameplay_outcome,
        "baseline": baseline,
    }
    if prepare_only:
        return {"schema_version": 2, "run_id": run_id, "source_sha256": source_sha256,
                "change": {"id": change_id, "git": identity},
                "native_authority": "native_runtime_only", "jev_input": {"state": state},
                "deterministic": deterministic, "jev": {"answers": {}, "status": "not_requested"}}
    group_questions = _jev_questions(
        baseline is not None,
        include_next_fix=False,
        actor_specs=[],
        include_timeline=False,
    )
    group_questions["group_coherence"] = _group_coherence_question()
    group_state = _group_jev_state(state)
    api_key = _jev_key(env_file)
    group_response = _call_jev(group_state, api_key, group_questions)
    group_answers = _answer_summary(group_response)
    responses = [group_response]
    actor_answers: dict[str, Any] = {}
    actor_question_sets: dict[str, dict[str, Any]] = {}
    actor_stage_records: list[dict[str, Any]] = []
    timeline_actors = {
        _as_int(actor.get("bot_guid")): actor
        for actor in (boss_dps_review.get("timeline_comparison") or {}).get(
            "actors", []
        )
        if isinstance(actor, dict) and _as_int(actor.get("bot_guid"))
    }
    for actor in boss_dps_review.get("actor_loss_signals", []):
        if not isinstance(actor, dict) or not _as_int(actor.get("bot_guid")):
            continue
        actor_questions = _jev_questions(
            False,
            include_next_fix=False,
            actor_specs=[actor],
            include_timeline=False,
            include_assignment=False,
        )
        actor_questions = {
            key: value
            for key, value in actor_questions.items()
            if key.startswith("actor_action_")
        }
        if not actor_questions:
            continue
        guid = _as_int(actor.get("bot_guid"))
        actor_state = _actor_jev_state(
            state,
            actor,
            timeline_actors.get(guid),
        )
        actor_response = _call_jev(actor_state, api_key, actor_questions)
        actor_answers.update(_answer_summary(actor_response))
        responses.append(actor_response)
        actor_key = str(guid)
        actor_question_sets[actor_key] = actor_questions
        actor_stage_records.append({
            "stage": "actor_review",
            "bot_guid": guid,
            "class_spec": actor.get("class_spec"),
            "question_ids": sorted(actor_questions),
            "state_sections": sorted(actor_state),
        })

    review_answers = {**group_answers, **actor_answers}
    fix_state = {
        "task": "Magmaw 10N bounded next-fix selection",
        "authority": state.get("authority"),
        "run_id": state.get("run_id"),
        "segment_id": state.get("segment_id"),
        "change": state.get("change"),
        "route_review": state.get("route_review"),
        "native_gameplay_outcome": state.get("native_gameplay_outcome"),
        "baseline": state.get("baseline"),
        "group_timeline": _compact_group_timeline(
            boss_dps_review.get("timeline_comparison")
        ),
        "prior_judgments": review_answers,
    }
    fix_questions = {"next_fix": _next_fix_question()}
    fix_response = _call_jev(fix_state, api_key, fix_questions)
    responses.append(fix_response)
    answers = {**review_answers, **_answer_summary(fix_response)}
    questions = dict(group_questions)
    for actor_questions in actor_question_sets.values():
        questions.update(actor_questions)
    questions.update(fix_questions)
    stage_records = [{
        "stage": "group_review",
        "question_ids": sorted(group_questions),
        "state_sections": sorted(group_state),
    }]
    stage_records.extend(actor_stage_records)
    stage_records.append({
        "stage": "next_fix",
        "question_ids": sorted(fix_questions),
        "state_sections": sorted(fix_state),
    })
    confidences = [
        _as_float(answer.get("confidence"))
        for answer in answers.values()
        if isinstance(answer, dict) and "confidence" in answer
    ]
    confidences.extend(
        max(_as_float(answer.get("noul")), 1.0 - _as_float(answer.get("noul")))
        for answer in answers.values()
        if isinstance(answer, dict) and "noul" in answer
    )
    low_confidence = sorted(
        key for key, answer in answers.items()
        if isinstance(answer, dict)
        and (
            ("confidence" in answer and _as_float(answer.get("confidence")) < JEV_CONFIDENCE_FLOOR)
            or (
                "noul" in answer
                and max(_as_float(answer.get("noul")), 1.0 - _as_float(answer.get("noul")))
                < JEV_CONFIDENCE_FLOOR
            )
        )
    )
    usage: dict[str, Any] = {}
    for response in responses:
        response_usage = response.get("usage")
        if not isinstance(response_usage, dict):
            continue
        for key, value in response_usage.items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + value
            elif key not in usage:
                usage[key] = value
    question_sets_by_stage: dict[str, dict[str, Any]] = {
        "group_review": group_questions,
    }
    question_sets_by_stage.update({
        f"actor_review_{guid}": question_set
        for guid, question_set in actor_question_sets.items()
    })
    question_sets_by_stage["next_fix"] = fix_questions
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
        "native_gameplay_outcome": native_gameplay_outcome,
        "jev": {
            "model": group_response.get("model", JEV_MODEL),
            "answers": answers,
            "usage": usage,
            "question_ids": sorted(questions),
            "request_stages": stage_records,
            "confidence_floor": JEV_CONFIDENCE_FLOOR,
            "low_confidence_questions": low_confidence,
            "minimum_confidence": min(confidences) if confidences else None,
        },
        "jev_input": {
            "state": state,
            "question_contract": {
                stage: {
                    question_id: {
                        "type": question.get("type"),
                        "criteria": sorted(question.get("criteria", {})),
                    }
                    for question_id, question in question_set.items()
                }
                for stage, question_set in question_sets_by_stage.items()
            },
            "typed_answer_fields": {
                "choice": ["type", "choice", "confidence", "probabilities"],
                "noul": ["type", "noul"],
            },
        },
        "deterministic": deterministic,
        "baseline": baseline,
        "progress": {
            "stuck_behaviors_observed": deterministic["stuck_behaviors"],
            "active_stuck_behaviors": deterministic["active_stuck_behaviors"],
            "resolved_stuck_behavior_counts": deterministic["resolved_stuck_behavior_counts"],
            "actor_action_judgments": {
                key: value
                for key, value in answers.items()
                if key.startswith("actor_action_")
            },
            "actor_assignment_judgments": {
                key: value
                for key, value in answers.items()
                if key.startswith("actor_assignment_")
            },
            "group_coherence": answers.get("group_coherence"),
            "actor_action_gate": _actor_action_gate(answers),
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
    parser.add_argument("--combat-log", type=Path, help="optional combat_log.json; auto-discovered beside a run directory")
    parser.add_argument("--native-log", type=Path, help="optional worldserver_output.log for native encounter diagnostics; auto-discovered beside a run directory")
    parser.add_argument(
        "--timeline-comparison",
        type=Path,
        help="optional all-actor WCL-vs-bot timeline comparison JSON",
    )
    parser.add_argument(
        "--wcl-reference",
        type=Path,
        default=DEFAULT_WCL_REFERENCE,
        help="compact, repository-tracked WCL comparison context",
    )
    parser.add_argument("--env-file", type=Path, default=Path(".env"), help="file containing the mandatory JEV key")
    parser.add_argument("--prepare-only", action="store_true", help="deterministic review only; no key or model request")
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
            combat_log_path=args.combat_log,
            native_log_path=args.native_log,
            scope_route_prefix=args.scope_route_prefix,
            wcl_reference_path=args.wcl_reference,
            timeline_comparison_path=args.timeline_comparison,
            prepare_only=args.prepare_only,
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

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
        for key in ("diagnosis", "status", "raid_runtime", "roster", "members", "bots", "admission_receipt"):
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
        "reason_code",
        "retry_reason",
    )
    return [
        {key: row[key] for key in allowed if key in row}
        for row in rows
        if isinstance(row, dict)
    ]


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
            result.append(
                {
                    "bot_guid": item["bot_guid"],
                    "class_spec": item["class_spec"],
                    "reason": item["reason"],
                    "count": item["count"],
                    "action_categories": sorted(item["action_categories"]),
                    "spell_ids": sorted(item["spell_ids"])[:4],
                }
            )
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
    non_failure_rows: list[dict[str, Any]] = []
    actionable_rows: list[dict[str, Any]] = []
    reason_counts: Counter[str] = Counter()
    expected_count = 0
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
        "candidate_scan_count": expected_count + non_failure_count + actionable_count,
        "expected_profile_wait_count": expected_count,
        "expected_profile_wait_reasons": reason_summary(expected_rows),
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
            "elapsed_party_dps",
            "elapsed_party_hps",
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
        result["elapsed_party_dps_basis"] = "wall_clock_duration_seconds"
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
        if isinstance(elapsed, (int, float)):
            actor["elapsed_dps_delta_vs_wcl"] = float(elapsed) - float(observed)
        if isinstance(active, (int, float)):
            actor["active_dps_delta_vs_wcl"] = float(active) - float(observed)
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
                    "active_dps",
                    "elapsed_dps",
                    "active_seconds",
                    "damage_uptime",
                    "wcl_observed_dps",
                    "elapsed_dps_delta_vs_wcl",
                )
                if key in actor
            }
            support_actors.append(support)
    result["actors"] = dps_actors
    result["support_actors"] = support_actors
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


def _boss_dps_review(
    deterministic: dict[str, Any],
    entries: list[dict[str, Any]],
    live_report: dict[str, Any] | None,
    actor_identity: Mapping[str, dict[str, Any]] | None,
    wcl_reference: dict[str, Any] | None,
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
    return {
        "scope_route_node": DEFAULT_BOSS_ROUTE[0],
        "combat_metrics": metrics,
        "combat_diagnostics": deterministic.get("boss_combat_diagnostics", []),
        "action_outcomes": _compact_jev_action_outcomes(
            native_action_outcomes
        ),
        "native_outcome_summary": native_outcome_summary,
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
        # Only gates outside the expected profile-wait set are sent as the
        # short candidate list. The complete native rows remain in the
        # deterministic report for local audit and replay.
        "candidate_rejections": candidate_signal["actionable_candidate_groups"],
        "candidate_rejection_summary": candidate_signal,
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
            "trace_capture": trace_capture,
            "interpretation": "full_window_native_aggregate_is_authoritative_when_present; retained_tail_is_missing_capture_not_proof_of_no_rejection",
        },
        "trace_capture": trace_capture,
        "wcl_reference": wcl_reference,
    }


def _jev_questions(
    has_baseline: bool,
    *,
    include_next_fix: bool = True,
) -> dict[str, dict[str, Any]]:
    questions: dict[str, dict[str, Any]] = {
        "path_consistency": {
            "type": "choice",
            "instructions": "Classify the route_review only. Use route generations and native terminal evidence: many decisions within one generation are normal and are not route repetition. The retained route-node sample can omit a node after it completed, so route_nodes_observed is not authoritative by itself. If route_acceptance.complete_native_terminal_evidence and route_acceptance.observed_order_monotonic are true, with no route_repeated_nodes, route_unexpected, or active unresolved route event, choose aligned even when the sampled node list has a gap. Use loop_or_gap only for explicit route reversal, repeated route generation, unexpected node, or missing native terminal evidence. Treat an ordered prefix as acceptable for a segment canary. Use native_gameplay_outcome as the gameplay authority; never treat certification_status=uncertified or acceptable_final_evidence=false by itself as a native wipe. If the live report has zero active bots or zero native trace rows, choose insufficient_evidence.",
            "criteria": {
                "aligned": "Observed route is ordered and the current segment has no unexplained loop or gap.",
                "ordered_segment": "The trace is an ordered, intentionally partial segment and is not enough to judge a full clear.",
                "loop_or_gap": "The trace shows repeated decisions, route reversal, missing expected handoff, or unexplained path churn.",
                "insufficient_evidence": "There are too few native trace rows to compare the path safely.",
            },
        },
        "stuck_behavior": {
            "type": "choice",
            "instructions": "Classify the primary currently-unresolved behavior from route_review. Prefer active_stuck_behavior_counts and active_stuck_behaviors, which are restricted to the latest non-terminal route generation. Treat raw stuck_behavior_counts and resolved_stuck_behavior_counts as historical progress evidence, not an active blocker, when native route terminal evidence proves that node completed. When active_bots is zero and the run says admission failed or the pool was underfilled, choose lifecycle. Choose none when the run admitted bots, the active stuck set is empty, and no native unresolved route event remains. A clear native_gameplay_outcome with certification_status=uncertified is not a stuck or wipe result.",
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
            "instructions": "Classify the most actionable DPS loss area from boss_dps_review only. Compare elapsed_party_dps with active party_dps, inspect every DPS actor's elapsed_dps, active_dps, damage_uptime, movement, abilities, native_outcome_summary, native_outcome_signal, action_outcomes, candidate_rejection_summary, candidate_rejections, and decision_outcomes. Native action outcomes are the authority for submitted-action loss. Candidate rejections are profile-search counts: the summary separates expected waits and conditional profile gates from a small actionable candidate list. Do not infer action_rejection from expected candidate-wait volume, conditional profile gates, or candidate rows alone; require corroborating no_action, cast_failed, no_line_of_sight, out_of_range, or repeated native backoff outcomes at material per-actor frequency. When native_outcome_signal.actionable_failure_ratio is low (below roughly 0.10) for every DPS actor and the active stuck set is empty, do not choose action_rejection as the dominant loss; use movement, uptime, or no_material_loss based on the actor metrics. Prefer an attributable execution loss over a generic rotation explanation. Route stuck counters are historical unless route_review marks them active. If active_bots is zero or boss combat metrics are unavailable, choose insufficient_data and never infer action_rejection from a missing action log.",
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
        "canary_safe_to_promote": {
            "type": "noul",
            "instructions": "Is this evidence safe to promote as a successful Magmaw canary result? Use native_gameplay_outcome first. A native clear with certification_status=uncertified is a valid diagnostic clear but is not promotable; do not call it a wipe.",
            "criteria": {
                "true": "native_gameplay_outcome.status is clear, certification_status is accepted, the route evidence is attributable, and no death/repetition guardrail fired.",
                "false": "The native outcome is incomplete, wiped, stalled, or clear only with certification_status=uncertified. An uncertified clear is not a wipe.",
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
    if include_next_fix:
        questions["next_fix"] = _next_fix_question()
    return questions


def _next_fix_question() -> dict[str, Any]:
    return {
        "type": "choice",
        "instructions": "Choose one bounded next engineering action after reviewing the typed evidence judgments and both named evidence views. Keep gameplay authority native and use the smallest fix that addresses the evidenced failure. If admission or lifecycle prevented bots from starting, choose admission_lifecycle. If boss_dps_review contains repeated native candidate rejection after admission, prefer shared_arbitration or rotation_profile over movement_recovery unless movement is the direct blocker. Do not choose a class rotation fix when the evidence only shows a shared movement or target lease failure.",
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
        "elapsed_party_dps": metrics.get("elapsed_party_dps"),
        "combat_seconds": metrics.get("combat_seconds"),
        "duration_sec": metrics.get("duration_sec"),
        "boss_dps_review": report.get("jev_input", {}).get("state", {}).get(
            "boss_dps_review", {}
        ),
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
    wcl_reference_path: Path | None = None,
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
    actor_identity = _actor_identity(live_report)
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
    analysis_path = combat_analysis_path or discovered_analysis
    if analysis_path and analysis_path.exists():
        analysis = _load_json(analysis_path)
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
        "reference_context": wcl_reference,
        "baseline": baseline,
    }
    review_questions = _jev_questions(
        baseline is not None,
        include_next_fix=False,
    )
    api_key = _jev_key(env_file)
    review_response = _call_jev(state, api_key, review_questions)
    review_answers = _answer_summary(review_response)
    fix_state = dict(state)
    fix_state["prior_judgments"] = review_answers
    fix_questions = {"next_fix": _next_fix_question()}
    fix_response = _call_jev(fix_state, api_key, fix_questions)
    answers = {**review_answers, **_answer_summary(fix_response)}
    questions = {**review_questions, **fix_questions}
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
    for response in (review_response, fix_response):
        response_usage = response.get("usage")
        if not isinstance(response_usage, dict):
            continue
        for key, value in response_usage.items():
            if isinstance(value, (int, float)):
                usage[key] = usage.get(key, 0) + value
            elif key not in usage:
                usage[key] = value
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
            "model": review_response.get("model", JEV_MODEL),
            "answers": answers,
            "usage": usage,
            "question_ids": sorted(questions),
            "request_stages": [
                {
                    "stage": "evidence_review",
                    "question_ids": sorted(review_questions),
                    "state_sections": sorted(state),
                },
                {
                    "stage": "next_fix",
                    "question_ids": sorted(fix_questions),
                    "state_sections": sorted(fix_state),
                },
            ],
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
                for stage, question_set in (
                    ("evidence_review", review_questions),
                    ("next_fix", fix_questions),
                )
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
    parser.add_argument(
        "--wcl-reference",
        type=Path,
        default=DEFAULT_WCL_REFERENCE,
        help="compact, repository-tracked WCL comparison context",
    )
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
            wcl_reference_path=args.wcl_reference,
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

"""Build a compact, reproducible role-efficiency audit from a live bot report."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


COMBAT_EVENT_ACTIONS = {
    "boss_action",
    "trash_action",
    "validation_route_boss_action",
    "validation_route_trash_action",
    "validation_route_group_heal",
}
SCHEDULING_RESULTS = {"casting", "global_cooldown", "cooldown", "throttled"}
FAILURE_RESULTS = {
    "bad_spell",
    "cast_failed",
    "dead_target",
    "invalid_target",
    "no_line_of_sight",
    "no_mana",
    "out_of_range",
}

REQUIRED_ROTATION_GROUPS = {
    "Scvaltank": [{53595}, {26573}, {31935}, {53600}],
    "Scvaldpsa": [{44457}, {133}, {92315, 11366}, {11129}],
    "Scvaldpsb": [{1978}, {53209}, {56641}, {19434, 3044}, {3045}],
    "Scvaldpsc": [{17364}, {60103}, {8050}, {73680}, {403, 421}, {51533}],
}


def _role(entry: dict[str, Any]) -> str:
    goal = entry.get("role_goal", "")
    if goal.startswith("survive_hold_threat"):
        return "tank"
    if goal.startswith("keep_group_alive"):
        return "healer"
    return "dps"


def _unique_trace(report: dict[str, Any]) -> list[dict[str, Any]]:
    entries = report.get("trace", {}).get("entries", [])
    unique: dict[tuple[int, int], dict[str, Any]] = {}
    for entry in entries:
        unique[(int(entry.get("bot_guid", 0)), int(entry.get("sequence", 0)))] = entry
    return sorted(unique.values(), key=lambda item: (item.get("timestamp_ms", 0), item.get("bot_guid", 0)))


def _actual_attempts(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    attempts: dict[tuple[int, int], dict[str, Any]] = {}
    for entry in entries:
        attempt = entry.get("combat_attempt") or {}
        recorded_at = int(attempt.get("recorded_at_ms", 0))
        if recorded_at:
            attempts[(int(entry.get("bot_guid", 0)), recorded_at)] = entry
        elif entry.get("action") in COMBAT_EVENT_ACTIONS and attempt.get("phase"):
            # Legacy reports did not timestamp the attempt. Event timestamps are
            # the least ambiguous fallback and same-tick duplicate events collapse.
            attempts[(int(entry.get("bot_guid", 0)), int(entry.get("timestamp_ms", 0)))] = entry
    return sorted(attempts.values(), key=lambda item: (item.get("timestamp_ms", 0), item.get("bot_guid", 0)))


def build_audit(report: dict[str, Any], source_hash: str) -> dict[str, Any]:
    entries = _unique_trace(report)
    attempts = _actual_attempts(entries)
    names = sorted({entry.get("bot_name", "") for entry in entries if entry.get("bot_name")})
    role_by_name = {name: _role(next(entry for entry in entries if entry.get("bot_name") == name)) for name in names}

    attempts_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    entries_by_name: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for entry in attempts:
        attempts_by_name[entry.get("bot_name", "")].append(entry)
    for entry in entries:
        entries_by_name[entry.get("bot_name", "")].append(entry)

    bots: list[dict[str, Any]] = []
    for name in names:
        bot_attempts = attempts_by_name[name]
        result_counts = Counter(
            (entry.get("combat_attempt") or {}).get("failure", {}).get("result", "unknown")
            for entry in bot_attempts
        )
        spell_counts = Counter(
            int((entry.get("combat_attempt") or {}).get("action", {}).get("spell_id", 0))
            for entry in bot_attempts
            if int((entry.get("combat_attempt") or {}).get("action", {}).get("spell_id", 0))
        )
        successes = result_counts["ok"]
        failures = sum(result_counts[result] for result in FAILURE_RESULTS)
        scheduling = sum(result_counts[result] for result in SCHEDULING_RESULTS)
        no_action = result_counts["no_action"]
        scheduling_no_action = sum(
            (entry.get("combat_attempt") or {}).get("failure", {}).get("result") == "no_action"
            and bool((entry.get("combat_attempt") or {}).get("failure", {}).get("gates", {}).get("casting"))
            for entry in bot_attempts
        )
        actionable = successes + failures
        total = len(bot_attempts)

        uptime_samples = [
            (entry.get("combat_attempt") or {}).get("uptime", {})
            for entry in bot_attempts
            if (entry.get("combat_attempt") or {}).get("uptime")
        ]
        passive_active = sum(
            bool(sample.get("melee_auto_attacking"))
            or bool(sample.get("ranged_auto_active"))
            or bool(sample.get("pet_attacking"))
            for sample in uptime_samples
        )
        active_attempts = sum(
            (
                (entry.get("combat_attempt") or {}).get("failure", {}).get("result") == "ok"
                or (entry.get("combat_attempt") or {}).get("failure", {}).get("result") in SCHEDULING_RESULTS
                or (
                    (entry.get("combat_attempt") or {}).get("failure", {}).get("result") == "no_action"
                    and bool((entry.get("combat_attempt") or {}).get("failure", {}).get("gates", {}).get("casting"))
                )
                or bool((entry.get("combat_attempt") or {}).get("uptime", {}).get("melee_auto_attacking"))
                or bool((entry.get("combat_attempt") or {}).get("uptime", {}).get("ranged_auto_active"))
                or bool((entry.get("combat_attempt") or {}).get("uptime", {}).get("pet_attacking"))
            )
            for entry in bot_attempts
        )

        tank_samples = []
        all_hostile_samples: list[tuple[int, int, int]] = []
        if role_by_name[name] == "tank":
            bot_guid = next(int(entry.get("bot_guid", 0)) for entry in entries_by_name[name])
            seen_ticks: set[int] = set()
            for entry in entries_by_name[name]:
                tick = int(entry.get("timestamp_ms", 0))
                progress = entry.get("route_progress") or {}
                target = progress.get("target") or {}
                victim = int((progress.get("state") or {}).get("victim_guid", 0))
                if tick not in seen_ticks and victim and float(target.get("hp_pct", 0.0)) > 0.0:
                    seen_ticks.add(tick)
                    tank_samples.append(victim == bot_guid)
                threat = entry.get("threat_snapshot") or {}
                engaged = int(threat.get("engaged_hostiles", 0))
                if engaged:
                    all_hostile_samples.append(
                        (engaged, int(threat.get("tank_owned_hostiles", 0)), int(threat.get("healer_targeting_hostiles", 0)))
                    )

        healer_dwell_ms = 0
        dwell_start = None
        dwell_last = None
        for entry in entries_by_name[name] if role_by_name[name] == "tank" else []:
            threat = entry.get("threat_snapshot") or {}
            timestamp = int(entry.get("timestamp_ms", 0))
            if int(threat.get("healer_targeting_hostiles", 0)) > 0:
                if dwell_start is None or (dwell_last is not None and timestamp - dwell_last > 3000):
                    dwell_start = timestamp
                dwell_last = timestamp
                healer_dwell_ms = max(healer_dwell_ms, max(0, timestamp - dwell_start))
            else:
                dwell_start = None
                dwell_last = None

        healer_attempts = [
            entry for entry in bot_attempts if (entry.get("combat_attempt") or {}).get("phase") == "heal_cast"
        ]
        healer_success = sum(
            (entry.get("combat_attempt") or {}).get("failure", {}).get("result") == "ok"
            for entry in healer_attempts
        )

        bots.append(
            {
                "bot_name": name,
                "role": role_by_name[name],
                "deaths": sum(entry.get("action") == "death" for entry in entries_by_name[name]),
                "attempts": total,
                "result_counts": dict(sorted(result_counts.items())),
                "successful_submission_rate": round(successes / actionable, 4) if actionable else None,
                "active_action_coverage": round(active_attempts / total, 4) if total else None,
                "cast_failure_rate": round(failures / actionable, 4) if actionable else None,
                "passive_uptime_rate": round(passive_active / len(uptime_samples), 4) if uptime_samples else None,
                "tank_threat_retention_rate": round(sum(tank_samples) / len(tank_samples), 4) if tank_samples else None,
                "tank_all_hostile_retention_rate": round(
                    sum(owned for _engaged, owned, _healer in all_hostile_samples)
                    / sum(engaged for engaged, _owned, _healer in all_hostile_samples),
                    4,
                ) if all_hostile_samples else None,
                "healer_target_exposure_rate": round(
                    sum(healer for _engaged, _owned, healer in all_hostile_samples)
                    / sum(engaged for engaged, _owned, _healer in all_hostile_samples),
                    4,
                ) if all_hostile_samples else None,
                "max_healer_target_dwell_ms": healer_dwell_ms if all_hostile_samples else None,
                "heal_cast_success_rate": round(healer_success / len(healer_attempts), 4) if healer_attempts else None,
                "pet_alive_rate": round(
                    sum(bool(entry.get("pet_alive")) for entry in entries_by_name[name] if int((entry.get("threat_snapshot") or {}).get("engaged_hostiles", 0)) > 0)
                    / len([entry for entry in entries_by_name[name] if int((entry.get("threat_snapshot") or {}).get("engaged_hostiles", 0)) > 0]),
                    4,
                ) if name == "Scvaldpsb" and any(int((entry.get("threat_snapshot") or {}).get("engaged_hostiles", 0)) > 0 for entry in entries_by_name[name]) else None,
                "missing_rotation_groups": [
                    sorted(group) for group in REQUIRED_ROTATION_GROUPS.get(name, []) if not group.intersection(spell_counts)
                ],
                "top_spell_mix": [
                    {"spell_id": spell_id, "attempts": count}
                    for spell_id, count in spell_counts.most_common(12)
                ],
            }
        )

    failures: list[str] = []
    for bot in bots:
        if bot["role"] != "healer" and (bot["active_action_coverage"] is None or bot["active_action_coverage"] < 0.70):
            failures.append(f"{bot['bot_name']}:active_action_coverage")
        if bot["cast_failure_rate"] is not None and bot["cast_failure_rate"] > 0.05:
            failures.append(f"{bot['bot_name']}:cast_failure_rate")
        if bot["role"] == "tank" and (bot["tank_threat_retention_rate"] is None or bot["tank_threat_retention_rate"] < 0.90):
            failures.append(f"{bot['bot_name']}:tank_threat_retention")
        if bot["role"] == "healer" and bot["heal_cast_success_rate"] is not None and bot["heal_cast_success_rate"] < 0.95:
            failures.append(f"{bot['bot_name']}:heal_cast_success_rate")
        if bot["bot_name"] in REQUIRED_ROTATION_GROUPS and bot["deaths"]:
            failures.append(f"{bot['bot_name']}:death_free")
        if bot["missing_rotation_groups"]:
            failures.append(f"{bot['bot_name']}:required_rotation_coverage")
        if bot["bot_name"] == "Scvaltank":
            if bot["tank_all_hostile_retention_rate"] is None or bot["tank_all_hostile_retention_rate"] < 0.98:
                failures.append("Scvaltank:all_hostile_threat_retention")
            if bot["healer_target_exposure_rate"] is None or bot["healer_target_exposure_rate"] > 0.01:
                failures.append("Scvaltank:healer_target_exposure")
            if bot["max_healer_target_dwell_ms"] is None or bot["max_healer_target_dwell_ms"] > 3000:
                failures.append("Scvaltank:healer_target_dwell")
        if bot["bot_name"] == "Scvaldpsb" and (bot["pet_alive_rate"] is None or bot["pet_alive_rate"] < 0.90):
            failures.append("Scvaldpsb:pet_alive_rate")

    hazard_exit_actions = sum(entry.get("action") == "move_out_of_hazard" for entry in entries)
    hazard_exit_failures = sum(entry.get("action") == "hold_hazard_exit_failed" for entry in entries)
    if REQUIRED_ROTATION_GROUPS.keys() <= set(names):
        if int(report.get("status", {}).get("deaths") or 0) > 0:
            failures.append("party:death_free")
        if int(report.get("status", {}).get("stuck") or 0) > 0:
            failures.append("party:stuck_free")
        if hazard_exit_actions < 2:
            failures.append("party:hazard_activation_coverage")
        if hazard_exit_failures:
            failures.append("party:hazard_exit_failure")

    status = report.get("status", {})
    return {
        "schema": "stonecore_role_efficiency_v2",
        "source_report_sha256": source_hash,
        "legacy_attempt_timestamps": not any(
            int((entry.get("combat_attempt") or {}).get("recorded_at_ms", 0)) for entry in entries
        ),
        "run": {
            "duration_seconds": status.get("duration_seconds"),
            "kills": status.get("kills"),
            "deaths": status.get("deaths"),
            "route_index": (status.get("validation_route") or {}).get("manifest_index"),
            "route_count": (status.get("validation_route") or {}).get("manifest_count"),
        },
        "bots": bots,
        "mechanics": {
            "hazard_exit_actions": hazard_exit_actions,
            "hazard_exit_failures": hazard_exit_failures,
        },
        "passed": not failures and len(bots) == 5,
        "failure_labels": failures + ([] if len(bots) == 5 else ["expected_five_role_bots"]),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("report", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    raw = args.report.read_bytes()
    audit = build_audit(json.loads(raw), hashlib.sha256(raw).hexdigest())
    rendered = json.dumps(audit, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0 if audit["passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())

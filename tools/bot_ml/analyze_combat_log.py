#!/usr/bin/env python3
"""Build compact Warcraft Logs-like combat summaries from bot combat telemetry."""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


RANGED_CLASS_IDS = {3, 5, 8, 9}
KNOWN_AVOIDABLE_KEYWORDS = (
    "flay",
    "fissure",
    "lava",
    "gravity well",
    "ground",
    "eruption",
    "shatter",
)


def _number(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _weighted_average(rows: list[dict[str, Any]], field: str) -> float:
    weight = sum(int(row.get("event_count") or 0) for row in rows)
    if not weight:
        return 0.0
    return sum(_number(row.get(field)) * int(row.get("event_count") or 0) for row in rows) / weight


def _ability_rows(rows: list[dict[str, Any]], total_damage: int) -> list[dict[str, Any]]:
    grouped: dict[tuple[int, str, bool, int, str], dict[str, Any]] = {}
    for row in rows:
        key = (
            int(row.get("spell_id") or 0),
            str(row.get("spell_name") or "Unknown"),
            bool(row.get("source_is_pet")),
            int(row.get("source_entry") or 0),
            str(row.get("source_name") or ""),
        )
        target = grouped.setdefault(
            key,
            {
                "spell_id": key[0],
                "spell_name": key[1],
                "source_is_pet": key[2],
                "source_entry": key[3],
                "source_name": key[4],
                "damage": 0,
                "events": 0,
                "moving_events": 0,
                "distance_weighted": 0.0,
            },
        )
        events = int(row.get("event_count") or 0)
        target["damage"] += int(row.get("amount") or 0)
        target["events"] += events
        target["moving_events"] += int(row.get("moving_events") or 0)
        target["distance_weighted"] += _number(row.get("distance_avg")) * events

    abilities: list[dict[str, Any]] = []
    for row in grouped.values():
        events = max(1, int(row.pop("events")))
        moving_events = int(row.pop("moving_events"))
        distance_weighted = float(row.pop("distance_weighted"))
        row["events"] = events
        row["damage_share"] = round(int(row["damage"]) / max(1, total_damage), 6)
        row["moving_fraction"] = round(moving_events / events, 6)
        row["distance_avg"] = round(distance_weighted / events, 3)
        abilities.append(row)
    return sorted(abilities, key=lambda row: (-int(row["damage"]), int(row["spell_id"])))


def analyze_combat_log(combat_log: dict[str, Any]) -> dict[str, Any]:
    """Return encounter, DPS/HPS, rotation, pet, and positioning diagnostics."""
    abilities = [row for row in combat_log.get("abilities") or [] if isinstance(row, dict)]
    buckets = [row for row in combat_log.get("second_buckets") or [] if isinstance(row, dict)]
    by_generation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in abilities:
        by_generation[int(row.get("route_generation") or 0)].append(row)

    bucket_seconds: dict[tuple[int, int, str, bool], set[int]] = defaultdict(set)
    for row in buckets:
        if int(row.get("amount") or 0) > 0:
            bucket_seconds[
                (
                    int(row.get("route_generation") or 0),
                    int(row.get("actor_guid") or 0),
                    str(row.get("perspective") or ""),
                    bool(row.get("source_is_pet")),
                )
            ].add(int(row.get("second") or 0))

    encounters: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for generation in sorted(by_generation):
        rows = by_generation[generation]
        timestamps = [int(row.get("first_at_ms") or 0) for row in rows] + [int(row.get("last_at_ms") or 0) for row in rows]
        timestamps = [value for value in timestamps if value > 0]
        first_ms = min(timestamps, default=0)
        last_ms = max(timestamps, default=first_ms)
        duration_sec = max(1.0, (last_ms - first_ms) / 1000.0)
        party_damage_seconds: set[int] = set()
        for (bucket_generation, _actor_guid, perspective, _source_is_pet), seconds in bucket_seconds.items():
            if bucket_generation == generation and perspective == "damage_done":
                party_damage_seconds.update(seconds)
        combat_seconds = max(1, len(party_damage_seconds))
        node_id = next((str(row.get("route_node_id") or "") for row in rows if row.get("route_node_id")), "")
        label = next((str(row.get("route_label") or "") for row in rows if row.get("route_label")), "")

        actor_guids = sorted({int(row.get("actor_guid") or 0) for row in rows if int(row.get("actor_guid") or 0)})
        actors: list[dict[str, Any]] = []
        for actor_guid in actor_guids:
            actor_rows = [row for row in rows if int(row.get("actor_guid") or 0) == actor_guid]
            done = [row for row in actor_rows if row.get("perspective") == "damage_done"]
            taken = [row for row in actor_rows if row.get("perspective") == "damage_taken"]
            healing = [row for row in actor_rows if row.get("perspective") == "healing_done"]
            total_damage = sum(int(row.get("amount") or 0) for row in done)
            total_taken = sum(int(row.get("amount") or 0) for row in taken)
            total_healing = sum(int(row.get("amount") or 0) for row in healing)
            active_seconds = len(bucket_seconds[(generation, actor_guid, "damage_done", False)])
            pet_active_seconds = len(bucket_seconds[(generation, actor_guid, "damage_done", True)])
            healing_seconds = len(bucket_seconds[(generation, actor_guid, "healing_done", False)])
            ability_summary = _ability_rows(done, total_damage)
            actor_name = next((str(row.get("actor_name") or "") for row in actor_rows if row.get("actor_name")), "")
            actor_role = next((str(row.get("actor_role") or "") for row in actor_rows if row.get("actor_role")), "")
            actor_class_id = next((int(row.get("actor_class_id") or 0) for row in actor_rows if row.get("actor_class_id")), 0)
            pet_damage = sum(int(row["damage"]) for row in ability_summary if row.get("source_is_pet"))
            player_damage = total_damage - pet_damage
            player_done = [row for row in done if not row.get("source_is_pet")]
            actor_report = {
                "actor_guid": actor_guid,
                "actor_name": actor_name,
                "actor_role": actor_role,
                "actor_class_id": actor_class_id,
                "damage": total_damage,
                "dps": round(total_damage / combat_seconds, 3),
                "elapsed_dps": round(total_damage / duration_sec, 3),
                "active_seconds": active_seconds,
                "active_dps": round(player_damage / max(1, active_seconds), 3),
                "damage_uptime": round(active_seconds / combat_seconds, 6),
                "damage_taken": total_taken,
                "healing": total_healing,
                "hps": round(total_healing / combat_seconds, 3),
                "elapsed_hps": round(total_healing / duration_sec, 3),
                "healing_active_seconds": healing_seconds,
                "pet_damage": pet_damage,
                "pet_damage_share": round(pet_damage / max(1, total_damage), 6),
                "pet_active_seconds": pet_active_seconds,
                "pet_active_dps": round(pet_damage / max(1, pet_active_seconds), 3),
                "pet_uptime": round(pet_active_seconds / combat_seconds, 6),
                "distance_avg": round(_weighted_average(player_done, "distance_avg"), 3),
                "moving_fraction": round(_weighted_average(player_done, "moving_fraction"), 6),
                "abilities": ability_summary,
                "damage_taken_sources": _ability_rows(taken, total_taken)[:10],
            }
            actors.append(actor_report)

            non_pet = [row for row in ability_summary if not row.get("source_is_pet") and int(row.get("damage") or 0) > 0]
            non_pet_events = sum(int(row.get("events") or 0) for row in non_pet)
            if actor_role == "dps" and non_pet_events >= 20 and len(non_pet) < 3:
                diagnostics.append({
                    "severity": "warning",
                    "kind": "rotation_low_variety",
                    "route_generation": generation,
                    "route_node_id": node_id,
                    "actor_guid": actor_guid,
                    "actor_name": actor_name,
                    "damaging_abilities": len(non_pet),
                })
            if non_pet_events >= 20 and non_pet and float(non_pet[0].get("damage_share") or 0) >= 0.75:
                diagnostics.append({
                    "severity": "warning",
                    "kind": "single_ability_damage_dominance",
                    "route_generation": generation,
                    "route_node_id": node_id,
                    "actor_guid": actor_guid,
                    "actor_name": actor_name,
                    "spell_id": non_pet[0]["spell_id"],
                    "spell_name": non_pet[0]["spell_name"],
                    "damage_share": non_pet[0]["damage_share"],
                })
            if actor_role == "dps" and combat_seconds >= 10 and total_damage > 0 and active_seconds / combat_seconds < 0.35:
                diagnostics.append({
                    "severity": "warning",
                    "kind": "low_damage_uptime",
                    "route_generation": generation,
                    "route_node_id": node_id,
                    "actor_guid": actor_guid,
                    "actor_name": actor_name,
                    "damage_uptime": round(active_seconds / combat_seconds, 6),
                })
            non_pet_event_count = sum(int(row.get("event_count") or 0) for row in done if not row.get("source_is_pet"))
            if actor_class_id in RANGED_CLASS_IDS and non_pet_event_count >= 10 and _weighted_average(player_done, "distance_avg") < 8.0:
                diagnostics.append({
                    "severity": "warning",
                    "kind": "ranged_damage_too_close",
                    "route_generation": generation,
                    "route_node_id": node_id,
                    "actor_guid": actor_guid,
                    "actor_name": actor_name,
                    "distance_avg": round(_weighted_average(player_done, "distance_avg"), 3),
                })

            avoidable_damage = sum(
                int(row.get("amount") or 0)
                for row in taken
                if any(keyword in str(row.get("spell_name") or "").lower() for keyword in KNOWN_AVOIDABLE_KEYWORDS)
            )
            if avoidable_damage:
                diagnostics.append({
                    "severity": "warning",
                    "kind": "known_avoidable_damage_taken",
                    "route_generation": generation,
                    "route_node_id": node_id,
                    "actor_guid": actor_guid,
                    "actor_name": actor_name,
                    "amount": avoidable_damage,
                })

        actors.sort(key=lambda row: (-int(row["damage"]), int(row["actor_guid"])))
        party_damage = sum(int(row["damage"]) for row in actors)
        party_healing = sum(int(row["healing"]) for row in actors)
        encounters.append({
            "route_generation": generation,
            "route_node_id": node_id,
            "route_label": label,
            "first_at_ms": first_ms,
            "last_at_ms": last_ms,
            "duration_sec": round(duration_sec, 3),
            "combat_duration_sec": combat_seconds,
            "party_damage": party_damage,
            "party_dps": round(party_damage / combat_seconds, 3),
            "elapsed_party_dps": round(party_damage / duration_sec, 3),
            "party_healing": party_healing,
            "party_hps": round(party_healing / combat_seconds, 3),
            "elapsed_party_hps": round(party_healing / duration_sec, 3),
            "party_damage_taken": sum(int(row["damage_taken"]) for row in actors),
            "actors": actors,
        })

    return {
        "schema": "bot_combat_analysis_v2",
        "source_schema_version": combat_log.get("combat_log_schema_version"),
        "tracked_event_count": int(combat_log.get("event_count") or 0),
        "aggregate_count": int(combat_log.get("aggregate_count") or len(abilities)),
        "second_bucket_count": int(combat_log.get("second_bucket_count") or len(buckets)),
        "recent_event_count": len(combat_log.get("recent_events") or []),
        "recent_events_dropped": int(combat_log.get("recent_events_dropped") or 0),
        "all_events_preserved_in_aggregates": True,
        "encounters": encounters,
        "diagnostics": diagnostics,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Combat-log JSON or live-validation report JSON")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    payload = json.loads(args.input.read_text(encoding="utf-8"))
    combat_log = payload.get("combat_log") if isinstance(payload.get("combat_log"), dict) else payload
    report = analyze_combat_log(combat_log)
    rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compare every Magmaw actor's bot timeline with a compact WCL cast timeline.

The two sides intentionally keep different event semantics:

* WCL contributes completed player casts.
* Trinity contributes landed, positive damage observations from the native
  combat log.

Those are not interchangeable event types.  The report exposes both cadence
views, their normalized first-to-first window, the largest bot gaps, and the
encounter-window DPS result.  It never turns a missing WCL reference into a
passing actor and never treats a utility cast with no landed damage row as a
rotation failure.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable, Mapping


SCHEMA = "magmaw_timeline_comparison_v1"
ENCOUNTER_ROUTE = "bwd.magmaw.encounter"
ENCOUNTER_TARGET_ENTRIES = frozenset({41570, 41806, 42321, 42347, 48270})
TIME_RE = re.compile(r"^(?:(?P<hours>\d+):)?(?P<minutes>\d+):(?P<seconds>\d+(?:\.\d+)?)$")
CAST_DURATION_RE = re.compile(r"\s+\d+(?:\.\d+)?\s+sec$")

# These are landed damage rows whose cadence is expected to be denser than the
# corresponding WCL cast count.  Keep this list conservative: unknown spells
# remain "direct_or_unknown" instead of being silently classified as ticks.
PERIODIC_SPELL_IDS = frozenset({
    172,       # Corruption
    5570,      # Insect Swarm
    8921,      # Moonfire
    93402,     # Sunfire
    12654,     # Ignite
    1978,      # Serpent Sting
    30108,     # Unstable Affliction
    3674,      # Black Arrow
    44457,     # Living Bomb
    44461,     # Living Bomb
    8050,      # Flame Shock
    83077,     # Improved Serpent Sting
    88453,     # Serpent Sting
    109800,    # Shadowbolt Volley
    109858,    # Speaking of Rage
})

CLASS_ID_TO_SPEC = {
    2: "holy_paladin",
    3: "survival_hunter",
    5: "discipline_priest",
    6: "blood_death_knight",
    7: "elemental_shaman",
    8: "fire_mage",
    9: "affliction_warlock",
    11: "balance_druid",
}


def parse_time(value: Any) -> float:
    """Parse WCL's MM:SS.mmm value into seconds."""
    if isinstance(value, (int, float)):
        return float(value)
    match = TIME_RE.match(str(value or "").strip())
    if not match:
        raise ValueError(f"unsupported timeline time: {value!r}")
    return (
        int(match.group("hours") or 0) * 3600.0
        + int(match.group("minutes")) * 60.0
        + float(match.group("seconds"))
    )


def normalize_ability(value: Any) -> str:
    """Remove WCL cast-time annotations while retaining the spell name."""
    ability = str(value or "").strip()
    ability = CAST_DURATION_RE.sub("", ability)
    ability = re.sub(r"\s+C(?:anceled|ancelled)$", "", ability, flags=re.IGNORECASE)
    return ability


def _target_from_wcl(value: Any) -> str | None:
    text = str(value or "").strip()
    if "→" not in text:
        return None
    return text.split("→", 1)[1].strip() or None


def parse_wcl_csv(path: Path, *, actor_id: str, class_spec: str) -> dict[str, Any]:
    """Parse completed WCL cast rows without retaining the HTML/CSV noise."""
    casts: list[dict[str, Any]] = []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            if str(row.get("Type") or "").strip().lower() != "cast":
                continue
            ability = normalize_ability(row.get("Ability"))
            if not ability:
                continue
            casts.append({
                "t": round(parse_time(row.get("Time")), 3),
                "ability": ability,
                "target": _target_from_wcl(row.get("Source → Target")),
            })
    casts.sort(key=lambda item: (item["t"], item["ability"]))
    return {
        "actor_id": actor_id,
        "class_spec": class_spec,
        "source_path": str(path),
        "casts": casts,
    }


def _load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _actor_identity(report: Mapping[str, Any] | None) -> dict[int, dict[str, Any]]:
    """Extract stable actor identity from a live validation report."""
    identities: dict[int, dict[str, Any]] = {}

    def visit(value: Any, depth: int = 0) -> None:
        if depth > 7:
            return
        if isinstance(value, list):
            for item in value:
                visit(item, depth + 1)
            return
        if not isinstance(value, dict):
            return
        guid = 0
        for key in ("bot_guid", "guid", "actor_guid", "unit_guid"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.isdigit():
                candidate = int(candidate)
            if isinstance(candidate, (int, float)):
                guid = int(candidate)
                if guid:
                    break
        if guid:
            identity: dict[str, Any] = {}
            for target, keys in {
                "bot_name": ("bot_name", "character_name", "actor_name", "name"),
                "role": ("role", "actor_role"),
                "class_spec": ("class_spec", "spec", "actor_spec", "bot_spec"),
                "class_name": ("class_name", "class"),
            }.items():
                for key in keys:
                    if value.get(key) not in (None, ""):
                        identity[target] = value[key]
                        break
            if identity:
                identities[guid] = {**identities.get(guid, {}), **identity}
        for key in (
            "diagnosis", "status", "raid_runtime", "roster", "members", "bots",
            "admission_receipt", "scenario_reports",
        ):
            nested = value.get(key)
            if isinstance(nested, (dict, list)):
                visit(nested, depth + 1)

    visit(report)
    return identities


def _percentile(values: list[float], quantile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, math.ceil(quantile * len(ordered)) - 1))
    return round(ordered[index], 3)


def _cadence(timestamps: Iterable[float]) -> dict[str, Any]:
    values = sorted(float(value) for value in timestamps)
    gaps = [right - left for left, right in zip(values, values[1:])]
    return {
        "event_count": len(values),
        "first_t": round(values[0], 3) if values else None,
        "last_t": round(values[-1], 3) if values else None,
        "max_gap_sec": round(max(gaps), 3) if gaps else None,
        "p95_gap_sec": _percentile(gaps, 0.95),
        "mean_gap_sec": round(sum(gaps) / len(gaps), 3) if gaps else None,
    }


def _largest_gaps(events: list[dict[str, Any]], *, limit: int = 6) -> list[dict[str, Any]]:
    ordered = sorted(events, key=lambda item: float(item["t"]))
    gaps: list[dict[str, Any]] = []
    for left, right in zip(ordered, ordered[1:]):
        gap = float(right["t"]) - float(left["t"])
        gaps.append({
            "gap_sec": round(gap, 3),
            "from_t": round(float(left["t"]), 3),
            "to_t": round(float(right["t"]), 3),
            "from_ability": left.get("ability"),
            "to_ability": right.get("ability"),
        })
    gaps.sort(key=lambda item: (-float(item["gap_sec"]), float(item["from_t"])))
    return gaps[:limit]


def _wcl_actor_summary(actor: Mapping[str, Any], window_sec: float) -> dict[str, Any]:
    casts = [
        dict(row)
        for row in actor.get("casts", [])
        if isinstance(row, dict) and 0.0 <= float(row.get("t", 0.0)) <= window_sec
    ]
    casts.sort(key=lambda row: (float(row["t"]), str(row.get("ability") or "")))
    by_ability: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in casts:
        by_ability[str(row.get("ability") or "unknown")].append(row)
    ability_summary = []
    for ability, rows in by_ability.items():
        cadence = _cadence(row["t"] for row in rows)
        ability_summary.append({
            "ability": ability,
            "cast_count": cadence["event_count"],
            "first_t": cadence["first_t"],
            "last_t": cadence["last_t"],
            "max_gap_sec": cadence["max_gap_sec"],
            "times": [round(float(row["t"]), 3) for row in rows[:24]],
        })
    ability_summary.sort(key=lambda row: (-int(row["cast_count"]), row["ability"]))
    return {
        "completed_casts": len(casts),
        "cadence": _cadence(row["t"] for row in casts),
        "ability_summary": ability_summary[:24],
    }


def _bot_actor_summary(
    events: list[dict[str, Any]],
    *,
    window_sec: float,
) -> dict[str, Any]:
    window_events = [
        event
        for event in events
        if 0.0 <= float(event["t"]) <= window_sec
    ]
    direct_events = [
        event
        for event in window_events
        if not bool(event.get("periodic"))
    ]
    by_ability: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in window_events:
        by_ability[str(event.get("ability") or "unknown")].append(event)
    ability_summary = []
    for ability, rows in by_ability.items():
        cadence = _cadence(row["t"] for row in rows)
        ability_summary.append({
            "ability": ability,
            "spell_ids": sorted({int(row.get("spell_id") or 0) for row in rows}),
            "landed_damage_events": cadence["event_count"],
            "landed_damage": round(sum(float(row.get("amount") or 0.0) for row in rows)),
            "periodic": all(bool(row.get("periodic")) for row in rows),
            "first_t": cadence["first_t"],
            "last_t": cadence["last_t"],
            "max_gap_sec": cadence["max_gap_sec"],
            "times": [round(float(row["t"]), 3) for row in rows[:24]],
        })
    ability_summary.sort(
        key=lambda row: (-int(row["landed_damage_events"]), row["ability"])
    )
    return {
        "landed_damage_events": len(window_events),
        "landed_damage": round(sum(float(event.get("amount") or 0.0) for event in window_events)),
        "cadence": _cadence(event["t"] for event in window_events),
        "direct_or_unknown_cadence": _cadence(event["t"] for event in direct_events),
        "largest_gaps": _largest_gaps(direct_events),
        "ability_summary": ability_summary[:24],
    }


def _ability_diffs(
    wcl: Mapping[str, Any],
    bot: Mapping[str, Any],
    *,
    limit: int = 16,
) -> list[dict[str, Any]]:
    wcl_counts = {
        str(row.get("ability")): int(row.get("cast_count") or 0)
        for row in wcl.get("ability_summary", [])
        if isinstance(row, dict)
    }
    bot_counts = {
        str(row.get("ability")): int(row.get("landed_damage_events") or 0)
        for row in bot.get("ability_summary", [])
        if isinstance(row, dict)
    }
    rows: list[dict[str, Any]] = []
    for ability in sorted(set(wcl_counts) | set(bot_counts)):
        wcl_count = wcl_counts.get(ability, 0)
        bot_count = bot_counts.get(ability, 0)
        if not wcl_count and not bot_count:
            continue
        rows.append({
            "ability": ability,
            "wcl_completed_casts": wcl_count,
            "bot_landed_damage_events": bot_count,
            "delta_landed_events_minus_casts": bot_count - wcl_count,
            "event_to_cast_ratio": round(bot_count / max(1, wcl_count), 3),
            "interpretation": (
                "landed_damage_events_are_not_casts; periodic effects and multi-target "
                "damage can legitimately exceed WCL casts"
            ),
        })
    rows.sort(
        key=lambda row: (
            -abs(int(row["delta_landed_events_minus_casts"])),
            row["ability"],
        )
    )
    return rows[:limit]


def _load_wcl_actors(manifest_path: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    manifest = _load_json(manifest_path)
    actors: list[dict[str, Any]] = []
    for actor in manifest.get("actors", []):
        if not isinstance(actor, dict):
            continue
        item = dict(actor)
        csv_path = item.get("csv")
        if csv_path and not item.get("casts"):
            path = Path(str(csv_path))
            if not path.is_absolute():
                path = manifest_path.parent / path
            item = {
                **item,
                **parse_wcl_csv(
                    path,
                    actor_id=str(item.get("actor_id") or item.get("class_spec") or "unknown"),
                    class_spec=str(item.get("class_spec") or "unknown"),
                ),
            }
        actors.append(item)
    return manifest, actors


def compare_timelines(
    bot_run: Path,
    wcl_manifest_path: Path,
    *,
    include_roles: frozenset[str] = frozenset({"dps", "tank", "healer"}),
) -> dict[str, Any]:
    """Build a compact all-actor comparison from one closed bot run."""
    report = _load_json(bot_run / "report.json")
    combat_log = _load_json(bot_run / "combat_log.json")
    combat_analysis = _load_json(bot_run / "combat_analysis.json")
    wcl_manifest, wcl_actors = _load_wcl_actors(wcl_manifest_path)
    identities = _actor_identity(report)
    encounter = next(
        (
            row
            for row in combat_analysis.get("encounters", [])
            if isinstance(row, dict) and row.get("route_node_id") == ENCOUNTER_ROUTE
        ),
        None,
    )
    if not isinstance(encounter, dict):
        raise ValueError(f"closed bot run has no {ENCOUNTER_ROUTE} encounter: {bot_run}")
    first_at_ms = int(encounter.get("first_at_ms") or 0)
    bot_duration = float(encounter.get("duration_sec") or 0.0)
    if not first_at_ms or bot_duration <= 0.0:
        raise ValueError("encounter window has no usable boundary")
    wcl_duration = float(wcl_manifest.get("duration_sec") or 0.0)
    if wcl_duration <= 0.0:
        raise ValueError("WCL manifest has no positive duration_sec")
    common_window = min(bot_duration, wcl_duration)

    actor_metrics = {
        int(row.get("actor_guid")): row
        for row in encounter.get("actors", [])
        if isinstance(row, dict) and int(row.get("actor_guid") or 0)
    }
    raw_events = combat_log.get("recent_events", [])
    by_actor: defaultdict[int, list[dict[str, Any]]] = defaultdict(list)
    for event in raw_events:
        if not isinstance(event, dict):
            continue
        if event.get("kind") != "damage" or event.get("route_node_id") != ENCOUNTER_ROUTE:
            continue
        target_entry = int(event.get("target_entry") or 0)
        if target_entry not in ENCOUNTER_TARGET_ENTRIES:
            continue
        amount = float(event.get("originated_amount") or 0.0)
        if amount <= 0.0:
            continue
        actor_guid = int(event.get("actor_guid") or 0)
        if not actor_guid:
            continue
        timestamp = (int(event.get("timestamp_ms") or 0) - first_at_ms) / 1000.0
        if timestamp < 0.0 or timestamp > bot_duration:
            continue
        spell_id = int(event.get("spell_id") or 0)
        by_actor[actor_guid].append({
            "t": round(timestamp, 3),
            "ability": str(event.get("spell_name") or "unknown"),
            "spell_id": spell_id,
            "amount": round(amount),
            "periodic": spell_id in PERIODIC_SPELL_IDS,
            "source_is_pet": bool(event.get("source_is_pet")),
            "target_entry": target_entry,
        })

    wcl_by_spec: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for actor in wcl_actors:
        wcl_by_spec[str(actor.get("class_spec") or "unknown")].append(actor)
    reuse_counts: Counter[str] = Counter()
    actors: list[dict[str, Any]] = []
    for guid, metrics in sorted(actor_metrics.items()):
        identity = identities.get(guid, {})
        role = str(identity.get("role") or metrics.get("actor_role") or "unknown")
        if role not in include_roles:
            continue
        class_spec = str(
            identity.get("class_spec")
            or metrics.get("class_spec")
            or CLASS_ID_TO_SPEC.get(int(metrics.get("actor_class_id") or 0), "unknown")
        )
        references = wcl_by_spec.get(class_spec, [])
        reference = references[0] if references else None
        reference_reuse_index = None
        if reference is not None:
            reuse_counts[class_spec] += 1
            reference_reuse_index = reuse_counts[class_spec]
        wcl_summary = (
            _wcl_actor_summary(reference, common_window)
            if reference is not None
            else None
        )
        bot_summary = _bot_actor_summary(by_actor.get(guid, []), window_sec=common_window)
        actor_row: dict[str, Any] = {
            "bot_guid": guid,
            "bot_name": identity.get("bot_name") or metrics.get("actor_name"),
            "role": role,
            "class_spec": class_spec,
            "comparison_status": "comparable" if reference is not None else "missing_wcl_reference",
            "reference_actor_id": reference.get("actor_id") if reference else None,
            "reference_source_name": reference.get("source_name") if reference else None,
            "reference_reuse_index": reference_reuse_index,
            "reference_reused_for_duplicate_local_actor": bool(reference_reuse_index and reference_reuse_index > 1),
            "wcl_observed_dps": reference.get("observed_dps") if reference else None,
            "bot_encounter_window_dps": metrics.get("encounter_window_dps"),
            "bot_active_dps": metrics.get("active_dps"),
            "bot_damage_uptime": metrics.get("damage_uptime"),
            "bot_moving_fraction": metrics.get("moving_fraction"),
            "bot_active_seconds": metrics.get("active_seconds"),
            "bot_damage": metrics.get("damage"),
            "wcl": wcl_summary,
            "bot": bot_summary,
            "ability_diffs": _ability_diffs(wcl_summary, bot_summary) if wcl_summary else [],
            "comparison_limitations": [
                "WCL rows are completed casts; bot rows are positive landed damage observations.",
                "Periodic ticks and multi-target damage can outnumber the originating cast.",
                "WCL is a reference timeline, not an acceptance floor; gear and assignments differ.",
            ],
        }
        if reference is None:
            actor_row["comparison_limitations"].append(
                "No same-class/spec WCL cast timeline was supplied; cadence is diagnostic only."
            )
        actors.append(actor_row)

    comparable = [row for row in actors if row["comparison_status"] == "comparable"]
    return {
        "schema": SCHEMA,
        "reference": {
            "id": wcl_manifest.get("reference_id"),
            "url": wcl_manifest.get("url"),
            "mode": wcl_manifest.get("mode"),
            "duration_sec": round(wcl_duration, 3),
            "target_scope": wcl_manifest.get("target_scope", "Magmaw and parasites"),
        },
        "bot_run": {
            "path": str(bot_run),
            "run_id": report.get("run_id"),
            "completion_reason": report.get("completion_reason"),
            "native_gameplay_outcome": report.get("native_gameplay_outcome"),
        },
        "scope": {
            "route_node_id": ENCOUNTER_ROUTE,
            "actor_roles": sorted(include_roles),
            "actor_count": len(actors),
            "comparable_actor_count": len(comparable),
            "missing_wcl_reference_actor_count": len(actors) - len(comparable),
        },
        "comparison_window": {
            "basis": "normalized_first_encounter_event_to_first_event",
            "wcl_duration_sec": round(wcl_duration, 3),
            "bot_encounter_duration_sec": round(bot_duration, 3),
            "common_window_sec": round(common_window, 3),
            "bot_clipped_to_common_window": bot_duration > common_window,
        },
        "actors": actors,
        "signal_contract": {
            "primary_signal": "per_actor_wcl_cast_cadence_vs_bot_landed_event_cadence",
            "secondary_signal": "movement_gaps_native_failures_and_encounter_window_dps",
            "jev_role": "review_compact_diff_and_propose_one_bounded_next_fix; never submit actions",
            "missing_reference_policy": "report_actor_explicitly_as_missing_wcl_reference",
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bot-run", type=Path, required=True)
    parser.add_argument("--wcl-manifest", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = compare_timelines(args.bot_run, args.wcl_manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(
        "Magmaw timeline comparison "
        f"actors={result['scope']['actor_count']} "
        f"comparable={result['scope']['comparable_actor_count']} "
        f"output={args.output}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

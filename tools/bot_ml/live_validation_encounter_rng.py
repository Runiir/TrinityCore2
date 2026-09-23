"""Uncontrolled random encounter events, per kill, from the native combat log.

Some native scripts pick an encounter event at random, and the pick can move
an actor's DPS more than the change being measured. Magmaw's Massive Crash is
one: DATA_PREPARE_MASSIVE_CRASH_AND_GET_TARGET_GUID in
src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/instance_blackwing_descent.cpp
chooses the left or right Massive Crash dummy (NPC 47330) with urand, and that
dummy casts 88287 (SPELL_MASSIVE_CRASH_DAMAGE) six seconds later. The two
dummies stand a few yards apart but face different arcs. In the bot raid's
positions the right dummy's arc covers the ranged area and hits 7-9 of 10
players plus 2-4 pets; the left dummy hit no player, only 1-3 pets, in all
five such casts (fid16-8586fdd, bundle2-19b2af6). A label that drew the
raid-wide side 4/4 and one that drew it 2/5 differ by about 4k Balance DPS for
that reason alone.

Side rule for ``massive_crash`` (one entry per cast: 88287 damage events of one
source within ``CAST_GAP_MS``):

1. ``source_position``: the caster is NPC 47330. Within 1 yard (2D) of
   MassiveCrashRightSpawnPosition (-288.59, -14.8472), the same test the
   instance script uses to identify the right dummy, the side is
   ``raid_wide``. Any other 47330 position is ``far``.
2. ``players_hit`` (only when the caster position is missing): players hit
   (target_entry 0; pets excluded) divided by the raid size. At least 0.5 is
   ``raid_wide``, at most 0.3 is ``far``, anything between is ``unknown``.

Both readings are recorded. ``basis_conflict`` is true when the hit share
contradicts the position, e.g. because the raid stood somewhere else.

Output: report.json ``encounter_rng`` and combat_analysis.json
``encounter_rng``. It is information for comparisons: it never changes
acceptance, counting or a verdict.
"""
from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any, Mapping, Sequence

RNG_SCHEMA = "encounter_rng_v1"
SIDES = ("raid_wide", "far", "unknown")
CAST_GAP_MS = 2000
DEFAULT_RAID_SIZE = 10
RULES: dict[str, dict[str, Any]] = {
    "massive_crash": {
        "boss_entries": (41570,),
        "spell_ids": (88287,),
        "source_entry": 47330,
        "side_positions": {"raid_wide": (-288.59, -14.8472)},
        "other_side": "far",
        "position_tolerance_yards": 1.0,
        "hit_share": {"raid_wide": 0.5, "far": 0.3},
        "script": "instance_blackwing_descent.cpp DATA_PREPARE_MASSIVE_CRASH_AND_GET_TARGET_GUID urand(LEFT, RIGHT)",
    },
}


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _boss_entries(route_manifest: Mapping[str, Any] | None) -> set[int]:
    manifest = route_manifest if isinstance(route_manifest, Mapping) else {}
    return {_int(route.get("source_entry")) for route in manifest.get("routes") or []
            if isinstance(route, Mapping) and str(route.get("kind") or route.get("node_kind") or "").lower() == "boss"}


def _raid_size(events: Sequence[Mapping[str, Any]], combat_analysis: Mapping[str, Any] | None, node: str | None) -> int:
    for encounter in (combat_analysis or {}).get("encounters") or []:
        if isinstance(encounter, Mapping) and encounter.get("route_node_id") == node and encounter.get("actors"):
            return len({_int(actor.get("actor_guid")) for actor in encounter["actors"] if isinstance(actor, Mapping)})
    actors = {_int(event.get("actor_guid")) for event in events if event.get("actor_role")}
    actors.discard(0)
    return len(actors) or DEFAULT_RAID_SIZE


def _window_start(combat_analysis: Mapping[str, Any] | None, node: str | None) -> int | None:
    for encounter in (combat_analysis or {}).get("encounters") or []:
        if isinstance(encounter, Mapping) and encounter.get("route_node_id") == node and _int(encounter.get("first_at_ms")) > 0:
            return _int(encounter["first_at_ms"])
    return None


def side_from_position(rule: Mapping[str, Any], source_entry: int, x: float | None, y: float | None) -> str | None:
    if source_entry != rule["source_entry"] or x is None or y is None:
        return None
    for side, (sx, sy) in rule["side_positions"].items():
        if math.hypot(x - sx, y - sy) <= rule["position_tolerance_yards"]:
            return side
    return rule["other_side"]


def side_from_hits(rule: Mapping[str, Any], players_hit: int, raid_size: int) -> str:
    share = players_hit / raid_size if raid_size > 0 else 0.0
    if share >= rule["hit_share"]["raid_wide"]:
        return "raid_wide"
    if share <= rule["hit_share"]["far"]:
        return "far"
    return "unknown"


def _casts(events: Sequence[Mapping[str, Any]], spell_ids: Sequence[int]) -> list[list[Mapping[str, Any]]]:
    hits = sorted((event for event in events if event.get("kind") == "damage" and _int(event.get("spell_id")) in spell_ids),
                  key=lambda event: (_int(event.get("source_guid")), _int(event.get("timestamp_ms"))))
    casts: list[list[Mapping[str, Any]]] = []
    for event in hits:
        last = casts[-1][-1] if casts else None
        if (last is not None and _int(last.get("source_guid")) == _int(event.get("source_guid"))
                and _int(event.get("timestamp_ms")) - _int(last.get("timestamp_ms")) <= CAST_GAP_MS):
            casts[-1].append(event)
        else:
            casts.append([event])
    return sorted(casts, key=lambda rows: _int(rows[0].get("timestamp_ms")))


def rule_events(name: str, rule: Mapping[str, Any], events: Sequence[Mapping[str, Any]],
                combat_analysis: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows = []
    for cast in _casts(events, rule["spell_ids"]):
        first = cast[0]
        node = first.get("route_node_id")
        players = sorted({(_int(e.get("target_guid")), str(e.get("target_name") or "")) for e in cast
                          if _int(e.get("target_entry")) == 0 and _int(e.get("target_guid")) > 0})
        units = {_int(e.get("target_guid")) for e in cast}
        raid_size = _raid_size(events, combat_analysis, node)
        x, y = _float(first.get("source_x")), _float(first.get("source_y"))
        by_position = side_from_position(rule, _int(first.get("source_entry")), x, y)
        by_hits = side_from_hits(rule, len(players), raid_size)
        start = _window_start(combat_analysis, node)
        at_ms = _int(first.get("timestamp_ms"))
        rows.append({
            "timestamp_ms": at_ms,
            "at_sec": round((at_ms - start) / 1000.0, 3) if start else None,
            "route_node_id": node,
            "side": by_position or by_hits,
            "side_basis": "source_position" if by_position else "players_hit",
            "side_from_hits": by_hits,
            "basis_conflict": bool(by_position and by_hits != "unknown" and by_hits != by_position),
            "source_entry": _int(first.get("source_entry")),
            "source_guid": _int(first.get("source_guid")),
            "source_position": [x, y] if x is not None and y is not None else None,
            "players_hit": len(players),
            "pets_hit": len(units) - len(players),
            "units_hit": len(units),
            "raid_size": raid_size,
            "player_names": [name for _, name in players],
            "damage_total": sum(_int(e.get("amount")) for e in cast),
        })
    return rows


def encounter_rng(combat_log: Mapping[str, Any] | None, route_manifest: Mapping[str, Any] | None = None,
                  combat_analysis: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Random encounter events of one kill. A rule appears when its boss is on the route or it fired."""
    events = [event for event in (combat_log or {}).get("recent_events") or [] if isinstance(event, Mapping)]
    bosses = _boss_entries(route_manifest)
    result: dict[str, Any] = {"schema": RNG_SCHEMA, "informational": True,
                              "recent_events_dropped": _int((combat_log or {}).get("recent_events_dropped")),
                              "summary": {}}
    for name, rule in RULES.items():
        rows = rule_events(name, rule, events, combat_analysis)
        if rows or bosses & set(rule["boss_entries"]):
            result[name] = rows
            counts = Counter(row["side"] for row in rows)
            result["summary"][name] = {side: counts.get(side, 0) for side in SIDES}
    return result


def attach_encounter_rng(report: dict[str, Any], route_manifest: Mapping[str, Any] | None) -> dict[str, Any]:
    """Harness hook: report["encounter_rng"] and combat_analysis["encounter_rng"]. Never raises."""
    try:
        log = report.get("combat_log") if isinstance(report.get("combat_log"), Mapping) else None
        analysis = report.get("combat_analysis") if isinstance(report.get("combat_analysis"), Mapping) else None
        result = encounter_rng(log, route_manifest, analysis)
    except KeyboardInterrupt:
        raise
    except BaseException as error:  # informational: a bug here must not cost the run its report
        result = {"schema": RNG_SCHEMA, "informational": True, "status": "error",
                  "error": f"{type(error).__name__}: {error}", "summary": {}}
    report["encounter_rng"] = result
    if isinstance(report.get("combat_analysis"), dict) and report["combat_analysis"]:
        report["combat_analysis"]["encounter_rng"] = result
    return result


def scoreboard_summary(rng: Mapping[str, Any] | None, basis: str) -> dict[str, Any] | None:
    """Compact per-kill form: each event's side, time and players hit."""
    if not isinstance(rng, Mapping) or rng.get("schema") != RNG_SCHEMA or rng.get("status") == "error":
        return None
    compact: dict[str, Any] = {"basis": basis}
    for name in RULES:
        if isinstance(rng.get(name), list):
            compact[name] = [{key: row.get(key) for key in ("side", "side_basis", "at_sec", "players_hit", "units_hit")}
                             for row in rng[name]]
    return compact


def rng_from_run_dir(run_dir: Path, report: Mapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Compact per-kill RNG: the harness block when report.json has one, else recomputed from combat_log.json."""
    run_dir = Path(run_dir)
    if report is None:
        report = json.loads((run_dir / "report.json").read_text())
    if isinstance(report.get("encounter_rng"), Mapping):
        return scoreboard_summary(report["encounter_rng"], "harness")
    if not (run_dir / "combat_log.json").exists():
        return None
    manifest = report.get("validation_route_manifest")
    if not manifest and (run_dir / "validation_route_manifest.json").exists():
        manifest = json.loads((run_dir / "validation_route_manifest.json").read_text())
    analysis_path = run_dir / "combat_analysis.json"
    analysis = json.loads(analysis_path.read_text()) if analysis_path.exists() else report.get("combat_analysis")
    log = json.loads((run_dir / "combat_log.json").read_text())
    return scoreboard_summary(encounter_rng(log, manifest, analysis), "combat_log_recomputed")

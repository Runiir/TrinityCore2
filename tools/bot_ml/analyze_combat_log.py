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


def _raw_event_amount(row: dict[str, Any]) -> int:
    return int(row.get("amount") or 0)


def _originated_amount(row: dict[str, Any]) -> int:
    # Schema v1 has no provenance field, so its amount is the best available
    # originated total. Schema v2+ explicitly records share-damage copies as
    # zero originated amount while retaining their raw event amount. Schema 3
    # uses the same field for both hostile and friendly perspectives.
    if "originated_amount" in row:
        return int(row.get("originated_amount") or 0)
    return _raw_event_amount(row)


def is_environmental_self_damage(row: dict[str, Any]) -> bool:
    """Native environmental damage: the victim is its own attacker, with no spell.

    TrinityCore deals falling, lava, drowning and fatigue damage through
    ``Unit::DealDamage(victim, victim, ...)`` without a SpellInfo, so the bot
    combat log records it as a spell-0 "Melee" hit whose source is the target
    (round-2 Nefarian descent: about 60k per bot on the drop).  It is neither
    friendly fire nor damage done.  Aggregate rows carry names, not GUIDs, so a
    player (entry 0) hitting itself by name is the aggregate-level signature.
    """
    try:
        if int(row.get("spell_id") or 0) != 0 or row.get("source_is_pet"):
            return False
        source_guid = int(row.get("source_guid") or 0)
        target_guid = int(row.get("target_guid") or 0)
        if source_guid and target_guid:
            return source_guid == target_guid
        if int(row.get("source_entry") or 0) or int(row.get("target_entry") or 0):
            return False
    except (TypeError, ValueError):
        return False
    source_name = str(row.get("source_name") or "")
    return bool(source_name) and source_name == str(row.get("target_name") or "")


def _combat_log_schema_version(combat_log: dict[str, Any]) -> int:
    try:
        value = int(combat_log.get("combat_log_schema_version") or 1)
    except (TypeError, ValueError):
        return 1
    return max(1, value)


def _distance_samples(row: dict[str, Any]) -> int:
    """Events with an observed source position.

    Native aggregates count them in ``distance_samples``; ticks from a caster
    who left the map have no position.  Older logs lack the field, and every
    event there had a position.
    """
    value = row.get("distance_samples") if "distance_samples" in row else row.get("event_count")
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


def _sampled_total(rows: list[dict[str, Any]]) -> int:
    return sum(_distance_samples(row) for row in rows)


def _weighted_average(rows: list[dict[str, Any]], field: str) -> float | None:
    """Average a distance/movement field over rows with position samples.

    Zero-sample rows and null values are missing data, not zero distance.
    Returns ``None`` when no row carries a sample.
    """
    total = 0.0
    weight = 0
    for row in rows:
        samples = _distance_samples(row)
        value = row.get(field)
        if samples <= 0 or value is None:
            continue
        total += _number(value) * samples
        weight += samples
    return total / weight if weight else None


def _rounded(value: float | None, digits: int) -> float | None:
    return None if value is None else round(value, digits)


def _damage_by_target_entry(rows: list[dict[str, Any]]) -> dict[str, int]:
    totals: dict[str, int] = {}
    for row in rows:
        entry = str(int(row.get("target_entry") or 0))
        totals[entry] = totals.get(entry, 0) + _originated_amount(row)
    return dict(sorted(totals.items(), key=lambda item: int(item[0])))


def _ability_rows(
    rows: list[dict[str, Any]],
    total_damage: int,
    *,
    raw_total_damage: int | None = None,
    use_originated: bool = False,
    include_target: bool = False,
) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], dict[str, Any]] = {}
    for row in rows:
        base_key = (
            int(row.get("spell_id") or 0),
            str(row.get("spell_name") or "Unknown"),
            bool(row.get("source_is_pet")),
            int(row.get("source_entry") or 0),
            str(row.get("source_name") or ""),
        )
        key = base_key + (
            int(row.get("target_entry") or 0),
            str(row.get("target_name") or ""),
        ) if include_target else base_key
        target = grouped.setdefault(
            key,
            {
                "spell_id": key[0],
                "spell_name": key[1],
                "source_is_pet": key[2],
                "source_entry": key[3],
                "source_name": key[4],
                "damage": 0,
                "raw_event_damage": 0,
                "originated_damage": 0,
                "events": 0,
                "moving_events": 0,
                "distance_weighted": 0.0,
                "distance_samples": 0,
                "moving_samples": 0,
            },
        )
        if include_target:
            target["target_entry"] = key[5]
            target["target_name"] = key[6]
        events = int(row.get("event_count") or 0)
        raw_damage = _raw_event_amount(row)
        originated_damage = _originated_amount(row)
        target["damage"] += originated_damage if use_originated else raw_damage
        target["raw_event_damage"] += raw_damage
        target["originated_damage"] += originated_damage
        target["events"] += events
        samples = _distance_samples(row)
        if samples > 0:
            target["moving_events"] += int(row.get("moving_events") or 0)
            target["moving_samples"] += samples
            if row.get("distance_avg") is not None:
                target["distance_weighted"] += _number(row.get("distance_avg")) * samples
                target["distance_samples"] += samples

    abilities: list[dict[str, Any]] = []
    for row in grouped.values():
        events = max(1, int(row.pop("events")))
        moving_events = int(row.pop("moving_events"))
        distance_weighted = float(row.pop("distance_weighted"))
        distance_samples = int(row.pop("distance_samples"))
        moving_samples = int(row.pop("moving_samples"))
        row["events"] = events
        row["damage_share"] = round(int(row["damage"]) / max(1, total_damage), 6)
        row["raw_event_damage_share"] = round(
            int(row["raw_event_damage"]) / max(1, raw_total_damage or total_damage), 6
        )
        row["originated_damage_share"] = round(
            int(row["originated_damage"]) / max(1, total_damage), 6
        )
        row["moving_fraction"] = round(moving_events / moving_samples, 6) if moving_samples else None
        row["distance_avg"] = round(distance_weighted / distance_samples, 3) if distance_samples else None
        row["distance_samples"] = distance_samples
        abilities.append(row)
    return sorted(abilities, key=lambda row: (-int(row["damage"]), int(row["spell_id"])))


def _compact_action_outcomes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the native full-window outcome ledger small and attribution-safe."""
    allowed = (
        "route_generation",
        "route_node_id",
        "actor_guid",
        "actor_name",
        "actor_role",
        "actor_class_id",
        "phase",
        "action_type",
        "action_name",
        "spell_id",
        "result",
        "reason",
        "retry_reason",
        "first_at_ms",
        "last_at_ms",
        "count",
    )
    compact = [
        {key: row[key] for key in allowed if key in row}
        for row in rows
        if isinstance(row, dict)
    ]
    return sorted(
        compact,
        key=lambda row: (
            int(row.get("actor_guid") or 0),
            str(row.get("phase") or ""),
            str(row.get("action_name") or ""),
            str(row.get("result") or ""),
            str(row.get("reason") or ""),
        ),
    )


def _compact_candidate_rejections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep native profile-gate counts attributable to each actor and spell."""
    allowed = (
        "route_generation",
        "route_node_id",
        "actor_guid",
        "actor_name",
        "actor_role",
        "actor_class_id",
        "phase",
        "spell_id",
        "action_category",
        "reason",
        "first_at_ms",
        "last_at_ms",
        "count",
    )
    compact = [
        {key: row[key] for key in allowed if key in row}
        for row in rows
        if isinstance(row, dict)
    ]
    return sorted(
        compact,
        key=lambda row: (
            int(row.get("actor_guid") or 0),
            str(row.get("reason") or ""),
            int(row.get("spell_id") or 0),
            str(row.get("action_category") or ""),
        ),
    )


KILLED_HOSTILE_RECONCILIATION_TOLERANCE_PCT = 1.0
# Hostiles whose health is shared with (or reset by) another unit cannot be
# reconciled against their own max HP.  Keyed by creature entry.
RECONCILIATION_EXEMPT_ENTRIES: dict[int, str] = {
    41570: "magmaw_shares_health_with_exposed_head",
    42347: "exposed_head_of_magmaw_shared_health",
    48270: "exposed_head_of_magmaw_shared_health",
}
UNIT_DEATH_EVENT_KINDS = frozenset({"death", "unit_death", "unit_died", "killed"})
CREATURE_GUID_LOW_MASK = 0xFFFFFFFF


def _landed_health(row: dict[str, Any], field: str) -> int:
    observation = row.get("landed_damage_observation")
    if not isinstance(observation, dict):
        return 0
    try:
        return int(observation.get(field) or 0)
    except (TypeError, ValueError):
        return 0


def _death_keys(rows: Any) -> tuple[set[tuple[int, int]], set[int]]:
    """Return confirmed deaths as ``(guid_low, entry)`` pairs and bare entries.

    Accepts combat-log death events (``target_guid``/``target_entry``) and
    native death evidence (``target_id`` full GUID plus ``target_entry``).
    """
    exact: set[tuple[int, int]] = set()
    entries: set[int] = set()
    for row in rows or []:
        if not isinstance(row, dict):
            continue
        try:
            entry = int(row.get("target_entry") or row.get("entry") or 0)
            guid = int(row.get("target_guid") or row.get("target_id") or row.get("guid") or 0)
        except (TypeError, ValueError):
            continue
        if guid:
            exact.add((guid & CREATURE_GUID_LOW_MASK, entry))
        elif entry:
            entries.add(entry)
    return exact, entries


NATIVE_KILL_TRACE_ACTIONS = frozenset({"mob_killed", "boss_killed", "raid_boss_killed"})


def unit_deaths_from_report(report: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect confirmed unit deaths from native live-validation evidence.

    Sources: ``status.validation_route.boss_death_evidence`` (full GUID in
    ``target_id``) and kill rows in the retained trace (low GUID in
    ``target_id``, entry in ``event_target``).
    """
    deaths: list[dict[str, Any]] = []
    status = report.get("status") if isinstance(report.get("status"), dict) else {}
    route = status.get("validation_route") if isinstance(status.get("validation_route"), dict) else {}
    for row in route.get("boss_death_evidence") or []:
        if isinstance(row, dict) and row.get("target_id") and row.get("target_entry"):
            deaths.append({"target_guid": row.get("target_id"), "target_entry": row.get("target_entry"), "source": "boss_death_evidence"})
    trace = report.get("trace") if isinstance(report.get("trace"), dict) else {}
    entries = list(trace.get("entries") or [])
    for bot in trace.get("bots") or []:
        if isinstance(bot, dict):
            entries.extend(bot.get("entries") or [])
    for entry in entries:
        if not isinstance(entry, dict) or str(entry.get("action") or "") not in NATIVE_KILL_TRACE_ACTIONS:
            continue
        target = entry.get("event_target") if isinstance(entry.get("event_target"), dict) else {}
        guid = entry.get("target_id") or target.get("guid")
        entry_id = target.get("entry") or entry.get("target_entry")
        if guid and entry_id:
            deaths.append({"target_guid": guid, "target_entry": entry_id, "source": "trace_" + str(entry.get("action"))})
    return deaths


def killed_hostile_damage_reconciliation(
    combat_log: dict[str, Any],
    unit_deaths: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compare logged damage taken by every dead hostile with its max HP.

    ``amount`` is the landed, overkill-free damage, so a hostile that died with
    every damage event logged reconciles to its maximum health.  A shortfall
    means damage that reached the hostile was not logged (for example periodic
    ticks from a bot that already died); an excess means it regained health.
    ``unlogged_health_loss`` sums health drops between consecutive logged
    events that no logged event explains; any such loss is flagged.

    A hostile is dead when a logged hit killed it or a death is confirmed by a
    combat-log death event or ``unit_deaths`` (native boss/trace evidence).
    A hostile whose killing blow was not logged is never skipped: with a
    confirmed death it is reconciled (``killing_blow_unlogged``); without one
    it is listed under ``unconfirmed_deaths`` (it may also have survived or
    despawned).  Shared-health or resetting targets in
    ``RECONCILIATION_EXEMPT_ENTRIES`` are reported but never flagged.
    """
    all_events = [row for row in combat_log.get("recent_events") or [] if isinstance(row, dict)]
    events = [row for row in all_events if str(row.get("kind") or "") == "damage"]
    events.sort(key=lambda row: (int(row.get("timestamp_ms") or 0), int(row.get("event_sequence") or 0)))
    death_exact, death_entries = _death_keys(
        [row for row in all_events if str(row.get("kind") or "") in UNIT_DEATH_EVENT_KINDS]
        + list(unit_deaths or [])
    )
    friendly: set[tuple[int, int]] = set()
    bot_guids: set[int] = set()
    for row in events:
        actor = int(row.get("actor_guid") or 0)
        if actor:
            bot_guids.add(actor)
        if row.get("source_is_pet"):
            friendly.add((int(row.get("source_guid") or 0), int(row.get("source_entry") or 0)))
    hostile_keys: set[tuple[int, int]] = set()
    for row in events:
        source = int(row.get("source_guid") or 0)
        if not (source in bot_guids or row.get("source_is_pet")):
            continue
        key = (int(row.get("target_guid") or 0), int(row.get("target_entry") or 0))
        if key[0] and key[1] and key not in friendly and key[0] not in bot_guids:
            hostile_keys.add(key)
    by_target: dict[tuple[int, int], list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        key = (int(row.get("target_guid") or 0), int(row.get("target_entry") or 0))
        if key in hostile_keys:
            by_target[key].append(row)

    hostiles: list[dict[str, Any]] = []
    unconfirmed: list[dict[str, Any]] = []
    for key, rows in by_target.items():
        killing = next(
            (
                row for row in rows
                if 0 < _landed_health(row, "target_health_before_damage") <= int(row.get("amount") or 0)
            ),
            None,
        )
        death_confirmed = (
            (key[0] & CREATURE_GUID_LOW_MASK, key[1]) in death_exact or key[1] in death_entries
        )
        max_health = max(_landed_health(row, "target_max_health") for row in rows)
        if max_health <= 0:
            continue
        recorded = sum(int(row.get("amount") or 0) for row in rows)
        unlogged_loss = 0
        health_gain = 0
        for previous, current in zip(rows, rows[1:]):
            expected = _landed_health(previous, "target_health_before_damage") - int(previous.get("amount") or 0)
            observed = _landed_health(current, "target_health_before_damage")
            if observed < expected:
                unlogged_loss += expected - observed
            elif observed > expected:
                health_gain += observed - expected
        last = rows[-1]
        health_after_last = max(
            0, _landed_health(last, "target_health_before_damage") - int(last.get("amount") or 0)
        )
        exempt = RECONCILIATION_EXEMPT_ENTRIES.get(key[1], "")
        row_out: dict[str, Any] = {
            "target_guid": key[0],
            "target_entry": key[1],
            "target_name": str(rows[0].get("target_name") or ""),
            "route_node_id": str((killing or last).get("route_node_id") or ""),
            "route_generation": int((killing or last).get("route_generation") or 0),
            "max_health": max_health,
            "recorded_damage_taken": recorded,
            "damage_before_first_logged_event": max(
                0, max_health - _landed_health(rows[0], "target_health_before_damage")
            ),
            "unlogged_health_loss": unlogged_loss,
            "health_gain_between_events": health_gain,
            "health_after_last_logged_event": health_after_last,
            "shared_damage_events": sum(1 for row in rows if row.get("shared_damage")),
            "damage_events": len(rows),
            "first_at_ms": int(rows[0].get("timestamp_ms") or 0),
            "last_logged_at_ms": int(last.get("timestamp_ms") or 0),
            "killing_blow_unlogged": killing is None,
            "death_confirmed_by": (
                "logged_killing_blow" if killing is not None
                else "unit_death_evidence" if death_confirmed
                else None
            ),
            "exempt": exempt or None,
        }
        if killing is None and not death_confirmed:
            row_out["flagged"] = False
            unconfirmed.append(row_out)
            continue
        delta = recorded - max_health
        mismatch_pct = abs(delta) * 100.0 / max_health
        flag_reasons: list[str] = []
        if mismatch_pct > KILLED_HOSTILE_RECONCILIATION_TOLERANCE_PCT:
            flag_reasons.append("recorded_damage_mismatch")
        if unlogged_loss > 0:
            flag_reasons.append("unlogged_health_loss")
        row_out.update({
            "delta": delta,
            "mismatch_pct": round(mismatch_pct, 4),
            "killed_at_ms": int((killing or last).get("timestamp_ms") or 0),
            "killing_blow_source": str(killing.get("source_name") or "") if killing else "",
            "flag_reasons": [] if exempt else flag_reasons,
            "flagged": bool(flag_reasons) and not exempt,
        })
        hostiles.append(row_out)
    hostiles.sort(key=lambda row: (row["killed_at_ms"], row["target_guid"]))
    unconfirmed.sort(key=lambda row: (row["last_logged_at_ms"], row["target_guid"]))
    dropped = int(combat_log.get("recent_events_dropped") or 0)
    mismatches = [row for row in hostiles if row["flagged"]]
    return {
        "schema": "bot_killed_hostile_damage_reconciliation_v2",
        "tolerance_pct": KILLED_HOSTILE_RECONCILIATION_TOLERANCE_PCT,
        "basis": "sum_landed_overkill_free_damage_vs_max_health",
        "flag_rule": "mismatch_pct_above_tolerance_or_unlogged_health_loss_above_zero",
        "exempt_entries": {str(entry): reason for entry, reason in sorted(RECONCILIATION_EXEMPT_ENTRIES.items())},
        "source": "combat_log_recent_events",
        "event_window_complete": dropped == 0,
        "recent_events_dropped": dropped,
        "killed_hostile_count": len(hostiles),
        "killing_blow_unlogged_count": sum(1 for row in hostiles if row["killing_blow_unlogged"]),
        "mismatch_count": len(mismatches),
        "unconfirmed_death_count": len(unconfirmed),
        "reconciled": dropped == 0 and not mismatches,
        "mismatches": mismatches,
        "hostiles": hostiles,
        "unconfirmed_deaths": unconfirmed,
    }


def full_wipes_from_status(status: Any) -> list[dict[str, Any]]:
    """The native full-wipe edges a status exports (``raid_runtime.full_wipes``); [] without one.

    The server's ledger is scoped to the cohort's native attempt; each row is
    stamped with the status's ``attempt_id`` (when it has one) so a combat log
    from another attempt is never closed by it.
    """
    runtime = status.get("raid_runtime") if isinstance(status, dict) else None
    rows = runtime.get("full_wipes") if isinstance(runtime, dict) else None
    if not isinstance(rows, list):
        return []
    attempt_id = status.get("attempt_id") if isinstance(status, dict) else None
    wipes = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        wipe = dict(row)
        if attempt_id is not None and "attempt_id" not in wipe:
            wipe["attempt_id"] = attempt_id
        wipes.append(wipe)
    return wipes


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def matching_full_wipe(
    full_wipes: list[dict[str, Any]] | None,
    *,
    route_generation: int,
    route_node_id: str,
    pull_at_ms: int,
    capture_last_at_ms: int,
    attempt_id: Any = None,
) -> dict[str, Any] | None:
    """The first native full wipe that ends this attempt, or ``None``.

    The wipe belongs to the attempt by its native boundaries, not by outgoing
    damage (the raid often stops dealing damage before the last member dies):
    the same native attempt (``attempt_id``, when both sides name one), the
    same route node and the same route generation, at or after the pull. A
    wipe that names no route generation is bounded by the generation's last
    captured event instead, because nothing else bounds it.
    """
    if pull_at_ms <= 0:
        return None
    wipes = sorted(
        (row for row in full_wipes or [] if isinstance(row, dict) and _int_or_zero(row.get("at_ms")) > 0),
        key=lambda row: _int_or_zero(row.get("at_ms")),
    )
    for wipe in wipes:
        at_ms = _int_or_zero(wipe.get("at_ms"))
        if at_ms < pull_at_ms:
            continue
        if attempt_id is not None and wipe.get("attempt_id") is not None and str(wipe["attempt_id"]) != str(attempt_id):
            continue
        node = str(wipe.get("route_node_id") or "")
        if node and node != route_node_id:
            continue
        wipe_generation = _int_or_zero(wipe.get("route_generation"))
        if wipe_generation:
            if wipe_generation != route_generation:
                continue
        elif at_ms > capture_last_at_ms:
            continue
        return wipe
    return None


# Fields of a spanning record with no per-record evidence on the wipe's side:
# they are never estimated. Position samples become missing data (0 samples).
_UNATTRIBUTABLE_ROW_FIELDS = ("event_count", "raw_amount", "absorbed_amount", "moving_events", "distance_samples")


def _row_key(row: dict[str, Any]) -> tuple[str, int, bool]:
    return (str(row.get("perspective") or ""), _int_or_zero(row.get("actor_guid")), bool(row.get("source_is_pet")))


def split_rows_at_full_wipe(
    rows: list[dict[str, Any]], buckets: list[dict[str, Any]], at_ms: int
) -> tuple[list[dict[str, Any]], dict[str, Any], set[tuple[str, int, bool]]]:
    """Keep only the evidence of the attempt that ended at ``at_ms``.

    Records are classified by their exact millisecond timestamps: a record
    that ends at or before the wipe is kept, one that starts after it is
    dropped. Only a record that genuinely spans the wipe is split, and only
    with attributable evidence: its own pre-wipe amount is its
    actor/perspective/source per-second buckets before the wipe minus every
    other (non-spanning) record of that key, accepted only when it
    reconciles on both sides of the wipe. The wipe's own second mixes both
    sides, so a split is attributable only when that key's bucket for the
    wipe second is empty (or the wipe is the second's last millisecond);
    the whole second is never admitted. A spanning record that cannot be
    attributed (another spanning record of the same key, no buckets, an
    occupied wipe-second bucket, or buckets that do not reconcile) is never
    estimated: it is credited with nothing and reported unresolved, which
    leaves the window unmeasurable (``full_wipe_split_unresolved``).

    Also returns the keys whose wipe-second bucket is attributable to the
    attempt (a kept record of that key had an event in that second, at or
    before the wipe); the caller keeps only those wipe-second buckets.
    """
    cut_s = at_ms // 1000
    whole_second_before = at_ms % 1000 == 999

    def side(second: int) -> str:
        if second < cut_s or (second == cut_s and whole_second_before):
            return "before"
        return "wipe" if second == cut_s else "after"

    groups: dict[tuple[str, int, bool], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups[_row_key(row)].append(row)
    sums: dict[tuple[str, int, bool], dict[tuple[str, str], int]] = defaultdict(lambda: defaultdict(int))
    for bucket in buckets:
        key = _row_key(bucket)
        where = side(_int_or_zero(bucket.get("second")))
        for field in ("amount", "originated_amount"):
            if field in bucket:
                sums[key][(field, where)] += _int_or_zero(bucket.get(field))
        sums[key][("present", where)] += 1
    kept: list[dict[str, Any]] = []
    wipe_second_keys: set[tuple[str, int, bool]] = set()
    dropped = resolved = 0
    unresolved: list[dict[str, Any]] = []
    for key, group in groups.items():
        before = [row for row in group if _int_or_zero(row.get("last_at_ms")) <= at_ms]
        after = [row for row in group if _int_or_zero(row.get("first_at_ms")) > at_ms]
        settled = {id(row) for row in (*before, *after)}
        spanning = [row for row in group if id(row) not in settled]
        kept.extend(before)
        dropped += len(after)
        if whole_second_before or any(_int_or_zero(row.get("last_at_ms")) // 1000 == cut_s for row in before):
            wipe_second_keys.add(key)
        if not spanning:
            continue
        split = _attributed_split(spanning, before, after, sums.get(key), at_ms)
        if split is None:
            unresolved.extend({
                "perspective": key[0], "actor_guid": key[1], "source_is_pet": key[2],
                "spell_id": _int_or_zero(row.get("spell_id")),
                "target_entry": _int_or_zero(row.get("target_entry")),
                "amount": _int_or_zero(row.get("amount")),
            } for row in spanning)
            continue
        kept.append(split)
        resolved += 1
    return kept, {
        "resolution": "exact_ms_records_one_second_buckets_for_spanning",
        "excluded_after_wipe": dropped,
        "spanning_wipe": resolved + len(unresolved),
        "spanning_split_by_own_second_buckets": resolved,
        "spanning_unresolved": len(unresolved),
        "unresolved_records": unresolved,
    }, wipe_second_keys


def _attributed_split(
    spanning: list[dict[str, Any]],
    before: list[dict[str, Any]],
    after: list[dict[str, Any]],
    sums: dict[tuple[str, str], int] | None,
    at_ms: int,
) -> dict[str, Any] | None:
    """The one spanning record's own pre-wipe part, or ``None`` when it is not attributable."""
    if len(spanning) != 1 or not sums or not (sums[("present", "before")] or sums[("present", "after")]):
        return None
    if sums[("amount", "wipe")] or sums[("originated_amount", "wipe")]:
        return None  # the wipe's own second mixes both sides: not separable
    row = spanning[0]
    split = dict(row)
    for field in ("amount", "originated_amount"):
        if field not in row:
            continue
        own_before = sums[(field, "before")] - sum(_int_or_zero(other.get(field)) for other in before)
        own_after = sums[(field, "after")] - sum(_int_or_zero(other.get(field)) for other in after)
        if own_before < 0 or own_after < 0 or own_before + own_after != _int_or_zero(row.get(field)):
            return None
        split[field] = own_before
    if "shared_amount" in row:
        split["shared_amount"] = split["amount"] - split.get("originated_amount", split["amount"])
    for field in _UNATTRIBUTABLE_ROW_FIELDS:
        if field in split:
            split[field] = 0
    split["last_at_ms"] = at_ms
    split["split_at_full_wipe"] = True
    split["split_unattributed_fields"] = [field for field in _UNATTRIBUTABLE_ROW_FIELDS if field in row]
    return split


def close_encounters_at_full_wipes(
    encounters: list[dict[str, Any]], full_wipes: list[dict[str, Any]] | None
) -> None:
    """Mark already-aggregated windows that a native full wipe ended.

    Window bounds only: ``analyze_combat_log`` splits the evidence at the wipe
    *before* it aggregates, so prefer passing ``full_wipes`` there. A window
    that already carries an ``attempt_outcome`` is left unchanged, as is every
    window without a matching wipe (byte-identical).
    """
    for encounter in encounters:
        if encounter.get("attempt_outcome"):
            continue
        first = _int_or_zero(encounter.get("first_at_ms"))
        last = _int_or_zero(encounter.get("last_at_ms"))
        wipe = matching_full_wipe(
            full_wipes,
            route_generation=_int_or_zero(encounter.get("route_generation")),
            route_node_id=str(encounter.get("route_node_id") or ""),
            pull_at_ms=first,
            capture_last_at_ms=max(last, _int_or_zero(encounter.get("capture_last_at_ms"))),
        )
        if wipe is None:
            continue
        at_ms = _int_or_zero(wipe.get("at_ms"))
        encounter["unclipped_last_at_ms"] = last
        encounter["last_at_ms"] = at_ms
        encounter["duration_sec"] = round(max(1.0, (at_ms - first) / 1000.0), 3)
        _mark_full_wipe(encounter, wipe)


def _mark_full_wipe(encounter: dict[str, Any], wipe: dict[str, Any]) -> None:
    encounter["full_wipe_at_ms"] = _int_or_zero(wipe.get("at_ms"))
    encounter["full_wipe_generation"] = _int_or_zero(wipe.get("wipe_generation"))
    encounter["attempt_outcome"] = "full_wipe"
    encounter["encounter_window_boundary_basis"] = "first_positive_originated_damage_to_full_wipe"


def _full_wipe_cuts(
    by_generation: dict[int, list[dict[str, Any]]],
    buckets: list[dict[str, Any]],
    full_wipes: list[dict[str, Any]] | None,
    attempt_id: Any,
) -> dict[int, dict[str, Any]]:
    """Per route generation, the native full wipe that ended its attempt and its pre-wipe evidence."""
    cuts: dict[int, dict[str, Any]] = {}
    if not full_wipes:
        return cuts
    for generation, rows in by_generation.items():
        timestamps = [
            value
            for row in rows
            for value in (_int_or_zero(row.get("first_at_ms")), _int_or_zero(row.get("last_at_ms")))
            if value > 0
        ]
        damage = [
            row for row in rows
            if row.get("perspective") == "damage_done" and _originated_amount(row) > 0
        ]
        damage_timestamps = [
            value
            for row in damage
            for value in (_int_or_zero(row.get("first_at_ms")), _int_or_zero(row.get("last_at_ms")))
            if value > 0
        ]
        capture_last = max(timestamps, default=0)
        node_id = next((str(row.get("route_node_id") or "") for row in rows if row.get("route_node_id")), "")
        pull_at_ms = min(damage_timestamps, default=min(timestamps, default=0))
        wipe = matching_full_wipe(
            full_wipes,
            route_generation=generation,
            route_node_id=node_id,
            pull_at_ms=pull_at_ms,
            capture_last_at_ms=capture_last,
            attempt_id=attempt_id,
        )
        if wipe is None:
            continue
        at_ms = _int_or_zero(wipe.get("at_ms"))
        generation_buckets = [
            row for row in buckets if _int_or_zero(row.get("route_generation")) == generation
        ]
        kept, evidence, wipe_second_keys = split_rows_at_full_wipe(rows, generation_buckets, at_ms)
        cuts[generation] = {
            "wipe": wipe,
            "at_ms": at_ms,
            "rows": kept,
            "evidence": evidence,
            "wipe_second_keys": wipe_second_keys,
            "unclipped_last_at_ms": max(damage_timestamps, default=capture_last),
            "unclipped_capture_last_at_ms": capture_last,
            # The attempt's identity and pull stay those of its whole evidence,
            # even when an unresolved split leaves no credited record.
            "pull_at_ms": pull_at_ms,
            "route_node_id": node_id,
            "route_label": next((str(row.get("route_label") or "") for row in rows if row.get("route_label")), ""),
        }
    return cuts


def _bucket_in_attempt(row: dict[str, Any], cuts: dict[int, dict[str, Any]]) -> bool:
    """A per-second bucket belongs to the attempt: before the wipe's second, or in it when attributable."""
    cut = cuts.get(_int_or_zero(row.get("route_generation")))
    if cut is None:
        return True
    second, cut_s = _int_or_zero(row.get("second")), int(cut["at_ms"]) // 1000
    return second < cut_s or (second == cut_s and _row_key(row) in cut["wipe_second_keys"])


def _drop_after_full_wipe(
    rows: list[dict[str, Any]], cuts: dict[int, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Drop outcome/rejection records that began after their generation's full wipe."""
    kept = []
    for row in rows:
        cut = cuts.get(_int_or_zero(row.get("route_generation")))
        if cut is not None and _int_or_zero(row.get("first_at_ms")) > int(cut["at_ms"]):
            continue
        kept.append(row)
    return kept


def analyze_combat_log(
    combat_log: dict[str, Any],
    unit_deaths: list[dict[str, Any]] | None = None,
    full_wipes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Return encounter, DPS/HPS, rotation, pet, and positioning diagnostics.

    ``unit_deaths`` (optional) confirms deaths whose killing blow was not
    logged; see ``killed_hostile_damage_reconciliation``. ``full_wipes``
    (optional, the status's ``raid_runtime.full_wipes``) ends an encounter
    at the first native full wipe of its attempt (same attempt, route node and
    route generation): its evidence is split at the wipe before aggregation.
    """
    schema_version = _combat_log_schema_version(combat_log)
    friendly_split_available = (
        schema_version >= 3
        and combat_log.get("damage_attribution_schema")
        == "originated_amount_v2_friendly_split"
    )
    abilities = [row for row in combat_log.get("abilities") or [] if isinstance(row, dict)]
    buckets = [row for row in combat_log.get("second_buckets") or [] if isinstance(row, dict)]
    action_outcomes = [
        row for row in combat_log.get("action_outcomes") or [] if isinstance(row, dict)
    ]
    candidate_rejections = [
        row for row in combat_log.get("candidate_rejections") or []
        if isinstance(row, dict)
    ]
    by_generation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in abilities:
        by_generation[int(row.get("route_generation") or 0)].append(row)
    logged_counts = (len(buckets), len(action_outcomes), len(candidate_rejections))
    wipe_cuts = _full_wipe_cuts(by_generation, buckets, full_wipes, combat_log.get("attempt_id"))
    if wipe_cuts:
        # A native full wipe ends the attempt: split its evidence at the wipe
        # before any actor, ability, healing or DPS aggregate is computed.
        for generation, cut in wipe_cuts.items():
            by_generation[generation] = cut["rows"]
        buckets = [row for row in buckets if _bucket_in_attempt(row, wipe_cuts)]
        action_outcomes = _drop_after_full_wipe(action_outcomes, wipe_cuts)
        candidate_rejections = _drop_after_full_wipe(candidate_rejections, wipe_cuts)
    action_outcomes_by_generation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in action_outcomes:
        action_outcomes_by_generation[int(row.get("route_generation") or 0)].append(row)
    candidate_rejections_by_generation: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in candidate_rejections:
        candidate_rejections_by_generation[int(row.get("route_generation") or 0)].append(row)

    raw_bucket_seconds: dict[tuple[int, int, str, bool], set[int]] = defaultdict(set)
    originated_bucket_seconds: dict[tuple[int, int, str, bool], set[int]] = defaultdict(set)
    for row in buckets:
        perspective = str(row.get("perspective") or "")
        if perspective == "friendly_damage_done" and not friendly_split_available:
            # Legacy payloads cannot carry a trustworthy friendly split. Keep
            # them readable without inventing one from an unknown row.
            continue
        # Second buckets carry no spell or target, so an environmental
        # self-hit's second stays in the active-combat denominator exactly as
        # before; only the damage numerators move to ``environmental_damage``.
        raw_amount = _raw_event_amount(row)
        originated_amount = _originated_amount(row)
        key = (
            int(row.get("route_generation") or 0),
            int(row.get("actor_guid") or 0),
            perspective,
            bool(row.get("source_is_pet")),
        )
        if raw_amount > 0:
            raw_bucket_seconds[key].add(int(row.get("second") or 0))
        if originated_amount > 0:
            originated_bucket_seconds[key].add(int(row.get("second") or 0))

    encounters: list[dict[str, Any]] = []
    diagnostics: list[dict[str, Any]] = []
    for generation in sorted(by_generation):
        rows = by_generation[generation]
        timestamps = [int(row.get("first_at_ms") or 0) for row in rows] + [int(row.get("last_at_ms") or 0) for row in rows]
        timestamps = [value for value in timestamps if value > 0]
        capture_first_ms = min(timestamps, default=0)
        capture_last_ms = max(timestamps, default=capture_first_ms)
        originated_damage_rows = [
            row
            for row in rows
            if row.get("perspective") == "damage_done"
            and _originated_amount(row) > 0
        ]
        damage_timestamps = [
            int(row.get("first_at_ms") or 0)
            for row in originated_damage_rows
        ] + [
            int(row.get("last_at_ms") or 0)
            for row in originated_damage_rows
        ]
        damage_timestamps = [value for value in damage_timestamps if value > 0]
        # WCL Summary DPS uses the fight window, not the lifetime of cleanup
        # telemetry. Healing, callbacks, and route-terminal heartbeats may
        # continue after the boss is dead and must not dilute hostile damage.
        # Keep the full capture bounds below so the tail remains diagnostic.
        first_ms = min(damage_timestamps, default=capture_first_ms)
        last_ms = max(damage_timestamps, default=capture_last_ms)
        cut = wipe_cuts.get(generation)
        if cut is not None:
            first_ms = int(cut["pull_at_ms"])
            last_ms = int(cut["at_ms"])
        duration_sec = max(1.0, (last_ms - first_ms) / 1000.0)
        capture_duration_sec = max(
            1.0, (capture_last_ms - capture_first_ms) / 1000.0
        )
        party_damage_seconds: set[int] = set()
        raw_event_damage_seconds: set[int] = set()
        for (bucket_generation, _actor_guid, perspective, _source_is_pet), seconds in originated_bucket_seconds.items():
            if bucket_generation == generation and perspective == "damage_done":
                party_damage_seconds.update(seconds)
        for (bucket_generation, _actor_guid, perspective, _source_is_pet), seconds in raw_bucket_seconds.items():
            if bucket_generation == generation and (
                perspective == "damage_done"
                or (friendly_split_available and perspective == "friendly_damage_done")
            ):
                raw_event_damage_seconds.update(seconds)
        # Keep the legacy active-combat denominator for HPS and elapsed
        # comparability. Provenance changes only the damage numerator; the
        # origin-only active window is exposed separately below.
        combat_seconds = max(1, len(raw_event_damage_seconds))
        node_id = next((str(row.get("route_node_id") or "") for row in rows if row.get("route_node_id")), "")
        label = next((str(row.get("route_label") or "") for row in rows if row.get("route_label")), "")
        if cut is not None:
            node_id, label = node_id or cut["route_node_id"], label or cut["route_label"]

        actor_guids = sorted({int(row.get("actor_guid") or 0) for row in rows if int(row.get("actor_guid") or 0)})
        actors: list[dict[str, Any]] = []
        for actor_guid in actor_guids:
            actor_rows = [row for row in rows if int(row.get("actor_guid") or 0) == actor_guid]
            done = [row for row in actor_rows if row.get("perspective") == "damage_done"]
            # Environmental self-damage is recorded on the friendly side of the
            # split.  Only the friendly (originated) figures exclude it; damage
            # done, every encounter-window field and every raw_event_* field
            # (read by analyze_magmaw_trace) keep their previous meaning.
            friendly_rows = [
                row for row in actor_rows
                if friendly_split_available
                and row.get("perspective") == "friendly_damage_done"
            ]
            environmental = [row for row in friendly_rows if is_environmental_self_damage(row)]
            friendly = [row for row in friendly_rows if not is_environmental_self_damage(row)]
            environmental_damage = sum(_raw_event_amount(row) for row in environmental)
            taken = [row for row in actor_rows if row.get("perspective") == "damage_taken"]
            healing = [row for row in actor_rows if row.get("perspective") == "healing_done"]
            total_damage = sum(_originated_amount(row) for row in done)
            friendly_damage = sum(_originated_amount(row) for row in friendly)
            raw_event_damage = sum(
                _raw_event_amount(row) for row in [*done, *friendly_rows]
            )
            raw_event_friendly_damage = sum(_raw_event_amount(row) for row in friendly_rows)
            total_taken = sum(_raw_event_amount(row) for row in taken)
            total_healing = sum(int(row.get("amount") or 0) for row in healing)
            active_seconds = len(originated_bucket_seconds[(generation, actor_guid, "damage_done", False)])
            pet_active_seconds = len(originated_bucket_seconds[(generation, actor_guid, "damage_done", True)])
            healing_seconds = len(raw_bucket_seconds[(generation, actor_guid, "healing_done", False)])
            ability_summary = _ability_rows(
                done,
                total_damage,
                raw_total_damage=raw_event_damage,
                use_originated=True,
            )
            friendly_ability_summary = _ability_rows(
                friendly,
                friendly_damage,
                raw_total_damage=raw_event_friendly_damage - environmental_damage,
                use_originated=True,
                include_target=True,
            )
            actor_name = next((str(row.get("actor_name") or "") for row in actor_rows if row.get("actor_name")), "")
            actor_role = next((str(row.get("actor_role") or "") for row in actor_rows if row.get("actor_role")), "")
            actor_class_id = next((int(row.get("actor_class_id") or 0) for row in actor_rows if row.get("actor_class_id")), 0)
            pet_damage = sum(int(row["damage"]) for row in ability_summary if row.get("source_is_pet"))
            raw_event_pet_damage = sum(
                _raw_event_amount(row)
                for row in [*done, *friendly]
                if row.get("source_is_pet")
            )
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
                # WCL's Summary DPS uses the selected fight window.  Keep an
                # explicit name for that denominator so downstream evidence
                # cannot confuse it with the legacy active-combat `dps` or
                # actor damage-bearing `active_dps`.
                "encounter_window_dps": round(total_damage / duration_sec, 3),
                "encounter_window_dps_basis": "originated_damage_over_duration_sec",
                # Originated damage done per target creature entry (0 = no entry), so a
                # consumer can scope native DPS to a reference's enemy set.
                "damage_by_target_entry": _damage_by_target_entry(done),
                "raw_event_damage": raw_event_damage,
                "raw_event_dps": round(raw_event_damage / max(1, len(raw_event_damage_seconds)), 3),
                "friendly_damage": friendly_damage,
                "raw_event_friendly_damage": raw_event_friendly_damage,
                # Falling/lava/drowning self-damage: never friendly or done.
                "environmental_damage": environmental_damage,
                "environmental_sources": _ability_rows(environmental, environmental_damage),
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
                "raw_event_pet_damage": raw_event_pet_damage,
                "raw_event_pet_damage_share": round(
                    raw_event_pet_damage / max(1, raw_event_damage), 6
                ),
                "pet_active_seconds": pet_active_seconds,
                "pet_active_dps": round(pet_damage / max(1, pet_active_seconds), 3),
                "pet_uptime": round(pet_active_seconds / combat_seconds, 6),
                "distance_avg": _rounded(_weighted_average(player_done, "distance_avg"), 3),
                "moving_fraction": _rounded(_weighted_average(player_done, "moving_fraction"), 6),
                "distance_samples": _sampled_total(player_done),
                "abilities": ability_summary,
                "friendly_abilities": friendly_ability_summary,
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
            # Only positioned events can show a ranged actor standing too close.
            sampled_player_events = _sampled_total(player_done)
            player_distance = _weighted_average(player_done, "distance_avg")
            if (
                actor_class_id in RANGED_CLASS_IDS
                and sampled_player_events >= 10
                and player_distance is not None
                and player_distance < 8.0
            ):
                diagnostics.append({
                    "severity": "warning",
                    "kind": "ranged_damage_too_close",
                    "route_generation": generation,
                    "route_node_id": node_id,
                    "actor_guid": actor_guid,
                    "actor_name": actor_name,
                    "distance_avg": round(player_distance, 3),
                    "distance_samples": sampled_player_events,
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
        party_friendly_damage = sum(int(row["friendly_damage"]) for row in actors)
        party_raw_event_friendly_damage = sum(
            int(row["raw_event_friendly_damage"]) for row in actors
        )
        party_healing = sum(int(row["healing"]) for row in actors)
        outgoing_rows = [
            row for row in rows
            if row.get("perspective") == "damage_done"
            or (friendly_split_available and row.get("perspective") == "friendly_damage_done")
        ]
        encounters.append({
            "route_generation": generation,
            "route_node_id": node_id,
            "route_label": label,
            "first_at_ms": first_ms,
            "last_at_ms": last_ms,
            "duration_sec": round(duration_sec, 3),
            "capture_first_at_ms": capture_first_ms,
            "capture_last_at_ms": capture_last_ms,
            "capture_duration_sec": round(capture_duration_sec, 3),
            "encounter_window_boundary_basis": (
                "first_to_last_positive_originated_damage_done"
                if damage_timestamps
                else "full_capture_fallback_no_originated_damage"
            ),
            "combat_duration_sec": combat_seconds,
            "originated_damage_seconds": len(party_damage_seconds),
            "party_damage": party_damage,
            "party_dps": round(party_damage / combat_seconds, 3),
            "elapsed_party_dps": round(party_damage / duration_sec, 3),
            "encounter_window_party_dps": round(party_damage / duration_sec, 3),
            "encounter_window_party_dps_basis": "originated_damage_over_duration_sec",
            "raw_event_damage": sum(_raw_event_amount(row) for row in outgoing_rows),
            "raw_event_dps": round(
                sum(_raw_event_amount(row) for row in outgoing_rows)
                / max(1, len(raw_event_damage_seconds)),
                3,
            ),
            "party_friendly_damage": party_friendly_damage,
            "party_raw_event_friendly_damage": party_raw_event_friendly_damage,
            "party_environmental_damage": sum(int(row["environmental_damage"]) for row in actors),
            "party_healing": party_healing,
            "party_hps": round(party_healing / combat_seconds, 3),
            "elapsed_party_hps": round(party_healing / duration_sec, 3),
            "party_damage_taken": sum(int(row["damage_taken"]) for row in actors),
            "action_outcome_count": len(action_outcomes_by_generation.get(generation, [])),
            "action_outcomes": _compact_action_outcomes(
                action_outcomes_by_generation.get(generation, [])
            ),
            "candidate_rejection_count": len(
                candidate_rejections_by_generation.get(generation, [])
            ),
            "candidate_rejections": _compact_candidate_rejections(
                candidate_rejections_by_generation.get(generation, [])
            ),
            "actors": actors,
        })
        if cut is not None:
            encounters[-1].update({
                "unclipped_last_at_ms": cut["unclipped_last_at_ms"],
                "unclipped_capture_last_at_ms": cut["unclipped_capture_last_at_ms"],
                "full_wipe_evidence_split": cut["evidence"],
            })
            if cut["evidence"]["spanning_unresolved"]:
                # No attributable split: the attempt's figures are incomplete,
                # never an estimate, and the window is not measurable.
                encounters[-1]["full_wipe_split_unresolved"] = True
                encounters[-1]["full_wipe_split_unresolved_actor_guids"] = sorted({
                    int(row["actor_guid"]) for row in cut["evidence"]["unresolved_records"]})
            _mark_full_wipe(encounters[-1], cut["wipe"])

    return {
        "schema": "bot_combat_analysis_v3",
        "source_schema_version": combat_log.get("combat_log_schema_version"),
        "tracked_event_count": int(combat_log.get("event_count") or 0),
        "aggregate_count": int(combat_log.get("aggregate_count") or len(abilities)),
        "second_bucket_count": int(combat_log.get("second_bucket_count") or logged_counts[0]),
        "action_outcome_count": logged_counts[1],
        "candidate_rejection_count": logged_counts[2],
        "recent_event_count": len(combat_log.get("recent_events") or []),
        "recent_events_dropped": int(combat_log.get("recent_events_dropped") or 0),
        "all_events_preserved_in_aggregates": True,
        "encounters": encounters,
        "diagnostics": diagnostics,
        "killed_hostile_damage_reconciliation": killed_hostile_damage_reconciliation(
            combat_log, unit_deaths
        ),
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

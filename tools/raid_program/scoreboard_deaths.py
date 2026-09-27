"""Encounter-generic helpers for the scoreboard's boss-window death count (round 2, BWD 10N).

Three additions to ``scoreboard_record.death_evidence``; none changes a record whose deaths
already reconciled with the route death count, and none reads anything encounter-specific
except what a raid target declares:

encounter-scoped reconciliation
    The whole-run basis (lethal events == route deaths, no dropped ring-buffer events) fails
    whenever the ring buffer dropped early trash events. When the killed-hostile damage
    reconciliation of the encounter node itself has no mismatch, at least one killed hostile on
    that node, and the retained ring covers the death-accounting interval (the oldest retained
    event belongs to an earlier node and precedes the node's first event and the window start;
    the ring drops oldest first), the in-window lethal events are the boss-window deaths
    (``combat_log_lethal_damage_encounter_reconciled``). Otherwise the count stays unknown.

native death signal
    The final raid runtime's per-member native_recovery counts (native_death_count from
    BotNativeLifeEvents when present, else members with a wipe-scoped death_sequence).
    ``death_signal_conflict`` is true when the combat log shows lethal hits while the native
    signal shows no death at all (run 6bf52232: 1103 lethal events, 0 native deaths).

boss-window death exemptions (target ``boss_window_death_exemptions``)
    A phase in which deaths do not fail a kill (Chimaeron Mortality, user decision
    2026-09-27), scoped per boss attempt (a pull, ended by a reset or wipe; see
    ``boss_attempts``). Within an attempt the phase starts at its first marker: an event carrying
    one of ``spell_ids``, or a damage event leaving a ``boss_entries`` creature at or below
    ``health_pct_at_most`` of its maximum health, and ends at the attempt's last boss event.
    Boss-window deaths inside such an interval are counted under the exemption's ``record_key``
    instead of ``boss_window_deaths``. A target without the field is unaffected.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

ENCOUNTER_RECONCILED_BASIS = "combat_log_lethal_damage_encounter_reconciled"


def _ordered(events: Iterable[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    rows = [event for event in events if isinstance(event, Mapping) and event.get("timestamp_ms")]
    return sorted(rows, key=lambda event: (int(event.get("timestamp_ms") or 0), int(event.get("event_sequence") or 0)))


def death_accounting_coverage(events: Iterable[Mapping[str, Any]], node: str,
                              window_first_ms: int | None) -> dict[str, Any]:
    """Whether the retained ring covers the whole death-accounting interval of the encounter.

    Deaths count from the encounter's route-node start (its first event of any kind: the pull,
    the first hostile hit), not from the first outgoing damage (window_first_ms). The ring drops
    oldest first, so the interval is covered only when the oldest retained event belongs to an
    earlier node and precedes both the node's first retained event and the window start. An
    oldest retained event on the node itself may have lost earlier node events: not covered.
    """
    ordered = _ordered(events)
    earliest = ordered[0] if ordered else None
    node_events = [event for event in ordered if event.get("route_node_id") == node]
    start_candidates = [int(node_events[0]["timestamp_ms"])] if node_events else []
    if window_first_ms is not None:
        start_candidates.append(int(window_first_ms))
    start = min(start_candidates) if start_candidates else None
    covered = (earliest is not None and start is not None
               and earliest.get("route_node_id") != node
               and int(earliest["timestamp_ms"]) <= start)
    return {
        "covered": bool(covered),
        "earliest_retained_at_ms": int(earliest["timestamp_ms"]) if earliest else None,
        "earliest_retained_route_node_id": earliest.get("route_node_id") if earliest else None,
        "death_accounting_start_ms": start,
    }


def encounter_reconciliation(analysis: Mapping[str, Any], log: Mapping[str, Any], node: str,
                             window_first_ms: int | None) -> dict[str, Any] | None:
    """Encounter-scoped reconciliation facts, or None without a killed-hostile reconciliation."""
    reconciliation = analysis.get("killed_hostile_damage_reconciliation")
    if not isinstance(reconciliation, Mapping):
        return None
    hostiles = [row for row in reconciliation.get("hostiles") or [] if isinstance(row, Mapping)]
    mismatches = [row for row in reconciliation.get("mismatches") or [] if isinstance(row, Mapping)]
    dropped = int(log.get("recent_events_dropped") or 0)
    coverage = death_accounting_coverage(log.get("recent_events") or [], node, window_first_ms)
    window_retained = dropped == 0 or coverage["covered"]
    encounter_killed = sum(row.get("route_node_id") == node for row in hostiles)
    encounter_mismatches = sum(row.get("route_node_id") == node for row in mismatches)
    return {
        "mismatch_count": int(reconciliation.get("mismatch_count") or len(mismatches)),
        "encounter_mismatch_count": encounter_mismatches,
        "encounter_killed_hostiles": encounter_killed,
        "recent_events_dropped": dropped,
        "earliest_retained_at_ms": coverage["earliest_retained_at_ms"],
        "earliest_retained_route_node_id": coverage["earliest_retained_route_node_id"],
        "death_accounting_start_ms": coverage["death_accounting_start_ms"],
        "window_first_at_ms": window_first_ms,
        "window_retained": window_retained,
        "reconciled": encounter_mismatches == 0 and encounter_killed > 0 and window_retained,
    }


def _raid_runtime(report: Mapping[str, Any] | None) -> Mapping[str, Any] | None:
    report = report or {}
    status = report.get("status") if isinstance(report.get("status"), Mapping) else {}
    for runtime in (status.get("raid_runtime"), report.get("accepted_raid_runtime")):
        if isinstance(runtime, Mapping) and isinstance(runtime.get("native_recovery"), Mapping):
            return runtime
    return None


def native_death_signal(report: Mapping[str, Any] | None) -> dict[str, Any] | None:
    """Native per-member death evidence from the final raid runtime; None when absent."""
    runtime = _raid_runtime(report)
    if runtime is None:
        return None
    members = [row for row in runtime["native_recovery"].get("members") or [] if isinstance(row, Mapping)]
    if not members:
        return None
    counted = all("native_death_count" in row for row in members)
    if counted:
        deaths = sum(int(row.get("native_death_count") or 0) for row in members)
        resurrections = sum(int(row.get("native_resurrection_count") or 0) for row in members)
        basis = "native_life_edges"
    else:
        deaths = sum(int(row.get("death_sequence") or 0) > 0 for row in members)
        resurrections = sum(int(row.get("resurrection_sequence") or 0) > 0 for row in members)
        basis = "wipe_scoped_death_sequence"
    return {"basis": basis, "members": len(members), "deaths": deaths, "resurrections": resurrections}


def death_signal_fields(lethal_count: int, signal: dict[str, Any] | None) -> dict[str, Any]:
    """death_signal_conflict: lethal combat-log hits while the native signal saw no death."""
    if signal is None:
        return {}
    return {"native_death_signal": signal,
            "death_signal_conflict": lethal_count > 0 and int(signal["deaths"]) == 0}


class ExemptionConfigError(ValueError):
    """A boss_window_death_exemptions entry is malformed; the scoreboard refuses rather than guessing."""


def death_exemptions(target: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """The target's validated boss-window death exemptions (empty when the field is absent)."""
    if not target or "boss_window_death_exemptions" not in target:
        return []
    value = target["boss_window_death_exemptions"]
    if not isinstance(value, list):
        raise ExemptionConfigError("boss_window_death_exemptions must be a list")
    exemptions = []
    for row in value:
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise ExemptionConfigError(f"exemption needs an id: {row!r}")
        key = row.get("record_key")
        if not isinstance(key, str) or not key.endswith("_deaths") or key == "boss_window_deaths":
            raise ExemptionConfigError(f"exemption {row['id']} needs a record_key ending in _deaths")
        spells = row.get("spell_ids") or []
        entries = row.get("boss_entries") or []
        pct = row.get("health_pct_at_most")
        if not all(isinstance(spell, int) for spell in spells) or not all(isinstance(e, int) for e in entries):
            raise ExemptionConfigError(f"exemption {row['id']}: spell_ids and boss_entries are integer lists")
        if pct is not None and (not isinstance(pct, (int, float)) or not 0 < pct < 100 or not entries):
            raise ExemptionConfigError(f"exemption {row['id']}: health_pct_at_most needs boss_entries and 0-100")
        if not spells and pct is None:
            raise ExemptionConfigError(f"exemption {row['id']} declares no start marker")
        exemptions.append(row)
    return exemptions


# A boss attempt (one pull) ends at a reset or wipe. In the combat log that shows as: a new boss
# object (guid), the boss's health back up by more than ATTEMPT_RESET_HEALTH_PCT of its maximum
# between two hits on it (evade/reset), or no boss event in either direction for ATTEMPT_GAP_MS
# (a wipe's release, runback and rebuff).
ATTEMPT_GAP_MS = 30000
ATTEMPT_RESET_HEALTH_PCT = 5.0


def _boss_events(events: Iterable[Mapping[str, Any]], entries: set[int], spells: set[int]) -> list[Mapping[str, Any]]:
    return [event for event in _ordered(events)
            if int(event.get("target_entry") or 0) in entries or int(event.get("source_entry") or 0) in entries
            or (spells and int(event.get("spell_id") or 0) in spells)]


def boss_attempts(events: Iterable[Mapping[str, Any]], entries: set[int],
                  spells: set[int] = frozenset()) -> list[list[Mapping[str, Any]]]:
    """The boss events of each attempt (pull), in order."""
    attempts: list[list[Mapping[str, Any]]] = []
    last_at = None
    last_guid = None
    last_after_pct = None
    for event in _boss_events(events, entries, spells):
        at = int(event["timestamp_ms"])
        on_boss = int(event.get("target_entry") or 0) in entries
        guid = int((event.get("target_guid") if on_boss else event.get("source_guid")) or 0) or None
        observation = event.get("landed_damage_observation") or {}
        before = int(observation.get("target_health_before_damage") or 0) if on_boss else 0
        maximum = int(observation.get("target_max_health") or 0) if on_boss else 0
        before_pct = before * 100.0 / maximum if before > 0 and maximum > 0 else None
        new_attempt = (not attempts or last_at is None or at - last_at > ATTEMPT_GAP_MS
                       or (guid is not None and last_guid is not None and guid != last_guid)
                       or (before_pct is not None and last_after_pct is not None
                           and before_pct > last_after_pct + ATTEMPT_RESET_HEALTH_PCT))
        if new_attempt:
            attempts.append([])
            last_after_pct = None
        attempts[-1].append(event)
        last_at = at
        if guid is not None:
            last_guid = guid
        if before_pct is not None:
            last_after_pct = (before - int(event.get("amount") or 0)) * 100.0 / maximum
    return attempts


def _marker(event: Mapping[str, Any], spells: set[int], entries: set[int], pct: float | None) -> str | None:
    spell = int(event.get("spell_id") or 0)
    if spell and spell in spells:
        return f"spell_{spell}"
    if pct is None or event.get("kind") != "damage" or int(event.get("target_entry") or 0) not in entries:
        return None
    observation = event.get("landed_damage_observation") or {}
    before = int(observation.get("target_health_before_damage") or 0)
    maximum = int(observation.get("target_max_health") or 0)
    if before > 0 and maximum > 0 and (before - int(event.get("amount") or 0)) * 100.0 <= float(pct) * maximum:
        return f"boss_health_at_most_{pct:g}_pct"
    return None


def exemption_intervals(events: Iterable[Mapping[str, Any]], exemption: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Per attempt, the exempt phase: from its first marker to the attempt's last boss event.

    A marker never carries into a later attempt: a wipe at 19% does not exempt the next pull.
    """
    spells = set(exemption.get("spell_ids") or [])
    entries = set(exemption.get("boss_entries") or [])
    pct = exemption.get("health_pct_at_most")
    intervals = []
    for attempt in boss_attempts(events, entries, spells):
        for event in attempt:
            marker = _marker(event, spells, entries, pct)
            if marker:
                intervals.append({"started_at_ms": int(event["timestamp_ms"]),
                                  "ended_at_ms": int(attempt[-1]["timestamp_ms"]), "marker": marker})
                break
    return intervals


def exemption_start(events: Iterable[Mapping[str, Any]], exemption: Mapping[str, Any]) -> dict[str, Any] | None:
    """The first attempt's exempt-phase start, or None when no attempt reached the phase."""
    intervals = exemption_intervals(events, exemption)
    return {"started_at_ms": intervals[0]["started_at_ms"], "marker": intervals[0]["marker"]} if intervals else None


def apply_exemptions(deaths: list[dict[str, Any]], events: list[Mapping[str, Any]],
                     exemptions: list[dict[str, Any]]) -> tuple[int, dict[str, Any]]:
    """Mark in-window deaths inside an exempt phase; returns (non-exempt window deaths, record fields)."""
    fields: dict[str, Any] = {}
    summary: dict[str, Any] = {}
    for exemption in exemptions:
        intervals = exemption_intervals(events, exemption)
        count = 0
        for death in deaths:
            if not death["in_boss_window"] or "exemption" in death:
                continue
            if any(row["started_at_ms"] <= death["timestamp_ms"] <= row["ended_at_ms"] for row in intervals):
                death["exemption"] = exemption["id"]
                count += 1
        fields[exemption["record_key"]] = count
        first = intervals[0] if intervals else {"started_at_ms": None, "marker": None}
        summary[exemption["id"]] = {"record_key": exemption["record_key"], "deaths": count,
                                    "started_at_ms": first["started_at_ms"], "marker": first["marker"],
                                    "intervals": intervals}
    window = sum(death["in_boss_window"] and "exemption" not in death for death in deaths)
    return window, {**fields, "boss_window_death_exemptions": summary}

"""Record-time inputs for the run-sanity checks (tools.raid_program.run_sanity).

``sanity_input_fields(run_dir, target, root)`` returns ``{"sanity_inputs": {...}}``, an additive,
informational field of new ``raid_scoreboard_kill_v1`` records (scoreboard_record.record_from_run_dir).
Nothing in counting or the verdict reads it, so ``evaluate_target`` output is unchanged; records written
before it existed simply lack it and run_sanity reports the dependent checks as not evaluable.

It holds the facts the stored record did not keep:

deaths
    A lethal-damage scan of the retained combat log that runs whatever the route death count says.
    ``death_evidence`` returns early with 0 when ``route_deaths`` is 0, so a clear whose bots were
    revived in place (BWD 10N round 2 Nefarian: route_deaths 0-2, 1,045-1,207 native deaths) could
    record 0 boss-window deaths. Also the native death signal of the final raid runtime.
combat_log
    Whether the combat log was available, how many ring events it retained and dropped, whether the
    ring still covers the boss window, and whether the harness truncated its capture (16 MB cap).
enrage_pulls
    For each calibration-registry creature of this scenario with ``enrage_after_ms``: the pulls inside
    the boss window (the same pull detection the fidelity code uses for its post-enrage cut) and how
    long the enrage anchors stayed engaged in each, so a kill that ran past Berserk is distinguishable
    from a window that spans several pulls.
health_half
    Of the hits bots took inside the boss window (combat-log damage with the target's health before
    the hit and its maximum), how many found the bot at exactly half its maximum health (+-1 hp). BWD
    10N round 2 Nefarian: seeded-lockout bots loaded with an invalid instance were repopped at their
    homebind every tick and revived at 50%, so 93-95% of the hits they took found them at half health.
revives
    How fast bots came back after dying in the boss window (BossWindow: the node-or-time attribution of
    death_evidence; deaths outside it are only counted, since recovered trash deaths are fine).
    ``native``: per member with native life edges, the last death and last resurrection times of the
    final raid runtime, whether the death is in the boss window, and their gap when it was measured (round
    2 Nefarian: 2-11 ms); a resurrection the producer inferred (native_dead true, or marked inferred) is
    not a measurement. ``combat_log``: per bot, the shortest time from a boss-window lethal hit to the next
    hit that found it alive; a short gap proves an instant revive, a long one proves nothing.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "raid_run_sanity_inputs_v1"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def capture_truncated(report: Mapping[str, Any] | None) -> bool:
    """The harness cut the worldserver output capture (so the combat log may be partial or missing)."""
    report = report or {}
    transport = report.get("combat_calibration_transport")
    return bool((isinstance(transport, Mapping) and transport.get("capture_truncated"))
                or "worldserver_output_truncated" in (report.get("failure_labels") or []))


def enrage_rows(registry: Mapping[str, Any] | None, scenario: str,
                entries: set[int] = frozenset()) -> dict[int, dict[str, Any]]:
    """Registry creatures with a scripted enrage that belong to this scenario.

    A row belongs when its raid, mode and boss spell the scenario id (``<raid>_<mode>_<boss>``, the
    raid-target naming) or its entry is one of ``entries`` (bosses the run's fidelity block saw).
    """
    rows = {}
    for key, row in ((registry or {}).get("creatures") or {}).items():
        if not isinstance(row, dict) or not isinstance(row.get("enrage_after_ms"), (int, float)):
            continue
        if row["enrage_after_ms"] <= 0:
            continue
        spelled = f"{row.get('raid')}_{str(row.get('mode') or '').lower()}_{row.get('boss')}"
        if spelled == scenario or _int(key) in entries:
            rows[_int(key)] = row
    return rows


def enrage_pulls(events: list[Mapping[str, Any]], window: Mapping[str, Any] | None,
                 entry: int, row: Mapping[str, Any]) -> dict[str, Any] | None:
    """Pulls of one enrage creature inside the boss window and each pull's engaged time.

    A pull's engaged time runs from its start to the last anchor event before the next pull. The
    fidelity code (live_validation_fidelity._pull_starts) defines the pull starts.
    """
    from tools.bot_ml.live_validation_fidelity import PULL_EVENT_KINDS, _pull_starts
    if not window:
        return None
    first, last = _int(window.get("first_at_ms")), _int(window.get("last_at_ms"))
    if first <= 0 or last <= first:
        return None
    anchors = {_int(value) for value in row.get("enrage_anchor_entries") or []} or {entry}
    enrage_ms = int(row["enrage_after_ms"])
    starts = _pull_starts(first, events, anchors)
    anchor_times = sorted(_int(event.get("timestamp_ms")) for event in events
                          if isinstance(event, Mapping) and event.get("kind") in PULL_EVENT_KINDS
                          and first <= _int(event.get("timestamp_ms")) <= last
                          and (_int(event.get("source_entry")) in anchors or _int(event.get("target_entry")) in anchors))
    engaged, post_enrage = [], 0
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else last + 1
        inside = [at for at in anchor_times if start <= at < end]
        engaged.append(round(((inside[-1] if inside else start) - start) / 1000.0, 3))
        post_enrage += sum(at >= start + enrage_ms for at in inside)
    return {"name": row.get("name"), "enrage_after_ms": enrage_ms, "anchor_entries": sorted(anchors),
            "pulls": len(starts), "engaged_sec": engaged, "longest_engaged_sec": max(engaged),
            "post_enrage_anchor_events": post_enrage}


def _death_scan(run_dir: Path, node: str, target: Mapping[str, Any]) -> dict[str, Any]:
    from tools.raid_program.scoreboard_record import death_evidence
    evidence = death_evidence(run_dir, node, None, dict(target))  # never the route_deaths == 0 shortcut
    known = not str(evidence.get("death_basis") or "").startswith("unknown")
    in_window: dict[str, int] = {}
    for death in evidence.get("deaths") or []:
        if death.get("in_boss_window"):
            in_window[str(death.get("actor_id"))] = in_window.get(str(death.get("actor_id")), 0) + 1
    return {
        "basis": evidence.get("death_basis"),
        "lethal_events": len(evidence.get("deaths") or []) if known else None,
        "lethal_events_in_boss_window": sum(in_window.values()) if known else None,
        "lethal_events_in_boss_window_by_actor": dict(sorted(in_window.items())) if known else None,
        "native_death_signal": evidence.get("native_death_signal"),
        "death_signal_conflict": evidence.get("death_signal_conflict"),
    }


def _before_and_max(event: Mapping[str, Any]) -> tuple[int | None, int]:
    observation = event.get("landed_damage_observation") or {}
    before = observation.get("target_health_before_damage")
    return (None if before is None else _int(before)), _int(observation.get("target_max_health"))


def _party_hits(events: list[Mapping[str, Any]], analysis: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    """Damage events on party members (the analyzer's encounter actors and every logged actor), in time order."""
    encounters = [row for row in (analysis or {}).get("encounters") or [] if isinstance(row, Mapping)]
    party = {_int(actor.get("actor_guid")) for row in encounters for actor in row.get("actors") or []
             if isinstance(actor, Mapping)}
    party |= {_int(event.get("actor_guid")) for event in events if event.get("actor_guid")}
    party.discard(0)
    hits = [event for event in events if event.get("kind") == "damage" and _int(event.get("target_guid")) in party]
    return sorted(hits, key=lambda event: (_int(event.get("timestamp_ms")), _int(event.get("event_sequence"))))


NATIVE_EVENT_MATCH_MS = 50  # a native death edge and the combat-log lethal hit that caused it


class BossWindow:
    """Boss-window attribution shared by every per-event input, as scoreboard_record.death_evidence does it:
    an event is in the window when it is on the encounter route node or inside the analysed damage window
    (the encounter's first to last damage). A bare time (a native life edge has no node) is in it only
    inside the analysed damage window; nothing else on the node (e.g. a pre-pull heal) widens it."""

    def __init__(self, window: Mapping[str, Any] | None, node: str) -> None:
        self.node = node
        self.first = _int((window or {}).get("first_at_ms"))
        self.last = _int((window or {}).get("last_at_ms"))
        self.known = window is not None and self.first > 0 and self.last >= self.first
        self.start, self.end = (self.first, self.last) if self.known else (0, 0)

    def has_event(self, event: Mapping[str, Any]) -> bool:
        at = _int(event.get("timestamp_ms"))
        return self.known and (event.get("route_node_id") == self.node or self.first <= at <= self.last)

    def has_time(self, at: int) -> bool:
        return self.known and self.first <= at <= self.last


def health_half(hits: list[Mapping[str, Any]], boss: BossWindow, tolerance_hp: int = 1) -> dict[str, Any] | None:
    """Hits taken in the boss window with a known health before the hit, and how many found the bot at
    exactly half its maximum health (+-tolerance_hp). None without a boss window."""
    if not boss.known:
        return None
    counted: dict[str, list[int]] = {}
    for event in hits:
        if not boss.has_event(event):
            continue
        before, maximum = _before_and_max(event)
        if not before or maximum <= 0:
            continue
        row = counted.setdefault(str(_int(event.get("target_guid"))), [0, 0])
        row[0] += 1
        row[1] += abs(before - maximum / 2.0) <= tolerance_hp
    total = sum(row[0] for row in counted.values())
    at_half = sum(row[1] for row in counted.values())
    return {"hits": total, "at_half": at_half, "fraction": round(at_half / total, 4) if total else None,
            "tolerance_hp": tolerance_hp,
            "by_actor": {actor: {"hits": row[0], "at_half": row[1]} for actor, row in sorted(counted.items())}}


def _native_gap(member: Mapping[str, Any]) -> tuple[int | None, str | None]:
    """(gap_ms, None) when the last death and a later resurrection were both observed, else (None, why).

    BotNativeLifeEvents StepLethal infers an unobserved resurrection when a lethal hit lands on a bot it
    still holds dead, stamping it with that new death's time: equal timestamps and native_dead true. That
    is no measurement. Neither is a resurrection a record marks as inferred, one before the last death,
    or equal timestamps without native_dead to tell them apart.
    """
    died, back = _int(member.get("native_last_death_ms")), _int(member.get("native_last_resurrection_ms"))
    dead = member.get("native_dead")
    if any(value for key, value in member.items() if "inferred" in str(key) and "resurrection" in str(key)):
        return None, "the producer marks the last resurrection as inferred"
    if dead is True:
        return None, "the bot is dead: its last resurrection preceded its last death or was inferred at its time"
    if not back or back < died:
        return None, "no resurrection after the last death"
    if dead is None and back == died:
        return None, "equal death and resurrection times without native_dead: possibly an inferred resurrection"
    return back - died, None


def revives(hits: list[Mapping[str, Any]], report: Mapping[str, Any] | None, boss: BossWindow) -> dict[str, Any]:
    """Death-to-resurrection gaps of deaths in the boss window, from the native life edges and, as a
    lower-power proxy, the combat log. Deaths outside the window (trash, after the kill) are only counted:
    recovered trash deaths are fine."""
    from tools.raid_program.scoreboard_deaths import _raid_runtime  # the final raid runtime of report.json
    lethal_nodes: dict[str, list[tuple[int, Any]]] = {}
    for event in hits:
        before, _ = _before_and_max(event)
        if before is not None and _int(event.get("amount")) >= before:
            lethal_nodes.setdefault(str(_int(event.get("target_guid"))), []).append(
                (_int(event.get("timestamp_ms")), event.get("route_node_id")))

    def native_in_window(actor: str, died: int) -> bool:
        """In the analysed damage window, unless the lethal hit behind it is logged on another node."""
        nodes = {node for at, node in lethal_nodes.get(actor, []) if abs(at - died) <= NATIVE_EVENT_MATCH_MS}
        if nodes and all(node and node != boss.node for node in nodes):
            return False
        return boss.has_time(died)

    native = []
    runtime = _raid_runtime(report)
    for member in (runtime or {}).get("native_recovery", {}).get("members") or []:
        if not isinstance(member, Mapping) or "native_death_count" not in member:
            continue
        died = _int(member.get("native_last_death_ms"))
        if not _int(member.get("native_death_count")) or not died:
            continue
        gap, why = _native_gap(member)
        native.append({"actor_id": str(_int(member.get("guid"))), "deaths": _int(member.get("native_death_count")),
                       "resurrections": _int(member.get("native_resurrection_count")), "last_death_ms": died,
                       "last_resurrection_ms": _int(member.get("native_last_resurrection_ms")),
                       "native_dead": member.get("native_dead"),
                       "in_boss_window": native_in_window(str(_int(member.get("guid"))), died),
                       "measured": gap is not None, "gap_ms": gap, **({"unmeasured": why} if why else {})})
    lethal: dict[str, tuple[int, bool]] = {}
    shortest: dict[str, int] = {}
    pairs = outside = 0
    for event in hits:
        before, _ = _before_and_max(event)
        if before is None:
            continue
        actor, at = str(_int(event.get("target_guid"))), _int(event.get("timestamp_ms"))
        if actor in lethal and before > 0:
            died_at, in_window = lethal.pop(actor)
            if in_window:
                shortest[actor] = min(at - died_at, shortest.get(actor, at - died_at))
                pairs += 1
            else:
                outside += 1
        if _int(event.get("amount")) >= before:
            lethal[actor] = (at, boss.has_event(event))
    return {"native": native, "native_available": runtime is not None,
            "boss_window": {"start_ms": boss.start, "end_ms": boss.end} if boss.known else None,
            "combat_log": {"pairs": pairs, "outside_boss_window_pairs": outside,
                           "min_gap_ms_by_actor": dict(sorted(shortest.items()))}}


def sanity_inputs(run_dir: Path, target: Mapping[str, Any], root: Path) -> dict[str, Any]:
    from tools.bot_ml.live_validation_fidelity import load_registry
    from tools.raid_program.scoreboard_deaths import death_accounting_coverage
    run_dir = Path(run_dir)
    node = str(target["encounter_route_node_id"])
    report = _read_json(run_dir / "report.json")
    analysis = _read_json(run_dir / "combat_analysis.json")
    log = _read_json(run_dir / "combat_log.json")
    events = [event for event in (log or {}).get("recent_events") or [] if isinstance(event, Mapping)]
    window = next((row for row in (analysis or {}).get("encounters") or []
                   if isinstance(row, Mapping) and row.get("route_node_id") == node), None)
    dropped = _int((log or {}).get("recent_events_dropped"))
    retained = None
    if isinstance(log, Mapping) and window is not None:
        coverage = death_accounting_coverage(events, node, _int(window.get("first_at_ms")) or None)
        retained = dropped == 0 or bool(coverage["covered"])
    fields: dict[str, Any] = {
        "schema": SCHEMA,
        "combat_log": {"available": isinstance(log, Mapping), "retained_events": len(events),
                       "recent_events_dropped": dropped, "boss_window_retained": retained,
                       "capture_truncated": capture_truncated(report)},
        "deaths": _death_scan(run_dir, node, target),
    }
    hits = _party_hits(events, analysis)
    boss = BossWindow(window, node)
    fields["health_half"] = health_half(hits, boss) if isinstance(log, Mapping) else None
    fields["revives"] = revives(hits, report if isinstance(report, Mapping) else None, boss)
    fidelity = (report or {}).get("encounter_fidelity") if isinstance(report, Mapping) else None
    seen = {_int(key) for key in ((fidelity or {}).get("boss_melee") or {})} if isinstance(fidelity, Mapping) else set()
    pulls = {}
    for entry, row in sorted(enrage_rows(load_registry(root), str(target.get("scenario") or ""), seen).items()):
        result = enrage_pulls(events, window, entry, row) if isinstance(log, Mapping) else None
        if result is not None:
            pulls[str(entry)] = result
    fields["enrage_pulls"] = pulls
    return fields


def sanity_input_fields(run_dir: Path, target: Mapping[str, Any], root: Path) -> dict[str, Any]:
    """``{"sanity_inputs": ...}`` for a new kill record; informational, so it never raises."""
    try:
        return {"sanity_inputs": sanity_inputs(run_dir, target, root)}
    except Exception as error:  # informational: never costs a kill its record
        return {"sanity_inputs": {"schema": SCHEMA, "error": f"{type(error).__name__}: {error}"[:300]}}

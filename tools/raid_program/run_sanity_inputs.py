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
nefarian_observations, decision_trace
    Only for NEFARIAN_SCENARIOS (BWD 10N round 3, BotNefarianWarriorWatch.h and the executor-refusal trace):
    the counts of the Nefarian strategy's decision-trace observations inside the boss window,
    ``{bone_warrior_active_over_45s: n, bone_warrior_on_pillar: n, move_refused: {actor_id: {"<mechanic>:
    <reason>": n}}}``, read from the run directory's retained decision trace (``trace_history.jsonl.gz`` and
    ``terminal_trace_drain.jsonl.gz``, the two files the harness writes). ``decision_trace`` says how far that
    trace can be trusted: a count above zero is evidence whatever the coverage, but a zero only proves anything
    when the trace is ``complete``. Complete needs positive proof, not the absence of a visible gap: the boss
    window is known, every actor the combat analysis saw has rows, and per actor the retained rows include one
    at or before the window's start and one at or after its end with every per-bot sequence number between
    them (sequences are dense per bot). A bounded tail (the terminal ``trace all N`` drain, the newest 8 rows a
    heartbeat) is contiguous yet covers neither edge, so it never attests absence over the window.
    ``nefarian_observations`` is None when there are no rows in the boss window to count.
    The rows must also be the judged capture's (``boss.capture``, capture_identity; see scan_decision_trace): each
    decision-trace entry names its own ``cohort_id``, ``server_epoch`` and ``attempt_id`` (the entry carries no
    combat-log epoch; one is compared when a row claims it), and a row of another cohort, server epoch or
    attempt is excluded from the counts and the coverage. Rows that do not name them (or name them unusably or
    contradictorily), or a capture that does not identify itself, leave the trace incomplete
    (``capture_unidentified``, ``row_identity_missing``, ``row_identity_conflict``, ``other_capture_rows``):
    dense rows of unknown or foreign provenance never certify a zero.

    The server keeps the same counts per cohort attempt (BotNefarianObservationCounters.h) and exports them
    in ``.botauto status`` as ``raid_runtime.encounter_observations.nefarian`` with ``complete: true`` once
    they are live for the attempt. The final status of the run directory (``report.json``'s status; only a run
    without a report falls back to ``latest.json``; a report that exists but cannot be read is ``unreadable``,
    never absent) is the source (``decision_trace.source`` ``server_status``, complete) when its block is
    well-formed, belongs to the status's own attempt (the block, ``raid_runtime`` and the status agree on a
    positive ``attempt_id``), is bound to the judged capture and the status was read at or after the end of the
    analysed boss window (``world_update.now_ms``, the clock of the combat log and the trace) and the observer
    itself observed near both edges of that window (``first_observed_at_ms`` / ``last_observed_at_ms``: the
    publication times, in the combat log's clock, of the first and newest snapshot the server's watch observed;
    see observation_window_coverage). A late status read time proves the counters were read after the window, not
    that anything was observed in it: the read time is never promoted to observation time. An older heartbeat,
    another attempt's block or a status without a read time proves nothing and is never promoted to complete
    evidence; a block whose observation times are missing, start after the window's start plus
    NEFARIAN_OBSERVATION_BOUND_MS or end before its end minus that bound is refused (``observation_time_missing``,
    ``observation_started_after_window``, ``observation_ended_before_window``).

    The judged capture is the combat-log export (``combat_log.json``) that supplied the boss window
    (``capture_identity``: cohort_id, server_epoch, attempt_id and combat_log_epoch, the cohort's start
    lifecycle). Every claim the status makes for those four fields (its generic identity, ``raid_runtime`` and
    the counter block, which carries ``attempt_id`` and ``combat_log_epoch``) must equal the capture's, and each
    field needs the capture's value and at least one claim: another attempt's or lifecycle's counters, however
    consistent and however late, are ``capture_mismatch``; a capture or status that does not say which
    attempt it is are ``capture_identity_missing`` (``server_counters.identity_conflicts`` / ``identity_missing``
    name the fields). Both refuse the counters.

    The trace scan above is the source only when the server exported no counters at all (no final status, or
    a status whose keys lack the Nefarian block, as an older build has). A block that is present but unusable,
    whether ``null`` or inside a ``status``, ``raid_runtime`` or ``encounter_observations`` that is ``null`` or
    not an object (status_block), is ``malformed``, never absent. Any other refusal (incomplete, malformed,
    unreadable, attempt_mismatch, capture_mismatch, capture_identity_missing, window_unknown, no_snapshot_time
    or before_window_end) leaves the observations to the trace's counts, but ``decision_trace.complete`` is False
    with ``incomplete_reason`` ``native_counters_<state>``: dense retained decision rows do not establish that the
    observer covered the encounter, so they never override an explicit ``complete: false`` or any other
    unusable native export (``retained_trace_complete`` records what the scan alone found).
    The native counts themselves are kept apart from that completeness (status_counters; the Atramedes reader does
    the same): the counters keep their counts as a lower bound, so a well-formed block of the judged capture's final
    status that says ``complete: false`` (or claims completeness but missed a window edge) contributes its counts,
    merged per key with the trace's (merge_lower_bounds; ``decision_trace.source`` is then ``server_status``): a
    recorded violation still blocks, and the refusal diagnostics are not lost, while ``decision_trace.complete``
    stays False, so a zero of such a block stays unproven. A block of another attempt or capture, or read before
    the window's end, contributes nothing.
    ``decision_trace.server_counters`` says why the status block was not used.
    The server counts bone warriors as distinct warriors and every refused step (uncoalesced).
atramedes_observations, atramedes_server_counters
    Only for ATRAMEDES_SCENARIOS (BWD 10N round 3; user decision 2026-09-30, "Bound kiter Sound": the tracked
    kiter stays at 10 Sound or less during every air-phase Roaring Flame chase). The server samples the Sound
    of the player the flame chases per cohort attempt (BotAtramedesObservationCounters.h) and exports
    ``raid_runtime.encounter_observations.atramedes``: ``{air_phases, chases, chase_samples, max_kiter_sound,
    samples_above_10, max_sample_gap_ms, complete, attempt_id}``. There is no decision-trace fallback: the only
    source is the final status, judged exactly as the Nefarian counters are (report.json, or latest.json only
    without a report, and an unreadable report is never absent; the block, ``raid_runtime`` and the status agree
    on a positive ``attempt_id``; the block is bound to the judged capture's cohort, server, attempt and
    combat-log lifecycle; the status was read at or after the end of the analysed boss window). A well-formed
    block of that final export is ``atramedes_observations`` with its own ``complete`` (true only when the
    server's sampling covered the attempt and, in the harness's own check, its first and newest sample are near
    the two edges of the boss window: observation_window_coverage, ATRAMEDES_OBSERVATION_BOUND_MS; a sampling that
    did not span the window keeps its counts with ``complete`` False, and the state says which edge);
    anything else is None, and ``atramedes_server_counters`` says why (no_file, unreadable, absent, malformed,
    attempt_mismatch, capture_mismatch, capture_identity_missing, window_unknown, no_snapshot_time or
    before_window_end).
"""
from __future__ import annotations

import gzip
import json
import zlib
from pathlib import Path
from typing import Any, Mapping

SCHEMA = "raid_run_sanity_inputs_v1"
NEFARIAN_SCENARIOS = frozenset({"blackwing_descent_10n_nefarian"})
# Decision-trace action (prefix) -> key of sanity_inputs.nefarian_observations; both are result "observation".
BONE_WARRIOR_ACTIONS = {"nefarian_bone_warrior_active_over_45s": "bone_warrior_active_over_45s",
                        "nefarian_bone_warrior_on_pillar": "bone_warrior_on_pillar"}
BONE_WARRIOR_KEYS = tuple(BONE_WARRIOR_ACTIONS.values())
MOVE_REFUSED_PREFIX = "nefarian_move_refused:"  # "nefarian_move_refused:<mechanic>:<executor reason>", result refused
ATRAMEDES_SCENARIOS = frozenset({"blackwing_descent_10n_atramedes"})
ATRAMEDES_SOUND_BOUND = 10  # the user's bound (2026-09-30) and the server's KiterSoundBound
# Counts of raid_runtime.encounter_observations.atramedes (BotAtramedesObservationCounters.h).
ATRAMEDES_KEYS = ("air_phases", "chases", "chase_samples", "max_kiter_sound", f"samples_above_{ATRAMEDES_SOUND_BOUND}")
# How far from the boss window's edges the server's observer may have its first and its newest observation: the
# observer's own gap bound (BotNefarianWarriorWatch.h WarriorObservationGapMs; BotAtramedesObservationStore.h
# MaxGroundGapMs, the ground bound: an engagement starts and ends on the ground). tests/
# test_observation_window_coverage.py holds them equal to the C++ constants.
NEFARIAN_OBSERVATION_BOUND_MS = 2000
ATRAMEDES_OBSERVATION_BOUND_MS = 5000
# The states of observation_window_coverage: a block that claims completeness but whose observer did not span the window.
COVERAGE_STATES = ("observation_time_missing", "observation_started_after_window", "observation_ended_before_window")


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
    inside the analysed damage window; nothing else on the node (e.g. a pre-pull heal) widens it.

    ``capture`` is the identity of the combat-log capture that supplied the window (capture_identity); the
    status counters are judged against it (status_scope). None: the window's capture is unidentified."""

    def __init__(self, window: Mapping[str, Any] | None, node: str, capture: Mapping[str, Any] | None = None) -> None:
        self.node = node
        self.capture = capture
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


def _positive(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None


CAPTURE_FIELDS = ("cohort_id", "server_epoch", "attempt_id", "combat_log_epoch")
# What a decision-trace entry exports natively (BotWorldTrace::AppendDecisionTraceEntryJson): its cohort, server
# epoch and attempt. The combat-log lifecycle is not one of them, so a row is compared on it only when it claims one.
TRACE_IDENTITY_FIELDS = CAPTURE_FIELDS[:3]


def _identity_value(field: str, value: Any) -> Any:
    """``value`` when it is a usable identity (a non-empty cohort id, else a positive integer), else None."""
    if field == "cohort_id":
        return value if isinstance(value, str) and value else None
    return _positive(value)


def decision_trace_files(run_dir: Path) -> list[Path]:
    """The retained decision-trace files present in a run directory.

    The harness writes both as gzip JSONL of ``{"bot_guid", "bot_name", "entry": <decision-trace entry>}``:
    ``trace_history.jsonl.gz`` holds every row of the route nodes it was asked to retain
    (``--retain-trace-route-node``) and ``terminal_trace_drain.jsonl.gz`` the bounded drain of a failed run.
    """
    from tools.bot_ml.live_validation_heartbeat import TRACE_HISTORY_FILE
    from tools.bot_ml.live_validation_terminal_signals import TERMINAL_TRACE_DRAIN_FILE
    return [run_dir / name for name in (TRACE_HISTORY_FILE, TERMINAL_TRACE_DRAIN_FILE) if (run_dir / name).is_file()]


def _trace_actor(row: Mapping[str, Any], entry: Mapping[str, Any]) -> str:
    actor = entry.get("actor")
    return str(_int(row.get("bot_guid")) or _int(actor.get("guid") if isinstance(actor, Mapping) else 0))


def _claimed_identity(row: Mapping[str, Any], entry: Mapping[str, Any], field: str) -> tuple[str, Any]:
    """(state, value) of one identity field of a retained trace row: its entry and the harness wrapper are both
    claims. ``value`` when every claim is the same usable identity; else ``missing`` (no claim), ``unusable``
    (a claim that is not an identity) or ``conflict`` (usable claims that differ)."""
    claims = [source[field] for source in (entry, row) if source.get(field) is not None]
    values = [_identity_value(field, claim) for claim in claims]
    if not claims:
        return "missing", None
    if any(value is None for value in values):
        return "unusable", None
    return ("conflict", None) if len(set(values)) > 1 else ("value", values[0])


def trace_row_binding(row: Mapping[str, Any], entry: Mapping[str, Any], capture: Mapping[str, Any] | None) -> str:
    """How one retained trace row relates to the judged capture (``boss.capture``, capture_identity).

    ``bound``: the row names the capture's cohort, server epoch and attempt (and its combat-log epoch when it
    claims one). ``foreign``: a usable claim of the row differs from the capture's value: another cohort, server
    or attempt's row, which counts for nothing here. ``conflict``: the row contradicts itself (its entry and
    wrapper name different identities). ``unidentified``: anything else, so the row's provenance cannot be
    established: a required field missing or unusable, or a capture that does not say its own.
    """
    capture = capture or {}
    states = {field: _claimed_identity(row, entry, field) for field in CAPTURE_FIELDS}
    if any(state == "conflict" for state, _ in states.values()):
        return "conflict"
    if any(state == "value" and capture.get(field) is not None and value != capture[field]
           for field, (state, value) in states.items()):
        return "foreign"
    if any(states[field][0] != "value" or capture.get(field) is None for field in TRACE_IDENTITY_FIELDS):
        return "unidentified"
    epoch_state = states["combat_log_epoch"][0]
    if epoch_state == "unusable" or (epoch_state == "value" and capture.get("combat_log_epoch") is None):
        return "unidentified"
    return "bound"


def window_edge_coverage(stamps: Mapping[str, Mapping[int, int]], boss: BossWindow,
                         actors: set[str]) -> tuple[list[str], list[str], list[str]]:
    """(no start row, no end row, holes) actors: who the retained rows do not prove for the whole boss window.

    ``stamps`` maps actor -> {sequence: timestamp_ms} of every retained row (whatever its node). An actor is
    proven when its rows hold one at or before the window's start and one at or after its end, and every
    sequence number between the newest start-side row and the earliest end-side row is retained.
    """
    no_start, no_end, holes = [], [], []
    for actor in sorted(actors):
        rows = stamps.get(actor) or {}
        before = [sequence for sequence, at in rows.items() if at <= boss.start]
        after = [sequence for sequence, at in rows.items() if at >= boss.end]
        if not before:
            no_start.append(actor)
        if not after:
            no_end.append(actor)
        if before and after:
            low, high = max(before), min(after)
            if high < low or sum(low <= sequence <= high for sequence in rows) != high - low + 1:
                holes.append(actor)
    return no_start, no_end, holes


def scan_decision_trace(run_dir: Path, boss: BossWindow,
                        party: set[int]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(nefarian_observations, decision_trace) of a run directory's retained decision trace.

    Only rows of the judged capture count or cover anything (trace_row_binding): a row's own ``cohort_id``,
    ``server_epoch`` and ``attempt_id`` (and its ``combat_log_epoch`` when it claims one) must be the
    capture's (``boss.capture``). A foreign row (another cohort, server epoch, attempt or lifecycle) is
    excluded from the counts and the coverage; a row whose provenance cannot be established (identity fields
    missing or unusable, or a capture that does not say its own) or that contradicts itself is excluded too and
    leaves the trace incomplete: dense rows of another capture, or of unknown origin, never certify a zero.
    Entries are the trace rows of the boss window (BossWindow.has_event: the encounter route node or the
    analysed damage window), deduplicated by (bot, sequence, timestamp) across the two files. An entry is
    counted by its action alone (not its situation or result), so a renamed result can only over-count.
    ``complete`` is the coverage a zero needs, established from the rows themselves: a known boss window,
    readable files, rows for every actor in ``party`` (the combat analysis's actors of the window), no
    per-bot sequence number missing between two retained window rows (sequences are dense per bot: the light
    heartbeat tails keep 8 of ~30 rows per second) and, per actor, retained rows at or before the window's
    start and at or after its end (window_edge_coverage), so a contiguous tail of the newest rows never
    counts as the whole window. ``incomplete_reason`` is then a stable code: no_trace_file,
    boss_window_unknown, unreadable, capture_unidentified (the capture has no cohort, server epoch or
    attempt), row_identity_conflict, row_identity_missing, other_capture_rows (every identified row is
    another capture's), no_window_rows, sequence_gaps, unsequenced_rows, sequence_conflicts (one sequence
    number seen at two times), actors_without_rows, window_start_not_covered or window_end_not_covered.
    """
    files = decision_trace_files(Path(run_dir))
    counts = {key: 0 for key in BONE_WARRIOR_KEYS}
    refused: dict[str, dict[str, int]] = {}
    sequences: dict[str, set[int]] = {}
    stamps: dict[str, dict[int, int]] = {}  # every retained row, whatever its node: the window-edge proof
    conflicts = 0
    seen: set[tuple[str, int, int]] = set()
    rows_by_file: dict[str, int] = {}
    unreadable: list[str] = []
    unsequenced = 0
    bound = 0  # rows of the judged capture; the only rows that count or cover
    unbound = {"foreign": 0, "conflict": 0, "unidentified": 0}
    for path in files if boss.known else []:
        rows_by_file[path.name] = 0
        try:
            with gzip.open(path, "rt", encoding="utf-8") as handle:
                for line in handle:
                    if not line.strip():
                        continue
                    rows_by_file[path.name] += 1
                    try:
                        row = json.loads(line)
                    except ValueError:
                        unreadable.append(f"{path.name}: malformed row")
                        continue
                    entry = row.get("entry") if isinstance(row, Mapping) else None
                    if not isinstance(entry, Mapping):
                        unreadable.append(f"{path.name}: row without an entry")
                        continue
                    binding = trace_row_binding(row, entry, boss.capture)
                    if binding != "bound":  # another capture's row, or one whose provenance is unknown: no evidence
                        unbound[binding] += 1
                        continue
                    bound += 1
                    actor, sequence = _trace_actor(row, entry), _int(entry.get("sequence"))
                    at = _int(entry.get("timestamp_ms"))
                    if sequence > 0 and at > 0 and actor != "0":
                        if stamps.setdefault(actor, {}).setdefault(sequence, at) != at:
                            conflicts += 1
                    if not boss.has_event(entry):
                        continue
                    key = (actor, sequence, at)
                    if key in seen:
                        continue
                    seen.add(key)
                    if sequence > 0:
                        sequences.setdefault(actor, set()).add(sequence)
                    else:
                        unsequenced += 1
                    action = str(entry.get("action") or "")
                    for prefix, name in BONE_WARRIOR_ACTIONS.items():
                        counts[name] += action.startswith(prefix)
                    if action.startswith(MOVE_REFUSED_PREFIX):
                        reason = action[len(MOVE_REFUSED_PREFIX):]
                        refused.setdefault(actor, {})[reason] = refused.get(actor, {}).get(reason, 0) + 1
        except (OSError, EOFError, zlib.error, UnicodeError) as error:  # a truncated or corrupt gzip
            unreadable.append(f"{path.name}: {type(error).__name__}")
    gaps = sum(max(sequence) - min(sequence) + 1 - len(sequence) for sequence in sequences.values())
    silent = sorted(str(guid) for guid in party if str(guid) not in sequences)
    required = ({str(guid) for guid in party} | set(sequences)) - {"0"}
    no_start, no_end, holes = window_edge_coverage(stamps, boss, required) if boss.known else ([], [], [])
    identified = all((boss.capture or {}).get(field) is not None for field in TRACE_IDENTITY_FIELDS)
    reason = ("no_trace_file" if not files else "boss_window_unknown" if not boss.known
              else "unreadable" if unreadable else "capture_unidentified" if not identified
              else "row_identity_conflict" if unbound["conflict"] else "row_identity_missing" if unbound["unidentified"]
              else "other_capture_rows" if not bound and unbound["foreign"] else "no_window_rows" if not seen
              else "sequence_gaps" if gaps or holes else "unsequenced_rows" if unsequenced
              else "sequence_conflicts" if conflicts else "actors_without_rows" if silent
              else "window_start_not_covered" if no_start else "window_end_not_covered" if no_end else None)
    coverage = {"available": bool(files), "files": rows_by_file, "window_rows": len(seen), "actors": len(sequences),
                "bound_rows": bound, "foreign_rows": unbound["foreign"], "conflicting_rows": unbound["conflict"],
                "unidentified_rows": unbound["unidentified"], "capture_identified": identified,
                "sequence_gaps": gaps, "unsequenced_rows": unsequenced, "sequence_conflicts": conflicts,
                "actors_without_rows": silent, "window_start_uncovered": no_start, "window_end_uncovered": no_end,
                "unreadable": sorted(set(unreadable))[:5], "complete": reason is None, "incomplete_reason": reason}
    observations = {**counts, "move_refused": {actor: dict(sorted(rows.items())) for actor, rows in
                                               sorted(refused.items())}} if seen else None
    return observations, coverage


STATUS_FILES = ("report.json", "latest.json")  # the final status, in order of preference


def _count_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else None


class _UnusableBlock:
    """status_block's answer for a block that is present but cannot be one (see UNUSABLE_BLOCK)."""

    def __repr__(self) -> str:
        return "UNUSABLE_BLOCK"


UNUSABLE_BLOCK = _UnusableBlock()


def status_block(payload: Any, encounter: str = "nefarian") -> Any:
    """``status.raid_runtime.encounter_observations.<encounter>`` of a report/heartbeat payload.

    Only a key that is genuinely missing is absent (None: a server that does not export the block, as an older
    build). A present value that cannot hold or be the block, whatever the reason (a ``null`` or non-object
    ``status``, ``raid_runtime`` or ``encounter_observations``, or a ``null`` block), is an export that exists and
    is unusable: UNUSABLE_BLOCK, which parses as malformed and never leaves the trace to stand in. A block that
    is present with any other non-object value is returned as it is (parse_status_observations: malformed).
    """
    for key in ("status", "raid_runtime", "encounter_observations", encounter):
        if not isinstance(payload, Mapping):
            return UNUSABLE_BLOCK
        if key not in payload:
            return None
        payload = payload[key]
    return UNUSABLE_BLOCK if payload is None else payload


def _block_counts(block: Mapping[str, Any]) -> dict[str, Any] | None:
    """The counts of a counter block (the warrior counts and the per-actor refusals), None when malformed."""
    counts = {key: _count_or_none(block.get(key)) for key in BONE_WARRIOR_KEYS}
    refused = block.get("move_refused")
    if None in counts.values() or not isinstance(refused, Mapping):
        return None
    parsed: dict[str, dict[str, int]] = {}
    for actor, rows in refused.items():
        if not isinstance(rows, Mapping) or any(_count_or_none(count) is None for count in rows.values()):
            return None
        parsed[str(actor)] = {str(reason): int(count) for reason, count in sorted(rows.items())}
    return {**counts, "move_refused": dict(sorted(parsed.items()))}


def parse_status_observations(block: Any) -> tuple[dict[str, Any] | None, str]:
    """(observations, state) of one exported counter block; state is complete, absent, incomplete or malformed.

    ``absent`` is only a block the status does not export at all (status_block: None); a present ``null``, a
    non-object or an UNUSABLE_BLOCK is ``malformed``.

    The counts are kept apart from the completeness, as the Atramedes reader does: a well-formed block whose
    ``complete`` is the JSON boolean false is ``incomplete`` and still returns its counts, which the native
    counters keep as a lower bound (BotNefarianObservationCounters.h: an uncovered live attempt keeps its counts).
    Whether a caller may use them is its decision (status_counters binds them to the judged capture first); they
    are never proof of a zero. A ``complete`` that is not a boolean, or malformed counts, return None.
    """
    if block is None:
        return None, "absent"
    if not isinstance(block, Mapping):
        return None, "malformed"
    if block.get("complete") is not True:
        return (_block_counts(block) if block.get("complete") is False else None), "incomplete"
    counts = _block_counts(block)
    return (counts, "complete") if counts is not None else (None, "malformed")


def has_observed_evidence(counts: Mapping[str, Any] | None) -> bool:
    """True when counts hold a violation or a refused step: what a lower bound can still show."""
    return isinstance(counts, Mapping) and (any(counts.get(key) for key in BONE_WARRIOR_KEYS)
                                            or bool(counts.get("move_refused")))


def merge_lower_bounds(native: Mapping[str, Any], trace: Mapping[str, Any] | None) -> dict[str, Any]:
    """Two lower bounds of one attempt's counts (the incomplete native counters and the retained trace): the
    per-key maximum, so neither source's recorded violation or refusal diagnostics is lost."""
    trace = trace if isinstance(trace, Mapping) else {}
    merged = {key: max(_int(native.get(key)), _int(trace.get(key))) for key in BONE_WARRIOR_KEYS}
    refused: dict[str, dict[str, int]] = {}
    for source in (native.get("move_refused"), trace.get("move_refused")):
        for actor, rows in (source.items() if isinstance(source, Mapping) else ()):
            row = refused.setdefault(str(actor), {})
            for reason, count in (rows.items() if isinstance(rows, Mapping) else ()):
                row[str(reason)] = max(row.get(str(reason), 0), _int(count))
    return {**merged, "move_refused": {actor: dict(sorted(rows.items())) for actor, rows in sorted(refused.items())}}


def capture_identity(log: Any) -> dict[str, Any]:
    """The identity of the combat-log capture that supplied the judged boss window.

    ``combat_log.json`` is the harness's full ``botauto_combatlog`` export; it carries the native event-stream
    identity (tools.bot_ml.combat_log_event_stream.combat_log_identity): the cohort, the server epoch, the
    attempt and the combat-log epoch (the cohort's start lifecycle, advanced by every Start and StartAutonomy).
    A field the log does not export, or exports unusably, is None (an unidentified capture).
    """
    log = log if isinstance(log, Mapping) else {}
    runtime = log.get("raid_runtime") if isinstance(log.get("raid_runtime"), Mapping) else {}
    return {field: _identity_value(field, log.get(field) if log.get(field) is not None else runtime.get(field))
            for field in CAPTURE_FIELDS}


def capture_binding(payload: Any, block: Mapping[str, Any],
                    capture: Mapping[str, Any] | None) -> tuple[list[str], list[str]]:
    """(conflicts, missing): the identity fields on which a status's counter block disagrees with, or cannot be
    tied to, the judged capture.

    A field is claimed by every place the status exports it: its own generic identity (cohort_id,
    server_epoch, attempt_id), its ``raid_runtime`` (server_epoch, attempt_id) and the counter block
    (attempt_id and combat_log_epoch: the block is one attempt's and one start lifecycle's). Every claim must
    equal the capture's value (a conflict), and each field needs the capture's value and at least one claim
    (else it is missing): consistent fields of another attempt, or a status that does not say which lifecycle
    its counters belong to, prove nothing about the judged capture.
    """
    status = payload.get("status") if isinstance(payload, Mapping) else None
    status = status if isinstance(status, Mapping) else {}
    runtime = status.get("raid_runtime") if isinstance(status.get("raid_runtime"), Mapping) else {}
    conflicts: list[str] = []
    missing: list[str] = []
    for field in CAPTURE_FIELDS:
        claims = [source.get(field) for source in (block, runtime, status) if source.get(field) is not None]
        expected = (capture or {}).get(field)
        if expected is not None and any(_identity_value(field, claim) != expected for claim in claims):
            conflicts.append(field)
        elif expected is None or not claims:
            missing.append(field)
    return conflicts, missing


def observation_window_coverage(block: Mapping[str, Any], boss: BossWindow, bound_ms: int) -> str | None:
    """None when the server's observer spans the boss window, else the state that says why not.

    The store exports ``first_observed_at_ms`` and ``last_observed_at_ms``: the publication times (system ms, the
    combat log's clock, the clock ``boss`` is in) of the first and the newest snapshot its observer took in the
    attempt. The observer's own ``complete`` only says it had no internal gap; an observer that took one sample
    and then nothing is ``complete`` and covers no window. So the window is covered only when the first
    observation is at or before the window's start plus ``bound_ms`` and the newest at or after its end minus
    ``bound_ms``; with no internal gap (``complete``) that is continuous coverage of the whole window, each
    edge within the observer's own gap bound. The status's read time is not an observation time and never
    stands in for ``last_observed_at_ms``. ``observation_time_missing``: an export without usable times (an
    older build's block, or an observer that took nothing); ``observation_started_after_window``;
    ``observation_ended_before_window``.
    """
    first, last = _positive(block.get("first_observed_at_ms")), _positive(block.get("last_observed_at_ms"))
    if first is None or last is None or last < first:
        return "observation_time_missing"
    if first > boss.start + bound_ms:
        return "observation_started_after_window"
    if last < boss.end - bound_ms:
        return "observation_ended_before_window"
    return None


def status_scope(payload: Any, block: Mapping[str, Any], boss: BossWindow | None) -> str:
    """"complete" when a well-formed counter block is the judged capture's and covers the window's end.

    The block, the status's ``raid_runtime`` and (when exported) the status itself must agree on one positive
    ``attempt_id``; else ``attempt_mismatch``. That attempt, the cohort, the server and the combat-log epoch
    must then be the judged capture's (``boss.capture``, capture_identity; see capture_binding):
    ``capture_mismatch`` when a claim differs, ``capture_identity_missing`` when the capture or the status
    leaves a field unsaid. The counters are cumulative per attempt, so the status is a final export of the
    window when it was read (``world_update.now_ms``, the combat-log clock) at or after the window's last damage:
    ``window_unknown`` without an analysed window, ``no_snapshot_time`` without a read time,
    ``before_window_end`` for an older heartbeat. That is a read time, not an observation: whether the observer
    itself spanned the window is observation_window_coverage, which the callers apply to a "complete" scope.
    """
    status = payload.get("status") if isinstance(payload, Mapping) else None
    status = status if isinstance(status, Mapping) else {}
    runtime = status.get("raid_runtime")
    attempts = [_positive(block.get("attempt_id")), _positive((runtime if isinstance(runtime, Mapping) else {})
                                                              .get("attempt_id"))]
    if status.get("attempt_id") is not None:
        attempts.append(_positive(status.get("attempt_id")))
    if None in attempts or len(set(attempts)) != 1:
        return "attempt_mismatch"
    if boss is None or not boss.known:
        return "window_unknown"
    conflicts, missing = capture_binding(payload, block, boss.capture)
    if conflicts:
        return "capture_mismatch"
    if missing:
        return "capture_identity_missing"
    update = status.get("world_update")
    now = _positive(update.get("now_ms") if isinstance(update, Mapping) else None)
    if now is None:
        return "no_snapshot_time"
    return "complete" if now >= boss.end else "before_window_end"


def _status_payload(path: Path, report: Any = None) -> tuple[Any, str | None]:
    """(payload, None) of a readable final-status file, else (None, why).

    ``report`` is an already-read report.json. ``no_file`` when the file does not exist; ``unreadable`` when it
    exists but is truncated, malformed or not a JSON object: a present, unreadable final export is never
    treated as absent, so an older heartbeat cannot stand in for it.
    """
    payload = report if report is not None else _read_json(path)
    if isinstance(payload, Mapping):
        return payload, None
    return None, "unreadable" if report is not None or path.exists() else "no_file"


def _refused_counters(states: Mapping[str, str], boss: BossWindow | None, payload: Any = None,
                      block: Any = None) -> dict[str, Any]:
    """The ``server_counters`` of a run whose final status counters were not used (and, for a refusal of the
    capture binding, the identity fields that conflict or are missing)."""
    identity: dict[str, Any] = {}
    if payload is not None and isinstance(block, Mapping) and boss is not None and any(
            str(state).startswith("capture_") for state in states.values()):
        conflicts, missing = capture_binding(payload, block, boss.capture)
        identity = {"identity_conflicts": conflicts, "identity_missing": missing}
    return {"file": None, "states": dict(states), "complete": False, **identity,
            **({"window_end_ms": boss.end} if boss is not None and boss.known else {})}


def status_counters(run_dir: Path, report: Any = None,
                    boss: BossWindow | None = None) -> tuple[dict[str, Any] | None, bool, dict[str, Any]]:
    """(counts, proven, server_counters) from the run directory's final status.

    ``report`` is the already-read report.json (read here when None). Only the final export counts: an
    existing report.json is judged alone (its block, attempt, capture identity and read time; see
    status_scope), so an older heartbeat in latest.json never stands in for a missing, malformed, unreadable or
    unproven final block; latest.json is read only when the run directory has no report. A present but
    unreadable file is ``unreadable``, never ``no_file``. ``server_counters`` records each consulted file's state.

    The counts are kept apart from whether they are proven (as the Atramedes reader does). ``proven`` is True for
    a complete block of the judged capture that the observer spanned the boss window with
    (observation_window_coverage). Otherwise the counts are a lower bound, returned when the block is well-formed
    and bound to the judged capture's final status (status_scope is "complete": its attempt, capture identity and
    read time): a block that says ``complete: false``, or that claims completeness but did not observe near both
    window edges. A lower bound can show a violation or a refused step; it never proves a zero. Every other
    refusal (another attempt or capture, read before the window's end, malformed, absent, unreadable) returns no
    counts: a block that is not the judged attempt's is no evidence of it.
    """
    states: dict[str, str] = {}
    payload = block = None
    for name in STATUS_FILES:
        payload, why = _status_payload(Path(run_dir) / name, report if name == "report.json" else None)
        if why is not None:
            states[name] = why
            if why == "unreadable":
                break
            continue
        block = status_block(payload)
        observations, state = parse_status_observations(block)
        lower = None
        if observations is not None:
            scope = status_scope(payload, block, boss)
            if scope != "complete":  # another attempt's or capture's counts, or read too early: no evidence of this kill
                observations = None
                state = scope if state == "complete" else state
            elif state == "complete":  # read after the window: the observer itself must also span it
                state = observation_window_coverage(block, boss, NEFARIAN_OBSERVATION_BOUND_MS) or "complete"
                lower = observations if state in COVERAGE_STATES else None
            else:  # `complete: false`, but the judged capture's own final export: a lower bound
                lower = observations
        states[name] = state
        if state == "complete":
            return observations, True, {"file": name, "states": states, "complete": True,
                                        "attempt_id": block["attempt_id"],
                                        "snapshot_now_ms": payload["status"]["world_update"]["now_ms"],
                                        "first_observed_at_ms": block["first_observed_at_ms"],
                                        "last_observed_at_ms": block["last_observed_at_ms"]}
        return lower, False, _refused_counters(states, boss, payload, block)
    return None, False, _refused_counters(states, boss, payload, block)


def status_observations(run_dir: Path, report: Any = None,
                        boss: BossWindow | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(nefarian_observations, server_counters): status_counters' counts when they are proven, else None."""
    counts, proven, server = status_counters(run_dir, report, boss)
    return (counts if proven else None), server


def native_counter_state(states: Mapping[str, str]) -> str | None:
    """The state of the run's final status counters when the server exported any, else None.

    None only when no final status carries a Nefarian block at all (no file, or a status whose keys lack the
    block, as an older build's): the one case in which the decision trace may stand in. Any other state
    (incomplete, malformed, unreadable, a refused scope) says the native observer's export exists and was not
    usable; a block or a container on its path that is present but null or not an object is ``malformed``, never
    absent (status_block).
    """
    for name in STATUS_FILES:
        state = states.get(name)
        if state not in (None, "no_file"):
            return None if state == "absent" else state
    return None


def nefarian_inputs(run_dir: Path, report: Any, boss: BossWindow,
                    party: set[int]) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(nefarian_observations, decision_trace): the final status counters when proven, else the trace.

    The trace scan is a fallback for a server that exported no counters at all (native_counter_state). When it
    did, and they are unusable (``complete: false`` above all), the trace's counts stay evidence, but the
    trace never vouches for a zero: dense retained decision rows do not show the observer covered the attempt.
    Even as the fallback the trace counts only rows of the judged capture (scan_decision_trace).

    The native counts of an unproven block of the judged capture (status_counters: ``complete: false``, or an
    observer that missed a window edge) are a lower bound and stay evidence beside the trace's: a recorded
    violation (it still blocks) and the refusal diagnostics are merged in (merge_lower_bounds; ``source`` is then
    ``server_status``), while ``decision_trace.complete`` stays False, so an unproven zero keeps blocking.
    """
    counts, proven, server = status_counters(run_dir, report, boss)
    if proven:
        return counts, {"source": "server_status", "complete": True, "incomplete_reason": None,
                        "server_counters": server}
    observations, coverage = scan_decision_trace(run_dir, boss, party)
    native = native_counter_state(server["states"])
    if native is not None:
        coverage = {**coverage, "retained_trace_complete": coverage["complete"], "complete": False,
                    "incomplete_reason": f"native_counters_{native}"}
    source = "decision_trace"
    if has_observed_evidence(counts):
        observations, source = merge_lower_bounds(counts, observations), "server_status"
    return observations, {**coverage, "source": source, "server_counters": server}


def parse_atramedes_observations(block: Any) -> tuple[dict[str, Any] | None, str]:
    """(observations, state) of one exported Atramedes block; state is complete, incomplete, absent or malformed.

    A well-formed block keeps its counts whatever its ``complete`` (a count above the bound is evidence even
    when the sampling missed something); ``complete`` must be a JSON boolean. As for Nefarian, ``absent`` is
    only a block the status does not export; a present ``null``, non-object or UNUSABLE_BLOCK is ``malformed``.
    """
    if block is None:
        return None, "absent"
    if not isinstance(block, Mapping):
        return None, "malformed"
    counts = {key: _count_or_none(block.get(key)) for key in (*ATRAMEDES_KEYS, "max_sample_gap_ms")}
    complete = block.get("complete")
    if None in counts.values() or not isinstance(complete, bool):
        return None, "malformed"
    return {**counts, "complete": complete}, "complete" if complete else "incomplete"


def atramedes_inputs(run_dir: Path, report: Any = None,
                     boss: BossWindow | None = None) -> tuple[dict[str, Any] | None, dict[str, Any]]:
    """(atramedes_observations, atramedes_server_counters) from the run directory's final status.

    The Nefarian rules (status_observations): only the final export counts (an existing report.json is judged
    alone, and an unreadable one is not absent; latest.json only without one), and only as the judged
    capture's attempt (status_scope: cohort, server, attempt and combat-log lifecycle), read at or after the
    end of the boss window. Its well-formed block is returned with the block's own ``complete``.
    """
    states: dict[str, str] = {}
    payload = block = None
    for name in STATUS_FILES:
        payload, why = _status_payload(Path(run_dir) / name, report if name == "report.json" else None)
        if why is not None:
            states[name] = why
            if why == "unreadable":
                break
            continue
        block = status_block(payload, "atramedes")
        observations, state = parse_atramedes_observations(block)
        scope = status_scope(payload, block, boss) if observations is not None else None
        coverage = (observation_window_coverage(block, boss, ATRAMEDES_OBSERVATION_BOUND_MS)
                    if observations is not None and scope == "complete" else None)
        if coverage is not None:  # the counts stay evidence, but a sampling that missed a window edge covers none
            observations = {**observations, "complete": False}
        states[name] = coverage or (state if scope in (None, "complete") else scope)
        if observations is not None and scope == "complete":
            return observations, {"file": name, "states": states, "complete": observations["complete"],
                                  "attempt_id": block["attempt_id"],
                                  "snapshot_now_ms": payload["status"]["world_update"]["now_ms"],
                                  "first_observed_at_ms": _positive(block.get("first_observed_at_ms")),
                                  "last_observed_at_ms": _positive(block.get("last_observed_at_ms"))}
        break
    return None, _refused_counters(states, boss, payload, block)


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
    boss = BossWindow(window, node, capture_identity(log))  # the window's capture: what counters must belong to
    fields["health_half"] = health_half(hits, boss) if isinstance(log, Mapping) else None
    fields["revives"] = revives(hits, report if isinstance(report, Mapping) else None, boss)
    if str(target.get("scenario") or "") in NEFARIAN_SCENARIOS:
        party = {_int(actor.get("actor_guid")) for actor in (window or {}).get("actors") or []
                 if isinstance(actor, Mapping)} - {0}
        try:
            fields["nefarian_observations"], fields["decision_trace"] = nefarian_inputs(run_dir, report, boss, party)
        except Exception as error:  # the scan never costs the record its other inputs
            fields["nefarian_observations"] = None
            fields["decision_trace"] = {"available": None, "complete": False, "incomplete_reason": "unreadable",
                                        "error": f"{type(error).__name__}: {error}"[:300]}
    if str(target.get("scenario") or "") in ATRAMEDES_SCENARIOS:
        try:
            fields["atramedes_observations"], fields["atramedes_server_counters"] = atramedes_inputs(
                run_dir, report, boss)
        except Exception as error:  # never costs the record its other inputs; the check reports it unproven
            fields["atramedes_observations"] = None
            fields["atramedes_server_counters"] = {"file": None, "states": {}, "complete": False,
                                                   "error": f"{type(error).__name__}: {error}"[:300]}
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

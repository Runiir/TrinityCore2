"""Round 3 harness package H: watchdog signals checked against round-2 BWD 10N sequences.

The loop tests replay the shapes of the round-2 shard heartbeats (rebuilt from
worldserver.console.log by the reviewer's replay): the batch Magmaw run whose
pre-pull gate failed at heartbeat 8 yet engaged natively at 18 and died at 22,
Maloriak held by the same gate until a diagnosis error, and Omnotron wiped by a
contaminating Golem Sentry that re-engaged after every runback.  Contamination
is a label only: the reviewer's scenarios A, B and B2 are runs that recover and
clear, and Omnotron's real wipe loop ends through the near-wipe death loop.
"""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.bot_ml.live_validation_terminal_signals import (
    TERMINAL_TRACE_DRAIN_FILE,
    HeartbeatSignals,
    NearWipeTracker,
    RouteActionLedger,
    drain_terminal_trace,
)
from tools.bot_ml.run_live_bot_validation import (
    command_script,
    live_validation_report,
    parse_json_objects,
    route_segment_complete,
    run_transport_completion_watchdog,
    should_defer_active_combat_bot_diagnosis,
    supersede_transient_route_failures,
)

COHORT = "c0"
PREPULL_REASON = "raid_prepull_unknown_spec_contract_beast_mastery_hunter"
PREPULL_LABEL = "raid_prepull_consumables_failed:" + PREPULL_REASON
TRACE = f".botauto trace {COHORT} all 128 delta"
TAIL = f".botauto trace {COHORT} all 128"
GOLEM_ENTRY = 42800
GOLEM_GUID = 17379574786623012865
MAGMAW_GUID = 17379570517425520858
DRUDGE_GUID = 17379570517425520001
OMNOTRON = dict(node="bwd.omnotron.regroup", generation=1, kind="regroup", kills=0)
MAGMAW = dict(node="bwd.magmaw.encounter", generation=4, kind="boss")


class LoopKeptRunning(Exception):
    """The scripted heartbeats ran out while the watchdog was still running."""


def _manifest(node="bwd.maloriak.encounter", generation=3) -> dict:
    return {"schema": "bot_live_validation_route_manifest_v1",
            "routes": [{"route_node_id": node, "route_generation": generation, "kind": "boss"}]}


MANIFEST = _manifest()


def _status(*, node="bwd.maloriak.encounter", generation=3, kind="boss", alive=10, kills=3,
            deaths=0, prepull_failed=False, contamination=False, wipe_generation=0,
            manifest_complete=False, boss_dead=False, engaged=False, prepull_generation=None,
            hostile_guid=0, hostile_entry=0, contamination_rows=()) -> dict:
    route = {"node_id": node, "generation": generation, "kind": kind, "manifest_complete": manifest_complete}
    scope = {"route_node_id": node, "route_generation": generation}
    if contamination:
        route["contamination_evidence"] = [{**scope, "route_kind": kind, "target_entry": GOLEM_ENTRY,
                                            "target_id": GOLEM_GUID,
                                            "result": "validation_route_future_encounter_contamination"}]
    if contamination_rows:
        # The native list survives route advances: rows keep their own scope.
        route["contamination_evidence"] = [
            {**row, "result": "validation_route_future_encounter_contamination"} for row in contamination_rows]
    if manifest_complete:
        route["terminal_evidence"] = [scope]
    if boss_dead:
        route["boss_death_evidence"] = [{**scope, "target_id": 991, "target_entry": 41378, "result": "ok"}]
    return {
        "ok": True, "action": "botauto_status", "active": True, "cohort_id": COHORT,
        "active_bots": 10, "target_bots": 10, "kills": kills, "deaths": deaths, "decisions": 500,
        "validation_route": route,
        "raid_runtime": {
            "instance_kind": "raid", "expected_size": 10, "alive_size": alive,
            "wipe_state": "engaged" if engaged else "ready" if alive == 10 else "partial_deaths",
            "encounter_in_progress": engaged, "encounter_phase": "combat" if engaged else "formation",
            "wipe_generation": wipe_generation, "recovery_state": "none",
            "native_hostile_activity_active": bool(hostile_guid or hostile_entry),
            "native_hostile_activity_guid": hostile_guid, "native_hostile_activity_entry": hostile_entry,
            "prepull_consumables": {
                "schema": "raid_prepull_consumables_v1", "required": prepull_failed, "ready": False,
                "failed": prepull_failed, "failure_reason": PREPULL_REASON if prepull_failed else "",
                "attempt_id": 1, "wipe_generation": 0,
                "route_generation": generation if prepull_generation is None else prepull_generation,
            },
        },
    }


def _diagnose(*, error=False) -> dict:
    row = {"identity": {"bot_guid": 5}, "snapshot": {"decision": {"action": "raid_prepull_failed"}}}
    if error:
        row["diagnosis"] = {"diagnosis_code": "blocked_no_fallback", "severity": "error"}
    return {"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1, "bots": [row]}


def _trace(entries: list[dict], *, pending=0, guid=5, newest=0) -> dict:
    bot = {"bot_guid": guid, "bot_name": "Bwbot", "delta": True, "pending_entry_count": pending, "entries": entries}
    if newest:
        bot["newest_retained_sequence"] = newest
    return {"ok": True, "action": "botauto_trace", "trace_schema_version": 1, "bots": [bot]}


def _route_rows(first: int, count: int, *, node="bwd.maloriak.encounter", generation=3) -> list[dict]:
    return [{"sequence": first + index, "timestamp_ms": 1_000 + first + index,
             "action": "validation_route_hold_anchor", "result": "hold",
             "route_node_id": node, "route_generation": generation} for index in range(count)]


def _output(*rows: dict) -> str:
    return "\n".join(json.dumps(row) for row in rows)


def _run(tmp_path: Path, beats: list[dict], *, max_beats: int | None = None, manifest: dict | None = None,
         drain_traces: list[dict] | None = None, tail_trace: dict | None = None) -> tuple[list[str], Path, str]:
    """Drive the transport watchdog over scripted heartbeats.

    Each beat maps ``status``/``diagnose``/``trace`` to payloads.  Past the last
    scripted beat the last one repeats; ``sleep`` interrupts after ``max_beats``
    so a loop that never terminates raises ``LoopKeptRunning``.  Cleanup delta
    traces come from ``drain_traces``; the non-delta tail from ``tail_trace``.
    """
    commands: list[str] = []
    state = {"beat": 0, "drain": 0, "cleanup": False}
    drains = list(drain_traces or [])

    def execute(command: str, _timeout: int) -> tuple[str, int, bool]:
        commands.append(command)
        beat = beats[min(state["beat"], len(beats)) - 1]
        if command.startswith(".botauto combatlog") or command.startswith(".botauto stop"):
            state["cleanup"] = True
            payload = {"ok": True, "action": "botauto_combatlog" if "combatlog" in command else "botauto_stop"}
        elif command.startswith(".botauto status"):
            payload = beat["status"]
        elif command.startswith(".botauto diagnose"):
            payload = beat.get("diagnose") or _diagnose()
        elif command == TAIL:
            payload = tail_trace or _trace([])
        elif command.startswith(".botauto trace") and state["cleanup"]:
            payload = drains[state["drain"]] if state["drain"] < len(drains) else _trace([], pending=0)
            state["drain"] += 1
        else:
            payload = beat.get("trace") or _trace([])
        return json.dumps(payload) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        state["beat"] += 1
        if state["beat"] > (max_beats or len(beats)):
            raise LoopKeptRunning

    output_dir = tmp_path / "run"
    output, _code, _timed_out, _command = run_transport_completion_watchdog(
        execute, ["attached"], None,
        command_script(selector="all", trace_limit=128, start=False, stop=True,
                       exit_server=False, cohort_id=COHORT, trace_delta=True),
        output_dir, {}, {"scenario_id": "blackwing_descent_10n_c0_diagnostic"},
        validation_route_manifest=manifest or MANIFEST, heartbeat_sec=1, no_progress_window_sec=600,
        status_command=f".botauto status {COHORT}", sleep=sleep,
    )
    return commands, output_dir, output


def _heartbeats(output_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (output_dir / "heartbeat_events.jsonl").read_text().splitlines()]


def _report(output_dir: Path) -> dict:
    return json.loads((output_dir / "report.json").read_text())


# Item 2: a failed pre-pull gate is an advisory label, never a terminal by itself.

def test_batch_magmaw_sequence_clears_despite_a_failed_prepull_gate(tmp_path):
    """Round-2 batch Magmaw: gate failed for 10 unengaged heartbeats, then engage, kill, clear."""
    beats = [{"status": _status(**MAGMAW, kills=3), "trace": _trace(_route_rows(1, 20, **_scope(MAGMAW)))}]
    beats += [{"status": _status(**MAGMAW, kills=3, prepull_failed=True),
               "trace": _trace(_route_rows(21 + index * 10, 10, **_scope(MAGMAW)))} for index in range(10)]
    beats += [{"status": _status(**MAGMAW, kills=3, prepull_failed=True, engaged=True, alive=alive),
               "trace": _trace(_route_rows(121 + index * 5, 5, **_scope(MAGMAW)))}
              for index, alive in enumerate([9, 9, 9, 8])]
    killed = dict(**MAGMAW, kills=4, prepull_failed=True, boss_dead=True, alive=8)
    beats += [
        {"status": _status(**killed), "trace": _trace(_route_rows(141, 2, **_scope(MAGMAW)))},
        # Heartbeat 25 of the batch: the drained window holds no route action
        # and idle bots report error diagnoses.  Round 2 labelled it
        # bot_diagnosis_error and the run ended as a machine failure.
        {"status": _status(**killed), "diagnose": _diagnose(error=True), "trace": _trace([])},
        {"status": _status(**{**killed, "alive": 10}, manifest_complete=True),
         "diagnose": _diagnose(error=True), "trace": _trace([])},
    ]
    commands, output_dir, _output_text = _run(tmp_path, beats, manifest=_manifest(**_scope(MAGMAW)))
    heartbeats = _heartbeats(output_dir)
    assert len(heartbeats) == len(beats) == 18
    assert PREPULL_LABEL not in heartbeats[0]["failure_labels"]
    assert all(PREPULL_LABEL in row["failure_labels"] for row in heartbeats[1:17])
    assert all(row["completion_reason"] != "machine_failure_predicate" for row in heartbeats)
    assert all("bot_diagnosis_error" not in row["failure_labels"] for row in heartbeats)
    report = _report(output_dir)
    assert report["completion_reason"] == "validation_route_manifest_complete"
    assert report["failure_labels"] == []
    assert TAIL not in commands and not (output_dir / TERMINAL_TRACE_DRAIN_FILE).exists()


def _scope(where: dict) -> dict:
    return {"node": where["node"], "generation": where["generation"]}


def test_batch_maloriak_sequence_ends_on_the_diagnosis_error_not_the_label(tmp_path):
    """Round-2 Maloriak: the gate held the pull; the drained window then surfaced the error."""
    beats = [{"status": _status(kills=3), "trace": _trace(_route_rows(1, 30))}]
    beats += [{"status": _status(kills=3, prepull_failed=True), "trace": _trace(_route_rows(31 + index * 20, 20))}
              for index in range(10)]
    beats += [{"status": _status(kills=3, prepull_failed=True), "diagnose": _diagnose(error=True),
               "trace": _trace([])}]
    _commands, output_dir, _output_text = _run(tmp_path, beats)
    heartbeats = _heartbeats(output_dir)
    assert len(heartbeats) == 12
    assert heartbeats[1]["failure_labels"] == [PREPULL_LABEL]
    assert all(row["completion_reason"] == "incomplete_evidence" for row in heartbeats[1:11])
    report = _report(output_dir)
    assert report["completion_reason"] == "machine_failure_predicate"
    # The advisory label never headlines a gameplay failure.
    assert report["failure_labels"] == ["bot_diagnosis_error", PREPULL_LABEL]
    assert report["failure_reason"] == "bot_diagnosis_error"
    assert report["evidence"]["prepull_consumables_failure"]["failure_reason"] == PREPULL_REASON


def test_a_prepull_label_never_turns_a_provisional_no_progress_into_a_failure():
    stalled = {**_route_rows(1, 1)[0], "route_progress": {"no_progress": {"count": 5, "threshold": 3}}}
    report = live_validation_report(_output(_status(prepull_failed=True), _diagnose(), _trace([stalled])),
                                    validation_route_manifest=MANIFEST)
    assert report["failure_labels"][-1] == PREPULL_LABEL
    assert report["completion_reason"] == "no_progress_observed"
    zero_progress = live_validation_report(
        _output(_status(prepull_failed=True, kills=0), _diagnose(), _trace([])),
        validation_route_manifest=MANIFEST)
    assert zero_progress["failure_labels"][-1] == PREPULL_LABEL
    assert zero_progress["completion_reason"] != "machine_failure_predicate"


def test_the_advisory_label_does_not_block_a_combat_deferral():
    report = {"completion_reason": "machine_failure_predicate",
              "failure_labels": ["bot_diagnosis_error", PREPULL_LABEL],
              "watchdog_state": {"live_combat_progress": {"damage": [
                  {"route_node_id": "bwd.magmaw.encounter", "route_generation": 4,
                   "attempt_epoch": 0, "party_damage": 5}]}}}
    assert should_defer_active_combat_bot_diagnosis(report) is True
    report["failure_labels"] = [PREPULL_LABEL]
    assert should_defer_active_combat_bot_diagnosis(report) is False


def test_the_advisory_label_never_blocks_a_manifest_less_route_segment():
    route = {"route_node_id": "bwd.maloriak.lab_trash", "route_generation": 2, "kind": "trash"}
    scope = {"route_node_id": "bwd.maloriak.lab_trash", "route_generation": 2}
    report = {"failure_labels": ["no_progress_observed", PREPULL_LABEL],
              "evidence": {"route_terminal_evidence": [scope], "trash_pulls": 3}, "trace": {}}
    assert route_segment_complete(report, route) is True
    supersede_transient_route_failures(report)
    assert report["failure_labels"] == [] and report["failure_reason"] is None
    assert report["superseded_failure_labels"] == ["no_progress_observed", PREPULL_LABEL]
    report["failure_labels"] = ["bot_diagnosis_error", PREPULL_LABEL]
    assert route_segment_complete(report, route) is False


def test_a_stale_prepull_failure_from_another_route_generation_is_ignored():
    report = live_validation_report(
        _output(_status(prepull_failed=True, prepull_generation=2), _diagnose(), _trace(_route_rows(1, 2))),
        validation_route_manifest=MANIFEST)
    assert report["evidence"]["prepull_consumables_failure"] == {}
    assert all(not label.startswith("raid_prepull") for label in report["failure_labels"])


def test_prepull_failure_never_overrides_a_native_clear():
    status = _status(prepull_failed=True, manifest_complete=True, boss_dead=True)
    report = live_validation_report(_output(status, _diagnose(), _trace(_route_rows(1, 2))),
                                    validation_route_manifest=MANIFEST)
    assert PREPULL_LABEL not in report["failure_labels"]
    assert report["evidence"]["prepull_consumables_failure"]["failure_reason"] == PREPULL_REASON
    assert report["completion_reason"] == "validation_route_manifest_complete"


# Item 3: label predicates keep the window count; the cumulative count is separate.

def test_label_predicates_use_the_window_and_the_cumulative_count_is_reported(tmp_path):
    beats = [
        {"status": _status(), "trace": _trace(_route_rows(1, 7))},
        # After kills, a drained window with an error diagnosis still fails the
        # run: the cumulative count must not mask a stalled route.
        {"status": _status(), "diagnose": _diagnose(error=True), "trace": _trace([])},
    ]
    _commands, output_dir, _output_text = _run(tmp_path, beats)
    heartbeats = _heartbeats(output_dir)
    assert [row["progress_counters"]["validation_route_actions"] for row in heartbeats] == [7, 0]
    assert [row["progress_counters"]["validation_route_actions_cumulative"] for row in heartbeats] == [7, 7]
    report = _report(output_dir)
    assert report["completion_reason"] == "machine_failure_predicate"
    assert report["failure_labels"][0] == "bot_diagnosis_error"


def test_an_idle_raid_after_a_native_boss_kill_is_not_a_dead_route():
    signals = HeartbeatSignals()
    live_validation_report(_output(_status(**MAGMAW), _diagnose(), _trace(_route_rows(1, 5, **_scope(MAGMAW)))),
                           signals=signals)
    idle = live_validation_report(
        _output(_status(**MAGMAW, kills=4, boss_dead=True), _diagnose(error=True), _trace([])), signals=signals)
    assert idle["evidence"]["validation_route_actions"] == 0
    assert idle["evidence"]["validation_route_actions_cumulative"] == 5
    assert "bot_diagnosis_error" not in idle["failure_labels"]
    # The boss death of an earlier node does not cover the current one.
    stalled = _status(node="bwd.maloriak.encounter", generation=5, kills=4)
    stalled["validation_route"]["boss_death_evidence"] = [
        {"route_node_id": MAGMAW["node"], "route_generation": 4, "target_id": 991, "target_entry": 41570, "result": "ok"}]
    later = live_validation_report(_output(stalled, _diagnose(error=True), _trace([])), signals=signals)
    assert "bot_diagnosis_error" in later["failure_labels"]


def test_route_action_ledger_deduplicates_repeated_rows():
    ledger = RouteActionLedger()
    rows = [{**row, "bot_guid": 5} for row in _route_rows(1, 4)]
    assert ledger.observe(rows) == 4
    # A light tail or a drain re-exports rows already counted.
    assert ledger.observe(rows[2:] + [{"bot_guid": 5, "sequence": 9, "action": "cast_spell"}]) == 4
    assert ledger.observe([{**rows[0], "sequence": 10, "timestamp_ms": 99}]) == 5


# Item 4: contamination is a label only; wipe loops end through the near-wipe death loop.

def _contaminated_clear(tmp_path, beats, node, generation, *, kills):
    rows = beats[-1]["status"]["validation_route"]["contamination_evidence"]
    clear = _status(node=node, generation=generation, kind="boss", kills=kills + 1, boss_dead=True,
                    manifest_complete=True, contamination_rows=rows)
    beats = beats + [{"status": clear, "trace": _trace(_route_rows(900, 2, node=node, generation=generation))}]
    _commands, output_dir, _output_text = _run(tmp_path, beats, manifest=_manifest(node, generation))
    heartbeats = _heartbeats(output_dir)
    return heartbeats, _report(output_dir)


SENTRY_ROW = {"route_node_id": "bwd.omnotron.regroup", "route_generation": 1, "route_kind": "regroup",
              "target_id": GOLEM_GUID, "target_entry": GOLEM_ENTRY}


def test_scenario_a_magmaw_pull_after_a_recovered_drudge_near_wipe_clears(tmp_path):
    """A bot tags Magmaw from the drudge node; Magmaw reads as the active hostile all pre-pull."""
    row = {"route_node_id": "bwd.magmaw.drudges", "route_generation": 3, "route_kind": "trash",
           "target_id": MAGMAW_GUID, "target_entry": 41570}
    drudges = dict(node="bwd.magmaw.drudges", generation=3, kind="trash", contamination_rows=[row])
    rows = lambda first, **where: _trace(_route_rows(first, 5, **where))  # noqa: E731
    beats = [
        {"status": _status(**drudges, kills=1, hostile_guid=DRUDGE_GUID, hostile_entry=42362),
         "trace": rows(1, node="bwd.magmaw.drudges", generation=3)},
        {"status": _status(**drudges, kills=2, alive=4, deaths=6, hostile_guid=DRUDGE_GUID, hostile_entry=42362),
         "trace": rows(6, node="bwd.magmaw.drudges", generation=3)},
        {"status": _status(**drudges, kills=3, deaths=6), "trace": rows(11, node="bwd.magmaw.drudges", generation=3)},
    ] + [
        {"status": _status(**MAGMAW, kills=3, deaths=6, contamination_rows=[row],
                           hostile_guid=MAGMAW_GUID, hostile_entry=41570),
         "trace": rows(16 + index * 5, **_scope(MAGMAW))} for index in range(4)
    ]
    heartbeats, report = _contaminated_clear(tmp_path, beats, MAGMAW["node"], 4, kills=3)
    assert len(heartbeats) == 8
    assert all("validation_route_future_encounter_contamination" in row["failure_labels"] for row in heartbeats[:7])
    assert report["completion_reason"] == "validation_route_manifest_complete"


@pytest.mark.parametrize("near_wipe_hostile", [(GOLEM_GUID, GOLEM_ENTRY), (DRUDGE_GUID, 1)], ids=["B", "B2"])
def test_scenarios_b_sentry_fought_on_its_own_node_after_recovery_clear(tmp_path, near_wipe_hostile):
    """B: the sentry wiped the regroup node, the raid recovered and fought it on its own node.

    B2: the same, but the sentry was not the reported hostile at the near-wipe.
    """
    guid, entry = near_wipe_hostile
    regroup = dict(node="bwd.omnotron.regroup", generation=1, kind="regroup", contamination_rows=[SENTRY_ROW])
    sentries = dict(node="bwd.omnotron.sentries", generation=2, kind="trash", contamination_rows=[SENTRY_ROW])
    beats = [
        {"status": _status(**regroup, kills=0, alive=3, deaths=7, hostile_guid=guid, hostile_entry=entry),
         "trace": _trace(_route_rows(1, 5, node="bwd.omnotron.regroup", generation=1))},
        {"status": _status(**regroup, kills=0, deaths=7),
         "trace": _trace(_route_rows(6, 5, node="bwd.omnotron.regroup", generation=1))},
        {"status": _status(**sentries, kills=0, deaths=7, hostile_guid=GOLEM_GUID, hostile_entry=GOLEM_ENTRY),
         "trace": _trace(_route_rows(11, 5, node="bwd.omnotron.sentries", generation=2))},
        {"status": _status(**sentries, kills=2, deaths=7),
         "trace": _trace(_route_rows(16, 5, node="bwd.omnotron.sentries", generation=2))},
    ]
    heartbeats, report = _contaminated_clear(tmp_path, beats, "bwd.omnotron.encounter", 3, kills=2)
    assert len(heartbeats) == 5
    assert report["completion_reason"] == "validation_route_manifest_complete"


def test_omnotron_contamination_wipe_loop_ends_as_a_death_loop_at_heartbeat_10(tmp_path):
    """Round-2 Omnotron replay: the Golem re-engages after each runback; hb10 is the third near-wipe."""
    alive = [1, 8, 9, 9, 3, 5, 10, 10, 10, 3, 10, 5]
    golem = {3, 4, 5, 9, 11, 12}
    beats = [{"status": _status(**OMNOTRON, contamination=True, alive=count, wipe_generation=0 if index == 0 else 1,
                                **({"hostile_guid": GOLEM_GUID, "hostile_entry": GOLEM_ENTRY}
                                   if index + 1 in golem else {})),
              "trace": _trace(_route_rows(index * 5 + 1, 5, node=OMNOTRON["node"], generation=1))}
             for index, count in enumerate(alive)]
    commands, output_dir, _output_text = _run(tmp_path, beats, manifest=_manifest("bwd.omnotron.encounter", 3))
    heartbeats = _heartbeats(output_dir)
    assert len(heartbeats) == 10
    assert all(row["failure_labels"][0] == "validation_route_future_encounter_contamination" for row in heartbeats)
    report = _report(output_dir)
    assert report["completion_reason"] == "death_loop_watchdog"
    assert "validation_route_death_loop" in report["failure_labels"]
    assert commands[-1] == f".botauto stop {COHORT}"


def test_a_transient_contaminating_patrol_never_ends_a_run_that_clears(tmp_path):
    engaged = dict(contamination=True, hostile_guid=GOLEM_GUID, hostile_entry=GOLEM_ENTRY)
    beats = [{"status": _status(**engaged), "trace": _trace(_route_rows(index * 5 + 1, 5))} for index in range(3)]
    beats += [{"status": _status(contamination=True), "trace": _trace(_route_rows(16, 5))},
              {"status": _status(contamination=True, boss_dead=True, manifest_complete=True, kills=4),
               "trace": _trace(_route_rows(21, 2))}]
    _commands, output_dir, _output_text = _run(tmp_path, beats)
    report = _report(output_dir)
    assert len(_heartbeats(output_dir)) == 5
    assert report["completion_reason"] == "validation_route_manifest_complete"


# Item 5: repeated near-wipes on one node are a death loop.

OMNOTRON_ALIVE = [1, 8, 9, 9, 3, 5, 10, 10, 10, 3, 10, 5, 1, 10, 9]


def test_omnotron_near_wipes_count_as_death_loop_episodes():
    tracker = NearWipeTracker()
    episodes = [tracker.observe(_status(**OMNOTRON, alive=alive, wipe_generation=0 if index == 0 else 1))
                for index, alive in enumerate(OMNOTRON_ALIVE)]
    assert episodes == [1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 4, 4, 4, 4]
    # Idempotent: the final-timeout path rebuilds the same heartbeat.
    assert tracker.observe(_status(**OMNOTRON, alive=9, wipe_generation=1)) == 4


def test_near_wipe_baselines_come_from_the_first_observation():
    tracker = NearWipeTracker()
    # Carried-in wipe generation and deaths are not a new wipe or a burst.
    assert tracker.observe(_status(**MAGMAW, alive=10, wipe_generation=2, deaths=40)) == 0
    assert tracker.observe(_status(**MAGMAW, alive=10, wipe_generation=2, deaths=41)) == 0
    assert tracker.observe(_status(**MAGMAW, alive=10, wipe_generation=2, deaths=47)) == 1


def test_the_kill_heartbeat_is_never_a_near_wipe():
    """The kill pull can lose half the raid and still clear."""
    tracker = NearWipeTracker()
    assert tracker.observe(_status(**MAGMAW, alive=10, deaths=2)) == 0
    assert tracker.observe(_status(**MAGMAW, alive=4, deaths=8, boss_dead=True)) == 0
    assert tracker.observe(_status(**MAGMAW, alive=4, deaths=8, boss_dead=True, manifest_complete=True)) == 0
    completed = NearWipeTracker()
    assert completed.observe(_status(**MAGMAW, alive=10)) == 0
    assert completed.observe(_status(**MAGMAW, alive=3, manifest_complete=True)) == 0


def test_recovered_trash_deaths_and_partial_deaths_are_not_death_loops():
    tracker = NearWipeTracker()
    # Magmaw batch: partial deaths (8/10) never count.
    for alive in (10, 8, 9, 10, 9, 8, 8, 10):
        assert tracker.observe(_status(**MAGMAW, alive=alive)) == 0
    trash = dict(node="bwd.maloriak.lab_trash", generation=2, kind="trash")
    # A node entered while the raid is already down does not inherit the drop.
    assert tracker.observe(_status(**trash, alive=4, kills=0)) == 0
    assert tracker.observe(_status(**trash, alive=10, kills=0)) == 0
    assert tracker.observe(_status(**trash, alive=4, kills=0)) == 1
    assert tracker.observe(_status(**trash, alive=10, kills=0)) == 1
    # A kill after the near-wipe: the raid recovered and progressed.
    assert tracker.observe(_status(**trash, alive=10, kills=2)) == 0
    # Boss window: add kills never reset boss near-wipes.
    boss = dict(node="bwd.maloriak.encounter", generation=3, kind="boss")
    assert tracker.observe(_status(**boss, alive=10, kills=2)) == 0
    assert tracker.observe(_status(**boss, alive=3, kills=2)) == 1
    assert tracker.observe(_status(**boss, alive=10, kills=5)) == 1
    # A burst of deaths between heartbeats is a near-wipe even if the dip was not sampled.
    assert tracker.observe(_status(**boss, alive=10, kills=5, deaths=0)) == 1
    assert tracker.observe(_status(**boss, alive=10, kills=5, deaths=6)) == 2


def test_repeated_near_wipes_end_the_run_as_a_death_loop(tmp_path):
    beats = [{"status": _status(**OMNOTRON, alive=alive),
              "trace": _trace(_route_rows(index * 3 + 1, 3, node=OMNOTRON["node"], generation=1))}
             for index, alive in enumerate([1, 8, 3, 10, 3])]
    _commands, output_dir, _output_text = _run(tmp_path, beats, max_beats=6)
    heartbeats = _heartbeats(output_dir)
    assert [row["progress_counters"]["death_loop_events"] for row in heartbeats] == [1, 1, 2, 2, 3]
    report = _report(output_dir)
    assert report["completion_reason"] == "death_loop_watchdog"
    assert "validation_route_death_loop" in report["failure_labels"]
    assert report["evidence"]["near_wipe_death_loop"]["history"][-1]["alive"] == 3


# Item 6: after a terminal failure the pending and newest trace rows are captured.

def test_terminal_failure_drains_the_backlog_and_captures_the_newest_rows(tmp_path):
    beats = [{"status": _status(), "trace": _trace(_route_rows(1, 39))},
             {"status": _status(), "diagnose": _diagnose(error=True),
              "trace": _trace([{**row, "action": "cast_spell"} for row in _route_rows(40, 128)],
                              pending=184, newest=351)}]
    drains = [_trace(_route_rows(168, 128), pending=56, newest=351),
              _trace(_route_rows(296, 56), pending=0, newest=351)]
    tail = _trace(_route_rows(224, 128), newest=351)
    commands, output_dir, output = _run(tmp_path, beats, drain_traces=drains, tail_trace=tail)
    assert _report(output_dir)["failure_reason"] == "bot_diagnosis_error"
    stop = commands.index(f".botauto stop {COHORT}")
    assert [command for command in commands[:stop] if command.startswith(".botauto trace")][-3:] == [TRACE, TRACE, TAIL]
    with gzip.open(output_dir / TERMINAL_TRACE_DRAIN_FILE, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert len(rows) == 184 and max(row["entry"]["sequence"] for row in rows) == 351
    receipt = next(row for row in parse_json_objects(output) if row.get("purpose") == "terminal_trace_drain")
    assert receipt["delta_backlog_drained"] is True and receipt["newest_captured"] is True
    assert receipt["bots"][0]["last_captured_sequence"] == 351 and receipt["bots"][0]["tail_rows"] == 128


def test_a_bounded_drain_reports_the_backlog_it_left_honestly(tmp_path):
    """Delta exports return the OLDEST pending rows; only the tail reaches the newest."""
    calls: list[str] = []
    now = {"t": 0.0}

    def run(command: str) -> tuple[str, bool]:
        calls.append(command)
        now["t"] += 4.0
        if command == TAIL:
            # No newest_retained_sequence here: the tail is the newest rows by definition.
            return json.dumps(_trace(_route_rows(2263, 128))), True
        first = 1 + 128 * (len(calls) - 1)
        return json.dumps(_trace(_route_rows(first, 128), pending=2390 - first - 127, newest=2390)), True

    receipt = json.loads(drain_terminal_trace(
        run, [".botauto status c0", TRACE], tmp_path, parse_json_objects,
        budget_sec=10.0, clock=lambda: now["t"],
    ))
    assert calls == [TRACE, TRACE, TRACE, TAIL]
    assert receipt["action"] == "harness_cleanup_step" and receipt["purpose"] == "terminal_trace_drain"
    assert receipt["delta_stop_reason"] == "budget_exhausted" and receipt["timed_out"] is True
    assert receipt["delta_backlog_drained"] is False and receipt["delta_pending_after"] == 2390 - 384
    assert receipt["newest_captured"] is True and receipt["completed"] is True
    assert receipt["bots"][0]["newest_retained_sequence"] == 2390 and receipt["bots"][0]["tail_rows"] == 128
    # No delta trace command configured: nothing to drain.
    assert drain_terminal_trace(run, [".botauto status c0"], tmp_path, parse_json_objects) == ""


def test_a_failed_tail_never_claims_the_newest_rows(tmp_path):
    def run(command: str) -> tuple[str, bool]:
        if command == TAIL:
            return "", True
        # A delta row that happens to reach newest_retained_sequence is not proof.
        return json.dumps(_trace(_route_rows(10, 1), pending=0, newest=10)), True

    receipt = json.loads(drain_terminal_trace(run, [TRACE], tmp_path, parse_json_objects))
    assert receipt["delta_backlog_drained"] is True
    assert receipt["tail_captured"] is False and receipt["newest_captured"] is False
    assert receipt["completed"] is False and receipt["bots"][0]["newest_captured"] is False


def test_a_native_clear_does_not_drain(tmp_path):
    beats = [{"status": _status(manifest_complete=True, boss_dead=True),
              "trace": _trace(_route_rows(1, 5), pending=40)}]
    commands, output_dir, _output_text = _run(tmp_path, beats)
    assert commands.count(TRACE) == 1 and TAIL not in commands
    assert not (output_dir / TERMINAL_TRACE_DRAIN_FILE).exists()
    assert _report(output_dir)["completion_reason"] == "validation_route_manifest_complete"


# Item 7: native fall damage is environmental, not friendly.

def _self_hit(guid: int, name: str, role: str, amount: int) -> dict:
    return {
        "route_generation": 4, "route_node_id": "bwd.nefarian.descent", "perspective": "friendly_damage_done",
        "actor_guid": guid, "actor_name": name, "actor_role": role, "actor_class_id": 6,
        "source_entry": 0, "source_name": name, "source_is_pet": False, "spell_id": 0, "spell_name": "Melee",
        "target_entry": 0, "target_name": name, "amount": amount, "originated_amount": amount,
        "raw_amount": amount, "event_count": 1, "first_at_ms": 5_000, "last_at_ms": 5_000,
    }


def _nefarian_drop_log(*, with_falls: bool, fall_spell_id: int = 0) -> dict:
    friendly_fire = {**_self_hit(2, "Bwnefnbb", "tank", 300), "spell_id": 3, "spell_name": "Friendly Fire",
                     "target_name": "Bwnefnba", "first_at_ms": 3_000, "last_at_ms": 3_000}
    hostile = {**_self_hit(2, "Bwnefnbb", "tank", 1000), "perspective": "damage_done", "spell_id": 7,
               "spell_name": "Strike", "target_entry": 41918, "target_name": "Animated Bone Warrior",
               "first_at_ms": 1_000, "last_at_ms": 9_000}
    abilities = [friendly_fire, hostile]
    buckets = [
        {"route_generation": 4, "perspective": "damage_done", "actor_guid": 2,
         "source_is_pet": False, "second": 1, "amount": 1000, "originated_amount": 1000},
        {"route_generation": 4, "perspective": "friendly_damage_done", "actor_guid": 2,
         "source_is_pet": False, "second": 3, "amount": 300, "originated_amount": 300},
    ]
    if with_falls:
        abilities += [{**_self_hit(1, "Bwnefnba", "tank", 60232), "spell_id": fall_spell_id},
                      {**_self_hit(2, "Bwnefnbb", "tank", 61955), "spell_id": fall_spell_id}]
        # Bwnefnba's only friendly-side row is its fall, in a second of its own.
        buckets += [{"route_generation": 4, "perspective": "friendly_damage_done", "actor_guid": actor,
                     "source_is_pet": False, "second": second, "amount": amount, "originated_amount": amount}
                    for actor, amount, second in ((1, 60232, 7), (2, 61955, 5))]
    return {"combat_log_schema_version": 8, "damage_attribution_schema": "originated_amount_v2_friendly_split",
            "abilities": abilities, "second_buckets": buckets}


def test_fall_damage_is_environmental_not_friendly():
    encounter = analyze_combat_log(_nefarian_drop_log(with_falls=True))["encounters"][0]
    actors = {row["actor_name"]: row for row in encounter["actors"]}
    assert actors["Bwnefnba"]["friendly_damage"] == 0
    # raw_event_* keep their previous meaning (analyze_magmaw_trace reads them).
    assert actors["Bwnefnba"]["raw_event_damage"] == actors["Bwnefnba"]["raw_event_friendly_damage"] == 60232
    assert actors["Bwnefnba"]["environmental_damage"] == 60232
    assert actors["Bwnefnba"]["friendly_abilities"] == []
    assert actors["Bwnefnbb"]["friendly_damage"] == 300
    assert actors["Bwnefnbb"]["environmental_damage"] == 61955
    assert actors["Bwnefnbb"]["damage"] == 1000
    assert encounter["party_friendly_damage"] == 300
    assert encounter["party_environmental_damage"] == 122187
    # The fall seconds stay in the active-combat denominator, as before.
    assert encounter["combat_duration_sec"] == 4


RATE_FIELDS = ("combat_duration_sec", "party_dps", "party_hps", "raw_event_damage", "raw_event_dps",
               "party_raw_event_friendly_damage", "party_damage_taken")
ACTOR_RATE_FIELDS = ("dps", "hps", "damage_uptime", "pet_uptime", "raw_event_damage", "raw_event_dps",
                     "raw_event_friendly_damage", "raw_event_pet_damage", "raw_event_pet_damage_share")


def test_environmental_tagging_moves_only_the_friendly_figures():
    """dps/hps/uptime and every raw_event_* field are those of the pre-tagging accounting."""
    tagged = analyze_combat_log(_nefarian_drop_log(with_falls=True))["encounters"][0]
    # The same rows as ordinary friendly fire (a spell): the pre-tagging accounting.
    untagged = analyze_combat_log(_nefarian_drop_log(with_falls=True, fall_spell_id=1))["encounters"][0]
    for field in RATE_FIELDS:
        assert tagged[field] == untagged[field], field
    assert tagged["party_friendly_damage"] == untagged["party_friendly_damage"] - 122187
    actors = {row["actor_guid"]: row for row in untagged["actors"]}
    for actor in tagged["actors"]:
        for name in ACTOR_RATE_FIELDS:
            assert actor[name] == actors[actor["actor_guid"]][name], (actor["actor_name"], name)


ENCOUNTER_WINDOW_FIELDS = ("first_at_ms", "last_at_ms", "duration_sec", "encounter_window_party_dps",
                           "encounter_window_boundary_basis", "party_damage", "elapsed_party_dps")
ACTOR_WINDOW_FIELDS = ("damage", "encounter_window_dps", "elapsed_dps", "active_seconds", "active_dps")


@pytest.mark.parametrize("field", ENCOUNTER_WINDOW_FIELDS)
def test_environmental_rows_leave_every_encounter_window_field_unchanged(field):
    with_falls = analyze_combat_log(_nefarian_drop_log(with_falls=True))["encounters"][0]
    without = analyze_combat_log(_nefarian_drop_log(with_falls=False))["encounters"][0]
    assert with_falls[field] == without[field]
    actors = {row["actor_guid"]: row for row in with_falls["actors"]}
    for actor in without["actors"]:
        for name in ACTOR_WINDOW_FIELDS:
            assert actors[actor["actor_guid"]][name] == actor[name]

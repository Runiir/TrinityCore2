"""Round 3 harness package H: terminal signals from the round-2 BWD 10N batch."""
from __future__ import annotations

import gzip
import json
from pathlib import Path

import pytest

from tools.bot_ml.analyze_combat_log import analyze_combat_log
from tools.bot_ml.live_validation_terminal_signals import (
    TERMINAL_TRACE_DRAIN_FILE,
    ContaminationWatchdog,
    NearWipeTracker,
    RouteActionLedger,
    drain_terminal_trace,
)
from tools.bot_ml.run_live_bot_validation import (
    command_script,
    live_validation_report,
    parse_json_objects,
    run_transport_completion_watchdog,
)

COHORT = "c0"
PREPULL_REASON = "raid_prepull_unknown_spec_contract_beast_mastery_hunter"
PREPULL_LABEL = "raid_prepull_consumables_failed:" + PREPULL_REASON
TRACE = f".botauto trace {COHORT} all 128 delta"


class LoopKeptRunning(Exception):
    """The scripted heartbeats ran out while the watchdog was still running."""


MANIFEST = {
    "schema": "bot_live_validation_route_manifest_v1",
    "routes": [{"route_node_id": "bwd.maloriak.encounter", "route_generation": 3, "kind": "boss"}],
}


def _status(*, node="bwd.maloriak.encounter", generation=3, kind="boss", alive=10, kills=3,
            deaths=0, prepull_failed=False, contamination=False, wipe_generation=0,
            manifest_complete=False, boss_dead=False, engaged=False, prepull_generation=None) -> dict:
    route = {"node_id": node, "generation": generation, "kind": kind, "manifest_complete": manifest_complete}
    scope = {"route_node_id": node, "route_generation": generation}
    if contamination:
        route["contamination_evidence"] = [{**scope, "target_entry": 42800,
                                            "result": "validation_route_future_encounter_contamination"}]
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
            "encounter_in_progress": engaged,
            "wipe_generation": wipe_generation, "recovery_state": "none",
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


def _trace(entries: list[dict], *, pending=0, guid=5) -> dict:
    return {"ok": True, "action": "botauto_trace", "trace_schema_version": 1,
            "bots": [{"bot_guid": guid, "bot_name": "Bwbot", "delta": True,
                      "pending_entry_count": pending, "entries": entries}]}


def _route_rows(first: int, count: int, *, node="bwd.maloriak.encounter", generation=3) -> list[dict]:
    return [{"sequence": first + index, "timestamp_ms": 1_000 + first + index,
             "action": "validation_route_hold_anchor", "result": "hold",
             "route_node_id": node, "route_generation": generation} for index in range(count)]


def _run(tmp_path: Path, beats: list[dict], *, max_beats: int | None = None,
         drain_traces: list[dict] | None = None) -> tuple[list[str], Path]:
    """Drive the transport watchdog over scripted heartbeats.

    Each beat maps ``status``/``diagnose``/``trace`` to payloads.  Past the last
    scripted beat the last one repeats; ``sleep`` interrupts after ``max_beats``
    so a loop that never terminates raises ``LoopKeptRunning``.
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
    run_transport_completion_watchdog(
        execute, ["attached"], None,
        command_script(selector="all", trace_limit=128, start=False, stop=True,
                       exit_server=False, cohort_id=COHORT, trace_delta=True),
        output_dir, {}, {"scenario_id": "blackwing_descent_10n_maloriak_c0_diagnostic"},
        validation_route_manifest=MANIFEST, heartbeat_sec=1, no_progress_window_sec=600,
        status_command=f".botauto status {COHORT}", sleep=sleep,
    )
    return commands, output_dir


def _heartbeats(output_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (output_dir / "heartbeat_events.jsonl").read_text().splitlines()]


def _report(output_dir: Path) -> dict:
    return json.loads((output_dir / "report.json").read_text())


# Item 2: a failed pre-pull gate is labelled on the heartbeat that reports it.

def test_prepull_failure_is_labelled_at_once_and_terminal_on_the_next_heartbeat(tmp_path):
    beats = [{"status": _status(), "trace": _trace(_route_rows(1, 5))},
             {"status": _status(prepull_failed=True), "trace": _trace([])},
             {"status": _status(prepull_failed=True), "trace": _trace([])}]
    _commands, output_dir = _run(tmp_path, beats, max_beats=5)
    heartbeats = _heartbeats(output_dir)
    assert len(heartbeats) == 3
    assert PREPULL_LABEL not in heartbeats[0]["failure_labels"]
    # Surfaced on the heartbeat that first reports it (round 2: ~395 s later).
    assert heartbeats[1]["failure_labels"][0] == PREPULL_LABEL
    assert heartbeats[1]["completion_reason"] != "machine_failure_predicate"
    report = _report(output_dir)
    assert report["completion_reason"] == "machine_failure_predicate"
    assert report["failure_reason"] == PREPULL_LABEL
    terminal = report["watchdog_state"]["terminal_failure"]
    assert terminal["kind"] == "raid_prepull_consumables_failed"
    assert terminal["first_observed_heartbeat_index"] == 2 and terminal["route_generation"] == 3
    assert report["evidence"]["prepull_consumables_failure"]["failure_reason"] == PREPULL_REASON


def test_a_failed_prepull_gate_does_not_cut_a_native_engagement_short(tmp_path):
    """Round-2 Magmaw smoke: failed=true, yet Magmaw engaged natively and died."""
    manifest_node = dict(node="bwd.maloriak.encounter", generation=3)
    beats = [{"status": _status(**manifest_node, prepull_failed=True), "trace": _trace(_route_rows(1, 5))},
             {"status": _status(**manifest_node, prepull_failed=True, engaged=True), "trace": _trace([])},
             {"status": _status(**manifest_node, prepull_failed=True, manifest_complete=True, boss_dead=True),
              "trace": _trace([])}]
    _commands, output_dir = _run(tmp_path, beats, max_beats=5)
    heartbeats = _heartbeats(output_dir)
    assert heartbeats[0]["failure_labels"][0] == PREPULL_LABEL
    report = _report(output_dir)
    assert report["completion_reason"] == "validation_route_manifest_complete"
    assert PREPULL_LABEL not in report["failure_labels"]


def test_a_stale_prepull_failure_from_another_route_generation_is_ignored():
    status = _status(prepull_failed=True, prepull_generation=2)
    output = "\n".join(json.dumps(row) for row in (status, _diagnose(), _trace(_route_rows(1, 2))))
    report = live_validation_report(output, validation_route_manifest=MANIFEST)
    assert report["evidence"]["prepull_consumables_failure"] == {}
    assert all(not label.startswith("raid_prepull") for label in report["failure_labels"])


def test_prepull_failure_never_overrides_a_native_clear():
    status = _status(prepull_failed=True, manifest_complete=True, boss_dead=True)
    output = "\n".join(json.dumps(row) for row in (status, _diagnose(), _trace(_route_rows(1, 2))))
    report = live_validation_report(output, validation_route_manifest=MANIFEST)
    assert PREPULL_LABEL not in report["failure_labels"]
    assert report["evidence"]["prepull_consumables_failure"]["failure_reason"] == PREPULL_REASON
    assert report["completion_reason"] == "validation_route_manifest_complete"


# Item 3: a drained trace window does not erase the attempt's route actions.

def test_route_actions_are_cumulative_across_drained_trace_windows(tmp_path):
    beats = [
        {"status": _status(), "trace": _trace(_route_rows(1, 7))},
        # A long hold: the delta window has no route action and one bot has an
        # error diagnosis.  Round 2 labelled this bot_diagnosis_error.
        {"status": _status(), "diagnose": _diagnose(error=True), "trace": _trace([])},
        {"status": _status(), "diagnose": _diagnose(error=True), "trace": _trace([])},
    ]
    with pytest.raises(LoopKeptRunning):
        _run(tmp_path, beats)
    heartbeats = _heartbeats(tmp_path / "run")
    assert [row["progress_counters"]["validation_route_actions"] for row in heartbeats] == [7, 7, 7]
    assert [row["progress_counters"]["validation_route_actions_window"] for row in heartbeats] == [7, 0, 0]
    assert all("bot_diagnosis_error" not in row["failure_labels"] for row in heartbeats)


def test_route_action_ledger_deduplicates_repeated_rows():
    ledger = RouteActionLedger()
    rows = [{**row, "bot_guid": 5} for row in _route_rows(1, 4)]
    assert ledger.observe(rows) == 4
    # A light tail or a drain re-exports rows already counted.
    assert ledger.observe(rows[2:] + [{"bot_guid": 5, "sequence": 9, "action": "cast_spell"}]) == 4
    assert ledger.observe([{**rows[0], "sequence": 10, "timestamp_ms": 99}]) == 5


# Item 4: persistent future-encounter contamination is a typed terminal.

def test_contamination_is_terminal_after_two_consecutive_heartbeats(tmp_path):
    beats = [{"status": _status(node="bwd.omnotron.regroup", generation=1, kind="regroup",
                                kills=0, contamination=True),
              "trace": _trace(_route_rows(index * 5 + 1, 5, node="bwd.omnotron.regroup", generation=1))}
             for index in range(4)]
    commands, output_dir = _run(tmp_path, beats, max_beats=4)
    heartbeats = _heartbeats(output_dir)
    assert len(heartbeats) == 2
    assert heartbeats[0]["completion_reason"] != "future_encounter_contamination_watchdog"
    report = _report(output_dir)
    assert report["completion_reason"] == "future_encounter_contamination_watchdog"
    assert report["failure_reason"] == "validation_route_future_encounter_contamination"
    terminal = report["watchdog_state"]["terminal_failure"]
    assert terminal["consecutive_heartbeats"] == 2 and terminal["first_observed_heartbeat_index"] == 1
    assert "watchdog_failure_is_not_final_evidence" in report["final_evidence_rejections"]
    assert commands[-1] == f".botauto stop {COHORT}"


def test_contamination_that_clears_restarts_the_grace():
    watchdog = ContaminationWatchdog()
    dirty = {"evidence": {"contamination_evidence": [{"route_node_id": "bwd.omnotron.regroup",
                                                      "route_generation": 1}]}}
    clean = {"evidence": {"contamination_evidence": []}}
    assert watchdog.observe(dirty, 1) is None
    assert watchdog.observe(clean, 2) is None
    assert watchdog.observe(dirty, 3) is None
    terminal = watchdog.observe(dirty, 4)
    assert terminal and terminal["first_observed_heartbeat_index"] == 3


# Item 5: repeated near-wipes on one node are a death loop.

OMNOTRON_ALIVE = [1, 8, 9, 9, 3, 5, 10, 10, 10, 3, 10, 5, 1, 10, 9]


def test_omnotron_near_wipes_count_as_death_loop_episodes():
    tracker = NearWipeTracker()
    episodes = [tracker.observe(_status(node="bwd.omnotron.regroup", generation=1, kind="regroup",
                                        kills=0, alive=alive, wipe_generation=0 if index == 0 else 1))
                for index, alive in enumerate(OMNOTRON_ALIVE)]
    assert episodes == [1, 1, 1, 1, 2, 2, 2, 2, 2, 3, 3, 4, 4, 4, 4]
    # Idempotent: the final-timeout path rebuilds the same heartbeat.
    assert tracker.observe(_status(node="bwd.omnotron.regroup", generation=1, kind="regroup",
                                   kills=0, alive=9, wipe_generation=1)) == 4


def test_recovered_trash_deaths_and_partial_deaths_are_not_death_loops():
    tracker = NearWipeTracker()
    # Magmaw batch: partial deaths (8/10) never count.
    for alive in (10, 8, 9, 10, 9, 8, 8, 10):
        assert tracker.observe(_status(node="bwd.magmaw.encounter", generation=4, alive=alive)) == 0
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
    regroup = dict(node="bwd.omnotron.regroup", generation=1, kind="regroup", kills=0)
    beats = [{"status": _status(**regroup, alive=alive),
              "trace": _trace(_route_rows(index * 3 + 1, 3, node="bwd.omnotron.regroup", generation=1))}
             for index, alive in enumerate([1, 8, 3, 10, 3])]
    _commands, output_dir = _run(tmp_path, beats, max_beats=6)
    heartbeats = _heartbeats(output_dir)
    assert [row["progress_counters"]["death_loop_events"] for row in heartbeats] == [1, 1, 2, 2, 3]
    report = _report(output_dir)
    assert report["completion_reason"] == "death_loop_watchdog"
    assert "validation_route_death_loop" in report["failure_labels"]
    assert report["evidence"]["near_wipe_death_loop"]["history"][-1]["alive"] == 3


# Item 6: after a terminal failure the pending trace is drained.

def test_terminal_failure_drains_every_pending_trace_row(tmp_path):
    beats = [{"status": _status(prepull_failed=True), "trace": _trace(_route_rows(1, 39))},
             {"status": _status(prepull_failed=True), "trace": _trace(_route_rows(40, 128), pending=184)}]
    drains = [_trace(_route_rows(168, 128), pending=56), _trace(_route_rows(296, 56), pending=0)]
    commands, output_dir = _run(tmp_path, beats, max_beats=4, drain_traces=drains)
    assert _report(output_dir)["failure_reason"] == PREPULL_LABEL
    trace_calls = [index for index, command in enumerate(commands) if command == TRACE]
    stop = commands.index(f".botauto stop {COHORT}")
    assert len(trace_calls) == 4 and trace_calls[-1] < stop
    with gzip.open(output_dir / TERMINAL_TRACE_DRAIN_FILE, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    assert len(rows) == 184 and rows[-1]["entry"]["sequence"] == 351


def test_terminal_trace_drain_receipt_and_bounds(tmp_path):
    outputs = [json.dumps(_trace(_route_rows(1, 3), pending=5)) for _ in range(10)]
    calls = {"count": 0}
    now = {"t": 0.0}

    def run(_command: str) -> tuple[str, bool]:
        calls["count"] += 1
        now["t"] += 4.0
        return outputs[calls["count"] - 1], True

    receipt = json.loads(drain_terminal_trace(
        run, [".botauto status c0", TRACE], tmp_path, parse_json_objects,
        budget_sec=10.0, clock=lambda: now["t"],
    ))
    assert calls["count"] == 3
    assert receipt["action"] == "harness_cleanup_step"
    assert receipt["purpose"] == "terminal_trace_drain"
    assert receipt["stop_reason"] == "budget_exhausted" and receipt["completed"] is False
    assert receipt["pending_after"] == 5 and receipt["bots_pending"] == [5]
    assert receipt["last_decisions"][0]["sequence"] == 3
    # No delta trace command configured: nothing to drain.
    assert drain_terminal_trace(run, [".botauto status c0"], tmp_path, parse_json_objects) == ""


def test_a_native_clear_does_not_drain(tmp_path):
    beats = [{"status": _status(manifest_complete=True, boss_dead=True),
              "trace": _trace(_route_rows(1, 5), pending=40)}]
    commands, output_dir = _run(tmp_path, beats)
    assert commands.count(TRACE) == 1
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


def test_fall_damage_is_environmental_not_friendly():
    friendly_fire = {**_self_hit(2, "Bwnefnbb", "tank", 300), "spell_id": 3, "spell_name": "Friendly Fire",
                     "target_name": "Bwnefnba"}
    hostile = {**_self_hit(2, "Bwnefnbb", "tank", 1000), "perspective": "damage_done", "spell_id": 7,
               "spell_name": "Strike", "target_entry": 41918, "target_name": "Animated Bone Warrior",
               "first_at_ms": 1_000}
    report = analyze_combat_log({
        "combat_log_schema_version": 8,
        "damage_attribution_schema": "originated_amount_v2_friendly_split",
        "abilities": [_self_hit(1, "Bwnefnba", "tank", 60232), _self_hit(2, "Bwnefnbb", "tank", 61955),
                      friendly_fire, hostile],
        "second_buckets": [
            {"route_generation": 4, "perspective": "friendly_damage_done", "actor_guid": 1,
             "source_is_pet": False, "second": 5, "amount": 60232, "originated_amount": 60232},
            {"route_generation": 4, "perspective": "damage_done", "actor_guid": 2,
             "source_is_pet": False, "second": 1, "amount": 1000, "originated_amount": 1000},
        ],
    })
    encounter = report["encounters"][0]
    actors = {row["actor_name"]: row for row in encounter["actors"]}
    assert actors["Bwnefnba"]["friendly_damage"] == 0
    assert actors["Bwnefnba"]["raw_event_damage"] == 0
    assert actors["Bwnefnba"]["environmental_damage"] == 60232
    assert actors["Bwnefnba"]["friendly_abilities"] == []
    assert actors["Bwnefnbb"]["friendly_damage"] == 300
    assert actors["Bwnefnbb"]["environmental_damage"] == 61955
    assert actors["Bwnefnbb"]["damage"] == 1000
    assert encounter["party_friendly_damage"] == 300
    assert encounter["party_environmental_damage"] == 122187
    # The fall second does not extend the active-combat denominator.
    assert encounter["combat_duration_sec"] == 1

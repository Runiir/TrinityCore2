"""Repeated native encounter resets on one boss node end the run as a typed stall.

Round 6 batch (blackwing_descent_10n-r06-b1-20260926T152851Z), Nefarian c0: on
``bwd.nefarian.encounter`` (route generation 10) ``boss_reset_generation`` rose
from 0 to 26 while ``wipe_generation`` stayed 0: both dragons evaded and
respawned about every three minutes, bots kept hitting things, and the
``route_party_damage`` liveness signal kept the watchdog alive for 79 minutes
until the emergency cap.  Replayed status by status, the tracker fires on the
38th Nefarian status (third unexplained reset) and on no other round-5/6 shard,
Magmaw smoke included; round-5 Maloriak's two wipes (each with its reset) and
recoveries stay unexplained-reset free.
"""
from __future__ import annotations

import inspect
import json
from pathlib import Path

from tools.bot_ml import run_live_bot_validation as harness
from tools.bot_ml.live_validation_terminal_signals import (
    DEFAULT_MAX_ENCOUNTER_RESETS,
    EncounterResetTracker,
)
from tools.bot_ml.run_live_bot_validation import (
    command_script,
    run_transport_completion_watchdog,
    run_worldserver_completion_watchdog,
)

COHORT = "blackwing_descent_10n_nefarian_c0"
NODE = "bwd.nefarian.encounter"
GENERATION = 10


class LoopKeptRunning(Exception):
    pass


def _status(resets: int, *, wipes: int = 0, node: str = NODE, generation: int = GENERATION, kind: str = "boss",
            instance_kind: str = "raid", engaged: bool = True, boss_dead: bool = False,
            manifest_complete: bool = False, kills: int = 4, reset_at_wipe: int | None = None,
            recovery_state: str = "none") -> dict:
    route = {"node_id": node, "generation": generation, "kind": kind, "manifest_complete": manifest_complete}
    scope = {"route_node_id": node, "route_generation": generation}
    if boss_dead:
        route["boss_death_evidence"] = [{**scope, "target_id": 991, "target_entry": 41376, "result": "ok"}]
    if manifest_complete:
        route["terminal_evidence"] = [scope]
    return {
        "ok": True, "action": "botauto_status", "active": True, "cohort_id": COHORT,
        "active_bots": 10, "target_bots": 10, "kills": kills, "deaths": 0, "decisions": 500,
        "validation_route": route,
        "raid_runtime": {
            "instance_kind": instance_kind, "expected_size": 10, "active_size": 10, "alive_size": 10,
            "encounter_in_progress": engaged, "wipe_state": "engaged" if engaged else "ready",
            "wipe_generation": wipes, "recovery_state": recovery_state,
            "boss_reset_generation": resets,
            "boss_reset_generation_at_wipe": max(0, wipes - 1) if reset_at_wipe is None else reset_at_wipe,
        },
    }


# The tracker on the round-5/6 status shapes.

def test_nefarian_evade_loop_is_an_unexplained_reset_loop():
    tracker = EncounterResetTracker(max_resets=3)
    assert [tracker.observe(_status(resets)) for resets in (0, 0, 1, 1, 2, 3)] == [0, 0, 1, 1, 2, 3]
    assert tracker.loop and tracker.receipt()["history"][-1]["unexplained_resets"] == 3


def test_maloriak_wipes_with_recovery_are_explained_resets():
    """Round 5 Maloriak: each wipe reset the boss once; recovery and re-pull followed."""
    tracker = EncounterResetTracker(max_resets=3)
    shape = [(0, 0), (1, 1), (1, 1), (1, 1), (2, 2), (2, 2), (2, 2)]
    assert [tracker.observe(_status(resets, wipes=wipes)) for resets, wipes in shape] == [0] * len(shape)
    assert not tracker.loop


def test_a_wipe_plus_extra_evades_counts_only_the_extras():
    tracker = EncounterResetTracker(max_resets=3)
    for resets, wipes, expected in ((0, 0, 0), (1, 1, 0), (2, 1, 1), (3, 1, 2), (4, 1, 3)):
        assert tracker.observe(_status(resets, wipes=wipes)) == expected
    assert tracker.loop


def _pending(resets: int = 0, wipes: int = 1) -> dict:
    """The first tracked status right after the all-dead edge, before the boss reset sample."""
    return _status(resets, wipes=wipes, reset_at_wipe=resets, engaged=True, recovery_state="awaiting_native_reset")


def test_a_wipe_whose_reset_is_still_pending_at_the_baseline_explains_that_reset():
    for threshold in (1, 3):
        tracker = EncounterResetTracker(max_resets=threshold)
        assert tracker.observe(_pending()) == 0
        assert tracker.receipt()["pending_wipe_reset_at_baseline"] is True
        # The wipe's native reset arrives on the next heartbeat.
        assert tracker.observe(_status(1, wipes=1, reset_at_wipe=0, engaged=False)) == 0
        assert not tracker.loop
    # Later evades are still counted, from the first unexplained one.
    tracker = EncounterResetTracker(max_resets=3)
    tracker.observe(_pending())
    counts = [tracker.observe(_status(r, wipes=1, reset_at_wipe=0)) for r in (1, 2, 3, 4)]
    assert counts == [0, 1, 2, 3] and tracker.loop


def test_an_already_accounted_wipe_reset_and_older_wipes_get_no_credit():
    # The latest wipe's reset already arrived (reset 4 > at-wipe 3): no pending pairing.
    tracker = EncounterResetTracker(max_resets=1)
    assert tracker.observe(_status(4, wipes=2, reset_at_wipe=3)) == 0
    assert tracker.receipt()["pending_wipe_reset_at_baseline"] is False
    assert tracker.observe(_status(5, wipes=2, reset_at_wipe=3)) == 1 and tracker.loop
    # A pending latest wipe credits one reset, never one per historical wipe.
    tracker = EncounterResetTracker(max_resets=3)
    assert tracker.observe(_pending(resets=4, wipes=5)) == 0
    assert [tracker.observe(_status(r, wipes=5, reset_at_wipe=4)) for r in (5, 6, 7, 8)] == [0, 1, 2, 3]


def test_scope_kill_and_kind_rules():
    tracker = EncounterResetTracker(max_resets=3)
    # Resets carried in from an earlier node are the baseline, not a loop here.
    assert tracker.observe(_status(5, node="bwd.nefarian.descent", generation=9, kind="transport")) == 0
    assert tracker.observe(_status(5)) == 0
    assert tracker.observe(_status(7)) == 2
    # A boss kill on the node settles it.
    assert tracker.observe(_status(9, boss_dead=True)) == 0 and not tracker.loop
    # Dungeons (Stonecore) and non-boss nodes are never tracked.
    dungeon = EncounterResetTracker(max_resets=3)
    assert [dungeon.observe(_status(r, instance_kind="dungeon")) for r in range(6)] == [0] * 6
    trash = EncounterResetTracker(max_resets=3)
    assert [trash.observe(_status(r, kind="trash")) for r in range(6)] == [0] * 6
    disabled = EncounterResetTracker()
    assert [disabled.observe(_status(r)) for r in range(6)] == [0] * 6 and not disabled.loop


# The completion watchdog.

def _diagnose(damage: int) -> dict:
    return {"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1, "bots": [],
            "combat_metrics": {"schema": "bot_combat_metrics_v3", "measurement_basis": "hostile_originated_damage",
                               "available": True, "route_node_id": NODE, "route_generation": GENERATION,
                               "party_damage": damage}}


def _run(tmp_path: Path, statuses: list[dict], **kwargs) -> tuple[list[str], Path]:
    commands: list[str] = []
    state = {"beat": 0}

    def execute(command: str, _timeout: int) -> tuple[str, int, bool]:
        commands.append(command)
        beat = min(state["beat"], len(statuses)) - 1
        if command.startswith(".botauto status"):
            payload = statuses[beat]
        elif command.startswith(".botauto diagnose"):
            # Party damage keeps rising across every reset.
            payload = _diagnose(100_000 * (beat + 1))
        elif command.startswith(".botauto trace"):
            payload = {"ok": True, "action": "botauto_trace", "trace_schema_version": 1, "bots": []}
        else:
            payload = {"ok": True, "action": "botauto_" + command.split()[1], "cohort_id": COHORT}
        return json.dumps(payload) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        state["beat"] += 1
        if state["beat"] > len(statuses):
            raise LoopKeptRunning

    manifest = {"schema": "bot_live_validation_route_manifest_v1",
                "routes": [{"route_node_id": NODE, "route_generation": GENERATION, "kind": "boss"}]}
    output_dir = tmp_path / "run"
    try:
        run_transport_completion_watchdog(
            execute, ["attached"], None,
            command_script(selector="all", trace_limit=128, start=False, stop=True, exit_server=False,
                           cohort_id=COHORT, trace_delta=True),
            output_dir, {}, {"scenario_id": "blackwing_descent_10n_nefarian_c0_diagnostic"},
            validation_route_manifest=manifest, heartbeat_sec=1, no_progress_window_sec=600,
            status_command=f".botauto status {COHORT}", sleep=sleep, **kwargs,
        )
    except LoopKeptRunning:
        pass
    return commands, output_dir


def _heartbeats(output_dir: Path) -> list[dict]:
    return [json.loads(line) for line in (output_dir / "heartbeat_events.jsonl").read_text().splitlines()]


def test_the_round6_nefarian_shape_ends_as_an_encounter_reset_loop(tmp_path):
    resets = [0, 0, 1, 1, 2, 2, 3, 3, 4, 4]
    commands, output_dir = _run(tmp_path, [_status(value) for value in resets])
    heartbeats = _heartbeats(output_dir)
    assert len(heartbeats) == 7  # the heartbeat whose status carries the third reset
    assert [row["progress_counters"]["encounter_resets_unexplained"] for row in heartbeats] == resets[:7]
    report = json.loads((output_dir / "report.json").read_text())
    assert report["completion_reason"] == "encounter_reset_loop_watchdog"
    assert "encounter_reset_loop" in report["failure_labels"]
    assert report["watchdog_state"]["encounter_reset_loop"] is True
    assert report["acceptable_final_evidence"] is False
    assert "failure_labels_present" in report["final_evidence_rejections"]
    assert report["native_gameplay_outcome"]["status"] == "stalled"
    assert report["evidence"]["encounter_reset_loop_receipt"]["unexplained_resets"] == 3
    assert commands[-1] == f".botauto stop {COHORT}"


def test_party_damage_into_a_pull_that_reset_is_not_progress(tmp_path):
    _commands, output_dir = _run(tmp_path, [_status(value) for value in (0, 0, 1, 1)], max_encounter_resets=9)
    liveness = [row["semantic_liveness"] for row in _heartbeats(output_dir)]
    # Damage rose on every heartbeat (100k, 200k, 300k, 400k); the heartbeat
    # that carries the reset (3) does not advance the liveness clock.
    assert [row["last_progress_value"] for row in liveness] == [4, 200_000, 200_000, 400_000]


def test_legitimate_wipes_with_recovery_and_a_kill_still_clear(tmp_path):
    shape = [_status(0), _status(1, wipes=1, engaged=False), _status(1, wipes=1), _status(2, wipes=2, engaged=False),
             _status(2, wipes=2), _status(2, wipes=2, engaged=False, boss_dead=True, manifest_complete=True, kills=5)]
    _commands, output_dir = _run(tmp_path, shape)
    report = json.loads((output_dir / "report.json").read_text())
    assert report["completion_reason"] == "validation_route_manifest_complete"
    assert "encounter_reset_loop" not in report["failure_labels"]


def test_transport_watchdog_explains_a_pending_wipe_reset_at_thresholds_1_and_3(tmp_path):
    for threshold in (1, 3):
        statuses = [_pending(), _status(1, wipes=1, reset_at_wipe=0, engaged=False),
                    _status(1, wipes=1, reset_at_wipe=0, engaged=False), _status(1, wipes=1, reset_at_wipe=0)]
        _commands, output_dir = _run(tmp_path / str(threshold), statuses, max_encounter_resets=threshold)
        heartbeats = _heartbeats(output_dir)
        assert len(heartbeats) == 4
        assert [row["progress_counters"]["encounter_resets_unexplained"] for row in heartbeats] == [0, 0, 0, 0]
        report = json.loads((output_dir / "report.json").read_text())
        assert report["completion_reason"] != "encounter_reset_loop_watchdog"
        assert "encounter_reset_loop" not in report["failure_labels"]


def test_the_threshold_is_configurable_and_zero_disables_it(tmp_path):
    resets = [0, 1, 2, 3, 4, 5]
    _commands, output_dir = _run(tmp_path / "five", [_status(value) for value in resets], max_encounter_resets=5)
    assert len(_heartbeats(output_dir)) == 6
    assert json.loads((output_dir / "report.json").read_text())["completion_reason"] == "encounter_reset_loop_watchdog"
    _commands, output_dir = _run(tmp_path / "off", [_status(value) for value in resets], max_encounter_resets=0)
    report = json.loads((output_dir / "report.json").read_text())
    assert report["completion_reason"] != "encounter_reset_loop_watchdog" and len(_heartbeats(output_dir)) == 6
    assert report["evidence"]["encounter_reset_loop_receipt"] == {}


def test_accepted_single_cohort_paths_are_opt_in():
    """bot-live-validate (legacy Magmaw, Stonecore) keeps its outcomes; the shard coordinator uses 3."""
    assert inspect.signature(run_worldserver_completion_watchdog).parameters["max_encounter_resets"].default == 0
    assert (inspect.signature(run_transport_completion_watchdog).parameters["max_encounter_resets"].default
            == DEFAULT_MAX_ENCOUNTER_RESETS == 3)
    main_source = inspect.getsource(harness._main)
    assert '"--max-encounter-resets"' in main_source and "default=0" in main_source.split('"--max-encounter-resets"')[1][:80]

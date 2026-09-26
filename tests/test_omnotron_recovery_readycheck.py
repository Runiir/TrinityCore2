"""A wiped Omnotron shard must get the leader's native ready check.

Round 3 batch 1 (blackwing_descent_10n-r03-b1-20260925T200656Z, Omnotron c0):
after the native full wipe every member released, ran back, re-entered and was
resurrected at the instance entrance (-345.872, -224.344, 193.127); the boss
reset (boss_reset_generation 1 > 0) and the hostile reset were observed. The
only missing evidence was the native ready check, so
SuppressNativeRaidRecovery held every bot (no decision tick for 346-371 s)
while tools.raid_program.capture_progress.ready_for_native_readycheck held on
11 consecutive status heartbeats (worldserver.console.log lines 1844-3708).
The shard coordinator's completion watchdog never sent `.botauto readycheck`
(0 occurrences in the console log), and its transport refused the verb.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tools.bot_ml.live_validation_native_readycheck import (
    NativeReadyCheckRequester,
    readycheck_request_identity,
)
from tools.bot_ml.run_live_bot_validation import command_script, run_transport_completion_watchdog
from tools.raid_program import shard_coordinator as sc
from tools.raid_program.capture_progress import ready_for_native_readycheck

COHORT = "blackwing_descent_10n_omnotron_c0"
NODE = "bwd.omnotron.encounter"
GENERATION = 3
READYCHECK = f".botauto readycheck {COHORT}"


def _status(phase: str, *, wipe_generation: int = 1, alive: int = 10) -> dict:
    """Status payloads shaped like the round-3 Omnotron c0 heartbeats."""
    engaged = phase == "engaged"
    recovered = phase in ("evidence_pending", "ready_check_done")
    native = {
        "death_observed": phase != "engaged",
        "corpse_observed": phase != "engaged",
        "release_observed": recovered,
        "runback_observed": recovered,
        "resurrection_observed": recovered,
        "ready_check_action_observed": phase == "ready_check_done",
        "evidence_complete": phase == "ready_check_done",
    }
    runtime = {
        "instance_kind": "raid", "expected_size": 10, "alive_size": alive if phase != "wiped" else 0,
        "attempt_id": 1, "assignment_generation": 1,
        "wipe_generation": 0 if engaged else wipe_generation,
        "wipe_state": "engaged" if engaged else "wiped",
        "recovery_state": "none" if engaged else "recovery_evidence_pending",
        "encounter_in_progress": engaged, "encounter_phase": "combat" if engaged else "recovery",
        "native_recovery_hold_active": not engaged,
        "native_recovery_route_generation": 0 if engaged else GENERATION,
        "native_recovery_node_id": "" if engaged else NODE,
        "boss_reset_generation": 0 if engaged else wipe_generation,
        "boss_reset_generation_at_wipe": 0 if engaged else wipe_generation - 1,
        "native_hostile_activity_active": engaged,
        "native_hostile_inactivity_observed": not engaged,
        "native_hostile_reset_generation": 0 if engaged else wipe_generation,
        "native_hostile_reset_generation_at_wipe": 0 if engaged else wipe_generation - 1,
        "native_hostile_observation_attempt_id": 1,
        "native_hostile_observation_route_generation": GENERATION,
        "native_hostile_observation_node_id": NODE,
        "native_recovery": native,
    }
    return {
        "ok": True, "action": "botauto_status", "active": True, "cohort_id": COHORT,
        "active_bots": 10, "target_bots": 10, "kills": 2, "deaths": 0, "decisions": 500,
        "validation_route": {"node_id": NODE, "generation": GENERATION, "kind": "boss",
                             "manifest_complete": False},
        "raid_runtime": runtime,
    }


def test_round3_final_status_satisfies_the_native_readycheck_predicate() -> None:
    assert ready_for_native_readycheck(_status("evidence_pending"))
    for phase in ("engaged", "wiped", "ready_check_done"):
        assert not ready_for_native_readycheck(_status(phase))


def test_requester_sends_one_readycheck_per_recovery_scope() -> None:
    requester = NativeReadyCheckRequester(COHORT)
    assert requester.command == READYCHECK
    assert requester.due([_status("engaged")]) == ""
    assert requester.due([_status("wiped")]) == ""
    assert requester.due([{"note": 1}, _status("evidence_pending")]) == READYCHECK
    # The same wipe's later heartbeats do not repeat the request.
    assert requester.due([_status("evidence_pending")]) == ""
    assert requester.due([_status("ready_check_done")]) == ""
    # A second wipe of the same node is a new recovery scope.
    assert requester.due([_status("evidence_pending", wipe_generation=2)]) == READYCHECK
    assert requester.requests == [
        readycheck_request_identity(_status("evidence_pending")),
        readycheck_request_identity(_status("evidence_pending", wipe_generation=2)),
    ]


def test_requester_ignores_other_cohorts_and_failed_status() -> None:
    requester = NativeReadyCheckRequester(COHORT)
    foreign = {**_status("evidence_pending"), "cohort_id": "blackwing_descent_10n_maloriak_c0"}
    failed = {**_status("evidence_pending"), "ok": False}
    assert requester.due([foreign, failed]) == ""
    assert NativeReadyCheckRequester("default").command == ".botauto readycheck"


class _LoopKeptRunning(Exception):
    pass


def test_transport_watchdog_sends_the_readycheck_after_the_status_that_allows_it(tmp_path: Path) -> None:
    beats = ["engaged", "engaged", "wiped", "evidence_pending", "evidence_pending", "evidence_pending"]
    commands: list[str] = []
    phases: list[str] = []
    state = {"beat": 0}

    def execute(command: str, _timeout: int) -> tuple[str, int, bool]:
        commands.append(command)
        phase = beats[min(state["beat"], len(beats) - 1)]
        phases.append(phase)
        if command.startswith(".botauto status"):
            payload = _status(phase)
        elif command.startswith(".botauto readycheck"):
            payload = {"ok": True, "action": "botauto_readycheck", "cohort_id": COHORT,
                       "ready_check_pending": True, "ready_check_complete": False}
        elif command.startswith(".botauto diagnose"):
            payload = {"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1, "bots": []}
        elif command.startswith(".botauto trace"):
            payload = {"ok": True, "action": "botauto_trace", "trace_schema_version": 1, "bots": []}
        else:
            payload = {"ok": True, "action": "botauto_" + command.split()[1]}
        return json.dumps(payload) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        state["beat"] += 1
        if state["beat"] >= len(beats):
            raise _LoopKeptRunning

    manifest = {"schema": "bot_live_validation_route_manifest_v1",
                "routes": [{"route_node_id": NODE, "route_generation": GENERATION, "kind": "boss"}]}
    with pytest.raises(_LoopKeptRunning):
        run_transport_completion_watchdog(
            execute, ["attached"], None,
            command_script(selector="all", trace_limit=128, start=False, stop=True,
                           exit_server=False, cohort_id=COHORT, trace_delta=True),
            tmp_path / "run", {}, {"scenario_id": "blackwing_descent_10n_omnotron_c0_diagnostic"},
            validation_route_manifest=manifest, heartbeat_sec=1, no_progress_window_sec=600,
            status_command=f".botauto status {COHORT}", sleep=sleep,
        )
    assert commands.count(READYCHECK) == 1
    index = commands.index(READYCHECK)
    statuses = [i for i, c in enumerate(commands) if c.startswith(".botauto status")]
    # Sent once, right after the first status with complete native evidence,
    # and never while engaged or before the release/runback/resurrection.
    first_ready = next(i for i in statuses if phases[i] == "evidence_pending")
    assert index == first_ready + 1
    assert [phases[i] for i in statuses if i < index] == ["engaged", "wiped", "evidence_pending"]
    assert len([i for i in statuses if i > index]) >= 2  # later heartbeats do not repeat it


def test_shard_transport_accepts_the_addressed_readycheck(tmp_path: Path) -> None:
    assert "readycheck" in sc.SHARD_VERBS

    class Console:
        def __init__(self) -> None:
            self.sent: list[str] = []

        def __call__(self, command: str, timeout_sec: int, *, owner: str = "") -> tuple[str, int, bool]:
            self.sent.append(command)
            reply = {"ok": True, "action": "botauto_readycheck", "cohort_id": COHORT}
            return json.dumps(reply) + "\n", 0, False

    class Spec:
        cohort_id = COHORT
        profile = "blackwing_descent_10n_omnotron_c0_diagnostic"

    console = Console()
    transport = sc.ShardTransport(console, Spec(), tmp_path)  # type: ignore[arg-type]
    output, code, timed_out = transport(READYCHECK, 5)
    assert (code, timed_out) == (0, False) and console.sent == [READYCHECK]
    assert json.loads(output.strip())["action"] == "botauto_readycheck"
    assert transport(".botauto readycheck blackwing_descent_10n_maloriak_c0", 5) == ("", 1, False)
    assert transport.refused_commands == 1

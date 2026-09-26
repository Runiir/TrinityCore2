"""The completion watchdogs' native wipe-recovery ready check (round-4 review fixes).

Covers what tests/test_omnotron_recovery_readycheck.py (the round-3 Omnotron
shape) does not: the predicate for any raid size, a refused reply re-arming the
same scope (one retry per heartbeat, bounded per scope), a SOAP refusal that is
not a transport failure, the end-of-heartbeat send order, the world-tick read of
the status reply, receipts in watchdog_state, and the opt-in process path.
"""
from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path

import pytest

from tools.bot_ml import run_live_bot_validation as harness
from tools.bot_ml.live_validation_native_readycheck import (
    MAX_REQUESTS_PER_SCOPE,
    NativeReadyCheckRequester,
    ready_for_native_readycheck,
)
from tools.bot_ml.run_live_bot_validation import (
    command_script,
    run_transport_completion_watchdog,
    run_worldserver_completion_watchdog,
)
from tools.raid_program import shard_coordinator as sc

COHORT = "blackwing_descent_25n_omnotron_c0"
NODE = "bwd.omnotron.encounter"
GENERATION = 3
READYCHECK = f".botauto readycheck {COHORT}"
MANIFEST = {"schema": "bot_live_validation_route_manifest_v1",
            "routes": [{"route_node_id": NODE, "route_generation": GENERATION, "kind": "boss"}]}


class LoopKeptRunning(Exception):
    """The scripted heartbeats ran out while the watchdog was still running."""


def _status(*, size: int = 25, active: int | None = None, alive: int | None = None, wipe_generation: int = 1,
            ready: bool = True, tick: int = 0) -> dict:
    """A status after a native full wipe whose recovery evidence lacks only the ready check."""
    runtime = {
        "instance_kind": "raid", "expected_size": size,
        "active_size": size if active is None else active,
        "alive_size": size if alive is None else alive, "roster_complete": True,
        "attempt_id": 1, "assignment_generation": 1, "wipe_generation": wipe_generation,
        "wipe_state": "wiped", "recovery_state": "recovery_evidence_pending",
        "encounter_in_progress": False, "encounter_phase": "recovery",
        "native_recovery_hold_active": True, "native_recovery_route_generation": GENERATION,
        "native_recovery_node_id": NODE,
        "boss_reset_generation": wipe_generation, "boss_reset_generation_at_wipe": wipe_generation - 1,
        "native_hostile_activity_active": False,
        "native_recovery": {
            "death_observed": True, "corpse_observed": True, "release_observed": True,
            "runback_observed": True, "resurrection_observed": True,
            "ready_check_action_observed": not ready, "evidence_complete": not ready,
        },
    }
    return {
        "ok": True, "action": "botauto_status", "active": True, "cohort_id": COHORT,
        "active_bots": size, "target_bots": size, "kills": 2, "deaths": 0, "decisions": 500,
        "validation_route": {"node_id": NODE, "generation": GENERATION, "kind": "boss", "manifest_complete": False},
        "raid_runtime": runtime,
        "world_update": {"schema": "bot_world_update_ticks_v1", "first_update_at_ms": 1, "now_ms": 1_000 + tick,
                         "stall_count": 0, "stalls": []},
    }


def _refused(reason: str = "native_recovery_hostile_activity") -> dict:
    return {"ok": False, "action": "botauto_readycheck", "cohort_id": COHORT, "failure_reason": reason,
            "ready_check_action_generation": 0}


ACCEPTED = {"ok": True, "action": "botauto_readycheck", "cohort_id": COHORT, "ready_check_pending": True,
            "ready_check_complete": False, "ready_check_action_generation": 1}


def _run(tmp_path: Path, *, beats: int, readycheck_replies: list, status=None, diagnose=None,
         **kwargs) -> tuple[list[str], Path, int, bool]:
    """Run the transport watchdog; ``readycheck_replies`` are (payload|text, returncode, timed_out)."""
    commands: list[str] = []
    replies = list(readycheck_replies)
    state = {"beat": 0}

    def execute(command: str, _timeout: int) -> tuple[str, int, bool]:
        commands.append(command)
        if command.startswith(".botauto status"):
            payload = (status or (lambda _beat: _status(tick=len(commands))))(state["beat"])
        elif command.startswith(".botauto readycheck"):
            reply, code, timed_out = replies.pop(0) if replies else (ACCEPTED, 0, False)
            return (reply if isinstance(reply, str) else json.dumps(reply)) + "\n", code, timed_out
        elif command.startswith(".botauto diagnose"):
            payload = diagnose or {"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1, "bots": []}
        elif command.startswith(".botauto trace"):
            payload = {"ok": True, "action": "botauto_trace", "trace_schema_version": 1, "bots": []}
        else:
            payload = {"ok": True, "action": "botauto_" + command.split()[1], "cohort_id": COHORT}
        return json.dumps(payload) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        state["beat"] += 1
        if state["beat"] > beats:
            raise LoopKeptRunning

    output_dir = tmp_path / "run"
    returncode, timed_out = 0, False
    try:
        _output, returncode, timed_out, _command = run_transport_completion_watchdog(
            execute, ["attached"], None,
            command_script(selector="all", trace_limit=128, start=False, stop=True,
                           exit_server=False, cohort_id=COHORT, trace_delta=True),
            output_dir, {}, {"scenario_id": "blackwing_descent_25n_omnotron_c0_diagnostic"},
            validation_route_manifest=MANIFEST, heartbeat_sec=1, no_progress_window_sec=600,
            status_command=f".botauto status {COHORT}", sleep=sleep, **kwargs,
        )
    except LoopKeptRunning:
        returncode = -1
    return commands, output_dir, returncode, timed_out


def _receipt(output_dir: Path) -> dict:
    return json.loads((output_dir / "latest.json").read_text())["watchdog_state"]["native_readycheck"]


# Item 4: any raid size, mirroring RequestNativeRaidReadyCheckForCohort.

def test_the_predicate_holds_for_a_25_man_raid_and_mirrors_the_native_roster_gate():
    assert ready_for_native_readycheck(_status(size=25))
    assert ready_for_native_readycheck(_status(size=10))
    assert not ready_for_native_readycheck(_status(size=25, alive=24))
    assert not ready_for_native_readycheck(_status(size=25, active=24, alive=24))
    assert not ready_for_native_readycheck(_status(size=0, active=0, alive=0))
    assert not ready_for_native_readycheck(_status(ready=False))
    missing = _status()
    del missing["raid_runtime"]["active_size"]
    assert not ready_for_native_readycheck(missing)
    incomplete = _status()
    incomplete["raid_runtime"]["roster_complete"] = False
    assert not ready_for_native_readycheck(incomplete)


def test_a_25_man_wiped_shard_gets_its_readycheck(tmp_path):
    commands, output_dir, _code, _timed_out = _run(tmp_path, beats=3, readycheck_replies=[(ACCEPTED, 0, False)])
    assert commands.count(READYCHECK) == 1
    requests = _receipt(output_dir)["requests"]
    assert [row["outcome"] for row in requests] == ["accepted"]
    assert requests[0]["scope"] == {"attempt_id": 1, "wipe_generation": 1, "assignment_generation": 1,
                                    "route_generation": GENERATION, "route_node_id": NODE}


# Item 1: a refused reply re-arms the same scope, one retry per heartbeat, bounded per scope.

def test_a_refused_readycheck_is_retried_on_the_next_heartbeat_until_accepted(tmp_path):
    replies = [(_refused(), 0, False), (_refused("all_raid_members_must_be_alive"), 0, False), (ACCEPTED, 0, False)]
    commands, output_dir, _code, _timed_out = _run(tmp_path, beats=5, readycheck_replies=replies)
    assert commands.count(READYCHECK) == 3
    # One request per heartbeat: every ready check follows a different status.
    statuses = [index for index, command in enumerate(commands) if command.startswith(".botauto status")]
    sent = [index for index, command in enumerate(commands) if command == READYCHECK]
    assert [sum(1 for index in statuses if index < position) for position in sent] == [1, 2, 3]
    receipt = _receipt(output_dir)
    assert [(row["outcome"], row["failure_reason"], row["request"], row["rearmed"]) for row in receipt["requests"]] == [
        ("refused", "native_recovery_hostile_activity", 1, True),
        ("refused", "all_raid_members_must_be_alive", 2, True),
        ("accepted", "", 3, False),
    ]
    assert receipt["scopes"][0]["accepted"] is True and receipt["scopes"][0]["exhausted"] is False


def test_retries_are_bounded_per_scope_and_a_new_wipe_is_a_new_scope(tmp_path):
    beat_status = lambda beat: _status(wipe_generation=1 if beat <= 5 else 2, tick=beat)  # noqa: E731
    commands, output_dir, _code, _timed_out = _run(
        tmp_path, beats=7, status=beat_status,
        readycheck_replies=[(_refused(), 0, False)] * MAX_REQUESTS_PER_SCOPE + [(ACCEPTED, 0, False)])
    assert commands.count(READYCHECK) == MAX_REQUESTS_PER_SCOPE + 1
    scopes = {scope["scope"]["wipe_generation"]: scope for scope in _receipt(output_dir)["scopes"]}
    assert scopes[1]["requests"] == MAX_REQUESTS_PER_SCOPE and scopes[1]["exhausted"] is True
    assert scopes[2]["requests"] == 1 and scopes[2]["accepted"] is True


# Item 2: a refusal is not a transport failure; a timeout or a lost transport is.

SOAP_FAULT = (
    '<?xml version="1.0" encoding="UTF-8"?><SOAP-ENV:Envelope><SOAP-ENV:Body><SOAP-ENV:Fault>'
    "<faultcode>SOAP-ENV:Client</faultcode><faultstring>"
    + json.dumps(_refused()).replace('"', "&quot;")
    + "</faultstring></SOAP-ENV:Fault></SOAP-ENV:Body></SOAP-ENV:Envelope>"
)


@pytest.mark.parametrize("reply", [json.dumps(_refused()), SOAP_FAULT, "<html>500</html>"],
                         ids=["json_500", "soap_fault_500", "unparsed_500"])
def test_a_soap_refusal_re_arms_and_never_ends_the_watchdog(tmp_path, reply):
    commands, output_dir, returncode, timed_out = _run(
        tmp_path, beats=3, readycheck_replies=[(reply, 500, False), (ACCEPTED, 0, False)])
    assert returncode == -1 and timed_out is False  # still running: no transport failure
    assert commands.count(READYCHECK) == 2
    first = _receipt(output_dir)["requests"][0]
    assert first["outcome"] in {"refused", "refused_unparsed"} and first["returncode"] == 500
    assert first["propagate"] is False and first["rearmed"] is True


@pytest.mark.parametrize(("code", "timed_out"), [(1, False), (124, True)], ids=["lost", "timeout"])
def test_a_lost_or_timed_out_transport_still_ends_the_watchdog(tmp_path, code, timed_out):
    commands, _output_dir, returncode, watchdog_timed_out = _run(
        tmp_path, beats=3, readycheck_replies=[("", code, timed_out)])
    assert returncode == code and watchdog_timed_out is timed_out
    assert commands.count(READYCHECK) == 1
    assert commands[-1] == f".botauto stop {COHORT}"


# Items 3 and 5: send order and world ticks.

def test_no_readycheck_is_sent_on_a_heartbeat_that_ends_the_run(tmp_path):
    error = {"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1,
             "bots": [{"diagnosis": {"diagnosis_code": "blocked_no_fallback", "severity": "error"}}]}
    commands, output_dir, returncode, _timed_out = _run(tmp_path, beats=3, readycheck_replies=[], diagnose=error)
    report = json.loads((output_dir / "report.json").read_text())
    assert returncode == 0 and report["completion_reason"] == "machine_failure_predicate"
    assert READYCHECK not in commands
    assert report["watchdog_state"]["native_readycheck"]["requests"] == []


def test_the_readycheck_is_the_last_command_of_its_heartbeat_and_ticks_read_every_status(tmp_path):
    commands, output_dir, _code, _timed_out = _run(
        tmp_path, beats=3, readycheck_replies=[(_refused(), 0, False), (_refused(), 0, False)])
    for index, command in enumerate(commands):
        if command == READYCHECK:
            assert commands[index - 1] == f".botauto trace {COHORT} all 128 delta"
    statuses = sum(1 for command in commands if command.startswith(".botauto status"))
    ticks = json.loads((output_dir / "world_update_ticks.json").read_text())
    assert ticks["reads"] == statuses


# Item 6: the process path is opt-in; the raid program's shard coordinator opts in.

FAKE_WORLDSERVER = """#!/usr/bin/env python3
import json, sys
log = open(sys.argv[2] + ".log", "a", encoding="utf-8")
status = json.loads(open(sys.argv[2], encoding="utf-8").read())
print("TC> ", flush=True)
for line in sys.stdin:
    cmd = line.strip()
    log.write(cmd + "\\n"); log.flush()
    if cmd.startswith(".botauto status"):
        print(json.dumps(status))
    elif cmd.startswith(".botauto readycheck"):
        print(json.dumps({"ok": True, "action": "botauto_readycheck", "cohort_id": status["cohort_id"]}))
    elif cmd.startswith(".botauto diagnose"):
        print('{"ok":true,"action":"botauto_diagnose","diagnosis_schema_version":1,"bots":[]}')
    elif cmd.startswith(".botauto trace"):
        print('{"ok":true,"action":"botauto_trace","trace_schema_version":1,"entries":[]}')
    elif cmd.startswith(".botauto combatlog"):
        print('{"ok":true,"action":"botauto_combatlog_complete","events":[]}')
    elif cmd.startswith(".botauto stop"):
        print('{"ok":true,"action":"botauto_stop"}')
    elif cmd.startswith("server shutdown"):
        break
    print("TC> ", flush=True)
"""


@pytest.mark.parametrize("enabled", [False, True], ids=["default_off", "opt_in"])
def test_the_process_watchdog_sends_the_readycheck_only_when_opted_in(tmp_path, enabled):
    binary = tmp_path / "fake_worldserver.py"
    binary.write_text(f"#!{sys.executable}\n" + FAKE_WORLDSERVER.split("\n", 1)[1], encoding="utf-8")
    binary.chmod(0o755)
    config = tmp_path / "status.json"
    # A 10-man status: the accepted single-cohort shape that must not change by default.
    config.write_text(json.dumps(_status(size=10)), encoding="utf-8")
    kwargs = {"native_readycheck": True} if enabled else {}
    run_worldserver_completion_watchdog(
        binary, config, 3, command_script(selector="all", trace_limit=5, start=False, stop=True,
                                          cohort_id=COHORT),
        tmp_path / "run", {}, {}, heartbeat_sec=1, no_progress_window_sec=600, **kwargs,
    )
    commands = (tmp_path / "status.json.log").read_text(encoding="utf-8").splitlines()
    assert (READYCHECK in commands) is enabled
    if enabled:
        assert commands.count(READYCHECK) == 1  # accepted: one request for the scope


def test_opt_in_defaults_and_the_shard_coordinator_opts_in():
    assert inspect.signature(run_worldserver_completion_watchdog).parameters["native_readycheck"].default is False
    assert inspect.signature(run_transport_completion_watchdog).parameters["native_readycheck"].default is True
    main_source = inspect.getsource(harness._main)
    assert '"--native-readycheck"' in main_source and 'action="store_true"' in main_source
    assert "native_readycheck=True" in inspect.getsource(sc.ShardCoordinator.run_one)
    assert "readycheck" in sc.SHARD_VERBS


def test_a_requester_without_a_reply_never_resends_the_scope():
    requester = NativeReadyCheckRequester(COHORT)
    assert requester.due([_status()], 1) == READYCHECK and requester.take() == READYCHECK
    assert requester.due([_status()], 2) == ""  # awaiting its reply
    assert requester.record_reply("", heartbeat_index=2)["outcome"] == "no_reply"
    assert requester.due([_status()], 3) == READYCHECK  # a missing reply is a refusal

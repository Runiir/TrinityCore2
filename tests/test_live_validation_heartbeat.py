"""In-combat heartbeats stay light; out-of-combat heartbeats stay full."""
from __future__ import annotations

import gzip
import json

import pytest

from tools.bot_ml import live_validation_heartbeat as heartbeat
from tools.bot_ml.run_live_bot_validation import (
    command_script,
    heartbeat_commands_from_script,
    parse_json_objects,
    run_transport_completion_watchdog,
    run_worldserver_completion_watchdog,
)

FULL_TRACE = ".botauto trace all 128 delta"


def status(**runtime) -> dict:
    route = runtime.pop("route", {"kind": "trash", "node_id": "bwd.magmaw.drudges"})
    return {
        "ok": True,
        "action": "botauto_status",
        "active": True,
        "bots": 10,
        "active_bots": 10,
        "target_bots": 10,
        "decisions": 5,
        "kills": 1,
        "validation_route": route,
        "raid_runtime": {
            "active": True,
            "instance_kind": "raid",
            "wipe_state": "ready",
            "recovery_state": "none",
            **runtime,
        },
    }


@pytest.mark.parametrize(
    "runtime,reasons",
    [
        ({"native_hostile_activity_active": True}, ["native_hostile_activity_active"]),
        ({"encounter_in_progress": True, "wipe_state": "engaged"}, ["encounter_in_progress", "wipe_state_engaged", "boss_route_node_open"]),
        ({"route": {"kind": "boss", "manifest_complete": False}}, ["boss_route_node_open"]),
        ({"route": {"kind": "boss", "manifest_complete": True}}, []),
        ({"route": {"kind": "boss"}, "wipe_state": "wiped", "recovery_state": "release_resurrection_pending"}, []),
        ({}, []),
    ],
)
def test_combat_activity_classification(runtime, reasons):
    payload = status(**runtime)
    if "encounter_in_progress" in runtime:
        payload["validation_route"] = {"kind": "boss", "manifest_complete": False}
    activity = heartbeat.combat_activity(payload)
    assert activity["reasons"] == reasons
    assert activity["active"] is bool(reasons)


def test_light_trace_command_is_a_small_non_delta_tail():
    assert heartbeat.light_trace_command(FULL_TRACE) == ".botauto trace all 8"
    assert heartbeat.light_trace_command(".botauto trace cohort-a all 128 delta", 4) == ".botauto trace cohort-a all 4"
    assert heartbeat.light_trace_command(".botauto trace all 5 delta") == ".botauto trace all 5"
    assert heartbeat.light_trace_command(".botauto diagnose all") == ".botauto diagnose all"


def test_planner_escalates_to_full_when_a_stall_is_suspected():
    planner = heartbeat.HeartbeatPlanner([".botauto status", FULL_TRACE], 180, parse_json_objects)
    combat = json.dumps(status(native_hostile_activity_active=True))
    planner.begin({"semantic_liveness": {"elapsed_no_progress_sec": 30}})
    planner.observe(".botauto status", combat)
    assert planner.mode == "light"
    assert planner.effective_command(FULL_TRACE) == ".botauto trace all 8"
    planner.begin({"semantic_liveness": {"elapsed_no_progress_sec": 95}})
    planner.observe(".botauto status", combat)
    assert planner.mode == "full"
    assert planner.reasons == ["semantic_no_progress_half_window"]
    assert planner.effective_command(FULL_TRACE) == FULL_TRACE
    planner.begin({"progress_counters": {"validation_route_no_progress_diagnoses": 1}})
    planner.observe(".botauto status", combat)
    assert planner.mode == "full"
    disabled = heartbeat.HeartbeatPlanner([FULL_TRACE], 180, parse_json_objects, enabled=False)
    disabled.begin(None)
    disabled.observe(".botauto status", combat)
    assert disabled.effective_command(FULL_TRACE) == FULL_TRACE


def _responses(in_combat: list[bool]):
    """Return a responder that reports combat for the Nth status query."""
    state = {"status_calls": 0}

    def respond(command: str) -> str:
        if command.startswith(".botauto status"):
            index = min(state["status_calls"], len(in_combat) - 1)
            state["status_calls"] += 1
            payload = status(native_hostile_activity_active=in_combat[index])
        elif command.startswith(".botauto diagnose"):
            payload = {"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1, "bots": []}
        elif command.startswith(".botauto trace"):
            payload = {
                "ok": True,
                "action": "botauto_trace",
                "trace_schema_version": 1,
                "bots": [{
                    "bot_guid": 30001,
                    "pending_entry_count": 0,
                    "entries": [{"sequence": 7, "action": "trash_action", "route_node_id": "bwd.magmaw.drudges"}],
                }],
            }
        elif command == ".botexp summary":
            payload = {"duration_minutes": 1, "total_kills": 1}
        elif command.startswith(".botauto combatlog"):
            payload = {"ok": True, "action": "botauto_combatlog", "recent_events": []}
        else:
            payload = {"ok": True, "action": "botauto_stop"}
        return json.dumps(payload)

    return respond


def test_transport_heartbeats_are_light_in_combat_and_full_out_of_combat(tmp_path):
    respond = _responses([False, True, True, False])
    commands: list[str] = []
    beats = {"count": 0}

    def execute(command: str, _timeout: int):
        commands.append(command)
        return respond(command) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        beats["count"] += 1
        if beats["count"] > 4:
            raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        run_transport_completion_watchdog(
            execute, ["attached"], None,
            command_script(start=False, exit_server=False, trace_delta=True, trace_limit=128),
            tmp_path, {}, {}, heartbeat_sec=1, no_progress_window_sec=600,
            sleep=sleep, retain_trace_route_nodes=("bwd.magmaw.drudges",), light_combat_heartbeats=True,
        )
    traces = [command for command in commands if command.startswith(".botauto trace")]
    assert traces == [FULL_TRACE, ".botauto trace all 8", ".botauto trace all 8", FULL_TRACE]
    assert commands.count(".botauto diagnose all") == 4
    timings = heartbeat.load_command_timings(tmp_path)
    modes = [row["mode"] for row in timings if row["command"].startswith(".botauto trace")]
    assert modes == ["full", "light", "light", "full"]
    assert all(row["configured_command"] == FULL_TRACE for row in timings if row["command"].startswith(".botauto trace"))
    assert all(row["completed_at_ms"] >= row["sent_at_ms"] > 0 for row in timings)
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["heartbeat_plan"]["mode"] == "full"
    with gzip.open(tmp_path / heartbeat.TRACE_HISTORY_FILE, "rt", encoding="utf-8") as handle:
        rows = [json.loads(line) for line in handle]
    # One retained row, deduplicated across the four heartbeat exports.
    assert [row["entry"]["sequence"] for row in rows] == [7]


FAKE_WORLDSERVER = """#!/usr/bin/env python3
import json, sys
responses = json.load(open(sys.argv[-1]))
combat = responses['combat']
status_calls = 0
log = open(responses['log'], 'a')
print('TC> ', flush=True)
for line in sys.stdin:
    cmd = line.strip()
    log.write(cmd + '\\n'); log.flush()
    if cmd.startswith('server shutdown'):
        break
    if cmd.startswith('.botauto status'):
        payload = dict(responses['status'])
        payload['raid_runtime'] = dict(payload['raid_runtime'], native_hostile_activity_active=combat[min(status_calls, len(combat) - 1)])
        status_calls += 1
    elif cmd.startswith('.botauto diagnose'):
        payload = {'ok': True, 'action': 'botauto_diagnose', 'diagnosis_schema_version': 1, 'bots': []}
    elif cmd.startswith('.botauto trace'):
        payload = {'ok': True, 'action': 'botauto_trace', 'trace_schema_version': 1, 'bots': []}
    elif cmd == '.botexp summary':
        payload = {'duration_minutes': 1, 'total_kills': 1}
    else:
        payload = {'ok': True, 'action': 'other'}
    print(json.dumps(payload))
    print('TC> ', flush=True)
"""


def test_process_heartbeats_are_light_in_combat(tmp_path):
    log = tmp_path / "commands.log"
    responses = tmp_path / "responses.json"
    responses.write_text(json.dumps({"combat": [True, True, False], "status": status(), "log": str(log)}), encoding="utf-8")
    binary = tmp_path / "fake_worldserver.py"
    binary.write_text(FAKE_WORLDSERVER, encoding="utf-8")
    binary.chmod(0o755)
    output_dir = tmp_path / "run"
    # The fake reads its responses from the ``--config`` argument.
    output, _returncode, _timed_out, _command = run_worldserver_completion_watchdog(
        binary, responses, 4,
        command_script(start=False, trace_delta=True, trace_limit=128),
        output_dir, {}, {}, heartbeat_sec=1, no_progress_window_sec=600,
        retain_trace_route_nodes=("bwd.magmaw.drudges",), light_combat_heartbeats=True,
    )
    commands = log.read_text(encoding="utf-8").splitlines()
    traces = [command for command in commands if command.startswith(".botauto trace")]
    assert traces[:2] == [".botauto trace all 8", ".botauto trace all 8"]
    assert all(trace == FULL_TRACE for trace in traces[2:])
    assert commands[-1] == "server shutdown force 0"
    # Cleanup drains the untouched delta cursor for the retained node once.
    assert commands[-3:-1] == [".botauto combatlog", FULL_TRACE] or commands[-4:-1] == [".botauto combatlog", ".botauto combatlog", FULL_TRACE]
    drain = [row for row in parse_json_objects(output) if row.get("purpose") == "trace_retention_drain"]
    assert drain and drain[0]["drain_calls"] == 1
    timings = heartbeat.load_command_timings(output_dir)
    assert {row["phase"] for row in timings} >= {"heartbeat", "cleanup", "trace_retention_drain"}


def _trace(pending: int, *nodes: str, start: int = 1) -> str:
    return json.dumps({
        "ok": True,
        "action": "botauto_trace",
        "trace_schema_version": 1,
        "bots": [{
            "bot_guid": 30001,
            "pending_entry_count": pending,
            "entries": [
                {"sequence": start + index, "route_node_id": node}
                for index, node in enumerate(nodes)
            ],
        }],
    })


def test_trace_retention_drains_until_the_backlog_moves_past_the_node(tmp_path):
    retention = heartbeat.TraceRouteRetention(tmp_path, ("bwd.magmaw.drudges",), parse_json_objects)
    first = retention.observe(heartbeat_index=1, phase="full", command=FULL_TRACE,
                              output=_trace(300, "bwd.magmaw.chainwielder", "bwd.magmaw.drudges"))
    assert first == {"matching_rows": 1, "pending_entry_count": 300, "entry_count": 2}
    assert retention.should_continue_drain(first, 1)
    second = retention.observe(heartbeat_index=1, phase="trace_retention_drain", command=FULL_TRACE,
                               output=_trace(200, "bwd.magmaw.drudges", "bwd.magmaw.drudges", start=2))
    assert retention.should_continue_drain(second, 2)
    past = retention.observe(heartbeat_index=1, phase="trace_retention_drain", command=FULL_TRACE,
                             output=_trace(100, "bwd.magmaw.encounter", start=10))
    assert not retention.should_continue_drain(past, 3)
    assert not retention.should_continue_drain({"pending_entry_count": 0, "entry_count": 5, "matching_rows": 5}, 1)
    assert not retention.should_continue_drain({"pending_entry_count": 9, "entry_count": 5, "matching_rows": 5}, heartbeat.TRACE_HISTORY_MAX_DRAIN_CALLS)
    with gzip.open(tmp_path / heartbeat.TRACE_HISTORY_FILE, "rt", encoding="utf-8") as handle:
        sequences = [json.loads(line)["entry"]["sequence"] for line in handle]
    assert sequences == [2, 3]
    disabled = heartbeat.TraceRouteRetention(tmp_path / "off", (), parse_json_objects)
    assert disabled.observe(heartbeat_index=1, phase="full", command=FULL_TRACE, output=_trace(1, "x"))["entry_count"] == 0
    assert not (tmp_path / "off").exists()


def test_no_light_combat_heartbeats_restores_the_full_trace_sequence(tmp_path):
    """--no-light-combat-heartbeats sends exactly the configured commands."""
    respond = _responses([True, True, True])
    commands: list[str] = []
    beats = {"count": 0}

    def execute(command: str, _timeout: int):
        commands.append(command)
        return respond(command) + "\n", 0, False

    def sleep(_seconds: float) -> None:
        beats["count"] += 1
        if beats["count"] > 3:
            raise KeyboardInterrupt

    script = command_script(start=False, exit_server=False, trace_delta=True, trace_limit=128)
    _startup, heartbeat_commands, _cleanup = heartbeat_commands_from_script(script)
    assert heartbeat_commands == [".botauto status", ".botauto diagnose all", FULL_TRACE, ".botexp summary"]
    with pytest.raises(KeyboardInterrupt):
        run_transport_completion_watchdog(
            execute, ["attached"], None, script, tmp_path, {}, {},
            heartbeat_sec=1, no_progress_window_sec=600, sleep=sleep,
            light_combat_heartbeats=False,
        )
    assert commands == heartbeat_commands * 3
    latest = json.loads((tmp_path / "latest.json").read_text(encoding="utf-8"))
    assert latest["heartbeat_plan"]["mode"] == "full"
    assert latest["heartbeat_plan"]["commands"] == heartbeat_commands
    assert not (tmp_path / heartbeat.TRACE_HISTORY_FILE).exists()


def test_no_light_flag_reaches_the_soap_watchdog(tmp_path, monkeypatch):
    import argparse

    from tools.bot_ml import run_live_bot_validation as live

    respond = _responses([True])
    commands: list[str] = []

    def execute(_url, _user, _password, command, _timeout):
        commands.append(command)
        return respond(command) + "\n", 0, False

    monkeypatch.setattr(live, "execute_soap_command", execute)
    args = argparse.Namespace(
        soap_url="http://127.0.0.1:7878/", soap_user="u", soap_password="p",
        timeout_sec=2, output_dir=tmp_path, duration_policy="completion-watchdog",
        heartbeat_sec=1, no_progress_window_sec=600, max_repeated_decision_count=20,
        max_death_loop_count=3, calibration_native_completion=False,
        light_combat_heartbeats=False, retain_trace_route_node=[],
    )
    live.run_soap_completion_watchdog(
        args, command_script(start=False, exit_server=False, trace_delta=True, trace_limit=128), {}, {}, None
    )
    traces = [command for command in commands if command.startswith(".botauto trace")]
    assert traces and all(command == FULL_TRACE for command in traces)


def test_process_no_light_combat_heartbeats_sends_full_traces(tmp_path):
    log = tmp_path / "commands.log"
    responses = tmp_path / "responses.json"
    responses.write_text(json.dumps({"combat": [True], "status": status(), "log": str(log)}), encoding="utf-8")
    binary = tmp_path / "fake_worldserver.py"
    binary.write_text(FAKE_WORLDSERVER, encoding="utf-8")
    binary.chmod(0o755)
    run_worldserver_completion_watchdog(
        binary, responses, 3,
        command_script(start=False, trace_delta=True, trace_limit=128),
        tmp_path / "run", {}, {}, heartbeat_sec=1, no_progress_window_sec=600,
        light_combat_heartbeats=False,
    )
    commands = log.read_text(encoding="utf-8").splitlines()
    heartbeat_rows = [command for command in commands if not command.startswith((".botauto combatlog", "server "))]
    # Cleanup reads status once more for native world ticks.
    assert heartbeat_rows[-1] == ".botauto status"
    heartbeat_rows = heartbeat_rows[:-1]
    assert heartbeat_rows
    assert heartbeat_rows == [".botauto status", ".botauto diagnose all", FULL_TRACE, ".botexp summary"] * (len(heartbeat_rows) // 4)


def test_light_combat_heartbeats_are_opt_in():
    """The full trace is the default: light mode hides watchdog rows and is only an opt-in."""
    import inspect
    from tools.bot_ml import run_live_bot_validation as harness
    for runner in (harness.run_transport_completion_watchdog, harness.run_worldserver_completion_watchdog):
        assert inspect.signature(runner).parameters["light_combat_heartbeats"].default is False
    source = inspect.getsource(harness._main)
    assert '"--light-combat-heartbeats"' in source and "set_defaults(light_combat_heartbeats=False)" in source

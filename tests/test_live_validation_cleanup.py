"""Stop/export cleanup always runs; SOAP keeps the route manifest."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

from tools.bot_ml import run_live_bot_validation as live
from tools.bot_ml.live_validation_cleanup import (
    CLEANUP_STEP_MAX_SEC,
    CLEANUP_TOTAL_BUDGET_SEC,
    CleanupBudget,
)
from tools.bot_ml.live_validation_heartbeat import cleanup_steps_from_payloads

FULL_TRACE = ".botauto trace all 128 delta"

MANIFEST = {"routes": [
    {"route_node_id": "trash", "route_generation": 1, "kind": "trash"},
    {"route_node_id": "boss", "route_generation": 2, "kind": "boss"},
]}


def clear_status(bots: int, leases: int) -> dict:
    return {
        "ok": True,
        "action": "botauto_status",
        "active": bots > 0,
        "bots": bots,
        "active_bots": bots,
        "target_bots": 10,
        "lease_count": leases,
        "decisions": 3,
        "kills": 2,
        "validation_route": {
            "kind": "boss",
            "node_id": "boss",
            "generation": 2,
            "manifest_complete": True,
            "terminal_evidence": [
                {"route_node_id": "trash", "route_generation": 1},
                {"route_node_id": "boss", "route_generation": 2},
            ],
            "boss_death_evidence": [
                {"route_node_id": "boss", "route_generation": 2, "result": "ok", "target_id": 39}
            ],
        },
    }


class CohortState:
    """Model the server-side cohort a production cleanup must release."""

    def __init__(self, *, combatlog_times_out: bool = False) -> None:
        self.bots = 10
        self.leases = 10
        self.commands: list[str] = []
        self.timeouts: dict[str, int] = {}
        self.combatlog_times_out = combatlog_times_out

    def execute(self, command: str, timeout: int) -> tuple[str, int, bool]:
        self.commands.append(command)
        self.timeouts[command] = timeout
        if command.startswith(".botauto status"):
            return json.dumps(clear_status(self.bots, self.leases)), 0, False
        if command.startswith(".botauto diagnose"):
            return json.dumps({"ok": True, "action": "botauto_diagnose", "diagnosis_schema_version": 1, "bots": []}), 0, False
        if command.startswith(".botauto trace"):
            return json.dumps({"ok": True, "action": "botauto_trace", "trace_schema_version": 1, "bots": []}), 0, False
        if command.startswith(".botauto combatlog"):
            if self.combatlog_times_out:
                return "", 124, True
            return '{"ok":true,"action":"botauto_combatlog_complete","chunk_count":0}', 0, False
        if command.startswith(".botauto stop"):
            self.bots = 0
            self.leases = 0
            return json.dumps({"ok": True, "action": "botauto_stop"}), 0, False
        return json.dumps({"duration_minutes": 1, "total_kills": 2}), 0, False


def _summary(output: str) -> dict:
    return next(
        row for row in reversed(live.parse_json_objects(output))
        if row.get("action") == "harness_cleanup_summary"
    )


def test_failed_export_after_a_clear_still_stops_and_keeps_the_verdict(tmp_path):
    cohort = CohortState(combatlog_times_out=True)
    script = live.command_script(start=False, stop=True, exit_server=False, trace_delta=True, trace_limit=128)
    output, returncode, timed_out, _ = live.run_transport_completion_watchdog(
        cohort.execute, ["SOAP"], 30, script, tmp_path, {}, {},
        validation_route_manifest=deepcopy(MANIFEST), heartbeat_sec=1,
        sleep=lambda _seconds: None,
    )
    assert cohort.commands.index(".botauto combatlog") < cohort.commands.index(".botauto stop")
    assert (cohort.bots, cohort.leases) == (0, 0)
    steps = cleanup_steps_from_payloads(live.parse_json_objects(output))
    assert [(step["command"], step["timed_out"], step["completed"]) for step in steps] == [
        (".botauto combatlog", True, False),
        (".botauto stop", False, True),
    ]
    # The native clear stands: the export failure is a cleanup record only.
    assert (returncode, timed_out) == (0, False)
    summary = _summary(output)
    assert summary["complete"] is False
    assert [row["command"] for row in summary["failed_steps"]] == [".botauto combatlog"]
    assert summary["watchdog_timed_out"] is False
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["timed_out"] is False
    assert live.observed_native_manifest_clear(report)


def test_emergency_cap_timeout_still_exports_and_stops_with_capped_steps(tmp_path):
    cohort = CohortState()
    script = live.command_script(start=False, stop=True, exit_server=False, trace_delta=True, trace_limit=128)
    output, returncode, timed_out, _ = live.run_transport_completion_watchdog(
        cohort.execute, ["SOAP"], 0, script, tmp_path, {}, {},
        validation_route_manifest=deepcopy(MANIFEST), heartbeat_sec=1,
        sleep=lambda _seconds: None,
    )
    assert (returncode, timed_out) == (124, True)
    assert ".botauto combatlog" in cohort.commands
    assert cohort.commands[-1] == ".botauto stop"
    assert cohort.timeouts[".botauto combatlog"] == CLEANUP_STEP_MAX_SEC
    assert cohort.timeouts[".botauto stop"] == CLEANUP_STEP_MAX_SEC
    assert (cohort.bots, cohort.leases) == (0, 0)
    assert _summary(output)["watchdog_timed_out"] is True


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def test_cleanup_budget_caps_steps_and_reserves_the_stop():
    clock = FakeClock()
    budget = CleanupBudget(deadline=clock.now - 5, stop_pending=True, clock=clock)
    assert budget.step_timeout(".botauto combatlog") == 180
    assert budget.step_timeout(".botauto stop") == 180
    clock.now += 420  # 180 s left, 60 s of it reserved for the stop
    assert budget.step_timeout(".botauto combatlog") == 120
    clock.now += 125
    assert budget.step_timeout(".botauto combatlog") == 0
    assert budget.step_timeout(".botauto stop") == 60
    budget.skip(".botauto calibrate stop")
    clock.now += 100  # the budget is spent; the stop still gets its reserve
    assert budget.step_timeout(".botauto stop") == 60
    budget.stop_pending = False
    assert budget.step_timeout(".botauto trace all 128 delta") == 0
    summary = json.loads(budget.summary_receipt(watchdog_timed_out=False))
    assert summary["cleanup_budget_exhausted"] is True
    assert summary["skipped_steps"] == [".botauto calibrate stop"]
    assert summary["cleanup_overrun_sec"] == 645.0  # all of it past the cap
    assert summary["cleanup_budget_sec"] == CLEANUP_TOTAL_BUDGET_SEC


def test_transport_cleanup_budget_bounds_every_step_and_drains_before_stop(tmp_path, monkeypatch):
    clock = FakeClock()
    monkeypatch.setattr(
        live, "CleanupBudget",
        lambda **kwargs: CleanupBudget(clock=clock, **kwargs),
    )
    calls: list[tuple[str, int]] = []
    cohort = CohortState()

    def execute(command: str, timeout: int):
        if command.startswith(".botauto status"):
            return cohort.execute(command, timeout)
        calls.append((command, timeout))
        if command == ".botauto combatlog":
            # Slow and incomplete: the harness retries the export once.
            clock.now += timeout
            return "{}", 0, False
        if command == FULL_TRACE and clock.now > 1000.0:
            clock.now += timeout
            return "", 124, True
        return cohort.execute(command, timeout)

    script = live.command_script(start=False, stop=True, exit_server=False, trace_delta=True, trace_limit=128)
    output, returncode, timed_out, _ = live.run_transport_completion_watchdog(
        execute, ["SOAP"], 30, script, tmp_path, {}, {},
        validation_route_manifest=deepcopy(MANIFEST), heartbeat_sec=1,
        sleep=lambda _seconds: None, retain_trace_route_nodes=("trash",),
    )
    cleanup_calls = [(command, timeout) for command, timeout in calls if not command.startswith((".botauto diagnose", ".botexp"))]
    assert cleanup_calls.pop(0)[0] == FULL_TRACE  # the heartbeat's own trace
    # Two export attempts and one drain call use 540 s; the stop gets the
    # reserved 60 s and runs after the drain.
    assert cleanup_calls == [
        (".botauto combatlog", 180),
        (".botauto combatlog", 180),
        (FULL_TRACE, 180),
        (".botauto stop", 60),
    ]
    assert (returncode, timed_out) == (0, False)
    assert (cohort.bots, cohort.leases) == (0, 0)


def test_soap_completion_watchdog_receives_route_manifest(tmp_path, monkeypatch):
    cohort = CohortState()
    monkeypatch.setattr(
        live, "execute_soap_command",
        lambda _url, _user, _password, command, timeout: cohort.execute(command, timeout),
    )
    args = argparse.Namespace(
        soap_url="http://127.0.0.1:7878/", soap_user="u", soap_password="p",
        timeout_sec=30, output_dir=tmp_path, duration_policy="completion-watchdog",
        heartbeat_sec=1, no_progress_window_sec=180, max_repeated_decision_count=20,
        max_death_loop_count=3, calibration_native_completion=False,
        light_combat_heartbeats=True, retain_trace_route_node=[],
    )
    script = live.command_script(start=False, stop=False, exit_server=False, trace_delta=True, trace_limit=128)
    _output, returncode, timed_out, command = live.run_soap_completion_watchdog(
        args, script, {}, {}, deepcopy(MANIFEST)
    )
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["validation_route_manifest"] == MANIFEST
    assert live.observed_native_manifest_clear(report)
    # The native clear ended the watchdog on its first heartbeat.
    assert report["heartbeat_index"] == 1
    # One heartbeat status, then the cleanup world-tick status read.
    assert cohort.commands.count(".botauto status") == 2
    assert (returncode, timed_out, command) == (0, False, ["SOAP", args.soap_url])


FAKE_WORLDSERVER = """#!/usr/bin/env python3
import json, sys, time
config = json.load(open(sys.argv[-1]))
log = open(config['log'], 'a')
bots = 0
leases = 0
print('TC> ', flush=True)
for line in sys.stdin:
    cmd = line.strip()
    log.write(cmd + '\\n'); log.flush()
    if cmd.startswith('server shutdown'):
        before = bots
        bots = leases = 0
        json.dump({'bots_before_shutdown': before, 'bots_at_exit': bots, 'leases_at_exit': leases}, open(config['state'], 'w'))
        print('PlayerBot remove all complete world_bots=0', flush=True)
        if config.get('shutdown') == 'hang':
            print('TC> ', flush=True)
            time.sleep(600)
        time.sleep(float(config.get('exit_delay') or 0))
        break
    if cmd == '.botauto start':
        bots = leases = 10
        payload = {'ok': True, 'action': 'botauto_start'}
    elif cmd == '.botauto stop':
        bots = leases = 0
        payload = {'ok': True, 'action': 'botauto_stop'}
    elif cmd.startswith('.botauto status'):
        payload = dict(config['status'], active=bots > 0, bots=bots, active_bots=bots, lease_count=leases)
    elif cmd.startswith('.botauto diagnose'):
        payload = {'ok': True, 'action': 'botauto_diagnose', 'diagnosis_schema_version': 1, 'bots': []}
    elif cmd.startswith('.botauto trace'):
        payload = {'ok': True, 'action': 'botauto_trace', 'trace_schema_version': 1, 'bots': [
            {'bot_guid': 30001, 'pending_entry_count': 0, 'entries': [{'sequence': 1, 'route_node_id': 'trash'}]}
        ] if bots else []}
    elif cmd.startswith('.botauto combatlog'):
        time.sleep(float(config.get('combatlog_delay') or 0))
        payload = {'ok': True, 'action': 'botauto_combatlog_complete', 'chunk_count': 0}
    else:
        payload = {'duration_minutes': 1, 'total_kills': 2}
    print(json.dumps(payload, separators=(',', ':')))
    print('TC> ', flush=True)
"""


def _fake_worldserver(tmp_path, **options):
    config = tmp_path / "fake.json"
    config.write_text(json.dumps({
        "log": str(tmp_path / "commands.log"),
        "state": str(tmp_path / "state.json"),
        "status": clear_status(10, 10),
        **options,
    }), encoding="utf-8")
    binary = tmp_path / "fake_worldserver.py"
    binary.write_text(FAKE_WORLDSERVER, encoding="utf-8")
    binary.chmod(0o755)
    return binary, config


def test_production_process_script_releases_every_bot_and_lease(tmp_path):
    """commands.txt in process mode is combatlog -> server shutdown (no stop)."""
    binary, config = _fake_worldserver(tmp_path)
    state = tmp_path / "state.json"
    log = tmp_path / "commands.log"
    script = live.command_script(
        selector="all", trace_limit=128, start=True, stop=False, exit_server=True, trace_delta=True
    )
    assert ".botauto stop" not in script
    output, returncode, timed_out, _ = live.run_worldserver_completion_watchdog(
        binary, config, 30, script, tmp_path / "run", {}, {},
        heartbeat_sec=1, validation_route_manifest=deepcopy(MANIFEST),
    )
    commands = log.read_text(encoding="utf-8").splitlines()
    assert ".botauto stop" not in commands
    assert commands.index(".botauto combatlog") < commands.index("server shutdown force 0")
    assert commands[-1] == "server shutdown force 0"
    # The server exited on its own after shutdown (no kill, no timeout) and
    # reported zero bots and leases; the bots were live until shutdown.
    assert (returncode, timed_out) == (0, False)
    assert json.loads(state.read_text()) == {"bots_before_shutdown": 10, "bots_at_exit": 0, "leases_at_exit": 0}
    assert "world_bots=0" in output
    steps = cleanup_steps_from_payloads(live.parse_json_objects(output))
    assert [step["command"] for step in steps] == [".botauto combatlog"]

    summary = _summary(output)
    assert summary["complete"] is True
    assert summary["shutdown_sent"] is True and summary["shutdown_killed"] is False
    assert summary["worldserver_exit_code"] == 0


def _process_script(**kwargs) -> str:
    return live.command_script(
        selector="all", trace_limit=128, start=True, exit_server=True, trace_delta=True, **kwargs
    )


def test_shutdown_kill_after_a_clear_is_a_cleanup_overrun_not_a_timeout(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "SHUTDOWN_GRACE_SEC", 1)
    binary, config = _fake_worldserver(tmp_path, shutdown="hang")
    output, returncode, timed_out, _ = live.run_worldserver_completion_watchdog(
        binary, config, 30, _process_script(stop=False), tmp_path / "run", {}, {},
        heartbeat_sec=1, validation_route_manifest=deepcopy(MANIFEST),
    )
    assert (returncode, timed_out) == (0, False)
    summary = _summary(output)
    assert summary["shutdown_killed"] is True
    assert summary["worldserver_exit_code"] == -9
    assert summary["watchdog_timed_out"] is False
    assert summary["complete"] is False
    report = json.loads((tmp_path / "run" / "report.json").read_text())
    assert report["timed_out"] is False
    assert live.observed_native_manifest_clear(report)


def test_shutdown_always_gets_its_grace_even_past_the_emergency_cap(tmp_path, monkeypatch):
    monkeypatch.setattr(live, "SHUTDOWN_GRACE_SEC", 2)
    # The clear lands at ~1 s, the export takes 3.5 s (past the 3 s cap by
    # more than the grace), and the server needs 1.2 s to exit.
    binary, config = _fake_worldserver(tmp_path, combatlog_delay=3.5, exit_delay=1.2)
    output, returncode, timed_out, _ = live.run_worldserver_completion_watchdog(
        binary, config, 3, _process_script(stop=False), tmp_path / "run", {}, {},
        heartbeat_sec=1, validation_route_manifest=deepcopy(MANIFEST),
    )
    summary = _summary(output)
    assert summary["shutdown_killed"] is False
    assert summary["worldserver_exit_code"] == 0
    assert summary["cleanup_overrun_sec"] > 1.0
    assert (returncode, timed_out) == (0, False)


def test_process_trace_drain_runs_before_the_stop(tmp_path):
    binary, config = _fake_worldserver(tmp_path)
    script = _process_script(stop=True)
    output, returncode, timed_out, _ = live.run_worldserver_completion_watchdog(
        binary, config, 30, script, tmp_path / "run", {}, {},
        heartbeat_sec=1, validation_route_manifest=deepcopy(MANIFEST),
        retain_trace_route_nodes=("trash",),
    )
    commands = (tmp_path / "commands.log").read_text(encoding="utf-8").splitlines()
    tail = [value for index, value in enumerate(commands) if index >= commands.index(".botauto combatlog")]
    tail = [value for index, value in enumerate(tail) if index == 0 or value != tail[index - 1]]
    assert tail == [".botauto combatlog", FULL_TRACE, ".botauto stop", "server shutdown force 0"]
    assert (returncode, timed_out) == (0, False)
    drain = [row for row in live.parse_json_objects(output) if row.get("purpose") == "trace_retention_drain"]
    assert drain[0]["drain_calls"] == 1


def test_transport_trace_drain_runs_before_the_stop(tmp_path):
    cohort = CohortState()
    script = live.command_script(start=False, stop=True, exit_server=False, trace_delta=True, trace_limit=128)
    live.run_transport_completion_watchdog(
        cohort.execute, ["SOAP"], 30, script, tmp_path, {}, {},
        validation_route_manifest=deepcopy(MANIFEST), heartbeat_sec=1,
        sleep=lambda _seconds: None, retain_trace_route_nodes=("trash",),
    )
    tail = cohort.commands[cohort.commands.index(".botauto combatlog"):]
    tail = [value for index, value in enumerate(tail) if index == 0 or value != tail[index - 1]]
    assert tail == [".botauto combatlog", FULL_TRACE, ".botauto stop"]

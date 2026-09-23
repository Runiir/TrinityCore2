"""Stop/export cleanup always runs; SOAP keeps the route manifest."""
from __future__ import annotations

import argparse
import json
from copy import deepcopy

from tools.bot_ml import run_live_bot_validation as live
from tools.bot_ml.live_validation_heartbeat import cleanup_steps_from_payloads

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


def test_failed_export_still_stops_cohort_and_records_every_step(tmp_path):
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
    # The export failure still fails the capture after the stop ran.
    assert (returncode, timed_out) == (124, True)
    assert json.loads((tmp_path / "latest.json").read_text())["timed_out"] is True


def test_emergency_cap_timeout_still_exports_and_stops(tmp_path):
    cohort = CohortState()
    script = live.command_script(start=False, stop=True, exit_server=False, trace_delta=True, trace_limit=128)
    _output, returncode, timed_out, _ = live.run_transport_completion_watchdog(
        cohort.execute, ["SOAP"], 0, script, tmp_path, {}, {},
        validation_route_manifest=deepcopy(MANIFEST), heartbeat_sec=1,
        sleep=lambda _seconds: None,
    )
    assert (returncode, timed_out) == (124, True)
    assert ".botauto combatlog" in cohort.commands
    assert cohort.commands[-1] == ".botauto stop"
    assert cohort.timeouts[".botauto combatlog"] >= 120
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
    assert cohort.commands.count(".botauto status") == 1
    assert (returncode, timed_out, command) == (0, False, ["SOAP", args.soap_url])


FAKE_WORLDSERVER = """#!/usr/bin/env python3
import json, sys
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
        payload = {'ok': True, 'action': 'botauto_trace', 'trace_schema_version': 1, 'bots': []}
    elif cmd.startswith('.botauto combatlog'):
        payload = {'ok': True, 'action': 'botauto_combatlog_complete', 'chunk_count': 0}
    else:
        payload = {'duration_minutes': 1, 'total_kills': 2}
    print(json.dumps(payload))
    print('TC> ', flush=True)
"""


def test_production_process_script_releases_every_bot_and_lease(tmp_path):
    """commands.txt in process mode is combatlog -> server shutdown (no stop)."""
    config = tmp_path / "fake.json"
    state = tmp_path / "state.json"
    log = tmp_path / "commands.log"
    config.write_text(json.dumps({"log": str(log), "state": str(state), "status": clear_status(10, 10)}), encoding="utf-8")
    binary = tmp_path / "fake_worldserver.py"
    binary.write_text(FAKE_WORLDSERVER, encoding="utf-8")
    binary.chmod(0o755)
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

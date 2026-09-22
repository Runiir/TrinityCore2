"""An observed clear ends capture; it does not certify diagnostic evidence."""
from copy import deepcopy
import json

import pytest

from tools.bot_ml import run_live_bot_validation as live


def clear_report():
    scopes = [{"route_node_id": name, "route_generation": i}
              for i, name in enumerate(("entry", "trash", "boss"), 1)]
    return {
        "returncode": 0, "timed_out": False,
        "acceptable_final_evidence": False,
        "final_evidence_rejections": ["segment_or_route_context_is_debug_only"],
        "completion_reason": "validation_route_manifest_complete",
        "validation_route_manifest": {"routes": [
            dict(scope, kind=kind) for scope, kind in
            zip(scopes, ("regroup", "trash", "boss"))]},
        "evidence": {"route_terminal_evidence": deepcopy(scopes),
                     "real_boss_kill_evidence": [deepcopy(scopes[-1])],
                     "manifest_completion_evidence": [deepcopy(scopes[-1])]},
        "watchdog_state": {"progress_total": 4},
    }


@pytest.mark.parametrize("missing", ["route_terminal_evidence", "real_boss_kill_evidence", "manifest_completion_evidence"])
def test_incomplete_or_wrong_generation_is_not_clear(missing):
    report = clear_report()
    report["evidence"][missing][-1]["route_generation"] = 99
    assert not live.observed_native_manifest_clear(report)
    report["evidence"][missing] = []
    assert not live.observed_native_manifest_clear(report)


def test_native_clear_preserves_certification_rejection():
    report = clear_report()
    before = deepcopy(report)
    assert live.observed_native_manifest_clear(report)
    assert report == before
    assert not report["acceptable_final_evidence"]


@pytest.mark.parametrize("key,value", [("timed_out", True), ("returncode", 1)])
def test_infrastructure_failure_not_native_clear(key, value):
    report = clear_report()
    report[key] = value
    assert not live.observed_native_manifest_clear(report)


@pytest.mark.parametrize("transport", ["process", "attached"])
def test_production_watchdogs_stop_at_uncertified_clear(tmp_path, monkeypatch, transport):
    report = clear_report()
    calls = []
    def heartbeat(*args, **kwargs):
        calls.append(True)
        assert len(calls) == 1, "watchdog polled again after native clear"
        return deepcopy(report)
    monkeypatch.setattr(live, "rolling_heartbeat_report", heartbeat)
    script = ".botauto status\n.botauto combatlog\n.botauto stop\n"
    if transport == "attached":
        commands = []
        def execute(command, timeout):
            commands.append(command)
            return ('{"action":"botauto_combatlog_complete"}\nTC> '
                    if command == ".botauto combatlog" else "TC> "), 0, False
        output, rc, timed_out, _ = live.run_transport_completion_watchdog(
            execute, ["session"], 5, script, tmp_path, {}, {},
            validation_route_manifest=report["validation_route_manifest"],
            heartbeat_sec=1, sleep=lambda _: None)
        assert commands.count(".botauto stop") == 1
        assert commands.index(".botauto combatlog") < commands.index(".botauto stop")
        assert not any("shutdown" in command for command in commands)
    else:
        binary = tmp_path / "fake_worldserver.py"
        binary.write_text(
            "#!/usr/bin/env python3\nimport sys\nprint('TC> ', flush=True)\n"
            "for line in sys.stdin:\n"
            " print('CMD ' + line.strip(), flush=True)\n"
            " if line.strip() == '.botauto combatlog': print('{\"action\":\"botauto_combatlog_complete\"}', flush=True)\n"
            " if line.startswith('server shutdown'): break\n"
            " print('TC> ', flush=True)\n")
        binary.chmod(0o755)
        config = tmp_path / "server.conf"
        config.write_text("")
        output, rc, timed_out, _ = live.run_worldserver_completion_watchdog(
            binary, config, 5, script, tmp_path, {}, {}, heartbeat_sec=1,
            validation_route_manifest=report["validation_route_manifest"])
        assert output.count("CMD .botauto stop") == 1
        assert output.index("CMD .botauto combatlog") < output.index("CMD .botauto stop")
        assert "CMD server shutdown force 0" in output
    assert rc == 0 and not timed_out
    saved = json.loads((tmp_path / "latest.json").read_text())
    assert not saved["acceptable_final_evidence"]
    assert saved["final_evidence_rejections"] == report["final_evidence_rejections"]

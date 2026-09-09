import sys

import pytest

from tools.bot_ml import run_live_bot_validation as capture


@pytest.mark.parametrize("calibration", [False, True])
def test_process_startup_waits_only_for_ordinary_population(tmp_path, monkeypatch, calibration):
    server = tmp_path / "server.py"
    server.write_text(
        f"#!{sys.executable}\n"
        "import sys\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    command = line.strip()\n"
        "    print('CMD ' + command)\n"
        "    if command.startswith('.botauto calibrate start'):\n"
        "        print('{\"action\":\"botauto_calibrate_start\",\"ok\":true}')\n"
        "    elif command == '.botauto status':\n"
        "        print('{\"action\":\"botauto_status\",\"active\":true,\"bots\":0,\"target_bots\":0}')\n"
        "    elif command.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n"
    )
    server.chmod(0o755)
    config = tmp_path / "world.conf"
    config.write_text("BotWorld.TargetPopulation = 0\n")
    waits = []

    def ordinary_ready(process, deadline):
        waits.append((process.pid, deadline))
        assert not calibration, "calibration must not wait for ordinary bots"
        return "ordinary-readiness-checked\n"

    monkeypatch.setattr(capture, "wait_for_bot_status_ready", ordinary_ready)
    # Only termination is synthetic. Startup dispatch, process transport,
    # command ordering and the readiness call site remain production code.
    monkeypatch.setattr(capture, "rolling_heartbeat_report", lambda *a, **kw: {
        "acceptable_final_evidence": True,
    })
    script = ".botauto start\n"
    if calibration:
        script += ".botauto calibrate start single_target_300 affliction_warlock 1\n"
    script += ".botauto status\n"
    output, code, timed_out, _ = capture.run_worldserver_completion_watchdog(
        server, config, 5, script, tmp_path / "validation", {}, {}, heartbeat_sec=1,
    )
    assert code == 0 and not timed_out
    assert len(waits) == (0 if calibration else 1)
    assert output.index("CMD .botauto start") < output.index("CMD .botauto status")
    if calibration:
        assert output.index("CMD .botauto start") < output.index("CMD .botauto calibrate start")
        assert output.index("CMD .botauto calibrate start") < output.index("CMD .botauto status")
    else:
        assert "ordinary-readiness-checked" in output

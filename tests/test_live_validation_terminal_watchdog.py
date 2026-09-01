from __future__ import annotations

import json

from tools.bot_ml.run_live_bot_validation import (
    command_script,
    raid_terminal_watchdog_failure,
    run_worldserver_completion_watchdog,
)


def _report(runtime: dict, *, failure_reason: str = "") -> dict:
    return {
        "status": {
            "failure_reason": failure_reason or None,
            "raid_runtime": {
                "instance_kind": "raid",
                "admission_phase": "active",
                "bot_actions_enabled": True,
                "expected_size": 10,
                "active_size": 10,
                "alive_size": 10,
                "wipe_state": "engaged",
                "wipe_generation": 0,
                "recovery_state": "none",
                **runtime,
            },
        },
        "watchdog_state": {"progress_total": 0},
    }


def test_explicit_action_gate_failure_is_immediately_typed_terminal() -> None:
    terminal = raid_terminal_watchdog_failure(
        _report(
            {
                "admission_phase": "terminal",
                "bot_actions_enabled": False,
            },
            failure_reason="validation_active_hunter_pet_admission_identity_drift",
        )
    )

    assert terminal == {
        "kind": "cohort_action_gate_failure",
        "completion_reason": "cohort_action_gate_failure_watchdog",
        "failure_reason": "validation_active_hunter_pet_admission_identity_drift",
    }


def test_all_dead_without_typed_recovery_is_terminal() -> None:
    terminal = raid_terminal_watchdog_failure(
        _report(
            {
                "alive_size": 0,
                "wipe_state": "wiped",
                "wipe_generation": 2,
                "recovery_state": "none",
            }
        )
    )

    assert terminal is not None
    assert terminal["kind"] == "cohort_wiped_without_active_recovery"
    assert terminal["completion_reason"] == "cohort_wipe_without_recovery_watchdog"


def test_all_dead_with_active_valid_recovery_continues() -> None:
    terminal = raid_terminal_watchdog_failure(
        _report(
            {
                "alive_size": 0,
                "wipe_state": "wiped",
                "wipe_generation": 2,
                "recovery_state": "release_resurrection_pending",
            }
        )
    )

    assert terminal is None


def test_partial_deaths_continue() -> None:
    terminal = raid_terminal_watchdog_failure(
        _report(
            {
                "alive_size": 4,
                "wipe_state": "partial_deaths",
                "wipe_generation": 0,
                "recovery_state": "none",
            }
        )
    )

    assert terminal is None


def test_semantic_progress_continues() -> None:
    report = _report({"alive_size": 10, "wipe_state": "engaged"})
    report["watchdog_state"] = {
        "progress_total": 17,
        "live_combat_progress": {
            "damage": [{"party_damage": 12345}],
            "health": [{"hp_pct": 0.72}],
        },
    }

    assert raid_terminal_watchdog_failure(report) is None


def test_full_wipe_with_explicit_remaining_recovery_budget_continues() -> None:
    terminal = raid_terminal_watchdog_failure(
        _report(
            {
                "alive_size": 0,
                "wipe_state": "wiped",
                "wipe_generation": 2,
                "recovery_state": "none",
                "recovery_attempts_remaining": 1,
            }
        )
    )

    assert terminal is None


def test_terminal_gate_still_captures_and_cleans_up(tmp_path) -> None:
    command_log = tmp_path / "commands.log"
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"log = open({str(command_log)!r}, 'a', encoding='utf-8')\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    log.write(cmd + '\\n'); log.flush()\n"
        "    if cmd.startswith('.botauto status'):\n"
        "        print('{\"ok\":true,\"action\":\"botauto_status\",\"active_bots\":10,\"target_bots\":10,\"failure_reason\":\"validation_active_hunter_pet_admission_identity_drift\",\"raid_runtime\":{\"active\":true,\"instance_kind\":\"raid\",\"admission_phase\":\"terminal\",\"bot_actions_enabled\":false,\"expected_size\":10,\"active_size\":10,\"alive_size\":10,\"wipe_state\":\"engaged\",\"wipe_generation\":0,\"recovery_state\":\"none\"}}')\n"
        "    elif cmd.startswith('.botauto diagnose'):\n"
        "        print('{\"ok\":true,\"action\":\"botauto_diagnose\",\"diagnosis_schema_version\":1,\"bots\":[]}')\n"
        "    elif cmd.startswith('.botauto trace'):\n"
        "        print('{\"ok\":true,\"action\":\"botauto_trace\",\"trace_schema_version\":1,\"entries\":[]}')\n"
        "    elif cmd.startswith('.botauto combatlog'):\n"
        "        print('{\"ok\":true,\"action\":\"botauto_combatlog\",\"events\":[]}')\n"
        "    elif cmd.startswith('.botauto stop'):\n"
        "        print('{\"ok\":true,\"action\":\"botauto_stop\"}')\n"
        "    elif cmd.startswith('server shutdown'):\n"
        "        break\n"
        "    print('TC> ', flush=True)\n"
        "log.close()\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    output_dir = tmp_path / "validation"

    _output, returncode, timed_out, _command = run_worldserver_completion_watchdog(
        fake_worldserver,
        config,
        10,
        command_script(selector="all", trace_limit=5, start=False, stop=True),
        output_dir,
        {},
        {"scenario_id": "blackwing_descent_10n_magmaw_diagnostic"},
        heartbeat_sec=1,
        no_progress_window_sec=180,
        validation_route_manifest={
            "schema": "bot_live_validation_route_manifest_v1",
            "route_count": 4,
        },
    )

    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert returncode == 0
    assert timed_out is False
    assert report["completion_reason"] == "cohort_action_gate_failure_watchdog"
    assert report["failure_reason"] == "validation_active_hunter_pet_admission_identity_drift"
    assert any(command.startswith(".botauto diagnose") for command in commands)
    assert any(command.startswith(".botauto trace") for command in commands)
    assert any(command.startswith(".botauto combatlog") for command in commands)
    assert any(command.startswith(".botauto stop") for command in commands)
    assert "server shutdown force 0" in commands

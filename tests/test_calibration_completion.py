from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from tools.bot_ml import run_live_bot_validation as runner
from tools.bot_ml.calibration_completion import (
    native_calibration_requested,
    native_calibration_window_complete,
)


def _script() -> str:
    return runner.command_script(
        start=False,
        stop=True,
        exit_server=False,
        combat_calibration=True,
        calibration_only=True,
    )


def _complete_report():
    return {'calibration_only': True, 'returncode': 0, 'timed_out': False,
        'calibration_observation_mode': 'native_completion',
        'requested_calibration': {'mode': 'single_target_300', 'target_spec': 'fire_mage', 'seed': 1},
        'combat_calibration': {'window_complete': True, 'phase': 'complete',
            'mode': 'single_target_300', 'target_spec': 'fire_mage', 'seed': 1,
            'target_guid': 101, 'runtime_authority': 'explicit_sql_rule_profiles',
            'runtime_mode': 'calibration_fixture', 'non_certifying_assistance': True,
            'generic_ml_runtime_authority': False, 'reset_applied': True, 'reset_id': 'window1',
            'cross_window_event_count': 0, 'scored_seconds': 300,
            'scored_started_at_ms': 1000, 'scored_ended_at_ms': 301000,
            'profile_generation': 7, 'profile_content_hash': 'a'*64,
            'previous_window': {'bots': [{'guid': 101, 'attempts': 10, 'dps': 40000}]}}}


def test_complete_explicit_probe_cannot_qualify_even_after_recomputation():
    report = _complete_report()
    assert runner.apply_calibration_only_acceptance(report)['calibration_acceptance']['passed']
    report['calibration_observation_mode'] = 'explicit_probe'
    runner.apply_calibration_only_acceptance(report)
    assert report['calibration_acceptance']['rejections'] == ['calibration_explicit_probe_not_qualifying']
    report['role_calibration_evaluation'] = {'passed': True}
    runner.AcceptanceRecomputer().recompute(report, identity_required=False, session_required=False)
    assert not report['acceptable_final_evidence']
    assert not report['calibration_acceptance']['passed']


@pytest.mark.parametrize('change', [{'scored_seconds': 299}, {'scored_seconds': 301},
                                  {'scored_ended_at_ms': 302000}])
def test_calibration_acceptance_rejects_inexact_scoring(change):
    report = _complete_report()
    report['combat_calibration'].update(change)
    assert not runner.apply_calibration_only_acceptance(report)['calibration_acceptance']['passed']


def _transport_for(clock: list[float], *, disconnect: bool = False):
    commands: list[str] = []

    def execute(command: str, _timeout: int):
        commands.append(command)
        if command.startswith(".botauto calibrate start"):
            payload = {"ok": True, "action": "botauto_calibrate_start"}
        elif command == ".botauto calibrate status":
            if disconnect:
                return "transport disconnected", 1, False
            if clock[0] < 150:
                payload = {
                    "ok": True,
                    "action": "botauto_calibrate_status",
                    "phase": "warmup",
                    "scored_seconds": 0,
                    "window_complete": False,
                    "bots": [],
                }
            elif clock[0] < 350:
                payload = {
                    "ok": True,
                    "action": "botauto_calibrate_status",
                    "phase": "scoring",
                    "scored_seconds": 100,
                    "scored_started_at_ms": 1_000,
                    "window_complete": False,
                    "bots": [],
                }
            else:
                payload = {
                    "ok": True,
                    "action": "botauto_calibrate_status",
                    "phase": "complete",
                    "scored_seconds": 300,
                    "scored_started_at_ms": 1_000,
                    "scored_ended_at_ms": 301_000,
                    "window_complete": True,
                    "bots": [],
                }
        elif command == ".botauto status":
            payload = {
                "ok": True,
                "action": "botauto_status",
                "active": True,
                "active_bots": 0,
                "target_bots": 0,
            }
        elif command.startswith(".botauto combatlog"):
            payload = {"ok": True, "action": "botauto_combatlog", "events": []}
        elif command.endswith(" calibrate stop"):
            payload = {
                "ok": True,
                "action": "botauto_calibrate_stop",
                "fixture_cleanup_submitted_or_absent": True,
            }
        elif command.endswith(" stop"):
            payload = {"ok": True, "action": "botauto_stop"}
        else:
            payload = {}
        return json.dumps(payload), 0, False

    return commands, execute


def test_unspecified_observation_selects_native_completion_dispatch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
):
    input_log = tmp_path / "input.log"
    input_log.write_text("", encoding="utf-8")
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")
    output_dir = tmp_path / "report"
    monkeypatch.setattr(
        runner,
        "enforce_runtime_asset_closure_from_args",
        lambda *_args, **_kwargs: {"complete": True},
    )
    monkeypatch.setattr(
        runner,
        "preflight_calibration_reference_binding",
        lambda **_kwargs: {"required": True, "valid": True},
    )
    monkeypatch.setattr(
        runner,
        "preflight_validation_scenario_stage",
        lambda *args, **kwargs: {"valid": True, "required": False},
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_live_bot_validation.py",
            "--calibration-only",
            "--duration-policy",
            "fixed-window",
            "--input-log",
            str(input_log),
            "--config",
            str(config),
            "--output-dir",
            str(output_dir),
            "--dry-run",
        ],
    )

    assert runner.main() == 0
    capsys.readouterr()
    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))

    assert native_calibration_requested(
        calibration_only=True, observe_sec_was_explicit=False
    )
    assert report["calibration_observation_mode"] == "native_completion"
    assert report["duration_policy"] == "completion-watchdog"
    assert report["observe_sec"] == 0
    assert report["timeout_sec"] == runner.DEFAULT_CALIBRATION_TIMEOUT_SEC


@pytest.mark.parametrize("scored_seconds", [299.999, 300.001, float("nan"), 301.0])
def test_native_completion_requires_exact_scored_duration(scored_seconds: float):
    assert not native_calibration_window_complete(
        {
            "phase": "complete",
            "window_complete": True,
            "scored_seconds": scored_seconds,
        }
    )


def test_native_completion_accepts_exact_scored_duration_with_native_timestamps():
    assert native_calibration_window_complete(
        {
            "phase": "complete",
            "window_complete": True,
            "scored_seconds": 300,
            "scored_started_at_ms": 1_000,
            "scored_ended_at_ms": 301_000,
        }
    )


def test_native_transport_waits_for_warmup_scoring_and_terminal_window(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clock = [0.0]
    commands, execute = _transport_for(clock)
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])

    output, returncode, timed_out, _ = runner.run_transport_completion_watchdog(
        execute,
        ["session"],
        1_000,
        _script(),
        tmp_path,
        {},
        {},
        heartbeat_sec=100,
        no_progress_window_sec=500,
        calibration_native_completion=True,
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert returncode == 0
    assert timed_out is False
    assert clock[0] == 400
    assert commands.index(".botauto calibrate stop") > commands.index(
        ".botauto calibrate status"
    )
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    completion = report["watchdog_state"]["calibration_completion"]
    assert completion["warmup_elapsed_seconds"] == 200
    assert completion["scored_seconds"] == 300
    assert completion["window_complete"] is True
    assert '"phase": "complete"' in output


def test_native_transport_terminates_prolonged_setup_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clock = [0.0]
    commands: list[str] = []

    def execute(command: str, _timeout: int):
        commands.append(command)
        if command.startswith(".botauto calibrate start"):
            return '{"ok":true,"action":"botauto_calibrate_start"}', 0, False
        if command == ".botauto calibrate status":
            payload = {
                "ok": True,
                "action": "botauto_calibrate_status",
                "phase": "warmup",
                "scored_seconds": 0,
                "window_complete": False,
                "bots": [
                    {
                        "guid": 7,
                        "attempts": 0,
                        "movement_diagnostic": {
                            "last_recovery_result": "persistent_setup_target_unreachable"
                        },
                    }
                ],
            }
            return json.dumps(payload), 0, False
        if command == ".botauto status":
            return '{"ok":true,"action":"botauto_status","active":true}', 0, False
        if command.startswith(".botauto combatlog"):
            return '{"ok":true,"action":"botauto_combatlog","events":[]}', 0, False
        if command.endswith(" calibrate stop"):
            return (
                '{"ok":true,"action":"botauto_calibrate_stop",'
                '"fixture_cleanup_submitted_or_absent":true}',
                0,
                False,
            )
        return '{"ok":true,"action":"botauto_stop"}', 0, False

    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])
    output, returncode, timed_out, _ = runner.run_transport_completion_watchdog(
        execute,
        ["session"],
        100,
        _script(),
        tmp_path,
        {},
        {},
        heartbeat_sec=5,
        no_progress_window_sec=10,
        calibration_native_completion=True,
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert returncode == 0
    assert timed_out is False
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["completion_reason"] == "calibration_pre_scoring_blocker_watchdog"
    assert commands[-1] == ".botauto stop"


def test_native_transport_disconnect_is_not_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    clock = [0.0]
    commands, execute = _transport_for(clock, disconnect=True)
    monkeypatch.setattr(runner.time, "monotonic", lambda: clock[0])

    _output, returncode, timed_out, _ = runner.run_transport_completion_watchdog(
        execute,
        ["session"],
        100,
        _script(),
        tmp_path,
        {},
        {},
        heartbeat_sec=10,
        no_progress_window_sec=30,
        calibration_native_completion=True,
        sleep=lambda seconds: clock.__setitem__(0, clock[0] + seconds),
    )

    assert returncode == 1
    assert timed_out is False
    assert ".botauto calibrate stop" in commands

from __future__ import annotations

import json
import subprocess

import tools.bot_ml.run_live_bot_validation as validation
from tools.bot_ml.run_live_bot_validation import (
    advance_semantic_liveness,
    command_script,
    persist_rolling_heartbeat,
    run_transport_completion_watchdog,
    run_worldserver_completion_watchdog,
)


def _report(*, damage: int | None, alive: int = 10, recovery: str = "none") -> dict:
    live_damage = [] if damage is None else [{
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 4,
        "attempt_epoch": 0,
        "party_damage": damage,
    }]
    return {
        "expected_cohort_id": "default",
        "status": {
            "cohort_id": "default",
            "server_epoch": 41,
            "attempt_id": 7,
            "profile_generation": 3,
            "profile_content_hash": "a" * 64,
            "validation_route": {
                "node_id": "bwd.magmaw.encounter",
                "generation": 4,
            },
            "raid_runtime": {
                "server_epoch": 41,
                "attempt_id": 7,
                "profile_generation": 3,
                "expected_size": 10,
                "alive_size": alive,
                "wipe_state": "wiped" if alive == 0 else "engaged",
                "wipe_generation": 2 if alive == 0 else 0,
                "recovery_state": recovery,
                "recovery_generation": 2 if recovery != "none" else 0,
                "recovery_attempts_remaining": 1 if recovery != "none" else 0,
            },
        },
        "watchdog_state": {
            "progress_total": 6,
            "live_combat_progress": {"health": [], "damage": live_damage},
        },
    }


def _initial_clock() -> dict:
    return {
        "last_progress_total": 6,
        "last_progress_monotonic": 10.0,
        "last_progress_unix": 1010,
        "last_progress_type": "route_party_damage",
        "last_progress_value": 100,
        "last_progress_route_node_id": "bwd.magmaw.encounter",
        "last_progress_route_generation": 4,
        "previous_live_combat_progress": _report(damage=100)["watchdog_state"]["live_combat_progress"],
        "previous_terminal_catchup_progress": {},
    }


def _advance(report: dict, clock: dict, *, now: float, emergency: bool = False) -> tuple[dict, dict]:
    advanced = advance_semantic_liveness(
        report,
        observed_monotonic=now,
        observed_unix=1000 + int(now),
        no_progress_window_sec=300,
        emergency_cap_reached=emergency,
        **clock,
    )
    receipt = advanced.pop("receipt")
    return advanced, receipt


def test_damage_progress_resets_identity_bound_semantic_clock() -> None:
    clock, receipt = _advance(_report(damage=250), _initial_clock(), now=25.0)

    assert clock["last_progress_monotonic"] == 25.0
    assert receipt["last_progress_type"] == "route_party_damage"
    assert receipt["last_progress_value"] == 250
    assert receipt["route_node_id"] == "bwd.magmaw.encounter"
    assert receipt["route_generation"] == 4
    assert receipt["attempt_id"] == 7
    assert receipt["elapsed_no_progress_sec"] == 0.0


def test_139_second_gap_does_not_expire_300_second_window() -> None:
    _clock, receipt = _advance(_report(damage=100), _initial_clock(), now=149.0)

    assert receipt["elapsed_no_progress_sec"] == 139.0
    assert receipt["remaining_no_progress_sec"] == 161.0
    assert receipt["semantic_progress_expired"] is False


def test_recovery_then_resumed_damage_records_new_progress() -> None:
    clock, recovery = _advance(
        _report(damage=None, alive=0, recovery="release_resurrection_pending"),
        _initial_clock(),
        now=149.0,
    )
    assert recovery["alive_count"] == 0
    assert recovery["recovery_generation"] == 2
    assert recovery["recovery_budget_remaining"] == 1

    clock, _first_resumed = _advance(_report(damage=250), clock, now=160.0)
    clock, resumed = _advance(_report(damage=300), clock, now=165.0)
    assert resumed["last_progress_at_unix"] == 1165
    assert resumed["last_progress_value"] == 300
    assert resumed["elapsed_no_progress_sec"] == 0.0


def test_semantic_expiry_and_emergency_cap_are_distinct() -> None:
    _clock, expired = _advance(_report(damage=100), _initial_clock(), now=310.0)
    assert expired["semantic_progress_expired"] is True
    assert expired["emergency_cap_reached"] is False
    assert expired["remaining_no_progress_sec"] == 0.0
    assert expired["emergency_cap_interrupted_recent_progress_or_recovery"] is False

    _clock, capped = _advance(
        _report(damage=100), _initial_clock(), now=149.0, emergency=True
    )
    assert capped["semantic_progress_expired"] is False
    assert capped["emergency_cap_reached"] is True
    assert capped["emergency_cap_interrupted_recent_progress_or_recovery"] is True


def test_compact_heartbeat_and_latest_retain_only_liveness_receipt(tmp_path) -> None:
    _clock, receipt = _advance(_report(damage=250), _initial_clock(), now=25.0)
    heartbeat = {
        "heartbeat_index": 3,
        "heartbeat_generated_at_unix": 1025,
        "semantic_liveness": receipt,
    }

    persist_rolling_heartbeat(tmp_path, heartbeat)

    stream_row = json.loads((tmp_path / "heartbeat_events.jsonl").read_text())
    latest = json.loads((tmp_path / "latest.json").read_text())
    report = json.loads((tmp_path / "report.json").read_text())
    assert stream_row["semantic_liveness"] == receipt
    assert latest["semantic_liveness"] == receipt
    assert report["semantic_liveness"] == receipt
    assert "status" not in stream_row
    assert "diagnosis" not in stream_row
    assert "trace" not in stream_row


def test_transport_heartbeat_command_timeout_persists_final_receipt(tmp_path) -> None:
    def execute_command(_command: str, _remaining: int) -> tuple[str, int, bool]:
        return "", 124, True

    _output, returncode, timed_out, _command = run_transport_completion_watchdog(
        execute_command,
        ["SOAP", "local"],
        30,
        command_script(selector="all", trace_limit=1, start=False, stop=False),
        tmp_path,
        {},
        {"scenario_id": "blackwing_descent_10n_magmaw_diagnostic"},
        heartbeat_sec=1,
        no_progress_window_sec=300,
        sleep=lambda _seconds: None,
    )

    report = json.loads((tmp_path / "report.json").read_text())
    assert (returncode, timed_out) == (124, True)
    assert report["semantic_liveness"]["emergency_cap_reached"] is True
    assert report["completion_reason"] == "emergency_wall_clock_timeout"


def test_process_startup_timeout_persists_final_receipt(tmp_path, monkeypatch) -> None:
    fake_worldserver = tmp_path / "fake_worldserver.py"
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\nimport time\ntime.sleep(60)\n",
        encoding="utf-8",
    )
    fake_worldserver.chmod(0o755)
    config = tmp_path / "worldserver.conf"
    config.write_text("", encoding="utf-8")

    def startup_timeout(*_args, **_kwargs):
        raise subprocess.TimeoutExpired([str(fake_worldserver)], 1)

    monkeypatch.setattr(validation, "read_until_console_prompt", startup_timeout)
    _output, returncode, timed_out, _command = run_worldserver_completion_watchdog(
        fake_worldserver,
        config,
        30,
        command_script(selector="all", trace_limit=1, start=False, stop=False),
        tmp_path,
        {},
        {"scenario_id": "blackwing_descent_10n_magmaw_diagnostic"},
        heartbeat_sec=1,
        no_progress_window_sec=300,
    )

    report = json.loads((tmp_path / "report.json").read_text())
    assert (returncode, timed_out) == (124, True)
    assert report["semantic_liveness"]["emergency_cap_reached"] is True
    assert report["completion_reason"] == "emergency_wall_clock_timeout"


def _with_kill(report: dict, *, guid: int = 17379576916926791863, generation: int = 4) -> dict:
    report["status"]["validation_route"]["boss_death_evidence"] = [{
        "result": "confirmed_unit_death", "route_generation": generation, "route_kind": "boss",
        "route_node_id": "bwd.magmaw.encounter", "target_entry": 43296, "target_id": guid,
    }]
    return report


def test_a_confirmed_boss_kill_after_a_wipe_is_progress_by_identity() -> None:
    # Run 6bf52232 (BWD 10N Chimaeron): the respawned boss died 184 s after the last recorded
    # progress; the windowed progress_total (6 here) stayed under the recovery high-water mark,
    # so without an identity-based kill signal the watchdog stopped before the node completed.
    clock = dict(_initial_clock(), last_progress_total=83)
    report = _with_kill(_report(damage=100))
    clock, receipt = _advance(report, clock, now=194.0)
    assert receipt["last_progress_type"] == "boss_kill"
    assert receipt["last_progress_value"] == 43296
    assert receipt["elapsed_no_progress_sec"] == 0.0 and receipt["semantic_progress_expired"] is False
    assert clock["previous_boss_kill_scopes"] == [("bwd.magmaw.encounter", 4, 17379576916926791863, 43296)]

    # The same kill seen again is not new progress; the clock keeps running from the kill.
    clock, again = _advance(_with_kill(_report(damage=100)), clock, now=300.0)
    assert again["last_progress_type"] == "boss_kill" and again["elapsed_no_progress_sec"] == 106.0


def test_boss_kill_scopes_ignore_unconfirmed_rows() -> None:
    route = {"boss_death_evidence": [
        {"result": "confirmed_unit_death", "route_node_id": "n", "route_generation": 2, "target_id": 9,
         "target_entry": 5},
        {"result": "observed", "route_node_id": "n", "route_generation": 2, "target_id": 8, "target_entry": 5},
        {"result": "confirmed_unit_death", "route_node_id": "", "route_generation": 2, "target_id": 7},
        "junk",
    ]}
    assert validation.boss_kill_scopes(route) == [("n", 2, 9, 5)]
    # No kill evidence: nothing changes for runs without a kill (Magmaw, Stonecore, calibration).
    clock, receipt = _advance(_report(damage=100), _initial_clock(), now=149.0)
    assert receipt["last_progress_type"] == "route_party_damage" and clock["previous_boss_kill_scopes"] == []

from __future__ import annotations

import json

from tools.bot_ml.run_live_bot_validation import (
    command_script,
    raid_terminal_watchdog_failure,
    run_transport_completion_watchdog,
    run_worldserver_completion_watchdog,
)


def _report(runtime: dict, *, failure_reason: str = "") -> dict:
    scenario_id = "blackwing_descent_10n_magmaw_diagnostic"
    profile_hash = "a" * 64
    receipt = {
        "attempt_id": 7,
        "server_epoch": 41,
        "scenario_id": scenario_id,
        "runtime_profile": scenario_id,
        "profile_generation": 3,
        "profile_content_hash": profile_hash,
        "group_guid": 501,
        "instance_id": 23,
        "members": [
            {
                "guid": 1000 + index,
                "group_guid": 501,
                "instance_id": 23,
            }
            for index in range(10)
        ],
    }
    return {
        "returncode": 0,
        "timed_out": False,
        "expected_cohort_id": "default",
        "status": {
            "ok": True,
            "action": "botauto_status",
            "active": True,
            "cohort_id": "default",
            "active_bots": 10,
            "target_bots": 10,
            "lease_count": 10,
            "attempt_id": 7,
            "server_epoch": 41,
            "active_profile": scenario_id,
            "profile_generation": 3,
            "profile_content_hash": profile_hash,
            "failure_reason": failure_reason or None,
            "raid_runtime": {
                "active": True,
                "instance_kind": "raid",
                "admission_phase": "active",
                "bot_actions_enabled": True,
                "attempt_id": 7,
                "server_epoch": 41,
                "profile_generation": 3,
                "profile_content_hash": profile_hash,
                "admission_receipt": receipt,
                "expected_size": 10,
                "active_size": 10,
                "provisioned_member_count": 10,
                "roster_complete": True,
                "unique_leases": True,
                "group_guid": 501,
                "instance_id": 23,
                "roster": [
                    {
                        "guid": 1000 + index,
                        "active": True,
                        "lease_owned": True,
                    }
                    for index in range(10)
                ],
                "alive_size": 10,
                "wipe_state": "engaged",
                "wipe_generation": 0,
                "recovery_state": "none",
                **runtime,
            },
        },
        "validation_context": {"scenario_id": scenario_id},
        "evidence": {"manifest_completion_evidence": []},
        "validation_route_manifest": {},
        "completion_reason": "incomplete_evidence",
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
        "attempt_id": 7,
        "server_epoch": 41,
        "scenario_id": "blackwing_descent_10n_magmaw_diagnostic",
    }


def test_all_dead_without_native_unrecoverable_terminal_is_deferred() -> None:
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

    assert terminal is None


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


def test_action_gate_requires_exact_botauto_status_identity() -> None:
    report = _report(
        {"admission_phase": "terminal", "bot_actions_enabled": False},
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )
    report["status"]["action"] = "botauto_diagnose"
    assert raid_terminal_watchdog_failure(report) is None

    report["status"]["action"] = "botauto_status"
    report["status"]["raid_runtime"]["attempt_id"] = 8
    assert raid_terminal_watchdog_failure(report) is None


def test_same_profile_concurrent_cohort_group_or_instance_cannot_terminalize() -> None:
    def terminal_report() -> dict:
        return _report(
            {"admission_phase": "terminal", "bot_actions_enabled": False},
            failure_reason="validation_active_hunter_pet_admission_identity_drift",
        )

    wrong_cohort = terminal_report()
    wrong_cohort["status"]["cohort_id"] = "concurrent"
    assert raid_terminal_watchdog_failure(wrong_cohort) is None

    wrong_group = terminal_report()
    wrong_group["status"]["raid_runtime"]["group_guid"] = 777
    assert raid_terminal_watchdog_failure(wrong_group) is None

    wrong_instance = terminal_report()
    wrong_instance["status"]["raid_runtime"]["instance_id"] = 24
    assert raid_terminal_watchdog_failure(wrong_instance) is None

    wrong_roster = terminal_report()
    wrong_roster["status"]["raid_runtime"]["roster"][0]["guid"] = 9001
    assert raid_terminal_watchdog_failure(wrong_roster) is None


def test_underfilled_or_nonunique_cohort_cannot_terminalize() -> None:
    underfilled = _report(
        {
            "admission_phase": "terminal",
            "bot_actions_enabled": False,
            "active_size": 9,
        },
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )
    assert raid_terminal_watchdog_failure(underfilled) is None

    nonunique = _report(
        {
            "admission_phase": "terminal",
            "bot_actions_enabled": False,
            "unique_leases": False,
        },
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )
    assert raid_terminal_watchdog_failure(nonunique) is None


def test_successful_clear_precedes_later_action_gate_failure() -> None:
    report = _report(
        {"admission_phase": "terminal", "bot_actions_enabled": False},
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )
    report["completion_reason"] = "validation_route_manifest_complete"
    report["validation_route_manifest"] = {
        "routes": [
            {
                "route_node_id": "bwd.magmaw.encounter",
                "route_generation": 4,
                "kind": "boss",
            }
        ]
    }
    scope = {"route_node_id": "bwd.magmaw.encounter", "route_generation": 4}
    report["evidence"].update(
        {
            "manifest_completion_evidence": [scope],
            "route_terminal_evidence": [scope],
            "real_boss_kill_evidence": [scope],
        }
    )

    assert raid_terminal_watchdog_failure(report) is None


def test_incomplete_or_wrong_manifest_completion_does_not_hide_action_gate() -> None:
    report = _report(
        {"admission_phase": "terminal", "bot_actions_enabled": False},
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )
    report["completion_reason"] = "validation_route_manifest_complete"
    report["validation_route_manifest"] = {
        "routes": [
            {
                "route_node_id": "bwd.magmaw.encounter",
                "route_generation": 4,
                "kind": "boss",
            }
        ]
    }
    report["evidence"]["manifest_completion_evidence"] = [
        {"route_node_id": "wrong.node", "route_generation": 4}
    ]

    terminal = raid_terminal_watchdog_failure(report)
    assert terminal is not None
    assert terminal["failure_reason"] == (
        "validation_active_hunter_pet_admission_identity_drift"
    )


def test_terminal_gate_still_captures_and_cleans_up(tmp_path) -> None:
    command_log = tmp_path / "commands.log"
    fake_worldserver = tmp_path / "fake_worldserver.py"
    status_payload = _report(
        {"admission_phase": "terminal", "bot_actions_enabled": False},
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )["status"]
    status_payload.update({"active_bots": 10, "target_bots": 10})
    fake_worldserver.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        f"log = open({str(command_log)!r}, 'a', encoding='utf-8')\n"
        "print('TC> ', flush=True)\n"
        "for line in sys.stdin:\n"
        "    cmd = line.strip()\n"
        "    log.write(cmd + '\\n'); log.flush()\n"
        "    if cmd.startswith('.botauto status'):\n"
        f"        print({json.dumps(json.dumps(status_payload))})\n"
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
    heartbeat = json.loads(
        (output_dir / "heartbeat_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    commands = command_log.read_text(encoding="utf-8").splitlines()
    assert returncode == 0
    assert timed_out is False
    assert report["completion_reason"] == "cohort_action_gate_failure_watchdog"
    assert report["failure_reason"] == "validation_active_hunter_pet_admission_identity_drift"
    assert heartbeat["completion_reason"] == "cohort_action_gate_failure_watchdog"
    assert heartbeat["failure_reason"] == "validation_active_hunter_pet_admission_identity_drift"
    assert any(command.startswith(".botauto diagnose") for command in commands)
    assert any(command.startswith(".botauto trace") for command in commands)
    assert any(command.startswith(".botauto combatlog") for command in commands)
    assert any(command.startswith(".botauto stop") for command in commands)
    assert "server shutdown force 0" in commands


def test_attached_transport_terminal_preserves_cleanup(tmp_path) -> None:
    status_payload = _report(
        {"admission_phase": "terminal", "bot_actions_enabled": False},
        failure_reason="validation_active_hunter_pet_admission_identity_drift",
    )["status"]
    status_payload.update({"active_bots": 10, "target_bots": 10})
    commands: list[str] = []

    def execute(command: str, _timeout: int) -> tuple[str, int, bool]:
        commands.append(command)
        if command.startswith(".botauto status"):
            payload = status_payload
        elif command.startswith(".botauto diagnose"):
            payload = {
                "ok": True,
                "action": "botauto_diagnose",
                "diagnosis_schema_version": 1,
                "bots": [],
            }
        elif command.startswith(".botauto trace"):
            payload = {
                "ok": True,
                "action": "botauto_trace",
                "trace_schema_version": 1,
                "entries": [],
            }
        elif command.startswith(".botauto combatlog"):
            payload = {"ok": True, "action": "botauto_combatlog", "events": []}
        else:
            payload = {"ok": True, "action": "botauto_stop"}
        return json.dumps(payload) + "\n", 0, False

    output_dir = tmp_path / "transport"
    _output, returncode, timed_out, _command = run_transport_completion_watchdog(
        execute,
        ["attached"],
        None,
        command_script(
            selector="all",
            trace_limit=5,
            start=False,
            stop=True,
            exit_server=False,
        ),
        output_dir,
        {},
        {"scenario_id": "blackwing_descent_10n_magmaw_diagnostic"},
        heartbeat_sec=1,
        no_progress_window_sec=180,
        validation_route_manifest={
            "schema": "bot_live_validation_route_manifest_v1",
            "route_count": 4,
        },
        sleep=lambda _seconds: None,
    )

    report = json.loads((output_dir / "report.json").read_text(encoding="utf-8"))
    heartbeat = json.loads(
        (output_dir / "heartbeat_events.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()[0]
    )
    assert returncode == 0
    assert timed_out is False
    assert report["completion_reason"] == "cohort_action_gate_failure_watchdog"
    assert heartbeat["completion_reason"] == "cohort_action_gate_failure_watchdog"
    assert heartbeat["failure_reason"] == "validation_active_hunter_pet_admission_identity_drift"
    assert any(command.startswith(".botauto diagnose") for command in commands)
    assert any(command.startswith(".botauto trace") for command in commands)
    assert any(command.startswith(".botauto combatlog") for command in commands)
    assert any(command.startswith(".botauto stop") for command in commands)
    assert not any(command.startswith("server ") for command in commands)

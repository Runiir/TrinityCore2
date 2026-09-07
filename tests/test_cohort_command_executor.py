import json

import pytest

from tools.bot_ml.run_live_bot_validation import CohortCommandExecutor, require_serial_cohort_registry


@pytest.mark.parametrize("command", [
    ".server exit", "server exit", ".botauto stop", ".botauto stop witness",
    ".botauto ownership", ".botauto unknown target", "",
    ".botauto status target\n.server exit",
    ".botauto status target\r.botauto stop witness",
    ".botauto status target\x00",
])
def test_worker_rejects_unscoped_commands_before_transport(command):
    calls = []
    executor = CohortCommandExecutor(lambda *args: calls.append(args), "target")
    with pytest.raises(RuntimeError, match="forbidden"):
        executor.run(command)
    assert calls == []
    assert executor.commands == []


def test_addressed_cleanup_reaches_only_owned_cohort():
    calls = []

    def transport(command, timeout):
        calls.append(command)
        if command == ".botauto cohorts":
            return '{"action":"botauto_cohorts","ok":true,"cohorts":[{"cohort_id":"target"}]}', 0, False
        return '{"action":"botauto_stop","cohort_id":"target","ok":true}', 0, False

    executor = CohortCommandExecutor(transport, "target")
    assert executor.stop()[1:] == (0, False)
    assert calls == [".botauto cohorts", ".botauto stop target"]


def test_foreign_response_is_rejected():
    def transport(command, timeout):
        if command == ".botauto cohorts":
            return '{"action":"botauto_cohorts","ok":true,"cohorts":[{"cohort_id":"target"}]}', 0, False
        return '{"action":"botauto_status","cohort_id":"witness"}', 0, False

    executor = CohortCommandExecutor(
        transport, "target",
    )
    with pytest.raises(RuntimeError, match="cross-cohort payload"):
        executor.run(executor.status_command)


@pytest.mark.parametrize("verb", ["start", "prepare", "diagnose", "trace", "calibrate", "stop"])
def test_unknown_cohort_cannot_trigger_native_legacy_fallback(verb):
    calls = []

    def transport(command, timeout):
        calls.append(command)
        return '{"action":"botauto_cohorts","ok":true,"cohorts":[{"cohort_id":"witness"}]}', 0, False

    executor = CohortCommandExecutor(transport, "missing")
    with pytest.raises(RuntimeError, match="legacy fallback forbidden"):
        executor.run(f".botauto {verb} missing")
    assert calls == [".botauto cohorts"]


@pytest.mark.parametrize("registry", [{}, {"cohorts": [None]},
    {"cohorts": [{"cohort_id": "witness", "active": True}]},
    {"cohorts": [{"cohort_id": "target", "active": 1}]}])
def test_serial_runner_rejects_foreign_active_or_unknown_registry(registry):
    with pytest.raises(RuntimeError, match="cannot share"):
        require_serial_cohort_registry(registry, "target")


def test_serial_runner_can_use_multicohort_capable_server_alone():
    require_serial_cohort_registry({"cohorts": [
        {"cohort_id": "target", "active": True},
        {"cohort_id": "witness", "active": False},
    ]}, "target")


def test_exclusive_attempt_rejects_overlap_but_can_clean_its_own_cohort():
    calls = []
    registry = {"action": "botauto_cohorts", "ok": True, "cohorts": [
        {"cohort_id": "target", "active": True},
        {"cohort_id": "witness", "active": False},
    ]}

    def transport(command, timeout):
        calls.append(command)
        if command == ".botauto cohorts":
            return json.dumps(registry), 0, False
        return '{"ok":true,"cohort_id":"target","action":"botauto_status"}', 0, False

    executor = CohortCommandExecutor(transport, "target", exclusive=True)
    executor.run(executor.status_command)
    registry["cohorts"][1]["active"] = True
    with pytest.raises(RuntimeError, match="cannot share"):
        executor.run(executor.status_command)
    assert executor.serial_registry_failed
    assert executor.serial_registry_checks == 1
    assert calls.count(executor.status_command) == 1
    executor.exclusive = False
    executor.stop()
    assert calls[-1] == ".botauto stop target"


@pytest.mark.parametrize("session,expected", [
    ({"max_active_cohorts": 1}, True),
    ({"max_active_cohorts": 2}, False),
    ({"max_active_cohorts": True}, False),
    ({"max_active_cohorts": 2, "serial_execution_verified": True, "serial_registry_checks": 3}, True),
    ({"max_active_cohorts": 2, "serial_execution_verified": False, "serial_registry_checks": 3}, False),
    ({"max_active_cohorts": 2, "serial_execution_verified": True, "serial_registry_checks": 0}, False),
])
def test_calibration_admission_distinguishes_capacity_from_execution(session, expected):
    from tools.bot_ml.build_phase8_all_spec_calibration_contract import serial_execution_verified
    assert serial_execution_verified(session) is expected

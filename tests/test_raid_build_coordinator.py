from __future__ import annotations

import copy
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import pytest

from tools.raid_program import queued_build as qb


ROOT = Path(__file__).resolve().parents[1]
POLICY_PATH = ROOT / "experiments/configs/cata_raid_build_resource_policy_v1.json"
SCRIPT = ROOT / "tools/raid_program/queued_build.py"


def policy() -> dict:
    return json.loads(POLICY_PATH.read_text(encoding="utf-8"))


def state_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> qb.Paths:
    monkeypatch.setenv("TRINITY_RAID_BUILD_TESTING", "1")
    monkeypatch.setenv("TRINITY_RAID_BUILD_STATE_DIR_OVERRIDE", str(tmp_path / "state"))
    return qb.Paths.for_worktree(ROOT)


def synthetic_snapshot(*, available_gib: float = 24.0, load: float = 0.1) -> dict:
    return {
        "captured_at_utc": qb.utc_now(),
        "memory_total_bytes": 31 * 1024**3,
        "memory_available_bytes": int(available_gib * 1024**3),
        "swap_used_bytes": 0,
        "memory_psi_some_avg10": 0.0,
        "memory_psi_full_avg10": 0.0,
        "load_average_1m": load,
        "load_average_5m": load,
        "load_average_15m": load,
        "filesystem_available_bytes": 50 * 1024**3,
    }


def wait_for(predicate, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition did not become true before timeout")


def test_policy_preserves_host_reserve_and_caps_fanout() -> None:
    frozen = policy()
    assert frozen["coordination"]["maximum_active_heavyweight_leases"] == 1
    assert frozen["parallelism"]["maximum_compiler_jobs"] == 3
    assert frozen["parallelism"]["maximum_linker_jobs"] == 1
    assert qb.reserve_bytes(frozen, synthetic_snapshot()) == int(31 * 0.30 * 1024**3)
    assert qb.pressure_reasons(frozen, synthetic_snapshot(available_gib=9.0)) == [
        "memory_reserve"
    ]
    qb.validate_command(["cmake", "--build", "build", "--parallel", "3"], 3)
    with pytest.raises(qb.CoordinatorError):
        qb.validate_command(["cmake", "--build", "build", "--parallel"], 3)
    with pytest.raises(qb.CoordinatorError):
        qb.validate_command(["ninja", "-j12"], 3)
    with pytest.raises(qb.CoordinatorError):
        qb.validate_command(["bash", "-c", "make -j12"], 3)


def test_fifo_single_admission_and_cancel_waiter(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state_paths(tmp_path, monkeypatch)
    first = qb.new_ticket(ROOT, "synthetic", [sys.executable, "-c", "pass"])
    second = qb.new_ticket(ROOT, "synthetic", [sys.executable, "-c", "pass"])
    qb.enqueue(paths, first)
    qb.enqueue(paths, second)
    assert first["queue_sequence"] == 1
    assert second["queue_sequence"] == 2

    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    admitted, _, reasons = qb.try_admit(paths, policy(), second["ticket_id"], ROOT)
    assert admitted is False
    assert reasons == ["fifo_wait"]
    admitted, _, reasons = qb.try_admit(paths, policy(), first["ticket_id"], ROOT)
    assert admitted is True
    assert reasons == []
    assert qb.cancel_ticket(paths, second["ticket_id"])["state"] == "canceled"
    report = qb.status(paths, recover=False)
    assert report["active"] == first["ticket_id"]
    assert report["queue"] == [first["ticket_id"]]


def test_stale_recovery_is_pid_reuse_safe_and_cleans_child_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state_paths(tmp_path, monkeypatch)
    child = subprocess.Popen(
        [sys.executable, "-c", "import time; time.sleep(30)"], start_new_session=True
    )
    ticket = qb.new_ticket(ROOT, "synthetic")
    qb.enqueue(paths, ticket)
    with qb.locked_state(paths) as state:
        state["active"] = ticket["ticket_id"]
        stored = state["tickets"][ticket["ticket_id"]]
        stored["state"] = "active"
        stored["lease_owner"] = {"pid": os.getpid(), "start_ticks": -1}
        stored["child"] = qb.process_identity(child.pid) | {"pgid": child.pid}
    events = qb.status(paths, recover=True)["recovery_events"]
    assert events[0]["classification"] == "stale_lease_recovered"
    assert events[0]["child_process_group_terminated"] is True
    child.wait(timeout=3)
    assert child.returncode in {-signal.SIGTERM, -signal.SIGKILL}

    reuse_ticket = qb.new_ticket(ROOT, "synthetic")
    qb.enqueue(paths, reuse_ticket)
    with qb.locked_state(paths) as state:
        state["active"] = reuse_ticket["ticket_id"]
        stored = state["tickets"][reuse_ticket["ticket_id"]]
        stored["state"] = "active"
        stored["lease_owner"] = {"pid": os.getpid(), "start_ticks": -1}
        stored["child"] = {
            "pid": os.getpid(),
            "start_ticks": -1,
            "pgid": os.getpid(),
        }
    reuse_event = qb.status(paths, recover=True)["recovery_events"][0]
    assert reuse_event["child_process_group_terminated"] is False


def test_killed_cli_lease_owner_is_recovered_without_orphan_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state_paths(tmp_path, monkeypatch)
    environment = dict(os.environ)
    runner = subprocess.Popen(
        [
            sys.executable,
            str(SCRIPT),
            "--worktree",
            str(ROOT),
            "--policy",
            str(POLICY_PATH),
            "run",
            "--resource-class",
            "synthetic",
            "--",
            sys.executable,
            "-c",
            "import time; time.sleep(30)",
        ],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    wait_for(lambda: qb.status(paths, recover=False)["active"] is not None)
    active = qb.status(paths, recover=False)
    ticket_id = active["active"]
    child_identity = active["tickets"][ticket_id]["child"]
    runner.kill()
    runner.wait(timeout=3)
    recovered = qb.status(paths, recover=True)
    assert recovered["recovery_events"][0]["classification"] == "stale_lease_recovered"
    wait_for(lambda: not qb.same_process(child_identity["pid"], child_identity["start_ticks"]))
    assert recovered["active"] is None
    assert recovered["queue"] == []


def test_synthetic_pressure_breach_aborts_complete_process_group(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state_paths(tmp_path, monkeypatch)
    frozen = copy.deepcopy(policy())
    frozen["admission_thresholds"]["sample_interval_seconds"] = 0.01
    frozen["admission_thresholds"]["sustained_unsafe_sample_count"] = 2
    frozen["coordination"]["termination_grace_seconds"] = 0.2
    ticket = qb.new_ticket(ROOT, "synthetic", [sys.executable, "-c", "pass"])
    qb.enqueue(paths, ticket)
    with qb.locked_state(paths) as state:
        state["active"] = ticket["ticket_id"]
        stored = state["tickets"][ticket["ticket_id"]]
        stored["state"] = "active"
        stored["lease_owner"] = qb.process_identity(os.getpid())

    descendant_pid_path = tmp_path / "descendant.pid"
    code, classification, samples, reasons = qb.execute_process(
        [
            sys.executable,
            "-c",
            "import pathlib,subprocess,sys,time; p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); pathlib.Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(30)",
            str(descendant_pid_path),
        ],
        ROOT,
        qb.coordinated_environment(frozen, paths, ticket["ticket_id"]),
        paths.logs / "pressure.log",
        frozen,
        paths,
        ticket["ticket_id"],
        snapshot_provider=lambda _: synthetic_snapshot(available_gib=1.0),
    )
    assert code < 0
    assert classification == "build_resource_abort"
    assert len(samples) >= 2
    assert "memory_reserve" in reasons
    child_identity = qb.status(paths, recover=False)["tickets"][ticket["ticket_id"]]["child"]
    assert qb.same_process(child_identity["pid"], child_identity["start_ticks"]) is False
    descendant_pid = int(descendant_pid_path.read_text(encoding="utf-8"))
    with pytest.raises(ProcessLookupError):
        os.kill(descendant_pid, 0)


def test_two_cli_runs_share_one_fifo_lease_and_emit_valid_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state_paths(tmp_path, monkeypatch)
    first_receipt = tmp_path / "first.json"
    second_receipt = tmp_path / "second.json"
    environment = dict(os.environ)
    common = [
        sys.executable,
        str(SCRIPT),
        "--worktree",
        str(ROOT),
        "--policy",
        str(POLICY_PATH),
        "run",
        "--resource-class",
        "synthetic",
    ]
    sleeper = ["--", sys.executable, "-c", "import time; time.sleep(0.35)", "secret-not-retained"]
    first = subprocess.Popen(
        common + ["--receipt", str(first_receipt)] + sleeper,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    wait_for(lambda: qb.status(paths, recover=False)["active"] is not None)
    second = subprocess.Popen(
        common + ["--receipt", str(second_receipt)] + sleeper,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    first_stdout, first_stderr = first.communicate(timeout=10)
    second_stdout, second_stderr = second.communicate(timeout=10)
    assert (first.returncode, first_stderr) == (0, "")
    assert (second.returncode, second_stderr) == (0, "")
    assert first_stdout and second_stdout

    first_data = json.loads(first_receipt.read_text(encoding="utf-8"))
    second_data = json.loads(second_receipt.read_text(encoding="utf-8"))
    assert first_data["queue_sequence"] < second_data["queue_sequence"]
    assert datetime.fromisoformat(first_data["ended_at_utc"].replace("Z", "+00:00")) <= datetime.fromisoformat(
        second_data["admitted_at_utc"].replace("Z", "+00:00")
    )
    for receipt in (first_data, second_data):
        report = qb.verify_receipt(
            first_receipt if receipt is first_data else second_receipt,
            policy(),
            allow_test_mode=True,
        )
        assert report["valid"] is True
        assert receipt["classification"] == "success"
        assert receipt["compiler_job_ceiling"] == 3
        assert receipt["linker_job_ceiling"] == 1
        assert receipt["command_arguments_retained"] is False
        assert "secret-not-retained" not in json.dumps(receipt)
        with pytest.raises(qb.CoordinatorError):
            qb.verify_receipt(
                first_receipt if receipt is first_data else second_receipt,
                policy(),
            )
    final = qb.status(paths, recover=False)
    assert final["active"] is None
    assert final["queue"] == []


def test_cmake_integration_applies_compile_and_link_controls() -> None:
    cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "TRINITY_RAID_BUILD_COORDINATED" in cmake
    assert "CMAKE_JOB_POOL_COMPILE" in cmake
    assert "CMAKE_JOB_POOL_LINK" in cmake
    assert "RULE_LAUNCH_LINK" in cmake
    assert 'CMAKE_CXX_ARCHIVE_CREATE "<CMAKE_AR> qcT' in cmake
    assert "thin intermediate archives enabled" in cmake


def test_all_registered_worktrees_share_git_common_queue_state() -> None:
    main_common = qb.git_common_dir(ROOT)
    output = qb.git_output(ROOT, "worktree", "list", "--porcelain")
    worktrees = [Path(line.split(" ", 1)[1]) for line in output.splitlines() if line.startswith("worktree ")]
    assert worktrees
    assert all(qb.git_common_dir(worktree) == main_common for worktree in worktrees)

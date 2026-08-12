from __future__ import annotations

import copy
import base64
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
from tools.raid_program import privileged_build_attestation as pba


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


def initialized_git_repo(path: Path) -> Path:
    path.mkdir()
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.email", "tests@example.invalid"], check=True)
    subprocess.run(["git", "-C", str(path), "config", "user.name", "Raid Tests"], check=True)
    (path / "tracked.txt").write_text("frozen\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(path), "add", "tracked.txt"], check=True)
    subprocess.run(["git", "-C", str(path), "commit", "-qm", "fixture"], check=True)
    return path


def configured_git_repo(path: Path, flags: str = "-O1 -DNDEBUG") -> Path:
    repo = initialized_git_repo(path)
    (repo / ".gitignore").write_text("build/\n", encoding="utf-8")
    (repo / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.16)\n"
        "project(raid_fixture CXX)\n"
        "add_executable(raid_fixture main.cpp)\n"
        "file(MAKE_DIRECTORY ${CMAKE_BINARY_DIR}/src/server/worldserver)\n"
        "add_custom_target(worldserver COMMAND ${CMAKE_COMMAND} -E copy /bin/true "
        "${CMAKE_BINARY_DIR}/src/server/worldserver/worldserver)\n",
        encoding="utf-8",
    )
    (repo / "main.cpp").write_text("int main() { return 0; }\n", encoding="utf-8")
    cache = repo / "build/CMakeCache.txt"
    cache.parent.mkdir(parents=True)
    cache.write_text(
        "\n".join(
            (
                "CMAKE_BUILD_TYPE:STRING=Release",
                "CMAKE_GENERATOR:INTERNAL=Unix Makefiles",
                "CMAKE_MAKE_PROGRAM:FILEPATH=/usr/bin/gmake",
                "CMAKE_EXPORT_COMPILE_COMMANDS:BOOL=ON",
                "CMAKE_CXX_FLAGS:STRING=",
                f"CMAKE_CXX_FLAGS_RELEASE:STRING={flags}",
                "CMAKE_CXX_COMPILER:FILEPATH=/usr/bin/c++",
                "CMAKE_CXX_COMPILER_LAUNCHER:STRING=",
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION:BOOL=OFF",
                "CMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE:BOOL=OFF",
                "UNITY_BUILDS:BOOL=OFF",
                "USE_COREPCH:BOOL=OFF",
                "USE_SCRIPTPCH:BOOL=OFF",
                "WITH_COREDEBUG:BOOL=OFF",
                "",
            )
        ),
        encoding="utf-8",
    )
    (repo / "build/compile_commands.json").write_text(
        json.dumps([{
            "directory": str(repo / "build"),
            "command": "/usr/bin/c++ -O1 -DNDEBUG -c main.cpp",
            "file": str(repo / "main.cpp"),
        }]),
        encoding="utf-8",
    )
    (repo / "build/Makefile").write_text("# generated fixture\n", encoding="utf-8")
    subprocess.run(
        ["git", "-C", str(repo), "add", ".gitignore", "CMakeLists.txt", "main.cpp"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "commit", "-qm", "freeze cmake cache"], check=True)
    return repo


def seed_configure_lineage(
    repo: Path,
    frozen: dict,
    tmp_path: Path,
) -> dict:
    command = [
        "/usr/bin/cmake", "-S", ".", "-B", "build", "-G", "Unix Makefiles"
    ]
    command.extend(f"-D{key}={value}" for key, value in qb.expected_build_configuration(frozen).items())
    code, receipt = qb.run_ticket(
        repo,
        frozen,
        "configure",
        command,
        None,
        tmp_path / "configure-receipt.json",
        2.0,
    )
    assert code == 0
    assert receipt["classification"] == "success"
    return receipt


def exact_worldserver_build(frozen: dict) -> list[str]:
    return [
        frozen["mechanical_controls"]["cmake_executable"],
        "--build", "build", "--target", "worldserver", "--parallel",
        str(frozen["parallelism"]["maximum_compiler_jobs"]),
    ]


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
        snapshot_provider=lambda _: synthetic_snapshot(
            available_gib=1.0 if descendant_pid_path.exists() else 24.0
        ),
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


def test_source_drift_before_admission_aborts_without_launching_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    paths = state_paths(tmp_path, monkeypatch)
    repo = initialized_git_repo(tmp_path / "repo")
    marker = tmp_path / "child-launched"
    command = [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).touch()", str(marker)]
    ticket = qb.new_ticket(repo, "synthetic", command)
    qb.enqueue(paths, ticket)
    (repo / "tracked.txt").write_text("changed before admission\n", encoding="utf-8")
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])

    code, receipt = qb.run_ticket(
        repo, policy(), "synthetic", command, ticket["ticket_id"],
        tmp_path / "preadmission.json", 2.0,
    )
    assert code == 76
    assert receipt["classification"] == "build_provenance_abort"
    assert "source_identity_changed_or_dirty_before_admission" in receipt["provenance_reasons"]
    assert marker.exists() is False


def test_successful_command_that_mutates_source_is_provenance_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = initialized_git_repo(tmp_path / "repo")
    receipt_path = tmp_path / "completion.json"
    command = [
        sys.executable, "-c",
        "import pathlib; pathlib.Path('tracked.txt').write_text('changed during command\\n')",
    ]
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])

    code, receipt = qb.run_ticket(
        repo, policy(), "synthetic", command, None, receipt_path, 2.0,
    )
    assert code == 76
    assert receipt["schema_version"] == 2
    assert receipt["classification"] == "build_provenance_abort"
    assert receipt["source_identity"]["request"] != receipt["source_identity"]["completion"]
    assert "source_identity_changed_or_dirty_before_completion" in receipt["provenance_reasons"]


def test_legacy_receipt_is_historical_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = initialized_git_repo(tmp_path / "repo")
    receipt_path = tmp_path / "receipt.json"
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    code, receipt = qb.run_ticket(
        repo, policy(), "synthetic", [sys.executable, "-c", "pass"], None,
        receipt_path, 2.0,
    )
    assert code == 0
    forged = copy.deepcopy(receipt)
    forged["source_identity"]["completion"]["tree"] = "f" * 40
    forged.pop("receipt_sha256")
    forged["receipt_sha256"] = qb.sha256_bytes(qb.canonical_json(forged))
    receipt_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="differs from coordinator canonical record"):
        qb.verify_receipt(receipt_path, policy(), allow_test_mode=True)

    receipt["schema_version"] = 1
    receipt.pop("receipt_sha256")
    receipt["receipt_sha256"] = qb.sha256_bytes(qb.canonical_json(receipt))
    receipt_path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="differs from coordinator canonical record"):
        qb.verify_receipt(receipt_path, policy(), allow_test_mode=True)


def test_v8_rejects_wrong_effective_cmake_settings_before_child_launch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo", flags="-O3 -DNDEBUG")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    command = exact_worldserver_build(frozen)
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])

    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", command, None,
        tmp_path / "wrong-cache.json", 2.0,
    )
    assert code == 76
    assert receipt["classification"] == "build_provenance_abort"
    assert receipt["build_configuration"]["request"]["matches_policy"] is False
    assert "build_configuration_or_configure_lineage_missing_before_admission" in receipt[
        "provenance_reasons"
    ]


def test_v8_matching_cache_without_coordinated_configure_lineage_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    command = exact_worldserver_build(frozen)
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])

    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", command, None,
        tmp_path / "missing-lineage.json", 2.0,
    )
    assert code == 76
    assert receipt["classification"] == "build_provenance_abort"
    assert receipt["configure_lineage"] is None
    assert "build_configuration_or_configure_lineage_missing_before_admission" in receipt[
        "provenance_reasons"
    ]


def test_v8_receipt_binds_effective_cmake_settings_and_current_cache(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    binary = repo / "build/src/server/worldserver/worldserver"
    command = exact_worldserver_build(frozen)
    receipt_path = tmp_path / "bound-cache.json"
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    configure_receipt = seed_configure_lineage(repo, frozen, tmp_path)

    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", command, None, receipt_path, 2.0,
    )
    assert code == 0
    assert receipt["classification"] == "success"
    assert receipt["configure_lineage"]["receipt_sha256"] == configure_receipt["receipt_sha256"]
    assert receipt["build_configuration_stable"] is True
    snapshots = receipt["build_configuration"]
    assert all(
        snapshots[stage]["settings"] == qb.expected_build_configuration(frozen)
        for stage in ("request", "admission", "completion")
    )
    assert qb.verify_receipt(receipt_path, frozen, allow_test_mode=True)["valid"] is True

    cache = repo / "build/CMakeCache.txt"
    cache.write_text(cache.read_text().replace("-O1", "-O3"), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="current effective CMake settings"):
        qb.verify_receipt(receipt_path, frozen, allow_test_mode=True)


def test_v8_full_cache_drift_during_build_is_provenance_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    command = exact_worldserver_build(frozen)
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    seed_configure_lineage(repo, frozen, tmp_path)

    def mutate_cache(*_args):
        cache = repo / "build/CMakeCache.txt"
        cache.write_text(cache.read_text() + "UNSELECTED_SETTING:STRING=changed\n")
        return 0, "success", [synthetic_snapshot()], []

    monkeypatch.setattr(qb, "execute_process", mutate_cache)

    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", command, None,
        tmp_path / "cache-drift.json", 2.0,
    )
    assert code == 76
    assert receipt["classification"] == "build_provenance_abort"
    assert receipt["build_configuration"]["request"]["settings"] == receipt[
        "build_configuration"
    ]["completion"]["settings"]
    assert receipt["build_configuration"]["request"]["cache_sha256"] != receipt[
        "build_configuration"
    ]["completion"]["cache_sha256"]
    assert "build_configuration_changed_or_mismatched_at_completion" in receipt[
        "provenance_reasons"
    ]


def test_v8_generated_build_graph_drift_is_provenance_abort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    seed_configure_lineage(repo, frozen, tmp_path)
    flags = repo / "build/CMakeFiles/raid_fixture.dir/flags.make"
    assert flags.is_file()
    command = exact_worldserver_build(frozen)

    def mutate_graph(*_args):
        flags.write_text(flags.read_text().replace("-O1", "-O3"))
        return 0, "success", [synthetic_snapshot()], []

    monkeypatch.setattr(qb, "execute_process", mutate_graph)
    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", command, None,
        tmp_path / "graph-drift.json", 2.0,
    )
    assert code == 76
    assert receipt["classification"] == "build_provenance_abort"
    assert receipt["build_configuration"]["request"]["cache_sha256"] == receipt[
        "build_configuration"
    ]["completion"]["cache_sha256"]
    assert receipt["build_configuration"]["request"]["build_graph"]["manifest_sha256"] != receipt[
        "build_configuration"
    ]["completion"]["build_graph"]["manifest_sha256"]


def test_fabricated_never_enqueued_receipt_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    binary = repo / "build/src/server/worldserver/worldserver"
    command = exact_worldserver_build(frozen)
    receipt_path = tmp_path / "authentic.json"
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    seed_configure_lineage(repo, frozen, tmp_path)
    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", command, None, receipt_path, 2.0,
    )
    assert code == 0

    forged = copy.deepcopy(receipt)
    forged["ticket_id"] = "raid-build-never-enqueued"
    forged.pop("receipt_sha256")
    forged["receipt_sha256"] = qb.sha256_bytes(qb.canonical_json(forged))
    forged_path = tmp_path / "forged.json"
    forged_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="canonical receipt record is missing"):
        qb.verify_receipt(forged_path, frozen, allow_test_mode=True)


def test_v8_configure_command_must_explicitly_bind_every_effective_setting() -> None:
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    controls = frozen["mechanical_controls"]
    command = [
        controls["cmake_executable"], "-S", ".", "-B", "build", "-G",
        controls["cmake_generator"],
        *(f"-D{key}={value}" for key, value in qb.expected_build_configuration(frozen).items()),
    ]
    qb.validate_command(command, 1, resource_class="configure", policy=frozen)
    with pytest.raises(qb.CoordinatorError, match="CMAKE_CXX_FLAGS_RELEASE"):
        qb.validate_command(
            [value for value in command if not value.startswith("-DCMAKE_CXX_FLAGS_RELEASE=")],
            1,
            resource_class="configure",
            policy=frozen,
        )
    for forbidden_override in (
        "-DCMAKE_INTERPROCEDURAL_OPTIMIZATION_RELEASE=ON",
        "-DCMAKE_CXX_COMPILER_LAUNCHER=/tmp/inject-o3",
    ):
        with pytest.raises(qb.CoordinatorError):
            qb.validate_command(
                [
                    value
                    for value in command
                    if not value.startswith(forbidden_override.split("=", 1)[0] + "=")
                ] + [forbidden_override],
                1,
                resource_class="configure",
                policy=frozen,
            )
    fake_cmake = Path("/tmp/cmake")
    with pytest.raises(qb.CoordinatorError, match="frozen CMake executable"):
        qb.validate_command(
            [str(fake_cmake), *command[1:]], 1,
            resource_class="configure", policy=frozen,
        )
    with pytest.raises(qb.CoordinatorError, match="exact policy-owned"):
        qb.validate_command(
            [*command, "-N"], 1,
            resource_class="configure", policy=frozen,
        )


def test_v8_worldserver_command_and_environment_are_policy_owned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    qb.validate_command(
        exact_worldserver_build(frozen), 1,
        resource_class="worldserver_build", policy=frozen,
    )
    with pytest.raises(qb.CoordinatorError, match="exact policy invocation"):
        qb.validate_command(
            ["/usr/bin/cp", "/bin/true", "build/src/server/worldserver/worldserver"],
            1, resource_class="worldserver_build", policy=frozen,
        )
    paths = qb.Paths.for_worktree(ROOT)
    monkeypatch.setenv("COMPILER_PATH", str(tmp_path / "attacker"))
    monkeypatch.setenv("LD_PRELOAD", str(tmp_path / "inject.so"))
    monkeypatch.setenv("MAKEFILES", str(tmp_path / "inject.mk"))
    monkeypatch.setenv("GNUMAKEFLAGS", "--eval=fixture")
    monkeypatch.setenv("LD_LIBRARY_PATH", str(tmp_path / "lib"))
    environment = qb.coordinated_environment(
        frozen, paths, "fixture-ticket"
    )
    assert "COMPILER_PATH" not in environment
    assert "LD_PRELOAD" not in environment
    assert "MAKEFILES" not in environment
    assert "GNUMAKEFLAGS" not in environment
    assert "LD_LIBRARY_PATH" not in environment
    assert environment["PATH"] == qb.SAFE_BUILD_PATH
    assert environment["LANG"] == environment["LC_ALL"] == "C.UTF-8"
    assert qb.toolchain_snapshot(frozen)["matches_policy"] is True


def test_privileged_ed25519_attestation_binds_exact_success_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_paths(tmp_path, monkeypatch)
    repo = configured_git_repo(tmp_path / "repo")
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(frozen), encoding="utf-8")
    monkeypatch.setattr(qb, "resource_snapshot", lambda _: synthetic_snapshot())
    monkeypatch.setattr(qb, "find_live_validation_processes", lambda *_args, **_kwargs: [])
    seed_configure_lineage(repo, frozen, tmp_path)
    receipt_path = tmp_path / "build-receipt.json"
    code, receipt = qb.run_ticket(
        repo, frozen, "worldserver_build", exact_worldserver_build(frozen), None,
        receipt_path, 2.0,
    )
    assert code == 0

    private_key = tmp_path / "private.pem"
    public_key = tmp_path / "public.pem"
    subprocess.run(
        ["/usr/bin/openssl", "genpkey", "-algorithm", "ED25519", "-out", str(private_key)],
        check=True, capture_output=True,
    )
    subprocess.run(
        ["/usr/bin/openssl", "pkey", "-in", str(private_key), "-pubout", "-out", str(public_key)],
        check=True, capture_output=True,
    )
    service_config = tmp_path / "service.json"
    service = {
        "schema_version": 1,
        "service_id": "test-privileged-service",
        "state": "provisioned",
        "key_id": "test-ed25519-key-1",
        "public_key_path": str(public_key),
        "public_key_sha256": qb.sha256_file(public_key),
        "minimum_ledger_sequence": 1,
    }
    service_config.write_text(json.dumps(service), encoding="utf-8")
    attestation = {
        "schema_version": 1,
        "service_id": service["service_id"],
        "key_id": service["key_id"],
        "ledger_sequence": 1,
        "ledger_record_id": "test-ledger-record-0001",
        "signed_at_utc": qb.utc_now(),
    }
    payload = pba.signed_payload(receipt, attestation)
    payload_path = tmp_path / "payload.json"
    signature_path = tmp_path / "signature.bin"
    payload_path.write_bytes(qb.canonical_json(payload))
    subprocess.run(
        [
            "/usr/bin/openssl", "pkeyutl", "-sign", "-inkey", str(private_key),
            "-rawin", "-in", str(payload_path), "-out", str(signature_path),
        ],
        check=True, capture_output=True,
    )
    attestation["payload"] = payload
    attestation["payload_sha256"] = qb.sha256_bytes(qb.canonical_json(payload))
    attestation["signature_base64"] = base64.b64encode(signature_path.read_bytes()).decode()
    attestation["attestation_sha256"] = qb.sha256_bytes(qb.canonical_json(attestation))
    attestation_path = tmp_path / "attestation.json"
    attestation_path.write_text(json.dumps(attestation), encoding="utf-8")

    report = pba.verify_privileged_attestation(
        attestation_path, receipt_path, policy_path, service_config,
        allow_test_mode=True,
    )
    assert report["valid"] is True
    assert report["receipt_sha256"] == receipt["receipt_sha256"]
    assert report["ledger_sequence"] == 1

    unprovisioned = dict(service) | {"state": "unprovisioned_external_authority_required"}
    service_config.write_text(json.dumps(unprovisioned), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="not provisioned"):
        pba.verify_privileged_attestation(
            attestation_path, receipt_path, policy_path, service_config,
            allow_test_mode=True,
        )
    service_config.write_text(json.dumps(service), encoding="utf-8")
    forged = copy.deepcopy(attestation)
    forged["ledger_sequence"] = 2
    forged.pop("attestation_sha256")
    forged["attestation_sha256"] = qb.sha256_bytes(qb.canonical_json(forged))
    attestation_path.write_text(json.dumps(forged), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="payload differs"):
        pba.verify_privileged_attestation(
            attestation_path, receipt_path, policy_path, service_config,
            allow_test_mode=True,
        )


def test_cmake_integration_applies_compile_and_link_controls() -> None:
    cmake = (ROOT / "CMakeLists.txt").read_text(encoding="utf-8")
    assert "TRINITY_RAID_BUILD_COORDINATED" in cmake
    assert "CMAKE_JOB_POOL_COMPILE" in cmake
    assert "CMAKE_JOB_POOL_LINK" in cmake
    assert "RULE_LAUNCH_LINK" in cmake
    assert 'CMAKE_CXX_ARCHIVE_CREATE "<CMAKE_AR> qcT' in cmake
    assert "thin intermediate archives enabled" in cmake
    assert "-Wl,--reduce-memory-overheads" in cmake
    assert "GNU low-memory executable linking enabled" in cmake


def test_worldserver_artifact_hash_helper(tmp_path: Path) -> None:
    binary = tmp_path / "worldserver"
    binary.write_bytes(b"\x7fELFcoordinated-fixture")
    assert qb.sha256_file(binary) == "f0ad5a96d17f421decff47373c360f97e12dce40c367ec85646dcdb6d4076c57"


def test_receipt_rejects_worldserver_not_produced_by_ticket(tmp_path: Path) -> None:
    frozen = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v6.json").read_text()
    )
    receipt = {
            "schema_version": 2,
        "policy_id": frozen["policy_id"],
        "ticket_id": "stale-fixture",
        "queue_sequence": 1,
        "worktree": str(ROOT),
        "commit": "0" * 40,
            "worktree_porcelain_sha256_at_request": "0" * 64,
            "source_identity": {
                stage: {
                    "commit": "0" * 40, "tree": "1" * 40,
                    "clean": True, "dirty": False,
                    "porcelain_sha256": "0" * 64,
                }
                for stage in ("request", "admission", "completion")
            },
            "source_identity_stable": True,
            "provenance_reasons": [],
        "build_configuration": {"request": None, "admission": None, "completion": None},
        "build_configuration_stable": True,
        "configure_lineage": None,
        "toolchain_identity": {
            "admission": {"expected": {}, "actual": {}, "matches_policy": True},
            "completion": {"expected": {}, "actual": {}, "matches_policy": True},
            "stable": True,
        },
        "environment_contract": {
            "base_environment": {
                "PATH": qb.SAFE_BUILD_PATH, "LANG": "C.UTF-8",
                "LC_ALL": "C.UTF-8", "TZ": "UTC",
            },
            "inherit_parent_environment": False,
            "coordinator_variables": sorted({
                "CMAKE_BUILD_PARALLEL_LEVEL", "CTEST_PARALLEL_LEVEL", "MAKEFLAGS",
                "NINJAFLAGS", "TRINITY_RAID_BUILD_COORDINATED",
                "TRINITY_RAID_BUILD_TICKET", "TRINITY_RAID_BUILD_COMPILER_JOBS",
                "TRINITY_RAID_BUILD_LINKER_JOBS", "TRINITY_RAID_BUILD_LINK_LOCK",
            }),
        },
        "command_sha256": "0" * 64,
        "resource_class": "worldserver_build",
        "classification": "success",
        "exit_code": 0,
        "compiler_job_ceiling": 1,
        "linker_job_ceiling": 1,
        "test_mode": False,
        "command_arguments_retained": False,
        "peak_observations": {},
        "log_sha256": "0" * 64,
        "output_artifacts": [{
            "kind": "worldserver_elf",
            "path": "/tmp/stale-worldserver",
            "size_bytes": 123,
            "sha256": "0" * 64,
            "produced_by_ticket": False,
        }],
        "policy_sha256": qb.sha256_bytes(qb.canonical_json(frozen)),
    }
    unsigned = dict(receipt)
    receipt["receipt_sha256"] = qb.sha256_bytes(qb.canonical_json(unsigned))
    path = tmp_path / "receipt.json"
    path.write_text(json.dumps(receipt), encoding="utf-8")
    with pytest.raises(qb.CoordinatorError, match="coordinator canonical receipt record"):
        qb.verify_receipt(path, frozen)


def test_degraded_v4_retains_thresholds_and_freezes_link_mitigations() -> None:
    v3 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v3.json").read_text()
    )
    v4 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v4.json").read_text()
    )
    assert v4["parallelism"] == v3["parallelism"]
    assert v4["admission_thresholds"] == v3["admission_thresholds"]
    assert v4["mechanical_controls"]["gnu_thin_intermediate_archives"] is True
    assert v4["mechanical_controls"]["gnu_reduce_memory_overheads_final_link"] is True
    assert v4["mechanical_controls"]["receipt_worldserver_sha256_required"] is True


def test_degraded_v5_retains_thresholds_and_disables_unity() -> None:
    v4 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v4.json").read_text()
    )
    v5 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v5.json").read_text()
    )
    assert v5["parallelism"] == v4["parallelism"]
    assert v5["admission_thresholds"] == v4["admission_thresholds"]
    assert v5["mechanical_controls"]["unity_builds"] is False
    assert v5["mechanical_controls"]["gnu_reduce_memory_overheads_final_link"] is True


def test_degraded_v6_retains_thresholds_and_disables_precompiled_headers() -> None:
    v5 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v5.json").read_text()
    )
    v6 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v6.json").read_text()
    )
    assert v6["parallelism"] == v5["parallelism"]
    assert v6["admission_thresholds"] == v5["admission_thresholds"]
    assert v6["mechanical_controls"]["unity_builds"] is False
    assert v6["mechanical_controls"]["core_precompiled_headers"] is False
    assert v6["mechanical_controls"]["script_precompiled_headers"] is False
    assert v6["mechanical_controls"]["gnu_reduce_memory_overheads_final_link"] is True


def test_degraded_v7_retains_all_safety_limits_and_uses_release_build_type() -> None:
    v6 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v6.json").read_text()
    )
    v7 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v7.json").read_text()
    )
    assert v7["parallelism"] == v6["parallelism"]
    assert v7["admission_thresholds"] == v6["admission_thresholds"]
    for key in (
        "unity_builds", "core_precompiled_headers", "script_precompiled_headers",
        "gnu_thin_intermediate_archives", "gnu_reduce_memory_overheads_final_link",
        "process_group_watchdog", "receipt_verification_required",
    ):
        assert v7["mechanical_controls"][key] == v6["mechanical_controls"][key]
    assert v7["mechanical_controls"]["cmake_build_type"] == "Release"


def test_degraded_v8_freezes_complete_low_memory_release_configuration() -> None:
    v7 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v7.json").read_text()
    )
    v8 = json.loads(
        (ROOT / "experiments/configs/cata_raid_build_resource_policy_degraded_v8.json").read_text()
    )
    assert v8["parallelism"] == v7["parallelism"]
    assert v8["admission_thresholds"] == v7["admission_thresholds"]
    assert v8["mechanical_controls"]["cmake_build_type"] == "Release"
    assert v8["mechanical_controls"]["cmake_executable"] == "/usr/bin/cmake"
    assert len(v8["mechanical_controls"]["cmake_executable_sha256"]) == 64
    assert v8["mechanical_controls"]["cmake_export_compile_commands"] is True
    assert v8["mechanical_controls"]["cmake_cxx_flags"] == ""
    assert v8["mechanical_controls"]["cmake_release_cxx_flags"] == "-O1 -DNDEBUG"
    assert v8["mechanical_controls"]["cmake_cxx_compiler"] == "/usr/bin/c++"
    assert v8["mechanical_controls"]["cmake_cxx_compiler_launcher"] == ""
    assert v8["mechanical_controls"]["with_coredebug"] is False
    assert v8["mechanical_controls"]["interprocedural_optimization"] is False
    assert v8["mechanical_controls"]["release_interprocedural_optimization"] is False


def test_live_validation_scan_matches_argv_not_unrelated_prose(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc = tmp_path / "proc"
    proc.mkdir()
    unrelated = proc / "101"
    unrelated.mkdir()
    (unrelated / "cmdline").write_bytes(
        b"/usr/bin/python\0-c\0print('worldserver and dvc push')\0"
    )
    protected = proc / "102"
    protected.mkdir()
    (protected / "cmdline").write_bytes(
        b"/opt/trinity/worldserver\0--config\0test.conf\0"
    )
    original_path = qb.Path

    def redirected_path(value: str) -> Path:
        return proc if value == "/proc" else original_path(value)

    monkeypatch.setattr(qb, "Path", redirected_path)
    assert qb.find_live_validation_processes(policy()) == [
        {"pid": 102, "matched_pattern": "worldserver"}
    ]


def test_all_registered_worktrees_share_git_common_queue_state() -> None:
    main_common = qb.git_common_dir(ROOT)
    output = qb.git_output(ROOT, "worktree", "list", "--porcelain")
    worktrees = [Path(line.split(" ", 1)[1]) for line in output.splitlines() if line.startswith("worktree ")]
    assert worktrees
    assert all(qb.git_common_dir(worktree) == main_common for worktree in worktrees)

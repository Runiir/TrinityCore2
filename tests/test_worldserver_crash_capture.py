"""Opt-in gdb crash capture keeps the console transport byte-exact.

A fake worldserver (a real native process with a second thread) answers the
owned console like TrinityCore's CLI and, on `botauto stop`, jumps into
non-executable data as the round-4 six-shard batch did (SIGSEGV executing
libstdc++'s typeinfo vtable during `.botauto stop`, no core, 51-byte reply).
"""
from __future__ import annotations

from contextlib import nullcontext
import json
import os
import shutil
import signal
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import crash_capture
from tools.raid_program import shard_coordinator as sc
from tools.raid_program import shared_instance_console as console_module
from tools.raid_program.shared_instance_fixture import sha256

FAKE_WORLDSERVER = r'''
#include <pthread.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

static const unsigned long destroyed_object_vtable[4] = {0, 0, 0, 0};

static void* heartbeat(void* arg) { (void)arg; for (;;) sleep(1); return NULL; }

__attribute__((noinline)) void fake_stop_cohort(void)
{
    void (*call)(void) = (void (*)(void))(void*)destroyed_object_vtable;
    call();
}

int main(void)
{
    pthread_t thread;
    pthread_create(&thread, NULL, heartbeat, NULL);
    char line[4096];
    printf("TC>");
    fflush(stdout);
    while (fgets(line, sizeof(line), stdin))
    {
        printf("%s", line);
        if (!strncmp(line, "server exit", 11))
        {
            if (!getenv("FAKE_HANG_ON_EXIT"))
                return 0;
            /* A shutdown that never finishes and ignores SIGTERM. */
            signal(SIGTERM, SIG_IGN);
            for (;;)
                pause();
        }
        if (!strncmp(line, "botauto stop", 12))
        {
            fflush(stdout);
            fake_stop_cohort();
        }
        if (!strncmp(line, "botauto cohorts", 15))
            printf("{\"ok\":true,\"action\":\"botauto_cohorts\",\"server_process_id\":%d,"
                   "\"max_active_cohorts\":6,\"active_cohort_count\":0,\"map_worker_threads\":1,"
                   "\"shard_isolation\":true,\"cohorts\":[],\"failure_reason\":null}\n", (int)getpid());
        else
            printf("{\"ok\":true,\"action\":\"botauto_status\",\"lines\":\"%s\",\"columns\":\"%s\"}\n",
                   getenv("LINES") ? getenv("LINES") : "unset", getenv("COLUMNS") ? getenv("COLUMNS") : "unset");
        printf("TC> ");
        fflush(stdout);
    }
    return 0;
}
'''

GDB_CHATTER = ("libthread_db", "Thread ", "SIGSEGV", "Inferior", "gdb", "Reading symbols")


@pytest.fixture
def fake_worldserver(tmp_path: Path) -> Path:
    if shutil.which("gdb") is None or shutil.which("cc") is None:
        pytest.skip("gdb and a C compiler are required")
    source = tmp_path / "fake_worldserver.c"
    source.write_text(FAKE_WORLDSERVER, encoding="utf-8")
    binary = tmp_path / "bin" / "worldserver"
    binary.parent.mkdir()
    subprocess.run(["cc", "-O0", "-o", str(binary), str(source), "-lpthread"], check=True)
    return binary


@pytest.fixture
def unlocked(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(console_module, "live_validation_lock", lambda *_: nullcontext())
    monkeypatch.setattr(console_module, "worldserver_processes",
                        lambda: {"returncode": 1, "pids": [], "error": None})
    for name in crash_capture.SCREEN_VARIABLES:
        monkeypatch.delenv(name, raising=False)


def _owned(binary: Path, output: Path, lifecycle: dict, crash_capture: bool = True):
    return console_module.owned_console(repository=output, source=output, binary=binary,
                                        config=output / "worldserver.conf", output_dir=output,
                                        startup_timeout_sec=30, lifecycle=lifecycle,
                                        crash_capture=crash_capture)


def test_crash_under_gdb_is_reported_like_the_live_incident(tmp_path, fake_worldserver, unlocked):
    output = tmp_path / "run"
    lifecycle: dict = {}
    with _owned(fake_worldserver, output, lifecycle) as base:
        # The worldserver is gdb's child: identity checks use its pid, not gdb's.
        assert base.server_pid != base.process.pid
        assert lifecycle["server_pid"] == base.server_pid and lifecycle["debugger_pid"] == base.process.pid
        assert base.crash_backtrace == output / crash_capture.BACKTRACE_NAME
        console_module.verify_process_binary(base.process, sha256(fake_worldserver), pid=base.server_pid,
                                             binary=fake_worldserver, backtrace=base.crash_backtrace)
        # A pid that is not gdb's live worldserver child is never hashed.
        with pytest.raises(RuntimeError, match="exited before executable verification; gdb log: "):
            console_module.verify_process_binary(base.process, sha256(fake_worldserver), pid=os.getpid(),
                                                 binary=fake_worldserver, backtrace=base.crash_backtrace)
        transport = sc.ShardConsoleTransport.adopt(base)
        assert transport.server_pid == base.server_pid
        assert transport.crash_backtrace == base.crash_backtrace
        console = sc.SerializedConsole(transport, output / "console_journal.jsonl")

        registry = sc.read_registry(console, 10)
        sc.require_shard_capacity(registry, 1, server_pid=transport.server_pid)
        with pytest.raises(sc.ShardRunError, match="does not match the owned worldserver"):
            sc.require_shard_capacity(registry, 1, server_pid=base.process.pid)
        status, code, timed_out = console(".botauto status blackwing_descent_10n_atramedes_c0", 10)
        assert (code, timed_out) == (0, False)
        # gdb added neither LINES nor COLUMNS to the worldserver's environment.
        assert sc.one_payload(status, "botauto_status") == {"ok": True, "action": "botauto_status",
                                                            "lines": "unset", "columns": "unset"}

        stop, code, timed_out = console(".botauto stop blackwing_descent_10n_atramedes_c0", 30)
        # As in the incident: the echo only, no reply, the server gone.
        assert (code, timed_out) == (1, False)
        assert stop.strip() == "botauto stop blackwing_descent_10n_atramedes_c0"
        assert base.process.wait(timeout=30) == 139
        health = console.health()
        assert health["server_exited"] and health["server_exit_code"] == 139 and not health["healthy"]
    assert lifecycle["process_return_code"] == 139
    assert "forced_termination" not in lifecycle

    log = (output / "worldserver.console.log").read_text(encoding="utf-8")
    assert log.startswith("TC>botauto cohorts\n")
    assert not [word for word in GDB_CHATTER if word in log]
    journal = [json.loads(line) for line in (output / "console_journal.jsonl").read_text().splitlines()]
    assert [row["returncode"] for row in journal] == [0, 0, 1]

    summary = crash_capture.summarize(output)
    assert summary["crashed"] is True and summary["signal"] == 11
    assert any("fake_stop_cohort" in frame for frame in summary["frames"])
    backtrace = (output / crash_capture.BACKTRACE_NAME).read_text(encoding="utf-8")
    assert "received signal SIGSEGV" in backtrace
    assert "<fake_stop_cohort+" in backtrace  # the stack words name the caller of a garbage pc
    assert "Thread 2" in backtrace  # thread apply all bt


def test_normal_shutdown_under_gdb_keeps_exit_code_zero(tmp_path, fake_worldserver, unlocked):
    output = tmp_path / "run"
    lifecycle: dict = {}
    with _owned(fake_worldserver, output, lifecycle) as base:
        reply, code, timed_out = base(".botauto status x", 10)
        assert (code, timed_out) == (0, False) and '"action":"botauto_status"' in reply
    assert lifecycle["process_exited"] is True and lifecycle["process_return_code"] == 0
    assert "forced_termination" not in lifecycle
    assert crash_capture.summarize(output)["crashed"] is False
    log = (output / "worldserver.console.log").read_text(encoding="utf-8")
    assert log.endswith("server exit\n") and "Inferior" not in log


@pytest.mark.parametrize("capture,return_code,forced", [(True, 137, "worldserver_sigkill"), (False, -9, None)])
def test_a_forced_kill_is_never_a_clean_exit(tmp_path, fake_worldserver, unlocked, monkeypatch,
                                             capture, return_code, forced):
    """Review of 0002: gdb quits on its own SIGTERM with 0; the worldserver has its own group."""
    monkeypatch.setattr(console_module, "SHUTDOWN_TIMEOUT_SEC", 1)
    monkeypatch.setattr(console_module, "TERMINATION_GRACE_SEC", 1)
    monkeypatch.setenv("FAKE_HANG_ON_EXIT", "1")
    output = tmp_path / "run"
    lifecycle: dict = {}
    with _owned(fake_worldserver, output, lifecycle, crash_capture=capture) as base:
        server_pid = base.server_pid
        assert base(".botauto status x", 10)[1] == 0
    assert lifecycle["process_exited"] is True
    assert lifecycle["process_return_code"] == return_code
    assert lifecycle.get("forced_termination") == forced
    assert not Path(f"/proc/{server_pid}").exists()


def test_inferior_signals_only_its_own_process(tmp_path):
    child = subprocess.Popen(["sleep", "30"])
    inferior = crash_capture.Inferior(child.pid, crash_capture.pidfd_open(child.pid))
    assert crash_capture.is_inferior(os.getpid(), child.pid, Path(shutil.which("sleep")))
    assert not crash_capture.is_inferior(os.getpid() + 1, child.pid, Path(shutil.which("sleep")))
    assert inferior.send(signal.SIGTERM) is True
    child.wait(timeout=10)
    # Reaped: the pid may be recycled, the pidfd still names the dead process.
    assert inferior.send(signal.SIGTERM) is False
    inferior.close()


def test_gdb_files_are_never_written_over_an_earlier_run(tmp_path):
    binary = Path(shutil.which("true") or "/usr/bin/true")
    if shutil.which("gdb") is None:
        pytest.skip("gdb is required")
    crash_capture.debugger_command(binary, [], tmp_path)
    with pytest.raises(FileExistsError):
        crash_capture.debugger_command(binary, [], tmp_path)
    (tmp_path / crash_capture.SCRIPT_NAME).unlink()
    (tmp_path / crash_capture.BACKTRACE_NAME).write_text("earlier run\n")
    with pytest.raises(FileExistsError, match="fresh run directory"):
        crash_capture.debugger_command(binary, [], tmp_path)


def test_gdb_version_is_checked(tmp_path):
    assert crash_capture.parse_gdb_version("GNU gdb (Ubuntu 17.1-2ubuntu1) 17.1\nCopyright") == (17, 1)
    assert crash_capture.parse_gdb_version("GNU gdb (GDB) Red Hat Enterprise Linux 12.1-2.el9") == (12, 1)
    assert crash_capture.parse_gdb_version("GNU gdb (GDB) 11.2") == (11, 2)
    old = tmp_path / "old-gdb"
    old.write_text("#!/bin/sh\necho 'GNU gdb (GDB) 11.2'\n")
    old.chmod(0o755)
    with pytest.raises(RuntimeError, match=r"needs gdb >= 12 .* is 11\.2"):
        crash_capture.debugger_command(Path("/opt/ws/worldserver"), [], tmp_path, gdb=str(old))
    assert not (tmp_path / crash_capture.SCRIPT_NAME).exists()


def test_gdb_script_redirects_before_loading_and_passes_signals(tmp_path):
    script = crash_capture.gdb_script(Path("/opt/ws/worldserver"), ["--config", "/tmp/run/w.conf"],
                                      tmp_path / "bt.txt", environment={"HOME": "/root"})
    lines = script.splitlines()
    assert "unset environment LINES" in lines and "unset environment COLUMNS" in lines
    assert lines.index("unset environment LINES") < lines.index("run")
    kept = crash_capture.gdb_script(Path("/opt/ws/worldserver"), [], tmp_path / "bt.txt",
                                    environment={"LINES": "50", "COLUMNS": "200"})
    assert "unset environment" not in kept
    assert lines.index("set logging enabled on") < lines.index("file /opt/ws/worldserver")
    assert lines.index("set logging redirect on") < lines.index("set logging enabled on")
    assert "set startup-with-shell off" in lines and "set print thread-events off" in lines
    assert "set args --config /tmp/run/w.conf" in lines
    assert "handle SIGTERM nostop noprint pass" in lines
    assert lines.index("run") < lines.index("python")
    for unsafe in ("/tmp/run dir/w.conf", '/tmp/"w.conf', "/tmp/w\n.conf"):
        with pytest.raises(ValueError):
            crash_capture.gdb_script(Path("/opt/ws/worldserver"), ["--config", unsafe], tmp_path / "bt.txt")


def test_summary_of_a_backtrace_file(tmp_path):
    assert crash_capture.summarize(tmp_path) == {"path": str(tmp_path / crash_capture.BACKTRACE_NAME),
                                                "present": False, "crashed": False, "signal": None,
                                                "frames": []}
    (tmp_path / crash_capture.BACKTRACE_NAME).write_text(
        "[Inferior 1 (process 7) exited normally]\n", encoding="utf-8")
    assert crash_capture.summarize(tmp_path)["crashed"] is False
    (tmp_path / crash_capture.BACKTRACE_NAME).write_text(
        "Thread 1 \"worldserver\" received signal SIGSEGV, Segmentation fault.\n"
        "0x000070dfc7a90b00 in vtable for __cxxabiv1::__si_class_type_info ()\n"
        "worldserver_crash signal=11\nrip 0x70dfc7a90b00\n"
        "#0  0x000070dfc7a90b00 in vtable for __cxxabiv1::__si_class_type_info ()\n"
        "#1  0x00005555572d637e in WorldObject::CanSeeOrDetect(WorldObject const*, bool, bool, bool) const ()\n"
        "\nThread 2 (Thread 0x7 (LWP 8) \"MapUpdater\"):\n#0  0x1 in poll ()\n", encoding="utf-8")
    summary = crash_capture.summarize(tmp_path)
    assert summary["crashed"] is True and summary["signal"] == 11
    assert summary["frames"] == [
        "#0  0x000070dfc7a90b00 in vtable for __cxxabiv1::__si_class_type_info ()",
        "#1  0x00005555572d637e in WorldObject::CanSeeOrDetect(WorldObject const*, bool, bool, bool) const ()"]


def test_crash_capture_requires_gdb(tmp_path):
    with pytest.raises(RuntimeError, match="not installed"):
        crash_capture.debugger_command(Path("/opt/ws/worldserver"), [], tmp_path, gdb="no-such-gdb-binary")


def test_main_plumbs_the_gdb_backtrace_flag(tmp_path, monkeypatch):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps({"schema": sc.RUN_PLAN_SCHEMA, "shards": [{
        "cohort_id": "blackwing_descent_10n_magmaw_c0",
        "profile": "blackwing_descent_10n_magmaw_c0_diagnostic"}]}))
    calls = []
    monkeypatch.setattr(sc, "load_run_plan", lambda path, select=(): object())
    monkeypatch.setattr(sc, "run_live", lambda plan, **kwargs: calls.append(kwargs)
                        or {"terminal_reason": "completed", "shards": []})
    outside = Path("/tmp") / f"crash-capture-main-{tmp_path.name}"
    assert sc.main(["--plan", str(plan_path), "--output-dir", str(outside), "--gdb-backtrace"]) == 0
    assert sc.main(["--plan", str(plan_path), "--output-dir", str(outside)]) == 0
    assert [call["crash_capture"] for call in calls] == [True, False]

"""One coordinator owns an attached server; workers receive addressed commands."""
from __future__ import annotations

from contextlib import contextmanager
import os
from pathlib import Path
import re
import signal
import subprocess
import time
from typing import Any, Callable, Iterator

from tools.bot_ml.live_validation_session import live_validation_lock
from tools.raid_program import crash_capture as crash_capture_module
from tools.raid_program.raid_shard_preflight import worldserver_processes
from tools.raid_program.shared_instance_fixture import sha256

# Owned shutdown: `server exit`, then escalating signals (tests shorten these).
SHUTDOWN_TIMEOUT_SEC = 30
TERMINATION_GRACE_SEC = 5


def verify_process_binary(process: subprocess.Popen[bytes], expected_sha256: str,
                          pid: int | None = None, binary: Path | None = None,
                          backtrace: Path | None = None) -> str:
    """Hash the executed inode, which can differ from a replaced launch path.

    Under crash capture `process` is gdb and `pid` its worldserver child: the
    child must still be gdb's live child running `binary` on both sides of the
    hash, so a recycled pid is never hashed.
    """
    detail = f"; gdb log: {backtrace}" if backtrace else ""
    inferior = pid is not None and pid != process.pid

    def alive() -> bool:
        return process.poll() is None and (
            not inferior or binary is None
            or crash_capture_module.is_inferior(process.pid, pid, binary))

    if not alive():
        raise RuntimeError(f"owned worldserver exited before executable verification{detail}")
    observed = sha256(Path(f"/proc/{pid if inferior else process.pid}/exe"))
    if not alive() or observed != expected_sha256:
        raise RuntimeError(f"owned worldserver executable differs from build receipt{detail}")
    return observed


class ConsoleTransport:
    def __init__(self, process: subprocess.Popen[bytes], log_path: Path,
                 max_response_bytes: int = 16 * 1024 * 1024):
        self.process = process
        self.log_path = log_path
        if max_response_bytes <= 0:
            raise ValueError("positive console response budget required")
        self.max_response_bytes = max_response_bytes
        self.failed = False
        # The worldserver's own pid and gdb's log; differ under crash capture.
        self.server_pid = process.pid
        self.crash_backtrace: Path | None = None

    def wait_ready(self, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("worldserver exited during startup")
            with self.log_path.open("rb") as stream:
                stream.seek(max(0, self.log_path.stat().st_size - 65536))
                if b"TC>" in stream.read():
                    return
            time.sleep(0.25)
        raise RuntimeError("worldserver startup deadline exceeded")

    def __call__(self, command: str, timeout_sec: int) -> tuple[str, int, bool]:
        # Once a reply is incomplete, its late bytes may contaminate any later
        # response. Only owner shutdown remains legal after transport failure.
        if self.failed or self.process.poll() is not None:
            return "", 1, False
        if "\n" in command or "\r" in command or "\0" in command:
            raise ValueError("one console command required")
        tokens = command.lstrip(".").split()
        if len(tokens) < 2 or tokens[0] != "botauto":
            raise ValueError("coordinator transport accepts botauto commands only")
        action = "botauto_" + tokens[1]
        # Native start returns status on success and start on rejection.
        # Both terminate the command; the caller validates success/identity.
        actions = b"(?:botauto_status|botauto_start)" if tokens[1] == "start" else action.encode()
        if tokens[1] == "combatlog":
            actions = b"(?:botauto_combatlog|botauto_combatlog_complete)"
        if tokens[1] == "calibrate":
            # Full status may be chunked; progress/direct and rejection replies
            # also terminate at the console prompt. Chunks alone never do.
            actions = b"(?:botauto_calibrate|botauto_calibrate_start|botauto_calibrate_stop|botauto_calibrate_status|botauto_calibrate_status_complete)"
        marker = re.compile(rb'"action"\s*:\s*"' + actions + rb'"')
        deadline = time.monotonic() + timeout_sec
        output = bytearray()
        with self.log_path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            assert self.process.stdin is not None
            try:
                self.process.stdin.write((command.lstrip(".") + "\n").encode())
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.failed = True
                return "", 1, False
            while time.monotonic() < deadline:
                output.extend(stream.read(1024 * 1024))
                if len(output) > self.max_response_bytes:
                    self.failed = True
                    return "console response exceeded byte budget", 1, False
                found = marker.search(output)
                if found and b"TC>" in output[found.end():]:
                    return output.decode(errors="replace"), 0, False
                if self.process.poll() is not None:
                    self.failed = True
                    return output.decode(errors="replace"), 1, False
                time.sleep(0.05)
        self.failed = True
        return output.decode(errors="replace"), 1, True


@contextmanager
def owned_console(*, repository: Path, source: Path, binary: Path, config: Path,
                  output_dir: Path, startup_timeout_sec: int = 180,
                  before_launch: Callable[[], None] | None = None,
                  lifecycle: dict[str, Any] | None = None,
                  crash_capture: bool = False) -> Iterator[ConsoleTransport]:
    """Launch once under the shared owner lock; always close only this PID group.

    crash_capture runs the worldserver as gdb's inferior (tools.raid_program.crash_capture):
    the console bytes are unchanged, a fatal signal N leaves
    <output_dir>/worldserver.crash_backtrace.txt and exit status 128 + N.
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    with live_validation_lock(repository, "shared-instance-isolation"):
        # Admission never replaces, kills, or attaches to an unrelated server,
        # including a renamed copy (scoreboard_run pins /tmp/worldserver-<sha12>).
        existing = worldserver_processes()
        if existing["returncode"] != 1:
            raise RuntimeError("worldserver already exists or process inventory unavailable: "
                               f"pids={existing['pids']} error={existing['error']}")
        if before_launch is not None:
            before_launch()
        with (output_dir / "worldserver.console.log").open("xb") as log:
            # After the exclusive open: never over an earlier run's gdb files.
            arguments = ["--config", str(config)]
            backtrace = output_dir / crash_capture_module.BACKTRACE_NAME
            command = ([str(binary), *arguments] if not crash_capture
                       else crash_capture_module.debugger_command(binary, arguments, output_dir))
            process = subprocess.Popen(command, cwd=source,
                                       stdin=subprocess.PIPE, stdout=log, stderr=log,
                                       start_new_session=True)
            if lifecycle is not None:
                lifecycle.update(server_started=True, server_pid=process.pid)
                if crash_capture:
                    lifecycle.update(debugger_pid=process.pid, crash_backtrace=str(backtrace))
            transport = ConsoleTransport(process, output_dir / "worldserver.console.log")
            inferior: crash_capture_module.Inferior | None = None
            try:
                if crash_capture:
                    transport.crash_backtrace = backtrace
                    inferior = crash_capture_module.wait_inferior(
                        process, binary, startup_timeout_sec, backtrace)
                    transport.server_pid = inferior.pid
                    if lifecycle is not None:
                        lifecycle.update(server_pid=inferior.pid)
                transport.wait_ready(startup_timeout_sec)
                yield transport
            finally:
                if process.poll() is None:
                    try:
                        assert process.stdin is not None
                        process.stdin.write(b"server exit\n")
                        process.stdin.flush()
                        process.wait(timeout=SHUTDOWN_TIMEOUT_SEC)
                    except (BrokenPipeError, OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
                        if process.poll() is None and inferior is not None:
                            _terminate_inferior(process, inferior, lifecycle)
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGTERM)
                            try:
                                process.wait(timeout=TERMINATION_GRACE_SEC)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.wait(timeout=TERMINATION_GRACE_SEC)
                if inferior is not None:
                    inferior.close()
                if process.stdin:
                    process.stdin.close()
                if lifecycle is not None:
                    lifecycle.update(process_exited=process.poll() is not None,
                                     process_return_code=process.returncode)


def _terminate_inferior(process: subprocess.Popen[bytes], inferior: crash_capture_module.Inferior,
                        lifecycle: dict[str, Any] | None) -> None:
    """Escalate on the worldserver itself: it has its own process group, and gdb
    quits on its own SIGTERM with exit 0 after killing it. SIGTERM lets it shut
    down; SIGKILL then makes gdb exit 128 + 9, so a forced kill is never clean."""
    for signum, step in ((signal.SIGTERM, "worldserver_sigterm"), (signal.SIGKILL, "worldserver_sigkill")):
        if process.poll() is not None or not inferior.send(signum):
            return
        if lifecycle is not None:
            lifecycle["forced_termination"] = step
        try:
            process.wait(timeout=TERMINATION_GRACE_SEC)
            return
        except subprocess.TimeoutExpired:
            continue

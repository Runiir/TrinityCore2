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
from tools.raid_program.shared_instance_fixture import sha256


def verify_process_binary(process: subprocess.Popen[bytes], expected_sha256: str) -> str:
    """Hash the executed inode, which can differ from a replaced launch path."""
    if process.poll() is not None:
        raise RuntimeError("owned worldserver exited before executable verification")
    observed = sha256(Path(f"/proc/{process.pid}/exe"))
    if process.poll() is not None or observed != expected_sha256:
        raise RuntimeError("owned worldserver executable differs from build receipt")
    return observed


class ConsoleTransport:
    def __init__(self, process: subprocess.Popen[bytes], log_path: Path):
        self.process = process
        self.log_path = log_path
        self.failed = False

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
        if tokens[1] == "combatlog":
            action += "_complete"
        marker = re.compile(rb'"action"\s*:\s*"' + action.encode() + rb'"')
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
                output.extend(stream.read(65536))
                if len(output) > 16 * 1024 * 1024:
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
                  lifecycle: dict[str, Any] | None = None) -> Iterator[ConsoleTransport]:
    """Launch once under the shared owner lock; always close only this PID group."""
    output_dir.mkdir(parents=True, exist_ok=True)
    with live_validation_lock(repository, "shared-instance-isolation"):
        # Admission never replaces, kills, or attaches to an unrelated server.
        existing = subprocess.run(["pgrep", "-x", "worldserver"], capture_output=True)
        if existing.returncode != 1:
            raise RuntimeError("worldserver already exists or process inventory unavailable")
        if before_launch is not None:
            before_launch()
        with (output_dir / "worldserver.console.log").open("xb") as log:
            process = subprocess.Popen([str(binary), "--config", str(config)], cwd=source,
                                       stdin=subprocess.PIPE, stdout=log, stderr=log,
                                       start_new_session=True)
            if lifecycle is not None:
                lifecycle.update(server_started=True, server_pid=process.pid)
            transport = ConsoleTransport(process, output_dir / "worldserver.console.log")
            try:
                transport.wait_ready(startup_timeout_sec)
                yield transport
            finally:
                if process.poll() is None:
                    try:
                        assert process.stdin is not None
                        process.stdin.write(b"server exit\n")
                        process.stdin.flush()
                        process.wait(timeout=30)
                    except (BrokenPipeError, OSError, subprocess.TimeoutExpired, KeyboardInterrupt):
                        if process.poll() is None:
                            os.killpg(process.pid, signal.SIGTERM)
                            try:
                                process.wait(timeout=5)
                            except subprocess.TimeoutExpired:
                                os.killpg(process.pid, signal.SIGKILL)
                                process.wait(timeout=5)
                if process.stdin:
                    process.stdin.close()
                if lifecycle is not None:
                    lifecycle.update(process_exited=process.poll() is not None,
                                     process_return_code=process.returncode)

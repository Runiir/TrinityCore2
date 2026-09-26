"""Opt-in native backtraces for an owned worldserver: run it as gdb's inferior.

On this host a crashed worldserver leaves nothing behind: apport owns
core_pattern and ignores binaries that do not belong to a package, the shard
runs keep `ulimit -c 0`, and glibc no longer ships catchsegv or libSegFault.
With crash capture, tools.raid_program.shared_instance_console.owned_console
starts `gdb -q -nx -batch -x <run>/worldserver.gdb` instead of the
worldserver. The worldserver is gdb's direct child (startup-with-shell off)
and inherits the console's stdin pipe and console log unchanged, and gdb
does not add LINES or COLUMNS to its environment. Every line gdb itself
prints (thread events, the stop notification, the backtrace) is redirected to
<run>/worldserver.crash_backtrace.txt, so the console transport reads exactly
the worldserver's bytes, as without gdb.

Exit status of the launched process (gdb): the worldserver's own exit code
after a normal exit; 128 + N after the worldserver died of signal N (SIGSEGV
-> 139 after registers, the stack words, `bt` and `thread apply all bt` are
logged; SIGKILL -> 137). The worldserver runs in its own process group, so it
is addressed through the pidfd of wait_inferior(), never by pid or group.
"""
from __future__ import annotations

import ctypes
from dataclasses import dataclass
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time
from typing import Any, Mapping, Sequence

SCRIPT_NAME = "worldserver.gdb"
BACKTRACE_NAME = "worldserver.crash_backtrace.txt"
CRASH_MARKER = "worldserver_crash signal="
MINIMUM_GDB = (12, 0)  # `set logging enabled on`
# Signals the worldserver handles or ignores itself; gdb passes them through
# silently instead of stopping (a stop would hang the batch session).
PASSED_SIGNALS = ("SIGPIPE", "SIGHUP", "SIGINT", "SIGTERM", "SIGUSR1", "SIGUSR2", "SIGALRM", "SIGCHLD")
# gdb exports its screen size to the inferior; readline echo depends on them.
SCREEN_VARIABLES = ("LINES", "COLUMNS")
_UNSAFE_PATH = re.compile(r'[\s"\'\\]')

# Post-mortem in gdb's Python: a failing command (e.g. an unwinder that cannot
# leave a garbage pc) must not abort the batch before the worldserver is
# killed and the exit status is set.
_POST_MORTEM = '''python
import gdb

def _run(command):
    try:
        gdb.execute(command)
    except gdb.error as error:
        gdb.write("gdb_command_failed %s: %s\\n" % (command, error))

_code = gdb.convenience_variable("_exitcode")
_signal = gdb.convenience_variable("_exitsignal")
if _code is not None:
    gdb.execute("quit %d" % int(_code))
if _signal is not None:
    gdb.execute("quit %d" % (128 + int(_signal)))
_signo = 0
try:
    _signo = int(gdb.parse_and_eval("$_siginfo.si_signo"))
except gdb.error:
    pass
gdb.write("''' + CRASH_MARKER + '''%d\\n" % _signo)
for _command in ("info registers", "x/48ga $sp", "bt 64", "thread apply all bt 48"):
    _run(_command)
_run("kill")
gdb.execute("quit %d" % (128 + _signo if _signo else 1))
end
'''


def _checked(path: Path | str) -> str:
    text = str(path)
    if not text or _UNSAFE_PATH.search(text):
        raise ValueError(f"crash capture needs a path without whitespace or quotes: {text!r}")
    return text


def gdb_script(binary: Path, arguments: Sequence[str], backtrace: Path,
               environment: Mapping[str, str] | None = None) -> str:
    """The gdb command file: quiet, output redirected, run once, post-mortem on a signal."""
    environment = os.environ if environment is None else environment
    lines = [
        "set pagination off",
        "set confirm off",
        "set width 0",
        "set height 0",
        "set debuginfod enabled off",
        "set print thread-events off",
        "set print inferior-events off",
        "set startup-with-shell off",
        # Production parity: keep ASLR (and never need personality(2) rights).
        "set disable-randomization off",
        f"set logging file {_checked(backtrace)}",
        "set logging overwrite on",
        "set logging redirect on",
        "set logging enabled on",
        *(f"handle {name} nostop noprint pass" for name in PASSED_SIGNALS),
        *(f"unset environment {name}" for name in SCREEN_VARIABLES if name not in environment),
        f"file {_checked(binary)}",
        "set args " + " ".join(_checked(argument) for argument in arguments),
        "run",
    ]
    return "\n".join(lines) + "\n" + _POST_MORTEM


def parse_gdb_version(text: str) -> tuple[int, int] | None:
    """(major, minor) from the first line of `gdb --version`, e.g. 'GNU gdb (Ubuntu 17.1-2ubuntu1) 17.1'."""
    first = text.splitlines()[0] if text else ""
    match = re.search(r"(\d+)\.(\d+)[^\s]*\s*$", first.strip())
    return (int(match.group(1)), int(match.group(2))) if match else None


def require_gdb(gdb: str = "gdb") -> str:
    executable = shutil.which(gdb)
    if executable is None:
        raise RuntimeError(f"crash capture requested but {gdb!r} is not installed")
    try:
        version_text = subprocess.run([executable, "--version"], capture_output=True, text=True,
                                      timeout=30).stdout
    except (OSError, subprocess.TimeoutExpired) as error:
        raise RuntimeError(f"crash capture: `{executable} --version` failed: {error}") from error
    version = parse_gdb_version(version_text)
    if version is None or version < MINIMUM_GDB:
        found = ".".join(map(str, version)) if version else repr(version_text.splitlines()[:1])
        raise RuntimeError(f"crash capture needs gdb >= {MINIMUM_GDB[0]} (`set logging enabled`); "
                           f"{executable} is {found}")
    return executable


def debugger_command(binary: Path, arguments: Sequence[str], output_dir: Path,
                     gdb: str = "gdb", environment: Mapping[str, str] | None = None) -> list[str]:
    """Create <output_dir>/worldserver.gdb (never over an earlier run) and return the gdb command."""
    executable = require_gdb(gdb)
    backtrace = output_dir / BACKTRACE_NAME
    if backtrace.exists():
        raise FileExistsError(f"{backtrace} already exists; crash capture needs a fresh run directory")
    script = output_dir / SCRIPT_NAME
    with script.open("x", encoding="utf-8") as stream:
        stream.write(gdb_script(binary, arguments, backtrace, environment))
    return [executable, "-q", "-nx", "-batch", "-x", _checked(script)]


def _parent_pid(stat: str) -> int | None:
    # comm may hold spaces and parentheses; the fields after the last ')' do not.
    fields = stat[stat.rfind(")") + 1:].split()
    return int(fields[1]) if len(fields) > 1 and fields[1].isdigit() else None


def is_inferior(parent_pid: int, pid: int, binary: Path, proc: Path = Path("/proc")) -> bool:
    """`pid` is gdb's child and already executes `binary` (before exec it is still a gdb fork)."""
    try:
        return (_parent_pid((proc / str(pid) / "stat").read_text()) == parent_pid
                and os.path.samefile(proc / str(pid) / "exe", binary))
    except (OSError, ValueError):
        return False


def inferior_pid(parent_pid: int, binary: Path, proc: Path = Path("/proc")) -> int | None:
    for entry in proc.iterdir():
        if entry.name.isdigit() and is_inferior(parent_pid, int(entry.name), binary, proc):
            return int(entry.name)
    return None


# Linux syscall numbers (unified table, x86-64 and arm64); used when this
# Python's os/signal modules lack the wrappers (conda-forge builds do).
_SYS_PIDFD_SEND_SIGNAL = 424
_SYS_PIDFD_OPEN = 434


def _syscall(number: int, *arguments: int) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(ctypes.c_long(number), *(ctypes.c_long(value) for value in arguments))
    if result < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))  # ESRCH -> ProcessLookupError
    return int(result)


def pidfd_open(pid: int) -> int:
    if hasattr(os, "pidfd_open"):
        return os.pidfd_open(pid)
    return _syscall(_SYS_PIDFD_OPEN, pid, 0)


def pidfd_send_signal(pidfd: int, signum: int) -> None:
    if hasattr(signal, "pidfd_send_signal"):
        signal.pidfd_send_signal(pidfd, signum)
    else:
        _syscall(_SYS_PIDFD_SEND_SIGNAL, pidfd, int(signum), 0, 0)


@dataclass
class Inferior:
    """The worldserver under gdb, held by pidfd so a recycled pid is never signalled."""
    pid: int
    pidfd: int

    def send(self, signum: int) -> bool:
        """False once the worldserver has exited (or was reaped by gdb)."""
        try:
            pidfd_send_signal(self.pidfd, signum)
            return True
        except ProcessLookupError:
            return False

    def close(self) -> None:
        if self.pidfd >= 0:
            os.close(self.pidfd)
            self.pidfd = -1


def wait_inferior(process: subprocess.Popen[bytes], binary: Path, timeout_sec: float,
                  backtrace: Path | None = None, proc: Path = Path("/proc")) -> Inferior:
    """The worldserver gdb started, pinned by pidfd before its identity is re-checked."""
    detail = f"; gdb log: {backtrace}" if backtrace else ""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f"gdb exited ({process.returncode}) before starting the worldserver{detail}")
        pid = inferior_pid(process.pid, binary, proc)
        if pid is not None:
            try:
                pidfd = pidfd_open(pid)
            except ProcessLookupError:
                continue
            try:
                # Signal 0 through the pidfd: the pinned process still lives,
                # and its identity is read again after pinning.
                pidfd_send_signal(pidfd, 0)
                pinned = is_inferior(process.pid, pid, binary, proc)
            except ProcessLookupError:
                pinned = False
            except BaseException:
                os.close(pidfd)
                raise
            if pinned:
                return Inferior(pid, pidfd)
            os.close(pidfd)
        time.sleep(0.05)
    raise RuntimeError(f"worldserver did not start under gdb before the startup deadline{detail}")


def summarize(output_dir: Path, max_frames: int = 16) -> dict[str, Any]:
    """shard_run.json summary: whether the worldserver died on a signal, and its first frames."""
    path = output_dir / BACKTRACE_NAME
    summary: dict[str, Any] = {"path": str(path), "present": path.is_file(), "crashed": False,
                               "signal": None, "frames": []}
    if not summary["present"]:
        return summary
    text = path.read_text(encoding="utf-8", errors="replace")
    marker = text.find(CRASH_MARKER)
    if marker < 0:
        return summary
    signal_number = re.match(r"\d+", text[marker + len(CRASH_MARKER):])
    summary.update(crashed=True, signal=int(signal_number.group()) if signal_number else None)
    backtrace = text.find("\n#0 ", marker)
    if backtrace >= 0:
        frames = []
        for line in text[backtrace + 1:].splitlines():
            if not line.startswith("#"):
                break
            frames.append(line.strip())
            if len(frames) == max_frames:
                break
        summary["frames"] = frames
    return summary

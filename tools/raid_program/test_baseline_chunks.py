"""Supervision of tools.raid_program.test_baseline's pytest processes ("chunks").

Every chunk runs ``python -m raid_test_baseline_runner`` (test_baseline_runner.py: ``pytest.main`` plus
a completion marker) with the result plugin (test_baseline_plugin.py) in its own session, so its whole
process group can be stopped. A chunk is clean (``chunk_problem`` returns None) only when all hold:

* it did not time out and was not killed by a signal;
* it wrote a results file, the plugin's ``finish`` line (every sessionfinish implementation before the
  plugin's trylast one returned) and the runner's ``complete`` line (nothing escaped ``pytest.main``:
  no hookwrapper, trylast hook, ``pytest_unconfigure`` or ``sys.exit`` error; and every atexit handler,
  run by the runner before the marker, succeeded), and no ``escaped`` or ``exit_error`` line;
* its exit code is 0 or 1 and equals both recorded statuses;
* with a non-zero exit code, its stderr (kept apart from stdout) holds no pytest ``INTERNALERROR>``
  line. The markers and the exit-code match are the source of truth: a traceback printed and handled
  (``traceback.print_exc()`` under ``-s`` or ``capsys.disabled()``) is not an error.

Termination: ``terminate_on_signals`` turns SIGTERM, SIGINT and SIGHUP into ``Terminated`` in the main
thread; the cleanup paths (``_Chunks`` stops every running chunk's process group, ``cleanup_on_exit``
reaps leftovers by run marker and removes the scratch) run with those signals blocked, so a second
signal cannot cut cleanup short. Chunks are started with signals unblocked (a child inherits the signal
mask, and tests must keep default signal behaviour); a chunk the signal catches between its start and
its registration still carries the run marker, so the reaper stops it. A supervisor killed by SIGKILL
takes its chunks down through the runner's PR_SET_PDEATHSIG.

Known limitation: after a SIGKILL of the supervisor, test descendants that started their own session
(e.g. a detached fake worldserver) survive, since nothing of the supervisor runs any more. They keep
the markers they inherited through the environment, so the next check or refresh reaps them at its
start (``reap_orphans``).

Every process carries ``RAID_TEST_BASELINE_RUN=<run id>`` (a uuid per check/refresh invocation) and
``RAID_TEST_BASELINE_SUPERVISOR=<supervisor pid>``. ``reap_leftovers`` kills only processes whose run
marker equals its own run id exactly; ``reap_orphans`` only processes whose supervisor no longer exists,
so a concurrent run of another invocation is never touched.
"""
from __future__ import annotations

import contextlib
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Iterable, Iterator

from tools.raid_program.test_baseline_runner import EXIT_ESCAPED

PLUGIN_SOURCE = Path(__file__).with_name("test_baseline_plugin.py")
PLUGIN_NAME = "raid_test_baseline_plugin"
RUNNER_SOURCE = Path(__file__).with_name("test_baseline_runner.py")
RUNNER_NAME = "raid_test_baseline_runner"
CHUNK_TIMEOUT_SEC = 1800
PYTEST_BASE = ("-p", "no:cacheprovider", "-p", PLUGIN_NAME, "-q", "--tb=no", "--no-header",
               "--continue-on-collection-errors")
RUN_ENV = "RAID_TEST_BASELINE_RUN"  # per-invocation marker every pytest process (and its children) inherits
SUPERVISOR_ENV = "RAID_TEST_BASELINE_SUPERVISOR"
OK_EXIT_CODES = (0, 1)  # pytest: all passed, some failed
EXIT_NAMES = {2: "interrupted", 3: "internal error", 4: "usage error", 5: "no tests collected",
              EXIT_ESCAPED: "an exception escaped pytest"}
INTERNAL_ERROR_PREFIX = "INTERNALERROR>"
TERMINATING_SIGNALS = (signal.SIGTERM, signal.SIGINT, signal.SIGHUP)


def new_run_id() -> str:
    """A unique id per check/refresh invocation: its scratch directory and its process marker."""
    return uuid.uuid4().hex[:16]


# --- signals ------------------------------------------------------------------------------------------

class Terminated(Exception):
    """The supervisor received SIGTERM, SIGINT or SIGHUP; cleanup runs as the exception unwinds."""

    def __init__(self, signum: int) -> None:
        super().__init__(signal.Signals(signum).name)
        self.signum = signum


@contextlib.contextmanager
def terminate_on_signals() -> Iterator[None]:
    """In the main thread, raise Terminated on the first SIGTERM/SIGINT/SIGHUP (later ones are ignored
    so they cannot interrupt the cleanup the first one started); elsewhere a no-op."""
    if threading.current_thread() is not threading.main_thread():
        yield
        return
    fired: list[int] = []

    def handler(signum, frame):
        if fired:
            return
        fired.append(signum)
        raise Terminated(signum)

    previous = {sig: signal.signal(sig, handler) for sig in TERMINATING_SIGNALS}
    try:
        yield
    finally:
        for sig, old in previous.items():
            signal.signal(sig, old)


@contextlib.contextmanager
def signals_blocked() -> Iterator[None]:
    """Defer the terminating signals over a critical section; a pending one is delivered after it."""
    old = signal.pthread_sigmask(signal.SIG_BLOCK, TERMINATING_SIGNALS)
    try:
        yield
    finally:
        signal.pthread_sigmask(signal.SIG_SETMASK, old)


# --- processes ----------------------------------------------------------------------------------------

def _support_dir(scratch: Path) -> Path:
    folder = scratch / "plugin"
    folder.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PLUGIN_SOURCE, folder / f"{PLUGIN_NAME}.py")
    shutil.copyfile(RUNNER_SOURCE, folder / f"{RUNNER_NAME}.py")
    return folder


def _env(support_dir: Path, output: Path, run_id: str) -> dict[str, str]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", RAID_TEST_BASELINE_OUTPUT=str(output),
               **{RUN_ENV: run_id, SUPERVISOR_ENV: str(os.getpid())})
    env["PYTHONPATH"] = os.pathsep.join(filter(None, [str(support_dir), env.get("PYTHONPATH", "")]))
    return env


def _kill_group(process: subprocess.Popen) -> None:
    for sig in (signal.SIGTERM, signal.SIGKILL):
        try:
            os.killpg(process.pid, sig)
        except (ProcessLookupError, PermissionError):
            return
        time.sleep(0.5)


def parse_results(path: Path, timed_out: bool = False) -> tuple[dict[str, dict[str, Any]], dict[str, Any]]:
    """(nodeid -> {outcome, when, message}, markers {"finish", "complete", "escaped"}) of one chunk file.

    A test that started but never reported is a failure when the runner did not complete: ``timeout``
    when its chunk hit the timeout, ``crashed`` otherwise (the process died under it).
    """
    results: dict[str, dict[str, Any]] = {}
    started: list[str] = []
    markers: dict[str, Any] = {"finish": None, "complete": None, "escaped": None, "exit_error": None}
    if path.exists():
        for line in path.read_text(errors="replace").splitlines():
            try:
                row = json.loads(line)
            except ValueError:
                continue
            event = row.get("event")
            if event == "start":
                started.append(row["nodeid"])
            elif event == "result":
                results[row["nodeid"]] = {key: row.get(key) for key in ("outcome", "when", "message")}
            elif event in ("finish", "complete"):
                markers[event] = int(row.get("exitstatus") or 0)
            elif event in ("escaped", "exit_error"):
                markers[event] = str(row.get("error") or "unknown error")
    if markers["complete"] is None:
        for nodeid in started:
            if nodeid not in results:
                results[nodeid] = {"outcome": "failed", "when": "timeout" if timed_out else "crashed",
                                   "message": "chunk timeout" if timed_out else "pytest process ended mid-test"}
    return results, markers


def stderr_problem(text: str, returncode: int | None) -> str | None:
    """pytest's own INTERNALERROR line on stderr of a chunk that exited non-zero, or None."""
    if not returncode:
        return None
    for line in text.splitlines():
        if line.startswith(INTERNAL_ERROR_PREFIX):
            return line.strip()[:200]
    return None


def chunk_problem(*, timed_out: bool, results_file: bool, markers: dict[str, Any], returncode: int | None,
                  timeout: float, stderr: str = "") -> str | None:
    """Why one pytest process did not run cleanly, or None (module docstring)."""
    if timed_out:
        return f"timed out after {timeout:.0f} s"
    if returncode is not None and returncode < 0:
        try:
            name = signal.Signals(-returncode).name
        except ValueError:
            name = f"signal {-returncode}"
        return f"pytest was killed by {name}"
    if markers.get("escaped"):
        return f"an exception escaped pytest: {markers['escaped']}"
    if markers.get("exit_error"):
        return f"an exit handler failed after pytest: {markers['exit_error']}"
    name = f", {EXIT_NAMES[returncode]}" if returncode in EXIT_NAMES else ""
    if not results_file:
        return f"no results file (exit {returncode}{name})"
    if markers.get("complete") is None:
        return f"the pytest runner never completed (exit {returncode}{name}): the process died or exited early"
    if returncode not in OK_EXIT_CODES:
        return f"pytest exit {returncode} ({EXIT_NAMES.get(returncode, 'unexpected')})"
    if markers.get("finish") is None:
        return f"the pytest session never finished (exit {returncode}): a sessionfinish hook failed"
    if not markers["finish"] == markers["complete"] == returncode:
        return (f"inconsistent exit statuses: session {markers['finish']}, pytest.main {markers['complete']}, "
                f"process {returncode}")
    line = stderr_problem(stderr, returncode)
    if line:
        return f"pytest internal error on stderr: {line}"
    return None


class _Chunks:
    """Argument groups run as separate pytest processes, ``jobs`` at a time, each in its own session."""

    def __init__(self, cwd: Path, groups: list[list[str]], jobs: int, scratch: Path, extra: Iterable[str],
                 timeout: float, label: str, run_id: str) -> None:
        self.cwd, self.jobs, self.scratch, self.extra = cwd, max(1, jobs), scratch, list(extra)
        self.timeout, self.label, self.total, self.run_id = timeout, label, len(groups), run_id
        self.pending = list(enumerate(groups))
        self.running: dict[int, dict[str, Any]] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.statuses: dict[int, int | None] = {}
        self.timed_out: list[int] = []
        self.errors: list[dict[str, Any]] = []
        self.support = _support_dir(scratch)
        self.started = time.monotonic()

    def _path(self, index: int, suffix: str) -> Path:
        return self.scratch / f"{self.label}-{index:03d}.{suffix}"

    def _start(self, index: int, group: list[str]) -> None:
        output = self._path(index, "jsonl")
        output.unlink(missing_ok=True)
        argv = [sys.executable, "-m", RUNNER_NAME, *PYTEST_BASE, *self.extra, *group]
        stdout, stderr = self._path(index, "log").open("w"), self._path(index, "err").open("w")
        # Not under signals_blocked: the child would inherit the blocked mask (see the module docstring).
        process = subprocess.Popen(argv, cwd=self.cwd, env=_env(self.support, output, self.run_id), stdout=stdout,
                                   stderr=stderr, stdin=subprocess.DEVNULL, start_new_session=True)
        self.running[index] = {"process": process, "begun": time.monotonic(), "output": output,
                               "files": (stdout, stderr), "group": group}

    def _stop(self, entry: dict[str, Any]) -> int | None:
        returncode = entry["process"].poll()  # the exit code before any cleanup signal
        _kill_group(entry["process"])  # the chunk's leftover children, e.g. fake worldservers
        entry["process"].wait()
        for handle in entry["files"]:
            handle.close()
        return returncode

    def _finish(self, index: int, timed_out: bool) -> None:
        with signals_blocked():
            entry = self.running[index]
            returncode = self._stop(entry)
            del self.running[index]
        if timed_out:
            self.timed_out.append(index)
        chunk, markers = parse_results(entry["output"], timed_out)
        self.results.update(chunk)
        self.statuses[index] = returncode if returncode is not None else entry["process"].returncode
        problem = chunk_problem(timed_out=timed_out, results_file=entry["output"].exists(), markers=markers,
                                returncode=returncode, timeout=self.timeout,
                                stderr=self._path(index, "err").read_text(errors="replace"))
        if problem:
            group = entry["group"]
            self.errors.append({"label": self.label, "chunk": index, "problem": problem, "exit_code": returncode,
                                "markers": markers, "args": group[:3] + (["..."] if len(group) > 3 else []),
                                "log": str(self._path(index, "err"))})
        print(f"  {self.label}: {len(self.statuses)}/{self.total} chunks, {len(self.results)} results, "
              f"{time.monotonic() - self.started:.0f} s", file=sys.stderr, flush=True)

    def run(self) -> dict[str, Any]:
        try:
            while self.pending or self.running:
                while self.pending and len(self.running) < self.jobs:
                    self._start(*self.pending.pop(0))
                time.sleep(0.2)
                for index, entry in list(self.running.items()):
                    if entry["process"].poll() is not None:
                        self._finish(index, False)
                    elif time.monotonic() - entry["begun"] > self.timeout:
                        self._finish(index, True)
        finally:
            with signals_blocked():  # interrupted (Terminated, KeyboardInterrupt, error): stop every chunk
                for entry in list(self.running.values()):
                    self._stop(entry)
                self.running.clear()
        return {"results": self.results, "exit_statuses": self.statuses, "timed_out_chunks": sorted(self.timed_out),
                "errors": self.errors, "seconds": round(time.monotonic() - self.started, 1)}


def run_pytest(cwd: Path, groups: list[list[str]], jobs: int, scratch: Path, extra: Iterable[str] = (),
               timeout: float = CHUNK_TIMEOUT_SEC, label: str = "run", run_id: str | None = None) -> dict[str, Any]:
    """Run each argument group as one pytest process, ``jobs`` at a time; merged plugin results.

    Every process carries ``RAID_TEST_BASELINE_RUN=run_id`` (a new id when None). Returns
    {"results": nodeid -> {outcome, when, message}, "exit_statuses", "timed_out_chunks", "errors", "seconds"};
    "errors" lists the chunks that did not run cleanly (chunk_problem).
    """
    scratch.mkdir(parents=True, exist_ok=True)
    return _Chunks(cwd, groups, jobs, scratch, extra, timeout, label, run_id or new_run_id()).run()


def _ancestors() -> set[int]:
    pids, pid = set(), os.getpid()
    while pid > 1 and pid not in pids:
        pids.add(pid)
        try:
            pid = int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])
        except (OSError, ValueError, IndexError):
            break
    return pids


def _sweep(should_kill) -> list[str]:
    """SIGKILL every process (not this one or an ancestor) whose environment ``should_kill`` accepts."""
    killed, skip = [], _ancestors()
    for proc in Path("/proc").iterdir():
        if not proc.name.isdigit() or int(proc.name) in skip:
            continue
        try:
            environ = dict(item.split(b"=", 1) for item in (proc / "environ").read_bytes().split(b"\0")
                           if b"=" in item)
            argv = (proc / "cmdline").read_bytes().split(b"\0")
        except OSError:
            continue
        if should_kill(environ):
            try:
                os.kill(int(proc.name), signal.SIGKILL)
                killed.append(f"{proc.name} {' '.join(part.decode(errors='replace') for part in argv[:2])}")
            except OSError:
                continue
    return killed


def reap_leftovers(run_id: str) -> list[str]:
    """Stop processes one invocation's pytest runs left behind (e.g. a test's fake worldserver that escaped
    its process group). Only processes whose environment holds exactly ``RAID_TEST_BASELINE_RUN=run_id``
    are touched: a real worldserver, another agent's test run or another refresh of the same commit
    carries no marker or a different one."""
    return _sweep(lambda environ: environ.get(RUN_ENV.encode()) == run_id.encode())


def reap_orphans() -> list[str]:
    """Stop marked processes whose supervisor is gone (killed by SIGKILL, so it could not reap them).
    A process of a supervisor that is still running is never touched."""
    def orphaned(environ: dict[bytes, bytes]) -> bool:
        supervisor = environ.get(SUPERVISOR_ENV.encode(), b"")
        return RUN_ENV.encode() in environ and supervisor.isdigit() and not Path(f"/proc/{int(supervisor)}").exists()
    return _sweep(orphaned)


@contextlib.contextmanager
def cleanup_on_exit(run_id: str, scratch: Path, keep: bool, what: str) -> Iterator[None]:
    """Reap the run's leftovers and remove its scratch however the body ends, with signals deferred."""
    try:
        yield
    finally:
        with signals_blocked():
            reaped = reap_leftovers(run_id)
            if reaped:
                print(f"{what}: stopped leftover test processes: {reaped}", file=sys.stderr)
            if not keep:
                shutil.rmtree(scratch, ignore_errors=True)

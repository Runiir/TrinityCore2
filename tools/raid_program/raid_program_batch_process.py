"""Process lifecycle of one ``program run-batches`` batch: launch shard_coordinator, and reap it on every exit path.

Signals. ``signal_guard`` replaces the SIGINT/SIGTERM/SIGHUP handlers with a handler that only records
the signal; it never raises. run-batches holds one guard for its whole loop and ``run_coordinator`` a
nested one, so from before the spawn until after the cleanup no signal can interrupt ``Popen`` (a
signal after fork is recorded; the pid is always known), the wait or the cleanup. Every recorded
signal stops the batch at a defined point:

* recorded before the spawn (in any active guard): nothing is spawned; ``BatchInterrupted``;
* recorded during the spawn or the wait: the wait ends and the batch is cleaned up;
* recorded during the cleanup: the cleanup finishes (a second signal only skips the grace period);
* after a verified cleanup any recorded signal raises ``BatchInterrupted``; a cleanup that cannot be
  verified raises ``CleanupUnverified`` whatever the exit reason (it always wins over the interrupt).

Cleanup. shard_coordinator runs in its own process group (``start_new_session``). The worldserver, or gdb
with the worldserver as its inferior under ``--gdb-backtrace``, runs in yet another session
(``shared_instance_console`` launches it with ``start_new_session``), so the group signal never reaches it:

1. the coordinator group gets SIGINT (its own teardown stops every shard and shuts the server down) and a
   grace period; if the coordinator or any member is still there, the group gets SIGKILL and must then be
   empty (a child that outlives the coordinator is found by its pgid);
2. every worldserver or gdb process whose argv names this batch's output directory (the shard config
   ``<output-dir>/worldserver.validation.conf``, the gdb script ``<output-dir>/worldserver.gdb``), plus
   the pids shard_run.json records while they still name it, gets SIGKILL (the worldserver first, then
   its gdb parent); the scan is repeated until one finds none.

Verification is fail-closed: a /proc read error other than "the process is gone", or a recorded pid
whose identity cannot be confirmed, makes it false. Every process operation is injectable, so tests
signal no real process except their own harmless sleeper.
"""
from __future__ import annotations

import contextlib
import errno
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Callable

from tools.raid_program.development_graph import GraphError

PROC = Path('/proc')
GRACE_SECONDS = 180       # the coordinator's teardown after SIGINT: stop every shard, shut the server down
KILL_WAIT_SECONDS = 30    # after SIGKILL: the group and the batch's servers must be gone
POLL_SECONDS = 0.5
SERVER_SCANS = 3          # repeated scans catch an inferior gdb forked while its parent was being killed
GUARDED = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
GONE = (errno.ENOENT, errno.ESRCH)


class BatchInterrupted(KeyboardInterrupt):
    """A signal stopped the batch; ``cleanup`` is its verified cleanup (None when nothing was spawned)."""

    def __init__(self, reason: str = 'interrupted', cleanup: dict | None = None):
        super().__init__(reason)
        self.reason, self.cleanup = reason, cleanup


class CleanupUnverified(GraphError):
    """The batch's processes could not be shown gone (it may also have been interrupted)."""

    def __init__(self, message: str, code: int | None, cleanup: dict, signals: list[str] | None = None):
        super().__init__(message)
        self.code, self.cleanup, self.signals = code, cleanup, list(signals or [])


class Uninspectable(Exception):
    """A /proc entry could not be read for a reason other than the process being gone."""


def _log(message: str) -> None:
    print('run-batches: ' + message, file=sys.stderr, flush=True)


class SignalGuard:
    def __init__(self):
        self.signals: list[str] = []
        self.installed = False


_GUARDS: list[SignalGuard] = []


def _record(signum, frame) -> None:
    name = signal.Signals(signum).name
    for guard in _GUARDS:
        guard.signals.append(name)


def pending_signals() -> list[str]:
    """Signals recorded by any active guard (an outer run-batches loop included)."""
    return [name for guard in _GUARDS for name in guard.signals]


@contextlib.contextmanager
def signal_guard():
    """Record SIGINT/SIGTERM/SIGHUP instead of acting on them; nested guards share one handler.

    The outermost guard installs the handler and restores the previous ones before it leaves the stack,
    so a signal is always either recorded by a guard or handled by the default behaviour, never lost.
    """
    guard = SignalGuard()
    previous = {}
    _GUARDS.append(guard)  # before the handler exists, so no recorded signal can miss this guard
    try:
        if len(_GUARDS) == 1:
            with contextlib.suppress(ValueError):  # not the main thread: the default handlers stay
                for signum in GUARDED:
                    previous[signum] = signal.signal(signum, _record)
        guard.installed = signal.getsignal(signal.SIGTERM) is _record
        yield guard
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        _GUARDS.remove(guard)


def _read(path: Path, binary: bool = False):
    """File contents, None when the process is gone, Uninspectable on any other error."""
    try:
        data = path.read_bytes()  # /proc may hold any bytes (comm, argv): never decode strictly
        return data if binary else data.decode('utf-8', errors='surrogateescape')
    except OSError as error:
        if error.errno in GONE:
            return None
        raise Uninspectable(f'{path}: {error}') from error


def _stat(proc: Path, pid: int) -> tuple[str, int, int] | None:
    """(state, ppid, pgrp); None when the process is gone; Uninspectable when unreadable or malformed."""
    text = _read(proc / str(pid) / 'stat')
    if text is None:
        return None
    fields = text[text.rfind(')') + 1:].split()  # comm may hold spaces and parentheses
    try:
        return fields[0], int(fields[1]), int(fields[2])
    except (IndexError, ValueError) as error:
        raise Uninspectable(f'{proc}/{pid}/stat is malformed') from error


def alive(proc: Path, pid: int) -> bool:
    """True while the process exists and is not a zombie; Uninspectable when that cannot be told."""
    row = _stat(proc, pid)
    return row is not None and row[0] not in ('Z', 'X')


def _pids(proc: Path) -> list[int]:
    try:
        return sorted(int(entry.name) for entry in proc.iterdir() if entry.name.isdigit())
    except OSError as error:
        raise Uninspectable(f'cannot scan {proc}: {error}') from error


def group_members(proc: Path, pgid: int) -> tuple[list[int], list[str]]:
    """(live members of a process group, inspection errors); any error means membership is unknown."""
    try:
        pids = _pids(proc)
    except Uninspectable as error:
        return [], [str(error)]
    members, errors = [], []
    for pid in pids:
        try:
            row = _stat(proc, pid)
        except Uninspectable as error:
            errors.append(str(error))
            continue
        if row and row[2] == pgid and row[0] not in ('Z', 'X'):
            members.append(pid)
    return members, errors


def _argv(proc: Path, pid: int) -> list[str] | None:
    data = _read(proc / str(pid) / 'cmdline', binary=True)
    return None if data is None else [arg.decode(errors='replace') for arg in data.split(b'\0') if arg]


def _kind_of(name: str) -> str | None:
    from tools.raid_program.raid_shard_preflight import is_worldserver_name
    if is_worldserver_name(name):
        return 'worldserver'
    return 'gdb' if os.path.basename(name.strip().removesuffix(' (deleted)')).startswith('gdb') else None


def recorded_pids(output_dir: Path) -> list[int]:
    """Server and debugger pids shard_run.json records (the worldserver lifecycle), if it was written."""
    try:
        summary = json.loads((output_dir / 'shard_run.json').read_text(encoding='utf-8'))
        lifecycle = (summary.get('worldserver') or {}).get('lifecycle') or {}
    except (OSError, ValueError, AttributeError):
        return []
    return sorted({value for key in ('server_pid', 'debugger_pid') if isinstance(value := lifecycle.get(key), int)})


def batch_servers(proc: Path, output_dir: Path) -> tuple[dict[int, str], list[str]]:
    """({pid: 'worldserver'|'gdb'} of live processes whose argv names the output directory, inspection errors).

    A recorded pid must be confirmed: alive with an argv that names the directory (ours) or not (reused and
    never signalled); an alive recorded pid whose argv cannot be read is an error, never an assumption.
    """
    marker = str(output_dir)
    errors: list[str] = []
    try:
        pids = set(_pids(proc))
    except Uninspectable as error:
        return {}, [str(error)]
    recorded = set(recorded_pids(output_dir))
    found = {}
    for pid in sorted(pids | recorded):
        if pid == os.getpid():
            continue
        try:
            if not alive(proc, pid):
                continue
            argv = _argv(proc, pid)
            if argv is None:
                continue  # exited between the reads
            if not argv:  # a kernel thread, or a process whose argv is gone
                if pid in recorded:
                    errors.append(f'recorded pid {pid} is alive but its identity cannot be confirmed (empty argv)')
                continue
            if not any(arg == marker or arg.startswith(marker + '/') for arg in argv):
                continue  # not this batch (a recorded pid reused by another process is never signalled)
            kind = _kind_of(argv[0])
            if kind is None:
                try:
                    kind = _kind_of(os.readlink(proc / str(pid) / 'exe'))
                except OSError as error:
                    if error.errno in GONE:
                        continue
                    errors.append(f'pid {pid} names {marker} but its executable cannot be read ({error})')
                    continue
            if kind:
                found[pid] = kind
        except Uninspectable as error:
            errors.append(str(error))
    return found, errors


def _until(done: Callable[[], bool], seconds: float, sleep, clock, hurry: Callable[[], bool] = lambda: False) -> bool:
    deadline = clock() + seconds
    while not done():
        if clock() >= deadline or hurry():
            return done()
        sleep(POLL_SECONDS)
    return True


def reap_group(process, *, proc: Path, killpg, sleep, clock, grace_seconds: float, kill_wait_seconds: float,
               hurry: Callable[[], bool]) -> dict:
    """SIGINT the coordinator's group, then SIGKILL it if anything remains; verify it is empty."""
    pgid, steps, errors = process.pid, [], []

    def send(signum: int) -> None:
        steps.append(signal.Signals(signum).name)
        try:
            killpg(pgid, signum)
        except ProcessLookupError:
            pass  # the group is already empty
        except OSError as error:
            errors.append(f'{signal.Signals(signum).name}: {error}')

    def clear() -> bool:
        members, problems = group_members(proc, pgid)
        return process.poll() is not None and not members and not problems
    if not clear():
        _log(f'stopping the batch: SIGINT to shard_coordinator group {pgid} (up to {grace_seconds:.0f} s for its '
             'teardown; a second interrupt skips the wait)')
        send(signal.SIGINT)
        _until(clear, grace_seconds, sleep, clock, hurry)
    if not clear():
        _log(f'SIGKILL to shard_coordinator group {pgid}')
        send(signal.SIGKILL)
        _until(clear, kill_wait_seconds, sleep, clock)
    members, problems = group_members(proc, pgid)
    exited = process.poll()
    return {'pgid': pgid, 'signals': steps, 'coordinator_exit': exited, 'members_left': members,
            'errors': errors + problems, 'verified': exited is not None and not members and not problems}


def reap_batch_servers(output_dir: Path, *, proc: Path, kill, sleep, clock, kill_wait_seconds: float) -> dict:
    """SIGKILL every worldserver (then gdb) of this batch; rescan until a scan finds none and reads cleanly."""
    killed: dict[str, str] = {}
    errors: list[str] = []
    found, problems = batch_servers(proc, output_dir)
    for _ in range(SERVER_SCANS):
        if not found:
            break
        for pid in sorted(found, key=lambda pid: (found[pid] != 'worldserver', pid)):  # the inferior before its gdb
            _log(f'SIGKILL to leftover {found[pid]} pid {pid} of {output_dir}')
            killed[str(pid)] = found[pid]
            try:
                kill(pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            except OSError as error:
                errors.append(f'pid {pid}: {error}')

        def gone(pids=tuple(found)) -> bool:
            try:
                return not any(alive(proc, pid) for pid in pids)
            except Uninspectable:
                return False
        _until(gone, kill_wait_seconds, sleep, clock)
        found, problems = batch_servers(proc, output_dir)
    survivors = sorted(found)
    errors += problems
    return {'found': killed, 'survivors': survivors, 'errors': errors, 'verified': not survivors and not problems}


def cleanup_batch(process, output_dir: Path, *, guard: SignalGuard | None = None, proc: Path | None = None,
                  killpg=None, kill=None, sleep=None, clock=None, grace_seconds: float = GRACE_SECONDS,
                  kill_wait_seconds: float = KILL_WAIT_SECONDS) -> dict:
    """Both reaping steps; ``verified`` only when the group and the batch servers are shown gone.

    Run it inside a signal guard: a signal then never aborts it; a second one skips the grace period.
    """
    proc, killpg, kill = proc or PROC, killpg or os.killpg, kill or os.kill  # resolved per call, never at import
    sleep, clock = sleep or time.sleep, clock or time.monotonic
    hurry = (lambda: len(guard.signals) >= 2) if guard is not None else (lambda: False)
    # Each step runs whatever the other did: an unexpected error in one marks it unverified, never skips the other.
    try:
        group = reap_group(process, proc=proc, killpg=killpg, sleep=sleep, clock=clock, grace_seconds=grace_seconds,
                           kill_wait_seconds=kill_wait_seconds, hurry=hurry)
    except Exception as error:  # noqa: BLE001 - fail closed, then still sweep the servers
        group = {'pgid': getattr(process, 'pid', None), 'signals': [], 'coordinator_exit': None, 'members_left': [],
                 'errors': [f'group cleanup failed: {type(error).__name__}: {error}'], 'verified': False}
    try:
        servers = reap_batch_servers(output_dir, proc=proc, kill=kill, sleep=sleep, clock=clock,
                                     kill_wait_seconds=kill_wait_seconds)
    except Exception as error:  # noqa: BLE001 - fail closed
        servers = {'found': {}, 'survivors': [], 'errors': [f'server cleanup failed: {type(error).__name__}: {error}'],
                   'verified': False}
    return {'group': group, 'servers': servers, 'verified': group['verified'] and servers['verified']}


def describe(cleanup: dict) -> str:
    group, servers = cleanup['group'], cleanup['servers']
    parts = []
    if not group['verified']:
        parts.append(f"shard_coordinator group {group['pgid']} not shown empty: members {group['members_left']}, "
                     f"coordinator exit {group['coordinator_exit']}"
                     + (f"; {'; '.join(group['errors'])}" if group['errors'] else ''))
    if not servers['verified']:
        parts.append(f"batch servers not shown gone: survivors {servers['survivors']} (killed {servers['found']})"
                     + (f"; {'; '.join(servers['errors'])}" if servers['errors'] else ''))
    return '; '.join(parts)


def _wait(process, timeout: float, guard: SignalGuard, sleep, clock) -> int | None:
    """The exit status, 124 at the emergency cap, or None as soon as a signal is recorded."""
    deadline = clock() + timeout
    while not guard.signals:
        code = process.poll()
        if code is not None:
            return code
        if clock() >= deadline:
            _log(f'shard_coordinator passed the {timeout} s emergency cap')
            return 124
        sleep(POLL_SECONDS)
    return None


def run_coordinator(root: Path, plan_path: str, output_dir: Path, log_path: Path, timeout: int, *,
                    popen=None, **options) -> int:
    """shard_coordinator for one batch in its own process group; reaped on every exit path.

    Returns its exit status (124 at the emergency cap). Raises CleanupUnverified when the group or the batch
    servers cannot be shown gone (whatever ended the batch), else BatchInterrupted when any signal was
    recorded before, during or after the spawn, the wait or the cleanup.
    """
    command = ['nice', '-n', '5', sys.executable, '-m', 'tools.raid_program.shard_coordinator', '--plan', plan_path,
               '--output-dir', str(output_dir), '--gdb-backtrace']
    sleep, clock = options.get('sleep') or time.sleep, options.get('clock') or time.monotonic
    process, code, cleanup = None, None, None
    with signal_guard() as guard:
        before = pending_signals()
        if before:  # an outer guard (the run-batches loop) already recorded one: spawn nothing
            raise BatchInterrupted(f"signal {', '.join(before)} before the batch started", None)
        with log_path.open('w', encoding='utf-8') as log:
            try:
                # A signal during Popen (even after fork) is only recorded, so the pid is always known here.
                process = (popen or subprocess.Popen)(command, cwd=root, stdout=log, stderr=subprocess.STDOUT,
                                                      start_new_session=True)
                code = _wait(process, timeout, guard, sleep, clock)
            except KeyboardInterrupt:  # raised by other means than the guarded signals: the same path
                guard.signals.append('KeyboardInterrupt')
            finally:
                if process is not None:
                    cleanup = cleanup_batch(process, output_dir, guard=guard, **options)
        signals = list(guard.signals)
    if cleanup is not None and not cleanup['verified']:
        raise CleanupUnverified('batch cleanup could not be verified: ' + describe(cleanup)
                                + (f" (interrupted by {', '.join(signals)})" if signals else ''), code, cleanup, signals)
    if signals:
        raise BatchInterrupted(f"signal {', '.join(signals)}", cleanup)
    return code if code is not None else process.poll()

"""Reaping of a run-batches batch on every exit path: a fake /proc, fake signals, a fake clock and a fake Popen.

Signals are real: tests raise SIGINT/SIGTERM at this process while the guard's recording handler is
installed (it never raises). The only real child is a harmless sleeper in
test_real_popen_termination_after_fork_is_reaped; nothing else is launched or signalled.
"""
from __future__ import annotations

import os
import shutil
import signal
import subprocess
import threading
from pathlib import Path

import pytest

from tools.raid_program import raid_program_batch_process as process_module
from tools.raid_program.raid_program_batch_process import (
    BatchInterrupted, CleanupUnverified, run_coordinator, signal_guard)

COORDINATOR, CHILD, GDB, SERVER, PLAY = 500, 501, 600, 601, 700
main_thread = pytest.mark.skipif(threading.current_thread() is not threading.main_thread(),
                                 reason='signal handlers need the main thread')


class World:
    """A fake /proc plus the signal, clock and Popen fakes that act on it."""

    def __init__(self, folder: Path, output: Path):
        self.proc, self.output = folder / 'proc', output
        self.proc.mkdir()
        self.now, self.killpg_calls, self.kill_calls = 0.0, [], []
        self.on_killpg: dict[int, callable] = {}
        self.on_kill: dict[int, callable] = {}
        self.unkillable: set[int] = set()
        self.process = None

    def add(self, pid: int, pgid: int, argv: list[str], ppid: int = 1) -> None:
        folder = self.proc / str(pid)
        folder.mkdir(parents=True)
        (folder / 'stat').write_text(f'{pid} ({Path(argv[0]).name[:15]}) S {ppid} {pgid} {pgid} 0 -1\n')
        (folder / 'cmdline').write_bytes(b'\0'.join(arg.encode() for arg in argv) + b'\0')
        os.symlink(argv[0], folder / 'exe')

    def remove(self, *pids: int) -> None:
        for pid in pids:
            shutil.rmtree(self.proc / str(pid), ignore_errors=True)

    def spawn_coordinator(self) -> None:
        self.add(COORDINATOR, COORDINATOR, ['nice', '-n', '5', 'python', '-m', 'tools.raid_program.shard_coordinator',
                                            '--output-dir', str(self.output)])

    def batch(self, play_server: bool = True) -> None:
        """The coordinator and a child in its group; gdb and the worldserver in their own session."""
        self.spawn_coordinator()
        self.add(CHILD, COORDINATOR, ['/usr/bin/mysql', '--batch'], ppid=COORDINATOR)
        self.add(GDB, GDB, ['/usr/bin/gdb', '-q', '-nx', '-batch', '-x', f'{self.output}/worldserver.gdb'],
                 ppid=COORDINATOR)
        self.add(SERVER, GDB, ['/repo/build/bin/worldserver', '--config', f'{self.output}/worldserver.validation.conf'],
                 ppid=GDB)
        if play_server:  # a live play server: never ours, never signalled
            self.add(PLAY, PLAY, ['/repo/build/bin/worldserver', '--config', '/tmp/play/worldserver-play.conf'])

    def sleep(self, seconds: float) -> None:
        self.now += seconds

    def clock(self) -> float:
        return self.now

    def killpg(self, pgid: int, signum: int) -> None:
        self.killpg_calls.append((pgid, signal.Signals(signum).name))
        action = self.on_killpg.get(signum)
        if action:
            action()

    def kill(self, pid: int, signum: int) -> None:
        self.kill_calls.append((pid, signal.Signals(signum).name))
        if pid in self.on_kill:
            self.on_kill.pop(pid)()
        if pid not in self.unkillable:
            self.remove(pid)

    def options(self, **extra) -> dict:
        return {'proc': self.proc, 'killpg': self.killpg, 'kill': self.kill, 'sleep': self.sleep,
                'clock': self.clock, 'grace_seconds': 180, 'kill_wait_seconds': 30} | extra


class FakeProcess:
    """poll() runs ``on_poll`` (which may raise a real signal) and returns the exit status once exited."""

    def __init__(self, world: World, on_poll=None):
        self.world, self.pid, self.returncode, self.on_poll = world, COORDINATOR, None, on_poll
        world.process = self

    def exit(self, code: int) -> None:
        self.returncode = code
        self.world.remove(COORDINATOR)

    def poll(self):
        if self.on_poll is not None and self.returncode is None:
            self.on_poll(self)
        return self.returncode


def launcher(world: World, on_poll=None, seen: dict | None = None, during_spawn=None):
    def popen(command, **options):
        if seen is not None:
            seen.update(command=command, **options)
        process = FakeProcess(world, on_poll)
        if during_spawn is not None:  # after the fork, before Popen returns
            during_spawn()
        return process
    return popen


def interrupt_once(name: str):
    def on_poll(process):
        if not getattr(process, 'signalled', False):
            process.signalled = True
            signal.raise_signal(getattr(signal, name))
    return on_poll


def exits(code: int):
    def on_poll(process):
        process.exit(code)
    return on_poll


@pytest.fixture
def world(tmp_path):
    output = tmp_path / 'run' / 'bwd-r02-b1-20260930T000000Z'
    output.mkdir(parents=True)
    return World(tmp_path, output)


def run(world: World, on_poll=None, seen=None, timeout: int = 11400, during_spawn=None, **extra) -> int:
    log = world.output.with_name(world.output.name + '.coordinator.log')
    return run_coordinator(Path('/repo'), 'plans/b1.json', world.output, log, timeout,
                           popen=launcher(world, on_poll, seen, during_spawn), **world.options(**extra))


@main_thread
def test_run_coordinator_interrupt_reaps_group(world):
    """Ctrl-C during the wait: SIGINT to the coordinator group; its teardown exits, but gdb and the worldserver
    run in another session and survive it, so they are killed (the worldserver first); the play server is not."""
    world.batch()
    world.on_killpg[signal.SIGINT] = lambda: (world.process.exit(130), world.remove(CHILD))
    seen = {}
    before = signal.getsignal(signal.SIGINT)
    with pytest.raises(BatchInterrupted, match='signal SIGINT') as caught:
        run(world, interrupt_once('SIGINT'), seen)
    assert signal.getsignal(signal.SIGINT) is before, 'the previous handlers are restored'
    cleanup = caught.value.cleanup
    assert cleanup['verified'] and world.killpg_calls == [(COORDINATOR, 'SIGINT')]
    assert world.kill_calls == [(SERVER, 'SIGKILL'), (GDB, 'SIGKILL')], 'the inferior first, then its gdb parent'
    assert cleanup['servers']['found'] == {str(SERVER): 'worldserver', str(GDB): 'gdb'}
    assert (world.proc / str(PLAY)).is_dir(), 'a worldserver of another run is never signalled'
    assert seen['start_new_session'] and seen['command'][-5:] == [
        '--plan', 'plans/b1.json', '--output-dir', str(world.output), '--gdb-backtrace']


def test_timeout_reaps_group_even_if_parent_exits(world):
    """At the emergency cap the coordinator exits on SIGINT but a child of its group ignores it: the group still
    gets SIGKILL and must be empty; the exit status is 124."""
    world.batch(play_server=False)
    world.remove(GDB, SERVER)  # the coordinator's teardown already stopped the server
    world.on_killpg[signal.SIGINT] = lambda: world.process.exit(130)
    world.on_killpg[signal.SIGKILL] = lambda: world.remove(CHILD)
    assert run(world, timeout=5) == 124
    assert world.killpg_calls == [(COORDINATOR, 'SIGINT'), (COORDINATOR, 'SIGKILL')]
    assert world.now >= 5 + 180, 'the grace period ran out before SIGKILL'
    assert not (world.proc / str(CHILD)).exists() and world.kill_calls == []


@main_thread
def test_first_interrupt_during_cleanup_stops_batch(world):
    """The coordinator exited 0, then the first SIGTERM arrives while a leftover server is being killed: cleanup
    finishes, and the batch ends in BatchInterrupted instead of returning 0 (run-batches must not continue)."""
    world.batch(play_server=False)
    world.remove(CHILD)
    world.on_kill[SERVER] = lambda: signal.raise_signal(signal.SIGTERM)
    with pytest.raises(BatchInterrupted, match='signal SIGTERM') as caught:
        run(world, exits(0))
    assert caught.value.cleanup['verified'] and world.kill_calls == [(SERVER, 'SIGKILL'), (GDB, 'SIGKILL')]
    assert world.killpg_calls == [], 'the coordinator had exited: its group was already empty'


@main_thread
def test_interrupt_with_survivors_uses_unverified_failure(world):
    """Interrupted and a server survives SIGKILL: CleanupUnverified (never a claim that processes stopped)."""
    world.batch(play_server=False)
    world.on_killpg[signal.SIGINT] = lambda: (world.process.exit(130), world.remove(CHILD))
    world.unkillable.add(SERVER)
    with pytest.raises(CleanupUnverified, match=rf'survivors \[{SERVER}\].*interrupted by SIGTERM') as caught:
        run(world, interrupt_once('SIGTERM'))
    assert caught.value.signals == ['SIGTERM'] and not caught.value.cleanup['verified']


@main_thread
def test_interrupt_during_spawn_does_not_orphan_child(world):
    """SIGTERM after the fork, before Popen returns: only recorded, so the pid is known and the child is reaped."""
    world.on_killpg[signal.SIGINT] = lambda: world.process.exit(130)
    with pytest.raises(BatchInterrupted, match='signal SIGTERM') as caught:
        run(world, during_spawn=lambda: (world.spawn_coordinator(), signal.raise_signal(signal.SIGTERM)))
    assert caught.value.cleanup['verified'] and world.killpg_calls == [(COORDINATOR, 'SIGINT')]
    assert world.process.returncode == 130 and not (world.proc / str(COORDINATOR)).exists()


@main_thread
def test_a_signal_already_recorded_by_the_loop_spawns_nothing(world):
    spawned = []
    with signal_guard():
        signal.raise_signal(signal.SIGHUP)
        with pytest.raises(BatchInterrupted, match='before the batch started') as caught:
            run_coordinator(Path('/repo'), 'plans/b1.json', world.output, world.output.with_name('x.log'), 60,
                            popen=lambda *args, **kwargs: spawned.append(args), **world.options())
    assert spawned == [] and caught.value.cleanup is None


@main_thread
def test_real_popen_termination_after_fork_is_reaped(tmp_path):
    """A real harmless sleeper as the 'coordinator'; SIGTERM arrives after its fork, before Popen returns. The
    real cleanup (real /proc, real killpg on the sleeper's own session) must stop and reap it."""
    sleeper = shutil.which('sleep')
    if not sleeper:
        pytest.skip('no sleep binary')
    output = tmp_path / 'out'
    output.mkdir()
    spawned = []

    def popen(command, **options):
        assert options['start_new_session'], 'the sleeper gets its own session like the coordinator'
        process = subprocess.Popen([sleeper, '120'], **options)
        spawned.append(process)
        signal.raise_signal(signal.SIGTERM)  # after the fork, before Popen returns
        return process
    try:
        with pytest.raises(BatchInterrupted, match='signal SIGTERM') as caught:
            run_coordinator(tmp_path, 'plans/b1.json', output, tmp_path / 'out.log', 60, popen=popen,
                            grace_seconds=10, kill_wait_seconds=5)
    finally:
        for process in spawned:  # never leave the sleeper behind, even if the assertion failed
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
    process = spawned[0]
    assert caught.value.cleanup['verified'] and caught.value.cleanup['group']['signals'] == ['SIGINT']
    assert process.returncode == -signal.SIGINT, 'stopped by the group SIGINT and reaped (poll returned its status)'
    assert not Path(f'/proc/{process.pid}').exists() or process_module._stat(Path('/proc'), process.pid)[1] != os.getpid()


def test_stat_access_error_cannot_certify_cleanup(world):
    """An unreadable stat (not 'gone') of any process makes group membership unknown: never verified."""
    world.spawn_coordinator()
    world.add(CHILD, COORDINATOR, ['/usr/bin/mysql'])
    stat = world.proc / str(CHILD) / 'stat'
    stat.unlink()
    stat.mkdir()  # reading it fails with EISDIR, not ENOENT
    world.on_killpg[signal.SIGINT] = lambda: world.process.exit(130)
    with pytest.raises(CleanupUnverified, match=f'group {COORDINATOR} not shown empty.*{CHILD}/stat') as caught:
        run(world, timeout=1)
    group = caught.value.cleanup['group']
    assert not group['verified'] and group['signals'] == ['SIGINT', 'SIGKILL'] and group['members_left'] == []


def test_an_unreadable_candidate_argv_cannot_certify_cleanup(world):
    world.add(SERVER, SERVER, ['/repo/build/bin/worldserver', '--config', f'{world.output}/worldserver.validation.conf'])
    cmdline = world.proc / str(SERVER) / 'cmdline'
    cmdline.unlink()
    cmdline.mkdir()
    found, errors = process_module.batch_servers(world.proc, world.output)
    assert found == {} and errors and 'cmdline' in errors[0]
    with pytest.raises(CleanupUnverified, match='batch servers not shown gone'):
        run(world, exits(0))


def test_a_recorded_pid_whose_identity_cannot_be_confirmed_is_unverified(world):
    (world.output / 'shard_run.json').write_text('{"worldserver": {"lifecycle": {"server_pid": 601}}}')
    world.add(SERVER, SERVER, ['x'])
    (world.proc / str(SERVER) / 'cmdline').write_bytes(b'')  # alive, argv unreadable as empty
    found, errors = process_module.batch_servers(world.proc, world.output)
    assert found == {} and 'identity cannot be confirmed' in errors[0]


def test_a_normal_exit_still_sweeps_the_group_and_the_batch_servers(world):
    world.batch(play_server=False)
    world.remove(CHILD)
    assert run(world, exits(0)) == 0
    assert world.killpg_calls == [] and world.kill_calls == [(SERVER, 'SIGKILL'), (GDB, 'SIGKILL')]


def test_a_clean_exit_signals_nothing(world):
    assert run(world, exits(1)) == 1 and world.killpg_calls == [] and world.kill_calls == []


def test_unverified_cleanup_names_the_survivors(world):
    world.batch(play_server=False)
    world.on_killpg[signal.SIGINT] = lambda: world.process.exit(130)  # the child survives SIGINT and SIGKILL
    world.unkillable.add(SERVER)
    with pytest.raises(CleanupUnverified, match=rf'members \[{CHILD}\].*survivors \[{SERVER}\]') as caught:
        run(world, timeout=1)
    assert caught.value.code == 124 and not caught.value.cleanup['verified'] and caught.value.signals == []


def test_a_recorded_pid_reused_by_another_process_is_never_signalled(world):
    (world.output / 'shard_run.json').write_text(
        '{"worldserver": {"lifecycle": {"server_pid": 700, "debugger_pid": 600}}}')
    world.add(PLAY, PLAY, ['/repo/build/bin/worldserver', '--config', '/tmp/play/worldserver-play.conf'])
    world.add(GDB, GDB, ['/usr/bin/gdb', '-q', '-nx', '-batch', '-x', f'{world.output}/worldserver.gdb'])
    assert process_module.recorded_pids(world.output) == [600, 700]
    assert process_module.batch_servers(world.proc, world.output) == ({GDB: 'gdb'}, [])


def test_an_inferior_forked_during_the_kill_is_found_by_the_rescan(world):
    world.add(GDB, GDB, ['/usr/bin/gdb', '-q', '-nx', '-batch', '-x', f'{world.output}/worldserver.gdb'])
    world.on_kill[GDB] = lambda: world.add(SERVER, GDB, ['/repo/build/bin/worldserver', '--config',
                                                        f'{world.output}/worldserver.validation.conf'])
    assert run(world, exits(0)) == 0
    assert world.kill_calls == [(GDB, 'SIGKILL'), (SERVER, 'SIGKILL')]


def test_an_unscannable_proc_is_unverified(world):
    shutil.rmtree(world.proc)
    with pytest.raises(CleanupUnverified, match='cannot scan'):
        run(world, exits(0))


@main_thread
def test_a_second_signal_only_skips_the_grace_period(world):
    world.batch(play_server=False)
    world.on_killpg[signal.SIGINT] = lambda: signal.raise_signal(signal.SIGTERM)  # the second signal
    world.on_killpg[signal.SIGKILL] = lambda: (world.process.exit(-9), world.remove(CHILD))
    with pytest.raises(BatchInterrupted, match='signal SIGINT, SIGTERM') as caught:
        run(world, interrupt_once('SIGINT'))
    assert caught.value.cleanup['verified'] and world.now < 180
    assert world.killpg_calls == [(COORDINATOR, 'SIGINT'), (COORDINATOR, 'SIGKILL')]


def test_non_utf8_proc_comm_cannot_abort_server_cleanup(world):
    """A non-UTF-8 comm in some stat: the group scan must not raise, and the server sweep still runs."""
    world.add(CHILD + 50, CHILD + 50, ['/usr/bin/odd'])
    (world.proc / str(CHILD + 50) / 'stat').write_bytes(b'551 (odd\xff\xfename) S 1 551 551 0 -1\n')
    world.add(GDB, GDB, ['/usr/bin/gdb', '-q', '-nx', '-batch', '-x', f'{world.output}/worldserver.gdb'])
    world.add(SERVER, GDB, ['/repo/build/bin/worldserver', '--config', f'{world.output}/worldserver.validation.conf'])
    assert run(world, exits(0)) == 0
    assert world.kill_calls == [(SERVER, 'SIGKILL'), (GDB, 'SIGKILL')]


def test_an_exception_in_the_group_step_still_sweeps_the_servers(world, monkeypatch):
    world.add(SERVER, SERVER, ['/repo/build/bin/worldserver', '--config', f'{world.output}/worldserver.validation.conf'])

    def broken(*args, **kwargs):
        raise UnicodeDecodeError('utf-8', b'\xff', 0, 1, 'boom')
    monkeypatch.setattr(process_module, 'reap_group', broken)
    with pytest.raises(CleanupUnverified, match='group cleanup failed: UnicodeDecodeError') as caught:
        run(world, exits(0))
    assert world.kill_calls == [(SERVER, 'SIGKILL')] and caught.value.cleanup['servers']['verified']

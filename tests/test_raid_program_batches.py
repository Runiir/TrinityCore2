"""program run-batches with a fake coordinator, fake ingest and fake process inventory (never a real worldserver)."""
from __future__ import annotations

import json
import os
import signal
import subprocess
import threading
from pathlib import Path

import pytest

from tools.raid_program import raid_program, raid_program_batches as batches, raid_program_rounds as rounds
from tools.raid_program import raid_program_runs as runs
from tools.raid_program.development_graph import GraphError

from tests.test_raid_program_rounds import (  # noqa: F401 - the world fixture is used by name
    BINARY, RAID, fake_build, program, sha, world)

LABEL = 'bwd-r01-test'
COHORTS = [f'{RAID}_10n_alpha_c0', f'{RAID}_10n_beta_c0']
PLENTY = {'headroom_bytes': 1 << 40, 'filesystem_available_bytes': 1 << 40, 'quota_available_bytes': None}


class Loop:
    """Shared tally: the fake coordinator writes shard runs, the fake ingest adds kills, the counter reads them."""

    def __init__(self, root: Path, needed: int = 3, gain: dict | None = None, write: bool = True,
                 errors: list | None = None, binary: str = BINARY):
        self.root, self.needed, self.write, self.binary = root, needed, write, binary
        self.gain = {'alpha': 1, 'beta': 1} if gain is None else gain
        self.kills = {'alpha': 0, 'beta': 0}
        self.errors, self.calls, self.stamps = errors or [], [], 0

    def coordinator(self, root, plan_path, output, log, timeout):
        self.calls.append({'plan': plan_path, 'output': str(output), 'timeout': timeout})
        log.write_text('shard_coordinator log\nworldserver crashed: SIGSEGV\n')
        if not self.write:
            return 134
        shards = []
        for cohort in COHORTS:
            run_dir = output / 'shards' / cohort
            run_dir.mkdir(parents=True)
            (run_dir / 'report.json').write_text('{}')
            shards.append({'cohort_id': cohort, 'run_dir': str(run_dir), 'native_clear': True,
                           'completion_reason': 'validation_route_manifest_complete', 'lockout': None, 'error': ''})
        (output / 'shard_run.json').write_text(json.dumps({
            'schema': 'raid_shard_run_v1', 'run_id': f'run{len(self.calls)}', 'terminal_reason': 'completed',
            'worldserver': {'path': '/w', 'sha256': self.binary}, 'shards': shards}))
        return 0

    def ingest(self, root, label):
        for boss, gain in self.gain.items():
            self.kills[boss] += gain
        rounds.current_round(program(root))  # the state is readable between steps
        return {'ingested': [{'boss_key': boss} for boss, gain in self.gain.items() if gain],
                'errors': list(self.errors)}

    def counter(self, root, scenario, label):
        assert label == LABEL
        return self.kills[scenario.rsplit('_', 1)[-1]], self.needed

    def stamp(self):
        self.stamps += 1
        return f'20260929T0000{self.stamps:02d}Z'

    def run(self, root, **options):
        options.setdefault('inventory', lambda: [])
        options.setdefault('headroom', lambda path: dict(PLENTY))
        return batches.run_batches(root, LABEL, sha(root), coordinator=self.coordinator, ingest=self.ingest,
                                   counter=self.counter, stamp=self.stamp, **options)


@pytest.fixture
def ready(world, tmp_path_factory, monkeypatch):
    """A built round with written plans; run roots go to a pytest dir under /tmp (the archive requires /tmp)."""
    root = world['root']
    monkeypatch.setattr(batches, 'RUN_ROOT', tmp_path_factory.mktemp('runroot'))
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='x')
    fake_build(root)
    runs.run_plans(root)
    return world


def test_the_loop_runs_until_every_target_boss_has_its_kills(ready):
    root = ready['root']
    loop = Loop(root)
    result = loop.run(root)
    assert result['stopped'] == 'targets_met' and result['exit_status'] == 0 and len(loop.calls) == 3
    assert result['kills'] == {'alpha': {'counted': 3, 'needed': 3}, 'beta': {'counted': 3, 'needed': 3}}
    assert all(Path(call['output']).name.startswith(f'{LABEL}-b1-') for call in loop.calls)
    assert all(call['plan'].endswith('boss_shards_plan_b1.json') for call in loop.calls)
    recorded = rounds.current_round(program(root))['runs']
    assert [run['run_id'] for run in recorded] == ['run1', 'run2', 'run3'] and not any(r.get('failed') for r in recorded)
    assert all(row['gained'] == {'alpha': 1, 'beta': 1} for row in result['batches'])
    assert 'does not commit' in result['next_action'] and f'program assess --label {LABEL}' in result['next_action']


def test_targets_already_met_run_nothing(ready):
    root = ready['root']
    loop = Loop(root)
    loop.run(root, max_batches=5)
    again = Loop(root)
    again.kills = {'alpha': 3, 'beta': 3}
    result = again.run(root)
    assert result['stopped'] == 'targets_met' and again.calls == [] and result['batches'] == []


def test_a_batch_without_a_counted_kill_stops_the_loop(ready):
    root = ready['root']
    loop = Loop(root, gain={'alpha': 0, 'beta': 0})
    result = loop.run(root)
    assert result['stopped'] == 'no_progress' and len(loop.calls) == 1 and result['exit_status'] == 1
    assert result['short'] == ['alpha', 'beta'] and result['batches'][0]['gained'] == {'alpha': 0, 'beta': 0}


def test_progress_for_any_short_boss_continues_until_max_batches(ready):
    root = ready['root']
    loop = Loop(root, needed=10, gain={'alpha': 1, 'beta': 0})
    result = loop.run(root, max_batches=2)
    assert result['stopped'] == 'max_batches' and len(loop.calls) == 2 and result['kills']['alpha']['counted'] == 2


def test_a_batch_without_shard_run_is_recorded_as_failed(ready):
    root = ready['root']
    loop = Loop(root, write=False)
    result = loop.run(root)
    assert result['stopped'] == 'batch_failed' and len(loop.calls) == 1
    failed = rounds.current_round(program(root))['runs'][-1]
    assert failed['failed'] and failed['batch'] == 1 and 'exited 134 without shard_run.json' in failed['reason']
    assert 'SIGSEGV' in failed['reason'] and 'SIGSEGV' in result['batches'][0]['failed']


class SetupFailedLoop(Loop):
    """The coordinator refused before any shard ran but still wrote shard_run.json (round 3, BWD 10N)."""

    def coordinator(self, root, plan_path, output, log, timeout):
        self.calls.append({'plan': plan_path, 'output': str(output), 'timeout': timeout})
        log.write_text('shard_coordinator log\n')
        output.mkdir(parents=True)
        (output / 'shard_run.json').write_text(json.dumps({
            'schema': 'raid_shard_run_v1', 'run_id': None, 'terminal_reason': 'setup_failed',
            'error': 'raid shard provisioning refused: gear stage missing', 'shards': [], 'ingest': [],
            'worldserver': {'path': '/w', 'sha256': self.binary}}))
        return 1


def test_a_setup_failed_shard_run_without_shards_is_recorded_as_failed(ready):
    root = ready['root']
    loop = SetupFailedLoop(root)
    result = loop.run(root)
    assert result['stopped'] == 'batch_failed' and len(loop.calls) == 1 and 'error' not in result['batches'][0]
    failed = rounds.current_round(program(root))['runs'][-1]
    assert failed['failed'] and failed['batch'] == 1 and failed['terminal_reason'] == 'no_shard_run'
    assert 'setup_failed' in failed['reason'] and 'gear stage missing' in failed['reason']
    assert 'gear stage missing' in result['batches'][0]['failed'] and result['batches'][0]['shard_run']


def test_setup_failure_detection_needs_no_shards_and_setup_failed(tmp_path):
    summary = tmp_path / 'shard_run.json'
    assert batches._setup_failure(summary) is None  # absent: the no-shard_run path reports it
    summary.write_text('{not json')
    assert batches._setup_failure(summary) is None
    summary.write_text(json.dumps({'terminal_reason': 'setup_failed', 'error': 'boom', 'shards': []}))
    assert batches._setup_failure(summary) == 'boom'
    # Negative controls: shards that ran, or another terminal reason, keep the normal record path.
    summary.write_text(json.dumps({'terminal_reason': 'setup_failed', 'error': 'x',
                                   'shards': [{'cohort_id': COHORTS[0]}]}))
    assert batches._setup_failure(summary) is None
    summary.write_text(json.dumps({'terminal_reason': 'completed', 'shards': []}))
    assert batches._setup_failure(summary) is None


def test_ingest_errors_stop_the_loop(ready):
    root = ready['root']
    loop = Loop(root, errors=[{'cohort_id': COHORTS[0], 'error': 'evidence not archived'}])
    result = loop.run(root)
    assert result['stopped'] == 'ingest_errors' and len(loop.calls) == 1 and result['batches'][0]['ingest']['errors']


def test_a_record_error_keeps_the_batch_row_and_stops(ready):
    root = ready['root']
    loop = Loop(root, binary='f' * 64)
    result = loop.run(root)
    assert result['stopped'] == 'error' and "not this round's build" in result['error']
    assert result['batches'][0]['exit_status'] == 0 and result['batches'][0]['output_dir']


def test_a_real_worldserver_refuses_before_anything_runs(ready):
    root = ready['root']
    loop = Loop(root)
    real = [{'pid': 42, 'paths': ['/home/u/trinity/build/src/server/worldserver/worldserver'], 'fake': False}]
    with pytest.raises(GraphError, match='a real worldserver is running .*pid 42.*Never stop a live play server'):
        loop.run(root, inventory=lambda: real)
    assert loop.calls == [] and not rounds.current_round(program(root))['runs']


def test_stray_pytest_fakes_are_waited_out(ready):
    root = ready['root']
    loop = Loop(root)
    fake = [{'pid': 7, 'paths': ['/tmp/pytest-of-u/pytest-3/test_x0/bin/worldserver'], 'fake': True}]
    answers, sleeps = [fake, fake], []

    def inventory():
        return answers.pop(0) if answers else []
    result = loop.run(root, inventory=inventory, sleep=sleeps.append, max_batches=1)
    assert sleeps == [batches.POLL_SECONDS, batches.POLL_SECONDS] and len(loop.calls) == 1
    assert result['batches'][0]['waited']['stray_fakes_seen'] == fake


def test_stray_fakes_that_never_exit_refuse_after_the_bound():
    ticks = iter(range(0, 10_000, 10))
    fake = [{'pid': 7, 'paths': ['/home/u/.cache/x/worldserver'], 'fake': True}]
    with pytest.raises(GraphError, match='stray pytest fake worldserver.*after 30 s.*kill them'):
        batches.wait_for_no_worldserver(lambda: fake, wait_seconds=30, sleep=lambda s: None, clock=lambda: next(ticks))


def test_low_headroom_refuses_before_the_coordinator(ready):
    root = ready['root']
    loop = Loop(root)
    with pytest.raises(GraphError, match='writable bytes .*Archive old /tmp run directories'):
        loop.run(root, headroom=lambda path: {'headroom_bytes': 1024})
    assert loop.calls == []


def test_preflight_refusals(world):
    root = world['root']
    rounds.plan(root)
    with pytest.raises(GraphError, match='not run'):
        batches.run_batches(root, LABEL)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='x')
    fake_build(root)
    with pytest.raises(GraphError, match='program run-plan'):
        batches.run_batches(root, LABEL)
    runs.run_plans(root)
    with pytest.raises(GraphError, match='changed'):
        batches.run_batches(root, LABEL, 'f' * 64)
    with pytest.raises(GraphError, match='--max-batches'):
        batches.run_batches(root, LABEL, max_batches=0)


def test_only_untargeted_bosses_run_each_batch_once(ready):
    root = ready['root']
    for unit in ready['discovery']['units']:
        unit['raid_target']['present'] = False
    loop = Loop(root)
    result = loop.run(root)
    assert result['stopped'] == 'no_target_bosses' and len(loop.calls) == 1 and result['exit_status'] == 0


def test_inventory_classifies_pytest_and_cache_fakes(tmp_path, monkeypatch):
    from tools.raid_program import raid_shard_preflight
    proc, home = tmp_path / 'proc', tmp_path / 'home'
    exes = {11: '/tmp/pytest-of-u/pytest-9/test_crash0/bin/worldserver',
            12: str(home / '.cache/crash_capture/bin/worldserver-abc123'),
            13: '/home/u/trinity/build/src/server/worldserver/worldserver',
            14: '/tmp/play/worldserver (deleted)'}
    for pid, exe in exes.items():
        (proc / str(pid)).mkdir(parents=True)
        os.symlink(exe, proc / str(pid) / 'exe')
        (proc / str(pid) / 'cmdline').write_bytes(exe.encode() + b'\0-c\0x.conf\0')
    monkeypatch.setattr(raid_shard_preflight, 'worldserver_processes', lambda proc_path: {
        'returncode': 0, 'pids': sorted(exes), 'error': None})
    rows = {row['pid']: row['fake'] for row in batches.worldserver_inventory(proc, home=home)}
    assert rows == {11: True, 12: True, 13: False, 14: False}
    monkeypatch.setattr(raid_shard_preflight, 'worldserver_processes', lambda proc_path: {
        'returncode': None, 'pids': [], 'error': 'proc_scan_failed'})
    with pytest.raises(GraphError, match='inventory is incomplete'):
        batches.worldserver_inventory(proc, home=home)


def test_the_cli_verb_is_wired_and_exits_nonzero_on_a_stop(ready, monkeypatch):
    from tools.raid_program import raid_program_ingest
    root = ready['root']
    loop = Loop(root, gain={'alpha': 0, 'beta': 0})
    monkeypatch.setattr(batches, 'run_coordinator', loop.coordinator)
    monkeypatch.setattr(batches, 'worldserver_inventory', lambda: [])
    monkeypatch.setattr(batches, 'check_headroom', lambda reader=None: dict(PLENTY))
    monkeypatch.setattr(batches, 'verdict_count', loop.counter)
    monkeypatch.setattr(raid_program_ingest, 'ingest', loop.ingest)
    result = raid_program.command(root, ['run-batches', '--label', LABEL, '--max-batches', '1', '--expect', sha(root)])
    assert result['run_batches']['stopped'] == 'no_progress' and result['exit_status'] == 1
    assert result['resume']['stage'] == 'run' and len(loop.calls) == 1


def test_a_refusal_after_a_batch_stops_and_keeps_the_report(ready):
    root = ready['root']
    loop = Loop(root)
    answers = [[], [{'pid': 5, 'paths': ['/opt/worldserver'], 'fake': False}]]
    result = loop.run(root, inventory=lambda: answers.pop(0))
    assert result['stopped'] == 'refused' and 'pid 5' in result['error'] and len(loop.calls) == 1
    assert result['exit_status'] == 1 and len(rounds.current_round(program(root))['runs']) == 1


def test_resume_shows_the_counted_kills_once_the_round_has_a_label(ready, monkeypatch):
    from tools.raid_program import raid_program_state as store
    root = ready['root']
    assert batches.kill_summary(root, program(root)) is None, 'nothing before the first ingest'
    store.update(root, lambda state: (rounds.current_round(rounds.active(state)).update(label=LABEL), state)[1])
    monkeypatch.setattr(batches, 'verdict_count', lambda root, scenario, label: (1 if scenario.endswith('alpha') else 3, 3))
    assert batches.kill_summary(root, program(root)).startswith('alpha 1/3')
    assert f'Counted kills under {LABEL} so far: alpha 1/3' in raid_program.resume(root)['next_action']


def test_an_interrupted_batch_stops_the_loop_without_recording_or_ingesting(ready):
    from tools.raid_program.raid_program_batch_process import BatchInterrupted
    root = ready['root']
    loop = Loop(root)

    def interrupted(root, plan_path, output, log, timeout):
        loop.calls.append({'output': str(output)})
        raise BatchInterrupted('signal SIGTERM', {'verified': True, 'group': {}, 'servers': {}})
    result = batches.run_batches(root, LABEL, sha(root), coordinator=interrupted, ingest=loop.ingest,
                                 counter=loop.counter, stamp=loop.stamp, inventory=lambda: [],
                                 headroom=lambda path: dict(PLENTY))
    assert result['stopped'] == 'interrupted' and result['exit_status'] == 1 and 'SIGTERM' in result['error']
    assert result['batches'][0]['cleanup']['verified'] and loop.kills == {'alpha': 0, 'beta': 0}, 'no ingest'
    assert rounds.current_round(program(root))['runs'] == [] and '--shard-run' in result['next_action']


def test_unverified_cleanup_records_a_failed_batch_and_stops(ready):
    from tools.raid_program.raid_program_batch_process import CleanupUnverified
    root = ready['root']
    loop = Loop(root)
    cleanup = {'verified': False,
               'group': {'verified': True, 'pgid': 500, 'members_left': [], 'coordinator_exit': 0, 'errors': []},
               'servers': {'verified': False, 'survivors': [601], 'found': {'601': 'worldserver'}, 'errors': []}}

    def stuck(root, plan_path, output, log, timeout):
        loop.coordinator(root, plan_path, output, log, timeout)  # a complete shard_run.json exists
        raise CleanupUnverified('batch cleanup could not be verified', 0, cleanup)
    result = batches.run_batches(root, LABEL, sha(root), coordinator=stuck, ingest=loop.ingest, counter=loop.counter,
                                 stamp=loop.stamp, inventory=lambda: [], headroom=lambda path: dict(PLENTY))
    assert result['stopped'] == 'cleanup_unverified' and result['exit_status'] == 1
    recorded = rounds.current_round(program(root))['runs']
    assert len(recorded) == 1 and recorded[0]['failed'] and 'survivors [601]' in recorded[0]['reason']
    assert loop.kills == {'alpha': 0, 'beta': 0}, 'an unverified batch is never ingested'
    assert 'never touch a play server' in result['next_action']


main_thread = pytest.mark.skipif(threading.current_thread() is not threading.main_thread(),
                                 reason='signal handlers need the main thread')


@main_thread
def test_a_signal_during_ingest_stops_before_another_batch(ready):
    root = ready['root']
    loop = Loop(root, needed=5)
    ingest = loop.ingest

    def ingest_then_signal(root, label):
        result = ingest(root, label)
        signal.raise_signal(signal.SIGTERM)  # recorded by the loop's guard; ingest itself completes
        return result
    result = batches.run_batches(root, LABEL, sha(root), coordinator=loop.coordinator, ingest=ingest_then_signal,
                                 counter=loop.counter, stamp=loop.stamp, inventory=lambda: [],
                                 headroom=lambda path: dict(PLENTY))
    assert result['stopped'] == 'interrupted' and len(loop.calls) == 1, 'no batch after the signal'
    assert 'recorded and ingested' in result['error'] and result['exit_status'] == 1


@main_thread
def test_a_signal_while_waiting_out_fakes_launches_nothing(ready):
    root = ready['root']
    loop = Loop(root)
    fake = [{'pid': 7, 'paths': ['/tmp/pytest-of-u/pytest-3/test_x0/bin/worldserver'], 'fake': True}]

    def inventory():
        signal.raise_signal(signal.SIGINT)
        return fake
    result = batches.run_batches(root, LABEL, sha(root), coordinator=loop.coordinator, ingest=loop.ingest,
                                 counter=loop.counter, stamp=loop.stamp, inventory=inventory,
                                 headroom=lambda path: dict(PLENTY), sleep=lambda seconds: None)
    assert result['stopped'] == 'interrupted' and loop.calls == [] and 'waiting for worldservers' in result['error']


@main_thread
def test_an_interrupted_batch_with_survivors_is_recorded_as_cleanup_unverified(ready, tmp_path):
    """End to end: the real run_coordinator (fake /proc, fake Popen) inside the real loop guard."""
    from tests.test_raid_program_batch_process import CHILD, SERVER, World, interrupt_once, launcher
    root = ready['root']
    loop = Loop(root)

    def coordinator(root_path, plan_path, output, log, timeout):
        world = World(tmp_path, output)
        world.batch(play_server=False)
        world.on_killpg[signal.SIGINT] = lambda: (world.process.exit(130), world.remove(CHILD))
        world.unkillable.add(SERVER)
        loop.calls.append({'output': str(output)})
        return batches.run_coordinator(root_path, plan_path, output, log, timeout,
                                       popen=launcher(world, interrupt_once('SIGTERM')), **world.options())
    result = batches.run_batches(root, LABEL, sha(root), coordinator=coordinator, ingest=loop.ingest,
                                 counter=loop.counter, stamp=loop.stamp, inventory=lambda: [],
                                 headroom=lambda path: dict(PLENTY))
    assert result['stopped'] == 'cleanup_unverified' and len(loop.calls) == 1 and loop.kills['alpha'] == 0
    recorded = rounds.current_round(program(root))['runs'][-1]
    assert recorded['failed'] and 'interrupted by SIGTERM' in recorded['reason'] and f'survivors [{SERVER}]' in recorded['reason']
    assert 'were stopped' not in result['next_action'] and 'could not be shown gone' in result['next_action']
    assert result['batches'][0]['cleanup']['group']['verified'], 'the coordinator group was empty; only the server survived'


@main_thread
def test_signal_during_final_plan_selection_is_not_success(ready, monkeypatch):
    root = ready['root']
    loop = Loop(root)
    loop.kills = {'alpha': 3, 'beta': 3}
    runs.record_run(root, None, sha(root), failed_batch=1, reason='earlier batch')  # every plan has a run
    real = batches._next_plan

    def selecting(*args):
        signal.raise_signal(signal.SIGTERM)
        return real(*args)
    monkeypatch.setattr(batches, '_next_plan', selecting)
    result = loop.run(root)
    assert result['stopped'] == 'interrupted' and result['exit_status'] == 1 and loop.calls == []
    assert 'targets_met' in result['error']


@main_thread
def test_signal_during_max_batches_epilogue_is_not_success(ready, monkeypatch):
    root = ready['root']
    loop = Loop(root, needed=1)
    real, seen = batches._next_plan, []

    def selecting(*args):
        seen.append(1)
        if len(seen) == 2:  # the epilogue's selection after the single allowed batch
            signal.raise_signal(signal.SIGTERM)
        return real(*args)
    monkeypatch.setattr(batches, '_next_plan', selecting)
    result = loop.run(root, max_batches=1)
    assert len(loop.calls) == 1 and result['stopped'] == 'interrupted' and result['exit_status'] == 1

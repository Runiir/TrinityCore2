"""program assess and run_sanity: blocking findings keep a unit open; a missing module fails loudly."""
from __future__ import annotations

import sys

import pytest

from tools.raid_program import raid_program, raid_program_rounds as rounds, raid_program_sanity as sanity
from tools.raid_program.development_graph import GraphError

from tests.test_raid_program_rounds import (  # noqa: F401 - the world fixture is used by name
    PASS, RAID, both, complete_round, fake_build, fake_ingest, program, sha, shard_run, world)

REAL_LOAD = sanity.load_sanity  # the world fixture fakes load_sanity; the absent-module test restores it
ALPHA = f'{RAID}_10n_alpha'
DURATION = {'check': 'duration_outlier', 'severity': 'blocking', 'kill_id': 'lbl-r1-r1-alpha',
            'detail': 'boss window 1080 s is 3.0x the longest matched WCL fight (360 s)',
            'evidence': {'boss_window_ms': 1080000, 'reference_max_ms': 360000}}
UNMEASURED = {'check': 'unmeasured_kills', 'severity': 'warn', 'kill_id': None, 'detail': '1 kill unmeasured',
              'evidence': {}}


def test_a_blocking_finding_keeps_a_passing_unit_open_and_routes_investigation(world):
    root = world['root']
    world['sanity'] = {ALPHA: [DURATION, UNMEASURED]}
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    alpha = program(root)['units']['alpha']['results'][-1]
    beta = program(root)['units']['beta']['results'][-1]
    assert alpha['verdict']['status'] == 'pass' and alpha['status'] == 'open'
    assert alpha['not_accepted_because'] == ['sanity:duration_outlier']
    assert [row['check'] for row in alpha['sanity']] == ['duration_outlier', 'unmeasured_kills']
    assert beta['status'] == 'accepted' and beta['sanity'] == []
    view = raid_program.resume(root)
    assert view['stage'] == 'plan' and 'Investigate before tuning' in view['next_action']
    assert 'alpha: duration_outlier [lbl-r1-r1-alpha]: boss window 1080 s' in view['next_action']
    assert 'Sanity warnings' in view['next_action'] and 'alpha: unmeasured_kills' in view['next_action']
    assert view['last_sanity']['investigate_before_tuning'][0].startswith('alpha: duration_outlier')
    rounds.plan(root)
    packet = rounds.current_round(program(root))['packets']['boss:alpha']
    assert packet['owner_skill'] == 'raid-performance-loop' and packet['task'].startswith('Investigate before tuning')


def test_warnings_alone_never_block(world):
    root = world['root']
    world['sanity'] = {ALPHA: [UNMEASURED]}
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    assert program(root)['units']['alpha']['status'] == 'accepted'


def test_a_raising_or_malformed_check_blocks_instead_of_passing(world, monkeypatch):
    root = world['root']

    def broken(root, scenario, label):
        if scenario == ALPHA:
            raise KeyError('enrage_after_ms')
        return [{'check': 'idle_actor', 'severity': 'fatal'}]
    monkeypatch.setattr(sanity, 'load_sanity', lambda: broken)
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    units = program(root)['units']
    assert units['alpha']['results'][-1]['not_accepted_because'] == ['sanity:sanity_check_failed']
    assert units['beta']['results'][-1]['not_accepted_because'] == ['sanity:sanity_finding_malformed']


def test_large_evidence_is_truncated_in_the_state():
    row = sanity.unit_findings(lambda root, scenario, label: [
        DURATION | {'evidence': {'series': list(range(5000))}}], None, 'x', 'l')[0]
    assert row['evidence'] == {'truncated': True, 'bytes': row['evidence']['bytes']} and row['check'] == 'duration_outlier'


def test_assess_fails_loudly_without_the_run_sanity_module(world, monkeypatch):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='x')
    fake_build(root)
    from tools.raid_program import raid_program_runs as runs
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1', both()))
    fake_ingest(root, world, 'lbl')
    monkeypatch.setattr(sanity, 'load_sanity', REAL_LOAD)
    monkeypatch.setitem(sys.modules, 'tools.raid_program.run_sanity', None)  # the module is absent
    before = sha(root)
    with pytest.raises(GraphError, match='program assess needs tools.raid_program.run_sanity.sanity_findings'):
        raid_program.command(root, ['assess', '--label', 'lbl', '--expect', before])
    assert sha(root) == before and program(root)['stage'] == 'run', 'nothing is assessed without the sanity check'

"""Round state machine of the raid program on a synthetic two-boss discovery."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import raid_program, raid_program_rounds as rounds, raid_program_state as store
from tools.raid_program.development_graph import GraphError
from tools.raid_program.queued_build import DEFAULT_POLICY_RELATIVE

REAL = Path(__file__).resolve().parents[1]
RAID, MODE = 'blackwing_descent', '10N'


def _unit(key: str, index: int, closure: list[str]) -> dict:
    cohort = f'{RAID}_10n_{key}_c0'
    return {
        'unit_id': f'raid:{RAID}:{MODE}:{key}', 'boss_key': key, 'boss_index': index, 'name': key,
        'strategy_slug': key, 'boss_scenario': f'{RAID}:{key}:{MODE}', 'boss_graph': None, 'cohort_id': cohort,
        'scenario_id': cohort + '_diagnostic', 'runtime_profile_id': cohort + '_diagnostic', 'pool_tag': cohort + '_diagnostic',
        'lockout': {'precompleted_boss_keys': closure, 'seed_boss_argument': ','.join(closure) or 'none',
                    'fresh_instance': not closure, 'diagnostic_only_assistance': bool(closure),
                    'certifies_predecessors': False, 'seedable': True, 'refusal': None},
        'boss_nodes': [f'bwd.{key}.encounter'], 'composition_boss': key, 'spec_selection_status': 'provisional',
        'research': {'contract': None, 'fidelity_state': 'accepted'},
        'native_script': {'path': f'src/boss_{key}.cpp', 'present': True, 'catalog_status': 'ok'},
        'damage_fidelity': {'closable': True, 'reason': None},
        'raid_target': {'scenario': f'{RAID}_10n_{key}', 'path': f'experiments/configs/raid_targets/{RAID}_10n_{key}.json',
                        'present': True, 'ambiguous': False},
        'files': {'owned': [f'src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/{key.title()}/**',
                            f'tests/test_{key}_*.py'],
                  'focused_tests': f'pixi run python -m pytest -q tests/test_{key}_*.py'},
        'missing_inputs': [], 'ready_to_run': True, 'acceptance_blocked': False, 'input_owner_skill': None,
        'raid_run_blockers': []}


def discovery() -> dict:
    e2e = {'unit_id': f'raid:{RAID}:{MODE}:e2e', 'route_composition': 'experiments/configs/raid_route_compositions/x.json',
           'scenario_id': f'{RAID}_10n', 'cohort_id': f'{RAID}_10n_full_c0', 'runtime_profile_id': f'{RAID}_10n_full',
           'pool_tag': f'{RAID}_10n_full', 'boss_nodes': {'alpha': ['bwd.alpha.encounter'], 'beta': ['bwd.beta.encounter']},
           'missing_inputs': [], 'ready_to_run': True, 'owner_skill': None, 'raid_run_blockers': []}
    return {'program_id': f'{RAID}:{MODE}', 'raid': RAID, 'mode': MODE, 'mode_token': '10n', 'size': 10,
            'name': 'Test Raid', 'map_id': 669, 'prerequisites': 'p.json', 'composition': 'c.json', 'raid_inputs': [],
            'units': [_unit('alpha', 0, []), _unit('beta', 1, ['alpha'])], 'excluded_bosses': [], 'e2e': e2e,
            'sources': {}}


@pytest.fixture
def world(tmp_path, monkeypatch):
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    policy = tmp_path / DEFAULT_POLICY_RELATIVE
    policy.parent.mkdir(parents=True)
    shutil.copy2(REAL / DEFAULT_POLICY_RELATIVE, policy)
    holder = {'discovery': discovery(), 'verdicts': {}}
    fake = lambda root, raid, mode: copy.deepcopy(holder['discovery'])
    monkeypatch.setattr(rounds, 'discover_program', fake)
    monkeypatch.setattr(raid_program, 'discover_program', fake)
    monkeypatch.setattr(rounds, '_verdict', lambda root, unit, label, build: holder['verdicts'].get(unit['boss_key'])
                        if label else None)
    rounds.select(tmp_path, holder['discovery'])
    holder['root'] = tmp_path
    return holder


def sha(root: Path) -> str:
    return store.state_sha256(store.load(root)[1])


def program(root: Path) -> dict:
    return rounds.active(store.load(root)[0])


def handoff(root: Path, packet_id: str, files: list[str], **extra) -> Path:
    path = root / 'handoffs' / (packet_id.replace(':', '_') + '.json')
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps({'packet_id': packet_id, 'round': program(root)['round'], 'changed_files': files,
                                'new_files': [], 'tests': [{'command': 'pytest', 'result': 'passed'}],
                                'patch_requests': [], 'validation_neutrality': 'n/a', 'risks': [], 'open_items': [],
                                'resolved_inputs': [], **extra}))
    return path


def fake_build(root: Path) -> dict:
    binary = root / rounds.WORLDSERVER
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b'worldserver')
    runner = lambda root, policy, kind, command: (0, {'classification': 'success', 'ticket_id': kind}, f'/q/{kind}.json', True)
    return rounds.build(root, runner=runner, worktree_state=lambda root: {'clean': True, 'commit': 'c' * 40})


def shard_run(root: Path, name: str, rows: list[dict], terminal: str = 'completed') -> Path:
    directory = root / 'runs' / name
    shards = []
    for row in rows:
        run_dir = directory / 'shards' / row['cohort_id']
        run_dir.mkdir(parents=True, exist_ok=True)
        if row.get('killed') is not None:
            (run_dir / 'report.json').write_text(json.dumps({'native_gameplay_outcome': {
                'real_boss_kill_evidence': [{'route_node_id': node} for node in row['killed']]}}))
        shards.append({'cohort_id': row['cohort_id'], 'run_dir': str(run_dir), 'native_clear': row.get('clear', True),
                       'completion_reason': row.get('reason', 'validation_route_manifest_complete'),
                       'lockout': row.get('lockout'), 'error': '', 'start_refusal': None})
    path = directory / 'shard_run.json'
    path.write_text(json.dumps({'schema': 'raid_shard_run_v1', 'run_id': name, 'terminal_reason': terminal,
                                'shards': shards}))
    return path


def complete_round(root: Path, verdicts: dict, holder: dict, rows: list[dict], label: str = 'lbl') -> None:
    for packet_id, packet in rounds.current_round(program(root))['packets'].items():
        rounds.record_handoff(root, packet_id, handoff(root, packet_id, []))
    assert program(root)['stage'] == 'build'
    assert fake_build(root)['success']
    plans = rounds.run_plans(root)['plans']
    assert len(plans) == 1
    rounds.record_run(root, shard_run(root, f"r{program(root)['round']}", rows))
    holder['verdicts'] = verdicts
    rounds.assess(root, label)


def test_full_program_cycle_reaches_complete(world):
    root = world['root']
    assert program(root)['stage'] == 'plan'
    rounds.plan(root, expected_sha256=sha(root))
    current = rounds.current_round(program(root))
    assert sorted(current['packets']) == ['boss:alpha', 'boss:beta'] and program(root)['stage'] == 'implement'
    packet = raid_program.packet(root, 'boss:alpha')
    assert packet['schema'] == 'raid_program_worker_packet_v1'
    assert packet['owned_files'][0].endswith('/Encounters/Alpha/**')
    assert 'src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Beta/**' in packet['forbidden_files']
    assert set(packet['handoff']['required_fields']) >= {'changed_files', 'new_files', 'tests', 'patch_requests',
                                                         'validation_neutrality', 'risks', 'open_items'}
    assert packet['focused_tests'] == ['pixi run python -m pytest -q tests/test_alpha_*.py']
    view = raid_program.resume(root)
    assert view['stage'] == 'implement' and view['packets']['boss:beta']['handoff'] == 'pending'
    assert any('program handoff' in command for command in view['commands'])

    rows = [{'cohort_id': f'{RAID}_10n_alpha_c0'},
            {'cohort_id': f'{RAID}_10n_beta_c0', 'clear': False, 'reason': 'semantic_progress_plateau_watchdog',
             'lockout': {'state': 'verified'}}]
    complete_round(root, {'alpha': {'status': 'pass', 'reasons': []}}, world, rows)
    state = program(root)
    assert state['stage'] == 'plan' and state['round'] == 2
    assert state['units']['alpha']['status'] == 'accepted' and state['units']['beta']['status'] == 'open'
    assert state['units']['beta']['results'][-1]['outcome'] == 'semantic_progress_plateau_watchdog'
    plan_document = json.loads((root / state['rounds'][0]['run_plans'][0]['path']).read_text())
    lockouts = {row['boss_key']: row['lockout'] for row in plan_document['shards']}
    assert lockouts['alpha'] is None
    assert lockouts['beta'] == {'raid': RAID, 'difficulty': '10n', 'precompleted_boss_keys': ['alpha'],
                                'seed_boss_argument': 'alpha'}

    rounds.plan(root)
    current = rounds.current_round(program(root))
    assert list(current['packets']) == ['boss:beta']
    assert current['packets']['boss:beta']['owner_skill'] == 'raid-performance-loop'
    both = [{'cohort_id': f'{RAID}_10n_alpha_c0'}, {'cohort_id': f'{RAID}_10n_beta_c0', 'lockout': {'state': 'verified'}}]
    complete_round(root, {'alpha': {'status': 'pass'}, 'beta': {'status': 'pass'}}, world, both)
    assert program(root)['stage'] == 'e2e'
    assert 'raid_route_composer' in raid_program.resume(root)['commands'][0]

    plan = rounds.run_plans(root)['plans'][0]
    assert plan['kind'] == 'e2e' and plan['cohorts'] == [f'{RAID}_10n_full_c0']
    e2e = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter', 'bwd.beta.encounter']}])
    rounds.record_e2e(root, e2e)
    final = raid_program.resume(root)
    assert final['stage'] == 'complete' and final['parent_objective_complete'] and final['commands'] == []


def test_failed_e2e_opens_a_round_with_a_shards_packet(world):
    root = world['root']
    rounds.plan(root)
    rows = [{'cohort_id': f'{RAID}_10n_alpha_c0'}, {'cohort_id': f'{RAID}_10n_beta_c0', 'lockout': {'state': 'verified'}}]
    complete_round(root, {'alpha': {'status': 'pass'}, 'beta': {'status': 'pass'}}, world, rows)
    rounds.run_plans(root)
    seeded = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'lockout': {'state': 'verified'},
                                      'killed': ['bwd.alpha.encounter']}])
    rounds.record_e2e(root, seeded)
    state = program(root)
    assert state['stage'] == 'plan' and state['e2e']['status'] == 'open'
    assert {'seeded_lockout_forbidden', 'boss_kills_missing:bwd.beta.encounter'} <= set(state['e2e']['results'][-1]['problems'])
    rounds.plan(root)
    packets = rounds.current_round(program(root))['packets']
    assert list(packets) == ['shards']
    assert any(item['input'] == 'e2e_run' for item in packets['shards']['inputs'])


def test_accepted_boss_reopens_on_regression(world):
    root = world['root']
    rounds.plan(root)
    rows = [{'cohort_id': f'{RAID}_10n_alpha_c0'},
            {'cohort_id': f'{RAID}_10n_beta_c0', 'clear': False, 'reason': 'no_progress_watchdog'}]
    complete_round(root, {'alpha': {'status': 'pass'}}, world, rows)
    rounds.plan(root)
    regressed = [{'cohort_id': f'{RAID}_10n_alpha_c0', 'clear': False, 'reason': 'no_progress_watchdog'},
                 {'cohort_id': f'{RAID}_10n_beta_c0', 'clear': False, 'reason': 'no_progress_watchdog'}]
    complete_round(root, {}, world, regressed)
    alpha = program(root)['units']['alpha']
    assert alpha['status'] == 'open' and alpha['results'][-1]['reopened']


def test_stage_guards_and_stale_writers(world):
    root = world['root']
    stale = sha(root)
    with pytest.raises(GraphError, match='not build'):
        fake_build(root)
    rounds.plan(root)
    with pytest.raises(GraphError, match='stage is implement'):
        rounds.plan(root)
    with pytest.raises(GraphError, match='changed'):
        rounds.record_handoff(root, 'boss:alpha', None, abandon_reason='x', expected_sha256=stale)
    with pytest.raises(GraphError, match='outside its packet'):
        rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', ['src/server/game/Bots/BotAI.cpp']))
    with pytest.raises(GraphError, match='another packet or round'):
        rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', [], round=7))
    rounds.record_handoff(root, 'boss:alpha', None, abandon_reason='agent did not return')
    rounds.record_handoff(root, 'boss:beta', handoff(root, 'boss:beta', ['tests/test_beta_strategy.py']))
    assert program(root)['stage'] == 'build'
    dirty = lambda root: {'clean': False, 'commit': 'c' * 40}
    with pytest.raises(GraphError, match='clean tree'):
        rounds.build(root, runner=lambda *a: (0, {}, '', True), worktree_state=dirty)
    failed = rounds.build(root, runner=lambda root, policy, kind, command: (2, {'classification': 'failure'}, 'r', False),
                          worktree_state=lambda root: {'clean': True, 'commit': 'c' * 40})
    assert not failed['success'] and program(root)['stage'] == 'build'
    assert fake_build(root)['success'] and program(root)['stage'] == 'run'
    rounds.run_plans(root)
    with pytest.raises(GraphError, match='every planned batch'):
        rounds.assess(root, 'lbl')
    with pytest.raises(GraphError, match='match no run plan'):
        rounds.record_run(root, shard_run(root, 'x', [{'cohort_id': f'{RAID}_10n_alpha_c0'}]))
    other = copy.deepcopy(world['discovery']) | {'program_id': 'firelands:10N', 'raid': 'firelands'}
    with pytest.raises(GraphError, match='mid-round'):
        rounds.select(root, other)


def test_build_uses_the_default_policy_job_count(world):
    root = world['root']
    policy = json.loads((REAL / DEFAULT_POLICY_RELATIVE).read_text())
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    dry = rounds.build(root, dry_run=True)
    jobs = policy['parallelism']['maximum_compiler_jobs']
    assert dry['policy']['path'] == DEFAULT_POLICY_RELATIVE.as_posix() and dry['policy']['maximum_compiler_jobs'] == jobs
    assert dry['commands']['worldserver_build'][-2:] == ['--parallel', str(jobs)]
    assert f"{jobs} compiler jobs from the policy" in raid_program.resume(root)['next_action']


def test_no_ready_shard_still_closes_the_round(world):
    root = world['root']
    for unit in world['discovery']['units']:
        unit['ready_to_run'] = False
        unit['missing_inputs'] = [{'input': 'runtime_scenario', 'detail': 'x', 'owner_skill': 'raid-shard-architecture',
                                   'blocks': 'run'}]
    rounds.plan(root)
    assert 'shards' in rounds.current_round(program(root))['packets']
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    fake_build(root)
    assert rounds.run_plans(root)['plans'] == []
    assert 'program assess' in raid_program.resume(root)['commands'][0]
    rounds.assess(root)
    state = program(root)
    assert state['round'] == 2 and state['units']['alpha']['results'][-1]['outcome'] == 'not_run'


def test_verdict_must_come_from_the_round_build(monkeypatch, tmp_path):
    from tools.raid_program import scoreboard_verdict
    monkeypatch.setattr(scoreboard_verdict, 'evaluate_target', lambda root, scenario, label: {
        'status': 'pass', 'reasons': [], 'kills': 3, 'target_sha256': 't', 'worldserver_sha256': 'other'})
    unit = _unit('alpha', 0, [])
    assert rounds._verdict(tmp_path, unit, 'lbl', {'worldserver_sha256': 'mine'})['status'] == 'build_mismatch'
    assert rounds._verdict(tmp_path, unit, 'lbl', {'worldserver_sha256': 'other'})['status'] == 'pass'
    assert rounds._verdict(tmp_path, unit, None, None) is None


def test_packets_route_shard_files_and_refuse_shared_ownership(world):
    root = world['root']
    world['discovery']['units'][0]['missing_inputs'] = [
        {'input': 'runtime_profile', 'detail': 'x', 'owner_skill': 'raid-shard-architecture', 'blocks': 'run'}]
    rounds.plan(root)
    boss = raid_program.packet(root, 'boss:alpha')
    shards = raid_program.packet(root, 'shards')
    assert 'experiments/configs/validation_scenarios_cata_001.json' in boss['patch_request_routes']['shards']
    assert 'experiments/configs/validation_scenarios_cata_001.json' in shards['owned_files']
    assert 'shards' not in shards['patch_request_routes']
    assert shards['inputs'][0]['unit'] == 'alpha' and boss['inputs'] == []
    assert not set(boss['owned_files']) & set(shards['owned_files'])


def test_plan_refuses_overlapping_packet_ownership(world):
    root = world['root']
    shared = 'experiments/configs/raid_targets/shared.json'
    for unit in world['discovery']['units']:
        unit['files']['owned'].append(shared)
    with pytest.raises(GraphError, match='share owned files'):
        rounds.plan(root)
    assert program(root)['stage'] == 'plan' and program(root)['rounds'] == []


def test_external_work_is_adopted_without_a_handoff_file(world):
    root = world['root']
    rounds.plan(root)
    rounds.record_handoff(root, 'boss:alpha', None, external_reason='done in round 2 commits abc123')
    with pytest.raises(GraphError, match='not both'):
        rounds.record_handoff(root, 'boss:beta', None, abandon_reason='x', external_reason='y')
    rounds.record_handoff(root, 'boss:beta', None, abandon_reason='no agent')
    assert program(root)['stage'] == 'build'
    packets = raid_program.resume(root)['packets']
    assert packets['boss:alpha']['handoff'] == 'external' and packets['boss:beta']['handoff'] == 'abandoned'

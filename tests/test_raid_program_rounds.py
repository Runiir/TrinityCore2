"""Round state machine of the raid program on a synthetic two-boss discovery."""
from __future__ import annotations

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.raid_program import raid_program, raid_program_build as builds, raid_program_ingest as ingests
from tools.raid_program import raid_program_rounds as rounds, raid_program_runs as runs, raid_program_state as store
from tools.raid_program.development_graph import GraphError
from tools.raid_program.queued_build import DEFAULT_POLICY_RELATIVE

REAL = Path(__file__).resolve().parents[1]
RAID, MODE = 'blackwing_descent', '10N'
BINARY = 'b' * 64
AUDIT = {'input': 'script_readiness_audit', 'detail': 'stale', 'owner_skill': 'raid-encounter-research',
         'blocks': 'acceptance'}


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
                            f'sql/w/*{key}*', f'tests/test_{key}_*.py'],
                  'focused_tests': f'pixi run python -m pytest -q tests/test_{key}_*.py'},
        'missing_inputs': [], 'ready_to_run': True, 'acceptance_blocked': False, 'input_owner_skill': None,
        'raid_run_blockers': []}


def discovery() -> dict:
    cohort = f'{RAID}_10n_full_c0'
    e2e = {'unit_id': f'raid:{RAID}:{MODE}:e2e', 'route_composition': 'experiments/configs/raid_route_compositions/x.json',
           'route_template_scenario_id': f'{RAID}_10n', 'scenario_id': cohort, 'cohort_id': cohort,
           'runtime_profile_id': cohort, 'pool_tag': cohort,
           'boss_key': 'full', 'boss_nodes': {'alpha': ['bwd.alpha.encounter'], 'beta': ['bwd.beta.encounter']},
           'expected_boss_nodes': ['bwd.alpha.encounter', 'bwd.beta.encounter'],
           'missing_inputs': [], 'ready_to_run': True, 'owner_skill': None, 'raid_run_blockers': []}
    return {'program_id': f'{RAID}:{MODE}', 'raid': RAID, 'mode': MODE, 'mode_token': '10n', 'size': 10,
            'name': 'Test Raid', 'map_id': 669, 'prerequisites': 'p.json', 'composition': 'c.json', 'raid_inputs': [],
            'units': [_unit('alpha', 0, []), _unit('beta', 1, ['alpha'])], 'excluded_bosses': [], 'e2e': e2e,
            'sources': {}, 'shard_tests': ['tests/test_raid_shard_plan.py'],
            'generated_plan': 'dataset/raid_shard_provisioning/test_raid_v1/plan.json'}


def git(root: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(root), '-c', 'user.name=t', '-c', 'user.email=t@t', *args],
                          check=True, capture_output=True, text=True).stdout.strip()


def commit_all(root: Path, message: str = 'step') -> str:
    git(root, 'add', '-A')
    git(root, 'commit', '-q', '--allow-empty', '-m', message)
    return git(root, 'rev-parse', 'HEAD')


def write_target(root: Path, boss: str) -> None:
    """A minimal raid_target_v1 the real scoreboard recorder accepts."""
    folder = root / 'experiments/configs/raid_targets'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'wcl_test_manifest.json').write_text(json.dumps({'references': []}))
    scenario = f'{RAID}_10n_{boss}'
    (folder / f'{scenario}.json').write_text(json.dumps({
        'schema': 'raid_target_v1', 'scenario': scenario, 'encounter_route_node_id': f'bwd.{boss}.encounter',
        'wcl_reference_manifest': 'experiments/configs/raid_targets/wcl_test_manifest.json',
        'matched_reference_ids': [], 'kills_per_measurement': 3}))


@pytest.fixture
def world(tmp_path, monkeypatch):
    from tools.raid_program import scoreboard_run
    subprocess.run(['git', 'init', '-q', str(tmp_path)], check=True)
    policy = tmp_path / DEFAULT_POLICY_RELATIVE
    policy.parent.mkdir(parents=True)
    shutil.copy2(REAL / DEFAULT_POLICY_RELATIVE, policy)
    for boss in ('alpha', 'beta'):
        write_target(tmp_path, boss)
    holder = {'discovery': discovery(), 'verdicts': {}, 'recorded': [], 'archived': [], 'archive_errors': []}

    def archive(root, scenario, kill_id, sources, pointers):  # keeps the sources; the deleting one is in test_raid_program_build
        holder['archived'].append((scenario, kill_id, [str(path) for path in sources]))
        if holder['archive_errors']:
            return None, holder['archive_errors'].pop()
        return f'artifacts/cata_raid_program/scoreboard_{scenario}_{kill_id}.tar.gz.dvc', None
    monkeypatch.setattr(scoreboard_run, 'archive_evidence', archive)
    monkeypatch.setattr(rounds, 'discover_program', lambda root, raid, mode: copy.deepcopy(holder['discovery']))
    monkeypatch.setattr(rounds, 'verdict_for', lambda root, unit, label, build: copy.deepcopy(
        holder['verdicts'].get(unit['boss_key'])) if label else None)
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


def runner(binary: str | None = BINARY, fail: str | None = None):
    def run(root, policy, kind, command):
        if kind == fail:
            return 2, {'classification': 'failure', 'ticket_id': kind}, f'/q/{kind}.json', False
        artifacts = [{'kind': 'worldserver_elf', 'produced_by_ticket': True, 'sha256': binary}] if binary else []
        return 0, {'classification': 'success', 'ticket_id': kind,
                   'output_artifacts': artifacts if kind == 'worldserver_build' else []}, f'/q/{kind}.json', True
    return run


def fake_build(root: Path, **options) -> dict:
    return builds.build(root, runner=options.pop('run', runner()),
                        worktree_state=lambda root: {'clean': True, 'commit': 'c' * 40}, **options)


def shard_run(root: Path, name: str, rows: list[dict], terminal: str = 'completed', binary: str = BINARY) -> Path:
    directory = root / 'runs' / name
    shards = []
    for row in rows:
        run_dir = directory / 'shards' / row['cohort_id']
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / 'report.json').write_text(json.dumps({
            'native_gameplay_outcome': {'native_clear': row.get('clear', True),
                                        'real_boss_kill_evidence': [{'route_node_id': node} for node in row.get('killed') or []]},
            'completion_reason': row.get('reason', 'validation_route_manifest_complete'), 'status': {'deaths': 0},
            'measurement_validity': {'valid_for_dps': True}}))
        shards.append({'cohort_id': row['cohort_id'], 'run_dir': str(run_dir), 'native_clear': row.get('clear', True),
                       'completion_reason': row.get('reason', 'validation_route_manifest_complete'),
                       'lockout': row.get('lockout'), 'error': '', 'start_refusal': None})
    (directory / 'console_journal.jsonl').write_text('{}\n')
    path = directory / 'shard_run.json'
    path.write_text(json.dumps({'schema': 'raid_shard_run_v1', 'run_id': name, 'terminal_reason': terminal,
                                'worldserver': {'path': '/w', 'sha256': binary}, 'shards': shards}))
    return path


def fake_ingest(root: Path, holder: dict, label: str) -> dict:
    return ingests.ingest(root, label)  # real recorder; the fixture's archiver keeps the sources


def both(**alpha) -> list[dict]:
    return [{'cohort_id': f'{RAID}_10n_alpha_c0', **alpha},
            {'cohort_id': f'{RAID}_10n_beta_c0', 'lockout': {'state': 'verified'}}]


def complete_round(root: Path, verdicts: dict, holder: dict, rows: list[dict], label: str | None = None) -> None:
    for packet_id in rounds.current_round(program(root))['packets']:
        rounds.record_handoff(root, packet_id, None, external_reason='test')
    assert program(root)['stage'] == 'build'
    assert fake_build(root)['success']
    plans = runs.run_plans(root)['plans']
    if plans:
        runs.record_run(root, shard_run(root, f"r{program(root)['round']}", rows))
    label = label or f"lbl-r{program(root)['round']}"
    if plans:
        fake_ingest(root, holder, label)
    holder['verdicts'] = verdicts
    rounds.assess(root, label if plans else None)


PASS = {'status': 'pass', 'reasons': []}


def test_full_program_cycle_reaches_complete(world):
    root = world['root']
    rounds.plan(root, expected_sha256=sha(root))
    current = rounds.current_round(program(root))
    assert sorted(current['packets']) == ['boss:alpha', 'boss:beta'] and program(root)['stage'] == 'implement'
    packet = raid_program.packet(root, 'boss:alpha')
    assert packet['schema'] == 'raid_program_worker_packet_v1'
    assert packet['owned_files'][0].endswith('/Encounters/Alpha/**')
    assert 'src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Beta/**' in packet['forbidden_files']
    assert set(packet['handoff']['required_fields']) >= {'changed_files', 'new_files', 'tests', 'patch_requests',
                                                         'validation_neutrality', 'risks', 'open_items'}
    view = raid_program.resume(root)
    assert view['stage'] == 'implement' and view['packets']['boss:beta']['handoff'] == 'pending'

    rows = [{'cohort_id': f'{RAID}_10n_alpha_c0'},
            {'cohort_id': f'{RAID}_10n_beta_c0', 'clear': False, 'reason': 'semantic_progress_plateau_watchdog',
             'lockout': {'state': 'verified'}}]
    complete_round(root, {'alpha': PASS}, world, rows)
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
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    assert program(root)['stage'] == 'e2e'
    assert 'raid_route_composer' in raid_program.resume(root)['commands'][0]

    plan = runs.run_plans(root)['plans'][0]
    document = json.loads((root / plan['path']).read_text())['shards'][0]
    assert document['scenario_id'] == document['runtime_profile_id'] == document['pool_tag'] == f'{RAID}_10n_full_c0'
    assert plan['kind'] == 'e2e' and document['lockout'] is None
    e2e = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter', 'bwd.beta.encounter']}])
    runs.record_e2e(root, e2e)
    final = raid_program.resume(root)
    assert final['stage'] == 'complete' and final['parent_objective_complete'] and final['commands'] == []


def test_failed_e2e_opens_a_round_with_a_shards_packet(world):
    root = world['root']
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    runs.run_plans(root)
    seeded = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'lockout': {'state': 'verified'},
                                      'killed': ['bwd.alpha.encounter']}])
    runs.record_e2e(root, seeded)
    state = program(root)
    assert state['stage'] == 'plan' and state['e2e']['status'] == 'open'
    assert {'seeded_lockout_forbidden', 'boss_kills_missing:bwd.beta.encounter'} <= set(state['e2e']['results'][-1]['problems'])
    rounds.plan(root)
    packets = rounds.current_round(program(root))['packets']
    assert list(packets) == ['shards']
    assert any(item['input'] == 'e2e_run' for item in packets['shards']['inputs'])
    assert packets['shards']['focused_tests'] == ['pixi run python -m pytest -q tests/test_raid_shard_plan.py']


def test_e2e_stage_has_an_exit_without_a_shard_run(world):
    root = world['root']
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    world['discovery']['e2e'] |= {'ready_to_run': False, 'missing_inputs': [
        {'input': 'e2e_runtime_profile', 'detail': 'x', 'owner_skill': 'raid-shard-architecture', 'blocks': 'run'}]}
    with pytest.raises(GraphError, match='e2e --failed'):
        runs.run_plans(root)
    view = raid_program.resume(root)
    assert view['commands'][0].startswith('pixi run python -m tools.raid_program.raid_workloop program e2e --failed')
    runs.record_e2e(root, None, failed_reason='e2e_runtime_profile missing')
    state = program(root)
    assert state['stage'] == 'plan' and state['e2e']['results'][-1]['problems'] == ['no_run:e2e_runtime_profile missing']


def test_e2e_run_must_use_the_round_binary(world):
    root = world['root']
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    runs.run_plans(root)
    other = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': []}], binary='f' * 64)
    with pytest.raises(GraphError, match="not this round's build"):
        runs.record_e2e(root, other)


def test_raid_level_inputs_gate_e2e_and_open_a_research_packet(world):
    root = world['root']
    world['discovery']['raid_inputs'] = [AUDIT]
    rounds.plan(root)
    assert 'research' not in rounds.current_round(program(root))['packets'], 'the audit waits for accepted bosses'
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    state = program(root)
    assert state['stage'] == 'plan' and state['round'] == 2, 'raid-level inputs keep the program out of e2e'
    rounds.plan(root)
    packets = rounds.current_round(program(root))['packets']
    assert list(packets) == ['research'] and packets['research']['inputs'][0]['input'] == 'script_readiness_audit'
    research = raid_program.packet(root, 'research')
    assert 'experiments/configs/cata_raid_script_readiness_v1.json' in research['owned_files']
    world['discovery']['raid_inputs'] = []
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    assert program(root)['stage'] == 'e2e'
    runs.run_plans(root)
    world['discovery']['raid_inputs'] = [AUDIT]
    e2e = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter', 'bwd.beta.encounter']}])
    runs.record_e2e(root, e2e)
    assert 'raid_inputs_open:script_readiness_audit' in program(root)['e2e']['results'][-1]['problems']


@pytest.mark.parametrize('change,reason', [
    ('not_run', 'not_run'), ('blocked', 'missing_inputs:raid_target'), ('no_verdict', 'verdict_missing'),
    ('failing_verdict', 'verdict:fail')])
def test_accepted_boss_reopens_unless_it_passes_again(world, change, reason):
    root = world['root']
    rounds.plan(root)
    complete_round(root, {'alpha': PASS}, world, both())
    assert program(root)['units']['alpha']['status'] == 'accepted'
    rounds.plan(root)
    rows, verdicts = both(), {'alpha': PASS, 'beta': PASS}
    alpha = world['discovery']['units'][0]
    if change == 'not_run':
        alpha['ready_to_run'] = False
        rows = rows[1:]
    elif change == 'blocked':
        alpha['missing_inputs'] = [{'input': 'raid_target', 'detail': 'x', 'owner_skill': 'raid-tuning-playbook',
                                    'blocks': 'acceptance'}]
        alpha['acceptance_blocked'] = True
    elif change == 'no_verdict':
        verdicts.pop('alpha')
    else:
        verdicts['alpha'] = {'status': 'fail', 'reasons': ['below_target']}
    complete_round(root, verdicts, world, rows)
    result = program(root)['units']['alpha']['results'][-1]
    assert result['status'] == 'open' and result['reopened'] and reason in result['not_accepted_because']


def test_assess_refuses_without_a_label_when_target_bosses_ran(world):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    fake_build(root)
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1', both()))
    with pytest.raises(GraphError, match='--label'):
        rounds.assess(root)
    fake_ingest(root, world, 'round-label')
    with pytest.raises(GraphError, match='round-label'):
        rounds.assess(root, 'other-label')


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
    for bad in ['/abs/path.h', 'tests/../src/x.cpp', 'tests//test_alpha_x.py', 'tests/./test_alpha_x.py']:
        with pytest.raises(GraphError, match='handoff path'):
            rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', [bad]))
    with pytest.raises(GraphError, match='outside its packet'):
        rounds.record_handoff(root, 'boss:alpha', handoff(root, 'boss:alpha', ['sql/w/sub/alpha.sql']))
    rounds.record_handoff(root, 'boss:alpha', None, abandon_reason='agent did not return')
    rounds.record_handoff(root, 'boss:beta', handoff(root, 'boss:beta', ['tests/test_beta_strategy.py', 'sql/w/2026_beta.sql']))
    assert program(root)['stage'] == 'build'
    with pytest.raises(GraphError, match='clean tree'):
        builds.build(root, runner=runner(), worktree_state=lambda root: {'clean': False, 'commit': 'c' * 40})
    other = copy.deepcopy(world['discovery']) | {'program_id': 'firelands:10N', 'raid': 'firelands'}
    with pytest.raises(GraphError, match='mid-round'):
        rounds.select(root, other)


def test_build_failure_persists_steps_and_success_needs_a_binary(world):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    failed = fake_build(root, run=runner(fail='worldserver_build'))
    assert not failed['success'] and program(root)['stage'] == 'build'
    saved = json.loads(builds.progress_path(root, program(root)).read_text())
    assert [step['step'] for step in saved['steps']] == ['configure', 'worldserver_build']
    with pytest.raises(GraphError, match='no completed worldserver ticket'):
        builds.finish(root)
    unhashed = fake_build(root, run=runner(binary=None))
    assert not unhashed['success'] and 'sha256' in unhashed['error'] and program(root)['stage'] == 'build'
    assert fake_build(root)['worldserver_sha256'] == BINARY and program(root)['stage'] == 'run'


def test_build_uses_the_default_policy_job_count(world):
    root = world['root']
    policy = json.loads((REAL / DEFAULT_POLICY_RELATIVE).read_text())
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    dry = builds.build(root, dry_run=True)
    jobs = policy['parallelism']['maximum_compiler_jobs']
    assert dry['policy']['path'] == DEFAULT_POLICY_RELATIVE.as_posix() and dry['policy']['maximum_compiler_jobs'] == jobs
    assert dry['commands']['worldserver_build'][-2:] == ['--parallel', str(jobs)]
    assert f"{jobs} compiler jobs from the policy" in raid_program.resume(root)['next_action']


def test_reopen_and_coordinator_fix_from_the_build_stage(world):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='x')
    rounds.record_fix(root, 'repaired a missing include after the handoffs')
    assert program(root)['stage'] == 'build'
    assert rounds.current_round(program(root))['coordinator_fixes'][0]['reason'].startswith('repaired')
    rounds.reopen_packet(root, 'boss:beta', 'review found a lawfulness defect')
    state = program(root)
    assert state['stage'] == 'implement' and rounds.current_round(state)['packets']['boss:beta']['handoff'] is None
    assert raid_program.resume(root)['packets']['boss:beta']['handoff'] == 'pending'
    with pytest.raises(GraphError, match='not build'):
        fake_build(root)


def test_run_plans_once_replan_and_files_after_the_state_update(world):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    fake_build(root)
    stale = sha(root)
    store.update(root, lambda state: state | {'focus': 'boss'})  # any write moves the state hash
    with pytest.raises(GraphError, match='changed'):
        runs.run_plans(root, stale)
    assert not (root / 'artifacts/cata_raid_program/raid_programs').exists(), 'no plan file before the checked update'
    first = runs.run_plans(root)['plans']
    with pytest.raises(GraphError, match='--replan'):
        runs.run_plans(root)
    assert runs.run_plans(root, replan=True)['plans'] == first
    runs.record_run(root, shard_run(root, 'r1', both()))
    with pytest.raises(GraphError, match='instead of replanning'):
        runs.run_plans(root, replan=True)


def test_runs_bind_to_the_round_binary_and_failed_batches_are_recorded(world):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    fake_build(root)
    runs.run_plans(root)
    with pytest.raises(GraphError, match="not this round's build"):
        runs.record_run(root, shard_run(root, 'r1', both(), binary='f' * 64))
    with pytest.raises(GraphError, match='--reason'):
        runs.record_run(root, None, failed_batch=1)
    runs.record_run(root, None, failed_batch=1, reason='worldserver crashed before shard_run.json')
    rounds.assess(root)
    result = program(root)['units']['alpha']['results'][-1]
    assert result['outcome'] == 'batch_failed' and result['status'] == 'open'


def test_run_stage_commands_are_complete(world):
    root = world['root']
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    fake_build(root)
    runs.run_plans(root)
    commands = raid_program.resume(root)['commands']
    dry = [command for command in commands if command.endswith('--dry-run')]
    assert dry and all('--output-dir' in command for command in dry)
    label = raid_program.round_label(program(root))
    assert f'program ingest --label {label}' in ' '.join(commands)
    assert any('--failed-batch 1' in command for command in commands)


def test_packets_route_shard_files_and_refuse_shared_ownership(world):
    root = world['root']
    world['discovery']['units'][0]['missing_inputs'] = [
        {'input': 'runtime_profile', 'detail': 'x', 'owner_skill': 'raid-shard-architecture', 'blocks': 'run'}]
    rounds.plan(root)
    boss = raid_program.packet(root, 'boss:alpha')
    shards = raid_program.packet(root, 'shards')
    assert 'experiments/configs/validation_scenarios_cata_001.json' in boss['patch_request_routes']['shards']
    assert 'experiments/configs/cata_raid_script_readiness_v1.json' in boss['patch_request_routes']['coordinator']
    assert 'experiments/configs/validation_scenarios_cata_001.json' in shards['owned_files']
    assert 'shards' not in shards['patch_request_routes']
    assert shards['inputs'][0]['unit'] == 'alpha' and boss['inputs'] == []
    assert not set(boss['owned_files']) & set(shards['owned_files'])


@pytest.mark.parametrize('pattern', ['experiments/configs/raid_targets/shared.json', 'sql/w/*lph*'])
def test_plan_refuses_overlapping_packet_ownership(world, pattern):
    root = world['root']
    world['discovery']['units'][1]['files']['owned'].append(pattern)
    world['discovery']['units'][0]['files']['owned'].append('experiments/configs/raid_targets/shared.json')
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


def test_no_ready_shard_still_closes_the_round(world):
    root = world['root']
    for unit in world['discovery']['units']:
        unit['ready_to_run'] = False
        unit['missing_inputs'] = [{'input': 'runtime_scenario', 'detail': 'x', 'owner_skill': 'raid-shard-architecture',
                                   'blocks': 'run'}]
        unit['acceptance_blocked'] = True
    rounds.plan(root)
    assert 'shards' in rounds.current_round(program(root))['packets']
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, abandon_reason='x')
    fake_build(root)
    assert runs.run_plans(root)['plans'] == []
    assert 'program assess' in raid_program.resume(root)['commands'][0]
    rounds.assess(root)
    state = program(root)
    assert state['round'] == 2 and state['units']['alpha']['results'][-1]['outcome'] == 'not_run'


def test_verdict_must_come_from_the_round_build(monkeypatch, tmp_path):
    from tools.raid_program import scoreboard_verdict
    monkeypatch.setattr(scoreboard_verdict, 'evaluate_target', lambda root, scenario, label: {
        'status': 'pass', 'reasons': [], 'kills': 3, 'target_sha256': 't', 'worldserver_sha256': 'other'})
    unit = _unit('alpha', 0, [])
    assert rounds.verdict_for(tmp_path, unit, 'lbl', {'worldserver_sha256': 'mine'})['status'] == 'build_mismatch'
    assert rounds.verdict_for(tmp_path, unit, 'lbl', None)['status'] == 'build_mismatch'
    assert rounds.verdict_for(tmp_path, unit, 'lbl', {'worldserver_sha256': 'other'})['status'] == 'pass'
    assert rounds.verdict_for(tmp_path, unit, None, None) is None


def to_run(root: Path) -> None:
    rounds.plan(root)
    for packet_id in list(rounds.current_round(program(root))['packets']):
        rounds.record_handoff(root, packet_id, None, external_reason='x')
    fake_build(root)


def test_run_plans_name_the_generated_plan(world):
    root = world['root']
    to_run(root)
    plan = runs.run_plans(root)['plans'][0]
    document = json.loads((root / plan['path']).read_text())
    assert document['raid_shard_plan'] == 'dataset/raid_shard_provisioning/test_raid_v1/plan.json'
    world['discovery']['generated_plan'] = None
    with pytest.raises(GraphError, match='generated raid_shard_plan'):
        runs.run_plans(root, replan=True)


def test_shard_runs_must_live_under_tmp(world):
    root = world['root']
    to_run(root)
    runs.run_plans(root)
    path = shard_run(root, 'r1', both())
    summary = json.loads(path.read_text())
    summary['shards'][0]['run_dir'] = '/var/lib/elsewhere/alpha'
    path.write_text(json.dumps(summary))
    with pytest.raises(GraphError, match='under /tmp'):
        runs.record_run(root, path)


def test_ingest_records_then_archives_and_reports_failures(world):
    from tools.raid_program.scoreboard_core import exclusion_reason, load_records
    root = world['root']
    to_run(root)
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1', both()))
    world['archive_errors'].append('archive_run_evidence failed (exit 1)')
    result = raid_program.command(root, ['ingest', '--label', 'round1'])
    assert result['exit_status'] == 1
    pending = [error for error in result['ingest']['errors'] if 'retry' in error]
    assert pending and pending[0]['retry'].endswith('archive-pending --scenario blackwing_descent_10n_alpha')
    alpha = load_records(root, f'{RAID}_10n_alpha')[0]
    assert alpha['outcome'] == 'clear' and alpha['archive_error'] and alpha['evidence_paths']
    assert exclusion_reason(alpha) == 'no_evidence', 'counted only once archive-pending attaches the pointer'
    beta = load_records(root, f'{RAID}_10n_beta')[0]
    assert beta['evidence_dvc_pointer'] and exclusion_reason(beta) is None
    again = raid_program.command(root, ['ingest', '--label', 'round1'])
    assert again['exit_status'] == 1 and len(load_records(root, f'{RAID}_10n_alpha')) == 1, 'never recorded twice'
    archived = [kill_id for _, kill_id, _ in world['archived']]
    assert archived.count('round1-r1-blackwing_descent_10n_alpha_c0') == 1


def test_ingest_archives_batch_and_untargeted_shard_evidence(world):
    root = world['root']
    world['discovery']['units'][1]['raid_target']['present'] = False
    to_run(root)
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1', both()))
    result = ingests.ingest(root, 'round1')
    assert not result['errors']
    assert [row['cohort_id'] for row in result['shard_evidence']] == [f'{RAID}_10n_beta_c0']
    batch = next(iter(result['batch_evidence'].values()))
    assert {Path(path).name for path in batch['paths']} == {'shard_run.json', 'console_journal.jsonl'}
    current = rounds.current_round(program(root))
    assert current['runs'][0]['evidence']['pointer'] and current['shard_evidence'][0]['evidence_dvc_pointer']
    assert ingests.ingest(root, 'round1')['batch_evidence'] == {}, 'archived batches are not archived again'


def test_e2e_run_root_is_archived_after_reading_the_report(world):
    root = world['root']
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    runs.run_plans(root)
    e2e = shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter', 'bwd.beta.encounter']}])
    runs.record_e2e(root, e2e)
    result = program(root)['e2e']['results'][-1]
    assert result['outcome'] == 'clear' and result['evidence']['pointer']
    assert world['archived'][-1][2] == [str(e2e.parent)]


def to_e2e(root: Path, holder: dict) -> Path:
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, holder, both())
    runs.run_plans(root)
    return shard_run(root, 'e2e', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter', 'bwd.beta.encounter']}])


def test_e2e_archive_error_never_completes_and_archive_pending_retries(world):
    root = world['root']
    e2e = to_e2e(root, world)
    world['archive_errors'].append('archive_run_evidence failed (exit 1)')
    result = raid_program.command(root, ['e2e', '--shard-run', str(e2e)])
    assert result['exit_status'] == 1
    view = result['resume']
    assert view['stage'] == 'e2e' and not view['parent_objective_complete']
    assert program(root)['e2e']['status'] == 'evidence_pending'
    assert view['pending_e2e_evidence'][0]['error'] == 'archive_run_evidence failed (exit 1)'
    assert view['commands'] == ['pixi run python -m tools.raid_program.raid_workloop program e2e --archive-pending']
    with pytest.raises(GraphError, match='awaiting its evidence archive'):
        runs.record_e2e(root, e2e)
    assert e2e.exists(), 'the /tmp root is kept for the retry'
    final = raid_program.command(root, ['e2e', '--archive-pending'])
    assert final['stage'] == 'complete' and final['parent_objective_complete'] and not final['pending_e2e_evidence']
    assert program(root)['e2e']['results'][-1]['evidence']['pointer']


def test_complete_state_needs_an_archived_e2e_pointer(world):
    root = world['root']

    def forged(state):
        target = rounds.active(state)
        for unit in target['units'].values():
            unit['status'] = 'accepted'
        target['e2e'] = target['e2e'] | {'status': 'accepted', 'results': [{'outcome': 'clear', 'evidence': {'pointer': None}}]}
        target['stage'] = 'complete'
        return state
    with pytest.raises(GraphError, match='archived evidence pointer'):
        store.update(root, forged)


def test_e2e_result_survives_a_concurrent_write_during_a_deleting_archive(world):
    root = world['root']
    e2e = to_e2e(root, world)
    before = sha(root)

    def deleting_with_concurrent_write(root, name, kill_id, sources):
        store.set_focus(root, 'boss')  # e.g. a boss-level start while the archive runs
        for source in sources:
            shutil.rmtree(source)
        return {'pointer': f'artifacts/cata_raid_program/scoreboard_{name}_{kill_id}.tar.gz.dvc', 'error': None,
                'paths': [str(source) for source in sources]}
    runs.record_e2e(root, e2e, before, archive=deleting_with_concurrent_write)
    state = program(root)
    assert state['stage'] == 'complete' and state['e2e']['status'] == 'accepted'
    assert state['e2e']['results'][-1]['evidence']['state'] == 'archived' and not e2e.exists()
    assert store.load(root)[0]['focus'] == 'boss'


def test_run_plans_check_identity_against_the_generated_plan_under_root(world):
    from tools.raid_program.shard_coordinator import ShardPlanError
    root = world['root']
    to_run(root)
    generated = root / world['discovery']['generated_plan']
    generated.parent.mkdir(parents=True)

    def planned(boss, precompleted):
        cohort = f'{RAID}_10n_{boss}_c0'
        return {'cohort_id': cohort, 'runtime_profile_id': cohort + '_diagnostic', 'scenario_id': cohort + '_diagnostic',
                'pool_tag': cohort + '_diagnostic', 'boss_key': boss,
                'lockout': {'precompleted_boss_keys': precompleted} if precompleted else None}
    generated.write_text(json.dumps({'schema': 'raid_shard_plan_v1', 'shards': [planned('alpha', []), planned('beta', ['alpha'])]}))
    assert runs.run_plans(root)['plans'][0]['cohorts'] == [f'{RAID}_10n_alpha_c0', f'{RAID}_10n_beta_c0']
    generated.write_text(json.dumps({'schema': 'raid_shard_plan_v1', 'shards': [planned('alpha', []), planned('beta', [])]}))
    with pytest.raises(ShardPlanError, match='differs from its generated plan shard'):
        runs.run_plans(root, replan=True)


def test_archive_and_postprocess_output_stays_off_stdout(world, capfd):
    root = world['root']
    to_run(root)
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1', both()))

    def noisy(root, scenario, kill_id, sources, pointers):
        print('python stdout from the archiver')
        subprocess.run(['echo', 'subprocess stdout from archive_run_evidence'], check=True)
        return f'artifacts/cata_raid_program/scoreboard_{scenario}_{kill_id}.tar.gz.dvc', None
    capfd.readouterr()
    ingests.ingest(root, 'round1', archive=noisy)
    captured = capfd.readouterr()
    assert captured.out == '' and 'subprocess stdout from archive_run_evidence' in captured.err
    assert 'python stdout from the archiver' in captured.err


def test_e2e_archive_output_stays_off_stdout(world, capfd):
    root = world['root']
    e2e = to_e2e(root, world)

    def noisy(root, name, kill_id, sources):
        subprocess.run(['echo', '{"schema": "cata_evidence_cleanup_v1"}'], check=True)
        return {'pointer': f'artifacts/cata_raid_program/{name}_{kill_id}.tar.gz.dvc', 'error': None, 'paths': []}
    capfd.readouterr()
    runs.record_e2e(root, e2e, archive=noisy)
    captured = capfd.readouterr()
    assert captured.out == '' and 'cata_evidence_cleanup_v1' in captured.err
    assert program(root)['stage'] == 'complete'


def e2e_failing_archive(root: Path, holder: dict) -> tuple[Path, str]:
    """P3 setup: a clear whose archive failed, then its /tmp root is lost (tmpfs after a reboot)."""
    e2e = to_e2e(root, holder)
    holder['archive_errors'].append('dvc push failed')
    runs.record_e2e(root, e2e)
    shutil.rmtree(e2e.parent)
    return e2e, sha(root)


def test_p3_lost_root_has_a_typed_exit_that_reruns_the_full_route(world):
    root = world['root']
    e2e, before = e2e_failing_archive(root, world)
    result = raid_program.command(root, ['e2e', '--archive-pending'])
    evidence = program(root)['e2e']['results'][-1]['evidence']
    assert result['exit_status'] == 1 and evidence['state'] == 'failed' and evidence['root_missing']
    view = result['resume']
    assert view['commands'][0].startswith('pixi run python -m tools.raid_program.raid_workloop program e2e --evidence-lost')
    assert view['pending_e2e_evidence'][0]['retry'].endswith('--evidence-lost <reason>')
    with pytest.raises(GraphError, match='awaiting its evidence archive'):
        runs.record_e2e(root, e2e)
    runs.evidence_lost(root, 'tmpfs cleared by a reboot')
    state = program(root)
    last = state['e2e']['results'][-1]
    assert last['outcome'] == 'evidence_lost' and last['evidence']['state'] == 'lost'
    assert state['e2e']['status'] == 'open' and state['stage'] == 'plan' and not raid_program.resume(root)['parent_objective_complete']
    rounds.plan(root)
    shards = rounds.current_round(program(root))['packets']['shards']
    assert any(item['input'] == 'e2e_run' and 'evidence_lost' in item['detail'] for item in shards['inputs'])


def test_failed_is_allowed_while_a_clear_awaits_evidence(world):
    root = world['root']
    e2e_failing_archive(root, world)
    runs.record_e2e(root, None, failed_reason='abandon this attempt; the route is re-run next round')
    state = program(root)
    assert state['stage'] == 'plan' and state['e2e']['status'] == 'open'
    assert [row['outcome'] for row in state['e2e']['results']] == ['clear', 'failed']


def test_evidence_lost_is_refused_while_the_root_or_a_completed_archive_exists(world):
    root = world['root']
    e2e = to_e2e(root, world)
    world['archive_errors'].append('dvc push failed')
    runs.record_e2e(root, e2e)
    with pytest.raises(GraphError, match='still exists'):
        runs.evidence_lost(root, 'too early')
    result = program(root)['e2e']['results'][-1]
    base = root / 'artifacts/cata_raid_program' / f"scoreboard_blackwing_descent_10n_e2e_r{result['round']:02d}-e2e"
    pointer = Path(f'{base}.tar.gz.dvc')
    pointer.parent.mkdir(parents=True, exist_ok=True)
    pointer.write_text('outs: []\n')
    Path(f'{base}.publication.json').write_text(json.dumps({'dvc_pointer': str(pointer.relative_to(root))}))
    shutil.rmtree(e2e.parent)  # the archive completed and deleted the root before its state update
    with pytest.raises(GraphError, match='completed archive exists'):
        runs.evidence_lost(root, 'wrong: the archive completed')
    runs.archive_pending_e2e(root)
    state = program(root)
    evidence = state['e2e']['results'][-1]['evidence']
    assert evidence['adopted'] and evidence['pointer'] == str(pointer.relative_to(root)) and state['stage'] == 'complete'


def test_p4_a_program_switch_cannot_lose_the_pointer(world):
    root = world['root']
    e2e = to_e2e(root, world)
    other = copy.deepcopy(world['discovery']) | {'program_id': 'firelands:10N', 'raid': 'firelands'}

    def switching(root, name, kill_id, sources):
        with pytest.raises(GraphError, match='awaiting its evidence archive'):
            rounds.select(root, other)  # select() refuses to leave a program awaiting evidence

        def forced(state):  # a writer that switches anyway must still not lose the pointer
            state['programs']['firelands:10N'] = rounds.new_program(other)
            state['active_program'] = 'firelands:10N'
            return state
        store.update(root, forced)
        shutil.rmtree(sources[0])
        return {'pointer': f'artifacts/cata_raid_program/scoreboard_{name}_{kill_id}.tar.gz.dvc', 'error': None,
                'paths': [str(source) for source in sources]}
    runs.record_e2e(root, e2e, archive=switching)
    state = store.load(root)[0]
    bwd = state['programs'][f'{RAID}:{MODE}']
    assert state['active_program'] == 'firelands:10N'
    assert bwd['stage'] == 'complete' and bwd['e2e']['results'][-1]['evidence']['pointer']


def test_p4_a_vanished_result_is_a_typed_error(world):
    root = world['root']
    e2e = to_e2e(root, world)

    def dropping(root, name, kill_id, sources):
        def drop(state):
            state['programs'][f'{RAID}:{MODE}']['e2e']['results'].pop()
            state['programs'][f'{RAID}:{MODE}']['e2e']['status'] = 'open'
            return state
        store.update(root, drop)
        return {'pointer': 'artifacts/cata_raid_program/x.tar.gz.dvc', 'error': None, 'paths': []}
    with pytest.raises(GraphError, match='vanished'):
        runs.record_e2e(root, e2e, archive=dropping)


def test_p5_an_old_failed_run_with_open_evidence_does_not_block_later_rounds(world):
    root = world['root']
    to_e2e(root, world)
    failing = shard_run(root, 'e2e-fail', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter']}])
    world['archive_errors'].append('dvc push failed')
    runs.record_e2e(root, failing)
    assert program(root)['e2e']['results'][-1]['evidence']['state'] == 'failed' and program(root)['stage'] == 'plan'
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    assert program(root)['stage'] == 'e2e'
    runs.record_e2e(root, None, failed_reason='plan not runnable this time')
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    runs.run_plans(root)
    fresh = shard_run(root, 'e2e-new', [{'cohort_id': f'{RAID}_10n_full_c0', 'killed': ['bwd.alpha.encounter', 'bwd.beta.encounter']}])
    runs.record_e2e(root, fresh)
    assert program(root)['stage'] == 'complete'
    assert raid_program.resume(root)['pending_e2e_evidence'][0]['outcome'] == 'failed', 'still listed for retry'


def test_e2e_plan_matches_the_generated_full_raid_shard(world):
    from tools.raid_program.shard_coordinator import ShardPlanError
    root = world['root']
    rounds.plan(root)
    complete_round(root, {'alpha': PASS, 'beta': PASS}, world, both())
    generated = root / world['discovery']['generated_plan']
    generated.parent.mkdir(parents=True, exist_ok=True)
    full = f'{RAID}_10n_full_c0'
    generated.write_text(json.dumps({'schema': 'raid_shard_plan_v1', 'shards': [
        {'cohort_id': full, 'runtime_profile_id': full, 'scenario_id': full, 'pool_tag': full, 'boss_key': 'full',
         'shard_kind': 'full_raid', 'lockout': {'precompleted_boss_keys': []}}]}))
    plan = runs.run_plans(root)['plans'][0]
    document = json.loads((root / plan['path']).read_text())
    assert document['kind'] == 'e2e' and document['shards'][0]['boss_key'] == 'full'
    stale = copy.deepcopy(document)
    stale['shards'][0]['boss_key'] = 'e2e'
    with pytest.raises(ShardPlanError, match=r"differs from its generated plan shard: \['boss_key'\]"):
        runs.validate_document(root, stale)


def test_voided_kills_without_evidence_do_not_fail_ingest(world):
    from tools.raid_program.scoreboard import void_kill
    root = world['root']
    to_run(root)
    runs.run_plans(root)
    runs.record_run(root, shard_run(root, 'r1', both()))
    world['archive_errors'].append('evidence lost before archive')
    assert raid_program.command(root, ['ingest', '--label', 'round1'])['exit_status'] == 1
    void_kill(root, f'{RAID}_10n_alpha', 'round1-r1-blackwing_descent_10n_alpha_c0', 'evidence lost; never counted')
    again = raid_program.command(root, ['ingest', '--label', 'round1'])
    assert 'exit_status' not in again and again['ingest']['voided'][0]['kill_id'] == 'round1-r1-blackwing_descent_10n_alpha_c0'

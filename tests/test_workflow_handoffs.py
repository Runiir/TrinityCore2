"""Exercise production handoffs; queue/native provenance has its own fixtures."""
import json

import pytest

from tests.test_development_graph import case, put, receipt, reach
from tools.raid_program import development_graph as graph
from tools.raid_program.build_handoff import finish_build
from tools.raid_program.worker_packet import packet
from tools.raid_program.workflow_step import apply_step, main


def commit(root, *paths):
    graph.git(root, 'add', '-f', *paths)
    graph.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid',
              'commit', '-qm', 'fixture')


def build_case(case):
    root, state, evidence = reach(case, 'build')
    put(root / graph.STATE_PATH, state)
    commit(root, str(graph.STATE_PATH))
    queued = {'resource_class': 'worldserver_build', 'commit': graph.git(root, 'rev-parse', 'HEAD'),
              'exit_code': 0, 'source_identity_stable': True, 'test_mode': False,
              'output_artifacts': [{'kind': 'worldserver_elf', 'sha256': 'b'*64, 'produced_by_ticket': True}]}
    path = root / '.git/queue-result.json'
    put(path, queued)
    return root, state, path, queued


def test_finish_generates_complete_receipt_and_advances_without_build(case):
    root, state, path, _ = build_case(case)
    before = (root / graph.STATE_PATH).read_bytes()
    result = finish_build(root, path)
    assert (root / graph.STATE_PATH).read_bytes() == before
    assert finish_build(root, path) == result
    ref = result['receipt']
    native = json.loads((root / ref['path']).read_text())
    assert native['binary_sha256'] == 'b'*64
    assert native['operation_id'] == state['development_graph']['claim']['operation_id']
    transition = apply_step(root, ref['path'], owner=state['development_graph']['claim']['owner'])
    assert transition['stage'] == 'validate'


@pytest.mark.parametrize('mutation', ['configure', 'not_produced', 'wrong_claim', 'changed_source', 'failed_verifier'])
def test_finish_rejects_unusable_queue_evidence(case, monkeypatch, mutation):
    root, state, path, queued = build_case(case)
    if mutation == 'configure': queued['resource_class'] = 'configure'
    if mutation == 'not_produced': queued['output_artifacts'][0]['produced_by_ticket'] = False
    if mutation == 'wrong_claim':
        state['development_graph']['claim']['owner'] = 'different-owner'
        put(root / graph.STATE_PATH, state)
    if mutation == 'changed_source':
        (root / 'code.cpp').write_text('changed since reviewed build')
        commit(root, 'code.cpp')
    if mutation == 'failed_verifier':
        from tools.raid_program import queued_build
        monkeypatch.setattr(queued_build, 'verify_receipt', lambda *a, **k: {'gate_bearing': False})
    put(path, queued)
    with pytest.raises(ValueError): finish_build(root, path)
    assert not list((root / 'artifacts/cata_raid_program').glob('workflow-build-*.json'))


def test_plan_rejects_stale_source_before_implementation(case):
    root, state, evidence = case
    base = graph.git(root, 'rev-parse', 'HEAD')
    state['development_graph']['source_base_commit'] = base
    (root / 'unowned.cpp').write_text('already changed by a prior unit')
    commit(root, 'unowned.cpp')
    with pytest.raises(graph.GraphError, match='outside bounded assignment'):
        graph.reduce(root, state, receipt(root, state, evidence, base_commit=base))
    assert state['development_graph']['stage'] == 'diagnose'


def test_implementation_claim_rechecks_source_before_worker_starts(case):
    root, state, evidence = case
    state = graph.reduce(root, state, receipt(root, state, evidence))
    (root / 'unowned.cpp').write_text('changed after plan')
    commit(root, 'unowned.cpp')
    g = state['development_graph']
    with pytest.raises(graph.GraphError, match='outside bounded assignment'):
        graph.reduce(root, state, {'action': 'claim', 'owner': 'worker', 'unit_id': g['unit']['id'], 'revision': g['revision']})


def test_new_unit_gets_current_baseline_without_accepting_previous_requirements(case):
    root, state, evidence = reach(case, 'route')
    (root / 'code.cpp').write_text('next diagnosis starts here')
    commit(root, 'code.cpp')
    g = state['development_graph']
    next_state = graph.reduce(root, state, {'action': 'route', 'reason': 'next proven edge',
        'unit_id': g['unit']['id'], 'revision': g['revision'],
        'unit': {'id': 'u2', 'edge': 'edge2', 'requirements': ['actor_1'], 'next_action': 'diagnose'}})
    assert next_state['development_graph']['source_base_commit'] == graph.git(root, 'rev-parse', 'HEAD')
    assert next_state['development_graph']['requirements'] == g['requirements']


def context(root, evidence, kind='implementation'):
    return {'kind': kind, 'question': 'Which slot becomes usable next?',
            'decision': 'Repair the estimator only if native pairing disagrees.',
            'counterexample': 'Waiting slot cannot become ready before its regenerating partner.',
            'fixture': evidence, 'native_behavior': [{'path': 'code.cpp',
                'sha256': graph.snapshot(root, ['code.cpp'])['code.cpp'], 'start_line': 1, 'end_line': 1}]}


def test_worker_packet_joins_real_source_and_preserves_parent(case, tmp_path, capsys):
    root, state, evidence = case
    state = graph.reduce(root, state, receipt(root, state, evidence, worker_context=context(root, evidence)))
    put(root / graph.STATE_PATH, state)
    result = packet(root)
    assert result['context']['native_behavior'][0]['text'] == 'original'
    assert result['open_requirements'] == ['setup', 'actor_1', 'actor_2']
    assert result['required_test_commands'] == ['pytest focused']
    target = tmp_path / 'packet.json'
    assert main(['--root', str(root), 'packet', '--output', str(target)]) == 0
    assert json.loads(target.read_text()) == result
    assert len(capsys.readouterr().out) < 1000


@pytest.mark.parametrize('problem', ['missing_context', 'missing_decision', 'observation_without_outcomes', 'bad_hash', 'large'])
def test_worker_packet_reports_missing_or_incoherent_context(case, problem):
    root, state, evidence = case
    ctx = context(root, evidence)
    if problem == 'missing_decision': ctx.pop('decision')
    if problem == 'observation_without_outcomes': ctx['kind'] = 'observation'
    if problem == 'bad_hash': ctx['native_behavior'][0]['sha256'] = '0'*64
    if problem == 'large': ctx['question'] = 'x'*10000
    if problem == 'missing_context':
        state = graph.reduce(root, state, receipt(root, state, evidence))
        put(root / graph.STATE_PATH, state)
        with pytest.raises(ValueError, match='lacks worker_context'): packet(root)
    else:
        with pytest.raises(ValueError):
            graph.reduce(root, state, receipt(root, state, evidence, worker_context=ctx))


def test_observation_packet_requires_actionable_live_outcomes(case):
    root, state, evidence = case
    ctx = context(root, evidence, 'observation')
    ctx['observation_decision'] = {'signal': 'slot readiness at the decision',
        'if_confirmed': 'Route a paired-timer estimator repair.',
        'if_refuted': 'Keep estimator and compare target legality.',
        'live_check': 'Join the next native decision using actor/cast/time.'}
    state = graph.reduce(root, state, receipt(root, state, evidence, worker_context=ctx))
    put(root / graph.STATE_PATH, state)
    assert packet(root)['context']['observation_decision'] == ctx['observation_decision']

"""Production reducer/CLI fixtures for closed, unaccepted historical runs."""
import copy
import json
import subprocess
from pathlib import Path

import pytest

from test_development_graph import case, claimed, put, reach, receipt
from tools.raid_program import completed_operation as completed
from tools.raid_program import development_graph as graph
from tools.raid_program import workflow_step


def commit(root, *files):
    graph.git(root, 'add', '-f', *files)
    graph.git(root, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'fixture')
    return graph.git(root, 'rev-parse', 'HEAD')


@pytest.mark.parametrize('action', ['release', 'rework'])
@pytest.mark.parametrize('attach', [True, False])
def test_completed_run_blocks_false_reconciliation_even_if_not_attached(case, action, attach):
    root, state, evidence = reach(case, 'validate')
    g = state['development_graph']; event = receipt(root, state, evidence)
    run = json.loads((root/event['receipt']['path']).read_text())
    run['calibration_acceptance_passed'] = False
    path = root/'artifacts/cata_raid_program/completed.json'; put(path, run)
    ref = {'path': str(path.relative_to(root)), 'sha256': graph.digest(path.read_bytes())}
    rec = put(root/'reconcile.json', {'operation_id': g['claim']['operation_id'],
        'ownership_checked': True, 'active_operation': False, 'completed_operation': False,
        'reusable_receipt_found': False, 'evidence': [ref] if attach else []})
    before = copy.deepcopy(state)
    with pytest.raises(graph.GraphError, match='operation already completed'):
        graph.reduce(root, state, {'revision': g['revision'], 'unit_id': g['unit']['id'],
            'action': action, 'reason': 'reference rejected; retry', 'receipt': rec,
            'claim_token': g['claim']['token']})
    assert state == before


def test_other_operation_does_not_block_legitimate_abandoned_claim(case):
    root, state, evidence = reach(case, 'validate'); g = state['development_graph']
    put(root/'artifacts/cata_raid_program/other.json', {'kind': 'run', 'closed': True,
        'unit_id': g['unit']['id'], 'operation_id': 'other'})
    rec = put(root/'reconcile.json', {'operation_id': g['claim']['operation_id'],
        'ownership_checked': True, 'active_operation': False, 'completed_operation': False,
        'reusable_receipt_found': False})
    result = graph.reduce(root, state, {'revision': g['revision'], 'unit_id': g['unit']['id'],
        'action': 'release', 'receipt': rec, 'claim_token': g['claim']['token']})
    assert 'claim' not in result['development_graph']


def recorded_case(case, change_before_launch=False):
    root, state, evidence = reach(case, 'validate')
    event = receipt(root, state, evidence)
    put(root/graph.STATE_PATH, state)
    if change_before_launch:
        (root/'code.cpp').write_text('changed after build')
        commit(root, 'code.cpp')
    launch = commit(root, str(graph.STATE_PATH))
    (root/'code.cpp').write_text('later gameplay, not validated by old run')
    commit(root, 'code.cpp')
    return root, state, evidence, event, launch


def test_explicit_historical_admission_preserves_identity_and_blocks_current_acceptance(case):
    root, state, evidence, event, launch = recorded_case(case)
    with pytest.raises(graph.GraphError, match='source changed'):
        graph.reduce(root, state, event)
    assert completed.find_launch_commit(root, state['development_graph']) == launch
    before = (root/graph.STATE_PATH).read_bytes()
    args = (root, event['receipt']['path'])
    preview = workflow_step.apply_step(*args, owner='fixture-tab', recorded_source=True, dry_run=True)
    assert preview['event']['recorded_source_commit'] == launch
    assert (root/graph.STATE_PATH).read_bytes() == before
    workflow_step.apply_step(*args, owner='fixture-tab', recorded_source=True)
    assessed = graph.read(root/graph.STATE_PATH); g = assessed['development_graph']
    assert g['stage'] == 'assess' and g['run']['source_scope'] == 'recorded_source_only'
    assert g['run']['build_identity'] == state['development_graph']['build_identity']
    stripped = copy.deepcopy(assessed)
    stripped['development_graph']['run'].pop('source_scope')
    with pytest.raises(graph.GraphError, match='source scope differs'):
        graph.check_state(root, stripped)
    with pytest.raises(graph.GraphError, match='cannot accept the current source'):
        graph.reduce(root, assessed, receipt(root, assessed, evidence))
    closed = graph.reduce(root, assessed, receipt(root, assessed, evidence,
        repair_accepted=False, accepted_requirements=[]))
    closed = claimed(root, closed)
    published = graph.reduce(root, closed, receipt(root, closed, evidence))
    assert published['development_graph']['stage'] == 'route'
    assert published['development_graph']['requirements'] == state['development_graph']['requirements']


def test_recorded_source_refuses_changes_between_build_and_launch(case):
    root, state, evidence, event, launch = recorded_case(case, change_before_launch=True)
    with pytest.raises(graph.GraphError, match='between recorded build and launch'):
        graph.reduce(root, state, dict(event, recorded_source_commit=launch))


@pytest.mark.parametrize('changes,match', [
    ({'closed': False}, 'closed and cleaned'),
    ({'cleanup_verified': False}, 'closed and cleaned'),
    ({'build_identity': {}}, 'run/build mismatch'),
    ({'operation_id': 'other'}, 'operation identity mismatch'),
])
def test_historical_path_preserves_existing_run_checks(case, changes, match):
    root, state, evidence, event, launch = recorded_case(case)
    data = graph.read(root/event['receipt']['path']); data.update(changes)
    event['receipt'] = put(root/'bad-run.json', data)
    with pytest.raises(graph.GraphError, match=match):
        graph.reduce(root, state, dict(event, recorded_source_commit=launch))


def test_wrong_or_uncommitted_claim_cannot_gain_historical_admission(case):
    root, state, evidence = reach(case, 'validate')
    with pytest.raises(graph.GraphError, match='no committed launch snapshot'):
        completed.find_launch_commit(root, state['development_graph'])


def test_compact_default_has_full_opt_in_without_read_mutation(case):
    root, state, _ = case
    state['development_graph']['completed_measurements'] = [{'spec': 'fixture', 'details': 'x'*30000}]
    put(root/graph.STATE_PATH, state); before = (root/graph.STATE_PATH).read_bytes()
    command = ['python', '-m', 'tools.raid_program.raid_workloop', '--root', str(root), 'resume']
    output = subprocess.check_output(command, text=True)
    compact = json.loads(output)
    assert len(output) < 6000 and compact['completed_measurement_count'] == 1
    assert compact['objective'] == state['development_graph']['objective']
    assert compact['dps_acceptance']['minimum_reference_ratio'] == .95
    full = json.loads(subprocess.check_output(command + ['--full'], text=True))
    assert full['completed_measurements'] == state['development_graph']['completed_measurements']
    assert (root/graph.STATE_PATH).read_bytes() == before

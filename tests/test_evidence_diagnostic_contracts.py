import json
import shlex

import pytest

from tools.raid_program.evidence_view import main


def progress():
    return dict(state_sha256='a' * 64, revision=381, stage='validate',
        coordinator_worktree='/repo', objective='Complete every actor and the encounter',
        unit={'id': 'boss:setup', 'edge': 'missing_enchant', 'owner_skill': 'raid-role-implementation',
              'objective': 'Repair exact setup', 'requirements': ['tank'], 'next_action': 'Validate setup readback',
              'forbidden_changes': ['No damage tuning']},
        claim={'owner': 'worker', 'operation_id': 'op', 'stage': 'validate'}, changed_bootstrap_sources=[], same_edge_failures=0,
        open_requirements={f'actor_{i}': {'status': 'open', 'history': 'x' * 10000} for i in range(25)},
        latest_assessment={'path': 'assessment.json', 'sha256': 'b' * 64},
        receipts={'build': {'path': 'build.json', 'sha256': 'c' * 64}},
        next_action='Reconcile claimed validation before launching', parent_objective_complete=False)


def test_large_saved_task_retains_decision_fields_and_executable_next_command(monkeypatch, capsys):
    p = progress()
    monkeypatch.setattr('tools.raid_program.development_graph.resume', lambda root: p)
    main(['task', '--max-chars', '6000'])
    text = capsys.readouterr().out
    d = json.loads(text)
    assert len(text) <= 6000
    assert d['objective'] == p['objective'] and d['unit']['edge'] == 'missing_enchant'
    assert d['blockers']['claimed_operation_owner'] == 'worker'
    assert d['evidence']['latest_assessment'] == p['latest_assessment']
    assert len(d['open_requirement_ids']) == 25 and not d['parent_objective_complete']
    command = shlex.split(d['next_command'])
    main(command[command.index('task'):])
    detail = json.loads(capsys.readouterr().out)
    assert detail['receipts']['build'] == p['receipts']['build']
    main(['task', '--section', 'unit'])
    assert json.loads(capsys.readouterr().out)['unit']['forbidden_changes'] == ['No damage tuning']


def test_unrepresentable_required_fields_fail_without_structural_fallback(monkeypatch, capsys):
    p = progress(); p['objective'] = 'x' * 20000
    monkeypatch.setattr('tools.raid_program.development_graph.resume', lambda root: p)
    with pytest.raises(SystemExit) as error:
        main(['task', '--max-chars', '6000'])
    output = capsys.readouterr()
    assert error.value.code == 2 and output.out == ''
    assert 'query_exceeds_output_budget' in output.err and 'required selectors' in output.err


def test_result_separates_repair_metrics_from_reference_failure_without_raw_snapshots(tmp_path, capsys):
    p = tmp_path/'report.json'
    report = {'completion_reason': 'combat_calibration_role_gate_failed', 'returncode': 0, 'timed_out': False,
        'role_calibration_evaluation': {'passed': False, 'failure_reasons': ['reference_conditions_not_comparable'],
            'checks': {'dispels': True, 'reference_comparison_eligible': False, 'other': None}},
        'role_calibration_record': {'window': {'scored_duration_seconds': 300},
            'metrics': {'dispel_success_ratio': 1, 'death_count': 0},
            'raw_runtime_status': {'repeated_snapshots': 'x' * 1000000}}}
    p.write_text(json.dumps(report))
    main(['result', str(p), '--metric', '/role_calibration_record/metrics/dispel_success_ratio', '--max-chars', '6000'])
    output = capsys.readouterr().out; d = json.loads(output)
    assert len(output) < 6000 and 'repeated_snapshots' not in output
    assert d['role_gate']['passed'] is False
    assert d['role_gate']['failed_checks'] == ['reference_comparison_eligible']
    assert d['role_gate']['unknown_checks'] == ['other']
    assert d['role_metrics']['dispel_success_ratio'] == 1 and d['scored_seconds'] == 300
    assert d['native_clear'] is None and 'role_calibration_identity' in d['missing_observations']
    assert d['source']['payload_bytes'] > 1000000
    with pytest.raises(SystemExit):
        main(['result', str(p), '--metric', '/role_calibration_record/raw_runtime_status'])
    assert 'requires_scalar' in capsys.readouterr().err
    with pytest.raises(SystemExit):
        main(['result', str(p), '--metric', '/missing'])
    assert capsys.readouterr().out == ''


def test_reference_result_uses_native_compatibility_fields_and_rejects_malformed_metrics(tmp_path, capsys):
    p = tmp_path/'report.json'
    report = {'completion_reason': 'role_gate_failed', 'role_calibration_record': {
        'reference_condition_compatibility': {'conditions_compatible': False,
            'reasons': ['request_hash_mismatch'], 'checks': {'request_hash_matches': False}}}}
    p.write_text(json.dumps(report))
    main(['result', str(p), '--section', 'reference'])
    result = json.loads(capsys.readouterr().out)['reference_gate']
    assert result['conditions_compatible'] is False
    assert result['reasons'] == ['request_hash_mismatch']
    report['role_calibration_record']['metrics'] = ['malformed']
    p.write_text(json.dumps(report))
    with pytest.raises(SystemExit):
        main(['result', str(p)])
    assert 'result_field_requires_object' in capsys.readouterr().err

import hashlib
import io
import json
import tarfile

import pytest

from test_evidence_view import calibration
from tools.raid_program.evidence_task import checked, report_input, task_view


def descriptor(root, name, data):
    path = root/name
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data).encode()
    path.write_bytes(payload)
    return {'path': name, 'sha256': hashlib.sha256(payload).hexdigest()}


def run_fixture(root):
    payload = json.dumps(calibration(guid=42)).encode()
    archive_path = root/'capture.tar.gz'
    with tarfile.open(archive_path, 'w:gz') as archive:
        for name, data in [('different/report.json', b'{}'), ('generic/spec/report.json', payload)]:
            info = tarfile.TarInfo(name); info.size = len(data)
            archive.addfile(info, io.BytesIO(data))
    pointer = descriptor(root, 'capture.tar.gz.dvc', {'outs': []})
    return {'kind': 'run', 'unit_id': 'boss:unit1', 'target_spec': 'test_spec',
            'report_summary': {'actor_report_sha256': hashlib.sha256(payload).hexdigest()}, 'evidence': [pointer]}


def test_report_resolved_by_hash_and_missing_payload_has_hydration_command(tmp_path):
    run = run_fixture(tmp_path)
    assert report_input(tmp_path, run).endswith('::generic/spec/report.json')
    (tmp_path/'capture.tar.gz').unlink()
    with pytest.raises(ValueError, match='pixi run dvc pull'):
        report_input(tmp_path, run)


def test_changed_receipt_rejected(tmp_path):
    ref = descriptor(tmp_path, 'receipt.json', {'kind': 'run'})
    (tmp_path/'receipt.json').write_text('{}')
    with pytest.raises(ValueError, match='hash mismatch'):
        checked(tmp_path, ref)


def test_persisted_receipts_reject_parent_and_symlink_escapes(tmp_path):
    outside = tmp_path.parent / 'outside-receipt.json'
    outside.write_text('{}')
    parent = {
        'path': '../outside-receipt.json',
        'sha256': hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    with pytest.raises(ValueError, match='escapes repository'):
        checked(tmp_path, parent)

    link = tmp_path / 'receipt-link.json'
    link.symlink_to(outside)
    symlink = {
        'path': 'receipt-link.json',
        'sha256': hashlib.sha256(outside.read_bytes()).hexdigest(),
    }
    with pytest.raises(ValueError, match='escapes repository'):
        checked(tmp_path, symlink)


def test_report_input_rejects_escaped_dvc_pointer(tmp_path):
    outside = tmp_path.parent / 'outside-capture.tar.gz.dvc'
    outside.write_text('{}')
    run = {
        'report_summary': {'actor_report_sha256': '0' * 64},
        'evidence': [{
            'path': '../outside-capture.tar.gz.dvc',
            'sha256': hashlib.sha256(outside.read_bytes()).hexdigest(),
        }],
    }
    with pytest.raises(ValueError, match='escapes repository'):
        report_input(tmp_path, run)


def test_saved_task_binds_actual_actor_promoted_reference_and_preserves_parent(tmp_path, monkeypatch):
    from tools.raid_program import raid_workloop
    run = run_fixture(tmp_path)
    ref = descriptor(tmp_path, 'run.json', run)
    assessment = descriptor(tmp_path, 'assessment.json', {'unit_id': run['unit_id'], 'evidence': [ref], 'baseline': ref})
    graph = {'objective': 'all actors', 'unit': {'id': 'boss:unit2', 'requirements': ['actor_999']},
             'stage': 'review', 'claim': {'owner': 'other-worker'},
             'requirements': {'actor_999': {'status': 'open'}, 'raid': {'status': 'open'}},
             'history': [{'from': 'assess', 'event': {'action': 'advance', 'receipt': assessment}}]}
    state = descriptor(tmp_path, 'experiments/configs/cata_raid_active_work_unit_v1.json', {'development_graph': graph})
    content = b'{}'; hashed_name = hashlib.sha256(content).hexdigest()+'.json'
    (tmp_path/hashed_name).write_bytes(content)
    refs = {k: hashed_name for k in ('raid_sim_request', 'raid_sim_result', 'compute_stats')}
    monkeypatch.setattr(raid_workloop, 'build_spec_work_unit', lambda spec, root: {'benchmark': {
        'state': 'ready', 'accepted_dps_reference_class': 'self_provided_baseline', 'rotation_review_reference_artifacts': refs}})
    result = task_view(tmp_path)
    assert 'missing' not in result
    assert result['retained_run']['actor'] == '42'
    assert result['reference_catalog']['root'] == str(tmp_path)
    assert result['reference_catalog']['state'] == 'ready'
    assert '--actor 42' in result['commands'][0]['command']
    assert 'admission ' in result['commands'][0]['command']
    assert result['claim'] == graph['claim'] and result['unit'] == graph['unit']
    assert result['open_requirements'] == graph['requirements']
    assert checked(tmp_path, state)['development_graph'] == graph


def test_task_view_rejects_reference_path_escape(tmp_path, monkeypatch):
    run = run_fixture(tmp_path)
    ref = descriptor(tmp_path, 'run.json', run)
    assessment = descriptor(tmp_path, 'assessment.json', {
        'unit_id': run['unit_id'], 'evidence': [ref], 'baseline': ref,
    })
    graph = {
        'objective': 'all actors',
        'unit': {'id': 'boss:unit2', 'requirements': ['actor_999']},
        'stage': 'review',
        'requirements': {'actor_999': {'status': 'open'}, 'raid': {'status': 'open'}},
        'history': [{'from': 'assess', 'event': {'action': 'advance', 'receipt': assessment}}],
    }
    descriptor(
        tmp_path,
        'experiments/configs/cata_raid_active_work_unit_v1.json',
        {'development_graph': graph},
    )
    outside = tmp_path.parent / 'reference.json'
    payload = b'{}'
    outside.write_bytes(payload)
    reference = hashlib.sha256(payload).hexdigest() + '.json'
    outside.rename(tmp_path.parent / reference)
    monkeypatch.setattr(
        'tools.raid_program.raid_workloop.build_spec_work_unit',
        lambda spec, root: {'benchmark': {
            'state': 'ready',
            'accepted_dps_reference_class': 'self_provided_baseline',
            'rotation_review_reference_artifacts': {
                key: '../' + reference
                for key in ('raid_sim_request', 'raid_sim_result', 'compute_stats')
            },
        }},
    )
    result = task_view(tmp_path)
    assert result['missing'] == 'receipt path escapes repository'


def test_detail_sections_keep_tier_and_finish_line_compact(tmp_path):
    from tools.raid_program.evidence_task import progress_view
    progress = {'state_sha256': 's', 'revision': 1, 'stage': 'diagnose', 'coordinator_worktree': str(tmp_path),
                'open_requirements': {'actor_1': {'status': 'open'}},
                'tier': {'risk_tier': 'class_native', 'remaining_steps': ['diagnose'], 'skipped_steps': ['smoke'],
                         'conditional_steps': {}, 'declared': {'unit': None, 'plan': None}},
                'finish_line': {'target_path': 't.json', 'target_present': True, 'work_item': None, 'rule': 'long rule',
                                'open_actor_requirements': ['actor_1'], 'open_encounter_requirements': [],
                                'verdict_command': 'cmd', 'run_receipt_command': 'cmd'}}
    view = progress_view(progress, tmp_path, 'requirements')
    assert view['tier'] == {'risk_tier': 'class_native', 'remaining_steps': ['diagnose']}
    assert view['finish_line'] == {'target_path': 't.json', 'target_present': True, 'work_item': None}
    assert view['open_requirements'] == progress['open_requirements']

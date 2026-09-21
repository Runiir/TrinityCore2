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
    assert '--actor 42' in result['commands'][0]['command']
    assert 'admission ' in result['commands'][0]['command']
    assert result['claim'] == graph['claim'] and result['unit'] == graph['unit']
    assert result['open_requirements'] == graph['requirements']
    assert checked(tmp_path, state)['development_graph'] == graph

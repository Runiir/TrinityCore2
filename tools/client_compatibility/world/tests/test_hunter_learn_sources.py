"""Actual remote semantics and pinned manifests gate the new ordinary unit."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.client_compatibility import hunter_learn_sources as sources


def test_pure_contract_source_and_rest_modules_import_without_live_ui_dependencies():
    code = '''
import importlib, sys
class BlockUI:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('google', 'PIL', 'tools.client_compatibility.interaction_')):
            raise AssertionError('pure guard imported live dependency: ' + fullname)
sys.meta_path.insert(0, BlockUI())
for name in ('hunter_learn_contract', 'hunter_learn_sources', 'hunter_learn_preservation', 'hunter_learn_pet'):
    importlib.import_module('tools.client_compatibility.' + name)
'''
    subprocess.run([sys.executable, '-c', code], check=True, cwd=Path(__file__).resolve().parents[4], capture_output=True)


def remote_fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(sources.lab, 'ROOT', tmp_path)
    p = tmp_path / 'evidence' / sources.REMOTE_NAME
    p.parent.mkdir()
    episode = p.parent / 'fixture' / 'episode.json'
    episode.parent.mkdir()
    episode.write_text('{}')
    value = {'schema': 'client442_native_feedback_remote_review_v1', 'actual_remote_verified': True,
        'complete_json_png_verified': True, 'pointer': sources.POINTER, 'archive_sha256': sources.ARCHIVE_SHA256,
        'bytes': sources.ARCHIVE_BYTES, 'proof': {'operation': 'pets.revive', 'owner': 6, 'pet_number': 16,
            'native_requests': 1, 'modern_requests': 1, 'native_dead_to_alive': True, 'capture_checks': 18,
            'restoration_checks': 17, 'closure_checks': 21, 'shutdown_checks': 8, 'all_six_offline': True,
            'both_owned_clients_stopped': True, 'named_pet_preserved': 4, 'qualification_added': False}}
    checkpoint = {'file': sources.POINTER.removesuffix('.dvc'), 'sha256': sources.ARCHIVE_SHA256,
        'bytes': sources.ARCHIVE_BYTES, 'cloud_verified': True, 'file_manifest': [
            {'path': str(episode.relative_to(tmp_path)), 'sha256': sources.lab.sha256(episode)}]}
    return p, episode, value, checkpoint


@pytest.mark.parametrize('fault', [None, 'local_only', 'wrong_operation', 'missing_delivery', 'boolean_count',
    'wrong_shutdown', 'wrong_archive', 'changed_source', 'duplicate_manifest', 'changed_review'])
def test_remote_admission_requires_actual_complete_matching_semantics(tmp_path, monkeypatch, fault):
    path, episode, value, checkpoint = remote_fixture(tmp_path, monkeypatch)
    if fault == 'local_only': value['actual_remote_verified'] = False
    elif fault == 'wrong_operation': value['proof']['operation'] = 'pets.dismiss'
    elif fault == 'missing_delivery': value['proof']['modern_requests'] = 0
    elif fault == 'boolean_count': value['proof']['native_requests'] = True
    elif fault == 'wrong_shutdown': value['proof']['shutdown_checks'] = 7
    elif fault == 'wrong_archive': checkpoint['bytes'] -= 1
    elif fault == 'changed_source': episode.write_text('{"changed":true}')
    elif fault == 'duplicate_manifest': checkpoint['file_manifest'].append(deepcopy(checkpoint['file_manifest'][0]))
    path.write_text(json.dumps(value))
    monkeypatch.setattr(sources, 'REMOTE_SHA256', sources.lab.sha256(path))
    if fault == 'changed_review': path.write_text(json.dumps({**value, 'reviewed_at': 42}))
    if fault:
        with pytest.raises(RuntimeError): sources.remote_admission(path, checkpoint, [episode])
    else:
        assert sources.remote_admission(path, checkpoint, [episode]) == value


@pytest.mark.parametrize('fault', ['symlink', 'incomplete', 'failure', 'unfinished', 'reverse_time'])
def test_closed_ancestry_requires_private_complete_immutable_source(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(sources.lab, 'ROOT', tmp_path)
    p = tmp_path / 'evidence' / 'unit' / 'episode.json'
    p.parent.mkdir(parents=True)
    value = {'completed': True, 'failure': None, 'started_at': 1, 'finished_at': 2}
    if fault == 'incomplete': value['completed'] = False
    elif fault == 'failure': value['failure'] = 'unexpected native state'
    elif fault == 'unfinished': value.pop('finished_at')
    elif fault == 'reverse_time': value['finished_at'] = 0
    p.write_text(json.dumps(value))
    if fault == 'symlink':
        target = p.with_name('carried.json')
        p.rename(target)
        p.symlink_to(target)
    with pytest.raises(RuntimeError): sources.closed(p)

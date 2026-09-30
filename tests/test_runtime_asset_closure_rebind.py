"""Runtime asset closure rebind (the committed form of the coordinator's /tmp helper)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
import yaml

from tools.raid_program import runtime_asset_closure_rebind as rebinding
from tools.raid_program.runtime_asset_closure import _inventory

REAL = Path(__file__).resolve().parents[1]
ROUTES, GEAR = 'dataset/validation_scenarios', 'dataset/validation_gear_profiles'


def _dump(value) -> str:
    return json.dumps(value, indent=2) + '\n'


def _entry(root: Path, path: str, mode: str = '0644') -> dict:
    data = (root / path).read_bytes()
    return {'path': path, 'type': 'file', 'mode': mode, 'size_bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()}


def _lock(root: Path, outputs: dict[str, str]) -> None:
    """dvc.lock outs for the two stages; md5 derived from the files so a content change moves it."""
    stages = {}
    for stage, output in outputs.items():
        files = sorted((root / output).iterdir())
        blob = b''.join(path.read_bytes() for path in files)
        stages[stage] = {'outs': [{'path': output, 'hash': 'md5', 'md5': hashlib.md5(blob).hexdigest() + '.dir',
                                   'size': len(blob), 'nfiles': len(files)}]}
    (root / 'dvc.lock').write_text(yaml.safe_dump({'schema': '2.0', 'stages': stages}))


@pytest.fixture
def closure(tmp_path):
    root = tmp_path
    for folder, names in ((ROUTES, ('manifest.json', 'validation_routes.jsonl')), (GEAR, ('profiles.json',))):
        (root / folder).mkdir(parents=True)
        for name in names:
            path = root / folder / name
            path.write_text(f'{{"payload": "{name}"}}\n')
            path.chmod(0o644)
    _lock(root, {'validation_scenarios': ROUTES, 'validation_gear': GEAR})
    lock = yaml.safe_load((root / 'dvc.lock').read_text())

    def asset_class(class_id, folder):
        files = [_entry(root, f'{folder}/{path.name}') for path in sorted((root / folder).iterdir())]
        return {'id': class_id, 'root': 'source-checkout', 'rule': 'complete-directory', 'path': folder,
                'expected_inventory': {key: _inventory(files)[key] for key in rebinding.INVENTORY_KEYS},
                'expected_files': files}

    def provenance(class_id, stage, folder):
        out = lock['stages'][stage]['outs'][0]
        return {'class_id': class_id, 'stage': stage, 'output_path': folder, 'md5': out['md5'], 'size': out['size'],
                'nfiles': out['nfiles']}
    manifest = {'schema': 'cata_runtime_asset_closure_manifest_v2',
                'dvc_provenance': [provenance('validation_routes', 'validation_scenarios', ROUTES),
                                   provenance('validation_gear_profiles', 'validation_gear', GEAR)],
                'asset_classes': [{'id': 'native', 'rule': 'exact-file', 'expected_files': []},
                                  asset_class('validation_routes', ROUTES), asset_class('validation_gear_profiles', GEAR)]}
    (root / rebinding.CLOSURE).parent.mkdir(parents=True, exist_ok=True)
    (root / rebinding.CLOSURE).write_text(_dump(manifest))
    sha = hashlib.sha256((root / rebinding.CLOSURE).read_bytes()).hexdigest()
    (root / rebinding.INPUT).write_text(_dump({'schema': 'input', 'asset_class_source': {
        'path': rebinding.CLOSURE.as_posix(), 'sha256': sha, 'exclude_class_ids': ['atomic_bundle']}}))
    return root


def _texts(root: Path) -> tuple[str, str]:
    return (root / rebinding.CLOSURE).read_text(), (root / rebinding.INPUT).read_text()


def test_a_current_closure_is_bound_and_never_rewritten(closure):
    before = _texts(closure)
    result = rebinding.rebind(closure)
    assert result['bound'] and not result['written'] and result['files'] == [] and _texts(closure) == before


def test_a_reproduced_payload_is_rebound_and_the_input_pointer_follows(closure):
    (closure / ROUTES / 'validation_routes.jsonl').write_text('{"payload": "reproduced routes, longer"}\n')
    _lock(closure, {'validation_scenarios': ROUTES, 'validation_gear': GEAR})
    before = _texts(closure)
    check = rebinding.rebind(closure, write=False)
    assert not check['bound'] and _texts(closure) == before, 'write=False reports without writing'
    fields = {change['field'] for change in check['changes']}
    assert {'dvc_provenance[validation_routes].md5', f'{ROUTES}/validation_routes.jsonl.sha256',
            'validation_routes.expected_inventory.inventory_sha256', 'asset_class_source.sha256'} <= fields
    assert not any(field.startswith('dvc_provenance[validation_gear_profiles]') for field in fields)
    written = rebinding.rebind(closure)
    assert written['written'] and written['files'] == [rebinding.CLOSURE.as_posix(), rebinding.INPUT.as_posix()]
    pointer = json.loads((closure / rebinding.INPUT).read_text())['asset_class_source']['sha256']
    assert pointer == hashlib.sha256((closure / rebinding.CLOSURE).read_bytes()).hexdigest() == written['closure_sha256']
    assert rebinding.rebind(closure)['bound'], 'rebinding is idempotent'


def test_gear_profiles_are_rebound_too_and_files_can_be_added_or_removed(closure):
    (closure / GEAR / 'report.json').write_text('{"new": true}\n')
    (closure / GEAR / 'report.json').chmod(0o644)
    (closure / ROUTES / 'manifest.json').unlink()
    _lock(closure, {'validation_scenarios': ROUTES, 'validation_gear': GEAR})
    result = rebinding.rebind(closure)
    fields = [change['field'] for change in result['changes']]
    assert f'validation_gear_profiles.expected_files: added {GEAR}/report.json' in fields
    assert f'validation_routes.expected_files: removed {ROUTES}/manifest.json' in fields
    manifest = json.loads((closure / rebinding.CLOSURE).read_text())
    classes = {row['id']: row for row in manifest['asset_classes']}
    assert [row['path'] for row in classes['validation_gear_profiles']['expected_files']] == [
        f'{GEAR}/profiles.json', f'{GEAR}/report.json']
    assert [row['path'] for row in classes['validation_routes']['expected_files']] == [f'{ROUTES}/validation_routes.jsonl']
    assert classes['validation_gear_profiles']['expected_inventory']['file_count'] == 2
    assert rebinding.rebind(closure)['bound']


def test_mode_mismatch_needs_a_chmod_unless_modes_are_ignored(closure):
    (closure / ROUTES / 'manifest.json').chmod(0o664)
    with pytest.raises(rebinding.RebindError, match='chmod it first'):
        rebinding.rebind(closure)
    assert rebinding.rebind(closure, write=False, check_modes=False)['bound']


def test_a_file_that_does_not_round_trip_is_never_rewritten(closure):
    path = closure / rebinding.CLOSURE
    path.write_text(json.dumps(json.loads(path.read_text())))  # compact JSON: not the indent=2 layout
    with pytest.raises(rebinding.RebindError, match='round-trip'):
        rebinding.rebind(closure)


def test_cli_check_exits_nonzero_when_stale(closure, capsys):
    assert rebinding.main(['--root', str(closure), '--check']) == 0
    assert json.loads(capsys.readouterr().out)['bound'] is True
    (closure / GEAR / 'profiles.json').write_text('{"payload": "changed"}\n')
    assert rebinding.main(['--root', str(closure), '--check']) == 1
    assert json.loads(capsys.readouterr().out)['bound'] is False


@pytest.mark.skipif(not (REAL / ROUTES).is_dir() or not (REAL / GEAR).is_dir(), reason='DVC payloads not checked out')
def test_the_committed_closure_matches_the_checked_out_payloads():
    """The port reproduces the committed closure byte for byte (read-only; modes are the refresh step's job)."""
    result = rebinding.rebind(REAL, write=False, check_modes=False)
    assert result['bound'], result['changes'][:5]

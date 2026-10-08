"""Latest excluded UI172 authority remains portable and small during live input."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.client_compatibility import bag_swap_fresh_sources as f
from tools.client_compatibility import bag_swap_failed_evidence as p
from tools.client_compatibility import bag_swap_failed_sources as failed
from tools.client_compatibility import review_bag_swap_failed_checkpoint as reviewer
from tools.client_compatibility.world.tests.test_bag_swap_failed_publication import (
    fixture as parent_fixture, refresh, archive, encoded)


def _rebase(value, before, after):
    if type(value) is dict:
        for key, child in value.items():
            if type(child) is str and child.startswith(str(before) + '/'):
                value[key] = str(after) + child[len(str(before)):]
            else:
                _rebase(child, before, after)
    elif type(value) is list:
        for child in value:
            _rebase(child, before, after)


def fixture(tmp_path, monkeypatch):
    """Return store, strict latest bundle, authority-ready refs, and fresh map.

    Only private test pins adapt the synthetic serialized authority. No runtime
    receipt or environment variable can select an alternative admitted report.
    """
    store, pause = parent_fixture(tmp_path, monkeypatch)
    from tools.client_compatibility import item_actionbar_evidence as old_evidence
    previous_root, root = store.root, old_evidence.lab.ROOT
    store.root = root
    for member, value in store.data.items():
        if member.startswith('evidence/unit/'):
            _rebase(value, previous_root, root)
    old_cache = next(v for v in store.data.values() if type(v) is dict and v.get('schema') == f.original.CACHE_SCHEMA)
    ready = store.data[str(Path(pause['original_preparation_source']['path']).relative_to(root))]
    current_repo = failed._repo(ready)
    for member, value in store.data.items():
        if member.startswith('evidence/unit/'):
            _rebase(value, current_repo, old_evidence.lab.REPO)
    ready['predecessor'] = deepcopy(old_cache['refs'])
    for member, value in store.data.items():
        if member.startswith('evidence/unit/') and type(value) is dict and 'predecessor' in value:
            value['predecessor'] = deepcopy(old_cache['refs'])
            if 'primary_stop_source' in value:
                value['primary_stop_source'] = deepcopy(old_cache['refs']['primary_stop'])
    refresh(store)
    expected = deepcopy(failed._HISTORICAL_SOURCES)
    _rebase(expected, previous_root, root)
    for ref in expected.values():
        ref['sha256'] = store.digests[str(Path(ref['path']).relative_to(root))]
    monkeypatch.setattr(failed, '_HISTORICAL_SOURCES', expected)
    closure_ref = {'path': str(root / 'evidence/unit/closed/episode.json'),
        'sha256': store.digests['evidence/unit/closed/episode.json']}
    monkeypatch.setattr(p, 'ROOT', root)
    monkeypatch.setattr(p, '_CLOSURE_SOURCE', closure_ref)
    monkeypatch.setattr(f, 'ROOT', root)
    raw, cp, prefix = archive(store.files, 'evidence/unit/')
    cp.update(file=f.POINTER.removesuffix('.dvc'), cloud_verified=True)
    data, digests, tracking, _ = reviewer.inspect_archive(io.BytesIO(raw), cp, prefix)
    proof = p.proof(data, digests, tracking)
    cp_ref = {'path': str(root / 'evidence/unit/checkpoint_receipt.json'),
        'sha256': hashlib.sha256(encoded(cp)).hexdigest()}
    pointer_raw = ('outs:\n- md5: ' + hashlib.md5(raw).hexdigest() + '\n  size: ' + str(len(raw)) +
        '\n  hash: md5\n  path: ' + Path(cp['file']).name + '\n').encode()
    pointer = {'source': {'path': str(tmp_path / 'repo' / f.POINTER),
        'sha256': hashlib.sha256(pointer_raw).hexdigest()}, 'pointer': f.POINTER,
        'oid': hashlib.md5(raw).hexdigest(), 'bytes': len(raw)}
    remote = {'schema': 'client442_bag_swap_failed_remote_review_v1', 'reviewed_at': pause['finished_at'] + 100,
        'checkpoint_source': cp_ref, 'pointer': f.POINTER, 'pointer_sha256': pointer['source']['sha256'],
        'object_md5': pointer['oid'], 'archive_sha256': cp['sha256'], 'bytes': len(raw),
        'actual_remote_verified': True, 'complete_manifest_verified': True, 'complete_json_png_jsonl_verified': True,
        'local_archive_created': False, 'qualification_added': False, 'operations_admitted': 0,
        'json_members': len(data), 'png_members': sum(name.endswith('.png') for name in digests),
        'journal_members': len(tracking['raw_journals']), 'proof': proof}
    remote_ref = {'path': str(root / 'evidence/unit_remote.json'), 'sha256': hashlib.sha256(encoded(remote)).hexdigest()}
    monkeypatch.setattr(f, '_ACCEPTED_REMOTE_SOURCE', remote_ref)
    refs = {'closure': closure_ref, 'remote': remote_ref, 'checkpoint': cp_ref,
        'primary_stop': old_cache['refs']['primary_stop']}
    values = {'closure': data['evidence/unit/closed/episode.json'], 'remote': remote, 'checkpoint': cp,
        'primary_stop': old_cache['values']['primary_stop'], 'dvc_pointer': pointer,
        'pointer_raw_hex': pointer_raw.hex()}
    graph = {'data': data, 'digests': digests, 'journals': tracking['raw_journals']}
    old = f.validate_bundle(values, refs, graph)
    launch = root / 'evidence/fresh/launch'
    launch.mkdir(parents=True)
    full_ref = f.write_cache(launch, old)
    compact_ref = f.write_runtime(launch, old, full_ref)
    store.data = dict(data)
    store.digests = dict(digests)
    store.raw_journals = dict(graph['journals'])
    for ref in (full_ref, compact_ref):
        member = str(Path(ref['path']).relative_to(root))
        store.data[member] = json.loads(Path(ref['path']).read_text())
        store.files[member] = Path(ref['path']).read_bytes()
        store.digests[member] = ref['sha256']
    members = []
    for name in f.required_members(old):
        row = next(row for row in cp['file_manifest'] if row['path'] == name)
        raw_member = encoded(data[name]) if name == 'tracking/checkpoint.json' else store.files[name]
        # Archived metadata is generated by archive(), not the input source map.
        assert hashlib.sha256(raw_member).hexdigest() == row['sha256']
        copy = 'evidence/fresh/predecessor/' + row['sha256'] + Path(name).suffix
        store.files[copy] = raw_member
        store.digests[copy] = row['sha256']
        if name.endswith('.json'): store.data[copy] = deepcopy(data[name])
        elif name.endswith('.jsonl'): store.raw_journals[copy] = deepcopy(graph['journals'][name])
        members.append({'original_path': str(root / name), 'original_member': name, 'sha256': row['sha256'],
            'bytes': row['bytes'], 'copy_member': copy})
    authorities = []
    for role in ('remote', 'checkpoint'):
        source, value = refs[role], values[role]
        copy = 'evidence/fresh/predecessor/' + source['sha256'] + '.json'
        raw_member = encoded(value)
        store.files[copy], store.data[copy], store.digests[copy] = raw_member, deepcopy(value), source['sha256']
        authorities.append({'role': role, 'original_path': source['path'], 'sha256': source['sha256'],
            'bytes': len(raw_member), 'copy_member': copy})
    mapping = {'schema': f.ANCESTRY_SCHEMA, 'authority_source': full_ref, 'archive': old['archive'],
        'dvc_pointer': pointer, 'pointer_raw_hex': pointer_raw.hex(), 'members': members,
        'authorities': authorities, 'actual_remote_verified': True, 'compressed_md5': pointer['oid'],
        'local_archive_created': False}
    map_member = 'evidence/fresh/predecessor_ui172.json'
    store.data[map_member] = mapping
    store.files[map_member] = encoded(mapping)
    store.digests[map_member] = hashlib.sha256(store.files[map_member]).hexdigest()
    authority_ready = {'authority_source': full_ref, 'runtime_authority_source': compact_ref, 'predecessor': refs}
    store.mock_archive = raw
    return store, old, authority_ready, mapping


def test_latest_full_and_compact_caches_use_actual_excluded_baseline_and_both_ancestor_epochs(tmp_path, monkeypatch):
    store, old, ready, mapping = fixture(tmp_path, monkeypatch)
    assert f.validate_carry(store, ready)['remote_proof'] == old['remote_proof']
    compact = f.cached_runtime(ready['runtime_authority_source']['path'], ready['authority_source'])
    assert compact['snapshot'] == old['closure']['after']
    assert compact['closure']['exact_precision']['row']['exact_rest_bonus'] == 53.438228607177734
    assert compact['snapshot']['2']['native']['logout_time'] == 1791422949
    assert compact['predecessor']['closure'] != compact['closure']['predecessor']['closure']
    assert compact['predecessor']['primary_stop'] == compact['closure']['predecessor']['primary_stop']
    assert Path(ready['runtime_authority_source']['path']).stat().st_size <= f.MAX_RUNTIME_BYTES
    assert any(row['original_member'].endswith('.jsonl') for row in mapping['members'])
    assert all(row['original_member'] in old['graph']['digests'] for row in mapping['members'])


def test_compact_live_reader_never_loads_or_replays_full_graph(tmp_path, monkeypatch):
    _, old, ready, _ = fixture(tmp_path, monkeypatch)
    full_path = Path(ready['authority_source']['path'])
    original_load, original_open = json.load, Path.open
    def no_full_load(handle, *args, **kwargs):
        assert Path(handle.name) != full_path
        return original_load(handle, *args, **kwargs)
    def bounded_full_open(path, *args, **kwargs):
        if path == full_path:
            assert args[0] == 'rb'
        return original_open(path, *args, **kwargs)
    def forbidden(*args, **kwargs): raise AssertionError('live full graph replay')
    monkeypatch.setattr(json, 'load', no_full_load)
    monkeypatch.setattr(Path, 'open', bounded_full_open)
    monkeypatch.setattr(f, 'cached_bundle', forbidden)
    monkeypatch.setattr(f, 'validate_bundle', forbidden)
    monkeypatch.setattr(p, 'proof', forbidden)
    assert f.cached_runtime(ready['runtime_authority_source']['path'], ready['authority_source'])['snapshot'] == old['snapshot']


def test_mocked_full_remote_stream_and_required_raw_carry_writer(tmp_path, monkeypatch):
    store, old, ready, _ = fixture(tmp_path, monkeypatch)
    from tools.client_compatibility import review_hunter_learn_checkpoint as remote
    calls = []
    def stream(request, **kwargs):
        calls.append(request)
        return io.BytesIO(store.mock_archive)
    monkeypatch.setattr(remote, 'remote_options', lambda repo: {})
    monkeypatch.setattr(remote, 'remote_request', lambda options, oid: oid)
    monkeypatch.setattr(f, 'urlopen', stream)
    for role in ('closure', 'remote', 'checkpoint'):
        path = Path(old['predecessor'][role]['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(encoded(old['values'][role]))
    pointer = Path(old['dvc_pointer']['source']['path'])
    pointer.parent.mkdir(parents=True)
    pointer.write_bytes(bytes.fromhex(old['pointer_raw_hex']))
    streamed = f.source_bundle(*(old['predecessor'][role]['path'] for role in ('closure', 'remote', 'checkpoint')),
        repo=tmp_path / 'repo')
    assert streamed['remote_proof'] == old['remote_proof']
    outer = store.root / 'evidence/new_carry'
    outer.mkdir()
    mapping = f.carry_authority(outer, ready['authority_source'], admitted=streamed, repo=tmp_path / 'repo')
    assert calls == [old['dvc_pointer']['oid']] * 2
    assert {r['original_member'] for r in mapping['members']} == set(f.required_members(old))
    assert len(mapping['members']) < len(old['graph']['digests'])
    assert not list(outer.rglob('*.tar*'))
    for member in [m for m, value in store.data.items() if type(value) is dict and value.get('schema') == f.ANCESTRY_SCHEMA]:
        del store.data[member]
    for path in outer.rglob('*'):
        if not path.is_file(): continue
        member, raw = str(path.relative_to(store.root)), path.read_bytes()
        store.digests[member] = hashlib.sha256(raw).hexdigest()
        if path.suffix == '.json': store.data[member] = json.loads(raw)
        elif path.suffix == '.jsonl': store.raw_journals[member] = [json.loads(row) for row in raw.splitlines()]
    assert f.validate_carry(store, ready)['snapshot'] == old['snapshot']


def test_full_cache_rejects_changed_core_commitment_before_portable_admission(tmp_path, monkeypatch):
    _, old, _, _ = fixture(tmp_path, monkeypatch)
    cache = f.cache_value(old)
    cache['core_sha256'] = '0' * 64
    with pytest.raises(RuntimeError, match='core commitment'):
        f.validate_cache(cache)


def test_writers_cannot_mint_authority_from_coedited_but_unproved_core(tmp_path, monkeypatch):
    _, old, ready, _ = fixture(tmp_path, monkeypatch)
    bad = deepcopy(old)
    bad['closure'], bad['values'] = deepcopy(old['closure']), deepcopy(old['values'])
    # Co-edit every runtime-visible copy while leaving the verified raw graph
    # unchanged. This passes structural compact checks but has no source basis.
    for c in (bad['closure'], bad['values']['closure']):
        for snapshot in (c['before'], c['after'], c['all_offline_snapshot'],
                c['exact_precision']['before'], c['exact_precision']['after']):
            snapshot['2']['native']['totaltime'] += 1
    bad['snapshot'] = deepcopy(bad['closure']['after'])
    f._runtime_core({key: bad[key] for key in f.CORE_FIELDS}, f.ROOT)
    destination = f.ROOT / 'evidence/unproved'
    destination.mkdir()
    with pytest.raises(RuntimeError): f.write_cache(destination, bad)
    with pytest.raises(RuntimeError): f.write_runtime(destination, bad, ready['authority_source'])
    assert list(destination.iterdir()) == []


@pytest.mark.parametrize('fault', ['full_changed', 'compact_changed', 'wrong_schema', 'wrong_source', 'oversize',
    'coedited_core', 'coedited_checkpoint_ref', 'coedited_full_ref'])
def test_compact_runtime_refuses_changed_bytes_or_wrong_identity(tmp_path, monkeypatch, fault):
    _, _, ready, _ = fixture(tmp_path, monkeypatch)
    path = Path(ready['runtime_authority_source']['path'])
    if fault == 'full_changed':
        with Path(ready['authority_source']['path']).open('ab') as handle: handle.write(b' ')
    elif fault == 'oversize': path.write_bytes(b' ' * (f.MAX_RUNTIME_BYTES + 1))
    else:
        value = json.loads(path.read_text())
        if fault == 'compact_changed': value['core']['snapshot']['2']['native']['rest_bonus'] += 1
        elif fault == 'coedited_core':
            core, c = value['core'], value['core']['closure']
            for snapshot in (core['snapshot'], c['before'], c['after'], c['all_offline_snapshot'],
                    c['exact_precision']['before'], c['exact_precision']['after']):
                snapshot['2']['native']['totaltime'] += 1
            f._runtime_core(core, f.ROOT)
        elif fault == 'coedited_checkpoint_ref':
            value['core']['predecessor']['checkpoint']['sha256'] = '0' * 64
            f._runtime_core(value['core'], f.ROOT)
        elif fault == 'coedited_full_ref':
            ready['authority_source'] = deepcopy(ready['authority_source'])
            ready['authority_source']['sha256'] = value['authority_source']['sha256'] = '0' * 64
        elif fault == 'wrong_schema': value['schema'] = f.original.RUNTIME_SCHEMA
        else: value['authority_source']['sha256'] = '0' * 64
        path.write_bytes(encoded(value))
    with pytest.raises(RuntimeError): f.cached_runtime(path, ready['authority_source'])


@pytest.mark.parametrize('fault', ['missing_member', 'wrong_digest', 'changed_json', 'truncated_journal', 'wrong_predecessor'])
def test_portable_fresh_carry_rebinds_raw_parent_bytes_and_complete_journals(tmp_path, monkeypatch, fault):
    store, _, ready, mapping = fixture(tmp_path, monkeypatch)
    if fault == 'missing_member': mapping['members'].pop()
    elif fault == 'wrong_digest': store.digests[mapping['members'][0]['copy_member']] = '0' * 64
    elif fault == 'changed_json':
        row = next(r for r in mapping['members'] if r['original_member'].endswith('.json'))
        store.data[row['copy_member']] = {'changed': True}
    elif fault == 'truncated_journal':
        row = next(r for r in mapping['members'] if r['original_member'] == 'tracking/events.jsonl')
        store.raw_journals[row['copy_member']] = store.raw_journals[row['copy_member']][1:]
    else: ready['predecessor'] = deepcopy(ready['predecessor']); ready['predecessor']['remote']['sha256'] = '0' * 64
    with pytest.raises(RuntimeError): f.validate_carry(store, ready)


def test_pure_import_does_not_load_ui_sql_or_protobuf():
    code = """
import sys
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.startswith(('pymysql','google.protobuf','PIL','tools.client_compatibility.interaction_')):
   raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
from tools.client_compatibility import bag_swap_fresh_sources
"""
    subprocess.run([sys.executable, '-B', '-c', code], check=True, capture_output=True, cwd=Path(__file__).resolve().parents[4])

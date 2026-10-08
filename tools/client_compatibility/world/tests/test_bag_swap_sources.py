"""Full archived UI171 proof, actual pointer bytes and immutable cache admission."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.client_compatibility import bag_swap_sources as s
from tools.client_compatibility import item_actionbar_evidence as e
from tools.client_compatibility import review_item_actionbar_checkpoint as reviewer
from tools.client_compatibility.world.tests.test_item_actionbar_evidence import (
    fixture as episode_fixture, proof_closure_fixture, archive_fixture)


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return path


def fixture(tmp_path, monkeypatch, *, transition=False, extra=None, journal_edges=False):
    make = proof_closure_fixture if transition else episode_fixture
    batch, paths, values, packets, events = make(tmp_path, monkeypatch)
    if journal_edges:
        # Both records are outside the semantic UI171 window, but belong to its
        # actual complete archive journals and must survive a later carry.
        packets = [{'session': 'scout', 'time': 1079, 'name': 'CMSG_CAST_SPELL', 'body': '00'}, *packets,
            {'session': 'scout', 'time': 1127, 'name': 'CMSG_CAST_SPELL', 'body': '01'}]
        events = [{'session': 'scout', 'time': 1079, 'event': 'prefix_fixture'}, *events,
            {'session': 'scout', 'time': 1127, 'event': 'suffix_fixture'}]
    for kind, rows in (('packets', packets), ('events', events)):
        path = e.lab.ROOT / 'evidence/fixture_original_journals' / (kind + '.jsonl')
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b''.join((json.dumps(row) + '\n').encode() for row in rows))
        paths['raw_' + kind] = path
    raw, checkpoint = archive_fixture(batch, packets, events, extra)
    checkpoint.update(file=s.POINTER.removesuffix('.dvc'), cloud_verified=True)
    prefix = str(batch.relative_to(e.lab.ROOT)) + '/'
    data, digests, tracking, _ = reviewer.inspect_archive(io.BytesIO(raw), checkpoint, prefix)
    proof = e.proof(data, digests, tracking)
    remote = {'schema': 'client442_item_actionbar_remote_review_v1', 'reviewed_at': 1200,
        'pointer': s.POINTER, 'archive_sha256': checkpoint['sha256'], 'bytes': len(raw),
        'actual_remote_verified': True, 'complete_json_png_verified': True,
        'json_members': len(data), 'png_members': len(digests) - len(data),
        'local_archive_created': False, 'qualification_added': False, 'proof': proof}
    paths['checkpoint'] = write(batch / 'checkpoint_receipt.json', checkpoint)
    paths['remote'] = write(e.lab.ROOT / 'evidence/ui171_remote_review.json', remote)
    pointer_path = e.lab.REPO / s.POINTER
    pointer_path.parent.mkdir(parents=True, exist_ok=True)
    oid = hashlib.md5(raw).hexdigest()
    pointer_path.write_text('outs:\n- md5: ' + oid + '\n  size: ' + str(len(raw)) +
        '\n  hash: md5\n  path: ' + Path(checkpoint['file']).name + '\n')
    config = e.lab.REPO / '.dvc/config'
    config.parent.mkdir(parents=True)
    config.write_text('[core]\nremote = test\n[remote "test"]\nurl = https://example.invalid/objects\n')
    fetches = []

    def fetch(request, timeout):
        fetches.append((request.full_url, timeout))
        return io.BytesIO(raw)

    monkeypatch.setattr(s, 'urlopen', fetch)
    return batch, paths, values, checkpoint, remote, fetches


def admit(paths):
    return s.source_bundle(paths['final'], paths['remote'], paths['checkpoint'])


def test_admits_actual_caller_archive_then_cache_needs_no_network_or_original_predecessors(tmp_path, monkeypatch):
    _, paths, _, checkpoint, _, fetches = fixture(tmp_path, monkeypatch, transition=True)
    before = {role: paths[role].read_bytes() for role in ('final', 'remote', 'checkpoint')}
    result = admit(paths)
    assert len(fetches) == 1 and fetches[0][1] == 60
    assert result['archive']['sha256'] == checkpoint['sha256']
    assert result['snapshot'] == result['closure']['after']
    assert result['remote_proof']['runtime_code_commit'] == 'c' * 40
    assert result['remote_proof']['proof_code_commit'] == 'f' * 40
    assert result['remote_proof']['both_owned_clients_stopped'] is True
    assert result['graph']['tracking']['members'] == sorted(e.TRACKING_MEMBERS)
    assert result['predecessor']['primary_stop'] == result['closure']['predecessor']['primary_stop']
    payload = {'schema': s.CACHE_SCHEMA, 'values': result['values'],
        'refs': result['predecessor'], 'graph': result['graph']}
    cache = write(e.lab.ROOT / 'evidence/bags_swap_authority.json', payload)
    for ref in result['closure']['predecessor'].values():
        Path(ref['path']).unlink()
    monkeypatch.setattr(s, 'urlopen', lambda *_args, **_kwargs: pytest.fail('cache must never fetch the remote'))
    assert s.cached_bundle(cache) == result
    assert s.validate_bundle(result['values'], result['predecessor'], result['graph']) == result
    assert {role: paths[role].read_bytes() for role in before} == before


def test_first_stream_binds_full_raw_journal_bytes_including_semantically_excluded_prefix_and_suffix(tmp_path, monkeypatch):
    _, paths, _, _, _, _ = fixture(tmp_path, monkeypatch, journal_edges=True)
    result = admit(paths)
    assert result['journal_manifest'] == result['graph']['journal_manifest']
    for member, kind in zip(e.TRACKING_MEMBERS, ('packets', 'events')):
        raw = paths['raw_' + kind].read_bytes()
        assert result['journal_manifest'][member] == {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        semantic = result['graph']['tracking'][kind]
        assert all(1080 <= row['time'] <= 1126 for row in semantic)
        filtered_bytes = b''.join((json.dumps(row) + '\n').encode() for row in semantic)
        assert hashlib.sha256(filtered_bytes).hexdigest() != result['journal_manifest'][member]['sha256']


@pytest.mark.parametrize('fault', ['legacy_cache', 'missing_member', 'bad_digest', 'boolean_bytes', 'zero_bytes'])
def test_cache_requires_both_exact_typed_first_stream_raw_journal_identities(tmp_path, monkeypatch, fault):
    _, paths, _, _, _, _ = fixture(tmp_path, monkeypatch)
    bundle = admit(paths)
    graph = bundle['graph']
    if fault == 'legacy_cache': graph.pop('journal_manifest')
    elif fault == 'missing_member': graph['journal_manifest'].pop(e.TRACKING_MEMBERS[0])
    elif fault == 'bad_digest': graph['journal_manifest'][e.TRACKING_MEMBERS[0]]['sha256'] = 'invented'
    elif fault == 'boolean_bytes': graph['journal_manifest'][e.TRACKING_MEMBERS[0]]['bytes'] = True
    else: graph['journal_manifest'][e.TRACKING_MEMBERS[0]]['bytes'] = 0
    with pytest.raises(RuntimeError):
        s.validate_bundle(bundle['values'], bundle['predecessor'], graph)


@pytest.mark.parametrize('fault', ['not_reviewed', 'not_complete', 'qualification', 'local_archive',
    'wrong_pointer', 'wrong_size', 'wrong_sha', 'boolean_count', 'false_offline', 'missing_shutdown',
    'early_review', 'wrong_json_count', 'wrong_png_count'])
def test_actual_remote_receipt_cannot_substitute_identity_or_typed_whole_proof(tmp_path, monkeypatch, fault):
    _, paths, _, _, remote, _ = fixture(tmp_path, monkeypatch)
    if fault == 'not_reviewed': remote['actual_remote_verified'] = False
    elif fault == 'not_complete': remote['complete_json_png_verified'] = False
    elif fault == 'qualification': remote['qualification_added'] = True
    elif fault == 'local_archive': remote['local_archive_created'] = True
    elif fault == 'wrong_pointer': remote['pointer'] = s.POINTER.replace('_171.', '_170.')
    elif fault == 'wrong_size': remote['bytes'] += 1
    elif fault == 'wrong_sha': remote['archive_sha256'] = 'a' * 64
    elif fault == 'boolean_count': remote['proof']['native_item_requests'] = True
    elif fault == 'false_offline': remote['proof']['all_six_offline'] = False
    elif fault == 'missing_shutdown': remote['proof'].pop('shutdown_checks')
    elif fault == 'early_review': remote['reviewed_at'] = 1125
    elif fault == 'wrong_json_count': remote['json_members'] += 1
    else: remote['png_members'] = True
    write(paths['remote'], remote)
    with pytest.raises(RuntimeError):
        admit(paths)


@pytest.mark.parametrize('fault', ['json', 'png', 'extra_json', 'journal', 'journal_counts',
    'packet_body', 'late_forbidden', 'primary_source', 'snapshot', 'pointer_raw', 'transition'])
def test_portable_full_graph_refuses_missing_or_changed_sources_journals_and_proof_transition(tmp_path, monkeypatch, fault):
    _, paths, _, _, _, _ = fixture(tmp_path, monkeypatch, transition=True)
    bundle = admit(paths)
    values, refs, graph = bundle['values'], bundle['predecessor'], bundle['graph']
    if fault == 'json': graph['data'].pop(next(iter(graph['data'])))
    elif fault == 'png': graph['digests'].pop(next(p for p in graph['digests'] if p.endswith('.png')))
    elif fault == 'extra_json': graph['data']['evidence/unreviewed.json'] = {}
    elif fault == 'journal': graph['tracking']['members'].pop()
    elif fault == 'journal_counts': graph['tracking']['journal_counts'][e.TRACKING_MEMBERS[0]]['rows'] += 1
    elif fault == 'packet_body':
        next(p for p in graph['tracking']['packets'] if p['name'] == 'CMSG_SET_ACTION_BUTTON')['body'] = '00'
    elif fault == 'late_forbidden':
        row = {'event': 'native_packet', 'session': 'scout', 'time': 1124,
            'direction': 'to_native', 'name': 'CMSG_CAST_SPELL', 'bytes': 1}
        graph['tracking']['events'].append(row)
        count = graph['tracking']['journal_counts'][e.TRACKING_MEMBERS[1]]
        count['rows'] += 1
        count['serialized_bytes'] += e.serialized_row_bytes(row)
    elif fault == 'primary_source': refs['primary_stop']['sha256'] = 'a' * 64
    elif fault == 'snapshot': values['closure']['after']['6']['pets'][0]['curhealth'] += 1
    elif fault == 'pointer_raw': values['pointer_raw_hex'] = '00'
    else:
        member = str(paths['final'].relative_to(e.lab.ROOT))
        graph['data'][member]['proof_code_transition']['read_only'] = False
        values['closure']['proof_code_transition']['read_only'] = False
    with pytest.raises(RuntimeError):
        s.validate_bundle(values, refs, graph)


@pytest.mark.parametrize('fault', ['checkpoint', 'pointer', 'closure', 'remote', 'symlink', 'object_md5'])
def test_admission_refuses_actual_authority_file_drift_or_wrong_remote_object_key(tmp_path, monkeypatch, fault):
    _, paths, _, checkpoint, _, _ = fixture(tmp_path, monkeypatch)
    if fault == 'checkpoint':
        checkpoint['file_manifest'].append(deepcopy(checkpoint['file_manifest'][0]))
        write(paths['checkpoint'], checkpoint)
    elif fault in ('pointer', 'object_md5'):
        path = e.lab.REPO / s.POINTER
        text = path.read_text()
        old = hashlib.md5(b'').hexdigest()  # A real but different object hash.
        if fault == 'pointer': text = 'outs: []\n'
        else: text = text.replace(text.split('md5: ')[1].splitlines()[0], old)
        path.write_text(text)
    elif fault == 'closure':
        value = json.loads(paths['final'].read_text())
        value['completed'] = False
        write(paths['final'], value)
    elif fault == 'remote':
        paths['remote'].unlink()
    else:
        target = paths['remote'].with_name('original_review.json')
        paths['remote'].rename(target)
        paths['remote'].symlink_to(target)
    with pytest.raises(RuntimeError):
        admit(paths)


def test_derived_cache_requires_exact_schema_and_source_closed_ready_requires_cache_reference(tmp_path, monkeypatch):
    _, paths, _, _, _, _ = fixture(tmp_path, monkeypatch)
    bundle = admit(paths)
    cache = write(e.lab.ROOT / 'evidence/bags_swap_authority.json', {'schema': s.CACHE_SCHEMA,
        'values': bundle['values'], 'refs': bundle['predecessor'], 'graph': bundle['graph']})
    ready = {'phase': 'bags_swap_scout_ready', 'completed': True, 'failure': None, 'started_at': 1201,
        'finished_at': 1202, 'actor': bundle['origin_actor'], 'all_offline_snapshot': bundle['snapshot'],
        'predecessor': bundle['predecessor'], 'authority_source': s.bound(cache)}
    assert s.prepared(ready) == ready
    ready.pop('authority_source')
    with pytest.raises(RuntimeError): s.prepared(ready)
    payload = json.loads(cache.read_text())
    payload['schema'] = 'pending_future_authority'
    write(cache, payload)
    with pytest.raises(RuntimeError, match='exact derived'):
        s.cached_bundle(cache)


def runtime_fixture(tmp_path, monkeypatch, *, large_full=False):
    _, paths, _, _, _, _ = fixture(tmp_path, monkeypatch, transition=True)
    old = admit(paths)
    full = e.lab.ROOT / 'evidence/bags_swap_full_authority.json'
    raw = (json.dumps({'schema': s.CACHE_SCHEMA, 'values': old['values'],
        'refs': old['predecessor'], 'graph': old['graph']}, separators=(',', ':')) + '\n').encode()
    if large_full:
        raw += b' ' * (3 * s.MAX_RUNTIME_BYTES)
    full.write_bytes(raw)
    full_ref = s.bound(full)
    compact = s.compact_authority(old, full_ref)
    path = e.lab.ROOT / 'evidence/runtime_authority.json'
    path.write_bytes((json.dumps(compact, separators=(',', ':')) + '\n').encode())
    return old, full, full_ref, compact, path


def test_compact_runtime_derives_exact_core_and_never_reads_or_replays_full_graph(tmp_path, monkeypatch):
    old, full, full_ref, compact, path = runtime_fixture(tmp_path, monkeypatch, large_full=True)
    assert set(compact) == {'schema', 'authority_source', 'core'} and compact['schema'] == s.RUNTIME_SCHEMA
    assert compact['core'] == {key: old[key] for key in s.CORE_FIELDS}
    assert path.stat().st_size <= s.MAX_RUNTIME_BYTES < full.stat().st_size
    calls, reads = [], []
    original_loads, original_open = json.loads, Path.open

    def bounded_json(raw, *args, **kwargs):
        assert len(raw) <= s.MAX_RUNTIME_BYTES, 'full graph JSON must never be parsed by cached_runtime'
        calls.append(len(raw))
        return original_loads(raw, *args, **kwargs)

    class FullCacheReader:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *_args): self.handle.close()
        def fileno(self): return self.handle.fileno()
        def read(self, size=-1):
            assert 0 < size <= s.HASH_CHUNK_BYTES, 'full cache reads must stay bounded'
            reads.append(size)
            return self.handle.read(size)

    def opened(source, *args, **kwargs):
        handle = original_open(source, *args, **kwargs)
        return FullCacheReader(handle) if source == full else handle

    monkeypatch.setattr(json, 'loads', bounded_json)
    monkeypatch.setattr(Path, 'open', opened)
    monkeypatch.setattr(Path, 'read_bytes', lambda *_args: pytest.fail('runtime cache must never allocate whole files'))
    monkeypatch.setattr(Path, 'read_text', lambda *_args, **_kwargs: pytest.fail('runtime cache must never read full text'))
    monkeypatch.setattr(s, 'cached_bundle', lambda *_args, **_kwargs: pytest.fail('full graph admission must not run'))
    monkeypatch.setattr(s, 'validate_bundle', lambda *_args, **_kwargs: pytest.fail('full graph validation must not run'))
    monkeypatch.setattr(e, 'proof', lambda *_args, **_kwargs: pytest.fail('full graph proof must not replay'))
    assert s.cached_runtime(path, full_ref) == compact['core']
    assert calls == [path.stat().st_size] and len(reads) > 3


def test_compact_derivation_is_portable_and_does_not_open_evicted_original_sources(tmp_path, monkeypatch):
    old, full, full_ref, compact, _ = runtime_fixture(tmp_path, monkeypatch)
    full.unlink()
    monkeypatch.setattr(Path, 'open', lambda *_args, **_kwargs: pytest.fail('pure compact derivation must not read source files'))
    assert s.compact_authority(old, full_ref) == compact


@pytest.mark.parametrize('fault', ['schema', 'extra_field', 'missing_core', 'wrong_full_ref', 'closure_failure',
    'snapshot', 'runtime', 'boolean_pid', 'bad_ticks', 'actor', 'shutdown', 'pointer', 'primary',
    'oversize', 'malformed_json', 'compact_symlink', 'fullcache_symlink', 'fullcache_changed'])
def test_runtime_cache_rejects_changed_compact_core_or_actual_fullcache_bytes(tmp_path, monkeypatch, fault):
    _, full, full_ref, compact, path = runtime_fixture(tmp_path, monkeypatch)
    core = compact['core']
    if fault == 'schema': compact['schema'] = 'future_unverified_runtime'
    elif fault == 'extra_field': compact['unverified'] = True
    elif fault == 'missing_core': core.pop('predecessor')
    elif fault == 'wrong_full_ref': compact['authority_source']['sha256'] = 'a' * 64
    elif fault == 'closure_failure': core['closure']['completed'] = False
    elif fault == 'snapshot':
        core['snapshot'] = deepcopy(core['snapshot'])
        core['snapshot']['6']['pets'][0]['curhealth'] += 1
    elif fault == 'runtime':
        core['runtime'] = deepcopy(core['runtime'])
        core['runtime']['client']['pid'] += 1
    elif fault == 'boolean_pid':
        core['runtime']['client']['pid'] = True
        core['closure']['runtime'] = deepcopy(core['runtime'])
    elif fault == 'bad_ticks':
        core['runtime']['client']['start_ticks'] = '02000'
        core['closure']['runtime'] = deepcopy(core['runtime'])
    elif fault == 'actor': core['origin_actor']['guid'] = 6
    elif fault == 'shutdown': core['closure']['shutdown_checks']['primary_still_stopped'] = 1
    elif fault == 'pointer': core['dvc_pointer']['bytes'] = True
    elif fault == 'primary':
        core['primary_stop_source'] = deepcopy(core['primary_stop_source'])
        core['primary_stop_source']['sha256'] = 'a' * 64
    elif fault == 'oversize': core['closure']['unexpected_payload'] = 'x' * s.MAX_RUNTIME_BYTES
    if fault not in ('malformed_json', 'compact_symlink', 'fullcache_symlink', 'fullcache_changed'):
        path.write_bytes((json.dumps(compact, separators=(',', ':')) + '\n').encode())
    elif fault == 'malformed_json': path.write_bytes(b'{')
    elif fault == 'compact_symlink':
        original = path.with_name('original_compact.json')
        path.rename(original)
        path.symlink_to(original)
    elif fault == 'fullcache_symlink':
        original = full.with_name('original_fullcache.json')
        full.rename(original)
        full.symlink_to(original)
    else: full.write_bytes(full.read_bytes() + b' ')
    with pytest.raises(RuntimeError):
        s.cached_runtime(path, full_ref)


def test_compact_builder_refuses_oversized_or_nonadmitted_bundle_and_wrong_reference_roles(tmp_path, monkeypatch):
    old, _, full_ref, _, _ = runtime_fixture(tmp_path, monkeypatch)
    bare = {key: old[key] for key in s.CORE_FIELDS}
    with pytest.raises(RuntimeError, match='already admitted'):
        s.compact_authority(bare, full_ref)
    old['predecessor'] = {**old['predecessor'], 'invented': deepcopy(old['predecessor']['closure'])}
    with pytest.raises(RuntimeError, match='reference roles'):
        s.compact_authority(old, full_ref)
    old['predecessor'].pop('invented')
    old['closure']['unexpected_payload'] = 'x' * s.MAX_RUNTIME_BYTES
    with pytest.raises(RuntimeError, match='one-MiB'):
        s.compact_authority(old, full_ref)


def test_import_never_loads_ui_sql_auth_protocol_or_pillow():
    code = """import importlib,sys
class Block:
 def find_spec(self,name,path=None,target=None):
  if name.startswith(('PIL','pymysql','google','Crypto','tools.second_client','tools.client_compatibility.auth','tools.client_compatibility.interaction_trial','tools.client_compatibility.world.control')): raise RuntimeError(name)
sys.meta_path.insert(0,Block())
importlib.import_module('tools.client_compatibility.bag_swap_sources')
print('pure bag-swap source import passed')
"""
    result = subprocess.run([sys.executable, '-B', '-c', code], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'pure bag-swap source import passed'

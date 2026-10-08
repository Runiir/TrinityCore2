"""A crash authority preserves the indexed parent and explicit service epochs."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path

import pytest

from tools.client_compatibility import bag_swap_offline_sources as source
from tools.client_compatibility import bag_swap_evidence as evidence
from tools.client_compatibility import interaction_bag_swap_continuation as continuation
from tools.client_compatibility.world.tests.test_bag_swap_offline_boundary import case
from tools.client_compatibility.world.tests.test_bag_swap_indexed_sources import core, ref
from tools.client_compatibility.world.tests.test_bag_swap_indexed_archive import carried, encoded, packed
from tools.client_compatibility import bag_swap_indexed_archive as archive


def authority(root):
    closed = case(root, recovered=True)[0]
    old = core(root)
    old['snapshot'] = deepcopy(closed['ready_baseline'])
    old['runtime'] = deepcopy(closed['previous_runtime'])
    old['origin_actor'] = deepcopy(closed['actor'])
    old['primary_stop_source'] = closed['sources']['primary_stop']
    old['predecessor']['primary_stop'] = old['primary_stop_source']
    return old, source._core(old, closed)


def test_new_authority_keeps_historical_client_separate_and_selects_v2(tmp_path):
    old, value = authority(tmp_path)
    compact = source.compact_authority(value, ref(tmp_path, 'evidence/next/resume/authority.json'), root=tmp_path)
    assert compact['core']['predecessor'] == old['predecessor']
    assert compact['core']['dvc_pointer'] == old['dvc_pointer']
    assert compact['core']['runtime']['client'] == value['closure']['previous_client']
    assert 'runtime' not in value['closure']
    assert set(value['closure']['current_services']) == {'worldserver', 'modern_world'}
    assert continuation.authority_sources(source.RUNTIME_SCHEMA) is source
    assert source.LOGIN_SYNC_SCHEMA == 'client442_bag_swap_login_sync_v2'


@pytest.mark.parametrize('fault', ['saved_change', 'current_client', 'qualification', 'wrong_parent_services'])
def test_compact_authority_cannot_relabel_a_live_client_or_unrelated_boundary(tmp_path, fault):
    old, value = authority(tmp_path)
    if fault == 'saved_change': value['snapshot']['3']['saved']['actions'] = [[0, 1, 0]]
    elif fault == 'current_client': value['closure']['current_services']['client'] = value['closure']['previous_client']
    elif fault == 'qualification': value['closure']['qualification_added'] = True
    else:
        old['runtime']['worldserver']['pid'] += 1
        with pytest.raises(RuntimeError, match='exact indexed predecessor'):
            source._core(old, value['closure'])
        return
    with pytest.raises(RuntimeError):
        source.compact_authority(value, ref(tmp_path, 'evidence/next/authority.json'), root=tmp_path)


def test_portable_crash_map_resolves_original_json_and_journal_without_original_files(tmp_path, monkeypatch):
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    original = ref(tmp_path, 'evidence/ui174/crash_after01/boundary.json')
    original['sha256'] = hashlib.sha256(b'closed').hexdigest()
    member = 'evidence/next/crash_sources/' + original['sha256'] + '.json'
    carry = {'schema': source.CARRY_SCHEMA, 'boundary_source': original,
        'indexed_carry_source': ref(tmp_path, 'evidence/next/predecessor_ui173.json'), 'authorities': [],
        'members': [{'original_path': original['path'], 'sha256': original['sha256'], 'bytes': 6,
            'copy_member': member, 'kind': 'json'}]}
    store = evidence.Sources({'evidence/next/crash_ancestry.json': carry, member: {'source': 'actual'}},
        {member: original['sha256']})
    assert store.get(original, False) == {'source': 'actual'}
    assert not __import__('pathlib').Path(original['path']).exists()
    broken = deepcopy(carry)
    broken['members'].append(deepcopy(broken['members'][0]))
    with pytest.raises(RuntimeError, match='duplicate original'):
        source.validate_manifest(broken, tmp_path)


def test_runtime_read_rejects_changed_source_descriptor_and_digest(tmp_path):
    _, value = authority(tmp_path)
    directory = tmp_path / 'evidence/next/resume'
    directory.mkdir(parents=True)
    descriptor = {'schema': source.CACHE_SCHEMA,
        'indexed_authority_source': ref(tmp_path, 'evidence/next/resume/indexed_authority.json'),
        'carry_source': ref(tmp_path, 'evidence/next/crash_ancestry.json'),
        'boundary_source': ref(tmp_path, 'evidence/ui174/crash_after01/boundary.json'),
        'core_sha256': hashlib.sha256(source._encode(value)).hexdigest()}
    full = directory / 'authority.json'
    full.write_bytes(source._encode(descriptor))
    full_ref = source.bound(full)
    runtime = directory / 'runtime_authority.json'
    runtime.write_bytes(source._encode(source.compact_authority(value, full_ref, root=tmp_path)))
    runtime_ref = source.bound(runtime)
    assert source.cached_runtime(runtime, full_ref, root=tmp_path, compact_ref=runtime_ref) == value
    runtime.write_text(json.dumps({'schema': source.RUNTIME_SCHEMA, 'core': value}) + '\n')
    with pytest.raises(RuntimeError):
        source.cached_runtime(runtime, full_ref, root=tmp_path, compact_ref=runtime_ref)


@pytest.fixture
def crash_carry(carried, monkeypatch):
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    directory = c['batch'] / 'crash_sources'
    directory.mkdir()
    historical = 'evidence/ui174/'
    values = {'scout_ready01/episode.json': ('json', encoded({
        'schema': 'client442_laya_interactions_v1', 'phase': 'bags_swap_scout_ready',
        'completed': True, 'failure': None,
        'authority_source': ref(c['root'], historical + 'resume/authority.json'),
        'runtime_authority_source': ref(c['root'], historical + 'resume/runtime_authority.json')})),
        'crash_after01/boundary.json': ('json', encoded({'completed': True, 'failure': None})),
        'crash_before01/client.blob': ('binary', b'{"historical_run_metadata":true}\n'),
        'crash_after01/events.jsonl': ('journal', encoded({'time': 3, 'event': 'crash'}))}
    rows, refs = [], {}
    suffixes = {'json': '.json', 'binary': '.bin', 'journal': '.jsonl'}
    for name, (kind, raw) in values.items():
        sha = hashlib.sha256(raw).hexdigest()
        target = directory / (sha + suffixes[kind]); target.write_bytes(raw)
        original = str(c['root'] / (historical + name))
        refs[name] = {'path': original, 'sha256': sha}
        rows.append({'original_path': original, 'sha256': sha, 'bytes': len(raw),
            'copy_member': str(target.relative_to(c['root'])), 'kind': kind})
    value = {'schema': source.CARRY_SCHEMA, 'members': rows, 'authorities': [],
        'boundary_source': refs['crash_after01/boundary.json'], 'indexed_carry_source': c['carry_ref']}
    path = c['batch'] / 'crash_ancestry.json'; path.write_bytes(encoded(value))
    c.update(crash=value, crash_path=path, crash_refs=refs)
    return c


def test_raw_local_carry_preserves_historical_ready_and_binary_types(crash_carry):
    c = crash_carry
    store = source.local_store(c['batch'], root=c['root'])
    ready = c['crash_refs']['scout_ready01/episode.json']
    assert not Path(ready['path']).exists()
    assert store.get(ready, False)['phase'] == 'bags_swap_scout_ready'
    assert store.get(ready, False)['authority_source']['path'].endswith('ui174/resume/authority.json')
    journal = c['crash_refs']['crash_after01/events.jsonl']
    assert source._journal(store, journal) == [{'time': 3, 'event': 'crash'}]
    binary = c['crash_refs']['crash_before01/client.blob']
    member = store.member(binary)
    assert member not in store.data and member not in store.raw_journals
    with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
        store.get(binary, False)
    with pytest.raises(RuntimeError):
        # The outer indexed store has no journal view for retained binary bytes.
        archive.local_sources(c['batch'], root=c['root']).journal(
            {'path': str(c['root'] / member), 'sha256': binary['sha256']})


def test_portable_raw_carry_uses_the_same_historical_role_boundary(crash_carry):
    c = crash_carry; prefix = str(c['batch'].relative_to(c['root'])) + '/'
    files = {str(p.relative_to(c['root'])): p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
    files.update({prefix + 'current/episode.json': encoded({'value': 'current'}),
        prefix + 'current/frame.png': b'\x89PNG\r\n\x1a\ncurrent',
        'tracking/packets.jsonl': encoded({'time': 4, 'packet': 'current'}),
        'tracking/events.jsonl': encoded({'time': 4, 'event': 'current'})})
    raw, cp, _ = packed(files)
    data, digests, tracking, _ = archive.inspect_archive(io.BytesIO(raw), cp, prefix)
    try:
        store = evidence.Sources(data, digests, paths=tracking['paths'])
        store.raw_journals = tracking['raw_journals']
        assert store.get(c['crash_refs']['scout_ready01/episode.json'], False)['phase'] == 'bags_swap_scout_ready'
        assert source._journal(store, c['crash_refs']['crash_after01/events.jsonl']) == [{'time': 3, 'event': 'crash'}]
        binary = c['crash_refs']['crash_before01/client.blob']
        assert store.member(binary) not in store.data
        with pytest.raises(RuntimeError, match='not an ordinary JSON view'): store.get(binary, False)
    finally:
        tracking['_spool'].cleanup()


@pytest.mark.parametrize('fault', ['sha', 'bytes', 'missing_copy', 'extra_copy', 'missing_map',
    'indexed_carry', 'current_original', 'renamed_copy', 'boundary_binary'])
def test_crash_map_cannot_hide_unbound_or_current_raw_sources(crash_carry, fault):
    c = crash_carry; value = deepcopy(c['crash'])
    row = value['members'][0]; path = c['root'] / row['copy_member']
    if fault == 'sha': row['sha256'] = 'a' * 64
    elif fault == 'bytes': row['bytes'] += 1
    elif fault == 'missing_copy': path.unlink()
    elif fault == 'extra_copy': (path.parent / ('a' * 64 + '.json')).write_bytes(b'{}\n')
    elif fault == 'missing_map': c['crash_path'].unlink()
    elif fault == 'indexed_carry': value['indexed_carry_source']['sha256'] = 'a' * 64
    elif fault == 'current_original': row['original_path'] = str(c['batch'] / 'scout_ready01/episode.json')
    elif fault == 'renamed_copy':
        renamed = path.with_name('renamed.json'); path.rename(renamed)
        row['copy_member'] = str(renamed.relative_to(c['root']))
    else:
        row = next(r for r in value['members'] if r['original_path'] == value['boundary_source']['path'])
        path = c['root'] / row['copy_member']; renamed = path.with_suffix('.bin'); path.rename(renamed)
        row.update(kind='binary', copy_member=str(renamed.relative_to(c['root'])))
    if fault != 'missing_map': c['crash_path'].write_bytes(encoded(value))
    with pytest.raises(RuntimeError): source.local_store(c['batch'], root=c['root'])


@pytest.mark.parametrize('fault', ['missing_role', 'wrong_sha', 'oversized_role'])
def test_historical_crash_copies_do_not_exempt_current_receipt_roles(crash_carry, fault):
    c = crash_carry
    descriptor = c['batch'] / 'descriptor.json'; descriptor.write_bytes(b'{}\n')
    runtime = c['batch'] / 'runtime.json'; runtime.write_bytes(b'{}\n')
    if fault == 'oversized_role': descriptor.write_bytes(b'{"padding":"' + b'x' * source.MAX_DESCRIPTOR_BYTES + b'"}\n')
    current = {'schema': 'client442_bag_swap_scout_resume_v1',
        'authority_source': source.bound(descriptor), 'runtime_authority_source': source.bound(runtime)}
    if fault == 'missing_role': del current['runtime_authority_source']
    elif fault == 'wrong_sha': current['authority_source']['sha256'] = 'a' * 64
    (c['batch'] / 'resume.json').write_bytes(encoded(current))
    with pytest.raises(RuntimeError): source.local_store(c['batch'], root=c['root'])


def test_current_offline_roles_bind_their_new_exact_sources_beside_historical_ready(crash_carry):
    c = crash_carry
    descriptor = c['batch'] / 'descriptor.json'
    descriptor.write_bytes(encoded({'schema': source.CACHE_SCHEMA, 'login_sync_schema': source.LOGIN_SYNC_SCHEMA}))
    runtime = c['batch'] / 'runtime.json'
    runtime.write_bytes(encoded({'schema': source.RUNTIME_SCHEMA, 'authority_source': source.bound(descriptor)}))
    refs = {'authority_source': source.bound(descriptor), 'runtime_authority_source': source.bound(runtime)}
    (c['batch'] / 'resume.json').write_bytes(encoded({'schema': 'client442_bag_swap_scout_resume_v1', **refs}))
    store = source.local_store(c['batch'], root=c['root'])
    assert store.member(refs['authority_source']) == str(descriptor.relative_to(c['root']))
    assert store.get(refs['authority_source'], False)['login_sync_schema'] == source.LOGIN_SYNC_SCHEMA
    assert store.get(refs['runtime_authority_source'], False)['authority_source'] == refs['authority_source']


@pytest.mark.parametrize('schema', [source.CACHE_SCHEMA, source.RUNTIME_SCHEMA])
@pytest.mark.parametrize('reader', ['local', 'portable'])
def test_offline_schema_caps_precede_document_decode_without_an_owner(crash_carry, monkeypatch, schema, reader):
    c = crash_carry
    forbidden = encoded({'schema': schema, 'padding': 'x' * source.MAX_DESCRIPTOR_BYTES})
    (c['batch'] / 'renamed_authority.json').write_bytes(forbidden)
    original = archive._json
    def guarded(raw):
        assert raw != forbidden, 'over-cap offline role reached the document decoder'
        return original(raw)
    monkeypatch.setattr(archive, '_json', guarded)
    with pytest.raises(RuntimeError, match='retained indexed JSON exceeds its exact raw byte bound before decode'):
        if reader == 'local': source.local_store(c['batch'], root=c['root'])
        else:
            prefix = str(c['batch'].relative_to(c['root'])) + '/'
            files = {str(p.relative_to(c['root'])): p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
            files.update({prefix + 'current/episode.json': b'{}\n', prefix + 'current.png': b'\x89PNG\r\n\x1a\nsmall',
                'tracking/packets.jsonl': encoded({'time': 4}), 'tracking/events.jsonl': encoded({'time': 4})})
            raw, cp, _ = packed(files)
            archive.inspect_archive(io.BytesIO(raw), cp, prefix)


@pytest.mark.parametrize('schema', [source.CACHE_SCHEMA, source.RUNTIME_SCHEMA])
def test_offline_schema_declaration_must_be_unambiguous(crash_carry, schema):
    c = crash_carry
    (c['batch'] / 'ambiguous.json').write_text('{"schema":' + json.dumps(schema) + ',"schema":"ordinary"}\n')
    with pytest.raises(RuntimeError, match='schema declaration must be unambiguous before decode'):
        source.local_store(c['batch'], root=c['root'])


@pytest.mark.parametrize('reader', ['local', 'portable'])
@pytest.mark.parametrize('owner', ['ready', 'resume'])
@pytest.mark.parametrize('fault', ['descriptor_current', 'runtime_current', 'both_current',
    'missing_role', 'untyped_role', 'duplicate_role'])
def test_rehashed_historical_receipt_cannot_exempt_current_or_ambiguous_roles(crash_carry, reader, owner, fault):
    c = crash_carry; row = c['crash']['members'][0]
    old_path = c['root'] / row['copy_member']
    value = json.loads(old_path.read_bytes())
    if owner == 'resume':
        value['schema'] = 'client442_bag_swap_scout_resume_v1'
        del value['phase']
    current = {'authority_source': ref(c['root'], str(c['batch'].relative_to(c['root'])) + '/resume/authority.json'),
        'runtime_authority_source': ref(c['root'], str(c['batch'].relative_to(c['root'])) + '/resume/runtime_authority.json')}
    if fault in ('descriptor_current', 'both_current'): value['authority_source'] = current['authority_source']
    if fault in ('runtime_current', 'both_current'): value['runtime_authority_source'] = current['runtime_authority_source']
    if fault == 'missing_role': del value['runtime_authority_source']
    elif fault == 'untyped_role': value['runtime_authority_source'] = 'historical'
    raw = encoded(value)
    if fault == 'duplicate_role':
        raw = raw.rstrip()[:-1] + b',"authority_source":' + encoded(current['authority_source']).strip() + b'}\n'
    sha = hashlib.sha256(raw).hexdigest()
    path = old_path.with_name(sha + '.json'); old_path.unlink(); path.write_bytes(raw)
    row.update(sha256=sha, bytes=len(raw), copy_member=str(path.relative_to(c['root'])))
    # Both the original-path declaration and all raw copy identities are valid.
    # Only the embedded role claim differs, reproducing the independent review.
    assert not Path(row['original_path']).is_relative_to(c['batch'])
    c['crash_path'].write_bytes(encoded(c['crash']))
    match = 'historical crash receipt cannot bind current-batch' if fault.endswith('current') else None
    with pytest.raises(RuntimeError, match=match):
        if reader == 'local': source.local_store(c['batch'], root=c['root'])
        else:
            prefix = str(c['batch'].relative_to(c['root'])) + '/'
            files = {str(p.relative_to(c['root'])): p.read_bytes() for p in c['batch'].rglob('*') if p.is_file()}
            files.update({prefix + 'current/episode.json': b'{}\n', prefix + 'current.png': b'\x89PNG\r\n\x1a\nsmall',
                'tracking/packets.jsonl': encoded({'time': 4}), 'tracking/events.jsonl': encoded({'time': 4})})
            raw, cp, _ = packed(files)
            archive.inspect_archive(io.BytesIO(raw), cp, prefix)


def test_actual_failed_prelaunch_carry_replays_when_explicitly_supplied(monkeypatch):
    """Read the preserved real failed start without writing or relaunching it."""
    supplied = os.environ.get('CLIENT442_OFFLINE_CARRY_REPLAY')
    if supplied is None: pytest.skip('explicit immutable local carry path required')
    batch = Path(supplied)
    root = batch.parent.parent
    monkeypatch.setattr(evidence.lab, 'ROOT', root)
    store = source.local_store(batch, root=root)
    carry_ref = source.bound(batch / 'crash_ancestry.json')
    carry = store.get(carry_ref, False)
    indexed_ref = source.bound(batch / 'resume/indexed_authority.json')
    old = source.parent.validate_cache(store.get(indexed_ref, False), store=store, root=root)
    closed = store.get(carry['boundary_source'], False)
    expected = source._core(old, closed)
    descriptor = {'schema': source.CACHE_SCHEMA, 'indexed_authority_source': indexed_ref,
        'carry_source': carry_ref, 'boundary_source': carry['boundary_source'],
        'core_sha256': hashlib.sha256(source._encode(expected)).hexdigest()}
    assert source.validate_cache(descriptor, store=store, root=root) == expected
    assert closed['excluded_failed_entry'] is True and closed['operations_admitted'] == 0
    # Reject a missing exact historical ready SHA without editing its real file.
    ready_member = store.member(closed['sources']['preparation'])
    digest = store.digests.pop(ready_member)
    with pytest.raises(RuntimeError): source.validate_cache(descriptor, store=store, root=root)
    store.digests[ready_member] = digest
    # The real raw path/size map also refuses a corrupted declared byte count.
    indexed_copies = archive.validate_carry_manifest(store.get(carry['indexed_carry_source'], False), root)
    sizes = {member: Path(path).stat().st_size for member, path in store.paths.items()}
    sizes[ready_member] += 1
    with pytest.raises(RuntimeError, match='every crash copy must bind its exact raw bytes'):
        archive._crash_copies(store.paths, store.digests, indexed_copies, root, sizes)

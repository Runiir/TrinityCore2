"""Raw scoped ancestors and exact opaque-cache handling for stopped UI173."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path

import pytest

from tools.client_compatibility import bag_swap_source_index as s
from tools.client_compatibility.world.tests import test_bag_swap_fresh_sources as fresh_fixture
from tools.client_compatibility.world.tests.test_bag_swap_failed_publication import archive, encoded


def ancestor_fixture(tmp_path, monkeypatch):
    """Use the genuine serialized ancestor fixture, with its missing raw compact.

    Only private admission pins adapt these synthetic bytes. Neither a receipt
    nor an environment variable can choose an opaque class or ancestor source.
    """
    parent = fresh_fixture.parent_fixture

    def with_compact(*args):
        store, pause = parent(*args)
        cache = next(v for v in store.data.values() if v.get('schema') == s.original.CACHE_SCHEMA)
        c, refs = cache['values']['closure'], cache['refs']
        core = {'closure': c, 'snapshot': c['after'], 'predecessor': refs,
            'primary_stop_source': refs['primary_stop'], 'dvc_pointer': cache['values']['dvc_pointer'],
            'runtime': c['runtime'], 'origin_actor': c['actor']}
        ready = store.get(pause['original_preparation_source'], False)
        ref = store.put('old_runtime_authority.json', {'schema': s.original.RUNTIME_SCHEMA,
            'authority_source': ready['authority_source'], 'core': core})
        for member, value in store.data.items():
            if member.startswith('evidence/unit/') and 'runtime_authority_source' in value:
                value['runtime_authority_source'] = deepcopy(ref)
        return store, pause

    monkeypatch.setattr(fresh_fixture, 'parent_fixture', with_compact)
    store, old, ready, mapping = fresh_fixture.fixture(tmp_path, monkeypatch)
    monkeypatch.setattr(s, 'ROOT', store.root)
    old_ready = old['graph']['data'][str(Path(old['closure']['original_preparation_source']['path']).relative_to(store.root))]
    legacy_ref = old_ready['authority_source']
    legacy_copy = next(r['copy_member'] for r in mapping['members']
        if r['original_member'] == str(Path(legacy_ref['path']).relative_to(store.root)))
    # Actual UI173 retains copied raw members, not each original UI172 source.
    wanted = {r['copy_member'] for r in mapping['members'] + mapping['authorities']}
    wanted |= {'evidence/fresh/predecessor_ui172.json', *(str(Path(ready[k]['path']).relative_to(store.root))
        for k in ('authority_source', 'runtime_authority_source'))}
    compact_ref = old_ready['runtime_authority_source']
    compact_key = str(Path(compact_ref['path']).relative_to(store.root))
    wanted.add(compact_key)
    data, digests, journals, paths = {}, {}, {}, {}
    for member in wanted:
        raw = store.files[member]
        path = store.root / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        paths[member], digests[member] = str(path), hashlib.sha256(raw).hexdigest()
        if member in store.data: data[member] = deepcopy(store.data[member])
        if member in store.raw_journals: journals[member] = deepcopy(store.raw_journals[member])
    full_key = str(Path(ready['authority_source']['path']).relative_to(store.root))
    opaque = {'ui172_authority': {'source': ready['authority_source'], 'bytes': len(store.files[full_key]),
            'core_sha256': hashlib.sha256(s.fresh._encode({k: old[k] for k in s.fresh.CORE_FIELDS})).hexdigest()},
        'ui171_authority': {'source': legacy_ref, 'bytes': len(store.files[legacy_copy]), 'core_sha256': None}}
    monkeypatch.setattr(s, '_OPAQUE_SOURCES', opaque)
    data.pop(full_key)
    data.pop(legacy_copy)
    return s.Sources(data, digests, journals, paths=paths, root=store.root), ready


@pytest.fixture(scope='module')
def ancestors(tmp_path_factory):
    patch = pytest.MonkeyPatch()
    store, ready = ancestor_fixture(tmp_path_factory.mktemp('source-index-ancestors'), patch)
    yield store, ready, patch
    patch.undo()


def test_raw_scoped_ancestors_match_both_remote_proofs_without_loading_opaque_graphs(ancestors, monkeypatch):
    store, ready, _ = ancestors
    original_json = s._json
    def no_full_cache(raw):
        assert not (b'"graph"' in raw and (b'"values"' in raw or b'"core_sha256"' in raw))
        return original_json(raw)
    monkeypatch.setattr(s, '_json', no_full_cache)
    monkeypatch.setattr(s.original, 'cached_bundle', lambda *a, **k: pytest.fail('legacy whole-cache parse'))
    monkeypatch.setattr(s.fresh, 'cached_bundle', lambda *a, **k: pytest.fail('fresh whole-cache parse'))
    result = s.prove_ancestors(store, ready)
    assert result['ui172']['snapshot']['2']['native']['logout_time'] == 1791422949
    assert result['ui172']['remote_proof']['operations_admitted'] == 0
    assert result['ui171']['remote_proof']['actual_packet_journals_verified'] is True
    assert result['opaque_authority']['source'] == ready['authority_source']


@pytest.mark.parametrize('fault', ['missing_frame', 'wrong_digest', 'changed_compact', 'truncated_journal', 'missing_compact'])
def test_raw_ancestor_replay_rejects_changed_or_missing_retained_sources(ancestors, tmp_path, fault):
    source, ready, _ = ancestors
    store = s.Sources(deepcopy(source.data), dict(source.digests), deepcopy(source.raw_journals),
        paths=dict(source.paths), root=source.root)
    if fault == 'missing_frame':
        del store.digests[next(m for m in store.digests if m.endswith('.png'))]
    elif fault == 'wrong_digest':
        store.digests[next(m for m in store.raw_journals)] = '0' * 64
    elif fault == 'changed_compact':
        value = store.get(ready['runtime_authority_source'], False)
        value['core']['snapshot']['2']['native']['logout_time'] += 1
    elif fault == 'missing_compact':
        legacy = next(v for v in store.data.values() if v.get('schema') == s.original.RUNTIME_SCHEMA)
        del store.data[next(m for m, v in store.data.items() if v is legacy)]
    else:
        row = next(r for v in store.data.values() if v.get('schema') == 'client442_bag_swap_ancestry_v1'
            for r in v['journals'] if r['original_member'].endswith('packets.jsonl'))
        member = store.member({'path': str(store.root / row['copy_member']), 'sha256': row['sha256']})
        retained = store.raw_journals[member][1:]
        raw = b''.join(encoded(r) + b'\n' for r in retained)
        target = tmp_path / 'truncated.jsonl'
        target.write_bytes(raw)
        row.update(sha256=hashlib.sha256(raw).hexdigest(), bytes=len(raw))
        store.digests[member], store.paths[member], store.raw_journals[member] = row['sha256'], str(target), retained
    with pytest.raises(RuntimeError): s.prove_ancestors(store, ready)


def test_index_points_to_existing_bytes_and_only_copies_missing_external_compact(ancestors, tmp_path, monkeypatch):
    store, ready, _ = ancestors
    # The portable fixture's compact lives outside this current batch, as in
    # the actual UI173 predecessor carry. No existing member is copied again.
    directory = store.root / 'evidence/fresh'
    legacy_compact = next(m for m, v in store.data.items() if v.get('schema') == s.original.RUNTIME_SCHEMA)
    extra = {'path': str(store.root / legacy_compact), 'sha256': store.digests[legacy_compact]}
    out = directory / 'index_output/source_index.json'
    out.parent.mkdir()
    ref = s.build_source_index(directory, out, extra_sources=[extra])
    value = json.loads(out.read_bytes())
    assert ref['sha256'] == hashlib.sha256(out.read_bytes()).hexdigest()
    assert all(row['member'] == row['source_member'] for row in value['blobs'])
    assert len(list((out.parent / 'source_blobs').iterdir())) == 1
    assert not any(row['kind'].endswith('_authority') and '/source_blobs/' in row['member'] for row in value['blobs'])
    copied = s.local_sources(directory)
    assert copied.get(extra, False)['schema'] == s.original.RUNTIME_SCHEMA


def test_missing_compact_preflight_loads_actual_bytes_and_returns_exact_copy_ref(ancestors):
    source, ready, _ = ancestors
    store = s.Sources(deepcopy(source.data), dict(source.digests), source.raw_journals,
        paths=dict(source.paths), root=source.root)
    key = next(m for m, v in store.data.items() if v.get('schema') == s.original.RUNTIME_SCHEMA)
    ref = {'path': str(store.root / key), 'sha256': store.digests[key]}
    del store.data[key], store.digests[key], store.paths[key]
    assert s.preload_ancestor_sources(store, ready) == (ref,)
    assert store.get(ref, False)['schema'] == s.original.RUNTIME_SCHEMA
    assert s.preload_ancestor_sources(store, ready) == ()


@pytest.mark.parametrize('fault', ['outside', 'parent_segment', 'symlink'])
def test_writer_rejects_invalid_destination_before_copying_an_external_source(ancestors, tmp_path, fault):
    store, _, _ = ancestors
    compact_member = next(m for m, v in store.data.items() if v.get('schema') == s.original.RUNTIME_SCHEMA)
    extra = {'path': str(store.root / compact_member), 'sha256': store.digests[compact_member]}
    directory = store.root / 'evidence/fresh'
    outside = tmp_path / 'outside'
    outside.mkdir()
    if fault == 'outside': output = outside / 'source_index.json'
    elif fault == 'parent_segment': output = directory / '..' / '..' / 'escaped/source_index.json'
    else:
        link = directory / 'invalid_link'
        link.symlink_to(outside, target_is_directory=True)
        output = link / 'source_index.json'
    with pytest.raises(RuntimeError): s.build_source_index(directory, output, extra_sources=[extra])
    assert list(outside.iterdir()) == []


def test_full_manifest_tar_replays_both_raw_scopes_with_opaque_cache_leaves(ancestors):
    store, ready, _ = ancestors
    compact_member = next(m for m, v in store.data.items() if v.get('schema') == s.original.RUNTIME_SCHEMA)
    compact_ref = {'path': str(store.root / compact_member), 'sha256': store.digests[compact_member]}
    files = {m: Path(p).read_bytes() for m, p in store.paths.items() if m != compact_member}
    copy = 'evidence/fresh/source_blobs/' + compact_ref['sha256'] + '.json'
    files[copy] = Path(store.paths[compact_member]).read_bytes()
    row = {'sha256': compact_ref['sha256'], 'bytes': len(files[copy]), 'member': copy,
        'source_member': copy, 'kind': 'json'}
    index = {'schema': s.SCHEMA, 'blobs': [row], 'scopes': [{'id': 'ui171', 'parent': None},
        {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}], 'aliases': [{'scope': 'ui172',
        'original_path': compact_ref['path'], 'original_member': compact_member, 'sha256': row['sha256'],
        'bytes': row['bytes'], 'blob': copy}]}
    files['evidence/fresh/source_index.json'] = encoded(index)
    files['evidence/fresh/excluded/episode.json'] = b'{"completed":true,"failure":null}\n'
    files['tracking/packets.jsonl'] = b'{"time":1,"name":"archive_fixture"}\n'
    files['tracking/events.jsonl'] = b'{"time":1,"event":"archive_fixture"}\n'
    raw, cp, prefix = archive(files, 'evidence/fresh/')
    data, digests, tracking, _ = s.inspect_archive(io.BytesIO(raw), cp, prefix)
    try:
        assert len(tracking['opaque_sources']) == 2
        assert set(digests) == {r['path'] for r in cp['file_manifest']}
        remote = s.Sources(data, digests, tracking['raw_journals'], paths=tracking['paths'], root=store.root)
        result = s.prove_ancestors(remote, ready)
        assert result['ui172']['remote_proof']['original_ui171_raw_journals_verified'] is True
        assert result['ui172']['remote_proof']['operations_admitted'] == 0
    finally: tracking['_spool'].cleanup()


def _archive_fixture(tmp_path, monkeypatch, *, altered=None, extra=()):
    root = tmp_path / 'root'
    monkeypatch.setattr(s, 'ROOT', root)
    prefix = 'evidence/unit/'
    opaque_name = prefix + 'authority.json'
    raw_cache = s.fresh._encode({'core_sha256': 'a' * 64, 'graph': {'padding': 'x' * 8192},
        'refs': {}, 'schema': s.fresh.CACHE_SCHEMA, 'values': {}})
    sha = hashlib.sha256(raw_cache).hexdigest()
    monkeypatch.setattr(s, '_OPAQUE_SOURCES', {'ui172_authority': {'source': {'path': str(root / opaque_name),
        'sha256': sha}, 'bytes': len(raw_cache), 'core_sha256': 'a' * 64}})
    files = {prefix + 'pause/episode.json': b'{"completed":true,"failure":null}\n',
        prefix + 'pause/screen.png': b'\x89PNG\r\n\x1a\nfixture', opaque_name: raw_cache,
        prefix + 'binary.bin': b'actual opaque binary bytes',
        'tracking/packets.jsonl': b'{"time":2,"name":"fixture"}\n',
        'tracking/events.jsonl': b'{"time":3,"event":"fixture"}\n'}
    raw, cp, prefix = archive(files, prefix, actual_overrides=altered, extra=extra)
    return raw, cp, prefix, opaque_name


def test_complete_archive_hashes_every_member_and_spools_only_exact_opaque_class(tmp_path, monkeypatch):
    raw, cp, prefix, member = _archive_fixture(tmp_path, monkeypatch)
    original_json = s._json
    monkeypatch.setattr(s, '_json', lambda value: (pytest.fail('opaque whole-cache JSON parse')
        if b'"core_sha256"' in value else original_json(value)))
    data, digests, tracking, size = s.inspect_archive(io.BytesIO(raw), cp, prefix)
    try:
        assert member not in data and member in tracking['paths']
        assert set(digests) == {r['path'] for r in cp['file_manifest']}
        assert len(tracking['raw_journals']) == 2 and size == len(raw)
        assert Path(tracking['paths'][member]).read_bytes().startswith(b'{"core_sha256"')
        assert tracking['opaque_sources'][member]['kind'] == 'ui172_authority'
    finally: tracking['_spool'].cleanup()


@pytest.mark.parametrize('fault', ['binary_changed', 'bad_time', 'malformed_metadata', 'opaque_changed',
    'gzip_trailer', 'unmanifested_json', 'undeclared_blob', 'ordinary_oversize'])
def test_stream_refuses_unbound_opaque_and_global_manifest_or_eof_damage(tmp_path, monkeypatch, fault):
    altered = None
    if fault == 'binary_changed': altered = {'evidence/unit/binary.bin': b'changed bytes'}
    elif fault == 'bad_time': altered = {'tracking/events.jsonl': b'{"time":null,"event":"fixture"}\n'}
    elif fault == 'malformed_metadata': altered = {'tracking/checkpoint.json': b'{}'}
    elif fault == 'opaque_changed': altered = {'evidence/unit/authority.json': b'{"changed":true}'}
    raw, cp, prefix, _ = _archive_fixture(tmp_path, monkeypatch, altered=altered)
    if fault == 'gzip_trailer':
        raw += b'x'
        cp.update(bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    elif fault in ('unmanifested_json', 'undeclared_blob'):
        import tarfile
        member = tarfile.TarInfo('outside/' + ('unbound.json' if fault == 'unmanifested_json' else 'unbound.blob'))
        member.size = 2
        raw, cp, prefix, _ = _archive_fixture(tmp_path, monkeypatch, extra=[(member, b'{}')])
    elif fault == 'ordinary_oversize': monkeypatch.setattr(s, 'MAX_JSON', 16)
    with pytest.raises(RuntimeError): s.inspect_archive(io.BytesIO(raw), cp, prefix)


def test_logical_scopes_use_distinct_objects_and_reject_ambiguous_source_aliases(tmp_path):
    root = tmp_path / 'root'
    value = {'completed': True, 'failure': None}
    sha = hashlib.sha256(encoded(value)).hexdigest()
    store = s.Sources({'evidence/current/value.json': value}, {'evidence/current/value.json': sha}, root=root)
    rows = [{'original_member': 'evidence/old/value.json', 'sha256': sha, 'bytes': len(encoded(value)),
        'copy_member': 'evidence/current/value.json'}]
    old = store.scope(rows)
    assert old.data['evidence/old/value.json'] is not value
    assert old.source_ref(old.data['evidence/old/value.json'])['path'] == str(root / 'evidence/old/value.json')
    store.aliases = [(str(root / 'evidence/original.json'), sha, 'evidence/a.json'),
        (str(root / 'evidence/original.json'), sha, 'evidence/b.json')]
    store.digests.update({'evidence/a.json': sha, 'evidence/b.json': sha})
    with pytest.raises(RuntimeError, match='ambiguous'):
        store.member({'path': str(root / 'evidence/original.json'), 'sha256': sha})


@pytest.mark.parametrize('fault', ['duplicate_sha', 'wrong_parent', 'unknown_opaque'])
def test_flat_index_rejects_duplicate_payloads_wrong_scope_and_unadmitted_opaque(fault):
    value = {'schema': s.SCHEMA, 'blobs': [{'member': 'evidence/a.json', 'source_member': 'evidence/a.json',
        'sha256': 'a' * 64, 'bytes': 2, 'kind': 'json'}],
        'scopes': [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'},
            {'id': 'ui173', 'parent': 'ui172'}], 'aliases': []}
    if fault == 'duplicate_sha': value['blobs'].append({**value['blobs'][0], 'member': 'evidence/b.json'})
    elif fault == 'wrong_parent': value['scopes'][2]['parent'] = 'ui171'
    else: value['blobs'][0]['kind'] = 'ui172_authority'
    with pytest.raises(RuntimeError): s.validate_index(value)


def test_legacy_token_skip_preserves_escaped_strings_across_small_chunk_boundaries(monkeypatch):
    monkeypatch.setattr(s, 'CHUNK', 7)
    value = {'graph': {'data': {'giant': '\\"}[{}' * 100}, 'journal_manifest': {'tracking/packets.jsonl': {'bytes': 3}}},
        'schema': s.original.CACHE_SCHEMA, 'values': {'actual': 'bytes'}, 'refs': {'a': 'b'}}
    selected = s._Cursor(io.BytesIO(encoded(value))).fields({'schema', 'values', 'refs'}, ('graph', {'journal_manifest'}))
    assert selected == {k: v for k, v in value.items() if k != 'graph'} | {'graph': {'journal_manifest': value['graph']['journal_manifest']}}


def test_exact_index_alias_uses_canonical_payload_when_legacy_names_retain_identical_bytes(tmp_path):
    root, sha = tmp_path / 'root', 'a' * 64
    original_path = str(root / 'evidence/old/value.json')
    legacy = {'schema': 'client442_bag_swap_ancestry_v1', 'members': [{'original_path': original_path,
        'sha256': sha, 'copy_member': 'evidence/current/legacy.json'}]}
    index = {'schema': s.SCHEMA, 'blobs': [{'member': 'evidence/current/canonical.json',
        'source_member': 'evidence/current/canonical.json', 'sha256': sha, 'bytes': 2, 'kind': 'json'}],
        'scopes': [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}],
        'aliases': [{'scope': 'ui171', 'original_path': original_path, 'original_member': 'evidence/old/value.json',
            'sha256': sha, 'bytes': 2, 'blob': 'evidence/current/canonical.json'}]}
    store = s.Sources({'evidence/current/map.json': legacy}, {'evidence/current/legacy.json': sha,
        'evidence/current/canonical.json': sha}, root=root, index=index)
    assert store.member({'path': original_path, 'sha256': sha}) == 'evidence/current/canonical.json'


def test_declared_binary_blob_cannot_hide_ordinary_json_provenance_and_size(tmp_path, monkeypatch):
    root = tmp_path / 'root'
    monkeypatch.setattr(s, 'ROOT', root)
    monkeypatch.setattr(s, 'MAX_JSON', 16)
    payload = encoded({'ordinary': 'JSON bytes' * 20})
    member = 'evidence/unit/foreign.blob'
    row = {'member': member, 'source_member': 'evidence/unit/ordinary.json', 'sha256': hashlib.sha256(payload).hexdigest(),
        'bytes': len(payload), 'kind': 'binary'}
    index = {'schema': s.SCHEMA, 'blobs': [row], 'scopes': [{'id': 'ui171', 'parent': None},
        {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}], 'aliases': [{'scope': 'ui173',
        'original_path': str(root / row['source_member']), 'original_member': row['source_member'],
        'sha256': row['sha256'], 'bytes': row['bytes'], 'blob': member}]}
    files = {member: payload, 'evidence/unit/pause/episode.json': b'{}',
        'evidence/unit/pause/screen.png': b'\x89PNG\r\n\x1a\nfixture',
        'tracking/packets.jsonl': b'{"time":1}\n', 'tracking/events.jsonl': b'{"time":1}\n'}
    raw, cp, prefix = archive(files)
    with pytest.raises(RuntimeError, match='source class'):
        s.inspect_archive(io.BytesIO(raw), cp, prefix, index=index)


@pytest.mark.parametrize('reader', ['local', 'archive'])
@pytest.mark.parametrize('name', ['source_index.json', 'renamed.json', 'source.blob'])
@pytest.mark.parametrize('extra_byte', [0, 1])
def test_source_index_retained_bytes_exact_cap_and_cap_plus_one_for_every_json_path(
        tmp_path, monkeypatch, reader, name, extra_byte):
    root, prefix = tmp_path / 'root', 'evidence/unit/'
    monkeypatch.setattr(s, 'ROOT', root)
    payload = b'actual binary bytes'
    binary = {'member': prefix + 'data.bin', 'source_member': prefix + 'data.bin', 'kind': 'binary',
        'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload)}
    scopes = [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}]
    value = {'schema': s.SCHEMA, 'blobs': [binary], 'scopes': scopes, 'aliases': []}
    # The raw hash/byte count includes all retained padding. Canonicalizing this
    # small document would conceal the actual cap+1 source-byte violation.
    body = encoded(value)
    raw_index = body + b' ' * (s.MAX_INDEX + extra_byte - len(body))
    assert len(raw_index) == 16 * 1024 * 1024 + extra_byte
    assert len(encoded(value)) < s.MAX_INDEX
    member = prefix + name
    classified = None
    if name.endswith('.blob'):
        classified = {'schema': s.SCHEMA, 'scopes': scopes, 'aliases': [], 'blobs': [{
            'member': member, 'source_member': prefix + 'original_index.json', 'kind': 'json',
            'sha256': hashlib.sha256(raw_index).hexdigest(), 'bytes': len(raw_index)}]}
    if reader == 'local':
        directory = root / prefix
        directory.mkdir(parents=True)
        (root / member).write_bytes(raw_index)
        (root / binary['member']).write_bytes(payload)
        if extra_byte:
            with pytest.raises(RuntimeError, match='retained raw source index.*bound'):
                s.local_sources(directory, index=classified)
        else:
            result = s.local_sources(directory, index=classified)
            assert result.data[member] == value
            assert result.digests[member] == hashlib.sha256(raw_index).hexdigest()
    else:
        files = {member: raw_index, binary['member']: payload,
            prefix + 'pause/episode.json': b'{}', prefix + 'pause/screen.png': b'\x89PNG\r\n\x1a\nfixture',
            'tracking/packets.jsonl': b'{"time":1}\n', 'tracking/events.jsonl': b'{"time":1}\n'}
        raw, cp, prefix = archive(files, prefix)
        if extra_byte:
            with pytest.raises(RuntimeError, match='retained raw source index.*bound'):
                s.inspect_archive(io.BytesIO(raw), cp, prefix, index=classified)
        else:
            data, digests, tracking, _ = s.inspect_archive(io.BytesIO(raw), cp, prefix, index=classified)
            try:
                assert data[member] == value
                assert digests[member] == hashlib.sha256(raw_index).hexdigest()
            finally: tracking['_spool'].cleanup()


def test_direct_in_memory_index_validation_is_bounded_without_retained_byte_metadata(monkeypatch):
    monkeypatch.setattr(s, 'MAX_INDEX', 1024)
    member = 'evidence/' + 'x' * 1000 + '.bin'
    value = {'schema': s.SCHEMA, 'blobs': [{'member': member, 'source_member': member, 'kind': 'binary',
        'sha256': 'a' * 64, 'bytes': 1}], 'scopes': [{'id': 'ui171', 'parent': None},
        {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}], 'aliases': []}
    with pytest.raises(RuntimeError, match='in-memory source index.*bound'): s.validate_index(value)


@pytest.mark.parametrize('extra_byte', [0, 1])
def test_local_sha_dedup_retains_the_index_byte_limit_and_separate_source_objects(tmp_path, monkeypatch, extra_byte):
    root, prefix = tmp_path / 'root', 'evidence/unit/'
    monkeypatch.setattr(s, 'ROOT', root)
    directory = root / prefix
    directory.mkdir(parents=True)
    payload = b'actual binary bytes'
    value = {'schema': s.SCHEMA, 'blobs': [{'member': prefix + 'data.bin', 'source_member': prefix + 'data.bin',
        'sha256': hashlib.sha256(payload).hexdigest(), 'bytes': len(payload), 'kind': 'binary'}],
        'scopes': [{'id': 'ui171', 'parent': None}, {'id': 'ui172', 'parent': 'ui171'},
            {'id': 'ui173', 'parent': 'ui172'}], 'aliases': []}
    body = encoded(value)
    raw = body + b' ' * (s.MAX_INDEX + extra_byte - len(body))
    for name in ('a.json', 'b.json'): (directory / name).write_bytes(raw)
    (directory / 'data.bin').write_bytes(payload)
    original_json, calls = s._source_json, []
    def decoded_once(raw):
        calls.append(len(raw))
        return original_json(raw)
    monkeypatch.setattr(s, '_source_json', decoded_once)
    if extra_byte:
        with pytest.raises(RuntimeError, match='retained raw source index.*bound'):
            s.local_sources(directory, index=value)
    else:
        result = s.local_sources(directory, index=value)
        assert result.data[prefix + 'a.json'] == result.data[prefix + 'b.json'] == value
        assert result.data[prefix + 'a.json'] is not result.data[prefix + 'b.json']
    assert calls == [len(raw)]


@pytest.mark.parametrize('cap_delta', [0, -1])
def test_in_memory_index_cap_includes_the_writers_final_newline(monkeypatch, cap_delta):
    member = 'evidence/unit/data.bin'
    value = {'schema': s.SCHEMA, 'blobs': [{'member': member, 'source_member': member, 'kind': 'binary',
        'sha256': 'a' * 64, 'bytes': 1}], 'scopes': [{'id': 'ui171', 'parent': None},
        {'id': 'ui172', 'parent': 'ui171'}, {'id': 'ui173', 'parent': 'ui172'}], 'aliases': []}
    raw = s.fresh._encode(value)
    assert raw.endswith(b'\n') and len(raw) == len(encoded(value)) + 1
    monkeypatch.setattr(s, 'MAX_INDEX', len(raw) + cap_delta)
    if cap_delta:
        with pytest.raises(RuntimeError, match='in-memory source index.*bound'): s.validate_index(value)
    else:
        assert s.validate_index(value) == {member: value['blobs'][0]}

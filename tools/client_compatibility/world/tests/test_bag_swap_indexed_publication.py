"""Committed source writer and indexed publication route guards."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools.client_compatibility import bag_swap_indexed_sources as source
from tools.client_compatibility import checkpoint_bag_swap as checkpoint
from tools.client_compatibility import review_bag_swap_checkpoint as reviewer
from tools.client_compatibility import bag_swap_projection as projection
from tools.client_compatibility.world.tests.test_bag_swap_indexed_sources import epoch_fixture
from tools.client_compatibility.world.tests.test_bag_swap_indexed_sources import core
from tools.client_compatibility.world.tests.test_bag_swap_indexed_archive import carried


def execute_public_local(tmp_path):
    """Whole PUBLIC local replay in a private synthetic lab; no actual authority."""
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility.observation import journal
    from tools.client_compatibility.world.tests.test_bag_swap_full_unit import complete_fixture
    with pytest.MonkeyPatch.context() as patch:
        data, digests, tracking, files, _, prefix = complete_fixture(tmp_path, patch)
        expected = evidence.proof(data, digests, tracking)
        root = evidence.lab.ROOT
        assert root.is_relative_to(tmp_path)
        for member, raw in files.items():
            path = root / member
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
        globals = {root / 'evidence/world_packets.jsonl': tracking['packets'],
            root / 'logs/modern_world.jsonl': tracking['events']}
        patch.setattr(journal, 'entries', lambda path: iter(globals[Path(path)]))
        actual = evidence.local(root / prefix.rstrip('/'))
        assert actual == expected and actual['native_swap_pairs'] == 2
        # Exercise both legacy carried and current source-ref fallback readers
        # without an already parsed journal map, using the same pinned files.
        unmaterialized = evidence.Sources(data, digests, local=True)
        closure = next(value for value in data.values() if value.get('phase') == evidence.PHASE)
        _, _, current = evidence.lifecycle(unmaterialized, closure['sources'])
        assert checkpoint.validate_carry(unmaterialized, current[0])
        bare_tracking = {**tracking, 'raw_journals': {}}
        assert evidence.actual_journals(unmaterialized, closure, bare_tracking, current)['actual_packet_journals_verified']
    return {'public_local_entrypoint': True, 'real_local_store_and_proof': True,
        'reader_or_proof_mocked': False, 'global_journal_dependency_mocked': True,
        'unmaterialized_current_and_legacy_journal_fallbacks_executed': True,
        'synthetic_legacy_whole_unit': True, 'actual_parent_evidence': False,
        'native_swap_pairs': 2, 'inventory_restored': actual['inventory_restored']}


def test_complete_synthetic_public_local_entrypoint_executes_real_readers_and_proof(tmp_path):
    result = execute_public_local(tmp_path)
    assert result['inventory_restored'] and result['reader_or_proof_mocked'] is False


def test_public_indexed_local_reuses_stably_materialized_current_journal(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility.observation import journal
    c = carried
    path = c['batch'] / 'journals/packets.jsonl'
    path.parent.mkdir()
    raw = b'{"time":1,"packet":"AAAA"}\n'
    path.write_bytes(raw)
    member, sha = str(path.relative_to(c['root'])), hashlib.sha256(raw).hexdigest()
    ready = c['batch'] / 'probe_ready.json'
    ready.write_text(json.dumps({'completed': True, 'failure': None, 'native_session': 'probe',
        'started_at': .5, 'finished_at': .7}))
    closure = c['batch'] / 'probe_closure.json'
    closure.write_text(json.dumps({'phase': evidence.PHASE, 'finished_at': 2,
        'sources': {'preparation': source.bound(ready)}}))
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    monkeypatch.setattr(journal, 'entries', lambda path: [])
    original = evidence.bound
    def no_second_hash(target):
        assert Path(target) != path, 'public local must reuse its stable journal'
        return original(target)
    monkeypatch.setattr(evidence, 'bound', no_second_hash)
    def final_spy(data, digests, tracking):
        assert tracking['raw_journals'][member] == [{'time': 1, 'packet': 'AAAA'}]
        assert digests[member] == sha
        return tracking['raw_journals'][member]
    monkeypatch.setattr(evidence, 'proof', final_spy)
    assert evidence.local(c['batch']) == [{'time': 1, 'packet': 'AAAA'}]


@pytest.mark.parametrize('pinned', [False, True])
def test_unmaterialized_local_journal_rejects_hash_decode_restore_race(tmp_path, monkeypatch, pinned):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import bag_swap_indexed_archive as archive
    path = tmp_path / 'packets.jsonl'
    raw_a, raw_b = b'{"time":1,"packet":"AAAA"}\n', b'{"time":1,"packet":"BBBB"}\n'
    path.write_bytes(raw_a)
    ref = source.bound(path)
    real_bound, real_parse = evidence.bound, archive._journal
    if pinned:
        path.write_bytes(raw_b)
    else:
        def replace_after_hash(target):
            result = real_bound(target)
            path.write_bytes(raw_b)
            return result
        monkeypatch.setattr(evidence, 'bound', replace_after_hash)
    def restore_after_parse(handle, size):
        result = real_parse(handle, size)
        path.write_bytes(raw_a)
        return result
    monkeypatch.setattr(archive, '_journal', restore_after_parse)
    with pytest.raises(RuntimeError, match='pinned source SHA|changed while decoding'):
        evidence.local_journal(path, ref if pinned else None)
    assert path.read_bytes() == raw_a


def test_unmaterialized_local_journal_caps_before_hash_or_decode(tmp_path, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility.bag_swap_indexed_archive import MAX_JOURNAL
    path = tmp_path / 'oversized.jsonl'
    with path.open('wb') as handle:
        handle.truncate(MAX_JOURNAL + 1)
    monkeypatch.setattr(evidence, 'bound', lambda path: pytest.fail('over-cap journal must not hash'))
    with pytest.raises(RuntimeError, match='unchanged bound'):
        evidence.local_journal(path)
    path.unlink()


def test_indexed_writer_rejects_reused_stopped_publication_before_source_output(tmp_path, monkeypatch):
    store, closure, ready, resume, epoch = epoch_fixture(tmp_path)
    root = tmp_path
    directory = root / 'evidence/ui174/resume'
    directory.mkdir(parents=True)
    monkeypatch.setattr(source, 'ROOT', root)
    monkeypatch.setattr(source, 'REPO', root / 'repo')
    monkeypatch.setattr(source.subprocess, 'check_output', lambda *a, **k: closure['code_commit'])
    monkeypatch.setattr(projection, 'source_identities', lambda repo: epoch['committed_sources'])
    with pytest.raises(RuntimeError): source.current_code_epoch(directory, {'closure': closure})
    assert not (directory / 'code_sources').exists()


def test_checkpoint_epoch_dispatch_uses_stopped_publication_without_legacy_graph(monkeypatch):
    expected = {'path': '/actual/source.json', 'sha256': 'a' * 64}
    seen = []
    monkeypatch.setattr(source, 'current_code_epoch', lambda directory, old: seen.append((directory, old)) or expected)
    old = {'closure': {'schema': 'client442_bag_swap_stopped_entry_closure_v1'}}
    assert checkpoint.current_code_epoch(Path('/new'), old) == expected
    assert seen == [(Path('/new'), old)]
    assert 'graph' not in old


def test_remote_indexed_route_rejects_duplicate_carry_manifest_rows():
    cp = {'file_manifest': [{'path': 'evidence/ui174/predecessor_ui173.json'},
        {'path': 'evidence/ui174/predecessor_ui173.json'}]}
    with pytest.raises(RuntimeError): reviewer.inspect_archive(None, cp, 'evidence/ui174/')


def test_successor_explicit_vector_keeps_historical_v1_helper_and_stopped_helpers_out_of_changed_set():
    assert 'tools/client_compatibility/bag_swap_login_sync.py' not in source.CHANGED_OLD
    assert 'tools/client_compatibility/world/tests/test_bag_swap_login_sync.py' not in source.CHANGED_OLD
    assert 'tools/client_compatibility/bag_swap_stopped_contract.py' not in source.CHANGED_OLD
    assert 'tools/client_compatibility/bag_swap_source_index.py' not in source.CHANGED_OLD
    assert 'tools/client_compatibility/bag_swap_login_sync_v2.py' in source.NEW_FILES
    assert 'tools/client_compatibility/native_bridge/service.cpp' in source.INDEXED_DEPENDENCIES
    assert 'tools/client_compatibility/native_bridge/session_auth.cpp' in source.INDEXED_DEPENDENCIES
    assert 'tools/client_compatibility/native_bridge/events.cpp' in source.INDEXED_DEPENDENCIES


def runtime_fixture(carried):
    """Bind the live consumer to small synthetic sources; no admission is minted."""
    c = carried
    value = core(c['root'])
    value['predecessor'] = deepcopy(c['predecessor'])
    value['primary_stop_source'] = c['predecessor']['primary_stop']
    value['closure']['predecessor']['primary_stop'] = c['predecessor']['primary_stop']
    value['closure']['source_index_source'] = c['carry']['source_index_source']
    value['dvc_pointer'] = c['carry']['dvc_pointer']
    directory = c['batch'] / 'resume'
    directory.mkdir()
    desc = {'schema': source.CACHE_SCHEMA, 'refs': value['predecessor'],
        'core_sha256': hashlib.sha256(source._encode(value)).hexdigest(),
        'source_index_source': value['closure']['source_index_source'], 'carry_source': c['carry_ref'],
        'dvc_pointer': value['dvc_pointer'], 'pointer_raw_hex': c['carry']['pointer_raw_hex']}
    path = directory / 'authority.json'
    path.write_bytes(source._encode(desc))
    ref = source.bound(path)
    runtime = source.compact_authority(value, ref, root=c['root'])
    runtime_path = directory / 'runtime_authority.json'
    runtime_path.write_bytes(source._encode(runtime))
    return c, value, path, ref, runtime_path


def test_live_runtime_reads_only_small_admitted_identity_sources(carried, monkeypatch):
    c, value, path, ref, runtime_path = runtime_fixture(carried)
    monkeypatch.setattr(source, 'validate_parent', lambda *a, **k: pytest.fail('live input cannot replay parent'))
    monkeypatch.setattr(source, 'cached_bundle', lambda *a, **k: pytest.fail('live input cannot load parent journal/opaque bytes'))
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    monkeypatch.setattr(adapter, 'local_sources', lambda *a, **k: pytest.fail('live input cannot materialize whole raw carry'))
    assert source.cached_runtime(runtime_path, ref, root=c['root']) == value


@pytest.mark.parametrize('fault', ['descriptor_bytes', 'core', 'carry_bytes', 'runtime_padding'])
def test_live_runtime_rejects_changed_small_identity_sources(carried, fault):
    c, value, path, ref, runtime_path = runtime_fixture(carried)
    if fault == 'descriptor_bytes': path.write_bytes(path.read_bytes() + b' ')
    elif fault == 'core':
        runtime = json.loads(runtime_path.read_bytes())
        runtime['core']['closure']['owned_game_identity']['pid'] += 1
        runtime_path.write_bytes(source._encode(runtime))
    elif fault == 'carry_bytes':
        carry_path = Path(c['carry_ref']['path'])
        carry_path.write_bytes(carry_path.read_bytes() + b' ')
    else: runtime_path.write_bytes(runtime_path.read_bytes() + b' ' * source.MAX_RUNTIME_BYTES)
    with pytest.raises(RuntimeError): source.cached_runtime(runtime_path, ref, root=c['root'])


def test_provider_restores_typed_parent_journals_from_generic_evidence_store(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    outer = adapter.local_sources(c['batch'], root=c['root'])
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    generic = evidence.Sources(outer.data, outer.digests, paths=outer.paths)
    generic.raw_journals = outer.raw_journals
    assert not hasattr(generic, 'journal')
    _, (_, _, tracking) = source._carry(generic, {'carry_source': c['carry_ref'],
        'refs': c['carry']['predecessor'], 'source_index_source': c['carry']['source_index_source'],
        'dvc_pointer': c['carry']['dvc_pointer'], 'pointer_raw_hex': c['carry']['pointer_raw_hex']})
    assert tracking['packets'] == [{'time': 1, 'packet': 'parent'}]
    assert tracking['events'] == [{'time': 1, 'event': 'parent'}]


def test_local_offline_proof_retains_carried_blob_journals(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility.observation import journal
    c = carried
    outer = adapter.local_sources(c['batch'], root=c['root'])
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    monkeypatch.setattr(evidence, 'local_store', lambda directory: outer)
    monkeypatch.setattr(journal, 'entries', lambda path: [])
    monkeypatch.setattr(evidence, 'collect', lambda member, lines, data, tracking: None)
    monkeypatch.setattr(evidence, 'proof', lambda data, digests, tracking: tracking['raw_journals'])
    result = evidence.local(c['batch'])
    assert result == outer.raw_journals and result


@pytest.mark.parametrize('local', [False, True])
def test_generic_store_preserves_every_original_carry_class(carried, monkeypatch, local):
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    outer = adapter.local_sources(c['batch'], root=c['root'])
    generic = evidence.Sources(outer.data, outer.digests, local=local, paths=outer.paths)
    for row in [*c['carry']['members'], *c['carry']['authorities']]:
        ref = {'path': row['original_path'], 'sha256': row['sha256']}
        assert generic.logical_kinds[(ref['path'], ref['sha256'])] == frozenset((row['kind'],))
        if row['kind'] == 'json' and Path(ref['path']).is_relative_to(c['root'] / 'evidence'):
            assert generic.get(ref, False) == outer.get(ref, False)
        elif row['kind'] == 'json':
            with pytest.raises(RuntimeError, match='private evidence'):
                generic.get(ref, False)
        else:
            with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
                generic.get(ref, False)


def test_generic_binary_original_cannot_borrow_json_from_direct_data_or_local_file(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    outer = adapter.local_sources(c['batch'], root=c['root'])
    row = next(r for r in c['carry']['members'] if r['original_member'].endswith('/json_copy.log'))
    ref = {'path': row['original_path'], 'sha256': row['sha256']}
    path = Path(ref['path'])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(c['files'][row['original_member']])
    monkeypatch.setattr(source, '_json_file', lambda *a, **k: pytest.fail('binary original must be rejected before local decode'))
    for direct in (False, True):
        data, digests = dict(outer.data), dict(outer.digests)
        if direct:
            data[row['original_member']] = outer.data[row['copy_member']]
            digests[row['original_member']] = row['sha256']
        generic = evidence.Sources(data, digests, local=True, paths=outer.paths)
        with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
            generic.get(ref, False)


@pytest.mark.parametrize('target_kind', ['json', 'binary'])
def test_generic_legacy_alias_preserves_indexed_target_class_before_local_fallback(carried, monkeypatch, target_kind):
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    outer = adapter.local_sources(c['batch'], root=c['root'])
    row = next(r for r in c['carry']['members'] if r['kind'] == target_kind and
        r['sha256'] == c['predecessor']['closure']['sha256'])
    path = str(c['root'] / 'evidence/ui170/older_alias.json')
    data = dict(outer.data)
    data['evidence/ui174/legacy_map.json'] = {'schema': evidence.ANCESTRY_SCHEMA,
        'members': [{'original_path': path, 'sha256': row['sha256'], 'copy_member': row['original_member']}]}
    generic = evidence.Sources(data, outer.digests, local=True, paths=outer.paths)
    monkeypatch.setattr(source, '_json_file', lambda *a, **k: pytest.fail('known alias must use the carried copy'))
    ref = {'path': path, 'sha256': row['sha256']}
    if target_kind == 'json':
        assert generic.get(ref, False)['value'] == 'parent'
    else:
        with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
            generic.get(ref, False)


def test_generic_union_classes_apply_only_to_explicit_physical_copy(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_indexed_archive as adapter
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    outer = adapter.local_sources(c['batch'], root=c['root'])
    generic = evidence.Sources(outer.data, outer.digests, paths=outer.paths)
    binary = next(r for r in c['carry']['members'] if r['original_member'].endswith('/json_copy.log'))
    copy_ref = {'path': str(c['root'] / binary['copy_member']), 'sha256': binary['sha256']}
    assert generic.copy_kinds[(copy_ref['path'], copy_ref['sha256'])] == frozenset(('json', 'binary'))
    assert generic.get(copy_ref, False)['value'] == 'parent'
    with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
        generic.get({'path': binary['original_path'], 'sha256': binary['sha256']}, False)
    empty = next(r for r in c['carry']['members'] if r['original_member'].endswith('/empty.log'))
    with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
        generic.get({'path': str(c['root'] / empty['copy_member']), 'sha256': empty['sha256']}, False)


def test_generic_local_fallback_retains_classes_when_carry_is_loaded_after_construction(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    generic = evidence.Sources({}, {}, local=True)
    assert generic.get(c['carry_ref'], False) == c['carry']
    assert generic.get(c['predecessor']['closure'], False)['value'] == 'parent'
    binary = next(r for r in c['carry']['members'] if r['original_member'].endswith('/json_copy.log'))
    monkeypatch.setattr(source, '_json_file', lambda *a, **k: pytest.fail('newly loaded binary alias must be rejected before decode'))
    with pytest.raises(RuntimeError, match='not an ordinary JSON view'):
        generic.get({'path': binary['original_path'], 'sha256': binary['sha256']}, False)


def test_generic_local_copy_decode_keeps_original_role_cap_and_explicit_typed_opt_in(carried, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    c = carried
    monkeypatch.setattr(evidence.lab, 'ROOT', c['root'])
    ref = c['predecessor']['closure']
    row = next(r for r in c['carry']['members'] if r['original_path'] == ref['path'])
    generic = evidence.Sources({'evidence/current/carry.json': c['carry'], 'evidence/current/compact.json': {
        'schema': source.RUNTIME_SCHEMA, 'authority_source': ref}}, {}, local=True)
    original_reader, calls = source._json_file, []
    def checked(path, limit, **kwargs):
        calls.append((path, limit, kwargs))
        return original_reader(path, limit, **kwargs)
    monkeypatch.setattr(source, '_json_file', checked)
    assert generic.get(ref, False)['value'] == 'parent'
    copy = c['root'] / row['copy_member']
    assert calls == [(copy, source.MAX_DESCRIPTOR_BYTES, {'root': c['root'],
        'expected_ref': {'path': str(copy), 'sha256': ref['sha256']}, 'allow_raw_json': True})]


@pytest.mark.parametrize('suffix', ['.blob', '.log', '.jsonl'])
def test_generic_local_unclassified_non_json_source_never_opts_into_raw_json(tmp_path, monkeypatch, suffix):
    from tools.client_compatibility import bag_swap_evidence as evidence
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    path = tmp_path / ('evidence/old/unclassified' + suffix)
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"completed":true,"failure":null}\n')
    original_reader, calls = source._json_file, []
    def checked(target, limit, **kwargs):
        calls.append(kwargs)
        return original_reader(target, limit, **kwargs)
    monkeypatch.setattr(source, '_json_file', checked)
    with pytest.raises(RuntimeError, match='ordinary private JSON'):
        evidence.Sources({}, {}, local=True).get(source.bound(path), False)
    assert len(calls) == 1 and not calls[0].get('allow_raw_json', False)


def test_generic_unaliased_historical_local_json_uses_stable_capped_reader(tmp_path, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import bag_swap_sources as original
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/old/source.json'
    path.parent.mkdir(parents=True)
    path.write_bytes(b'{"source_owned":true}\n')
    ref = source.bound(path)
    original_reader, reads = source._json_file, []
    def checked(target, limit, **kwargs):
        reads.append((target, limit, kwargs))
        return original_reader(target, limit, **kwargs)
    monkeypatch.setattr(source, '_json_file', checked)
    assert evidence.Sources({}, {}, local=True).get(ref, False) == {'source_owned': True}
    assert reads == [(path, original.MAX_JSON_BYTES, {'root': tmp_path, 'expected_ref': ref})]


@pytest.mark.parametrize('role', ['runtime', 'descriptor', 'carry'])
def test_generic_renamed_source_owned_roles_keep_predecode_caps(tmp_path, monkeypatch, role):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/current/renamed_private.json'
    path.parent.mkdir(parents=True)
    limit = source.MAX_CARRY_BYTES if role == 'carry' else source.MAX_RUNTIME_BYTES
    path.write_bytes(b'{"role":"oversized"}' + b' ' * limit)
    ref = source.bound(path)
    if role == 'runtime': hint = {'schema': 'client442_bag_swap_scout_resume_v1',
        'phase': 'pending', 'runtime_authority_source': ref}
    elif role == 'descriptor': hint = {'schema': source.RUNTIME_SCHEMA, 'authority_source': ref}
    else: hint = {'schema': source.CACHE_SCHEMA, 'carry_source': ref}
    generic = evidence.Sources({'evidence/current/hint.json': hint}, {}, local=True)
    monkeypatch.setattr(reader, '_json', lambda raw: pytest.fail('source-owned role cap must precede decode'))
    with pytest.raises(RuntimeError, match='exact byte cap'):
        generic.get(ref, False)


def test_generic_ready_ref_caps_renamed_descriptor_after_bounded_runtime_dispatch(tmp_path, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    directory = tmp_path / 'evidence/current'
    directory.mkdir(parents=True)
    descriptor = directory / 'renamed_descriptor.json'
    descriptor.write_bytes(b'{"role":"oversized"}' + b' ' * source.MAX_DESCRIPTOR_BYTES)
    ref = source.bound(descriptor)
    runtime = directory / 'renamed_compact.json'
    runtime.write_bytes(source._encode({'schema': source.RUNTIME_SCHEMA, 'authority_source': ref}))
    runtime_ref = source.bound(runtime)
    generic = evidence.Sources({'evidence/current/ready.json': {
        'schema': 'client442_laya_interactions_v1', 'phase': 'bags_swap_scout_ready',
        'authority_source': ref, 'runtime_authority_source': runtime_ref}}, {}, local=True)
    original_reader, calls = source._json_file, []
    def checked(path, limit, **kwargs):
        calls.append((path, limit))
        return original_reader(path, limit, **kwargs)
    monkeypatch.setattr(source, '_json_file', checked)
    with pytest.raises(RuntimeError, match='exact byte cap'):
        generic.get(ref, False)
    assert calls == [(runtime, source.MAX_RUNTIME_BYTES), (descriptor, source.MAX_DESCRIPTOR_BYTES)]


@pytest.mark.parametrize('nested', [False, True])
def test_generic_ordinary_carry_filename_keeps_ordinary_json_bound(tmp_path, monkeypatch, nested):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import bag_swap_sources as original
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    directory = tmp_path / ('evidence/current/nested' if nested else 'evidence/current')
    directory.mkdir(parents=True)
    payload = {'schema': 'ordinary_snapshot_v1', 'captured': True}
    raw = source._encode(payload) + b' ' * source.MAX_CARRY_BYTES
    original_reader, limits = source._json_file, []
    def checked(path, limit, **kwargs):
        limits.append(limit)
        return original_reader(path, limit, **kwargs)
    monkeypatch.setattr(source, '_json_file', checked)
    for name in ('ordinary.json', 'predecessor_ui173.json'):
        path = directory / name
        path.write_bytes(raw)
        assert evidence.Sources({}, {}, local=True).get(source.bound(path), False) == payload
    assert limits == [original.MAX_JSON_BYTES, original.MAX_JSON_BYTES]


def test_generic_actual_carry_schema_keeps_predecode_bound_without_role_hint(tmp_path, monkeypatch):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import bag_swap_indexed_archive as archive
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    path = tmp_path / 'evidence/current/predecessor_ui173.json'
    path.parent.mkdir(parents=True)
    path.write_bytes(source._encode({'schema': archive.SCHEMA}) + b' ' * source.MAX_CARRY_BYTES)
    ref = source.bound(path)
    monkeypatch.setattr(reader, '_json', lambda raw: pytest.fail('actual carry cap must precede document decode'))
    with pytest.raises(RuntimeError, match='raw byte bound before decode'):
        evidence.Sources({}, {}, local=True).get(ref, False)


@pytest.mark.parametrize('role', ['runtime', 'descriptor'])
@pytest.mark.parametrize('metadata', [
    {'schema': 'ordinary_snapshot_v1'},
    {'schema': 'ordinary_snapshot_v1', 'phase': 'bags_swap_scout_ready'},
    {'schema': 'client442_laya_interactions_v1', 'phase': 'unrelated_phase'}])
def test_generic_unrelated_role_named_fields_keep_ordinary_local_json_bound(tmp_path, monkeypatch, role, metadata):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import bag_swap_sources as original
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    directory = tmp_path / 'evidence/current'
    directory.mkdir(parents=True)
    payload = {'schema': 'ordinary_snapshot_v1', 'padding': 'x' * source.MAX_RUNTIME_BYTES}
    path = directory / 'large_ordinary.json'
    path.write_bytes(source._encode(payload))
    ref = source.bound(path)
    hint = dict(metadata)
    if role == 'runtime':
        hint['runtime_authority_source'] = ref
    else:
        hint.update(authority_source=ref, runtime_authority_source={
            'path': str(directory / 'absent_unrelated_compact.json'), 'sha256': 'f' * 64})
    generic = evidence.Sources({'evidence/current/unrelated.json': hint}, {}, local=True)
    original_reader, calls = source._json_file, []
    def checked(target, limit, **kwargs):
        calls.append((target, limit))
        return original_reader(target, limit, **kwargs)
    monkeypatch.setattr(source, '_json_file', checked)
    assert generic._json_limit(ref) == original.MAX_JSON_BYTES
    assert generic.get(ref, False) == payload
    assert calls == [(path, original.MAX_JSON_BYTES)]


@pytest.mark.parametrize('role', ['runtime', 'descriptor'])
@pytest.mark.parametrize('metadata', [
    {'schema': 'client442_bag_swap_scout_resume_v1', 'phase': 'pending'},
    {'schema': 'client442_laya_interactions_v1', 'phase': 'bags_swap_scout_ready'}])
def test_generic_exact_owner_keeps_renamed_ordinary_target_cap_before_decode(tmp_path, monkeypatch, role, metadata):
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as reader
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    directory = tmp_path / 'evidence/current'
    directory.mkdir(parents=True)
    raw = source._encode({'schema': 'ordinary_snapshot_v1', 'padding': 'x' * source.MAX_RUNTIME_BYTES})
    path = directory / 'renamed_bound_target.json'
    path.write_bytes(raw)
    ref = source.bound(path)
    hint = dict(metadata)
    if role == 'runtime':
        hint['runtime_authority_source'] = ref
    else:
        compact = directory / 'renamed_compact.json'
        compact.write_bytes(source._encode({'schema': source.RUNTIME_SCHEMA, 'authority_source': ref}))
        hint.update(authority_source=ref, runtime_authority_source=source.bound(compact))
    generic = evidence.Sources({'evidence/current/owner.json': hint}, {}, local=True)
    original_decoder, decoded = reader._json, []
    def checked(value):
        assert value != raw, 'over-cap ordinary bound target must not reach document decoder'
        decoded.append(len(value))
        return original_decoder(value)
    monkeypatch.setattr(reader, '_json', checked)
    with pytest.raises(RuntimeError, match='exact byte cap'):
        generic.get(ref, False)
    if role == 'runtime':
        assert not decoded
    else:
        assert len(decoded) == 1 and decoded[0] < source.MAX_RUNTIME_BYTES

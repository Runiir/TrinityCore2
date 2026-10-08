"""Small descriptor and exact successor publication/source boundaries."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools.client_compatibility import bag_swap_indexed_sources as source
from tools.client_compatibility import bag_swap_stopped_evidence as stopped
from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture as preserved


def ref(root, member, sha='a' * 64):
    return {'path': str(root / member), 'sha256': sha}


def core(root):
    snapshot, _, _, exact, _ = preserved()
    roles = {'closure': ref(root, stopped.BATCH + 'stopped_closure01/closure.json'),
        'remote': ref(root, 'evidence/ui173_stopped_remote_review.json'),
        'checkpoint': ref(root, stopped.BATCH + 'checkpoint_receipt.json'),
        'primary_stop': ref(root, 'evidence/primary_stop/episode.json')}
    runtime = {k: {'pid': 100 + i, 'start_ticks': str(200 + i)} for i, k in
        enumerate(('worldserver', 'modern_world', 'client'))}
    pointer = {'source': ref(root, source.POINTER), 'pointer': source.POINTER, 'oid': 'b' * 32, 'bytes': 2048}
    closure = {'schema': stopped.SCHEMA, 'phase': stopped.PHASE, 'completed': True, 'failure': None,
        'controller': 'code', 'model': None, 'revision': None, 'excluded_failed_entry': True,
        'operations_admitted': 0, 'input_sent': False, 'mutation_sent': False, 'qualification_added': False,
        'bag_input_sent': False, 'normal_logout_input_sent': False, 'entry_input_sent': True, 'cases': [], 'cleanup': [],
        'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(stopped.SCRIPT),
        'stop_checks': dict.fromkeys(stopped.STOP_CHECKS, True), 'sources': deepcopy(stopped.SOURCES),
        'started_at': 100, 'audit_until': 101, 'source_validation_finished_at': 102, 'finished_at': 103,
        'before': deepcopy(snapshot), 'after': deepcopy(snapshot), 'all_offline_snapshot': deepcopy(snapshot),
        'actor': {'guid': 2, 'account_id': 2, 'actor': 'scout'}, 'runtime': runtime,
        'predecessor': deepcopy(roles), 'source_index_source': ref(root, stopped.BATCH + 'source_index.json'),
        'owned_game_identity': {'pid': 999, 'source': stopped.SOURCES['preparation'],
            'frame': {'monitor': {'input_isolation': {'game_pid': 999}}}},
        'exact_precision': {'query': source.PRECISION_QUERY, 'input_sent': False, 'mutation_sent': False,
            'before': deepcopy(snapshot), 'after': deepcopy(snapshot), 'before_row': deepcopy(exact), 'after_row': deepcopy(exact),
            'before_query_started_at': 100.1, 'before_query_finished_at': 100.2,
            'after_query_started_at': 102.1, 'after_query_finished_at': 102.2}}
    return {'closure': closure, 'snapshot': snapshot, 'predecessor': roles, 'primary_stop_source': roles['primary_stop'],
        'dvc_pointer': pointer, 'runtime': runtime, 'origin_actor': closure['actor']}


def descriptor(root, actual):
    return {'schema': source.CACHE_SCHEMA,
        'core_sha256': hashlib.sha256(source._encode(actual)).hexdigest(), 'refs': actual['predecessor'],
        'source_index_source': actual['closure']['source_index_source'], 'carry_source': ref(root, 'evidence/ui174/predecessor_ui173.json'),
        'dvc_pointer': actual['dvc_pointer'], 'pointer_raw_hex': '00'}


def test_small_descriptor_and_runtime_bind_latest_stopped_snapshot(tmp_path):
    value = core(tmp_path)
    source._runtime_core(value, tmp_path)
    desc = descriptor(tmp_path, value)
    assert source._descriptor(desc, root=tmp_path) == desc
    compact = source.compact_authority(value, ref(tmp_path, 'evidence/ui174/resume/authority.json'), root=tmp_path)
    assert compact['schema'] == source.RUNTIME_SCHEMA
    assert compact['core']['closure']['phase'] == stopped.PHASE
    assert not {'graph', 'values', 'journals', 'data'} & set(desc)


@pytest.mark.parametrize('fault', ['invented_ticks', 'invented_game_lifetime', 'ordinary_logout', 'admission',
    'changed_precision', 'late_precision', 'missing_stop_check', 'wrong_primary_stop', 'bool_pid', 'peer_changed'])
def test_runtime_rejects_relabeling_inexact_precision_and_unobserved_stop_facts(tmp_path, fault):
    value = core(tmp_path)
    c = value['closure']
    if fault == 'invented_ticks': c['game_start_ticks'] = '123'
    elif fault == 'invented_game_lifetime': c['game_before'] = {'pid': 999, 'start_ticks': '123'}
    elif fault == 'ordinary_logout': c['normal_logout_input_sent'] = True
    elif fault == 'admission': c['operations_admitted'] = 1
    elif fault == 'changed_precision': c['exact_precision']['after_row']['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'late_precision': c['exact_precision']['after_query_finished_at'] = 103
    elif fault == 'missing_stop_check': c['stop_checks'].pop(next(iter(stopped.STOP_CHECKS)))
    elif fault == 'wrong_primary_stop': value['primary_stop_source'] = value['predecessor']['closure']
    elif fault == 'bool_pid': c['owned_game_identity']['pid'] = True
    else: value['snapshot']['3']['saved']['skills'] = [[1, 1, 1]]
    with pytest.raises(RuntimeError): source._runtime_core(value, tmp_path)


@pytest.mark.parametrize('fault', ['extra_graph', 'wrong_schema', 'missing_ref', 'foreign_checkpoint', 'future_remote', 'big_descriptor'])
def test_descriptor_is_distinct_bounded_and_has_exact_actual_publication_roles(tmp_path, fault):
    desc = descriptor(tmp_path, core(tmp_path))
    if fault == 'extra_graph': desc['graph'] = {}
    elif fault == 'wrong_schema': desc['schema'] = 'client442_bag_swap_fresh_predecessor_authority_v1'
    elif fault == 'missing_ref': desc['refs'].pop('checkpoint')
    elif fault == 'foreign_checkpoint': desc['refs']['checkpoint']['path'] = str(tmp_path / 'evidence/other/checkpoint_receipt.json')
    elif fault == 'future_remote': desc['refs']['remote']['path'] = str(tmp_path / stopped.BATCH / 'future_remote.json')
    else: desc['pointer_raw_hex'] = '00' * source.MAX_DESCRIPTOR_BYTES
    with pytest.raises(RuntimeError): source._descriptor(desc, root=tmp_path)


class Store:
    def __init__(self, root): self.root, self.values = root, {}
    def add(self, member, value):
        result = ref(self.root, member, hashlib.sha256(source._encode(value)).hexdigest())
        self.values[result['path']] = value
        return result
    def get(self, result, successful=True): return self.values[result['path']]


def epoch_fixture(tmp_path):
    repo = tmp_path / 'repo'
    store = Store(tmp_path)
    previous_rows = [{'path': str(repo / member), 'sha256': hashlib.sha256(raw).hexdigest()}
        for member, raw in (('experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json', b'old config'),
            ('tools/client_compatibility/untouched.py', b'unchanged'))]
    previous = {'schema': stopped.EPOCH_SCHEMA, 'code_commit': 'b' * 40,
        'committed_sources': sorted(previous_rows, key=lambda r: r['path']), 'carried_sources': []}
    closure = {'code_commit': 'b' * 40, 'committed_sources': previous['committed_sources'], 'code_source_epoch': previous}
    wanted = sorted(set(str(Path(r['path']).relative_to(repo)) for r in previous_rows) |
        set(source.NEW_FILES) | set(source.INDEXED_DEPENDENCIES))
    originals, copies = [], []
    for i, member in enumerate(wanted):
        raw = b'old config' if member.endswith('442_bag_swap_roundtrip_v1.json') else b'unchanged' if member.endswith('untouched.py') else member.encode()
        sha = hashlib.sha256(raw).hexdigest()
        originals.append({'path': str(repo / member), 'sha256': sha})
        copies.append(store.add('evidence/ui174/code/' + str(i) + '.json', {'schema': stopped.CODE_SCHEMA,
            'code_commit': 'd' * 40, 'original_path': str(repo / member), 'sha256': sha, 'bytes': len(raw), 'raw_hex': raw.hex()}))
    epoch = {'schema': source.EPOCH_SCHEMA, 'code_commit': 'd' * 40, 'committed_sources': originals, 'carried_sources': copies}
    epoch_ref = store.add('evidence/ui174/code/epoch.json', epoch)
    remote_ref = store.add('evidence/ui173_remote.json', {'proof': {'code_epochs': {'code_commit': 'b' * 40}}})
    ready = {'current_code_epoch_source': epoch_ref, 'predecessor': {'remote': remote_ref},
        'code_commit': epoch['code_commit'], 'committed_sources': originals}
    return store, closure, ready, {'current_code_epoch_source': epoch_ref}, epoch


def test_indexed_epoch_extends_validated_publication_and_contains_all_six_causal_sources(tmp_path):
    store, closure, ready, resume, epoch = epoch_fixture(tmp_path)
    result = source.validate_current_code_epoch(store, resume, ready, closure)
    assert result['predecessor_publication_code_commit'] == 'b' * 40
    assert set(source.INDEXED_DEPENDENCIES) <= {str(Path(r['path']).relative_to(tmp_path / 'repo')) for r in epoch['committed_sources']}


@pytest.mark.parametrize('fault', ['publication_reused', 'stale_publication', 'missing_source', 'extra_source', 'unrelated_changed',
    'wrong_envelope', 'wrong_resume', 'wrong_schema'])
def test_indexed_epoch_rejects_publication_reuse_missing_sources_and_unrelated_change(tmp_path, fault):
    store, closure, ready, resume, epoch = epoch_fixture(tmp_path)
    if fault == 'publication_reused': epoch['code_commit'] = ready['code_commit'] = 'b' * 40
    elif fault == 'stale_publication': store.get(ready['predecessor']['remote'], False)['proof']['code_epochs']['code_commit'] = 'a' * 40
    elif fault == 'missing_source': epoch['committed_sources'].pop()
    elif fault == 'extra_source': epoch['committed_sources'].append({'path': str(tmp_path / 'repo/zz_extra.py'), 'sha256': 'a' * 64})
    elif fault == 'unrelated_changed': next(r for r in epoch['committed_sources'] if r['path'].endswith('untouched.py'))['sha256'] = 'f' * 64
    elif fault == 'wrong_envelope': store.get(epoch['carried_sources'][0], False)['raw_hex'] = '00'
    elif fault == 'wrong_resume': resume['current_code_epoch_source'] = ready['predecessor']['remote']
    else: epoch['schema'] = 'client442_bag_swap_current_code_epoch_v1'
    with pytest.raises(RuntimeError): source.validate_current_code_epoch(store, resume, ready, closure)


def test_missing_actual_publication_pins_cannot_start_source_admission(tmp_path):
    with pytest.raises(RuntimeError): source.admission_pins(None, root=tmp_path)


def test_stable_reader_hashes_exact_decoded_bytes_with_one_open(tmp_path, monkeypatch):
    path = tmp_path / 'evidence/pins.json'
    path.parent.mkdir()
    raw = source._encode({'value': 'original'})
    path.write_bytes(raw)
    expected = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    original = Path.open
    opens = []
    def counted(target, *args, **kwargs):
        if target == path: opens.append(args[0] if args else kwargs.get('mode', 'r'))
        return original(target, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', counted)
    monkeypatch.setattr(source, 'bound', lambda *a: pytest.fail('independent hash opens cannot bind decoded bytes'))
    value, actual = source._json_file(path, 1024, root=tmp_path, expected_ref=expected)
    assert value == {'value': 'original'} and actual == expected and opens == ['rb']


@pytest.mark.parametrize('mutation', ['B_then_A', 'grow', 'shrink', 'replace_inode'])
def test_stable_reader_rejects_read_time_mutation_before_decode(tmp_path, monkeypatch, mutation):
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as decoder
    path = tmp_path / 'evidence/pins.json'
    path.parent.mkdir()
    raw = source._encode({'value': 'original'})
    path.write_bytes(raw)
    expected = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    original = Path.open
    class Changed:
        def __init__(self, handle): self.handle = handle
        def __enter__(self): return self
        def __exit__(self, *args): self.handle.close()
        def fileno(self): return self.handle.fileno()
        def read(self, size):
            if mutation == 'replace_inode':
                replacement = path.with_name('replacement.json')
                replacement.write_bytes(raw)
                replacement.replace(path)
            elif mutation == 'grow': path.write_bytes(raw + b' ' * 1025)
            elif mutation == 'shrink': path.write_bytes(b'{}')
            else: path.write_bytes(source._encode({'value': 'modified'}))
            got = self.handle.read(size)
            if mutation == 'B_then_A': path.write_bytes(raw)
            return got
    def opened(target, *args, **kwargs):
        handle = original(target, *args, **kwargs)
        return Changed(handle) if target == path and args == ('rb',) else handle
    monkeypatch.setattr(Path, 'open', opened)
    monkeypatch.setattr(decoder, '_json', lambda *a: pytest.fail('mutated raw file must reject before decode'))
    with pytest.raises(RuntimeError): source._json_file(path, 1024, root=tmp_path, expected_ref=expected)


def test_stable_reader_rejects_A_B_A_during_decode(tmp_path, monkeypatch):
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as decoder
    path = tmp_path / 'evidence/pins.json'
    path.parent.mkdir()
    raw = source._encode({'value': 'original'})
    path.write_bytes(raw)
    expected = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    original = decoder._json
    def changing(payload):
        value = original(payload)
        path.write_bytes(source._encode({'value': 'modified'}))
        path.write_bytes(raw)
        return value
    monkeypatch.setattr(decoder, '_json', changing)
    with pytest.raises(RuntimeError, match='changed while parsing'):
        source._json_file(path, 1024, root=tmp_path, expected_ref=expected)


def test_stable_reader_rejects_wrong_pinned_hash_before_decode(tmp_path, monkeypatch):
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as decoder
    path = tmp_path / 'evidence/pins.json'
    path.parent.mkdir()
    path.write_bytes(b'{"value":"modified"}')
    monkeypatch.setattr(decoder, '_json', lambda *a: pytest.fail('unpinned bytes cannot reach decoder'))
    with pytest.raises(RuntimeError, match='pinned source'):
        source._json_file(path, 1024, root=tmp_path, expected_ref={'path': str(path), 'sha256': 'a' * 64})


def preflight_fixture(tmp_path):
    value = core(tmp_path)
    pins = {}
    for key, raw in (
        ('closure', source._encode(value['closure'])),
        ('checkpoint', source._encode({'cloud_verified': True, 'file': source.POINTER.removesuffix('.dvc'),
            'bytes': 2048, 'sha256': 'c' * 64}))):
        path = Path(value['predecessor'][key]['path'])
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
        pins[key] = source.bound(path)
    remote = Path(value['predecessor']['remote']['path'])
    remote.parent.mkdir(parents=True, exist_ok=True)
    remote.write_bytes(b'{"entire_remote_proof_is_not_preflight":true}')
    pins['remote'] = source.bound(remote)
    repo = tmp_path / 'repo'
    pointer = repo / source.POINTER
    pointer.parent.mkdir(parents=True)
    pointer.write_text('outs:\n- md5: ' + 'b' * 32 + '\n  size: 2048\n  hash: md5\n  path: ' +
        Path(source.POINTER.removesuffix('.dvc')).name + '\n')
    return value, pins, repo


def test_preflight_reads_only_exact_pinned_small_core_and_pointer(tmp_path, monkeypatch):
    value, pins, repo = preflight_fixture(tmp_path)
    original = Path.open
    remote = Path(pins['remote']['path'])
    def opened(target, *args, **kwargs):
        if target == remote: pytest.fail('full remote proof cannot be decoded before current offline checks')
        return original(target, *args, **kwargs)
    monkeypatch.setattr(Path, 'open', opened)
    actual = source.preflight_bundle(*(pins[k]['path'] for k in ('closure','remote','checkpoint')),
        pins=pins, root=tmp_path, repo=repo)
    assert set(actual) == set(source.CORE_FIELDS)
    assert actual['snapshot'] == value['snapshot'] and actual['runtime'] == value['runtime']
    assert actual['predecessor'] == {**pins, 'primary_stop': value['primary_stop_source']}


@pytest.mark.parametrize('fault', ['closure_sha', 'checkpoint_sha', 'pointer_size', 'wrong_role_path'])
def test_preflight_rejects_stale_small_role_or_pointer_before_admission(tmp_path, fault):
    _, pins, repo = preflight_fixture(tmp_path)
    if fault.endswith('_sha'): pins[fault.removesuffix('_sha')]['sha256'] = 'f' * 64
    elif fault == 'pointer_size':
        pointer = repo / source.POINTER
        pointer.write_text(pointer.read_text().replace('size: 2048', 'size: 4096'))
    paths = [pins[k]['path'] for k in ('closure','remote','checkpoint')]
    if fault == 'wrong_role_path': paths[1] = str(tmp_path / 'evidence/other_remote.json')
    with pytest.raises(RuntimeError): source.preflight_bundle(*paths, pins=pins, root=tmp_path, repo=repo)


def test_checkpoint_provider_selection_uses_stable_pinned_runtime(tmp_path, monkeypatch):
    from tools.client_compatibility import checkpoint_bag_swap as checkpoint
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as decoder
    monkeypatch.setattr(source, 'ROOT', tmp_path)
    runtime = tmp_path / 'evidence/ui174/runtime_authority.json'
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(source._encode({'schema': source.RUNTIME_SCHEMA}))
    compact_ref = source.bound(runtime)
    authority = runtime.with_name('authority.json')
    authority.write_bytes(b'{}')
    ready = {'phase': 'bags_swap_scout_ready', 'authority_source': source.bound(authority),
        'runtime_authority_source': compact_ref}
    monkeypatch.setattr(checkpoint, 'closed', lambda *a: ready)
    # Replace after the ready pin is captured, without providing a new ref.
    runtime.write_bytes(source._encode({'schema': source.RUNTIME_SCHEMA}) + b' ' * source.MAX_RUNTIME_BYTES)
    monkeypatch.setattr(decoder, '_json', lambda *a: pytest.fail('oversized replacement cannot decode'))
    monkeypatch.setattr(continuation, 'authority_sources', lambda *a: pytest.fail('replacement cannot dispatch'))
    with pytest.raises(RuntimeError, match='one-MiB raw byte bound before decode'):
        checkpoint.carry(tmp_path / 'evidence/ui174', tmp_path / 'evidence/preparation.json')


def initialization_fixture(tmp_path):
    store = Store(tmp_path)
    old = core(tmp_path)
    commit = 'd' * 40
    captured = {'schema': 'client442_interaction_batch_v1', 'started_at': 104,
        'native_worldserver': deepcopy(old['runtime']['worldserver']), 'code_commit': commit}
    batch_ref = store.add('evidence/ui174/batch.json', captured)
    native_ref = store.add('evidence/ui174/native_server_before.json', deepcopy(old['runtime']['worldserver']))
    refs = {'batch_source': batch_ref, 'native_server_before_source': native_ref}
    resume = {'started_at': 105, 'code_commit': commit, **refs}
    resume_ref = store.add('evidence/ui174/resume/report.json', resume)
    epoch_ref = store.add('evidence/ui174/resume/epoch.json', {'schema': source.EPOCH_SCHEMA,
        'code_commit': commit})
    ready = {'started_at': 106, 'code_commit': commit, 'resume_source': resume_ref,
        'current_code_epoch_source': epoch_ref, **refs}
    return store, old, captured, resume, ready


def test_offline_indexed_proof_binds_prior_ordinary_initialization(tmp_path):
    from tools.client_compatibility import bag_swap_evidence as evidence
    store, old, captured, resume, ready = initialization_fixture(tmp_path)
    assert evidence.indexed_initialization(store, ready, resume, old) == {
        key: ready[key] for key in ('batch_source', 'native_server_before_source')}


@pytest.mark.parametrize('fault', ['missing', 'foreign_batch', 'native_changed', 'bool_pid',
    'late_capture', 'predecessor_capture', 'code_changed', 'epoch_changed', 'resume_ref_changed', 'extra_field'])
def test_offline_indexed_proof_rejects_uninitialized_or_reconstructed_originals(tmp_path, fault):
    from tools.client_compatibility import bag_swap_evidence as evidence
    store, old, captured, resume, ready = initialization_fixture(tmp_path)
    native = store.get(ready['native_server_before_source'], False)
    if fault == 'missing': ready.pop('batch_source')
    elif fault == 'foreign_batch': ready['batch_source'] = store.add('evidence/foreign/batch.json', captured)
    elif fault == 'native_changed': native['start_ticks'] = '999'
    elif fault == 'bool_pid': native['pid'] = True
    elif fault == 'late_capture': captured['started_at'] = ready['started_at']
    elif fault == 'predecessor_capture': captured['started_at'] = old['closure']['finished_at']
    elif fault == 'code_changed': captured['code_commit'] = 'e' * 40
    elif fault == 'epoch_changed': store.get(ready['current_code_epoch_source'], False)['code_commit'] = 'e' * 40
    elif fault == 'resume_ref_changed': resume['native_server_before_source'] = ready['batch_source']
    else: captured['reconstructed_after_experiment'] = True
    with pytest.raises(RuntimeError): evidence.indexed_initialization(store, ready, resume, old)


@pytest.mark.parametrize('schema', [source.CACHE_SCHEMA, source.RUNTIME_SCHEMA])
def test_unknown_renamed_local_authority_keeps_role_cap_before_decoder(tmp_path, monkeypatch, schema):
    from tools.client_compatibility import review_bag_swap_failed_checkpoint as decoder
    from tools.client_compatibility import bag_swap_evidence as evidence
    path = tmp_path / 'evidence/renamed_authority.json'
    path.parent.mkdir()
    path.write_bytes(source._encode({'schema': schema}) + b' ' * source.MAX_RUNTIME_BYTES)
    pinned = source.bound(path)
    monkeypatch.setattr(evidence.lab, 'ROOT', tmp_path)
    monkeypatch.setattr(decoder, '_json', lambda *a: pytest.fail('unbound renamed authority cannot decode over its role cap'))
    with pytest.raises(RuntimeError, match='exact raw byte bound before decode'):
        evidence.Sources({}, {}, local=True).get(pinned, False)


from tools.client_compatibility.world.tests.test_bag_swap_indexed_archive import carried


@pytest.mark.parametrize('consumer', ['provider', 'source_report', 'live_evidence'])
@pytest.mark.parametrize('replacement', ['schema_only_to_valid', 'same_semantics'])
def test_indexed_second_runtime_read_retains_original_compact_pin(carried, monkeypatch, consumer, replacement):
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    from tools.client_compatibility import bag_swap_evidence as evidence
    from tools.client_compatibility.world.tests.test_bag_swap_indexed_publication import runtime_fixture
    c, actual, path, full_ref, compact_path = runtime_fixture(carried)
    monkeypatch.setattr(source, 'ROOT', c['root'])
    monkeypatch.setattr(continuation.lab, 'ROOT', c['root'])
    # Even unchanged semantic JSON with different raw bytes must not replace
    # the selected report pin before the provider's second read.
    valid_raw = compact_path.read_bytes()
    raw_a = source._encode({'schema': source.RUNTIME_SCHEMA}) if replacement == 'schema_only_to_valid' else valid_raw
    compact_path.write_bytes(raw_a)
    compact_ref = source.bound(compact_path)
    raw_b = valid_raw if replacement == 'schema_only_to_valid' else raw_a + b' '
    original, calls = source.cached_runtime, []
    def replace_at_second_read(path, ref, **kwargs):
        assert kwargs.get('compact_ref') == compact_ref
        calls.append(kwargs['compact_ref'])
        compact_path.write_bytes(raw_b)
        return original(path, ref, **kwargs)
    if consumer == 'provider':
        compact_path.write_bytes(raw_b)
        with pytest.raises(RuntimeError, match='decoded JSON bytes differ'):
            original(compact_path, full_ref, root=c['root'], compact_ref=compact_ref)
    else:
        monkeypatch.setattr(source, 'cached_runtime', replace_at_second_read)
        selected = {'authority_source': full_ref, 'runtime_authority_source': compact_ref,
            'predecessor': actual['predecessor']}
        with pytest.raises(RuntimeError, match='decoded JSON bytes differ'):
            if consumer == 'source_report': continuation.source_report(selected)
            else: evidence.predecessor(evidence.Sources({}, {}, local=True), selected, live=True)
        assert calls == [compact_ref]


def test_indexed_pinned_runtime_accepts_exact_bytes_and_rejects_wrong_path(carried):
    from tools.client_compatibility.world.tests.test_bag_swap_indexed_publication import runtime_fixture
    c, value, _, full_ref, compact_path = runtime_fixture(carried)
    pin = source.bound(compact_path)
    assert source.cached_runtime(compact_path, full_ref, root=c['root'], compact_ref=pin) == value
    wrong = {**pin, 'path': str(c['batch'] / 'another_private_compact.json')}
    with pytest.raises(RuntimeError, match='exact source path'):
        source.cached_runtime(compact_path, full_ref, root=c['root'], compact_ref=wrong)

"""Mocked pure dispatch tests; no provider admission or operational action."""
from copy import deepcopy
from pathlib import Path
from types import ModuleType, SimpleNamespace
import sys
from unittest.mock import Mock

import pytest

from tools.client_compatibility import bag_swap_evidence as evidence
from tools.client_compatibility import checkpoint_bag_swap as checkpoint
from tools.client_compatibility import bag_swap_indexed_sources as indexed
from tools.client_compatibility import interaction_bag_swap_continuation as continuation

RUNTIME = 'client442_bag_swap_closed_logout_runtime_v1'
CACHE = 'client442_bag_swap_closed_logout_authority_v1'
CARRY = 'client442_bag_swap_closed_logout_ancestry_v1'
EPOCH = 'client442_bag_swap_closed_logout_code_epoch_v1'
CLOSURE = 'client442_bag_swap_closed_logout_boundary_v1'


def ref(path):
    return {'path': str(path), 'sha256': 'a' * 64}


@pytest.fixture
def provider(monkeypatch):
    value = ModuleType('tools.client_compatibility.bag_swap_closed_logout_sources')
    for name in ('validate_manifest', 'local_store', 'cached_bundle', 'validate_carry',
        'current_code_epoch', 'validate_current_code_epoch', 'validate_cache', 'cached_runtime', 'compact_authority'):
        setattr(value, name, Mock(name=name))
    monkeypatch.setitem(sys.modules, value.__name__, value)
    return value


def test_normal_manifest_unions_typed_views_without_historical_single_kind_substitution(provider):
    row = {'original_path': str(evidence.lab.ROOT / 'evidence/synthetic/original.json'),
        'sha256': 'a' * 64, 'copy_member': 'evidence/new/synthetic.blob', 'kinds': ['json', 'binary']}
    manifest = {'schema': CARRY, 'members': [row], 'authorities': []}
    store = evidence.Sources({'manifest': manifest}, {})
    identity = (row['original_path'], row['sha256'])
    assert store.logical_kinds[identity] == frozenset(('json', 'binary'))
    assert store.copy_kinds[(str(store.root / row['copy_member']), row['sha256'])] == frozenset(('json', 'binary'))
    store._json_view(ref(row['original_path']))
    provider.validate_manifest.assert_called_once_with(manifest, store.root)
    row['kinds'] = ['binary']
    store._refresh_maps()
    with pytest.raises(RuntimeError, match='JSON view'): store._json_view(ref(row['original_path']))


def test_new_descriptor_and_carry_use_one_and_sixteen_mib_limits():
    authority, carry = ref('/tmp/synthetic/authority.json'), ref('/tmp/synthetic/predecessor_ui176.json')
    store = evidence.Sources({'runtime': {'schema': RUNTIME, 'authority_source': authority},
        'cache': {'schema': CACHE, 'carry_source': carry}}, {})
    assert store._json_limit(authority) == 1024 * 1024
    assert store._json_limit(carry) == 16 * 1024 * 1024


def test_local_store_routes_existing_normal_manifest_before_legacy_walk(monkeypatch, provider):
    directory = Path('/tmp/synthetic')
    monkeypatch.setattr(Path, 'is_file', lambda path: path == directory / 'predecessor_ui176.json')
    marker = object()
    provider.local_store.return_value = marker
    assert evidence.local_store(directory) is marker
    provider.local_store.assert_called_once_with(directory)


def test_epoch_dispatch_preserves_fresh_epoch_inputs(provider):
    store, resume, ready = object(), {'code_commit': 'c' * 40}, {'code_commit': 'c' * 40}
    old = {'closure': {'schema': CLOSURE, 'code_commit': 'b' * 40}}
    marker = object()
    provider.validate_current_code_epoch.return_value = provider.current_code_epoch.return_value = marker
    assert evidence.current_code_epoch(store, resume, ready, old['closure']) is marker
    provider.validate_current_code_epoch.assert_called_once_with(store, resume, ready, old['closure'])
    directory = Path('/tmp/synthetic')
    assert checkpoint.current_code_epoch(directory, old) is marker
    provider.current_code_epoch.assert_called_once_with(directory, old)


def test_validate_carry_delegates_exact_store_and_ready(provider):
    ready = {'authority_source': ref('/tmp/synthetic/authority.json')}
    store = SimpleNamespace(get=Mock(return_value={'schema': CACHE}))
    marker = object()
    provider.validate_carry.return_value = marker
    assert checkpoint.validate_carry(store, ready) is marker
    provider.validate_carry.assert_called_once_with(store, ready)


@pytest.mark.parametrize('foreign_batch', [False, True])
def test_normal_carry_revalidates_bundle_then_exact_large_carry(monkeypatch, provider, foreign_batch):
    directory = Path('/tmp/synthetic')
    authority = ref(directory / 'authority.json')
    compact = ref(directory / 'runtime_authority.json')
    carry = ref((Path('/tmp/other') if foreign_batch else directory) / 'predecessor_ui176.json')
    ready = {'phase': 'bags_swap_scout_ready', 'authority_source': authority, 'runtime_authority_source': compact}
    monkeypatch.setattr(checkpoint, 'closed', lambda path: ready)
    monkeypatch.setattr(checkpoint, 'bound', lambda path: authority)
    monkeypatch.setattr(indexed, 'read_runtime_source', lambda value: {'schema': RUNTIME})
    monkeypatch.setattr(continuation, 'authority_sources', lambda schema: provider if schema == RUNTIME else None)
    manifest = {'schema': CARRY}
    reader = Mock(side_effect=[({'carry_source': carry}, authority), (manifest, carry)])
    monkeypatch.setattr(indexed, '_json_file', reader)
    if foreign_batch:
        with pytest.raises(RuntimeError, match='another batch'): checkpoint.carry(directory, '/tmp/ready.json')
        assert reader.call_count == 1
    else:
        assert checkpoint.carry(directory, '/tmp/ready.json') is manifest
        assert reader.call_args_list[0].args == (authority['path'], 1024 * 1024)
        assert reader.call_args_list[0].kwargs == {'expected_ref': authority}
        assert reader.call_args_list[1].args == (carry['path'], 16 * 1024 * 1024)
        assert reader.call_args_list[1].kwargs == {'expected_ref': carry}
    provider.cached_bundle.assert_called_once_with(authority['path'])


@pytest.mark.parametrize('live', [False, True])
def test_predecessor_uses_full_store_or_compact_reference_and_v2_initialization(monkeypatch, provider, live):
    directory = evidence.lab.ROOT / 'evidence/synthetic'
    authority, runtime_ref, resume_ref = [ref(directory / name) for name in ('authority.json', 'runtime.json', 'resume.json')]
    previous = {name: {'pid': index + 10, 'start_ticks': str(index + 100)}
        for index, name in enumerate(('worldserver', 'modern_world', 'client'))}
    current = deepcopy(previous)
    current['client'] = {'pid': 99, 'start_ticks': '999'}
    old = {'runtime': previous, 'snapshot': {}, 'predecessor': {'closure': 'typed-ui176'},
        'dvc_pointer': {'oid': 'a' * 32}, 'closure': {'schema': CLOSURE, 'finished_at': 1.}}
    compact = {'schema': RUNTIME, 'core': old}
    ready = {'authority_source': authority, 'runtime_authority_source': runtime_ref,
        'resume_source': resume_ref, 'all_offline_snapshot': {}, 'predecessor': old['predecessor'],
        'predecessor_dvc_pointer': old['dvc_pointer'], 'actor': {'guid': 2}, 'runtime': current,
        'started_at': 4., 'native_session': 'native', 'selection_source': ref(directory / 'selection.json'),
        'realm_authentication': {'event': 'world_authenticated', 'account_id': 2, 'session': 'native', 'time': 3.5}}
    resume = {'schema': 'client442_bag_swap_scout_resume_v1', 'phase': 'bags_swap_scout_launched',
        'completed': True, 'failure': None, 'installed': True, 'authority_source': authority,
        'runtime_authority_source': runtime_ref, 'predecessor': old['predecessor'],
        'all_offline_snapshot': {}, 'origin_actor': ready['actor'], 'runtime': current, 'previous_runtime': previous,
        'available_memory_kib_before': 6 * 1024 * 1024, 'started_at': 2., 'launch_finished_at': 3.,
        'checks': dict.fromkeys(('native_unchanged', 'bridge_unchanged', 'fresh_scout', 'all_six_saved_snapshots',
            'primary_stopped', 'HDMI_1', 'private_input'), True)}
    cache = {'schema': CACHE}
    def get(reference, successful=True):
        return {authority['path']: cache, runtime_ref['path']: compact, resume_ref['path']: resume}[reference['path']]
    store = SimpleNamespace(local=live, get=Mock(side_effect=get))
    monkeypatch.setattr(continuation, 'authority_sources', lambda schema: provider if schema == RUNTIME else None)
    monkeypatch.setattr(continuation, 'read_runtime_authority', lambda reference: compact)
    monkeypatch.setattr(evidence, 'bound', lambda path: runtime_ref)
    epoch, initialization = Mock(), Mock()
    monkeypatch.setattr(evidence, 'current_code_epoch', epoch)
    monkeypatch.setattr(evidence, 'indexed_initialization', initialization)
    monkeypatch.setattr(evidence.shared, 'screen_review', lambda *args: {'selected_character': 'Harnesstwo', 'selected_level': 1})
    provider.validate_cache.return_value = provider.cached_runtime.return_value = old
    provider.compact_authority.return_value = compact
    assert evidence.predecessor(store, ready, live=live) is old
    if live:
        provider.cached_runtime.assert_called_once_with(runtime_ref['path'], authority, compact_ref=runtime_ref)
        provider.validate_cache.assert_not_called()
    else:
        provider.validate_cache.assert_called_once_with(cache, store=store)
        provider.cached_runtime.assert_not_called()
    epoch.assert_called_once_with(store, resume, ready, old['closure'])
    initialization.assert_called_once_with(store, ready, resume, old)


def test_current_initialization_accepts_new_typed_epoch_and_requires_exact_current_commit():
    directory = evidence.lab.ROOT / 'evidence/synthetic'
    batch_ref, native_ref, epoch_ref = [ref(directory / name) for name in ('batch.json', 'native_server_before.json', 'epoch.json')]
    native = {'pid': 10, 'start_ticks': '100'}
    common = {'batch_source': batch_ref, 'native_server_before_source': native_ref, 'code_commit': 'c' * 40}
    ready = {**common, 'resume_source': ref(directory / 'resume/resume.json'), 'started_at': 4., 'current_code_epoch_source': epoch_ref}
    resume = {**common, 'started_at': 3.}
    batch = {'schema': 'client442_interaction_batch_v1', 'started_at': 2., 'native_worldserver': native, 'code_commit': 'c' * 40}
    epoch = {'schema': EPOCH, 'code_commit': 'c' * 40}
    data = {batch_ref['path']: batch, native_ref['path']: native, epoch_ref['path']: epoch}
    store = SimpleNamespace(root=evidence.lab.ROOT, get=lambda reference, successful=True: data[reference['path']])
    old = {'runtime': {'worldserver': native}, 'closure': {'finished_at': 1.}}
    assert evidence.indexed_initialization(store, ready, resume, old) == {'batch_source': batch_ref, 'native_server_before_source': native_ref}
    epoch['code_commit'] = 'b' * 40
    with pytest.raises(RuntimeError, match='code epoch differs'): evidence.indexed_initialization(store, ready, resume, old)

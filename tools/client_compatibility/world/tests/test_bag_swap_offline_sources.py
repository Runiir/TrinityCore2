"""A crash authority preserves the indexed parent and explicit service epochs."""
from copy import deepcopy
import hashlib
import json

import pytest

from tools.client_compatibility import bag_swap_offline_sources as source
from tools.client_compatibility import bag_swap_evidence as evidence
from tools.client_compatibility import interaction_bag_swap_continuation as continuation
from tools.client_compatibility.world.tests.test_bag_swap_offline_boundary import case
from tools.client_compatibility.world.tests.test_bag_swap_indexed_sources import core, ref


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

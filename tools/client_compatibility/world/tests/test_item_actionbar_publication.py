"""Carry only the bounded, exact JSON ancestry needed by the admitted UI170 proof."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools.client_compatibility import checkpoint_item_actionbar as p
from tools.client_compatibility import item_actionbar_sources as s


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return s.bound(path)


def fixture(tmp_path):
    root = tmp_path / 'private'
    batch = root / 'evidence' / 'client_interactions_20990101_ui170'
    roles = {role: write(batch / role / 'episode.json', {'phase': 'hunter_fixture_' + role,
        'sources': []}) for role in s.ROLES}
    missing = {'path': str(root / 'evidence/ui168/absent/episode.json'), 'sha256': 'a' * 64}
    ignored = write(batch / 'ignored_metadata.json', {'ignored': True})
    prior = write(root / 'evidence/ui169/opaque/episode.json', {'source': missing, 'sources': [missing]})
    opaque_remote = write(batch / 'opaque_prior_remote.json', {'source': missing,
        'file_manifest': [{'path': 'relative/metadata.json', 'sha256': 'b' * 64}]})
    prior_cp = write(root / 'evidence/ui169/checkpoint_receipt.json', {'source': missing,
        'file_manifest': [{'path': 'not/a/graph/edge.json', 'sha256': 'b' * 64}]})
    resume = write(batch / 'resume/resume.json', {'checkpoint_source': prior_cp, 'sources': [prior]})
    roles['preparation'] = write(Path(roles['preparation']['path']), {'phase': 'await_owned_class_lobby_review',
        'accepted_previous_sources': [prior], 'remote_source': opaque_remote, 'sources': [resume]})
    entry = write(batch / 'entry/episode.json', {'fixture_source': roles['preparation'],
        'rest_baseline_source': roles['first_precision']})
    spawn = write(batch / 'spawn.json', {'source': missing, 'schema': 'read_only_spawn'})
    opened = write(batch / 'opened/episode.json', {'entry_source': entry, 'trainer_identity': {
        'entry_source': entry, 'spawn_source': spawn}})
    opening_review = write(batch / 'opened/review.json', {'source': opened, 'reviewed': True})
    selected = write(batch / 'selected/episode.json', {'source': opened, 'screen_review': {**opening_review,
        'frame': {'file': 'owned.png', 'sha256': 'c' * 64, 'metadata': ignored}}})
    train_review = write(batch / 'selected/review.json', {'source': selected, 'control': 'Train', 'reviewed': True})
    failed = write(batch / 'failed/episode.json', {'completed': False, 'failure': 'actual failed observation',
        'started_at': 10, 'finished_at': 11, 'source': selected, 'purchase_source': selected,
        'entry_source': entry, 'screen_review': {**train_review, 'frame': {'file': 'selected.png', 'sha256': 'd' * 64}}})
    roles['purchase'] = write(Path(roles['purchase']['path']), {'completed': True, 'failure': None,
        'started_at': 20, 'finished_at': 21, 'purchase_started_at': 10.2, 'purchase_finished_at': 10.3,
        'observation_settlement_source': failed, 'source': selected, 'purchase_source': selected,
        'entry_source': entry, 'baseline': {'entry_source': entry, 'rest_baseline_source': roles['first_precision'],
            'precision_source': roles['first_precision']},
        'trainer_identity': {'entry_source': entry, 'spawn_source': spawn},
        'screen_review': {**train_review, 'frame': {'file': 'selected.png', 'sha256': 'd' * 64}},
        'observation_reconciliation': {'source': failed, 'selected_source': selected},
        'reconciliation_preconditions': {'source': failed, 'selected_source': selected},
        'file_manifest': [ignored], 'frame': {'metadata': ignored}, 'unrelated_metadata': ignored})
    stop = write(root / 'evidence/ui155/stop/episode.json', {'source': missing})
    closure = write(batch / 'closure/episode.json', {'phase': 'hunter_learn_parked_boundary', 'sources': roles,
        'primary_stop_source': stop})
    pause = write(batch / 'pause/episode.json', {'source': closure, 'primary_stop_source': stop})
    remote = write(batch / 'remote.json', {'proof': {'operation': 'spellbook.learn_spell'}, 'source': missing,
        'file_manifest': [ignored]})
    checkpoint = write(batch / 'checkpoint_receipt.json', {'file_manifest': [ignored], 'source': missing})
    predecessor = {'closure': closure, 'pause': pause, 'remote': remote, 'checkpoint': checkpoint, 'primary_stop': stop}
    required = [*predecessor.values(), *roles.values(), prior, opaque_remote, prior_cp, resume, entry, spawn,
        opened, opening_review, selected, train_review, failed]
    expected = {r['path']: r['sha256'] for r in required}

    def resolver(ref):
        raw = Path(ref['path']).read_bytes()
        if hashlib.sha256(raw).hexdigest() != ref['sha256']:
            raise RuntimeError('actual source digest differs')
        return json.loads(raw)

    return root, predecessor, resolver, expected, ignored


def test_recursive_graph_keeps_reconciled_failed_selected_review_and_exact_nested_edges(tmp_path):
    root, predecessor, resolver, expected, ignored = fixture(tmp_path)
    result = p.source_graph(predecessor, resolver, root=root)
    assert {r['path']: r['sha256'] for r in result} == expected
    assert ignored['path'] not in {r['path'] for r in result}
    assert result == sorted(result, key=lambda r: r['path'])


def test_graph_can_be_rederived_from_portable_digest_checked_archive_values(tmp_path):
    root, predecessor, resolver, _, _ = fixture(tmp_path)
    refs = p.source_graph(predecessor, resolver, root=root)
    archive = {r['path']: (r['sha256'], resolver(r)) for r in refs}
    for ref in refs:
        Path(ref['path']).unlink()

    def portable(ref):
        digest, value = archive[ref['path']]
        if digest != ref['sha256']: raise RuntimeError('archive digest differs')
        return deepcopy(value)

    assert p.source_graph(predecessor, portable, root=root) == refs


@pytest.mark.parametrize('fault', ['missing', 'digest', 'conflict', 'missing_hash', 'extra_ref_field',
    'relative_path', 'outside', 'not_json', 'bad_screen', 'bad_container', 'bad_sources', 'bad_prior_list', 'cap', 'bool_cap'])
def test_graph_refuses_missing_changed_conflicting_malformed_or_unbounded_ancestry(tmp_path, fault):
    root, predecessor, resolver, _, _ = fixture(tmp_path)
    closure = resolver(predecessor['closure'])
    purchase_ref = closure['sources']['purchase']
    purchase = resolver(purchase_ref)
    target = purchase['entry_source']
    limit = 128
    if fault == 'missing': Path(target['path']).unlink()
    elif fault == 'digest': Path(target['path']).write_text('{"changed":true}')
    elif fault == 'conflict': purchase['baseline']['entry_source']['sha256'] = 'e' * 64
    elif fault == 'missing_hash': purchase['entry_source'].pop('sha256')
    elif fault == 'extra_ref_field': purchase['entry_source']['metadata'] = True
    elif fault == 'relative_path': purchase['entry_source']['path'] = 'evidence/entry.json'
    elif fault == 'outside': purchase['entry_source']['path'] = str(tmp_path / 'outside.json')
    elif fault == 'not_json': purchase['entry_source']['path'] = str(root / 'evidence/entry.png')
    elif fault == 'bad_screen': purchase['screen_review']['unknown'] = True
    elif fault == 'bad_container': purchase['trainer_identity'] = []
    elif fault == 'bad_sources': purchase['sources'] = {'arbitrary': target}
    elif fault == 'bad_prior_list': purchase['accepted_previous_sources'] = {'one': target}
    elif fault == 'cap': limit = 5
    else: limit = True
    if fault not in ('missing', 'digest', 'cap', 'bool_cap'):
        closure['sources']['purchase'] = write(Path(purchase_ref['path']), purchase)
        predecessor['closure'] = write(Path(predecessor['closure']['path']), closure)
        paused = resolver(predecessor['pause']); paused['source'] = predecessor['closure']
        predecessor['pause'] = write(Path(predecessor['pause']['path']), paused)
    with pytest.raises(RuntimeError): p.source_graph(predecessor, resolver, root=root, limit=limit)


def test_carry_preserves_raw_failed_bytes_original_refs_dedup_and_never_overwrites(tmp_path, monkeypatch):
    root, predecessor, resolver, expected, _ = fixture(tmp_path)
    batch = root / 'evidence/client_interactions_20990101_ui171'
    batch.mkdir()
    pointer_path = tmp_path / 'repo/artifacts/client_harness/442_interactions_20990101_170.tar.gz.dvc'
    pointer_path.parent.mkdir(parents=True)
    pointer_path.write_text('outs: []\n')
    pointer = {'source': s.bound(pointer_path), 'pointer': str(pointer_path.relative_to(tmp_path / 'repo')),
        'oid': 'f' * 32, 'bytes': 42}
    ready = write(batch / 'ready/episode.json', {'phase': 'item_actionbar_scout_ready', 'actor': {'guid': 2},
        'completed': True, 'failure': None, 'started_at': 30, 'finished_at': 31,
        'predecessor': predecessor, 'predecessor_dvc_pointer': pointer, 'all_offline_snapshot': {'mock': 'authority'}})
    monkeypatch.setattr(p.lab, 'ROOT', root)
    monkeypatch.setattr(s, 'ROOT', root)
    monkeypatch.setattr(s, 'source_bundle', lambda *args, **kwargs: {
        'snapshot': {'mock': 'authority'}, 'dvc_pointer': pointer})
    original = {path: Path(path).read_bytes() for path in expected}
    result = p.carry(batch, Path(ready['path']))
    assert {r['original_path']: r['sha256'] for r in result['sources']} == expected
    for row in result['sources']:
        assert Path(row['copy_path']).read_bytes() == original[row['original_path']]
        assert row['bytes'] == len(original[row['original_path']])
        assert Path(row['copy_path']).stat().st_mode & 0o777 == 0o600
    failed = next(r for r in result['sources'] if '/failed/' in r['original_path'])
    assert json.loads(Path(failed['copy_path']).read_text())['completed'] is False
    assert not any(Path(r['copy_path']).name == 'episode.json' for r in result['sources'])
    before = (batch / 'ancestry_manifest.json').read_bytes()
    with pytest.raises(RuntimeError): p.carry(batch, Path(ready['path']))
    assert (batch / 'ancestry_manifest.json').read_bytes() == before

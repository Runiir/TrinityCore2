"""Source-specific observation can navigate only after the paid outcome is proved."""
from copy import deepcopy
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_hunter_learn_reconciliation as reconcile


def originals(monkeypatch, fault='none'):
    actor, runtime = {'guid': 6}, {'worldserver': {'pid': 1}}
    selected_ref = {'path': '/private/selected/episode.json', 'sha256': 'selected'}
    prep_ref = {'path': '/private/preparation', 'sha256': 'preparation'}
    review_ref = {'path': '/private/selected/review.json', 'sha256': 'review'}
    frame = {'file': 'selected.png'}
    selected = {'actor': actor, 'runtime': runtime, 'native_session': 'hunter', 'fixture_source': prep_ref,
        'finished_at': 20, 'frame': frame}
    entry_ref = {'path': '/private/entry', 'sha256': 'entry'}
    snapshot = {'6': {'saved': {'spells': []}}}
    failed = {'actor': actor, 'runtime': runtime, 'native_session': 'hunter', 'fixture_source': prep_ref,
        'started_at': 22, 'finished_at': 40, 'purchase_source': selected_ref,
        'entry_source': entry_ref, 'baseline': {'snapshot': snapshot}, 'login_known_spell_ids': [1515],
        'book_layout_baseline': {}, 'pose_fixture': {}, 'trainer_identity': {}, 'native_catalog': {},
        'purchase_started_at': 30, 'purchase_finished_at': 35, 'purchase_packets': [],
        'trainer_identity_checked_at': 30, 'screen_review': {**review_ref, 'frame': frame},
        'cases': [{'id': 'spellbook.learn_spell.train1462', 'status': 'infrastructure_failure', 'error': 'original error'}]}
    review = {'reviewed': True, 'reviewed_at': 21, 'control': 'Train', 'frame': frame,
        'source': selected_ref, 'fixture_source_sha256': 'preparation'}
    entry = {key: value for key, value in selected.items() if key != 'frame'}
    if fault == 'runtime': failed['runtime'] = {'worldserver': {'pid': 2}}
    if fault == 'review': review['control'] = 'Other'
    if fault == 'chronology': failed['finished_at'] = 101
    def bound(path):
        return {'failed': reconcile.FAILED_SOURCE if fault != 'source' else {**reconcile.FAILED_SOURCE, 'sha256': 'wrong'},
            '/private/preparation': prep_ref, '/private/selected/review.json': review_ref}[str(path)]
    monkeypatch.setattr(reconcile, 'bound', bound)
    def private_json(path, episode=True):
        assert episode is (str(path) == 'failed'), 'separate Train review is not an episode'
        return deepcopy(failed if str(path) == 'failed' else review)
    monkeypatch.setattr(reconcile, 'private_json', private_json)
    monkeypatch.setattr(reconcile, 'linked', lambda ref: deepcopy(selected if ref == selected_ref else entry))
    monkeypatch.setattr(reconcile, 'baseline', lambda *args: ({'learn_offline_baseline': snapshot}, 'hunter'))
    persisted = []
    trial = SimpleNamespace(fixture=actor, receipt={'runtime': runtime, 'started_at': 100},
        persist=lambda: persisted.append(deepcopy(trial.receipt)))
    return trial, failed, selected, persisted


@pytest.mark.parametrize('fault', ['none', 'source', 'runtime', 'review', 'chronology'])
def test_original_observation_source_keeps_failed_train_case_and_original_clock(monkeypatch, fault):
    trial, failed, selected, persisted = originals(monkeypatch, fault)
    if fault != 'none':
        with pytest.raises(RuntimeError): reconcile.original(trial, '/private/preparation', 'failed')
        assert not persisted
        return
    reconcile.original(trial, '/private/preparation', 'failed')
    assert trial.receipt['started_at'] == 100 > failed['finished_at']
    assert trial.receipt['original_purchase_interval'] == [30, 35]
    assert trial.receipt['purchase_started_at'] == 30
    assert trial.receipt['original_case'] == failed['cases'][0]
    assert trial.receipt['purchase_input_sent'] is False and trial.receipt['input_sent'] is False
    assert trial.receipt['original_purchase_input_sent'] is True and trial.receipt['train_input_replayed'] is False
    assert 'cases' not in trial.receipt


@pytest.mark.parametrize('fault', ['none', 'before', 'after', 'validation'])
def test_observation_never_replays_gameplay_and_gates_caption_on_paid_authority(monkeypatch, fault):
    trial, failed, selected, _ = originals(monkeypatch)
    saved = {'spells': [[1462, 1, 0]]}
    proof = {'purchase_checks': {'one_exact_native_purchase': True}, 'after_saved': saved,
        'after_resources': {'money': 8062}, 'protected_checks': {'protected': True}, 'public_actionbar_after': {}}
    calls = []
    trial.clean_panels = lambda: calls.append('close')
    monkeypatch.setattr(reconcile, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: object()))
    def current(*args):
        label = args[-1]
        calls.append(label)
        if fault == ('before' if label.endswith('before') else 'after'):
            raise RuntimeError('unexpected actual paid state')
        return deepcopy(proof), {'lua_errors': {}, 'blocked_actions': {}}, {'file': label + '.png'}
    monkeypatch.setattr(reconcile, 'current', current)
    monkeypatch.setattr(reconcile, 'reconciled_known', lambda *args: {1515, 1462})
    def caption(t, learned, label, is_learned):
        assert learned == {1515, 1462} and is_learned is True
        calls.append('caption')
        t.receipt.setdefault('cases', []).append({'id': 'book.navigation', 'status': 'spellbook_navigation_pass'})
        return {'visible': True}, {'id': 1462}
    monkeypatch.setattr(reconcile, 'caption', caption)
    monkeypatch.setattr(reconcile, 'entries', lambda _: [])
    def validate(receipt, *args, **kwargs):
        calls.append('validate')
        if fault == 'validation': raise RuntimeError('actual journal differs')
        assert receipt['started_at'] == 100 and receipt['original_case'] == failed['cases'][0]
        assert receipt['finished_at'] == 110
        assert receipt['purchase_input_sent'] is False and receipt['train_input_replayed'] is False
        assert receipt['input_sent'] is True and receipt['gameplay_input_sent'] is False
    monkeypatch.setattr(reconcile, 'validate_observation_reconciliation', validate)
    monkeypatch.setattr(reconcile.time, 'time', lambda: 110)
    if fault != 'none':
        with pytest.raises(RuntimeError): reconcile.observe(trial, '/private/preparation', 'failed')
        if fault == 'before': assert calls == ['hunter_learn_reconciliation_before']
        return
    reconcile.observe(trial, '/private/preparation', 'failed')
    assert calls == ['hunter_learn_reconciliation_before', 'close', 'caption', 'close',
        'hunter_learn_reconciliation_after', 'validate']
    assert trial.receipt['completed'] is True and trial.receipt['phase'] == 'hunter_learn_transition_complete'
    assert trial.receipt['cases'] == [{'id': 'book.navigation', 'status': 'spellbook_navigation_pass'}]
    assert trial.receipt['book_navigation_input_sent'] is True and trial.receipt['mutation_sent'] is False
    assert trial.receipt['input_sent'] is True and trial.receipt['gameplay_input_sent'] is False


@pytest.mark.parametrize('fault', ['none', 'dead', 'combat', 'moving', 'health', 'cursor', 'targeting'])
def test_current_observation_rejects_nonidle_owner_before_any_book_input(monkeypatch, fault):
    state = {'cursor_info': {}, 'spell_targeting': False}
    movement = {'dead': False, 'in_combat': False, 'speed': 0, 'health_percent': 100}
    if fault == 'dead': movement['dead'] = True
    if fault == 'combat': movement['in_combat'] = True
    if fault == 'moving': movement['speed'] = 1
    if fault == 'health': movement['health_percent'] = 99
    if fault == 'cursor': state['cursor_info'] = ['spell', 1462]
    if fault == 'targeting': state['spell_targeting'] = True
    calls = []
    frame = {'movement': movement}
    failed = {'cases': [{'after_frame': {'movement': {'health_percent': 100}}}]}
    trial = SimpleNamespace(observe=lambda _: (state, frame))
    original_saved = {'spells': [[1462, 1, 0]]}
    monkeypatch.setattr(reconcile, 'bar_detail', lambda *args: calls.append('public') or {'actual': True})
    monkeypatch.setattr(reconcile, 'saved', lambda _: deepcopy(original_saved))
    monkeypatch.setattr(reconcile, 'known', lambda _: deepcopy(original_saved['spells']))
    monkeypatch.setattr(reconcile, 'resources', lambda _: {'money': 8062})
    monkeypatch.setattr(reconcile, 'protected', lambda _: {'protected': True})
    monkeypatch.setattr(reconcile, 'entries', lambda _: [{'name': 'actual journal row'}])
    monkeypatch.setattr(reconcile.time, 'time', lambda: 110)
    def authority(*args, **kwargs):
        calls.append('authority')
        assert kwargs['state'] == state and kwargs['observed_until'] == 110
        assert kwargs['rows'] == [{'name': 'actual journal row'}]
        return {'checked_at': 110}
    monkeypatch.setattr(reconcile, 'observation_reconciliation', authority)
    if fault == 'none':
        proof, observed, observed_frame = reconcile.current(trial, {}, 'hunter', failed, {}, {},
            SimpleNamespace(poll=lambda: object()), 'current')
        assert proof == {'checked_at': 110} and observed == state and observed_frame == frame
        assert calls == ['public', 'authority']
    else:
        with pytest.raises(RuntimeError, match='idle living owner'):
            reconcile.current(trial, {}, 'hunter', failed, {}, {}, SimpleNamespace(poll=lambda: object()), 'current')
        assert calls == []

"""Offline1462 cleanup cannot repair unrelated state or bypass an ordinary logout."""
from copy import deepcopy
import json
import struct
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_hunter_learn_cleanup as cleanup
from tools.client_compatibility.hunter_learn_contract import BASE_SPELLS, cleanup_expected
from tools.client_compatibility.hunter_rest_accrual import float32, native_rest


@pytest.fixture
def state():
    before = {str(g): {'native': {'guid': g, 'account': 1 if g == 1 else 2, 'online': 0},
        'saved': {'spells': [], 'skills': [], 'actions': [],
            'quests': {'character_queststatus': [], 'character_queststatus_rewarded': []}}, 'pets': [], 'inventory': []}
        for g in range(1, 7)}
    h = before['6']
    h['native'].update(name='Harnesshunt', race=1, **{'class': 3}, level=10, xp=45, money=8708,
        rest_bonus=150.0, logout_time=20, is_logout_resting=0, totaltime=50, leveltime=40, latency=1,
        position_x=1.0, position_y=2.0, position_z=3.0, orientation=4.0, map=0)
    h['saved']['spells'] = deepcopy(BASE_SPELLS)
    h['saved']['actions'] = [[0, 0, 1515, 0]]
    h['pets'] = [{'id': n, 'owner': 6, 'CreatedBySpell': 13481, 'curhealth': 278,
        'savetime': 10, 'name': 'Harnesswolf' if n == 4 else 'Wolf'} for n in (4, 16)]
    current = deepcopy(before)
    exact, text = native_rest(150.0, 80, 7600, 1)
    current['6']['native'].update(money=8062, rest_bonus=text, logout_time=130, totaltime=80, leveltime=70)
    current['6']['saved']['spells'] = sorted(BASE_SPELLS + [[1462, 1, 0]])
    current['6']['pets'][1]['savetime'] = 120
    return before, current, exact


@pytest.fixture
def graph(tmp_path, monkeypatch, state):
    monkeypatch.setattr(cleanup.lab, 'ROOT', tmp_path)
    native = {k: {'pid': i, 'start_ticks': str(i)} for i, k in enumerate(('worldserver', 'modern_world', 'client'), 1)}
    monkeypatch.setattr(cleanup, 'runtime', lambda: deepcopy(native))
    monkeypatch.setattr(cleanup, 'identity', lambda k: deepcopy(native[k]))
    rest_sources = {'rate': 1, 'config_source': {'path': 'config', 'sha256': 'stable'},
        'native_formula_source': {'path': 'formula', 'sha256': 'stable'}, 'native_float_storage_sources': []}
    monkeypatch.setattr(cleanup.preservation, 'rest_sources', lambda: deepcopy(rest_sources))
    before, current, exact = deepcopy(state)
    hunter = {'guid': 6, 'account_id': 2, 'character_name': 'Harnesshunt', 'race': 1, 'class': 3, 'level': 10}
    origin = {'guid': 2, 'account_id': 2, 'character_name': 'Harnesstwo', 'race': 1, 'class': 1, 'level': 1}
    def write(name, value, started, finished):
        path = tmp_path / 'evidence' / name / 'episode.json'
        path.parent.mkdir(parents=True, exist_ok=True)
        body = {'completed': True, 'failure': None, 'started_at': started, 'finished_at': finished,
            'runtime': native, 'actor': hunter, **value}
        path.write_text(json.dumps(body))
        return path
    prep = write('prep', {'phase': 'await_owned_class_lobby_review', 'actor': origin, 'origin_actor': origin,
        'class_actor': hunter, 'learn_offline_baseline': before,
        'protected_baseline': {str(g): before[str(g)] for g in range(1, 6)}}, 1, 2)
    def exact_row(snapshot, exact_value):
        native_hunter = snapshot['6']['native']
        keys = ('guid', 'account', 'name', 'class', 'level', 'xp', 'online', 'rest_bonus', 'logout_time', 'is_logout_resting')
        return {**{k: native_hunter[k] for k in keys}, 'exact_rest_bonus': exact_value,
            'exact_rest_bonus_float32_bits': struct.pack('<f', exact_value).hex()}
    def precision(name, source, snapshot, value, started, finished):
        return write(name, {'phase': 'hunter_learn_rest_precision_complete', 'source': cleanup.bound(source),
            'sources': [cleanup.bound(source)], 'query': cleanup.preservation.PRECISION_QUERY,
            'input_sent': False, 'mutation_sent': False, 'qualification_added': False,
            'before': snapshot, 'after': deepcopy(snapshot), 'row': exact_row(snapshot, value),
            'rest_sources': rest_sources, 'checks': {k: True for k in cleanup.PRECISION_CHECKS}}, started, finished)
    exact_before = precision('exact_before', prep, before, 150.0, 3, 4)
    reload = {'owner': 6, 'pet_number': 16, 'created_by_spell': 13481, 'health': 278,
        'native_reload_source_verified': True}
    entry = write('entry', {'phase': 'owned_class_entered', 'fixture_source': cleanup.bound(prep),
        'native_session': 'session', 'native_before_entry': before['6']['native'],
        'entered_native': {**before['6']['native'], 'online': 1},
        'rest_baseline_source': cleanup.bound(exact_before), 'native_pet_reload': reload,
        'state': {'xp_max': 7600, 'xp': 45, 'level': 10, 'player': 'Harnesshunt', 'xp_exhaustion': 2 * int(exact)},
        'login_packets': [{'name': 'CMSG_PLAYER_LOGIN', 'direction': 'to_native', 'session': 'session', 'time': 100.1},
            {'name': 'SMSG_LOGIN_VERIFY_WORLD', 'direction': 'from_native', 'session': 'session', 'time': 100.2}]}, 99, 101)
    baseline = {'snapshot': before, 'saved': before['6']['saved'], 'entry_source': cleanup.bound(entry),
        'rest_baseline_source': cleanup.bound(exact_before), 'native_pet_reload': reload}
    purchase = write('purchase', {'phase': 'hunter_learn_transition_complete', 'baseline': baseline,
        'entry_source': cleanup.bound(entry), 'fixture_source': cleanup.bound(prep),
        'pose_fixture': {'before': [1.0, 2.0, 3.0, 4.0, 0]}, 'native_session': 'session',
        'after_saved': current['6']['saved'], 'purchase_checks': {str(i): True for i in range(10)}}, 102, 103)
    restore = write('restore', {'phase': 'hunter_learn_online_restored', 'baseline': baseline,
        'entry_source': cleanup.bound(entry), 'fixture_source': cleanup.bound(prep), 'native_session': 'session',
        'purchase_source': cleanup.bound(purchase), 'book_layout_restored': {'page': 1},
        'pose_restoration': {'restored': [1.0, 2.0, 3.0, 4.0, 0], 'checks': {'restored': True}},
        'after_saved': current['6']['saved']}, 104, 105)
    packets = [{'name': name, 'direction': direction, 'body': body, 'time': when, 'session': 'session'}
        for name, direction, body, when in [('CMSG_LOGOUT_REQUEST', 'to_native', '', 120),
            ('SMSG_LOGOUT_COMPLETE', 'from_native', '', 130), ('SMSG_LOGOUT_COMPLETE', 'to_client', '00', 130.1)]]
    park = write('park', {'phase': 'await_original_selection_review', 'fixture_source': cleanup.bound(prep),
        'source': cleanup.bound(restore), 'entry_source': cleanup.bound(entry), 'baseline': baseline,
        'rest_baseline_source': cleanup.bound(exact_before), 'native_pet_reload': reload,
        'native_session': 'session', 'logout_packets': packets, 'logout_started_at': 119, 'logout_finished_at': 131,
        'all_offline_snapshot': current, 'checks': {k: True for k in cleanup.PARK_CHECKS}}, 119, 132)
    exact_after = precision('exact_after', park, current, exact, 133, 134)
    monkeypatch.setattr(cleanup, 'snapshot', lambda: deepcopy(current))
    return {'before': before, 'current': current, 'prep': prep, 'purchase': purchase, 'restore': restore,
        'park': park, 'exact_before': exact_before, 'exact_after': exact_after, 'write': write,
        'exact_row': exact_row, 'rest_sources': rest_sources, 'native': native, 'tmp': tmp_path}


def test_closed_parking_proof_uses_actual_float_bits_without_reconstruction(graph):
    proof = cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])
    assert proof['matches'][0]['offline_seconds'] == 80
    assert proof['rounded_baseline_reconstruction'] is False
    assert proof['rest_sources'] == graph['rest_sources']


@pytest.mark.parametrize('fault', ['creator_health', 'new_saved_row', 'money', 'inventory', 'protected_actor',
    'rest_bonus', 'exact_bits', 'source_hash', 'formula_hash', 'missing_logout', 'duplicate_logout', 'delivery_body'])
def test_whole_parking_rejects_unsupported_delta_or_forged_ancestry(graph, fault):
    park = json.loads(graph['park'].read_text())
    after = json.loads(graph['exact_after'].read_text())
    if fault == 'creator_health': park['all_offline_snapshot']['6']['pets'][1]['curhealth'] = 279
    elif fault == 'new_saved_row': park['all_offline_snapshot']['6']['saved']['spells'].append([883, 1, 0])
    elif fault == 'money': park['all_offline_snapshot']['6']['native']['money'] += 1
    elif fault == 'inventory': park['all_offline_snapshot']['6']['inventory'].append([1])
    elif fault == 'protected_actor': park['all_offline_snapshot']['1']['native']['online'] = 1
    elif fault == 'rest_bonus': park['all_offline_snapshot']['6']['native']['rest_bonus'] += 1
    elif fault == 'exact_bits': after['row']['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'source_hash': park['entry_source']['sha256'] = '0' * 64
    elif fault == 'formula_hash': after['rest_sources']['config_source']['sha256'] = 'changed'
    elif fault == 'missing_logout': park['logout_packets'].pop()
    elif fault == 'duplicate_logout': park['logout_packets'].append(deepcopy(park['logout_packets'][0]))
    else: park['logout_packets'][2]['body'] = ''
    if fault not in ('exact_bits', 'formula_hash'):
        after['before'] = deepcopy(park['all_offline_snapshot'])
        after['after'] = deepcopy(after['before'])
    graph['park'].write_text(json.dumps(park))
    after['source'] = cleanup.bound(graph['park'])
    after['sources'] = [after['source']]
    graph['exact_after'].write_text(json.dumps(after))
    with pytest.raises(RuntimeError):
        cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])


def test_source_rewrites_are_never_used_to_repair_a_float_observation(graph):
    body = graph['exact_before'].read_bytes()
    row = json.loads(body)
    row['row']['exact_rest_bonus'] = float32(150.001)
    graph['exact_before'].write_text(json.dumps(row))
    changed = graph['exact_before'].read_bytes()
    with pytest.raises(RuntimeError): cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])
    assert graph['exact_before'].read_bytes() == changed


def test_restoration_can_remove_the_purchase_automatic_action_before_park(graph):
    purchase = json.loads(graph['purchase'].read_text())
    purchase['after_saved']['actions'].append([0, 1, 1462, 0])
    graph['purchase'].write_text(json.dumps(purchase))
    restore = json.loads(graph['restore'].read_text())
    restore['purchase_source'] = cleanup.bound(graph['purchase'])
    graph['restore'].write_text(json.dumps(restore))
    park = json.loads(graph['park'].read_text())
    park['source'] = cleanup.bound(graph['restore'])
    graph['park'].write_text(json.dumps(park))
    precision = json.loads(graph['exact_after'].read_text())
    precision['source'] = cleanup.bound(graph['park'])
    precision['sources'] = [precision['source']]
    graph['exact_after'].write_text(json.dumps(precision))
    assert cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])['matches']


def test_precision_is_read_only_and_does_not_construct_trial(graph, monkeypatch):
    current = graph['current']
    row = graph['exact_row'](current, json.loads(graph['exact_after'].read_text())['row']['exact_rest_bonus'])
    row.pop('exact_rest_bonus_float32_bits')
    calls = []
    class Query:
        description = [(k,) for k in row]
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, sql): calls.append(sql)
        def fetchall(self): return [tuple(row.values())]
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Query()
    monkeypatch.setattr(cleanup.lab, 'connection', Connection)
    monkeypatch.setattr(cleanup, 'Trial', lambda *args, **kwargs: pytest.fail('read-only precision created Trial'))
    result = cleanup.precision(graph['tmp'] / 'evidence' / 'new_precision', graph['park'])
    assert calls == [cleanup.preservation.PRECISION_QUERY]
    assert result['before'] == result['after'] == current
    assert result['input_sent'] is result['mutation_sent'] is False
    assert set(result['checks']) == set(cleanup.PRECISION_CHECKS)


def test_precision_rejects_online_snapshot_before_any_query(graph, monkeypatch):
    current = deepcopy(graph['current'])
    current['6']['native']['online'] = 1
    monkeypatch.setattr(cleanup, 'snapshot', lambda: current)
    monkeypatch.setattr(cleanup.lab, 'connection', lambda: pytest.fail('online precision attempted SQL'))
    with pytest.raises(RuntimeError): cleanup.precision(graph['tmp'] / 'evidence' / 'bad_precision', graph['park'])


def test_preflight_captures_native_prerequisites_without_input_or_trial(graph, monkeypatch):
    monkeypatch.setattr(cleanup, 'snapshot', lambda: deepcopy(graph['before']))
    monkeypatch.setattr(cleanup, 'native_prerequisites', lambda: {'sha256': 'exact-static-native-source'})
    monkeypatch.setattr(cleanup, 'Trial', lambda *args, **kwargs: pytest.fail('preflight created Trial'))
    result = cleanup.preflight(graph['tmp'] / 'evidence' / 'preflight', graph['prep'])
    assert result['before'] == result['after'] == graph['before']
    assert result['phase'] == 'hunter_learn_prerequisites_reviewed'
    assert result['input_sent'] is result['mutation_sent'] is False
    assert set(result['runtime']) == {'worldserver', 'modern_world'}


def test_unexplained_creator883_cannot_be_normalized_or_accepted(graph):
    park = json.loads(graph['park'].read_text())
    park['all_offline_snapshot']['6']['pets'][1]['CreatedBySpell'] = 883
    graph['park'].write_text(json.dumps(park))
    precise = json.loads(graph['exact_after'].read_text())
    precise['source'] = cleanup.bound(graph['park'])
    precise['sources'] = [precise['source']]
    precise['before'] = precise['after'] = park['all_offline_snapshot']
    graph['exact_after'].write_text(json.dumps(precise))
    with pytest.raises(RuntimeError): cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])


def test_normal_native_creator_normalization_is_read_only_noop(graph, monkeypatch):
    monkeypatch.setattr(cleanup.lab, 'connection', lambda: pytest.fail('unchanged creator attempted mutation SQL'))
    result = cleanup.normalize(graph['tmp'] / 'evidence' / 'noop_normalize', graph['prep'], graph['park'], graph['exact_after'])
    assert result['before'] == result['after'] == result['expected_after']
    assert result['normalized_columns'] == [] and result['mutation_sent'] is False
    assert set(result['checks']) == set(cleanup.NORMALIZE_CHECKS)


@pytest.fixture
def recovery(graph):
    from tools.client_compatibility.hunter_learn_contract import TRAINER_GUID, TRAINER, SPELL
    source = json.loads(graph['restore'].read_text())
    source['baseline']['resources'] = {'money': 8708, 'health': 222, 'mana': 100}
    failed = deepcopy(source)
    failed.update(completed=False, failure='RuntimeError: stock caption did not settle', phase='hunter_learn_purchase_started',
        purchase_input_sent=True, purchase_started_at=102.1, pose_fixture={'before': [1.0, 2.0, 3.0, 4.0, 0]})
    failed_path = graph['write']('failed', failed, 102, 103)
    # The explicit arguments belong to the new write; strip copied prior timestamps.
    failed['started_at'], failed['finished_at'] = 102, 103
    failed_path.write_text(json.dumps(failed))
    source.update(phase='hunter_learn_recovery_restored', failed_source=cleanup.bound(failed_path),
        purchase_source=cleanup.bound(failed_path), failed_whole_excluded=True, recovery_only=True,
        qualification_added=False, train_input_replayed=False, purchase_qualified=False,
        purchase_input_sent=True, purchase_started_at=102.1, after_resources={'money': 8062, 'health': 222, 'mana': 100},
        purchase_packets=[{'name': 'CMSG_TRAINER_BUY_SPELL', 'direction': 'to_native', 'time': 102.2,
            'session': 'session', 'body': struct.pack('<QII', TRAINER_GUID, TRAINER, SPELL).hex()},
            {'name': 'SMSG_LEARNED_SPELL', 'direction': 'from_native', 'time': 102.3,
                'session': 'session', 'body': struct.pack('<II', SPELL, 0).hex()}])
    source['started_at'], source['finished_at'] = 104, 105
    graph['restore'].write_text(json.dumps(source))
    park = json.loads(graph['park'].read_text())
    park.update(source=cleanup.bound(graph['restore']), baseline=source['baseline'], recovery_only=True,
        failed_whole_excluded=True, purchase_qualified=False, failed_source=source['failed_source'], train_input_replayed=False)
    graph['park'].write_text(json.dumps(park))
    precise = json.loads(graph['exact_after'].read_text())
    precise.update(source=cleanup.bound(graph['park']), sources=[cleanup.bound(graph['park'])])
    graph['exact_after'].write_text(json.dumps(precise))
    return graph, source, failed_path


def test_paid_failure_cleanup_proof_cannot_enter_success_path(recovery):
    graph, source, _ = recovery
    proof = cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'], recovery=True)
    assert proof['matches'][0]['offline_seconds'] == 80
    with pytest.raises(RuntimeError): cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])


@pytest.mark.parametrize('fault', ['paid_twice', 'different_spell', 'pet_cast', 'refunded_already',
    'qualification', 'replay', 'failed_hash', 'failed_admitted'])
def test_paid_recovery_refuses_replay_and_unrelated_or_admitted_failure(recovery, fault):
    graph, source, failed_path = recovery
    old = json.loads(graph['prep'].read_text())
    if fault == 'paid_twice': source['purchase_packets'].append(deepcopy(source['purchase_packets'][0]))
    elif fault == 'different_spell': source['purchase_packets'][1]['body'] = struct.pack('<II', 883, 0).hex()
    elif fault == 'pet_cast': source['purchase_packets'].append({'direction': 'to_native', 'name': 'CMSG_PET_ACTION'})
    elif fault == 'refunded_already': source['after_resources']['money'] = 8708
    elif fault == 'qualification': source['qualification_added'] = True
    elif fault == 'replay': source['train_input_replayed'] = True
    elif fault == 'failed_hash': source['failed_source']['sha256'] = '0' * 64
    else:
        failed = json.loads(failed_path.read_text())
        failed['completed'], failed['failure'] = True, None
        failed_path.write_text(json.dumps(failed))
        source['failed_source'] = source['purchase_source'] = cleanup.bound(failed_path)
    with pytest.raises(RuntimeError): cleanup.recovery_contract(source, cleanup.bound(graph['prep']), old)


def test_no_purchase_recovery_uses_zero_request_facts_even_after_intent_marker(recovery):
    graph, source, _ = recovery
    source.update(phase='hunter_learn_no_purchase_recovery_restored', no_purchase_observed=True,
        purchase_packets=[], after_saved=deepcopy(graph['before']['6']['saved']),
        after_resources=deepcopy(source['baseline']['resources']))
    paid, expected_saved, _ = cleanup.recovery_contract(source, cleanup.bound(graph['prep']), json.loads(graph['prep'].read_text()))
    assert paid is False and expected_saved == graph['before']['6']['saved']
    source['purchase_packets'].append({'name': 'CMSG_TRAINER_BUY_SPELL', 'direction': 'to_native'})
    with pytest.raises(RuntimeError):
        cleanup.recovery_contract(source, cleanup.bound(graph['prep']), json.loads(graph['prep'].read_text()))


def transaction_fixture(monkeypatch, before, expected):
    current = {'value': deepcopy(before), 'committed': deepcopy(before)}
    events = []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return self
        def execute(self, sql, args=None):
            events.append('mutation_sql')
            h = current['value']['6']
            if sql.startswith('DELETE'):
                rows = [r for r in h['saved']['spells'] if r == [1462, 1, 0]]
                self.rowcount = len(rows)
                h['saved']['spells'] = [r for r in h['saved']['spells'] if r not in rows]
            elif sql.startswith('UPDATE'):
                self.rowcount = int(h['native']['money'] == 8062 and h['native']['online'] == 0)
                if self.rowcount: h['native']['money'] = 8708
            else: pytest.fail('unexpected mutation statement')
        def begin(self): events.append('begin')
        def commit(self):
            events.append('commit')
            current['committed'] = deepcopy(current['value'])
        def rollback(self):
            events.append('rollback')
            current['value'] = deepcopy(current['committed'])
    monkeypatch.setattr(cleanup.lab, 'connection', Connection)
    monkeypatch.setattr(cleanup, 'snapshot', lambda: deepcopy(current['committed']))
    monkeypatch.setattr(cleanup, 'cursor_snapshot', lambda q: deepcopy(current['value']))
    return current, events


def test_transaction_commits_only_after_entire_exact_postcondition(monkeypatch, state):
    baseline, before, _ = state
    expected = cleanup_expected(baseline, before)
    current, events = transaction_fixture(monkeypatch, before, expected)
    def guard(): events.append('guard')
    def mutation(q):
        events.append('mutation')
        current['value'] = deepcopy(expected)
    after = cleanup.transaction(before, expected, guard, mutation)
    assert after == expected and after['6']['native']['money'] == 8708
    assert after['6']['native']['rest_bonus'] == before['6']['native']['rest_bonus']
    assert after['6']['pets'] == before['6']['pets']
    assert events == ['guard', 'begin', 'guard', 'mutation', 'guard', 'commit', 'guard']


@pytest.mark.parametrize('fault', ['stale_locked_state', 'wrong_postcondition', 'partial_mutation', 'source_changed', 'interrupt'])
def test_transaction_rolls_back_stale_state_partial_mutation_or_source_change(monkeypatch, state, fault):
    baseline, before, _ = state
    expected = cleanup_expected(baseline, before)
    current, events = transaction_fixture(monkeypatch, before, expected)
    guard_count = 0
    def guard():
        nonlocal guard_count
        guard_count += 1
        if fault == 'source_changed' and guard_count == 3: raise RuntimeError('immutable source changed')
    def mutation(q):
        current['value'] = deepcopy(expected)
        if fault == 'wrong_postcondition': current['value']['1']['saved']['actions'].append([1])
        if fault == 'partial_mutation': raise RuntimeError('refund did not match')
        if fault == 'interrupt': raise KeyboardInterrupt()
    if fault == 'stale_locked_state': current['value']['6']['native']['online'] = 1
    with pytest.raises((RuntimeError, KeyboardInterrupt)):
        cleanup.transaction(before, expected, guard, mutation)
    assert events == ['begin', 'rollback']
    assert current['value'] == current['committed'] == before


@pytest.mark.parametrize('failed_statement', [1, 2])
def test_cleanup_sql_demands_one_new_spell_and_one_exact_refund(failed_statement):
    class Query:
        rowcount = 1
        calls = []
        def execute(self, sql, args=None):
            self.calls.append((sql, args))
            self.rowcount = 0 if len(self.calls) == failed_statement else 1
    q = Query()
    with pytest.raises(RuntimeError): cleanup.cleanup_sql(q)
    assert len(q.calls) == failed_statement


def test_creator_sql_never_contains_a_health_update(state):
    _, before, _ = state
    for pet in before['6']['pets']:
        pet.update({k: 0 for k in cleanup.PET_COLUMNS if k not in pet})
    before['6']['pets'][1]['CreatedBySpell'] = 883
    expected = deepcopy(before)
    expected['6']['pets'][1]['CreatedBySpell'] = 13481
    class Query:
        rowcount = 1
        sql = None
        def execute(self, sql, args): self.sql = sql
    q = Query()
    cleanup.creator_sql(q, before, expected)
    set_clause = q.sql.split(' SET ', 1)[1].split(' WHERE ', 1)[0]
    assert set_clause == 'p.CreatedBySpell=13481'
    assert 'curhealth' in q.sql and 'online<>0' in q.sql


@pytest.fixture
def failed_commit(graph):
    rest = cleanup.parking_proof(graph['prep'], graph['park'], graph['exact_after'])
    before = graph['current']
    expected = cleanup_expected(graph['before'], before)
    refs = [cleanup.bound(graph[k]) for k in ('prep', 'purchase', 'restore', 'park', 'exact_after')]
    value = {'schema': 'client442_hunter_learn_offline_lifecycle_v1', 'completed': False,
        'failure': 'OperationalError: read failed after commit', 'phase': 'hunter_learn_offline_cleanup_started',
        'before': before, 'expected_after': expected, 'input_sent': False, 'mutation_sent': True,
        'qualification_added': False, 'sources': refs, 'preparation_source': refs[0], 'purchase_source': refs[1],
        'restoration_source': refs[2], 'park_source': refs[3], 'precision_source': refs[4],
        'creator_normalization_source': None, 'removed_spell': 1462, 'refunded_copper': 646,
        'native_rest_accrual_preserved': rest, 'commit_attempted': True, 'transaction_committed': True}
    path = graph['write']('failed_commit', value, 135, 136)
    return graph, path, expected


@pytest.mark.parametrize('acknowledged', [True, False])
def test_commit_settlement_is_read_only_and_never_replays_delete_or_refund(failed_commit, monkeypatch, acknowledged):
    graph, failed_path, expected = failed_commit
    value = json.loads(failed_path.read_text())
    value['transaction_committed'] = acknowledged
    failed_path.write_text(json.dumps(value))
    original = failed_path.read_bytes()
    monkeypatch.setattr(cleanup, 'snapshot', lambda: deepcopy(expected))
    monkeypatch.setattr(cleanup.lab, 'connection', lambda: pytest.fail('read-only settlement opened mutation connection'))
    monkeypatch.setattr(cleanup, 'cleanup_sql', lambda q: pytest.fail('settlement replayed refund'))
    result = cleanup.settle_clean(graph['tmp'] / 'evidence' / 'settled', failed_path)
    assert result['phase'] == 'hunter_learn_offline_cleaned' and result['after'] == expected
    assert result['mutation_sent'] is result['input_sent'] is False
    assert result['original_mutation_sent'] is result['settled_commit_only'] is True
    assert result['transaction_committed'] is True and result['commit_attempted'] is False
    assert result['sources'] == value['sources'] + [cleanup.bound(failed_path)]
    assert result['cleanup_failed_source'] == cleanup.bound(failed_path)
    assert failed_path.read_bytes() == original


@pytest.mark.parametrize('fault', ['no_commit_attempt', 'not_failed', 'wrong_phase', 'not_offline',
    'wrong_money', 'wrong_expected', 'source_hash', 'gameplay_mutation'])
def test_commit_settlement_refuses_uncommitted_or_unrelated_state(failed_commit, monkeypatch, fault):
    graph, failed_path, expected = failed_commit
    value = json.loads(failed_path.read_text())
    actual = deepcopy(expected)
    if fault == 'no_commit_attempt': value['commit_attempted'] = False
    elif fault == 'not_failed': value['completed'], value['failure'] = True, None
    elif fault == 'wrong_phase': value['phase'] = 'hunter_learn_recovery_cleanup_started'
    elif fault == 'not_offline': actual['6']['native']['online'] = 1
    elif fault == 'wrong_money': actual['6']['native']['money'] = 9354
    elif fault == 'wrong_expected': value['expected_after']['6']['native']['xp'] = 46
    elif fault == 'source_hash': value['precision_source']['sha256'] = '0' * 64
    else: value['input_sent'] = True
    failed_path.write_text(json.dumps(value))
    monkeypatch.setattr(cleanup, 'snapshot', lambda: actual)
    monkeypatch.setattr(cleanup.lab, 'connection', lambda: pytest.fail('rejected settlement opened mutation connection'))
    with pytest.raises(RuntimeError): cleanup.settle_clean(graph['tmp'] / 'evidence' / 'bad_settled', failed_path)


def test_commit_checkpoint_precedes_commit_and_records_acknowledgment(monkeypatch, state):
    baseline, before, _ = state
    expected = cleanup_expected(baseline, before)
    current, events = transaction_fixture(monkeypatch, before, expected)
    def mutation(q): current['value'] = deepcopy(expected)
    cleanup.transaction(before, expected, lambda: None, mutation, lambda key: events.append(key))
    assert events == ['begin', 'commit_attempted', 'commit', 'transaction_committed']


def test_same_cursor_projection_locks_every_owned_native_and_saved_row(state):
    before = state[0]
    calls = []
    class Query:
        description = []
        result = []
        def execute(self, sql, args):
            calls.append((sql, args))
            assert sql.endswith(' FOR UPDATE')
            h = before[str(args[0])]
            if '.characters ' in sql:
                self.description = [(k,) for k in h['native']]
                self.result = [tuple(h['native'].values())]
            elif '.character_pet ' in sql:
                self.description = [(k,) for k in h['pets'][0]] if h['pets'] else []
                self.result = [tuple(p.values()) for p in h['pets']]
            elif '.character_inventory ' in sql: self.result = h['inventory']
            else:
                table = sql.split('client442_characters.', 1)[1].split(' ', 1)[0]
                key = {'character_spell': 'spells', 'character_skills': 'skills', 'character_action': 'actions'}.get(table)
                self.result = h['saved'][key] if key else h['saved']['quests'][table]
        def fetchall(self): return self.result
    result = cleanup.cursor_snapshot(Query())
    assert result == before
    assert len(calls) == 48 and {args[0] for _, args in calls} == set(range(1, 7))


def test_full_clean_writer_commits_only_new_spell_and_refund(graph, monkeypatch):
    expected = cleanup_expected(graph['before'], graph['current'])
    current, events = transaction_fixture(monkeypatch, graph['current'], expected)
    result = cleanup.clean(graph['tmp'] / 'evidence' / 'clean', graph['prep'], graph['purchase'],
        graph['restore'], graph['park'], graph['exact_after'])
    assert result['completed'] is True and result['after'] == expected
    assert result['commit_attempted'] is result['transaction_committed'] is True
    assert result['mutation_sent'] is True and set(result['checks']) == set(cleanup.CLEAN_CHECKS)
    assert events == ['begin', 'mutation_sql', 'mutation_sql', 'commit']
    assert current['committed']['6']['pets'] == graph['current']['6']['pets']


def test_real_writer_failure_after_commit_can_settle_without_second_mutation(graph, monkeypatch):
    expected = cleanup_expected(graph['before'], graph['current'])
    _, events = transaction_fixture(monkeypatch, graph['current'], expected)
    original_checkpoint = cleanup.commit_checkpoint
    def failing_checkpoint(output, receipt):
        checkpoint = original_checkpoint(output, receipt)
        def wrapped(key):
            checkpoint(key)
            if key == 'transaction_committed': raise RuntimeError('post-commit verification interrupted')
        return wrapped
    monkeypatch.setattr(cleanup, 'commit_checkpoint', failing_checkpoint)
    output = graph['tmp'] / 'evidence' / 'committed_then_failed'
    with pytest.raises(RuntimeError, match='post-commit'):
        cleanup.clean(output, graph['prep'], graph['purchase'], graph['restore'], graph['park'], graph['exact_after'])
    failed_path = output / 'episode.json'
    original_failed = failed_path.read_bytes()
    result = cleanup.settle_clean(graph['tmp'] / 'evidence' / 'settled_actual_commit', failed_path)
    assert result['after'] == expected and result['mutation_sent'] is False
    assert events == ['begin', 'mutation_sql', 'mutation_sql', 'commit', 'rollback']
    assert failed_path.read_bytes() == original_failed


def interrupted_receipt(path, expected_failure):
    receipt = json.loads((path / 'episode.json').read_text())
    assert receipt['completed'] is False and receipt['failure'] == expected_failure
    assert receipt['finished_at'] > receipt['started_at']
    return receipt


@pytest.mark.parametrize('action', ['preflight', 'precision', 'normalize'])
def test_readonly_receipt_writers_preserve_and_propagate_interruptions(graph, monkeypatch, action):
    def interrupt(*args, **kwargs): raise KeyboardInterrupt('observation interrupted')
    output = graph['tmp'] / 'evidence' / ('interrupted_' + action)
    if action == 'preflight':
        monkeypatch.setattr(cleanup, 'snapshot', lambda: deepcopy(graph['before']))
        monkeypatch.setattr(cleanup, 'native_prerequisites', interrupt)
        call = lambda: cleanup.preflight(output, graph['prep'])
    elif action == 'precision':
        monkeypatch.setattr(cleanup.lab, 'connection', interrupt)
        call = lambda: cleanup.precision(output, graph['park'])
    else:
        monkeypatch.setattr(cleanup, 'immutable_guard', lambda *args: interrupt)
        call = lambda: cleanup.normalize(output, graph['prep'], graph['park'], graph['exact_after'])
    with pytest.raises(KeyboardInterrupt): call()
    receipt = interrupted_receipt(output, 'KeyboardInterrupt: observation interrupted')
    assert receipt['mutation_sent'] is False and receipt['input_sent'] is False


def test_clean_writer_records_interrupt_and_rolls_back_partial_delete(graph, monkeypatch):
    expected = cleanup_expected(graph['before'], graph['current'])
    current, events = transaction_fixture(monkeypatch, graph['current'], expected)
    def interrupt(q):
        q.execute('DELETE')
        raise KeyboardInterrupt()
    monkeypatch.setattr(cleanup, 'cleanup_sql', interrupt)
    output = graph['tmp'] / 'evidence' / 'interrupted_cleanup'
    with pytest.raises(KeyboardInterrupt):
        cleanup.clean(output, graph['prep'], graph['purchase'], graph['restore'], graph['park'], graph['exact_after'])
    receipt = interrupted_receipt(output, 'KeyboardInterrupt: ')
    assert receipt['commit_attempted'] is receipt['transaction_committed'] is False
    assert current['committed'] == current['value'] == graph['current']
    assert events == ['begin', 'mutation_sql', 'rollback']


def test_paid_recovery_cleanup_records_systemexit_without_committing(recovery, monkeypatch):
    graph, _, _ = recovery
    expected = cleanup_expected(graph['before'], graph['current'])
    current, events = transaction_fixture(monkeypatch, graph['current'], expected)
    def interrupt(q): raise SystemExit('recovery interrupted')
    monkeypatch.setattr(cleanup, 'cleanup_sql', interrupt)
    output = graph['tmp'] / 'evidence' / 'interrupted_recovery_cleanup'
    with pytest.raises(SystemExit):
        cleanup.clean_recovery(output, graph['prep'], graph['restore'], graph['park'], graph['exact_after'])
    receipt = interrupted_receipt(output, 'SystemExit: recovery interrupted')
    assert receipt['recovery_only'] is receipt['failed_whole_excluded'] is True
    assert receipt['commit_attempted'] is receipt['transaction_committed'] is False
    assert current['committed'] == graph['current'] and events == ['begin', 'rollback']


def test_interrupt_after_actual_commit_can_settle_without_repeating_mutation(graph, monkeypatch):
    expected = cleanup_expected(graph['before'], graph['current'])
    _, events = transaction_fixture(monkeypatch, graph['current'], expected)
    original_checkpoint = cleanup.commit_checkpoint
    def failing_checkpoint(output, receipt):
        checkpoint = original_checkpoint(output, receipt)
        def wrapped(key):
            checkpoint(key)
            if key == 'transaction_committed': raise KeyboardInterrupt('after commit')
        return wrapped
    monkeypatch.setattr(cleanup, 'commit_checkpoint', failing_checkpoint)
    output = graph['tmp'] / 'evidence' / 'interrupted_after_commit'
    with pytest.raises(KeyboardInterrupt):
        cleanup.clean(output, graph['prep'], graph['purchase'], graph['restore'], graph['park'], graph['exact_after'])
    interrupted_receipt(output, 'KeyboardInterrupt: after commit')
    failed_path = output / 'episode.json'
    original = failed_path.read_bytes()
    result = cleanup.settle_clean(graph['tmp'] / 'evidence' / 'settled_interrupt', failed_path)
    assert result['after'] == expected and result['mutation_sent'] is False
    assert events == ['begin', 'mutation_sql', 'mutation_sql', 'commit', 'rollback']
    assert failed_path.read_bytes() == original


def test_readonly_settlement_retains_and_propagates_systemexit(failed_commit, monkeypatch):
    graph, failed_path, expected = failed_commit
    monkeypatch.setattr(cleanup, 'snapshot', lambda: deepcopy(expected))
    def interrupt(): raise SystemExit('settlement interrupted')
    monkeypatch.setattr(cleanup, 'immutable_guard', lambda *args: interrupt)
    output = graph['tmp'] / 'evidence' / 'interrupted_settlement'
    with pytest.raises(SystemExit): cleanup.settle_clean(output, failed_path)
    receipt = interrupted_receipt(output, 'SystemExit: settlement interrupted')
    assert receipt['settled_commit_only'] is True and receipt['mutation_sent'] is False


def test_ui_main_closes_interrupted_trial_before_propagating(graph, monkeypatch):
    output = graph['tmp'] / 'evidence' / 'interrupted_park_trial'
    class Trial:
        def __init__(self, path, **kwargs):
            self.out = path
            path.mkdir(parents=True)
            self.receipt = {'started_at': 1, 'completed': True, 'failure': None}
        def persist(self): cleanup.persist(self.out, self.receipt)
    def interrupt(*args, **kwargs): raise KeyboardInterrupt('ordinary park interrupted')
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_owned_class_fixture',
        SimpleNamespace(SCRIPT_BOUNDARY={}))
    monkeypatch.setattr(cleanup, 'Trial', Trial)
    monkeypatch.setattr(cleanup, 'park', interrupt)
    monkeypatch.setattr(sys, 'argv', ['cleanup', 'park', '--preparation', str(graph['prep']),
        '--source', str(graph['restore']), '--output', str(output)])
    with pytest.raises(KeyboardInterrupt): cleanup.main()
    interrupted_receipt(output, 'KeyboardInterrupt: ordinary park interrupted')


@pytest.mark.parametrize('failure_stage', ['logout_return', 'snapshot', 'protected', 'registration', 'frame'])
def test_park_checkpoints_completed_logout_before_later_failure(graph, monkeypatch, failure_stage):
    old = json.loads(graph['prep'].read_text())
    restored = json.loads(graph['restore'].read_text())
    packets = json.loads(graph['park'].read_text())['logout_packets']
    native_snapshot = deepcopy(graph['current'])
    if failure_stage == 'protected': native_snapshot['1']['saved']['actions'].append([0, 1, 1, 0])
    output = graph['tmp'] / 'evidence' / ('failed_park_' + failure_stage)
    output.mkdir(parents=True)
    class Trial:
        fixture = old['class_actor']
        out = output
        receipt = {'started_at': 110, 'completed': False, 'failure': None, 'runtime': graph['native'],
            'fixture_source': cleanup.bound(graph['prep'])}
        persisted = []
        def persist(self):
            self.persisted.append(deepcopy(self.receipt))
            cleanup.persist(self.out, self.receipt)
        def clean_panels(self): pass
    t = Trial()
    def ordinary_logout(trial):
        assert trial.receipt['logout_started_at'] == 119
        assert trial.persisted[-1]['logout_started_at'] == 119
        if failure_stage == 'logout_return': raise RuntimeError('logout postcondition read failed')
    def snapshot():
        if failure_stage == 'snapshot': raise RuntimeError('offline snapshot failed')
        return native_snapshot
    def register(guid):
        if failure_stage == 'registration': raise RuntimeError('original registration failed')
        return old['origin_actor']
    def shot(path):
        if failure_stage == 'frame': raise RuntimeError('selection screenshot failed')
        return {'file': path.name}
    seconds = iter([119, 131])
    monkeypatch.setattr(cleanup.time, 'time', lambda: next(seconds))
    monkeypatch.setattr(cleanup, 'prepared', lambda *args: old)
    monkeypatch.setattr(cleanup, 'saved', lambda guid: restored['after_saved'])
    monkeypatch.setattr(cleanup, 'protected', lambda old: {'unchanged': True})
    monkeypatch.setattr(cleanup, 'origin_checks', lambda old: {'original_character': True,
        'original_saved_rows': True, 'native_worldserver': True})
    monkeypatch.setattr(cleanup.actors, 'session_entry', lambda fixture: {'session': 'session'})
    monkeypatch.setattr(cleanup.actors, 'register', register)
    monkeypatch.setattr(cleanup, 'logout', ordinary_logout)
    monkeypatch.setattr(cleanup, 'entries', lambda path: deepcopy(packets))
    monkeypatch.setattr(cleanup, 'snapshot', snapshot)
    monkeypatch.setattr(cleanup, 'shot', shot)
    with pytest.raises(RuntimeError): cleanup.park(t, graph['prep'], graph['restore'])
    checkpoint = t.persisted[-1]
    assert checkpoint['phase'] == 'hunter_learn_logout_started' and checkpoint['completed'] is False
    assert checkpoint['logout_started_at'] == 119 and checkpoint['logout_finished_at'] == 131
    assert checkpoint['logout_packets'] == packets
    assert checkpoint['source'] == cleanup.bound(graph['restore'])
    assert checkpoint['entry_source'] == restored['entry_source']
    assert checkpoint['qualification_added'] is False
    if failure_stage not in ('logout_return', 'snapshot'):
        assert checkpoint['all_offline_snapshot'] == native_snapshot

"""Real-shaped stopped-entry/source-epoch fixtures without live imports."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

import pytest

from tools.client_compatibility import bag_swap_stopped_evidence as evidence
from tools.client_compatibility import checkpoint_bag_swap_stopped as producer
from tools.client_compatibility.bag_swap_sources import bound


class MemorySources:
    """Only this test adapter can mint synthetic current-epoch receipts."""
    def __init__(self):
        self.data, self.digests, self.raw_journals = {}, {}, {}
        self.root = evidence.lab.ROOT

    def add(self, name, value):
        raw = producer._encoded(value)
        member = evidence.BATCH + 'synthetic_stopped_fixture/' + name
        self.data[member], self.digests[member] = deepcopy(value), hashlib.sha256(raw).hexdigest()
        return {'path': str(self.root / member), 'sha256': self.digests[member]}

    def member(self, ref):
        member = str(Path(ref['path']).relative_to(self.root))
        if member not in self.digests:
            path = Path(ref['path'])
            assert bound(path) == ref
            self.digests[member] = ref['sha256']
        assert self.digests[member] == ref['sha256']
        return member

    def get(self, ref, successful=True):
        member = self.member(ref)
        if member not in self.data:
            self.data[member] = json.loads(Path(ref['path']).read_text())
        value = self.data[member]
        if successful:
            assert value['completed'] is True and value['failure'] is None
        return value

    def journal(self, ref):
        return self.raw_journals[self.member(ref)]


@lru_cache(maxsize=1)
def actual_rows():
    from tools.client_compatibility.observation.journal import entries
    root = evidence.lab.ROOT
    ready = json.loads(Path(evidence.SOURCES['preparation']['path']).read_text())
    until = 1791432514.2053306
    raw = [row for row in entries(root / 'evidence/world_packets.jsonl') if
        ready['started_at'] <= row.get('time', -1) <= until and row.get('session') == ready['native_session']]
    events = [row for row in entries(root / 'logs/modern_world.jsonl') if
        ready['started_at'] <= row.get('time', -1) <= until and row.get('session') in (ready['native_session'], 'b47a0541')]
    assert len(raw) == 5444 and len(events) == 6731
    return raw, events


def fixture():
    from tools.client_compatibility.bag_swap_projection import STOPPED_SOURCE_FILES
    from tools.client_compatibility.bag_swap_stopped_contract import stopped_history
    store = MemorySources()
    old = evidence.historical(store, evidence.SOURCES)
    ready, observation = old['preparation'], old['observation']
    frame_ref = {'path': str(Path(evidence.SOURCES['preparation']['path']).parent / ready['frame']['file']),
        'sha256': ready['frame']['sha256']}
    store.member(frame_ref)
    old_epoch = store.get(ready['current_code_epoch_source'], False)
    repo = evidence._repo(ready['committed_sources'])
    wanted = sorted(set(evidence._vector(ready['committed_sources'], repo)) |
        set(evidence.NEW_FILES) | set(STOPPED_SOURCE_FILES))
    refs, copies = [], []
    commit = 'b' * 40
    for index, member in enumerate(wanted):
        raw = (repo / member).read_bytes()
        sha = hashlib.sha256(raw).hexdigest()
        row = {'path': str(repo / member), 'sha256': sha}
        refs.append(row)
        copies.append(store.add(f'code_{index}.json', {'schema': evidence.CODE_SCHEMA,
            'code_commit': commit, 'original_path': row['path'], 'sha256': sha, 'bytes': len(raw), 'raw_hex': raw.hex()}))
    epoch = {'schema': evidence.EPOCH_SCHEMA, 'code_commit': commit, 'committed_sources': refs, 'carried_sources': copies}
    raw, events = actual_rows()
    journal_refs = {}
    for role, values in (('packets', raw), ('events', events)):
        member = evidence.BATCH + 'synthetic_stopped_fixture/' + role + '.jsonl'
        serialized = b''.join(producer._encoded(row) for row in values)
        store.digests[member] = hashlib.sha256(serialized).hexdigest()
        store.raw_journals[member] = deepcopy(values)
        journal_refs[role] = {'path': str(store.root / member), 'sha256': store.digests[member]}
    until = 1791432514.2053306
    history = stopped_history(raw, events, ready, old['failed_entry'], observation, old['precision'], audit_until=until)
    index_ref = store.add('index.json', {'schema': 'client442_bag_swap_source_index_v1'})
    log_member = evidence.BATCH + 'synthetic_stopped_fixture/owned_stop_output.log'
    store.digests[log_member] = evidence.STOP_LOG_SHA
    closure = {'schema': evidence.SCHEMA, 'phase': evidence.PHASE, 'completed': True, 'failure': None,
        'controller': 'code', 'model': None, 'revision': None, 'actor': ready['actor'], 'runtime': ready['runtime'],
        'started_at': until - 1, 'audit_until': until, 'finished_at': until + 1,
        'source_validation_finished_at': until + .2,
        'code_commit': commit, 'committed_sources': refs, 'code_source_epoch': epoch,
        'prior_code_epoch_source': ready['current_code_epoch_source'], 'sources': deepcopy(evidence.SOURCES),
        'authority_source': ready['authority_source'], 'runtime_authority_source': ready['runtime_authority_source'],
        'source_index_source': index_ref, 'predecessor': ready['predecessor'],
        'before': deepcopy(observation['after']), 'after': deepcopy(observation['after']),
        'all_offline_snapshot': deepcopy(observation['after']),
        'exact_precision': {'query': evidence.PRECISION_QUERY,
            'before_row': deepcopy(observation['exact_after_precision']['row']),
            'after_row': deepcopy(observation['exact_after_precision']['row']),
            'before': deepcopy(observation['after']), 'after': deepcopy(observation['after']),
            'input_sent': False, 'mutation_sent': False,
            'before_query_started_at': until - .9, 'before_query_finished_at': until - .8,
            'after_query_started_at': until + .3, 'after_query_finished_at': until + .4},
        'journal_interval': {'from': ready['started_at'], 'until': until}, 'journal_sources': journal_refs, 'history': history,
        'owned_game_identity': {'pid': observation['observed_owned_game_pid'],
            'source': evidence.SOURCES['preparation'], 'frame': ready['frame']},
        'stop_checks': dict.fromkeys(evidence.STOP_CHECKS, True),
        'stop_log_source': {'path': str(store.root / log_member), 'sha256': evidence.STOP_LOG_SHA},
        'stop_action': observation['stop_action'], 'entry_input_sent': True, 'bag_input_sent': False,
        'normal_logout_input_sent': False, 'input_sent': False, 'mutation_sent': False,
        'qualification_added': False, 'operations_admitted': 0, 'excluded_failed_entry': True,
        'cases': [], 'cleanup': [], 'custom_script_permission': 'blocked_by_user', 'softTargetInteract': evidence.SCRIPT}
    assert len(old_epoch['committed_sources']) == 89
    return store, closure


def test_actual_immutable_historical_sources_have_their_real_failed_stop_shape():
    old = evidence.historical(MemorySources(), evidence.SOURCES)
    assert old['failed_entry']['completed'] is False
    assert old['failed_entry']['entry_input_finished_at'] == 1791431448.852425
    assert old['failed_entry']['finished_at'] == 1791431460.6547172
    assert old['observation']['exact_after_precision']['row']['exact_rest_bonus_float32_bits'] == '6b985b42'


def test_complete_real_shaped_new_closure_keeps_old_failed_epoch_and_actual_system_stop():
    store, value = fixture()
    computed, _ = evidence.validate_closure(store, value)
    assert computed['code_epochs']['original_raw_source_members'] == 89
    assert computed['code_epochs']['current_raw_source_members'] == 102
    assert computed['system_stop_only'] is True
    assert computed['operations_admitted'] == 0


@pytest.mark.parametrize('fault', ('qualification', 'input', 'normal_logout', 'fake_ticks', 'fake_stop_time',
    'wrong_pid', 'wrong_display', 'wrong_monitor', 'missing_png', 'wrong_png', 'stop_check', 'wrong_precision',
    'protected_actor', 'old_rest', 'new_code_label', 'wrong_old_epoch', 'old_source_substitution', 'omitted_queue',
    'tampered_raw_code', 'extra_source', 'wrong_history', 'wrong_journal_interval', 'script_permission', 'wrong_stop_log'))
def test_coherent_labels_cannot_replace_actual_stop_source_fields(fault):
    store, value = fixture()
    if fault == 'qualification': value['qualification_added'] = True
    elif fault == 'input': value['input_sent'] = True
    elif fault == 'normal_logout': value['normal_logout_input_sent'] = True
    elif fault == 'fake_ticks': value['game_start_ticks'] = '58326990'
    elif fault == 'fake_stop_time': value['sigterm_at'] = 1791431566.0
    elif fault == 'wrong_pid': value['owned_game_identity']['pid'] += 1
    elif fault == 'wrong_display': value['owned_game_identity'] = deepcopy(value['owned_game_identity']); value['owned_game_identity']['frame']['monitor']['input_isolation']['display'] = ':3'
    elif fault == 'wrong_monitor': value['owned_game_identity'] = deepcopy(value['owned_game_identity']); value['owned_game_identity']['frame']['monitor']['monitor']['name'] = 'DP-1'
    elif fault in ('missing_png', 'wrong_png'):
        member = str(Path(store.member(evidence.SOURCES['preparation'])).parent / value['owned_game_identity']['frame']['file'])
        store.digests[member] = None if fault == 'missing_png' else 'f' * 64
    elif fault == 'stop_check': value['stop_checks']['observed_owned_game_pid_absent'] = False
    elif fault == 'wrong_precision': value['exact_precision']['after_row']['exact_rest_bonus'] += 1
    elif fault == 'protected_actor': value['after']['3']['native']['health'] += 1
    elif fault == 'old_rest': value['before']['2']['native']['rest_bonus'] = 53.4382
    elif fault == 'new_code_label': value['code_commit'] = 'c' * 40
    elif fault == 'wrong_old_epoch': value['prior_code_epoch_source'] = value['source_index_source']
    elif fault == 'old_source_substitution': value['sources']['failed_entry']['sha256'] = 'f' * 64
    elif fault == 'omitted_queue':
        rows = value['code_source_epoch']['committed_sources']; copies = value['code_source_epoch']['carried_sources']
        i = next(i for i, row in enumerate(rows) if row['path'].endswith('/native_bridge/channel.cpp'))
        del rows[i]; del copies[i]
    elif fault == 'tampered_raw_code':
        ref = value['code_source_epoch']['carried_sources'][0]; store.get(ref, False)['raw_hex'] = 'ff'
    elif fault == 'extra_source': value['code_source_epoch']['committed_sources'].append({'path': '/tmp/unowned.py', 'sha256': 'f' * 64})
    elif fault == 'wrong_history': value['history']['source_packet_count'] += 1
    elif fault == 'wrong_journal_interval': value['journal_interval']['until'] -= 1
    elif fault == 'script_permission': value['custom_script_permission'] = 'enabled'
    elif fault == 'wrong_stop_log': value['stop_log_source']['sha256'] = 'f' * 64
    with pytest.raises((RuntimeError, AssertionError)):
        evidence.validate_closure(store, value)


@pytest.mark.parametrize('bad', (None, float('nan'), float('inf'), float('-inf')))
def test_journal_collector_rejects_attributable_bad_time_before_filter(monkeypatch, bad):
    from tools.client_compatibility.observation import journal
    monkeypatch.setattr(journal, 'entries', lambda path: iter([{'session': 'foreign', 'account_id': 2, 'time': bad}]))
    with pytest.raises(RuntimeError, match='malformed attributable'):
        producer.journal_rows(Path('/unused'), 1.0, 2.0, {'owned'})


def _mock_collector(monkeypatch, tmp_path):
    from tools.client_compatibility import bag_swap_source_index as indexed
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    from tools.client_compatibility import interaction_bag_swap_failed_entry_pause as older
    store, value = fixture()
    ready = store.get(evidence.SOURCES['preparation'], False)
    before = value['before']
    monkeypatch.setattr(continuation, 'snapshot', lambda: deepcopy(before))
    monkeypatch.setattr(continuation, 'identity', lambda kind: ready['runtime'][kind])
    monkeypatch.setattr(continuation, 'registration', lambda: ready['actor'])
    monkeypatch.setattr(continuation, 'focus', lambda: pytest.fail('post-stop closure cannot focus a window'))
    monkeypatch.setattr(evidence.lab, 'owned_process', lambda kind: None)
    monkeypatch.setattr(evidence.lab, 'stop', lambda kind: pytest.fail('post-stop closure cannot send another stop'))
    monkeypatch.setattr(indexed, 'local_sources', lambda directory: store)
    monkeypatch.setattr(indexed, 'preload_ancestor_sources', lambda *a: ())
    monkeypatch.setattr(indexed, 'prove_ancestors', lambda *a: {'test_only': 'pure predecessor fixture'})
    monkeypatch.setattr(indexed, 'build_source_index', lambda *a, **k: value['source_index_source'])
    monkeypatch.setattr(older, 'read_precision', lambda current: deepcopy(value['exact_precision']['before_row']))
    monkeypatch.setattr(producer, 'code_epoch', lambda *a: value['code_source_epoch'])
    monkeypatch.setattr(producer, 'retain_journals', lambda *a: (
        {k: store.journal(ref) for k, ref in value['journal_sources'].items()}, value['journal_sources']))
    output = tmp_path / 'new_post_stop'
    monkeypatch.setattr(producer, '_out', lambda *a: (tmp_path, output))
    original_bound = producer.bound
    def bound_fixture(path):
        found = original_bound(path)
        if Path(path) == output / 'owned_stop_output.log':
            assert found['sha256'] == evidence.STOP_LOG_SHA
            return deepcopy(value['stop_log_source'])
        return found
    monkeypatch.setattr(producer, 'bound', bound_fixture)
    return value, output


def test_final_offline_snapshot_is_rechecked_after_long_source_replay(monkeypatch, tmp_path):
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    value, output = _mock_collector(monkeypatch, tmp_path)
    before = value['before']
    changed = deepcopy(before)
    changed['5']['native']['health'] += 1
    snapshots = iter([before, before, changed])
    monkeypatch.setattr(continuation, 'snapshot', lambda: next(snapshots))
    with pytest.raises(RuntimeError, match='stale the current offline'):
        producer.close(tmp_path, output, Path('/tmp/ui173_failed_entry_stop01.log'))
    assert not (output / 'closure.json').exists()
    failure = json.loads((output / 'failed_collection.json').read_text())
    assert failure['completed'] is False and failure['input_sent'] is False


def _neighbor(row):
    changed = deepcopy(row)
    changed['exact_rest_bonus'] = 54.89884948730469
    changed['exact_rest_bonus_float32_bits'] = '6c985b42'
    assert changed['rest_bonus'] == row['rest_bonus'] == 54.8988
    return changed


def test_final_exact_query_rejects_adjacent_float_drift_hidden_by_identical_snapshot(monkeypatch, tmp_path):
    from tools.client_compatibility import interaction_bag_swap_failed_entry_pause as older
    value, output = _mock_collector(monkeypatch, tmp_path)
    row = value['exact_precision']['before_row']
    queries, validated = [], []
    source_proof = evidence._source_proof
    def replay(*args):
        result = source_proof(*args)
        validated.append(True)
        return result
    def query(snapshot):
        assert snapshot == value['before']
        queries.append(bool(validated))
        return deepcopy(row) if len(queries) == 1 else _neighbor(row)
    monkeypatch.setattr(evidence, '_source_proof', replay)
    monkeypatch.setattr(older, 'read_precision', query)
    with pytest.raises(RuntimeError, match='fresh final exact FLOAT'):
        producer.close(tmp_path, output, Path('/tmp/ui173_failed_entry_stop01.log'))
    assert queries == [False, True] and validated == [True]
    assert not (output / 'closure.json').exists()
    failure = json.loads((output / 'failed_collection.json').read_text())
    assert failure['completed'] is False and failure['mutation_sent'] is False


def test_collector_retains_two_real_mock_query_samples_after_final_source_validation(monkeypatch, tmp_path):
    from tools.client_compatibility import interaction_bag_swap_failed_entry_pause as older
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    value, output = _mock_collector(monkeypatch, tmp_path)
    queries, checks = [], []
    row = value['exact_precision']['before_row']
    def query(snapshot):
        queries.append(deepcopy(row))
        return queries[-1]
    original_checks = producer.current_checks
    def current_checks(*args):
        checks.append(len(queries))
        return original_checks(*args)
    monkeypatch.setattr(older, 'read_precision', query)
    monkeypatch.setattr(producer, 'current_checks', current_checks)
    snapshots = []
    def snapshot():
        snapshots.append(len(queries))
        return deepcopy(value['before'])
    monkeypatch.setattr(continuation, 'snapshot', snapshot)
    ref = producer.close(tmp_path, output, Path('/tmp/ui173_failed_entry_stop01.log'))
    found = json.loads(Path(ref['path']).read_bytes())
    precision = found['exact_precision']
    assert len(queries) == 2 and checks == [0, 2] and snapshots == [0, 1, 1, 2]
    assert precision['before_row'] == queries[0] and precision['after_row'] == queries[1]
    assert found['source_validation_finished_at'] <= precision['after_query_started_at']
    assert precision['after_query_finished_at'] < found['finished_at']
    assert found['completed'] is True and found['input_sent'] is False


@pytest.mark.parametrize('fault', ('snapshot', 'registration'))
def test_final_query_is_followed_by_fresh_snapshot_and_registration_checks(monkeypatch, tmp_path, fault):
    from tools.client_compatibility import interaction_bag_swap_failed_entry_pause as older
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    value, output = _mock_collector(monkeypatch, tmp_path)
    queries = []
    def query(snapshot):
        queries.append(True)
        return deepcopy(value['exact_precision']['before_row'])
    monkeypatch.setattr(older, 'read_precision', query)
    if fault == 'snapshot':
        def snapshot():
            state = deepcopy(value['before'])
            if len(queries) == 2: state['5']['native']['health'] += 1
            return state
        monkeypatch.setattr(continuation, 'snapshot', snapshot)
        message = 'final exact query changed'
    else:
        ready = json.loads(Path(evidence.SOURCES['preparation']['path']).read_bytes())
        monkeypatch.setattr(continuation, 'registration', lambda: {} if len(queries) == 2 else ready['actor'])
        message = 'ten actual source-shaped checks'
    with pytest.raises(RuntimeError, match=message):
        producer.close(tmp_path, output, Path('/tmp/ui173_failed_entry_stop01.log'))
    assert len(queries) == 2 and not (output / 'closure.json').exists()


@pytest.mark.parametrize('fault', ('adjacent_after', 'coedited_adjacent', 'missing_after', 'before_replay'))
def test_portable_precision_requires_two_source_bound_ordered_exact_samples(fault):
    store, value = fixture()
    precision = value['exact_precision']
    if fault == 'adjacent_after': precision['after_row'] = _neighbor(precision['after_row'])
    elif fault == 'coedited_adjacent':
        precision['before_row'] = _neighbor(precision['before_row'])
        precision['after_row'] = deepcopy(precision['before_row'])
    elif fault == 'missing_after': del precision['after_row']
    else: precision['after_query_started_at'] = value['audit_until'] - .1
    with pytest.raises(RuntimeError, match='exact offline FLOAT|final exact query'):
        evidence.validate_closure(store, value)

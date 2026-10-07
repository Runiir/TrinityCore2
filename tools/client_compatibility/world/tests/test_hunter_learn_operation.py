"""Execution helpers wait for real transitions and roll back unstaged world rows."""
from types import SimpleNamespace
from copy import deepcopy
from contextlib import nullcontext

import pytest

from tools.client_compatibility import interaction_spellbook_learn_spell as operation
from tools.client_compatibility import interaction_hunter_learn_pose as pose


def spell_probe(learned):
    return {'visible': True, 'book_type': 'spell', 'skill_line': 2, 'page': 1,
        'tabs': [{'index': 2, 'name': 'Beast Mastery', 'checked': True}],
        'rows': [{'id': 1462, 'api_id': 1462, 'action': 1462,
            'kind': 'SPELL' if learned else 'FUTURESPELL', 'api_kind': 'SPELL' if learned else 'FUTURESPELL',
            'known': learned, 'trainer': not learned, 'shown_name': 'Beast Lore', 'name': 'Beast Lore', 'button': 'SpellButton9'}]}


def test_caption_waits_for_learned_event_state_without_replaying_training(monkeypatch):
    reads = iter([spell_probe(False), spell_probe(False), spell_probe(True)])
    observed = []
    monkeypatch.setattr(operation, 'open_book', lambda *args: None)
    monkeypatch.setattr(operation, 'navigate', lambda *args, **kwargs: {'status': 'spellbook_navigation_pass'})
    monkeypatch.setattr(operation.time, 'sleep', lambda _: None)
    def detail(*args, **kwargs):
        p = next(reads)
        observed.append(p['rows'][0]['kind'])
        return p
    monkeypatch.setattr(operation, 'detail', detail)
    p, row = operation.caption(object(), {1515, 93321, 1462}, 'learned', True)
    assert observed == ['FUTURESPELL', 'FUTURESPELL', 'SPELL'] and row['known'] is True


@pytest.mark.parametrize('fault', ['second_insert', 'projection', 'receipt_write', 'interrupt'])
def test_staging_rolls_back_world_rows_before_host_teleport_on_any_precommit_failure(monkeypatch, fault):
    calls = []
    original = [-9465.12, 50.9323, 56.8473, 4.58812, 0]
    baseline = {'saved': {'spells': [[1515, 1, 0], [79682, 1, 0]]}, 'resources': {'money': 8708}}
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, args=None):
            self.query = query
            calls.append(query.split(' ', 1)[0])
            if query.startswith('INSERT') and args[0] == 102 and fault == 'second_insert':
                raise RuntimeError('injected second-row failure')
            if query.startswith('INSERT') and args[0] == 102 and fault == 'interrupt':
                raise KeyboardInterrupt('interrupted second row')
        def fetchone(self):
            if 'name IN' in self.query: return None
            if 'MAX(id)' in self.query: return [100]
            if 'position_x,position_y' in self.query:
                return [*original[:4], 1] if fault == 'projection' else original
            raise AssertionError(self.query)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
        def begin(self): calls.append('begin')
        def commit(self): calls.append('commit')
        def rollback(self): calls.append('rollback')
    class Trial:
        receipt = {'runtime': {'worldserver': {'pid': 1}}}
        def observe(self, *args):
            return {}, {'movement': {'dead': False, 'in_combat': False, 'speed': 0}}
        def persist(self):
            calls.append('persist')
            if fault == 'receipt_write': raise RuntimeError('injected receipt failure')
        def execute(self, *args): raise AssertionError('no gameplay input before commit')
    monkeypatch.setattr(pose.lab, 'connection', Connection)
    monkeypatch.setattr(pose.lab, 'server_command', lambda command: calls.append(command))
    monkeypatch.setattr(pose, 'native_prerequisites', lambda: {'sha256': 'pinned'})
    monkeypatch.setattr(pose, 'saved', lambda _: baseline['saved'])
    monkeypatch.setattr(pose, 'resources', lambda _: baseline['resources'])
    monkeypatch.setattr(pose, 'protected', lambda _: {'protected': True})
    monkeypatch.setattr(pose, 'pose', lambda: original)
    monkeypatch.setattr(pose.time, 'sleep', lambda _: None)
    monkeypatch.setattr(pose, 'teleport_row', lambda q, number:
        [number, *original, pose.NAMES[number - 101]])
    with pytest.raises(KeyboardInterrupt if fault == 'interrupt' else RuntimeError): pose.stage(Trial(), {}, object(), baseline)
    assert 'rollback' in calls and 'commit' not in calls
    assert not any(c.startswith('tele ') or c.startswith('reload ') for c in calls)


@pytest.mark.parametrize('packet', [None, 'CMSG_TRAINER_BUY_SPELL', 'SMSG_LEARNED_SPELL',
    'SMSG_LEARNED_SPELLS', 'CMSG_SET_ACTION_BUTTON'])
def test_zero_request_train_failure_settles_from_native_facts_without_replaying_intent(monkeypatch, packet):
    original = {'spells': [[1515, 1, 0], [79682, 1, 0]], 'actions': []}
    failed = {'baseline': {'saved': original, 'resources': {'money': 8708}},
        'entry_source': {'path': 'entry'}, 'login_known_spell_ids': [1515, 93321],
        'purchase_input_sent': True, 'pose_fixture': {'owned': True}, 'book_layout_baseline': {}}
    events = []
    trial = SimpleNamespace(receipt={}, clean_panels=lambda: events.append('panels'))
    monkeypatch.setattr(operation, 'failed_stage', lambda *args: ({}, 'hunter', failed))
    monkeypatch.setattr(operation, 'linked', lambda _: {'started_at': 10})
    monkeypatch.setattr(operation, 'bound', lambda _: {'path': 'failed', 'sha256': 'exact'})
    monkeypatch.setattr(operation.time, 'time', lambda: 20)
    rows = [] if packet is None else [{'session': 'hunter', 'time': 12, 'name': packet,
        'direction': 'from_client' if packet.startswith('CMSG') else 'from_native'}]
    monkeypatch.setattr(operation, 'entries', lambda _: rows)
    monkeypatch.setattr(operation, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: object()))
    monkeypatch.setattr(operation, 'resources', lambda _: {'money': 8708})
    monkeypatch.setattr(operation, 'saved', lambda _: deepcopy(original))
    monkeypatch.setattr(operation, 'protected', lambda _: {'protected': True})
    monkeypatch.setattr(operation, 'restore_layout', lambda *args: events.append('layout') or {})
    monkeypatch.setattr(operation, 'restore_pose', lambda *args: events.append('pose') or {})
    if packet:
        with pytest.raises(RuntimeError): operation.recover(trial, 'preparation', 'failed', False)
        assert not events
    else:
        operation.recover(trial, 'preparation', 'failed', False)
        assert events == ['layout', 'panels', 'pose']
        assert trial.receipt['train_input_replayed'] is False and trial.receipt['failed_whole_excluded'] is True


@pytest.mark.parametrize('authority', [True, False])
def test_already_deleted_pose_requires_persisted_exact_authority_and_never_teleports(monkeypatch, authority):
    original = [-9465.12, 50.9323, 56.8473, 4.58812, 0]
    saved = {'spells': [[1515, 1, 0], [79682, 1, 0]]}
    fixture = {'owner': 6, 'native': {'pid': 1}, 'before': original, 'native_restore_projection': original,
        'rows': [[101, *original, pose.NAMES[0]], [102, *original, pose.NAMES[1]]]}
    settlement = {'fixture': fixture, 'restored': original, 'removed': [101, 102],
        'expected_saved': saved, 'gameplay_input_sent': False}
    calls = []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, args): assert query.startswith('SELECT ')
        def fetchall(self): return []
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
    trial = SimpleNamespace(receipt={'runtime': {'worldserver': {'pid': 1}}}, persist=lambda: calls.append('persist'))
    monkeypatch.setattr(pose.lab, 'connection', Connection)
    monkeypatch.setattr(pose.lab, 'server_command', calls.append)
    monkeypatch.setattr(pose, 'pose', lambda: original)
    monkeypatch.setattr(pose, 'saved', lambda _: saved)
    monkeypatch.setattr(pose, 'protected', lambda _: {'protected': True})
    if authority:
        proof = pose.restore(trial, fixture, {}, saved, settlement)
        assert proof['settlement_only'] is True and proof['native_teleport_replayed'] is False
        assert calls == ['persist', 'reload game_tele']
    else:
        with pytest.raises(RuntimeError): pose.restore(trial, fixture, {}, saved)
        assert not calls


@pytest.mark.parametrize('unexpected_action', [False, True])
def test_paid_lost_outcome_persists_only_observed_native_purchase_without_train_replay(monkeypatch, unexpected_action):
    import struct
    original = {'spells': [[1515, 1, 0], [79682, 1, 0]], 'actions': []}
    expected = {**original, 'spells': sorted(original['spells'] + [[1462, 1, 0]])}
    failed = {'baseline': {'saved': original, 'resources': {'money': 8708}},
        'entry_source': {'path': 'entry'}, 'login_known_spell_ids': [1515, 93321],
        'purchase_input_sent': True, 'purchase_started_at': 11, 'pose_fixture': {}, 'book_layout_baseline': {}}
    rows = [{'session': 'hunter', 'time': 12, 'name': 'CMSG_TRAINER_BUY_SPELL', 'direction': 'to_native',
        'body': struct.pack('<QII', operation.TRAINER_GUID, 40, 1462).hex()},
        {'session': 'hunter', 'time': 13, 'name': 'SMSG_LEARNED_SPELL', 'direction': 'from_native',
            'body': struct.pack('<II', 1462, 0).hex()}]
    if unexpected_action: rows.append({**rows[0], 'name': 'CMSG_SET_ACTION_BUTTON'})
    current, calls = [deepcopy(original)], []
    trial = SimpleNamespace(receipt={}, clean_panels=lambda: None, persist=lambda: calls.append('persist'))
    monkeypatch.setattr(operation, 'failed_stage', lambda *args: ({}, 'hunter', failed))
    monkeypatch.setattr(operation, 'linked', lambda _: {'started_at': 10})
    monkeypatch.setattr(operation, 'bound', lambda _: {'path': 'failed', 'sha256': 'exact'})
    monkeypatch.setattr(operation.time, 'time', lambda: 20)
    monkeypatch.setattr(operation.time, 'sleep', lambda _: None)
    monkeypatch.setattr(operation, 'entries', lambda _: rows)
    oracle = SimpleNamespace(poll=lambda: oracle)
    monkeypatch.setattr(operation, 'Inventory', lambda *args: oracle)
    monkeypatch.setattr(operation, 'resources', lambda _: {'money': 8062})
    monkeypatch.setattr(operation, 'saved', lambda _: deepcopy(current[0]))
    monkeypatch.setattr(operation, 'protected', lambda _: {'protected': True})
    monkeypatch.setattr(operation, 'restore_layout', lambda *args: {})
    monkeypatch.setattr(operation, 'restore_pose', lambda *args: {})
    def save(command):
        calls.append(command)
        current[0] = deepcopy(expected)
    monkeypatch.setattr(operation.lab, 'server_command', save)
    if unexpected_action:
        with pytest.raises(RuntimeError): operation.recover(trial, 'preparation', 'failed', True)
        assert not calls
    else:
        operation.recover(trial, 'preparation', 'failed', True)
        assert calls == ['persist', 'saveall']
        assert trial.receipt['after_saved'] == expected and trial.receipt['train_input_replayed'] is False


def test_controller_interruption_closes_actual_failed_receipt_before_propagating(monkeypatch):
    persisted = []
    trial = SimpleNamespace(receipt={'started_at': 10}, persist=lambda: persisted.append(deepcopy(trial.receipt)))
    monkeypatch.setattr(operation, 'Trial', lambda *args, **kwargs: trial)
    monkeypatch.setattr(operation, 'actor', lambda _: nullcontext())
    monkeypatch.setattr(operation.time, 'time', lambda: 20)
    monkeypatch.setattr('sys.argv', ['learning', 'recover-pose', '--preparation', '/private/prep',
        '--source', '/private/failed', '--output', '/private/recovery'])
    def interrupted(*args):
        trial.receipt['completed'] = True
        raise KeyboardInterrupt('actual interrupt')
    monkeypatch.setattr(operation, 'recover', interrupted)
    with pytest.raises(KeyboardInterrupt): operation.main()
    assert persisted[-1]['completed'] is False
    assert persisted[-1]['failure'] == 'KeyboardInterrupt: actual interrupt' and persisted[-1]['finished_at'] == 20

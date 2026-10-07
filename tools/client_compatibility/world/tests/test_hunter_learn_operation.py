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


@pytest.mark.parametrize('fault', ['none', 'public_xy', 'native_height', 'native_translation',
    'native_nan', 'native_infinite', 'missing_ack', 'map'])
def test_staging_uses_native_landing_and_retains_public_zero_height_diagnostics(monkeypatch, fault):
    import math
    from tools.client_compatibility.world.buffer import Writer, player_high
    from tools.client_compatibility.world import transfers
    original = [-9465.12, 50.9323, 56.8473, 4.58812, 1 if fault == 'map' else 0]
    baseline = {'saved': {'spells': deepcopy(operation.BASE_SPELLS)}, 'resources': {'money': 8708}}
    x, y, z, facing = pose.TRAINER_ROW[4:8]
    landing = [x + 3 * math.cos(facing), y + 3 * math.sin(facing), z, (facing + math.pi) % math.tau, 0]
    state = {'target': {'name': pose.TRAINER_NAME, 'visible': True},
        'world_position': [landing[0] + (2 if fault == 'public_xy' else 0), landing[1], 0, 0],
        'lua_errors': {}, 'blocked_actions': {}}
    frame = {'file': 'hunter_learn_trainer_staged.png', 'movement': {'dead': False, 'in_combat': False, 'speed': 0}}
    commands, persisted, inserted, reads = [], [], {}, []
    class Cursor:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def execute(self, query, args=None):
            self.query = query
            if query.startswith('INSERT'): inserted[args[0]] = list(args)
        def fetchone(self):
            if 'name IN' in self.query: return None
            if 'MAX(id)' in self.query: return [100]
            if 'position_x,position_y' in self.query: return original
            raise AssertionError(self.query)
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def cursor(self): return Cursor()
        def begin(self): pass
        def commit(self): pass
        def rollback(self): raise AssertionError('fixture preparation must commit before the captured teleport')
    class Trial:
        def __init__(self):
            self.receipt = {'runtime': {'worldserver': {'pid': 1}}, 'native_session': 'hunter'}
        def observe(self, label): return deepcopy(state), deepcopy(frame)
        def execute(self, action):
            assert action == {'kind': 'chat', 'value': '/targetexact ' + pose.TRAINER_NAME}
        def persist(self): persisted.append(deepcopy(self.receipt))
    def native_teleport(height):
        # Native near-teleport GUID6, no vehicle/transport, sequence11.
        w = Writer()
        for i in (6, 0, 3, 2): w.bits(i == 0, 1)
        for _ in range(6): w.bits(0, 1)
        return w.pack('Iff', 11, landing[0], landing[3]).pack('f', height).raw(b'\x07').pack('f', landing[1]).finish()
    height = float('nan') if fault == 'native_nan' else float('inf') if fault == 'native_infinite' else (
        z + (2 if fault in ('native_height', 'native_translation') else 0))
    native = native_teleport(height)
    owner = SimpleNamespace(character={'guid': 6})
    modern_source = native_teleport(z) if fault == 'native_translation' else native
    modern_name, modern = transfers.response(owner, 'MSG_MOVE_TELEPORT', modern_source)
    client_ack = Writer().guid(6, player_high()).pack('II', 11, 123).finish()
    native_ack_name, native_ack = transfers.request(owner, 'CMSG_MOVE_TELEPORT_ACK', client_ack)
    packets = [{'session': 'hunter', 'time': stamp, 'direction': direction, 'name': name, 'body': body.hex()}
        for stamp, direction, name, body in (
            (101, 'from_native', 'MSG_MOVE_TELEPORT', native), (101.01, 'to_client', modern_name, modern),
            (101.02, 'from_client', 'CMSG_MOVE_TELEPORT_ACK', client_ack), (101.03, 'to_native', native_ack_name, native_ack))]
    if fault == 'missing_ack': packets.pop()
    trial = Trial()
    monkeypatch.setattr(pose.lab, 'connection', Connection)
    monkeypatch.setattr(pose.lab, 'server_command', commands.append)
    monkeypatch.setattr(pose, 'native_prerequisites', lambda: {'sha256': 'pinned'})
    monkeypatch.setattr(pose, 'saved', lambda _: reads.append('saved') or deepcopy(baseline['saved']))
    monkeypatch.setattr(pose, 'resources', lambda _: reads.append('resources') or deepcopy(baseline['resources']))
    monkeypatch.setattr(pose, 'protected', lambda _: reads.append('protected') or {'protected': True})
    monkeypatch.setattr(pose, 'pose', lambda: original)
    monkeypatch.setattr(pose, 'teleport_row', lambda q, number: inserted[number])
    monkeypatch.setattr(pose, 'entries', lambda _: deepcopy(packets))
    stamps = iter((100, 102))
    monkeypatch.setattr(pose.time, 'time', lambda: next(stamps))
    monkeypatch.setattr(pose.time, 'sleep', lambda _: None)
    if fault == 'none':
        fixture, actual, actual_frame = pose.stage(trial, {}, object(), baseline)
        assert actual == state and actual_frame == frame and fixture['landing'] == landing
        assert all(trial.receipt['staging_checks'].values())
        assert trial.receipt['staging_teleport']['native_teleport'] == packets[0]
        assert trial.receipt['staging_teleport']['map'] == 0
        assert abs(trial.receipt['staging_teleport']['native_position'][2] - z) < .001
    else:
        with pytest.raises(RuntimeError, match='public_xy' if fault == 'public_xy' else 'native_xyz_map_ack'):
            pose.stage(trial, {}, object(), baseline)
        assert trial.receipt['staging_checks']['public_xy'] is (fault != 'public_xy')
        assert trial.receipt['staging_checks']['native_xyz_map_ack'] is (fault == 'public_xy')
        assert all(trial.receipt['staging_checks'][k] for k in ('saved_rows', 'resources', 'protected_actors', 'ui_clean'))
    assert persisted[-1]['state'] == state and persisted[-1]['frame'] == frame
    assert persisted[-1]['staging_checks'] == trial.receipt['staging_checks']
    assert persisted[-1]['staging_packets'] == packets and reads.count('saved') == 2
    assert commands == ['saveall', 'reload game_tele', 'tele name Harnesshunt ' + pose.NAMES[1]]


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


def test_recon_closes_stock_book_before_passive_actionbar_page_and_retains_caption(monkeypatch):
    snapshot = {'6': {'native': {'activeTalentGroup': 0}}}
    original = {'spells': deepcopy(operation.BASE_SPELLS), 'actions': []}
    resources = {'money': 8708}
    entered = {'learn_offline_baseline': snapshot, 'rest_baseline_source': {'path': 'precision'},
        'resources': resources, 'native_pet_reload': {'source': 'entry'}}
    layout = {'book_type': 'spell', 'skill_line': 1, 'page': 1, 'pages': {'1': 1, '2': 1}}
    future = spell_probe(False)
    calls = []
    class Trial:
        def __init__(self):
            self.receipt, self.panels = {}, []
        def clean_panels(self):
            calls.append(('close', tuple(self.panels)))
            self.panels = []
        def observe(self, label):
            return {'panels': list(self.panels)}, {'file': label + '.png'}
        def execute(self, action):
            raise AssertionError('recon must not Train, cast, or modify actions')
    trial = Trial()
    monkeypatch.setattr(operation, 'baseline', lambda *args: ({'learn_offline_baseline': snapshot}, 'hunter'))
    monkeypatch.setattr(operation, 'entry_source', lambda *args: entered)
    monkeypatch.setattr(operation, 'native_prerequisites', lambda: {})
    monkeypatch.setattr(operation, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: object()))
    monkeypatch.setattr(operation, 'wire_known', lambda *args: {1515, 79682})
    monkeypatch.setattr(operation, 'known', lambda _: deepcopy(operation.BASE_SPELLS))
    monkeypatch.setattr(operation, 'resources', lambda _: resources)
    monkeypatch.setattr(operation, 'saved', lambda _: deepcopy(original))
    monkeypatch.setattr(operation, 'pets', lambda _: [])
    monkeypatch.setattr(operation, 'bound', lambda path: {'path': str(path), 'sha256': 'exact'})
    monkeypatch.setattr(operation, 'protected', lambda _: {'protected': True})
    def open_book(t, label):
        t.panels = ['SpellBookFrame']
        return deepcopy(layout)
    def caption(t, *args):
        t.panels = ['SpellBookFrame']
        return deepcopy(future), deepcopy(future['rows'][0])
    def passive_bar(t, label):
        assert not t.panels, 'observer145 never schedules actionbars while the stock book is open'
        calls.append(('read', label))
        return {'active_spec': 1}
    monkeypatch.setattr(operation, 'open_book', open_book)
    monkeypatch.setattr(operation, 'caption', caption)
    monkeypatch.setattr(operation, 'bar_detail', passive_bar)
    operation.recon(trial, 'preparation', 'entry')
    assert calls == [('close', ()), ('close', ('SpellBookFrame',)), ('read', 'hunter_learn_bar_baseline')]
    assert trial.receipt['future_probe'] == future and trial.receipt['book_layout_baseline'] == layout
    assert trial.receipt['completed'] is True


def test_one_train_closes_trainer_and_learned_book_before_both_passive_actionbar_reads(monkeypatch):
    import struct
    original = {'spells': deepcopy(operation.BASE_SPELLS), 'actions': []}
    after_saved = {**original, 'spells': sorted(operation.BASE_SPELLS + [[1462, 1, 0]])}
    source = {'path': 'selected', 'sha256': 'exact'}
    selected = {'frame': {'file': 'selected.png'}, 'entry_source': {'path': 'entry'},
        'login_known_spell_ids': [1515, 79682],
        'baseline': {'saved': original, 'resources': {'money': 8708}, 'active_spec': 0}}
    public = {'active_spec': 1, 'frames': {'MainMenuBar': True},
        'actions': [{'button': 'ActionButton' + str(i), 'slot': i, 'kind': None, 'id': None, 'visible': True}
            for i in range(1, 13)]}
    rows = [{'session': 'hunter', 'time': stamp, 'direction': direction, 'name': name, 'body': body.hex()}
        for stamp, direction, name, body in (
            (100.1, 'to_native', 'CMSG_TRAINER_BUY_SPELL', struct.pack('<QII', operation.TRAINER_GUID, 40, 1462)),
            (100.2, 'from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', 1462, 0)),
            (100.3, 'to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, 1462, 0)))]
    calls, paid = [], [False]
    class Trial:
        def __init__(self):
            self.receipt, self.panels = {}, ['ClassTrainerFrame']
        def persist(self): pass
        def clean_panels(self):
            calls.append(('close', tuple(self.panels)))
            self.panels = []
        def observe(self, label):
            return {'panels': list(self.panels), 'lua_errors': {}, 'blocked_actions': {},
                'trainer': {'service': {'name': 'Beast Lore', 'state': 'available', 'cost': 646}}}, {'file': label + '.png'}
        def execute(self, action):
            raise AssertionError('unexpected cast or action-bar input')
    class Cursor:
        def __init__(self, *args): self.polls = 0
        def poll(self):
            self.polls += 1
            return deepcopy(rows) if self.polls == 2 else []
    trial = Trial()
    monkeypatch.setattr(operation, 'prior', lambda *args: ({}, 'hunter', selected))
    monkeypatch.setattr(operation, 'reviewed', lambda *args: {'source': source, 'frame': selected['frame'], 'point': [100, 100]})
    monkeypatch.setattr(operation, 'bound', lambda _: source)
    monkeypatch.setattr(operation, 'controls', lambda _: [{'name': 'ClassTrainerTrainButton'}])
    monkeypatch.setattr(operation, 'point', lambda _: [100, 100])
    monkeypatch.setattr(operation, 'native_prerequisites', lambda: {})
    monkeypatch.setattr(operation, 'Cursor', Cursor)
    monkeypatch.setattr(operation, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: object()))
    monkeypatch.setattr(operation, 'resources', lambda _: {'money': 8062 if paid[0] else 8708})
    monkeypatch.setattr(operation, 'known', lambda _: deepcopy(after_saved['spells'] if paid[0] else original['spells']))
    monkeypatch.setattr(operation, 'saved', lambda _: deepcopy(after_saved if paid[0] else original))
    monkeypatch.setattr(operation, 'linked', lambda _: {'started_at': 99})
    monkeypatch.setattr(operation, 'entries', lambda _: [])
    monkeypatch.setattr(operation, 'protected', lambda _: {'protected': True})
    stamps = iter((100, 101, 102))
    monkeypatch.setattr(operation.time, 'time', lambda: next(stamps))
    monkeypatch.setattr(operation.time, 'sleep', lambda _: None)
    monkeypatch.setattr(operation.lab, 'server_command', lambda command: calls.append(('native', command)))
    def passive_bar(t, label):
        assert not t.panels, 'observer145 never schedules actionbars while trainer or book panels are open'
        calls.append(('read', label))
        return deepcopy(public)
    def caption(t, *args):
        t.panels = ['SpellBookFrame']
        return spell_probe(True), spell_probe(True)['rows'][0]
    def train_once(t, case_id, goal, selector, outcome):
        calls.append(('train', case_id))
        paid[0] = True
        return outcome({}, {'lua_errors': {}, 'blocked_actions': {}}, 'interact')
    monkeypatch.setattr(operation, 'bar_detail', passive_bar)
    monkeypatch.setattr(operation, 'caption', caption)
    monkeypatch.setattr(operation, 'click_case', train_once)
    operation.learn(trial, 'preparation', 'selected', 'review')
    assert [v for v in calls if v[0] == 'train'] == [('train', 'spellbook.learn_spell.train1462')]
    assert ('close', ('ClassTrainerFrame',)) in calls and ('close', ('SpellBookFrame',)) in calls
    assert [v[1] for v in calls if v[0] == 'read'] == ['hunter_learn_after_purchase_actions', 'hunter_learn_transition_actions']
    assert trial.receipt['learned_probe'] == spell_probe(True) and trial.receipt['after_saved'] == after_saved
    assert trial.receipt['completed'] is True and all(trial.receipt['purchase_checks'].values())

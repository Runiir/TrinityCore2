"""Mocked interruption tests: no client, server, database, launcher or network."""
from contextlib import contextmanager
from copy import deepcopy
import importlib
import json
import os
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_item_actionbar as op
from tools.client_compatibility import item_actionbar_contract as proof

SCOUT = {'guid': 2, 'account_id': 2, 'character_name': 'Harnesstwo', 'race': 1, 'class': 1, 'level': 1}
RUNTIME = {'client': {'pid': 22, 'start_ticks': 33}, 'worldserver': {'pid': 44, 'start_ticks': 55}}
PREP = Path('/private/preparation/episode.json')
SOURCE = Path('/private/source/episode.json')
REVIEW = Path('/private/source/review.json')
ENTRY = Path('/private/entry/episode.json')


def ref(path):
    return {'path': str(path), 'sha256': 'a' * 64}


def action_rows():
    return [[0, 0, 6603, 0], [1, 8, 78, 0]]


def public(rows, page=1):
    active = {r[1]: r[2:] for r in rows if r[0] == 0}
    buttons = []
    for i in range(12):
        value = active.get(i + (page - 1) * 12)
        buttons.append({'button': 'ActionButton' + str(i + 1), 'slot': i + 1 + (page - 1) * 12,
            'kind': {0: 'spell', 48: 'flyout', 128: 'item', 64: 'macro'}.get(value[1]) if value else '',
            'id': value[0] if value else 0, 'visible': value is not None})
    return {'active_spec': 1, 'page': page, 'effective_page': page, 'bonus_offset': 0,
        'viewport': {'width': 1280, 'height': 720}, 'frames': {'MainMenuBar': True},
        'actions': buttons, 'keys': {'ACTIONPAGE1': ['SHIFT-1'], 'SITORSTAND': ['X']}}


def requests(*, clear=False, at=22, slot0=3):
    value = 0 if clear else op.ITEM | 128 << 24
    return [{'session': 'owned', 'time': at, 'name': op.ACTION, 'direction': 'from_client',
        'body': struct.pack('<IB', value, slot0).hex()},
        {'session': 'owned', 'time': at, 'name': op.ACTION, 'direction': 'to_native',
        'body': struct.pack('<BI', slot0, value).hex()}]


def native():
    return {'pose': {'stand': 0, 'sheath': 0}, 'afk': False, 'selection': 0, 'health': 60,
        'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0}


def state(*, bags=None, cursor=None):
    return {'player': 'Harnesstwo', 'level': 1, 'world_position': [1, 2, 3, 0], 'target': {'exists': False},
        'panels': [], 'bags': [0] if bags is None else bags, 'cursor_info': [] if cursor is None else cursor,
        'spell_targeting': False, 'lua_errors': [], 'blocked_actions': []}


def baseline():
    resources = {'money': 0, 'backpack': [{'guid': (0x4000 << 48) | 41, 'id': 6948, 'count': 1}]}
    saved = {'actions': action_rows(), 'spells': [], 'skills': [], 'quests': {'old': []}}
    snap = {str(g): {'native': {'guid': g, 'online': 0, 'activeTalentGroup': 0,
        'position_x': 1, 'position_y': 2, 'position_z': 3, 'orientation': 0, 'map': 0},
        'saved': deepcopy(saved), 'pets': [], 'inventory': [[g, 41, 6948, 1, '0 0 0 0 0']]} for g in range(1, 7)}
    return {'snapshot': snap, 'saved': saved, 'resources': resources, 'public': public(action_rows()),
        'state': state(bags=[]), 'active_spec': 0, 'entry_source': ref(ENTRY), 'precision_source': ref(PREP),
        'native_state': native(), 'native_original': {'pose': native()['pose'], 'afk': False,
            'selection': {'native_guid': 0}, 'resources': resources, 'actions': action_rows()},
        'stock_grid_sources': [proof.GRID_SOURCE]}


def placement(base=None):
    base = baseline() if base is None else base
    after = op.expected_saved(base, 3, True)
    return proof.addition_guard(base['saved']['actions'], after['actions'], requests(at=10.1),
        'owned', 10, 11, 0, public(after['actions']))


class Trial:
    def __init__(self, tmp_path):
        self.out = tmp_path
        self.fixture = SCOUT
        self.receipt = {'started_at': 20, 'actor': SCOUT, 'runtime': RUNTIME, 'cases': [],
            'completed': False, 'failure': None, 'qualification_added': False}
        self.events, self.persisted = [], []
        self.cursor = []
        self.io = SimpleNamespace(hold_modifier=self.held, drag=self.drag)

    def persist(self):
        self.persisted.append(deepcopy(self.receipt))

    def observe(self, label):
        return state(cursor=self.cursor), {'file': label + '.png', 'sha256': 'b' * 64}

    def execute(self, action):
        self.events.append(('execute', deepcopy(action)))
        if action.get('button') == 3:
            self.cursor = []

    def drag(self, start, end):
        self.events.append(('shift_drag', start, end))
        self.cursor = ['item', 6948]

    @contextmanager
    def held(self, modifier):
        self.events.append(('held', modifier))
        yield

    def clean_panels(self):
        self.events.append(('clean_panels',))


def common(monkeypatch, t, base=None):
    base = baseline() if base is None else base
    saved_holder = [deepcopy(base['saved'])]
    shown_holder = [deepcopy(base['public'])]
    rows_holder = [requests()]
    monkeypatch.setattr(op, 'bound', ref)
    monkeypatch.setattr(op, 'native_state', lambda session: native())
    monkeypatch.setattr(op, 'resources', lambda session: deepcopy(base['resources']))
    monkeypatch.setattr(op, 'saved', lambda: deepcopy(saved_holder[0]))
    monkeypatch.setattr(op, 'detail', lambda *args: deepcopy(shown_holder[0]))
    monkeypatch.setattr(op, 'packet_rows', lambda *args: deepcopy(rows_holder[0]))
    monkeypatch.setattr(op, 'peers', lambda *args: {'all': True})
    monkeypatch.setattr(op, 'no_forbidden', lambda *args, **kwargs: {'no_forbidden_input': True})
    monkeypatch.setattr(op, 'slot_control', lambda *args: {'name': 'BagItem', 'x': 1000, 'y': 1000})
    monkeypatch.setattr(op, 'screen_geometry', lambda *args: {'exact_pixels': True})
    monkeypatch.setattr(op, 'reviewed_points', lambda *args, **kwargs: ([20, 20], [600, 600]))
    monkeypatch.setattr(op.time, 'time', lambda: 22)
    monkeypatch.setattr(op.time, 'sleep', lambda _: None)
    monkeypatch.setattr(op, 'stock_sources', lambda: [{'path': 'stock-pickup', 'sha256': 'c' * 64}])
    monkeypatch.setattr(op, 'stock_grid_sources', lambda: deepcopy([proof.GRID_SOURCE]))
    monkeypatch.setattr(op, 'validate_placement', lambda stage, session: stage['placement'])
    monkeypatch.setattr(op, 'consume_attempt', lambda *args: {'path': '/mocked/attempt.json', 'sha256': 'a' * 64})
    monkeypatch.setattr(op, 'restore_layout', lambda *args: {'layout': True})
    return base, saved_holder, shown_holder, rows_holder


def drag_stage(base):
    return {'baseline': base, 'slot0': 3, 'public': base['public'], 'source_control': {'name': 'BagItem', 'x': 1000, 'y': 1000},
        'frame': {'file': 'reviewed.png', 'sha256': 'b' * 64}, 'state': state(), 'button': base['public']['actions'][3]}


def test_operation_import_does_not_load_auth_or_protobuf():
    before = set(sys.modules)
    importlib.reload(op)
    assert not any(n.startswith(('google.protobuf', 'tools.client_compatibility.auth')) for n in set(sys.modules) - before)


def test_drag_persists_intent_before_one_input_and_saves_only_exact_addition(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, rows_holder = common(monkeypatch, t)
    stage = drag_stage(base)
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    original_execute = t.execute
    def execute(action):
        assert t.persisted[-1]['drag_input_sent'] is True
        assert t.persisted[-1]['drag_intent']['slot0'] == 3
        original_execute(action)
        shown_holder[0] = public(op.expected_saved(base, 3, True)['actions'])
    t.execute = execute
    def save():
        t.events.append(('saveall',))
        saved_holder[0] = op.expected_saved(base, 3, True)
    monkeypatch.setattr(op, 'server_save', save)
    op.drag(t, PREP, SOURCE, REVIEW)
    assert t.receipt['phase'] == 'item_actionbar_placed'
    assert t.receipt['placement']['slot0'] == 3
    assert len(t.events) == 2 and [e[0] for e in t.events] == ['execute', 'saveall']
    assert t.receipt['cases'][0]['status'] == 'item_actionbar_drag_pass'


@pytest.mark.parametrize('fault', ['wrong_slot', 'extra_action', 'forbidden_use', 'saved_drift', 'cursor'])
def test_bad_placement_cannot_trigger_saveall_or_replay(monkeypatch, tmp_path, fault):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, rows_holder = common(monkeypatch, t)
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', drag_stage(base)))
    def execute(action):
        t.events.append(('execute', deepcopy(action)))
        shown_holder[0] = public(op.expected_saved(base, 3, True)['actions'])
        if fault == 'wrong_slot': rows_holder[0] = requests(slot0=4)
        if fault == 'extra_action': rows_holder[0] += requests(slot0=5)
        if fault == 'forbidden_use': rows_holder[0] += [{'session': 'owned', 'time': 22,
            'name': 'CMSG_USE_ITEM', 'direction': 'from_client', 'body': ''}]
        if fault == 'saved_drift': saved_holder[0]['quests']['old'].append(1)
        if fault == 'cursor': t.cursor = ['item', 6948]
    t.execute = execute
    monkeypatch.setattr(op, 'server_save', lambda: pytest.fail('invalid outcome must not save'))
    with pytest.raises(RuntimeError):
        op.drag(t, PREP, SOURCE, REVIEW)
    assert len(t.events) == 1
    assert t.receipt['completed'] is False and t.receipt['failed_whole_excluded'] is True
    assert t.receipt['raw_placement_failure']['packets'] == rows_holder[0]
    assert t.receipt['first_failure']


def test_keyboard_interrupt_keeps_packets_when_outcome_observation_fails(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, _, _, rows_holder = common(monkeypatch, t)
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', drag_stage(base)))
    def execute(action):
        t.events.append(('execute', deepcopy(action)))
        raise KeyboardInterrupt('attributable interruption')
    t.execute = execute
    read = op.detail
    monkeypatch.setattr(op, 'detail', lambda t, label: (_ for _ in ()).throw(RuntimeError('render lost'))
        if 'failure' in label else read(t, label))
    with pytest.raises(KeyboardInterrupt):
        op.run(t, 'drag', PREP, SOURCE, REVIEW)
    assert len(t.events) == 1
    assert t.receipt['failure'] == 'KeyboardInterrupt: attributable interruption'
    assert t.receipt['finished_at'] == 22
    raw = t.receipt['raw_placement_failure']
    assert raw['packets'] == rows_holder[0] and raw['errors']['public'] == 'RuntimeError: render lost'
    assert 'cursor_info' in raw and 'saved' in raw and 'resources' in raw


@pytest.mark.parametrize('saved_already_placed', [False, True])
def test_guarded_placement_save_admits_only_baseline_or_sole_expected_row(monkeypatch, tmp_path, saved_already_placed):
    t = Trial(tmp_path)
    base, saved_holder, _, _ = common(monkeypatch, t)
    expected = op.expected_saved(base, 3, True)
    if saved_already_placed:
        saved_holder[0] = expected
    monkeypatch.setattr(op, 'server_save', lambda: saved_holder.__setitem__(0, deepcopy(expected)))
    after = op.save_guarded(t, base, 'owned', 3, public(expected['actions']), requests(), 21, 22, placed=True)
    assert after == expected
    assert t.receipt['saveall_authority']['saved_before'] == (expected if saved_already_placed else base['saved'])


def test_clear_retains_exact_clear_pair_before_wrong_cursor_fails(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, rows_holder = common(monkeypatch, t)
    placed = placement(base)
    expected = op.expected_saved(base, 3, True)
    saved_holder[0], shown_holder[0], rows_holder[0] = expected, public(expected['actions']), requests(clear=True)
    stage = {'baseline': base, 'placement': placed, 'public': shown_holder[0], 'source': ref(SOURCE)}
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    original_drag = t.drag
    def shift_drag(start, end):
        assert t.persisted[-1]['clear_input_sent'] is True
        original_drag(start, end)
        t.cursor = ['spell', 6948]
        shown_holder[0] = base['public']
    t.io.drag = shift_drag
    monkeypatch.setattr(op, 'server_save', lambda: pytest.fail('invalid cursor must not save in normal clear'))
    with pytest.raises(RuntimeError, match='exact carried Hearthstone'):
        op.clear(t, PREP, SOURCE, REVIEW)
    assert t.receipt['clear_request_proof']['action'] == 0
    assert [e[0] for e in t.events] == ['held', 'shift_drag']
    assert t.receipt['raw_clear_failure']['cursor_info'] == ['spell', 6948]


def test_clear_sends_one_shift_pickup_then_one_right_cancel_and_save(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, rows_holder = common(monkeypatch, t)
    placed = placement(base)
    saved_holder[0] = op.expected_saved(base, 3, True)
    shown_holder[0] = public(saved_holder[0]['actions'])
    stage = {'baseline': base, 'placement': placed, 'public': deepcopy(shown_holder[0]), 'source': ref(SOURCE)}
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    rows_holder[0] = requests(clear=True, at=22)
    original_drag = t.drag
    def shift_drag(start, end):
        original_drag(start, end)
        shown_holder[0] = base['public']
    t.io.drag = shift_drag
    def save():
        t.events.append(('saveall',))
        saved_holder[0] = base['saved']
    monkeypatch.setattr(op, 'server_save', save)
    monkeypatch.setattr(op.time, 'time', lambda: 23)
    rows_holder[0] = requests(clear=True, at=23)
    op.clear(t, PREP, SOURCE, REVIEW)
    assert [e[0] for e in t.events] == ['held', 'shift_drag', 'execute', 'saveall']
    assert t.events[2][1]['button'] == 3
    assert t.receipt['phase'] == 'item_actionbar_restored' and t.receipt['after_saved'] == base['saved']
    assert t.receipt['cursor_after_cancel'] == []


def failed_receipt(base, *, clear=False):
    return {'actor': SCOUT, 'runtime': RUNTIME, 'preparation_source': ref(PREP), 'native_session': 'owned',
        'started_at': 10 if not clear else 15, 'finished_at': 19, 'completed': False,
        'failure': 'RuntimeError: outcome capture interrupted', 'qualification_added': False, 'baseline': base,
        'phase': 'item_actionbar_clear_started' if clear else 'item_actionbar_drag_started',
        'drag_input_sent': True, 'drag_started_at': 10, 'drag_finished_at': 11,
        'drag_packets': requests(at=10.1), 'drag_intent': {'slot0': 3},
        'clear_input_sent': clear, 'clear_started_at': 15 if clear else None,
        'clear_intent': {'slot0': 3, 'end': [600, 600]}, 'placement': placement(base) if clear else None,
        'drag_source': ref(SOURCE), 'placement_saved': op.expected_saved(base, 3, True),
        'placement_resources': base['resources']}


def recovery_common(monkeypatch, t, base, failed, raw, rows):
    monkeypatch.setattr(op, 'context', lambda *args: ({'all_offline_snapshot': base['snapshot']}, 'owned'))
    monkeypatch.setattr(op, 'private_json', lambda path: deepcopy(failed))
    monkeypatch.setattr(op, 'closed', lambda path, **kwargs: deepcopy(failed))
    monkeypatch.setattr(op, 'entry_source', lambda *args: {'saved': base['saved'], 'resources': base['resources'],
        'active_spec': base['active_spec'], 'native_original': base['native_original'], 'public': base['public'],
        'precision_source': base['precision_source'], 'state': base['state']})
    monkeypatch.setattr(op, 'retain_raw', lambda *args: deepcopy(raw))
    monkeypatch.setattr(op, 'packet_rows', lambda *args: deepcopy(rows))


def test_failed_placement_lost_before_saveall_is_recovered_without_drag(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, _ = common(monkeypatch, t)
    failed = failed_receipt(base)
    immutable = deepcopy(failed)
    shown_holder[0] = public(op.expected_saved(base, 3, True)['actions'])
    rows = requests(at=10.1)
    raw = {'saved': base['saved'], 'resources': base['resources'], 'public': shown_holder[0], 'state': state(), 'frame': {}}
    recovery_common(monkeypatch, t, base, failed, raw, rows)
    def save():
        t.events.append(('saveall',))
        saved_holder[0] = op.expected_saved(base, 3, True)
    monkeypatch.setattr(op, 'server_save', save)
    op.recover(t, PREP, SOURCE)
    assert t.events == [('saveall',)] and failed == immutable
    assert t.receipt['phase'] == 'item_actionbar_recovery_placed'
    assert t.receipt['recovery_only'] is True and t.receipt['failed_whole_excluded'] is True
    assert t.receipt['drag_input_sent'] is False and t.receipt['gameplay_input_replayed'] is False


def test_failed_clear_saves_stale_sql_before_fresh_cursor_review_without_shift_replay(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, _ = common(monkeypatch, t)
    saved_holder[0] = op.expected_saved(base, 3, True)
    failed = failed_receipt(base, clear=True)
    rows = requests(clear=True, at=15.1)
    t.cursor = ['item', 6948]
    raw = {'saved': saved_holder[0], 'resources': base['resources'], 'public': base['public'],
        'state': state(cursor=t.cursor), 'frame': {'file': 'current.png'}}
    recovery_common(monkeypatch, t, base, failed, raw, rows)
    def save():
        t.events.append(('saveall',))
        saved_holder[0] = base['saved']
    monkeypatch.setattr(op, 'server_save', save)
    op.recover(t, PREP, SOURCE)
    assert t.events == [('saveall',)] and saved_holder[0] == base['saved']
    assert t.receipt['phase'] == 'item_actionbar_cursor_ready'
    assert t.receipt['clear_request_proof']['action'] == 0
    assert t.receipt['clear_input_sent'] is False and t.receipt['drag_input_sent'] is False
    assert t.receipt['cursor_cancel_point'] == [600, 600]


def test_recovery_refuses_an_unrelated_saved_change_before_any_save(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, _ = common(monkeypatch, t)
    failed = failed_receipt(base)
    unexpected = deepcopy(base['saved'])
    unexpected['quests']['old'].append(1)
    rows = requests(at=10.1)
    shown = public(op.expected_saved(base, 3, True)['actions'])
    raw = {'saved': unexpected, 'resources': base['resources'], 'public': shown, 'state': state(), 'frame': {}}
    recovery_common(monkeypatch, t, base, failed, raw, rows)
    monkeypatch.setattr(op, 'server_save', lambda: pytest.fail('unrelated change must not save'))
    with pytest.raises(RuntimeError, match='unrelated saved'):
        op.recover(t, PREP, SOURCE)
    assert t.events == [] and t.receipt['failed_whole_excluded'] is True


def test_no_outcome_recovery_remains_excluded_and_restores_baseline(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, _, _, _ = common(monkeypatch, t)
    failed = failed_receipt(base)
    raw = {'saved': base['saved'], 'resources': base['resources'], 'public': base['public'], 'state': state(), 'frame': {}}
    recovery_common(monkeypatch, t, base, failed, raw, [])
    monkeypatch.setattr(op, 'server_save', lambda: pytest.fail('absent native outcome must not save'))
    op.recover(t, PREP, SOURCE)
    assert t.receipt['phase'] == 'item_actionbar_restored' and t.receipt['placement_absent'] is True
    assert t.receipt['first_failure_source'] == ref(SOURCE) and t.events == []


def test_cursor_settlement_only_cancels_after_source_bound_saved_clear(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, _, shown_holder, rows_holder = common(monkeypatch, t)
    failed = failed_receipt(base, clear=True)
    placed = placement(base)
    rows = requests(clear=True, at=15.1)
    pair = proof.action_packets(rows, 'owned', 15, 19, 3, clear=True)
    t.cursor = ['item', 6948]
    stage = {'baseline': base, 'placement': placed, 'clear_started_at': 15, 'clear_request_proof': pair,
        'first_failure_source': ref(SOURCE), 'cursor_cancel_point': [600, 600], 'frame': {'file': 'reviewed.png'},
        'state': state(cursor=t.cursor), 'recovery_only': True, 'failed_whole_excluded': True}
    rows_holder[0] = rows
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    monkeypatch.setattr(op, 'closed', lambda *args, **kwargs: failed)
    review = {'source': ref(SOURCE), 'frame': stage['frame'], 'point': [600, 600],
        'empty_point_reviewed': True, 'empty_point_world_space': True}
    monkeypatch.setattr(op, 'reviewed', lambda *args: review)
    monkeypatch.setattr(op, 'server_save', lambda: pytest.fail('already saved cursor settlement must not need save'))
    op.cursor_settlement(t, PREP, SOURCE, REVIEW)
    assert len(t.events) == 1 and t.events[0][0] == 'execute' and t.events[0][1]['button'] == 3
    assert t.receipt['phase'] == 'item_actionbar_restored'
    assert t.receipt['clear_input_sent'] is False and t.receipt['gameplay_input_replayed'] is False


def test_pixel_geometry_rejects_moved_reviewed_point(tmp_path):
    from PIL import Image
    old_dir, new_dir = tmp_path / 'old', tmp_path / 'new'
    old_dir.mkdir()
    new_dir.mkdir()
    image = Image.new('RGB', (1280, 720), (3, 4, 5))
    image.save(old_dir / 'old.png')
    image.save(new_dir / 'new.png')
    stage = {'state': state(), 'frame': {'file': 'old.png', 'sha256': op.lab.sha256(old_dir / 'old.png')}}
    trial = SimpleNamespace(out=new_dir)
    result = op.screen_geometry(trial, old_dir / 'episode.json', stage, state(), {'file': 'new.png'}, ([400, 500],))
    assert result['exact_pixels'] is True
    image.putpixel((400, 500), (9, 9, 9))
    image.save(new_dir / 'new.png')
    with pytest.raises(RuntimeError, match='pixels changed'):
        op.screen_geometry(trial, old_dir / 'episode.json', stage, state(), {'file': 'new.png'}, ([400, 500],))


def test_private_source_rejects_symlink_ancestor(monkeypatch, tmp_path):
    import json
    real = tmp_path / 'evidence' / 'real'
    real.mkdir(parents=True)
    (real / 'episode.json').write_text(json.dumps({'completed': True}))
    link = tmp_path / 'evidence' / 'alias'
    link.symlink_to(real, target_is_directory=True)
    monkeypatch.setattr(op.lab, 'ROOT', tmp_path)
    with pytest.raises(RuntimeError, match='private owned'):
        op.private_json(link / 'episode.json')


@pytest.mark.parametrize('fault', [None, 'saved', 'resources', 'pose', 'afk', 'target', 'spec', 'public'])
def test_full_baseline_is_bound_to_immutable_entry(fault):
    base = baseline()
    entry = {'saved': deepcopy(base['saved']), 'resources': deepcopy(base['resources']),
        'active_spec': 0, 'native_original': deepcopy(base['native_original']),
        'precision_source': base['precision_source'], 'public': deepcopy(base['public']), 'state': deepcopy(base['state'])}
    if fault == 'saved': base['saved']['quests']['old'].append(1)
    elif fault == 'resources': base['resources']['backpack'][0]['count'] = 2
    elif fault == 'pose': base['native_state']['pose']['stand'] = 1
    elif fault == 'afk': base['native_state']['afk'] = True
    elif fault == 'target': base['native_state']['selection'] = 9
    elif fault == 'spec': base['active_spec'] = False
    elif fault == 'public': base['public']['actions'][4].update(kind='spell', id=78)
    if fault:
        with pytest.raises(RuntimeError):
            op.baseline_authority(base, entry, {'all_offline_snapshot': base['snapshot']})
    else:
        op.baseline_authority(base, entry, {'all_offline_snapshot': base['snapshot']})


@pytest.mark.parametrize('fault', [None, 'missing_request', 'saved_quest', 'retained_packet', 'resource'])
def test_cleanup_rederives_placement_from_actual_journal(monkeypatch, fault):
    base = baseline()
    placed = placement(base)
    rows = requests(at=10.1)
    stage = {'baseline': base, 'placement': placed, 'drag_started_at': 10, 'drag_finished_at': 11,
        'drag_packets': deepcopy(rows), 'placement_saved': op.expected_saved(base, 3, True),
        'placement_resources': deepcopy(base['resources'])}
    if fault == 'missing_request': rows.pop()
    elif fault == 'saved_quest': stage['placement_saved']['quests']['old'].append(1)
    elif fault == 'retained_packet': stage['drag_packets'][0]['body'] = 'bad'
    elif fault == 'resource': stage['placement_resources']['backpack'][0]['count'] = 2
    monkeypatch.setattr(op, 'packet_rows', lambda *args: deepcopy(rows))
    if fault:
        with pytest.raises(RuntimeError):
            op.validate_placement(stage, 'owned')
    else:
        assert op.validate_placement(stage, 'owned') == placed


@pytest.mark.parametrize('fault', [None, 'slot', 'float_item', 'source', 'frame', 'inside', 'bounds', 'grid_unreviewed', 'wrong_grid'])
def test_drag_review_binds_actual_public_button_and_two_fresh_points(monkeypatch, fault):
    base = baseline()
    stage = drag_stage(base)
    monkeypatch.setattr(op, 'point', lambda control: [20, 20])
    monkeypatch.setattr(op, 'bound', ref)
    d = {'source': ref(SOURCE), 'frame': stage['frame'], 'slot0': 3, 'item': 6948, 'item_guid': 41,
        'public_button': stage['button'], 'point': [20, 20], 'pickup_point_inside_button': True,
        'source_control': stage['source_control'], 'destination_point': [500, 600],
        'destination_point_inside_button': True, 'stock_grid_cell_reviewed': True, 'stock_grid_source': proof.GRID_SOURCE}
    if fault == 'slot': d['slot0'] = 11
    elif fault == 'float_item': d['item'] = 6948.0
    elif fault == 'source': d['source'] = ref(PREP)
    elif fault == 'frame': d['frame'] = {'file': 'old.png'}
    elif fault == 'inside': d['destination_point_inside_button'] = False
    elif fault == 'bounds': d['destination_point'] = [1280, 500]
    elif fault == 'grid_unreviewed': d['stock_grid_cell_reviewed'] = False
    elif fault == 'wrong_grid': d['stock_grid_source'] = {**proof.GRID_SOURCE, 'sha256': 'wrong'}
    monkeypatch.setattr(op, 'reviewed', lambda *args: d)
    if fault:
        with pytest.raises(RuntimeError):
            op.reviewed_points(SimpleNamespace(receipt={}), REVIEW, SOURCE, stage)
    else:
        assert op.reviewed_points(SimpleNamespace(receipt={}), REVIEW, SOURCE, stage) == ([20, 20], [500, 600])


def test_recon_uses_reviewed_backpack_icon_and_observed_empty_button(monkeypatch, tmp_path):
    t = Trial(tmp_path)
    base, _, _, _ = common(monkeypatch, t)
    entry = {'saved': base['saved'], 'resources': base['resources'], 'public': base['public'], 'active_spec': 0,
        'precision_source': base['precision_source'], 'native_original': base['native_original'],
        'state': base['state'], 'frame': {'file': 'entry.png'}}
    monkeypatch.setattr(op, 'context', lambda *args: ({'all_offline_snapshot': base['snapshot']}, 'owned'))
    monkeypatch.setattr(op, 'entry_source', lambda *args: entry)
    monkeypatch.setattr(op, 'reviewed', lambda *args: {'source': ref(ENTRY), 'frame': entry['frame'],
        'point': [800, 650], 'pickup_point_inside_button': True})
    def observe(label):
        shown = state(bags=[] if label == 'item_actionbar_original' else [0])
        shown['bag_items'] = [{'bag': 0, 'slot': 1, 'id': 6948, 'count': 1, 'locked': False}]
        return shown, {'file': label + '.png'}
    t.observe = observe
    op.recon(t, PREP, ENTRY, REVIEW)
    assert t.events == [('execute', {'kind': 'click', 'value': [800, 650]})]
    assert t.receipt['phase'] == 'item_actionbar_reconciled'
    assert t.receipt['button']['button'] == 'ActionButton2' and t.receipt['slot0'] == 1
    assert t.receipt['baseline']['native_original'] == entry['native_original']


@pytest.mark.parametrize('fault', [None, 'old_review', 'consumed_before_click', 'changed_code_without_capture'])
def test_recon_fresh_screen_review_and_entry_attempt_guards(monkeypatch, tmp_path, fault):
    from tools.client_compatibility import interaction_item_actionbar_entry_capture as cap
    t = Trial(tmp_path)
    base, _, _, _ = common(monkeypatch, t)
    entry = {'saved': base['saved'], 'resources': base['resources'], 'public': base['public'], 'active_spec': 0,
        'precision_source': base['precision_source'], 'native_original': base['native_original'],
        'state': base['state'], 'frame': {'file': 'original_entry.png'}, 'code_commit': 'a' * 40}
    fresh = {**entry, 'frame': {'file': 'fresh_entry.png'}, 'code_commit': 'b' * 40}
    fresh_path = tmp_path / 'fresh/episode.json'
    t.receipt['code_commit'] = fresh['code_commit']
    monkeypatch.setattr(op, 'context', lambda *args: ({'all_offline_snapshot': base['snapshot']}, 'owned'))
    monkeypatch.setattr(op, 'entry_source', lambda *args: entry)
    sources, gates, geometry = [], [], []
    def source(*args):
        sources.append(args[-1])
        return fresh
    def gate(reference):
        gates.append(reference)
        if fault == 'consumed_before_click' and len(gates) == 2:
            raise RuntimeError('entry consumed before bag click')
    monkeypatch.setattr(cap, 'screen_source', source)
    monkeypatch.setattr(cap, 'unconsumed', gate)
    reviewed_source = ENTRY if fault == 'old_review' else fresh_path
    reviewed_frame = entry['frame'] if fault == 'old_review' else fresh['frame']
    monkeypatch.setattr(op, 'reviewed', lambda *args: {'source': ref(reviewed_source), 'frame': reviewed_frame,
        'point': [800, 650], 'pickup_point_inside_button': True})
    monkeypatch.setattr(op, 'screen_geometry', lambda trial, path, screen, *args:
        geometry.append((path, screen['frame'])) or {'exact_pixels': True})
    def observe(label):
        shown = state(bags=[] if label == 'item_actionbar_original' else [0])
        shown['bag_items'] = [{'bag': 0, 'slot': 1, 'id': 6948, 'count': 1, 'locked': False}]
        return shown, {'file': label + '.png'}
    t.observe = observe
    if fault:
        with pytest.raises(RuntimeError):
            op.recon(t, PREP, ENTRY, REVIEW, None if fault == 'changed_code_without_capture' else fresh_path)
        assert t.events == []
    else:
        op.recon(t, PREP, ENTRY, REVIEW, fresh_path)
        assert sources == [fresh_path] and gates == [ref(ENTRY), ref(ENTRY)]
        assert geometry == [(fresh_path, fresh['frame'])]
        assert t.events == [('execute', {'kind': 'click', 'value': [800, 650]})]
        assert t.receipt['baseline']['entry_source'] == ref(ENTRY)


def attempt_fixture(monkeypatch, tmp_path, kind='drag'):
    root = tmp_path / 'lab'
    entry_dir = root / 'evidence' / 'entry'
    entry_dir.mkdir(parents=True, mode=0o700)
    entry = entry_dir / 'episode.json'
    entry.write_text(json.dumps({'completed': True, 'actor': SCOUT, 'native_session': 'owned',
        'started_at': 5, 'finished_at': 6, 'failure': None}))
    output = root / 'evidence' / 'output1'
    output.mkdir(mode=0o700)
    trial = Trial(output)
    trial.receipt.update(preparation_source=ref(PREP), native_session='owned')
    base = baseline()
    base['entry_source'] = op.bound(entry)
    intent = {'source': ref(SOURCE), 'review': ref(REVIEW), 'slot0': 3,
        'item': 6948, 'item_guid': 41, 'start': [20, 20], 'end': [600, 600]}
    monkeypatch.setattr(op.lab, 'ROOT', root)
    return trial, base, intent, entry_dir / ('item_actionbar_' + kind + '_attempt.json')


@pytest.mark.parametrize('kind', ['drag', 'clear'])
def test_attempt_marker_is_exclusive_private_durable_and_bound_to_entry(monkeypatch, tmp_path, kind):
    t, base, intent, marker = attempt_fixture(monkeypatch, tmp_path, kind)
    fsync = op.os.fsync
    synced = []
    def sync(fd):
        synced.append(fd)
        fsync(fd)
    monkeypatch.setattr(op.os, 'fsync', sync)
    result = op.consume_attempt(t, base, 'owned', kind, intent)
    actual = json.loads(marker.read_text())
    assert os.stat(marker).st_mode & 0o777 == 0o600
    assert len(synced) == 2 and actual['entry_source'] == base['entry_source']
    assert actual['runtime'] == RUNTIME and actual['actor'] == SCOUT and actual['native_session'] == 'owned'
    assert actual['operation_output'] == str(t.out / 'episode.json') and actual['input_intent'] == intent
    assert actual['consumed'] is True and actual['input_replay_allowed'] is False
    assert t.receipt[kind + '_attempt_source'] == result == op.bound(marker)
    changed = {**intent, 'source': ref(Path('/new/capture/episode.json'))}
    with pytest.raises(RuntimeError, match='already consumed'):
        op.consume_attempt(t, base, 'owned', kind, changed)
    assert json.loads(marker.read_text()) == actual and len(synced) == 2


def test_marker_symlink_is_rejected_without_touching_target(monkeypatch, tmp_path):
    t, base, intent, marker = attempt_fixture(monkeypatch, tmp_path)
    protected = marker.with_name('protected.json')
    protected.write_text('unchanged')
    marker.symlink_to(protected)
    with pytest.raises(RuntimeError, match='already consumed'):
        op.consume_attempt(t, base, 'owned', 'drag', intent)
    assert protected.read_text() == 'unchanged' and marker.is_symlink()


@pytest.mark.parametrize('interruption', [RuntimeError('no native outcome'), KeyboardInterrupt('interrupted input')])
def test_failed_drag_consumption_survives_changed_capture_and_baseline_restoration(monkeypatch, tmp_path, interruption):
    consume, real_bound = op.consume_attempt, op.bound
    t1, base, _, marker = attempt_fixture(monkeypatch, tmp_path)
    _, _, _, _ = common(monkeypatch, t1, base)
    monkeypatch.setattr(op, 'consume_attempt', consume)
    monkeypatch.setattr(op, 'bound', lambda path: real_bound(path) if Path(path).is_file() else ref(path))
    stage = drag_stage(base)
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    def fail(action):
        assert marker.is_file() and t1.persisted[-1]['drag_attempt_source'] == real_bound(marker)
        t1.events.append(('execute', deepcopy(action)))
        raise interruption
    t1.execute = fail
    if isinstance(interruption, Exception):
        op.run(t1, 'drag', PREP, SOURCE, REVIEW)
    else:
        with pytest.raises(KeyboardInterrupt):
            op.run(t1, 'drag', PREP, SOURCE, REVIEW)
    before = marker.read_bytes()
    assert t1.receipt['completed'] is False and len(t1.events) == 1
    # Current native/public rows are the complete baseline after failed no-outcome
    # housekeeping. A fresh capture alone must not grant another input attempt.
    output2 = t1.out.with_name('output2')
    output2.mkdir(mode=0o700)
    t2 = Trial(output2)
    t2.receipt.update(preparation_source=ref(PREP), native_session='owned')
    changed_source = Path('/private/new-capture/episode.json')
    stage['frame'] = {'file': 'new-capture.png', 'sha256': 'd' * 64}
    with pytest.raises(RuntimeError, match='already consumed'):
        op.drag(t2, PREP, changed_source, REVIEW)
    assert t2.events == [] and marker.read_bytes() == before
    assert t2.receipt['attempt_consumption_refused']['input_replayed'] is False


def test_failed_shift_clear_consumption_survives_another_capture(monkeypatch, tmp_path):
    consume, real_bound = op.consume_attempt, op.bound
    t1, base, _, marker = attempt_fixture(monkeypatch, tmp_path, 'clear')
    _, saved_holder, shown_holder, rows_holder = common(monkeypatch, t1, base)
    monkeypatch.setattr(op, 'consume_attempt', consume)
    monkeypatch.setattr(op, 'bound', lambda path: real_bound(path) if Path(path).is_file() else ref(path))
    placed = placement(base)
    saved_holder[0] = op.expected_saved(base, 3, True)
    shown_holder[0] = public(saved_holder[0]['actions'])
    rows_holder[0] = requests(clear=True)
    stage = {'baseline': base, 'placement': placed, 'public': deepcopy(shown_holder[0]), 'source': ref(SOURCE)}
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    def fail(start, end):
        assert marker.is_file() and t1.persisted[-1]['clear_attempt_source'] == real_bound(marker)
        t1.events.append(('shift_attempt', start, end))
        raise KeyboardInterrupt('interrupted Shift clear')
    t1.io.drag = fail
    with pytest.raises(KeyboardInterrupt):
        op.run(t1, 'clear', PREP, SOURCE, REVIEW)
    before = marker.read_bytes()
    output2 = t1.out.with_name('output2')
    output2.mkdir(mode=0o700)
    t2 = Trial(output2)
    t2.receipt.update(preparation_source=ref(PREP), native_session='owned')
    with pytest.raises(RuntimeError, match='already consumed'):
        op.clear(t2, PREP, Path('/private/new-clear-capture/episode.json'), REVIEW)
    assert t2.events == [] and marker.read_bytes() == before


def test_interrupted_marker_write_still_consumes_the_entry(monkeypatch, tmp_path):
    t, base, intent, marker = attempt_fixture(monkeypatch, tmp_path)
    sync = op.os.fsync
    def interrupted_sync(fd):
        raise KeyboardInterrupt('during marker durability')
    monkeypatch.setattr(op.os, 'fsync', interrupted_sync)
    with pytest.raises(KeyboardInterrupt):
        op.consume_attempt(t, base, 'owned', 'drag', intent)
    assert marker.is_file() and t.events == []
    monkeypatch.setattr(op.os, 'fsync', sync)
    with pytest.raises(RuntimeError, match='already consumed'):
        op.consume_attempt(t, base, 'owned', 'drag', intent)


@pytest.mark.parametrize('fault', [None, 'power', 'xp', 'missing_health'])
def test_sparse_native_owner_fields_default_only_omitted_zero_values(monkeypatch, fault):
    from tools.client_compatibility.world.objects import INDEX
    # A native creation mask transmits nonzero values and omits power/XP0.
    fields = {INDEX['UNIT_FIELD_HEALTH']: 60, INDEX['UNIT_FIELD_MAXHEALTH']: 60,
        INDEX['PLAYER_NEXT_LEVEL_XP']: 400}
    if fault == 'power': fields[INDEX['UNIT_FIELD_POWER1']] = 7
    elif fault == 'xp': fields[INDEX['PLAYER_XP']] = 7
    elif fault == 'missing_health': fields.pop(INDEX['UNIT_FIELD_HEALTH'])
    oracle = SimpleNamespace(objects={2: fields}, guid=2, pair=lambda *args: 0)
    oracle.poll = lambda: oracle
    monkeypatch.setattr(op, 'inventory', lambda session: oracle)
    base = baseline()
    monkeypatch.setattr(op, 'saved', lambda: base['saved'])
    monkeypatch.setattr(op, 'resources', lambda session: base['resources'])
    monkeypatch.setattr(op, 'peers', lambda base: {'all': True})
    observed = op.native_state('owned')
    assert observed['power'] == (7 if fault == 'power' else 0)
    assert observed['xp'] == (7 if fault == 'xp' else 0)
    if fault:
        with pytest.raises(RuntimeError, match='health, rage, XP'):
            op.assert_live(base, 'owned', base['saved'])
    else:
        _, _, guarded, checks = op.assert_live(base, 'owned', base['saved'])
        assert guarded['health'] == guarded['max_health'] == 60 and checks == {'all': True}


@pytest.mark.parametrize('placed', [False, True])
def test_capture_accepts_hidden_empty_grid_but_requires_visible_placed_item(monkeypatch, tmp_path, placed):
    t = Trial(tmp_path)
    base, saved_holder, shown_holder, _ = common(monkeypatch, t)
    inserted = placement(base) if placed else None
    saved_holder[0] = op.expected_saved(base, 3, placed)
    shown_holder[0] = public(saved_holder[0]['actions'])
    stage = {'baseline': base, 'slot0': 3, 'placement': inserted}
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    op.capture(t, PREP, SOURCE)
    assert t.receipt['button']['visible'] is placed
    assert t.receipt['phase'] == ('item_actionbar_clear_ready' if placed else 'item_actionbar_drag_ready')
    if placed:
        shown_holder[0]['actions'][3]['visible'] = False
        with pytest.raises(RuntimeError, match='placed item'):
            op.capture(Trial(tmp_path), PREP, SOURCE)


def test_real_hidden_grid_drop_visible_item_clear_hidden_roundtrip_preserves_flyout(monkeypatch, tmp_path):
    t1 = Trial(tmp_path)
    base = baseline()
    base['saved']['actions'] = [[0, 0, 6603, 0], [0, 8, 2, 48], [1, 8, 78, 0]]
    base['public'] = public(base['saved']['actions'])
    base['native_original']['actions'] = deepcopy(base['saved']['actions'])
    _, saved_holder, shown_holder, rows_holder = common(monkeypatch, t1, base)
    assert all(r['visible'] is False for r in base['public']['actions'] if not r['kind'])
    stage = drag_stage(base)
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    execute = t1.execute
    def drop(action):
        execute(action)
        shown_holder[0] = public(op.expected_saved(base, 3, True)['actions'])
    t1.execute = drop
    monkeypatch.setattr(op, 'server_save', lambda: saved_holder.__setitem__(0, op.expected_saved(base, 3, True)))
    op.drag(t1, PREP, SOURCE, REVIEW)
    assert t1.receipt['placement']['button']['visible'] is True
    assert t1.receipt['stock_grid_sources'] == [proof.GRID_SOURCE]
    t2 = Trial(tmp_path)
    stage2 = {'baseline': base, 'placement': t1.receipt['placement'], 'public': deepcopy(shown_holder[0]), 'source': ref(SOURCE)}
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage2))
    rows_holder[0] = requests(clear=True)
    shift = t2.drag
    def pickup(start, end):
        shift(start, end)
        shown_holder[0] = base['public']
    t2.io.drag = pickup
    monkeypatch.setattr(op, 'server_save', lambda: saved_holder.__setitem__(0, deepcopy(base['saved'])))
    op.clear(t2, PREP, SOURCE, REVIEW)
    assert t2.receipt['clear_proof']['button']['visible'] is False
    assert t2.receipt['after_saved'] == base['saved']
    assert shown_holder[0]['actions'][8] == base['public']['actions'][8] == {
        'button': 'ActionButton9', 'slot': 9, 'kind': 'flyout', 'id': 2, 'visible': True}


@pytest.mark.parametrize('fault', ['mainbar_hidden', 'visibility_unknown'])
def test_hidden_empty_grid_is_not_admitted_without_the_visible_stock_bar(monkeypatch, tmp_path, fault):
    t = Trial(tmp_path)
    base, _, shown_holder, _ = common(monkeypatch, t)
    stage = {'baseline': base, 'slot0': 3}
    monkeypatch.setattr(op, 'prior', lambda *args: ({}, 'owned', stage))
    if fault == 'mainbar_hidden':
        shown_holder[0]['frames']['MainMenuBar'] = False
    else:
        shown_holder[0]['actions'][3]['visible'] = None
    with pytest.raises(RuntimeError):
        op.capture(t, PREP, SOURCE)
    assert t.events == []

"""Reject borrowed auto-placement and clear evidence before ordinary cleanup."""
from contextlib import contextmanager
from copy import deepcopy
import itertools
from pathlib import Path
import struct
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import hunter_learn_autobar as proof
from tools.client_compatibility import hunter_learn_contract as contract
from tools.client_compatibility import interaction_hunter_learn_autobar as controller


def packet(direction, name, body, time):
    return {'session': 'hunter', 'time': time, 'direction': direction, 'name': name, 'body': body.hex()}


def requests(slot0=3, value=1462, at=10.3):
    return [packet('from_client', proof.ACTION, struct.pack('<IB', value, slot0), at),
        packet('to_native', proof.ACTION, struct.pack('<BI', slot0, value), at + .1)]


def learning(slot0=3):
    return [packet('from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', 1462, 0), 10.1),
        packet('to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, 1462, 0), 10.2),
        *requests(slot0)]


def public(actions, spec=0, page=1):
    mapping = {r[1]: r[2:] for r in actions if r[0] == spec}
    rows = []
    for index in range(1, 13):
        slot = index + (page - 1) * 12
        entry = mapping.get(slot - 1)
        rows.append({'button': 'ActionButton' + str(index), 'slot': slot, 'visible': True,
            **({'kind': {0: 'spell', 64: 'macro', 128: 'item'}[entry[1]], 'id': entry[0]} if entry else {})})
    return {'active_spec': spec + 1, 'page': page, 'effective_page': page, 'bonus_offset': 0,
        'frames': {'MainMenuBar': True}, 'actions': rows}


def baseline():
    return [[0, 0, 6603, 0], [0, 10, 6948, 128], [1, 3, 1515, 0]]


def placement():
    old = baseline()
    after = sorted(old + [[0, 3, 1462, 0]])
    return proof.addition_guard(old, after, learning(), 'hunter', 10, 11, 0, public(after))


def test_one_new_native_slot_and_actual_public_button_after_exact_learn_delivery():
    result = placement()
    assert result['slot0'] == 3 and result['button']['button'] == 'ActionButton4'
    assert result['modern']['body'] == 'b605000003' and result['native']['body'] == '03b6050000'
    assert len(result['checks']) == 6 and all(result['checks'].values())
    result['after_actions'].clear()
    assert baseline() == [[0, 0, 6603, 0], [0, 10, 6948, 128], [1, 3, 1515, 0]]


def test_unchanged_actions_require_no_owned_action_request_and_exact_public_assignments():
    old = baseline()
    assert proof.addition_guard(old, old, learning()[:2], 'hunter', 10, 11, 0, public(old)) is None
    borrowed = [{**p, 'session': 'another'} for p in requests()]
    assert proof.addition_guard(old, old, borrowed, 'hunter', 10, 11, 0, public(old)) is None
    with pytest.raises(RuntimeError, match='hide an action placement'):
        proof.addition_guard(old, old, learning(), 'hunter', 10, 11, 0, public(old))
    drift = public(old)
    drift['actions'][1].update(kind='spell', id=1462)
    with pytest.raises(RuntimeError, match='public action assignment'):
        proof.addition_guard(old, old, [], 'hunter', 10, 11, 0, drift)


@pytest.mark.parametrize('fault', ['missing_modern', 'missing_native', 'foreign', 'before_window', 'after_window',
    'duplicate', 'wrong_modern_order', 'wrong_native_order', 'wrong_spell', 'wrong_slot', 'unrelated_request',
    'early_placement', 'reversed_pair', 'late_pair', 'missing_learn', 'wrong_learn', 'duplicate_learn', 'late_learn',
    'wrong_spec', 'occupied', 'two_added', 'removed_other', 'wrong_type', 'unsorted', 'duplicate_slot',
    'public_wrong_spec', 'public_wrong_spell', 'public_wrong_slot', 'hidden', 'public_other_drift',
    'missing_button', 'wrong_button', 'nonfinite', 'bool_slot', 'hidden_bar'])
def test_addition_rejects_foreign_reordered_or_drifted_actions(fault):
    old = baseline()
    after = sorted(old + [[0, 3, 1462, 0]])
    rows, shown, spec = learning(), public(after), 0
    if fault == 'missing_modern': rows.pop(2)
    elif fault == 'missing_native': rows.pop(3)
    elif fault == 'foreign': rows[2]['session'] = 'foreign'
    elif fault == 'before_window': rows[2]['time'] = 9.9
    elif fault == 'after_window': rows[3]['time'] = 11.1
    elif fault == 'duplicate': rows.append(deepcopy(rows[2]))
    elif fault == 'wrong_modern_order': rows[2]['body'] = struct.pack('<BI', 3, 1462).hex()
    elif fault == 'wrong_native_order': rows[3]['body'] = struct.pack('<IB', 1462, 3).hex()
    elif fault == 'wrong_spell': rows[2]['body'] = struct.pack('<IB', 1515, 3).hex()
    elif fault == 'wrong_slot': rows[3]['body'] = struct.pack('<BI', 4, 1462).hex()
    elif fault == 'unrelated_request': rows += requests(slot0=7, value=1515)
    elif fault == 'early_placement': rows[2]['time'] = 10.19
    elif fault == 'reversed_pair': rows[2]['time'] = 10.5
    elif fault == 'late_pair': rows[3]['time'] = 12.3
    elif fault == 'missing_learn': rows.pop(1)
    elif fault == 'wrong_learn': rows[1]['body'] = struct.pack('<IIBIB', 1, 0, 0, 1515, 0).hex()
    elif fault == 'duplicate_learn': rows.append(deepcopy(rows[1]))
    elif fault == 'late_learn': rows[0]['time'], rows[1]['time'] = 8.2, 10.2
    elif fault == 'wrong_spec': spec = 1
    elif fault == 'occupied': old = sorted(old + [[0, 3, 1515, 0]])
    elif fault == 'two_added': after = sorted(after + [[0, 4, 1462, 0]])
    elif fault == 'removed_other': after.pop(0)
    elif fault == 'wrong_type': after[1][3] = 64
    elif fault == 'unsorted': after.reverse()
    elif fault == 'duplicate_slot': after.insert(1, deepcopy(after[1]))
    elif fault == 'public_wrong_spec': shown['active_spec'] = 2
    elif fault == 'public_wrong_spell': shown['actions'][3]['id'] = 1515
    elif fault == 'public_wrong_slot': shown['actions'][3]['slot'] = 20
    elif fault == 'hidden': shown['actions'][3]['visible'] = False
    elif fault == 'public_other_drift': shown['actions'][7].update(kind='spell', id=1515)
    elif fault == 'missing_button': shown['actions'].pop()
    elif fault == 'wrong_button': shown['actions'][3]['button'] = 'ActionButton12'
    elif fault == 'nonfinite': rows[2]['time'] = float('nan')
    elif fault == 'bool_slot': after[1][1] = True
    elif fault == 'hidden_bar': shown['frames']['MainMenuBar'] = False
    with pytest.raises(RuntimeError):
        proof.addition_guard(old, after, rows, 'hunter', 8 if fault == 'late_learn' else 10,
            13 if fault == 'late_pair' else 11, spec, shown)


def test_auto_placement_can_use_an_observed_slot_on_a_different_main_bar_page():
    old, after = baseline(), sorted(baseline() + [[0, 29, 1462, 0]])
    result = proof.addition_guard(old, after, learning(29), 'hunter', 10, 11, 0, public(after, page=3))
    assert result['slot0'] == 29 and result['button']['slot'] == 30
    assert result['button']['button'] == 'ActionButton6'


@pytest.mark.parametrize('fault', [None, 'missing', 'duplicate', 'wrong_slot', 'wrong_id', 'wrong_session',
    'late_pair', 'before_placement', 'saved_extra', 'other_spec_drift', 'public_occupied', 'wrong_public_spec'])
def test_clear_requires_exact_slot_pair_and_complete_all_spec_baseline(fault):
    placed, after, rows, shown = placement(), baseline(), requests(value=0, at=20), public(baseline())
    since, until = 20, 21
    if fault == 'missing': rows.pop()
    elif fault == 'duplicate': rows.append(deepcopy(rows[1]))
    elif fault == 'wrong_slot': rows = requests(slot0=4, value=0, at=20)
    elif fault == 'wrong_id': rows = requests(value=1462, at=20)
    elif fault == 'wrong_session': rows[0]['session'] = 'other'
    elif fault == 'late_pair': rows[1]['time'], until = 22, 23
    elif fault == 'before_placement': rows, since, until = requests(value=0, at=10), 10, 11
    elif fault == 'saved_extra': after = sorted(after + [[0, 4, 1515, 0]])
    elif fault == 'other_spec_drift': after[-1][2] = 6603
    elif fault == 'public_occupied': shown['actions'][3].update(kind='spell', id=1462)
    elif fault == 'wrong_public_spec': shown['active_spec'] = 2
    if fault:
        with pytest.raises(RuntimeError): proof.clear_guard(placed, after, rows, 'hunter', since, until, shown)
    else:
        result = proof.clear_guard(placed, after, rows, 'hunter', since, until, shown)
        assert result['modern']['body'] == '0000000003' and result['native']['body'] == '0300000000'
        assert len(result['checks']) == 6 and all(result['checks'].values())


@pytest.mark.parametrize('fault', [None, 'slot', 'source', 'frame', 'button', 'world', 'inside', 'empty_review', 'samepoint', 'bounds'])
def test_review_binds_exact_fresh_button_and_empty_world_destination(monkeypatch, fault):
    placed = placement()
    ref = {'path': '/owned/episode.json', 'sha256': 'digest'}
    stage = {'frame': {'file': 'fresh.png'}, 'public': placed['public']}
    d = {'source': ref, 'frame': stage['frame'], 'slot0': 3, 'spell': 1462, 'public_button': placed['button'],
        'point': [400, 650], 'empty_point': [850, 400], 'empty_point_reviewed': True,
        'pickup_point_inside_button': True, 'empty_point_world_space': True}
    if fault == 'slot': d['slot0'] = 11
    elif fault == 'source': d['source'] = {**ref, 'sha256': 'borrowed'}
    elif fault == 'frame': d['frame'] = {'file': 'old.png'}
    elif fault == 'button': d['public_button'] = {**placed['button'], 'id': 1515}
    elif fault == 'world': d['empty_point_world_space'] = False
    elif fault == 'inside': d['pickup_point_inside_button'] = False
    elif fault == 'empty_review': d['empty_point_reviewed'] = False
    elif fault == 'samepoint': d['empty_point'] = d['point']
    elif fault == 'bounds': d['empty_point'] = [1280, 0]
    monkeypatch.setattr(controller, 'reviewed', lambda t, path, name: d)
    monkeypatch.setattr(controller, 'bound', lambda path: ref)
    t = SimpleNamespace(receipt={'purchase_source': ref})
    if fault:
        with pytest.raises(RuntimeError):
            controller.reviewed_points(t, Path('/review.json'), Path('/owned/episode.json'), stage,
                placed, placed['public'], placed['button'])
    else:
        assert controller.reviewed_points(t, Path('/review.json'), Path('/owned/episode.json'), stage,
            placed, placed['public'], placed['button']) == ([400, 650], [850, 400])


@pytest.mark.parametrize('fault', [None, 'wrong_clear', 'extra_request', 'saved_drift', 'resource_drift', 'geometry', 'invalid_cursor'])
def test_repair_only_sends_one_reviewed_shift_drag_then_cursor_cancel(monkeypatch, fault):
    placed, events, empty = placement(), [], public(baseline())
    before_saved = {'actions': placed['after_actions'], 'spells': [[1462, 1, 0]], 'quests': {'old': []}}
    after_saved = {**deepcopy(before_saved), 'actions': baseline()}
    if fault == 'saved_drift': after_saved['quests']['old'].append(7)
    native_resources = {'money': 8062, 'items': [6948]}
    after_resources = {**native_resources, 'money': 8061} if fault == 'resource_drift' else native_resources
    e = {'after_saved': before_saved, 'after_resources': native_resources}
    stage = {'frame': {'file': 'reviewed.png'}}
    @contextmanager
    def held(name):
        events.append(('modifier', name))
        yield
    t = SimpleNamespace(receipt={'clear_input_sent': False}, persist=lambda: None,
        io=SimpleNamespace(hold_modifier=held, drag=lambda start, end: events.append(('drag', start, end))),
        execute=lambda action: events.append(('click', action)),
        observe=lambda label: ({'cursor_info': ['item', 6948] if fault == 'invalid_cursor' else ['spell', 1462]} if 'cursor_cancel' not in label else
            {'cursor_info': []}, {'file': label + '.png'}))
    monkeypatch.setattr(controller, 'purchase', lambda *args: ({}, 'hunter', e, stage, placed))
    monkeypatch.setattr(controller, 'no_cast_pet', lambda *args: None)
    monkeypatch.setattr(controller, 'current', lambda *args: (before_saved, native_resources, placed['public'],
        placed['button'], {'cursor_info': []}, {'file': 'before.png'}))
    monkeypatch.setattr(controller, 'reviewed_points', lambda *args: ([400, 650], [850, 400]))
    def geometry(*args):
        if fault == 'geometry': raise RuntimeError('reviewed pickup point pixels changed')
        return {'exact_pixels': True}
    monkeypatch.setattr(controller, 'screen_geometry', geometry)
    monkeypatch.setattr(controller, 'stock_sources', lambda: [proof.PICKUP_SOURCE, proof.BINDING_SOURCE])
    monkeypatch.setattr(controller, 'protected', lambda old: {'all': True})
    monkeypatch.setattr(controller, 'detail', lambda *args: deepcopy(empty))
    monkeypatch.setattr(controller, 'bound', lambda path: {'path': str(path), 'sha256': 'test'})
    rows = requests(value=0, at=20.1)
    if fault == 'wrong_clear': rows = requests(slot0=11, value=0, at=20.1)
    elif fault == 'extra_request': rows += requests(slot0=7, value=1515, at=20.1)
    monkeypatch.setattr(controller, 'action_packets', lambda *args: rows)
    monkeypatch.setattr(controller, 'saved', lambda guid: after_saved)
    monkeypatch.setattr(controller, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(controller, 'resources', lambda oracle: after_resources)
    monkeypatch.setattr(controller.lab, 'server_command', lambda command: events.append(('server', command)))
    clock = itertools.count(20)
    monkeypatch.setattr(controller.time, 'time', lambda: float(next(clock)))
    monkeypatch.setattr(controller.time, 'sleep', lambda seconds: None)
    if fault:
        with pytest.raises(RuntimeError): controller.repair(t, Path('/prep'), Path('/purchase'), Path('/review'))
    else:
        controller.repair(t, Path('/prep'), Path('/purchase'), Path('/review'))
        assert t.receipt['phase'] == 'hunter_learn_auto_action_restored'
        assert len(t.receipt['restoration_checks']) == 12 and all(t.receipt['restoration_checks'].values())
    if fault == 'geometry':
        assert events == []
        return
    assert events[:2] == [('modifier', 'shift'), ('drag', [400, 650], [850, 400])]
    assert sum(event[0] == 'drag' for event in events) == 1
    if fault in ('wrong_clear', 'extra_request', 'invalid_cursor'):
        assert not any(event[0] in ('click', 'server') for event in events)
        assert t.receipt['clear_packets'] == rows and t.receipt['clear_finished_at'] >= 21
        assert t.receipt['public_after_clear'] == empty and 'clear_frame' in t.receipt
        assert t.receipt['cursor_cancel_input'] == {'kind': 'click', 'value': [850, 400],
            'button': 3, 'source': {'path': '/review', 'sha256': 'test'}}
    else:
        assert events[2:] == [('click', {'kind': 'click', 'value': [850, 400], 'button': 3}), ('server', 'saveall')]


def test_pure_autobar_import_does_not_load_ui_or_interaction_modules():
    program = ('import sys; import tools.client_compatibility.hunter_learn_autobar; '
        'assert not any(n.startswith(("PIL", "google.protobuf", "tools.client_compatibility.interaction_")) '
        'for n in sys.modules)')
    subprocess.run([sys.executable, '-c', program], check=True)


def paid_episode(failed=True):
    placed = placement()
    before_saved = {'actions': baseline(), 'spells': contract.BASE_SPELLS, 'skills': [], 'quests': {}}
    after_saved = {**deepcopy(before_saved), 'actions': placed['after_actions'],
        'spells': sorted(contract.BASE_SPELLS + [[1462, 1, 0]])}
    packets = [packet('to_native', 'CMSG_TRAINER_BUY_SPELL',
        struct.pack('<QII', contract.TRAINER_GUID, 40, 1462), 10), *learning()]
    old_resources = {'money': 8708, 'items': [6948]}
    new_resources = {**old_resources, 'money': 8062}
    return {'actor': {'guid': 6}, 'runtime': {'client': {'pid': 123}}, 'native_session': 'hunter',
        'fixture_source': {'path': '/prep', 'sha256': 'prep'}, 'started_at': 9, 'finished_at': 12,
        'completed': not failed, 'failure': 'caption did not settle' if failed else None,
        'phase': 'hunter_learn_purchase_started' if failed else 'hunter_learn_transition_complete',
        'purchase_input_sent': True, 'actionbar_restoration_required': True,
        'login_known_spell_ids': [1515, 79682], 'purchase_started_at': 10, 'purchase_finished_at': 11,
        'purchase_packets': packets, 'auto_action_placement': None if failed else placed,
        'baseline': {'saved': before_saved, 'resources': old_resources,
            'snapshot': {'6': {'native': {'activeTalentGroup': 0}}}},
        'after_saved': after_saved, 'after_resources': new_resources,
        'public_actionbar_after': placed['public'], 'purchase_checks': {'native_learning': True}}


@pytest.mark.parametrize('fault', [None, 'not_closed', 'not_paid', 'wrong_charge', 'saved_extra', 'borrowed_packets'])
def test_closed_failed_paid_purchase_is_housekeeping_only(monkeypatch, fault):
    e = paid_episode()
    if fault == 'not_closed': e['finished_at'] = None
    elif fault == 'not_paid': e['purchase_input_sent'] = False
    elif fault == 'wrong_charge': e['after_resources']['money'] -= 1
    elif fault == 'saved_extra': e['after_saved']['quests']['extra'] = [17]
    elif fault == 'borrowed_packets': e['purchase_packets'][2]['session'] = 'other'
    original = deepcopy(e)
    t = SimpleNamespace(fixture={'guid': 6}, receipt={'runtime': e['runtime']}, persist=lambda: None)
    monkeypatch.setattr(controller, 'baseline', lambda *args: ({}, 'hunter'))
    monkeypatch.setattr(controller, 'no_cast_pet', lambda *args: None)
    monkeypatch.setattr(controller, 'private_json', lambda path: e)
    monkeypatch.setattr(controller, 'bound', lambda path: {'path': str(path), 'sha256': 'prep' if str(path) == '/prep' else 'source'})
    if fault:
        with pytest.raises(RuntimeError): controller.purchase(t, Path('/prep'), Path('/purchase'))
    else:
        _, _, reconstructed, _, placed = controller.purchase(t, Path('/prep'), Path('/purchase'))
        assert reconstructed is e and placed['slot0'] == 3
        assert t.receipt['recovery_only'] is True and t.receipt['failed_whole_excluded'] is True
        assert t.receipt['qualification_added'] is False
    assert e == original


def test_lost_after_observation_reconstructs_only_journal_and_fresh_read_only_values(monkeypatch):
    complete = paid_episode()
    e = deepcopy(complete)
    for key in ('after_saved', 'after_resources', 'public_actionbar_after', 'purchase_finished_at'):
        e.pop(key)
    e['purchase_packets'] = []
    original = deepcopy(e)
    monkeypatch.setattr(controller, 'purchase_packets', lambda *args: complete['purchase_packets'])
    monkeypatch.setattr(controller, 'saved', lambda guid: complete['after_saved'])
    monkeypatch.setattr(controller, 'resources', lambda oracle: complete['after_resources'])
    monkeypatch.setattr(controller, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(controller, 'detail', lambda *args: complete['public_actionbar_after'])
    monkeypatch.setattr(controller, 'no_cast_pet', lambda *args: None)
    monkeypatch.setattr(controller.time, 'time', lambda: 15)
    reconstructed, observed = controller.observed_failed_purchase(e, 'hunter',
        t=SimpleNamespace(receipt={}, persist=lambda: None))
    assert reconstructed['after_saved'] == complete['after_saved']
    assert observed['purchase_packets'] == complete['purchase_packets']
    assert reconstructed['completed'] is False and reconstructed['failure'] == original['failure']
    assert e == original
    observed['purchase_packets'] = observed['purchase_packets'][1:]
    with pytest.raises(RuntimeError, match='immutable owned journal'):
        controller.observed_failed_purchase(e, 'hunter', observed)


@pytest.mark.parametrize('fault', [None, 'changed_pixels', 'changed_panels'])
def test_geometry_checks_actual_both_point_regions_before_input(monkeypatch, tmp_path, fault):
    class Image:
        size = (1280, 720)
        def __init__(self, path): self.fresh = Path(path).name == 'fresh.png'
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def convert(self, mode): return self
        def crop(self, box):
            value = b'drift' if fault == 'changed_pixels' and self.fresh and box[0] == 842 else b'stable'
            return SimpleNamespace(tobytes=lambda: value)
    monkeypatch.setitem(sys.modules, 'PIL', SimpleNamespace(Image=SimpleNamespace(open=Image)))
    t = SimpleNamespace(out=tmp_path)
    stage = {'frame': {'file': 'old.png'}, 'state': {'panels': [], 'bags': []}}
    state = {'panels': ['SpellBookFrame'] if fault == 'changed_panels' else [], 'bags': []}
    if fault:
        with pytest.raises(RuntimeError):
            controller.screen_geometry(t, tmp_path / 'review.json', stage, state, {'file': 'fresh.png'}, [400, 650], [850, 400])
    else:
        actual = controller.screen_geometry(t, tmp_path / 'review.json', stage, state, {'file': 'fresh.png'}, [400, 650], [850, 400])
        assert actual['regions'] == [[384, 634, 416, 666], [842, 392, 858, 408]]
        assert actual['exact_pixels'] is True


@pytest.mark.parametrize('fault', [None, 'cursor_empty', 'pending_sql', 'recorded_packets_only', 'wrong_pair',
    'other_cursor', 'saved_drift', 'geometry', 'no_recorded_clear', 'missing_cursor_proof', 'clear_state_cursor',
    'early_observe_fail_empty', 'early_observe_fail_cursor', 'source_pair_after_failure', 'missing_cancel_intent'])
def test_failed_clear_settle_saves_then_only_cancels_same_cursor_without_drag(monkeypatch, tmp_path, fault):
    placed, events = placement(), []
    e = paid_episode(False)
    expected = {**e['after_saved'], 'actions': baseline()}
    actor, runtime = e['actor'], e['runtime']
    packet_rows = requests(value=0, at=20)
    recorded = {'modern': packet_rows[0], 'native': packet_rows[1], 'button': public(baseline())['actions'][3]}
    original_ref = {'path': '/purchase', 'sha256': 'test'}
    evidence = tmp_path / 'evidence'
    evidence.mkdir()
    image = evidence / 'clear.png'
    image.write_bytes(b'authenticated retained frame')
    failed = {'actor': actor, 'runtime': runtime, 'native_session': 'hunter', 'completed': False,
        'failure': 'cursor cancellation timeout', 'qualification_added': False,
        'fixture_source': {'path': '/prep', 'sha256': 'test'}, 'started_at': 19, 'finished_at': 22,
        'source': original_ref, 'purchase_source': original_ref, 'auto_action_placement': placed,
        'before_saved': e['after_saved'], 'before_resources': e['after_resources'], 'clear_input_sent': True,
        'clear_started_at': 20, 'clear_finished_at': 21, 'clear_packets': packet_rows, 'clear_request_proof': recorded,
        'cursor_before_cancel': ['spell', 1462], 'cursor_before_clear': [],
        'cursor_cancel_input': {'kind': 'click', 'button': 3, 'value': [850, 400]},
        'bar_restore_input': {'kind': 'shift_drag'}, 'screen_review': {'sha256': 'review'},
        'clear_state': {'panels': [], 'bags': []},
        'clear_frame': {'file': 'clear.png', 'sha256': controller.lab.sha256(image)}}
    if fault == 'recorded_packets_only': failed.pop('clear_request_proof')
    elif fault == 'no_recorded_clear': failed.pop('clear_request_proof'); failed.pop('clear_packets')
    elif fault == 'missing_cursor_proof': failed.pop('cursor_before_cancel')
    elif fault == 'missing_cancel_intent': failed.pop('cursor_cancel_input')
    elif fault == 'clear_state_cursor':
        failed['clear_state']['cursor_info'] = failed.pop('cursor_before_cancel')
    elif fault in ('early_observe_fail_empty', 'early_observe_fail_cursor'):
        for key in ('clear_request_proof', 'clear_packets', 'clear_finished_at', 'clear_frame', 'clear_state', 'cursor_before_cancel'):
            failed.pop(key)
    elif fault == 'source_pair_after_failure':
        for key in ('clear_request_proof', 'clear_packets', 'clear_finished_at'):
            failed.pop(key)
        packet_rows = requests(value=0, at=23)
    elif fault == 'wrong_pair': packet_rows = requests(slot0=11, value=0, at=20)
    before = e['after_saved'] if fault == 'pending_sql' else expected
    if fault == 'saved_drift': before = {**before, 'quests': {'unexpected': [9]}}
    reads = iter([before, expected, expected])
    cursor = [] if fault in ('cursor_empty', 'early_observe_fail_empty') else ['spell', 1515] if fault == 'other_cursor' else ['spell', 1462]
    states = iter([{'cursor_info': cursor}, {'cursor_info': []}])
    t = SimpleNamespace(fixture=actor, receipt={'runtime': runtime}, out=evidence,
        persist=lambda: None, observe=lambda label: (next(states), {'file': 'fresh.png'}),
        execute=lambda action: events.append(('click', action)))
    def source(*args):
        t.receipt.update(purchase_source=original_ref, source=original_ref, fixture_source=failed['fixture_source'])
        return {}, 'hunter', e, e, placed
    monkeypatch.setattr(controller, 'purchase', source)
    monkeypatch.setattr(controller, 'no_cast_pet', lambda *args: None)
    monkeypatch.setattr(controller, 'private_json', lambda path: failed)
    monkeypatch.setattr(controller, 'bound', lambda path: {'path': str(path), 'sha256': 'test'})
    monkeypatch.setattr(controller.lab, 'ROOT', tmp_path)
    monkeypatch.setattr(controller, 'saved', lambda guid: next(reads))
    monkeypatch.setattr(controller, 'resources', lambda oracle: e['after_resources'])
    monkeypatch.setattr(controller, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(controller, 'detail', lambda *args: public(baseline()))
    intervals = []
    def action_packets(session, since, until):
        intervals.append((session, since, until))
        return [p for p in packet_rows if since <= p['time'] <= until]
    monkeypatch.setattr(controller, 'action_packets', action_packets)
    monkeypatch.setattr(controller, 'protected', lambda old: {'all': True})
    monkeypatch.setattr(controller, 'stock_sources', lambda: [proof.PICKUP_SOURCE, proof.BINDING_SOURCE])
    def geometry(*args):
        if fault == 'geometry': raise RuntimeError('current cancel point geometry differs')
        return {'exact_pixels': True}
    monkeypatch.setattr(controller, 'screen_geometry', geometry)
    monkeypatch.setattr(controller.lab, 'server_command', lambda command: events.append(('server', command)))
    monkeypatch.setattr(controller.time, 'time', lambda: 30)
    monkeypatch.setattr(controller.time, 'sleep', lambda seconds: None)
    rejecting = fault in ('wrong_pair', 'other_cursor', 'saved_drift', 'geometry', 'missing_cursor_proof',
        'early_observe_fail_cursor', 'source_pair_after_failure', 'missing_cancel_intent')
    if rejecting:
        with pytest.raises(RuntimeError): controller.settle(t, Path('/prep'), evidence / 'episode.json')
        assert not any(event[0] == 'click' for event in events)
    else:
        controller.settle(t, Path('/prep'), evidence / 'episode.json')
        assert events[0] == ('server', 'saveall')
        assert sum(event[0] == 'click' for event in events) == (0 if fault in ('cursor_empty', 'early_observe_fail_empty') else 1)
        assert t.receipt['clear_input_sent'] is False and t.receipt['settlement_only'] is True
        assert t.receipt['phase'] == 'hunter_learn_auto_action_restored'
        assert all(t.receipt['restoration_checks'].values())
        assert ('hunter', 20, 22) in intervals  # Failed receipt bounds the original source pair.


@pytest.mark.parametrize('fault', [None, 'wrong_charge', 'extra_action', 'sql_drift', 'save_failed', 'cast'])
def test_lost_outcome_native_authority_gates_one_saveall_before_sql_paid_capture(monkeypatch, fault):
    complete = paid_episode()
    e = deepcopy(complete)
    for key in ('after_saved', 'after_resources', 'public_actionbar_after', 'purchase_finished_at'):
        e.pop(key)
    e['purchase_packets'] = []
    original = deepcopy(e)
    rows = deepcopy(complete['purchase_packets'])
    if fault == 'extra_action': rows += requests(slot0=7, value=1515)
    native_resources = deepcopy(complete['after_resources'])
    if fault == 'wrong_charge': native_resources['money'] -= 1
    first_sql = deepcopy(e['baseline']['saved'])
    if fault == 'sql_drift': first_sql['quests']['unexpected'] = [8]
    last_sql = first_sql if fault == 'save_failed' else complete['after_saved']
    reads = iter([first_sql, last_sql])
    events = []
    t = SimpleNamespace(receipt={}, persist=lambda: events.append(('persist', deepcopy(t.receipt))))
    monkeypatch.setattr(controller, 'purchase_packets', lambda *args: rows)
    monkeypatch.setattr(controller, 'saved', lambda guid: next(reads))
    monkeypatch.setattr(controller, 'resources', lambda oracle: native_resources)
    monkeypatch.setattr(controller, 'Inventory', lambda *args: SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(controller, 'detail', lambda *args: complete['public_actionbar_after'])
    def cast_guard(*args):
        if fault == 'cast': raise RuntimeError('owned cast input')
    monkeypatch.setattr(controller, 'no_cast_pet', cast_guard)
    def save(command):
        assert t.receipt.get('recovery_native_authority') and t.receipt['recovery_only'] is True
        assert t.receipt['failed_whole_excluded'] is True and t.receipt['qualification_added'] is False
        events.append(('server', command))
    monkeypatch.setattr(controller.lab, 'server_command', save)
    monkeypatch.setattr(controller.time, 'time', lambda: 15)
    monkeypatch.setattr(controller.time, 'sleep', lambda seconds: None)
    if fault:
        with pytest.raises(RuntimeError): controller.observed_failed_purchase(e, 'hunter', t=t)
    else:
        reconstructed, observed = controller.observed_failed_purchase(e, 'hunter', t=t)
        assert reconstructed['after_saved'] == complete['after_saved']
        assert observed['after_resources'] == complete['after_resources']
    assert sum(event[0] == 'server' for event in events) == (1 if fault in (None, 'save_failed') else 0)
    assert e == original


@pytest.mark.parametrize('fault', [None, 'native_cast', 'modern_pet', 'foreign', 'before_entry', 'entry_hash'])
def test_paid_cleanup_rejects_cast_and_pet_action_over_whole_owned_entry(monkeypatch, fault):
    e = paid_episode()
    e['entry_source'] = {'path': '/entry', 'sha256': 'entry'}
    entry = {'actor': e['actor'], 'runtime': e['runtime'], 'native_session': 'hunter', 'started_at': 5}
    rows = []
    if fault in ('native_cast', 'modern_pet', 'foreign', 'before_entry'):
        rows = [packet('from_client' if fault == 'modern_pet' else 'to_native',
            'CMSG_PET_ACTION' if fault == 'modern_pet' else 'CMSG_CAST_SPELL', b'cast', 6)]
        if fault == 'foreign': rows[0]['session'] = 'another'
        elif fault == 'before_entry': rows[0]['time'] = 4
    monkeypatch.setattr(controller, 'private_json', lambda path: entry)
    monkeypatch.setattr(controller, 'bound', lambda path: {'path': '/entry', 'sha256': 'changed' if fault == 'entry_hash' else 'entry'})
    monkeypatch.setattr(controller, 'entries', lambda path: iter(rows))
    if fault in ('native_cast', 'modern_pet', 'entry_hash'):
        with pytest.raises(RuntimeError): controller.no_cast_pet(e, 'hunter', 15)
    else:
        controller.no_cast_pet(e, 'hunter', 15)


@pytest.mark.parametrize('interrupt', [KeyboardInterrupt, SystemExit])
def test_main_closes_failed_receipt_before_reraising_interrupt(monkeypatch, tmp_path, interrupt):
    receipts = []
    trial = SimpleNamespace(receipt={'completed': False, 'failure': None},
        persist=lambda: receipts.append(deepcopy(trial.receipt)))
    @contextmanager
    def actor(name): yield
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_owned_class_fixture',
        SimpleNamespace(SCRIPT_BOUNDARY={}))
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_social', SimpleNamespace(actor=actor))
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_trial', SimpleNamespace(Trial=lambda *a, **k: trial))
    monkeypatch.setattr(sys, 'argv', ['autobar', 'repair', '--preparation', '/prep', '--source', '/source', '--output', str(tmp_path / 'out')])
    def repair(*args):
        trial.receipt['clear_input_sent'] = True
        raise interrupt('interrupted after clear')
    monkeypatch.setattr(controller, 'repair', repair)
    monkeypatch.setattr(controller.time, 'time', lambda: 30)
    with pytest.raises(interrupt): controller.main()
    assert receipts[-1]['completed'] is False and receipts[-1]['failure'].startswith(interrupt.__name__ + ':')
    assert receipts[-1]['finished_at'] == 30 and receipts[-1]['clear_input_sent'] is True

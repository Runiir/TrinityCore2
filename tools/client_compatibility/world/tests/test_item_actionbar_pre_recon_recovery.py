"""Source-bound cleanup tests; every database, journal and UI read is mocked."""
from copy import deepcopy
import importlib
from itertools import count
import json
from pathlib import Path
import sys

import pytest

from tools.client_compatibility import interaction_item_actionbar_pre_recon_recovery as recovery
from tools.client_compatibility import item_actionbar_contract as contract
from tools.client_compatibility.world.tests.test_item_actionbar_operation import baseline, native, state

SCOUT = {'schema': 'client442_actor_v1', 'actor': 'scout', 'guid': 2, 'account_id': 2,
    'character_name': 'Harnesstwo', 'race': 1, 'class': 1, 'level': 1}
RUNTIME = {key: {'pid': index, 'start_ticks': str(100 + index)}
    for index, key in enumerate(('worldserver', 'modern_world', 'client'), 1)}


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2) + '\n')
    return path


class Trial:
    def __init__(self, out, base):
        self.out, self.base, self.fixture = out, base, deepcopy(SCOUT)
        self.receipt = {'started_at': 20, 'actor': self.fixture, 'runtime': deepcopy(RUNTIME),
            'completed': False, 'failure': None, 'code_commit': 'b' * 40, 'cases': [], 'cleanup': [],
            'controller': 'code_diagnostic_ordinary_inputs', 'model': None, 'qualification_added': False}
        self.events, self.persisted = [], []
        self.bags, self.cursor, self.fail_at = [0], {}, None
        self.holders = None

    def persist(self):
        self.persisted.append(deepcopy(self.receipt))

    def observe(self, label):
        if label == self.fail_at:
            raise KeyboardInterrupt('retained interruption')
        value = deepcopy(self.base['state'])
        value.update(bags=deepcopy(self.bags), cursor_info=deepcopy(self.cursor))
        return value, {'file': label + '.png', 'sha256': 'f' * 64,
            'movement': {'speed': 0, 'dead': False, 'in_combat': False, 'on_taxi': False}}

    def execute(self, action):
        assert self.persisted[-1]['first_failure_source']
        self.events.append(('input', deepcopy(action)))
        if action == {'kind': 'key', 'value': 'Escape'}:
            assert self.persisted[-1]['bag_close_input_sent'] is True
            self.bags = {}
        elif action == {'kind': 'key', 'value': 'X', 'hold': .4}:
            assert self.receipt['stand_attempt_source']
            self.holders['native']['pose']['stand'] = 0
            self.holders['rows'].extend(stand_rows(0, self.receipt['stand_cleanup_started_at']))
        else:
            assert action == {'kind': 'chat', 'value': '/afk'} and self.receipt['afk_attempt_source']
            self.holders['native']['afk'] = False

    def clean_panels(self):
        assert not self.bags and not self.cursor
        self.events.append(('already_clean',))


def fixture(tmp_path, monkeypatch):
    op = recovery.op
    root = tmp_path / 'private'
    prep = root / 'evidence/ready/episode.json'
    entry = root / 'evidence/entry/episode.json'
    failed_path = root / 'evidence/recon/episode.json'
    review_path = root / 'evidence/entry/review.json'
    base = baseline()
    base['state'].update(bags={}, panels={}, cursor_info={})
    write(prep, {'phase': 'item_actionbar_scout_ready', 'code_commit': 'a' * 40})
    entered = {'phase': 'item_actionbar_entered', 'completed': True, 'failure': None,
        'started_at': 1, 'finished_at': 5, 'actor': SCOUT, 'runtime': RUNTIME,
        'code_commit': 'a' * 40, 'native_session': 'owned',
        'saved': base['saved'], 'resources': base['resources'], 'active_spec': base['active_spec'],
        'native_original': base['native_original'], 'precision_source': base['precision_source'],
        'public': base['public'], 'state': base['state'], 'frame': {'file': 'entry.png', 'sha256': 'e' * 64}}
    write(entry, entered)
    base['entry_source'] = op.bound(entry)
    review = {'reviewed': True, 'control': 'MainMenuBarBackpackButton', 'source': op.bound(entry),
        'frame': entered['frame'], 'fixture_source_sha256': op.bound(prep)['sha256'],
        'point': [1109, 700], 'pickup_point_inside_button': True}
    write(review_path, review)
    raw_state = deepcopy(base['state']); raw_state['bags'] = [0]
    failed = {'schema': 'client442_laya_interactions_v1', 'completed': False,
        'failure': 'RuntimeError: actionbars diagnostic did not become visible', 'phase': None,
        'started_at': 10, 'finished_at': 15, 'actor': SCOUT, 'runtime': RUNTIME,
        'code_commit': 'a' * 40, 'native_session': 'owned', 'controller': 'code_diagnostic_ordinary_inputs',
        'model': None, 'qualification_added': False, 'mutation_sent': False, 'input_sent': True,
        'preparation_source': op.bound(prep), 'fixture_source': op.bound(prep),
        'entry_source': op.bound(entry), 'baseline': base, 'cases': [], 'cleanup': [],
        'backpack_open_review': op.bound(review_path), 'backpack_open_input': {'kind': 'click', 'value': [1109, 700]},
        'backpack_geometry': {'exact_pixels': True}, 'raw_stage_failure': {'state': raw_state,
            'saved': base['saved'], 'resources': base['resources'], 'native_state': base['native_state'],
            'input_replayed': False, 'errors': {'public': 'RuntimeError: actionbars diagnostic did not become visible'}}}
    write(failed_path, failed)
    old = {'all_offline_snapshot': base['snapshot']}
    t = Trial(root / 'evidence/recovery', base)
    holders = {'saved': deepcopy(base['saved']), 'resources': deepcopy(base['resources']),
        'native': native(), 'snapshot': deepcopy(base['snapshot']), 'rows': [], 'public': deepcopy(base['public'])}
    holders['snapshot']['2']['native']['online'] = 1
    t.holders = holders
    def context(t, path):
        assert path == prep
        t.receipt.update(preparation_source=op.bound(prep), fixture_source=op.bound(prep), native_session='owned')
        return old, 'owned'
    def entry_source(t, p, path, old, session):
        assert path == entry and p == prep and session == 'owned'
        t.receipt.update(entry_source=op.bound(entry), precision_source=entered['precision_source'])
        return deepcopy(entered)
    def detail(t, label):
        assert not t.bags, 'the open backpack must never wait for a passive action-bar page'
        t.events.append(('detail', label))
        return deepcopy(holders['public'])
    monkeypatch.setattr(recovery.sources, 'ROOT', root)
    monkeypatch.setattr(op.lab, 'ROOT', root)
    monkeypatch.setattr(op, 'context', context)
    monkeypatch.setattr(op, 'entry_source', entry_source)
    monkeypatch.setattr(op, 'saved', lambda: deepcopy(holders['saved']))
    monkeypatch.setattr(op, 'resources', lambda session: deepcopy(holders['resources']))
    monkeypatch.setattr(op, 'native_state', lambda session: deepcopy(holders['native']))
    monkeypatch.setattr(op, 'snapshot', lambda: deepcopy(holders['snapshot']))
    monkeypatch.setattr(op, 'packet_rows', lambda session, since, until:
        deepcopy([row for row in holders['rows'] if since <= row['time'] <= until]))
    monkeypatch.setattr(op, 'no_forbidden', lambda base, session, until, t=None:
        contract.forbidden_packets(holders['rows'], session, entered['started_at'], until))
    monkeypatch.setattr(op, 'detail', detail)
    monkeypatch.setattr(op, 'binding_key', lambda value: value)
    monkeypatch.setattr(op, 'server_save', lambda: pytest.fail('pre-recon recovery cannot SaveAll'))
    monkeypatch.setattr(recovery.time, 'time', lambda: 22)
    monkeypatch.setattr(recovery.time, 'sleep', lambda _: None)
    return t, prep, entry, failed_path, failed, holders


def test_one_escape_precedes_all_passive_bar_reads_and_emits_excluded_park_authority(tmp_path, monkeypatch):
    t, prep, entry, failed_path, failed, _ = fixture(tmp_path, monkeypatch)
    original = {path: path.read_bytes() for path in (prep, entry, failed_path)}
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is True and t.receipt['failure'] is None
    assert t.events[0] == ('input', {'kind': 'key', 'value': 'Escape'})
    assert len([event for event in t.events if event[0] == 'input']) == 1
    assert t.receipt['phase'] == 'item_actionbar_restored'
    assert set(t.receipt['layout_restoration_checks']) == recovery.LAYOUT_CHECKS
    assert all(t.receipt['layout_restoration_checks'].values())
    assert t.receipt['source'] == t.receipt['first_failure_source'] == recovery.op.bound(failed_path)
    assert t.receipt['preparation_source'] == recovery.op.bound(prep)
    assert t.receipt['entry_source'] == recovery.op.bound(entry)
    assert t.receipt['baseline'] == failed['baseline']
    assert t.receipt['after_saved'] == failed['baseline']['saved']
    assert t.receipt['after_resources'] == failed['baseline']['resources']
    assert t.receipt['after_native_state'] == failed['baseline']['native_state']
    assert t.receipt['recovery_only'] is True and t.receipt['failed_whole_excluded'] is True
    assert t.receipt['drag_input_sent'] is False and t.receipt['clear_input_sent'] is False
    assert t.receipt['gameplay_input_replayed'] is False and t.receipt['placement_absent'] is True
    assert t.receipt['actionbar_restored'] is True and t.receipt['code_commit'] == 'b' * 40
    assert {path: path.read_bytes() for path in original} == original
    assert not (entry.parent / 'item_actionbar_drag_attempt.json').exists()
    assert not (entry.parent / 'item_actionbar_clear_attempt.json').exists()
    assert t.receipt['escape_attempt_source']


@pytest.mark.parametrize('kind', ['drag', 'clear'])
@pytest.mark.parametrize('shape', ['partial', 'malformed', 'symlink'])
def test_every_consumed_marker_refuses_cleanup_input(tmp_path, monkeypatch, kind, shape):
    t, prep, entry, failed_path, _, _ = fixture(tmp_path, monkeypatch)
    marker = entry.parent / ('item_actionbar_' + kind + '_attempt.json')
    if shape == 'symlink': marker.symlink_to(entry.parent / 'missing.json')
    else: marker.write_text('' if shape == 'partial' else 'malformed')
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and not t.events
    assert marker.exists() or marker.is_symlink()


@pytest.mark.parametrize('name', ['CMSG_SET_ACTION_BUTTON', 'CMSG_USE_ITEM', 'CMSG_CAST_SPELL',
    'CMSG_SWAP_INV_ITEM', 'CMSG_DESTROY_ITEM', 'CMSG_PET_ACTION'])
@pytest.mark.parametrize('direction', ['from_client', 'to_native'])
def test_actual_mutation_names_refuse_escape_before_input(tmp_path, monkeypatch, name, direction):
    t, prep, _, failed_path, _, holders = fixture(tmp_path, monkeypatch)
    holders['rows'] = [{'time': 12, 'session': 'owned', 'name': name, 'direction': direction, 'body': ''}]
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and not t.events


@pytest.mark.parametrize('fault', ['actor', 'runtime', 'model', 'phase', 'failure', 'snapshot',
    'entry_sha', 'raw_saved', 'raw_resources', 'raw_native', 'review_sha', 'click', 'drag_flag', 'placement'])
def test_failed_source_drift_cannot_authorize_cleanup(tmp_path, monkeypatch, fault):
    t, prep, _, failed_path, failed, _ = fixture(tmp_path, monkeypatch)
    if fault == 'actor': failed['actor'] = {'guid': 6}
    elif fault == 'runtime': failed['runtime'] = {'client': {'pid': 99}}
    elif fault == 'model': failed['model'] = 'learned'
    elif fault == 'phase': failed['phase'] = 'item_actionbar_drag_started'
    elif fault == 'failure': failed['failure'] = 'some other failure'
    elif fault == 'snapshot': failed['baseline']['snapshot']['6']['inventory'] = []
    elif fault == 'entry_sha': failed['entry_source']['sha256'] = '0' * 64
    elif fault == 'raw_saved': failed['raw_stage_failure']['saved'] = {}
    elif fault == 'raw_resources': failed['raw_stage_failure']['resources'] = {}
    elif fault == 'raw_native': failed['raw_stage_failure']['native_state'] = {}
    elif fault == 'review_sha': failed['backpack_open_review']['sha256'] = '0' * 64
    elif fault == 'click': failed['backpack_open_input']['button'] = 3
    elif fault == 'drag_flag': failed['drag_input_sent'] = True
    else: failed['placement'] = {}
    write(failed_path, failed)
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and not t.events


@pytest.mark.parametrize('fault', ['saved', 'resources', 'health', 'peer', 'cursor', 'other_bag'])
def test_current_drift_refuses_escape_before_input(tmp_path, monkeypatch, fault):
    t, prep, _, failed_path, _, holders = fixture(tmp_path, monkeypatch)
    if fault in ('saved', 'resources'): holders[fault] = {}
    elif fault == 'health': holders['native']['health'] = 59
    elif fault == 'peer': holders['snapshot']['6']['inventory'] = []
    elif fault == 'cursor': t.cursor = ['item', 6948]
    else: t.bags = [1]
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and not t.events


def test_already_closed_backpack_performs_no_input(tmp_path, monkeypatch):
    t, prep, _, failed_path, _, _ = fixture(tmp_path, monkeypatch)
    t.bags = {}
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is True and t.receipt['bag_close_input_sent'] is False
    assert not any(event[0] == 'input' for event in t.events)


def test_post_escape_interruption_keeps_first_failure_and_never_replays_input(tmp_path, monkeypatch):
    t, prep, _, failed_path, _, _ = fixture(tmp_path, monkeypatch)
    t.fail_at = 'item_pre_recon_bag_close_wait'
    with pytest.raises(KeyboardInterrupt): recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and t.receipt['finished_at'] == 22
    assert t.receipt['first_failure_source'] == recovery.op.bound(failed_path)
    assert t.receipt['first_failure'] == 'RuntimeError: actionbars diagnostic did not become visible'
    assert t.receipt['failure'] == 'KeyboardInterrupt: retained interruption'
    assert t.receipt['raw_pre_recon_recovery_failure']['state']['bags'] == {}
    assert len([event for event in t.events if event[0] == 'input']) == 1
    t.fail_at = None
    recovery.run(t, prep, failed_path)
    assert len([event for event in t.events if event[0] == 'input']) == 1


def stand_rows(wanted, at):
    return [{'session': 'owned', 'time': at + index * .01, 'name': name, 'direction': direction, 'body': raw.hex()}
        for index, (name, direction, raw) in enumerate([
            ('CMSG_STAND_STATE_CHANGE', 'from_client', bytes([wanted])),
            ('CMSG_STANDSTATECHANGE', 'to_native', wanted.to_bytes(4, 'little')),
            ('SMSG_STAND_STATE_UPDATE', 'from_native', bytes([wanted])),
            ('SMSG_STAND_STATE_UPDATE', 'to_client', bytes([wanted]) + b'\0' * 4)])]


def observed_idle_rows():
    return stand_rows(1, 18) + [{'session': 'owned', 'time': 18.04, 'direction': 'from_native',
        'name': 'SMSG_UPDATE_OBJECT',
        'body': '0000010000000001020500000000000000201022000000000000000010003100000001000000000000000000000002000000'}]


def test_observed_seated_afk_mismatch_binds_packets_before_bounded_stand_and_afk_restore(tmp_path, monkeypatch):
    t, prep, _, failed_path, _, holders = fixture(tmp_path, monkeypatch)
    holders['native'].update(pose={'stand': 1, 'sheath': 0}, afk=True)
    holders['rows'] = observed_idle_rows()
    ticks = count(23, .1)
    monkeypatch.setattr(recovery.time, 'time', lambda: next(ticks))
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is True, t.receipt['failure']
    inputs = [event[1] for event in t.events if event[0] == 'input']
    assert inputs == [{'kind': 'key', 'value': 'Escape'}, {'kind': 'key', 'value': 'X', 'hold': .4},
        {'kind': 'chat', 'value': '/afk'}]
    fact = t.receipt['pre_recon_idle_observation']
    assert fact['label'] == 'unattributed_observed_post_failure_idle_state_mismatch'
    assert fact['observed_stand_packets'] == observed_idle_rows()[:4]
    assert fact['observed_owner_flags_packet'] == observed_idle_rows()[4]
    assert t.receipt['stand_cleanup_packets'] == stand_rows(0, t.receipt['stand_cleanup_started_at'])
    assert t.receipt['after_native_state'] == t.base['native_state']


@pytest.mark.parametrize('fault', ['afk_only', 'sit_only', 'target', 'sheath', 'pose',
    'missing_quartet', 'duplicate_quartet', 'wrong_body', 'missing_owner', 'duplicate_owner', 'before_failure'])
def test_unattributed_idle_exception_has_exact_native_and_packet_allowlist(tmp_path, monkeypatch, fault):
    t, prep, _, failed_path, _, holders = fixture(tmp_path, monkeypatch)
    holders['native'].update(pose={'stand': 1, 'sheath': 0}, afk=True)
    holders['rows'] = observed_idle_rows()
    if fault == 'afk_only': holders['native']['pose']['stand'] = 0
    elif fault == 'sit_only': holders['native']['afk'] = False
    elif fault == 'target': holders['native']['selection'] = 40
    elif fault == 'sheath': holders['native']['pose']['sheath'] = 1
    elif fault == 'pose': holders['native']['pose']['stand'] = 2
    elif fault == 'missing_quartet': holders['rows'].pop(0)
    elif fault == 'duplicate_quartet': holders['rows'].extend(stand_rows(1, 19))
    elif fault == 'wrong_body': holders['rows'][0]['body'] = '00'
    elif fault == 'missing_owner': holders['rows'].pop()
    elif fault == 'duplicate_owner': holders['rows'].append(deepcopy(holders['rows'][-1]))
    else:
        for row in holders['rows']: row['time'] -= 10
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and not t.events


def test_interrupted_escape_cannot_be_repeated_from_a_new_output(tmp_path, monkeypatch):
    t, prep, _, failed_path, _, _ = fixture(tmp_path, monkeypatch)
    def failed_input(action):
        t.events.append(('input', deepcopy(action)))
        raise KeyboardInterrupt('after sent Escape')
    t.execute = failed_input
    with pytest.raises(KeyboardInterrupt): recovery.run(t, prep, failed_path)
    second = Trial(t.out.with_name('another_output'), t.base)
    recovery.run(second, prep, failed_path)
    assert second.receipt['completed'] is False and not second.events
    assert 'already consumed' in second.receipt['failure']


@pytest.mark.parametrize('kind', ['stand', 'afk'])
def test_interrupted_idle_toggle_is_consumed_across_output_invocations(tmp_path, monkeypatch, kind):
    t, prep, _, failed_path, _, holders = fixture(tmp_path, monkeypatch)
    holders['native'].update(pose={'stand': 1, 'sheath': 0}, afk=True)
    holders['rows'] = observed_idle_rows()
    ticks = count(23, .1)
    monkeypatch.setattr(recovery.time, 'time', lambda: next(ticks))
    original_execute = t.execute
    def interrupted(action):
        if (kind == 'stand' and action.get('value') == 'X') or (kind == 'afk' and action.get('value') == '/afk'):
            t.events.append(('input', deepcopy(action)))
            raise KeyboardInterrupt('sent toggle with unknown outcome')
        original_execute(action)
    t.execute = interrupted
    with pytest.raises(KeyboardInterrupt): recovery.run(t, prep, failed_path)
    assert t.receipt[kind + '_attempt_source']
    second = Trial(t.out.with_name('another_output'), t.base)
    second.bags, second.holders = {}, holders
    recovery.run(second, prep, failed_path)
    assert second.receipt['completed'] is False
    assert not any(event[0] == 'input' for event in second.events)


@pytest.mark.parametrize('fault', ['saved', 'resources', 'peer', 'health', 'public_page', 'first_source_bytes'])
def test_after_escape_drift_retains_failure_without_another_cleanup_input(tmp_path, monkeypatch, fault):
    t, prep, _, failed_path, failed, holders = fixture(tmp_path, monkeypatch)
    original_execute = t.execute
    def execute(action):
        original_execute(action)
        if fault in ('saved', 'resources'): holders[fault] = {}
        elif fault == 'peer': holders['snapshot']['6']['inventory'] = []
        elif fault == 'health': holders['native']['health'] = 59
        elif fault == 'public_page': holders['public']['page'] = 2
        else: write(failed_path, {**failed, 'changed': True})
    t.execute = execute
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False and t.receipt['raw_pre_recon_recovery_failure']
    assert len([event for event in t.events if event[0] == 'input']) == 1
    assert t.receipt['recovery_only'] is True and t.receipt['failed_whole_excluded'] is True


def test_nonsettling_escape_is_not_repeated(tmp_path, monkeypatch):
    t, prep, _, failed_path, _, _ = fixture(tmp_path, monkeypatch)
    def no_change(action): t.events.append(('input', deepcopy(action)))
    t.execute = no_change
    ticks = iter([0, 17])
    monkeypatch.setattr(recovery.time, 'monotonic', lambda: next(ticks))
    recovery.run(t, prep, failed_path)
    assert t.receipt['completed'] is False
    assert 'refusing Escape replay' in t.receipt['failure']
    assert len([event for event in t.events if event[0] == 'input']) == 1
    assert not any(event[0] == 'detail' for event in t.events)


def test_import_does_not_load_ui_auth_or_sql_runtime():
    before = set(sys.modules)
    importlib.reload(recovery)
    assert not any(name.startswith(('PIL', 'google.protobuf', 'tools.client_compatibility.auth',
        'tools.client_compatibility.interaction_trial')) for name in set(sys.modules) - before)

"""A distinct idle renewal consumes only its new source-bound cleanup authority."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from tools.client_compatibility import interaction_item_actionbar_idle_renewal as renewal
from tools.client_compatibility.world.tests.test_item_actionbar_observer_reload import scene as reload_scene

SIT_BODY = '0000010000000001020300000000000000201022000031000000010000000000000000000000'
AFK_BODY = '00000100000000010205000000000000002000220000000000000000100031000000000000000000000002000000'


def sparse_idle(at=10):
    quartet = [{'session': 'owned', 'time': at + .1 + n * .01, 'name': name, 'direction': direction, 'body': raw}
        for n, (name, direction, raw) in enumerate((('CMSG_STAND_STATE_CHANGE', 'from_client', '01'),
            ('CMSG_STANDSTATECHANGE', 'to_native', '01000000'), ('SMSG_STAND_STATE_UPDATE', 'from_native', '01'),
            ('SMSG_STAND_STATE_UPDATE', 'to_client', '0100000000')))]
    return quartet + [{'session': 'owned', 'time': at + .14 + n * .01, 'name': 'SMSG_UPDATE_OBJECT',
        'direction': 'from_native', 'body': raw} for n, raw in enumerate((SIT_BODY, AFK_BODY))]


@pytest.fixture
def scene(reload_scene, monkeypatch):
    t, preparation, prior_path, prior, base, rows, committed, write = reload_scene
    op = renewal.op
    t.receipt['started_at'] = 20
    t.receipt['actor'] = t.fixture
    t.out = prior_path.parent.parent / 'renewal'
    t.out.mkdir()
    original_helper = Path(__file__).resolve().parents[4] / renewal.OLD_HELPER
    (op.lab.REPO / renewal.OLD_HELPER).write_bytes(original_helper.read_bytes())
    committed[str(renewal.OLD_HELPER)] = original_helper.read_bytes()
    prior['runtime_source_isolation'] = {'code_commit': prior['code_commit'],
        'operation_source': {'path': str(op.lab.REPO / renewal.OPERATION),
            'sha256': hashlib.sha256(committed[str(renewal.OPERATION)]).hexdigest()},
        'loaded_from': 'git_object_bytes', 'working_candidate_inputs_used': False}
    for kind in ('escape', 'stand', 'afk'):
        marker = Path(base['entry_source']['path']).parent / ('item_actionbar_pre_recon_' + kind + '_attempt.json')
        marker.write_text(json.dumps({'original': kind, 'input_replay_allowed': False}))
        prior[kind + '_attempt_source'] = op.bound(marker)
    write('restored', prior)
    entry_path = Path(base['entry_source']['path'])
    entry = json.loads(entry_path.read_text())
    entry['public'] = deepcopy(base['public'])
    entry_path.write_text(json.dumps(entry))
    base['entry_source'] = op.bound(entry_path)
    prior['entry_source'] = base['entry_source']
    prior['baseline'] = deepcopy(base)
    write('restored', prior)
    failed = {'completed': False, 'failure': 'RuntimeError: native baseline changed before ordinary reload',
        'code_commit': '4' * 40, 'restoration_code_commit': prior['code_commit'],
        'previous_code_commit': entry['code_commit'], 'first_failure': prior['first_failure'],
        'phase': 'item_actionbar_passive_observer_prepared', 'started_at': 10, 'finished_at': 11,
        'actor': t.fixture, 'runtime': t.receipt['runtime'], 'native_session': 'owned',
        'preparation_source': op.bound(preparation), 'fixture_source': op.bound(preparation),
        'source': op.bound(prior_path), 'restoration_source': op.bound(prior_path),
        'first_failure_source': prior['first_failure_source'], 'entry_source': base['entry_source'],
        'baseline': deepcopy(base), 'controller': 'code', 'model': None, 'revision': None, 'cases': [], 'cleanup': [],
        'input_sent': False, 'ordinary_inputs': [], 'mutation_sent': False, 'qualification_added': False,
        'drag_input_sent': False, 'clear_input_sent': False, 'gameplay_input_replayed': False, 'observer_only': True,
        'before_saved': deepcopy(base['saved']), 'before_resources': deepcopy(base['resources']),
        'before_native_state': deepcopy(base['native_state']), 'before_public': deepcopy(base['public']),
        'protected_checks': deepcopy(prior['protected_checks'])}
    failed_path = write('failed_observer', failed)
    rows.extend(sparse_idle())
    monkeypatch.setattr(op, 'packet_rows', lambda session, since, until: deepcopy(
        [row for row in rows if since <= row['time'] <= until]))
    ticks = iter(n / 100 for n in range(2100, 10000, 10))
    monkeypatch.setattr(renewal.time, 'time', lambda: next(ticks))
    monkeypatch.setattr(renewal, 'entries', lambda path: iter([]))
    monkeypatch.setattr(op, 'binding_key', lambda value: value.lower())
    t.native['pose']['stand'], t.native['afk'] = 1, True
    observe = t.observe
    def observed(label, **kwargs):
        state, frame = observe(label, **kwargs)
        frame['movement'] = {'speed': 0, 'dead': False, 'in_combat': False, 'on_taxi': False}
        return state, frame
    t.observe = observed
    def execute(action):
        assert t.persisted[-1]['ordinary_inputs'][-1]['input'] == action
        t.events.append(deepcopy(action))
        if action['kind'] == 'key':
            t.native['pose']['stand'] = 0
            at = renewal.time.time()
            rows.extend([{**row, 'time': at + n / 1000,
                'body': ('00', '00000000', '00', '0000000000')[n]} for n, row in enumerate(sparse_idle()[:4])])
        else:
            t.native['afk'] = False
    t.execute = execute
    return t, preparation, prior_path, failed_path, prior, failed, base, rows, write


def test_actual_two_sparse_updates_replay_without_inventing_a_combined_packet():
    proof = renewal.idle_packets(sparse_idle(), 'owned', 9, 12, 11)
    assert [p['body'] for p in proof['observed_owner_flags_packets']] == [SIT_BODY, AFK_BODY]
    assert proof['observed_owner_fields'] == {'UNIT_FIELD_BYTES_1': 1, 'PLAYER_FLAGS': 2}


@pytest.mark.parametrize('fault', ['missing_flags', 'duplicate', 'reverse', 'before_prior', 'after_failed', 'late',
    'extra_stand', 'movement', 'action', 'cast', 'foreign_session'])
def test_renewal_rejects_nonunique_or_unrelated_new_native_transition(fault):
    rows = sparse_idle()
    if fault == 'missing_flags': rows.pop()
    elif fault == 'duplicate': rows.append(deepcopy(rows[-1]))
    elif fault == 'reverse': rows[-1]['time'] = rows[-2]['time'] - .001
    elif fault == 'before_prior': rows[0]['time'] = 8
    elif fault == 'after_failed': rows[-1]['time'] = 11.1
    elif fault == 'late': rows[-1]['time'] = 12.5
    elif fault == 'extra_stand': rows.append(deepcopy(rows[0]))
    elif fault == 'foreign_session': rows[-1]['session'] = 'other'
    else:
        name = {'movement': 'CMSG_MOVE_START_FORWARD', 'action': renewal.op.ACTION, 'cast': 'CMSG_CAST_SPELL'}[fault]
        rows.append({'session': 'owned', 'time': 10.2, 'name': name, 'direction': 'to_native', 'body': ''})
    with pytest.raises(RuntimeError): renewal.idle_packets(rows, 'owned', 9, 14, 11)


def test_new_idle_cleanup_preserves_all_prior_authority_and_consumes_only_new_markers(scene):
    t, preparation, prior_path, failed_path, prior, failed, base, _, _ = scene
    old_markers = {key: Path(prior[key]['path']).read_bytes() for key in
        ('escape_attempt_source', 'stand_attempt_source', 'afk_attempt_source')}
    old_source, failed_source = prior_path.read_bytes(), failed_path.read_bytes()
    renewal.run(t, preparation, prior_path, failed_path)
    assert t.receipt['completed'] is True, t.receipt.get('failure')
    assert t.receipt['phase'] == 'item_actionbar_restored' and t.receipt['idle_renewal'] is True
    assert t.receipt['source'] == prior['first_failure_source']
    assert t.receipt['prior_restoration_source'] == renewal.op.bound(prior_path)
    assert t.receipt['failed_observer_source'] == renewal.op.bound(failed_path)
    assert t.events == [{'kind': 'key', 'value': 'x', 'hold': .4}, {'kind': 'chat', 'value': '/afk'}]
    assert len(t.receipt['restoration_checks']) == 13 and all(t.receipt['restoration_checks'].values())
    assert t.receipt['after_native_state'] == base['native_state']
    assert t.receipt['renewal_runtime_source']['loaded_from'] == 'committed_working_bytes'
    assert 'runtime_source_isolation' not in t.receipt
    assert prior_path.read_bytes() == old_source and failed_path.read_bytes() == failed_source
    for key, raw in old_markers.items():
        assert Path(prior[key]['path']).read_bytes() == raw
        assert t.receipt[key]['path'] != prior[key]['path'] if key != 'escape_attempt_source' else key not in t.receipt
    renewal.validate_restored_renewal(t.receipt, t.out / 'episode.json')


@pytest.mark.parametrize('key,value', [('input_sent', True), ('ordinary_inputs', [{'input': '/reload'}]),
    ('phase', 'item_actionbar_passive_observer_reload_started'), ('model', 'learned'), ('revision', 'learned'),
    ('controller', 'foreign'), ('mutation_sent', True), ('drag_input_sent', True), ('clear_input_sent', True),
    ('qualification_added', True), ('reload_attempt_source', {}), ('observer_only', False)])
def test_prior_failed_observer_must_have_no_input_or_consumed_reload(scene, key, value):
    t, preparation, prior_path, failed_path, _, failed, _, _, write = scene
    failed[key] = value
    write('failed_observer', failed)
    renewal.run(t, preparation, prior_path, failed_path)
    assert t.receipt['completed'] is False and t.events == []


@pytest.mark.parametrize('fault', ['wrong_native', 'bag_open', 'wrong_key', 'prior_marker_changed', 'reload_marker'])
def test_current_or_previous_authority_drift_refuses_every_cleanup_input(scene, fault):
    t, preparation, prior_path, failed_path, prior, _, base, _, _ = scene
    if fault == 'wrong_native': t.native['selection'] = 1
    elif fault == 'bag_open':
        original_observe = t.observe
        def observed(*args, **kwargs):
            state, frame = original_observe(*args, **kwargs)
            state['bags'] = [0]
            return state, frame
        t.observe = observed
    elif fault == 'wrong_key': base['public']['keys']['SITORSTAND'] = ['Q']
    elif fault == 'prior_marker_changed': Path(prior['stand_attempt_source']['path']).write_text('changed')
    else: (prior_path.parent / 'item_actionbar_observer_reload_attempt.json').write_text('consumed')
    renewal.run(t, preparation, prior_path, failed_path)
    assert t.receipt['completed'] is False and t.events == []


def test_interrupted_newstanding_input_is_terminal_and_preserves_first_markers(scene):
    t, preparation, prior_path, failed_path, prior, _, _, _, _ = scene
    old = Path(prior['stand_attempt_source']['path']).read_bytes()
    def interrupted(action):
        t.events.append(deepcopy(action))
        raise KeyboardInterrupt('new idle standing interrupted')
    t.execute = interrupted
    with pytest.raises(KeyboardInterrupt): renewal.run(t, preparation, prior_path, failed_path)
    new_marker = Path(t.receipt['stand_attempt_source']['path'])
    assert new_marker.exists() and Path(prior['stand_attempt_source']['path']).read_bytes() == old
    again = type(t)()
    again.receipt['started_at'] = 25
    renewal.run(again, preparation, prior_path, failed_path)
    assert again.receipt['completed'] is False and 'already consumed' in again.receipt['failure']
    assert again.events == []


@pytest.mark.parametrize('fault', ['native_flags', 'standing_key', 'restoration_packet', 'ancestry', 'marker_hash'])
def test_loader_typed_renewal_admission_rejects_forged_completed_receipt(scene, fault):
    t, preparation, prior_path, failed_path, _, _, _, _, _ = scene
    renewal.run(t, preparation, prior_path, failed_path)
    assert t.receipt['completed'] is True
    value = deepcopy(t.receipt)
    if fault == 'native_flags': value['pre_recon_idle_observation']['observed_owner_fields']['PLAYER_FLAGS'] = 0
    elif fault == 'standing_key': value['ordinary_inputs'][0]['input']['value'] = 'q'
    elif fault == 'restoration_packet': value['stand_cleanup_packets'][0]['body'] = '01'
    elif fault == 'ancestry': value['prior_restoration_source']['sha256'] = 'f' * 64
    else: value['stand_attempt_source']['sha256'] = 'f' * 64
    with pytest.raises(RuntimeError): renewal.validate_restored_renewal(value, t.out / 'episode.json')


def test_completed_renewal_cannot_be_copied_to_reset_its_reload_namespace(scene):
    t, preparation, prior_path, failed_path, _, _, _, _, _ = scene
    renewal.run(t, preparation, prior_path, failed_path)
    assert t.receipt['completed'] is True
    copy = t.out.parent / 'copied' / 'episode.json'
    copy.parent.mkdir()
    copy.write_text(json.dumps(t.receipt))
    with pytest.raises(RuntimeError, match='exact source and current code'):
        renewal.validate_restored_renewal(t.receipt, copy)


@pytest.mark.parametrize('fault', ['saved', 'resources', 'position'])
def test_drift_between_standing_and_afk_refuses_the_second_cleanup_input(scene, fault):
    t, preparation, prior_path, failed_path, _, _, base, _, _ = scene
    execute = t.execute
    def drift(action):
        execute(action)
        if action['kind'] == 'key':
            if fault == 'saved': base['saved']['quests'].append(1)
            elif fault == 'resources': base['resources']['money'] += 1
            else:
                observe = t.observe
                def moved(*args, **kwargs):
                    state, frame = observe(*args, **kwargs)
                    state['world_position'][0] += 1
                    return state, frame
                t.observe = moved
    t.execute = drift
    renewal.run(t, preparation, prior_path, failed_path)
    assert t.receipt['completed'] is False and t.receipt['failure']
    assert t.events == [{'kind': 'key', 'value': 'x', 'hold': .4}]
    assert not renewal.marker(t, 'afk').exists()

"""Actual journals bind input, native effect, public GUIDs and packet metadata."""
from copy import deepcopy
import hashlib
import json
from types import SimpleNamespace

import pytest

from tools.client_compatibility import bag_swap_evidence as e
from tools.client_compatibility import bag_swap_contract as c
from tools.client_compatibility import bag_swap_projection as projection
from tools.client_compatibility.world.tests.test_bag_swap_contract import native_rows
from tools.client_compatibility.world.tests.test_bag_swap_projection import packet, inventory_block, row
from tools.client_compatibility.world.tests.test_item_actionbar_contract import login_packets


def test_carried_authority_resolves_original_ui171_through_ui172_to_fresh_member(tmp_path, monkeypatch):
    monkeypatch.setattr(e.lab, 'ROOT', tmp_path)
    old, middle, current = ('evidence/ui171/frame.json', 'evidence/ui172/carried.json', 'evidence/ui173/carried.json')
    sha = 'a' * 64
    data = {'evidence/ui172/map.json': {'schema': e.ANCESTRY_SCHEMA, 'members': [
        {'original_path': str(tmp_path / old), 'sha256': sha, 'copy_member': middle}]},
        'evidence/ui173/map.json': {'schema': 'client442_bag_swap_fresh_ancestry_v1', 'members': [
            {'original_path': str(tmp_path / middle), 'sha256': sha, 'copy_member': current}], 'authorities': []},
        current: {'source_owned': True}}
    store = e.Sources(data, {current: sha})
    assert store.get({'path': str(tmp_path / old), 'sha256': sha}, False) == {'source_owned': True}
    assert store.member({'path': str(tmp_path / middle), 'sha256': sha}) == current
    remote = 'evidence/ui172_remote.json'
    store.maps[1]['authorities'].append({'original_path': str(tmp_path / remote), 'sha256': sha, 'copy_member': current})
    assert store.get({'path': str(tmp_path / remote), 'sha256': sha}, False) == {'source_owned': True}


@pytest.mark.parametrize('fault', ['cycle', 'duplicate', 'wrong_sha', 'escaping_copy'])
def test_carried_authority_chain_refuses_ambiguity_cycle_or_changed_member(tmp_path, monkeypatch, fault):
    monkeypatch.setattr(e.lab, 'ROOT', tmp_path)
    original, copied, sha = 'evidence/old/source.json', 'evidence/current/source.json', 'a' * 64
    row = {'original_path': str(tmp_path / original), 'sha256': sha, 'copy_member': copied}
    data = {'evidence/current/map.json': {'schema': 'client442_bag_swap_fresh_ancestry_v1', 'members': [row]},
        copied: {'source_owned': True}}
    digests = {copied: sha}
    if fault == 'cycle':
        row['copy_member'] = original
        digests = {}
    elif fault == 'duplicate':
        data['evidence/current/map.json']['members'].append(deepcopy(row))
    elif fault == 'wrong_sha':
        digests[copied] = 'b' * 64
    else:
        row['copy_member'] = '../outside.json'
    with pytest.raises(RuntimeError):
        e.Sources(data, digests).get({'path': str(tmp_path / original), 'sha256': sha}, False)


def fixture(tmp_path, monkeypatch):
    monkeypatch.setattr(e.lab, 'ROOT', tmp_path)
    wire = login_packets()
    native = native_rows(roundtrip=True)
    creation_times = [1100.4, 1100.5, 1100.6]
    for index, value in enumerate(native):
        value['time'] = creation_times[index] if index < 3 else value['time'] + 1091
    wire += native
    wire += [row(packet(inventory_block(swapped=True)), time=1101.25),
        row(packet(inventory_block(swapped=False)), time=1102.25)]
    for name, direction, time, body in [('CMSG_LOGOUT_REQUEST', 'from_client', 1103, '00'),
        ('CMSG_LOGOUT_REQUEST', 'to_native', 1103.01, ''), ('SMSG_LOGOUT_COMPLETE', 'from_native', 1103.2, ''),
        ('SMSG_LOGOUT_COMPLETE', 'to_client', 1103.21, '00')]:
        wire.append({'session': 'scout', 'name': name, 'direction': direction, 'time': time, 'body': body})
    wire.sort(key=lambda value: value['time'])
    replay = c.native_replay(wire, 'scout', 1099, 1103.2, rest_threshold=24)
    stages = []
    for inverse, kind, start, end, transition in ((False, 'forward', 1101, 1101.4, replay['native_inventory_transitions'][1]),
            (True, 'reverse', 1102, 1102.4, replay['native_inventory_transitions'][2])):
        window = c.packet_rows(wire, 'scout', start, end)
        stages.append({'phase': 'bags_swap_' + kind, kind + '_started_at': start, kind + '_finished_at': end,
            kind + '_packets': window, kind: c.swap_packets(window, 'scout', start, end, reverse=inverse),
            kind + '_native_transition': transition, kind + '_projection': projection.delivered_slots(window,
                'scout', transition['time'], end, swapped=not inverse)})
    events = [{'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical', 'time': 1100.01}]
    for value in wire:
        direction, name = value['direction'], value['name']
        native_packet = direction in ('to_native', 'from_native')
        session = 'scout' if native_packet or name in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGOUT_COMPLETE') else 'physical'
        events.append({'session': session, 'name': name, 'direction': direction, 'time': value['time'] - .001,
            'bytes': len(bytes.fromhex(value['body'])), 'event': 'native_packet' if native_packet else 'modern_packet'})
    events.sort(key=lambda value: value['time'])
    closure = {'phase': e.PHASE, 'finished_at': 1104}
    closure_member = 'evidence/swap/close/episode.json'
    digests = {closure_member: 'a' * 64}
    raw_members, refs = {}, {}
    for kind, rows in (('packets', wire), ('events', events)):
        member = 'evidence/swap/journals/' + kind + '.jsonl'
        raw = ''.join(json.dumps(value, separators=(',', ':')) + '\n' for value in rows).encode()
        digests[member] = hashlib.sha256(raw).hexdigest()
        raw_members[member] = rows
        refs[kind] = {'path': str(tmp_path / member), 'sha256': digests[member]}
    data = {closure_member: closure, 'evidence/swap/journal_receipt.json': {
        'schema': 'client442_bag_swap_journals_v1', 'closure_source': {'path': str(tmp_path / closure_member),
            'sha256': digests[closure_member]}, 'journal_sources': refs}}
    store = SimpleNamespace(data=data, digests=digests, local=False)
    tracking = {'members': set(e.TRACKING_MEMBERS), 'raw_journals': raw_members, 'events': events}
    entry = {'started_at': 1099, 'finished_at': 1101, 'native_owner_proof': {'rest_threshold': 24},
        'login_packets': login_packets()}
    park = {'logout_started_at': 1103, 'logout_finished_at': 1103.3,
        'logout_packets': [value for value in wire if value['name'] in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_COMPLETE') and
            value['direction'] != 'from_client']}
    park.update(raw_native_logout_history=c.packet_rows(wire, 'scout', 1099, 1103.2), native_logout_proof=replay)
    current = [{'native_session': 'scout'}, entry, {}, park, {}, {}]
    monkeypatch.setattr(e, 'stage_chain', lambda *args: stages)
    return store, closure, tracking, current, stages, wire, events


def test_actual_complete_journals_bind_both_request_pairs_native_effects_and_guid_deliveries(tmp_path, monkeypatch):
    store, closure, tracking, current, _, _, _ = fixture(tmp_path, monkeypatch)
    result = e.actual_journals(store, closure, tracking, current)
    assert result == {'actual_packet_journals_verified': True, 'native_item_fields_unchanged': True}


@pytest.mark.parametrize('fault', ['missing_modern_swap', 'wrong_modern_session', 'wrong_native_session',
    'missing_native_effect', 'missing_delivered_projection', 'wrong_bytes', 'wrong_event_kind',
    'extra_metadata_swap', 'wrong_instance', 'missing_instance', 'wrong_window', 'substituted_transition',
    'early_forward_projection', 'early_reverse_projection', 'missing_journal', 'wrong_closure', 'raw_event_drift',
    'changed_pre_stop_history', 'changed_pre_stop_proof'])
def test_missing_wrong_or_early_metadata_and_deliveries_never_prove_an_occupied_swap(tmp_path, monkeypatch, fault):
    store, closure, tracking, current, stages, wire, events = fixture(tmp_path, monkeypatch)
    modern = next(value for value in events if value.get('name') == c.ACTION and value.get('direction') == 'from_client')
    native = next(value for value in events if value.get('name') == c.ACTION and value.get('direction') == 'to_native')
    if fault == 'missing_modern_swap': events.remove(modern)
    elif fault == 'wrong_modern_session': modern['session'] = 'scout'
    elif fault == 'wrong_native_session': native['session'] = 'physical'
    elif fault == 'missing_native_effect':
        events.remove(next(value for value in events if value.get('name') == 'SMSG_UPDATE_OBJECT' and
            value.get('direction') == 'from_native' and 1101.1 < value['time'] < 1101.3))
    elif fault == 'missing_delivered_projection':
        events.remove(next(value for value in events if value.get('name') == 'SMSG_UPDATE_OBJECT' and
            value.get('direction') == 'to_client' and 1101.1 < value['time'] < 1101.3))
    elif fault == 'wrong_bytes': modern['bytes'] += 1
    elif fault == 'wrong_event_kind': native['event'] = 'modern_packet'
    elif fault == 'extra_metadata_swap': events.append({**modern, 'time': 1102.8})
    elif fault == 'wrong_instance': events[0]['account_id'] = 6
    elif fault == 'missing_instance': events[:] = [value for value in events if value.get('event') != 'instance_authenticated']
    elif fault == 'wrong_window': stages[0]['forward_packets'] = stages[0]['forward_packets'][:-1]
    elif fault == 'substituted_transition': stages[0]['forward_native_transition'] = stages[1]['reverse_native_transition']
    elif fault in ('early_forward_projection', 'early_reverse_projection'):
        chosen = stages[0 if fault == 'early_forward_projection' else 1]
        kind = 'forward' if fault == 'early_forward_projection' else 'reverse'
        delivered = next(value for value in wire if value is chosen[kind + '_projection']['delivery'] or
            value == chosen[kind + '_projection']['delivery'])
        delivered['time'] = chosen[kind + '_native_transition']['time'] - .01
        wire.sort(key=lambda value: value['time'])
        chosen[kind + '_packets'] = c.packet_rows(wire, 'scout', chosen[kind + '_started_at'], chosen[kind + '_finished_at'])
    elif fault == 'missing_journal': tracking['members'].remove(e.TRACKING_MEMBERS[0])
    elif fault == 'wrong_closure': store.data['evidence/swap/journal_receipt.json']['closure_source']['sha256'] = 'b' * 64
    elif fault == 'changed_pre_stop_history': current[3]['raw_native_logout_history'] = current[3]['raw_native_logout_history'][:-1]
    elif fault == 'changed_pre_stop_proof': current[3]['native_logout_proof'] = {}
    else: tracking['events'] = events[:-1]
    with pytest.raises(RuntimeError):
        e.actual_journals(store, closure, tracking, current)


@pytest.mark.parametrize('field,value', [('code_commit', 'f' * 40), ('custom_script_permission', 'allowed')])
def test_final_closure_cannot_coedit_code_or_script_labels_even_with_identical_source_package(monkeypatch, field, value):
    ready = {'actor': {'guid': 2}, 'runtime': {}, 'code_commit': 'c' * 40, 'committed_sources': [],
        'authority_source': {}, 'predecessor': {'primary_stop': {}}}
    closure = {'phase': e.PHASE, 'completed': True, 'failure': None, 'started_at': 20, 'finished_at': 21,
        'sources': {}, 'shutdown_checks': dict.fromkeys(e.shared.SHUTDOWN_CHECKS, True), 'proof': {},
        'before': {}, 'after': {}, 'all_offline_snapshot': {}, 'actor': ready['actor'], 'runtime': {},
        'primary_stop_source': {}, 'authority_source': {}, 'input_sent': False, 'mutation_sent': False,
        'qualification_added': False, 'action': 'stop_parked_scout_after_bag_swap_roundtrip', 'stop_attempted': True,
        'controller': 'code', 'model': None, 'revision': None, 'softTargetInteract': e.shared.SCRIPT_BOUNDARY,
        'code_commit': ready['code_commit'], 'custom_script_permission': 'blocked_by_user', 'committed_sources': []}
    closure[field] = value
    monkeypatch.setattr(e, 'lifecycle', lambda *args: ({}, {}, [ready, {}, {}, {}, {}, {'finished_at': 19}]))
    with pytest.raises(RuntimeError, match='whole closed occupied-swap resource pause'):
        e.proof({'evidence/swap/close/episode.json': closure}, {'evidence/swap/close/episode.json': 'a' * 64}, {})


def layout_fixture():
    state = {'bags': [], 'panels': [], 'target': {'exists': False}, 'world_position': [1, 2, 3, 4],
        'cursor_info': [], 'spell_targeting': False, 'lua_errors': [], 'blocked_actions': [], 'chat_edit_open': False}
    native = {'pose': {'stand': 0, 'sheath': 1}, 'afk': False, 'selection': 0, 'health': 60}
    public = {'active_spec': 1, 'page': 1, 'effective_page': 1, 'bonus_offset': 0, 'viewport': [1280, 720],
        'actions': [{'button': 'ActionButton1', 'slot': 1, 'kind': None, 'id': None, 'visible': True}]}
    base = {'state': state, 'native_state': native, 'public': public}
    operation = deepcopy(base)
    operation['layout_restoration_checks'] = dict.fromkeys(e.shared.LAYOUT_CHECKS, True)
    return operation, base


def test_actual_retained_layout_facts_restore_closed_original_layout():
    e.restored_layout(*layout_fixture())


@pytest.mark.parametrize('cursor', [0, 0.0, '', 'missing'])
def test_restored_layout_requires_actual_json_empty_cursor_shape(cursor):
    operation, base = layout_fixture()
    if cursor == 'missing': operation['state'].pop('cursor_info')
    else: operation['state']['cursor_info'] = cursor
    with pytest.raises(RuntimeError):
        e.restored_layout(operation, base)


@pytest.mark.parametrize('fault', ['bags', 'panels', 'target', 'position', 'pose', 'afk', 'cursor', 'bar', 'ui'])
def test_true_restoration_labels_cannot_hide_changed_retained_layout_facts(fault):
    operation, base = layout_fixture()
    if fault == 'bags': operation['state']['bags'] = [0]
    elif fault == 'panels': operation['state']['panels'] = ['SpellBookFrame']
    elif fault == 'target': operation['state']['target'] = {'exists': True}
    elif fault == 'position': operation['state']['world_position'][0] += 1
    elif fault == 'pose': operation['native_state']['pose']['stand'] = 1
    elif fault == 'afk': operation['native_state']['afk'] = True
    elif fault == 'cursor': operation['state']['cursor_info'] = ['item', 6948]
    elif fault == 'bar': operation['public']['actions'][0]['id'] = 6948
    else: operation['state']['lua_errors'] = ['error']
    with pytest.raises(RuntimeError, match='actual public/native'):
        e.restored_layout(operation, base)


@pytest.mark.parametrize('fault', ['peer_pet', 'owner_health', 'owner_saved'])
@pytest.mark.parametrize('kind', ['forward', 'reverse', 'restore'])
def test_intermediate_stage_full_projection_cannot_hide_unrelated_actor_or_owner_changes(kind, fault):
    from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture as preserved_fixture
    before, now, *_ = preserved_fixture(kind == 'forward')
    now['2']['native']['online'] = 1
    if fault == 'peer_pet': now['6']['pets'][0]['curhealth'] += 1
    elif fault == 'owner_health': now['2']['native']['health'] = 59
    else: now['2']['saved']['spells'] = [[1, 1, 0]]
    field = kind + '_snapshot' if kind != 'restore' else 'snapshot'
    with pytest.raises(RuntimeError):
        e.stage_snapshots(before, [{field: now}])


def test_inverse_and_restored_saved_projection_may_lag_exact_native_restore_until_normal_logout():
    from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture as preserved_fixture
    before, now, *_ = preserved_fixture(True)
    now['2']['native']['online'] = 1
    e.stage_snapshots(before, [{'reverse_snapshot': now}, {'snapshot': now}])


@pytest.mark.parametrize('fault', [None, 'missing', 'source', 'control', 'point', 'frame'])
def test_original_backpack_opening_requires_exact_review_and_source_owned_frame(monkeypatch, fault):
    ref = {'path': '/private/entry/episode.json', 'sha256': 'a' * 64}
    image = {'file': 'screen.png', 'sha256': 'b' * 64}
    entry = {'frame': image}
    review = {'reviewed': True, 'control': 'MainMenuBarBackpackButton', 'source': ref, 'frame': image,
        'pickup_point_inside_button': True, 'point': [1200, 680]}
    stage = {'backpack_open_review': ref, 'backpack_open_input': {'kind': 'click', 'value': [1200, 680]}}
    if fault == 'missing': review = {}
    elif fault == 'source': review['source'] = {**ref, 'sha256': 'c' * 64}
    elif fault == 'control': review['control'] = 'bags.swap_item'
    elif fault == 'point': review['point'] = [1201, 680]
    elif fault == 'frame': review['frame'] = {**image, 'sha256': 'c' * 64}
    seen = []
    monkeypatch.setattr(e, 'frame', lambda *args: seen.append(args))
    store = SimpleNamespace(get=lambda *args: review)
    if fault is None:
        e.opening_review(store, stage, ref, entry)
        assert len(seen) == 1
    else:
        with pytest.raises(RuntimeError, match='ordinary backpack opening'):
            e.opening_review(store, stage, ref, entry)

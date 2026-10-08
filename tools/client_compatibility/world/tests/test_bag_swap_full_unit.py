"""A complete producer-shaped occupied swap survives actual lifecycle and tar proof."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import tarfile

import pytest

from tools.client_compatibility import bag_swap_contract as c
from tools.client_compatibility import bag_swap_evidence as e
from tools.client_compatibility import bag_swap_preservation as preservation
from tools.client_compatibility import bag_swap_projection as projection
from tools.client_compatibility import bag_swap_sources as sources
from tools.client_compatibility import review_bag_swap_checkpoint as reviewer
from tools.client_compatibility import checkpoint_bag_swap as publication
from tools.client_compatibility.world.tests import test_item_actionbar_sources as prior_snapshot
from tools.client_compatibility.world.tests.test_bag_swap_publication import carried_fixture
from tools.client_compatibility.world.tests.test_bag_swap_contract import (
    inventory, resources, public as bag_public, slot_fields, item_fields, packets)
from tools.client_compatibility.world.tests.test_bag_swap_projection import packet as delivered_packet, inventory_block
from tools.client_compatibility.world.tests.test_item_actionbar_contract import native_packet, owner_fields, login_packets
from tools.client_compatibility.world.tests.test_item_actionbar_evidence import stock_public
from tools.client_compatibility.world.tests.test_item_actionbar_preservation import precision as precise



def capture_initialization(tmp_path, native, commit, started_at):
    """Execute ordinary initialize with fake process/Git/time; no live authority."""
    from tools.client_compatibility import checkpoint_interactions as initializer
    root = Path(tmp_path) / 'fake_initialization_lab'
    (root / 'evidence').mkdir(parents=True)
    batch = root / 'evidence/ordinary_batch'
    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(initializer.lab, 'ROOT', root)
        patch.setattr(initializer.lab, 'owned_process', lambda kind: deepcopy(native) if kind == 'worldserver' else None)
        patch.setattr(initializer.subprocess, 'check_output', lambda *a, **k: commit)
        patch.setattr(initializer.time, 'time', lambda: started_at)
        initializer.initialize(batch)
    return {name: (batch / name).read_bytes() for name in ('batch.json', 'native_server_before.json')}

def complete_fixture(tmp_path, monkeypatch, *, authority=None, boot_builder=None, code_epoch_builder=None,
        indexed=None):
    original_snapshot = prior_snapshot.snapshot
    def occupied_snapshot():
        value = original_snapshot()
        value['2']['inventory'] = inventory()
        return value
    if indexed is not None:
        carried, old, carried_ready, ancestry = indexed['authority']
        authority = indexed['authority']
    elif authority is None:
        monkeypatch.setattr(prior_snapshot, 'snapshot', occupied_snapshot)
        carried, carried_ready, ancestry = carried_fixture(tmp_path, monkeypatch)
    else:
        carried, old, carried_ready, ancestry = authority
    root, repo = e.lab.ROOT, e.lab.REPO
    cache_member = str(Path(carried_ready['authority_source']['path']).relative_to(root))
    cache = carried.data[cache_member]
    if authority is None:
        old = sources.validate_bundle(cache['values'], cache['refs'], cache['graph'])
    else:
        repo = next(Path(row['path']).parents[3] for row in old['closure']['committed_sources']
            if row['path'].endswith('/experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json'))
    baseline = deepcopy(old['snapshot'])
    c.owned_snapshot(baseline)
    batch = root / ('evidence/client_interactions_20990101_ui174' if indexed is not None else
        'evidence/client_interactions_20990101_ui173' if authority else
        'evidence/client_interactions_20990101_ui172')
    offset = int(old['closure']['finished_at']) + 10 - 1130 if authority else 0
    def tm(value):
        return value + offset + (13 if boot_builder and value >= 1201 else 0)
    paths = dict(carried.paths) if indexed is not None else {}
    if indexed is not None:
        data, digests, files = dict(carried.data), dict(carried.digests), dict(carried.paths)
    elif authority:
        members = [cache_member, str(Path(carried_ready['runtime_authority_source']['path']).relative_to(root))]
        members += [row['copy_member'] for row in ancestry['members'] + ancestry['authorities']]
        data = {member: carried.data[member] for member in members if member in carried.data}
        digests = {member: carried.digests[member] for member in members}
        files = {member: carried.files[member] for member in members}
    else:
        data, digests, files = dict(carried.data), dict(carried.digests), {}
    if indexed is None:
        files[cache_member] = Path(carried_ready['authority_source']['path']).read_bytes()
    for row in ancestry['members'] + ancestry['authorities'] if indexed is None else []:
        if not authority:
            files[row['copy_member']] = Path(row['original_path']).read_bytes()
    for row in ancestry.get('journals', []):
        files[row['copy_member']] = b''.join((json.dumps(line) + '\n').encode()
            for line in carried.raw_journals[row['copy_member']])
        assert hashlib.sha256(files[row['copy_member']]).hexdigest() == row['sha256']

    def insert(name, raw):
        path = batch / name
        physical = indexed['directory'] / name if indexed is not None else path
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_bytes(raw)
        member = str(path.relative_to(root))
        data[member], files[member], digests[member] = json.loads(raw), raw, hashlib.sha256(raw).hexdigest()
        paths[member] = str(physical)
        return {'path': str(path), 'sha256': digests[member]}

    def write(name, value):
        return insert(name, (json.dumps(value, indent=2) + '\n').encode())

    # Initialization executes before resume/preparation. The indexed driver must
    # retain the originals it captured before admission/carry; it cannot backfill
    # an experiment's missing ordinary batch identity at this late stage.
    initialization = indexed['initialization'] if indexed is not None else capture_initialization(
        tmp_path, old['runtime']['worldserver'], ('d' if authority else 'e') * 40, tm(1129))
    assert set(initialization) == {'batch.json', 'native_server_before.json'}
    initialization_refs = {key: insert(name, initialization[name]) for key, name in (
        ('batch_source', 'batch.json'), ('native_server_before_source', 'native_server_before.json'))}
    initialized = json.loads(initialization['batch.json'])
    assert initialized['native_worldserver'] == json.loads(initialization['native_server_before.json']) == old['runtime']['worldserver']
    assert initialized['code_commit'] == ('d' if authority else 'e') * 40
    assert old['closure']['finished_at'] < initialized['started_at'] < tm(1130)
    if indexed is None: write('ancestry_manifest.json', ancestry)
    compact_ref = carried_ready['runtime_authority_source'] if authority else write(
        'runtime_authority.json', sources.compact_authority(old, carried_ready['authority_source']))
    actor = deepcopy(old['origin_actor'])
    runtime = deepcopy(old['runtime'])
    runtime['client'] = {'pid': 50, 'start_ticks': '5000'} if authority else {'pid': 30, 'start_ticks': '3000'}
    monitor = {'second_monitor_verified': True, 'monitor': {'name': 'HDMI-1'}, 'pid': runtime['client']['pid'],
        'input_isolation': {'actor': 'scout', 'host_activation_sent': False, 'game_pid': 51 if authority else 31,
            'display': ':2', 'window_id': 37748738, 'actor_lock': 'scout'}}
    png = b'\x89PNG\r\n\x1a\nsynthetic-owned-swap-frame'
    def frame(name):
        path = batch / name / 'screen.png'
        physical = indexed['directory'] / name / 'screen.png' if indexed is not None else path
        physical.parent.mkdir(parents=True, exist_ok=True)
        physical.write_bytes(png)
        member = str(path.relative_to(root))
        files[member] = png
        paths[member] = str(physical)
        digests[member] = hashlib.sha256(png).hexdigest()
        return {'file': 'screen.png', 'sha256': digests[member], 'monitor': deepcopy(monitor)}

    committed_sources = []
    source_root = Path(__file__).resolve().parents[4]
    for relative in projection.SOURCE_FILES if indexed is None else ():
        path = repo / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((source_root / relative).read_bytes())
        committed_sources.append(sources.bound(path))
    epoch_ref = None
    if code_epoch_builder:
        committed_sources, epoch_ref = code_epoch_builder(old, repo, write)
    def trial(name, phase, start, finish, **fields):
        return {'schema': 'client442_laya_interactions_v1', 'phase': phase, 'completed': True, 'failure': None,
            'started_at': start, 'finished_at': finish, 'actor': deepcopy(actor), 'runtime': deepcopy(runtime),
            'controller': 'code', 'model': None, 'revision': None, 'code_commit': ('d' if authority else 'e') * 40,
            'committed_sources': deepcopy(committed_sources), 'cases': [], 'cleanup': [],
            'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(e.shared.SCRIPT_BOUNDARY),
            'qualification_added': False, 'input_sent': False, 'mutation_sent': False, **fields}

    resume = {'schema': 'client442_bag_swap_scout_resume_v1', 'phase': 'bags_swap_scout_launched',
        'completed': True, 'failure': None, 'installed': True, 'started_at': tm(1130),
        'launch_finished_at': tm(1131), 'finished_at': tm(1131), 'authority_source': carried_ready['authority_source'],
        'runtime_authority_source': compact_ref,
        'predecessor': old['predecessor'], 'all_offline_snapshot': baseline, 'origin_actor': actor,
        'runtime': runtime, 'previous_runtime': old['runtime'], 'available_memory_kib_before': 6 * 1024 * 1024,
        'checks': dict.fromkeys(('native_unchanged', 'bridge_unchanged', 'fresh_scout',
            'all_six_saved_snapshots', 'primary_stopped', 'HDMI_1', 'private_input'), True)}
    if indexed is not None:
        resume.update(initialization_refs, code_commit='d' * 40,
            committed_sources=deepcopy(committed_sources))
    if epoch_ref:
        resume['current_code_epoch_source'] = epoch_ref
    resume_ref = write('resume/report.json', resume)
    selection = trial('selection', 'bags_swap_scout_captured', tm(1131.1), tm(1131.2), frame=frame('selection'))
    selection_ref = write('selection/episode.json', selection)
    selection_review = {'reviewed': True, 'control': 'Harnesstwo', 'source': selection_ref,
        'frame': selection['frame'], 'selected_character': 'Harnesstwo', 'selected_level': 1}
    selection_review_ref = write('selection_review/review.json', selection_review)
    authentication = {'event': 'world_authenticated', 'account_id': 2, 'session': 'scout', 'time': tm(1131.5)}
    ready = trial('ready', 'bags_swap_scout_ready', tm(1132), tm(1133), authority_source=carried_ready['authority_source'],
        runtime_authority_source=compact_ref,
        predecessor=old['predecessor'], predecessor_dvc_pointer=old['dvc_pointer'], all_offline_snapshot=baseline,
        native_session='scout', resume_source=resume_ref, selection_source=selection_ref,
        realm_authentication=authentication, frame=frame('ready'),
        screen_review={**selection_review_ref, 'frame': selection['frame']})
    if indexed is not None:
        ready.update(initialization_refs)
    if epoch_ref:
        ready['current_code_epoch_source'] = epoch_ref
    ready_ref = write('ready/episode.json', ready)
    prior_precision = {'row': old['closure']['exact_precision']['after_row']} if indexed is not None else old['closure']['exact_precision'] if authority else next(value for value in old['graph']['data'].values() if
        value.get('phase') == 'item_actionbar_rest_precision_complete' and value.get('after') == baseline)
    exact_before = prior_precision['row']['exact_rest_bonus']
    exact_after, text = preservation.native_rest(exact_before, tm(1200) - baseline['2']['native']['logout_time'])
    if indexed is not None:
        binding = deepcopy(indexed['binding'])
    elif authority:
        member = str(Path(old['closure']['before_precision_source']['path']).relative_to(root))
        binding = deepcopy(old['graph']['data'][member]['rest_sources'])
    else:
        binding = deepcopy(prior_precision['rest_sources'])
    before = trial('before_precision', 'bags_swap_rest_precision_complete', tm(1134), tm(1135),
        source=ready_ref, before=baseline, after=baseline, query=preservation.PRECISION_QUERY,
        row=precise(baseline['2']['native'], exact_before), rest_sources=binding,
        checks=dict.fromkeys(e.shared.PRECISION_CHECKS, True))
    before_ref = write('before_precision/episode.json', before)
    state = {'player': 'Harnesstwo', 'guid': 'Player-1-00000002', 'level': 1, 'xp': 0, 'xp_max': 400,
        'xp_exhaustion': 2 * int(exact_after), 'panels': [], 'bags': [], 'bag_items': [], 'cursor_info': False,
        'spell_targeting': False, 'lua_errors': [], 'blocked_actions': [], 'chat_edit_open': False,
        'world_position': [-8914.86, -135.609, 80.4425, 5.83261], 'target': {'exists': False, 'guid': '', 'name': ''}}
    native_state = {'pose': {'stand': 0, 'sheath': 1}, 'afk': False, 'selection': 0,
        'health': 60, 'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0}
    native_resources = resources()
    native_resources['money'] = baseline['2']['native'].get('money', 0)
    native_original = {**native_state, 'selection': {'native_guid': 0}, 'resources': native_resources,
        'actions': baseline['2']['saved']['actions']}
    boot = None
    login = [{**row, 'time': row['time'] + 100 + offset} for row in login_packets()]
    creations = [native_packet({**owner_fields(), **slot_fields()}, time=tm(1200.5)),
        native_packet(item_fields(c.SOURCE), guid=c.SOURCE['guid'], kind=1, time=tm(1200.6)),
        native_packet(item_fields(c.DESTINATION), guid=c.DESTINATION['guid'], kind=1, time=tm(1200.7))]
    if boot_builder:
        boot, native_resources = boot_builder(baseline, exact_after, tm(1200), tm(1199), tm(1201))
        state['world_position'] = boot['baseline_pose']
        native_state['pose']['sheath'] = 0
        native_original.update(pose=native_state['pose'], resources=native_resources)
        login = boot['login_packets']
        creations = [row for row in boot['rows'] if row not in login]
    owner_proof = c.native_replay(login + creations, 'scout', tm(1199), tm(1201),
        login_sync=boot['proof'] if boot else None, events=boot['events'] if indexed is not None else None)
    entry = trial('entry', 'bags_swap_entered', tm(1199), tm(1201), preparation_source=ready_ref,
        precision_source=before_ref, all_offline_snapshot=baseline, native_session='scout',
        native_before_entry=baseline['2']['native'], entered_native={**baseline['2']['native'], 'online': 1},
        login_packets=login, owner_packets=owner_proof['packets'], native_owner_proof=owner_proof,
        saved=baseline['2']['saved'], resources=native_resources, active_spec=0,
        public=stock_public(baseline['2']['saved']['actions']), state=state, frame=frame('entry'), native_original=native_original)
    if boot:
        entry.update(login_sync=boot['proof'], raw_entry_packets=boot['rows'], raw_entry_events=boot['events'])
    entry_ref = write('entry/episode.json', entry)
    base = {'snapshot': baseline, 'saved': entry['saved'], 'resources': native_resources, 'public': entry['public'],
        'state': state, 'frame': entry['frame'], 'active_spec': 0, 'entry_source': entry_ref,
        'precision_source': before_ref, 'native_state': native_state, 'native_original': native_original}
    common = {'preparation_source': ready_ref, 'entry_source': entry_ref, 'precision_source': before_ref,
        'baseline': base, 'native_session': 'scout'}
    online = deepcopy(baseline)
    online['2']['native'].update(online=1, rest_bonus=text)
    opening_ref = write('opening_review/review.json', {'reviewed': True, 'control': 'MainMenuBarBackpackButton',
        'source': entry_ref, 'frame': entry['frame'], 'pickup_point_inside_button': True, 'point': [1200, 690]})
    opened = {**state, **bag_public()}
    first = trial('forward_ready', 'bags_swap_forward_ready', tm(1202), tm(1203), **common, state=opened,
        frame=frame('forward_ready'), resources=native_resources, snapshot=online, public=entry['public'], native_state=native_state,
        backpack_open_review=opening_ref, backpack_open_input={'kind': 'click', 'value': [1200, 690]})
    first_ref = write('forward_ready/episode.json', first)
    wire = boot['rows'] if boot else login + creations
    forward_wire = packets(start=tm(1204)) + [native_packet(slot_fields(True), creation=False, time=tm(1204.2)),
        {'session': 'scout', 'time': tm(1204.3), 'name': 'SMSG_UPDATE_OBJECT', 'direction': 'to_client',
            'body': delivered_packet(inventory_block()).hex()}]
    reverse_wire = packets(True, tm(1208)) + [native_packet(slot_fields(), creation=False, time=tm(1208.2)),
        {'session': 'scout', 'time': tm(1208.3), 'name': 'SMSG_UPDATE_OBJECT', 'direction': 'to_client',
            'body': delivered_packet(inventory_block(swapped=False)).hex()}]
    logout = [{'session': 'scout', 'time': tm(1215) + i * .1, 'name': name, 'direction': direction, 'body': raw}
        for i, (name, direction, raw) in enumerate((('CMSG_LOGOUT_REQUEST', 'to_native', ''),
            ('SMSG_LOGOUT_COMPLETE', 'from_native', ''), ('SMSG_LOGOUT_COMPLETE', 'to_client', '00')))]
    wire += forward_wire + reverse_wire + [{'session': 'scout', 'time': tm(1214.99), 'name': 'CMSG_LOGOUT_REQUEST',
        'direction': 'from_client', 'body': '00'}] + logout
    if not boot:
        wire.sort(key=lambda row: row['time'])
    def complete_events():
        events = deepcopy(boot['events']) if boot else [
            {'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical', 'time': tm(1200.15)}]
        for row in wire:
            physical = 'scout' if row['direction'] in ('to_native', 'from_native') or row['name'] in (
                'CMSG_PLAYER_LOGIN', 'SMSG_LOGOUT_COMPLETE') else 'physical'
            if any(event.get('session') == physical and event.get('name') == row['name'] and
                event.get('direction') == row['direction'] and event.get('bytes') == len(bytes.fromhex(row['body'])) and
                0 <= row['time'] - event['time'] < .1 for event in events):
                continue
            events.append({'event': 'native_packet' if row['direction'] in ('to_native', 'from_native') else 'modern_packet',
                'session': physical, 'time': row['time'] - .01, 'name': row['name'],
                'direction': row['direction'], 'bytes': len(bytes.fromhex(row['body']))})
        events.sort(key=lambda row: row['time'])
        return events
    full_events = complete_events() if indexed is not None else None
    replay = c.native_replay(wire, 'scout', tm(1199), tm(1215.1), login_sync=boot['proof'] if boot else None,
        events=full_events)

    def drag(kind, review_source, reviewed, inverse, start, finish, raw, inherited=None):
        intent = {'kind': 'drag', 'start': [20, 20] if not inverse else [60, 20],
            'end': [60, 20] if not inverse else [20, 20], 'item': 6948, 'item_guid': 41,
            'occupied_item': 58231, 'occupied_item_guid': 33,
            'source_slot': 2 if inverse else 1, 'destination_slot': 1 if inverse else 2}
        review = {'reviewed': True, 'control': 'bags.swap_item', 'source': review_source,
            'frame': reviewed['frame'], 'point': intent['start'], 'destination_point': intent['end'],
            'pickup_point_inside_button': True, 'destination_point_inside_button': True,
            **{key: intent[key] for key in ('item', 'item_guid', 'occupied_item', 'occupied_item_guid', 'source_slot', 'destination_slot')}}
        review_ref = write(kind + '_review/review.json', review)
        attempt_ref = write('entry/bag_swap_' + kind + '_attempt.json', {'schema': 'client442_bag_swap_consumed_attempt_v1',
            'operation': 'bags.swap_item', 'kind': kind, 'consumed': True, 'input_replay_allowed': False,
            'entry_source': entry_ref, 'preparation_source': ready_ref, 'actor': actor, 'runtime': runtime,
            'native_session': 'scout', 'input_intent': intent, 'created_at': start - .1,
            'operation_output': str(batch / kind / 'episode.json')})
        native = deepcopy(native_resources)
        if not inverse:
            native['backpack'][0], native['backpack'][1] = native['backpack'][1], native['backpack'][0]
        snapshot = deepcopy(online)
        snapshot['2']['inventory'] = c.expected_inventory(baseline['2']['inventory'], swapped=not inverse)
        transition = replay['native_inventory_transitions'][2 if inverse else 1]
        stage = trial(kind, 'bags_swap_' + kind, start, finish, **common, source=review_source,
            state={**state, **bag_public(not inverse)}, frame=frame(kind), snapshot=snapshot,
            public=entry['public'], native_state=native_state, resources=native)
        if inherited:
            stage.update(inherited)
        stage.update({kind: c.swap_packets(raw, 'scout', start, finish, reverse=inverse), kind + '_intent': intent,
            kind + '_review': review_ref, kind + '_review_source': review_source, kind + '_attempt_source': attempt_ref,
            kind + '_started_at': start, kind + '_finished_at': finish, kind + '_packets': raw,
            kind + '_native_transition': transition, kind + '_projection': projection.delivered_slots(raw, 'scout',
                transition['time'], finish, swapped=not inverse), kind + '_resources': native,
            kind + '_snapshot': snapshot, kind + '_cursor': False})
        return stage

    forward = drag('forward', first_ref, first, False, tm(1204), tm(1205), forward_wire)
    forward['autosave'] = {'mechanism': 'native_PlayerSaveInterval', 'bound_seconds': 150, 'heartbeat_seconds': 2,
        'persisted': True, 'saveall_sent': False, 'sql_write_sent': False, 'elapsed_seconds': 1,
        'configured_interval_ms': 90000, 'first_timer_ms': [45000, 135000],
        'config_source': binding['config_source'], 'native_timer_source': binding['native_formula_source']}
    forward_ref = write('forward/episode.json', forward)
    inherited = {key: value for key, value in forward.items() if key.startswith('forward') or key == 'autosave'}
    reverse_ready = trial('reverse_ready', 'bags_swap_reverse_ready', tm(1206), tm(1207), **common,
        source=forward_ref, state=forward['state'], frame=frame('reverse_ready'), snapshot=forward['snapshot'],
        resources=forward['resources'], public=entry['public'], native_state=native_state, **inherited)
    reverse_ready_ref = write('reverse_ready/episode.json', reverse_ready)
    reverse = drag('reverse', reverse_ready_ref, reverse_ready, True, tm(1208), tm(1209), reverse_wire, inherited)
    reverse_ref = write('reverse/episode.json', reverse)
    inherited.update({key: value for key, value in reverse.items() if key.startswith('reverse')})
    operation = trial('operation', 'bags_swap_restored', tm(1210), tm(1212), **common, source=reverse_ref,
        after_resources=native_resources, after_saved=baseline['2']['saved'], inventory_restored=True,
        actionbar_restored=True, state=state, public=entry['public'], native_state=native_state,
        snapshot=online, frame=frame('operation'), cursor_cancellations=[], **inherited,
        layout_restoration_checks=dict.fromkeys(e.shared.LAYOUT_CHECKS, True))
    operation_ref = write('operation/episode.json', operation)
    final = deepcopy(baseline)
    final['2']['native'].update(rest_bonus=text, logout_time=tm(1216),
        totaltime=baseline['2']['native']['totaltime'] + 20, leveltime=baseline['2']['native']['leveltime'] + 20)
    whole = c.packet_rows(wire, 'scout', tm(1199), tm(1215.1))
    park = trial('park', 'bags_swap_parked', tm(1214), tm(1217), **common, source=operation_ref,
        all_offline_snapshot=final, logout_started_at=tm(1214.9), logout_finished_at=tm(1216.9),
        logout_packets=logout, pre_logout_native_state=native_state, raw_native_logout_history=whole,
        native_logout_proof=replay, checks=dict.fromkeys(e.shared.PARK_CHECKS, True), frame=frame('park'))
    if indexed is not None:
        park['raw_native_logout_events'] = [row for row in full_events if tm(1199) <= row['time'] <= tm(1215.1)]
    park_ref = write('park/episode.json', park)
    after = trial('after_precision', 'bags_swap_rest_precision_complete', tm(1220), tm(1221),
        source=park_ref, before=final, after=final, query=preservation.PRECISION_QUERY,
        row=precise(final['2']['native'], exact_after), rest_sources=binding,
        checks=dict.fromkeys(e.shared.PRECISION_CHECKS, True))
    after_ref = write('after_precision/episode.json', after)
    refs = {'preparation': ready_ref, 'entry': entry_ref, 'operation': operation_ref, 'park': park_ref,
        'before_precision': before_ref, 'after_precision': after_ref}
    store = e.Sources(data, digests, paths=paths)
    store.raw_journals = carried.raw_journals
    result, restored, _ = e.lifecycle(store, refs)
    assert restored == final
    if indexed is None: assert publication.validate_carry(store, ready)
    final_review_ref = write('final_review/review.json', {'reviewed': True, 'control': 'Harnesstwo',
        'source': park_ref, 'frame': park['frame'], 'selected_character': 'Harnesstwo', 'selected_level': 1})
    closure = trial('final', e.PHASE, tm(1225), tm(1226), sources=refs, proof=result,
        before=final, after=final, all_offline_snapshot=final, authority_source=ready['authority_source'],
        primary_stop_source=ready['predecessor']['primary_stop'], shutdown_checks=dict.fromkeys(e.shared.SHUTDOWN_CHECKS, True),
        action='stop_parked_scout_after_bag_swap_roundtrip', stop_attempted=True,
        game_before={'pid': 51 if authority else 31, 'start_ticks': '5100' if authority else '3100'}, screen_review={**final_review_ref, 'frame': park['frame']},
        frame=frame('final'))
    closure_ref = write('final/episode.json', closure)
    # Current source-owned journals start at ready.started_at; the prior realm
    # authentication is retained in ready but lies outside that archive window.
    events = full_events if indexed is not None else complete_events()
    journal_refs = {}
    raw_journals = dict(carried.raw_journals)
    for kind, rows in (('packets', wire), ('events', events)):
        member = str(batch.relative_to(root)) + '/journals/' + kind + '.jsonl'
        raw = b''.join((json.dumps(row) + '\n').encode() for row in rows)
        files[member], digests[member], raw_journals[member] = raw, hashlib.sha256(raw).hexdigest(), rows
        journal_refs[kind] = {'path': str(root / member), 'sha256': digests[member]}
    write('journal_receipt.json', {'schema': 'client442_bag_swap_journals_v1', 'closure_source': closure_ref,
        'journal_sources': journal_refs})
    tracking = e.tracking_state()
    tracking.update(digests=digests, raw_journals=raw_journals, paths=paths)
    for member, rows in zip(e.TRACKING_MEMBERS, (wire, events)):
        e.collect(member, rows, data, tracking)
        files[member] = b''.join((json.dumps(row) + '\n').encode() for row in rows)
    return data, digests, tracking, files, result, str(batch.relative_to(root)) + '/'


def test_producer_shaped_lifecycle_and_full_actual_tar_prove_the_same_closed_swap(tmp_path, monkeypatch):
    data, digests, tracking, files, lifecycle, prefix = complete_fixture(tmp_path, monkeypatch)
    expected = e.proof(data, digests, tracking)
    assert expected['native_swap_pairs'] == lifecycle['native_swap_pairs'] == 2
    assert expected['shutdown_checks'] == 8 and expected['actual_packet_journals_verified'] is True
    assert expected['inventory_restored'] is True and expected['all_six_offline'] is True
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for member, raw in files.items():
            info = tarfile.TarInfo(member)
            info.size = len(raw)
            archive.addfile(info, io.BytesIO(raw))
    raw = stream.getvalue()
    checkpoint = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(),
        'file_manifest': [{'path': member, 'bytes': len(body), 'sha256': hashlib.sha256(body).hexdigest()}
            for member, body in files.items() if member.startswith(prefix)]}
    archived, hashes, actual, count = reviewer.inspect_archive(io.BytesIO(raw), checkpoint, prefix)
    assert count == len(raw)
    assert e.proof(archived, hashes, actual) == expected


def rebound_current_receipts(data, digests, tracking, files, prefix, mutate):
    """Rebind actual changed JSON bytes and all subsequent immutable references."""
    data, digests, tracking, files = deepcopy(data), dict(digests), deepcopy(tracking), dict(files)
    mutate(data)
    current = {member for member in data if member.startswith(prefix) and '/predecessor/' not in member}
    def replacements(value, hashes):
        if type(value) is dict:
            if value.get('path') in hashes and 'sha256' in value:
                value['sha256'] = hashes[value['path']]
            for child in value.values():
                replacements(child, hashes)
        elif type(value) is list:
            for child in value:
                replacements(child, hashes)
    for _ in range(24):
        raws = {member: (json.dumps(data[member], indent=2) + '\n').encode() for member in current}
        hashes = {str(e.lab.ROOT / member): hashlib.sha256(raw).hexdigest() for member, raw in raws.items()}
        before = deepcopy({member: data[member] for member in current})
        for member in current:
            replacements(data[member], hashes)
        if before == {member: data[member] for member in current}:
            break
    else:
        raise AssertionError('current fixture reference graph did not converge')
    for member, raw in raws.items():
        files[member], digests[member] = raw, hashlib.sha256(raw).hexdigest()
    tracking['digests'] = digests
    return data, digests, tracking, files


@pytest.mark.parametrize('fault', ['native_session', 'controller', 'model', 'custom_script_permission',
    'qualification_added', 'missing_restored_cursor', 'occupied_restored_cursor', 'leading_zero_ticks', 'unicode_ticks'])
def test_full_proof_rejects_rebound_chain_labels_cursor_and_noncanonical_child_identity(tmp_path, monkeypatch, fault):
    data, digests, tracking, files, _, prefix = complete_fixture(tmp_path, monkeypatch)
    def mutate(changed):
        if fault in ('missing_restored_cursor', 'occupied_restored_cursor'):
            operation = next(v for v in changed.values() if v.get('phase') == 'bags_swap_restored')
            if fault == 'missing_restored_cursor':
                operation['state'].pop('cursor_info')
            else:
                operation['state']['cursor_info'] = ['item', 6948]
        elif fault in ('leading_zero_ticks', 'unicode_ticks'):
            closure = next(v for v in changed.values() if v.get('phase') == e.PHASE)
            closure['game_before']['start_ticks'] = '02300' if fault == 'leading_zero_ticks' else '٢٣٠٠'
        else:
            forward = next(v for v in changed.values() if v.get('phase') == 'bags_swap_forward')
            forward[fault] = {'native_session': 'foreign', 'controller': 'model', 'model': 'non-null',
                'custom_script_permission': 'allowed', 'qualification_added': True}[fault]
    changed, hashes, actual, _ = rebound_current_receipts(data, digests, tracking, files, prefix, mutate)
    with pytest.raises(RuntimeError, match='source chain|original layout|physical child'):
        e.proof(changed, hashes, actual)


def test_full_proof_accepts_actual_observer_empty_dictionary_cursor(tmp_path, monkeypatch):
    data, digests, tracking, files, _, prefix = complete_fixture(tmp_path, monkeypatch)
    expected = e.proof(data, digests, tracking)
    def mutate(changed):
        operation = next(v for v in changed.values() if v.get('phase') == 'bags_swap_restored')
        operation['state']['cursor_info'] = {}
    changed, hashes, actual, _ = rebound_current_receipts(data, digests, tracking, files, prefix, mutate)
    assert e.proof(changed, hashes, actual) == expected



def test_complete_fake_fixture_executes_initialize_before_any_preparation(tmp_path, monkeypatch):
    from tools.client_compatibility import checkpoint_interactions as initializer
    calls = []
    ordinary = initializer.initialize
    def observed(directory):
        calls.append(directory)
        return ordinary(directory)
    monkeypatch.setattr(initializer, 'initialize', observed)
    data, digests, _, files, _, prefix = complete_fixture(tmp_path, monkeypatch)
    assert len(calls) == 1 and 'fake_initialization_lab' in str(calls[0])
    original = (calls[0] / 'batch.json').read_bytes()
    assert files[prefix + 'batch.json'] == original
    batch = data[prefix + 'batch.json']
    native = data[prefix + 'native_server_before.json']
    ready = data[prefix + 'ready/episode.json']
    assert batch['native_worldserver'] == native == ready['runtime']['worldserver']
    assert batch['code_commit'] == ready['code_commit']
    assert batch['started_at'] < ready['started_at']
    assert digests[prefix + 'batch.json'] == hashlib.sha256(original).hexdigest()

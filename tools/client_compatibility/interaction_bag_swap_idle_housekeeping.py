"""Excluded, once-only ordinary cleanup of the failed entry's automatic idle pose.

Capture is read-only. Restore accepts the exact source-owned capture review,
then consumes each required standing/AFK input before submitting it. This helper
does not log in, touch bags, qualify an interaction, or change the failed entry.
"""
import argparse
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

from . import lab_runtime as lab
from .item_actionbar_contract import INDEX, body, finite, records, require, strict_equal
from .world.buffer import Reader

C1 = 'e9a37f0666b911e47596443fa7850b48aa9797c5'
FAILED_SHA = 'cb64cec0472f9a23d176fbf1e98710aee72b0c195f03ca62b60355f7d994213f'
FAILED_IMAGE_SHA = '322ad4584ddaffe7cf6c43ba54bebaa9c39b8fef20bd10b8e01553e1dfe7c76f'
INITIAL_FACTS_SHA = '707b10512dbdb0fd1645ef4ad90f5c7ff6e3ca4a1357dee3c9b30b487b2caa62'
SCHEMA = 'client442_bag_swap_excluded_idle_housekeeping_v1'
OWN_FILES = ('tools/client_compatibility/interaction_bag_swap_idle_housekeeping.py',
    'tools/client_compatibility/world/tests/test_bag_swap_idle_housekeeping.py')
DEPENDENCIES = ('tools/client_compatibility/interaction_item_actionbar.py',
    'tools/client_compatibility/interaction_trial.py',
    'tools/client_compatibility/interaction_item_actionbar_parked_selection_capture.py',
    'tools/client_compatibility/item_actionbar_contract.py',
    'tools/client_compatibility/world/buffer.py', 'tools/client_compatibility/world/native_objects.py',
    'tools/client_compatibility/world/native_fields.json',
    'tools/client_compatibility/native_bridge/chat.cpp',
    'tools/client_compatibility/native_bridge/client_requests.cpp',
    'tools/client_compatibility/observation/interactions.py')
ROUTINE = frozenset(('CMSG_TIME_SYNC_RESPONSE', 'CMSG_TIME_SYNC_RESP',
    'CMSG_SERVER_TIME_OFFSET_REQUEST', 'CMSG_QUEST_GIVER_STATUS_QUERY'))
IGNORED_QUERIES = {'CMSG_TUTORIAL': 5, 'CMSG_GM_TICKET_GET_CASE_STATUS': 0,
    'CMSG_GET_ACCOUNT_NOTIFICATIONS': 0}
ORIGINAL = {'pose': {'stand': 0, 'sheath': 0}, 'afk': False, 'selection': 0,
    'health': 60, 'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0}


def bound(path):
    path = Path(path)
    require(path.is_absolute() and path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
        'ordinary source-owned file required')
    with path.open('rb') as handle:
        digest = hashlib.file_digest(handle, 'sha256').hexdigest()
    return {'path': str(path), 'sha256': digest}


def key(row):
    return json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)


def stand_chain(rows, wanted):
    relevant = [r for r in rows if r.get('name') in ('CMSG_STAND_STATE_CHANGE',
        'CMSG_STANDSTATECHANGE', 'SMSG_STAND_STATE_UPDATE')]
    expected = [('CMSG_STAND_STATE_CHANGE', 'from_client', bytes([wanted])),
        ('CMSG_STANDSTATECHANGE', 'to_native', wanted.to_bytes(4, 'little')),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', bytes([wanted])),
        ('SMSG_STAND_STATE_UPDATE', 'to_client', bytes([wanted]) + bytes(4))]
    found = [[r for r in relevant if (r.get('name'), r.get('direction'), body(r)) == shape] for shape in expected]
    require(len(relevant) == 4 and all(len(v) == 1 for v in found), 'one exact sit/stand quartet required')
    result = [v[0] for v in found]
    require(all(finite(r.get('time')) for r in result) and
        all(a['time'] < b['time'] for a, b in zip(result, result[1:])) and
        result[-1]['time'] - result[0]['time'] < 2, 'sit/stand quartet chronology differs')
    return result


def owner_pose_updates(rows):
    found = []
    for row in rows:
        if (row.get('name'), row.get('direction')) == ('SMSG_UPDATE_OBJECT', 'from_native'):
            for record in records(body(row)):
                fields = record.get('fields', {})
                selected = {str(k): fields[k] for k in (INDEX['UNIT_FIELD_BYTES_1'], INDEX['PLAYER_FLAGS']) if k in fields}
                if record.get('guid') == 2 and selected:
                    require(record['update_type'] == 0, 'idle history cannot recreate the owner')
                    found.append({'packet': row, 'fields': selected})
    return found


def original_objects(rows):
    owned = (2, (0x4000 << 48) | 41, (0x4000 << 48) | 33)
    objects, creations = {}, []
    for row in rows:
        if (row.get('name'), row.get('direction')) != ('SMSG_UPDATE_OBJECT', 'from_native'):
            continue
        for record in records(body(row)):
            if record['update_type'] == 3:
                require(not set(record['removed']) & set(owned), 'original entry removed its owned object')
                continue
            identity = record.get('guid')
            if identity not in owned:
                continue
            require(record['update_type'] != 3, 'original entry removed its owned object')
            if record['update_type'] in (1, 2):
                require(identity not in objects, 'original entry recreated its owned object')
                creations.append(identity)
                objects[identity] = {}
            require(identity in objects, 'original entry updated an uncreated owned object')
            objects[identity].update(record.get('fields', {}))
    require(creations.count(2) == 1, 'exact native original owner creation required')
    return {str(guid): {str(k): v for k, v in fields.items()} for guid, fields in objects.items()}


def native_history(rows, original):
    objects = deepcopy(original)
    require(type(objects) is dict and '2' in objects, 'complete original owned native fields required')
    for row in rows:
        if (row.get('name'), row.get('direction')) == ('SMSG_DESTROY_OBJECT', 'from_native'):
            raw = body(row)
            require(len(raw) == 9 and str(int.from_bytes(raw[:8], 'little')) not in objects,
                'idle gap destroyed its owner/items')
            continue
        if (row.get('name'), row.get('direction')) != ('SMSG_UPDATE_OBJECT', 'from_native'):
            continue
        for record in records(body(row)):
            if record['update_type'] == 3:
                require(not {str(guid) for guid in record['removed']} & set(objects), 'idle gap removed its owner/items')
                continue
            identity = str(record.get('guid'))
            if identity not in objects:
                continue
            require(record['update_type'] == 0, 'idle gap cannot recreate or remove its owner/items')
            for index, value in record.get('fields', {}).items():
                field = str(index)
                old = objects[identity].get(field, 0)
                permitted = identity == '2' and index in (INDEX['UNIT_FIELD_BYTES_1'], INDEX['PLAYER_FLAGS'])
                require(value == old or permitted, 'idle gap changed another complete native owner/item field')
                if permitted:
                    require(type(value) is int and value in ((0, 1) if index == INDEX['UNIT_FIELD_BYTES_1'] else (0, 2)),
                        'idle gap introduced unsupported pose or player flags')
                objects[identity][field] = value
    return objects


def metadata(rows, events, session, physical):
    result, used = [], set()
    for packet in sorted(rows, key=lambda r: r['time']):
        expected = session if packet['direction'] in ('to_native', 'from_native') or (
            packet['name'] == 'SMSG_STAND_STATE_UPDATE' and packet['direction'] == 'to_client') else physical
        found = [i for i, r in enumerate(events) if i not in used and r.get('session') == expected and
            r.get('event') == ('native_packet' if packet['direction'] in ('to_native', 'from_native') else 'modern_packet') and
            r.get('name') == packet['name'] and r.get('direction') == packet['direction'] and
            type(r.get('bytes')) is int and r['bytes'] == len(body(packet)) and finite(r.get('time')) and
            0 <= packet['time'] - r['time'] < .1]
        require(len(found) == 1, 'idle packets require unique physical/native metadata')
        used.add(found[0]); result.append(events[found[0]])
    return result


def clean_requests(rows, allowed):
    from .item_actionbar_contract import FORBIDDEN
    permit = {key(r) for r in allowed}
    for row in rows:
        if row.get('direction') not in ('from_client', 'to_native'):
            require(row.get('name') != 'SMSG_INVENTORY_CHANGE_FAILURE', 'idle gap inventory failure')
            continue
        require(key(row) in permit or row.get('name') in ROUTINE,
            'excluded idle gap refuses any additional client/native request')
        require(key(row) in permit or row.get('name') not in FORBIDDEN, 'excluded idle gameplay mutation')


def ignored_queries(events, owner):
    found = []
    for name, size in IGNORED_QUERIES.items():
        rows = sorted([r for r in events if r.get('name') == name], key=lambda r: r.get('time', 0))
        if not rows:
            continue
        require(len(rows) % 2 == 0 and len({key(r) for r in rows}) == len(rows),
            'each observed idle query occurrence must be distinct and paired')
        for incoming, dropped in zip(rows[::2], rows[1::2]):
            require([(r.get('event'), r.get('session'), r.get('bytes')) for r in (incoming, dropped)] ==
                [('modern_packet', owner, size), ('unmapped_client_packet', owner, size)] and
                incoming.get('direction') == 'from_client' and 'direction' not in dropped and
                all(type(r.get('bytes')) is int and finite(r.get('time')) for r in (incoming, dropped)) and
                0 <= dropped['time'] - incoming['time'] < .1,
                'observed idle query must be its unique metadata-only ignored owner pair')
        found += rows
    return found


def ping_metadata(events, owner, physical):
    """Bind the two observed latency streams without treating them as input."""
    rows = [r for r in events if r.get('name') == 'CMSG_PING']
    require(all(type(r.get('bytes')) is int and r['bytes'] == 8 and finite(r.get('time')) and
        (r.get('session'), r.get('event'), r.get('direction')) in
        ((physical, 'modern_packet', 'from_client'), (owner, 'modern_packet', 'from_client'),
         (owner, 'native_packet', 'to_native')) for r in rows), 'latency metadata shape differs')
    incoming = [r for r in rows if r.get('session') == owner and r.get('direction') == 'from_client']
    outgoing = [r for r in rows if r.get('direction') == 'to_native']
    require(len(incoming) == len(outgoing) and all(0 <= b['time'] - a['time'] < .1
        for a, b in zip(incoming, outgoing)) and len({key(r) for r in rows}) == len(rows),
        'owner latency metadata requires its unique ordinary native pair')
    return rows


def automatic_idle(rows, events, session, physical, since, until, *, original):
    require(finite(since) and finite(until) and since < until, 'honest failed-entry idle gap required')
    scoped = [r for r in rows if r.get('session') == session and since < r.get('time', 0) <= until]
    complete_native = native_history(scoped, original)
    quartet = stand_chain(scoped, 1)
    updates = owner_pose_updates(scoped)
    require(len(updates) == 1 and updates[0]['fields'] == {str(INDEX['UNIT_FIELD_BYTES_1']): 1,
        str(INDEX['PLAYER_FLAGS']): 2} and quartet[-1]['time'] <= updates[0]['packet']['time'] < quartet[-1]['time'] + 2,
        'automatic idle requires its sole seated/AFK native sparse effect')
    clean_requests(scoped, quartet[:2])
    scoped_events = [r for r in events if r.get('session') in (session, physical) and since < r.get('time', 0) <= until]
    require(not any(r.get('event') in ('native_player_created', 'world_connection_closed', 'native_stream_closed')
        for r in scoped_events), 'idle gap session was recreated or closed')
    matched = metadata([*quartet, updates[0]['packet']], scoped_events, session, physical)
    # Chat bodies are deliberately absent from the packet journal. The retained
    # bridge events still bind its name, byte length, owner and native forwarding.
    afk = [r for r in scoped_events if r.get('name') in ('CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK')]
    require(len(afk) == 2 and [(r.get('event'), r.get('name'), r.get('direction'), r.get('session'), r.get('bytes'))
        for r in afk] == [('modern_packet', 'CMSG_CHAT_MESSAGE_AFK', 'from_client', session, 5),
        ('native_packet', 'CMSG_MESSAGECHAT_AFK', 'to_native', session, 5)] and
        quartet[1]['time'] <= afk[0]['time'] < afk[1]['time'] <= updates[0]['packet']['time'] and
        afk[1]['time'] - afk[0]['time'] < .1,
        'automatic AFK must bind its actual metadata-only owner request pair')
    requests = [r for r in scoped_events if r.get('direction') in ('from_client', 'to_native')]
    ignored = ignored_queries(scoped_events, session)
    pings = ping_metadata(scoped_events, session, physical)
    permitted = {key(r) for r in matched + afk + ignored + pings}
    require(all(key(r) in permitted or r.get('name') in ROUTINE for r in requests),
        'automatic idle metadata contains another input')
    return {'session': session, 'instance_session': physical, 'since': since, 'until': until,
        'automatic_stand_packets': quartet, 'automatic_owner_update': updates[0], 'metadata': matched,
        'afk_metadata': afk, 'afk_body_retained': False, 'ignored_query_metadata': ignored,
        'ignored_query_bodies_retained': False,
        'latency_metadata': pings, 'latency_bodies_retained': False,
        'original_native_objects': original, 'ending_native_objects': complete_native,
        'source_packets': scoped, 'source_events': scoped_events}


def code_sources():
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=lab.REPO, text=True).strip()
    result = []
    for name in OWN_FILES + DEPENDENCIES:
        raw = subprocess.check_output(['git', 'show', commit + ':' + name], cwd=lab.REPO)
        require((lab.REPO / name).read_bytes() == raw, 'idle helper dependencies must match committed HEAD')
        result.append({'path': str(lab.REPO / name), 'sha256': hashlib.sha256(raw).hexdigest(),
            'bytes': len(raw), 'raw_hex': raw.hex()})
    return commit, result


def runtime_helpers():
    from . import interaction_item_actionbar as op
    return op


def journals():
    from .observation.journal import entries
    return list(entries(lab.ROOT / 'evidence/world_packets.jsonl')), list(entries(lab.ROOT / 'logs/modern_world.jsonl'))


def authority(t, preparation, failure):
    op = runtime_helpers()
    ready, failed = op.closed(preparation), op.closed(failure, False)
    require(bound(failure)['sha256'] == FAILED_SHA and ready.get('code_commit') == failed.get('code_commit') == C1 and
        failed.get('phase') == 'bags_swap_entry_started' and ready.get('phase') == 'bags_swap_scout_ready' and
        failed.get('preparation_source') == bound(preparation) and
        ready.get('actor') == failed.get('actor') == t.fixture and ready.get('runtime') == failed.get('runtime') == t.receipt['runtime'] and
        ready.get('native_session') == failed.get('native_session') and failed['finished_at'] < t.receipt['started_at'],
        'exact immutable failed C1 entry and same original owned session required')
    from . import actors
    require(actors.load() == t.fixture and actors.session_entry(t.fixture)['session'] == ready['native_session'],
        'idle housekeeping cannot change registration or replay login')
    originals = [r for row in failed['raw_entry_packets'] if row.get('name') == 'SMSG_UPDATE_OBJECT' and
        row.get('direction') == 'from_native' for r in records(body(row)) if r.get('guid') == 2 and r['update_type'] in (1, 2)]
    require(len(originals) == 1 and originals[0]['fields'].get(INDEX['UNIT_FIELD_BYTES_1'], 0) == 0 and
        originals[0]['fields'].get(INDEX['UNIT_FIELD_BYTES_2'], 0) == 0 and
        originals[0]['fields'].get(INDEX['PLAYER_FLAGS'], 0) == 0,
        'actual original login must prove standing, unsheathed and non-AFK')
    from .interaction_item_actionbar_parked_selection_capture import game_identity
    from .owned_input import focus
    game_identity(focus(), ready['frame'])
    commit, source_bytes = code_sources()
    t.receipt.update(schema=SCHEMA, phase='bags_swap_idle_housekeeping_started', code_commit=commit,
        committed_source_bytes=source_bytes, preparation_source=bound(preparation), original_entry_source=bound(failure),
        native_session=ready['native_session'], qualification_added=False, excluded_housekeeping=True,
        first_failure_excluded=True, input_sent=False, mutation_sent=False, ordinary_inputs=[])
    original_image = Path(failure).parent / 'bags_swap_entered.png'
    require(bound(original_image)['sha256'] == FAILED_IMAGE_SHA,
        'the actual failed entry observation PNG must retain its immutable bytes')
    from PIL import Image
    from .observation.interactions import decode_image
    with Image.open(original_image) as image:
        original_state = decode_image(image)
    require(original_state.get('guid') == t.guid and original_state.get('player') == 'Harnesstwo',
        'original failed capture belongs to another actor')
    t.receipt.update(original_failed_image=bound(original_image),
        original_world_position=original_state['world_position'], original_native_objects=original_objects(failed['raw_entry_packets']))
    facts_path = Path(failure).parent.parent / 'entry_failure_readonly01/facts.json'
    require(bound(facts_path)['sha256'] == INITIAL_FACTS_SHA, 'actual initial read-only resource source bytes changed')
    initial = json.loads(facts_path.read_text())
    require(initial.get('entry_source') == bound(failure) and initial.get('actor') == t.fixture and
        initial.get('runtime') == t.receipt['runtime'] and initial.get('session') == ready['native_session'] and
        initial.get('input_sent') is False and initial.get('mutation_sent') is False and
        initial.get('before') == ready['all_offline_snapshot'] and strict_equal(initial.get('native_state'), ORIGINAL) and
        failed['finished_at'] < initial['observed_at'] < t.receipt['started_at'] and
        all(initial['after'][g] == initial['before'][g] for g in ('1', '3', '4', '5', '6')) and
        initial['after']['2']['saved'] == initial['before']['2']['saved'] and
        initial['after']['2']['inventory'] == initial['before']['2']['inventory'] and initial['after']['2']['pets'] == [] and
        initial['after']['2']['native']['online'] == 1 and
        {k for k in initial['before']['2']['native'] if initial['before']['2']['native'][k] != initial['after']['2']['native'][k]} <=
        {'online', 'rest_bonus', 'totaltime', 'leveltime', 'logout_time', 'latency'},
        'initial resource authority must remain the honest post-failure read-only observation')
    t.receipt.update(original_resources_source=bound(facts_path), original_resources=initial['resources'])
    t.persist()
    return ready, failed


def facts(t, ready, label):
    op, session = runtime_helpers(), ready['native_session']
    snapshot, native = op.snapshot(), op.native_state(session)
    baseline = ready['all_offline_snapshot']
    require(all(snapshot[g] == baseline[g] for g in ('1', '3', '4', '5', '6')) and
        snapshot['2']['inventory'] == baseline['2']['inventory'] and snapshot['2']['saved'] == baseline['2']['saved'] and
        snapshot['2']['pets'] == [] and snapshot['2']['native']['online'] == 1 and
        {k for k in baseline['2']['native'] if snapshot['2']['native'][k] != baseline['2']['native'][k]} <=
        {'online', 'rest_bonus', 'totaltime', 'leveltime', 'logout_time', 'latency'},
        'idle housekeeping changed complete protected/saved inventory or owner state')
    require(strict_equal({k: v for k, v in native.items() if k not in ('pose', 'afk')},
        {k: v for k, v in ORIGINAL.items() if k not in ('pose', 'afk')}) and
        type(native.get('afk')) is bool and type(native['pose'].get('stand')) is int and
        type(native['pose'].get('sheath')) is int and native['pose']['sheath'] == 0,
        'idle housekeeping refuses health/power/target/summon/sheath differences')
    state, frame = t.observe(label)
    from .interaction_item_actionbar_parked_selection_capture import frame_identity
    frame_identity(frame, t.receipt['runtime'], ready['frame'])
    require(state.get('player') == 'Harnesstwo' and state.get('guid') == t.guid and
        type(state.get('level')) is int and state['level'] == 1 and
        strict_equal(state.get('world_position'), t.receipt['original_world_position']) and
        'cursor_info' in state and (state['cursor_info'] is False or state['cursor_info'] is None or
            type(state['cursor_info']) in (list, dict) and len(state['cursor_info']) == 0) and
        not any(state.get(k) for k in ('bags', 'panels', 'spell_targeting', 'lua_errors', 'blocked_actions')) and
        frame['movement'].get('speed') == 0 and all(frame['movement'].get(k) is False for k in ('dead', 'in_combat', 'on_taxi')),
        'fresh owned idle capture position/UI differs')
    public = op.detail(t, label + '_bars')
    from .item_actionbar_contract import public_assignments
    public_assignments(public, baseline['2']['saved']['actions'], baseline['2']['native']['activeTalentGroup'])
    native_resources = op.resources(session)
    from .item_actionbar_contract import item_resources
    item_resources(native_resources)
    destination = native_resources['backpack'][1]
    require(all(type(destination.get(k)) is int and destination[k] == v for k, v in
        {'guid': (0x4000 << 48) | 33, 'id': 58231, 'count': 1}.items()), 'occupied destination native GUID differs')
    require(strict_equal(native_resources, t.receipt['original_resources']), 'complete original native equipment/bags/resources changed')
    return {'observed_at': time.time(), 'snapshot': snapshot, 'native_state': native,
        'resources': native_resources, 'state': state, 'frame': frame, 'public': public}


def capture(t, preparation, failure, prior_path=None):
    ready, failed = authority(t, preparation, failure)
    found = facts(t, ready, 'idle_before')
    require(found['native_state'] == {**ORIGINAL, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True},
        'capture requires exact automatic seated/AFK mismatch')
    rows, events = journals()
    instances = [r for r in events if r.get('event') == 'instance_authenticated' and r.get('account_id') == 2 and
        failed['started_at'] <= r.get('time', 0) <= failed['finished_at']]
    require(len(instances) == 1, 'sole original physical login required')
    since = failed['finished_at']
    if prior_path is not None:
        prior = runtime_helpers().closed(prior_path)
        require(prior.get('schema') == SCHEMA and prior.get('phase') == 'bags_swap_idle_housekeeping_restored' and
            prior.get('original_entry_source') == bound(failure) and prior.get('preparation_source') == bound(preparation) and
            prior.get('runtime') == t.receipt['runtime'] and prior.get('after', {}).get('native_state') == ORIGINAL and
            prior['finished_at'] < t.receipt['started_at'] and
            prior.get('committed_source_bytes') == t.receipt['committed_source_bytes'],
            'a new idle cycle needs its exact prior successful excluded cleanup')
        since = prior['finished_at']
        t.receipt['prior_housekeeping_source'] = bound(prior_path)
    gap = automatic_idle(rows, events, ready['native_session'], instances[0]['session'], since, found['observed_at'],
        original=t.receipt['original_native_objects'])
    t.receipt.update(before=found, frame=found['frame'], automatic_idle=gap, completed=True,
        phase='bags_swap_idle_housekeeping_captured')


def consume(t, failed, kind, intent):
    cycle = {'original_entry_source': failed, 'automatic_stand_packets': t.receipt['automatic_idle']['automatic_stand_packets'],
        'automatic_owner_update': t.receipt['automatic_idle']['automatic_owner_update']}
    cycle_sha = hashlib.sha256(key(cycle).encode()).hexdigest()
    marker = Path(failed['path']).parent / ('bag_swap_idle_' + cycle_sha + '_' + kind + '_attempt.json')
    value = {'schema': 'client442_bag_swap_idle_consumed_input_v1', 'kind': kind, 'created_at': time.time(),
        'original_entry_source': failed, 'cycle_sha256': cycle_sha, 'capture_source': t.receipt['capture_source'],
        'operation_output': str(t.out / 'episode.json'), 'input_intent': intent, 'input_replay_allowed': False}
    directory = os.open(marker.parent, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        descriptor = os.open(marker.name, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=directory)
        with os.fdopen(descriptor, 'wb') as handle:
            handle.write((json.dumps(value, indent=2) + '\n').encode()); handle.flush(); os.fsync(handle.fileno())
        os.fsync(directory)
    finally:
        os.close(directory)
    t.receipt[kind + '_attempt_source'] = bound(marker)
    t.persist()


def cleanup_history(old, rows, events, inputs, until):
    """Bind only retained idle requests and exact consumed restoration effects."""
    gap = old['automatic_idle']
    owner, physical = gap['session'], gap['instance_session']
    scoped = [r for r in rows if r.get('session') == owner and gap['since'] < r.get('time', 0) <= until]
    complete_native = native_history(scoped, gap['original_native_objects'])
    relevant = [r for r in events if r.get('session') in (owner, physical) and gap['since'] < r.get('time', 0) <= until]
    require(type(inputs) is list and 1 <= len(inputs) <= 2 and
        [r.get('kind') for r in inputs] == ['stand', 'afk'][:len(inputs)] and
        all(r.get('input_replayed') is False and finite(r.get('started_at')) and finite(r.get('finished_at')) and
            r['started_at'] < r['finished_at'] <= until for r in inputs), 'one stand and at most one necessary AFK cleanup required')
    stand = inputs[0]
    restore_rows = [r for r in scoped if stand['started_at'] <= r['time'] <= until]
    restored = stand_chain(restore_rows, 0)
    require(restored[-1]['time'] <= stand['finished_at'] and
        stand['preflight']['native_state'] == {**ORIGINAL, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True},
        'standing cleanup must follow its observed seated/AFK preflight')
    clean_requests(scoped, gap['automatic_stand_packets'][:2] + restored[:2])
    matched = metadata(restored, relevant, owner, physical)
    later_afk = [r for r in relevant if r.get('name') in ('CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK') and
        r['time'] > gap['until']]
    if len(inputs) == 1:
        require(later_afk == [], 'unneeded AFK cleanup was submitted')
    else:
        afk = inputs[1]
        require(afk['input'] == {'kind': 'chat', 'value': '/afk'} and
            afk['preflight']['native_state'] == {**ORIGINAL, 'afk': True} and len(later_afk) == 2 and
            [(r.get('event'), r.get('name'), r.get('direction'), r.get('session')) for r in later_afk] ==
            [('modern_packet', 'CMSG_CHAT_MESSAGE_AFK', 'from_client', owner),
             ('native_packet', 'CMSG_MESSAGECHAT_AFK', 'to_native', owner)] and
            all(type(r.get('bytes')) is int and 2 <= r['bytes'] <= 513 for r in later_afk) and
            afk['started_at'] <= later_afk[0]['time'] < later_afk[1]['time'] <= afk['finished_at'] and
            later_afk[1]['time'] - later_afk[0]['time'] < .1, 'conditional AFK cleanup metadata differs')
    ignored = ignored_queries(relevant, owner)
    pings = ping_metadata(relevant, owner, physical)
    permitted = {key(r) for r in gap['metadata'] + gap['afk_metadata'] + matched + later_afk + ignored + pings}
    require(all(key(r) in permitted or r.get('name') in ROUTINE for r in relevant if
        r.get('direction') in ('from_client', 'to_native')), 'excluded cleanup metadata contains another input')
    require(not any(r.get('event') in ('native_player_created', 'world_connection_closed', 'native_stream_closed')
        for r in relevant), 'excluded cleanup lost its original login session')
    updates = owner_pose_updates(scoped)
    require(updates and updates[0] == gap['automatic_owner_update'], 'original idle sparse effect changed')
    pose, afk = 0, 0
    for update in updates:
        fields = update['fields']
        if str(INDEX['UNIT_FIELD_BYTES_1']) in fields:
            pose = fields[str(INDEX['UNIT_FIELD_BYTES_1'])]
            require(pose in (0, 1), 'excluded cleanup introduced another pose')
        if str(INDEX['PLAYER_FLAGS']) in fields:
            afk = fields[str(INDEX['PLAYER_FLAGS'])]
            require(afk in (0, 2), 'excluded cleanup introduced other player flags')
    require(pose == afk == 0 and updates[-1]['packet']['time'] >= restored[1]['time'],
        'native sparse effects must actually restore original standing/non-AFK')
    return {'restored_stand_packets': restored, 'restored_afk_metadata': later_afk,
        'owner_pose_updates': updates, 'metadata': matched, 'afk_body_retained': False,
        'ignored_query_metadata': ignored, 'ending_native_objects': complete_native, 'latency_metadata': pings}


def reviewed_capture(t, capture_path, review_path, old):
    require(Path(review_path).is_relative_to(lab.ROOT / 'evidence'), 'private source-owned idle review required')
    review_ref = bound(review_path)
    checked = json.loads(Path(review_path).read_text())
    image = old.get('frame', {})
    name = image.get('file')
    require(type(name) is str and Path(name).name == name and name.endswith('.png'),
        'ordinary reviewed source PNG name required')
    original = Path(capture_path).parent / name
    copied = Path(review_path).parent / name
    now = time.time()
    require(bound(original)['sha256'] == image.get('sha256') and bound(copied)['sha256'] == image.get('sha256') and
        0 <= now - original.stat().st_mtime < 120 and 0 <= now - copied.stat().st_mtime < 120 and
        checked.get('reviewed') is True and checked.get('control') == 'bags.swap_item.idle_housekeeping' and
        checked.get('source') == bound(capture_path) and checked.get('frame') == image and
        checked.get('ordinary_stand_afk_only') is True and bound(review_path) == review_ref,
        'fresh source-owned idle PNG review differs')
    return checked


def restore(t, preparation, failure, capture_path, review_path):
    ready, failed = authority(t, preparation, failure)
    op = runtime_helpers()
    capture_ref = bound(capture_path)
    old = op.closed(capture_path)
    require(bound(capture_path) == capture_ref, 'idle capture bytes changed during the source read')
    checked = reviewed_capture(t, capture_path, review_path, old)
    require(old.get('schema') == SCHEMA and old.get('phase') == 'bags_swap_idle_housekeeping_captured' and
        old.get('original_entry_source') == bound(failure) and old.get('preparation_source') == bound(preparation) and
        old.get('runtime') == t.receipt['runtime'] and old.get('code_commit') == t.receipt['code_commit'] and
        old.get('committed_source_bytes') == t.receipt['committed_source_bytes'] and old['finished_at'] < t.receipt['started_at'] and
        checked.get('reviewed') is True and checked.get('control') == 'bags.swap_item.idle_housekeeping' and
        checked.get('source') == bound(capture_path) and checked.get('frame') == old['frame'] and
        checked.get('ordinary_stand_afk_only') is True,
        'source-owned idle capture review and exact committed helper required')
    t.receipt.update(capture_source=bound(capture_path), review_source=bound(review_path),
        before=old['before'], automatic_idle=old['automatic_idle'])
    if 'prior_housekeeping_source' in old:
        t.receipt['prior_housekeeping_source'] = old['prior_housekeeping_source']
    t.persist()
    for kind in ('stand', 'afk'):
        found = facts(t, ready, 'idle_' + kind + '_preflight')
        current = found['native_state']
        if current == ORIGINAL:
            break
        if kind == 'stand':
            require(current == {**ORIGINAL, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True}, 'standing preflight differs')
            keys = found['public'].get('keys', {}).get('SITORSTAND')
            require(type(keys) is list and keys and keys == old['before']['public'].get('keys', {}).get('SITORSTAND'),
                'reviewed installed standing key differs')
            from .interaction_trial import binding_key
            intent = {'kind': 'key', 'value': binding_key(keys[0]), 'hold': .4}
        else:
            require(current == {**ORIGINAL, 'afk': True}, 'AFK preflight differs')
            intent = {'kind': 'chat', 'value': '/afk'}
        rows, events = journals()
        if kind == 'stand':
            actual_cycle = automatic_idle(rows, events, ready['native_session'], old['automatic_idle']['instance_session'],
                old['automatic_idle']['since'], found['observed_at'], original=t.receipt['original_native_objects'])
            require(actual_cycle['automatic_stand_packets'] == old['automatic_idle']['automatic_stand_packets'] and
                actual_cycle['automatic_owner_update'] == old['automatic_idle']['automatic_owner_update'],
                'fresh input preflight must rederive the exact reviewed immutable idle cycle')
        consume(t, bound(failure), kind, intent)
        row = {'kind': kind, 'input': intent, 'preflight': found, 'started_at': time.time(), 'input_replayed': False}
        t.receipt['ordinary_inputs'].append(row); t.receipt['input_sent'] = True; t.persist()
        from .interaction_item_actionbar_parked_selection_capture import game_identity
        from .owned_input import focus
        game_identity(focus(), found['frame'])
        try:
            t.execute(intent)
        finally:
            row['finished_at'] = time.time(); t.persist()
    after = facts(t, ready, 'idle_restored')
    require(after['native_state'] == ORIGINAL and after['resources'] == old['before']['resources'] and
        op.public_same(after['public'], old['before']['public']), 'excluded idle housekeeping did not exactly restore')
    rows, events = journals()
    scoped = [r for r in rows if r.get('session') == ready['native_session'] and
        failed['finished_at'] < r.get('time', 0) <= after['observed_at']]
    cleanup = cleanup_history(old, rows, events, t.receipt['ordinary_inputs'], after['observed_at'])
    t.receipt.update(after=after, frame=after['frame'], cleanup_history=cleanup, source_packets=scoped,
        source_events=[r for r in events if r.get('session') in (ready['native_session'], old['automatic_idle']['instance_session']) and
            failed['finished_at'] < r.get('time', 0) <= after['observed_at']], completed=True,
        phase='bags_swap_idle_housekeeping_restored')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('capture', 'restore'))
    for name in ('output', 'preparation', 'failure'):
        parser.add_argument('--' + name, type=Path, required=True)
    for name in ('capture', 'review', 'prior'):
        parser.add_argument('--' + name, type=Path)
    args = parser.parse_args()
    previous = os.environ.get('CLIENT442_ACTOR'); os.environ['CLIENT442_ACTOR'] = 'scout'
    try:
        from .interaction_trial import Trial
        t = Trial(args.output, controller='code', chat_key_hold=1.2, chat_open_retry=True)
        t.receipt.update(controller='code', custom_script_permission='blocked_by_user', qualification_added=False,
            softTargetInteract={'original': '0', 'current_stock_disabled': '1', 'original_restored': False})
        try:
            if args.action == 'capture': capture(t, args.preparation, args.failure, args.prior)
            else:
                require(args.capture and args.review, 'restore requires actual captured source and review')
                restore(t, args.preparation, args.failure, args.capture, args.review)
        except BaseException as error:
            t.receipt.update(completed=False, failure=f'{type(error).__name__}: {error}')
            if not isinstance(error, Exception): raise
        finally:
            t.receipt['finished_at'] = time.time(); t.persist()
        print(json.dumps({k: t.receipt.get(k) for k in ('completed', 'phase', 'failure')}))
    finally:
        if previous is None: os.environ.pop('CLIENT442_ACTOR', None)
        else: os.environ['CLIENT442_ACTOR'] = previous


if __name__ == '__main__':
    main()

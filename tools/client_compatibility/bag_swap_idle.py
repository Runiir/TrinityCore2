"""Pure source-owned authority for excluded idle restoration before a bag swap."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re

from . import bag_swap_contract as contract
from . import bag_swap_preservation as preservation
from .item_actionbar_contract import INDEX, body, finite, records, require, strict_equal, public_assignments

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


PROOF_SCHEMA = 'client442_bag_swap_idle_history_v1'
SUCCESS_HASHES = ('6adced56bcbec9dbdf16a584c45c7b7b2f90f92e0b1294402ecfe5b267b1ec86',
    'e8cbcca44ee8ac2bb7bce1562dd35d43bdb11d2ad67631e0d30cd3724bfc9316')
FAILED_CAPTURE_SHA = '50a1e8db99fad07b0c49b6c4f71bf564663435c4d2934d0575211df05640bfcd'
FAILED_CAPTURE_COMMIT = 'b3e115403c450c4fdb7552baf6464c45bb283d70'
FAILED_CAPTURE_HASHES = ('dcbaa8cce90307b89085fe3b9407ae841c63f2b544cbbc07c2419de96c1f88f5',
    'c8d2046fd1f195241a47408180a96bc5123ddcc1a9c25a1cb14abaa8c834e34d')
MAX_CYCLES = 4
OWNED = frozenset((2, (0x4000 << 48) | 41, (0x4000 << 48) | 33))
STAND_NAMES = frozenset(('CMSG_STAND_STATE_CHANGE', 'CMSG_STANDSTATECHANGE', 'SMSG_STAND_STATE_UPDATE'))
AFK_NAMES = frozenset(('CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK'))


def _ref(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'} and type(ref['path']) is str and
        Path(ref['path']).is_absolute() and '..' not in Path(ref['path']).parts and
        'evidence' in Path(ref['path']).parts and type(ref['sha256']) is str and
        re.fullmatch('[0-9a-f]{64}', ref['sha256']), 'exact private immutable idle reference required')
    return ref


def _hash(value):
    return hashlib.sha256(key(value).encode()).hexdigest()


def _raw(value, ref):
    # Producer serialization is verified against the immutable source SHA.
    for indent, sorted_keys, compact, newline in ((2, False, False, '\n'),
        (2, True, False, '\n'), (None, True, True, ''), (None, False, True, ''),
        (2, False, False, ''), (None, False, False, '\n')):
        raw = (json.dumps(value, indent=indent, sort_keys=sorted_keys,
            separators=(',', ':') if compact else None, allow_nan=False) + newline).encode()
        if hashlib.sha256(raw).hexdigest() == ref['sha256']:
            return raw.hex()
    raise RuntimeError('idle source value cannot reproduce its exact immutable JSON bytes')


def _bound_value(store, ref, successful=True):
    _ref(ref)
    value = store.get(ref, successful)
    require(type(value) is dict, 'idle source must be JSON dictionary')
    _raw(value, ref)
    return value


def _json_source(ref, value):
    return {'source': deepcopy(ref), 'raw_hex': _raw(value, ref)}


def _source_value(record):
    require(type(record) is dict and set(record) == {'source', 'raw_hex'}, 'exact compact source record required')
    _ref(record['source'])
    raw_hex = record['raw_hex']
    require(type(raw_hex) is str and 0 < len(raw_hex) <= 4_000_000 and len(raw_hex) % 2 == 0 and
        re.fullmatch('[0-9a-f]+', raw_hex), 'bounded exact compact source bytes required')
    raw = bytes.fromhex(raw_hex)
    require(hashlib.sha256(raw).hexdigest() == record['source']['sha256'], 'compact idle source bytes changed')
    value = json.loads(raw)
    require(type(value) is dict, 'compact idle source JSON must be dictionary')
    return value


def _code(vector, current, *, historical=False):
    require(type(vector) is list and len(vector) == len(OWN_FILES + DEPENDENCIES), 'complete twelve-member H source epoch required')
    roots, total = set(), 0
    for index, (row, suffix) in enumerate(zip(vector, OWN_FILES + DEPENDENCIES)):
        require(type(row) is dict and set(row) == {'path', 'sha256', 'bytes', 'raw_hex'} and
            type(row['path']) is str and Path(row['path']).is_absolute() and row['path'].endswith('/' + suffix) and
            type(row['raw_hex']) is str and re.fullmatch('[0-9a-f]+', row['raw_hex']) and len(row['raw_hex']) % 2 == 0,
            'exact committed H source member shape differs')
        roots.add(row['path'][:-len(suffix)])
        raw = bytes.fromhex(row['raw_hex']); total += len(raw)
        require(type(row['bytes']) is int and 0 < row['bytes'] == len(raw) and total <= 4_000_000 and
            hashlib.sha256(raw).hexdigest() == row['sha256'], 'committed H source raw bytes differ')
        if index < 2:
            require(row['sha256'] == (FAILED_CAPTURE_HASHES if historical else SUCCESS_HASHES)[index],
                'H helper must retain its exact frozen historical/successful bytes')
        matches = [r for r in current if r.get('path') == row['path']]
        require(len(matches) <= 1 and (not matches or historical or matches[0].get('sha256') == row['sha256']),
            'H dependency differs from the current committed source of the same path')
    require(len(roots) == 1, 'H code source vector crosses repositories')


def receipt_chain(store, latest_ref):
    """Read successful original H sources in chronological order, without I/O."""
    result, seen, ref = [], set(), latest_ref
    while ref is not None:
        _ref(ref)
        require(ref['path'] not in seen and len(result) < MAX_CYCLES, 'idle source chain cycles or exceeds four restorations')
        seen.add(ref['path']); value = _bound_value(store, ref)
        require(value.get('schema') == SCHEMA and value.get('phase') == 'bags_swap_idle_housekeeping_restored' and
            value.get('completed') is True and value.get('failure') is None, 'prior idle source must be a successful restored H')
        result.append((deepcopy(ref), value)); ref = value.get('prior_housekeeping_source')
    return list(reversed(result))


def _digest(store, path, expected):
    path = str(path); parts = Path(path).parts
    require('evidence' in parts, 'idle image must remain in source-owned private evidence')
    member = str(Path(*parts[parts.index('evidence'):]))
    found = [store.digests[k] for k in (path, member) if k in store.digests]
    require(found and all(v == expected for v in found), 'source-owned idle PNG bytes differ or are absent')


def _frame(store, frame, ref, ready, *, movement=True):
    require(type(frame) is dict and type(frame.get('file')) is str and Path(frame['file']).name == frame['file'] and
        frame['file'].endswith('.png') and type(frame.get('sha256')) is str and re.fullmatch('[0-9a-f]{64}', frame['sha256']),
        'source-owned idle PNG identity required')
    _digest(store, Path(ref['path']).parent / frame['file'], frame['sha256'])
    monitor, original = frame.get('monitor', {}), ready['frame']['monitor']
    isolation, before = monitor.get('input_isolation', {}), original['input_isolation']
    require(monitor.get('second_monitor_verified') is True and monitor.get('monitor', {}).get('name') == 'HDMI-1' and
        monitor.get('pid') == ready['runtime']['client']['pid'] and isolation.get('actor') == 'scout' and
        isolation.get('host_activation_sent') is False and all(type(isolation.get(k)) is type(before[k]) and
            isolation[k] == before[k] for k in ('game_pid', 'display', 'window_id')), 'idle frame changed its owned physical game')
    if movement:
        observed = frame.get('movement', {})
        require(observed.get('speed') == 0 and all(observed.get(k) is False for k in ('dead', 'in_combat', 'on_taxi')),
            'idle frame must be stationary, alive and outside combat/taxi')


def _closed(value, phase, ready):
    require(value.get('schema') == SCHEMA and value.get('phase') == phase and value.get('completed') is True and
        value.get('failure') is None and finite(value.get('started_at')) and finite(value.get('finished_at')) and
        0 < value['started_at'] < value['finished_at'] and value.get('actor') == ready['actor'] and
        value.get('runtime') == ready['runtime'] and value.get('native_session') == ready['native_session'] and
        value.get('controller') == 'code' and value.get('model') is None and value.get('revision') is None and
        value.get('qualification_added') is False and value.get('excluded_housekeeping') is True and
        value.get('first_failure_excluded') is True and value.get('cases') == [] and value.get('cleanup') == [] and
        value.get('custom_script_permission') == 'blocked_by_user' and value.get('softTargetInteract') == ready.get('softTargetInteract') and
        value.get('observer_file_sha256') == ready.get('observer_file_sha256') and
        value.get('compatibility_addon_sha256') == ready.get('compatibility_addon_sha256'), 'successful excluded H identity or boundary differs')


def _facts(store, value, ref, ready, original_resources, position, native):
    require(type(value) is dict and finite(value.get('observed_at')) and strict_equal(value.get('native_state'), native),
        'idle observation native state or time differs')
    preservation.online_preservation(ready['all_offline_snapshot'], value.get('snapshot'))
    contract.native_resources(original_resources, value.get('resources'))
    state = value.get('state', {})
    require(state.get('player') == 'Harnesstwo' and type(state.get('level')) is int and state['level'] == 1 and
        type(state.get('guid')) is str and re.fullmatch('Player-[0-9]+-00000002', state['guid']) and
        strict_equal(state.get('world_position'), position) and 'cursor_info' in state and
        (state['cursor_info'] is None or state['cursor_info'] is False or type(state['cursor_info']) in (list, dict) and not state['cursor_info']) and
        not any(state.get(k) for k in ('bags', 'panels', 'spell_targeting', 'lua_errors', 'blocked_actions')),
        'idle observed owner, position, cursor or UI differs')
    _frame(store, value['frame'], ref, ready)
    public_assignments(value.get('public'), ready['all_offline_snapshot']['2']['saved']['actions'],
        ready['all_offline_snapshot']['2']['native']['activeTalentGroup'])


def _relevant_packets(rows):
    result = []
    for row in rows:
        if row.get('name') in STAND_NAMES:
            result.append(row)
        elif (row.get('name'), row.get('direction')) == ('SMSG_DESTROY_OBJECT', 'from_native'):
            if int.from_bytes(body(row)[:8], 'little') in OWNED: result.append(row)
        elif (row.get('name'), row.get('direction')) == ('SMSG_UPDATE_OBJECT', 'from_native'):
            if any(r.get('guid') in OWNED or set(r.get('removed', [])) & OWNED for r in records(body(row))): result.append(row)
    return result


def _summary(value):
    return {k: deepcopy(v) for k, v in value.items() if k not in
        ('source_packets', 'source_events', 'original_native_objects', 'ending_native_objects')}


def _cycle_replay(cycle, original, owner, physical):
    rows, events = cycle['packets'], cycle['events']
    require(type(rows) is list and type(events) is list and all(type(r) is dict for r in rows + events), 'compact idle journal rows required')
    require(all(r.get('session') == owner and finite(r.get('time')) and
        set(r) == {'session', 'time', 'name', 'direction', 'body'} for r in rows), 'compact idle raw rows differ')
    gap = automatic_idle(rows, events, owner, physical, cycle['since'], cycle['captured_at'], original=original)
    require(strict_equal(cycle['automatic_idle'], _summary(gap)), 'compact automatic idle proof differs')
    cleanup = cleanup_history({'automatic_idle': gap}, rows, events, cycle['inputs'], cycle['restored_at'])
    require(strict_equal(cycle['cleanup_history'], _summary(cleanup)), 'compact restored idle proof differs')
    native_rows = [u['packet'] for u in cleanup['owner_pose_updates']]
    native_metadata = metadata(native_rows, events, owner, physical)
    require(strict_equal(native_metadata, cycle['native_metadata']), 'each native idle sparse effect must bind its exact metadata')
    # Every state transition must follow the consumed ordinary request.
    later = cleanup['owner_pose_updates'][1:]
    require(later and later[0]['packet']['time'] > cleanup['restored_stand_packets'][1]['time'] and
        later[0]['packet']['time'] <= cycle['inputs'][0]['finished_at'], 'standing sparse effect is not attributable to its input')
    if len(cycle['inputs']) == 2:
        afk = cleanup['restored_afk_metadata']
        require(later[-1]['fields'].get(str(INDEX['PLAYER_FLAGS'])) == 0 and later[-1]['packet']['time'] > afk[-1]['time'] and
            later[-1]['packet']['time'] <= cycle['inputs'][1]['finished_at'], 'AFK sparse effect is not attributable to its input')
    require(cleanup['ending_native_objects'] == original, 'idle native fields did not completely restore original owner/items')
    return gap, cleanup


def _history(proof):
    require(type(proof) is dict and proof.get('schema') == PROOF_SCHEMA and type(proof.get('cycles')) is list and
        1 <= len(proof['cycles']) <= MAX_CYCLES and re.fullmatch('[0-9a-f]{40}', proof.get('code_commit', '')),
        'compact source-owned idle history required')
    _ref(proof['original_entry_source']); _ref(proof['preparation_source'])
    require(proof['original_entry_source']['sha256'] == FAILED_SHA and
        type(proof.get('session')) is str and type(proof.get('instance_session')) is str and
        proof['session'] != proof['instance_session'] and
        set(proof.get('original_native_objects', {})) == {str(g) for g in OWNED}, 'idle history original identity differs')
    original = proof['original_native_objects']
    owner = original['2']
    require(owner.get(str(INDEX['UNIT_FIELD_BYTES_1']), 0) & 255 == 0 and
        owner.get(str(INDEX['UNIT_FIELD_BYTES_2']), 0) & 255 == 0 and
        not owner.get(str(INDEX['PLAYER_FLAGS']), 0) & 2, 'original idle native pose differs')
    _code(proof['committed_source_bytes'], proof['current_sources'])
    packet_keys, event_keys, sources = [], [], []
    previous = None
    for cycle in proof['cycles']:
        _ref(cycle['source']); _ref(cycle['capture_source'])
        require(cycle.get('prior_source') == previous and finite(cycle['started_at']) and finite(cycle['finished_at']) and
            cycle['captured_at'] < cycle['started_at'] < cycle['restored_at'] <= cycle['finished_at'] and
            (previous is None or cycle['since'] == proof['cycles'][len(sources) - 1]['finished_at']), 'compact idle chain chronology differs')
        gap, cleanup = _cycle_replay(cycle, original, proof['session'], proof['instance_session'])
        review = _source_value(cycle['review'])
        require(review.get('reviewed') is True and review.get('control') == 'bags.swap_item.idle_housekeeping' and
            review.get('source') == cycle['capture_source'] and review.get('frame') == cycle['capture_frame'] and
            review.get('ordinary_stand_afk_only') is True, 'exact compact idle review differs')
        digest = hashlib.sha256(key({'original_entry_source': proof['original_entry_source'],
            'automatic_stand_packets': gap['automatic_stand_packets'], 'automatic_owner_update': gap['automatic_owner_update']}).encode()).hexdigest()
        require(len(cycle['markers']) == len(cycle['inputs']), 'each compact idle input requires one source-owned marker')
        for row, source in zip(cycle['inputs'], cycle['markers']):
            marker = _source_value(source)
            expected = Path(proof['original_entry_source']['path']).parent / ('bag_swap_idle_' + digest + '_' + row['kind'] + '_attempt.json')
            require(source['source']['path'] == str(expected) and marker.get('schema') == 'client442_bag_swap_idle_consumed_input_v1' and
                marker.get('kind') == row['kind'] and marker.get('cycle_sha256') == digest and
                marker.get('capture_source') == cycle['capture_source'] and marker.get('original_entry_source') == proof['original_entry_source'] and
                marker.get('operation_output') == cycle['source']['path'] and marker.get('input_intent') == row['input'] and
                marker.get('input_replay_allowed') is False and finite(marker.get('created_at')) and
                row['preflight']['observed_at'] <= marker['created_at'] <= row['started_at'], 'exact consumed idle marker differs')
        packet_keys.extend(key(r) for r in gap['automatic_stand_packets'][:2] + cleanup['restored_stand_packets'][:2] +
            [u['packet'] for u in cleanup['owner_pose_updates']])
        event_keys.extend(key(r) for r in gap['metadata'] + gap['afk_metadata'] + cleanup['metadata'] +
            cleanup['restored_afk_metadata'] + native_metadata_list(cycle) + cleanup['ignored_query_metadata'] + cleanup['latency_metadata'])
        sources.append(cycle['source']); previous = cycle['source']
    require(proof['housekeeping_sources'] == sources and proof['allowed_packet_keys'] == sorted(set(packet_keys)) and
        proof['allowed_metadata_keys'] == sorted(set(event_keys)) and proof['since'] == proof['cycles'][0]['since'] and
        proof['until'] == proof['cycles'][-1]['restored_at'], 'compact idle source/key projection differs')
    return proof


def native_metadata_list(cycle):
    return cycle['native_metadata']


def validate_history(proof):
    """Reconstruct each bounded source-key allowance; full receipts are rebound separately."""
    try:
        return deepcopy(_history(proof))
    except (KeyError, ValueError, TypeError, IndexError) as error:
        raise RuntimeError('compact idle history is malformed') from error


def validate_receipt(store, H, ready, failed, E):
    """Rebind full excluded H receipts, then retain only their bounded proof projection."""
    latest = _ref(E.get('idle_housekeeping_source'))
    chain = receipt_chain(store, latest)
    require(strict_equal(chain[-1][1], H), 'latest source-owned H receipt differs')
    ready_ref, failed_ref = H.get('preparation_source'), H.get('original_entry_source')
    require(strict_equal(_bound_value(store, ready_ref), ready) and strict_equal(_bound_value(store, failed_ref, False), failed) and
        failed_ref['sha256'] == FAILED_SHA and failed.get('completed') is False and
        failed.get('phase') == 'bags_swap_entry_started' and failed.get('code_commit') == ready.get('code_commit') == C1 and
        failed.get('preparation_source') == ready_ref and E.get('original_entry_source') == failed_ref and
        E.get('preparation_source') == ready_ref and E.get('actor') == ready['actor'] and E.get('runtime') == ready['runtime'] and
        E.get('native_session') == ready['native_session'], 'original immutable failed C1 idle authority differs')
    initial_ref = H.get('original_resources_source'); initial = _bound_value(store, initial_ref, False)
    require(initial_ref['sha256'] == INITIAL_FACTS_SHA and initial.get('entry_source') == failed_ref and
        initial.get('actor') == ready['actor'] and initial.get('runtime') == ready['runtime'] and initial.get('session') == ready['native_session'] and
        initial.get('input_sent') is False and initial.get('mutation_sent') is False and initial.get('before') == ready['all_offline_snapshot'] and
        initial.get('native_state') == ORIGINAL, 'original honest read-only resource source differs')
    preservation.online_preservation(ready['all_offline_snapshot'], initial['after'])
    original = original_objects(failed['raw_entry_packets'])
    cycles, prior, physical = [], None, None
    for ref, value in chain:
        _closed(value, 'bags_swap_idle_housekeeping_restored', ready)
        capture_ref = value.get('capture_source'); capture = _bound_value(store, capture_ref)
        _closed(capture, 'bags_swap_idle_housekeeping_captured', ready)
        require(value.get('preparation_source') == capture.get('preparation_source') == ready_ref and
            value.get('original_entry_source') == capture.get('original_entry_source') == failed_ref and
            value.get('original_resources_source') == capture.get('original_resources_source') == initial_ref and
            value.get('original_resources') == capture.get('original_resources') == initial['resources'] and
            value.get('original_native_objects') == capture.get('original_native_objects') == original and
            value.get('original_failed_image') == capture.get('original_failed_image') and
            value['original_failed_image']['sha256'] == FAILED_IMAGE_SHA and
            value.get('prior_housekeeping_source') == capture.get('prior_housekeeping_source') == prior and
            value.get('code_commit') == capture.get('code_commit') and re.fullmatch('[0-9a-f]{40}', value['code_commit']) and
            value['code_commit'] not in (C1, E['code_commit']) and
            value.get('committed_source_bytes') == capture.get('committed_source_bytes') and
            (not cycles or value['code_commit'] == H['code_commit']) and
            value.get('mutation_sent') is False and capture.get('mutation_sent') is False and
            capture.get('input_sent') is False and capture.get('ordinary_inputs') == [] and value.get('input_sent') is True,
            'excluded capture/restore code, authority, prior source or input boundary differs')
        _code(value['committed_source_bytes'], E['committed_sources'])
        image = value['original_failed_image']; _ref(image); _digest(store, image['path'], FAILED_IMAGE_SHA)
        require(Path(image['path']) == Path(failed_ref['path']).parent / 'bags_swap_entered.png', 'original failed PNG source differs')
        position = value.get('original_world_position')
        require(position == capture.get('original_world_position'), 'original failed world position differs')
        gap = value.get('automatic_idle')
        require(gap == capture.get('automatic_idle') and gap.get('original_native_objects') == original and
            gap.get('session') == ready['native_session'] and gap.get('since') ==
            (failed['finished_at'] if prior is None else cycles[-1]['finished_at']), 'original automatic idle cycle boundary differs')
        physical = gap['instance_session'] if physical is None else physical
        require(gap['instance_session'] == physical, 'idle cycles changed physical login instance')
        recomputed = automatic_idle(gap['source_packets'], gap['source_events'], ready['native_session'], physical,
            gap['since'], capture['before']['observed_at'], original=original)
        require(strict_equal(gap, recomputed), 'complete automatic idle source journal differs')
        require(capture['started_at'] <= capture['before']['observed_at'] <= capture['finished_at'] < value['started_at'] and
            value['after']['observed_at'] <= value['finished_at'] < E['started_at'], 'idle capture/restoration observation chronology differs')
        _facts(store, capture['before'], capture_ref, ready, initial['resources'], position,
            {**ORIGINAL, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True})
        require(value.get('before') == capture['before'] and value.get('frame') == value['after']['frame'] and
            capture.get('frame') == capture['before']['frame'], 'idle top-level frames or reviewed before state differ')
        _facts(store, value['after'], ref, ready, initial['resources'], position, ORIGINAL)
        inputs = value.get('ordinary_inputs')
        require(type(inputs) is list and 1 <= len(inputs) <= 2, 'one stand and optional AFK input required')
        for index, row in enumerate(inputs):
            wanted = {**ORIGINAL, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True} if index == 0 else {**ORIGINAL, 'afk': True}
            _facts(store, row['preflight'], ref, ready, initial['resources'], position, wanted)
            require(value['started_at'] <= row['preflight']['observed_at'] <= row['started_at'] and
                (index == 0 or inputs[index - 1]['finished_at'] <= row['preflight']['observed_at']), 'idle preflight input order differs')
        cleanup = cleanup_history(capture, value['source_packets'], value['source_events'], inputs, value['after']['observed_at'])
        require(strict_equal(cleanup, value.get('cleanup_history')), 'complete idle cleanup source journal differs')
        review_ref = value.get('review_source'); review = _bound_value(store, review_ref, False)
        require(review.get('frame') == capture['frame'] and review.get('source') == capture_ref,
            'restoration review must bind exact captured screen')
        _digest(store, Path(review_ref['path']).parent / capture['frame']['file'], capture['frame']['sha256'])
        rows = [r for r in value['source_packets'] if gap['since'] < r.get('time', 0) <= value['after']['observed_at']]
        compact_rows = _relevant_packets(rows)
        native_effects = [u['packet'] for u in cleanup['owner_pose_updates']]
        effects_metadata = metadata(native_effects, value['source_events'], ready['native_session'], physical)
        names = STAND_NAMES | AFK_NAMES | set(IGNORED_QUERIES) | {'CMSG_PING'}
        selected_events = [r for r in value['source_events'] if gap['since'] < r.get('time', 0) <= value['after']['observed_at'] and
            (r.get('name') in names or r in effects_metadata)]
        compact_inputs = [{**row, 'preflight': {'native_state': row['preflight']['native_state'],
            'observed_at': row['preflight']['observed_at']}} for row in inputs]
        markers = [_json_source(value[k + '_attempt_source'], _bound_value(store, value[k + '_attempt_source'], False))
            for k in ('stand', 'afk')[:len(inputs)]]
        require(('afk_attempt_source' in value) == (len(inputs) == 2), 'idle cannot invent or omit a consumed AFK marker')
        cycles.append({'source': ref, 'capture_source': capture_ref, 'prior_source': prior,
            'started_at': value['started_at'], 'finished_at': value['finished_at'], 'since': gap['since'],
            'captured_at': capture['before']['observed_at'], 'restored_at': value['after']['observed_at'],
            'automatic_idle': _summary(gap), 'cleanup_history': _summary(cleanup), 'packets': compact_rows,
            'events': selected_events, 'native_metadata': effects_metadata, 'inputs': compact_inputs,
            'markers': markers, 'review': _json_source(review_ref, review), 'capture_frame': capture['frame']})
        prior = ref
    proof = {'schema': PROOF_SCHEMA, 'session': ready['native_session'], 'instance_session': physical,
        'original_entry_source': failed_ref, 'preparation_source': ready_ref, 'original_resources_source': initial_ref,
        'original_native_objects': original, 'code_commit': H['code_commit'],
        'committed_source_bytes': H['committed_source_bytes'], 'current_sources': E['committed_sources'],
        'cycles': cycles, 'housekeeping_sources': [ref for ref, _ in chain],
        'since': cycles[0]['since'], 'until': cycles[-1]['restored_at'], 'allowed_packet_keys': [], 'allowed_metadata_keys': []}
    for cycle in cycles:
        gap, cleanup = _cycle_replay(cycle, original, proof['session'], physical)
        proof['allowed_packet_keys'] += [key(r) for r in gap['automatic_stand_packets'][:2] + cleanup['restored_stand_packets'][:2] +
            [u['packet'] for u in cleanup['owner_pose_updates']]]
        proof['allowed_metadata_keys'] += [key(r) for r in gap['metadata'] + gap['afk_metadata'] + cleanup['metadata'] +
            cleanup['restored_afk_metadata'] + cycle['native_metadata'] + cleanup['ignored_query_metadata'] + cleanup['latency_metadata']]
    proof['allowed_packet_keys'] = sorted(set(proof['allowed_packet_keys']))
    proof['allowed_metadata_keys'] = sorted(set(proof['allowed_metadata_keys']))
    return validate_history(proof)

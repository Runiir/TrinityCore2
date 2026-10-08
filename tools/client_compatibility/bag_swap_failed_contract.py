"""Pure, excluded closure of the original failed occupied-bag entry.

This proves an observed login, automatic idle transition and timed logout. It
never grants bag-swap qualification or an allowance to the normal swap guard.
"""
from copy import deepcopy
import hashlib
from itertools import groupby
import json
import struct

from . import bag_swap_contract as contract
from . import bag_swap_login_sync as sync
from . import item_actionbar_contract as shared
from .world.buffer import Reader, Writer
from .world.native_objects import guid as native_guid, records

SCHEMA = 'client442_bag_swap_failed_entry_history_v1'
require, finite, body, key = shared.require, shared.finite, shared.body, sync.packet_key
INDEX = shared.INDEX
ROUTINE = {'CMSG_TIME_SYNC_RESPONSE': 8, 'CMSG_TIME_SYNC_RESP': 8,
    'CMSG_SERVER_TIME_OFFSET_REQUEST': 0, 'CMSG_QUEST_GIVER_STATUS_QUERY': 8}
IGNORED = {'CMSG_TUTORIAL': 5, 'CMSG_GM_TICKET_GET_CASE_STATUS': 0,
    'CMSG_GET_ACCOUNT_NOTIFICATIONS': 0}
STAND_NAMES = ('CMSG_STAND_STATE_CHANGE', 'CMSG_STANDSTATECHANGE', 'SMSG_STAND_STATE_UPDATE')
AFK_NAMES = ('CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK')
LOGOUT_NAMES = ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_RESPONSE', 'SMSG_LOGOUT_COMPLETE')
STUNNED = 0x00040000  # UnitDefines.h UNIT_FLAG_STUNNED.


def _one(rows, name, direction, raw):
    found = [r for r in rows if (r.get('name'), r.get('direction')) == (name, direction)]
    require(len(found) == 1 and body(found[0]) == raw,
        'failed closure requires one exact packet: ' + name + '/' + direction)
    return found[0]


def _ordered(rows, limit=2):
    require(all(a['time'] < b['time'] for a, b in zip(rows, rows[1:])) and
        rows[-1]['time'] - rows[0]['time'] < limit, 'failed closure packet chronology differs')


def _metadata(rows, events, session, physical):
    result, used = [], set()
    for packet in sorted(rows, key=lambda r: r['time']):
        direction = packet['direction']
        owner_delivery = packet['name'] in (*STAND_NAMES, *LOGOUT_NAMES) and direction == 'to_client'
        expected = session if direction in ('from_native', 'to_native') or owner_delivery else physical
        found = [i for i, e in enumerate(events) if i not in used and
            (e.get('session'), e.get('name'), e.get('direction'), e.get('event')) ==
            (expected, packet['name'], direction,
             'native_packet' if direction in ('from_native', 'to_native') else 'modern_packet') and
            type(e.get('bytes')) is int and e['bytes'] == len(body(packet)) and
            0 <= packet['time'] - e['time'] < .1]
        require(len(found) == 1, 'failed closure packet metadata must be unique and attributable')
        used.add(found[0]); result.append(events[found[0]])
    return result


def _ignored_metadata(events, session, physical):
    selected = []
    for name, size in IGNORED.items():
        rows = sorted([e for e in events if e.get('name') == name], key=lambda e: e['time'])
        require(len(rows) % 2 == 0, 'ignored query metadata must have complete occurrences')
        for incoming, dropped in zip(rows[::2], rows[1::2]):
            require([(e.get('event'), e.get('session'), e.get('bytes')) for e in (incoming, dropped)] ==
                [('modern_packet', session, size), ('unmapped_client_packet', session, size)] and
                incoming.get('direction') == 'from_client' and 'direction' not in dropped and
                all(type(e.get('bytes')) is int for e in (incoming, dropped)) and
                0 <= dropped['time'] - incoming['time'] < .1,
                'failed closure ignored query occurrence differs')
        selected += rows
    pings = [e for e in events if e.get('name') == 'CMSG_PING']
    require(all(type(e.get('bytes')) is int and e['bytes'] == 8 and
        (e.get('session'), e.get('event'), e.get('direction')) in
        ((physical, 'modern_packet', 'from_client'), (session, 'modern_packet', 'from_client'),
         (session, 'native_packet', 'to_native')) for e in pings),
        'failed closure latency metadata differs')
    incoming = [e for e in pings if e.get('session') == session and e.get('direction') == 'from_client']
    outgoing = [e for e in pings if e.get('direction') == 'to_native']
    require(len(incoming) == len(outgoing) and all(0 <= b['time'] - a['time'] < .1
        for a, b in zip(incoming, outgoing)), 'failed closure latency forwarding differs')
    return selected + pings


def _routine_metadata(rows, events, session, physical):
    result = []
    for name, direction in sorted({(r['name'], r['direction']) for r in rows}):
        packets = sorted([r for r in rows if (r['name'], r['direction']) == (name, direction)],
            key=lambda r: r['time'])
        expected = session if direction == 'to_native' or name == 'CMSG_SERVER_TIME_OFFSET_REQUEST' else physical
        candidates = sorted([e for e in events if (e.get('name'), e.get('direction')) == (name, direction)],
            key=lambda e: e['time'])
        require(len(packets) == len(candidates) and all(
            e.get('session') == expected and e.get('event') ==
            ('native_packet' if direction == 'to_native' else 'modern_packet') and
            type(e.get('bytes')) is int and e['bytes'] == len(body(p)) and
            0 <= p['time'] - e['time'] < .1 for p, e in zip(packets, candidates)),
            'every routine read-only occurrence must bind its own ordered metadata')
        result += candidates
    for modern_name, native_name in (('CMSG_TIME_SYNC_RESPONSE', 'CMSG_TIME_SYNC_RESP'),
            ('CMSG_QUEST_GIVER_STATUS_QUERY', 'CMSG_QUEST_GIVER_STATUS_QUERY')):
        incoming = sorted([r for r in rows if (r['name'], r['direction']) == (modern_name, 'from_client')],
            key=lambda r: r['time'])
        outgoing = sorted([r for r in rows if (r['name'], r['direction']) == (native_name, 'to_native')],
            key=lambda r: r['time'])
        require(len(incoming) == len(outgoing) and all(_routine_native(a) == body(b) and
            0 < b['time'] - a['time'] < .1 for a, b in zip(incoming, outgoing)),
            'routine read-only forwarding body or occurrence differs')
    return result


def _routine_native(row):
    raw = body(row)
    if row['name'] != 'CMSG_QUEST_GIVER_STATUS_QUERY':
        return raw
    reader = Reader(raw)
    low, high = reader.guid()
    reader.end()
    kind, entry = high >> 58, (high >> 6) & 0x7fffff
    require(kind in (8, 11) and 0 < low <= 0xffffffff and 0 < entry <= 0xfffff and
        high == (kind << 58) | (1 << 42) | (entry << 6) and
        Writer().guid(low, high).finish() == raw,
        'routine quest status read must retain its canonical realm1/map0 giver identity')
    native = ((0xf13 if kind == 8 else 0xf11) << 52) | (entry << 32) | low
    return struct.pack('<Q', native)


def _owned_records(row, wanted):
    if row['name'] == 'SMSG_DESTROY_OBJECT' and row['direction'] == 'from_native':
        raw = body(row)
        require(len(raw) == 9 and int.from_bytes(raw[:8], 'little') not in wanted and
            int.from_bytes(raw[:8], 'little') >> 48 != 0x4000,
            'failed closure destroyed an owned object')
    if (row['name'], row['direction']) != ('SMSG_UPDATE_OBJECT', 'from_native'):
        return []
    decoded = records(body(row))
    for record in decoded:
        if record['update_type'] == 3:
            require(not set(record['removed']) & wanted and
                not any(identity >> 48 == 0x4000 for identity in record['removed']),
                'failed closure removed an owned or unsupported item object')
        elif record.get('guid') not in wanted:
            require(record.get('guid', 0) >> 48 != 0x4000,
                'failed closure introduced another native item outside its complete original inventory')
            fields = record.get('fields', {})
            require(not (record['update_type'] in (1, 2) and record.get('kind') == 1 and
                (fields.get(INDEX['ITEM_FIELD_OWNER'], 0) |
                 fields.get(INDEX['ITEM_FIELD_OWNER'] + 1, 0) << 32) == 2),
                'failed closure created another actor2-owned item')
    return [r for r in decoded if r.get('guid') in wanted]


def _original(rows, inventory):
    wanted = {2, *((0x4000 << 48) | r[3] for r in inventory)}
    objects = {}
    for row in sorted(rows, key=lambda r: r['time']):
        for record in _owned_records(row, wanted):
            identity = record['guid']
            if record['update_type'] in (1, 2):
                require(identity not in objects and record.get('kind') == (4 if identity == 2 else 1),
                    'failed original needs one native owner and every inventory item creation')
                objects[identity] = {}
            require(identity in objects, 'failed original owned update precedes creation')
            objects[identity].update(record.get('fields', {}))
    require(set(objects) == wanted, 'failed original complete owner and inventory item creations are absent')
    owner = objects[2]
    require(owner.get(INDEX['UNIT_FIELD_BYTES_1'], 0) == owner.get(INDEX['PLAYER_FLAGS'], 0) == 0 and
        owner.get(INDEX['UNIT_FIELD_BYTES_2'], 0) & 255 == 0 and
        owner.get(INDEX['UNIT_FIELD_FLAGS'], 0) == 8,
        'failed original must stand unsheathed, non-AFK and player-controlled')
    start = INDEX['PLAYER_FIELD_INV_SLOT_HEAD']
    expected = {r[2]: (0x4000 << 48) | r[3] for r in inventory}
    for slot in range(39):
        require(owner.get(start + slot * 2, 0) | owner.get(start + slot * 2 + 1, 0) << 32 ==
            expected.get(slot, 0), 'failed original complete native inventory differs from SQL inventory')
    for sql in inventory:
        fields = objects[(0x4000 << 48) | sql[3]]
        require(fields.get(INDEX['OBJECT_FIELD_ENTRY']) == sql[5] and
            fields.get(INDEX['ITEM_FIELD_STACK_COUNT']) == sql[9] and
            fields.get(INDEX['ITEM_FIELD_OWNER'], 0) == fields.get(INDEX['ITEM_FIELD_CONTAINED'], 0) == 2 and
            fields.get(INDEX['ITEM_FIELD_OWNER'] + 1, 0) == fields.get(INDEX['ITEM_FIELD_CONTAINED'] + 1, 0) == 0,
            'failed original inventory item entry/count/owner/container differs')
    return objects


def _json_objects(objects):
    # Native masks omit zero values at creation and can later explicitly send
    # the same zero. Canonical zero omission preserves the entire field value.
    return {str(identity): {str(index): value for index, value in sorted(fields.items()) if value != 0}
        for identity, fields in sorted(objects.items())}


def _digest(values):
    result, first = hashlib.sha256(b'['), True
    for _, group in groupby(sorted(values, key=lambda r: r['time']), key=lambda r: r['time']):
        for row in sorted(group, key=key):
            if not first:
                result.update(b',')
            result.update(key(row).encode())
            first = False
    result.update(b']')
    return result.hexdigest()


def _suffix(rows, events, prefix, audit_until):
    session, physical, since = prefix['session'], prefix['instance_session'], prefix['until']
    actor_events = [e for e in events if e.get('account_id') == 2 or e.get('guid') == 2]
    require(all(finite(e.get('time')) for e in actor_events),
        'actor2-attributed metadata must have a finite audit time even on another session')
    require(not any(since < e['time'] <= audit_until and (e.get('event') == 'instance_authenticated' or
        e.get('guid') == 2) for e in actor_events), 'post-close audit cannot contain another actor2 instance or effect')
    raw = [r for owner in (session, physical) for r in shared.packet_rows(rows, owner, since, audit_until)
        if r['time'] > since]
    scoped = [e for e in events if e.get('session') in (session, physical) and since < e['time'] <= audit_until]
    require(not any(r['session'] == physical for r in raw) and not any(e['session'] == physical for e in scoped),
        'the retired physical instance cannot have post-close packets or metadata')
    require(not any(e.get('event') == 'instance_authenticated' and e.get('account_id') == 2 and
        finite(e.get('time')) and since < e['time'] <= audit_until for e in events),
        'post-close audit cannot admit another actor2 login')
    require(not any(r.get('name') == 'CMSG_PLAYER_LOGIN' and finite(r.get('time')) and
        since < r['time'] <= audit_until for r in rows), 'post-close audit cannot contain another login request')
    require(all(set(r) == sync.WIRE_FIELDS and r.get('direction') in sync.WIRE_DIRECTIONS and
        type(r.get('name')) is str and r['name'] for r in raw) and len(set(map(key, raw))) == len(raw) and
        len(set(map(key, scoped))) == len(scoped), 'post-close audit requires unique canonical rows')
    for row in raw:
        body(row)
    used = set()
    def claim(values):
        require(not (used & set(map(key, values))), 'post-close metadata is claimed more than once')
        used.update(map(key, values))
    def shape(event, name, direction, size, kind='modern_packet'):
        return (event.get('event'), event.get('name'), event.get('direction'), event.get('session'),
            event.get('bytes')) == (kind, name, direction, session, size) and type(event.get('bytes')) is int
    # This realm remains at character selection. The bridge discards these
    # reports without native forwarding; their absent bodies are explicit.
    ignored = {'CMSG_REPORT_CLIENT_VARIABLES': 945, 'CMSG_REPORT_ENABLED_ADDONS': 65,
        'CMSG_REPORT_KEYBINDING_EXECUTION_COUNTS': 2, 'CMSG_BATTLE_PAY_GET_PURCHASE_LIST': 0,
        'CMSG_BATTLE_PAY_GET_PRODUCT_LIST': 0, 'CMSG_UPDATE_VAS_PURCHASE_STATES': 0}
    for name, size in ignored.items():
        pair = sorted([e for e in scoped if e.get('name') == name], key=lambda e: e['time'])
        if not pair:
            continue
        require(len(pair) == 2 and shape(pair[0], name, 'from_client', size) and
            shape(pair[1], name, None, size, 'unmapped_client_packet') and
            0 < pair[1]['time'] - pair[0]['time'] < .1 and pair[1]['time'] < since + 2,
            'post-close ignored report must be its sole immediate dropped realm pair')
        claim(pair)
    queries = (('CMSG_SERVER_TIME_OFFSET_REQUEST', 'SMSG_SERVER_TIME_OFFSET', 0, 8, False),
        ('CMSG_GET_UNDELETE_CHARACTER_COOLDOWN_STATUS', 'SMSG_UNDELETE_COOLDOWN_STATUS_RESPONSE', 0, 9, True),
        ('CMSG_SOCIAL_CONTRACT_REQUEST', 'SMSG_SOCIAL_CONTRACT_REQUEST_RESPONSE', 0, 1, True))
    for request, response, size, response_size, once in queries:
        incoming = sorted([e for e in scoped if e.get('name') == request], key=lambda e: e['time'])
        outgoing = sorted([e for e in scoped if e.get('name') == response], key=lambda e: e['time'])
        require(len(incoming) == len(outgoing) and (not once or len(incoming) <= 1) and all(
            shape(a, request, 'from_client', size) and shape(b, response, 'to_client', response_size) and
            0 < b['time'] - a['time'] < .1 and (not once or b['time'] < since + 2)
            for a, b in zip(incoming, outgoing)), 'post-close read-only query/reply occurrence differs')
        claim(incoming + outgoing)
    pings = sorted([e for e in scoped if e.get('name') in ('CMSG_PING', 'SMSG_PONG')], key=lambda e: e['time'])
    require(len(pings) % 4 == 0, 'post-close latency requires complete metadata quartets')
    for offset in range(0, len(pings), 4):
        group = pings[offset:offset + 4]
        require(shape(group[0], 'CMSG_PING', 'from_client', 8) and
            shape(group[1], 'SMSG_PONG', 'to_client', 4) and
            shape(group[2], 'CMSG_PING', 'to_native', 8, 'native_packet') and
            shape(group[3], 'SMSG_PONG', 'from_native', 4, 'native_packet') and
            all(a['time'] < b['time'] for a, b in zip(group, group[1:])) and
            group[-1]['time'] - group[0]['time'] < 2,
            'post-close latency must bind its ordinary realm/native quartet')
    claim(pings)
    enumeration = sorted([e for e in scoped if e.get('name') in
        ('CMSG_ENUM_CHARACTERS', 'SMSG_ENUM_CHARACTERS_RESULT')], key=lambda e: e['time'])
    if enumeration:
        require(len(enumeration) == 4 and shape(enumeration[0], 'CMSG_ENUM_CHARACTERS', 'from_client', 0) and
            shape(enumeration[1], 'CMSG_ENUM_CHARACTERS', 'to_native', 0, 'native_packet') and
            shape(enumeration[2], 'SMSG_ENUM_CHARACTERS_RESULT', 'from_native', 1366, 'native_packet') and
            shape(enumeration[3], 'SMSG_ENUM_CHARACTERS_RESULT', 'to_client', 2944) and
            all(a['time'] < b['time'] for a, b in zip(enumeration, enumeration[1:])) and
            enumeration[-1]['time'] < since + 2,
            'post-close audit requires the sole exact account character-list exchange')
        claim(enumeration)
    require(used == set(map(key, scoped)), 'post-close audit contains another input, movement or lifecycle event')
    raw_shapes = {
        ('CMSG_ENUM_CHARACTERS', 'from_client'): b'', ('CMSG_ENUM_CHARACTERS', 'to_native'): b'',
        ('CMSG_SOCIAL_CONTRACT_REQUEST', 'from_client'): b'',
        ('SMSG_SOCIAL_CONTRACT_REQUEST_RESPONSE', 'to_client'): b'\0',
        ('CMSG_SERVER_TIME_OFFSET_REQUEST', 'from_client'): b'',
        ('SMSG_SERVER_TIME_OFFSET', 'to_client'): bytes(8),
        ('CMSG_GET_UNDELETE_CHARACTER_COOLDOWN_STATUS', 'from_client'): b'',
        ('SMSG_UNDELETE_COOLDOWN_STATUS_RESPONSE', 'to_client'): bytes(9)}
    for row in raw:
        identity = (row['name'], row['direction'])
        if identity in raw_shapes:
            require(body(row) == raw_shapes[identity], 'post-close read-only raw body differs')
        elif identity in (('SMSG_ENUM_CHARACTERS_RESULT', 'from_native'),
                ('SMSG_ENUM_CHARACTERS_RESULT', 'to_client')):
            require(len(body(row)) == (1366 if row['direction'] == 'from_native' else 2944),
                'post-close character-list raw size differs')
        else:
            raise RuntimeError('post-close audit refuses every other raw request or native effect')
        found = [e for e in scoped if (e.get('name'), e.get('direction'), e.get('bytes')) ==
            (row['name'], row['direction'], len(body(row))) and 0 <= row['time'] - e['time'] < .1]
        require(len(found) == 1, 'post-close raw read requires its unique realm metadata')
    return {'since': since, 'until': audit_until, 'old_physical_retired': True,
        'no_gameplay_or_additional_login': True, 'source_packet_count': len(raw), 'source_packets_sha256': _digest(raw),
        'source_event_count': len(scoped), 'source_events_sha256': _digest(scoped),
        'latency_body_retained': False, 'ignored_report_bodies_retained': False,
        'latency_occurrences': len(pings) // 4, 'character_list_occurrences': len(enumeration) // 4}


def failed_history(rows, events, ready, F, audit_until):
    """Close the original physical world and audit its realm through the cutoff."""
    try:
        require(type(F) is dict and type(events) is list and all(type(e) is dict for e in events) and
            finite(audit_until), 'typed failed entry and current audit cutoff required')
        instances = [e for e in events if e.get('event') == 'instance_authenticated' and
            e.get('account_id') == 2 and finite(e.get('time')) and
            F['started_at'] <= e['time'] <= F['entry_input_finished_at']]
        require(len(instances) == 1, 'one original physical instance required for closure audit')
        physical = instances[0]['session']
        closed = [e for e in events if (e.get('event'), e.get('session')) == ('world_connection_closed', physical) and
            finite(e.get('time')) and F['started_at'] <= e['time'] <= audit_until]
        require(len(closed) == 1, 'one same-boot physical close required before current audit cutoff')
        prefix = _failed_history(rows, events, ready, F, closed[0]['time'])
        audit = _suffix(rows, events, prefix, audit_until)
        return {**prefix, 'audit_until': audit_until, 'post_close_audit': audit}
    except (KeyError, ValueError, IndexError, struct.error, OverflowError) as error:
        raise RuntimeError('failed entry closure cannot be parsed exactly') from error


def _failed_history(rows, events, ready, F, until):
    require(type(ready) is dict and type(F) is dict and
        F.get('phase') == 'bags_swap_entry_started' and F.get('completed') is False and
        type(F.get('failure')) is str and F['failure'] and F.get('qualification_added') is False and
        F.get('cases') == [] and F.get('cleanup') == [],
        'only the original failed, unqualified entry without cleanup can close')
    since, original_end, session = F['started_at'], F['entry_input_finished_at'], F['native_session']
    require(all(finite(v) for v in (since, original_end, F.get('finished_at'), until)) and
        since < original_end <= F['finished_at'] < until and
        ready.get('native_session') == session, 'failed entry chronology or ready owner differs')
    contract.owned_snapshot(ready['all_offline_snapshot'])
    inventory = ready['all_offline_snapshot']['2']['inventory']
    native = F['native_before_entry']
    pose = [native[k] for k in ('position_x', 'position_y', 'position_z', 'orientation')]
    require(all(type(v) is float and finite(v) for v in pose), 'failed original native pose must retain four floats')
    scoped = shared.packet_rows(rows, session, since, until)
    require(all(set(r) == sync.WIRE_FIELDS and r.get('direction') in sync.WIRE_DIRECTIONS and
        type(r.get('name')) is str and r['name'] for r in scoped) and
        len(set(map(key, scoped))) == len(scoped), 'failed closure requires unique canonical raw rows')
    for row in scoped:
        body(row)
    original = shared.packet_rows(F['raw_entry_packets'], session, since, original_end)
    require(sorted(map(key, shared.packet_rows(scoped, session, since, original_end))) == sorted(map(key, original)),
        'failed original raw login history must remain complete and immutable')
    require(type(events) is list and all(type(e) is dict for e in events), 'failed closure events required')
    require(all(finite(e.get('time')) for e in events if e.get('session') == session),
        'failed closure native event times must be finite')
    boot = sync.login_sync(scoped, events, session, since, original_end, pose)
    physical = boot['instance_session']
    require(all(finite(e.get('time')) for e in events if e.get('session') == physical),
        'failed closure physical event times must be finite')
    owned_events = [e for e in events if e.get('session') in (session, physical) and since <= e['time'] <= until]
    require(len(set(map(key, owned_events))) == len(owned_events), 'failed closure metadata duplicates')
    require(len([e for e in owned_events if e.get('event') == 'instance_authenticated']) == 1,
        'failed closure cannot admit another authenticated login')
    require(len([e for e in events if e.get('event') == 'instance_authenticated' and
        e.get('account_id') == 2 and finite(e.get('time')) and since <= e['time'] <= until]) == 1,
        'failed closure cannot admit a foreign actor2 authenticated login')
    player_created = [e for e in owned_events if e.get('event') == 'native_player_created']
    require(len(player_created) == 1 and player_created[0].get('session') == session and
        type(player_created[0].get('guid')) is int and player_created[0]['guid'] == 2 and
        type(player_created[0].get('map')) is int and player_created[0]['map'] == 0 and
        sync._pose(player_created[0].get('position')) == sync._pose(boot['baseline_pose']) and
        boot['self_creation']['packet']['time'] <= player_created[0]['time'] <= boot['boot_finished_at'],
        'failed closure must bind its sole actual native player creation event')
    require(not any(e.get('event') == 'native_stream_closed' for e in owned_events),
        'failed closure native stream closed before the matched timed logout')
    close = [e for e in owned_events if e.get('event') == 'world_connection_closed']
    require(len(close) == 1 and close[0]['session'] == physical and close[0]['time'] == until,
        'failed closure must end at its exact physical connection close')
    require(not any(r['name'] == contract.ACTION for r in scoped) and
        not any(e.get('name') == contract.ACTION for e in owned_events), 'failed closure cannot contain any swap')
    login_names = ('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD')
    require(sorted(map(key, [r for r in scoped if r['name'] in login_names])) ==
        sorted(map(key, boot['login_packets'])), 'failed closure requires its sole original login')
    late = [r for r in scoped if r['time'] > F['finished_at']]
    quartet = [_one(late, name, direction, raw) for name, direction, raw in (
        ('CMSG_STAND_STATE_CHANGE', 'from_client', b'\x01'),
        ('CMSG_STANDSTATECHANGE', 'to_native', b'\x01\0\0\0'),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', b'\x01'),
        ('SMSG_STAND_STATE_UPDATE', 'to_client', b'\x01\0\0\0\0'))]
    require(len([r for r in scoped if r['name'] in STAND_NAMES]) == 4,
        'failed closure permits the sole automatic sit quartet, no cleanup stand')
    _ordered(quartet)
    modern = _one(scoped, 'CMSG_LOGOUT_REQUEST', 'from_client', b'\x80')
    request = _one(scoped, 'CMSG_LOGOUT_REQUEST', 'to_native', b'')
    response = _one(scoped, 'SMSG_LOGOUT_RESPONSE', 'from_native', bytes(5))
    delivered_response = _one(scoped, 'SMSG_LOGOUT_RESPONSE', 'to_client', bytes(5))
    root = _one(scoped, 'SMSG_MOVE_ROOT', 'from_native', bytes.fromhex('100300000000'))
    complete = _one(scoped, 'SMSG_LOGOUT_COMPLETE', 'from_native', b'')
    delivered_complete = _one(scoped, 'SMSG_LOGOUT_COMPLETE', 'to_client', b'\0')
    _ordered([modern, request, response, delivered_response, root])
    require(quartet[-1]['time'] < modern['time'] and root['time'] < complete['time'] <
        delivered_complete['time'] < until and 19 <= complete['time'] - request['time'] <= 21 and
        until - delivered_complete['time'] < 1,
        'failed closure must be the observed idle then ordinary timed logout')
    logout_rows = [modern, request, response, delivered_response, root, complete, delivered_complete]
    require(len([r for r in scoped if r['name'] in LOGOUT_NAMES or r['name'] == 'SMSG_MOVE_ROOT']) == 7,
        'failed closure has extra logout or root packets')
    for row in scoped:
        if row['time'] <= original_end:
            continue
        if (row['name'], row['direction']) == ('SMSG_MOVE_UPDATE', 'to_client'):
            reader = Reader(body(row))
            low, high = reader.guid()
            require((low, high) != (2, shared.player_high()) and high >> 58 in (8, 11),
                'failed closure delivered movement for its owner or another player')
            continue
        require(not row['name'].startswith(('SMSG_MOVE_', 'SMSG_SPLINE_MOVE_', 'MSG_MOVE_')) or
            key(row) == key(root), 'failed closure has another native or delivered movement effect')
        if row['name'] == 'SMSG_ON_MONSTER_MOVE':
            reader = Reader(body(row))
            identity = native_guid(reader) if row['direction'] == 'from_native' else reader.guid()[0]
            require(identity != 2, 'failed closure server spline moved its owner')
    base = _original(original, inventory)
    current = deepcopy(base)
    owned_native_rows, idle_effect, logout_effect = [], [], []
    for row in sorted([r for r in scoped if r['time'] > original_end], key=lambda r: r['time']):
        decoded = _owned_records(row, set(base))
        if decoded:
            owned_native_rows.append(row)
        for record in decoded:
            identity = record['guid']
            require(record['update_type'] == 0, 'failed closure cannot recreate any owned object')
            changed = {index: value for index, value in record.get('fields', {}).items()
                if value != current[identity].get(index, 0)}
            if changed:
                if identity == 2 and changed == {INDEX['UNIT_FIELD_BYTES_1']: 1, INDEX['PLAYER_FLAGS']: 2}:
                    require(not idle_effect and not logout_effect and quartet[-1]['time'] <= row['time'] <
                        quartet[-1]['time'] + 2, 'automatic seated/AFK effect is early, repeated or late')
                    idle_effect.append(row)
                elif identity == 2 and changed == {INDEX['UNIT_FIELD_FLAGS']: base[2][INDEX['UNIT_FIELD_FLAGS']] | STUNNED}:
                    require(len(idle_effect) == 1 and not logout_effect and root['time'] < row['time'] <
                        root['time'] + 2, 'native stunned effect must follow this logout root packet')
                    logout_effect.append(row)
                else:
                    raise RuntimeError('failed closure changed another complete native owner/item field')
            current[identity].update(record.get('fields', {}))
    require(len(idle_effect) == len(logout_effect) == 1,
        'failed closure requires sole seated/AFK and logout stunned effects')
    afk = [e for e in owned_events if e.get('name') in AFK_NAMES]
    require(len(afk) == 2 and [(e.get('event'), e.get('name'), e.get('direction'),
        e.get('session'), e.get('bytes')) for e in afk] ==
        [('modern_packet', AFK_NAMES[0], 'from_client', session, 5),
         ('native_packet', AFK_NAMES[1], 'to_native', session, 5)] and
        all(type(e.get('bytes')) is int for e in afk) and
        quartet[1]['time'] <= afk[0]['time'] < afk[1]['time'] <= idle_effect[0]['time'] and
        afk[1]['time'] - afk[0]['time'] < .1,
        'automatic AFK requires its sole metadata-only native forwarding pair')
    relevant_rows = quartet + logout_rows + owned_native_rows
    matched = _metadata(relevant_rows, owned_events, session, physical)
    unparsed_moves = [e for e in owned_events if e['time'] > original_end and
        (e.get('name'), e.get('direction'), e.get('session'), e.get('event')) ==
        ('SMSG_MOVE_UPDATE', 'to_client', physical, 'modern_packet')]
    require(all(type(e.get('bytes')) is int and e['bytes'] > 0 for e in unparsed_moves),
        'delivered movement metadata must retain its honest byte length')
    movement_metadata_keys = set(map(key, matched + unparsed_moves))
    require(all(key(e) in movement_metadata_keys for e in owned_events if e['time'] > original_end and
        str(e.get('name', '')).startswith(('SMSG_MOVE_', 'SMSG_SPLINE_MOVE_', 'MSG_MOVE_'))),
        'failed closure movement metadata has an unbound native or delivered effect')
    permit_raw = set(map(key, quartet[:2]))
    permit_events = set(map(key, matched + afk))
    contract.forbidden_packets([r for r in scoped if key(r) not in permit_raw], session, since, until, login_sync=boot)
    for owner in (session, physical):
        contract.forbidden_packets([e for e in owned_events if key(e) not in permit_events], owner,
            since, until, login_sync=boot)
    post_events = [e for e in owned_events if e['time'] > F['finished_at']]
    ignored = _ignored_metadata(post_events, session, physical)
    routine = [r for r in late if r['direction'] in ('from_client', 'to_native') and r['name'] in ROUTINE]
    require(all(len(body(r)) == ROUTINE[r['name']] for r in routine), 'routine read-only request shape differs')
    routine_metadata = _routine_metadata(routine, post_events, session, physical)
    permitted = permit_events | set(map(key, ignored + routine_metadata))
    require(all(r['name'] in ROUTINE or key(r) in permit_raw or key(r) in set(map(key, [modern, request]))
        for r in late if r['direction'] in ('from_client', 'to_native')),
        'failed closure admits no housekeeping or other post-failure input')
    permitted.update(map(key, _metadata([modern, request], owned_events, session, physical)))
    require(all(key(e) in permitted for e in post_events if e.get('direction') in ('from_client', 'to_native')),
        'failed closure metadata contains another post-failure input')
    replay = shared.native_replay(scoped, session, since, until)
    threshold = base[2].get(INDEX['PLAYER_REST_STATE_EXPERIENCE'], 0)
    require(replay['rest_threshold'] == threshold, 'failed closure rest threshold differs')
    retained_rows = sorted({key(r): r for r in boot['source_packets'] +
        [r for r in original if _owned_records(r, set(base))] + relevant_rows}.values(), key=lambda r: r['time'])
    retained_events = sorted({key(e): e for e in boot['source_events'] + matched + afk + close + player_created}.values(),
        key=lambda e: e['time'])
    native_state = {k: replay[k] for k in ('owner', 'health', 'max_health', 'powers', 'xp', 'xp_cap',
        'resting', 'summon', 'rest_threshold', 'rest_state')}
    initial_state = {**native_state, 'pose': {'stand': 0, 'sheath': 0}, 'afk': False,
        'unit_flags': base[2][INDEX['UNIT_FIELD_FLAGS']], 'native_rooted': False}
    final_state = {**native_state, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True,
        'unit_flags': current[2][INDEX['UNIT_FIELD_FLAGS']], 'native_rooted': True}
    return deepcopy({'schema': SCHEMA, 'qualification_excluded': True, 'session': session,
        'instance_session': physical, 'since': since, 'until': until, 'login_sync': boot,
        'rest_threshold': threshold, 'native_original': initial_state, 'native_final': final_state,
        'original_sql_inventory': inventory, 'original_objects': _json_objects(base),
        'final_objects': _json_objects(current), 'all_native_item_fields_unchanged': True,
        'all_native_inventory_slots_unchanged': True, 'no_swap_or_cleanup_input': True,
        'automatic_idle': {'stand_packets': quartet, 'owner_update': idle_effect[0],
            'afk_metadata': afk, 'afk_body_retained': False},
        'logout': {'modern': modern, 'native': request, 'response': response,
            'delivered_response': delivered_response, 'root': root, 'owner_update': logout_effect[0],
            'complete': complete, 'delivered_complete': delivered_complete, 'connection_closed': close[0]},
        'allowed_packet_keys': sorted(map(key, quartet[:2] + owned_native_rows)),
        'allowed_metadata_keys': sorted(map(key, matched + afk)),
        'source_packet_count': len(scoped), 'source_packets_sha256': _digest(scoped),
        'source_event_count': len(owned_events), 'source_events_sha256': _digest(owned_events),
        'metadata_only_delivered_movement_count': len(unparsed_moves),
        'metadata_only_delivered_movement_bodies_retained': False,
        'source_packets': retained_rows, 'source_events': retained_events})

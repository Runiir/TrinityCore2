"""Pure exclusion replay for source-selected UI176 and UI178 normal logouts.

The callback is only for isolated diagnostics. Production defaults to the
approved standard v2 module. No legacy module or historical receipt is changed.
"""
from copy import deepcopy
import hashlib
import importlib.util
import json
from pathlib import Path
import re

from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_login_sync_v2 as sync
from tools.client_compatibility import bag_swap_preservation as preservation
from tools.client_compatibility import item_actionbar_contract as shared
from tools.client_compatibility import bag_swap_failed_journals as journals
from tools.client_compatibility import bag_swap_stopped_contract as stopped_native
from tools.client_compatibility import interaction_bag_swap_idle_housekeeping as idle_contract
from tools.client_compatibility.bag_swap_failed_contract import (
    _one, _ordered, _metadata, _routine_metadata, _routine_native, _ignored_metadata,
    _original, _owned_records, _json_objects, _digest, STAND_NAMES,
    AFK_NAMES, LOGOUT_NAMES, STUNNED, ROUTINE)
from tools.client_compatibility.world.buffer import Reader, Writer, player_high
from tools.client_compatibility.world.native_objects import guid as native_guid
from tools.client_compatibility.world.gameobjects import modern_guid

SCHEMA = 'client442_bag_swap_closed_logout_history_v1'
require, finite, body, key = shared.require, shared.finite, shared.body, sync.packet_key
INDEX = shared.INDEX
MAX_ROWS = 250000
BOOT_EFFECTS = frozenset(('movement_forwarded', 'native_active_mover_confirmed',
    'active_mover_deferred_until_player_create'))
COMBAT_EFFECTS = frozenset(('SMSG_ATTACKER_STATE_UPDATE', 'SMSG_SPELL_START', 'SMSG_SPELL_GO',
    'SMSG_AURA_UPDATE', 'SMSG_AURA_UPDATE_ALL'))
ATTACK_EFFECTS = frozenset(('SMSG_ATTACK_START', 'SMSG_ATTACK_STOP'))
OBJECT_EFFECTS = frozenset(('SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT', 'SMSG_STAND_STATE_UPDATE'))
OWNER_EFFECTS = frozenset(('SMSG_LEARNED_SPELL', 'SMSG_LEARNED_SPELLS', 'SMSG_REMOVED_SPELL',
    'SMSG_SUPERCEDED_SPELL', 'SMSG_SEND_KNOWN_SPELLS', 'SMSG_SEND_UNLEARN_SPELLS',
    'SMSG_UPDATE_ACTION_BUTTONS', 'SMSG_SET_PROFICIENCY'))


def load_login_provider(path):
    """Load a bounded, explicit pure v2 candidate without replacing any module."""
    path = Path(path)
    with path.open('rb') as stream:
        raw = stream.read(2 * 1024 * 1024 + 1)
    require(len(raw) <= 2 * 1024 * 1024, 'bounded login classifier source required')
    spec = importlib.util.spec_from_file_location(
        'tools.client_compatibility._closed_logout_candidate_v2', path)
    module = importlib.util.module_from_spec(spec)
    exec(compile(raw, str(path), 'exec'), module.__dict__)
    require(module.SCHEMA == sync.SCHEMA, 'exact v2 classifier callback required')
    module.candidate_source = {'path': str(path), 'sha256': hashlib.sha256(raw).hexdigest()}
    return module


def ordered_digest(rows):
    digest = hashlib.sha256(b'[')
    for index, row in enumerate(rows):
        if index:
            digest.update(b',')
        digest.update(key(row).encode())
    digest.update(b']')
    return digest.hexdigest()


def _guard(rows, owner, since, until, *, login_sync, events, provider):
    """Bind all actual metadata before excluding exact inert startup rows.

    Callback reconstruction replaces only the standard dispatch during this
    isolated candidate. The remaining stock mutation guard receives all other
    actual rows; the immutable prefix and full metadata are separately exact.
    """
    require(provider.SCHEMA == sync.SCHEMA and type(events) is list and events,
        'v2 input authority requires complete actual metadata')
    proof = provider.validate_login_sync(login_sync, events=events)
    require(owner in (proof['session'], proof['instance_session']), 'input guard owner differs')
    allowed = set(proof['allowed_packet_keys']) | set(proof['allowed_metadata_keys'])
    attributed = [row for row in events if since <= row['time'] <= until and
        (row.get('session') in (proof['session'], proof['instance_session']) or
            row.get('account_id') == 2 or row.get('guid') == 2)]
    require(all(key(row) in allowed for row in attributed if row.get('event') in BOOT_EFFECTS),
        'every owned mover lifecycle effect must be one exact v2 startup allowance')
    require(not any(row.get('event') in ('cast_forwarded', 'cast_translation_rejected',
        'item_use_forwarded', 'item_use_translation_rejected', 'native_player_resurrected')
        for row in attributed), 'no additional owned cast, item-use or resurrection lifecycle is allowed')
    filtered = [row for row in rows if key(row) not in allowed]
    return contract.forbidden_packets(filtered, owner, since, until)


def _native_effects(packets, events, session, physical, prefix_end):
    """Bind sensitive effects to retained bodies before interpreting attribution.

    Native combat/aura layouts are parsed by the existing owner-aware reader.
    Spell learning and owner initialization have no NPC interpretation after
    startup. Other cast-effect layouts have no exclusion allowance here.
    """
    def sensitive(row):
        name = row.get('name')
        return name in COMBAT_EFFECTS | ATTACK_EFFECTS | OBJECT_EFFECTS | OWNER_EFFECTS or (
            type(name) is str and (name.startswith(('SMSG_SPELL', 'SMSG_LEARNED_SPELL',
                'SMSG_MOVE_', 'SMSG_SPLINE_MOVE_', 'SMSG_ON_MONSTER_MOVE')) or
                (name.startswith('MSG_MOVE_') and row.get('direction') in ('from_native', 'to_client'))))
    raw = [row for row in packets if sensitive(row)]
    # The recorder deliberately omits delivered position-update bodies. Their
    # separate NPC spline pairing below never asserts those bytes were saved.
    metadata = [row for row in events if sensitive(row) and not
        (row.get('name') == 'SMSG_MOVE_UPDATE' and row.get('direction') == 'to_client')]
    require(all(row['direction'] in ('from_native', 'to_client') for row in raw),
        'sensitive native effects require a native or delivered server path')
    require(all(row.get('event') in ('native_packet', 'modern_packet') and
        row.get('direction') in ('from_native', 'to_client') for row in metadata),
        'sensitive effect metadata requires its native or delivered server path')
    require(not any(row['time'] > prefix_end and (row['name'] in OWNER_EFFECTS or
        row['name'].startswith(('SMSG_SPELL', 'SMSG_LEARNED_SPELL')) and row['name'] not in COMBAT_EFFECTS)
        for row in raw + metadata), 'no post-prefix spell-learning or unsupported native cast effect is allowed')
    identities = {(row['name'], row['direction'], len(body(row))) for row in raw}
    require(all((row['name'], row['direction'], row['bytes']) in identities for row in metadata),
        'captured native effect metadata cannot omit its raw body occurrence')
    stopped_native._reconcile_raw(raw, metadata, session, physical)
    # This bridge delivers spell casts only for its owned caster. Native NPC
    # cast bodies can be independently parsed; their presence is not a permit
    # for a new delivered owner cast. Aura delivery is the observed logout
    # slot-zero removal, with its complete canonical translation and body.
    late_delivery = [row for row in raw if row['time'] > prefix_end and row['direction'] == 'to_client']
    require(not any(row['name'] in ATTACK_EFFECTS | {'SMSG_ATTACKER_STATE_UPDATE'} for row in late_delivery),
        'no post-prefix delivered melee or attack-control effect is allowed')
    require(not any(row['name'] in ('SMSG_SPELL_START', 'SMSG_SPELL_GO') for row in late_delivery),
        'no post-prefix delivered owner cast effect is allowed')
    clear = [row for row in raw if row['time'] > prefix_end and
        (row['name'], row['direction'], body(row)) ==
        ('SMSG_AURA_UPDATE', 'from_native', bytes.fromhex('01020000000000'))]
    delivered_clear = Writer().bits(0, 1).bits(1, 9).flush().pack('B', 0).bits(0, 1).flush().guid(2, player_high()).finish()
    delivered_auras = [row for row in late_delivery if row['name'] in ('SMSG_AURA_UPDATE', 'SMSG_AURA_UPDATE_ALL')]
    require(len(delivered_auras) <= 1 and all(len(clear) == 1 and row['name'] == 'SMSG_AURA_UPDATE' and
        body(row) == delivered_clear and 0 < row['time'] - clear[0]['time'] < .1 for row in delivered_auras),
        'post-prefix delivered aura must be the exact native logout slot-zero clear translation')
    return {'all_captured_sensitive_effect_bodies_reconciled': True,
        'no_post_prefix_owner_initialization_or_unsupported_cast': True,
        'no_additional_delivered_owner_cast': True, 'delivered_logout_aura_clear_count': len(delivered_auras)}


def _native_attack(row, wanted, *, original=False):
    """Fully consume native attack control before excluding both participants."""
    if row['name'] not in ATTACK_EFFECTS or row['direction'] != 'from_native':
        return
    reader = Reader(body(row))
    if row['name'] == 'SMSG_ATTACK_START':
        attacker, victim = reader.unpack('QQ')
    else:
        attacker, victim = native_guid(reader), native_guid(reader)
        dead, = reader.unpack('I')
        require(dead in (0, 1), 'native attack-stop death flag must be canonical')
    reader.end()
    require(original or not {attacker, victim} & wanted,
        'closed native attack control involved the owner or its inventory')


def _spline_updates(packets, events, session, physical, wanted, map_id):
    """Bind each metadata-only NPC position update to its two retained splines."""
    native = [row for row in packets if (row['name'], row['direction']) ==
        ('SMSG_ON_MONSTER_MOVE', 'from_native')]
    delivered = [row for row in packets if (row['name'], row['direction']) ==
        ('SMSG_ON_MONSTER_MOVE', 'to_client')]
    updates = [row for row in events if row.get('name') == 'SMSG_MOVE_UPDATE' and
        row.get('direction') == 'to_client']
    require(len(native) == len(delivered) == len(updates),
        'metadata-only position updates require every retained native and delivered NPC spline pair')
    require(all(all(a['time'] < b['time'] for a, b in zip(stream, stream[1:]))
        for stream in (native, updates, delivered)),
        'metadata-only position updates require ordered unique native and delivered spline streams')
    for incoming, event, outgoing in zip(native, updates, delivered):
        identity = native_guid(Reader(body(incoming)))
        target = Reader(body(outgoing)).guid()
        require(identity not in wanted and target == modern_guid(identity, map_id) and target[1] >> 58 in (8, 11),
            'metadata-only position update must belong to the same body-bound NPC spline')
        require(set(event) == {'event', 'session', 'time', 'name', 'direction', 'bytes'} and
            event['event'] == 'modern_packet' and event['session'] == physical and
            type(event['bytes']) is int and event['bytes'] == len(Writer().guid(*target).finish()) + 49 and
            incoming['session'] == outgoing['session'] == session and
            incoming['time'] < event['time'] < outgoing['time'] < incoming['time'] + .1,
            'metadata-only position update must be the canonical ordered native-to-delivered NPC spline occurrence')
    return {'metadata_only_delivered_position_update_count': len(updates),
        'delivered_position_update_bodies_retained': False,
        'delivered_position_updates_bound_to_retained_npc_splines': True}


def _routine_shape(row):
    if (row['name'], row['direction']) == ('CMSG_QUEST_GIVER_STATUS_QUERY', 'from_client'):
        return len(_routine_native(row)) == 8
    return len(body(row)) == ROUTINE[row['name']]


def _lobby(rows, events, prefix, audit_until):
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
    ignored = {'CMSG_REPORT_CLIENT_VARIABLES': 946, 'CMSG_REPORT_ENABLED_ADDONS': 65,
        'CMSG_REPORT_KEYBINDING_EXECUTION_COUNTS': 21, 'CMSG_BATTLE_PAY_GET_PURCHASE_LIST': 0,
        'CMSG_BATTLE_PAY_GET_PRODUCT_LIST': 0, 'CMSG_UPDATE_VAS_PURCHASE_STATES': 0}
    for name, size in ignored.items():
        pair = sorted([e for e in scoped if e.get('name') == name], key=lambda e: e['time'])
        if not pair:
            continue
        require(len(pair) == 2 and shape(pair[0], name, 'from_client', size) and
            shape(pair[1], name, None, size, 'unmapped_client_packet') and
            0 < pair[1]['time'] - pair[0]['time'] < .1 and pair[1]['time'] < since + 5,
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
            0 < b['time'] - a['time'] < .1 and (not once or b['time'] < since + 5)
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
            enumeration[-1]['time'] < since + 5,
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


def _prefix_history(rows, events, ready, F, until, provider, profile):
    sync = provider
    require(type(ready) is dict and type(F) is dict and
        F.get('phase') == ('bags_swap_entered' if profile == 'ui178_finalization' else
            'bags_swap_entry_started') and F.get('completed') is False and
        type(F.get('failure')) is str and F['failure'] and F.get('qualification_added') is False and
        F.get('cases') == [] and F.get('cleanup') == [],
        'only the original failed, unqualified entry without cleanup can close')
    since, original_end, session = F['started_at'], F['entry_input_finished_at'], F['native_session']
    if profile == 'ui178_finalization':
        original_end = F['login_sync']['until']
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
    original = shared.packet_rows(scoped if profile == 'ui178_finalization' else
        F['raw_entry_packets'], session, since, original_end)
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
    if profile == 'ui178_finalization':
        quartet = [_one(late, 'SMSG_STAND_STATE_UPDATE', direction, raw) for direction, raw in
            (('from_native', b'\x01'), ('to_client', b'\x01\0\0\0\0'))]
        require(len([r for r in scoped if r['name'] in STAND_NAMES]) == 2,
            'finalization closure permits only the two server-side logout sit packets')
    else:
        quartet = [_one(late, name, direction, raw) for name, direction, raw in (
            ('CMSG_STAND_STATE_CHANGE', 'from_client', b'\x01'),
            ('CMSG_STANDSTATECHANGE', 'to_native', b'\x01\0\0\0'),
            ('SMSG_STAND_STATE_UPDATE', 'from_native', b'\x01'),
            ('SMSG_STAND_STATE_UPDATE', 'to_client', b'\x01\0\0\0\0'))]
        require(len([r for r in scoped if r['name'] in STAND_NAMES]) == 4,
            'failed closure permits the sole automatic sit quartet, no cleanup stand')
    _ordered(quartet)
    modern = _one(scoped, 'CMSG_LOGOUT_REQUEST', 'from_client', b'\0')
    request = _one(scoped, 'CMSG_LOGOUT_REQUEST', 'to_native', b'')
    response = _one(scoped, 'SMSG_LOGOUT_RESPONSE', 'from_native', bytes(5))
    delivered_response = _one(scoped, 'SMSG_LOGOUT_RESPONSE', 'to_client', bytes(5))
    root = _one(scoped, 'SMSG_MOVE_ROOT', 'from_native', bytes.fromhex('100300000000'))
    complete = _one(scoped, 'SMSG_LOGOUT_COMPLETE', 'from_native', b'')
    delivered_complete = _one(scoped, 'SMSG_LOGOUT_COMPLETE', 'to_client', b'\0')
    _ordered([modern, request, response, delivered_response, root])
    require((delivered_response['time'] < quartet[0]['time'] < quartet[-1]['time'] < root['time']
        if profile == 'ui178_finalization' else quartet[-1]['time'] < modern['time']) and
        root['time'] < complete['time'] <
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
                if profile == 'ui178_finalization':
                    require(identity == 2 and changed == {INDEX['UNIT_FIELD_BYTES_1']: 1,
                        INDEX['UNIT_FIELD_FLAGS']: base[2][INDEX['UNIT_FIELD_FLAGS']] | STUNNED} and
                        not logout_effect and root['time'] < row['time'] < root['time'] + 2,
                        'finalization closure permits only the combined server sit and logout stunned effect')
                    logout_effect.append(row)
                elif identity == 2 and changed == {INDEX['UNIT_FIELD_BYTES_1']: 1, INDEX['PLAYER_FLAGS']: 2}:
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
    require(len(logout_effect) == 1 and len(idle_effect) ==
        (0 if profile == 'ui178_finalization' else 1),
        'failed closure requires its exact observed idle/logout owner transitions')
    afk = [e for e in owned_events if e.get('name') in AFK_NAMES]
    if profile == 'ui178_finalization':
        require(not afk, 'finalization closure cannot invent automatic AFK input')
    else:
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
    permit_raw = set(map(key, [] if profile == 'ui178_finalization' else quartet[:2]))
    permit_events = set(map(key, matched + afk))
    _guard([r for r in scoped if key(r) not in permit_raw], session, since, until, login_sync=boot, events=owned_events, provider=provider)
    for owner in (session, physical):
        _guard([e for e in owned_events if key(e) not in permit_events], owner,
            since, until, login_sync=boot, events=owned_events, provider=provider)
    post_events = [e for e in owned_events if e['time'] > F['finished_at']]
    ignored = _ignored_metadata(post_events, session, physical)
    routine = [r for r in late if r['direction'] in ('from_client', 'to_native') and r['name'] in ROUTINE]
    require(all(_routine_shape(r) for r in routine), 'routine read-only request shape differs')
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
    final_state = {**native_state, 'pose': {'stand': 1, 'sheath': 0},
        'afk': profile != 'ui178_finalization',
        'unit_flags': current[2][INDEX['UNIT_FIELD_FLAGS']], 'native_rooted': True}
    return deepcopy({'schema': SCHEMA, 'qualification_excluded': True, 'session': session,
        'instance_session': physical, 'since': since, 'until': until, 'login_sync': boot,
        'rest_threshold': threshold, 'native_original': initial_state, 'native_final': final_state,
        'original_sql_inventory': inventory, 'original_objects': _json_objects(base),
        'final_objects': _json_objects(current), 'all_native_item_fields_unchanged': True,
        'all_native_inventory_slots_unchanged': True, 'no_swap_or_cleanup_input': True,
        'automatic_idle': None if profile == 'ui178_finalization' else
            {'stand_packets': quartet, 'owner_update': idle_effect[0],
             'afk_metadata': afk, 'afk_body_retained': False},
        'logout': {'modern': modern, 'native': request, 'response': response,
            'delivered_response': delivered_response, 'root': root, 'owner_update': logout_effect[0],
            'complete': complete, 'delivered_complete': delivered_complete, 'connection_closed': close[0],
            **({'server_sit_packets': quartet} if profile == 'ui178_finalization' else {})},
        'allowed_packet_keys': sorted(map(key, ([] if profile == 'ui178_finalization' else
            quartet[:2]) + owned_native_rows)),
        'allowed_metadata_keys': sorted(map(key, matched + afk)),
        'source_packet_count': len(scoped), 'source_packets_sha256': _digest(scoped),
        'source_event_count': len(owned_events), 'source_events_sha256': _digest(owned_events),
        'metadata_only_delivered_movement_count': len(unparsed_moves),
        'metadata_only_delivered_movement_bodies_retained': False,
        'source_packets': retained_rows, 'source_events': retained_events})



def _reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'} and
        type(value['path']) is str and Path(value['path']).is_absolute() and
        type(value['sha256']) is str and re.fullmatch('[0-9a-f]{64}', value['sha256']),
        'typed source-owned original reference required')
    return deepcopy(value)


def _stop(ready, failed, stop, profile):
    require(type(ready) is dict and type(failed) is dict and type(stop) is dict and
        ready.get('phase') == 'bags_swap_scout_ready' and ready.get('completed') is True and
        ready.get('failure') is None and ready.get('controller') == 'code' and
        failed.get('failure') == ('RuntimeError: one complete owned modern/native login chain is required'
            if profile == 'ui178_finalization' else
            'RuntimeError: login settlement must be one ordered two-second initial prefix') and
        stop.get('schema') == 'client442_laya_interactions_v1' and
        stop.get('phase') == 'bags_swap_failed_entry_closed_paused' and
        stop.get('completed') is True and stop.get('failure') is None and
        stop.get('controller') == 'code_diagnostic_ordinary_inputs' and
        stop.get('stop_attempted') is stop.get('recovery_only') is stop.get('failed_whole_excluded') is True,
        'actual ready, immutable failed entry and excluded ordinary owned stop required')
    require(all(value.get(name) is False for value in (ready, failed, stop)
        for name in ('mutation_sent', 'qualification_added')) and
        stop.get('input_sent') is stop.get('bag_input_sent') is False and
        all(value.get('model') is value.get('revision') is None and value.get('fine_tuned') is False and
            value.get('custom_script_permission') == 'blocked_by_user' for value in (ready, failed, stop)),
        'original controller/script/exclusion labels differ')
    require(type(stop.get('shutdown_checks')) is dict and set(stop['shutdown_checks']) == journals.CHECKS and
        all(value is True for value in stop['shutdown_checks'].values()), 'all eight actual stop checks required')
    require(all(contract.strict_equal(value.get(name), ready.get(name)) for value in (failed, stop)
        for name in ('actor', 'runtime', 'code_commit')) and
        failed.get('native_session') == ready.get('native_session'), 'actual actor and runtime epoch differ')
    chronology = [ready['finished_at'], failed['started_at'], failed['entry_input_finished_at'],
        failed['finished_at'], stop['started_at'], stop['stop_started_at'], stop['stop_finished_at'], stop['finished_at']]
    require(all(finite(value) for value in chronology) and
        all(a < b for a, b in zip(chronology, chronology[1:])), 'actual source/owned-stop chronology differs')
    baseline = ready['all_offline_snapshot']
    require(contract.strict_equal(failed.get('all_offline_snapshot'), baseline) and
        contract.strict_equal(failed.get('native_before_entry'), baseline['2']['native']) and
        contract.strict_equal(stop.get('before'), stop.get('after')) and
        contract.strict_equal(stop.get('before'), stop.get('all_offline_snapshot')),
        'complete original baseline or stop snapshots differ')
    preservation._preserved(baseline, stop['after'])
    for name in ('exact_precision_before', 'exact_precision_after'):
        preservation.exact_precision(stop[name], stop['after'])
    require(contract.strict_equal(stop['exact_precision_before'], stop['exact_precision_after']),
        'owned stop changed the exact captured FLOAT bits')
    game = stop['game_before']
    require(type(game) is dict and set(game) == {'pid', 'start_ticks'} and type(game['pid']) is int and
        game['pid'] == ready['frame']['monitor']['input_isolation']['game_pid'] and
        type(game['start_ticks']) is str and re.fullmatch('[1-9][0-9]*', game['start_ticks']),
        'actual source-owned game PID/ticks required')
    require(stop['frame']['monitor'].get('second_monitor_verified') is True and
        stop['frame']['monitor']['monitor'].get('name') == 'HDMI-1', 'original owned monitor proof differs')
    preparation = _reference(failed.get('preparation_source'))
    require(preparation == stop.get('preparation_source'), 'original preparation source differs')
    refs = {'preparation': preparation, 'precision': _reference(failed.get('precision_source')),
        'failed_entry': _reference(stop.get('first_failure_source')), 'logout': _reference(stop.get('source'))}
    return refs


def _finalization_prefix(prefix, prefix_events, ready, failed, provider):
    require(failed.get('phase') == 'bags_swap_entered' and failed.get('completed') is False and
        failed.get('failure') == failed.get('entry_finalization_failure') ==
        'RuntimeError: one complete owned modern/native login chain is required' and
        type(failed.get('raw_entry_packets')) is list and not failed['raw_entry_packets'] and
        contract.strict_equal(prefix_events, failed.get('raw_entry_events')) and prefix,
        'original failed finalization labels and complete retained metadata must remain unchanged')
    expected = {'ordinary_login', 'native_owner', 'saved_baseline', 'protected_actors',
        'public_level1', 'empty_cursor'}
    require(type(failed.get('checks')) is dict and set(failed['checks']) == expected and
        all(value is True for value in failed['checks'].values()),
        'all six original successful pre-finalization checks must be retained')
    retained = failed['login_sync']
    require(retained.get('since') == failed['started_at'] and
        retained.get('session') == ready['native_session'] and
        finite(retained.get('until')) and retained['boot_finished_at'] <= retained['until'] <
        failed['entry_input_finished_at'], 'original successful v2 proof window differs')
    provider.validate_login_sync(retained, events=prefix_events)
    pose = [failed['native_before_entry'][name] for name in
        ('position_x', 'position_y', 'position_z', 'orientation')]
    rebuilt = provider.login_sync(prefix, prefix_events, ready['native_session'],
        failed['started_at'], retained['until'], pose)
    require(contract.strict_equal(rebuilt, retained) and
        contract.strict_equal(retained['login_packets'], failed.get('login_packets')),
        'all original successful v2 boot/login bytes must match the complete source journal')
    owner = contract.native_replay(prefix, ready['native_session'], failed['started_at'],
        retained['until'], login_sync=retained, events=prefix_events)
    require(contract.strict_equal(owner, failed.get('native_owner_proof')) and
        contract.strict_equal(owner['packets'], failed.get('owner_packets')),
        'original successful native-owner proof bytes must match the complete source journal')


def closed_history(packets, events, ready, failed, stop, *, login_provider=None,
        provenance_profile='ui176'):
    """Return exclusion metadata only; source-byte admission belongs to the provider."""
    try:
        require(type(provenance_profile) is str and
            provenance_profile in ('ui176', 'ui178_finalization'),
            'explicit supported closed-history provenance profile required')
        return _closed_history(packets, events, ready, failed, stop, login_provider or sync,
            provenance_profile)
    except (KeyError, ValueError, TypeError, IndexError, OverflowError) as error:
        raise RuntimeError('closed normal logout history cannot be parsed exactly') from error


def _closed_history(packets, events, ready, failed, stop, provider, profile):
    require(type(packets) is list and type(events) is list and
        len(packets) <= MAX_ROWS and len(events) <= MAX_ROWS, 'bounded complete journals required')
    journals._rows(packets, True)
    journals._rows(events, False)
    refs = _stop(ready, failed, stop, profile)
    require(provider.SCHEMA == sync.SCHEMA, 'approved v2 initializer classifier required')
    require(all(row['time'] <= stop['finished_at'] for row in packets + events),
        'journal contains rows after the frozen stop cutoff')
    since, prefix_end, session = failed['started_at'], failed['entry_input_finished_at'], ready['native_session']
    prefix = [row for row in packets if since <= row['time'] <= prefix_end]
    prefix_events = [row for row in events if since <= row['time'] <= prefix_end]
    if profile == 'ui178_finalization':
        _finalization_prefix(prefix, prefix_events, ready, failed, provider)
    else:
        require(contract.strict_equal(prefix, failed.get('raw_entry_packets')) and
            contract.strict_equal(prefix_events, failed.get('raw_entry_events')),
            'complete ordered failed prefixes differ')
    require(all(row['session'] == session for row in packets), 'RAW native-owner attribution differs')
    pose = [failed['native_before_entry'][name] for name in ('position_x', 'position_y', 'position_z', 'orientation')]
    boot = provider.login_sync(prefix, prefix_events, session, since, prefix_end, pose)
    provider.validate_login_sync(boot, events=prefix_events)
    physical = boot['instance_session']
    require(all(row.get('event') in ('native_packet', 'modern_packet', 'unmapped_client_packet',
        'world_connection_closed', 'native_stream_closed') and
        row.get('guid') != 2 and row.get('account_id') != 2
        for row in events if row['time'] > prefix_end),
        'post-prefix metadata has an additional attributable lifecycle or unknown native effect')
    # UI178's first successful proof is the original startup cutoff. The
    # longer failed-finalization interval is rederived, never a broader permit.
    effect_end = failed['login_sync']['until'] if profile == 'ui178_finalization' else prefix_end
    base = _original([row for row in prefix if row['time'] <= effect_end],
        ready['all_offline_snapshot']['2']['inventory'])
    effect_guard = _native_effects(packets, events, session, physical, effect_end)
    effect_guard.update(_spline_updates(packets, events, session, physical, set(base),
        failed['native_before_entry']['map']))
    aura_clear = [row for row in packets if row['time'] > effect_end and
        (row['name'], row['direction'], body(row)) == ('SMSG_AURA_UPDATE', 'from_native', bytes.fromhex('01020000000000'))]
    require(len(aura_clear) == 1, 'one exact observed actor2 slot-zero aura-clear body is required')
    aura_clear = aura_clear[0]
    native_root = _one(packets, 'SMSG_MOVE_ROOT', 'from_native', bytes.fromhex('100300000000'))
    native_complete = _one(packets, 'SMSG_LOGOUT_COMPLETE', 'from_native', b'')
    require(native_root['time'] < aura_clear['time'] < native_complete['time'] and
        native_complete['time'] - aura_clear['time'] < .1, 'the sole aura clear must bind the native logout completion')
    aura_metadata = _metadata([aura_clear], events, session, physical)
    owned_rows = []
    for row in packets:
        _native_attack(row, set(base), original=row['time'] <= effect_end)
        if key(row) != key(aura_clear):
            stopped_native._combat(row, set(base), original=row['time'] <= effect_end)
        if row['time'] > effect_end and _owned_records(row, set(base)):
            owned_rows.append(row)
    require(len(owned_rows) == (1 if profile == 'ui178_finalization' else 2) and
        all(a['time'] < b['time'] for a, b in zip(owned_rows, owned_rows[1:])),
        'only the actual ordered automatic-idle and logout owned updates are allowed')
    foreign = [row for row in events if row.get('session') not in (session, physical)]
    require(len(foreign) == 1 and set(foreign[0]) == {'event', 'session', 'status', 'time'} and
        foreign[0]['event'] == 'client_variant' and type(foreign[0]['session']) is str and
        foreign[0]['time'] < ready['started_at'] and
        foreign[0]['status'] == {'build': None, 'clientArch': 7878196, 'platformType': 5728622, 'type': 5730135},
        'only the actual pre-ready unattributed client-variant observation is retained')
    require(all(row.get('session') in (session, physical) for row in events
        if row.get('account_id') == 2 or row.get('guid') == 2), 'foreign actor2 attribution is forbidden')
    realm_auth = [row for row in events if row.get('event') == 'world_authenticated']
    instances = [row for row in events if row.get('event') == 'instance_authenticated']
    require(len(realm_auth) == len(instances) == 1 and realm_auth[0].get('session') == session and
        realm_auth[0].get('account_id') == 2 and realm_auth[0]['time'] < ready['started_at'] and
        instances[0].get('session') == physical, 'one original realm/physical authentication required')
    require(not any(row.get('name') == contract.ACTION for row in packets + events), 'no bag input belongs to this history')
    closes = [row for row in events if row.get('event') in ('world_connection_closed', 'native_stream_closed')]
    require(len(closes) == 3 and all(set(row) == {'event', 'session', 'error', 'time'} and
        type(row['error']) is str for row in closes), 'three exact actual close observations required')
    physical_close, realm_close, native_close = closes
    require([row['event'] for row in closes] == ['world_connection_closed', 'world_connection_closed', 'native_stream_closed'] and
        [row['session'] for row in closes] == [physical, session, session] and
        physical_close['error'].startswith('Operation canceled [system:125 at ') and
        realm_close['error'].startswith('End of file [asio.misc:2 at ') and
        native_close['error'].startswith('Operation canceled [system:125 at ') and
        failed['finished_at'] < physical_close['time'] < stop['started_at'] < stop['stop_started_at'] <
        realm_close['time'] < native_close['time'] <= stop['stop_finished_at'] and
        native_close['time'] - realm_close['time'] < 1, 'physical logout and actual owned-stop close chronology differs')
    first_raw = [row for row in packets if row['time'] <= physical_close['time']]
    first_events = [row for row in events if row['time'] <= physical_close['time']]
    history = _prefix_history(first_raw, first_events, ready, failed, physical_close['time'], provider, profile)
    history['logout']['observed_aura_clear'] = {'packet': deepcopy(aura_clear), 'metadata': deepcopy(aura_metadata[0]),
        'excluded_lifecycle_only': True}
    if profile == 'ui176':
        original = idle_contract.original_objects(prefix)
        logout_boundary = _metadata([history['logout']['modern']], first_events, session, physical)[0]['time']
        idle = idle_contract.automatic_idle([row for row in packets if row['time'] < logout_boundary],
            [row for row in events if row['time'] < logout_boundary], session, physical,
            prefix_end, logout_boundary, original=original)
        require(key(idle['automatic_owner_update']['packet']) == key(history['automatic_idle']['owner_update']),
            'automatic idle derivations differ')
    suffix_raw = [row for row in packets if physical_close['time'] < row['time'] < realm_close['time']]
    suffix_events = [row for row in events if physical_close['time'] < row['time'] < realm_close['time']]
    require(len(suffix_raw) == (6 if profile == 'ui178_finalization' else 8) and
        len(suffix_events) == (24 if profile == 'ui178_finalization' else 56) and
        not any(row['time'] >= realm_close['time'] for row in packets) and
        [row for row in events if row['time'] >= realm_close['time']] == [realm_close, native_close],
        'the selected actual lobby-and-stop tail must be complete')
    ping_rows = [row for row in suffix_events if row.get('name') in ('CMSG_PING', 'SMSG_PONG')]
    require(all(a['time'] < b['time'] for a, b in zip(ping_rows, ping_rows[1:])),
        'lobby latency must retain its observed occurrence order')
    lobby = _lobby(suffix_raw, suffix_events, history, realm_close['time'])
    require(lobby['latency_occurrences'] == (1 if profile == 'ui178_finalization' else 8) and
        lobby['character_list_occurrences'] == 1,
        'actual lobby read-only occurrence counts differ')
    # Stock mutation guards still see every non-startup/non-idle input in the
    # complete interval, including preparation and the stopped lobby suffix.
    allowances = set(boot['allowed_packet_keys']) | set(boot['allowed_metadata_keys']) |        set(history['allowed_packet_keys']) | set(history['allowed_metadata_keys'])
    for owner in (session, physical):
        _guard([row for row in packets if key(row) not in allowances], owner,
            min(row['time'] for row in packets), stop['finished_at'],
            login_sync=boot, events=events, provider=provider)
        _guard([row for row in events if key(row) not in allowances], owner,
            min(row['time'] for row in events), stop['finished_at'],
            login_sync=boot, events=events, provider=provider)
    return {'schema': SCHEMA, 'qualification_excluded': True, 'operations_admitted': 0,
        'session': session, 'instance_session': physical, 'sources': refs,
        'classifier_schema': provider.SCHEMA, 'classifier_candidate_source': getattr(provider, 'candidate_source', None),
        'original_failure_preserved': failed['failure'],
        **({'provenance_profile': profile, 'original_phase_preserved': failed['phase'],
            'original_raw_entry_packets_preserved_empty': True, 'journal_prefix_rederived': True,
            'original_finalization_failure_preserved': failed['entry_finalization_failure']}
            if profile == 'ui178_finalization' else {}),
        'original_prefix_packets_sha256': ordered_digest(prefix),
        'original_prefix_events_sha256': ordered_digest(prefix_events),
        'source_packet_count': len(packets), 'source_event_count': len(events),
        'source_packets_ordered_sha256': ordered_digest(packets), 'source_events_ordered_sha256': ordered_digest(events),
        'source_packets_canonical_sha256': _digest(packets), 'source_events_canonical_sha256': _digest(events),
        'login_sync': boot, 'native_original': history['native_original'], 'native_final': history['native_final'],
        'original_objects': history['original_objects'], 'final_objects': history['final_objects'],
        'automatic_idle': history['automatic_idle'], 'normal_logout': history['logout'],
        'native_effect_guard': effect_guard,
        'no_bag_or_extra_gameplay': True, 'all_native_item_fields_unchanged': True,
        'all_native_inventory_slots_unchanged': True, 'lobby': lobby, 'observed_close_events': deepcopy(closes),
        'pre_ready_client_variant': deepcopy(foreign[0]), 'shutdown_checks': deepcopy(stop['shutdown_checks']),
        'scout_absent': True, 'previous_client': deepcopy(ready['runtime']['client']),
        'current_services': {name: deepcopy(ready['runtime'][name]) for name in ('worldserver', 'modern_world')},
        'owned_game_identity': deepcopy(stop['game_before']), 'exact_precision': deepcopy(stop['exact_precision_after']),
        'all_six_offline_preserved': True, 'normal_logout_observed': True,
        'publication_or_qualification_added': False, 'missing_close_event_invented': False}

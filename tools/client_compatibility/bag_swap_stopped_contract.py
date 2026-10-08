"""Pure exclusion proof for the stopped UI173 failed entry and socket expiry."""
from collections import defaultdict
from copy import deepcopy
import hashlib
import math
import struct

from . import bag_swap_contract as contract
from . import bag_swap_failed_contract as native
from . import bag_swap_login_sync as sync
from . import bag_swap_preservation as preservation
from .world.buffer import Reader
from .world.native_objects import guid

SCHEMA = 'client442_bag_swap_stopped_history_v1'
FAILED_SHA256 = '63e2bd045a162b7cb125f76dd3532ca0f43a3e77137ca9e02a7e8cfbf009329a'
FAILED_PACKET_SHA256 = '0f34da132f14da0af714915ba0e131a7cf0fe429c50035e259cc1893b7fee22a'
FAILED_EVENT_SHA256 = '96811b7c04fb8cc2c025dc98eda26fb1dceee6f56355f8e9a6632e21ea8fd366'
CHECKS = frozenset(('actor2_native_changes_confined_to_accounting_rest', 'all_characters_offline',
    'all_saved_inventory_pets_unchanged', 'bridge_lifetime', 'native_lifetime',
    'observed_owned_game_pid_absent', 'origin_registration', 'primary_still_stopped',
    'protected_five_snapshots_unchanged', 'scout_launcher_absent'))
require, finite, strict_equal, body = contract.require, contract.finite, contract.strict_equal, contract.body
key, INDEX = sync.packet_key, contract.INDEX


def ordered_digest(rows):
    """Preserve original journal order, including cross-stream timestamp inversions."""
    digest = hashlib.sha256(b'[')
    for index, row in enumerate(rows):
        if index:
            digest.update(b',')
        digest.update(key(row).encode())
    digest.update(b']')
    return digest.hexdigest()


def _typed(rows, events, since, until):
    require(type(rows) is list and type(events) is list and all(type(r) is dict for r in rows + events),
        'complete stopped journal arrays must contain dictionaries')
    require(finite(since) and finite(until) and since < until and
        all(finite(r.get('time')) and since <= r['time'] <= until for r in rows + events),
        'every stopped journal time must be finite and inside the full audit interval')
    require(all(set(r) == sync.WIRE_FIELDS and type(r.get('name')) is str and r['name'] and
        type(r.get('session')) is str and r['session'] and r.get('direction') in sync.WIRE_DIRECTIONS
        for r in rows), 'stopped raw journal rows require canonical attribution and fields')
    for row in rows:
        body(row)
    for array in (rows, events):
        require(len({key(r) for r in array}) == len(array), 'stopped journal rows cannot be duplicated')


def _reconcile_raw(rows, events, session, physical):
    raw, metadata = defaultdict(list), defaultdict(list)
    for row in rows:
        raw[(row['name'], row['direction'], len(body(row)))].append(row)
    for event in events:
        if event.get('event') not in ('modern_packet', 'native_packet'):
            continue
        require(set(event) == {'session', 'time', 'event', 'name', 'direction', 'bytes'} and
            type(event['bytes']) is int and event['bytes'] >= 0 and
            event['direction'] in sync.WIRE_DIRECTIONS and type(event['name']) is str,
            'packet metadata must retain its exact typed fields')
        metadata[(event['name'], event['direction'], event['bytes'])].append(event)
    body_required = {r['name'] for r in rows} | {'SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT',
        'SMSG_ATTACKER_STATE_UPDATE', 'SMSG_SPELL_START', 'SMSG_SPELL_GO',
        'SMSG_AURA_UPDATE', 'SMSG_AURA_UPDATE_ALL', 'SMSG_ON_MONSTER_MOVE', 'SMSG_STAND_STATE_UPDATE'}
    require(all(identity in raw for identity in metadata if identity[0] in body_required),
        'captured native owner, item or combat metadata cannot omit its raw body occurrence')
    for identity, packets in raw.items():
        matched = metadata[identity]
        require(len(packets) == len(matched), 'every retained raw occurrence needs exactly one packet metadata row')
        for packet, event in zip(sorted(packets, key=lambda r: r['time']), sorted(matched, key=lambda r: r['time'])):
            is_native = packet['direction'] in ('from_native', 'to_native')
            require(event['event'] == ('native_packet' if is_native else 'modern_packet') and
                event['session'] in ((session,) if is_native else (session, physical)) and
                0 <= packet['time'] - event['time'] < .1,
                'raw and metadata occurrence attribution or chronology differs')


def _latency(events, session, physical):
    selected = [e for e in events if e.get('name') in ('CMSG_PING', 'SMSG_PONG')]
    counts = {}
    for owner, width in ((session, 4), (physical, 2)):
        stream = sorted([e for e in selected if e['session'] == owner], key=lambda e: e['time'])
        require(len(stream) % width == 0, 'latency metadata has an incomplete occurrence')
        for offset in range(0, len(stream), width):
            group = stream[offset:offset + width]
            expected = [('modern_packet', 'CMSG_PING', 'from_client', 8),
                ('modern_packet', 'SMSG_PONG', 'to_client', 4)]
            if width == 4:
                expected += [('native_packet', 'CMSG_PING', 'to_native', 8),
                    ('native_packet', 'SMSG_PONG', 'from_native', 4)]
            require([(e['event'], e['name'], e['direction'], e['bytes']) for e in group] == expected and
                all(a['time'] < b['time'] for a, b in zip(group, group[1:])) and
                group[-1]['time'] - group[0]['time'] < 2,
                'latency requires its exact ordered realm quartet or physical local pair')
        counts[owner] = len(stream) // width
    return selected, {'realm_occurrences': counts[session], 'physical_occurrences': counts[physical],
        'bodies_retained': False}


def _routine(rows, events, session, physical, prefix_end):
    late = [r for r in rows if r['time'] > prefix_end]
    late_events = [e for e in events if e['time'] > prefix_end]
    inputs = [r for r in late if r['direction'] in ('from_client', 'to_native')]
    require(all(r['name'] in native.ROUTINE and len(body(r)) == native.ROUTINE[r['name']] for r in inputs),
        'no post-entry gameplay, normal logout, movement or additional login request is admitted')
    matched = native._routine_metadata(inputs, late_events, session, physical)
    tutorials = [e for e in late_events if e.get('name') == 'CMSG_TUTORIAL']
    require(len(tutorials) == 2 and
        [(e.get('event'), e.get('session'), e.get('direction'), e.get('bytes')) for e in tutorials] ==
        [('modern_packet', session, 'from_client', 5), ('unmapped_client_packet', session, None, 5)] and
        set(tutorials[1]) == {'session', 'name', 'bytes', 'time', 'event'} and
        0 < tutorials[1]['time'] - tutorials[0]['time'] < .1,
        'the sole automatic tutorial report must be its exact metadata-only dropped realm pair')
    require(not any(r['name'] == 'CMSG_TUTORIAL' for r in late), 'tutorial body was not retained')
    require(all(key(e) in {key(v) for v in tutorials} for e in late_events
        if e.get('event') == 'unmapped_client_packet'), 'post-entry dropped input lacks its sole typed tutorial occurrence')
    latency, counts = _latency(events, session, physical)
    permitted = {key(e) for e in matched + tutorials + latency}
    require(all(key(e) in permitted for e in late_events if e.get('direction') in ('from_client', 'to_native')),
        'post-entry metadata contains an unbound request or native forwarding')
    requests = [e for e in late_events if e.get('name') == 'CMSG_SERVER_TIME_OFFSET_REQUEST']
    replies = [e for e in late_events if e.get('name') == 'SMSG_SERVER_TIME_OFFSET']
    require(len(requests) == len(replies) == 1 and replies[0].get('session') == session and
        (replies[0].get('event'), replies[0].get('direction'), replies[0].get('bytes')) ==
        ('modern_packet', 'to_client', 8) and 0 < replies[0]['time'] - requests[0]['time'] < .1 and
        not any(e.get('name') in ('CMSG_SERVER_TIME_OFFSET_REQUEST', 'SMSG_SERVER_TIME_OFFSET') and
            e.get('event') == 'native_packet' for e in late_events),
        'server-time query must have its sole local reply and no native forwarding')
    return {'latency': counts, 'tutorial_occurrences': 1, 'tutorial_body_retained': False,
        'server_time_occurrences': 1, 'server_time_reply_body_retained': False,
        'time_sync_occurrences': len([r for r in inputs if r['name'] == 'CMSG_TIME_SYNC_RESPONSE']),
        'quest_status_occurrences': len([r for r in inputs if r['name'] == 'CMSG_QUEST_GIVER_STATUS_QUERY' and
            r['direction'] == 'from_client'])}


def _combat(row, wanted, *, original=False):
    """Fully consume retained native combat/aura bodies before excluding NPCs."""
    if row['direction'] != 'from_native':
        return
    name = row['name']
    if name not in ('SMSG_ATTACKER_STATE_UPDATE', 'SMSG_SPELL_START', 'SMSG_SPELL_GO',
            'SMSG_AURA_UPDATE', 'SMSG_AURA_UPDATE_ALL'):
        return
    reader, identities = Reader(body(row)), []
    def identity():
        value = guid(reader)
        identities.append(value)
        return value
    if name == 'SMSG_ATTACKER_STATE_UPDATE':
        flags, = reader.unpack('I')
        identity(); identity()
        reader.unpack('2i')
        subcount, = reader.unpack('B')
        require(subcount <= 1, 'retained melee subdamage layout differs')
        if subcount:
            reader.unpack('ifi')
            if flags & 0x60: reader.unpack('i')
            if flags & 0x180: reader.unpack('i')
        reader.unpack('B2I')
        if flags & 0x2000: reader.unpack('i')
        if flags & 0x800000: reader.unpack('i')
        if flags & 1: reader.unpack('i10f2i')
    elif name in ('SMSG_SPELL_START', 'SMSG_SPELL_GO'):
        identity(); identity()
        _, _, flags, _, _ = reader.unpack('Bi3I')
        if name == 'SMSG_SPELL_GO':
            hits, = reader.unpack('B')
            for _ in range(hits): identities.append(reader.unpack('Q')[0])
            misses, = reader.unpack('B')
            require(misses == 0, 'unsupported spell miss layout is not part of this stopped history')
        targets, = reader.unpack('I')
        require(not targets & ~(2 | 32 | 64 | 2048), 'unsupported native spell target layout')
        if targets & (2 | 2048): identity()
        for flag in (32, 64):
            if targets & flag:
                identity(); reader.unpack('3f')
        if flags & 0x800: reader.unpack('I')
        if name == 'SMSG_SPELL_GO' and targets & 64: reader.unpack('B')
        if flags & 0x4000000: reader.unpack('2i')
    else:
        unit = identity()
        while reader.pos < len(reader.data):
            _, spell = reader.unpack('Bi')
            if spell <= 0: continue
            flags, _, _ = reader.unpack('H2B')
            identities.append(unit if flags & 8 else identity())
            if flags & 32: reader.unpack('2i')
            for bit in (1, 2, 4):
                if flags & 64 and flags & bit: reader.unpack('i')
    reader.end()
    require(original or not set(identities) & wanted,
        'stopped native combat or aura involved the owner or its inventory')


def _objects(rows, boot, inventory, prefix_end):
    base = native._original(boot['source_packets'], inventory)
    current = deepcopy(base)
    creation_key, initial_effect = key(boot['self_creation']['packet']), []
    owned_rows = []
    for row in sorted(rows, key=lambda r: r['time']):
        decoded = native._owned_records(row, set(base))
        if decoded: owned_rows.append(row)
        for record in decoded:
            identity = record['guid']
            if record['update_type'] in (1, 2):
                require(key(row) == creation_key, 'stopped history cannot recreate any owned object')
                continue
            require(record['update_type'] == 0, 'stopped history owned record layout differs')
            fields = record.get('fields', {})
            changed = {i: v for i, v in fields.items() if v != current[identity].get(i, 0)}
            if changed:
                require(identity == 2 and not initial_effect and
                    changed == {INDEX['UNIT_FIELD_AURASTATE']: 0x400000} and
                    fields == {55: 0x400000, 61: 49, 73: 0, 77: 0} and
                    boot['self_creation']['packet']['time'] < row['time'] < boot['initialization']['modern']['time'],
                    'stopped history changed another full native owner or item field')
                initial_effect.append(row)
            current[identity].update(fields)
        # The exact immutable original login also contains native stance/aura
        # initialization. Its body-bound prefix is not a later gameplay permit.
        _combat(row, set(base), original=row['time'] <= prefix_end)
        if row['name'] == 'SMSG_ON_MONSTER_MOVE':
            reader = Reader(body(row))
            identity = guid(reader) if row['direction'] == 'from_native' else reader.guid()[0]
            require(identity != 2, 'server spline moved the stopped owner')
        if row['time'] > boot['boot_finished_at'] and row['name'].startswith(('SMSG_MOVE_', 'SMSG_SPLINE_MOVE_', 'MSG_MOVE_')):
            require(False, 'stopped history has another server or native movement effect')
    require(len(initial_effect) == 1, 'the original above-75-percent-health aura-state transition is required')
    return base, current, owned_rows, initial_effect[0]


def _observation(ready, F, observation, before_precision):
    require(all(type(v) is dict for v in (ready, F, observation, before_precision)),
        'typed original ready, failed, stopped and precision sources are required')
    require(ready.get('phase') == 'bags_swap_scout_ready' and ready.get('completed') is True and
        F.get('phase') == 'bags_swap_entry_started' and F.get('completed') is False and
        F.get('failure') == 'RuntimeError: login settlement must be one ordered two-second initial prefix' and
        F.get('input_sent') is True and F.get('mutation_sent') is False and F.get('qualification_added') is False,
        'the original excluded failed entry and successful ready sources are required')
    require(F.get('native_session') == ready.get('native_session') and
        all(strict_equal(v.get(k), ready.get(k)) for v in (F, before_precision)
            for k in ('actor', 'runtime', 'code_commit', 'controller', 'model', 'revision', 'fine_tuned',
                'custom_script_permission')) and ready.get('controller') == 'code' and
        ready.get('custom_script_permission') == 'blocked_by_user' and
        ready.get('model') is ready.get('revision') is None and ready.get('fine_tuned') is False,
        'all original source stages must retain the same actual actor, runtime and code authority')
    require(observation.get('schema') == 'client442_failed_entry_stop_observation_v1' and
        observation.get('phase') == 'bags_swap_failed_entry_stopped_observed' and
        observation.get('failed_entry_source', {}).get('sha256') == FAILED_SHA256 and
        strict_equal(observation.get('ready_source'), F.get('preparation_source')) and
        strict_equal(observation.get('game_identity_source'), observation['ready_source']) and
        strict_equal(before_precision.get('source'), observation['ready_source']), 'original stopped source references differ')
    require(type(observation.get('checks')) is dict and set(observation['checks']) == CHECKS and
        all(v is True for v in observation['checks'].values()), 'all ten actual stopped observation checks are required')
    for name, expected in {'normal_logout_input_sent': False, 'bag_input_sent': False, 'entry_input_sent': True,
            'client_input_sent_by_this_observation': False, 'mutation_sent_by_this_observation': False,
            'qualification_added': False, 'operations_admitted': 0, 'excluded_failed_entry': True}.items():
        require(type(observation.get(name)) is type(expected) and observation[name] == expected,
            'stopped observation cannot invent gameplay, qualification or cleanup')
    pid = ready['frame']['monitor']['input_isolation']['game_pid']
    require(type(pid) is int and pid > 0 and type(observation.get('observed_owned_game_pid')) is int and
        observation['observed_owned_game_pid'] == pid and
        'game_start_ticks' not in observation, 'stopped game identity must be the retained PID without an invented start tick')
    require(observation.get('stop_action') == 'committed lab_runtime stop-client for actor=scout' and
        all(strict_equal(observation.get(k), ready.get(k)) for k in ('native_session', 'runtime', 'code_commit')),
        'stopped observation runtime or stop action differs')
    baseline, after = ready['all_offline_snapshot'], observation['after']
    require(strict_equal(F.get('all_offline_snapshot'), baseline) and
        strict_equal(F.get('native_before_entry'), baseline['2']['native']) and
        strict_equal(observation.get('ready_baseline'), baseline), 'complete original offline baseline differs')
    preservation._preserved(baseline, after)
    require(before_precision.get('phase') == 'bags_swap_rest_precision_complete' and before_precision.get('completed') is True and
        before_precision.get('input_sent') is False and before_precision.get('mutation_sent') is False and
        before_precision.get('qualification_added') is False and
        before_precision.get('query') == preservation.PRECISION_QUERY and
        strict_equal(before_precision.get('before'), baseline) and strict_equal(before_precision.get('after'), baseline),
        'source-bound before precision must preserve the full ready snapshot')
    exact = observation['exact_after_precision']
    require(exact.get('query') == preservation.PRECISION_QUERY and exact.get('input_sent') is False and
        exact.get('mutation_sent') is False and strict_equal(exact.get('before'), after) and strict_equal(exact.get('after'), after),
        'source-bound stopped precision must preserve the full current snapshot')
    return preservation.exact_precision(before_precision['row'], baseline), preservation.exact_precision(exact['row'], after), pid


def stopped_history(rows, events, ready, F, observation, before_precision, *, audit_until):
    """Validate complete ready-to-audit journals; this never qualifies a bag swap."""
    try:
        return _stopped_history(rows, events, ready, F, observation, before_precision, audit_until)
    except (ValueError, KeyError, IndexError, struct.error, OverflowError, TypeError) as error:
        raise RuntimeError('stopped history cannot be parsed exactly') from error


def _stopped_history(rows, events, ready, F, observation, before_precision, audit_until):
    exact_before, exact_after, pid = _observation(ready, F, observation, before_precision)
    since, session, prefix_end = ready['started_at'], ready['native_session'], F['entry_input_finished_at']
    require(all(finite(v) for v in (F['started_at'], F['finished_at'], prefix_end, observation.get('observed_at'))) and
        since < before_precision['started_at'] <= before_precision['finished_at'] < F['started_at'] <
        prefix_end < F['finished_at'] < observation['observed_at'] <= audit_until,
        'stopped source intervals or audit cutoff differ')
    _typed(rows, events, since, audit_until)
    pose = [F['native_before_entry'][k] for k in ('position_x', 'position_y', 'position_z', 'orientation')]
    boot = sync.login_sync(rows, events, session, F['started_at'], prefix_end, pose)
    physical = boot['instance_session']
    require(all(r['session'] == session for r in rows) and all(e.get('session') in (session, physical) for e in events),
        'complete stopped interval contains another raw or physical/native connection')
    original_rows = [r for r in rows if F['started_at'] <= r['time'] <= prefix_end]
    original_events = [e for e in events if F['started_at'] <= e['time'] <= prefix_end]
    require(strict_equal(original_rows, F['raw_entry_packets']) and strict_equal(original_events, F['raw_entry_events']),
        'original failed raw packet and metadata prefixes must remain ordered and exact')
    require(ordered_digest(original_rows) == FAILED_PACKET_SHA256 and
        ordered_digest(original_events) == FAILED_EVENT_SHA256,
        'original failed packet and event vectors must bind their actual immutable source bytes')
    require(not any(r['name'] in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_RESPONSE', 'SMSG_LOGOUT_COMPLETE', contract.ACTION)
        for r in rows) and not any(e.get('name') in ('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_RESPONSE',
        'SMSG_LOGOUT_COMPLETE', contract.ACTION) for e in events), 'stopped history cannot contain a normal logout or swap')
    for owner in (session, physical):
        contract.forbidden_packets(rows if owner == session else [], owner, since, audit_until, login_sync=boot)
        contract.forbidden_packets(events, owner, since, audit_until, login_sync=boot)
    require(len([e for e in events if e.get('event') == 'instance_authenticated']) == 1,
        'stopped history cannot contain an additional login')
    _reconcile_raw(rows, events, session, physical)
    routine = _routine(rows, events, session, physical, prefix_end)
    before_events = [e for e in events if e['time'] < F['started_at']]
    latency, _ = _latency(before_events, session, physical)
    require(strict_equal(before_events, latency), 'ready-to-entry interval can contain only its complete realm latency quartet')
    boundaries = [e for e in events if e.get('event') in ('world_connection_closed', 'native_stream_closed')]
    require(len(boundaries) == 3 and [(e['event'], e['session']) for e in boundaries] ==
        [('world_connection_closed', session), ('world_connection_closed', physical), ('native_stream_closed', session)] and
        all(set(e) == {'session', 'time', 'event', 'error'} and type(e['error']) is str for e in boundaries) and
        boundaries[0]['error'].startswith('End of file [asio.misc:2 ') and
        boundaries[1]['error'].startswith('Connection reset by peer [system:104 ') and
        boundaries[2]['error'].startswith('Operation canceled [system:125 ') and
        boundaries[0]['time'] < boundaries[1]['time'] < boundaries[2]['time'] < boundaries[0]['time'] + .1,
        'stopped stream must end at its exact realm EOF, physical reset and native cancellation')
    last_wire = max(r['time'] for r in rows)
    require(last_wire < boundaries[0]['time'] < last_wire + 1 and
        not any(e['time'] > boundaries[0]['time'] and key(e) not in {key(v) for v in boundaries} for e in events),
        'closed physical/native streams cannot contain later packets or events')
    require(not any(e['time'] > prefix_end and e.get('event') not in
        ('modern_packet', 'native_packet', 'unmapped_client_packet', 'world_connection_closed', 'native_stream_closed')
        for e in events), 'stopped history contains another effect, marker or lifecycle event')
    require(not any(e['time'] > prefix_end and
        str(e.get('name', '')).startswith(('SMSG_MOVE_', 'SMSG_SPLINE_MOVE_', 'MSG_MOVE_')) and
        e.get('name') != 'SMSG_MOVE_UPDATE' for e in events),
        'stopped metadata cannot conceal another native or server movement effect')
    base, final, owned_rows, initial_effect = _objects(rows, boot, ready['all_offline_snapshot']['2']['inventory'], prefix_end)
    replay = contract.native_replay(rows, session, F['started_at'], audit_until, login_sync=boot)
    threshold = final[2].get(INDEX['PLAYER_REST_STATE_EXPERIENCE'], 0)
    require(threshold == replay['rest_threshold'] == int(exact_after['exact_rest_bonus']), 'native rest threshold differs from exact FLOAT attribution')
    matches = []
    login = contract.login_packets(rows, session, F['started_at'], prefix_end)
    for second in range(math.floor(login['request']['time']), math.floor(login['verify']['time']) + 1):
        elapsed = second - exact_before['logout_time']
        if elapsed < 0: continue
        exact, display = preservation.native_rest(exact_before['exact_rest_bonus'], elapsed)
        if exact == exact_after['exact_rest_bonus'] and display == exact_after['rest_bonus']:
            matches.append({'native_login_second': second, 'offline_seconds': elapsed})
    require(len(matches) == 1, 'stopped rest requires one exact native login second and offline FLOAT accrual')
    logout_time = observation['after']['2']['native']['logout_time']
    require(logout_time == math.floor(boundaries[0]['time']) + 60,
        'saved stopped logout must bind the observed sixty-second socket-loss expiry')
    native_state = {k: replay[k] for k in ('owner', 'health', 'max_health', 'powers', 'xp', 'xp_cap',
        'resting', 'summon', 'rest_threshold', 'rest_state')}
    native_state.update(pose={'stand': final[2].get(INDEX['UNIT_FIELD_BYTES_1'], 0) & 255,
        'sheath': final[2].get(INDEX['UNIT_FIELD_BYTES_2'], 0) & 255},
        afk=bool(final[2].get(INDEX['PLAYER_FLAGS'], 0) & 2), position=boot['baseline_pose'])
    return deepcopy({'schema': SCHEMA, 'qualification_excluded': True, 'operations_admitted': 0,
        'session': session, 'instance_session': physical, 'since': since, 'original_prefix_end': prefix_end,
        'until': boundaries[-1]['time'], 'audit_until': audit_until, 'login_sync': boot,
        'original_failed_entry_source': observation['failed_entry_source'], 'ready_source': observation['ready_source'],
        'observed_owned_game_pid': pid, 'game_start_ticks_retained': False,
        'original_prefix_packet_count': len(original_rows), 'original_prefix_event_count': len(original_events),
        'source_packet_count': len(rows), 'source_event_count': len(events),
        'source_packets_sha256': ordered_digest(rows), 'source_events_sha256': ordered_digest(events),
        'last_wire_at': last_wire,
        'last_native_wire_at': max(r['time'] for r in rows if r['direction'] == 'from_native'),
        'boundaries': boundaries, 'normal_logout_input_sent': False,
        'saved_logout_time': logout_time, 'socket_expiry_seconds': 60, 'actual_sigterm_time_retained': False,
        'native_state': native_state, 'creation_objects': native._json_objects(base),
        'final_objects': native._json_objects(final), 'initial_health_aura_state_update': initial_effect,
        'all_native_inventory_item_fields_preserved': True, 'all_15_sql_item_fields_preserved': True,
        'all_six_offline_preserved': True, 'routine': routine,
        'metadata_only_delivered_movement_count': len([e for e in events if e['time'] > prefix_end and
            e.get('name') == 'SMSG_MOVE_UPDATE']), 'metadata_only_delivered_movement_bodies_retained': False,
        'metadata_only_delivered_movement_identity_proved': False,
        'rest': {**matches[0], 'before_float32_bits': exact_before['exact_rest_bonus_float32_bits'],
            'after_float32_bits': exact_after['exact_rest_bonus_float32_bits'], 'exact_after': exact_after['exact_rest_bonus'],
            'rest_threshold': threshold, 'rounded_baseline_reconstruction': False}})

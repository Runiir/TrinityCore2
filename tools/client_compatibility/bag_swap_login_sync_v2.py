"""Successor stationary startup proof with retained physical request boundaries.

Historical receipts use bag_swap_login_sync v1 unchanged. This v2 schema
requires full metadata rederivation at source-owned admission; serialized/raw
replay alone cannot prove completeness of a caller's supplied context.
"""
from copy import deepcopy
import json
import math
import struct

from . import item_actionbar_contract as shared
from .world.buffer import Reader, Writer, player_high
from .world.movement import encode, parse
from .world.native_objects import guid, movement as native_movement, records, values

SCHEMA = 'client442_bag_swap_login_sync_v2'
INITIALIZE = 'CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE'
ACTIVE = 'CMSG_SET_ACTIVE_MOVER'
HEARTBEAT = 'CMSG_MOVE_HEARTBEAT'
LANDING = 'CMSG_MOVE_FALL_LAND'
TURN = 'CMSG_MOVE_SET_TURN_RATE_CHEAT'
SKIPPED = 'CMSG_MOVE_TIME_SKIPPED'
require, finite, body = shared.require, shared.finite, shared.body
ACTOR_GUID = Writer().guid(2, player_high()).finish()
WIRE_FIELDS = frozenset(('session', 'time', 'name', 'direction', 'body'))
WIRE_DIRECTIONS = frozenset(('from_client', 'to_native', 'from_native', 'to_client'))


def packet_key(row):
    """Bind the complete raw packet or metadata row, including its exact time."""
    require(type(row) is dict and all(type(k) is str for k in row), 'canonical login row is required')
    try:
        return json.dumps(row, sort_keys=True, separators=(',', ':'), allow_nan=False)
    except (TypeError, ValueError) as error:
        raise RuntimeError('login row is not finite JSON') from error


def _pose(pose):
    require(type(pose) in (tuple, list) and len(pose) == 4 and
        all(type(v) is float and finite(v) for v in pose), 'four finite original native pose floats are required')
    try:
        raw = struct.pack('<4f', *pose)
    except (OverflowError, struct.error) as error:
        raise RuntimeError('original native pose overflows float32') from error
    require(all(math.isfinite(v) for v in struct.unpack('<4f', raw)), 'original pose float32 must be finite')
    return raw


def _stationary_creation(reader):
    # The general native reader deliberately discards these layout controls.
    # Inspect the complete bounded self layout before accepting its pose.
    require([reader.bits(1) for _ in range(8)] == [0, 0, 0, 0, 0, 1, 0, 1] and
        reader.bits(24) == 0 and reader.bits(6) == 0,
        'native login self creation has ancillary movement state')
    require([reader.bits(1) for _ in range(2)] == [1, 0] and reader.bits(3) == 0 and
        [reader.bits(1) for _ in range(5)] == [0, 1, 0, 0, 1] and reader.bits(5) == 0 and
        [reader.bits(1) for _ in range(4)] == [1, 0, 0, 1] and reader.bits(7) == 0,
        'native login self has flags, transport, spline, falling, pitch, elevation or padding')
    run_back, swim_back, z, x, pitch_rate = reader.unpack('5f')
    require(reader.unpack('B')[0] == 3, 'native self movement embedded GUID is not actor2')
    swim, y, walk = reader.unpack('3f')
    timestamp, = reader.unpack('I')
    turn_rate, flight, orientation, run, flight_back = reader.unpack('5f')
    speeds = [walk, run, run_back, swim, swim_back, flight, flight_back, turn_rate, pitch_rate]
    require(all(finite(v) for v in [x, y, z, orientation, *speeds]) and
        all(v > 0 for v in speeds), 'native login pose or movement capabilities are invalid')
    return {'position': [x, y, z, orientation], 'time': timestamp, 'speeds': speeds,
        'flags': 0, 'flags2': 0, 'pitch': 0}


def _creation(rows, login, pose):
    matches = []
    for row in rows:
        if (row.get('direction'), row.get('name')) != ('from_native', 'SMSG_UPDATE_OBJECT'):
            continue
        decoded = records(body(row))
        matches.extend((row, i) for i, r in enumerate(decoded) if r.get('guid') == 2 and
            r['update_type'] in (1, 2))
    require(len(matches) == 1, 'one original actor2 native self creation is required')
    packet, wanted = matches[0]
    require(login['request']['time'] <= packet['time'] <= login['delivered']['time'],
        'native self creation must belong to the original login delivery')
    reader = Reader(body(packet))
    map_id, count = reader.unpack('HI')
    require(map_id == 0 and 0 < count <= 10000, 'native login creation map or record count differs')
    result = None
    for index in range(count):
        update_type, = reader.unpack('B')
        if update_type == 3:
            removed, = reader.unpack('I')
            require(removed <= 10000, 'native login removal count exceeds bound')
            for _ in range(removed):
                require(guid(reader) != 2, 'native login packet removes its owner')
            continue
        identity = guid(reader)
        require(update_type in (0, 1, 2), 'native login update type differs')
        if update_type in (1, 2):
            kind, = reader.unpack('B')
            if index == wanted:
                require(identity == 2 and kind == 4, 'native login creation is not the self player')
                result = _stationary_creation(reader)
            else:
                native_movement(reader)
        values(reader)
    reader.end()
    require(result is not None and struct.pack('<4f', *result['position']) == pose,
        'native self creation displaced the original float32 pose')
    return {'packet': deepcopy(packet), 'record_index': wanted, 'movement': result}


def _modern_movement(row, pose, *, landing=False):
    reader = Reader(body(row))
    require(reader.guid() == (2, player_high()) and reader.data[:reader.pos] == ACTOR_GUID,
        'login settlement GUID is not canonical actor2')
    flags, flags2, flags3, timestamp = reader.unpack('4I')
    x, y, z, orientation, pitch, elevation = reader.unpack('6f')
    forces, index = reader.unpack('2I')
    require((flags, flags2, flags3) == ((0, 0x200, 0) if landing else (0x800, 0, 0)) and
        struct.pack('<4f', x, y, z, orientation) == pose and
        struct.pack('<2f', pitch, elevation) == bytes(8) and forces == index == 0,
        'login settlement raw flags, pose, pitch, elevation or forces differ')
    require([reader.bits(1) for _ in range(8)] == ([0] * 8 if landing else [0, 0, 1, 0, 0, 0, 0, 0]),
        'login settlement contains standing, transport, spline or extra presence bits')
    if not landing:
        fall_time, zspeed = reader.unpack('If')
        require(fall_time == 0 and struct.pack('<f', zspeed) == bytes(4) and reader.bits(1) == 1 and
            reader.bits(7) == 0, 'login heartbeat has falling velocity, duration or hidden fall bits')
        sin, cos, speed = reader.unpack('3f')
        require(all(finite(v) and -1 <= v <= 1 for v in (sin, cos)) and sin != 0 and cos != 0 and
            abs(sin * sin + cos * cos - 1) < 1e-6 and struct.pack('<f', speed) == bytes(4),
            'login heartbeat has invalid direction or nonzero horizontal speed')
    reader.end()
    result = parse(body(row), 2)
    result['position'] = list(result['position'])
    require(result['time'] == timestamp, 'login settlement clock differs')
    return result


def _one(rows, name, direction):
    matched = [r for r in rows if (r.get('name'), r.get('direction')) == (name, direction)]
    require(len(matched) == 1, 'one unique login settlement packet required: ' + name + '/' + direction)
    return matched[0]


def _native_pair(rows, modern, state):
    name, raw = encode(modern['name'], 2, state)
    native = _one(rows, name, 'to_native')
    require(body(native) == raw and modern['time'] < native['time'] and
        native['time'] - modern['time'] < .1, 'login settlement native body or forwarding order differs')
    return {'modern': deepcopy(modern), 'native': deepcopy(native), 'movement': state}


def _metadata_events(events, packets, session, physical):
    selected = []
    for packet in packets:
        direction = packet['direction']
        event_session = session if direction in ('to_native', 'from_native') or packet['name'] == 'CMSG_PLAYER_LOGIN' else physical
        candidates = [e for e in events if (e.get('session'), e.get('name'), e.get('direction')) ==
            (event_session, packet['name'], direction) and type(e.get('bytes')) is int and
            e['bytes'] == len(body(packet)) and finite(e.get('time')) and
            0 <= packet['time'] - e['time'] < .1 and packet_key(e) not in set(map(packet_key, selected))]
        require(len(candidates) == 1 and candidates[0].get('event') ==
            ('native_packet' if direction in ('to_native', 'from_native') else 'modern_packet') and
            type(candidates[0].get('bytes')) is int and candidates[0]['bytes'] == len(body(packet)),
            'unique original physical/native login packet metadata differs')
        selected.append(candidates[0])
    return selected


def _physical_request_interval(packet, events, physical, request_metadata):
    # A physical read loop logs its request before synchronous actor-locked
    # dispatch, then reads the next request only after that dispatch returns.
    # Native::send independently posts onto the native channel strand.
    positions = [i for i, e in enumerate(events) if packet_key(e) == packet_key(request_metadata)]
    require(len(positions) == 1, 'physical request metadata occurrence is missing or duplicated')
    anchor = positions[0]
    following = [(i, e) for i, e in enumerate(events) if i > anchor and e.get('session') == physical and
        (e.get('event'), e.get('direction')) == ('modern_packet', 'from_client')]
    next_index, boundary = following[0] if following else (len(events), None)
    if boundary is not None:
        require(set(boundary) == {'session', 'time', 'event', 'name', 'direction', 'bytes'} and
            type(boundary.get('name')) is str and boundary['name'] and
            type(boundary.get('bytes')) is int and boundary['bytes'] >= 0,
            'next physical request boundary must retain canonical metadata')
        require(sum(packet_key(e) == packet_key(boundary) for e in events) == 1,
            'selected physical request boundary occurrence is duplicated')
    upper = min(packet['time'] + .1, boundary['time']) if boundary is not None else packet['time'] + .1
    return anchor, next_index, upper, boundary


def _physical_event_follows(packet, event, events, physical, *, request_metadata=None):
    # Empty context is useful only for inspecting the explicit admission cap;
    # the complete classifier always supplies the matched request occurrence.
    if not events:
        return packet['time'] < event['time'] < packet['time'] + .1
    require(request_metadata is not None, 'physical effect requires its matched request metadata')
    anchor, following, upper, _ = _physical_request_interval(packet, events, physical, request_metadata)
    positions = [i for i, e in enumerate(events) if packet_key(e) == packet_key(event)]
    return len(positions) == 1 and anchor < positions[0] < following and packet['time'] < event['time'] < upper


def login_sync(rows, events, session, since, until, baseline_pose):
    """Validate the entire retained initial window and return exact inert boot rows."""
    try:
        return _login_sync(rows, events, session, since, until, baseline_pose)
    except (ValueError, IndexError, KeyError, struct.error, OverflowError) as error:
        raise RuntimeError('login settlement bodies cannot be parsed exactly') from error


def _login_sync(rows, events, session, since, until, baseline_pose):
    scoped = shared.packet_rows(rows, session, since, until)
    require(type(events) is list and all(type(e) is dict for e in events), 'original login event rows required')
    logins = [r for r in rows if r.get('name') == 'CMSG_PLAYER_LOGIN']
    require(all(finite(r.get('time')) and set(r) == WIRE_FIELDS and
        type(r.get('session')) is str and r['session'] and
        type(r.get('direction')) is str and r['direction'] in WIRE_DIRECTIONS for r in logins),
        'login requests require finite canonical attribution before filtering')
    for row in logins:
        body(row)
    require(all(r['session'] == session for r in logins if since <= r['time'] <= until),
        'another connection logged in during the owned login window')
    # Actor attribution must precede either time or session filtering. A second
    # physical connection cannot hide a malformed actor2 event outside the owner.
    attributed = [e for e in events if e.get('session') == session or
        e.get('account_id') == 2 or e.get('guid') == 2]
    require(all(finite(e.get('time')) and type(e.get('session')) is str and e['session'] and
        (e.get('account_id') != 2 or type(e['account_id']) is int) and
        (e.get('guid') != 2 or type(e['guid']) is int) for e in attributed),
        'actor2 login metadata requires a finite time and typed physical/native attribution')
    require(all(set(r) == WIRE_FIELDS and type(r.get('name')) is str and r['name'] and
        type(r.get('direction')) is str and r['direction'] in WIRE_DIRECTIONS for r in scoped),
        'original login requires canonical raw wire rows')
    for row in scoped:
        body(row)
    pose = _pose(baseline_pose)
    baseline = list(struct.unpack('<4f', pose))
    login = shared.login_packets(scoped, session, since, until)
    require(len(body(login['modern'])) == len(ACTOR_GUID) + 4 and
        body(login['modern']).startswith(ACTOR_GUID), 'original login GUID is not canonical actor2')
    require(struct.pack('<4f', *(login['world'][k] for k in
        ('position_x', 'position_y', 'position_z', 'orientation'))) == pose,
        'original login displaced its native baseline pose')
    creation = _creation(scoped, login, pose)
    initial = _one(scoped, INITIALIZE, 'from_client')
    active = _one(scoped, ACTIVE, 'to_native')
    require(len(body(initial)) == 4 and body(active) == bytes.fromhex('1003') and
        initial['time'] < active['time'] < initial['time'] + .1, 'owned login mover initialization differs')
    clock, = struct.unpack('<I', body(initial))
    heartbeat = _one(scoped, HEARTBEAT, 'from_client')
    landing = _one(scoped, LANDING, 'from_client')
    heart = _native_pair(scoped, heartbeat, _modern_movement(heartbeat, pose))
    land = _native_pair(scoped, landing, _modern_movement(landing, pose, landing=True))
    turn = _one(scoped, TURN, 'from_client')
    require(body(turn) == struct.pack('<f', math.pi), 'ignored login turn rate is not exactly float32 pi')
    skipped = [r for r in scoped if (r.get('name'), r.get('direction')) == (SKIPPED, 'from_client')]
    require(len(skipped) == 2, 'exactly two ignored login clock gaps are required')
    gaps = []
    for packet in skipped:
        reader = Reader(body(packet))
        require(reader.guid() == (2, player_high()) and reader.data[:reader.pos] == ACTOR_GUID,
            'ignored login clock GUID is not canonical actor2')
        gap, = reader.unpack('I')
        reader.end()
        gaps.append(gap)
    require(0 < clock < heart['movement']['time'] < land['movement']['time'] and
        land['movement']['time'] - clock <= 2000 and
        gaps == [heart['movement']['time'] - clock, land['movement']['time'] - heart['movement']['time']],
        'ignored login clock gaps do not equal the actual initializer/heartbeat/landing steps')
    modern_boot = [initial, turn, skipped[0], heartbeat, skipped[1], landing]
    native_boot = [active, heart['native'], land['native']]
    # Native::send posts onto its channel strand. Its emission can therefore
    # follow a subsequent modern packet; retain each stream's order and the
    # exact modern/native pairs instead of inventing a cross-stream edge.
    require(all(a['time'] < b['time'] for stream in (modern_boot, native_boot)
        for a, b in zip(stream, stream[1:])) and
        login['delivered']['time'] < initial['time'] and land['native']['time'] <= login['delivered']['time'] + 2,
        'login settlement must be one ordered two-second initial prefix')
    incoming = [r for r in scoped if r.get('direction') in ('from_client', 'to_native') and
        (str(r.get('name', '')).startswith(('CMSG_MOVE_', 'MSG_MOVE_')) or r.get('name') == ACTIVE)]
    # RAW time is sampled before the shared append mutex. Independent strands
    # can append in another cross-stream order without changing either stream.
    require([r for r in incoming if r['direction'] == 'from_client'] == modern_boot and
        [r for r in incoming if r['direction'] == 'to_native'] == native_boot,
        'extra, repeated or wrong per-stream startup RAW occurrence order is forbidden')
    # The physical handler appends its own request before posting its native
    # send. Keep that causal edge independently of unrelated stream appends.
    require(all(scoped.index(modern) < scoped.index(native) for modern, native in
        ((initial, active), (heartbeat, heart['native']), (landing, land['native']))),
        'startup native RAW must follow its own modern RAW occurrence')
    boot = sorted([*modern_boot, *native_boot], key=lambda r: r['time'])
    instances = [e for e in events if e.get('event') == 'instance_authenticated' and
        e.get('account_id') == 2 and finite(e.get('time')) and since <= e['time'] <= until]
    require(len(instances) == 1 and type(instances[0].get('account_id')) is int and
        type(instances[0].get('session')) is str and instances[0]['session'] and instances[0]['session'] != session and
        login['modern']['time'] <= instances[0]['time'] <= login['request']['time'],
        'one original actor2 physical instance must bind the native login')
    physical = instances[0]['session']
    actor_window = [e for e in attributed if since <= e['time'] <= until]
    require(all(e['session'] in (session, physical) and
        (e.get('event') != 'native_player_created' or e['session'] == session) and
        (e.get('event') not in ('movement_forwarded', 'native_active_mover_confirmed',
            'active_mover_deferred_until_player_create') or e['session'] == physical)
        for e in actor_window), 'actor2 login metadata belongs to another physical/native connection')
    relevant = [e for e in events if e.get('session') in (session, physical)]
    require(all(finite(e.get('time')) for e in relevant), 'owned login event time must be finite')
    relevant = [e for e in relevant if since <= e['time'] <= until]
    selected_packets = sorted([login[k] for k in ('modern', 'request', 'verify', 'delivered')] +
        [creation['packet'], *boot], key=lambda r: r['time'])
    matched = _metadata_events(relevant, selected_packets, session, physical)
    # Same native channel strand emits metadata and its RAW synchronously.
    # Validate actual occurrence order before sorting retained proof events;
    # timestamps/multisets alone can erase an impossible native permutation.
    packet_metadata = {packet_key(packet): event for packet, event in zip(selected_packets, matched)}
    native_positions = [[i for i, event in enumerate(relevant)
        if packet_key(event) == packet_key(packet_metadata[packet_key(packet)])] for packet in native_boot]
    require(all(len(positions) == 1 for positions in native_positions) and
        all(a[0] < b[0] for a, b in zip(native_positions, native_positions[1:])),
        'native startup metadata must retain unique ACTIVE/HEARTBEAT/LAND journal order')
    own_metadata = {packet_key(packet): event for packet, event in zip(selected_packets, matched)
        if packet['direction'] == 'from_client' and event['session'] == physical}
    boundaries = []
    for packet in modern_boot:
        _, _, _, boundary = _physical_request_interval(packet, relevant, physical, own_metadata[packet_key(packet)])
        if boundary is not None and boundary['time'] < packet['time'] + .1:
            boundaries.append(boundary)
    movement_events = [e for e in relevant if e.get('direction') in ('from_client', 'to_native') and
        (str(e.get('name', '')).startswith(('CMSG_MOVE_', 'MSG_MOVE_')) or e.get('name') == ACTIVE)]
    require(sorted(map(packet_key, movement_events)) == sorted(map(packet_key,
        [e for e in matched if e.get('name') in {r['name'] for r in boot}])),
        'movement packet metadata contains another or misattributed initial input')
    for packet in (turn, *skipped):
        dropped = [e for e in relevant if e.get('event') == 'unmapped_client_packet' and
            e.get('name') == packet['name'] and _physical_event_follows(packet, e, relevant, physical,
                request_metadata=own_metadata[packet_key(packet)])]
        require(len(dropped) == 1 and dropped[0].get('session') == physical and
            type(dropped[0].get('bytes')) is int and dropped[0]['bytes'] == len(body(packet)),
            'ignored login metadata lacks its exact physical drop event')
        matched.append(dropped[0])
    forwarded = [e for e in relevant if e.get('event') == 'movement_forwarded']
    require(len(forwarded) == 2, 'login movement must have exactly two forwarded effects')
    for pair in (heart, land):
        effect = [e for e in forwarded if e.get('name') == pair['modern']['name']]
        require(len(effect) == 1 and effect[0].get('session') == physical and type(effect[0].get('guid')) is int and
            effect[0]['guid'] == 2 and type(effect[0].get('position')) is list and
            _pose(effect[0]['position']) == pose and _physical_event_follows(pair['modern'], effect[0], relevant, physical,
                request_metadata=own_metadata[packet_key(pair['modern'])]),
            'forwarded login effect changed its physical owner, pose or chronology')
    confirmations = [e for e in relevant if e.get('event') in
        ('native_active_mover_confirmed', 'active_mover_deferred_until_player_create')]
    require(len(confirmations) == 1 and confirmations[0].get('event') == 'native_active_mover_confirmed' and
        confirmations[0].get('session') == physical and type(confirmations[0].get('guid')) is int and
        confirmations[0]['guid'] == 2 and _physical_event_follows(initial, confirmations[0], relevant, physical,
            request_metadata=own_metadata[packet_key(initial)]),
        'initial active mover event differs from its exact owned native pair')
    selected_events = sorted([*matched, *forwarded, *confirmations, instances[0]], key=lambda e: e['time'])
    require(len(set(map(packet_key, selected_events))) == len(selected_events), 'login event evidence is duplicated')
    metadata = [e for e in selected_events if e.get('name') in {r['name'] for r in boot} or
        e.get('event') == 'native_active_mover_confirmed']
    all_movement_metadata = [e for e in relevant if
        str(e.get('name', '')).startswith(('CMSG_MOVE_', 'MSG_MOVE_')) or e.get('name') == ACTIVE or
        e.get('event') in ('native_active_mover_confirmed', 'active_mover_deferred_until_player_create')]
    require(sorted(map(packet_key, all_movement_metadata)) == sorted(map(packet_key, metadata)),
        'every original movement metadata row must match the exact login settlement')
    # Next requests are causal context, never extra input allowances. Retain
    # only missing boundaries that tighten the .1s cap so reconstruction uses
    # the same physical dependencies without changing old sufficient proofs.
    selected_keys = set(map(packet_key, selected_events))
    selected_events = sorted([*selected_events, *{packet_key(e): e for e in boundaries
        if packet_key(e) not in selected_keys}.values()], key=lambda e: e['time'])
    return deepcopy({'schema': SCHEMA, 'session': session, 'instance_session': physical, 'since': since, 'until': until,
        'baseline_pose': baseline, 'login_packets': [login[k] for k in ('modern', 'request', 'verify', 'delivered')],
        'self_creation': creation, 'initialization': {'modern': initial, 'native': active, 'clock': clock},
        'heartbeat': heart, 'landing': land, 'ignored_metadata': [turn, *skipped], 'clock_deltas': gaps,
        'allowed_packet_keys': sorted(map(packet_key, boot)),
        'allowed_metadata_keys': sorted(map(packet_key, metadata)), 'boot_finished_at': land['native']['time'],
        'source_packets': selected_packets, 'source_events': selected_events})


def validate_login_sync(proof, *, events=None):
    """Reconstruct exact retained sources; supplied full metadata binds completeness.

    Without events this checks the serialized sources only. Source-owned entry
    admission or a metadata caller must supply its complete actual event window
    to establish that no causal request boundary was omitted from that proof.
    """
    require(type(proof) is dict and proof.get('schema') == SCHEMA, 'exact login settlement proof is required')
    try:
        rebuilt = login_sync(proof['source_packets'], proof['source_events'], proof['session'],
            proof['since'], proof['until'], proof['baseline_pose'])
    except KeyError as error:
        raise RuntimeError('login settlement proof source fields are absent') from error
    require(shared.strict_equal(proof, rebuilt), 'login settlement proof differs from its reconstructed exact sources')
    if events is not None:
        require(type(events) is list and events and all(type(e) is dict and
            type(e.get('event')) is str and e['event'] and 'body' not in e and finite(e.get('time')) for e in events),
            'login settlement caller context requires complete nonempty typed metadata')
        actual = login_sync(proof['source_packets'], events, proof['session'],
            proof['since'], proof['until'], proof['baseline_pose'])
        require(shared.strict_equal(proof, actual), 'login settlement proof differs from complete actual caller metadata')
    return rebuilt

"""Pure frozen UI170 trainer identity, from native creation through purchase."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import struct

from . import lab_runtime as lab
from .hunter_learn_contract import require, TRAINER_GUID, TRAINER_ROW, TRAINER_NAME, TRAINER, SPELL
from .world.buffer import Reader
from .world.native_objects import records, guid as native_guid

SCHEMA = 'client442_hunter_learn_trainer_identity_v1'
SPAWN_SOURCE = {'path': str(lab.ROOT / 'evidence/client_interactions_20261007_ui170/'
    'hunter_learning_trainer_spawn_uniqueness01.json'),
    'sha256': '50f901aff2012970a1f549d008ea373f8ad7adcb69f3a9ef33f3673ae8dba66e'}
NATIVE = {'pid': 2977495, 'start_ticks': '54227939'}
QUERY = ('SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,'
    'COALESCE(NULLIF(c.npcflag,0),t.npcflag),c.MovementType,ct.TrainerId '
    'FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id '
    'JOIN client442_world.creature_trainer ct ON ct.CreatureId=c.id WHERE c.id=46983 AND c.map=0 ORDER BY c.guid')
PUBLIC_GUID = 'Creature-0-1-0-0-46983-000000211A'
LESSON = [1462, 1, 646, 0, 0, 0, 0, 0, 0, 0]
CHECKS = ('pinned_unique_spawn', 'same_native_runtime', 'owned_entry_interval', 'one_native_creation',
    'exact_native_identity_pose', 'alive_stationary_unsummoned', 'current_public_target',
    'same_native_catalog', 'no_removal_recreation_or_drift')
_fields = Path(__file__).with_name('world') / 'native_fields.json'
require(hashlib.sha256(_fields.read_bytes()).hexdigest() ==
    '15b87e3f3142d8292cce49c138e46bab167bd86606f9cda1f6c345994ef16b9a', 'native trainer field schema differs')
INDEX = json.loads(_fields.read_text())


def canonical(value):
    return json.loads(json.dumps(value))


def packet_key(p):
    return tuple(p.get(k) for k in ('session', 'time', 'direction', 'name', 'body'))


def spawn_source_value():
    """Read the sole explicitly pinned root observation, without SQL or input."""
    body = Path(SPAWN_SOURCE['path']).read_bytes()
    require(hashlib.sha256(body).hexdigest() == SPAWN_SOURCE['sha256'], 'pinned trainer spawn source bytes differ')
    return json.loads(body)


def spawn_guard(spawn, spawn_source, runtime):
    require(spawn_source == SPAWN_SOURCE and spawn.get('schema') == 'client442_read_only_trainer_spawn_uniqueness_v1' and
        spawn.get('query') == QUERY and spawn.get('rows') == [TRAINER_ROW] and spawn.get('expected') == TRAINER_ROW and
        spawn.get('checks') == {'sole_entry_map_spawn': True} and spawn.get('native') == NATIVE and
        all(spawn.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added')) and
        type(spawn.get('recorded_at')) in (int, float) and math.isfinite(spawn['recorded_at']) and
        isinstance(runtime, dict) and runtime.get('worldserver') == NATIVE,
        'frozen unique trainer spawn or native runtime authority differs')


def target_guard(target):
    require(isinstance(target, dict) and target.get('guid') == PUBLIC_GUID and
        target.get('name') == TRAINER_NAME and target.get('visible') is True and
        target.get('exists') is True and target.get('player') is False and
        target.get('health') == target.get('max_health') == 230,
        'current public frozen trainer identity or living state differs')


def catalog_value(packet):
    reader = Reader(bytes.fromhex(packet['body']))
    guid, kind, trainer, count = reader.unpack('QIII')
    require(count <= 4096, 'native trainer catalog exceeds bound')
    rows = [list(reader.unpack('IBIBII2iII')) for _ in range(count)]
    greeting = reader.raw(len(reader.data) - reader.pos)
    require(len(greeting) <= 2048 and greeting.endswith(b'\0') and b'\0' not in greeting[:-1],
        'native trainer greeting boundary differs')
    reader.end()
    return {'packet': packet, 'guid': guid, 'trainer': trainer, 'kind': kind, 'rows': rows}


def fields_guard(fields):
    def pair(name):
        offset = INDEX[name]
        return fields.get(offset, 0) | fields.get(offset + 1, 0) << 32
    require(fields.get(INDEX['OBJECT_FIELD_ENTRY']) == 46983 and
        fields.get(INDEX['UNIT_FIELD_HEALTH']) == fields.get(INDEX['UNIT_FIELD_MAXHEALTH']) == 230 and
        fields.get(INDEX['UNIT_NPC_FLAGS']) == 49 and
        not pair('UNIT_FIELD_SUMMONEDBY') and not pair('UNIT_FIELD_CREATEDBY') and
        not fields.get(INDEX['UNIT_CREATED_BY_SPELL'], 0) and not fields.get(INDEX['UNIT_FIELD_PETNUMBER'], 0),
        'native trainer entry, health, service or unsummoned identity differs')


def facing_only(body):
    """Exact native facing-angle spline with zero XYZ displacement."""
    r = Reader(body)
    guid = native_guid(r)
    exit_voluntary, = r.unpack('B')
    position = list(r.unpack('3f'))
    sequence, face = r.unpack('IB')
    require(face == 4, 'frozen trainer movement is not native facing-only')
    facing, flags, duration, count = r.unpack('fIII')
    require(count == 1, 'frozen trainer movement has a displaced or unsupported path')
    point = list(r.unpack('3f'))
    r.end()
    expected = [struct.unpack('<f', struct.pack('<f', v))[0] for v in TRAINER_ROW[4:7]]
    require(guid == TRAINER_GUID and exit_voluntary == 0 and position == point == expected and
        flags == 0x100000 and duration == 1 and math.isfinite(facing) and 0 <= facing < math.tau,
        'frozen trainer native facing-only XYZ, flags or duration differs')
    return {'guid': guid, 'exit_voluntary': False, 'position': position, 'sequence': sequence,
        'face': face, 'facing': facing, 'flags': flags, 'duration': duration, 'points': [point], 'deltas': ''}


def teleport_guid(body):
    """Decode the native MoveUpdateTeleport GUID, including transport fields."""
    r = Reader(body)
    r.raw(12)
    no_o, spline, no_flags = [r.bits(1) for _ in range(3)]
    present = {i: r.bits(1) for i in (2, 4, 6)}
    fall = r.bits(1)
    present[0] = r.bits(1)
    transport = r.bits(1)
    present[5] = r.bits(1)
    if transport:
        tp = {i: r.bits(1) for i in (1, 4, 5, 3, 0)}
        time2 = r.bits(1)
        tp.update({i: r.bits(1) for i in (7, 6)})
        vehicle = r.bits(1)
        tp[2] = r.bits(1)
    r.bits(1)
    present.update({i: r.bits(1) for i in (7, 3)})
    no_pitch, no_flags2, no_time = [r.bits(1) for _ in range(3)]
    fall_direction = r.bits(1) if fall else 0
    if not no_flags2: r.bits(12)
    no_elevation = r.bits(1)
    if not no_flags: r.bits(30)
    present[1] = r.bits(1)
    r.align()
    octets = [0] * 8
    def octet(i):
        if present[i]: octets[i] = r.raw(1)[0] ^ 1
    octet(7)
    if transport:
        def tbyte(i):
            if tp[i]: r.raw(1)
        tbyte(3); tbyte(4); r.raw(4)
        if vehicle: r.raw(4)
        tbyte(1)
        if time2: r.raw(4)
        r.raw(4)
        for i in (7, 0, 6, 5, 2): tbyte(i)
        r.raw(13)
    octet(6)
    if not no_pitch: r.raw(4)
    if not no_elevation: r.raw(4)
    if not no_o: r.raw(4)
    for i in (2, 3, 1): octet(i)
    if fall: r.raw(8 + (12 if fall_direction else 0))
    for i in (5, 4): octet(i)
    if not no_time: r.raw(4)
    octet(0)
    r.end()
    return sum(v << (8 * i) for i, v in enumerate(octets))


def replay(rows, session, since, until, catalog):
    require(type(session) is str and session and all(type(t) in (int, float) and math.isfinite(t)
        for t in (since, until)) and since < until, 'exact owned trainer interval differs')
    scoped = sorted([p for p in rows if p.get('session') == session and
        since <= p.get('time', 0) <= until and p.get('direction') == 'from_native' and
        p.get('name') in ('SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT', 'SMSG_TRAINER_LIST',
            'SMSG_ON_MONSTER_MOVE', 'SMSG_ON_MONSTER_MOVE_TRANSPORT', 'SMSG_MOVE_UPDATE_TELEPORT')], key=lambda p: p['time'])
    creations, relevant, updates, facings, fields, pose = [], [], [], [], None, None
    for packet in scoped:
        name = packet['name']
        if name == 'SMSG_MOVE_UPDATE_TELEPORT':
            require(teleport_guid(bytes.fromhex(packet['body'])) != TRAINER_GUID,
                'frozen stationary trainer received native position teleport')
            continue
        if name in ('SMSG_ON_MONSTER_MOVE', 'SMSG_ON_MONSTER_MOVE_TRANSPORT'):
            if native_guid(Reader(bytes.fromhex(packet['body']))) == TRAINER_GUID:
                require(name == 'SMSG_ON_MONSTER_MOVE' and fields is not None,
                    'frozen trainer received transport movement or movement before creation')
                try:
                    parsed = facing_only(bytes.fromhex(packet['body']))
                except (ValueError, struct.error) as error:
                    raise RuntimeError('frozen trainer movement shape is unsupported: ' + str(error)) from error
                facings.append({'packet': packet, 'parsed': parsed})
                pose = parsed['position'] + [parsed['facing']]
                relevant.append(packet)
            continue
        if name == 'SMSG_TRAINER_LIST':
            parsed = catalog_value(packet)
            if (parsed['guid'] >> 32) & 0xfffff == 46983:
                require(parsed['guid'] == TRAINER_GUID, 'native trainer catalog substituted another runtime counter')
            if parsed['guid'] == TRAINER_GUID:
                require(parsed['trainer'] == TRAINER and parsed['kind'] == 0 and
                    [r for r in parsed['rows'] if r[0] == SPELL] == [LESSON], 'fresh native1462 trainer catalog differs')
                relevant.append(packet)
            continue
        if name == 'SMSG_DESTROY_OBJECT':
            body = bytes.fromhex(packet['body'])
            require(len(body) >= 8 and struct.unpack_from('<Q', body)[0] != TRAINER_GUID,
                'frozen trainer was destroyed')
            continue
        touched = False
        for obj in records(bytes.fromhex(packet['body'])):
            require(TRAINER_GUID not in obj.get('removed', []), 'frozen trainer was removed')
            if obj.get('kind') == 3 and obj.get('fields', {}).get(INDEX['OBJECT_FIELD_ENTRY']) == 46983:
                require(obj.get('guid') == TRAINER_GUID, 'another native46983 creation breaks sole frozen trainer identity')
            if obj.get('guid') != TRAINER_GUID:
                continue
            touched = True
            require(obj.get('map') == 0, 'native trainer map differs')
            if obj.get('update_type') in (1, 2):
                require(not creations and TRAINER_GUID >> 52 == 0xf13 and
                    (TRAINER_GUID >> 32) & 0xfffff == 46983 and TRAINER_GUID & 0xffffffff == 8474 and
                    obj.get('kind') == 3, 'one frozen native creature creation is required')
                movement = obj.get('movement', {})
                position = [struct.unpack('<f', struct.pack('<f', v))[0] for v in TRAINER_ROW[4:8]]
                require(list(movement.get('position', ())) == position and
                    movement.get('flags') == movement.get('flags2') == 0 and movement.get('pitch') == 0 and
                    not any(obj.get('flags', {}).get(k) for k in ('self', 'transport', 'vehicle', 'victim', 'rotation', 'area')),
                    'exact stationary native trainer float32 pose differs')
                fields = deepcopy(obj['fields'])
                pose = position
                creations.append({'packet': packet, 'object': obj})
            else:
                require(fields is not None and obj.get('update_type') == 0,
                    'native trainer update precedes its owned creation')
                fields.update(obj.get('fields', {}))
                updates.append(packet)
            fields_guard(fields)
        if touched:
            relevant.append(packet)
        require(len(relevant) <= 20000, 'attributed native trainer identity interval exceeds bound')
    require(len(creations) == 1 and fields is not None, 'one attributed native frozen trainer creation is required')
    require(len(relevant) <= 20000, 'attributed native trainer identity interval exceeds bound')
    require(isinstance(catalog, dict) and catalog.get('packet') is not None and
        catalog == catalog_value(catalog['packet']) and catalog.get('guid') == TRAINER_GUID and
        catalog.get('trainer') == TRAINER and catalog.get('kind') == 0 and
        [r for r in catalog.get('rows', []) if r[0] == SPELL] == [LESSON] and
        any(packet_key(p) == packet_key(catalog['packet']) for p in relevant) and
        creations[0]['packet']['time'] < catalog['packet']['time'] <= until,
        'source-bound trainer catalog does not match current native creation')
    return creations[0], updates, fields, relevant, facings, pose


def trainer_identity(rows, session, since, until, target, catalog, runtime, spawn, spawn_source, *, entry_ref):
    spawn_guard(spawn, spawn_source, runtime)
    target_guard(target)
    require(isinstance(entry_ref, dict) and set(entry_ref) == {'path', 'sha256'} and
        Path(entry_ref['path']).is_absolute() and Path(entry_ref['path']).is_relative_to(lab.ROOT / 'evidence') and
        Path(entry_ref['path']).name == 'episode.json' and isinstance(entry_ref['sha256'], str) and
        len(entry_ref['sha256']) == 64 and all(c in '0123456789abcdef' for c in entry_ref['sha256']),
        'trainer identity requires its immutable owned entry source')
    creation, updates, fields, relevant, facings, pose = replay(rows, session, since, until, catalog)
    return canonical({'schema': SCHEMA, 'native_session': session, 'source_interval': [since, until],
        'entry_source': entry_ref, 'runtime': runtime, 'spawn_source': spawn_source, 'spawn': spawn,
        'target': target, 'native_catalog': catalog, 'creation': creation, 'update_packets': updates,
        'final_fields': fields, 'wire_packets': relevant, 'facing_packets': facings, 'final_pose': pose,
        'checks': {k: True for k in CHECKS}})


def validate_trainer_identity(proof, target, catalog, runtime, entry_ref, wire=None, observed_until=None):
    require(isinstance(proof, dict) and proof.get('schema') == SCHEMA and proof.get('checks') ==
        {k: True for k in CHECKS}, 'complete frozen trainer identity proof differs')
    target_guard(target)
    require(target == proof.get('target') and catalog == proof.get('native_catalog') and
        runtime == proof.get('runtime') and entry_ref == proof.get('entry_source'),
        'immutable trainer source, public target, catalog or runtime changed')
    since, until = proof['source_interval']
    source_rows = proof['wire_packets'] if wire is None else list(wire)
    expected = trainer_identity(source_rows, proof['native_session'], since, until, target, catalog,
        runtime, proof['spawn'], proof['spawn_source'], entry_ref=entry_ref)
    require(proof == expected, 'frozen trainer proof differs from supplied native packet replay')
    if observed_until is not None:
        require(wire is not None and type(observed_until) in (int, float) and math.isfinite(observed_until) and
            observed_until >= until, 'extended current trainer interval requires raw wire')
        replay(source_rows, proof['native_session'], since, observed_until, catalog)
    return proof

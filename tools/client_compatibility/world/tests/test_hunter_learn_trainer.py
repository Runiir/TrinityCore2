"""Frozen UI170 trainer proof uses supplied bytes, never a live service."""
from copy import deepcopy
import hashlib
import json
import struct

import pytest

from tools.client_compatibility import hunter_learn_trainer as trainer
from tools.client_compatibility import hunter_learn_contract as contract
from tools.client_compatibility.world.buffer import Writer


SPAWN_BYTES = b'''{
  "schema": "client442_read_only_trainer_spawn_uniqueness_v1",
  "recorded_at": 1791407847.1633081,
  "query": "SELECT c.guid,c.id,t.name,c.map,c.position_x,c.position_y,c.position_z,c.orientation,COALESCE(NULLIF(c.npcflag,0),t.npcflag),c.MovementType,ct.TrainerId FROM client442_world.creature c JOIN client442_world.creature_template t ON t.entry=c.id JOIN client442_world.creature_trainer ct ON ct.CreatureId=c.id WHERE c.id=46983 AND c.map=0 ORDER BY c.guid",
  "rows": [
    [
      280678,
      46983,
      "Benjamin Foxworthy",
      0,
      -9464.94,
      117.432,
      58.046,
      1.39626,
      49,
      0,
      40
    ]
  ],
  "expected": [
    280678,
    46983,
    "Benjamin Foxworthy",
    0,
    -9464.94,
    117.432,
    58.046,
    1.39626,
    49,
    0,
    40
  ],
  "checks": {
    "sole_entry_map_spawn": true
  },
  "native": {
    "pid": 2977495,
    "start_ticks": "54227939"
  },
  "prior_diagnostic_errors": [
    "Root initialread-only query used nonexistent creature_template.trainer_id; corrected byactual creature_trainer.TrainerId schema.",
    "Firstpost-querymetadataattempt assumedoptionalengine key; fixed to existingidentity projection. Allqueryassertionspassed, no mutation."
  ],
  "input_sent": false,
  "mutation_sent": false,
  "qualification_added": false
}
'''


def packed_guid(guid):
    octets = [(guid >> (i * 8)) & 255 for i in range(8)]
    return bytes([sum(bool(v) << i for i, v in enumerate(octets))]) + bytes(v for v in octets if v)


def object_body(fields=None, *, guid=contract.TRAINER_GUID, creation=True, map_id=0, position=None, movement_flags=0):
    fields = {trainer.INDEX['OBJECT_FIELD_ENTRY']: 46983, trainer.INDEX['UNIT_FIELD_HEALTH']: 230,
              trainer.INDEX['UNIT_FIELD_MAXHEALTH']: 230, trainer.INDEX['UNIT_NPC_FLAGS']: 49} if fields is None else fields
    position = contract.TRAINER_ROW[4:8] if position is None else position
    prefix = struct.pack('<HIB', map_id, 1, 1 if creation else 0) + packed_guid(guid)
    if creation:
        # Installed creature creation uses the unit-movement layout, even while idle.
        w = Writer().bits(1, 8).bits(0, 24).bits(0, 6)
        w.bits(0, 1).bits(0, 1).bits(0, 3).bits(movement_flags, 30)
        for bit in (0, 1, 0, 0, 1, 0, 0, 0, 0, 0, 0, 0, 0, 1):
            w.bits(bit, 1)
        x, y, z, facing = position
        w.pack('ff', 4.5, 2.5).pack('f', z).pack('ff', x, 3.14).pack('ff', 4.722221851348877, y)
        w.pack('fIf', 2.5, 15959226, 3.1415939331054688).pack('fff', 7.0, facing, 8.000020027160645).pack('f', 4.5)
        prefix += bytes([3]) + w.finish()
    count = max(fields) // 32 + 1
    masks = [sum(1 << (i % 32) for i in fields if i // 32 == block) for block in range(count)]
    return prefix + struct.pack('<B' + 'I' * count, count, *masks) + b''.join(struct.pack('<I', fields[i]) for i in sorted(fields))


def packet(name, body, at, session='native-owned-hunter'):
    return {'session': session, 'direction': 'from_native', 'name': name, 'body': body.hex(), 'time': at}


def facing_body(*, position=None, point=None, angle=1.2790659666061401, face=4, flags=0x100000,
                duration=1, count=1, exit_voluntary=0, guid=contract.TRAINER_GUID):
    position = contract.TRAINER_ROW[4:7] if position is None else position
    point = position if point is None else point
    return packed_guid(guid) + struct.pack('<B3fIBfIII3f', exit_voluntary, *position, 23524, face, angle, flags,
                                          duration, count, *point)


def teleport_body(guid):
    octets = [(guid >> (i * 8)) & 255 for i in range(8)]
    w = Writer().pack('3f', 58, 117, -9464)
    w.bits(1, 1).bits(0, 1).bits(1, 1)
    for i in (2, 4, 6): w.bits(bool(octets[i]), 1)
    w.bits(0, 1).bits(bool(octets[0]), 1).bits(0, 1).bits(bool(octets[5]), 1)
    w.bits(0, 1)
    for i in (7, 3): w.bits(bool(octets[i]), 1)
    w.bits(1, 1).bits(1, 1).bits(1, 1).bits(1, 1).bits(bool(octets[1]), 1)
    w.flush()
    for i in (7, 6, 2, 3, 1, 5, 4, 0):
        if octets[i]: w.raw(bytes([octets[i] ^ 1]))
    return w.finish()


def trainer_fixture(*, runtime=None, entry_ref=None, since=1010.0, until=1011.34, catalog_at=1011.32, with_facing=False):
    runtime = {'worldserver': deepcopy(trainer.NATIVE)} if runtime is None else runtime
    entry_ref = {'path': str(trainer.lab.ROOT / 'evidence/synthetic/entry0/episode.json'), 'sha256': 'a' * 64} if entry_ref is None else entry_ref
    target = {'guid': trainer.PUBLIC_GUID, 'name': contract.TRAINER_NAME, 'visible': True, 'exists': True,
              'player': False, 'health': 230, 'max_health': 230, 'position': []}
    creation = packet('SMSG_UPDATE_OBJECT', object_body(), since + .4)
    body = struct.pack('<QIII', contract.TRAINER_GUID, 0, 40, 1) + struct.pack('<IBIBII2iII', *trainer.LESSON) + b'Hello!\0'
    catalog_packet = packet('SMSG_TRAINER_LIST', body, catalog_at)
    catalog = trainer.catalog_value(catalog_packet)
    rows = [creation, catalog_packet]
    if with_facing:
        rows.append(packet('SMSG_ON_MONSTER_MOVE', facing_body(), since + .41))
    proof = trainer.trainer_identity(rows, creation['session'], since, until, target, catalog, runtime,
                                     json.loads(SPAWN_BYTES), deepcopy(trainer.SPAWN_SOURCE), entry_ref=entry_ref)
    return proof, rows


def test_actual_native_facing_shape_keeps_exact_xyz_and_carries_original_packet():
    assert facing_body().hex() == 'f31a2187b730f100c3e313c62fddea421b2f6842e45b0000046fb8a33f000010000100000001000000c3e313c62fddea421b2f6842'
    proof, rows = trainer_fixture(with_facing=True)
    assert len(proof['facing_packets']) == 1
    assert proof['facing_packets'][0]['packet'] == rows[-1]
    assert proof['final_pose'] == proof['creation']['object']['movement']['position'][:3] + [1.2790659666061401]
    assert trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows) == proof
    rows.append(packet('SMSG_ON_MONSTER_MOVE', facing_body(angle=2), 1011.9))
    assert trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows, observed_until=1012) == proof


@pytest.mark.parametrize('fault', ['position', 'point', 'flags', 'duration', 'count', 'exit', 'face', 'nan', 'negative', 'suffix', 'truncated', 'transport'])
def test_facing_allowance_never_accepts_position_movement_or_unsupported_shape(fault):
    proof, rows = trainer_fixture()
    kwargs = {'position': {'position': [-9464, 117, 58]}, 'point': {'point': [-9464, 117, 58]},
        'flags': {'flags': 0x100001}, 'duration': {'duration': 2}, 'count': {'count': 2},
        'exit': {'exit_voluntary': 1}, 'face': {'face': 0}, 'nan': {'angle': float('nan')},
        'negative': {'angle': -1}}.get(fault, {})
    body = facing_body(**kwargs)
    if fault == 'suffix': body += b'ignored'
    if fault == 'truncated': body = body[:-1]
    name = 'SMSG_ON_MONSTER_MOVE_TRANSPORT' if fault == 'transport' else 'SMSG_ON_MONSTER_MOVE'
    rows.append(packet(name, body, 1011.9))
    with pytest.raises(RuntimeError):
        trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows, observed_until=1012)


def test_native_creature_teleport_decoder_rejects_trainer_and_allows_foreign_pet():
    proof, rows = trainer_fixture()
    assert trainer.teleport_guid(teleport_body(contract.TRAINER_GUID)) == contract.TRAINER_GUID
    pet = (0xf14 << 52) | (299 << 32) | 16
    assert trainer.teleport_guid(teleport_body(pet)) == pet
    rows.append(packet('SMSG_MOVE_UPDATE_TELEPORT', teleport_body(pet), 1011.9))
    assert trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows, observed_until=1012) == proof
    rows.append(packet('SMSG_MOVE_UPDATE_TELEPORT', teleport_body(contract.TRAINER_GUID), 1011.95))
    with pytest.raises(RuntimeError, match='teleport'):
        trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows, observed_until=1012)


def test_pinned_fixture_bytes_and_frozen_counter_are_exact():
    assert hashlib.sha256(SPAWN_BYTES).hexdigest() == trainer.SPAWN_SOURCE['sha256']
    assert contract.TRAINER_GUID == 0xf130b7870000211a
    assert contract.TRAINER_GUID & 0xffffffff == 8474 != contract.TRAINER_ROW[0]


def test_native_creation_catalog_and_public_target_bind_one_immutable_trainer():
    proof, rows = trainer_fixture()
    assert trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'],
                                            proof['entry_source'], wire=rows, observed_until=1012) == proof
    assert proof['creation']['object']['flags']['movement'] == 1
    assert proof['creation']['object']['flags']['stationary'] == 0
    assert proof['creation']['object']['movement']['position'] == [-9464.9404296875, 117.43199920654297, 58.04600143432617, 1.3962600231170654]
    assert len(proof['checks']) == 9 and all(proof['checks'].values())


@pytest.mark.parametrize('fault', ['missing_creation', 'duplicate_creation', 'wrong_counter', 'wrong_entry', 'wrong_map',
    'wrong_position', 'moving', 'health', 'max_health', 'npcflags', 'summoned', 'created', 'created_spell', 'pet_number',
    'removed', 'destroyed', 'recreated', 'dead_update', 'summoned_update', 'catalog_missing', 'catalog_guid',
    'catalog_cost', 'catalog_trainer', 'catalog_suffix', 'catalog_nonterminated', 'catalog_overlong', 'catalog_before_creation'])
def test_identity_rejects_unattributable_creation_or_catalog_and_hidden_state_changes(fault):
    proof, rows = trainer_fixture()
    fields = {int(k): v for k, v in proof['final_fields'].items()}
    if fault == 'missing_creation':
        rows.pop(0)
    elif fault == 'duplicate_creation':
        rows.insert(1, deepcopy(rows[0]))
    elif fault == 'wrong_counter':
        rows[0]['body'] = object_body(guid=17379592752471406478).hex()
    elif fault == 'wrong_entry':
        fields[trainer.INDEX['OBJECT_FIELD_ENTRY']] += 1
        rows[0]['body'] = object_body(fields).hex()
    elif fault == 'wrong_map':
        rows[0]['body'] = object_body(map_id=1).hex()
    elif fault == 'wrong_position':
        rows[0]['body'] = object_body(position=[*contract.TRAINER_ROW[4:7], 0]).hex()
    elif fault == 'moving':
        rows[0]['body'] = object_body(movement_flags=1).hex()
    elif fault in ('health', 'max_health', 'npcflags', 'summoned', 'created', 'created_spell', 'pet_number'):
        key = {'health': 'UNIT_FIELD_HEALTH', 'max_health': 'UNIT_FIELD_MAXHEALTH', 'npcflags': 'UNIT_NPC_FLAGS',
               'summoned': 'UNIT_FIELD_SUMMONEDBY', 'created': 'UNIT_FIELD_CREATEDBY', 'created_spell': 'UNIT_CREATED_BY_SPELL',
               'pet_number': 'UNIT_FIELD_PETNUMBER'}[fault]
        fields[trainer.INDEX[key]] = 1
        rows[0]['body'] = object_body(fields).hex()
    elif fault in ('removed', 'destroyed', 'recreated', 'dead_update', 'summoned_update'):
        if fault == 'removed':
            body = struct.pack('<HIBI', 0, 1, 3, 1) + packed_guid(contract.TRAINER_GUID)
            name = 'SMSG_UPDATE_OBJECT'
        elif fault == 'destroyed':
            body, name = struct.pack('<Q', contract.TRAINER_GUID), 'SMSG_DESTROY_OBJECT'
        elif fault == 'recreated':
            body, name = object_body(), 'SMSG_UPDATE_OBJECT'
        else:
            field = 'UNIT_FIELD_HEALTH' if fault == 'dead_update' else 'UNIT_FIELD_SUMMONEDBY'
            body, name = object_body({trainer.INDEX[field]: 0 if fault == 'dead_update' else 6}, creation=False), 'SMSG_UPDATE_OBJECT'
        rows.insert(1, packet(name, body, 1011.0))
    elif fault == 'catalog_missing':
        rows.pop()
    elif fault == 'catalog_before_creation':
        rows[1]['time'] = 1010.1
        proof['native_catalog']['packet']['time'] = 1010.1
    else:
        body = bytes.fromhex(rows[1]['body'])
        if fault == 'catalog_guid':
            body = struct.pack('<Q', contract.TRAINER_GUID + 1) + body[8:]
        elif fault == 'catalog_cost':
            body = body[:25] + struct.pack('<I', 645) + body[29:]
        elif fault == 'catalog_trainer':
            body = body[:12] + struct.pack('<I', 41) + body[16:]
        elif fault == 'catalog_suffix':
            body += b'ignored'
        elif fault == 'catalog_overlong':
            body = body[:-7] + b'x' * 2048 + b'\0'
        else:
            body = body[:-1]
        rows[1]['body'] = body.hex()
    with pytest.raises((RuntimeError, ValueError)):
        trainer.trainer_identity(rows, proof['native_session'], *proof['source_interval'], proof['target'],
                                 proof['native_catalog'], proof['runtime'], proof['spawn'], proof['spawn_source'], entry_ref=proof['entry_source'])


@pytest.mark.parametrize('fault', ['runtime', 'spawn_sha', 'spawn_path', 'spawn_row', 'spawn_query', 'spawn_checks',
    'spawn_native', 'spawn_mutation', 'public_guid', 'public_name', 'public_visible', 'public_health', 'entry',
    'claimed_fields', 'claimed_checks', 'claimed_creation', 'claimed_interval'])
def test_validation_rejects_changed_authority_or_claims(fault):
    proof, rows = trainer_fixture()
    if fault == 'runtime':
        proof['runtime']['worldserver']['pid'] += 1
    elif fault == 'spawn_sha':
        proof['spawn_source']['sha256'] = 'f' * 64
    elif fault == 'spawn_path':
        proof['spawn_source']['path'] += '.substitute'
    elif fault == 'spawn_row':
        proof['spawn']['rows'][0][0] += 1
    elif fault == 'spawn_query':
        proof['spawn']['query'] += ' LIMIT 1'
    elif fault == 'spawn_checks':
        proof['spawn']['checks']['sole_entry_map_spawn'] = False
    elif fault == 'spawn_native':
        proof['spawn']['native']['start_ticks'] = 'other'
    elif fault == 'spawn_mutation':
        proof['spawn']['mutation_sent'] = True
    elif fault.startswith('public_'):
        key = fault.removeprefix('public_')
        proof['target'][key] = {'guid': 'Creature-0-1-0-0-46983-000002F78E', 'name': 'Other', 'visible': False, 'health': 0}[key]
    elif fault == 'entry':
        proof['entry_source']['path'] = '/tmp/borrowed/episode.json'
    elif fault == 'claimed_fields':
        proof['final_fields'][str(trainer.INDEX['UNIT_FIELD_HEALTH'])] -= 1
    elif fault == 'claimed_checks':
        proof['checks']['one_native_creation'] = False
    elif fault == 'claimed_creation':
        proof['creation']['object']['guid'] += 1
    else:
        proof['source_interval'][0] = 1011
    with pytest.raises((RuntimeError, ValueError)):
        trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows)


@pytest.mark.parametrize('late', ['destroyed', 'removed', 'recreated', 'foreign_creation', 'entry', 'health', 'npcflags', 'summoned', 'movement', 'transport_movement', 'pet_number'])
def test_pretrain_extension_replays_actual_wire_without_mutating_initial_proof(late):
    proof, rows = trainer_fixture()
    old = deepcopy(proof)
    if late in ('movement', 'transport_movement'):
        body = packed_guid(contract.TRAINER_GUID)
        name = 'SMSG_ON_MONSTER_MOVE' if late == 'movement' else 'SMSG_ON_MONSTER_MOVE_TRANSPORT'
    elif late == 'destroyed':
        body, name = struct.pack('<Q', contract.TRAINER_GUID), 'SMSG_DESTROY_OBJECT'
    elif late == 'removed':
        body, name = struct.pack('<HIBI', 0, 1, 3, 1) + packed_guid(contract.TRAINER_GUID), 'SMSG_UPDATE_OBJECT'
    elif late == 'recreated':
        body, name = object_body(), 'SMSG_UPDATE_OBJECT'
    elif late == 'foreign_creation':
        body, name = object_body(guid=contract.TRAINER_GUID + 1), 'SMSG_UPDATE_OBJECT'
    else:
        field = {'entry': 'OBJECT_FIELD_ENTRY', 'health': 'UNIT_FIELD_HEALTH', 'npcflags': 'UNIT_NPC_FLAGS',
                 'summoned': 'UNIT_FIELD_SUMMONEDBY', 'pet_number': 'UNIT_FIELD_PETNUMBER'}[late]
        body, name = object_body({trainer.INDEX[field]: 1}, creation=False), 'SMSG_UPDATE_OBJECT'
    rows.append(packet(name, body, 1011.9))
    assert trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows) == proof
    with pytest.raises(RuntimeError):
        trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows, observed_until=1012)
    assert proof == old


def test_prior_failed_open_catalog_and_unrelated_updates_do_not_replace_current_catalog():
    proof, rows = trainer_fixture()
    prior = deepcopy(rows[-1])
    prior['time'] = 1011.1
    unrelated = packet('SMSG_UPDATE_OBJECT', object_body({trainer.INDEX['OBJECT_FIELD_ENTRY']: 299}, guid=123), 1011.2)
    rows.extend([prior, unrelated])
    proof = trainer.trainer_identity(rows, proof['native_session'], *proof['source_interval'], proof['target'],
        proof['native_catalog'], proof['runtime'], proof['spawn'], proof['spawn_source'], entry_ref=proof['entry_source'])
    assert trainer.validate_trainer_identity(proof, proof['target'], proof['native_catalog'], proof['runtime'], proof['entry_source'], wire=rows) == proof
    assert len([p for p in proof['wire_packets'] if p['name'] == 'SMSG_TRAINER_LIST']) == 2

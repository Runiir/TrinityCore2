"""Native creation evidence and conservative timing for one disposable Revive."""
from copy import deepcopy
import math
import struct
from .interaction_pet_dismiss import Presence
from .interaction_pet_target import pair
from .interaction_pet_summon import cast_identity
from .world.native_objects import records
from .world.native_objects import guid as native_guid
from .world.buffer import Reader
from .world.objects import INDEX


# Creature's default corpse delay is 60 seconds. Its expiry is set from integer
# GameTime seconds; reserve that first partial second. The clock is bound to
# ordinary CallPet chat setup BEFORE native handling, never packet receipt.
CORPSE_SECONDS = 59
MAX_SETUP_AGE = 25
MIN_SUBMISSION_REMAINING = 15  # 10-second Revive plus Return and scheduler margin.


class RevivePresence(Presence):
    def __init__(self, session, owner, started):
        super().__init__(session, owner, started)
        self.creations = {}
        self.destructions = {}
        self.call_requests = []
        self.lifetime_lower_bounds = {}
        self.owner_creation = None
        self.native_vital_packets = []
        self.pet_max_health_updates = []

    def inspect_packet(self, packet):
        if packet.get('name') == 'CMSG_CAST_SPELL' and packet.get('direction') == 'to_native':
            if cast_identity(packet)['spell'] == 883: self.call_requests.append(deepcopy(packet))
        if packet.get('direction') != 'from_native': return
        if packet.get('name') == 'SMSG_DESTROY_OBJECT':
            guid = struct.unpack_from('<Q', bytes.fromhex(packet['body']))[0]
            self.destructions.setdefault(guid, deepcopy(packet))
        if packet.get('name') != 'SMSG_UPDATE_OBJECT': return
        retained = False
        for row in records(bytes.fromhex(packet['body'])):
            fields = row.get('fields', {})
            if row.get('guid') == self.owner and row.get('kind') == 4 and self.owner_creation is None:
                self.owner_creation = {'packet': deepcopy(packet), 'object': deepcopy(row)}
            if (row.get('update_type') in (1, 2) and row.get('kind') == 3 and
                row['guid'] >> 52 == 0xf14 and pair(row.get('fields', {}), 'UNIT_FIELD_SUMMONEDBY') == self.owner):
                # Seeing an existing object again must not restart its corpse
                # clock. Sparse fields and pet-name timestamps never set it.
                self.creations.setdefault(row['guid'], {'packet': deepcopy(packet), 'object': deepcopy(row)})
            creation = self.creations.get(row.get('guid'))
            owned_wolf = bool(creation and dead_identity(creation['object'], self.owner))
            if owned_wolf and INDEX['UNIT_FIELD_MAXHEALTH'] in fields:
                self.pet_max_health_updates.append({'guid': row['guid'], 'max_health': fields[INDEX['UNIT_FIELD_MAXHEALTH']],
                    'packet': deepcopy(packet)})
            if not retained and (owned_wolf or row.get('guid') == self.owner) and any(INDEX[n] in fields for n in
                ('UNIT_FIELD_HEALTH', 'UNIT_FIELD_MAXHEALTH', 'UNIT_FIELD_POWER1', 'UNIT_FIELD_MAXPOWER1')):
                self.native_vital_packets.append(deepcopy(packet))
                retained = True
            for guid in row.get('removed', []):
                self.destructions.setdefault(guid, deepcopy(packet))


def dead_identity(pet, owner=6):
    fields = pet.get('fields', {}) if pet else {}
    return bool(pet and pet.get('guid', 0) >> 52 == 0xf14 and
        fields.get(INDEX['UNIT_FIELD_PETNUMBER']) == 16 and fields.get(INDEX['OBJECT_FIELD_ENTRY']) == 299 and
        pair(fields, 'UNIT_FIELD_SUMMONEDBY') == owner and
        fields.get(INDEX['UNIT_CREATED_BY_SPELL']) in (13481, 883) and
        fields.get(INDEX['UNIT_FIELD_HEALTH'], 0) == 0 and fields.get(INDEX['UNIT_FIELD_MAXHEALTH'], 0) > 0)


def corpse_budget(oracle, now):
    """Use this native object's first creation packet, never a saved/name clock."""
    pet = oracle.pet
    creation = oracle.creations.get(pet['guid']) if pet else None
    packet = creation['packet'] if creation else {}
    created = packet.get('time')
    if (not dead_identity(pet, oracle.owner) or not creation or
        not dead_identity(creation['object'], oracle.owner) or creation['object']['guid'] != pet['guid'] or
        packet.get('name') != 'SMSG_UPDATE_OBJECT' or packet.get('direction') != 'from_native' or
        packet.get('session') != oracle.session or
        type(created) not in (int, float) or not math.isfinite(created) or created < oracle.started or
        type(now) not in (int, float) or not math.isfinite(now) or now < created):
        raise RuntimeError('dead Wolf16 lacks valid same-entry native creation timing')
    age = now - created
    lower_bound = oracle.lifetime_lower_bounds.get(pet['guid'])
    started = lower_bound['started_at'] if lower_bound else None
    remaining = CORPSE_SECONDS - (now - started) if started is not None else None
    return {'guid': pet['guid'], 'pet_number': 16, 'created_at': created, 'observed_at': now,
        'age_seconds': age, 'conservative_corpse_seconds': CORPSE_SECONDS, 'remaining_seconds': remaining,
        'lifetime_started_at': started, 'lifetime_age_seconds': now - started if started is not None else None,
        'lifetime_source': lower_bound, 'native_present': oracle.present(),
        'setup_budget': bool(lower_bound and age <= MAX_SETUP_AGE and remaining >= MIN_SUBMISSION_REMAINING),
        'submission_budget': bool(lower_bound and remaining >= MIN_SUBMISSION_REMAINING),
        'max_setup_age_seconds': MAX_SETUP_AGE, 'minimum_submission_remaining_seconds': MIN_SUBMISSION_REMAINING,
        'creation_packet': packet}


def bind_call_lifetime(oracle, started_at, requests, previous_guid):
    """Bind this creation to one actual883 and its earlier fixture input setup."""
    pet = oracle.pet
    creation = oracle.creations.get(pet['guid']) if pet else None
    previous = oracle.creations.get(previous_guid)
    destruction = oracle.destructions.get(previous_guid)
    if (not creation or not dead_identity(pet, oracle.owner) or not dead_identity(creation['object'], oracle.owner) or
        not previous or not dead_identity(previous['object'], oracle.owner) or not destruction or
        previous_guid == pet['guid'] or previous_guid not in oracle.removed or
        destruction.get('session') != oracle.session or destruction.get('direction') != 'from_native' or
        destruction.get('name') not in ('SMSG_DESTROY_OBJECT', 'SMSG_UPDATE_OBJECT') or
        len(requests) != 1 or
        requests[0] not in oracle.call_requests or cast_identity(requests[0])['spell'] != 883 or
        type(started_at) not in (int, float) or not math.isfinite(started_at) or
        not oracle.started <= previous['packet']['time'] <= destruction['time'] <= started_at <= requests[0]['time'] <= creation['packet']['time']):
        raise RuntimeError('dead corpse lacks an attributable earlier one-CallPet fixture clock')
    # Native LoadPetData creates from the saved summon spell (13481 or 883).
    # EffectSummonPet sets the current 883 only after loading returns; a sparse
    # update can follow creation. The actual request and new incarnation bind it.
    oracle.lifetime_lower_bounds.setdefault(pet['guid'], {
        'source': 'ordinary_call_pet_fixture_chat_setup_before_native_request',
        'started_at': started_at, 'native_request': deepcopy(requests[0]),
        'previous_guid': previous_guid, 'previous_creation_packet': deepcopy(previous['packet']),
        'destruction_packet': deepcopy(destruction)})


def dead_pet_rows(fixture, current):
    """CallPet may change its own save clock/creator/active flag, never named4."""
    original = fixture['before']['6']['pets']
    if len(current) != 2 or {p.get('id') for p in current} != {4, 16}: return False
    before = {p['id']: p for p in original}
    after = {p['id']: p for p in current}
    disposable = after[16]
    ignored = {'curhealth', 'CreatedBySpell', 'active', 'savetime'}
    return (after[4] == before[4] and disposable.get('curhealth') == 0 and
        disposable.get('CreatedBySpell') in (13481, 883) and disposable.get('active') in (0, 1) and
        disposable.get('savetime', 0) >= before[16]['savetime'] and
        {k: v for k, v in disposable.items() if k not in ignored} ==
            {k: v for k, v in before[16].items() if k not in ignored})


def native_revive_timing(packets, request, lifetime_started_at):
    starts, completions = [], []
    for packet in packets:
        if packet.get('direction') != 'from_native' or packet.get('name') not in ('SMSG_SPELL_START', 'SMSG_SPELL_GO'):
            continue
        reader = Reader(bytes.fromhex(packet['body']))
        caster, unit = native_guid(reader), native_guid(reader)
        counter, spell = reader.unpack('Bi')
        if spell != 982 or counter != request['counter'] or caster != 6 or unit != 6: continue
        row = {'time': packet['time'], 'caster': caster, 'unit': unit, 'counter': counter, 'spell': spell}
        if packet['name'] == 'SMSG_SPELL_START':
            flags, flags_ex, cast_ms = reader.unpack('III')
            row.update(cast_time_ms=cast_ms, flags=flags, flags_ex=flags_ex)
            starts.append(row)
        else: completions.append(row)
    valid = len(starts) == len(completions) == 1
    result = {'starts': starts, 'completions': completions, 'one_matching_start_and_completion': valid}
    if valid:
        start, completion = starts[0], completions[0]
        result.update(actual_cast_seconds=completion['time'] - start['time'],
            native_start_remaining_seconds=lifetime_started_at + CORPSE_SECONDS - start['time'],
            completion_within_conservative_corpse_deadline=completion['time'] < lifetime_started_at + CORPSE_SECONDS,
            native_completion_ordered=completion['time'] >= start['time'],
            native_ten_second_cast=start['cast_time_ms'] == 10000)
    return result

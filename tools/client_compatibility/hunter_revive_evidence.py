"""Pure archived proof of one ordinary Revive and its complete offline closure."""
from copy import deepcopy
import json
import math
from pathlib import Path
import struct
from types import SimpleNamespace
from . import lab_runtime as lab
from .hunter_revive_fixture import dead_snapshot, restored_pets
from .hunter_revive_lifecycle import CORPSE_SECONDS, MIN_SUBMISSION_REMAINING, native_revive_timing
from .interaction_pet_summon import cast_identity
from .interaction_pet_command_probe import expected_guid
from .review_native_feedback_checkpoint import require, packet_key, whole
from .world.native_objects import records
from .world.objects import INDEX
from .world.buffer import Reader, player_high
from .world import casting


NAMES = {name: 'hunter_revive_' + suffix + '/episode.json' for name, suffix in (
    ('fixture', 'fixture01'), ('preparation', 'prepare01'), ('entry', 'entry01'),
    ('recon', 'recon03'), ('cast', 'cast01'), ('park', 'park01'),
    ('finish', 'original_finish01'), ('normalize', 'normalize01'), ('close', 'close02'))}
PAUSE = 'scout_revive_pause01/episode.json'
CAST_NAMES = {'CMSG_CAST_SPELL', 'SMSG_SPELL_START', 'SMSG_SPELL_GO',
    'SMSG_CAST_FAILED', 'SMSG_SPELL_FAILURE', 'SMSG_SPELL_FAILED_OTHER'}
FAILURES = {'SMSG_CAST_FAILED', 'SMSG_SPELL_FAILURE', 'SMSG_SPELL_FAILED_OTHER', 'CMSG_CANCEL_CAST'}
# Pin the reviewed UI169 FLOAT storage sources without reading mutable source
# files from this pure archive verifier.
FLOAT_STORAGE_SOURCES = {
    'src/server/database/Database/Field.cpp': 'eed8ddfa345c74109afa258db9f72c1d7e828e069c4ca1caf7e4ea0275e7b662',
    'src/server/database/Database/QueryResult.cpp': '56ac195234501b795956949846de208c8e5ab2fdaeeee29a56291a404ce6bdc1',
    'src/server/database/Database/MySQLPreparedStatement.cpp': '11dcd2db84b932850149ce4bad4107ba717c07d96c495e58577a91eec5bd4553',
    'sql/base/characters_database.sql': '880d4c7a92c600dd1cbdb4f3a1f388a4631de0cc08a34e176e078a6d8ea03be9'}


def tracking_state():
    return {'packets': set(), 'wire': [], 'events': [], 'instances': set()}


def fields(record):
    return {int(k): v for k, v in record.get('fields', {}).items()}


def pair(values, name):
    index = INDEX[name]
    return values.get(index, 0) | values.get(index + 1, 0) << 32


def same(left, right):
    return json.loads(json.dumps(left)) == json.loads(json.dumps(right))


def window(data):
    cast = data[NAMES['cast']]
    budget = cast['final_submission_corpse_budget']
    since = budget['lifetime_source']['started_at']
    until = cast['cast_finished_at']
    require(type(since) in (int, float) and type(until) in (int, float) and
        math.isfinite(since) and math.isfinite(until) and 0 < until - since < 120,
        'Revive journal window differs')
    return cast, budget, since, until


def relevant(packet, guid):
    if packet.get('name') in CAST_NAMES | FAILURES:
        return True
    if packet.get('direction') != 'from_native': return False
    if packet.get('name') == 'SMSG_DESTROY_OBJECT':
        return struct.unpack_from('<Q', bytes.fromhex(packet['body']))[0] == guid
    if packet.get('name') != 'SMSG_UPDATE_OBJECT': return False
    for row in records(bytes.fromhex(packet['body'])):
        values = fields(row)
        if row.get('guid') in (6, guid) or guid in row.get('removed', []): return True
        if row.get('kind') == 3 and pair(values, 'UNIT_FIELD_SUMMONEDBY') == 6: return True
    return False


def collect(member, lines, data, tracking):
    """Stream only bounded actual packets and metadata for this immutable cast."""
    cast, budget, since, until = window(data)
    entry = data[NAMES['entry']]
    session, guid = cast['native_session'], budget['guid']
    lower = budget['lifetime_source']
    previous = [lower['previous_creation_packet'], lower['destruction_packet']]
    previous_keys = {packet_key(p) for p in previous}
    for packet in lines:
        if member == 'tracking/events.jsonl':
            if (packet.get('event') == 'instance_authenticated' and packet.get('account_id') == 2 and
                entry['started_at'] <= packet.get('time', 0) <= entry['finished_at']):
                tracking['instances'].add(packet['session'])
            prior_metadata = packet.get('event') == 'native_packet' and packet.get('session') == session and any(
                (packet.get('name'), packet.get('direction'), packet.get('bytes')) ==
                (p['name'], p['direction'], len(bytes.fromhex(p['body']))) and
                0 <= p['time'] - packet.get('time', 0) < .1 for p in previous)
            if (packet.get('session') in {session} | tracking['instances'] and
                (since <= packet.get('time', 0) <= until or prior_metadata) and
                packet.get('event') in ('native_packet', 'modern_packet') and
                packet.get('name') in CAST_NAMES | FAILURES | {'SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT'}):
                tracking['events'].append(packet)
        elif member == 'tracking/packets.jsonl' and packet.get('session') == session:
            prior_packet = packet.get('name') in ('SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT') and packet_key(packet) in previous_keys
            in_window = since <= packet.get('time', 0) <= until
            if in_window and packet.get('name') in CAST_NAMES and cast['cast_started_at'] <= packet['time']:
                tracking['packets'].add(packet_key(packet))
            if prior_packet or in_window and relevant(packet, guid): tracking['wire'].append(packet)
        require(len(tracking['packets']) <= 256 and len(tracking['wire']) <= 512 and
            len(tracking['events']) <= 2048 and len(tracking['instances']) <= 1,
            'Revive journal bound exceeded')


def dead_creation(packet, guid, session):
    require(packet['name'] == 'SMSG_UPDATE_OBJECT' and packet['direction'] == 'from_native' and
        packet['session'] == session, 'dead native pet creation attribution differs')
    born = [r for r in records(bytes.fromhex(packet['body'])) if r.get('guid') == guid and r.get('update_type') in (1, 2)]
    require(len(born) == 1 and born[0].get('kind') == 3, 'dead native pet creation differs')
    pet = fields(born[0])
    require(guid >> 52 == 0xf14 and pet.get(INDEX['OBJECT_FIELD_ENTRY']) == 299 and
        pet.get(INDEX['UNIT_FIELD_PETNUMBER']) == 16 and pair(pet, 'UNIT_FIELD_SUMMONEDBY') == 6 and
        pet.get(INDEX['UNIT_CREATED_BY_SPELL']) in (13481, 883) and pet.get(INDEX['UNIT_FIELD_HEALTH'], 0) == 0 and
        pet.get(INDEX['UNIT_FIELD_MAXHEALTH'], 0) > 0, 'actual created dead Wolf16 identity differs')
    return pet


def wire_proof(cast, tracking):
    budget = cast['final_submission_corpse_budget']
    session, guid = cast['native_session'], budget['guid']
    recorded = cast['cast_packets']
    require(0 < len(recorded) <= 256 and len({packet_key(p) for p in recorded}) == len(recorded) and
        {packet_key(p) for p in recorded} == tracking['packets'],
        'actual archived Revive cast journal differs')
    wire = sorted(tracking['wire'], key=lambda p: p['time'])
    require(len({packet_key(p) for p in wire}) == len(wire), 'duplicate actual Revive packet')
    require(not any(p['name'] in FAILURES and p['time'] >= cast['cast_started_at'] for p in wire) and
        cast.get('failure_packets') == [], 'native/client Revive failure or cancellation differs')
    native = [p for p in recorded if (p['direction'], p['name']) == ('to_native', 'CMSG_CAST_SPELL')]
    modern = [p for p in recorded if (p['direction'], p['name']) == ('from_client', 'CMSG_CAST_SPELL')]
    require(len(native) == len(modern) == 1 and all(p['session'] == session for p in recorded),
        'single same-session ordinary Revive request differs')
    request = cast_identity(native[0]); modern_request = cast_identity(modern[0])
    require(request['spell'] == modern_request['spell'] == 982 and request['target_flags'] == 0 and
        0 <= native[0]['time'] - modern[0]['time'] < 2 and
        cast['native_cast_requests'] == [request] and same(cast['modern_cast_requests'], [modern_request]) and
        cast.get('ordinary_input') == {'kind': 'chat', 'value': '/cast Revive Pet'},
        'actual ordinary Revive982 payload differs')
    lower = budget['lifetime_source']; setup = lower['started_at']; creation = budget['creation_packet']
    previous_guid = lower['previous_guid']; prior_creation = lower['previous_creation_packet']; destruction = lower['destruction_packet']
    require(previous_guid != guid and previous_guid >> 52 == 0xf14 and
        prior_creation['time'] <= destruction['time'] <= setup and
        destruction['session'] == session and destruction['direction'] == 'from_native' and
        destruction['name'] == 'SMSG_DESTROY_OBJECT' and
        struct.unpack_from('<Q', bytes.fromhex(destruction['body']))[0] == previous_guid and
        {packet_key(prior_creation), packet_key(destruction)} <= {packet_key(p) for p in wire},
        'previous expired corpse and distinct fresh creation attribution differs')
    dead_creation(prior_creation, previous_guid, session)
    calls = [p for p in wire if (p['direction'], p['name']) == ('to_native', 'CMSG_CAST_SPELL') and
        p['time'] < creation['time']]
    require(lower['source'] == 'ordinary_call_pet_fixture_chat_setup_before_native_request' and
        len(calls) == 1 and calls[0] == lower['native_request'] and cast_identity(calls[0])['spell'] == 883 and
        setup <= calls[0]['time'] <= creation['time'] <= budget['observed_at'] <= cast['cast_started_at'] <= modern[0]['time'] and
        packet_key(creation) in {packet_key(p) for p in wire} and creation['name'] == 'SMSG_UPDATE_OBJECT' and
        creation['direction'] == 'from_native' and creation['session'] == session,
        'earlier ordinary Call Pet corpse lifetime source differs')
    elapsed = budget['observed_at'] - setup
    require(budget.get('native_present') is True and budget.get('submission_budget') is True and
        cast.get('final_submission_ready') is True and budget['conservative_corpse_seconds'] == CORPSE_SECONDS and
        budget['minimum_submission_remaining_seconds'] == MIN_SUBMISSION_REMAINING and
        budget['lifetime_started_at'] == setup and budget['created_at'] == creation['time'] and
        abs(budget['lifetime_age_seconds'] - elapsed) < 1e-6 and
        abs(budget['age_seconds'] - (budget['observed_at'] - creation['time'])) < 1e-6 and
        abs(budget['remaining_seconds'] - (CORPSE_SECONDS - elapsed)) < 1e-6 and
        budget['remaining_seconds'] >= MIN_SUBMISSION_REMAINING,
        'final native corpse submission budget differs')
    timing = native_revive_timing(recorded, request, setup)
    require(timing.get('native_ten_second_cast') is True and
        timing.get('completion_within_conservative_corpse_deadline') is True and
        timing.get('one_matching_start_and_completion') is True and timing.get('native_completion_ordered') is True and
        same(timing, cast['native_cast_timing']),
        'actual native Revive START10000/GO timing differs')
    completion = timing['completions'][0]
    require(cast['native_completions'] == [{k: completion[k] for k in ('caster', 'unit', 'counter', 'spell')}] and
        native[0]['time'] <= timing['starts'][0]['time'] < completion['time'] <= cast['cast_finished_at'],
        'actual Revive completion identity/order differs')
    pet = dead_creation(creation, guid, session); owner = {}; before = None; health_packet = None
    for packet in wire:
        if packet['time'] < creation['time']: continue
        if packet['time'] >= native[0]['time'] and before is None:
            before = deepcopy(pet)
            require(pair(owner, 'UNIT_FIELD_SUMMON') == guid, 'native owned corpse absent at request')
        if packet['name'] == 'SMSG_DESTROY_OBJECT':
            require(struct.unpack_from('<Q', bytes.fromhex(packet['body']))[0] != guid,
                'actual corpse destroyed during Revive')
        if packet['name'] != 'SMSG_UPDATE_OBJECT' or packet['direction'] != 'from_native': continue
        for row in records(bytes.fromhex(packet['body'])):
            require(guid not in row.get('removed', []), 'actual corpse removed during Revive')
            if row.get('guid') == 6: owner.update(fields(row))
            if row.get('guid') == guid:
                if row.get('update_type') in (1, 2) and packet_key(packet) != packet_key(creation):
                    raise RuntimeError('same corpse creation replayed during Revive')
                values = fields(row); pet.update(values)
                if values.get(INDEX['UNIT_FIELD_HEALTH'], 0) > 0 and health_packet is None:
                    require(packet['time'] >= completion['time'], 'pet was alive before native Revive completion')
                    health_packet = packet
    require(before is not None and same(before, cast['native_pet_before']['fields']) and
        health_packet is not None and pet.get(INDEX['UNIT_FIELD_HEALTH'], 0) > 0 and
        pair(owner, 'UNIT_FIELD_SUMMON') == guid and same(pet, cast['native_pet_after']['fields']) and
        cast['native_pet_before']['guid'] == cast['native_pet_after']['guid'] == guid,
        'actual native dead-to-alive owned pet update differs')
    public = cast['outcome_state']['target']
    require(public.get('exists') is True and public.get('guid') == expected_guid(cast['native_pet_after']) and
        public.get('name') == 'Wolf' and public.get('health', 0) > 0 and not cast['outcome_state'].get('errors') and
        cast['public_pet'].get('exists') is True and cast['public_pet'].get('guid') == public['guid'],
        'stock public living owned pet differs')
    require(len(tracking['instances']) == 1, 'fresh physical Revive instance attribution absent')
    important = [prior_creation, destruction, native[0], creation, health_packet]
    public_packets = [modern[0]]
    modern_identity = None
    for packet in recorded:
        if packet['direction'] == 'from_native' and packet['name'] in ('SMSG_SPELL_START', 'SMSG_SPELL_GO'):
            from .world.native_objects import guid as native_guid
            reader = Reader(bytes.fromhex(packet['body'])); native_guid(reader); native_guid(reader)
            _, spell = reader.unpack('Bi')
            if spell == 982: important.append(packet)
        elif packet['direction'] == 'to_client' and packet['name'] in ('SMSG_SPELL_START', 'SMSG_SPELL_GO'):
            reader = Reader(bytes.fromhex(packet['body']))
            caster, unit, identity, _ = [reader.guid() for _ in range(4)]
            spell, visual, _, _, duration = reader.unpack('iIIII')
            if spell != 982: continue
            require(caster == unit == (6, player_high()) and visual == modern_request['visual'] and
                (modern_identity is None or identity == modern_identity), 'modern Revive owner/identity differs')
            modern_identity = identity
            if packet['name'] == 'SMSG_SPELL_START':
                require(duration == 10000, 'modern Revive START duration differs')
            native_matches = [p for p in important if p['name'] == packet['name'] and
                0 <= packet['time'] - p['time'] < 2]
            require(len(native_matches) == 1, 'modern Revive outcome is not bound to its native delivery')
            owner = SimpleNamespace(character={'guid': 6, 'map': cast['native_pet_before']['map']},
                casts={request['counter']: {'spell': 982, 'visual': modern_request['visual'],
                    'guid': modern_request['guid'], 'server_guid': identity}})
            require(casting.response(owner, packet['name'], bytes.fromhex(native_matches[0]['body'])).hex() == packet['body'],
                'whole native-to-modern Revive lifecycle payload differs')
            public_packets.append(packet)
    require(len(public_packets) == 3 and {p['name'] for p in public_packets} ==
        {'CMSG_CAST_SPELL', 'SMSG_SPELL_START', 'SMSG_SPELL_GO'}, 'actual modern Revive START/GO absent')
    for packet in important:
        matches = [r for r in tracking['events'] if r.get('session') == session and
            (r.get('event'), r.get('name'), r.get('direction'), r.get('bytes')) ==
            ('native_packet', packet['name'], packet['direction'], len(bytes.fromhex(packet['body']))) and
            0 <= packet['time'] - r['time'] < .1]
        require(len(matches) == 1, 'actual native Revive metadata differs')
    physical = next(iter(tracking['instances']))
    for packet in public_packets:
        matches = [r for r in tracking['events'] if r.get('session') == physical and
            (r.get('event'), r.get('name'), r.get('direction'), r.get('bytes')) ==
            ('modern_packet', packet['name'], packet['direction'], len(bytes.fromhex(packet['body']))) and
            0 <= packet['time'] - r['time'] < .1]
        require(len(matches) == 1, 'actual physical modern Revive metadata differs')
    return {'native_requests': 1, 'modern_requests': 1, 'native_cast_time_ms': 10000,
        'actual_cast_seconds': timing['actual_cast_seconds'], 'native_dead_to_alive': True,
        'raw_health_update': health_packet, 'native_pet_guid': guid, 'physical_instances': 1}


def proof(data, digests, tracking):
    rows = {k: data[v] for k, v in NAMES.items()}; cast = rows['cast']; closure = rows['close']
    directory = Path(cast['fixture_source']['path']).parent.parent
    require(directory.parent == lab.ROOT / 'evidence', 'owned Revive archive directory differs')
    def ref(key): return {'path': str(directory / key), 'sha256': digests[key]}
    def linked(value):
        path = Path(value['path'])
        if path.is_relative_to(directory):
            key = str(path.relative_to(directory)); require(value == ref(key), 'Revive source digest differs')
            return data[key]
        require(path.is_relative_to(lab.ROOT / 'evidence'), 'foreign external Revive source')
        matches = [data[k] for k, sha in digests.items() if sha == value.get('sha256') and k.endswith('.json')]
        require(matches and all(same(v, matches[0]) for v in matches), 'external carried Revive source digest absent')
        return matches[0]
    fixture, old, entry, recon, park, finish, normalize = [rows[k] for k in
        ('fixture', 'preparation', 'entry', 'recon', 'park', 'finish', 'normalize')]
    for key, count in (('fixture', 7), ('preparation', 8), ('entry', 9), ('park', 4), ('finish', 5), ('close', 21)):
        whole(rows[key], 'checks', count)
    whole(cast, 'capture_checks', 18); whole(cast, 'restoration_checks', 17)
    require(recon.get('completed') is True and recon.get('failure') is None and
        normalize.get('completed') is True and normalize.get('failure') is None,
        'whole Revive recon/normalization differs')
    phases = {'fixture': 'owned_revive_dead_fixture_staged', 'preparation': 'await_owned_class_lobby_review',
        'entry': 'owned_class_entered', 'recon': 'await_owned_revive_cast_review', 'cast': 'owned_revive_cast_complete',
        'park': 'await_original_selection_review', 'normalize': 'owned_revive_fixture_normalized',
        'close': 'owned_revive_parked_boundary'}
    for key, phase in phases.items(): require(rows[key].get('phase') == phase, 'Revive source phase differs: ' + key)
    runtime, hunter, origin = cast['runtime'], old['class_actor'], old['origin_actor']
    require(tuple(hunter.get(k) for k in ('guid', 'account_id', 'class', 'level', 'character_name')) ==
        (6, 2, 3, 10, 'Harnesshunt') and origin.get('guid') == 2, 'owned Revive actors differ')
    for key in ('preparation', 'entry', 'recon', 'cast', 'park', 'finish', 'normalize', 'close'):
        row = rows[key]
        require(row.get('runtime') == runtime and row.get('model') is None and row.get('controller') in
            ('code', 'code_diagnostic_ordinary_inputs') and row.get('actor') == (origin if key in ('preparation', 'finish', 'close') else hunter),
            'same owned Revive runtime/controller/actor differs: ' + key)
        if key != 'normalize': require(row.get('custom_script_permission') == 'blocked_by_user', 'Revive script boundary differs')
    require(fixture['actor'] == hunter and fixture['model'] is None and fixture['controller'] == 'code' and
        fixture['runtime'] == {k: runtime[k] for k in ('worldserver', 'modern_world')}, 'offline Revive fixture runtime differs')
    order = ('fixture', 'preparation', 'entry', 'recon', 'cast', 'park', 'finish', 'close')
    previous = 0
    for key in order:
        row = rows[key]; require(previous < row['started_at'] < row['finished_at'], 'Revive source chronology differs')
        previous = row['finished_at']
    require(park['finished_at'] < normalize['started_at'] < normalize['finished_at'] < closure['started_at'],
        'offline Revive normalization chronology differs')
    require(old['fixture_source'] == ref(NAMES['fixture']) and all(rows[k].get('fixture_source') == ref(NAMES['preparation'])
        for k in ('entry', 'recon', 'cast', 'park', 'finish')) and
        recon['entry_source'] == cast['entry_source'] == ref(NAMES['entry']) and
        recon['dead_fixture_source'] == cast['dead_fixture_source'] == ref(NAMES['fixture']) and
        cast['recon_source'] == ref(NAMES['recon']) and cast['native_session'] == recon['native_session'] == entry['native_session'] and
        closure['sources'] == [ref(NAMES[k]) for k in ('preparation', 'fixture', 'cast', 'park', 'finish', 'normalize')] and
        normalize['sources'] == [ref(NAMES[k]) for k in ('fixture', 'cast', 'park')], 'complete Revive source chain differs')
    review = linked(cast['screen_review'])
    require(review.get('reviewed') is True and review.get('control') == 'Revive Pet' and
        review.get('source') == ref(NAMES['recon']) and review.get('frame') == recon['frame'] and
        review.get('fixture_source_sha256') == digests[NAMES['preparation']], 'exact reviewed Revive caption/frame differs')
    require(cast.get('input_sent') is True and cast.get('cast_input_sent') is True and cast.get('qualification_added') is False and
        closure.get('input_sent') is False and closure.get('qualification_added') is False and
        normalize.get('input_sent') is False and normalize.get('qualification_added') is False,
        'ordinary Revive/closure/normalization admission boundary differs')
    require(fixture.get('input_sent') is False and fixture.get('spell_grant_sent') is False and
        fixture.get('qualification_added') is False and fixture['after'] == fixture['expected_after'] == dead_snapshot(fixture['before']) and
        fixture['fixture_mutation'] == {'table': 'character_pet', 'owner': 6, 'id': 16, 'column': 'curhealth', 'before': 278, 'after': 0},
        'exact disposable offline dead fixture differs')
    prior_pause, prerequisite, prior_preparation = [linked(v) for v in fixture['sources']]
    whole(prior_pause, 'checks', 8)
    require(prior_pause['phase'] == 'parked_scout_resource_paused' and prior_pause['before'] == prior_pause['after'] == fixture['before'] and
        prerequisite.get('completed') is True and prerequisite.get('failure') is None and prerequisite.get('known_native_and_public') is True and
        prerequisite.get('input_sent') is False and prerequisite.get('spell_grant_sent') is False and
        prior_preparation.get('completed') is True and prior_preparation.get('failure') is None and
        prior_preparation.get('class_actor') == hunter, 'closed fixture prerequisite ancestry differs')
    require(prerequisite['sources'][2] == fixture['sources'][0] and
        prerequisite['runtime'] == fixture['runtime'] and prerequisite.get('automatic_skill_level_eligible') is True and
        prerequisite['public_revive'].get('id') == 982 and prerequisite['public_revive'].get('known') is True and
        prerequisite['public_revive'].get('name') == 'Revive Pet', 'exact native/public Revive prerequisite differs')
    known = prerequisite['native_known_spell_packet']; reader = Reader(bytes.fromhex(known['body']))
    initial, count = reader.unpack('BH'); require(initial == 1 and 0 < count <= 16000, 'native known-spell header differs')
    ids = [reader.unpack('Ih')[0] for _ in range(count)]
    cooldowns, = reader.unpack('H')
    for _ in range(cooldowns): reader.unpack('IIHii')
    reader.end()
    require(known.get('direction') == 'from_native' and known.get('name') == 'SMSG_SEND_KNOWN_SPELLS' and
        ids == known['ids'] and 982 in ids, 'actual native-known Revive prerequisite body differs')
    remote = linked(prerequisite['remote_source'])
    require(remote.get('actual_remote_verified') is True and remote.get('complete_json_png_verified') is True and
        prerequisite['source_checkpoint'] == {'pointer': remote['pointer'], 'sha256': remote['archive_sha256'], 'bytes': remote['bytes']},
        'actual previous remote prerequisite archive differs')
    stop = linked(closure['primary_stop_source']); whole(stop, 'checks', 8)
    require(stop['phase'] == 'user_requested_primary_client_stopped' and stop['before'] == stop['after'] == fixture['before']['1'] and
        closure['primary_stop_source'] == fixture['primary_stop_source'], 'primary stopped/preserved source differs')
    resume, restored = [linked(v) for v in old['sources']]
    whole(resume, 'checks', 7); whole(restored, 'checks', 3)
    require(resume['schema'] == 'client442_paused_scout_fixture_resume_v1' and
        resume['fixture_source'] == ref(NAMES['fixture']) and resume['preparation_source'] == fixture['sources'][2] and
        resume['primary_stop_source'] == closure['primary_stop_source'] and resume['runtime'] == restored['runtime'] == runtime and
        resume['offline_baselines'] == fixture['after'] and resume['restoration_source'] == old['sources'][1] and
        restored['phase'] == 'paused_scout_fixture_parked_restored' and restored['actor'] == origin and
        resume['origin_actor'] == origin and resume['class_actor'] == hunter and
        resume['previous_runtime'] == prior_pause['runtime'] and
        resume['runtime']['client'] != resume['previous_runtime']['client'] and
        fixture['finished_at'] < resume['started_at'] < resume['launch_finished_at'] < restored['started_at'] <
            restored['finished_at'] <= resume['finished_at'] < old['started_at'],
        'fresh one-scout resume/restoration ancestry differs')
    before, after = fixture['before'], closure['all_offline_snapshot']
    require(set(after) == {str(n) for n in range(1, 7)} and all(v['native']['online'] == 0 for v in after.values()) and
        old['natural_native'] == entry['native_before_entry'] == fixture['after']['6']['native'] and
        entry['entered_native'] == {**entry['native_before_entry'], 'online': 1} and
        old['natural_saved'] == fixture['after']['6']['saved'] and
        old['retained_class_pets'] == fixture['after']['6']['pets'] and
        all(after[g] == before[g] == old['protected_baseline'][g] for g in ('1', '2', '3', '4', '5')) and
        old['natural_saved'] == entry['entered_saved'] == cast['baseline_saved'] == park['retained_class_saved'] == after['6']['saved'] == before['6']['saved'] and
        after['6']['inventory'] == before['6']['inventory'] and after['6']['native'] == park['retained_class_fixture'] and
        normalize['before']['6']['pets'] == park['retained_class_pets'] and normalize['after'] == normalize['expected_after'] == after and
        restored_pets(before['6']['pets'], after['6']['pets']), 'complete parked Revive actor/pet preservation differs')
    expected = deepcopy(normalize['before']); expected['6']['pets'][1]['curhealth'] = 278; expected['6']['pets'][1]['CreatedBySpell'] = 13481
    require(expected == after and after['6']['pets'][0] == before['6']['pets'][0] and
        cast['retained_pet_after'][0] == before['6']['pets'][0] and park['retained_class_pets'][0] == before['6']['pets'][0] and
        cast['retained_pet_after'][1]['curhealth'] == park['retained_class_pets'][1]['curhealth'] == cast['native_pet_max_health'] and
        before['6']['pets'][1]['savetime'] <= cast['retained_pet_after'][1]['savetime'] <=
            park['retained_class_pets'][1]['savetime'] <= closure['finished_at'] and
        cast['baseline_resources'] == entry['resources'], 'named pet/resources or offline normalization delta differs')
    allowed = {'totaltime', 'leveltime', 'logout_time', 'latency'}
    if before['6']['native'].get('rest_bonus') != after['6']['native'].get('rest_bonus'):
        from .hunter_rest_accrual import accrual, PRECISION_QUERY
        rest = closure['native_rest_accrual_preserved']
        precision_key = 'hunter_rest_precision01/episode.json'; failed_key = 'hunter_revive_close01/episode.json'
        require(rest.get('precision_source') == ref(precision_key) and rest.get('entry_source') == ref(NAMES['entry']),
            'exact archived rest precision source differs')
        precision = linked(rest['precision_source']); failed = linked(ref(failed_key)); whole(precision, 'checks', 5)
        row = precision['row']
        require(precision.get('schema') == 'client442_owned_hunter_readonly_rest_precision_v1' and
            precision.get('phase') == 'owned_hunter_readonly_rest_precision_complete' and
            precision.get('query') == PRECISION_QUERY and set(precision['checks']) ==
                {'all_six_offline', 'all_saved_state_unchanged', 'hunter_identity', 'snapshot_rest_matches', 'exact_float32'} and
            all(v is True for v in precision['checks'].values()) and
            all(precision.get(k) is False for k in ('input_sent', 'mutation_sent', 'qualification_added')) and
            precision['sources'] == [ref(NAMES[k]) for k in ('entry', 'park', 'normalize')] + [ref(failed_key)] and
            precision['before'] == precision['after'] == after and
            all(row.get(k) == after['6']['native'].get(k) for k in
                ('guid', 'account', 'name', 'class', 'level', 'xp', 'online', 'rest_bonus', 'logout_time', 'is_logout_resting')) and
            failed.get('completed') is False and failed.get('failure') ==
                'RuntimeError: Hunter rest bonus differs from exact source-bound native offline accrual' and
            failed.get('phase') is None and failed.get('cases') == [] and failed.get('model') is None and
            failed.get('runtime') == runtime and failed.get('actor') == origin and failed.get('fixture_source') == ref(NAMES['preparation']) and
            normalize['finished_at'] < failed['started_at'] < failed['finished_at'] < precision['started_at'] <
                precision['finished_at'] < closure['started_at'], 'whole readonly rest precision and failed-close ancestry differs')
        require(rest.get('native_float_storage_sources') == [{'path': str(lab.REPO / path), 'sha256': sha}
            for path, sha in FLOAT_STORAGE_SOURCES.items()], 'exact native FLOAT storage source hashes differ')
        require(same(accrual(before['6']['native'], after['6']['native'], entry, 1, precise_after=row),
            {k: v for k, v in rest.items() if k not in
                ('entry_source', 'config_source', 'native_formula_source', 'precision_source', 'native_float_storage_sources')}),
            'exact native rest accrual differs')
        allowed.add('rest_bonus')
    require({k for k, v in before['6']['native'].items() if after['6']['native'].get(k) != v} <= allowed,
        'Hunter native columns changed beyond ordinary offline accounting')
    pause = data[PAUSE]; whole(pause, 'checks', 8)
    require(pause['phase'] == 'parked_scout_resource_paused' and pause['runtime'] == runtime and pause['actor'] == origin and
        pause['source'] == ref(NAMES['close']) and pause['primary_stop_source'] == closure['primary_stop_source'] and
        pause['before'] == pause['after'] == after and closure['finished_at'] < pause['started_at'] < pause['finished_at'],
        'both owned clients stopped with exact six-actor closure differs')
    displays = set()
    for key, row in [*[(NAMES[k], rows[k]) for k in ('preparation', 'entry', 'recon', 'cast', 'park', 'finish', 'close')], (PAUSE, pause)]:
        required = ('outcome_frame', 'restored_frame') if key == NAMES['cast'] else ('frame',)
        require(all(row.get(k) for k in required), 'required owned Revive frame absent')
        for frame_key in ('frame', 'outcome_frame', 'restored_frame'):
            frame = row.get(frame_key)
            if not frame: continue
            file = str(Path(key).parent / frame['file']); monitor = frame['monitor']; isolation = monitor['input_isolation']
            require(digests.get(file) == frame['sha256'] and monitor['second_monitor_verified'] is True and
                monitor['monitor']['name'] == 'HDMI-1' and monitor['pid'] == runtime['client']['pid'] and
                isolation['actor'] == 'scout' and isolation['host_activation_sent'] is False and isolation['display'].startswith(':'),
                'owned Revive frame/HDMI/private input differs')
            displays.add(isolation['display'])
    require(len(displays) == 1, 'Revive private display continuity differs')
    native = wire_proof(cast, tracking)
    return {'operation': 'pets.revive', 'owner': 6, 'pet_number': 16, **native,
        'capture_checks': 18, 'restoration_checks': 17, 'closure_checks': 21, 'shutdown_checks': 8,
        'named_pet_preserved': 4, 'all_six_offline': True, 'both_owned_clients_stopped': True,
        'qualification_added': False, 'scope': 'One ordinary Revive982 on offline-prepared disposable Wolf16, '
            'actual native dead-to-alive health update, public living pet, ordinary logout and full offline restoration. '
            'Natural combat death, expired/dismissed corpses and other pet/class variants remain open.'}

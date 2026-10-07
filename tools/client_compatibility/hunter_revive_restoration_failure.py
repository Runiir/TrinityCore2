"""Recognize only the recorded198-to278 native-max restoration failure."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import struct
from . import lab_runtime as lab
from .hunter_revive_lifecycle import native_revive_timing, CORPSE_SECONDS, MIN_SUBMISSION_REMAINING
from .interaction_hunter_stable_slots import bound
from .interaction_owned_class_fixture import SCRIPT_BOUNDARY
from .interaction_pet_command_probe import expected_guid
from .interaction_pet_summon import cast_identity
from .interaction_retained_class_fixture import closed
from .observation.journal import entries
from .world.native_objects import records
from .world.native_objects import guid as native_guid
from .world.buffer import Reader
from .world.objects import INDEX


FAILURE = 'RuntimeError: Revive fixture restoration differs'
VARIANT = 'post_revive_max_health_restoration_failure'
CAPTURE_KEYS = {'one_modern_cast', 'one_native_cast', 'matching_native_completion', 'no_failure_packets',
    'native_cast_timing', 'same_owned_pet', 'native_dead_to_alive', 'public_owned_living_pet',
    'owner_health_unchanged', 'resources', 'saved_rows', 'no_public_errors', 'ui_clean'} | {
    f'actor_{g}_unchanged' for g in ('1', '2', '3', '4', '5')}
RESTORATION_KEYS = {'original_character', 'original_saved_rows', 'native_worldserver', 'stored_named_pet',
    'living_disposable_pet', 'owner_vitals', 'owner_resources', 'saved_rows', 'owner_position',
    'empty_selection', 'ui_clean', 'public_owned_pet'} | {f'actor_{g}_unchanged' for g in ('1', '2', '3', '4', '5')}
CAST_NAMES = {'CMSG_CAST_SPELL', 'SMSG_SPELL_START', 'SMSG_SPELL_GO',
    'SMSG_CAST_FAILED', 'SMSG_SPELL_FAILURE', 'SMSG_SPELL_FAILED_OTHER'}


def fields(pet): return {int(k): v for k, v in pet.get('fields', {}).items()}
def same(a, b): return json.loads(json.dumps(a)) == json.loads(json.dumps(b))
def packet_key(p): return tuple(p.get(k) for k in ('time', 'session', 'name', 'direction', 'body'))
def pair(f, name): return f.get(INDEX[name], 0) | f.get(INDEX[name] + 1, 0) << 32


def shape(cast):
    """Strict receipt pattern; this result never admits the failed gameplay cast."""
    from .hunter_revive_failed_fixture import times
    if (cast.get('schema') != 'client442_laya_interactions_v1' or cast.get('completed') is not False or
        cast.get('failure') != FAILURE or cast.get('phase') is not None or
        cast.get('controller') != 'code_diagnostic_ordinary_inputs' or cast.get('model') is not None or
        cast.get('revision') is not None or cast.get('fine_tuned') is not False or len(cast.get('cases', [])) != 1 or
        cast.get('input_sent') is not True or cast.get('cast_input_sent') is not True or
        cast.get('qualification_added') is not False or cast.get('offline_fixture_normalization_pending') is not True or
        cast.get('ordinary_input') != {'kind': 'chat', 'value': '/cast Revive Pet'} or
        cast.get('custom_script_permission') != 'blocked_by_user' or cast.get('softTargetInteract') != SCRIPT_BOUNDARY or
        not times(cast, ('started_at', 'cast_started_at', 'cast_finished_at', 'finished_at')) or
        set(cast.get('capture_checks', {})) != CAPTURE_KEYS or
        not all(v is True for v in cast['capture_checks'].values()) or
        set(cast.get('restoration_checks', {})) != RESTORATION_KEYS or
        any(v is not (k != 'living_disposable_pet') for k, v in cast['restoration_checks'].items()) or
        cast.get('failure_packets') != [] or not cast.get('native_session')):
        raise RuntimeError('requires the exact post-Revive max-health restoration failure')
    case = cast['cases'][0]
    if (case.get('id') != 'fixture.pet_dismiss.book_revive_public_pet' or case.get('status') != 'spellbook_open_pass' or
        not cast['cast_finished_at'] <= case.get('time', 0) <= cast['finished_at']):
        raise RuntimeError('post-Revive failure includes a different case or gameplay qualification')
    if tuple(cast.get('actor', {}).get(k) for k in ('actor', 'guid', 'account_id', 'character_name', 'race', 'class', 'level')) != (
        'scout', 6, 2, 'Harnesshunt', 1, 3, 10):
        raise RuntimeError('post-Revive failed actor differs')
    before, after, restored = [cast.get(k, {}) for k in ('native_pet_before', 'native_pet_after', 'restored_native_pet')]
    for pet in (before, after, restored):
        f = fields(pet)
        if (not pet.get('guid') or pet['guid'] >> 52 != 0xf14 or f.get(INDEX['UNIT_FIELD_PETNUMBER']) != 16 or
            f.get(INDEX['OBJECT_FIELD_ENTRY']) != 299 or pair(f, 'UNIT_FIELD_SUMMONEDBY') != 6 or
            f.get(INDEX['UNIT_CREATED_BY_SPELL']) != 883):
            raise RuntimeError('post-Revive failed native pet identity differs')
    b, a, r = fields(before), fields(after), fields(restored)
    if (before['guid'] != after['guid'] or before['guid'] != restored['guid'] or
        b.get(INDEX['UNIT_FIELD_HEALTH'], 0) != 0 or b.get(INDEX['UNIT_FIELD_MAXHEALTH']) != 198 or
        not 0 < a.get(INDEX['UNIT_FIELD_HEALTH'], 0) <= 198 or a.get(INDEX['UNIT_FIELD_MAXHEALTH']) != 198 or
        r.get(INDEX['UNIT_FIELD_HEALTH']) != 278 or r.get(INDEX['UNIT_FIELD_MAXHEALTH']) != 278 or
        cast.get('native_pet_max_health') != 198 or cast.get('native_vitals_before') != {
            'UNIT_FIELD_HEALTH': 209, 'UNIT_FIELD_MAXHEALTH': 209, 'UNIT_FIELD_POWER1': 100, 'UNIT_FIELD_MAXPOWER1': 100}):
        raise RuntimeError('post-Revive failed198-to278 native max transition differs')
    target = cast.get('outcome_state', {}).get('target', {})
    public = cast.get('public_pet', {})
    state = cast.get('restored_state', {})
    if (target.get('exists') is not True or target.get('guid') != expected_guid(after) or
        target.get('name') != 'Wolf' or target.get('health', 0) <= 0 or
        public.get('exists') is not True or public.get('guid') != expected_guid(restored) or public.get('name') != 'Wolf' or
        public.get('power') != public.get('max_power') or public.get('power') != 100 or
        state.get('target', {}).get('exists') is not False or state.get('player_stats', {}).get('health') != 209 or
        state.get('player') != 'Harnesshunt' or state.get('errors') or state.get('lua_errors') or state.get('blocked_actions')):
        raise RuntimeError('post-Revive failed public living pet or restored owner differs')
    return cast


def journal(cast):
    ref = cast.get('entry_source', {})
    path = Path(ref.get('path', ''))
    if path.is_symlink() or bound(path) != ref: raise RuntimeError('post-Revive failed entry hash differs')
    entry = closed(path)
    if entry.get('native_session') != cast['native_session'] or entry.get('runtime') != cast.get('runtime'):
        raise RuntimeError('post-Revive failed journal entry differs')
    guid = cast['native_pet_before']['guid']
    budget = cast['final_submission_corpse_budget']
    lower = budget['lifetime_source']
    prior_keys = {packet_key(lower[k]) for k in ('native_request', 'previous_creation_packet', 'destruction_packet')}
    kept = []
    for p in entries(lab.ROOT / 'evidence/world_packets.jsonl'):
        if p.get('session') != cast['native_session'] or not entry['started_at'] <= p.get('time', 0) <= cast['finished_at']: continue
        relevant = packet_key(p) in prior_keys or p.get('name') in CAST_NAMES and cast['cast_started_at'] <= p['time'] <= cast['finished_at']
        if p.get('name') == 'CMSG_CANCEL_CAST' and p['time'] >= cast['cast_started_at']: relevant = True
        if p.get('direction') == 'from_native':
            if p.get('name') == 'SMSG_DESTROY_OBJECT':
                relevant |= struct.unpack_from('<Q', bytes.fromhex(p['body']))[0] in (6, guid)
            elif p.get('name') == 'SMSG_UPDATE_OBJECT':
                relevant |= any(r.get('guid') in (6, guid) or {6, guid} & set(r.get('removed', [])) for r in records(bytes.fromhex(p['body'])))
        if relevant: kept.append(p)
        if len(kept) > 512: raise RuntimeError('post-Revive failed native journal exceeds bound')
    return kept


def proof(cast, packets):
    shape(cast)
    guid, session = cast['native_pet_before']['guid'], cast['native_session']
    if not packets or len(packets) > 512 or len({packet_key(p) for p in packets}) != len(packets):
        raise RuntimeError('post-Revive failed journal is absent or duplicated')
    recorded = cast['cast_packets']
    if (not recorded or len(recorded) > 256 or len({packet_key(p) for p in recorded}) != len(recorded) or
        any(p.get('session') != session or not cast['cast_started_at'] <= p.get('time', 0) <= cast['cast_finished_at'] for p in recorded)):
        raise RuntimeError('post-Revive failed recorded same-session cast window differs')
    actual = [p for p in packets if p.get('name') in CAST_NAMES and cast['cast_started_at'] <= p['time'] <= cast['cast_finished_at']]
    if {packet_key(p) for p in actual} != {packet_key(p) for p in recorded}:
        raise RuntimeError('post-Revive failed actual cast journal differs')
    later = [p for p in packets if p['time'] > cast['cast_finished_at'] and p.get('name') in CAST_NAMES and
        (p['name'] == 'CMSG_CAST_SPELL' or p['name'] in CAST_NAMES - {'CMSG_CAST_SPELL', 'SMSG_SPELL_START', 'SMSG_SPELL_GO'})]
    if later:
        raise RuntimeError('post-Revive failed restoration window includes another cast request or failure')
    for packet in packets:
        if packet['time'] <= cast['cast_finished_at'] or packet.get('direction') != 'from_native' or packet.get('name') not in ('SMSG_SPELL_START', 'SMSG_SPELL_GO'): continue
        reader = Reader(bytes.fromhex(packet['body']))
        caster, unit = native_guid(reader), native_guid(reader)
        _, spell = reader.unpack('Bi')
        if caster == unit == 6 and spell == 982:
            raise RuntimeError('post-Revive failed restoration window includes another native982 execution')
    if any(p.get('name') in CAST_NAMES - {'CMSG_CAST_SPELL', 'SMSG_SPELL_START', 'SMSG_SPELL_GO'} for p in recorded):
        raise RuntimeError('post-Revive failed cast includes a failure packet')
    parsed = [(p, cast_identity(p)) for p in recorded]
    modern = [r for p, r in parsed if r and (p['name'], p['direction']) == ('CMSG_CAST_SPELL', 'from_client')]
    native = [r for p, r in parsed if r and (p['name'], p['direction']) == ('CMSG_CAST_SPELL', 'to_native')]
    go = [r for p, r in parsed if r and (p['name'], p['direction']) == ('SMSG_SPELL_GO', 'from_native') and r['spell'] == 982]
    if (len(modern) != 1 or len(native) != 1 or len(go) != 1 or modern[0]['spell'] != 982 or
        native[0]['spell'] != 982 or native[0]['counter'] != go[0]['counter'] or go[0]['caster'] != 6 or go[0]['unit'] != 6 or
        not same([modern, native, go], [cast['modern_cast_requests'], cast['native_cast_requests'], cast['native_completions']])):
        raise RuntimeError('post-Revive failed one native982 request/completion differs')
    budget = cast['final_submission_corpse_budget']
    lower = budget['lifetime_source']
    setup, created, observed = lower['started_at'], budget['creation_packet']['time'], budget['observed_at']
    prior = lower['previous_creation_packet']
    destruction = lower['destruction_packet']
    call = lower['native_request']
    raw_keys = {packet_key(p) for p in packets}
    if (lower.get('source') != 'ordinary_call_pet_fixture_chat_setup_before_native_request' or
        lower.get('previous_guid') == guid or lower.get('previous_guid', 0) >> 52 != 0xf14 or
        budget.get('guid') != guid or budget.get('native_present') is not True or budget.get('submission_budget') is not True or
        cast.get('final_submission_ready') is not True or budget.get('lifetime_started_at') != setup or
        cast.get('call_dead_pet_started_at') != setup or cast.get('call_dead_pet_native_requests') != [call] or
        budget.get('conservative_corpse_seconds') != CORPSE_SECONDS or
        budget.get('minimum_submission_remaining_seconds') != MIN_SUBMISSION_REMAINING or
        not prior['time'] <= destruction['time'] <= setup <= call['time'] <= created <= observed <= cast['cast_started_at'] or
        call.get('name') != 'CMSG_CAST_SPELL' or call.get('direction') != 'to_native' or cast_identity(call)['spell'] != 883 or
        destruction.get('name') != 'SMSG_DESTROY_OBJECT' or destruction.get('direction') != 'from_native' or
        struct.unpack_from('<Q', bytes.fromhex(destruction['body']))[0] != lower['previous_guid'] or
        any(p.get('session') != session for p in (prior, destruction, call)) or
        not {packet_key(p) for p in (prior, destruction, call, budget['creation_packet'])} <= raw_keys or
        abs(budget['lifetime_age_seconds'] - (observed - setup)) > 1e-6 or
        abs(budget['remaining_seconds'] - (CORPSE_SECONDS - (observed - setup))) > 1e-6 or
        budget['remaining_seconds'] < MIN_SUBMISSION_REMAINING):
        raise RuntimeError('post-Revive failure exact earlier883/creation/corpse budget differs')
    previous = [r for r in records(bytes.fromhex(prior['body'])) if r.get('guid') == lower['previous_guid'] and r.get('update_type') in (1, 2)]
    if (prior.get('name') != 'SMSG_UPDATE_OBJECT' or prior.get('direction') != 'from_native' or len(previous) != 1 or
        previous[0].get('kind') != 3 or fields(previous[0]).get(INDEX['UNIT_FIELD_PETNUMBER']) != 16 or
        fields(previous[0]).get(INDEX['UNIT_FIELD_HEALTH'], 0) != 0 or pair(fields(previous[0]), 'UNIT_FIELD_SUMMONEDBY') != 6):
        raise RuntimeError('post-Revive failure previous actual dead Wolf16 differs')
    timing = native_revive_timing(recorded, native[0], budget['lifetime_started_at'])
    if (not same(timing, cast.get('native_cast_timing')) or any(timing.get(k) is not True for k in
        ('one_matching_start_and_completion', 'native_completion_ordered', 'native_ten_second_cast', 'completion_within_conservative_corpse_deadline'))):
        raise RuntimeError('post-Revive failed exact native cast timing differs')
    completion = timing['completions'][0]['time']
    request_time = next(p['time'] for p in recorded if (p['name'], p['direction']) == ('CMSG_CAST_SPELL', 'to_native'))
    owner, pet = {}, None
    before, captured = None, None
    alive_packet, max_packet = None, None
    for packet in sorted(packets, key=lambda p: p['time']):
        if packet.get('session') != session or packet['time'] > cast['finished_at']:
            raise RuntimeError('post-Revive failed same-session journal window differs')
        if pet is not None and before is None and packet['time'] >= request_time:
            before = deepcopy(pet)
            if pair(owner, 'UNIT_FIELD_SUMMON') != guid: raise RuntimeError('actual dead pet ownership differs at Revive')
        if pet is not None and captured is None and packet['time'] > cast['cast_finished_at']: captured = deepcopy(pet)
        if packet['name'] == 'CMSG_CANCEL_CAST' and packet['time'] >= cast['cast_started_at']:
            raise RuntimeError('post-Revive failed cast was cancelled')
        if packet['name'] == 'SMSG_DESTROY_OBJECT' and struct.unpack_from('<Q', bytes.fromhex(packet['body']))[0] in (6, guid):
            raise RuntimeError('post-Revive failed owner or same pet was destroyed')
        if packet['name'] != 'SMSG_UPDATE_OBJECT' or packet['direction'] != 'from_native': continue
        for row in records(bytes.fromhex(packet['body'])):
            if {6, guid} & set(row.get('removed', [])): raise RuntimeError('post-Revive failed owner or same pet was removed')
            if row.get('guid') == 6: owner.update(fields(row))
            if row.get('guid') != guid: continue
            if row.get('update_type') in (1, 2):
                if pet is not None or packet_key(packet) != packet_key(budget['creation_packet']):
                    raise RuntimeError('post-Revive failed native creation differs')
                pet = fields(row)
            elif pet is None: raise RuntimeError('post-Revive failed update precedes creation')
            else: pet.update(fields(row))
            if pet.get(INDEX['UNIT_FIELD_HEALTH'], 0) > 0 and alive_packet is None:
                if packet['time'] < completion: raise RuntimeError('post-Revive failed pet was alive before completion')
                alive_packet = packet
            if pet.get(INDEX['UNIT_FIELD_MAXHEALTH']) == 278 and max_packet is None:
                if alive_packet is None: raise RuntimeError('post-Revive failed max changed before living outcome')
                max_packet = packet
    if captured is None: captured = deepcopy(pet)
    if (not same(before, cast['native_pet_before']['fields']) or not same(captured, cast['native_pet_after']['fields']) or
        not same(pet, cast['restored_native_pet']['fields']) or alive_packet is None or max_packet is None or
        pair(owner, 'UNIT_FIELD_SUMMON') != guid or {k: owner.get(INDEX[k]) for k in cast['native_vitals_before']} != cast['native_vitals_before']):
        raise RuntimeError('actual post-Revive failed dead/living/max/full-owner native proof differs')
    return {'schema': 'client442_post_revive_restoration_failure_proof_v1', 'variant': VARIANT,
        'guid': guid, 'native_pet_number': 16, 'pre_cast_max': 198, 'restored_max': 278,
        'alive_packet': alive_packet, 'max_transition_packet': max_packet,
        'raw_packets_sha256': hashlib.sha256(json.dumps(packets, sort_keys=True).encode()).hexdigest(),
        'raw_packets': packets, 'qualification_added': False, 'failed_cast_excluded': True}


def from_journal(cast): return proof(cast, journal(cast))

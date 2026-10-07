"""Reject forged admission and the actual expired corpse before qualification."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import struct
import sys
import pytest
from tools.client_compatibility import lab_runtime as lab
from tools.client_compatibility.hunter_revive_timing import native_revive_timing
from tools.client_compatibility.pet_packet_identity import cast_identity, expected_guid
from tools.client_compatibility.review_native_feedback_checkpoint import packet_key
from tools.client_compatibility.world.native_objects import records
from tools.client_compatibility.world.native_objects import guid as native_guid
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.objects import INDEX


# Candidate tests can run outside the checkout while a prior batch is sealed.
try:
    from tools.client_compatibility import hunter_revive_evidence as evidence
except ImportError:
    name = 'tools.client_compatibility.hunter_revive_evidence'
    spec = importlib.util.spec_from_file_location(name, Path(__file__).with_name('hunter_revive_evidence.py'))
    evidence = importlib.util.module_from_spec(spec); sys.modules[name] = evidence; spec.loader.exec_module(evidence)

TRACE = json.loads((lab.REPO / 'tools/client_compatibility/world/tests/fixtures/hunter_revive_expiry_ui167.json').read_text())
RELOAD = json.loads((lab.REPO / 'tools/client_compatibility/world/tests/fixtures/hunter_revive_reload_creator_ui168.json').read_text())


def packed_guid(guid):
    octets = [(guid >> (i * 8)) & 255 for i in range(8)]
    return bytes([sum(1 << i for i, value in enumerate(octets) if value)]) + bytes(value for value in octets if value)


def creation_for(packets, guid):
    return next(p for p in packets if p['name'] == 'SMSG_UPDATE_OBJECT' and p['direction'] == 'from_native' and any(
        r.get('guid') == guid and r.get('update_type') in (1, 2) for r in records(bytes.fromhex(p['body']))))


def destruction_for(packets, guid):
    return next(p for p in packets if p['name'] == 'SMSG_DESTROY_OBJECT' and p['direction'] == 'from_native' and
        struct.unpack_from('<Q', bytes.fromhex(p['body']))[0] == guid)


def revive_packet(name):
    for packet in TRACE['packets']:
        if packet['name'] != name or packet['direction'] != 'from_native': continue
        reader = Reader(bytes.fromhex(packet['body'])); native_guid(reader); native_guid(reader)
        if reader.unpack('Bi')[1] == 982: return packet
    raise AssertionError('trace lacks native Revive' + name)


def fixture(trace=TRACE, elapsed=10.0006):
    """Construct a synthetic Revive outcome after actual dead-creation packets."""
    guid = trace['pet_guid']; source_creation = creation_for(trace['packets'], guid)
    source_call = trace['call_fixture_native_requests'][0]
    packets = deepcopy([p for p in trace['packets'] if source_call['time'] <= p['time'] <= source_creation['time'] + .01])
    call = next(p for p in packets if p == source_call); creation = creation_for(packets, guid)
    setup = trace['call_fixture_chat_setup_started_at']; request_at = setup + 20
    previous_guid = trace.get('previous_pet_guid', trace.get('previous_guid'))
    previous = deepcopy(creation_for(trace['prior_packets'], previous_guid) if 'prior_packets' in trace else trace['previous_creation_packet'])
    destruction = deepcopy(destruction_for(trace['prior_packets'], previous_guid) if 'prior_packets' in trace else trace['destruction_packet'])
    packets[:0] = [previous, destruction]
    modern = {'session': trace['session'], 'time': request_at, 'direction': 'from_client', 'name': 'CMSG_CAST_SPELL',
        'body': '01830482f5bc0000000000000000d6030000069d030000000000000000000000000000000000000000000000000000000000000000000000'}
    native = {**modern, 'time': request_at + .0001, 'direction': 'to_native', 'body': '04d6030000000000000000000000'}
    start = {**revive_packet('SMSG_SPELL_START'), 'session': trace['session'], 'time': request_at + .01}
    go = {**revive_packet('SMSG_SPELL_GO'), 'session': trace['session'], 'time': start['time'] + elapsed}
    modern_start = {**start, 'direction': 'to_client', 'time': start['time'] + .0001,
        'body': '01a006040801a006040801a30483f504bc0000d6030000069d0300020804000000000010270000000000000000000000000000000000000000000000000000000000000000008000000000000000000000000164000000'}
    modern_go = {**go, 'direction': 'to_client', 'time': go['time'] + .0001,
        'body': '01a006040801a006040801a30483f504bc0000d6030000069d0300000904000000000013294000000000000000000000000000000000000000000000000000000100000000008000000000042400000000000000f8e513c65ed23f42894c634201a0060408014100000000'}
    body = struct.pack('<HIB', 0, 1, 0) + packed_guid(guid) + struct.pack('<BII', 1, 1 << INDEX['UNIT_FIELD_HEALTH'], 29)
    health = {**creation, 'time': go['time'] + .01, 'body': body.hex()}
    recorded = [modern, native, start, modern_start, go, modern_go]
    packets.extend([*recorded, health])
    pet = next(r for r in records(bytes.fromhex(creation['body'])) if r.get('guid') == guid)
    for packet in packets:
        if packet['time'] < creation['time'] or packet['time'] >= request_at or packet['name'] != 'SMSG_UPDATE_OBJECT': continue
        for row in records(bytes.fromhex(packet['body'])):
            if row.get('guid') == guid: pet['fields'].update(row.get('fields', {}))
    living = deepcopy(pet); living['fields'][INDEX['UNIT_FIELD_HEALTH']] = 29
    observed = setup + 17
    budget = {'guid': guid, 'pet_number': 16, 'created_at': creation['time'], 'observed_at': observed,
        'age_seconds': observed - creation['time'], 'conservative_corpse_seconds': 59,
        'remaining_seconds': 59 - (observed - setup), 'lifetime_started_at': setup,
        'lifetime_age_seconds': observed - setup, 'lifetime_source': {'started_at': setup,
            'source': 'ordinary_call_pet_fixture_chat_setup_before_native_request', 'native_request': call,
            'previous_guid': previous_guid, 'previous_creation_packet': previous, 'destruction_packet': destruction},
        'native_present': True, 'submission_budget': True, 'minimum_submission_remaining_seconds': 15,
        'creation_packet': creation}
    request = cast_identity(native)
    cast = {'native_session': trace['session'], 'final_submission_corpse_budget': budget, 'final_submission_ready': True,
        'cast_started_at': observed + .01, 'cast_finished_at': health['time'] + .1, 'cast_packets': recorded,
        'native_cast_requests': [request], 'modern_cast_requests': [cast_identity(modern)],
        'native_completions': [{k: 6 if k in ('caster', 'unit') else 4 if k == 'counter' else 982
            for k in ('caster', 'unit', 'counter', 'spell')}],
        'native_cast_timing': native_revive_timing(recorded, request, setup), 'failure_packets': [],
        'ordinary_input': {'kind': 'chat', 'value': '/cast Revive Pet'}, 'native_pet_before': pet, 'native_pet_after': living,
        'outcome_state': {'target': {'exists': True, 'guid': expected_guid(living), 'name': 'Wolf', 'health': 29}},
        'public_pet': {'exists': True, 'guid': expected_guid(living)}}
    tracking = evidence.tracking_state(); tracking['instances'].add('physical')
    tracking['packets'] = {packet_key(p) for p in recorded}; tracking['wire'] = packets
    tracking['events'] = [{'session': p['session'], 'event': 'native_packet', 'name': p['name'],
        'direction': p['direction'], 'bytes': len(bytes.fromhex(p['body'])), 'time': p['time'] - .00002}
        for p in [previous, destruction, native, creation, health, start, go]]
    tracking['events'].extend({'session': 'physical', 'event': 'modern_packet', 'name': p['name'],
        'direction': p['direction'], 'bytes': len(bytes.fromhex(p['body'])), 'time': p['time'] - .00002}
        for p in (modern, modern_start, modern_go))
    return cast, tracking


def test_native_raw_health_update_is_required_for_one_revive():
    cast, tracking = fixture()
    result = evidence.wire_proof(cast, tracking)
    assert result['native_dead_to_alive'] and result['native_requests'] == 1
    assert result['actual_cast_seconds'] == pytest.approx(10.0006)
    assert result['raw_health_update']['body'] == tracking['wire'][-1]['body']


def test_actual_ui168_receiver_elapsed_is_diagnostic_for_advertised_ten_second_cast():
    # Actual cast01 receipts advertise START10000ms at1791398577.6703427,
    # then GO at1791398587.6608095. Receiver elapsed is not a native clock.
    actual_elapsed = 1791398587.6608095 - 1791398577.6703427
    assert actual_elapsed == pytest.approx(9.990466833)
    cast, tracking = fixture(elapsed=actual_elapsed)
    result = evidence.wire_proof(cast, tracking)
    assert result['native_cast_time_ms'] == 10000 and result['native_dead_to_alive']
    assert result['actual_cast_seconds'] == pytest.approx(actual_elapsed)


@pytest.mark.parametrize('fault', ['reversed_order','wrong_duration','deadline'])
def test_receiver_elapsed_never_relaxes_native_order_duration_or_corpse_deadline(fault):
    elapsed = -.01 if fault == 'reversed_order' else 39 if fault == 'deadline' else 9.990466833
    cast, tracking = fixture(elapsed=elapsed)
    if fault == 'wrong_duration':
        start = next(p for p in cast['cast_packets'] if p['name'] == 'SMSG_SPELL_START' and p['direction'] == 'from_native')
        body = bytearray.fromhex(start['body']); old = packet_key(start)
        struct.pack_into('<I', body, 17, 9999); start['body'] = body.hex()
        tracking['packets'].remove(old); tracking['packets'].add(packet_key(start))
        cast['native_cast_timing'] = native_revive_timing(cast['cast_packets'], cast['native_cast_requests'][0],
            cast['final_submission_corpse_budget']['lifetime_source']['started_at'])
    with pytest.raises(RuntimeError, match='START10000/GO timing'):
        evidence.wire_proof(cast, tracking)


def test_actual_ui168_retained_tame_creator_passes_only_with_fresh_callpet_ancestry():
    cast, tracking = fixture(RELOAD)
    creation = cast['final_submission_corpse_budget']['creation_packet']
    born = next(r for r in records(bytes.fromhex(creation['body'])) if r.get('guid') == RELOAD['pet_guid'])
    assert born['fields'][INDEX['UNIT_CREATED_BY_SPELL']] == 13481
    assert cast['native_pet_before']['fields'][INDEX['UNIT_CREATED_BY_SPELL']] == 883
    assert evidence.wire_proof(cast, tracking)['native_dead_to_alive']
    assert creation == creation_for(RELOAD['packets'], RELOAD['pet_guid'])


@pytest.mark.parametrize('fault', ['wrong_creator','same_guid','missing_prior_creation','missing_prior_destruction',
    'wrong_destroyed_guid','late_destruction','prior_metadata'])
def test_retained_creator_never_substitutes_for_actual_prior_expiry_and_fresh_creation(fault):
    cast, tracking = fixture(RELOAD); lower = cast['final_submission_corpse_budget']['lifetime_source']
    if fault == 'wrong_creator':
        creation = cast['final_submission_corpse_budget']['creation_packet']
        assert creation['body'].count('a9340000') == 1
        creation['body'] = creation['body'].replace('a9340000', 'aa340000')
    elif fault == 'same_guid': lower['previous_guid'] = RELOAD['pet_guid']
    elif fault in ('missing_prior_creation','missing_prior_destruction'):
        key = packet_key(lower['previous_creation_packet' if fault == 'missing_prior_creation' else 'destruction_packet'])
        tracking['wire'] = [p for p in tracking['wire'] if packet_key(p) != key]
    elif fault == 'wrong_destroyed_guid': lower['destruction_packet']['body'] = struct.pack('<QB', RELOAD['pet_guid'], 0).hex()
    elif fault == 'late_destruction': lower['destruction_packet']['time'] = lower['started_at'] + .1
    elif fault == 'prior_metadata': tracking['events'].pop(0)
    with pytest.raises(RuntimeError): evidence.wire_proof(cast, tracking)


@pytest.mark.parametrize('fault', ['missing_packet', 'body', 'duplicate', 'second_request', 'failure', 'cancel',
    'late_setup', 'missing_call', 'unsupported_clock', 'short_budget', 'wrong_duration', 'forged_timing',
    'no_health', 'alive_before_go', 'destroy', 'wrong_pet', 'public_dead', 'missing_instance', 'metadata',
    'missing_modern_metadata', 'foreign_modern_instance', 'early_go', 'json_guid_tuple', 'modern_truncated', 'modern_suffix'])
def test_unsupported_or_substituted_live_outcome_cannot_be_admitted(fault):
    cast, tracking = fixture(); budget = cast['final_submission_corpse_budget']
    if fault == 'missing_packet': tracking['packets'].pop()
    elif fault == 'body': cast['cast_packets'][0]['body'] += '00'
    elif fault == 'duplicate': tracking['wire'].append(deepcopy(tracking['wire'][-1]))
    elif fault == 'second_request':
        p = {**cast['cast_packets'][1], 'time': cast['cast_packets'][1]['time'] + .1}
        cast['cast_packets'].append(p); tracking['packets'].add(packet_key(p)); tracking['wire'].append(p)
    elif fault in ('failure', 'cancel'):
        tracking['wire'].append({**cast['cast_packets'][1], 'name': 'SMSG_CAST_FAILED' if fault == 'failure' else 'CMSG_CANCEL_CAST'})
    elif fault == 'late_setup': budget['lifetime_source']['started_at'] = budget['creation_packet']['time'] + 1
    elif fault == 'missing_call': tracking['wire'].pop(2)
    elif fault == 'unsupported_clock': budget['lifetime_source']['source'] = 'pet_name_timestamp'
    elif fault == 'short_budget': budget['remaining_seconds'] = 14
    elif fault == 'wrong_duration':
        p = cast['cast_packets'][2]; body = bytearray.fromhex(p['body']); struct.pack_into('<I', body, 17, 5000)
        old = packet_key(p); p['body'] = body.hex(); tracking['packets'].remove(old); tracking['packets'].add(packet_key(p))
    elif fault == 'forged_timing': cast['native_cast_timing']['actual_cast_seconds'] = 1
    elif fault == 'no_health': tracking['wire'].pop()
    elif fault == 'alive_before_go': tracking['wire'][-1]['time'] = cast['cast_packets'][2]['time'] + 1
    elif fault == 'destroy':
        tracking['wire'].append({**destruction_for(TRACE['packets'], TRACE['pet_guid']), 'time': cast['cast_packets'][2]['time'] + 1})
    elif fault == 'wrong_pet': cast['native_pet_after']['guid'] += 1
    elif fault == 'public_dead': cast['outcome_state']['target']['health'] = 0
    elif fault == 'missing_instance': tracking['instances'].clear()
    elif fault == 'metadata': tracking['events'][-1]['bytes'] += 1
    elif fault == 'missing_modern_metadata': tracking['events'] = tracking['events'][:5]
    elif fault == 'foreign_modern_instance': tracking['events'][-1]['session'] = 'foreign'
    elif fault == 'early_go':
        cast['cast_packets'][4]['time'] = cast['cast_packets'][2]['time'] + .1
        cast['native_cast_timing'] = native_revive_timing(cast['cast_packets'], cast['native_cast_requests'][0],
            budget['lifetime_source']['started_at'])
        tracking['packets'] = {packet_key(p) for p in cast['cast_packets']}
    elif fault == 'json_guid_tuple':
        cast['modern_cast_requests'] = json.loads(json.dumps(cast['modern_cast_requests']))
        assert evidence.wire_proof(cast, tracking)['native_dead_to_alive']
        return
    elif fault in ('modern_truncated', 'modern_suffix'):
        p = cast['cast_packets'][3]; old = packet_key(p)
        p['body'] = p['body'][:80] if fault == 'modern_truncated' else p['body'][:-2] + 'ff'
        tracking['packets'].remove(old); tracking['packets'].add(packet_key(p))
    with pytest.raises((RuntimeError, ValueError, KeyError)): evidence.wire_proof(cast, tracking)


def test_actual_ui167_expiry_cannot_pass_even_with_successful_go_and_claimed_checks():
    cast, tracking = fixture()
    # The real corpse destruction occurs before its recorded Revive completion.
    cast['cast_packets'][2]['time'] = revive_packet('SMSG_SPELL_START')['time']
    cast['cast_packets'][4]['time'] = revive_packet('SMSG_SPELL_GO')['time']
    cast['native_cast_timing'] = native_revive_timing(cast['cast_packets'], cast['native_cast_requests'][0],
        cast['final_submission_corpse_budget']['lifetime_source']['started_at'])
    tracking['packets'] = {packet_key(p) for p in cast['cast_packets']}
    tracking['wire'].insert(-1, destruction_for(TRACE['packets'], TRACE['pet_guid']))
    with pytest.raises(RuntimeError, match='START10000/GO timing'): evidence.wire_proof(cast, tracking)


def test_collect_ignores_ambient_movement_and_binds_exact_global_cast_window():
    cast, tracking = fixture()
    data = {evidence.NAMES['cast']: cast, evidence.NAMES['entry']: {'started_at': 1, 'finished_at': 2}}
    actual = evidence.tracking_state()
    ambient = [{**tracking['wire'][0], 'name': 'SMSG_ON_MONSTER_MOVE', 'time': cast['cast_started_at'] + i / 1000}
        for i in range(2000)]
    evidence.collect('tracking/packets.jsonl', [*ambient, *tracking['wire']], data, actual)
    assert actual['packets'] == tracking['packets']
    assert actual['wire'] == tracking['wire']


def test_collect_cannot_replace_a_recorded_packet_with_another_session():
    cast, tracking = fixture(); data = {evidence.NAMES['cast']: cast, evidence.NAMES['entry']: {'started_at': 1, 'finished_at': 2}}
    actual = evidence.tracking_state(); rows = deepcopy(tracking['wire']); index = rows.index(cast['cast_packets'][0])
    rows[index]['session'] = 'foreign'
    evidence.collect('tracking/packets.jsonl', rows, data, actual)
    assert packet_key(tracking['wire'][index]) not in actual['packets']


def test_collect_rejects_unbounded_relevant_packets():
    cast, tracking = fixture(); data = {evidence.NAMES['cast']: cast, evidence.NAMES['entry']: {'started_at': 1, 'finished_at': 2}}
    actual = evidence.tracking_state()
    with pytest.raises(RuntimeError, match='bound'):
        evidence.collect('tracking/packets.jsonl', [tracking['wire'][0]] * 513, data, actual)


def complete_fixture(trace=TRACE):
    """Synthetic archived chain; actual native packet formats come from UI167."""
    cast, tracking = fixture(trace); data = {}; digests = {}; directory = lab.ROOT / 'evidence/test_revive_batch'
    hunter = dict(guid=6, account_id=2, actor='scout', **{'class': 3}, level=10, character_name='Harnesshunt')
    origin = dict(guid=2, account_id=2, actor='scout', **{'class': 1}, level=1, character_name='Harnesstwo')
    runtime = {'worldserver': {'pid': 100, 'start_ticks': '1'}, 'modern_world': {'pid': 101, 'start_ticks': '2'},
        'client': {'pid': 102, 'start_ticks': '3'}}
    previous_runtime = {**runtime, 'client': {'pid': 103, 'start_ticks': '4'}}
    epoch = cast['final_submission_corpse_budget']['lifetime_started_at']
    def checks(count): return {str(i): True for i in range(count)}
    def put(key, row):
        data[key] = row; digests[key] = f'{len(digests)+1:064x}'
        return {'path': str(directory / key), 'sha256': digests[key]}
    def episode(phase, started, finished, actor=hunter, count=None):
        row = {'phase': phase, 'started_at': started, 'finished_at': finished, 'actor': deepcopy(actor),
            'runtime': deepcopy(runtime), 'completed': True, 'failure': None, 'model': None,
            'controller': 'code_diagnostic_ordinary_inputs', 'custom_script_permission': 'blocked_by_user'}
        if count is not None: row['checks'] = checks(count)
        return row
    before = {str(g): {'native': {'online': 0, 'guid': g}, 'saved': {}, 'inventory': [], 'pets': []} for g in range(1, 7)}
    before['6']['native'].update(account=2, name='Harnesshunt', race=1, **{'class': 3}, level=10, health=209,
        money=8708, xp=45, rest_bonus=0, totaltime=10, leveltime=10, logout_time=1, latency=0)
    before['6']['pets'] = [dict(id=4, owner=6, entry=42717, name='Harnesswolf', renamed=1, slot=5, active=0,
        curhealth=278, CreatedBySpell=883, savetime=epoch-1000, PetType=1, level=10),
        dict(id=16, owner=6, entry=299, name='Wolf', renamed=0, slot=0, active=1, curhealth=278,
            CreatedBySpell=13481, savetime=epoch-100, PetType=1, level=10)]
    staged = deepcopy(before); staged['6']['pets'][1]['curhealth'] = 0
    prior_pause = episode('parked_scout_resource_paused', epoch-220, epoch-219, origin, 8)
    prior_pause.update(runtime=previous_runtime, before=before, after=before)
    pause_ref = put('carried_previous_pause01.json', prior_pause)
    prior_prep_ref = put('carried_previous_preparation01.json',
        {'completed': True, 'failure': None, 'class_actor': hunter})
    stop = episode('user_requested_primary_client_stopped', epoch-300, epoch-299, {'guid': 1}, 8)
    stop.update(before=before['1'], after=before['1'])
    primary_ref = put('carried_primary_stop01.json', stop)
    remote = {'actual_remote_verified': True, 'complete_json_png_verified': True, 'pointer': 'previous.tar.gz.dvc',
        'archive_sha256': 'a'*64, 'bytes': 123}
    remote_ref = put('carried_previous_remote_integrity01.json', remote)
    known_body = struct.pack('<BHIhH', 1, 1, 982, 0, 0).hex()
    prerequisite = {'completed': True, 'failure': None, 'known_native_and_public': True, 'input_sent': False,
        'spell_grant_sent': False, 'automatic_skill_level_eligible': True,
        'runtime': {k: runtime[k] for k in ('worldserver', 'modern_world')}, 'sources': [{}, {}, pause_ref],
        'public_revive': {'id': 982, 'known': True, 'name': 'Revive Pet'},
        'native_known_spell_packet': {'direction': 'from_native', 'name': 'SMSG_SEND_KNOWN_SPELLS', 'body': known_body, 'ids': [982]},
        'remote_source': remote_ref, 'source_checkpoint': {'pointer': remote['pointer'], 'sha256': remote['archive_sha256'], 'bytes': 123}}
    prerequisite_ref = put('hunter_revive_prerequisite01/episode.json', prerequisite)
    stage = episode('owned_revive_dead_fixture_staged', epoch-200, epoch-199, hunter, 7)
    stage.update(runtime=prerequisite['runtime'], controller='code', before=before, after=staged, expected_after=staged,
        sources=[pause_ref, prerequisite_ref, prior_prep_ref], primary_stop_source=primary_ref,
        input_sent=False, qualification_added=False, spell_grant_sent=False,
        fixture_mutation={'table': 'character_pet', 'owner': 6, 'id': 16, 'column': 'curhealth', 'before': 278, 'after': 0})
    stage_ref = put(evidence.NAMES['fixture'], stage)
    resume = episode(None, epoch-190, epoch-181, origin, 7)
    resume.update(schema='client442_paused_scout_fixture_resume_v1', fixture_source=stage_ref,
        preparation_source=prior_prep_ref, primary_stop_source=primary_ref, previous_runtime=previous_runtime,
        offline_baselines=staged, origin_actor=origin, class_actor=hunter, launch_finished_at=epoch-189)
    resume_ref = put('scout_resume01/resume.json', resume)
    restored = episode('paused_scout_fixture_parked_restored', epoch-188, epoch-182, origin, 3)
    restored_ref = put('scout_resume_original_finish01/episode.json', restored); resume['restoration_source'] = restored_ref
    old = episode('await_owned_class_lobby_review', epoch-180, epoch-179, origin, 8)
    old.update(origin_actor=origin, class_actor=hunter, natural_native=staged['6']['native'], natural_saved={},
        retained_class_pets=staged['6']['pets'], protected_baseline={g: before[g] for g in ('1','2','3','4','5')},
        fixture_source=stage_ref, sources=[resume_ref, restored_ref])
    prep_ref = put(evidence.NAMES['preparation'], old)
    entry = episode('owned_class_entered', epoch-170, epoch-169, hunter, 9)
    entry.update(fixture_source=prep_ref, native_session=cast['native_session'], native_before_entry=deepcopy(staged['6']['native']),
        entered_native={**staged['6']['native'], 'online': 1}, entered_saved={}, resources={})
    entry_ref = put(evidence.NAMES['entry'], entry)
    recon = episode('await_owned_revive_cast_review', epoch-100, epoch-99)
    recon.update(fixture_source=prep_ref, entry_source=entry_ref, dead_fixture_source=stage_ref, native_session=cast['native_session'])
    recon_ref = put(evidence.NAMES['recon'], recon)
    cast.update(episode('owned_revive_cast_complete', epoch-90, cast['cast_finished_at']+110))
    cast.update(fixture_source=prep_ref, entry_source=entry_ref, dead_fixture_source=stage_ref, recon_source=recon_ref,
        capture_checks=checks(18), restoration_checks=checks(17), input_sent=True, cast_input_sent=True,
        qualification_added=False, baseline_saved={}, baseline_resources={}, native_pet_max_health=198)
    retained = deepcopy(before['6']['pets']); retained[1].update(curhealth=198, CreatedBySpell=883, savetime=cast['finished_at'])
    cast['retained_pet_after'] = retained
    cast_ref = put(evidence.NAMES['cast'], cast)
    park = episode('await_original_selection_review', cast['finished_at']+1, cast['finished_at']+3, hunter, 4)
    native = {**before['6']['native'], 'logout_time': cast['finished_at']+2}
    parked_pets = deepcopy(retained); parked_pets[1]['savetime'] = cast['finished_at']+2
    park.update(fixture_source=prep_ref, retained_class_saved={}, retained_class_pets=parked_pets, retained_class_fixture=native)
    park_ref = put(evidence.NAMES['park'], park)
    finish = episode('fixture_original_restored', cast['finished_at']+4, cast['finished_at']+6, origin, 5)
    finish['fixture_source'] = prep_ref; finish_ref = put(evidence.NAMES['finish'], finish)
    norm_before = deepcopy(before); norm_before['6']['native'] = native; norm_before['6']['pets'] = parked_pets
    final = deepcopy(norm_before); final['6']['pets'][1].update(curhealth=278, CreatedBySpell=13481)
    norm = episode('owned_revive_fixture_normalized', cast['finished_at']+7, cast['finished_at']+8)
    norm.update(controller='code', input_sent=False, qualification_added=False, before=norm_before, expected_after=final,
        after=final, sources=[stage_ref, cast_ref, park_ref])
    norm_ref = put(evidence.NAMES['normalize'], norm)
    close = episode('owned_revive_parked_boundary', cast['finished_at']+9, cast['finished_at']+10, origin, 21)
    close.update(sources=[prep_ref, stage_ref, cast_ref, park_ref, finish_ref, norm_ref], all_offline_snapshot=final,
        primary_stop_source=primary_ref, input_sent=False, qualification_added=False)
    close_ref = put(evidence.NAMES['close'], close)
    pause = episode('parked_scout_resource_paused', cast['finished_at']+11, cast['finished_at']+12, origin, 8)
    pause.update(source=close_ref, primary_stop_source=primary_ref, before=final, after=final)
    put(evidence.PAUSE, pause)
    for key in (*[evidence.NAMES[k] for k in ('preparation','entry','recon','cast','park','finish','close')], evidence.PAUSE):
        row = data[key]
        for name in (('outcome_frame','restored_frame') if key == evidence.NAMES['cast'] else ('frame',)):
            image_key = str(Path(key).parent / (name+'.png')); digests[image_key] = f'{len(digests)+1:064x}'
            row[name] = {'file': name+'.png', 'sha256': digests[image_key], 'monitor': {'pid': runtime['client']['pid'],
                'second_monitor_verified': True, 'monitor': {'name': 'HDMI-1'},
                'input_isolation': {'actor': 'scout', 'host_activation_sent': False, 'display': ':3'}}}
    review = {'reviewed': True, 'control': 'Revive Pet', 'source': recon_ref, 'frame': recon['frame'],
        'fixture_source_sha256': prep_ref['sha256']}
    cast['screen_review'] = {**put(str(Path(evidence.NAMES['recon']).with_name('review.json')), review),
        'frame': deepcopy(recon['frame'])}
    return data, digests, tracking


def test_complete_synthetic_archived_source_chain_passes_without_ledger_admission():
    data, digests, tracking = complete_fixture()
    proof = evidence.proof(data, digests, tracking)
    assert proof['operation'] == 'pets.revive' and not proof['qualification_added']
    assert proof['closure_checks'] == 21 and proof['both_owned_clients_stopped']


def test_actual_augmented_screen_review_shape_binds_its_exact_source_and_frame():
    data, digests, tracking = complete_fixture()
    screen = data[evidence.NAMES['cast']]['screen_review']
    assert set(screen) == {'path','sha256','frame'}
    assert screen['frame'] == data[evidence.NAMES['recon']]['frame']
    assert evidence.proof(data, digests, tracking)['operation'] == 'pets.revive'


@pytest.mark.parametrize('fault', ['frame','digest','unknown_key','missing_frame'])
def test_augmented_screen_review_rejects_substitution_or_unknown_metadata(fault):
    data, digests, tracking = complete_fixture()
    screen = data[evidence.NAMES['cast']]['screen_review']
    if fault == 'frame': screen['frame']['monitor']['pid'] += 1
    elif fault == 'digest': digests[str(Path(evidence.NAMES['recon']).parent / screen['frame']['file'])] = '0'*64
    elif fault == 'unknown_key': screen['unexpected'] = 'unreviewed'
    elif fault == 'missing_frame': screen.pop('frame')
    with pytest.raises(RuntimeError, match='screen review reference|reviewed Revive caption/frame'):
        evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('failed_suffix', ['recon01','recon02'])
def test_failed_recons_stay_archived_and_cannot_substitute_the_third_recon(failed_suffix):
    data, digests, tracking = complete_fixture()
    failed_key = 'hunter_revive_' + failed_suffix + '/episode.json'
    failed = deepcopy(data[evidence.NAMES['recon']])
    failed.update(completed=False, failure='dead-pet target expired during caption', input_sent=False)
    data[failed_key] = failed; digests[failed_key] = 'f'*64
    # Retaining the excluded earlier receipt must not reject the later complete
    # evidence, and the cast remains bound to its exact accepted third recon.
    assert evidence.proof(data, digests, tracking)['operation'] == 'pets.revive'
    directory = Path(data[evidence.NAMES['cast']]['fixture_source']['path']).parent.parent
    data[evidence.NAMES['cast']]['recon_source'] = {'path': str(directory / failed_key), 'sha256': digests[failed_key]}
    with pytest.raises(RuntimeError, match='complete Revive source chain'):
        evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('substitution', ['pause_source','canonical_close'])
def test_failed_close01_stays_archived_and_cannot_substitute_successful_close02(substitution):
    data, digests, tracking = complete_fixture()
    failed_key = 'hunter_revive_close01/episode.json'
    failed = deepcopy(data[evidence.NAMES['close']])
    failed.update(completed=False, failure='Hunter rest bonus differs from exact source-bound native offline accrual')
    data[failed_key] = failed; digests[failed_key] = 'f'*64
    assert evidence.NAMES['close'] == 'hunter_revive_close02/episode.json'
    assert evidence.proof(data, digests, tracking)['operation'] == 'pets.revive'
    if substitution == 'pause_source':
        directory = Path(data[evidence.NAMES['cast']]['fixture_source']['path']).parent.parent
        data[evidence.PAUSE]['source'] = {'path': str(directory / failed_key), 'sha256': digests[failed_key]}
    else:
        data[evidence.NAMES['close']] = failed
    with pytest.raises(RuntimeError, match='both owned clients stopped|episode is not whole accepted'):
        evidence.proof(data, digests, tracking)


def precision_fixture():
    """Bind the actual UI169 exact FLOAT measurement into a synthetic full chain."""
    from tools.client_compatibility.hunter_rest_accrual import accrual, PRECISION_QUERY
    data, digests, tracking = complete_fixture()
    fixture = data[evidence.NAMES['fixture']]; entry = data[evidence.NAMES['entry']]
    close = data[evidence.NAMES['close']]; normalize = data[evidence.NAMES['normalize']]; park = data[evidence.NAMES['park']]
    directory = Path(data[evidence.NAMES['cast']]['fixture_source']['path']).parent.parent
    def ref(key): return {'path': str(directory / key), 'sha256': digests[key]}
    login = entry['started_at'] + .1; logout = int(login) - 1949
    for native in (fixture['before']['6']['native'], fixture['after']['6']['native'],
            entry['native_before_entry'], entry['entered_native']):
        native.update(rest_bonus=162.211, logout_time=logout, is_logout_resting=0)
    for native in (close['all_offline_snapshot']['6']['native'], normalize['before']['6']['native'], park['retained_class_fixture']):
        native.update(rest_bonus=168.588, is_logout_resting=0)
    entry['state'] = dict(xp_max=7600, xp=45, level=10, player='Harnesshunt', xp_exhaustion=336)
    entry['login_packets'] = [dict(time=login+i*.0001, session=entry['native_session'], name=name, direction=direction)
        for i, (name, direction) in enumerate((('CMSG_PLAYER_LOGIN','to_native'), ('SMSG_LOGIN_VERIFY_WORLD','from_native')))]
    failed_key = 'hunter_revive_close01/episode.json'; failed = deepcopy(close)
    failed.update(completed=False, failure='RuntimeError: Hunter rest bonus differs from exact source-bound native offline accrual',
        phase=None, cases=[],
        fixture_source=ref(evidence.NAMES['preparation']), started_at=normalize['finished_at']+.1, finished_at=normalize['finished_at']+.2)
    data[failed_key] = failed; digests[failed_key] = 'f'*64
    precision_key = 'hunter_rest_precision01/episode.json'
    native = close['all_offline_snapshot']['6']['native']
    row = {k: native[k] for k in ('guid','account','name','class','level','xp','online','rest_bonus','logout_time','is_logout_resting')}
    row.update(exact_rest_bonus=168.58815002441406, exact_rest_bonus_float32_bits='91962843')
    precision = dict(schema='client442_owned_hunter_readonly_rest_precision_v1',
        phase='owned_hunter_readonly_rest_precision_complete', completed=True, failure=None,
        query=PRECISION_QUERY,
        input_sent=False, mutation_sent=False, qualification_added=False,
        started_at=normalize['finished_at']+.3, finished_at=normalize['finished_at']+.4,
        before=deepcopy(close['all_offline_snapshot']), after=deepcopy(close['all_offline_snapshot']),
        sources=[ref(evidence.NAMES[k]) for k in ('entry','park','normalize')]+[ref(failed_key)], row=row,
        checks={k:True for k in ('all_six_offline','all_saved_state_unchanged','hunter_identity','snapshot_rest_matches','exact_float32')})
    data[precision_key] = precision; digests[precision_key] = 'e'*64
    close['native_rest_accrual_preserved'] = {**accrual(fixture['before']['6']['native'], native, entry, 1, precise_after=row),
        'entry_source': ref(evidence.NAMES['entry']), 'precision_source': ref(precision_key),
        'config_source': {}, 'native_formula_source': {},
        'native_float_storage_sources': [{'path': str(lab.REPO / path), 'sha256': sha}
            for path, sha in evidence.FLOAT_STORAGE_SOURCES.items()]}
    return data, digests, tracking


def test_exact_actual_rest_float_source_binds_successful_close02_without_admission():
    data, digests, tracking = precision_fixture()
    assert evidence.proof(data, digests, tracking)['qualification_added'] is False
    rest = data[evidence.NAMES['close']]['native_rest_accrual_preserved']
    assert rest['expected_native_float32'] == 168.58815002441406


def test_fresh_publishing_process_proves_synthetic_precision_chain_without_ui_or_protobuf():
    import subprocess
    script = '''
import importlib.abc
import sys
blocked = ('google.protobuf', 'PIL', 'tools.second_client',
    'tools.client_compatibility.auth', 'tools.client_compatibility.interaction_',
    'tools.client_compatibility.hunter_revive_lifecycle')
class NoUI(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(blocked):
            raise AssertionError('publishing proof imported UI/protobuf: ' + fullname)
sys.meta_path.insert(0, NoUI())
from tools.client_compatibility.hunter_revive_evidence import proof
from tools.client_compatibility.world.tests.test_hunter_revive_evidence import precision_fixture
data, digests, tracking = precision_fixture()
result = proof(data, digests, tracking)
assert result['operation'] == 'pets.revive' and result['qualification_added'] is False
assert not any(name.startswith(blocked) for name in sys.modules)
print('pure publishing proof passed')
'''
    result = subprocess.run([sys.executable, '-c', script], cwd=lab.REPO,
        capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stdout + result.stderr
    assert result.stdout.strip() == 'pure publishing proof passed'


@pytest.mark.parametrize('fault', ['source_digest','entry_source','source_role','failed_precision','mutation','changed_snapshot',
    'foreign_row','late_precision','wrong_bits','forged_inverse','failedclose_success','query','check_name',
    'failedclose_phase','failedclose_cases','failedclose_model','storage_role','storage_hash'])
def test_exact_rest_precision_cannot_be_foreign_mutating_lossy_or_substituted(fault):
    data, digests, tracking = precision_fixture()
    precision = data['hunter_rest_precision01/episode.json']; rest = data[evidence.NAMES['close']]['native_rest_accrual_preserved']
    if fault == 'source_digest': rest['precision_source']['sha256'] = '0'*64
    elif fault == 'entry_source': rest['entry_source']['sha256'] = '0'*64
    elif fault == 'source_role': precision['sources'][2]['sha256'] = '0'*64
    elif fault == 'failed_precision': precision['completed'] = False
    elif fault == 'mutation': precision['mutation_sent'] = True
    elif fault == 'changed_snapshot': precision['after']['6']['native']['money'] += 1
    elif fault == 'foreign_row': precision['row']['guid'] = 5
    elif fault == 'late_precision': precision['finished_at'] = data[evidence.NAMES['close']]['finished_at']+1
    elif fault == 'wrong_bits': precision['row']['exact_rest_bonus_float32_bits'] = '90962843'
    elif fault == 'forged_inverse': rest['expected_native_float32'] += .001
    elif fault == 'failedclose_success': data['hunter_revive_close01/episode.json']['completed'] = True
    elif fault == 'query': precision['query'] += ' AND 1=1'
    elif fault == 'check_name': precision['checks']['unrelated'] = precision['checks'].pop('exact_float32')
    elif fault == 'failedclose_phase': data['hunter_revive_close01/episode.json']['phase'] = 'owned_revive_parked_boundary'
    elif fault == 'failedclose_cases': data['hunter_revive_close01/episode.json']['cases'] = [{'input':'unexpected'}]
    elif fault == 'failedclose_model': data['hunter_revive_close01/episode.json']['model'] = 'unexpected'
    elif fault == 'storage_role': rest['native_float_storage_sources'][0]['path'] = str(lab.REPO / 'other.cpp')
    elif fault == 'storage_hash': rest['native_float_storage_sources'][0]['sha256'] = '0'*64
    with pytest.raises((RuntimeError, ValueError, KeyError)): evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('fault', ['fixture_digest','missing_frame','wrong_monitor','wrong_runtime','missing_resume',
    'foreign_resume','foreign_prerequisite','unknown_revive','unverified_previous_remote','live_actor','named_pet',
    'pet_creator','backward_savetime','future_savetime','changed_money','changed_rows','normalization_delta',
    'missing_pause','failed_cast','forged_public','mutated_capture'])
def test_complete_chain_rejects_missing_foreign_or_incomplete_admission(fault):
    data, digests, tracking = complete_fixture(); cast = data[evidence.NAMES['cast']]
    close = data[evidence.NAMES['close']]; old = data[evidence.NAMES['preparation']]
    if fault == 'fixture_digest': digests[evidence.NAMES['fixture']] = 'f'*64
    elif fault == 'missing_frame': cast.pop('outcome_frame')
    elif fault == 'wrong_monitor': cast['outcome_frame']['monitor']['monitor']['name'] = 'DP-1'
    elif fault == 'wrong_runtime': data[evidence.NAMES['entry']]['runtime']['client']['pid'] += 1
    elif fault == 'missing_resume': old['sources'] = []
    elif fault == 'foreign_resume': old['sources'][0]['sha256'] = 'f'*64
    elif fault == 'foreign_prerequisite': data['hunter_revive_prerequisite01/episode.json']['sources'][2] = {}
    elif fault == 'unknown_revive': data['hunter_revive_prerequisite01/episode.json']['native_known_spell_packet']['ids'] = []
    elif fault == 'unverified_previous_remote': data['carried_previous_remote_integrity01.json']['actual_remote_verified'] = False
    elif fault == 'live_actor': close['all_offline_snapshot']['4']['native']['online'] = 1
    elif fault == 'named_pet': close['all_offline_snapshot']['6']['pets'][0] = {**close['all_offline_snapshot']['6']['pets'][0], 'savetime': 1}
    elif fault == 'pet_creator': close['all_offline_snapshot']['6']['pets'][1]['CreatedBySpell'] = 883
    elif fault == 'backward_savetime': close['all_offline_snapshot']['6']['pets'][1]['savetime'] = 0
    elif fault == 'future_savetime': data[evidence.NAMES['park']]['retained_class_pets'][1]['savetime'] = close['finished_at']+1000
    elif fault == 'changed_money': close['all_offline_snapshot']['6']['native']['money'] += 1
    elif fault == 'changed_rows': close['all_offline_snapshot']['6']['saved'] = {'spells': [982]}
    elif fault == 'normalization_delta': data[evidence.NAMES['normalize']]['before']['6']['pets'][1]['name'] = 'Other'
    elif fault == 'missing_pause': data.pop(evidence.PAUSE)
    elif fault == 'failed_cast': cast['completed'] = False; cast['failure'] = 'one ordinary Revive failed'
    elif fault == 'forged_public': cast['public_pet']['guid'] = 'Pet-foreign'
    elif fault == 'mutated_capture': cast['native_pet_after']['fields'][INDEX['UNIT_FIELD_HEALTH']] = 198
    with pytest.raises((RuntimeError, ValueError, KeyError)): evidence.proof(data, digests, tracking)


@pytest.mark.parametrize('corruption', [None, 'compressed_digest', 'png_digest', 'missing_member'])
def test_remote_phase_admits_only_after_actual_complete_stream_integrity(tmp_path, monkeypatch, corruption):
    import hashlib
    import io
    import tarfile
    from types import SimpleNamespace
    monkeypatch.setattr(lab, 'ROOT', tmp_path / 'lab')
    monkeypatch.setattr(lab, 'REPO', tmp_path / 'repo')
    data, _, tracking = complete_fixture(); directory = lab.ROOT / 'evidence/test_revive_batch'
    png = b'fixture image bytes'; png_sha = hashlib.sha256(png).hexdigest()
    def visit(value, digests=None):
        if isinstance(value, list):
            for item in value: visit(item, digests)
        elif isinstance(value, dict):
            if 'file' in value and 'sha256' in value and 'monitor' in value: value['sha256'] = png_sha
            if 'path' in value and 'sha256' in value and digests:
                path = Path(value['path'])
                if path.is_relative_to(directory): value['sha256'] = digests[str(path.relative_to(directory))]
            if 'fixture_source_sha256' in value and digests:
                value['fixture_source_sha256'] = digests[evidence.NAMES['preparation']]
            for item in value.values(): visit(item, digests)
    # Hash-linked source graph is acyclic. Recompute until the written JSON refs
    # converge, then archive the exact bytes that the real reviewer will stream.
    data = json.loads(json.dumps(data)); visit(data)
    for _ in range(30):
        bodies = {key: (json.dumps(row, indent=2)+'\n').encode() for key, row in data.items()}
        hashes = {key: hashlib.sha256(body).hexdigest() for key, body in bodies.items()}
        previous = json.dumps(data, sort_keys=True); visit(data, hashes)
        if json.dumps(data, sort_keys=True) == previous: break
    else: pytest.fail('source hash graph did not converge')
    prefix = str(directory.relative_to(lab.ROOT)) + '/'; members = {prefix+k: body for k, body in bodies.items()}
    for key, row in data.items():
        for field in ('frame', 'outcome_frame', 'restored_frame'):
            if field in row: members[prefix+str(Path(key).parent / row[field]['file'])] = png
    metadata = deepcopy(tracking['events'])
    entry = data[evidence.NAMES['entry']]
    metadata.insert(0, {'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical', 'time': entry['started_at']+.5})
    journals = {'tracking/events.jsonl': metadata, 'tracking/packets.jsonl': tracking['wire']}
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as archive:
        for key, body in members.items():
            if corruption == 'missing_member' and key.endswith('outcome_frame.png'): continue
            if corruption == 'png_digest' and key.endswith('outcome_frame.png'): body += b'changed'
            info = tarfile.TarInfo(key); info.size = len(body); archive.addfile(info, io.BytesIO(body))
        for key, rows in journals.items():
            body = ''.join(json.dumps(p)+'\n' for p in rows).encode()
            info = tarfile.TarInfo(key); info.size = len(body); archive.addfile(info, io.BytesIO(body))
    compressed = stream.getvalue()
    cp = {'file': 'artifacts/client_harness/revive_fixture.tar.gz', 'bytes': len(compressed),
        'sha256': 'f'*64 if corruption == 'compressed_digest' else hashlib.sha256(compressed).hexdigest(),
        'file_manifest': [{'path': key, 'sha256': hashlib.sha256(body).hexdigest()} for key, body in members.items()]}
    directory.mkdir(parents=True); (directory/'checkpoint_receipt.json').write_text(json.dumps(cp))
    pointer = lab.REPO / (cp['file']+'.dvc'); pointer.parent.mkdir(parents=True)
    pointer.write_text(json.dumps({'outs': [{'size': len(compressed), 'md5': 'object'}]}))
    class Repo:
        def __init__(self, path):
            self.cloud = SimpleNamespace(get_remote_odb=lambda: SimpleNamespace(oid_to_path=lambda oid: oid,
                fs=SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(compressed))))
        def __enter__(self): return self
        def __exit__(self, *args): pass
    monkeypatch.setitem(sys.modules, 'dvc', SimpleNamespace())
    monkeypatch.setitem(sys.modules, 'dvc.repo', SimpleNamespace(Repo=Repo))
    monkeypatch.setitem(sys.modules, 'yaml', SimpleNamespace(safe_load=json.loads))
    module_path = Path(evidence.__file__).with_name('review_native_feedback_checkpoint.py')
    spec = importlib.util.spec_from_file_location('tools.client_compatibility._revive_remote_candidate', module_path)
    remote = importlib.util.module_from_spec(spec); spec.loader.exec_module(remote)
    output = lab.ROOT / 'evidence/remote_review.json'
    if corruption:
        with pytest.raises(RuntimeError, match='digest differs|archive or complete member set'):
            remote.review(directory, output, 'revive')
        assert not output.exists()
    else:
        remote.review(directory, output, 'revive')
        result = json.loads(output.read_text())
        assert result['actual_remote_verified'] and result['complete_json_png_verified']
        assert result['proof']['operation'] == 'pets.revive' and not result['proof']['qualification_added']

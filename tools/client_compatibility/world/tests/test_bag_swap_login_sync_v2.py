"""V2 preserves historical proofs while binding full physical request context."""
from copy import deepcopy
import hashlib
import json
import struct

import pytest

from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_login_sync as historical
from tools.client_compatibility import bag_swap_login_sync_v2 as sync
from tools.client_compatibility.world.tests import test_bag_swap_login_sync as retained

recorded, recorded_ui173, fresh_login = retained.recorded, retained.recorded_ui173, retained.fresh_login
packet, retime_packet_and_metadata = retained.packet, retained.retime_packet_and_metadata


def proof(value=None):
    value = recorded() if value is None else value
    return sync.login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()



def physical_event(value, kind):
    if kind == 'confirmation':
        request = packet(value, sync.INITIALIZE)
        effect = next(e for e in value['events'] if e.get('event') == 'native_active_mover_confirmed')
        native = packet(value, sync.ACTIVE, 'to_native')
    elif kind in ('heartbeat', 'landing'):
        name = sync.HEARTBEAT if kind == 'heartbeat' else sync.LANDING
        request = packet(value, name)
        effect = next(e for e in value['events'] if e.get('event') == 'movement_forwarded' and e.get('name') == name)
        native = packet(value, 'MSG_MOVE_HEARTBEAT' if kind == 'heartbeat' else 'MSG_MOVE_FALL_LAND', 'to_native')
    else:
        request = packet(value, sync.TURN) if kind == 'turn' else [r for r in value['rows'] if r['name'] == sync.SKIPPED][int(kind[-1]) - 1]
        candidates = [e for e in value['events'] if e.get('event') == 'unmapped_client_packet' and
            e.get('name') == request['name'] and 0 <= e['time'] - request['time'] < .1]
        effect = min(candidates, key=lambda e: e['time'])
        native = None
    return request, effect, native


def physical_upper(value, request, physical):
    following = [e['time'] for e in value['events'] if e.get('session') == physical and
        (e.get('event'), e.get('direction')) == ('modern_packet', 'from_client') and e['time'] > request['time']]
    return min([request['time'] + .1, *following])


def coherent_effect_after_native(value, kind):
    initial = proof(value)
    request, effect, native = physical_event(value, kind)
    upper = physical_upper(value, request, initial['instance_session'])
    # Schedule the two strands independently inside the unchanged request
    # bounds. UI172's next physical metadata precedes its original native HB.
    retime_packet_and_metadata(value, native, request['time'] + (upper - request['time']) / 3)
    effect['time'] = request['time'] + 2 * (upper - request['time']) / 3
    value['events'].sort(key=lambda e: e['time'])
    return request, effect, native, upper


@pytest.mark.parametrize('kind', ['confirmation', 'heartbeat', 'landing'])
def test_physical_effect_can_be_logged_after_its_native_callback(kind):
    value = recorded()
    request, effect, native, upper = coherent_effect_after_native(value, kind)
    result = proof(value)
    assert request['time'] < native['time'] < effect['time'] < upper
    assert sync.validate_login_sync(json.loads(json.dumps(result, allow_nan=False))) == result
    contract.forbidden_packets(value['events'], result['instance_session'], value['since'], value['until'], login_sync=result)
    contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=result, events=value['events'])


@pytest.mark.parametrize('kind', ['confirmation', 'heartbeat', 'landing', 'turn', 'skip1', 'skip2'])
@pytest.mark.parametrize('edge', ['before_request', 'at_request', 'at_upper', 'after_upper'])
def test_physical_effect_belongs_only_to_its_own_request_interval(kind, edge):
    value = recorded()
    initial = proof(value)
    request, effect, _ = physical_event(value, kind)
    upper = physical_upper(value, request, initial['instance_session'])
    effect['time'] = {'before_request': request['time'] - .000001, 'at_request': request['time'],
        'at_upper': upper, 'after_upper': upper + .000001}[edge]
    value['events'].sort(key=lambda e: e['time'])
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('kind', ['confirmation', 'heartbeat', 'landing'])
def test_another_same_physical_request_closes_effect_interval_even_when_not_movement(kind):
    value = recorded()
    request, effect, native, upper = coherent_effect_after_native(value, kind)
    initial = proof(value)
    next_request = {'event': 'modern_packet', 'session': initial['instance_session'], 'name': 'CMSG_SERVER_TIME_OFFSET_REQUEST',
        'direction': 'from_client', 'bytes': 0, 'time': (request['time'] + effect['time']) / 2}
    value['events'].append(next_request)
    value['events'].sort(key=lambda e: e['time'])
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('fault', ['duplicate', 'wrong_guid', 'wrong_pose', 'wrong_name', 'native_body'])
def test_accepting_after_native_effects_preserves_identity_body_pose_and_uniqueness(fault):
    value = recorded()
    request, effect, native, upper = coherent_effect_after_native(value, 'heartbeat')
    proof(value)
    if fault == 'duplicate': value['events'].append(deepcopy(effect))
    elif fault == 'wrong_guid': effect['guid'] = 3
    elif fault == 'wrong_pose': effect['position'][2] += .1
    elif fault == 'wrong_name': effect['name'] = sync.LANDING
    else: native['body'] += '00'
    value['events'].sort(key=lambda e: e['time'])
    with pytest.raises(RuntimeError):
        proof(value)


def test_actual_ui173_v2_context_has_separate_bytes_and_original_v1_failure_stays_immutable():
    value = recorded_ui173()
    before = (value['completed'], value['failure'], value['failed_entry_sha256'])
    result = proof(value)
    encoded = json.dumps(result, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert hashlib.sha256(encoded).hexdigest() == 'cf4de28e086a9509d3e7105d81c9222878b8d1908655ae74f09ad42dec878b57'
    context_names = {'CMSG_QUERY_TIME', 'CMSG_QUERY_CREATURE', 'CMSG_TIME_SYNC_RESPONSE'}
    context = [e for e in result['source_events'] if e.get('name') in context_names]
    assert len(context) == 3
    assert all(sync.packet_key(e) not in result['allowed_metadata_keys'] for e in context)
    historical_projection = {**result, 'schema': historical.SCHEMA, 'source_events': [e for e in result['source_events'] if e not in context]}
    old_bytes = json.dumps(historical_projection, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert hashlib.sha256(old_bytes).hexdigest() == 'fcb548e9f316557f12b2c6f4d19857f91a65fda619197925029ec25e272f5541'
    assert (value['completed'], value['failure'], value['failed_entry_sha256']) == before
    assert before[0] is False


PHYSICAL_KINDS = ('confirmation', 'heartbeat', 'landing', 'turn', 'skip1', 'skip2')


def add_routine_boundary(value, kind, timestamp=None):
    result = proof(value)
    request, effect, _ = physical_event(value, kind)
    upper = physical_upper(value, request, result['instance_session'])
    when = effect['time'] + (upper - effect['time']) / 3 if timestamp is None else timestamp
    boundary = {'event': 'modern_packet', 'session': result['instance_session'],
        'name': 'CMSG_SERVER_TIME_OFFSET_REQUEST', 'direction': 'from_client', 'bytes': 0, 'time': when}
    value['events'].append(boundary)
    # Genuine bounded routine RAW and its physical-only drop are retained too.
    if timestamp is None:
        raw_time = when + (upper - when) / 4
        value['rows'].append({'session': value['session'], 'time': raw_time, 'name': boundary['name'],
            'direction': 'from_client', 'body': ''})
        value['events'].append({'event': 'unmapped_client_packet', 'session': result['instance_session'],
            'name': boundary['name'], 'bytes': 0, 'time': raw_time + .000001})
    value['rows'].sort(key=lambda r: r['time'])
    value['events'].sort(key=lambda e: e['time'])
    return request, effect, boundary, upper


@pytest.mark.parametrize('kind', PHYSICAL_KINDS)
def test_routine_request_boundary_survives_serialization_without_becoming_an_allowance(kind):
    value = fresh_login()
    request, effect, boundary, _ = add_routine_boundary(value, kind)
    result = json.loads(json.dumps(proof(value), allow_nan=False))
    assert boundary in result['source_events']
    assert sync.packet_key(boundary) not in result['allowed_metadata_keys']
    assert request['time'] < effect['time'] < boundary['time']
    assert sync.validate_login_sync(result) == result
    assert sync.validate_login_sync(result, events=value['events']) == result
    for owner in (value['session'], result['instance_session']):
        contract.forbidden_packets(value['events'], owner, value['since'], value['until'], login_sync=result)
    contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=result, events=value['events'])


@pytest.mark.parametrize('kind', PHYSICAL_KINDS)
def test_serialized_effect_cannot_cross_its_retained_routine_request_boundary(kind):
    value = fresh_login()
    _, effect, boundary, upper = add_routine_boundary(value, kind)
    source = json.loads(json.dumps(proof(value)))
    retained = next(e for e in source['source_events'] if e == effect)
    retained['time'] = boundary['time'] + (upper - boundary['time']) / 2
    source['source_events'].sort(key=lambda e: e['time'])
    with pytest.raises(RuntimeError):
        sync.login_sync(source['source_packets'], source['source_events'], source['session'],
            source['since'], source['until'], source['baseline_pose'])
    with pytest.raises(RuntimeError):
        sync.validate_login_sync(source)


@pytest.mark.parametrize('kind', PHYSICAL_KINDS)
@pytest.mark.parametrize('cross_boundary', [False, True])
def test_deleted_context_cannot_be_accepted_when_complete_actual_caller_metadata_is_supplied(kind, cross_boundary):
    value = fresh_login()
    _, effect, boundary, upper = add_routine_boundary(value, kind)
    source = json.loads(json.dumps(proof(value)))
    source['source_events'].remove(boundary)
    if cross_boundary:
        selected = next(e for e in source['source_events'] if e == effect)
        selected['time'] = boundary['time'] + (upper - boundary['time']) / 2
        effect['time'] = selected['time']
        value['events'].sort(key=lambda e: e['time'])
        source['source_events'].sort(key=lambda e: e['time'])
    forged = sync.login_sync(source['source_packets'], source['source_events'], source['session'],
        source['since'], source['until'], source['baseline_pose'])
    # Serialized checks cannot prove a wholly omitted event existed. V2
    # authority therefore requires complete actual metadata, never raw-only.
    assert sync.validate_login_sync(forged) == forged
    with pytest.raises(RuntimeError, match='complete actual metadata'):
        contract.native_replay(value['rows'], value['session'], value['since'], value['until'], login_sync=forged)
    with pytest.raises(RuntimeError):
        sync.validate_login_sync(forged, events=value['events'])
    for owner in (value['session'], forged['instance_session']):
        with pytest.raises(RuntimeError):
            contract.forbidden_packets(value['events'], owner, value['since'], value['until'], login_sync=forged)
    with pytest.raises(RuntimeError):
        contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
            login_sync=forged, events=value['events'])


@pytest.mark.parametrize('kind', PHYSICAL_KINDS)
@pytest.mark.parametrize('placement', ['own_metadata', 'between_metadata_and_raw', 'own_raw', 'effect'])
def test_next_request_tied_or_before_own_raw_is_not_hidden_by_timestamp_filter(kind, placement):
    value = fresh_login()
    result = proof(value)
    request, effect, _ = physical_event(value, kind)
    own = max((e for e in value['events'] if e.get('session') == result['instance_session'] and
        (e.get('event'), e.get('name'), e.get('direction')) == ('modern_packet', request['name'], 'from_client') and
        e['time'] <= request['time']), key=lambda e: e['time'])
    when = {'own_metadata': own['time'], 'between_metadata_and_raw': (own['time'] + request['time']) / 2,
        'own_raw': request['time'], 'effect': effect['time']}[placement]
    add_routine_boundary(value, kind, when)
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('kind', PHYSICAL_KINDS)
def test_timestamp_sort_cannot_hide_wrong_physical_handler_journal_order(kind):
    value = fresh_login()
    _, effect, boundary, _ = add_routine_boundary(value, kind)
    assert effect['time'] < boundary['time']
    value['events'].remove(effect)
    value['events'].insert(value['events'].index(boundary) + 1, effect)
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('fault', ['empty', 'mixed', 'metadata_with_body', 'wire_with_event',
    'metadata_without_event', 'invalid_event', 'substituted_context'])
def test_proof_bound_metadata_ingress_rejects_empty_mixed_or_malformed_arrays(fault):
    value = fresh_login()
    result = proof(value)
    rows = deepcopy(value['events'])
    context = None
    if fault == 'empty': rows = []
    elif fault == 'mixed': rows.append(deepcopy(packet(value, sync.HEARTBEAT)))
    elif fault == 'metadata_with_body': rows[0]['body'] = ''
    elif fault == 'wire_with_event': rows = [{**packet(value, sync.HEARTBEAT), 'event': 'modern_packet'}]
    elif fault == 'metadata_without_event': rows[0].pop('event')
    elif fault == 'invalid_event': rows[0]['event'] = False
    else: context = deepcopy(rows[:-1])
    with pytest.raises(RuntimeError):
        contract.forbidden_packets(rows, result['instance_session'], value['since'], value['until'],
            login_sync=result, events=context)


def test_raw_only_replay_does_not_accept_a_fake_complete_metadata_context():
    value = fresh_login()
    result = proof(value)
    for invalid in ([], value['rows'], [*value['events'], packet(value, sync.HEARTBEAT)]):
        with pytest.raises(RuntimeError):
            contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
                login_sync=result, events=invalid)


@pytest.mark.parametrize('ui,fixture,expected', [(172, recorded,
    '657a55ffd0a537d7e9e74244f457ffd2185c8d1542e041e7ae0e68fd44031090'),
    (173, recorded_ui173, 'fcb548e9f316557f12b2c6f4d19857f91a65fda619197925029ec25e272f5541')])
def test_original_v1_proof_bytes_and_failed_receipts_remain_exact(ui, fixture, expected):
    value = fixture()
    original = deepcopy(value)
    old = historical.login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))
    assert hashlib.sha256(canonical(old)).hexdigest() == expected
    assert len(old['source_events']) == 21
    new = proof(value)
    assert new['schema'] == sync.SCHEMA != historical.SCHEMA
    assert new['allowed_packet_keys'] == old['allowed_packet_keys']
    assert new['allowed_metadata_keys'] == old['allowed_metadata_keys']
    projected = {**new, 'schema': historical.SCHEMA,
        'source_events': [e for e in new['source_events'] if e in old['source_events']]}
    assert canonical(projected) == canonical(old)
    assert historical.validate_login_sync(old) == old
    assert value == original
    if ui == 173:
        assert value['completed'] is False
    else:
        assert hashlib.sha256(canonical(new)).hexdigest() == '9067fb728d07878c00e376c720e16b7a4e01cc3379ebff3d125f346933278f21'


@pytest.mark.parametrize('fixture', [recorded, recorded_ui173])
def test_v2_validator_cannot_downgrade_to_a_historical_proof_schema(fixture):
    result = proof(fixture())
    result['schema'] = historical.SCHEMA
    with pytest.raises(RuntimeError, match='exact login settlement proof'):
        sync.validate_login_sync(result)


UI172_REQUIRED_CONTEXT = [
    {'session': '04aa8d2f', 'time': 1791421132.165183, 'name': 'CMSG_QUERY_TIME',
        'direction': 'from_client', 'event': 'modern_packet', 'bytes': 0},
    {'session': '04aa8d2f', 'time': 1791421132.408879, 'name': 'CMSG_QUERY_CREATURE',
        'direction': 'from_client', 'event': 'modern_packet', 'bytes': 4},
    {'session': '04aa8d2f', 'time': 1791421132.4254525, 'name': 'CMSG_TIME_SYNC_RESPONSE',
        'direction': 'from_client', 'event': 'modern_packet', 'bytes': 8},
]


def test_actual_ui172_full_causal_context_differs_from_its_reduced_historical_fixture():
    # These three immutable metadata rows were extracted from UI172's complete
    # failed_capture01/events.jsonl. Other unrelated full-journal metadata is
    # independently replayed by the source-bound audit, not fabricated here.
    value = recorded()
    reduced = proof(value)
    value['events'].extend(deepcopy(UI172_REQUIRED_CONTEXT))
    value['events'].sort(key=lambda e: e['time'])
    complete = proof(value)
    assert len(reduced['source_events']) == 21
    assert len(complete['source_events']) == 24
    assert hashlib.sha256(canonical(complete)).hexdigest() == '34d356f459b9072c5406c4e2cfa651850f48c4859fd4871f789588d94ea90991'
    assert all(e in complete['source_events'] and sync.packet_key(e) not in
        complete['allowed_metadata_keys'] for e in UI172_REQUIRED_CONTEXT)
    assert sync.validate_login_sync(complete, events=value['events']) == complete
    with pytest.raises(RuntimeError, match='complete actual caller metadata'):
        sync.validate_login_sync(reduced, events=value['events'])
    projected = {**complete, 'schema': historical.SCHEMA,
        'source_events': [e for e in complete['source_events'] if e not in UI172_REQUIRED_CONTEXT]}
    assert hashlib.sha256(canonical(projected)).hexdigest() == '657a55ffd0a537d7e9e74244f457ffd2185c8d1542e041e7ae0e68fd44031090'
    for owner in (value['session'], complete['instance_session']):
        contract.forbidden_packets(value['events'], owner, value['since'], value['until'], login_sync=complete)
    contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=complete, events=value['events'])


AUTHORITY_PATHS = ('source rederivation', 'physical metadata guard', 'native metadata guard',
    'raw guard', 'full native replay', 'occupied swap', 'occupied roundtrip')


def authority_roundtrip():
    from tools.client_compatibility.world.tests import test_bag_swap_contract as bags
    value = bags.fresh_roundtrip()
    physical = next(e['session'] for e in value['events'] if e.get('event') == 'instance_authenticated')
    start = min(r['time'] for r in value['rows'] if r['name'] == contract.ACTION)
    for row in value['rows']:
        if row['time'] >= start:
            native = row['direction'] in ('to_native', 'from_native')
            value['events'].append({'session': value['session'] if native else physical,
                'time': row['time'] - .00001, 'event': 'native_packet' if native else 'modern_packet',
                'name': row['name'], 'direction': row['direction'], 'bytes': len(bytes.fromhex(row['body']))})
    value['events'].sort(key=lambda e: e['time'])
    return value


def authority_call(value, result, path):
    interval = (value['session'], value['since'], value['until'])
    if path == 'source rederivation':
        return sync.validate_login_sync(result, events=value['events'])
    if path == 'physical metadata guard':
        return contract.forbidden_packets(value['events'], result['instance_session'], value['since'], value['until'], login_sync=result)
    if path == 'native metadata guard':
        return contract.forbidden_packets(value['events'], *interval, login_sync=result)
    if path == 'raw guard':
        return contract.forbidden_packets(value['rows'], *interval, login_sync=result, events=value['events'])
    if path == 'full native replay':
        return contract.native_replay(value['rows'], *interval, login_sync=result, events=value['events'])
    if path == 'occupied swap':
        first = min(r['time'] for r in value['rows'] if r['name'] == contract.ACTION)
        rows = [r for r in value['rows'] if r['name'] != contract.ACTION or r['time'] < first + .5]
        return contract.swap_packets(rows, *interval, login_sync=result, events=value['events'])
    assert path == 'occupied roundtrip'
    return contract.roundtrip_packets(value['rows'], *interval, login_sync=result, events=value['events'])


@pytest.mark.parametrize('kind', PHYSICAL_KINDS)
@pytest.mark.parametrize('placement', ['adjacent', 'after_handler'])
@pytest.mark.parametrize('path', AUTHORITY_PATHS)
def test_duplicate_actual_boundary_occurrence_rejects_on_each_authority_path(kind, placement, path):
    value = authority_roundtrip()
    _, _, boundary, _ = add_routine_boundary(value, kind)
    result = proof(value)
    assert value['events'].count(boundary) == result['source_events'].count(boundary) == 1
    authority_call(value, result, path)
    duplicate = deepcopy(boundary)
    if placement == 'adjacent':
        value['events'].insert(value['events'].index(boundary) + 1, duplicate)
    else:
        value['events'].append(duplicate)
    assert value['events'].count(boundary) == 2
    with pytest.raises(RuntimeError, match='boundary occurrence is duplicated'):
        proof(value)
    with pytest.raises(RuntimeError, match='boundary occurrence is duplicated'):
        authority_call(value, result, path)


@pytest.mark.parametrize('order', [(0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)])
@pytest.mark.parametrize('path', AUTHORITY_PATHS)
def test_native_metadata_permutations_cannot_be_sorted_into_a_valid_v2_proof(order, path):
    value = authority_roundtrip()
    result = proof(value)
    original_rows = deepcopy(value['rows'])
    names = (sync.ACTIVE, 'MSG_MOVE_HEARTBEAT', 'MSG_MOVE_FALL_LAND')
    selected = [next(e for e in value['events'] if
        (e.get('event'), e.get('direction'), e.get('name')) == ('native_packet', 'to_native', name)) for name in names]
    positions = [value['events'].index(e) for e in selected]
    assert positions == sorted(positions)
    authority_call(value, result, path)
    for position, index in zip(positions, order):
        value['events'][position] = selected[index]
    assert value['rows'] == original_rows
    # Historical v1 keeps this inherited behavior; only successor v2 repairs it.
    legacy = historical.login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))
    assert legacy['schema'] == historical.SCHEMA
    with pytest.raises(RuntimeError, match='native startup metadata'):
        proof(value)
    with pytest.raises(RuntimeError, match='native startup metadata'):
        authority_call(value, result, path)


def test_one_boundary_can_be_referenced_by_reconstruction_and_every_authority_guard():
    value = authority_roundtrip()
    _, _, boundary, _ = add_routine_boundary(value, 'heartbeat')
    result = json.loads(json.dumps(proof(value), allow_nan=False))
    before = deepcopy(value['events'])
    assert value['events'].count(boundary) == result['source_events'].count(boundary) == 1
    for path in AUTHORITY_PATHS:
        authority_call(value, result, path)
    assert sync.validate_login_sync(result) == result
    assert value['events'] == before
    assert value['events'].count(boundary) == result['source_events'].count(boundary) == 1


RAW_NATIVE_BOOT = ('CMSG_SET_ACTIVE_MOVER', 'MSG_MOVE_HEARTBEAT', 'MSG_MOVE_FALL_LAND')


def move_native_raw_after_physical(value, target):
    native = packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')
    physical = next(r for r in value['rows'] if r['direction'] == 'from_client' and
        r['name'] == target and r['time'] > native['time'])
    assert value['rows'].index(native) < value['rows'].index(physical)
    before = deepcopy(value['rows'])
    value['rows'].remove(native)
    value['rows'].insert(value['rows'].index(physical) + 1, native)
    for stream in (('from_client', 'to_client'), ('from_native', 'to_native')):
        assert [r for r in value['rows'] if r['direction'] in stream] == [r for r in before if r['direction'] in stream]
    assert sorted(map(sync.packet_key, value['rows'])) == sorted(map(sync.packet_key, before))
    return native, physical


def corrected_instance_raw_inversion(value):
    native = packet(value, 'MSG_MOVE_HEARTBEAT', 'to_native')
    skipped = next(r for r in value['rows'] if r['direction'] == 'from_client' and
        r['name'] == sync.SKIPPED and r['time'] > native['time'])
    query = next(r for r in value['rows'] if r['direction'] == 'from_client' and
        r['name'] == 'CMSG_QUERY_PLAYER_NAMES' and r['time'] > skipped['time'])
    delta = value['since'] - recorded()['since']
    context = {'session': value['session'], 'time': 1791421132.3824353 + delta,
        'event': 'modern_packet', 'direction': 'from_client', 'name': query['name'], 'bytes': 14}
    assert len(bytes.fromhex(query['body'])) == context['bytes']
    value['events'].append(context)
    value['events'].sort(key=lambda e: e['time'])
    before = proof(value)
    original_time = context['time']
    # Native wraps the realm strand. Its delayed RAW append must complete
    # before the next realm query samples metadata. Change only this copied,
    # unrelated context sample, preserving all own boot evidence and RAW bytes.
    context['time'] = skipped['time'] + (query['time'] - skipped['time']) / 3
    witness = skipped['time'] + (context['time'] - skipped['time']) / 2
    assert native['time'] < skipped['time'] < witness < context['time'] < query['time']
    assert 0 < context['time'] - original_time < .0001
    value['events'].sort(key=lambda e: e['time'])
    assert proof(value) == before
    assert context not in before['source_events']
    move_native_raw_after_physical(value, sync.SKIPPED)
    assert value['rows'].index(native) < value['rows'].index(query)
    return before


def test_actual_ui172_source_legal_raw_cross_stream_inversion_preserves_exact24_event_proof():
    value = recorded()
    value['events'].extend(deepcopy(UI172_REQUIRED_CONTEXT))
    value['events'].sort(key=lambda e: e['time'])
    original = corrected_instance_raw_inversion(value)
    result = proof(value)
    assert canonical(result) == canonical(original)
    assert hashlib.sha256(canonical(result)).hexdigest() == '34d356f459b9072c5406c4e2cfa651850f48c4859fd4871f789588d94ea90991'
    assert sync.validate_login_sync(result, events=value['events']) == result
    contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=result, events=value['events'])


@pytest.mark.parametrize('path', AUTHORITY_PATHS)
def test_source_legal_instance_raw_inversion_keeps_every_authority_path_positive(path):
    value = authority_roundtrip()
    result = corrected_instance_raw_inversion(value)
    assert proof(value) == result
    authority_call(value, result, path)


@pytest.mark.parametrize('adjacent', range(5))
def test_physical_raw_per_stream_occurrence_reversal_is_still_refused(adjacent):
    value = recorded()
    names = (sync.INITIALIZE, sync.TURN, sync.SKIPPED, sync.HEARTBEAT, sync.SKIPPED, sync.LANDING)
    selected = [r for r in value['rows'] if r['direction'] == 'from_client' and r['name'] in names]
    assert len(selected) == 6
    positions = [value['rows'].index(r) for r in selected]
    a, b = positions[adjacent:adjacent + 2]
    value['rows'][a], value['rows'][b] = value['rows'][b], value['rows'][a]
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('order', [(0, 2, 1), (1, 0, 2), (1, 2, 0), (2, 0, 1), (2, 1, 0)])
def test_native_raw_per_stream_occurrence_permutation_is_still_refused(order):
    value = recorded()
    selected = [packet(value, name, 'to_native') for name in RAW_NATIVE_BOOT]
    positions = [value['rows'].index(r) for r in selected]
    for position, index in zip(positions, order):
        value['rows'][position] = selected[index]
    with pytest.raises(RuntimeError, match='per-stream startup RAW'):
        proof(value)


@pytest.mark.parametrize('modern_name,native_name', [(sync.INITIALIZE, sync.ACTIVE),
    (sync.HEARTBEAT, 'MSG_MOVE_HEARTBEAT'), (sync.LANDING, 'MSG_MOVE_FALL_LAND')])
def test_native_raw_cannot_append_before_its_own_request_when_sampled_times_stay_valid(modern_name, native_name):
    value = recorded()
    modern, native = packet(value, modern_name), packet(value, native_name, 'to_native')
    assert modern['time'] < native['time'] < modern['time'] + .1
    streams = {direction: [r for r in value['rows'] if r['direction'] == direction]
        for direction in ('from_client', 'to_native')}
    value['rows'].remove(native)
    value['rows'].insert(value['rows'].index(modern), native)
    assert all([r for r in value['rows'] if r['direction'] == direction] == stream
        for direction, stream in streams.items())
    with pytest.raises(RuntimeError, match='native RAW must follow its own modern RAW'):
        proof(value)


UI174_CLOCKS = (603247621, 603249911, 603250161)


def replace_login_clocks(value, clocks, gaps=None):
    """Vary exact wire clocks while preserving the native movement encoding."""
    retained.change_body(packet(value, sync.INITIALIZE), 0, 'I', clocks[0])
    for name, clock in zip((sync.HEARTBEAT, sync.LANDING), clocks[1:]):
        modern = packet(value, name)
        retained.change_body(modern, len(sync.ACTOR_GUID) + 12, 'I', clock)
        native_name, raw = sync.encode(name, 2, sync.parse(bytes.fromhex(modern['body']), 2))
        packet(value, native_name, 'to_native')['body'] = raw.hex()
    skipped = [r for r in value['rows'] if (r['name'], r['direction']) == (sync.SKIPPED, 'from_client')]
    actual = [b - a for a, b in zip(clocks, clocks[1:])] if gaps is None else gaps
    for row, gap in zip(skipped, actual):
        retained.change_body(row, len(sync.ACTOR_GUID), 'I', gap)


@pytest.mark.parametrize('clocks', [UI174_CLOCKS, (1, 1751, 2001), (1, 1752, 2002),
    (1, 2, 0xffffffff), (0xffffffff - 2540, 0xffffffff - 250, 0xffffffff)])
def test_exact_skipped_client_clock_steps_use_the_physical_prefix_bound(clocks):
    # UI174's actual 2290/250-ms steps total 2540 ms during a 0.387-s
    # physical prefix. This wire-only regression does not replace the separate
    # full immutable UI174 receipt evaluation with all raw rows and metadata.
    value = fresh_login()
    replace_login_clocks(value, clocks)
    result = proof(value)
    assert result['initialization']['clock'] == clocks[0]
    assert result['clock_deltas'] == [b - a for a, b in zip(clocks, clocks[1:])]
    assert result['landing']['native']['time'] <= result['login_packets'][-1]['time'] + 2
    assert sync.validate_login_sync(json.loads(json.dumps(result)), events=value['events']) == result
    for owner in (value['session'], result['instance_session']):
        contract.forbidden_packets(value['events'], owner, value['since'], value['until'], login_sync=result)
    contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=result, events=value['events'])


@pytest.mark.parametrize('step', [0, 1])
@pytest.mark.parametrize('delta', [-1, 1])
def test_loading_clock_gaps_must_still_equal_each_exact_unsigned_step(step, delta):
    value = fresh_login()
    gaps = [2290, 250]
    gaps[step] += delta
    replace_login_clocks(value, UI174_CLOCKS, gaps)
    with pytest.raises(RuntimeError, match='clock gaps do not equal'):
        proof(value)


@pytest.mark.parametrize('clocks,gaps', [((0, 2290, 2540), [2290, 250]),
    ((100, 100, 350), [0, 250]), ((100, 2390, 2390), [2290, 0]),
    ((0xffffffff - 100, 0xffffffff - 50, 199), [50, 250]),
    ((0xffffffff - 100, 2189, 2439), [2290, 250])])
def test_zero_repeated_and_wrapped_uint32_clocks_are_still_refused(clocks, gaps):
    value = fresh_login()
    replace_login_clocks(value, clocks, gaps)
    with pytest.raises(RuntimeError, match='clock gaps do not equal'):
        proof(value)


@pytest.mark.parametrize('field', ['initializer', 'heartbeat', 'landing', 'skipped'])
def test_clock_fields_cannot_overflow_their_exact_uint32_wire_width(field):
    value = fresh_login()
    replace_login_clocks(value, UI174_CLOCKS)
    name = {'initializer': sync.INITIALIZE, 'heartbeat': sync.HEARTBEAT,
        'landing': sync.LANDING, 'skipped': sync.SKIPPED}[field]
    row = packet(value, name)
    offset = 0 if field == 'initializer' else len(sync.ACTOR_GUID) + (12 if field in ('heartbeat', 'landing') else 0)
    raw = bytes.fromhex(row['body'])
    row['body'] = (raw[:offset] + struct.pack('<Q', 1 << 32) + raw[offset + 4:]).hex()
    with pytest.raises(RuntimeError):
        proof(value)


@pytest.mark.parametrize('offset', [-.000001, 0, .000001])
def test_physical_two_second_initializer_boundary_with_loading_clocks(offset):
    value = fresh_login()
    replace_login_clocks(value, UI174_CLOCKS)
    result = proof(value)
    modern, native = packet(value, sync.LANDING), packet(value, 'MSG_MOVE_FALL_LAND', 'to_native')
    forward_delay = native['time'] - modern['time']
    target = result['initialization']['modern']['time'] + 2 + offset
    retime_packet_and_metadata(value, modern, target - forward_delay)
    retime_packet_and_metadata(value, native, target)
    if offset > 0:
        with pytest.raises(RuntimeError, match='ordered two-second initial prefix'):
            proof(value)
    else:
        complete = proof(value)
        assert complete['boot_finished_at'] == target
        assert sync.validate_login_sync(complete, events=value['events']) == complete

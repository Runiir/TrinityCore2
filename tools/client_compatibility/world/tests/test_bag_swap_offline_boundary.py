"""Interrupted-entry exclusion and an exact native startup online reset."""
from copy import deepcopy
from pathlib import Path

import pytest

from tools.client_compatibility import bag_swap_offline_boundary as boundary
from tools.client_compatibility import bag_swap_preservation as preservation
from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture as snapshots
from tools.client_compatibility.world.tests.test_bag_swap_login_sync import fresh_login
from tools.client_compatibility.world.tests.test_item_actionbar_contract import native_packet


def ref(root, member):
    return {'path': str(root / 'evidence' / member), 'sha256': 'a' * 64}


def precision(native, exact):
    return {**{k: native[k] for k in ('guid', 'account', 'name', 'class', 'level', 'xp',
        'online', 'rest_bonus', 'logout_time', 'is_logout_resting')}, 'exact_rest_bonus': exact,
        'exact_rest_bonus_float32_bits': preservation.float32_bits(exact)}


def case(root, recovered=False):
    wire = fresh_login()
    baseline = snapshots()[0]
    baseline['2']['native'].update(rest_bonus=53.0, logout_time=2000)
    stale = deepcopy(baseline)
    exact_after, display = preservation.native_rest(53.0, 4)
    stale['2']['native'].update(online=1, rest_bonus=display, totaltime=200, leveltime=200, logout_time=2305)
    offline = deepcopy(stale)
    offline['2']['native']['online'] = 0
    actor = {'actor': 'scout', 'guid': 2, 'account_id': 2}
    runtime = {k: {'pid': 100 + i, 'start_ticks': str(200 + i)}
        for i, k in enumerate(('worldserver', 'modern_world', 'client'))}
    common = {'actor': actor, 'runtime': runtime, 'code_commit': 'b' * 40, 'controller': 'code',
        'model': None, 'revision': None, 'custom_script_permission': 'blocked_by_user',
        'softTargetInteract': deepcopy(boundary.SCRIPT), 'qualification_added': False,
        'input_sent': False, 'mutation_sent': False, 'completed': True, 'failure': None}
    refs = {role: ref(root, 'ui174/' + name + '/episode.json')
        for role, name in (('preparation', 'scout_ready01'), ('failed_entry', 'entry01'),
            ('precision', 'rest_before01'), ('idle', 'failed_live_idle_capture01'))}
    refs.update(diagnostic=ref(root, 'crash/diagnostic.json'), primary_stop=ref(root, 'primary_stop/episode.json'))
    ready = {**deepcopy(common), 'phase': 'bags_swap_scout_ready', 'started_at': 1980., 'finished_at': 1990.,
        'all_offline_snapshot': deepcopy(baseline), 'native_session': wire['session'],
        'predecessor': {'primary_stop': refs['primary_stop']},
        'frame': {'monitor': {'input_isolation': {'game_pid': 999}}}}
    before_precision = {**deepcopy(common), 'phase': 'bags_swap_rest_precision_complete',
        'started_at': 1991., 'finished_at': 1992., 'source': refs['preparation'],
        'before': deepcopy(baseline), 'after': deepcopy(baseline), 'query': preservation.PRECISION_QUERY,
        'row': precision(baseline['2']['native'], 53.0)}
    failed = {**deepcopy(common), 'phase': 'bags_swap_entry_started', 'completed': False,
        'failure': 'RuntimeError: excluded old validator failure', 'started_at': wire['since'],
        'entry_input_finished_at': wire['until'], 'finished_at': wire['until'] + 1,
        'native_session': wire['session'], 'preparation_source': refs['preparation'],
        'precision_source': refs['precision'], 'input_sent': True, 'cases': [], 'cleanup': [],
        'all_offline_snapshot': deepcopy(baseline), 'native_before_entry': deepcopy(baseline['2']['native']),
        'raw_entry_packets': deepcopy(wire['rows']), 'raw_entry_events': deepcopy(wire['events'])}
    idle = {**deepcopy(common), 'phase': 'bags_swap_failed_live_idle_observed',
        'started_at': 2306., 'finished_at': 2310., 'excluded_failed_entry': True,
        'first_failure_source': refs['failed_entry'], 'all_snapshot': deepcopy(stale),
        'native_original': {'pose': {'stand': 1, 'sheath': 0}, 'afk': True,
            'actions': deepcopy(baseline['2']['saved']['actions'])}}
    session = wire['session']
    shapes = [('CMSG_STAND_STATE_CHANGE', 'from_client', '01'),
        ('CMSG_STANDSTATECHANGE', 'to_native', '01000000'),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', '01'),
        ('SMSG_STAND_STATE_UPDATE', 'to_client', '0100000000')]
    idle_packets = [dict(session=session, name=name, direction=direction, body=raw, time=2305. + i * .01)
        for i, (name, direction, raw) in enumerate(shapes)]
    idle_packets.append(dict(native_packet({68: 1, 148: 2}, creation=False, time=2305.04), session=session))
    idle_events = []
    for row in idle_packets:
        native = row['direction'] in ('to_native', 'from_native')
        metadata_owner = session if native or row['name'] == 'SMSG_STAND_STATE_UPDATE' else 'fresh-physical-instance'
        idle_events.append({'event': 'native_packet' if native else 'modern_packet', 'session': metadata_owner,
            'name': row['name'], 'direction': row['direction'], 'bytes': len(bytes.fromhex(row['body'])),
            'time': row['time'] - .00001})
    idle_events.extend([{'event': 'modern_packet', 'session': session, 'name': 'CMSG_CHAT_MESSAGE_AFK',
        'direction': 'from_client', 'bytes': 5, 'time': 2305.011},
        {'event': 'native_packet', 'session': session, 'name': 'CMSG_MESSAGECHAT_AFK',
            'direction': 'to_native', 'bytes': 5, 'time': 2305.012}])
    idle_events.sort(key=lambda r: r['time'])
    packets, events = wire['rows'] + idle_packets, wire['events'] + idle_events
    image = ref(root, 'ui174/entry01/bags_swap_entered.png')
    value = {key: deepcopy(common[key]) for key in ('actor', 'controller', 'model', 'revision',
        'custom_script_permission', 'softTargetInteract', 'qualification_added', 'input_sent',
        'mutation_sent', 'completed', 'failure')}
    value.update(schema=boundary.SCHEMA, phase=boundary.BEFORE_PHASE, started_at=2311., finished_at=2313.,
        sources=refs, previous_runtime=deepcopy(runtime), previous_client=deepcopy(runtime['client']),
        current_services={}, old_process_absence=dict.fromkeys(boundary.ABSENCE, True),
        owned_game_identity={'pid': 999, 'source': refs['preparation']}, ready_baseline=deepcopy(baseline),
        stale_snapshot=deepcopy(stale), excluded_failed_entry=True, operations_admitted=0,
        bag_input_sent=False, normal_logout_input_sent=False, original_failed_image=image,
        exact_precision={'query': preservation.PRECISION_QUERY,
            'before_row': precision(stale['2']['native'], exact_after),
            'after_row': precision(stale['2']['native'], exact_after)},
        journal_sources={k: ref(root, 'crash/' + k + '.jsonl') for k in ('packets', 'events')},
        journal_interval={'since': ready['finished_at'], 'audit_until': 2312.},
        service_files={k: ref(root, 'service/' + k) for k in
            ('native_binary', 'native_config', 'bridge_binary', 'bridge_build_receipt')})
    if recovered:
        value.update(phase=boundary.PHASE, started_at=2321., finished_at=2323.,
            recovery_started_after=2313., before_capture_source=ref(root, 'crash/boundary.json'),
            all_offline_snapshot=offline,
            current_services={k: {'pid': 300 + i, 'start_ticks': str(400 + i)}
                for i, k in enumerate(('worldserver', 'modern_world'))})
        value['sources']['before_capture'] = value['before_capture_source']
        value['exact_precision']['after_row']['online'] = 0
        value['journal_interval']['audit_until'] = 2322.
        events += [{'event': 'world_listener', 'port': 18087, 'time': 2314.},
            {'event': 'world_connection', 'session': 'readiness-probe', 'time': 2315.},
            {'event': 'world_connection_closed', 'session': 'readiness-probe', 'time': 2315.01, 'error': 'End of file'}]
    value['source_preservation'] = {role: {'before': deepcopy(r), 'after': deepcopy(r)}
        for role, r in {**value['sources'], 'failed_image': image}.items()}
    return value, ready, failed, before_precision, idle, packets, events


@pytest.mark.parametrize('recovered', [False, True])
def test_excluded_entry_and_automatic_idle_preserve_truthful_crash_lineage(tmp_path, recovered):
    values = case(tmp_path, recovered)
    original = deepcopy(values)
    proof = boundary.validate(*values)
    assert values == original
    assert proof['operations_admitted'] == 0
    assert proof['history']['automatic_idle_preserved_excluded'] is True
    assert proof['history']['normal_logout_proved'] is False
    assert proof['runtime']['scout_absent'] is True
    assert 'client' not in proof['runtime']['current_services']
    assert values[2]['completed'] is False
    if recovered:
        assert proof['transition']['only_online_changed'] is True
        assert proof['history']['startup_probe_sessions'] == ['readiness-probe']
        assert proof['history']['startup_listener_events'] == [{'event': 'world_listener', 'port': 18087, 'time': 2314.}]


@pytest.mark.parametrize('fault', ['foreign_session', 'wrong_port', 'extra_field', 'duplicate',
    'missing', 'before_recovery', 'after_probe', 'bad_time', 'stale_capture'])
def test_bridge_listener_requires_exact_unattributed_shape_and_recovery_chronology(tmp_path, fault):
    values = list(case(tmp_path, True))
    listener = values[-1][-3]
    if fault == 'foreign_session': listener['session'] = 'foreign'
    elif fault == 'wrong_port': listener['port'] = 18086
    elif fault == 'extra_field': listener['account_id'] = 2
    elif fault == 'duplicate': values[-1].append(dict(listener, time=2314.1))
    elif fault == 'missing': values[-1].remove(listener)
    elif fault == 'before_recovery': listener['time'] = values[0]['recovery_started_after']
    elif fault == 'after_probe': listener['time'] = 2315.001
    elif fault == 'bad_time': listener['time'] = True
    else:
        values = list(case(tmp_path))
        values[-1].append({'event': 'world_listener', 'port': 18087, 'time': 2311.})
    with pytest.raises(RuntimeError): boundary.validate(*values)


@pytest.mark.parametrize('fault', ['health', 'power', 'position', 'inventory', 'actions', 'pets', 'peer',
    'rest', 'logout', 'accounting', 'online', 'bits', 'rounded', 'missing_peer'])
def test_native_startup_refuses_every_change_except_the_exact_online_reset(tmp_path, fault):
    value = case(tmp_path, True)[0]
    stale, final = value['stale_snapshot'], value['all_offline_snapshot']
    before, after = value['exact_precision']['before_row'], value['exact_precision']['after_row']
    if fault == 'health': final['2']['native']['health'] -= 1
    elif fault == 'power': final['2']['native']['power1'] = 1
    elif fault == 'position': final['2']['native']['position_x'] += 1
    elif fault == 'inventory': final['2']['inventory'][0][9] = 2
    elif fault == 'actions': final['2']['saved']['actions'] = []
    elif fault == 'pets': final['2']['pets'] = [{'id': 9}]
    elif fault == 'peer': final['6']['pets'][0]['curhealth'] += 1
    elif fault == 'rest': final['2']['native']['rest_bonus'] += 1
    elif fault == 'logout': final['2']['native']['logout_time'] += 60
    elif fault == 'accounting': final['2']['native']['totaltime'] += 1
    elif fault == 'online': final['2']['native']['online'] = False
    elif fault == 'bits': after['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'rounded': before['exact_rest_bonus'] = before['rest_bonus']
    else: final.pop('6')
    with pytest.raises(RuntimeError): boundary.validate_transition(stale, final, before, after)


@pytest.mark.parametrize('fault', ['changed_failed', 'changed_image', 'normal_logout', 'swap', 'new_entry',
    'extra_afk', 'extra_stand', 'new_gameplay', 'missing_prefix', 'reordered_prefix', 'missing_idle',
    'missing_afk', 'afk_effect', 'native_inventory', 'missing_absence', 'fake_game_ticks',
    'current_client', 'old_service', 'wrong_previous_client', 'qualified', 'relabel_failed',
    'foreign_actor', 'bad_timestamp', 'owner_recreated', 'orphan_probe', 'authenticated_probe', 'late_probe'])
def test_closed_crash_boundary_refuses_unsupported_lineage_or_extra_input(tmp_path, fault):
    values = list(case(tmp_path, True))
    value, ready, failed, precision_value, idle, packets, events = values
    owner = ready['native_session']
    if fault == 'changed_failed': value['source_preservation']['failed_entry']['after']['sha256'] = 'b' * 64
    elif fault == 'changed_image': value['source_preservation']['failed_image']['after']['sha256'] = 'b' * 64
    elif fault in ('normal_logout', 'swap', 'new_entry', 'extra_stand', 'new_gameplay'):
        name = {'normal_logout': 'CMSG_LOGOUT_REQUEST', 'swap': 'CMSG_SWAP_INV_ITEM',
            'new_entry': 'CMSG_PLAYER_LOGIN', 'extra_stand': 'CMSG_STAND_STATE_CHANGE',
            'new_gameplay': 'CMSG_SET_SELECTION'}[fault]
        packets.append(dict(session=owner, name=name, direction='from_client', body='00', time=2311.))
    elif fault == 'extra_afk': events.append({'event': 'modern_packet', 'session': owner,
        'direction': 'from_client', 'bytes': 5, 'time': 2311., 'name': 'CMSG_CHAT_MESSAGE_AFK'})
    elif fault == 'missing_prefix': packets.pop(0)
    elif fault == 'reordered_prefix': packets[0], packets[1] = packets[1], packets[0]
    elif fault == 'missing_idle': packets[:] = [r for r in packets if r['name'] != 'CMSG_STAND_STATE_CHANGE']
    elif fault == 'missing_afk': events[:] = [r for r in events if r.get('name') != 'CMSG_MESSAGECHAT_AFK']
    elif fault == 'afk_effect': idle['native_original']['afk'] = False
    elif fault == 'native_inventory':
        packets.append(dict(native_packet({0: 2}, guid=(0x4000 << 48) | 41, creation=False, time=2311.), session=owner))
    elif fault == 'missing_absence': value['old_process_absence']['worldserver'] = False
    elif fault == 'fake_game_ticks': value['owned_game_identity']['start_ticks'] = '123'
    elif fault == 'current_client': value['current_services']['client'] = ready['runtime']['client']
    elif fault == 'old_service': value['current_services']['worldserver'] = ready['runtime']['worldserver']
    elif fault == 'wrong_previous_client': value['previous_client']['pid'] = 9999
    elif fault == 'qualified': value['qualification_added'] = True
    elif fault == 'relabel_failed': failed['completed'] = True
    elif fault == 'foreign_actor': idle['actor']['guid'] = 6
    elif fault == 'bad_timestamp': events.append(dict(event='native_player_created', guid=2, session='foreign', time=True))
    elif fault == 'owner_recreated': events.append(dict(event='native_player_created', guid=2, session=owner, time=2311.))
    elif fault == 'orphan_probe': events.pop()
    elif fault == 'authenticated_probe': events[-1]['account_id'] = 2
    else: events[-1]['time'] = value['journal_interval']['audit_until'] + 1
    with pytest.raises(RuntimeError): boundary.validate(*values)


def test_real_root_requires_actual_ui174_pins_even_when_other_fields_are_consistent(tmp_path):
    values = list(case(tmp_path))
    value, ready, failed, precise, idle, *_ = values
    actual = str(boundary.BATCH / 'scout_ready01/episode.json')
    value['sources']['preparation']['path'] = actual
    failed['preparation_source']['path'] = precise['source']['path'] = actual
    with pytest.raises(RuntimeError, match='actual UI174'): boundary.validate(*values)


def ping(session, when, native=False):
    return {'session': session, 'time': when, 'event': 'native_packet' if native else 'modern_packet',
        'name': 'CMSG_PING', 'direction': 'to_native' if native else 'from_client', 'bytes': 8}


def test_observed_slow_complete_ping_forwarding_retains_exact_occurrence_intervals():
    rows = [ping('owner', 10.), ping('owner', 10.227698, True), ping('owner', 11.),
        ping('physical', 11.3), ping('owner', 11.919185, True)]
    _, proof = boundary._latency(rows, 'owner', 'physical')
    assert proof['realm_occurrences'] == proof['native_forwarded_occurrences'] == 2
    assert proof['pairs'][1]['observed_delay_seconds'] == pytest.approx(.919185)
    assert proof['bodies_retained'] is False
    assert proof['terminal_incomplete_requests'] == []


def test_only_actual_terminal_incomplete_automatic_ping_is_preserved_without_invention():
    rows = [ping('owner', 10.), ping('owner', 10.1, True), ping('owner', 11.)]
    _, proof = boundary._latency(rows, 'owner', 'physical')
    assert proof['terminal_incomplete_requests'] == [rows[-1]]
    assert proof['missing_forward_invented'] is False


@pytest.mark.parametrize('fault', ['wrong_bytes', 'wrong_stream', 'earlier_missing', 'forward_before',
    'forward_after_next', 'terminal_not_tail', 'two_missing', 'reordered_incoming', 'reordered_forwarded'])
def test_latency_cannot_hide_missing_earlier_misaligned_or_foreign_occurrences(fault):
    rows = [ping('owner', 10.), ping('owner', 10.1, True), ping('owner', 11.), ping('owner', 11.9, True)]
    if fault == 'wrong_bytes': rows[-1]['bytes'] = 0
    elif fault == 'wrong_stream': rows[-1]['session'] = 'other'
    elif fault == 'earlier_missing': rows.pop(1)
    elif fault == 'forward_before': rows[1]['time'] = 9.
    elif fault == 'forward_after_next': rows[1]['time'] = 11.1
    elif fault == 'terminal_not_tail':
        rows.pop()
        rows.append({'event': 'native_packet', 'session': 'owner', 'name': 'SMSG_PONG',
            'direction': 'from_native', 'bytes': 4, 'time': 11.1})
    elif fault == 'reordered_incoming': rows[0], rows[2] = rows[2], rows[0]
    elif fault == 'reordered_forwarded': rows[1], rows[3] = rows[3], rows[1]
    else:
        rows.pop()
        rows.append(ping('owner', 12.))
    with pytest.raises(RuntimeError): boundary._latency(rows, 'owner', 'physical')

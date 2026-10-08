"""Pure exclusion proof for an interrupted entry and ordinary service recovery.

Previous client identities remain historical. A recovered boundary names only
the two currently observed services; startup resets an existing stale online
flag and does not provide evidence of normal logout or a bag interaction.
"""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import re

from . import bag_swap_contract as contract
from . import bag_swap_login_sync_v2 as sync
from . import bag_swap_preservation as preservation
from . import interaction_bag_swap_idle_housekeeping as idle_history

SCHEMA = 'client442_bag_swap_offline_boundary_v1'
BEFORE_PHASE = 'bags_swap_crash_stale_captured'
PHASE = 'bags_swap_crash_restart_closed_excluded'
PROOF_SCHEMA = 'client442_bag_swap_offline_boundary_proof_v1'
ROOT = Path.home() / '.local/share/trinity-client442-lab'
BATCH = ROOT / 'evidence/client_interactions_20261008_ui174'
PINS = {
    'preparation': ('scout_ready01', 'e5758afaca0e215ceedb6b71a1c80497d151713dce9e84123c8e73eaa0a9afab'),
    'failed_entry': ('entry01', 'fed10276437ce1d2ee8cd4c106b21ba9f10925c43a3870e17a7196b7573041bc'),
    'precision': ('rest_before01', '8d7aeaa9d2717524e163dfe5fe87acd177b5518c6083cd298186d1401c23a782'),
    'idle': ('failed_live_idle_capture01', '3dae180140b3c13d77964ed42e336f87a89bd6b974e4febf72046e78d96e2dcd'),
}
DIAGNOSTIC_SHA256 = '71b6b3624298c75d7cacb0db7b8b227e7b0a93ed6e3a75a01db35b2d069629fa'
SOURCE_ROLES = frozenset((*PINS, 'diagnostic', 'primary_stop'))
ABSENCE = frozenset(('worldserver', 'modern_world', 'previous_client', 'owned_game_pid'))
SERVICES = frozenset(('worldserver', 'modern_world'))
SCRIPT = {'original': '0', 'current_stock_disabled': '1', 'original_restored': False}
MAX_ROWS = 250000
ROUTINE = {'CMSG_TIME_SYNC_RESPONSE': 8, 'CMSG_TIME_SYNC_RESP': 8,
    'CMSG_SERVER_TIME_OFFSET_REQUEST': 0, 'CMSG_QUEST_GIVER_STATUS_QUERY': 8}
LOGOUT = frozenset(('CMSG_LOGOUT_REQUEST', 'SMSG_LOGOUT_RESPONSE', 'SMSG_LOGOUT_COMPLETE'))
require, finite, strict_equal, body = contract.require, contract.finite, contract.strict_equal, contract.body


def reference(ref):
    require(type(ref) is dict and set(ref) == {'path', 'sha256'} and
        type(ref['path']) is str and Path(ref['path']).is_absolute() and
        str(Path(ref['path'])) == ref['path'] and '..' not in Path(ref['path']).parts and
        type(ref['sha256']) is str and re.fullmatch('[0-9a-f]{64}', ref['sha256']),
        'canonical byte-bound offline source required')
    return ref


def _identity(value):
    require(type(value) is dict and {'pid', 'start_ticks'} <= set(value) and
        set(value) <= {'pid', 'start_ticks', 'engine', 'build'} and
        type(value['pid']) is int and value['pid'] > 0 and type(value['start_ticks']) is str and
        re.fullmatch('[1-9][0-9]*', value['start_ticks']), 'actual process lifetime required')
    if 'engine' in value:
        require(value['engine'] == 'cpp' and type(value.get('build')) is dict,
            'source-owned native bridge build identity required')


def _preserve_to_stale(before, after):
    old, now = contract.owned_snapshot(before), contract.owned_snapshot(after, offline=False)
    require(all(strict_equal(before[g], after[g]) for g in ('1', '3', '4', '5', '6')) and
        now['native']['online'] == 1 and set(old['native']) == set(now['native']) and
        {k for k in old['native'] if not strict_equal(old['native'][k], now['native'][k])} <=
            preservation.ACCOUNTING | {'rest_bonus', 'online'} and
        all(type(v['native'].get(k)) is int and v['native'][k] >= 0
            for v in (old, now) for k in preservation.ACCOUNTING) and
        all(now['native'][k] >= old['native'][k] for k in ('totaltime', 'leveltime', 'logout_time')) and
        finite(now['native'].get('rest_bonus')) and
        old['native']['rest_bonus'] <= now['native']['rest_bonus'] < contract.REST_CAP and
        strict_equal(now['saved'], old['saved']) and strict_equal(now['inventory'], old['inventory']) and
        now['pets'] == old['pets'] == [], 'crash changed protected or saved state beyond accounting/rest/online')
    return {'protected_five_unchanged': True, 'all_saved_inventory_pets_unchanged': True,
        'health_power_pose_unchanged': True, 'stale_online': 1}


def validate_transition(before, after, before_row, after_row):
    """Only native startup's stale actor2 online reset is admitted here."""
    contract.owned_snapshot(before, offline=False)
    contract.owned_snapshot(after)
    require(before['2']['native']['online'] == 1 and
        all(before[g]['native']['online'] == 0 for g in ('1', '3', '4', '5', '6')),
        'one stale actor2 online flag required before ordinary native startup')
    expected = deepcopy(before)
    expected['2']['native']['online'] = 0
    require(strict_equal(after, expected), 'native startup may change only actor2 online from one to zero')
    preservation.exact_precision(before_row, before)
    preservation.exact_precision(after_row, after)
    expected_row = deepcopy(before_row)
    expected_row['online'] = 0
    require(strict_equal(after_row, expected_row), 'startup must retain exact FLOAT bits and logout/accounting values')
    return {'kind': 'ordinary_native_startup_online_reset', 'owner': 2, 'online_before': 1,
        'online_after': 0, 'only_online_changed': True, 'exact_float32_unchanged': True,
        'rest_float32_bits': before_row['exact_rest_bonus_float32_bits'],
        'logout_time_unchanged': True, 'normal_logout_proved': False, 'operations_admitted': 0}


def validate_runtime(boundary):
    """Validate a small mixed-epoch boundary without claiming a current client."""
    require(type(boundary) is dict and boundary.get('schema') == SCHEMA and
        boundary.get('phase') in (BEFORE_PHASE, PHASE) and 'runtime' not in boundary,
        'explicit historical client and current service epochs required')
    previous = boundary.get('previous_runtime')
    require(type(previous) is dict and set(previous) == SERVICES | {'client'},
        'complete historical ready runtime required')
    for identity in previous.values():
        _identity(identity)
    require(strict_equal(boundary.get('previous_client'), previous['client']),
        'previous client must retain the immutable ready lifetime')
    current = boundary.get('current_services')
    require(type(current) is dict and set(current) == (SERVICES if boundary['phase'] == PHASE else set()),
        'only actual current native and bridge services may be projected')
    for kind, identity in current.items():
        _identity(identity)
        require((identity['pid'], identity['start_ticks']) !=
            (previous[kind]['pid'], previous[kind]['start_ticks']),
            'ordinary recovery requires a new service lifetime')
    checks = boundary.get('old_process_absence')
    require(type(checks) is dict and set(checks) == ABSENCE and all(v is True for v in checks.values()),
        'all old service/client lifetimes and observed game PID must be absent')
    game = boundary.get('owned_game_identity')
    require(type(game) is dict and set(game) == {'pid', 'source'} and
        type(game['pid']) is int and game['pid'] > 0, 'old game has only its actually retained PID and source')
    reference(game['source'])
    require(not any(k in boundary for k in ('game_start_ticks', 'game_before', 'sigterm_at',
        'stop_finished_at', 'normal_logout_time', 'socket_expiry_seconds')),
        'unobserved game ticks, normal logout or stop chronology cannot be invented')
    return {'previous_client': deepcopy(previous['client']), 'current_services': deepcopy(current),
        'scout_absent': True, 'owned_game_pid_absent': True}


def _sources(boundary, ready, failed, precision, idle):
    refs = boundary.get('sources')
    wanted = SOURCE_ROLES | ({'before_capture'} if boundary['phase'] == PHASE else set())
    require(type(refs) is dict and set(refs) == wanted, 'all actual crash-boundary source roles required')
    for ref in refs.values():
        reference(ref)
    production = Path(refs['preparation']['path']).is_relative_to(ROOT)
    if production:
        for role, (directory, sha) in PINS.items():
            require(refs[role] == {'path': str(BATCH / directory / 'episode.json'), 'sha256': sha},
                'actual UI174 immutable source pin differs')
        require(refs['diagnostic']['sha256'] == DIAGNOSTIC_SHA256,
            'actual copied UI174 crash diagnostic bytes differ')
    require(refs['preparation'] == failed.get('preparation_source') == precision.get('source') and
        refs['failed_entry'] == idle.get('first_failure_source') and
        refs['precision'] == failed.get('precision_source') and
        refs['primary_stop'] == ready.get('predecessor', {}).get('primary_stop'),
        'original preparation/failure/precision/idle/primary-stop lineage differs')
    if boundary['phase'] == PHASE:
        require(boundary.get('before_capture_source') == refs['before_capture'],
            'final boundary must bind the actual pre-start capture')
        require(finite(boundary.get('recovery_started_after')) and
            boundary['recovery_started_after'] < boundary['started_at'],
            'actual pre-start observation finish must bound recovered services')
    image = reference(boundary.get('original_failed_image'))
    require(Path(image['path']) == Path(refs['failed_entry']['path']).parent / 'bags_swap_entered.png',
        'original failed observation PNG must remain source-owned')
    preserved = boundary.get('source_preservation')
    require(type(preserved) is dict and set(preserved) == wanted | {'failed_image'},
        'complete immutable source and PNG preservation observations required')
    for role, ref in {**refs, 'failed_image': image}.items():
        require(type(preserved[role]) is dict and set(preserved[role]) == {'before', 'after'} and
            strict_equal(preserved[role]['before'], ref) and strict_equal(preserved[role]['after'], ref),
            'original failed/source bytes changed across observation')
    return refs


def _originals(boundary, ready, failed, precision, idle):
    require(all(type(v) is dict for v in (ready, failed, precision, idle)) and
        ready.get('phase') == 'bags_swap_scout_ready' and ready.get('completed') is True and
        ready.get('failure') is None and failed.get('phase') == 'bags_swap_entry_started' and
        failed.get('completed') is False and type(failed.get('failure')) is str and failed['failure'] and
        failed.get('input_sent') is True and failed.get('mutation_sent') is False and
        failed.get('qualification_added') is False and failed.get('cases') == failed.get('cleanup') == [] and
        precision.get('phase') == 'bags_swap_rest_precision_complete' and precision.get('completed') is True and
        precision.get('failure') is None and idle.get('phase') == 'bags_swap_failed_live_idle_observed' and
        idle.get('completed') is True and idle.get('failure') is None and idle.get('excluded_failed_entry') is True,
        'original ready/precision and excluded failed/idle outcomes must stay truthful')
    for value in (ready, failed, precision, idle):
        require(strict_equal(value.get('actor'), ready.get('actor')) and
            strict_equal(value.get('runtime'), ready.get('runtime')) and
            value.get('code_commit') == ready.get('code_commit') and value.get('controller') == 'code' and
            value.get('model') is value.get('revision') is None and
            value.get('custom_script_permission') == 'blocked_by_user' and
            strict_equal(value.get('softTargetInteract'), SCRIPT) and value.get('qualification_added') is False,
            'immutable original actor, runtime, source epoch or script authority differs')
    require(all(v.get('input_sent') is False and v.get('mutation_sent') is False for v in (ready, precision, idle)),
        'ready, precision and idle observations must remain read-only')
    baseline = ready.get('all_offline_snapshot')
    contract.owned_snapshot(baseline)
    require(strict_equal(boundary.get('ready_baseline'), baseline) and
        strict_equal(failed.get('all_offline_snapshot'), baseline) and
        strict_equal(failed.get('native_before_entry'), baseline['2']['native']) and
        strict_equal(precision.get('before'), baseline) and strict_equal(precision.get('after'), baseline) and
        precision.get('query') == preservation.PRECISION_QUERY and
        ready.get('native_session') == failed.get('native_session') and
        strict_equal(boundary.get('previous_runtime'), ready.get('runtime')) and
        strict_equal(boundary.get('actor'), ready.get('actor')),
        'complete immutable original baseline and owned session required')
    preservation.exact_precision(precision.get('row'), baseline)
    game = boundary['owned_game_identity']
    require(game['source'] == boundary['sources']['preparation'] and
        game['pid'] == ready.get('frame', {}).get('monitor', {}).get('input_isolation', {}).get('game_pid'),
        'old game PID must come from the actual retained ready monitor')
    times = [ready.get('finished_at'), precision.get('started_at'), precision.get('finished_at'),
        failed.get('started_at'), failed.get('entry_input_finished_at'), failed.get('finished_at'),
        idle.get('started_at'), idle.get('finished_at'), boundary.get('started_at'), boundary.get('finished_at')]
    require(all(finite(t) for t in times) and all(a < b for a, b in zip(times, times[1:])),
        'honest original entry, idle and new observation chronology required')
    _preserve_to_stale(baseline, idle.get('all_snapshot'))
    original = idle.get('native_original')
    require(type(original) is dict and strict_equal(original.get('pose'), {'stand': 1, 'sheath': 0}) and
        original.get('afk') is True and strict_equal(original.get('actions'), baseline['2']['saved']['actions']),
        'source-backed automatic seated/AFK idle facts required')
    return baseline


def _digest(rows):
    digest = hashlib.sha256(b'[')
    for index, row in enumerate(rows):
        if index:
            digest.update(b',')
        digest.update(sync.packet_key(row).encode())
    digest.update(b']')
    return digest.hexdigest()


def _latency(events, session, physical):
    """Retain asynchronous automatic pings inside their own request intervals."""
    pings = [r for r in events if r.get('name') == 'CMSG_PING']
    fields = {'session', 'time', 'event', 'name', 'direction', 'bytes'}
    shapes = {(physical, 'modern_packet', 'from_client'),
        (session, 'modern_packet', 'from_client'), (session, 'native_packet', 'to_native')}
    require(all(set(r) == fields and type(r['bytes']) is int and r['bytes'] == 8 and
        finite(r['time']) and (r['session'], r['event'], r['direction']) in shapes for r in pings),
        'automatic latency metadata has another attribution or shape')
    incoming = [r for r in pings if r['session'] == session and r['direction'] == 'from_client']
    forwarded = [r for r in pings if r['direction'] == 'to_native']
    require(all(a['time'] < b['time'] for stream in (incoming, forwarded)
        for a, b in zip(stream, stream[1:])), 'automatic ping streams must retain their observed occurrence order')
    require(len(incoming) - len(forwarded) in (0, 1), 'automatic ping forwarding occurrence count differs')
    pairs = []
    for index, (request, effect) in enumerate(zip(incoming, forwarded)):
        upper = incoming[index + 1]['time'] if index + 1 < len(incoming) else math.inf
        require(request['time'] <= effect['time'] < upper,
            'automatic ping forward must belong to its own ordered request interval')
        pairs.append({'request': deepcopy(request), 'forward': deepcopy(effect),
            'observed_delay_seconds': effect['time'] - request['time']})
    incomplete = incoming[len(forwarded):]
    if incomplete:
        require(incomplete[0]['time'] == max(r['time'] for r in events),
            'only the actual final interrupted non-gameplay request may lack forwarding')
    return pings, {'realm_occurrences': len(incoming), 'native_forwarded_occurrences': len(forwarded),
        'physical_occurrences': len([r for r in pings if r['session'] == physical]),
        'pairs': pairs, 'terminal_incomplete_requests': deepcopy(incomplete), 'bodies_retained': False,
        'missing_forward_invented': False}


def _history(boundary, ready, failed, precision, idle, packets, events):
    require(type(packets) is list and type(events) is list and len(packets) <= MAX_ROWS and
        len(events) <= MAX_ROWS and all(type(r) is dict for r in packets + events),
        'bounded complete packet and event journal arrays required')
    interval = boundary.get('journal_interval')
    require(type(interval) is dict and set(interval) == {'since', 'audit_until'} and
        interval['since'] == ready['finished_at'] and finite(interval['audit_until']) and
        boundary['started_at'] <= interval['audit_until'] <= boundary['finished_at'],
        'explicit ready-to-observation journal cutoff required')
    refs = boundary.get('journal_sources')
    require(type(refs) is dict and set(refs) == {'packets', 'events'}, 'both closed source-owned journals required')
    for ref in refs.values():
        reference(ref)
    session = ready['native_session']
    for r in packets + events:
        if r.get('session') == session or r.get('account_id') == 2 or r.get('guid') == 2 or r.get('event') == 'world_listener':
            require(finite(r.get('time')), 'malformed attributable time cannot be filtered out')
    since, until = interval['since'], interval['audit_until']
    rows = [r for r in packets if finite(r.get('time')) and since <= r['time'] <= until]
    scoped = [r for r in events if finite(r.get('time')) and since <= r['time'] <= until]
    require(all(set(r) == sync.WIRE_FIELDS and r.get('direction') in sync.WIRE_DIRECTIONS and
        type(r.get('session')) is str and r['session'] == session and type(r.get('name')) is str
        for r in rows), 'current raw history must retain exact owned attribution')
    for array in (rows, scoped):
        require(len({sync.packet_key(r) for r in array}) == len(array), 'current journal history contains duplicate rows')
    for r in rows:
        body(r)
    end = failed['entry_input_finished_at']
    prefix = [r for r in rows if failed['started_at'] <= r['time'] <= end]
    prefix_events = [r for r in scoped if failed['started_at'] <= r['time'] <= end]
    require(strict_equal(prefix, failed.get('raw_entry_packets')) and
        strict_equal(prefix_events, failed.get('raw_entry_events')), 'complete ordered failed-entry prefixes changed')
    pose = [failed['native_before_entry'][k] for k in ('position_x', 'position_y', 'position_z', 'orientation')]
    boot = sync.login_sync(prefix, prefix_events, session, failed['started_at'], end, pose)
    physical = boot['instance_session']
    require(not any(r.get('name') in LOGOUT | {contract.ACTION} for r in rows + scoped),
        'no normal logout or bag operation belongs to the crash boundary')
    authenticated = [r for r in scoped if r.get('event') in ('world_authenticated', 'instance_authenticated')]
    require(len(authenticated) == 1 and authenticated[0].get('event') == 'instance_authenticated' and
        authenticated[0].get('session') == physical and authenticated[0].get('account_id') == 2,
        'crash history cannot admit another realm or physical entry')
    replay = contract.native_replay(prefix, session, failed['started_at'], end, login_sync=boot, events=prefix_events)
    gap = idle_history.automatic_idle(rows, scoped, session, physical, end, idle['finished_at'],
        original=idle_history.original_objects(prefix))
    native = idle_history.native_history([r for r in rows if r['time'] > idle['finished_at']], gap['ending_native_objects'])
    require(strict_equal(native, gap['ending_native_objects']), 'post-idle native owner/item fields changed')
    late = [r for r in rows if r['time'] > idle['finished_at']]
    idle_history.clean_requests(late, [])
    require(all(r.get('name') in ROUTINE and len(body(r)) == ROUTINE[r['name']] for r in late
        if r.get('direction') in ('from_client', 'to_native')), 'late automatic read-only request body differs')
    late_events = [r for r in scoped if r['time'] > idle['finished_at'] and r.get('session') in (session, physical)]
    require(all(r.get('event') in ('modern_packet', 'native_packet', 'unmapped_client_packet',
        'world_connection_closed', 'native_stream_closed') for r in late_events),
        'post-idle history cannot recreate an owner or conceal another gameplay effect')
    ignored = idle_history.ignored_queries(late_events, session)
    latency, latency_proof = _latency(late_events, session, physical)
    allowed = {sync.packet_key(r) for r in ignored + latency}
    require(all(sync.packet_key(r) in allowed or (r.get('name') in ROUTINE and
        type(r.get('bytes')) is int and r['bytes'] == ROUTINE[r['name']]) for r in late_events
        if r.get('direction') in ('from_client', 'to_native')), 'post-idle metadata contains another gameplay input')
    listeners = [r for r in scoped if r.get('event') == 'world_listener']
    recovery_since = boundary.get('recovery_started_after')
    if boundary['phase'] == PHASE:
        require(len(listeners) == 1 and set(listeners[0]) == {'event', 'time', 'port'} and
            type(listeners[0]['port']) is int and listeners[0]['port'] == 18087 and
            finite(recovery_since) and recovery_since < listeners[0]['time'] <= until,
            'one exact observed modern bridge listener must belong to the recovery window')
    else:
        require(not listeners, 'a stale capture cannot admit a recovered bridge listener')
    startup = [r for r in scoped if r.get('session') not in (session, physical) and r.get('event') != 'world_listener']
    sessions = {r.get('session') for r in startup}
    require(None not in sessions and all(type(s) is str and s for s in sessions), 'unattributed startup event required')
    for owner in sessions:
        pair = [r for r in startup if r['session'] == owner]
        require(boundary['phase'] == PHASE and len(pair) == 2 and
            [r.get('event') for r in pair] == ['world_connection', 'world_connection_closed'] and
            listeners[0]['time'] < pair[0]['time'] < pair[1]['time'] <= until and
            set(pair[0]) == {'session', 'time', 'event'} and set(pair[1]) == {'session', 'time', 'event', 'error'} and
            type(pair[1]['error']) is str, 'only actually observed unauthenticated startup probes are allowed')
    exact_before, exact_after = precision['row'], boundary['exact_precision']['before_row']
    login = contract.login_packets(prefix, session, failed['started_at'], end)
    matches = []
    for second in range(math.floor(login['request']['time']), math.floor(login['verify']['time']) + 1):
        elapsed = second - exact_before['logout_time']
        if elapsed < 0:
            continue
        exact, display = preservation.native_rest(exact_before['exact_rest_bonus'], elapsed)
        if exact == exact_after['exact_rest_bonus'] and display == exact_after['rest_bonus']:
            matches.append({'native_login_second': second, 'offline_seconds': elapsed})
    require(len(matches) == 1 and int(exact_after['exact_rest_bonus']) == replay['rest_threshold'],
        'crash rest must bind one exact native login second and initial owner threshold')
    return {'since': since, 'audit_until': until, 'session': session, 'instance_session': physical,
        'source_packet_count': len(rows), 'source_event_count': len(scoped),
        'source_packets_sha256': _digest(rows), 'source_events_sha256': _digest(scoped),
        'original_prefix_packets_sha256': _digest(prefix), 'original_prefix_events_sha256': _digest(prefix_events),
        'original_failed_entry_excluded': True, 'login_rederived_schema': sync.SCHEMA,
        'automatic_idle_preserved_excluded': True, 'automatic_idle_stand': 1, 'automatic_idle_afk': True,
        'normal_logout_proved': False, 'missing_crash_close_events_invented': False,
        'observed_close_events': deepcopy([r for r in scoped if r.get('event') in
            ('world_connection_closed', 'native_stream_closed')]), 'startup_probe_sessions': sorted(sessions),
        'startup_listener_events': deepcopy(listeners),
        'late_latency': latency_proof, 'rest': matches[0]}


def validate(boundary, ready, failed, precision, idle, packets, events):
    """Replay an excluded stale capture or its ordinary server-restart closure."""
    try:
        return _validate(boundary, ready, failed, precision, idle, packets, events)
    except (KeyError, ValueError, TypeError, IndexError, OverflowError) as error:
        raise RuntimeError('offline crash boundary cannot be parsed exactly') from error


def _validate(boundary, ready, failed, precision, idle, packets, events):
    runtime = validate_runtime(boundary)
    require(boundary.get('completed') is True and boundary.get('failure') is None and
        boundary.get('controller') == 'code' and boundary.get('model') is boundary.get('revision') is None and
        boundary.get('excluded_failed_entry') is True and type(boundary.get('operations_admitted')) is int and
        boundary['operations_admitted'] == 0 and all(boundary.get(k) is False for k in
            ('qualification_added', 'input_sent', 'mutation_sent', 'bag_input_sent', 'normal_logout_input_sent')) and
        boundary.get('custom_script_permission') == 'blocked_by_user' and
        strict_equal(boundary.get('softTargetInteract'), SCRIPT), 'excluded read-only boundary labels required')
    _sources(boundary, ready, failed, precision, idle)
    baseline = _originals(boundary, ready, failed, precision, idle)
    stale = boundary.get('stale_snapshot')
    preservation_proof = _preserve_to_stale(baseline, stale)
    exact = boundary.get('exact_precision')
    require(type(exact) is dict and exact.get('query') == preservation.PRECISION_QUERY,
        'actual native exact FLOAT observations required')
    preservation.exact_precision(exact.get('before_row'), stale)
    if boundary['phase'] == PHASE:
        transition = validate_transition(stale, boundary.get('all_offline_snapshot'), exact['before_row'], exact.get('after_row'))
    else:
        require('all_offline_snapshot' not in boundary and strict_equal(exact.get('before_row'), exact.get('after_row')),
            'pre-start capture must retain its stale state without claiming offline recovery')
        transition = {'kind': 'observed_crash_stale_online', 'online': 1, 'normal_logout_proved': False}
    files = boundary.get('service_files')
    require(type(files) is dict and set(files) == {'native_binary', 'native_config', 'bridge_binary', 'bridge_build_receipt'},
        'installed service binary/config/build source identities required')
    for ref in files.values():
        reference(ref)
    history = _history(boundary, ready, failed, precision, idle, packets, events)
    return {'schema': PROOF_SCHEMA, 'excluded_failed_entry': True, 'qualification_added': False,
        'operations_admitted': 0, 'sources_preserved': True, 'original_failed_image_preserved': True,
        'preservation': preservation_proof, 'transition': transition, 'runtime': runtime, 'history': history}

"""Pure reconciliation of the failed-entry journals through the completed stop."""
from copy import deepcopy
import re

from . import bag_swap_contract as contract
from . import bag_swap_failed_contract as history
from . import bag_swap_login_sync as sync
from .item_actionbar_contract import body, finite, require, strict_equal

SCHEMA = 'client442_bag_swap_failed_journals_v1'
CHECKS = frozenset(('scout_launcher_absent', 'owned_game_absent', 'all_retained_saved_state',
    'all_characters_offline', 'primary_still_stopped', 'native_lifetime', 'bridge_lifetime',
    'origin_registration'))


def _rows(values, wire=False):
    # Validate every row before time filtering or assigning it to an actor.
    require(type(values) is list and all(type(r) is dict and finite(r.get('time')) for r in values),
        'every full and archived journal row must be a dictionary with finite time')
    keys = []
    for row in values:
        keys.append(sync.packet_key(row))
        if wire:
            require(set(row) == sync.WIRE_FIELDS and type(row.get('session')) is str and row['session'] and
                type(row.get('name')) is str and row['name'] and row.get('direction') in sync.WIRE_DIRECTIONS,
                'every raw journal row requires canonical native-owner attribution')
            body(row)
    require(len(set(keys)) == len(keys), 'full or archived journal duplicates a row')


def _window(rows, since, until):
    return [row for row in rows if since <= row['time'] <= until]


def _latency(events, session):
    rows = sorted(events, key=lambda e: e['time'])
    require(len(rows) % 4 == 0, 'ordinary realm latency requires complete quartets')
    expected = (('modern_packet', 'CMSG_PING', 'from_client', 8),
        ('modern_packet', 'SMSG_PONG', 'to_client', 4),
        ('native_packet', 'CMSG_PING', 'to_native', 8),
        ('native_packet', 'SMSG_PONG', 'from_native', 4))
    for index in range(0, len(rows), 4):
        group = rows[index:index + 4]
        require(all(set(e) == {'session', 'event', 'time', 'name', 'direction', 'bytes'} and
            e['session'] == session and type(e['bytes']) is int and
            (e['event'], e['name'], e['direction'], e['bytes']) == shape
            for e, shape in zip(group, expected)) and
            all(a['time'] < b['time'] for a, b in zip(group, group[1:])) and
            group[-1]['time'] - group[0]['time'] < 2,
            'ordinary realm latency metadata has another owner, shape or order')
    return rows


def _pause(pause, ready, failed):
    require(type(pause) is dict and type(ready) is dict and type(failed) is dict and
        pause.get('schema') == 'client442_bag_swap_failed_entry_closure_v1' and
        pause.get('phase') == 'bags_swap_failed_entry_closed_paused' and pause.get('completed') is True and
        pause.get('failure') is None and pause.get('qualification_added') is False and
        pause.get('excluded_failed_entry') is True and type(pause.get('operations_admitted')) is int and
        pause['operations_admitted'] == 0 and pause.get('input_sent') is False and
        pause.get('mutation_sent') is False and pause.get('cases') == pause.get('cleanup') == [] and
        pause.get('action') == 'stop_expired_failed_entry_scout' and pause.get('stop_attempted') is True,
        'a successful excluded stop without admitted input is required')
    require(type(pause.get('shutdown_checks')) is dict and set(pause['shutdown_checks']) == CHECKS and
        all(v is True for v in pause['shutdown_checks'].values()), 'all eight actual shutdown checks must be true')
    require(pause.get('controller') == 'code' and pause.get('model') is None and pause.get('revision') is None and
        pause.get('fine_tuned') is False and pause.get('custom_script_permission') == 'blocked_by_user',
        'excluded pause controller and script labels differ')
    for snapshot in (pause.get('before'), pause.get('after'), pause.get('all_offline_snapshot')):
        contract.owned_snapshot(snapshot)
    require(strict_equal(pause['before'], pause['after']) and
        strict_equal(pause['before'], pause['all_offline_snapshot']),
        'the complete six-actor offline native/saved/pet/inventory state changed during stop')
    before = pause['game_before']
    require(type(before) is dict and type(before.get('pid')) is int and before['pid'] > 0 and
        type(before.get('start_ticks')) is str and re.fullmatch(r'[1-9][0-9]*', before['start_ticks'], flags=re.ASCII),
        'the actual owned game process identity is required')
    frame, source = pause['frame'], pause['closing_frame_source']
    require(type(frame) is dict and type(source) is dict and type(frame.get('file')) is str and
        type(source.get('path')) is str and source['path'].rsplit('/', 1)[-1] == frame['file'] and
        type(source.get('sha256')) is str and re.fullmatch(r'[0-9a-f]{64}', source['sha256']) and
        frame.get('sha256') == source['sha256'], 'the actual closing frame source must bind the retained frame')


def _boundary(events, event, session, prefix):
    selected = [e for e in events if e.get('event') == event]
    require(len(selected) == 1 and set(selected[0]) == {'session', 'error', 'time', 'event'} and
        selected[0]['session'] == session and type(selected[0]['error']) is str and
        selected[0]['error'].startswith(prefix), 'one actual typed ' + event + ' teardown is required')
    return selected[0]


def validate_journals(packets, events, ready, failed, pause, pause_packets, pause_events):
    """Reconcile immutable pause copies and all journals through stop completion.

    The last two arrays are the original pause.journal_sources, not the earlier
    review capture. No existing receipt or earlier code epoch is rewritten.
    """
    try:
        return _validate_journals(packets, events, ready, failed, pause, pause_packets, pause_events)
    except (KeyError, ValueError, IndexError, TypeError) as error:
        raise RuntimeError('failed pause journals cannot be validated exactly') from error


def _validate_journals(packets, events, ready, failed, pause, pause_packets, pause_events):
    for rows, wire in ((packets, True), (events, False), (pause_packets, True), (pause_events, False)):
        _rows(rows, wire)
    _pause(pause, ready, failed)
    supplied = pause['failed_history']
    require(type(supplied) is dict, 'the original failed pause history is required')
    since, entry_since, audit_until, until, stop_finished = (ready['started_at'], failed['started_at'],
        supplied['audit_until'], pause['finished_at'], pause['stop_finished_at'])
    require(all(finite(v) for v in (since, ready['finished_at'], entry_since, pause['started_at'],
        audit_until, stop_finished, until)) and
        since < ready['finished_at'] < entry_since < pause['started_at'] <= audit_until < stop_finished <= until,
        'the original ready, failed entry, audit and bounded stop intervals differ')
    raw, metadata = _window(packets, since, until), _window(events, since, until)
    require(len(raw) == len(packets) and len(metadata) == len(events),
        'current journal copies must contain exactly the ready-to-pause interval')
    old_raw, old_events = _window(raw, entry_since, audit_until), _window(metadata, entry_since, audit_until)
    require(all(entry_since <= r['time'] <= audit_until for r in pause_packets + pause_events) and
        strict_equal(old_raw, pause_packets) and strict_equal(old_events, pause_events),
        'the complete original pause journal rows changed, were reordered or are missing from the full interval')
    original = history.failed_history(old_raw, old_events, ready, failed, audit_until)
    require(strict_equal(original, supplied), 'the original failed history differs from the complete pause journal replay')
    session, physical = original['session'], original['instance_session']
    require(pause.get('native_session') == ready.get('native_session') == failed.get('native_session') == session,
        'the ready, failed entry and pause have different native owners')
    require(not any(r.get('session') == physical for r in raw),
        'the packet journal must retain its native owner, not a physical-session alias')
    attributed = [e for e in metadata if e.get('account_id') == 2 or e.get('guid') == 2]
    require(all(e.get('session') in (session, physical) for e in attributed),
        'actor2 metadata cannot be attributed to another session')
    login_keys = {sync.packet_key(r) for r in original['login_sync']['login_packets']}
    require(all(sync.packet_key(r) in login_keys for r in raw if r.get('name') == 'CMSG_PLAYER_LOGIN'),
        'the full ready-to-stop interval contains another login request')
    prep_raw = [r for r in raw if r['time'] < entry_since]
    prep_events = [e for e in metadata if e['time'] < entry_since]
    require(not prep_raw and all(e.get('session') == session for e in prep_events),
        'the original ready-to-login prefix cannot contain raw input or another actor')
    prep_latency = _latency(prep_events, session)
    require(len(prep_latency) == 4, 'the complete original ready prefix requires its sole observed latency quartet')
    tail_raw = [r for r in raw if r['time'] > audit_until]
    tail_events = [e for e in metadata if e['time'] > audit_until]
    realm_close = _boundary(tail_events, 'world_connection_closed', session, 'End of file [asio.misc:2 at ')
    native_close = _boundary(tail_events, 'native_stream_closed', session, 'Operation canceled [system:125 at ')
    require(audit_until < realm_close['time'] < native_close['time'] <= stop_finished <= until and
        native_close['time'] - realm_close['time'] < 1,
        'the realm EOF and native cancellation must fall inside the actual bounded stop')
    active_raw = [r for r in tail_raw if r['time'] < realm_close['time']]
    active_events = [e for e in tail_events if e['time'] < realm_close['time']]
    require(not active_raw, 'the retained post-audit stop interval contains unexpected raw input or native mutation')
    tail_latency = _latency(active_events, session)
    require(len(tail_latency) == 4, 'the complete stop interval requires its sole observed latency quartet')
    require(len(tail_events) == len(active_events) + 2 and not tail_raw and
        all(e.get('session') == session for e in tail_events),
        'the completed stop interval contains an invented boundary, input or native effect')
    # Reuse the frozen closed-world guard on every ordinary event before the
    # actual EOF. The two independently typed teardown rows are never passed
    # as gameplay allowances or retroactively inserted into the old receipt.
    active_metadata = [e for e in metadata if e['time'] <= realm_close['time'] and e not in (realm_close, native_close)]
    activity = history.failed_history(raw, active_metadata, ready, failed, realm_close['time'])
    return deepcopy({'schema': SCHEMA, 'qualification_excluded': True, 'operations_admitted': 0,
        'interval': {'since': since, 'until': until, 'audit_until': audit_until},
        'failed_history': original, 'original_pause_journals_reconciled': True,
        'all_eight_shutdown_checks': deepcopy(pause['shutdown_checks']), 'all_six_offline_preserved': True,
        'pre_entry_latency_events': prep_latency,
        'post_stop_boundaries': {'actual_SIGTERM_time_retained': False,
            'stop_window': {'since': audit_until, 'until': stop_finished},
            'realm_connection_closed': realm_close, 'native_stream_closed': native_close,
            'events': [realm_close, native_close],
            'ordinary_latency_events': tail_latency, 'latency_bodies_retained': False,
            'pre_teardown_activity_audit': activity['post_close_audit']},
        'source_packet_count': len(raw), 'source_packets_sha256': history._digest(raw),
        'source_event_count': len(metadata), 'source_events_sha256': history._digest(metadata),
        'pause_packet_count': len(pause_packets), 'pause_packets_sha256': history._digest(pause_packets),
        'pause_event_count': len(pause_events), 'pause_events_sha256': history._digest(pause_events)})

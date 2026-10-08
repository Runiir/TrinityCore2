"""Client loading precedes the bounded stationary mover startup prefix."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import struct

import pytest

from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_login_sync_v2 as sync
from tools.client_compatibility.world.tests import test_bag_swap_login_sync as retained


def prove(value):
    return sync.login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))


def shift_suffix(value, cutoff, delta):
    for rows in (value['rows'], value['events']):
        for row in rows:
            if row['time'] >= cutoff: row['time'] += delta
    value['until'] += delta


@pytest.fixture(params=['synthetic', 'actual'])
def startup(request):
    if request.param == 'synthetic':
        value = retained.fresh_login()
        original = prove(value)
        delivered = original['login_packets'][-1]['time']
        shift_suffix(value, delivered + .000001, 3)
        return value
    supplied = os.environ.get('CLIENT442_LOADING_ENTRY_REPLAY')
    if supplied is None: pytest.skip('explicit immutable failed entry path required')
    raw = Path(supplied).read_bytes()
    assert hashlib.sha256(raw).hexdigest() == '71c1435300e6e7aede2ef8e9407ecbd760875b63446a05e5096be6524efb9686'
    entry = json.loads(raw)
    assert entry['completed'] is False and entry['failure'] is not None
    return {'rows': entry['raw_entry_packets'], 'events': entry['raw_entry_events'],
        'session': entry['native_session'], 'since': entry['started_at'], 'until': entry['finished_at'],
        'baseline_pose': [float(entry['native_before_entry'][key]) for key in
            ('position_x', 'position_y', 'position_z', 'orientation')]}


def test_loading_gap_does_not_consume_stationary_initializer_deadline(startup):
    before = deepcopy(startup)
    result = prove(startup)
    assert result['initialization']['modern']['time'] - result['login_packets'][-1]['time'] > 2
    assert result['landing']['native']['time'] - result['initialization']['modern']['time'] < 2
    assert sync.validate_login_sync(json.loads(json.dumps(result)), events=startup['events']) == result
    contract.native_replay(startup['rows'], startup['session'], startup['since'], startup['until'],
        login_sync=result, events=startup['events'])
    for owner in (startup['session'], result['instance_session']):
        contract.forbidden_packets(startup['events'], owner, startup['since'], startup['until'], login_sync=result)
    assert startup == before


@pytest.mark.parametrize('seconds, accepted', [(2, True), (2.00001, False)])
def test_two_seconds_is_still_the_exact_post_initializer_deadline(startup, seconds, accepted):
    result = prove(startup)
    landing = result['landing']['modern']
    own = [e['time'] for e in startup['events'] if (e.get('event'), e.get('name'), e.get('direction')) ==
        ('modern_packet', landing['name'], 'from_client') and e.get('session') == result['instance_session']
        and 0 <= landing['time'] - e['time'] < .1]
    assert len(own) == 1
    delta = result['initialization']['modern']['time'] + seconds - result['landing']['native']['time']
    shift_suffix(startup, own[0], delta)
    if accepted:
        rebuilt = prove(startup)
        assert rebuilt['landing']['native']['time'] == rebuilt['initialization']['modern']['time'] + 2
    else:
        with pytest.raises(RuntimeError, match='ordered two-second initial prefix'): prove(startup)


@pytest.mark.parametrize('fault', ['nonstationary', 'raw_order', 'native_metadata_order',
    'forwarding_delay', 'clock_gap', 'extra_heartbeat'])
def test_loading_anchor_preserves_exact_stationary_order_and_pair_guards(startup, fault):
    result = prove(startup)
    heartbeat = retained.packet(startup, sync.HEARTBEAT)
    if fault == 'nonstationary': retained.change_body(heartbeat, 21, 'f', startup['baseline_pose'][0] + 1)
    elif fault == 'raw_order':
        first = startup['rows'].index(heartbeat)
        second = startup['rows'].index(retained.packet(startup, sync.TURN))
        startup['rows'][first], startup['rows'][second] = startup['rows'][second], startup['rows'][first]
    elif fault == 'native_metadata_order':
        events = startup['events']
        first = next(i for i,e in enumerate(events) if (e.get('name'), e.get('direction')) == (sync.ACTIVE, 'to_native'))
        second = next(i for i,e in enumerate(events) if (e.get('name'), e.get('direction')) == ('MSG_MOVE_HEARTBEAT', 'to_native'))
        events[first], events[second] = events[second], events[first]
    elif fault == 'forwarding_delay':
        native = retained.packet(startup, 'MSG_MOVE_HEARTBEAT', 'to_native')
        retained.retime_packet_and_metadata(startup, native, heartbeat['time'] + .10001)
    elif fault == 'clock_gap':
        skipped = next(r for r in startup['rows'] if r['name'] == sync.SKIPPED)
        raw = bytearray.fromhex(skipped['body']); raw[-4:] = struct.pack('<I', result['clock_deltas'][0] + 1)
        skipped['body'] = raw.hex()
    else: startup['rows'].append(deepcopy(heartbeat))
    with pytest.raises(RuntimeError): prove(startup)


@pytest.mark.parametrize('capture, expected', [
    (retained.recorded, '9067fb728d07878c00e376c720e16b7a4e01cc3379ebff3d125f346933278f21'),
    (retained.recorded_ui173, 'cf4de28e086a9509d3e7105d81c9222878b8d1908655ae74f09ad42dec878b57')])
def test_old_v2_serialized_outputs_remain_exactly_unchanged(capture, expected):
    # Pinned from the committed classifier before this isolated anchor change.
    raw = json.dumps(prove(capture()), sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
    assert hashlib.sha256(raw).hexdigest() == expected

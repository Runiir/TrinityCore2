"""Synthetic normal-logout exclusion; no historical compressed fixture is read."""
from copy import deepcopy
import math
import struct
from types import SimpleNamespace

import pytest

from tools.client_compatibility import bag_swap_closed_logout_contract as closed
from tools.client_compatibility import bag_swap_contract as contract
from tools.client_compatibility import bag_swap_login_sync_v2 as sync
from tools.client_compatibility import bag_swap_preservation as preservation
from tools.client_compatibility.bag_swap_failed_journals import CHECKS
from tools.client_compatibility.world.buffer import Writer, player_high
from tools.client_compatibility.world.movement import encode, parse
from tools.client_compatibility.world import combat
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility import melee_result_evidence
from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture as snapshots
from tools.client_compatibility.world.tests.test_bag_swap_contract import item_fields, slot_fields
from tools.client_compatibility.world.tests.test_item_actionbar_contract import native_packet, owner_fields

SESSION, PHYSICAL = 'synthetic-realm', 'synthetic-instance'


def wire(name, direction, raw, time):
    return dict(session=SESSION, name=name, direction=direction, body=raw.hex(), time=time)


def metadata(row, *, login=False):
    native = row['direction'] in ('from_native', 'to_native')
    realm = native or login or (row['direction'] == 'to_client' and row['name'] in
        ('SMSG_STAND_STATE_UPDATE', 'SMSG_LOGOUT_RESPONSE', 'SMSG_LOGOUT_COMPLETE'))
    return dict(event='native_packet' if native else 'modern_packet', session=SESSION if realm else PHYSICAL,
        name=row['name'], direction=row['direction'], bytes=len(bytes.fromhex(row['body'])), time=row['time'] - .0001)


def self_creation(pose):
    """Build the complete stationary native self layout and inventory mask."""
    writer = Writer().pack('HI', 0, 1).pack('3B', 2, 1, 2).pack('B', 4)
    for values in ([0, 0, 0, 0, 0, 1, 0, 1],):
        for bit in values: writer.bits(bit, 1)
    writer.bits(0, 24).bits(0, 6)
    for bit in [1, 0, 0, 0, 0, 0, 1, 0, 0, 1]: writer.bits(bit, 1)
    writer.bits(0, 5)
    for bit in [1, 0, 0, 1]: writer.bits(bit, 1)
    writer.bits(0, 7).flush()
    x, y, z, orientation = pose
    writer.pack('5f', 2.5, 2.5, z, x, math.pi).pack('B', 3)
    writer.pack('3f', 4.7, y, 2.5).pack('I', 1000)
    writer.pack('5f', math.pi, 7., orientation, 7., 4.5)
    fields = {**owner_fields(), **slot_fields(), contract.INDEX['UNIT_FIELD_FLAGS']: 8}
    count = max(fields) // 32 + 1
    writer.pack('B', count)
    for group in range(count):
        writer.pack('I', sum(1 << (index % 32) for index in fields if index // 32 == group))
    for index in sorted(fields): writer.pack('I', fields[index])
    return writer.finish()


def movement(pose, clock, landing=False):
    writer = Writer().guid(2, player_high()).pack('4I', *(0, 0x200, 0, clock) if landing else (0x800, 0, 0, clock))
    writer.pack('6f', *pose, 0., 0.).pack('2I', 0, 0).bits(0 if landing else 0x20, 8).flush()
    if not landing:
        writer.pack('If', 0, 0.).bits(1, 1).bits(0, 7).flush().pack('3f', .6, .8, 0.)
    return writer.finish()


def reference(root, name):
    return {'path': str(root / name / 'episode.json'), 'sha256': 'a' * 64}


def fixture(root):
    baseline = snapshots()[0]
    baseline['2']['native'].update(rest_bonus=53., logout_time=1900)
    native = baseline['2']['native']
    pose = [native[key] for key in ('position_x', 'position_y', 'position_z', 'orientation')]
    verify = struct.pack('<i4f', 0, *pose)
    rows = [wire('CMSG_PLAYER_LOGIN', 'from_client', Writer().guid(2, player_high()).pack('f', 1000.).finish(), 2000.1),
        wire('CMSG_PLAYER_LOGIN', 'to_native', bytes.fromhex('2003'), 2000.2),
        wire('SMSG_UPDATE_OBJECT', 'from_native', self_creation(pose), 2000.25),
        wire('SMSG_LOGIN_VERIFY_WORLD', 'from_native', verify, 2000.3),
        wire('SMSG_LOGIN_VERIFY_WORLD', 'to_client', verify + bytes(4), 2000.31)]
    for item, time in ((contract.SOURCE, 2000.32), (contract.DESTINATION, 2000.33)):
        rows.append(dict(native_packet(item_fields(item), guid=item['guid'], kind=1, time=time), session=SESSION))
    rows.extend([wire(sync.INITIALIZE, 'from_client', struct.pack('<I', 1000), 2000.4),
        wire(sync.ACTIVE, 'to_native', bytes.fromhex('1003'), 2000.401),
        wire(sync.TURN, 'from_client', struct.pack('<f', math.pi), 2000.5),
        wire(sync.SKIPPED, 'from_client', sync.ACTOR_GUID + struct.pack('<I', 100), 2000.6)])
    for name, clock, time, landing in ((sync.HEARTBEAT, 1100, 2000.7, False), (sync.LANDING, 1250, 2000.9, True)):
        if landing: rows.append(wire(sync.SKIPPED, 'from_client', sync.ACTOR_GUID + struct.pack('<I', 150), 2000.8))
        raw = movement(pose, clock, landing)
        native_name, native_body = encode(name, 2, parse(raw, 2))
        rows.extend([wire(name, 'from_client', raw, time), wire(native_name, 'to_native', native_body, time + .001)])
    events = [metadata(row, login=row['name'] == 'CMSG_PLAYER_LOGIN') for row in rows]
    events.extend([dict(event='instance_authenticated', session=PHYSICAL, account_id=2, time=2000.15),
        dict(event='native_player_created', session=SESSION, guid=2, map=0, position=pose, time=2000.26),
        dict(event='native_active_mover_confirmed', session=PHYSICAL, guid=2, time=2000.4005)])
    for name, time in ((sync.TURN, 2000.5), (sync.SKIPPED, 2000.6), (sync.SKIPPED, 2000.8)):
        row = next(row for row in rows if row['name'] == name and row['time'] == time)
        events.append(dict(event='unmapped_client_packet', session=PHYSICAL, name=name,
            bytes=len(bytes.fromhex(row['body'])), time=time + .0005))
    for name, time in ((sync.HEARTBEAT, 2000.7), (sync.LANDING, 2000.9)):
        events.append(dict(event='movement_forwarded', session=PHYSICAL, name=name, guid=2, position=pose, time=time + .0005))
    events.sort(key=lambda row: row['time'])
    common = dict(actor={'actor': 'scout', 'guid': 2, 'account_id': 2},
        runtime={name: dict(pid=100 + index, start_ticks=str(200 + index))
            for index, name in enumerate(('worldserver', 'modern_world', 'client'))},
        code_commit='b' * 40, controller='code', model=None, revision=None, fine_tuned=False,
        custom_script_permission='blocked_by_user', mutation_sent=False, qualification_added=False,
        input_sent=False, completed=True, failure=None)
    ready = {**deepcopy(common), 'phase': 'bags_swap_scout_ready', 'started_at': 1980., 'finished_at': 1990.,
        'all_offline_snapshot': deepcopy(baseline), 'native_session': SESSION,
        'frame': {'monitor': {'input_isolation': {'game_pid': 999}}}}
    failed = {**deepcopy(common), 'phase': 'bags_swap_entry_started', 'completed': False, 'input_sent': True,
        'failure': 'RuntimeError: login settlement must be one ordered two-second initial prefix',
        'started_at': 2000., 'entry_input_finished_at': 2002., 'finished_at': 2003.,
        'native_session': SESSION, 'cases': [], 'cleanup': [], 'preparation_source': reference(root, 'ready'),
        'precision_source': reference(root, 'precision'), 'all_offline_snapshot': deepcopy(baseline),
        'native_before_entry': deepcopy(native), 'raw_entry_packets': deepcopy(rows), 'raw_entry_events': deepcopy(events)}
    late = [wire(name, direction, bytes.fromhex(raw), 2305. + index * .01) for index, (name, direction, raw) in enumerate([
        ('CMSG_STAND_STATE_CHANGE', 'from_client', '01'), ('CMSG_STANDSTATECHANGE', 'to_native', '01000000'),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', '01'), ('SMSG_STAND_STATE_UPDATE', 'to_client', '0100000000')])]
    late.append(dict(native_packet({68: 1, 148: 2}, creation=False, time=2305.04), session=SESSION))
    late.extend(wire(name, direction, bytes.fromhex(raw), time) for name, direction, raw, time in [
        ('CMSG_LOGOUT_REQUEST', 'from_client', '00', 2314.), ('CMSG_LOGOUT_REQUEST', 'to_native', '', 2314.001),
        ('SMSG_LOGOUT_RESPONSE', 'from_native', '0000000000', 2314.01),
        ('SMSG_LOGOUT_RESPONSE', 'to_client', '0000000000', 2314.02),
        ('SMSG_MOVE_ROOT', 'from_native', '100300000000', 2314.03)])
    late.append(dict(native_packet({53: 8 | 0x40000}, creation=False, time=2314.04), session=SESSION))
    late.extend(wire(name, direction, bytes.fromhex(raw), time) for name, direction, raw, time in [
        ('SMSG_AURA_UPDATE', 'from_native', '01020000000000', 2334.),
        ('SMSG_LOGOUT_COMPLETE', 'from_native', '', 2334.001), ('SMSG_LOGOUT_COMPLETE', 'to_client', '00', 2334.002)])
    late_events = [metadata(row) for row in late]
    late_events.extend([dict(event='modern_packet', session=SESSION, name='CMSG_CHAT_MESSAGE_AFK',
        direction='from_client', bytes=5, time=2305.011), dict(event='native_packet', session=SESSION,
        name='CMSG_MESSAGECHAT_AFK', direction='to_native', bytes=5, time=2305.012)])
    late_events.sort(key=lambda row: row['time'])
    rows += late
    events += late_events
    physical_close = dict(event='world_connection_closed', session=PHYSICAL,
        error='Operation canceled [system:125 at synthetic]', time=2334.003)
    events += [physical_close]
    lobby_raw, lobby_events = lobby_fixture(physical_close['time'])
    rows += lobby_raw
    events += lobby_events
    events += [dict(event='world_connection_closed', session=SESSION, error='End of file [asio.misc:2 at synthetic]', time=2601.1),
        dict(event='native_stream_closed', session=SESSION, error='Operation canceled [system:125 at synthetic]', time=2601.2)]
    events = [dict(event='client_variant', session='pre-ready-variant', time=1970.,
        status=dict(build=None, clientArch=7878196, platformType=5728622, type=5730135)),
        dict(event='world_authenticated', session=SESSION, account_id=2, time=1975.)] + events
    after = deepcopy(baseline)
    after['2']['native'].update(logout_time=2334, totaltime=300, leveltime=300)
    exact = {**{key: after['2']['native'][key] for key in ('guid', 'account', 'name', 'class', 'level',
        'xp', 'online', 'rest_bonus', 'logout_time', 'is_logout_resting')}, 'exact_rest_bonus': 53.,
        'exact_rest_bonus_float32_bits': preservation.float32_bits(53.)}
    stop = {**deepcopy(common), 'schema': 'client442_laya_interactions_v1', 'phase': 'bags_swap_failed_entry_closed_paused',
        'controller': 'code_diagnostic_ordinary_inputs', 'bag_input_sent': False, 'stop_attempted': True,
        'recovery_only': True, 'failed_whole_excluded': True, 'shutdown_checks': dict.fromkeys(CHECKS, True),
        'started_at': 2600., 'stop_started_at': 2601., 'stop_finished_at': 2602., 'finished_at': 2602.1,
        'before': deepcopy(after), 'after': deepcopy(after), 'all_offline_snapshot': deepcopy(after),
        'exact_precision_before': deepcopy(exact), 'exact_precision_after': deepcopy(exact),
        'game_before': dict(pid=999, start_ticks='1234'), 'preparation_source': failed['preparation_source'],
        'first_failure_source': reference(root, 'failed'), 'source': reference(root, 'logout'),
        'frame': {'monitor': {'second_monitor_verified': True, 'monitor': {'name': 'HDMI-1'}}}}
    return rows, events, ready, failed, stop


def lobby_fixture(since):
    raw, events = [], []
    def event(name, direction, size, time, kind='modern_packet'):
        value = dict(event=kind, session=SESSION, name=name, bytes=size, time=time)
        if direction is not None: value['direction'] = direction
        events.append(value)
        return value
    def retained(name, direction, body, time, kind='modern_packet'):
        event(name, direction, len(body), time - .0001, kind)
        raw.append(wire(name, direction, body, time))
    for index, (name, size) in enumerate([('CMSG_REPORT_CLIENT_VARIABLES', 946), ('CMSG_REPORT_ENABLED_ADDONS', 65),
        ('CMSG_REPORT_KEYBINDING_EXECUTION_COUNTS', 21), ('CMSG_BATTLE_PAY_GET_PURCHASE_LIST', 0),
        ('CMSG_BATTLE_PAY_GET_PRODUCT_LIST', 0), ('CMSG_UPDATE_VAS_PURCHASE_STATES', 0)]):
        time = since + .1 + index * .01
        event(name, 'from_client', size, time)
        event(name, None, size, time + .001, 'unmapped_client_packet')
    event('CMSG_GET_UNDELETE_CHARACTER_COOLDOWN_STATUS', 'from_client', 0, since + .2)
    event('SMSG_UNDELETE_COOLDOWN_STATUS_RESPONSE', 'to_client', 9, since + .201)
    retained('CMSG_SOCIAL_CONTRACT_REQUEST', 'from_client', b'', since + .22)
    retained('SMSG_SOCIAL_CONTRACT_REQUEST_RESPONSE', 'to_client', b'\0', since + .221)
    for offset in (.24, .44):
        retained('CMSG_SERVER_TIME_OFFSET_REQUEST', 'from_client', b'', since + offset)
        event('SMSG_SERVER_TIME_OFFSET', 'to_client', 8, since + offset + .001)
    for index, (name, direction, body, kind) in enumerate([
        ('CMSG_ENUM_CHARACTERS', 'from_client', b'', 'modern_packet'),
        ('CMSG_ENUM_CHARACTERS', 'to_native', b'', 'native_packet'),
        ('SMSG_ENUM_CHARACTERS_RESULT', 'from_native', bytes(1366), 'native_packet'),
        ('SMSG_ENUM_CHARACTERS_RESULT', 'to_client', bytes(2944), 'modern_packet')]):
        retained(name, direction, body, since + .3 + index * .001, kind)
    for index in range(8):
        time = since + .5 + index * 30
        for offset, (name, direction, size, kind) in enumerate([
            ('CMSG_PING', 'from_client', 8, 'modern_packet'), ('SMSG_PONG', 'to_client', 4, 'modern_packet'),
            ('CMSG_PING', 'to_native', 8, 'native_packet'), ('SMSG_PONG', 'from_native', 4, 'native_packet')]):
            event(name, direction, size, time + offset * .001, kind)
    raw.sort(key=lambda row: row['time'])
    events.sort(key=lambda row: row['time'])
    assert len(raw) == 8 and len(events) == 56
    return raw, events


def test_entire_synthetic_history_preserves_original_failure_and_excludes_all_operations(tmp_path):
    values = fixture(tmp_path)
    original = deepcopy(values)
    proof = closed.closed_history(*values)
    assert values == original
    assert proof['operations_admitted'] == 0 and proof['qualification_excluded'] is True
    assert proof['normal_logout_observed'] is True and proof['missing_close_event_invented'] is False
    assert proof['normal_logout']['modern']['body'] == '00'
    assert proof['normal_logout']['observed_aura_clear']['excluded_lifecycle_only'] is True
    assert proof['lobby']['latency_occurrences'] == 8
    assert proof['lobby']['source_packet_count'] == 8 and proof['lobby']['source_event_count'] == 56
    assert proof['native_original']['pose']['stand'] == 0 and proof['native_final']['pose']['stand'] == 1
    assert proof['native_final']['afk'] is True


@pytest.mark.parametrize('fault', ['reordered_prefix', 'logout_body', 'missing_idle', 'bag_input', 'extra_gameplay',
    'float_bits', 'stop_check', 'reordered_updates', 'reordered_ping', 'missing_close', 'extra_auth',
    'extra_owner_aura', 'missing_aura_clear', 'early_logout_complete', 'extra_game_ticks', 'protected_peer',
    'extra_item', 'wrong_monitor'])
def test_current_failed_history_rejects_changes_or_missing_actual_effects(tmp_path, fault):
    values = list(fixture(tmp_path))
    packets, events, ready, failed, stop = values
    if fault == 'reordered_prefix': packets[0], packets[1] = packets[1], packets[0]
    elif fault == 'logout_body': next(row for row in packets if (row['name'], row['direction']) == ('CMSG_LOGOUT_REQUEST', 'from_client'))['body'] = '80'
    elif fault == 'missing_idle': packets[:] = [row for row in packets if row['name'] != 'CMSG_STAND_STATE_CHANGE']
    elif fault in ('bag_input', 'extra_gameplay'):
        packets.append(wire(contract.ACTION if fault == 'bag_input' else 'CMSG_ATTACKSWING', 'from_client', b'\0', 2400.))
    elif fault == 'float_bits': stop['exact_precision_after']['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'stop_check': stop['shutdown_checks']['owned_game_absent'] = False
    elif fault == 'reordered_updates':
        indices = [index for index, row in enumerate(packets) if row['name'] == 'SMSG_UPDATE_OBJECT' and row['time'] > failed['finished_at']]
        packets[indices[0]], packets[indices[1]] = packets[indices[1]], packets[indices[0]]
    elif fault == 'reordered_ping':
        indices = [index for index, row in enumerate(events) if row.get('name') in ('CMSG_PING', 'SMSG_PONG')]
        events[indices[0]], events[indices[1]] = events[indices[1]], events[indices[0]]
    elif fault == 'missing_close': events.pop()
    elif fault == 'extra_auth': events.append(dict(event='instance_authenticated', session='other', account_id=2, time=2500.))
    elif fault == 'extra_owner_aura': packets.append(wire('SMSG_AURA_UPDATE', 'from_native', bytes.fromhex('01020000000000'), 2314.5))
    elif fault == 'missing_aura_clear': packets[:] = [row for row in packets if row['name'] != 'SMSG_AURA_UPDATE']
    elif fault == 'early_logout_complete': next(row for row in packets if (row['name'], row['direction']) == ('SMSG_LOGOUT_COMPLETE', 'from_native'))['time'] = 2314.5
    elif fault == 'extra_game_ticks': stop['game_before']['invented_current_start_ticks'] = '999'
    elif fault == 'protected_peer': stop['after']['6']['pets'][0]['curhealth'] += 1
    elif fault == 'extra_item': packets.append(dict(native_packet(item_fields(contract.SOURCE), guid=contract.SOURCE['guid'] + 1, kind=1, time=2310.), session=SESSION))
    elif fault == 'wrong_monitor': stop['frame']['monitor']['monitor']['name'] = 'DP-1'
    with pytest.raises(RuntimeError): closed.closed_history(*values)


def test_callback_requires_exact_v2_schema_before_any_authority_claim(tmp_path):
    class Unsupported:
        SCHEMA = 'invented_classifier'
    with pytest.raises(RuntimeError, match='v2 initializer'):
        closed.closed_history(*fixture(tmp_path), login_provider=Unsupported())


@pytest.mark.parametrize('event', ['native_active_mover_confirmed', 'active_mover_deferred_until_player_create'])
@pytest.mark.parametrize('owner', [SESSION, PHYSICAL])
@pytest.mark.parametrize('raw_guard', [False, True])
def test_boot_allowance_filter_keeps_the_complete_mover_lifecycle_guard(tmp_path, event, owner, raw_guard):
    packets, events, ready, failed, stop = fixture(tmp_path)
    pose = [failed['native_before_entry'][name] for name in ('position_x', 'position_y', 'position_z', 'orientation')]
    boot = sync.login_sync(failed['raw_entry_packets'], failed['raw_entry_events'], SESSION,
        failed['started_at'], failed['entry_input_finished_at'], pose)
    context = deepcopy(failed['raw_entry_events'])
    rows = failed['raw_entry_packets'] if raw_guard else context
    assert closed._guard(rows, owner, 2000., 2400., login_sync=boot, events=context, provider=sync)['no_forbidden_input']
    context.append(dict(event=event, session=owner, guid=2, time=2315.))
    with pytest.raises(RuntimeError, match='exact v2 startup allowance'):
        closed._guard(rows, owner, 2000., 2400., login_sync=boot, events=context, provider=sync)


@pytest.mark.parametrize('event', ['native_active_mover_confirmed', 'active_mover_deferred_until_player_create',
    'native_player_resurrected', 'unrecognized_owner_native_effect'])
@pytest.mark.parametrize('owner', [SESSION, PHYSICAL])
def test_entire_history_rejects_an_extra_owner_lifecycle_even_without_gameplay_input(tmp_path, event, owner):
    values = list(fixture(tmp_path))
    values[1].append(dict(event=event, session=owner, guid=2, time=2315.))
    values[1].sort(key=lambda row: row['time'])
    with pytest.raises(RuntimeError, match='lifecycle or unknown native effect'):
        closed.closed_history(*values)


@pytest.mark.parametrize('delivered', [False, True])
def test_valid_spell_learning_body_and_exact_metadata_are_still_a_forbidden_extra_effect(tmp_path, delivered):
    values = list(fixture(tmp_path))
    if delivered:
        raw = Writer().pack('2I', 1, 0).bits(0, 1).flush().pack('i', 1462).bits(0, 4).flush().finish()
        packet = wire('SMSG_LEARNED_SPELLS', 'to_client', raw, 2315.)
    else:
        # Protocol::initialize_response accepts this exact uint32 spell/zero
        # native layout. A full saved snapshot cannot erase an intervening learn.
        packet = wire('SMSG_LEARNED_SPELL', 'from_native', struct.pack('<2I', 1462, 0), 2315.)
    values[0].append(packet)
    values[0].sort(key=lambda row: row['time'])
    values[1].append(metadata(packet))
    values[1].sort(key=lambda row: row['time'])
    with pytest.raises(RuntimeError, match='spell-learning or unsupported native cast'):
        closed.closed_history(*values)


@pytest.mark.parametrize('name', ['SMSG_SPELL_START', 'SMSG_SPELL_GO', 'SMSG_ATTACKER_STATE_UPDATE',
    'SMSG_AURA_UPDATE', 'SMSG_AURA_UPDATE_ALL'])
@pytest.mark.parametrize('path', ['native_realm', 'modern_realm', 'modern_physical'])
def test_orphan_sensitive_effect_metadata_cannot_replace_its_missing_raw_body(tmp_path, name, path):
    values = list(fixture(tmp_path))
    values[1].append(dict(event='native_packet' if path == 'native_realm' else 'modern_packet',
        session=PHYSICAL if path == 'modern_physical' else SESSION, name=name,
        direction='from_native' if path == 'native_realm' else 'to_client', bytes=31, time=2315.))
    values[1].sort(key=lambda row: row['time'])
    with pytest.raises(RuntimeError, match='omit its raw body occurrence'):
        closed.closed_history(*values)


def native_guid_body(guid):
    octets = struct.pack('<Q', guid)
    return bytes([sum(bool(octet) << index for index, octet in enumerate(octets))]) + bytes(octet for octet in octets if octet)


def native_spell_go(caster, target=None):
    raw = native_guid_body(caster) * 2 + struct.pack('<Bi3I', 1, 133, 0, 0, 0) + b'\0\0'
    return raw + struct.pack('<I', 2 if target is not None else 0) + (native_guid_body(target) if target is not None else b'')


def test_body_bound_native_npc_cast_is_parsed_and_excluded_without_admitting_an_owner_cast(tmp_path):
    values = list(fixture(tmp_path))
    npc = 0xf130000001000001
    packet = wire('SMSG_SPELL_GO', 'from_native', native_spell_go(npc), 2315.)
    values[0].append(packet)
    values[0].sort(key=lambda row: row['time'])
    values[1].append(metadata(packet))
    values[1].sort(key=lambda row: row['time'])
    proof = closed.closed_history(*values)
    assert proof['operations_admitted'] == 0
    assert proof['native_effect_guard']['all_captured_sensitive_effect_bodies_reconciled'] is True
    assert proof['native_effect_guard']['no_additional_delivered_owner_cast'] is True


@pytest.mark.parametrize('owner_role', ['caster', 'target'])
def test_valid_native_cast_body_with_owner_participation_cannot_be_an_npc_exclusion(tmp_path, owner_role):
    values = list(fixture(tmp_path))
    raw = native_spell_go(2) if owner_role == 'caster' else native_spell_go(0xf130000001000001, 2)
    packet = wire('SMSG_SPELL_GO', 'from_native', raw, 2315.)
    values[0].append(packet)
    values[0].sort(key=lambda row: row['time'])
    values[1].append(metadata(packet))
    values[1].sort(key=lambda row: row['time'])
    with pytest.raises(RuntimeError, match='combat or aura involved the owner'):
        closed.closed_history(*values)


@pytest.mark.parametrize('owner', [SESSION, PHYSICAL])
def test_complete_canonical_delivered_logout_aura_clear_preserves_the_observed_native_effect(tmp_path, owner):
    values = list(fixture(tmp_path))
    raw = Writer().bits(0, 1).bits(1, 9).flush().pack('B', 0).bits(0, 1).flush().guid(2, player_high()).finish()
    packet = wire('SMSG_AURA_UPDATE', 'to_client', raw, 2334.0005)
    values[0].append(packet)
    values[0].sort(key=lambda row: row['time'])
    event = metadata(packet)
    event['session'] = owner
    values[1].append(event)
    values[1].sort(key=lambda row: row['time'])
    proof = closed.closed_history(*values)
    assert proof['native_effect_guard']['delivered_logout_aura_clear_count'] == 1
    assert proof['normal_logout']['observed_aura_clear']['excluded_lifecycle_only'] is True


@pytest.mark.parametrize('fault', ['extra_slot', 'another_actor', 'wrong_time', 'missing_native', 'duplicate'])
def test_delivered_aura_requires_the_sole_canonical_native_logout_clear(tmp_path, fault):
    values = list(fixture(tmp_path))
    raw = Writer().bits(0, 1).bits(1, 9).flush().pack('B', 1 if fault == 'extra_slot' else 0).bits(0, 1).flush().guid(
        3 if fault == 'another_actor' else 2, player_high()).finish()
    packet = wire('SMSG_AURA_UPDATE', 'to_client', raw, 2315. if fault == 'wrong_time' else 2334.0005)
    values[0].append(packet)
    values[1].append(metadata(packet))
    if fault == 'missing_native':
        values[0][:] = [row for row in values[0] if not (row['name'] == 'SMSG_AURA_UPDATE' and row['direction'] == 'from_native')]
        values[1][:] = [row for row in values[1] if not (row.get('name') == 'SMSG_AURA_UPDATE' and row.get('direction') == 'from_native')]
    if fault == 'duplicate':
        other = dict(packet, time=2334.0006)
        values[0].append(other)
        values[1].append(metadata(other))
    values[0].sort(key=lambda row: row['time'])
    values[1].sort(key=lambda row: row['time'])
    with pytest.raises(RuntimeError, match='slot-zero clear translation'):
        closed.closed_history(*values)


@pytest.mark.parametrize('name,size', [
    ('SMSG_UPDATE_OBJECT', 13), ('SMSG_DESTROY_OBJECT', 9), ('SMSG_STAND_STATE_UPDATE', 1),
    ('SMSG_ON_MONSTER_MOVE', 35), ('SMSG_ON_MONSTER_MOVE_TRANSPORT', 35),
    ('SMSG_MOVE_ROOT', 6), ('SMSG_MOVE_UNROOT', 6), ('SMSG_MOVE_SET_ACTIVE_MOVER', 2),
    ('SMSG_SPLINE_MOVE_SET_RUN_SPEED', 6), ('MSG_MOVE_SET_RUN_SPEED', 10)])
@pytest.mark.parametrize('path', ['native_realm', 'modern_realm', 'modern_physical'])
def test_object_stand_and_server_movement_metadata_require_each_actual_raw_occurrence(tmp_path, name, size, path):
    values = list(fixture(tmp_path))
    event = dict(event='native_packet' if path == 'native_realm' else 'modern_packet',
        session=PHYSICAL if path == 'modern_physical' else SESSION, name=name,
        direction='from_native' if path == 'native_realm' else 'to_client', bytes=size, time=2315.)
    if name == 'SMSG_STAND_STATE_UPDATE' and path != 'native_realm': event['bytes'] = 5
    values[1].append(event)
    values[1].sort(key=lambda row: row['time'])
    # Existing object, stand or root packets cannot cover a second metadata
    # occurrence. New movement names also need a retained body before parsing.
    with pytest.raises(RuntimeError): closed.closed_history(*values)


def append_packet(values, packet, *, delivered_owner=None):
    values[0].append(packet)
    event = metadata(packet)
    if delivered_owner is not None: event['session'] = delivered_owner
    values[1].append(event)
    for rows in values[:2]: rows.sort(key=lambda row: row['time'])


def native_attack(name, attacker, victim, *, dead=0):
    if name == 'SMSG_ATTACK_START': return struct.pack('<QQ', attacker, victim)
    assert name == 'SMSG_ATTACK_STOP'
    return native_guid_body(attacker) + native_guid_body(victim) + struct.pack('<I', dead)


NPC_ATTACKER, NPC_VICTIM = 0xf130000001000001, 0xf130000002000002


@pytest.mark.parametrize('name', ['SMSG_ATTACK_START', 'SMSG_ATTACK_STOP'])
@pytest.mark.parametrize('role', ['attacker', 'victim'])
@pytest.mark.parametrize('owned_guid', [2, contract.SOURCE['guid'], contract.DESTINATION['guid']])
def test_native_attack_control_cannot_attribute_owner_or_inventory_as_an_npc(tmp_path, name, role, owned_guid):
    values = list(fixture(tmp_path))
    attacker, victim = (owned_guid, NPC_VICTIM) if role == 'attacker' else (NPC_ATTACKER, owned_guid)
    append_packet(values, wire(name, 'from_native', native_attack(name, attacker, victim), 2315.))
    with pytest.raises(RuntimeError): closed.closed_history(*values)


@pytest.mark.parametrize('name,dead', [('SMSG_ATTACK_START', 0), ('SMSG_ATTACK_STOP', 0), ('SMSG_ATTACK_STOP', 1)])
def test_complete_native_npc_attack_controls_preserve_the_excluded_owner_and_items(tmp_path, name, dead):
    values = list(fixture(tmp_path))
    append_packet(values, wire(name, 'from_native', native_attack(name, NPC_ATTACKER, NPC_VICTIM, dead=dead), 2315.))
    original = deepcopy(values)
    proof = closed.closed_history(*values)
    assert values == original
    assert proof['operations_admitted'] == 0 and proof['qualification_excluded'] is True
    assert proof['normal_logout_observed'] is True
    assert proof['all_native_item_fields_unchanged'] is True
    assert proof['all_native_inventory_slots_unchanged'] is True
    assert proof['native_effect_guard']['all_captured_sensitive_effect_bodies_reconciled'] is True


@pytest.mark.parametrize('name', ['SMSG_ATTACK_START', 'SMSG_ATTACK_STOP'])
@pytest.mark.parametrize('fault', ['empty', 'truncated', 'trailing', 'malformed_guid'])
def test_native_attack_control_rejects_malformed_or_unconsumed_bodies(tmp_path, name, fault):
    values = list(fixture(tmp_path))
    raw = native_attack(name, NPC_ATTACKER, NPC_VICTIM)
    if fault == 'empty': raw = b''
    elif fault == 'truncated': raw = raw[:-1]
    elif fault == 'trailing': raw += b'\0'
    else:
        # START requires two complete uncompressed uint64s; STOP starts with
        # the full packed mask plus every declared GUID byte.
        raw = raw[:7] if name == 'SMSG_ATTACK_START' else b'\xff\x01'
    append_packet(values, wire(name, 'from_native', raw, 2315.))
    with pytest.raises(RuntimeError): closed.closed_history(*values)


def test_native_attack_stop_requires_the_typed_zero_or_one_death_flag(tmp_path):
    values = list(fixture(tmp_path))
    append_packet(values, wire('SMSG_ATTACK_STOP', 'from_native',
        native_attack('SMSG_ATTACK_STOP', NPC_ATTACKER, NPC_VICTIM, dead=2), 2315.))
    with pytest.raises(RuntimeError): closed.closed_history(*values)


def native_melee_result(attacker, victim):
    # Fully supported normal swing: zero damage/no subdamage, no overkill,
    # one ordinary victim state, no spell/state extension or rage field.
    return struct.pack('<I', 2) + native_guid_body(attacker) + native_guid_body(victim) + \
        struct.pack('<iiBBII', 0, -1, 0, 1, 0, 0)


@pytest.mark.parametrize('name', ['SMSG_ATTACK_START', 'SMSG_ATTACK_STOP', 'SMSG_ATTACKER_STATE_UPDATE'])
@pytest.mark.parametrize('owner', [SESSION, PHYSICAL])
@pytest.mark.parametrize('native_counterpart', [False, True])
def test_late_delivered_melee_has_no_allowance_even_with_a_complete_valid_body(tmp_path, name, owner, native_counterpart):
    values = list(fixture(tmp_path))
    if name == 'SMSG_ATTACKER_STATE_UPDATE':
        native = native_melee_result(NPC_ATTACKER, NPC_VICTIM)
        result = melee_result_evidence.translated(native, 0)
        assert (result['attacker'], result['victim'], result['damage']) == (NPC_ATTACKER, NPC_VICTIM, 0)
        delivered = bytes.fromhex(result['body'])
    else:
        native = native_attack(name, NPC_ATTACKER, NPC_VICTIM)
        result = combat.response(SimpleNamespace(character={'guid': 2, 'map': 0}), name, native)
        assert result[0] == name and result[1]
        delivered = result[1]
    assert delivered
    if native_counterpart: append_packet(values, wire(name, 'from_native', native, 2315.))
    append_packet(values, wire(name, 'to_client', delivered, 2315.001), delivered_owner=owner)
    with pytest.raises(RuntimeError): closed.closed_history(*values)


@pytest.mark.parametrize('name', ['SMSG_ATTACK_START', 'SMSG_ATTACK_STOP', 'SMSG_ATTACKER_STATE_UPDATE'])
def test_empty_delivered_melee_body_is_also_refused(tmp_path, name):
    values = list(fixture(tmp_path))
    append_packet(values, wire(name, 'to_client', b'', 2315.))
    with pytest.raises(RuntimeError): closed.closed_history(*values)


SPLINE_NPC_56 = (0xf13 << 52) | (1 << 32) | 0x101
SPLINE_NPC_57 = (0xf13 << 52) | (0x101 << 32) | 0x101
SPLINE_WANTED = {2, contract.SOURCE['guid'], contract.DESTINATION['guid']}


def spline_fixture(*, count=1, identity=SPLINE_NPC_56, map_id=0):
    """Supply only the identities this helper reads from already-bound RAW.

    The closure separately reconciles the complete retained body occurrences
    with metadata. This helper never claims the position body was saved.
    """
    packets, events = [], []
    target = modern_guid(identity, map_id)
    width = len(Writer().guid(*target).finish()) + 49
    for index in range(count):
        time = 3000. + index
        packets.append(wire('SMSG_ON_MONSTER_MOVE', 'from_native', native_guid_body(identity) + bytes(4), time))
        packets.append(wire('SMSG_ON_MONSTER_MOVE', 'to_client', Writer().guid(*target).raw(bytes(17)).finish(), time + .02))
        events.append(dict(event='modern_packet', session=PHYSICAL, name='SMSG_MOVE_UPDATE',
            direction='to_client', bytes=width, time=time + .01))
    return packets, events


def spline_proof(packets, events, *, map_id=0):
    return closed._spline_updates(packets, events, SESSION, PHYSICAL, SPLINE_WANTED, map_id)


@pytest.mark.parametrize('identity,expected_width', [(SPLINE_NPC_56, 56), (SPLINE_NPC_57, 57)])
def test_metadata_only_position_update_binds_exact_npc_pair_and_honest_byte_omission(identity, expected_width):
    values = spline_fixture(identity=identity)
    original = deepcopy(values)
    assert values[1][0]['bytes'] == expected_width
    proof = spline_proof(*values)
    assert values == original
    assert proof == {'metadata_only_delivered_position_update_count': 1,
        'delivered_position_update_bodies_retained': False,
        'delivered_position_updates_bound_to_retained_npc_splines': True}


def test_metadata_only_position_update_translation_uses_the_actual_map():
    values = spline_fixture(map_id=530)
    assert spline_proof(*values, map_id=530)['metadata_only_delivered_position_update_count'] == 1
    with pytest.raises(RuntimeError): spline_proof(*values, map_id=0)


@pytest.mark.parametrize('fault', ['orphan', 'missing_native', 'missing_delivered', 'missing_metadata',
    'duplicate_native', 'duplicate_delivered', 'duplicate_metadata', 'duplicate_complete_pair',
    'reordered_native', 'reordered_delivered', 'reordered_metadata', 'reordered_complete_pairs'])
def test_metadata_only_position_update_requires_complete_unique_observed_stream_pairs(fault):
    packets, events = spline_fixture(count=2)
    if fault == 'orphan': packets.clear()
    elif fault == 'missing_native': packets.pop(0)
    elif fault == 'missing_delivered': packets.pop(1)
    elif fault == 'missing_metadata': events.pop(0)
    elif fault == 'duplicate_native': packets.insert(0, deepcopy(packets[0]))
    elif fault == 'duplicate_delivered': packets.insert(1, deepcopy(packets[1]))
    elif fault == 'duplicate_metadata': events.insert(0, deepcopy(events[0]))
    elif fault == 'duplicate_complete_pair':
        packets[:0] = deepcopy(packets[:2])
        events.insert(0, deepcopy(events[0]))
    elif fault == 'reordered_native': packets[0], packets[2] = packets[2], packets[0]
    elif fault == 'reordered_delivered': packets[1], packets[3] = packets[3], packets[1]
    elif fault == 'reordered_metadata': events.reverse()
    else:
        packets[:] = packets[2:] + packets[:2]
        events.reverse()
    with pytest.raises(RuntimeError): spline_proof(packets, events)


@pytest.mark.parametrize('identity', [2, contract.SOURCE['guid'], contract.DESTINATION['guid'], 3])
def test_metadata_only_position_update_refuses_owner_inventory_and_other_player_identities(identity):
    packets, events = spline_fixture()
    packets[0]['body'] = (native_guid_body(identity) + bytes(4)).hex()
    with pytest.raises(RuntimeError): spline_proof(packets, events)


@pytest.mark.parametrize('fault', ['another_npc', 'other_player', 'foreign_native_owner', 'foreign_delivered_owner',
    'foreign_metadata_owner', 'realm_metadata_owner', 'wrong_size', 'bool_size', 'float_size', 'string_size',
    'wrong_kind', 'wrong_direction', 'missing_field', 'extra_field', 'same_as_native', 'same_as_delivered',
    'before_native', 'after_delivered', 'late_delivered', 'nan_time', 'infinite_time'])
def test_metadata_only_position_update_requires_exact_owner_shape_size_and_causal_time(fault):
    packets, events = spline_fixture()
    native, delivered, event = packets[0], packets[1], events[0]
    if fault in ('another_npc', 'other_player'):
        target = modern_guid(SPLINE_NPC_57 if fault == 'another_npc' else 3, 0)
        delivered['body'] = Writer().guid(*target).raw(bytes(17)).finish().hex()
    elif fault == 'foreign_native_owner': native['session'] = 'foreign-native'
    elif fault == 'foreign_delivered_owner': delivered['session'] = 'foreign-native'
    elif fault == 'foreign_metadata_owner': event['session'] = 'foreign-instance'
    elif fault == 'realm_metadata_owner': event['session'] = SESSION
    elif fault == 'wrong_size': event['bytes'] += 1
    elif fault == 'bool_size': event['bytes'] = True
    elif fault == 'float_size': event['bytes'] = float(event['bytes'])
    elif fault == 'string_size': event['bytes'] = str(event['bytes'])
    elif fault == 'wrong_kind': event['event'] = 'native_packet'
    elif fault == 'wrong_direction': event['direction'] = 'from_native'
    elif fault == 'missing_field': event.pop('bytes')
    elif fault == 'extra_field': event['guid'] = 2
    elif fault == 'same_as_native': event['time'] = native['time']
    elif fault == 'same_as_delivered': event['time'] = delivered['time']
    elif fault == 'before_native': event['time'] = native['time'] - .001
    elif fault == 'after_delivered': event['time'] = delivered['time'] + .001
    elif fault == 'late_delivered': delivered['time'] = native['time'] + .1
    elif fault == 'nan_time': event['time'] = float('nan')
    else: event['time'] = float('inf')
    with pytest.raises(RuntimeError): spline_proof(packets, events)


def finalization_fixture(root):
    """A successful retained first proof with an immutable failed final lookup."""
    values = list(fixture(root))
    packets, events, ready, failed, stop = values
    prefix = deepcopy(failed['raw_entry_packets'])
    boot = sync.login_sync(prefix, failed['raw_entry_events'], SESSION,
        failed['started_at'], 2001.5, [failed['native_before_entry'][name] for name in
            ('position_x', 'position_y', 'position_z', 'orientation')])
    owner = contract.native_replay(prefix, SESSION, failed['started_at'], boot['until'],
        login_sync=boot, events=failed['raw_entry_events'])
    failed.update(phase='bags_swap_entered', raw_entry_packets=[], login_sync=boot,
        failure='RuntimeError: one complete owned modern/native login chain is required',
        entry_finalization_failure='RuntimeError: one complete owned modern/native login chain is required',
        login_packets=deepcopy(boot['login_packets']), native_owner_proof=owner,
        owner_packets=deepcopy(owner['packets']),
        checks=dict.fromkeys(('ordinary_login', 'native_owner', 'saved_baseline',
            'protected_actors', 'public_level1', 'empty_cursor'), True))
    packets[:] = [row for row in packets if not 2304 <= row['time'] < 2306]
    events[:] = [row for row in events if not 2304 <= row['time'] < 2306]
    owner_index = next(i for i, row in enumerate(packets) if row['name'] == 'SMSG_UPDATE_OBJECT' and
        row['time'] == 2314.04)
    replacement = dict(native_packet({53: 8 | 0x40000, 68: 1}, creation=False, time=2314.04), session=SESSION)
    old_metadata = metadata(packets[owner_index])
    packets[owner_index] = replacement
    events[events.index(old_metadata)] = metadata(replacement)
    for direction, raw, time in [('from_native', b'\x01', 2314.024),
            ('to_client', b'\x01\0\0\0\0', 2314.026)]:
        row = wire('SMSG_STAND_STATE_UPDATE', direction, raw, time)
        packets.append(row); events.append(metadata(row))
    physical_close = next(e for e in events if e['event'] == 'world_connection_closed' and
        e['session'] == PHYSICAL)
    remove_names = ('CMSG_SERVER_TIME_OFFSET_REQUEST', 'SMSG_SERVER_TIME_OFFSET')
    packets[:] = [row for row in packets if not (row['time'] > physical_close['time'] and
        row['name'] in remove_names)]
    events[:] = [row for row in events if not (row['time'] > physical_close['time'] and
        (row.get('name') in remove_names or row.get('name') in ('CMSG_PING', 'SMSG_PONG') and
            row['time'] >= physical_close['time'] + 1))]
    packets.sort(key=lambda row: row['time']); events.sort(key=lambda row: row['time'])
    return values


def finalization_proof(values):
    return closed.closed_history(*values, provenance_profile='ui178_finalization')


def test_finalization_exclusion_rederives_real_journal_without_relabeling_or_repairing_failure(tmp_path):
    values = finalization_fixture(tmp_path)
    original = deepcopy(values)
    proof = finalization_proof(values)
    assert values == original
    assert values[3]['raw_entry_packets'] == [] and values[3]['completed'] is False
    assert proof['original_raw_entry_packets_preserved_empty'] is True
    assert proof['original_phase_preserved'] == 'bags_swap_entered'
    assert proof['original_finalization_failure_preserved'] == values[3]['failure']
    assert proof['journal_prefix_rederived'] is True
    assert proof['qualification_excluded'] is True and proof['operations_admitted'] == 0
    assert proof['automatic_idle'] is None and proof['native_final']['afk'] is False
    assert proof['native_final']['pose']['stand'] == 1
    assert proof['lobby']['source_packet_count'] == 6 and proof['lobby']['source_event_count'] == 24
    assert proof['lobby']['latency_occurrences'] == proof['lobby']['character_list_occurrences'] == 1
    assert len(proof['normal_logout']['server_sit_packets']) == 2
    with pytest.raises(RuntimeError): closed.closed_history(*values)


@pytest.mark.parametrize('fault', ['raw_repaired', 'metadata_missing', 'metadata_reordered', 'first_proof_body',
    'login_body', 'owner_proof', 'owner_packets', 'check_false', 'check_integer', 'check_missing',
    'failure_changed', 'failure_missing', 'phase_changed', 'marked_completed', 'missing_server_sit',
    'duplicate_server_sit', 'client_sit', 'afk_input', 'extra_owner_change', 'extra_item', 'extra_movement',
    'extra_cast', 'missing_login_raw', 'missing_boot_raw', 'lobby_ping_missing', 'lobby_extra_latency',
    'stop_check_false', 'exact_float_changed', 'gap_owner_change', 'gap_spell_learning'])
def test_finalization_profile_requires_original_sources_and_exact_observed_no_idle_logout(tmp_path, fault):
    values = finalization_fixture(tmp_path)
    packets, events, ready, failed, stop = values
    if fault == 'raw_repaired': failed['raw_entry_packets'] = deepcopy(packets[:1])
    elif fault == 'metadata_missing': failed['raw_entry_events'].pop()
    elif fault == 'metadata_reordered': failed['raw_entry_events'].reverse()
    elif fault == 'first_proof_body': failed['login_sync']['source_packets'][0]['body'] = '00'
    elif fault == 'login_body': failed['login_packets'][0]['body'] = '00'
    elif fault == 'owner_proof': failed['native_owner_proof']['rest_threshold'] += 1
    elif fault == 'owner_packets': failed['owner_packets'][0]['body'] = '00'
    elif fault.startswith('check_'):
        if fault == 'check_missing': failed['checks'].pop('empty_cursor')
        else: failed['checks']['empty_cursor'] = False if fault == 'check_false' else 1
    elif fault == 'failure_changed': failed['failure'] += ' changed'
    elif fault == 'failure_missing': failed.pop('entry_finalization_failure')
    elif fault == 'phase_changed': failed['phase'] = 'bags_swap_entry_started'
    elif fault == 'marked_completed': failed['completed'] = True
    elif fault == 'missing_server_sit':
        packets[:] = [r for r in packets if not (r['name'] == 'SMSG_STAND_STATE_UPDATE' and
            r['direction'] == 'from_native')]
    elif fault == 'duplicate_server_sit':
        row = deepcopy(next(r for r in packets if r['name'] == 'SMSG_STAND_STATE_UPDATE'))
        row['time'] += .0005; append_packet(values, row)
    elif fault == 'client_sit': append_packet(values, wire('CMSG_STAND_STATE_CHANGE', 'from_client', b'\1', 2314.025))
    elif fault == 'afk_input':
        events.append(dict(event='modern_packet', session=SESSION, name='CMSG_CHAT_MESSAGE_AFK',
            direction='from_client', bytes=5, time=2314.025))
        events.sort(key=lambda r: r['time'])
    elif fault == 'extra_owner_change':
        append_packet(values, dict(native_packet({61: 123}, creation=False, time=2314.5), session=SESSION))
    elif fault == 'extra_item':
        row = dict(native_packet({3: 999}, guid=(0x4000 << 48) | 44, kind=1, time=2314.5), session=SESSION)
        append_packet(values, row)
    elif fault in ('extra_movement', 'extra_cast'):
        append_packet(values, wire('CMSG_MOVE_HEARTBEAT' if fault == 'extra_movement' else 'CMSG_CAST_SPELL',
            'from_client', b'\0', 2314.5))
    elif fault in ('missing_login_raw', 'missing_boot_raw'):
        name = 'CMSG_PLAYER_LOGIN' if fault == 'missing_login_raw' else sync.INITIALIZE
        packets.pop(next(i for i, r in enumerate(packets) if r['name'] == name and r['direction'] == 'from_client'))
    elif fault == 'lobby_ping_missing':
        events.pop(next(i for i, r in enumerate(events) if r.get('name') == 'SMSG_PONG' and
            r['direction'] == 'from_native' and r['time'] > 2334.003))
    elif fault == 'lobby_extra_latency':
        extra = [deepcopy(r) for r in events if r.get('name') in ('CMSG_PING', 'SMSG_PONG') and
            r['time'] > 2334.003]
        for r in extra: r['time'] += 1
        events.extend(extra); events.sort(key=lambda r:r['time'])
    elif fault in ('gap_owner_change', 'gap_spell_learning'):
        row = (dict(native_packet({61: 123}, creation=False, time=2001.7), session=SESSION) if
            fault == 'gap_owner_change' else wire('SMSG_LEARNED_SPELL', 'from_native', b'\0', 2001.7))
        append_packet(values, row)
        failed['raw_entry_events'] = deepcopy([e for e in events if
            failed['started_at'] <= e['time'] <= failed['entry_input_finished_at']])
    elif fault == 'stop_check_false': stop['shutdown_checks']['owned_game_absent'] = False
    else: stop['exact_precision_after']['exact_rest_bonus_float32_bits'] = '00000000'
    with pytest.raises(RuntimeError): finalization_proof(values)


@pytest.mark.parametrize('profile', [None, '', 'ui178', 'ui178_finalization ', True, 1])
def test_closed_history_profile_cannot_be_implicit_or_an_unknown_mode(tmp_path, profile):
    with pytest.raises(RuntimeError): closed.closed_history(*finalization_fixture(tmp_path), provenance_profile=profile)

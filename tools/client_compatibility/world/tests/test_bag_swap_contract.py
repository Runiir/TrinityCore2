"""Occupied swaps retain both items and reject any additional gameplay input."""
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import sys

import pytest
import json

from tools.client_compatibility import bag_swap_contract as c
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.tests.test_item_actionbar_contract import native_packet, owner_fields


def modern(destination=36, source=35, hints=((255, 35), (255, 36))):
    writer = Writer().bits(len(hints), 2).flush()
    for bag, slot in hints:
        writer.pack('2B', bag, slot)
    return writer.pack('2B', destination, source).finish()


def packets(reverse=False, start=10, hints=((255, 35), (255, 36))):
    destination, source = (35, 36) if reverse else (36, 35)
    actions = [('from_client', modern(destination, source, hints)),
        ('to_native', bytes((c.native_slot(destination), c.native_slot(source))))]
    return [{'session': 'scout', 'time': start + i * .1, 'name': c.ACTION, 'direction': direction, 'body': raw.hex()}
        for i, (direction, raw) in enumerate(actions)]


def inventory():
    return [[2, 0, slot, guid, guid, item, 2, 0, 0, 1, 0, '0 0 0 0 0 ', 1, '', 0, 0, 0, 0, '']
        for guid, item, slot in c.ITEMS]


def resources(swapped=False):
    empty = {'guid': 0, 'id': 0, 'count': 0}
    value = {'money': 1, 'equipment': [deepcopy(empty) for _ in range(19)],
        'backpack': [deepcopy(empty) for _ in range(16)],
        'bags': [[deepcopy(empty) for _ in range(36)] for _ in range(4)]}
    value['backpack'][:2] = deepcopy([c.DESTINATION, c.SOURCE] if swapped else [c.SOURCE, c.DESTINATION])
    return value


def public(swapped=False):
    pair = [c.DESTINATION, c.SOURCE] if swapped else [c.SOURCE, c.DESTINATION]
    return {'bags': [0], 'bag_items': [{'bag': 0, 'slot': slot, 'id': item['id'], 'count': item['count'], 'locked': False}
        for slot, item in enumerate(pair, 1)]}


def slot_fields(swapped=False):
    pair = [c.DESTINATION, c.SOURCE] if swapped else [c.SOURCE, c.DESTINATION]
    start = c.INDEX['PLAYER_FIELD_INV_SLOT_HEAD']
    return {start + slot * 2 + part: item['guid'] >> (32 * part) & 0xffffffff
        for slot, item in zip((23, 24), pair) for part in (0, 1)}


def item_fields(item):
    return {c.INDEX[k]: value for k, value in {'OBJECT_FIELD_ENTRY': item['id'],
        'ITEM_FIELD_STACK_COUNT': 1, 'ITEM_FIELD_OWNER': 2, 'ITEM_FIELD_CONTAINED': 2,
        'ITEM_FIELD_SPELL_CHARGES': 0xffffffff, 'ITEM_FIELD_FLAGS': 1}.items()}


def native_rows(roundtrip=False):
    rows = [native_packet({**owner_fields(), **slot_fields()}, time=9),
        native_packet(item_fields(c.SOURCE), guid=c.SOURCE['guid'], kind=1, time=9.1),
        native_packet(item_fields(c.DESTINATION), guid=c.DESTINATION['guid'], kind=1, time=9.2),
        *packets(), native_packet(slot_fields(True), creation=False, time=10.2)]
    if roundtrip:
        rows += packets(True, 11) + [native_packet(slot_fields(), creation=False, time=11.2)]
    return rows


@pytest.mark.parametrize('hints', [(), ((255, 35),), ((255, 35), (255, 36)), ((255, 35), (30, 2), (255, 36))])
def test_optional_two_bit_hint_count_and_every_position_are_consumed(hints):
    decoded = c.modern_swap(modern(hints=hints))
    assert decoded['hint_count'] == len(hints)
    assert [r['modern'] for r in decoded['hints']] == [list(row) for row in hints]
    proof = c.swap_packets(packets(hints=hints), 'scout', 9, 11)
    assert proof['native']['body'] == '1817'
    assert proof['decoded']['native_destination'] == 24


@pytest.mark.parametrize('raw', [b'', b'\x80\xff\x23', b'\x40\xff\x23\x24',
    b'\x40\xff\x34\x24\x23', b'\x40\x1d\x00\x24\x23', b'\x40\x1e\x24\x24\x23',
    b'\x00\x24\x23\x00', b'\x00\x34\x23'])
def test_truncated_invalid_hint_unmapped_slot_and_trailing_bytes_are_refused(raw):
    with pytest.raises(RuntimeError):
        c.modern_swap(raw)


def test_exact_two_unique_pairs_include_ordinary_inverse_and_never_empty_destination():
    proof = c.roundtrip_packets(packets() + packets(True, 11), 'scout', 9, 12)
    assert proof['exactly_two_unique_pairs'] is True
    assert proof['reverse']['native']['body'] == '1718'


@pytest.mark.parametrize('fault', ['duplicate', 'extra_swap', 'extra_native', 'wrong_source', 'wrong_destination',
    'native_reversed', 'modern_trailing', 'native_trailing', 'hint_bad_position', 'foreign', 'reverse_time',
    'latency', 'bool_time', 'nan_time', 'uppercase_body', 'wrong_direction', 'incomplete_inverse'])
def test_swap_pair_and_roundtrip_refuse_request_drift(fault):
    rows = packets() + packets(True, 11)
    if fault == 'duplicate': rows.append(deepcopy(rows[0]))
    elif fault == 'extra_swap': rows += packets(start=11.4)
    elif fault == 'extra_native': rows.append({**rows[1], 'body': '1917'})
    elif fault == 'wrong_source': rows[0]['body'] = modern(36, 37).hex()
    elif fault == 'wrong_destination': rows[0]['body'] = modern(37, 35).hex()
    elif fault == 'native_reversed': rows[1]['body'] = '1718'
    elif fault == 'modern_trailing': rows[0]['body'] += '00'
    elif fault == 'native_trailing': rows[1]['body'] += '00'
    elif fault == 'hint_bad_position': rows[0]['body'] = modern(hints=((255, 51),)).hex()
    elif fault == 'foreign': rows[1]['session'] = 'other'
    elif fault == 'reverse_time': rows[2]['time'] = 9.9
    elif fault == 'latency': rows[1]['time'] = 12.1
    elif fault == 'bool_time': rows[0]['time'] = True
    elif fault == 'nan_time': rows[0]['time'] = float('nan')
    elif fault == 'uppercase_body': rows[0]['body'] = rows[0]['body'].upper()
    elif fault == 'wrong_direction': rows[1]['direction'] = 'to_client'
    else: rows.pop()
    with pytest.raises(RuntimeError): c.roundtrip_packets(rows, 'scout', 9, 13)


@pytest.mark.parametrize('name', sorted(c.FORBIDDEN) + ['CMSG_MOVE_START_FORWARD', 'MSG_MOVE_HEARTBEAT',
    'CMSG_PET_UNKNOWN_ACTION', 'CMSG_STABLE_UNKNOWN', 'CMSG_TRADE_ACCEPT', 'CMSG_LOOT_ITEM'])
@pytest.mark.parametrize('direction', ['from_client', 'to_native'])
def test_other_gameplay_input_is_refused_on_both_modern_and_native_sides(name, direction):
    with pytest.raises(RuntimeError):
        c.forbidden_packets([{'session': 'scout', 'time': 10, 'name': name, 'direction': direction}], 'scout', 9, 11)


def test_login_mover_initialization_has_no_movement_semantics():
    rows = [{'session': 'scout', 'time': 10, 'name': name, 'direction': 'to_native'} for name in c.MOVER_INITIALIZATION]
    assert c.forbidden_packets(rows, 'scout', 9, 11)['no_forbidden_input'] is True


@pytest.mark.parametrize('direction', ['from_native', 'to_client', 'unknown'])
def test_inventory_failure_is_refused_even_when_result_code_is_success(direction):
    row = {'session': 'scout', 'time': 10, 'name': 'SMSG_INVENTORY_CHANGE_FAILURE', 'direction': direction, 'body': '00'}
    with pytest.raises(RuntimeError): c.forbidden_packets([row], 'scout', 9, 11)


def test_saved_rows_exchange_only_the_two_slot_columns_and_all_fifteen_item_fields_are_exact():
    before = inventory()
    swapped = c.expected_inventory(before, swapped=True)
    proof = c.inventory_rows(before, swapped, swapped=True)
    assert proof['all_item_instance_fields_unchanged'] is True
    assert swapped[0][3] == 33 and swapped[1][3] == 41
    assert c.inventory_rows(before, before)['swapped'] is False


@pytest.mark.parametrize('column', range(19))
def test_every_saved_inventory_and_item_instance_column_is_guarded(column):
    before, after = inventory(), c.expected_inventory(inventory(), swapped=True)
    after[1][column] = after[1][column] + 1 if type(after[1][column]) is int else after[1][column] + 'x'
    with pytest.raises(RuntimeError): c.inventory_rows(before, after, swapped=True)


def test_full_native_resources_and_rendered_both_occupied_items_match_after_exchange():
    before, after = resources(), resources(True)
    assert c.native_resources(before, after, swapped=True)['all_other_native_resources_unchanged'] is True
    assert c.public_items(public(True), after, swapped=True)['public_guid_source'] == 'delivered_inventory_packets'


@pytest.mark.parametrize('fault', ['wrong_guid', 'low_guid', 'count', 'bool', 'empty_destination',
    'extra_equipment', 'extra_backpack', 'extra_bag', 'money', 'duplicate_guid', 'missing_bag'])
def test_native_resource_projection_is_complete_and_all_other_slots_remain_exact(fault):
    before, after = resources(), resources(True)
    if fault == 'wrong_guid': after['backpack'][0]['guid'] += 1
    elif fault == 'low_guid': after['backpack'][0]['guid'] = 33
    elif fault == 'count': after['backpack'][0]['count'] = 2
    elif fault == 'bool': after['backpack'][0]['count'] = True
    elif fault == 'empty_destination': after['backpack'][0] = {'guid': 0, 'id': 0, 'count': 0}
    elif fault.startswith('extra_'):
        destination = {'extra_equipment': after['equipment'], 'extra_backpack': after['backpack'], 'extra_bag': after['bags'][0]}[fault]
        destination[-1] = {'guid': (0x4000 << 48) | 123, 'id': 39, 'count': 1}
    elif fault == 'money': after['money'] += 1
    elif fault == 'duplicate_guid': after['backpack'][2] = deepcopy(c.SOURCE)
    else: after['bags'].pop()
    with pytest.raises(RuntimeError): c.native_resources(before, after, swapped=True)


@pytest.mark.parametrize('fault', ['wrong_id', 'wrong_count', 'locked', 'bool_bag', 'wrong_slot',
    'duplicate', 'missing_item', 'hidden_backpack', 'unrelated_row', 'other_shown_bag_omitted'])
def test_rendered_entries_counts_unlocked_and_every_shown_bag_are_guarded(fault):
    state, native = public(True), resources(True)
    if fault == 'wrong_id': state['bag_items'][0]['id'] += 1
    elif fault == 'wrong_count': state['bag_items'][0]['count'] += 1
    elif fault == 'locked': state['bag_items'][0]['locked'] = True
    elif fault == 'bool_bag': state['bag_items'][0]['bag'] = False
    elif fault == 'wrong_slot': state['bag_items'][0]['slot'] = 3
    elif fault == 'duplicate': state['bag_items'].append(deepcopy(state['bag_items'][0]))
    elif fault == 'missing_item': state['bag_items'].pop()
    elif fault == 'hidden_backpack': state['bags'] = []
    elif fault == 'unrelated_row': state['bag_items'].append({'bag': 0, 'slot': 3, 'id': 39, 'count': 1, 'locked': False})
    else:
        state['bags'].append(1)
        native['bags'][0][0] = {'guid': (0x4000 << 48) | 123, 'id': 39, 'count': 1}
    with pytest.raises(RuntimeError): c.public_items(state, native, swapped=True)


def test_native_replay_proves_both_full_item_creations_and_every_intermediate_inventory_state():
    proof = c.native_replay(native_rows(True), 'scout', 9, 12)
    assert proof['native_item_fields_preserved'] is True
    assert proof['native_inventory_states'] == [[c.SOURCE['guid'], c.DESTINATION['guid']],
        [c.DESTINATION['guid'], c.SOURCE['guid']], [c.SOURCE['guid'], c.DESTINATION['guid']]]
    assert [r['time'] for r in proof['native_inventory_transitions']] == [9, 10.2, 11.2]
    assert proof['native_inventory_transitions'][1]['packet'] == native_rows(True)[5]
    assert json.loads(json.dumps(proof)) == proof


@pytest.mark.parametrize('index,effect_time', [(5, 9.3), (8, 10.3)])
def test_native_inventory_exchange_cannot_precede_its_attributed_swap_request(index, effect_time):
    rows = native_rows(True)
    rows[index]['time'] = effect_time
    rows.sort(key=lambda row: row['time'])
    with pytest.raises(RuntimeError, match='exchange must|inverse must'):
        c.native_replay(rows, 'scout', 9, 12)


def test_reverse_only_request_cannot_reuse_an_unswapped_login_baseline():
    rows = native_rows()
    rows[3:5] = packets(True)
    with pytest.raises(RuntimeError): c.native_replay(rows, 'scout', 9, 12)


@pytest.mark.parametrize('fault', ['wrong_item', 'missing_item', 'duplicate_item', 'item_owner', 'count_transient',
    'charge_transient', 'item_extra_field', 'destroy_item', 'remove_item', 'other_slot_transient',
    'occupied_slot_empty', 'no_native_exchange', 'target_transient', 'combat_transient', 'extra_swap'])
def test_native_replay_rejects_hidden_transient_item_inventory_target_and_combat_changes(fault):
    rows = native_rows(True)
    if fault == 'wrong_item': rows[1] = native_packet(item_fields(c.DESTINATION), guid=c.SOURCE['guid'], kind=1, time=9.1)
    elif fault == 'missing_item': rows.pop(1)
    elif fault == 'duplicate_item': rows.insert(2, deepcopy(rows[1]))
    elif fault == 'item_owner':
        rows[1] = native_packet({**item_fields(c.SOURCE), c.INDEX['ITEM_FIELD_OWNER']: 3}, guid=c.SOURCE['guid'], kind=1, time=9.1)
    elif fault in ('count_transient', 'charge_transient', 'item_extra_field'):
        field = c.INDEX[{'count_transient': 'ITEM_FIELD_STACK_COUNT', 'charge_transient': 'ITEM_FIELD_SPELL_CHARGES',
            'item_extra_field': 'ITEM_FIELD_DURATION'}[fault]]
        rows.insert(3, native_packet({field: 2}, guid=c.SOURCE['guid'], creation=False, time=9.3))
    elif fault == 'destroy_item': rows.insert(3, {'session': 'scout', 'time': 9.3, 'name': 'SMSG_DESTROY_OBJECT',
        'direction': 'from_native', 'body': struct.pack('<QB', c.SOURCE['guid'], 0).hex()})
    elif fault == 'remove_item':
        guid = c.SOURCE['guid']; octets = struct.pack('<Q', guid)
        raw = Writer().pack('HIBI', 0, 1, 3, 1).pack('B', sum(bool(v) << i for i, v in enumerate(octets)))
        raw.raw(bytes(v for v in octets if v))
        rows.insert(3, {'session': 'scout', 'time': 9.3, 'name': 'SMSG_UPDATE_OBJECT', 'direction': 'from_native', 'body': raw.finish().hex()})
    elif fault == 'other_slot_transient': rows.insert(3, native_packet({c.INDEX['PLAYER_FIELD_INV_SLOT_HEAD']: 1}, creation=False, time=9.3))
    elif fault == 'occupied_slot_empty': rows[5] = native_packet({**slot_fields(True), c.INDEX['PLAYER_FIELD_INV_SLOT_HEAD'] + 48: 0}, creation=False, time=10.2)
    elif fault == 'no_native_exchange': rows.pop(5)
    elif fault == 'target_transient': rows.insert(3, native_packet({c.INDEX['UNIT_FIELD_TARGET']: 3}, creation=False, time=9.3))
    elif fault == 'combat_transient': rows.insert(3, native_packet({c.INDEX['UNIT_FIELD_FLAGS']: 0x80000}, creation=False, time=9.3))
    else: rows += packets(start=11.5)
    with pytest.raises(RuntimeError): c.native_replay(rows, 'scout', 9, 12)


def test_pure_modules_do_not_import_live_runtime_sql_ui_or_crypto():
    script = '''
import importlib, sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('Crypto', 'google', 'PIL', 'pymysql', 'requests',
            'tools.client_compatibility.interaction_', 'tools.client_compatibility.lab_runtime')):
            raise AssertionError('live dependency imported: ' + fullname)
sys.meta_path.insert(0, Block())
for name in ('bag_swap_contract', 'bag_swap_preservation', 'bag_swap_login_sync'):
    importlib.import_module('tools.client_compatibility.' + name)
'''
    subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[4], check=True,
        capture_output=True, env={**__import__('os').environ, 'PYTHONDONTWRITEBYTECODE': '1'})


def test_explicit_login_proof_allows_only_retained_boot_and_preserves_default_guard():
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import recorded, proof
    value = recorded()
    result = proof(value)
    with pytest.raises(RuntimeError):
        c.forbidden_packets(value['rows'], value['session'], value['since'], value['until'])
    assert c.forbidden_packets(value['rows'], value['session'], value['since'], value['until'],
        login_sync=result)['no_forbidden_input'] is True
    legacy = {'session': 'scout', 'name': 'CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE', 'time': 1,
        'direction': 'from_client', 'body': ''}
    assert c.forbidden_packets([legacy], 'scout', 0, 2)['no_forbidden_input'] is True


@pytest.mark.parametrize('name', ['CMSG_MOVE_HEARTBEAT', 'CMSG_MOVE_FALL_LAND',
    'CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE', 'CMSG_SET_ACTIVE_MOVER', 'CMSG_MOVE_JUMP', 'CMSG_SET_SELECTION'])
def test_valid_boot_receipt_never_allows_later_movement_or_initializer(name):
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import recorded, proof
    value = recorded()
    result = proof(value)
    rows = value['rows'] + [{'session': value['session'], 'name': name, 'time': value['until'] + 1,
        'direction': 'from_client', 'body': result['initialization']['modern']['body']}]
    with pytest.raises(RuntimeError):
        c.forbidden_packets(rows, value['session'], value['since'], value['until'] + 2, login_sync=result)


def test_full_history_roundtrip_and_native_replay_share_the_exact_login_allowance():
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import recorded, proof
    value = recorded()
    result = proof(value)
    start = value['until'] + 1
    additions = packets(start=start) + [native_packet(slot_fields(True), creation=False, time=start + .2)]
    additions += packets(True, start + 1) + [native_packet(slot_fields(), creation=False, time=start + 1.2)]
    additions = [{**row, 'session': value['session']} for row in additions]
    rows = value['rows'] + additions
    interval = (value['session'], value['since'], start + 2)
    assert c.roundtrip_packets(rows, *interval, login_sync=result)['exactly_two_unique_pairs'] is True
    replay = c.native_replay(rows, *interval, login_sync=result)
    assert replay['native_inventory_states'] == [[c.SOURCE['guid'], c.DESTINATION['guid']],
        [c.DESTINATION['guid'], c.SOURCE['guid']], [c.SOURCE['guid'], c.DESTINATION['guid']]]


def fresh_roundtrip():
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import fresh_login
    value = fresh_login()
    start = value['until'] + 1
    additions = packets(start=start) + [native_packet(slot_fields(True), creation=False, time=start + .2)]
    additions += packets(True, start + 1) + [native_packet(slot_fields(), creation=False, time=start + 1.2)]
    additions += [{'time': start + 2 + i * .1, 'name': name, 'direction': direction, 'body': raw}
        for i, (name, direction, raw) in enumerate((('CMSG_LOGOUT_REQUEST', 'from_client', '80'),
            ('CMSG_LOGOUT_REQUEST', 'to_native', ''), ('SMSG_LOGOUT_RESPONSE', 'from_native', '0000000000'),
            ('SMSG_LOGOUT_RESPONSE', 'to_client', '0000000000'), ('SMSG_LOGOUT_COMPLETE', 'from_native', ''),
            ('SMSG_LOGOUT_COMPLETE', 'to_client', '00')))]
    value['rows'] += [{**row, 'session': value['session']} for row in additions]
    value['until'] = start + 3
    return value


def test_serialized_fresh_boot_occupied_roundtrip_and_logout_replay_preserve_every_native_item():
    from tools.client_compatibility.bag_swap_login_sync import login_sync, validate_login_sync
    value = json.loads(json.dumps(fresh_roundtrip(), allow_nan=False))
    result = login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose')))
    entry = json.loads(json.dumps({'login_sync': result, 'raw_packets': value['rows'], 'raw_events': value['events']}))
    assert validate_login_sync(entry['login_sync']) == result
    interval = (value['session'], value['since'], value['until'])
    replay = c.native_replay(entry['raw_packets'], *interval, login_sync=entry['login_sync'])
    assert c.roundtrip_packets(entry['raw_packets'], *interval, login_sync=entry['login_sync'])['exactly_two_unique_pairs']
    for session in (result['session'], result['instance_session']):
        assert c.forbidden_packets(entry['raw_events'], session, value['since'], value['until'],
            login_sync=result)['no_forbidden_input']
    assert replay['native_inventory_states'] == [[c.SOURCE['guid'], c.DESTINATION['guid']],
        [c.DESTINATION['guid'], c.SOURCE['guid']], [c.SOURCE['guid'], c.DESTINATION['guid']]]
    assert replay['native_item_fields_preserved'] is True
    assert set(replay['item_fields']) == {str(c.SOURCE['guid']), str(c.DESTINATION['guid'])}
    assert any(row['name'] == 'SMSG_UPDATE_OBJECT' for row in replay['packets'])
    assert len([row for row in entry['raw_packets'] if row['name'] == 'SMSG_LOGOUT_COMPLETE']) == 2


@pytest.mark.parametrize('fault', ['late_heartbeat', 'late_initializer', 'repeated_native_land',
    'altered_boot_body', 'extra_directionless_effect'])
def test_fresh_whole_history_replay_cannot_filter_later_or_changed_movement(fault):
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import proof, packet
    from tools.client_compatibility import bag_swap_login_sync as sync
    value = fresh_roundtrip()
    result = proof(value)
    rows = deepcopy(value['rows'])
    if fault == 'extra_directionless_effect':
        events = value['events'] + [{**next(e for e in value['events'] if e['event'] == 'movement_forwarded'),
            'time': value['until'] - .01}]
        with pytest.raises(RuntimeError):
            c.forbidden_packets(events, result['instance_session'], value['since'], value['until'], login_sync=result)
        return
    if fault == 'altered_boot_body':
        next(r for r in rows if r['name'] == sync.HEARTBEAT)['body'] += '00'
    else:
        name, direction = {'late_heartbeat': (sync.HEARTBEAT, 'from_client'),
            'late_initializer': (sync.INITIALIZE, 'from_client'),
            'repeated_native_land': ('MSG_MOVE_FALL_LAND', 'to_native')}[fault]
        rows.append({**packet(value, name, direction), 'time': value['until'] - .01})
    with pytest.raises(RuntimeError):
        c.native_replay(rows, value['session'], value['since'], value['until'], login_sync=result)


@pytest.mark.parametrize('kind', ['raw_heartbeat', 'forwarded_metadata'])
def test_actual_caller_cannot_duplicate_a_valid_proof_allowed_boot_row(kind):
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import proof, packet
    from tools.client_compatibility import bag_swap_login_sync as sync
    value = fresh_roundtrip()
    result = proof(value)
    if kind == 'raw_heartbeat':
        rows = value['rows'] + [deepcopy(packet(value, sync.HEARTBEAT))]
        with pytest.raises(RuntimeError, match='allowance row is repeated'):
            c.native_replay(rows, value['session'], value['since'], value['until'], login_sync=result)
    else:
        duplicate = next(e for e in value['events'] if e['event'] == 'movement_forwarded')
        events = value['events'] + [deepcopy(duplicate)]
        with pytest.raises(RuntimeError, match='allowance row is repeated'):
            c.forbidden_packets(events, result['instance_session'], value['since'], value['until'], login_sync=result)


@pytest.mark.parametrize('kind', ['drop', 'forwarded', 'confirmation'])
def test_reconstructed_boot_proof_does_not_hide_extra_directionless_movement_metadata(kind):
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import recorded, proof
    value = recorded()
    result = proof(value)
    event = {'drop': 'unmapped_client_packet', 'forwarded': 'movement_forwarded',
        'confirmation': 'native_active_mover_confirmed'}[kind]
    extra = next(e for e in value['events'] if e.get('event') == event)
    events = value['events'] + [{**extra, 'time': value['until'] - .01}]
    with pytest.raises(RuntimeError):
        c.forbidden_packets(events, result['instance_session'], value['since'], value['until'], login_sync=result)


@pytest.mark.parametrize('name', ['CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK'])
@pytest.mark.parametrize('direction', ['from_client', 'to_native'])
def test_afk_input_requires_exact_idle_housekeeping_authority(name, direction):
    row = {'session': 'scout', 'name': name, 'time': 10, 'direction': direction, 'body': '0000'}
    with pytest.raises(RuntimeError):
        c.forbidden_packets([row], 'scout', 9, 11)
    with pytest.raises(RuntimeError):
        c.native_replay(native_rows(True) + [row], 'scout', 9, 12)


@pytest.mark.parametrize('field,value', [('UNIT_FIELD_BYTES_1', 1), ('PLAYER_FLAGS', 2),
    ('UNIT_FIELD_BYTES_2', 1)])
@pytest.mark.parametrize('transient', [False, True])
def test_native_stand_afk_and_sheath_changes_cannot_hide_in_owner_replay(field, value, transient):
    rows = native_rows(True)
    rows.insert(3, native_packet({c.INDEX[field]: value}, creation=False, time=9.3))
    if transient:
        rows.insert(4, native_packet({c.INDEX[field]: 0}, creation=False, time=9.4))
    with pytest.raises(RuntimeError):
        c.native_replay(rows, 'scout', 9, 12)


@pytest.mark.parametrize('field,value', [('UNIT_FIELD_BYTES_1', 1), ('PLAYER_FLAGS', 2),
    ('UNIT_FIELD_BYTES_2', 1)])
def test_original_native_owner_creation_requires_standing_non_afk_baseline(field, value):
    rows = native_rows(True)
    rows[0] = native_packet({**owner_fields(), **slot_fields(), c.INDEX[field]: value}, time=9)
    with pytest.raises(RuntimeError):
        c.native_replay(rows, 'scout', 9, 12)

"""Pure contract for an occupied backpack swap and its ordinary inverse."""
from copy import deepcopy
import struct

from . import item_actionbar_contract as shared
from .world.buffer import Reader
from .world.native_objects import records

ACTOR, INDEX = shared.ACTOR, shared.INDEX
HEALTH, XP_CAP, REST_CAP = shared.HEALTH, shared.XP_CAP, shared.REST_CAP
require, finite, strict_equal = shared.require, shared.finite, shared.strict_equal
packet_rows, body, login_packets = shared.packet_rows, shared.body, shared.login_packets
ACTION = 'CMSG_SWAP_INV_ITEM'
ENTRY_PHASE = 'bags_swap_entered'
SOURCE = {'guid': (0x4000 << 48) | 41, 'id': 6948, 'count': 1}
DESTINATION = {'guid': (0x4000 << 48) | 33, 'id': 58231, 'count': 1}
ITEMS = ((41, 6948, 23), (33, 58231, 24))
FORBIDDEN = (shared.FORBIDDEN - {ACTION}) | frozenset((
    'CMSG_SET_ACTION_BUTTON', 'CMSG_SET_ACTION_BAR_TOGGLES', 'CMSG_SET_ACTIONBAR_TOGGLES',
    'CMSG_SET_SELECTION', 'CMSG_TARGET_UNIT', 'CMSG_SET_TARGET', 'CMSG_ATTACK_SWING',
    'CMSG_ATTACK_STOP', 'CMSG_ATTACKSWING', 'CMSG_ATTACKSTOP', 'CMSG_CANCEL_CAST',
    'CMSG_CANCEL_CHANNELLING', 'CMSG_CANCEL_AURA', 'CMSG_CANCEL_AUTO_REPEAT_SPELL',
    'CMSG_TOGGLE_PVP', 'CMSG_SET_SHEATHED', 'CMSG_STANDSTATECHANGE', 'CMSG_STAND_STATE_CHANGE',
    'CMSG_CHAT_MESSAGE_AFK', 'CMSG_MESSAGECHAT_AFK',
    'CMSG_GAMEOBJ_USE', 'CMSG_GAME_OBJ_USE', 'CMSG_GAMEOBJ_REPORT_USE',
    'CMSG_GOSSIP_HELLO', 'CMSG_TALK_TO_GOSSIP', 'CMSG_GOSSIP_SELECT_OPTION',
    'CMSG_REPAIR_ITEM', 'CMSG_ITEM_REFUND', 'CMSG_ITEM_REFUND_INFO', 'CMSG_WRAP_ITEM',
    'CMSG_SOCKET_GEMS', 'CMSG_REFORGE_ITEM', 'CMSG_TRANSMOGRIFY_ITEMS',
    'CMSG_SWAP_SUB_GEAR', 'CMSG_EQUIPMENT_SET_USE', 'CMSG_SEND_MAIL', 'CMSG_BUYBACK_ITEM',
    'CMSG_MAIL_TAKE_ITEM', 'CMSG_MAIL_TAKE_MONEY', 'CMSG_MAIL_CREATE_TEXT_ITEM',
    'CMSG_MAIL_DELETE', 'CMSG_MAIL_RETURN_TO_SENDER', 'CMSG_AUTOSTORE_LOOT_ITEM',
    'CMSG_INITIATE_TRADE', 'CMSG_BEGIN_TRADE', 'CMSG_ACCEPT_TRADE', 'CMSG_SET_TRADE_ITEM',
    'CMSG_CLEAR_TRADE_ITEM', 'CMSG_SET_TRADE_GOLD', 'CMSG_SET_PET_SLOT',
    'CMSG_SUMMON_RESPONSE', 'CMSG_CANCEL_MOUNT_AURA', 'CMSG_ENABLE_TAXI_NODE',
    'CMSG_ACTIVATE_TAXI', 'CMSG_ACTIVATE_TAXI_EXPRESS', 'CMSG_AREA_TRIGGER',
    'CMSG_CLEAR_RAID_MARKER', 'CMSG_SET_RAID_TARGET', 'CMSG_SELL_ITEM',
))
FORBIDDEN_PREFIXES = ('CMSG_PET_', 'CMSG_STABLE_', 'CMSG_TRADE_', 'CMSG_LOOT_',
    'CMSG_DUEL_', 'CMSG_QUESTGIVER_', 'CMSG_BATTLEMASTER_', 'CMSG_BATTLEFIELD_',
    'CMSG_MOVE_', 'MSG_MOVE_')
# Login activates the mover without moving the character.
MOVER_INITIALIZATION = frozenset(('CMSG_MOVE_INIT_ACTIVE_MOVER_COMPLETE', 'CMSG_SET_ACTIVE_MOVER'))


def _inventory_layout(rows, swapped=False):
    require(type(swapped) is bool and type(rows) is list and all(type(r) is list and len(r) == 19 for r in rows),
        'complete 4-column inventory and 15-column item_instance rows are required')
    integer_columns = tuple(range(11)) + (12, 14, 15, 16, 17)
    require(all(all(type(r[i]) is int for i in integer_columns) and
        all(type(r[i]) is str for i in (11, 13, 18)) and r[0] == r[6] == 2 and r[3] == r[4] and
        r[3] > 0 and r[9] > 0 for r in rows), 'every owned inventory and item_instance column must retain its native type')
    require(rows == sorted(rows, key=lambda r: (r[1], r[2])) and
        len({tuple(r[1:3]) for r in rows}) == len(rows) and len({r[3] for r in rows}) == len(rows),
        'owned inventory positions and item GUIDs must be unique and canonical')
    selected = []
    for guid, item, original_slot in ITEMS:
        slot = 47 - original_slot if swapped else original_slot
        matches = [r for r in rows if r[3] == guid]
        require(len(matches) == 1 and matches[0][:7] == [2, 0, slot, guid, guid, item, 2] and matches[0][9] == 1,
            'occupied source6948/GUID41 and destination58231/GUID33/count1 must occupy the exact two backpack slots')
        selected.append(matches[0])
    return selected


def expected_inventory(rows, *, swapped=False):
    """Compute the sole allowed slot delta from the exact unswapped baseline."""
    _inventory_layout(rows)
    require(type(swapped) is bool, 'swap flag must be boolean')
    expected = deepcopy(rows)
    if swapped:
        for row in expected:
            if row[3] in (41, 33):
                row[2] = 47 - row[2]
        expected.sort(key=lambda r: (r[1], r[2]))
    return expected


def owned_snapshot(snapshot, offline=True, swapped=False):
    require(type(snapshot) is dict and type(offline) is bool and type(swapped) is bool and
        type(snapshot.get('2')) is dict, 'typed complete owned snapshot is required')
    rows = snapshot['2'].get('inventory')
    _inventory_layout(rows, swapped)
    normalized = deepcopy(snapshot)
    if swapped:
        for row in normalized['2']['inventory']:
            if row[3] in (41, 33):
                row[2] = 47 - row[2]
        normalized['2']['inventory'].sort(key=lambda r: (r[1], r[2]))
    shared.owned_snapshot(normalized, offline=offline)
    return snapshot['2']


def inventory_rows(before, after, *, swapped=False):
    _inventory_layout(before)
    _inventory_layout(after, swapped)
    require(strict_equal(after, expected_inventory(before, swapped=swapped)),
        'only the two character_inventory slot columns may exchange; all 15 item_instance fields must remain exact')
    return {'swapped': swapped, 'sql_item_guids': [41, 33], 'sql_slots': [23, 24],
        'all_item_instance_fields_unchanged': True, 'all_other_inventory_rows_unchanged': True,
        'before': deepcopy(before), 'after': deepcopy(after)}


def native_slot(slot):
    require(type(slot) is int and 0 <= slot <= 255, 'modern inventory slot must be a byte')
    if slot < 19:
        return slot
    if 30 <= slot < 34:
        return slot - 11
    if 35 <= slot < 51:
        return slot - 12
    if 59 <= slot < 106:
        return slot - 20
    raise RuntimeError('modern inventory slot has no native equivalent')


def native_position(bag, slot):
    require(type(bag) is int and type(slot) is int and 0 <= bag <= 255 and 0 <= slot <= 255,
        'modern inventory hint requires two bytes')
    if bag == 255:
        return (255, native_slot(slot))
    require(30 <= bag < 34 or 87 <= bag < 94, 'inventory hint container has no native equivalent')
    require(slot < 36, 'inventory hint bag item slot exceeds native bound')
    return (native_slot(bag), slot)


def modern_swap(raw):
    """Decode every optional InvUpdate row and both slot bytes exactly as the bridge."""
    require(type(raw) is bytes, 'modern swap body must be raw bytes')
    try:
        reader = Reader(raw)
        count = reader.bits(2)
        reader.align()
        hints = []
        for _ in range(count):
            bag, slot = reader.unpack('2B')
            hints.append({'modern': [bag, slot], 'native': list(native_position(bag, slot))})
        destination, source = reader.unpack('2B')
        native = [native_slot(destination), native_slot(source)]
        reader.end()
    except (ValueError, IndexError, struct.error) as error:
        raise RuntimeError('modern swap body must fully consume its 2-bit hints and both slot bytes') from error
    return {'hint_count': count, 'hints': hints, 'destination': destination, 'source': source,
        'native_destination': native[0], 'native_source': native[1]}


def forbidden_packets(rows, session, since, until, *, login_sync=None, idle_housekeeping=None):
    scoped = packet_rows(rows, session, since, until)
    allowed = set()
    if idle_housekeeping is not None:
        from .bag_swap_idle import validate_history
        from .bag_swap_login_sync import packet_key
        history = validate_history(idle_housekeeping)
        require(session in (history['session'], history['instance_session']),
            'idle housekeeping allowance belongs to another physical/native session')
        allowed.update(history['allowed_packet_keys'])
        allowed.update(history['allowed_metadata_keys'])
    if login_sync is not None:
        from .bag_swap_login_sync import packet_key, validate_login_sync
        proof = validate_login_sync(login_sync)
        require(session in (proof['session'], proof['instance_session']),
            'login settlement allowance belongs to another physical/native session')
        allowed.update(proof['allowed_packet_keys'])
        allowed.update(proof['allowed_metadata_keys'])
    bad = []
    for row in scoped:
        name = row.get('name')
        if (login_sync is not None or idle_housekeeping is not None) and 'event' not in row:
            from .bag_swap_login_sync import WIRE_DIRECTIONS, WIRE_FIELDS
            require(set(row) == WIRE_FIELDS and type(name) is str and name and
                type(row.get('direction')) is str and row['direction'] in WIRE_DIRECTIONS,
                'proof-bound replay requires canonical raw wire rows')
            body(row)
        if name == 'SMSG_INVENTORY_CHANGE_FAILURE':
            bad.append(row)
        elif login_sync is not None and row.get('event') in (
            'movement_forwarded', 'unmapped_client_packet', 'native_active_mover_confirmed',
            'active_mover_deferred_until_player_create') and (
            type(name) is str and name.startswith(('CMSG_MOVE_', 'MSG_MOVE_')) or
            row.get('event') in ('native_active_mover_confirmed', 'active_mover_deferred_until_player_create')):
            if packet_key(row) not in allowed:
                bad.append(row)
        elif row.get('direction') in ('from_client', 'to_native') and type(name) is str and (
            name in FORBIDDEN or (name.startswith(FORBIDDEN_PREFIXES) and
                (login_sync is not None or idle_housekeeping is not None or name not in MOVER_INITIALIZATION)) or
            ((login_sync is not None or idle_housekeeping is not None) and name in MOVER_INITIALIZATION)):
            if not allowed or packet_key(row) not in allowed:
                bad.append(row)
    require(not bad, 'bag swap refuses other gameplay mutation, item use/cast/action assignment, combat, target, movement, pet input or inventory failure')
    return {'no_forbidden_input': True, 'no_inventory_failure': True}


def _pair(requests, *, reverse=False):
    require(type(reverse) is bool, 'reverse flag must be boolean')
    require(len(requests) == 2, 'one unique modern/native backpack swap request pair is required')
    modern = [r for r in requests if r.get('direction') == 'from_client']
    native = [r for r in requests if r.get('direction') == 'to_native']
    require(len(modern) == len(native) == 1, 'swap pair must contain exactly one modern and one native request')
    modern, native = modern[0], native[0]
    parsed = modern_swap(body(modern))
    wanted = (35, 36) if reverse else (36, 35)
    require((parsed['destination'], parsed['source']) == wanted and
        body(native) == bytes(native_slot(s) for s in wanted),
        'exact modern36/35 to native24/23 or inverse35/36 to native23/24 is required')
    require(modern['time'] <= native['time'] and native['time'] - modern['time'] < 2,
        'swap request pair ordering or delivery latency differs')
    return {'reverse': reverse, 'modern': deepcopy(modern), 'native': deepcopy(native), 'decoded': parsed}


def swap_packets(rows, session, since, until, *, reverse=False, login_sync=None, idle_housekeeping=None):
    scoped = packet_rows(rows, session, since, until)
    forbidden_packets(rows, session, since, until, login_sync=login_sync, idle_housekeeping=idle_housekeeping)
    return _pair([r for r in scoped if r.get('name') == ACTION], reverse=reverse)


def roundtrip_packets(rows, session, since, until, *, login_sync=None, idle_housekeeping=None):
    scoped = packet_rows(rows, session, since, until)
    forbidden_packets(rows, session, since, until, login_sync=login_sync, idle_housekeeping=idle_housekeeping)
    requests = [r for r in scoped if r.get('name') == ACTION]
    require(len(requests) == 4, 'exactly two unique modern/native swap pairs total are required')
    forwards, reverses = [], []
    for row in requests:
        if row.get('direction') == 'from_client':
            parsed = modern_swap(body(row))
            key = (parsed['destination'], parsed['source'])
        elif row.get('direction') == 'to_native':
            raw = body(row)
            require(len(raw) == 2, 'native swap body must contain exactly two slot bytes')
            key = tuple(raw)
        else:
            raise RuntimeError('unexpected swap request direction')
        if key in ((36, 35), (24, 23)):
            forwards.append(row)
        elif key in ((35, 36), (23, 24)):
            reverses.append(row)
        else:
            raise RuntimeError('swap request touches a position outside the owned two-slot contract')
    forward, reverse = _pair(forwards), _pair(reverses, reverse=True)
    require(forward['native']['time'] < reverse['modern']['time'],
        'ordinary reverse swap must follow the delivered forward swap')
    return {'forward': forward, 'reverse': reverse, 'exactly_two_unique_pairs': True}


def item_resources(resources, *, swapped=False):
    require(type(swapped) is bool and type(resources) is dict and
        type(resources.get('equipment')) is list and len(resources['equipment']) == 19 and
        type(resources.get('backpack')) is list and len(resources['backpack']) == 16 and
        type(resources.get('bags')) is list and len(resources['bags']) == 4 and
        all(type(b) is list and len(b) == 36 for b in resources['bags']),
        'complete native equipment, backpack and four bag resources are required')
    all_items = resources['equipment'] + resources['backpack'] + [i for bag in resources['bags'] for i in bag]
    require(all(type(i) is dict and set(i) == {'guid', 'id', 'count'} and
        all(type(i[k]) is int and i[k] >= 0 for k in i) and
        ((i['guid'] == i['id'] == i['count'] == 0) or
         (i['guid'] >> 48 == 0x4000 and i['id'] > 0 and i['count'] > 0)) for i in all_items),
        'every live item requires a full native item GUID and exact integer entry/count')
    guids = [i['guid'] for i in all_items if i['guid']]
    require(len(set(guids)) == len(guids), 'native item GUID cannot occupy multiple resources')
    pair = [DESTINATION, SOURCE] if swapped else [SOURCE, DESTINATION]
    require(strict_equal(resources['backpack'][:2], pair),
        'native GUID41/6948 and GUID33/58231/count1 must occupy the two exact public backpack slots')
    if 'money' in resources:
        require(type(resources['money']) is int and resources['money'] >= 0, 'native money must be a nonnegative integer')
    return deepcopy(resources)


def native_resources(before, after, *, swapped=False):
    item_resources(before)
    item_resources(after, swapped=swapped)
    expected = deepcopy(before)
    if swapped:
        expected['backpack'][0], expected['backpack'][1] = expected['backpack'][1], expected['backpack'][0]
    require(strict_equal(after, expected), 'only the two live backpack indices may exchange; every other native resource must remain exact')
    return {'swapped': swapped, 'two_full_native_item_guids': [SOURCE['guid'], DESTINATION['guid']],
        'all_other_native_resources_unchanged': True}


def public_items(public, resources, *, swapped=False):
    """Match rendered API entry/count/unlocked state; packet evidence supplies public GUIDs."""
    item_resources(resources, swapped=swapped)
    require(type(public) is dict and type(public.get('bags')) is list and
        all(type(b) is int and 0 <= b <= 4 for b in public['bags']) and
        len(set(public['bags'])) == len(public['bags']) and 0 in public['bags'],
        'the rendered occupied backpack must be open')
    rows = public.get('bag_items')
    require(type(rows) is list and all(type(r) is dict and
        all(type(r.get(k)) is int for k in ('bag', 'slot', 'id', 'count')) and
        type(r.get('locked')) is bool and r['locked'] is False and
        r['bag'] in public['bags'] and 1 <= r['slot'] <= (16 if r['bag'] == 0 else 36) and
        r['id'] > 0 and r['count'] > 0 for r in rows) and
        len({(r['bag'], r['slot']) for r in rows}) == len(rows),
        'every rendered bag item must have one unlocked typed entry/count and a unique shown position')
    expected = []
    for bag in public['bags']:
        native = resources['backpack'] if bag == 0 else resources['bags'][bag - 1]
        expected.extend({'bag': bag, 'slot': slot, 'id': item['id'], 'count': item['count'], 'locked': False}
            for slot, item in enumerate(native, 1) if item['guid'])
    actual = [{k: r[k] for k in ('bag', 'slot', 'id', 'count', 'locked')} for r in rows]
    require(strict_equal(sorted(actual, key=lambda r: (r['bag'], r['slot'])),
        sorted(expected, key=lambda r: (r['bag'], r['slot']))),
        'every rendered item in every shown bag must match the complete native inventory')
    return {'swapped': swapped, 'rendered_item_entries_counts_unlocked': True,
        'public_guid_source': 'delivered_inventory_packets', 'items': deepcopy(rows)}


def native_replay(rows, session, since, until, *, rest_threshold=None, login_sync=None, idle_housekeeping=None):
    """Inspect every owner state and preserve both occupied items' complete native fields."""
    scoped = packet_rows(rows, session, since, until)
    forbidden_packets(rows, session, since, until, login_sync=login_sync, idle_housekeeping=idle_housekeeping)
    swaps = [r for r in scoped if r.get('name') == ACTION]
    forward, reverse = None, None
    if swaps:
        if len(swaps) == 2:
            forward = _pair(swaps)
        else:
            chain = roundtrip_packets(rows, session, since, until, login_sync=login_sync, idle_housekeeping=idle_housekeeping)
            forward, reverse = chain['forward'], chain['reverse']
    filtered = [r for r in rows if not (r.get('session') == session and r.get('name') == ACTION and
        finite(r.get('time')) and since <= r['time'] <= until)]
    owner = shared.native_replay(filtered, session, since, until, rest_threshold=rest_threshold)
    idle_native_keys = set()
    if idle_housekeeping is not None:
        from .bag_swap_idle import validate_history
        from .bag_swap_login_sync import packet_key
        idle_native_keys = set(validate_history(idle_housekeeping)['allowed_packet_keys'])
    selected = {i['guid']: i for i in (SOURCE, DESTINATION)}
    created, current, owner_fields, owner_inventory, inventory_states = {}, {}, {}, None, []
    idle_state = None
    inventory_transitions = []
    for row in owner['packets']:
        if row['name'] == 'SMSG_DESTROY_OBJECT':
            require(int.from_bytes(body(row)[:8], 'little') not in selected,
                'an occupied swap item was destroyed')
            continue
        for record in records(body(row)):
            if record['update_type'] == 3:
                require(not set(record['removed']) & set(selected), 'an occupied swap item was removed')
                continue
            guid = record['guid']
            if guid == 2:
                owner_fields.update(record.get('fields', {}))
                stand = owner_fields.get(INDEX['UNIT_FIELD_BYTES_1'], 0) & 255
                sheath = owner_fields.get(INDEX['UNIT_FIELD_BYTES_2'], 0) & 255
                afk = bool(owner_fields.get(INDEX['PLAYER_FLAGS'], 0) & 2)
                state = (stand, afk)
                require(sheath == 0 and (idle_state is not None or state == (0, False)),
                    'native original standing, sheath or AFK baseline differs')
                if idle_state is not None and state != idle_state:
                    require(bool(idle_native_keys) and packet_key(row) in idle_native_keys,
                        'native stand or AFK transition requires its exact validated idle housekeeping packet')
                idle_state = state
                start = INDEX['PLAYER_FIELD_INV_SLOT_HEAD']
                inventory = {i: owner_fields.get(i, 0) for i in range(start, start + 78)}
                pair_indices = {start + slot * 2 + part for slot in (23, 24) for part in (0, 1)}
                rest = {i: value for i, value in inventory.items() if i not in pair_indices}
                if owner_inventory is None:
                    owner_inventory = rest
                require(strict_equal(rest, owner_inventory), 'an unrelated native inventory slot changed temporarily')
                pair = [inventory[start + slot * 2] | inventory[start + slot * 2 + 1] << 32 for slot in (23, 24)]
                require(pair in ([SOURCE['guid'], DESTINATION['guid']], [DESTINATION['guid'], SOURCE['guid']]),
                    'native occupied inventory slots may only exchange their full item GUIDs')
                if not inventory_states or pair != inventory_states[-1]:
                    inventory_states.append(pair)
                    inventory_transitions.append({'guids': deepcopy(pair), 'time': row['time'], 'packet': deepcopy(row)})
                target = INDEX['UNIT_FIELD_TARGET']
                require(owner_fields.get(target, 0) | owner_fields.get(target + 1, 0) << 32 == 0 and
                    not owner_fields.get(INDEX['UNIT_FIELD_FLAGS'], 0) & 0x80000,
                    'native actor2 target selection or combat state changed')
            if guid not in selected:
                continue
            fields = record.get('fields', {})
            if record['update_type'] in (1, 2):
                require(guid not in created and record.get('kind') == 1,
                    'each occupied item needs one exact native item creation')
                current[guid] = deepcopy(fields)
                created[guid] = deepcopy(fields)
            else:
                require(guid in created, 'occupied item update precedes native creation')
                current[guid].update(fields)
                require(strict_equal(current[guid], created[guid]),
                    'occupied item native fields changed, including a temporary count/charge/owner change')
            def pair(name):
                start = INDEX[name]
                return current[guid].get(start, 0) | current[guid].get(start + 1, 0) << 32
            require(current[guid].get(INDEX['OBJECT_FIELD_ENTRY']) == selected[guid]['id'] and
                current[guid].get(INDEX['ITEM_FIELD_STACK_COUNT']) == 1 and
                pair('ITEM_FIELD_OWNER') == pair('ITEM_FIELD_CONTAINED') == 2,
                'native item creation must retain exact owned entry/count/owner/container')
    require(set(created) == set(selected), 'both full native occupied item creations are required')
    expected_states = [[SOURCE['guid'], DESTINATION['guid']]]
    if swaps:
        expected_states.append([DESTINATION['guid'], SOURCE['guid']])
    if len(swaps) == 4:
        expected_states.append([SOURCE['guid'], DESTINATION['guid']])
    require(strict_equal(inventory_states, expected_states),
        'native inventory must show exactly the baseline, forward exchange and optional ordinary inverse')
    if forward:
        require(forward['native']['time'] < inventory_transitions[1]['time'],
            'native forward exchange must occur strictly after its native swap request')
    if reverse:
        require(inventory_transitions[1]['time'] < reverse['modern']['time'] and
            reverse['native']['time'] < inventory_transitions[2]['time'],
            'native forward exchange must precede reverse input and the inverse must follow its native request')
    return {**owner, 'native_item_fields_preserved': True,
        'all_other_native_inventory_slots_preserved': True, 'native_inventory_states': inventory_states,
        'native_inventory_transitions': inventory_transitions,
        'item_fields': {str(guid): {str(index): value for index, value in fields.items()}
            for guid, fields in created.items()}}

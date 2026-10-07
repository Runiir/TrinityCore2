"""Pure, actor-bound contract for one ordinary Hearthstone bar drag and clear."""
from copy import deepcopy
import json
import math
from pathlib import Path
import struct

from .world.native_objects import records
from .world.buffer import Reader, player_high

ACTOR = {'guid': 2, 'account': 2, 'name': 'Harnesstwo', 'race': 1, 'class': 1, 'level': 1}
ITEM_ID, ITEM_SQL_GUID, ITEM_NATIVE_GUID = 6948, 41, (0x4000 << 48) | 41
ITEM_SQL_SLOT, ITEM_BAG, ITEM_SLOT = 23, 0, 1
HEALTH, XP_CAP, REST_CAP = 60, 400, 300
ACTION = 'CMSG_SET_ACTION_BUTTON'
GRID_SOURCE = {
    'build': 60895, 'source': 'local_read_only_CASC',
    'path': 'Interface/AddOns/Blizzard_ActionBar/Classic/ActionButton.lua',
    'sha256': '6eb7e7407828d2f74025c3790bc000ba12d271385e7db06411f13456946121e0',
    'snippets': [
        'function ActionButton_OnLoad(self)',
        'self:SetAttribute("showgrid", 0);',
        'local type, id = GetActionInfo(action);',
        'if ( HasAction(action) ) then',
        'if ( not self:GetAttribute("statehidden") ) then\n\t\t\tself:Show();',
        'if ( self:GetAttribute("showgrid") == 0 ) then\n\t\t\tself:Hide();',
        'function ActionButton_ShowGrid(button)',
        'if ( issecure() ) then\n\t\tbutton:SetAttribute("showgrid", button:GetAttribute("showgrid") + 1);',
        'if ( button:GetAttribute("showgrid") >= 1 and not button:GetAttribute("statehidden") ) then\n\t\tbutton:Show();',
        'elseif ( event == "ACTIONBAR_SHOWGRID" ) then\n\t\tActionButton_ShowGrid(self);',
    ],
}
INDEX = json.loads(Path(__file__).with_name('world').joinpath('native_fields.json').read_text())
FORBIDDEN = frozenset(('CMSG_USE_ITEM', 'CMSG_OPEN_ITEM', 'CMSG_CAST_SPELL',
    'CMSG_EQUIP_ITEM', 'CMSG_AUTO_EQUIP_ITEM', 'CMSG_AUTO_EQUIP_ITEM_SLOT', 'CMSG_AUTO_STORE_BAG_ITEM',
    'CMSG_AUTOEQUIP_ITEM', 'CMSG_AUTOEQUIP_ITEM_SLOT', 'CMSG_SWAP_ITEM',
    'CMSG_SWAP_INV_ITEM', 'CMSG_SPLIT_ITEM', 'CMSG_DESTROY_ITEM', 'CMSG_AUTOSTORE_BAG_ITEM',
    'CMSG_AUTOSTORE_BANK_ITEM', 'CMSG_AUTOBANK_ITEM', 'CMSG_SELL_ITEM', 'CMSG_BUY_ITEM',
    'CMSG_BUY_ITEM_IN_SLOT', 'CMSG_TRAINER_LIST', 'CMSG_TRAINER_BUY_SPELL', 'CMSG_PET_ACTION', 'CMSG_PET_SET_ACTION',
    'CMSG_PET_SPELL_AUTOCAST', 'CMSG_PET_RENAME', 'CMSG_PET_ABANDON', 'CMSG_PET_CANCEL_AURA'))


def require(value, message):
    if not value:
        raise RuntimeError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def strict_equal(left, right):
    """JSON equality that does not equate booleans with native numeric fields."""
    if type(left) is not type(right):
        return False
    if type(left) is dict:
        return set(left) == set(right) and all(strict_equal(left[k], right[k]) for k in left)
    if type(left) is list:
        return len(left) == len(right) and all(strict_equal(a, b) for a, b in zip(left, right))
    return left == right


def typed_window(session, since, until):
    require(type(session) is str and bool(session) and finite(since) and finite(until) and
        since <= until, 'one finite typed owned packet window is required')


def packet_rows(rows, session, since, until):
    typed_window(session, since, until)
    require(type(rows) is list and all(type(p) is dict for p in rows), 'raw packet rows must be dictionaries')
    owned = [p for p in rows if p.get('session') == session]
    require(all(finite(p.get('time')) for p in owned), 'owned packet time must be finite and numeric')
    return [p for p in owned if since <= p['time'] <= until]


def body(row):
    value = row.get('body')
    require(type(value) is str and len(value) % 2 == 0 and
        all(c in '0123456789abcdef' for c in value), 'raw packet body must be canonical lowercase hex')
    return bytes.fromhex(value)


def owned_snapshot(snapshot, offline=True):
    require(type(snapshot) is dict and set(snapshot) == {str(g) for g in range(1, 7)},
        'the complete six-actor snapshot is required')
    for g, value in snapshot.items():
        require(type(value) is dict and set(value) == {'native', 'saved', 'pets', 'inventory'} and
            type(value['native']) is dict and type(value['saved']) is dict and
            type(value['pets']) is list and type(value['inventory']) is list,
            'full native, saved, pets and inventory projection is required')
        n = value['native']
        require(type(n.get('guid')) is int and n['guid'] == int(g) and
            type(n.get('account')) is int and n['account'] == (1 if g == '1' else 2) and
            type(n.get('online')) is int and n['online'] in (0, 1) and (not offline or n['online'] == 0),
            'snapshot identity or offline status differs')
    own = snapshot['2']
    n = own['native']
    require(all(type(n.get(k)) is type(v) and n[k] == v for k, v in ACTOR.items()) and
        type(n.get('health')) is int and n['health'] == HEALTH and
        all(type(n.get('power' + str(i))) is int and n['power' + str(i)] == 0 for i in range(1, 6)) and
        type(n.get('xp')) is int and n['xp'] == 0 and type(n.get('is_logout_resting')) is int and
        n['is_logout_resting'] == 0 and own['pets'] == [], 'original level1 full-health pet-free actor differs')
    item = [r for r in own['inventory'] if type(r) is list and len(r) == 19 and r[2] == ITEM_SQL_SLOT]
    require(len(item) == 1 and item[0][:7] == [2, 0, ITEM_SQL_SLOT, ITEM_SQL_GUID, ITEM_SQL_GUID, ITEM_ID, 2] and
        all(type(item[0][i]) is int for i in range(11)) and item[0][9] == 1,
        'exact owned SQL Hearthstone GUID41/backpack slot23/count1 is required')
    return own


def item_resources(resources):
    require(type(resources) is dict and type(resources.get('equipment')) is list and len(resources['equipment']) == 19 and
        type(resources.get('backpack')) is list and len(resources['backpack']) == 16 and
        type(resources.get('bags')) is list and len(resources['bags']) == 4 and
        all(type(b) is list and len(b) == 36 for b in resources['bags']), 'complete native item resources are required')
    item = resources['backpack'][0]
    require(type(item) is dict and all(type(item.get(k)) is int and item[k] == v for k, v in
        {'guid': ITEM_NATIVE_GUID, 'id': ITEM_ID, 'count': 1}.items()),
        'native Hearthstone GUID41 must remain in public bag0/slot1 with count1')
    return deepcopy(item)


def action_rows(rows):
    require(type(rows) is list and all(type(r) is list and len(r) == 4 and
        all(type(v) is int for v in r) and r[0] in (0, 1) and 0 <= r[1] < 144 and
        0 < r[2] <= 0xffffff and 0 <= r[3] <= 255 for r in rows), 'saved action row layout differs')
    require(rows == sorted(rows, key=lambda r: (r[0], r[1])) and
        len({tuple(r[:2]) for r in rows}) == len(rows), 'saved action rows must be unique and canonical')


def saved_actions(snapshot, slot0, *, placed=False):
    own = owned_snapshot(snapshot, offline=False)
    spec = own['native'].get('activeTalentGroup')
    require(type(spec) is int and spec in (0, 1) and type(slot0) is int and 0 <= slot0 < 144 and
        type(placed) is bool, 'active spec, native slot or placement flag differs')
    rows = own['saved'].get('actions')
    action_rows(rows)
    require(not any(r[:2] == [spec, slot0] for r in rows), 'drag destination must be absent in the saved baseline')
    return sorted(deepcopy(rows) + ([[spec, slot0, ITEM_ID, 128]] if placed else []), key=lambda r: (r[0], r[1]))


def public_assignments(public, rows, active_spec):
    action_rows(rows)
    require(type(active_spec) is int and active_spec in (0, 1) and type(public) is dict and
        type(public.get('active_spec')) is int and public['active_spec'] == active_spec + 1 and
        public.get('frames', {}).get('MainMenuBar') is True, 'public main bar or active spec differs')
    buttons = public.get('actions')
    require(type(buttons) is list and len(buttons) == 12 and all(type(r) is dict for r in buttons) and
        [r.get('button') for r in buttons] == ['ActionButton' + str(i) for i in range(1, 13)] and
        all(type(r.get('slot')) is int and 1 <= r['slot'] <= 144 for r in buttons) and
        len({r['slot'] for r in buttons}) == 12, 'twelve actual distinct main-bar assignments are required')
    native = {r[1]: r[2:] for r in rows if r[0] == active_spec}
    for r in buttons:
        expected = native.get(r['slot'] - 1)
        kind, ident = r.get('kind'), r.get('id')
        require((expected is None and kind in (None, False, '') and ident in (None, False, 0)) or
            (expected is not None and type(ident) is int and ident == expected[0] and
             {'spell': 0, 'companion': 0, 'flyout': 48, 'macro': 64, 'item': 128}.get(kind) == expected[1]),
            'one public action assignment differs from its saved native row')
    return deepcopy(buttons)


def action_packets(rows, session, since, until, slot0, *, clear=False):
    require(type(slot0) is int and 0 <= slot0 < 144 and type(clear) is bool, 'bounded native action slot is required')
    scoped = packet_rows(rows, session, since, until)
    forbidden_packets(rows, session, since, until)
    requests = [p for p in scoped if p.get('name') == ACTION]
    value = 0 if clear else ITEM_ID | (128 << 24)
    expected = [('from_client', struct.pack('<IB', value, slot0)), ('to_native', struct.pack('<BI', slot0, value))]
    matches = [[p for p in requests if p.get('direction') == d and body(p) == b] for d, b in expected]
    require(len(requests) == 2 and all(len(v) == 1 for v in matches), 'one exact modern/native action request pair is required')
    modern, native = [v[0] for v in matches]
    require(modern['time'] <= native['time'] and native['time'] - modern['time'] < 2,
        'action request pair ordering or delivery latency differs')
    return deepcopy({'slot0': slot0, 'action': value, 'modern': modern, 'native': native})


def addition_guard(before_actions, after_actions, rows, session, since, until, active_spec, public):
    action_rows(before_actions)
    action_rows(after_actions)
    require(type(active_spec) is int and active_spec in (0, 1), 'native active spec differs')
    added = [r for r in after_actions if r not in before_actions]
    require(len(added) == 1 and added[0][0] == active_spec and added[0][2:] == [ITEM_ID, 128] and
        not any(r[:2] == added[0][:2] for r in before_actions) and
        after_actions == sorted(before_actions + added, key=lambda r: (r[0], r[1])),
        'only one Hearthstone row in an empty active-spec slot may be added')
    pair = action_packets(rows, session, since, until, added[0][1])
    buttons = public_assignments(public, after_actions, active_spec)
    button = next((b for b in buttons if b['slot'] == added[0][1] + 1), None)
    require(button is not None and button.get('visible') is True and button.get('kind') == 'item' and
        type(button.get('id')) is int and button['id'] == ITEM_ID, 'actual visible placed item button differs')
    return deepcopy({**pair, 'active_spec': active_spec, 'before_actions': before_actions,
        'after_actions': after_actions, 'public': public, 'button': button,
        'checks': {'one_added_item_row': True, 'baseline_slot_absent': True,
            'exact_request_pair': True, 'actual_public_slot': True, 'all_public_assignments': True}})


def clear_guard(placement, after_actions, rows, session, since, until, public):
    require(type(placement) is dict and placement.get('action') == ITEM_ID | (128 << 24), 'exact item placement proof is required')
    typed_window(session, since, until)
    require(type(placement.get('native')) is dict and placement['native'].get('session') == session and
        finite(placement['native'].get('time')) and placement['native']['time'] <= since,
        'ordinary clear must follow its owned source placement')
    action_rows(after_actions)
    require(after_actions == placement.get('before_actions'), 'ordinary item clear must restore every saved action row')
    pair = action_packets(rows, session, since, until, placement.get('slot0'), clear=True)
    buttons = public_assignments(public, after_actions, placement.get('active_spec'))
    button = next((b for b in buttons if b['slot'] == placement['slot0'] + 1), None)
    require(button is not None and type(button.get('visible')) is bool and not button.get('kind') and
        button.get('id') in (None, False, 0), 'cleared actual public button is not empty')
    return deepcopy({**pair, 'button': button, 'all_public_assignments': True, 'saved_actions_restored': True})


def forbidden_packets(rows, session, since, until):
    scoped = packet_rows(rows, session, since, until)
    forbidden = [p for p in scoped if p.get('direction') in ('from_client', 'to_native') and
        (p.get('name') in FORBIDDEN or str(p.get('name', '')).startswith(('CMSG_PET_', 'CMSG_STABLE_')))]
    require(not forbidden, 'item drag refuses use, cast, inventory mutation, trainer or pet input')
    return {'no_forbidden_input': True}


def login_packets(rows, session, since, until):
    scoped = packet_rows(rows, session, since, until)
    relevant = [p for p in scoped if p.get('name') in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGIN_VERIFY_WORLD')]
    pairs = [('CMSG_PLAYER_LOGIN', 'from_client'), ('CMSG_PLAYER_LOGIN', 'to_native'),
        ('SMSG_LOGIN_VERIFY_WORLD', 'from_native'), ('SMSG_LOGIN_VERIFY_WORLD', 'to_client')]
    matched = [[p for p in relevant if (p.get('name'), p.get('direction')) == pair] for pair in pairs]
    require(len(relevant) == 4 and all(len(v) == 1 for v in matched), 'one complete owned modern/native login chain is required')
    modern, request, verify, delivered = [v[0] for v in matched]
    try:
        reader = Reader(body(modern))
        identity = reader.guid()
        farclip, = reader.unpack('f')
        reader.end()
    except (ValueError, IndexError, struct.error) as error:
        raise RuntimeError('modern actor2 login body cannot be parsed exactly') from error
    require(identity == (2, player_high()) and math.isfinite(farclip),
        'modern login requires actor2 GUID and a finite farclip')
    require(body(request) == bytes.fromhex('2003') and len(body(verify)) == 20 and
        body(delivered) == body(verify) + bytes(4) and
        modern['time'] <= request['time'] <= verify['time'] <= delivered['time'] and
        verify['time'] - request['time'] < 10 and delivered['time'] - verify['time'] < 2,
        'native actor2 login body, world delivery or ordering differs')
    map_id, x, y, z, orientation = struct.unpack('<i4f', body(verify))
    require(map_id == 0 and all(math.isfinite(v) for v in (x, y, z, orientation)), 'native login world pose differs')
    return deepcopy({'modern': modern, 'request': request, 'verify': verify, 'delivered': delivered,
        'world': {'map': map_id, 'position_x': x, 'position_y': y, 'position_z': z, 'orientation': orientation}})


def native_replay(rows, session, since, until, *, rest_threshold=None):
    """Replay actual native creation/update bodies; inspect every intermediate owner state."""
    scoped = packet_rows(rows, session, since, until)
    forbidden_packets(rows, session, since, until)
    packets = [p for p in scoped if p.get('direction') == 'from_native' and
        p.get('name') in ('SMSG_UPDATE_OBJECT', 'SMSG_DESTROY_OBJECT')]
    require(packets == sorted(packets, key=lambda p: p['time']), 'native object journal order differs')
    require(rest_threshold is None or type(rest_threshold) is int and 0 <= rest_threshold < REST_CAP,
        'rest threshold must be an uncapped native integer')
    objects, created, threshold, rest_state = {}, False, rest_threshold, None
    for p in packets:
        if p['name'] == 'SMSG_DESTROY_OBJECT':
            raw = body(p)
            require(len(raw) == 9 and int.from_bytes(raw[:8], 'little') != 2, 'owner destroy packet is invalid or removes actor2')
            continue
        try:
            decoded = records(body(p))
        except (ValueError, KeyError, IndexError, struct.error) as error:
            raise RuntimeError('native object packet cannot be replayed exactly') from error
        for r in decoded:
            if r['update_type'] == 3:
                require(2 not in r['removed'], 'native actor2 was removed during the drag boundary')
                continue
            guid = r['guid']
            if r['update_type'] in (1, 2):
                objects[guid] = {}
            elif guid == 2:
                require(created, 'owner update precedes its native creation')
            objects.setdefault(guid, {}).update(r.get('fields', {}))
            fields = objects[guid]
            def get(name):
                return fields.get(INDEX[name], 0)
            def pair(name):
                return get(name) | fields.get(INDEX[name] + 1, 0) << 32
            if guid != 2:
                require(not ((r.get('kind') == 3 or guid >> 52 == 0xf14) and
                    (pair('UNIT_FIELD_SUMMONEDBY') == 2 or pair('UNIT_FIELD_CREATEDBY') == 2)),
                    'native actor2-owned pet creation is forbidden')
                continue
            if r['update_type'] in (1, 2):
                require(not created and r.get('kind') == 4 and r.get('flags', {}).get('self') == 1,
                    'exactly one actor2 self-player creation is required')
                created = True
                threshold = get('PLAYER_REST_STATE_EXPERIENCE') if threshold is None else threshold
                rest_state = get('PLAYER_BYTES_2') >> 24
            require(get('UNIT_FIELD_HEALTH') == get('UNIT_FIELD_MAXHEALTH') == HEALTH and
                all(get('UNIT_FIELD_POWER' + str(i)) == 0 for i in range(1, 6)) and
                get('UNIT_FIELD_LEVEL') == 1 and get('UNIT_FIELD_BYTES_0') & 0xffff == 257 and
                get('PLAYER_XP') == 0 and get('PLAYER_NEXT_LEVEL_XP') == XP_CAP and
                not get('PLAYER_FLAGS') & 0x20 and pair('UNIT_FIELD_SUMMON') == 0 and
                get('PLAYER_REST_STATE_EXPERIENCE') == threshold and get('PLAYER_BYTES_2') >> 24 == rest_state,
                'native owner health, rage, XP, resting, summon or rest state changed')
    require(created, 'native actor2 self-player creation is absent')
    return {'owner': 2, 'health': HEALTH, 'max_health': HEALTH, 'powers': [0] * 5,
        'xp': 0, 'xp_cap': XP_CAP, 'resting': False, 'summon': 0, 'rest_threshold': threshold,
        'rest_state': rest_state, 'packets': deepcopy(packets)}

"""Pure proofs for one observed Beast Lore client auto-placement and removal."""
from copy import deepcopy
import math
import struct


SPELL = 1462
ACTION = 'CMSG_SET_ACTION_BUTTON'
PICKUP_SOURCE = {
    'build': 60895, 'source': 'local_read_only_CASC',
    'path': 'Interface/AddOns/Blizzard_ActionBar/Classic/ActionBarFrame.xml',
    'sha256': '4a4b52df7eba3dd00f1c55999c05755e607b3546249f02268d723be8a1cf8d58',
    'handler': 'OnDragStart', 'pickup': 'PickupAction(self.action);',
    'modifier': 'IsModifiedClick("PICKUPACTION")',
}
BINDING_SOURCE = {
    'build': 60895, 'source': 'local_read_only_CASC',
    'path': 'Interface/AddOns/Blizzard_FrameXML/Bindings_Cata.xml',
    'sha256': '07dc4cf9a340cd1289fdf8397261dafb018e097ca3a19f94d3dd1735fd464661',
    'binding': '<ModifiedClick action="PICKUPACTION" default="SHIFT"/>',
}


def require(value, message):
    if not value:
        raise RuntimeError(message)


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def action_rows(rows):
    require(type(rows) is list and all(type(r) is list and len(r) == 4 and
        all(type(v) is int for v in r) and r[0] in (0, 1) and 0 <= r[1] < 144 and
        0 < r[2] <= 0xffffff and 0 <= r[3] <= 255 for r in rows),
        'full saved action rows have an invalid native identity')
    require(rows == sorted(rows, key=lambda r: (r[0], r[1])) and
        len({tuple(r[:2]) for r in rows}) == len(rows), 'saved action rows are not unique and canonical')


def scoped(rows, session, since, until):
    require(type(rows) is list and type(session) is str and session and finite(since) and finite(until) and
        since <= until, 'owned action packet interval differs')
    owned = [p for p in rows if p.get('session') == session]
    require(all(finite(p.get('time')) for p in owned), 'owned action packet time is invalid')
    return [p for p in owned if since <= p['time'] <= until]


def request_pair(rows, slot0, value):
    requests = [p for p in rows if p.get('name') == ACTION]
    expected = [('from_client', struct.pack('<IB', value, slot0).hex()),
        ('to_native', struct.pack('<BI', slot0, value).hex())]
    matches = [[p for p in requests if (p.get('direction'), p.get('body')) == e] for e in expected]
    require(len(requests) == 2 and all(len(v) == 1 for v in matches),
        'one exact modern and native action request pair is required; unrelated requests are refused')
    modern, native = (v[0] for v in matches)
    require(modern['time'] <= native['time'] and native['time'] - modern['time'] < 2,
        'modern and native action request ordering differs')
    return modern, native


def public_assignments(public, rows, active_spec):
    """Verify all twelve actual main buttons against complete saved rows."""
    require(type(active_spec) is int and active_spec in (0, 1) and
        type(public) is dict and type(public.get('active_spec')) is int and
        public['active_spec'] == active_spec + 1 and public.get('frames', {}).get('MainMenuBar') is True,
        'actual public action-bar active spec or visibility differs')
    buttons = public.get('actions', [])
    require(type(buttons) is list and len(buttons) == 12 and
        [r.get('button') for r in buttons] == ['ActionButton' + str(i) for i in range(1, 13)] and
        all(type(r.get('slot')) is int and 1 <= r['slot'] <= 144 for r in buttons) and
        len({r['slot'] for r in buttons}) == 12, 'twelve actual public main-bar slots are required')
    native = {r[1]: r[2:] for r in rows if r[0] == active_spec}
    for button in buttons:
        entry = native.get(button['slot'] - 1)
        kind, ident = button.get('kind'), button.get('id')
        require((entry is None and not kind and ident in (None, False, 0)) or
            (entry is not None and type(ident) is int and ident == entry[0] and
                {'spell': 0, 'companion': 0, 'macro': 64, 'item': 128}.get(kind) == entry[1]),
            'public action assignment differs from exact saved rows')
    return buttons


def public_slot(public, rows, active_spec, slot0, value):
    buttons = public_assignments(public, rows, active_spec)
    found = [r for r in buttons if r['slot'] == slot0 + 1]
    require(len(found) == 1 and found[0].get('visible') is True and
        ((value == SPELL and found[0].get('kind') == 'spell' and found[0].get('id') == SPELL) or
         (value == 0 and not found[0].get('kind') and found[0].get('id') in (None, False, 0))),
        'actual public Beast Lore slot is absent, hidden or has another action')
    return deepcopy(found[0])


def addition_guard(before_actions, after_actions, rows, session, since, until, active_spec, public):
    """Accept unchanged actions, or exactly one evidenced engine-added1462 row."""
    action_rows(before_actions)
    action_rows(after_actions)
    packets = scoped(rows, session, since, until)
    require(type(active_spec) is int and active_spec in (0, 1), 'native activeTalentGroup differs')
    requests = [p for p in packets if p.get('name') == ACTION]
    if after_actions == before_actions:
        require(not requests, 'unchanged saved actions cannot hide an action placement or replacement')
        public_assignments(public, before_actions, active_spec)
        return None
    added = [r for r in after_actions if r not in before_actions]
    require(len(added) == 1 and added[0][0] == active_spec and added[0][2:] == [SPELL, 0] and
        not any(r[0] == active_spec and (r[1] == added[0][1] or r[2] == SPELL) for r in before_actions) and
        after_actions == sorted(before_actions + added, key=lambda r: (r[0], r[1])),
        'only one Beast Lore addition to a previously absent active-spec slot is permitted')
    slot0 = added[0][1]
    modern, native = request_pair(packets, slot0, SPELL)
    learned = [('from_native', 'SMSG_LEARNED_SPELL', struct.pack('<II', SPELL, 0).hex()),
        ('to_client', 'SMSG_LEARNED_SPELLS', struct.pack('<IIBIB', 1, 0, 0, SPELL, 0).hex())]
    deliveries = [[p for p in packets if (p.get('direction'), p.get('name'), p.get('body')) == e]
        for e in learned]
    require(all(len(v) == 1 for v in deliveries), 'owned exact Beast Lore learned delivery is required')
    native_learn, client_learn = (v[0] for v in deliveries)
    require(native_learn['time'] <= client_learn['time'] <= modern['time'] and
        client_learn['time'] - native_learn['time'] < 2,
        'action placement must follow the owned Beast Lore learned delivery')
    button = public_slot(public, after_actions, active_spec, slot0, SPELL)
    return deepcopy({'slot0': slot0, 'active_spec': active_spec, 'before_actions': before_actions,
        'after_actions': after_actions, 'modern': modern, 'native': native,
        'learned_delivery': [native_learn, client_learn], 'public': public, 'button': button,
        'checks': {'one_added_1462_row': True, 'baseline_slot_absent': True, 'exact_request_pair': True,
            'owned_learn_before_placement': True, 'actual_public_slot': True, 'all_public_assignments': True}})


def clear_guard(placement, after_actions, rows, session, since, until, public):
    """Require one paired native clear and the exact complete baseline actions."""
    require(type(placement) is dict and type(placement.get('slot0')) is int and
        0 <= placement['slot0'] < 144, 'exact pending auto-placement is required')
    action_rows(placement['before_actions'])
    action_rows(after_actions)
    require(after_actions == placement['before_actions'], 'complete original saved action rows did not restore')
    packets = scoped(rows, session, since, until)
    modern, native = request_pair(packets, placement['slot0'], 0)
    require(placement['native'].get('session') == session and finite(placement['native'].get('time')) and
        placement['native']['time'] <= since, 'clear does not follow the same owned placement')
    button = public_slot(public, after_actions, placement['active_spec'], placement['slot0'], 0)
    return deepcopy({'modern': modern, 'native': native, 'button': button,
        'checks': {'exact_clear_pair': True, 'same_placement_slot': True, 'owned_ordered_clear': True,
            'actual_public_slot_empty': True, 'all_public_assignments': True, 'full_saved_baseline': True}})

"""Reject wrong actors, hidden item use and intermediate native owner changes."""
from copy import deepcopy
from pathlib import Path
import struct
import subprocess
import sys

import pytest

from tools.client_compatibility import item_actionbar_contract as c
from tools.client_compatibility.world.buffer import Writer, player_high


def public(rows, spec=0):
    native = {r[1]: r[2:] for r in rows if r[0] == spec}
    return {'active_spec': spec + 1, 'frames': {'MainMenuBar': True}, 'actions': [
        {'button': 'ActionButton' + str(i), 'slot': i + 72, 'visible': i + 71 in native,
         'kind': {0: 'spell', 48: 'flyout', 128: 'item'}.get(native.get(i + 71, [0, None])[1], ''),
         'id': native.get(i + 71, [0])[0]} for i in range(1, 13)]}


def action_packets(slot=74, clear=False):
    value = 0 if clear else c.ITEM_ID | (128 << 24)
    return [{'session': 'scout', 'time': 10 + i * .1, 'name': c.ACTION, 'direction': d, 'body': b.hex()}
        for i, (d, b) in enumerate((('from_client', struct.pack('<IB', value, slot)),
                                   ('to_native', struct.pack('<BI', slot, value))))]


def login_packets():
    native = struct.pack('<i4f', 0, -8914.86, -135.609, 80.4425, 5.83261)
    modern = Writer().guid(2, player_high()).pack('f', 1000).finish()
    return [{'session': 'scout', 'time': 1100.1 + i * .1, 'name': n, 'direction': d, 'body': b.hex()}
        for i, (n, d, b) in enumerate((('CMSG_PLAYER_LOGIN', 'from_client', modern),
            ('CMSG_PLAYER_LOGIN', 'to_native', bytes.fromhex('2003')),
            ('SMSG_LOGIN_VERIFY_WORLD', 'from_native', native),
            ('SMSG_LOGIN_VERIFY_WORLD', 'to_client', native + bytes(4))))]


def native_packet(fields, *, guid=2, creation=True, kind=4, time=10):
    w = Writer().pack('HI', 0, 1).pack('B', 2 if creation else 0)
    octets = struct.pack('<Q', guid)
    w.pack('B', sum(bool(v) << i for i, v in enumerate(octets)))
    w.raw(bytes(v for v in octets if v))
    if creation:
        w.pack('B', kind).bits(4 if guid == 2 else 0, 8).bits(0, 24).bits(0, 6).flush()
    count = max(fields) // 32 + 1
    w.pack('B', count)
    for group in range(count):
        w.pack('I', sum(1 << (k % 32) for k in fields if k // 32 == group))
    for key in sorted(fields):
        w.pack('I', fields[key])
    return {'session': 'scout', 'time': time, 'direction': 'from_native',
        'name': 'SMSG_UPDATE_OBJECT', 'body': w.finish().hex()}


def owner_fields():
    return {c.INDEX[k]: v for k, v in {'UNIT_FIELD_HEALTH': 60, 'UNIT_FIELD_MAXHEALTH': 60,
        'UNIT_FIELD_LEVEL': 1, 'UNIT_FIELD_BYTES_0': 257, 'PLAYER_NEXT_LEVEL_XP': 400,
        'PLAYER_REST_STATE_EXPERIENCE': 24, 'PLAYER_BYTES_2': 1 << 24, 'PLAYER_FLAGS': 0}.items()}


def test_item_placement_and_clear_match_full_bar_on_actual_nonfixed_slot():
    before = [[0, 72, 88163, 0], [0, 73, 88161, 0], [1, 0, 6603, 0]]
    after = sorted(before + [[0, 74, 6948, 128]])
    placed = c.addition_guard(before, after, action_packets(), 'scout', 10, 11, 0, public(after))
    assert placed['button']['button'] == 'ActionButton3' and placed['slot0'] == 74
    cleared = c.clear_guard(placed, before, [{**r, 'time': r['time'] + 1} for r in action_packets(clear=True)],
        'scout', 11, 12, public(before))
    assert cleared['action'] == 0 and cleared['saved_actions_restored'] is True
    assert cleared['button']['visible'] is False


def test_full_public_flyout_id_matches_dropdown_native_type_and_empty_buttons_are_hidden():
    before = [[0, 72, 88163, 0], [0, 73, 33, 48]]
    bar = public(before)
    assert bar['frames']['MainMenuBar'] is True and bar['actions'][2]['visible'] is False
    assert c.public_assignments(bar, before, 0)[1]['kind'] == 'flyout'
    after = sorted(before + [[0, 74, 6948, 128]])
    placed = c.addition_guard(before, after, action_packets(), 'scout', 10, 11, 0, public(after))
    rows = [{**r, 'time': r['time'] + 1} for r in action_packets(clear=True)]
    assert c.clear_guard(placed, before, rows, 'scout', 11, 12, bar)['button']['visible'] is False


@pytest.mark.parametrize('fault', ['wrong_id', 'wrong_kind', 'wrong_native_type', 'another_slot'])
def test_flyout_requires_exact_id_type_and_every_other_slot_assignment(fault):
    rows = [[0, 72, 88163, 0], [0, 73, 33, 48]]
    bar = public(rows)
    if fault == 'wrong_id': bar['actions'][1]['id'] = 34
    elif fault == 'wrong_kind': bar['actions'][1]['kind'] = 'spell'
    elif fault == 'wrong_native_type': rows[1][3] = 0
    else:
        bar['actions'][3].update(kind='flyout', id=33, visible=True)
    with pytest.raises(RuntimeError): c.public_assignments(bar, rows, 0)


@pytest.mark.parametrize('fault', ['wrong_id', 'wrong_kind', 'wrong_slot', 'missing_visible', 'hidden_mainbar'])
def test_hidden_empty_clear_still_requires_exact_identity_and_full_saved_assignments(fault):
    before, after = [[0, 73, 33, 48]], [[0, 73, 33, 48], [0, 74, 6948, 128]]
    placed = c.addition_guard(before, after, action_packets(), 'scout', 10, 11, 0, public(after))
    bar = public(before)
    if fault == 'wrong_id': bar['actions'][2]['id'] = 6948
    elif fault == 'wrong_kind': bar['actions'][2]['kind'] = 'item'
    elif fault == 'wrong_slot': bar['actions'][2]['slot'] = 120
    elif fault == 'missing_visible': bar['actions'][2].pop('visible')
    else: bar['frames']['MainMenuBar'] = False
    with pytest.raises(RuntimeError):
        c.clear_guard(placed, before, [{**r, 'time': r['time'] + 1} for r in action_packets(clear=True)],
            'scout', 11, 12, bar)


def test_grid_source_exact_installed_bytes_and_stock_visibility_snippets():
    import hashlib
    import json
    path = Path.home() / '.local/share/trinity-client442-lab/reference/local-60895/ui' / c.GRID_SOURCE['path']
    metadata = json.loads(path.with_suffix(path.suffix + '.source.json').read_text())
    assert metadata == {k: c.GRID_SOURCE[k] for k in ('build', 'source', 'path', 'sha256')}
    assert hashlib.sha256(path.read_bytes()).hexdigest() == c.GRID_SOURCE['sha256']
    assert all(snippet in path.read_text() for snippet in c.GRID_SOURCE['snippets'])


@pytest.mark.parametrize('fault', ['wrong_item', 'wrong_type', 'wrong_slot', 'duplicate', 'extra_native',
    'bool_time', 'nan_time', 'bool_slot', 'reverse', 'late', 'foreign', 'extra_cast', 'wrong_public', 'hidden', 'other_saved'])
def test_item_drag_refuses_packet_public_or_saved_drift(fault):
    before, after, rows = [], [[0, 74, 6948, 128]], action_packets()
    bar = public(after)
    if fault == 'wrong_item': rows[1]['body'] = struct.pack('<BI', 74, 6949 | 128 << 24).hex()
    elif fault == 'wrong_type': rows[0]['body'] = struct.pack('<IB', 6948, 74).hex()
    elif fault == 'wrong_slot': rows[1]['body'] = struct.pack('<BI', 75, 6948 | 128 << 24).hex()
    elif fault == 'duplicate': rows.append(deepcopy(rows[0]))
    elif fault == 'extra_native': rows.append({**rows[1], 'body': struct.pack('<BI', 90, 6603).hex()})
    elif fault == 'bool_time': rows[0]['time'] = True
    elif fault == 'nan_time': rows[0]['time'] = float('nan')
    elif fault == 'bool_slot': after[0][1] = True
    elif fault == 'reverse': rows[0]['time'] = 10.2
    elif fault == 'late': rows[1]['time'] = 12.2
    elif fault == 'foreign': rows[1]['session'] = 'other'
    elif fault == 'extra_cast': rows.append({**rows[1], 'name': 'CMSG_CAST_SPELL', 'body': ''})
    elif fault == 'wrong_public': bar['actions'][0]['kind'], bar['actions'][0]['id'] = 'spell', 6603
    elif fault == 'hidden': bar['actions'][2]['visible'] = False
    else: after.append([1, 10, 6603, 0])
    with pytest.raises(RuntimeError):
        c.addition_guard(before, after, rows, 'scout', 10, 13, 0, bar)


@pytest.mark.parametrize('name', sorted(c.FORBIDDEN) + ['CMSG_STABLE_PET', 'CMSG_PET_UNKNOWN_ACTION'])
def test_every_forbidden_input_family_is_refused(name):
    with pytest.raises(RuntimeError):
        c.forbidden_packets([{'session': 'scout', 'time': 10, 'name': name, 'direction': 'to_native'}], 'scout', 9, 11)


@pytest.mark.parametrize('name', ['CMSG_AUTO_EQUIP_ITEM', 'CMSG_AUTO_EQUIP_ITEM_SLOT', 'CMSG_AUTO_STORE_BAG_ITEM'])
@pytest.mark.parametrize('direction', ['from_client', 'to_native'])
def test_installed_modern_inventory_aliases_are_rejected_as_attempts(name, direction):
    # native_bridge/inventory_requests.cpp:75,81,87 translates these modern names.
    with pytest.raises(RuntimeError):
        c.forbidden_packets([{'session': 'scout', 'time': 10, 'name': name, 'direction': direction,
            'body': ''}], 'scout', 9, 11)


def test_login_positive_guid_body_and_native_world_delivery():
    result = c.login_packets(login_packets(), 'scout', 1099, 1101)
    assert result['request']['body'] == '2003' and result['world']['map'] == 0


@pytest.mark.parametrize('fault', ['modern_guid', 'modern_high', 'farclip_nan', 'modern_trailing',
    'native_guid', 'native_size', 'native_nan', 'delivery', 'duplicate', 'bool_time', 'foreign'])
def test_login_refuses_other_actor_or_unparsed_body(fault):
    rows = login_packets()
    if fault in ('modern_guid', 'modern_high', 'farclip_nan'):
        rows[0]['body'] = Writer().guid(3 if fault == 'modern_guid' else 2,
            0 if fault == 'modern_high' else player_high()).pack('f', float('nan') if fault == 'farclip_nan' else 1000).finish().hex()
    elif fault == 'modern_trailing': rows[0]['body'] += '00'
    elif fault == 'native_guid': rows[1]['body'] = '2002'
    elif fault == 'native_size': rows[2]['body'] += '00'
    elif fault == 'native_nan':
        rows[2]['body'] = struct.pack('<i4f', 0, float('nan'), 0, 0, 0).hex()
        rows[3]['body'] = rows[2]['body'] + '00000000'
    elif fault == 'delivery': rows[3]['body'] = rows[2]['body']
    elif fault == 'duplicate': rows.append(deepcopy(rows[1]))
    elif fault == 'bool_time': rows[0]['time'] = True
    else: rows[1]['session'] = 'other'
    with pytest.raises(RuntimeError): c.login_packets(rows, 'scout', 1099, 1101)


def test_actual_native_parser_replays_creation_and_afk_change_without_rest_tick():
    rows = [native_packet(owner_fields()), native_packet({c.INDEX['PLAYER_FLAGS']: 2}, creation=False, time=10.1)]
    proof = c.native_replay(rows, 'scout', 10, 11, rest_threshold=24)
    assert proof['health'] == proof['max_health'] == 60 and proof['resting'] is False
    assert len(proof['packets']) == 2


@pytest.mark.parametrize('field,value', [('UNIT_FIELD_HEALTH', 59), ('UNIT_FIELD_MAXHEALTH', 61),
    ('UNIT_FIELD_POWER1', 1), ('UNIT_FIELD_POWER5', 1), ('PLAYER_XP', 1), ('PLAYER_NEXT_LEVEL_XP', 401),
    ('PLAYER_FLAGS', 32), ('UNIT_FIELD_SUMMON', 16), ('PLAYER_REST_STATE_EXPERIENCE', 25), ('PLAYER_BYTES_2', 2 << 24)])
def test_temporary_native_changes_are_refused_even_if_later_restored(field, value):
    rows = [native_packet(owner_fields()), native_packet({c.INDEX[field]: value}, creation=False, time=10.1),
        native_packet({c.INDEX[field]: owner_fields().get(c.INDEX[field], 0)}, creation=False, time=10.2)]
    with pytest.raises(RuntimeError): c.native_replay(rows, 'scout', 10, 11)


def test_owned_pet_creation_and_duplicate_player_creation_are_refused():
    pet_guid = (0xf14 << 52) | 16
    pet = native_packet({c.INDEX['UNIT_FIELD_SUMMONEDBY']: 2}, guid=pet_guid, kind=3, time=10.1)
    for rows in ([native_packet(owner_fields()), pet], [native_packet(owner_fields()), native_packet(owner_fields(), time=10.1)]):
        with pytest.raises(RuntimeError): c.native_replay(rows, 'scout', 10, 11)


@pytest.mark.parametrize('fault', ['foreign_session', 'future_placement', 'bool_placement_time'])
def test_clear_is_bound_to_one_prior_owned_placement(fault):
    before, after = [], [[0, 74, 6948, 128]]
    placed = c.addition_guard(before, after, action_packets(), 'scout', 10, 11, 0, public(after))
    if fault == 'foreign_session': placed['native']['session'] = 'other'
    elif fault == 'future_placement': placed['native']['time'] = 12
    else: placed['native']['time'] = True
    rows = [{**r, 'time': r['time'] + 1} for r in action_packets(clear=True)]
    with pytest.raises(RuntimeError): c.clear_guard(placed, before, rows, 'scout', 11, 12, public(before))


def test_native_item_resources_require_exact_owned_guid_count_and_backpack_slot():
    empty = {'guid': 0, 'id': 0, 'count': 0}
    resources = {'equipment': [deepcopy(empty) for _ in range(19)], 'backpack': [deepcopy(empty) for _ in range(16)],
        'bags': [[deepcopy(empty) for _ in range(36)] for _ in range(4)]}
    resources['backpack'][0] = {'guid': c.ITEM_NATIVE_GUID, 'id': 6948, 'count': 1}
    assert c.item_resources(resources)['guid'] == (0x4000 << 48) | 41
    for fault in ('guid', 'count', 'slot'):
        changed = deepcopy(resources)
        if fault == 'guid': changed['backpack'][0]['guid'] += 1
        elif fault == 'count': changed['backpack'][0]['count'] = True
        else: changed['backpack'][0], changed['backpack'][1] = changed['backpack'][1], changed['backpack'][0]
        with pytest.raises(RuntimeError): c.item_resources(changed)


def test_all_core_imports_exclude_live_runtime_sql_ui_and_crypto_dependencies():
    script = '''
import importlib, sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('Crypto', 'google', 'PIL', 'pymysql', 'requests',
            'tools.client_compatibility.interaction_', 'tools.client_compatibility.lab_runtime')):
            raise AssertionError('live dependency imported: ' + fullname)
sys.meta_path.insert(0, Block())
for name in ('item_actionbar_contract', 'item_actionbar_preservation', 'item_actionbar_sources'):
    importlib.import_module('tools.client_compatibility.' + name)
'''
    subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[4], check=True,
        capture_output=True, env={**__import__('os').environ, 'PYTHONDONTWRITEBYTECODE': '1'})

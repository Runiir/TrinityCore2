"""Delivered actor2 inventory GUID proof uses fully consumed sparse wire masks."""
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess

import pytest

from tools.client_compatibility import bag_swap_projection as p
from tools.client_compatibility.world.buffer import Writer, player_high


def sparse_mask(writer, fields):
    # inventory_updates.cpp write_mask<46>: low presence32, high presence14,
    # then one MSB-first32 part for each nonempty array index.
    parts = [sum(1 << (field % 32) for field in fields if field // 32 == index) for index in range(46)]
    presence = sum(1 << index for index, value in enumerate(parts) if value)
    writer.pack('I', presence & 0xffffffff).bits(presence >> 32, 14)
    for part in parts:
        if part:
            writer.bits(part, 32)
    return writer.flush()


def inventory_block(*, swapped=True, owner=(2, player_high()), roots=1 << 7,
        fields=(131, 167, 168), guids=None, visibility=1, fragment=0, layout=3,
        kind=0, trailing=b''):
    data = Writer().pack('BBBI', visibility, fragment, layout, roots)
    sparse_mask(data, fields)
    if guids is None:
        guids = [(33 if swapped else 41, p.ITEM_HIGH), (41 if swapped else 33, p.ITEM_HIGH)]
    for low, high in guids:
        data.guid(low, high)
    body = data.raw(trailing).finish()
    return Writer().pack('B', kind).guid(*owner).pack('I', len(body)).raw(body).finish()


def packet(*blocks, map_id=0, trailing=b'', destroyed=None):
    if not blocks:
        blocks = (inventory_block(),)
    data = b''.join(blocks)
    writer = Writer().pack('HI', map_id, len(blocks)).bits(1, 1).bits(destroyed is not None, 1).flush()
    if destroyed is not None:
        writer.pack('HI', len(destroyed), len(destroyed))
        for guid in destroyed:
            writer.guid(*guid)
    return writer.pack('I', len(data)).raw(data).raw(trailing).finish()


def row(raw=None, *, time=10, session='scout', direction='to_client', name='SMSG_UPDATE_OBJECT'):
    return {'session': session, 'time': time, 'direction': direction, 'name': name,
        'body': (packet() if raw is None else raw).hex()}


@pytest.mark.parametrize('swapped', [True, False])
def test_exact_two_public_backpack_children_keep_both_full_modern_item_guids(swapped, monkeypatch):
    def no_git(*args, **kwargs):
        raise AssertionError('packet projection must not query git')
    monkeypatch.setattr(p.subprocess, 'check_output', no_git)
    raw = packet(inventory_block(swapped=swapped))
    expected = {'35': [33 if swapped else 41, p.ITEM_HIGH], '36': [41 if swapped else 33, p.ITEM_HIGH]}
    assert p.delta(raw) == expected
    delivery = row(raw)
    proof = p.delivered_slots([delivery], 'scout', 9, 11, swapped=swapped)
    assert proof['public_slots'] == expected
    assert proof['delivery'] == delivery
    assert proof['native_sql_slots'] == [23, 24]
    assert proof['rendered_guid_claim'] is False


@pytest.mark.parametrize('swapped', [True, False])
def test_installed_bridge_codec_two_slot_delta_matches_the_strict_public_parser(swapped):
    from tools.client_compatibility.world.objects import INDEX
    start = INDEX['PLAYER_FIELD_INV_SLOT_HEAD']
    low = [33, 41] if swapped else [41, 33]
    fields = {start + slot * 2 + part: (guid if part == 0 else 0x40000000)
        for slot, guid in zip((23, 24), low) for part in (0, 1)}
    executable = os.environ.get('CLIENT442_CODEC')
    if not executable:
        pytest.skip('set CLIENT442_CODEC to the existing standalone bridge codec')
    request = {'op': 'inventory_update', 'snapshot': {'guid': 2, 'fields': fields}, 'changed': fields}
    reply = subprocess.run([executable, str(Path(p.__file__).parent / 'world')],
        input=json.dumps(request) + '\n', text=True, capture_output=True, timeout=5, check=True)
    answer = json.loads(reply.stdout)
    assert 'error' not in answer
    actual = bytes.fromhex(answer['result'])
    assert actual == inventory_block(swapped=swapped)
    assert p.delta(packet(actual)) == {'35': [low[0], p.ITEM_HIGH], '36': [low[1], p.ITEM_HIGH]}


@pytest.mark.parametrize('owner,roots', [((3, player_high()), 1 << 7), ((2, 0), 1 << 7),
    ((2, p.ITEM_HIGH), 1 << 7), ((2, player_high()), 0)])
def test_wrong_owner_high_or_root_cannot_supply_the_owned_delivery(owner, roots):
    raw = packet(inventory_block(owner=owner, roots=roots))
    assert p.delta(raw) is None
    with pytest.raises(RuntimeError, match='one exact delivered'):
        p.delivered_slots([row(raw)], 'scout', 9, 11, swapped=True)


@pytest.mark.parametrize('additional_root', [0, 1, 6, 8])
@pytest.mark.parametrize('same_packet', [True, False])
def test_owner_inventory_combined_with_another_root_cannot_hide_beside_valid_delivery(additional_root, same_packet):
    malformed = inventory_block(roots=(1 << 7) | (1 << additional_root))
    rows = [row(packet(inventory_block(), malformed))] if same_packet else [row(), row(packet(malformed), time=10.1)]
    with pytest.raises(RuntimeError, match='unsupported owned inventory roots'):
        p.delivered_slots(rows, 'scout', 9, 11, swapped=True)


@pytest.mark.parametrize('fields', [(131, 169), (131,), (169,), (131, 277)])
@pytest.mark.parametrize('same_packet', [True, False])
def test_other_owner_inventory_slot_or_bare_parent_cannot_hide_beside_exact_pair(fields, same_packet):
    unrelated = inventory_block(fields=fields, guids=[(99, p.ITEM_HIGH)])
    rows = [row(packet(inventory_block(), unrelated))] if same_packet else [row(), row(packet(unrelated), time=10.1)]
    with pytest.raises(RuntimeError, match='other active-player fields'):
        p.delivered_slots(rows, 'scout', 9, 11, swapped=True)


@pytest.mark.parametrize('fields,payload', [((0, 31), Writer().pack('Q', 321).finish()),
    ((38, 50), Writer().pack('f', 1.0).finish()), ((320, 321), Writer().pack('I', 0).finish())])
@pytest.mark.parametrize('same_packet', [True, False])
def test_inventory_free_ancillary_coinage_combat_and_buyback_roots_do_not_hide_or_duplicate_pair(fields, payload, same_packet):
    ancillary = inventory_block(fields=fields, guids=[], trailing=payload)
    assert p.delta(packet(ancillary)) is None
    rows = [row(packet(inventory_block(), ancillary))] if same_packet else [row(), row(packet(ancillary), time=10.1)]
    assert p.delivered_slots(rows, 'scout', 9, 11, swapped=True)['public_slots'] == {
        '35': [33, p.ITEM_HIGH], '36': [41, p.ITEM_HIGH]}


@pytest.mark.parametrize('fields', [(131, 167), (131, 168), (167, 168), (31, 131, 167, 168),
    (131, 167, 168, 169)])
def test_both_children_parent_and_no_extra_active_player_fields_are_required(fields):
    raw = packet(inventory_block(fields=fields))
    with pytest.raises(RuntimeError, match='other active-player fields'):
        p.delta(raw)


@pytest.mark.parametrize('guids', [[(33, 0), (41, p.ITEM_HIGH)], [(33, player_high()), (41, p.ITEM_HIGH)],
    [(33, p.ITEM_HIGH), (41, p.ITEM_HIGH + 1)], [(33, p.ITEM_HIGH), (33, p.ITEM_HIGH)],
    [(32, p.ITEM_HIGH), (41, p.ITEM_HIGH)], [(0, 0), (41, p.ITEM_HIGH)]])
def test_both_delivered_item_guid_lows_and_high_types_are_exact(guids):
    with pytest.raises(RuntimeError, match='item GUID identities'):
        p.delta(packet(inventory_block(guids=guids)))


@pytest.mark.parametrize('header', [{'visibility': 0}, {'fragment': 1}, {'layout': 2}])
def test_actor_inventory_root_layout_matches_the_pinned_bridge(header):
    with pytest.raises(RuntimeError, match='root header'):
        p.delta(packet(inventory_block(**header)))


@pytest.mark.parametrize('raw', [packet(inventory_block(trailing=b'x')), packet(trailing=b'x'),
    packet()[:-1], packet(inventory_block(guids=[(33, p.ITEM_HIGH)])),
    packet(inventory_block(kind=1)), packet(map_id=1)])
def test_child_block_envelope_and_guid_rows_are_fully_consumed(raw):
    with pytest.raises(RuntimeError): p.delta(raw)


def test_duplicate_owned_two_slot_blocks_in_one_delivery_are_refused():
    raw = packet(inventory_block(), inventory_block())
    with pytest.raises(RuntimeError, match='duplicate owned inventory projection'):
        p.delta(raw)


def test_duplicate_owned_delivery_packets_are_refused():
    delivery = row()
    with pytest.raises(RuntimeError, match='one exact delivered'):
        p.delivered_slots([delivery, deepcopy(delivery)], 'scout', 9, 11, swapped=True)


@pytest.mark.parametrize('fault', ['wrong_direction', 'wrong_name', 'wrong_session', 'before_window',
    'after_window', 'bool_time', 'nan_time', 'opposite_swap_state'])
def test_delivered_proof_requires_one_correct_state_in_the_owned_typed_window(fault):
    delivery = row()
    if fault == 'wrong_direction': delivery['direction'] = 'from_native'
    elif fault == 'wrong_name': delivery['name'] = 'SMSG_LOGIN_VERIFY_WORLD'
    elif fault == 'wrong_session': delivery['session'] = 'other'
    elif fault == 'before_window': delivery['time'] = 8.99
    elif fault == 'after_window': delivery['time'] = 11.01
    elif fault == 'bool_time': delivery['time'] = True
    elif fault == 'nan_time': delivery['time'] = float('nan')
    else: delivery['body'] = packet(inventory_block(swapped=False)).hex()
    with pytest.raises(RuntimeError):
        p.delivered_slots([delivery], 'scout', 9, 11, swapped=True)


@pytest.mark.parametrize('boundary', [9, 11])
def test_owned_delivery_at_either_exact_window_boundary_is_included(boundary):
    assert p.delivered_slots([row(time=boundary)], 'scout', 9, 11, swapped=True)['delivery']['time'] == boundary


def test_separate_foreign_sized_blocks_and_other_removed_guids_do_not_claim_owned_projection():
    foreign = inventory_block(owner=(3, player_high()), trailing=b'uninterpreted foreign data')
    raw = packet(foreign, inventory_block(), destroyed=[(3, player_high())])
    assert p.delivered_slots([row(raw)], 'scout', 9, 11, swapped=True)['public_slots']['35'] == [33, p.ITEM_HIGH]


def test_owner_removal_cannot_be_hidden_beside_a_valid_owned_inventory_block():
    with pytest.raises(RuntimeError, match='owner removed'):
        p.delta(packet(inventory_block(), destroyed=[(2, player_high())]))


@pytest.mark.parametrize('low', [33, 41])
def test_either_occupied_item_removal_cannot_be_hidden_beside_valid_guid_projection(low):
    raw = packet(inventory_block(), destroyed=[(low, p.ITEM_HIGH)])
    with pytest.raises(RuntimeError, match='occupied swap item removed'):
        p.delivered_slots([row(raw)], 'scout', 9, 11, swapped=True)


@pytest.mark.parametrize('swapped', [0, 1, None])
def test_swap_state_flag_does_not_equate_native_numeric_values_with_boolean_state(swapped):
    with pytest.raises(RuntimeError, match='typed occupied swap state'):
        p.delivered_slots([row()], 'scout', 9, 11, swapped=swapped)


REQUIRED_SHARED_SOURCES = (
    'tools/client_compatibility/item_actionbar_contract.py',
    'tools/client_compatibility/item_actionbar_preservation.py',
    'tools/client_compatibility/world/buffer.py',
    'tools/client_compatibility/world/native_objects.py',
    'tools/client_compatibility/world/native_transport.py',
    'tools/client_compatibility/native_bridge/protocol.cpp',
    'tools/client_compatibility/native_bridge/buffer.cpp',
    'tools/client_compatibility/native_bridge/buffer.hpp',
)

from tools.client_compatibility.bag_swap_failed_evidence import PUBLICATION_DEPENDENCIES


def source_fixture(tmp_path, monkeypatch):
    relatives = list(p.SOURCE_FILES) + list(PUBLICATION_DEPENDENCIES) + ['tools/client_compatibility/bag_swap_projection.py',
        'tools/client_compatibility/bag_swap_contract.py',
        'tools/client_compatibility/world/tests/test_bag_swap_projection.py',
        'experiments/configs/client_harness/442_bag_swap_roundtrip_v1.json']
    committed = {}
    for relative in relatives:
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        committed[relative] = ('synthetic committed bytes for ' + relative).encode()
        path.write_bytes(committed[relative])
    def git_show(command, *, cwd):
        assert command[:2] == ['git', 'show'] and len(command) == 3 and cwd == tmp_path
        assert command[2].startswith('HEAD:')
        return committed[command[2].removeprefix('HEAD:')]
    monkeypatch.setattr(p.subprocess, 'check_output', git_show)
    return committed


def test_source_identities_bind_shared_contract_native_parser_and_modern_guid_serialization(tmp_path, monkeypatch):
    committed = source_fixture(tmp_path, monkeypatch)
    identities = p.source_identities(tmp_path)
    paths = {str(Path(r['path']).relative_to(tmp_path)) for r in identities}
    assert set(REQUIRED_SHARED_SOURCES) <= paths
    assert set(PUBLICATION_DEPENDENCIES) <= paths
    assert paths == set(committed)
    for identity in identities:
        relative = str(Path(identity['path']).relative_to(tmp_path))
        assert identity['sha256'] == hashlib.sha256(committed[relative]).hexdigest()


@pytest.mark.parametrize('relative', (*REQUIRED_SHARED_SOURCES, *PUBLICATION_DEPENDENCIES))
def test_changed_shared_dependency_cannot_reuse_other_committed_source_identities(relative, tmp_path, monkeypatch):
    source_fixture(tmp_path, monkeypatch)
    (tmp_path / relative).write_bytes(b'changed uncommitted bytes')
    with pytest.raises(RuntimeError, match='actual committed HEAD bytes'):
        p.source_identities(tmp_path)

"""Exact retained idle cycle and exclusive, conditional ordinary restoration."""
from copy import deepcopy
import json
import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_bag_swap_idle_housekeeping as h
from tools.client_compatibility.world.tests.test_item_actionbar_contract import native_packet


def cycle():
    owner, physical = 'c6195b73', '04aa8d2f'
    shapes = [('CMSG_STAND_STATE_CHANGE', 'from_client', '01', 1791421429.6256447),
        ('CMSG_STANDSTATECHANGE', 'to_native', '01000000', 1791421429.6257572),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', '01', 1791421429.6262417),
        ('SMSG_STAND_STATE_UPDATE', 'to_client', '0100000000', 1791421429.626324)]
    rows = [dict(session=owner, name=n, direction=d, body=b, time=t) for n, d, b, t in shapes]
    rows.append(dict(session=owner, name='SMSG_UPDATE_OBJECT', direction='from_native', time=1791421429.6353147,
        body='0000010000000001020500000000000000201022000000000000000010003100000001000000000000000000000002000000'))
    events = []
    for row in rows:
        native = row['direction'] in ('to_native', 'from_native')
        events.append(dict(event='native_packet' if native else 'modern_packet', session=owner if native or row['name'] == 'SMSG_STAND_STATE_UPDATE' else physical,
            name=row['name'], direction=row['direction'], bytes=len(bytes.fromhex(row['body'])), time=row['time'] - .00001))
    events += [dict(event='modern_packet', session=owner, name='CMSG_CHAT_MESSAGE_AFK', direction='from_client',
        bytes=5, time=1791421429.6257935), dict(event='native_packet', session=owner, name='CMSG_MESSAGECHAT_AFK',
        direction='to_native', bytes=5, time=1791421429.6258457)]
    events.sort(key=lambda r: r['time'])
    return rows, events


def idle():
    rows, events = cycle()
    return h.automatic_idle(rows, events, 'c6195b73', '04aa8d2f', 1791421143.6354768, 1791421702, original={'2': {'61': 49, '68': 0, '73': 0, '77': 0, '148': 0}})


def test_actual_retained_idle_native_sparse_effect_and_owner_chat_metadata():
    proof = idle()
    assert proof['automatic_owner_update']['fields'] == {'68': 1, '148': 2}
    assert proof['afk_body_retained'] is False
    assert all('body' not in row for row in proof['afk_metadata'])
    assert proof['afk_metadata'][0]['session'] == 'c6195b73'


def test_actual_packed_bytes2_upper_flags_preserve_unsheathed_original_pose():
    row = native_packet({h.INDEX['UNIT_FIELD_BYTES_1']: 0,
        h.INDEX['UNIT_FIELD_BYTES_2']: 285212672, h.INDEX['PLAYER_FLAGS']: 0})
    assert h.original_pose([row]) == {'pose': {'stand': 0, 'sheath': 0}, 'afk': False}
    fields = h.original_objects([row])
    assert fields['2'][str(h.INDEX['UNIT_FIELD_BYTES_2'])] == 285212672
    changed = native_packet({h.INDEX['UNIT_FIELD_BYTES_2']: 285212928}, creation=False)
    with pytest.raises(RuntimeError): h.native_history([changed], fields)


@pytest.mark.parametrize('fault', ['health', 'unchanged_aux', 'owner_recreated', 'owner_removed', 'item_field', 'item_removed'])
def test_complete_native_history_rejects_other_owner_and_item_changes(fault):
    original = {'2': {'61': 49, '68': 0, '73': 0, '77': 0, '148': 0, '18': 60},
        str((0x4000 << 48) | 41): {'0': 1}}
    if fault == 'health': row = native_packet({18: 59}, creation=False)
    elif fault == 'unchanged_aux': row = native_packet({61: 50, 68: 1, 148: 2}, creation=False)
    elif fault == 'owner_recreated': row = native_packet({68: 1}, creation=True)
    elif fault == 'owner_removed': row = dict(name='SMSG_UPDATE_OBJECT', direction='from_native', body='00000100000003010000000102')
    elif fault == 'item_field': row = native_packet({0: 2}, guid=(0x4000 << 48) | 41, creation=False)
    elif fault == 'item_removed': row = dict(name='SMSG_UPDATE_OBJECT', direction='from_native', body='0000010000000301000000c1290040')
    with pytest.raises(RuntimeError): h.native_history([row], original)


@pytest.mark.parametrize('name,size', list(h.IGNORED_QUERIES.items()))
@pytest.mark.parametrize('fault', [None, 'forwarded', 'wrong_bytes', 'duplicate', 'foreign', 'late_drop'])
def test_metadata_only_idle_queries_require_actual_ignored_pair(name, size, fault):
    rows, events = cycle()
    query = [dict(event='modern_packet', session='c6195b73', direction='from_client', name=name, bytes=size, time=1791421600),
        dict(event='unmapped_client_packet', session='c6195b73', name=name, bytes=size, time=1791421600.0001)]
    if fault == 'forwarded': query[1].update(event='native_packet', direction='to_native')
    elif fault == 'wrong_bytes': query[0]['bytes'] += 1
    elif fault == 'duplicate': query.append(deepcopy(query[0]))
    elif fault == 'foreign': query[0]['session'] = '04aa8d2f'
    elif fault == 'late_drop': query[1]['time'] += 1
    events += query
    events.sort(key=lambda r: r['time'])
    if fault:
        with pytest.raises(RuntimeError): h.automatic_idle(rows, events, 'c6195b73', '04aa8d2f', 1791421143.6354768, 1791421702, original={'2': {'61': 49, '68': 0, '73': 0, '77': 0, '148': 0}})
    else:
        assert h.automatic_idle(rows, events, 'c6195b73', '04aa8d2f', 1791421143.6354768, 1791421702, original={'2': {'61': 49, '68': 0, '73': 0, '77': 0, '148': 0}})['ignored_query_metadata'] == query


@pytest.mark.parametrize('fault', [None, 'bytes', 'foreign', 'missing_native', 'duplicate', 'late_native'])
def test_observed_latency_metadata_has_exact_two_stream_shapes(fault):
    rows = [dict(session='04aa8d2f', direction='from_client', name='CMSG_PING', bytes=8, time=1791421162.0816436, event='modern_packet'),
        dict(session='c6195b73', direction='from_client', name='CMSG_PING', bytes=8, time=1791421168.6112497, event='modern_packet'),
        dict(session='c6195b73', direction='to_native', name='CMSG_PING', bytes=8, time=1791421168.611436, event='native_packet')]
    if fault == 'bytes': rows[0]['bytes'] = 9
    elif fault == 'foreign': rows[0]['session'] = 'other'
    elif fault == 'missing_native': rows.pop()
    elif fault == 'duplicate': rows.append(deepcopy(rows[0]))
    elif fault == 'late_native': rows[-1]['time'] += 1
    if fault:
        with pytest.raises(RuntimeError): h.ping_metadata(rows, 'c6195b73', '04aa8d2f')
    else: assert h.ping_metadata(rows, 'c6195b73', '04aa8d2f') == rows


def test_genuine_repeated_ticket_query_has_separate_exact_ignored_pair():
    name = 'CMSG_GM_TICKET_GET_CASE_STATUS'
    rows = [dict(event=event, session='c6195b73', name=name, bytes=0, time=when, **extra)
        for event, when, extra in [('modern_packet', 1791421732.167396, {'direction': 'from_client'}),
            ('unmapped_client_packet', 1791421732.167465, {}),
            ('modern_packet', 1791422332.204763, {'direction': 'from_client'}),
            ('unmapped_client_packet', 1791422332.2048, {})]]
    assert h.ignored_queries(rows, 'c6195b73') == rows
    with pytest.raises(RuntimeError): h.ignored_queries(rows[:-1], 'c6195b73')


@pytest.mark.parametrize('fault', ['movement', 'swap', 'login', 'repeat_sit', 'late_sit', 'target',
    'body', 'native_body', 'missing_delivery', 'foreign_metadata', 'physical_afk', 'afk_bytes',
    'afk_repeat', 'closed_session', 'flags', 'recreated_owner'])
def test_idle_gap_refuses_other_input_or_unbound_native_metadata(fault):
    rows, events = cycle()
    if fault in ('movement', 'swap', 'login', 'target'):
        rows.append(dict(rows[0], name={'movement': 'CMSG_MOVE_HEARTBEAT', 'swap': 'CMSG_SWAP_INV_ITEM',
            'login': 'CMSG_PLAYER_LOGIN', 'target': 'CMSG_SET_SELECTION'}[fault], body='00', time=1791421430))
    elif fault == 'repeat_sit': rows.append(deepcopy(rows[0]))
    elif fault == 'late_sit': rows[-2]['time'] += 4
    elif fault == 'body': rows[0]['body'] = '00'
    elif fault == 'native_body': rows[1]['body'] = '0100000000'
    elif fault == 'missing_delivery': del rows[3]
    elif fault == 'foreign_metadata': events[0]['session'] = 'other'
    elif fault == 'physical_afk': next(r for r in events if r['name'] == 'CMSG_CHAT_MESSAGE_AFK')['session'] = '04aa8d2f'
    elif fault == 'afk_bytes': next(r for r in events if r['name'] == 'CMSG_CHAT_MESSAGE_AFK')['bytes'] = 0
    elif fault == 'afk_repeat': events.append(deepcopy(next(r for r in events if r['name'] == 'CMSG_CHAT_MESSAGE_AFK')))
    elif fault == 'closed_session': events.append(dict(event='native_stream_closed', session='c6195b73', time=1791421500))
    elif fault == 'flags': rows[-1] = dict(native_packet({68: 1, 148: 3}, creation=False, time=1791421429.6353147), session='c6195b73')
    elif fault == 'recreated_owner': rows[-1] = dict(native_packet({68: 1, 148: 2}, creation=True, time=1791421429.6353147), session='c6195b73')
    with pytest.raises(RuntimeError):
        h.automatic_idle(rows, events, 'c6195b73', '04aa8d2f', 1791421143.6354768, 1791421702, original={'2': {'61': 49, '68': 0, '73': 0, '77': 0, '148': 0}})


def restoration(with_afk=True):
    gap = idle()
    rows, events = cycle()
    start = 1791421800
    shapes = [('CMSG_STAND_STATE_CHANGE', 'from_client', '00'), ('CMSG_STANDSTATECHANGE', 'to_native', '00000000'),
        ('SMSG_STAND_STATE_UPDATE', 'from_native', '00'), ('SMSG_STAND_STATE_UPDATE', 'to_client', '0000000000')]
    restored = [dict(session='c6195b73', name=n, direction=d, body=b, time=start + .1 + i * .01) for i, (n, d, b) in enumerate(shapes)]
    updates = [dict(native_packet({68: 0, 148: 2 if with_afk else 0}, creation=False, time=start + .15), session='c6195b73')]
    for row in restored:
        native = row['direction'] in ('to_native', 'from_native')
        events.append(dict(event='native_packet' if native else 'modern_packet', session='c6195b73' if native or row['name'] == 'SMSG_STAND_STATE_UPDATE' else '04aa8d2f',
            name=row['name'], direction=row['direction'], bytes=len(bytes.fromhex(row['body'])), time=row['time'] - .00001))
    inputs = [dict(kind='stand', input={'kind': 'key', 'value': 'x', 'hold': .4}, started_at=start,
        finished_at=start + 1, input_replayed=False, preflight={'native_state': {**h.ORIGINAL, 'pose': {'stand': 1, 'sheath': 0}, 'afk': True}})]
    if with_afk:
        inputs.append(dict(kind='afk', input={'kind': 'chat', 'value': '/afk'}, started_at=start + 2,
            finished_at=start + 3, input_replayed=False, preflight={'native_state': {**h.ORIGINAL, 'afk': True}}))
        events += [dict(event='modern_packet', session='c6195b73', name='CMSG_CHAT_MESSAGE_AFK', direction='from_client', bytes=5, time=start + 2.1),
            dict(event='native_packet', session='c6195b73', name='CMSG_MESSAGECHAT_AFK', direction='to_native', bytes=5, time=start + 2.11)]
        updates.append(dict(native_packet({148: 0}, creation=False, time=start + 2.2), session='c6195b73'))
    return {'automatic_idle': gap}, rows + restored + updates, events, inputs, start + 4


@pytest.mark.parametrize('with_afk', [True, False])
def test_cleanup_has_exact_native_effect_and_only_necessary_afk(with_afk):
    proof = h.cleanup_history(*restoration(with_afk))
    assert len(proof['restored_afk_metadata']) == (2 if with_afk else 0)


@pytest.mark.parametrize('fault', ['replay', 'missing_native', 'foreign_afk', 'wrong_input', 'unneeded_afk',
    'flags_unrestored', 'later_move', 'wrong_preflight'])
def test_cleanup_refuses_unattributed_or_unrestored_input(fault):
    old, rows, events, inputs, until = restoration()
    if fault == 'replay': inputs[0]['input_replayed'] = True
    elif fault == 'missing_native': rows = [r for r in rows if not(r['name'] == 'CMSG_STANDSTATECHANGE' and r['body'] == '00000000')]
    elif fault == 'foreign_afk': events[-1]['session'] = 'other'
    elif fault == 'wrong_input': inputs[1]['input']['value'] = '/dance'
    elif fault == 'unneeded_afk': inputs.pop()
    elif fault == 'flags_unrestored': rows.pop()
    elif fault == 'later_move': rows.append(dict(rows[0], name='CMSG_MOVE_HEARTBEAT', body='00', time=until - .1))
    elif fault == 'wrong_preflight': inputs[0]['preflight']['native_state']['health'] = 59
    with pytest.raises(RuntimeError): h.cleanup_history(old, rows, events, inputs, until)


def test_durable_attempt_is_scoped_to_capture_and_never_replayed(tmp_path):
    failed = tmp_path / 'episode.json'; failed.write_text('{}\n')
    t = SimpleNamespace(out=tmp_path / 'restore', receipt={'automatic_idle': idle(),
        'capture_source': {'path': str(tmp_path / 'capture.json'), 'sha256': 'a' * 64}}, persist=lambda: None)
    ref = h.bound(failed)
    h.consume(t, ref, 'stand', {'kind': 'key', 'value': 'x', 'hold': .4})
    first = Path(t.receipt['stand_attempt_source']['path'])
    assert json.loads(first.read_text())['input_replay_allowed'] is False
    before = first.read_bytes()
    with pytest.raises(FileExistsError): h.consume(t, ref, 'stand', {'kind': 'key', 'value': 'x', 'hold': .4})
    assert first.read_bytes() == before
    t.receipt['capture_source']['sha256'] = 'b' * 64
    with pytest.raises(FileExistsError): h.consume(t, ref, 'stand', {'kind': 'key', 'value': 'x', 'hold': .4})
    # A genuinely later observed cycle differs in its actual wire/effect identity.
    for row in t.receipt['automatic_idle']['automatic_stand_packets']:
        row['time'] += 400
    t.receipt['automatic_idle']['automatic_owner_update']['packet']['time'] += 400
    h.consume(t, ref, 'stand', {'kind': 'key', 'value': 'x', 'hold': .4})
    assert Path(t.receipt['stand_attempt_source']['path']) != first


def facts_fixture(monkeypatch):
    from tools.client_compatibility.world.tests.test_item_actionbar_evidence import stock_public
    baseline = {str(g): {'native': {'online': 0}, 'saved': {'actions': []}, 'inventory': [], 'pets': []} for g in range(1, 7)}
    baseline['2']['native'].update(position_x=-8914.86, position_y=-135.609, position_z=80.4425, orientation=5.83261,
        activeTalentGroup=0, rest_bonus=52.723335, totaltime=100, leveltime=100, logout_time=1, latency=1)
    now = deepcopy(baseline); now['2']['native']['online'] = 1
    resources = {'equipment': [None] * 19, 'backpack': [None] * 16, 'bags': [[None] * 36 for _ in range(4)]}
    resources['backpack'][:2] = [dict(guid=(0x4000 << 48) | 41, id=6948, count=1), dict(guid=(0x4000 << 48) | 33, id=58231, count=1)]
    world = [-8914.900390625, -135.60000610352, 0, 0]
    state = dict(player='Harnesstwo', guid='Player-1-00000002', level=1, world_position=world,
        bags=[], panels=[], cursor_info={}, spell_targeting=False, lua_errors=[], blocked_actions=[])
    frame = {'movement': {'speed': 0, 'dead': False, 'in_combat': False, 'on_taxi': False}}
    public = stock_public([])
    op = SimpleNamespace(snapshot=lambda: now, native_state=lambda s: deepcopy(h.ORIGINAL),
        detail=lambda t, l: public, resources=lambda s: resources)
    monkeypatch.setattr(h, 'runtime_helpers', lambda: op)
    monkeypatch.setitem(sys.modules, 'tools.client_compatibility.interaction_item_actionbar_parked_selection_capture',
        SimpleNamespace(frame_identity=lambda f, r, original: None))
    t = SimpleNamespace(guid='Player-1-00000002', receipt={'runtime': {}, 'original_world_position': world,
        'original_resources': deepcopy(resources)}, observe=lambda l: (state, frame))
    return t, {'native_session': 'c6195b73', 'all_offline_snapshot': baseline, 'frame': {}}, now, state, op


def test_facts_accepts_real_unitposition_shape_and_unchanged_native_position(monkeypatch):
    t, ready, _, state, _ = facts_fixture(monkeypatch)
    found = h.facts(t, ready, 'fixture')
    assert found['state']['world_position'] == state['world_position']
    assert found['state']['world_position'][2:] == [0, 0]


@pytest.mark.parametrize('fault', ['rendered_position', 'native_position', 'protected_actor', 'cursor_zero', 'cursor_missing', 'health_type',
    'other_equipment', 'other_backpack', 'other_bag'])
def test_facts_rejects_actual_field_mismatches(monkeypatch, fault):
    t, ready, now, state, op = facts_fixture(monkeypatch)
    if fault == 'rendered_position': state['world_position'] = [-8914.86, -135.609, 80.4425, 5.83261]
    elif fault == 'native_position': now['2']['native']['position_x'] += 1
    elif fault == 'protected_actor': now['3']['native']['online'] = 1
    elif fault == 'cursor_zero': state['cursor_info'] = 0
    elif fault == 'cursor_missing': del state['cursor_info']
    elif fault == 'health_type': op.native_state = lambda s: {**h.ORIGINAL, 'health': 60.0}
    elif fault == 'other_equipment': op.resources('c6195b73')['equipment'][2] = {'id': 1}
    elif fault == 'other_backpack': op.resources('c6195b73')['backpack'][3] = {'id': 1}
    elif fault == 'other_bag': op.resources('c6195b73')['bags'][1][2] = {'id': 1}
    with pytest.raises(RuntimeError): h.facts(t, ready, 'fixture')


@pytest.mark.parametrize('fault', [None, 'changed_png', 'stale_png', 'changed_source', 'wrong_control'])
def test_source_owned_review_bytes_and_freshness(monkeypatch, tmp_path, fault):
    monkeypatch.setattr(h.lab, 'ROOT', tmp_path)
    directory = tmp_path / 'evidence/capture'; directory.mkdir(parents=True)
    source = directory / 'episode.json'; source.write_text('{}\n')
    image = directory / 'idle.png'; image.write_bytes(b'actual-owned-png')
    frame = {'file': image.name, 'sha256': h.bound(image)['sha256']}
    review = dict(reviewed=True, control='bags.swap_item.idle_housekeeping', source=h.bound(source), frame=frame, ordinary_stand_afk_only=True)
    path = directory / 'review.json'; path.write_text(json.dumps(review))
    if fault == 'changed_png': image.write_bytes(b'wrong')
    elif fault == 'stale_png': os.utime(image, (1, 1))
    elif fault == 'changed_source': source.write_text('{"different":true}\n')
    elif fault == 'wrong_control': review['control'] = 'other'; path.write_text(json.dumps(review))
    if fault:
        with pytest.raises(RuntimeError): h.reviewed_capture(None, source, path, {'frame': frame})
    else:
        assert h.reviewed_capture(None, source, path, {'frame': frame}) == review

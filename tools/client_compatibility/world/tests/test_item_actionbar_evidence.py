"""Whole source-bound receipts and actual tar journals; no semantic mocks."""
from copy import deepcopy
import hashlib
import io
import json
from pathlib import Path
import struct
import tarfile

import pytest

from tools.client_compatibility import item_actionbar_contract as c
from tools.client_compatibility import item_actionbar_evidence as e
from tools.client_compatibility import item_actionbar_preservation as p
from tools.client_compatibility import item_actionbar_sources as s
from tools.client_compatibility import checkpoint_item_actionbar as publication
from tools.client_compatibility import review_item_actionbar_checkpoint as reviewer
from tools.client_compatibility.world.tests.test_item_actionbar_sources import fixture as prior_fixture
from tools.client_compatibility.world.tests.test_item_actionbar_contract import (public, action_packets, login_packets,
    native_packet, owner_fields)
from tools.client_compatibility.world.tests.test_item_actionbar_preservation import precision as precise


def stock_public(rows, spec=0):
    value = public(rows, spec)
    for row in value['actions']:
        row['visible'] = bool(row.get('kind'))
    return value


def fixture(tmp_path, monkeypatch):
    root, repo, prior_paths, prior = prior_fixture(tmp_path)
    monkeypatch.setattr(e.lab, 'ROOT', root)
    monkeypatch.setattr(e.lab, 'REPO', repo)
    monkeypatch.setattr(s, 'ROOT', root)
    monkeypatch.setattr(s, 'REPO', repo)
    batch = root / 'evidence/client_interactions_20990101_ui171'
    batch.mkdir()
    # The accepted predecessor is synthetic authority, but every carried role
    # still has actual immutable JSON bytes. No future hash is supplied.
    for role in s.ROLES:
        path = Path(prior['closure']['sources'][role]['path'])
        path.parent.mkdir(exist_ok=True)
        value = {'phase': 'hunter_fixture_' + role, 'sources': []}
        if role == 'preparation':
            value.update(phase='await_owned_class_lobby_review', accepted_previous_sources=[])
        path.write_text(json.dumps(value))
        prior['closure']['sources'][role] = s.bound(path)
    prior_paths['closure'].write_text(json.dumps(prior['closure']))
    prior['pause']['source'] = s.bound(prior_paths['closure'])
    prior_paths['pause'].write_text(json.dumps(prior['pause']))
    for row in prior['checkpoint']['file_manifest']:
        path = root / row['path']
        row.update(bytes=path.stat().st_size, sha256=s.bound(path)['sha256'])
    prior_paths['checkpoint'].write_text(json.dumps(prior['checkpoint']))
    baseline = deepcopy(prior['pause']['after'])
    actor = deepcopy(prior['closure']['actor'])
    runtime = deepcopy(prior['closure']['runtime'])
    runtime['client'] = {'pid': 20, 'start_ticks': '2000'}
    monitor = {'second_monitor_verified': True, 'monitor': {'name': 'HDMI-1'}, 'pid': 20,
        'input_isolation': {'actor': 'scout', 'host_activation_sent': False, 'game_pid': 21}}
    png = b'\x89PNG\r\n\x1a\nsynthetic-pure-fixture'
    paths, values = {}, {}

    def write(name, value, episode=True):
        path = batch / name / ('episode.json' if episode else 'review.json')
        path.parent.mkdir(exist_ok=True)
        path.write_text(json.dumps(value, indent=2) + '\n')
        paths[name], values[name] = path, value
        return s.bound(path)

    def frame(name):
        path = batch / name / 'screen.png'
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(png)
        return {'file': 'screen.png', 'sha256': hashlib.sha256(png).hexdigest(), 'monitor': deepcopy(monitor)}

    def trial(name, phase, start, finish, **fields):
        return {'schema': 'client442_laya_interactions_v1', 'phase': phase, 'completed': True, 'failure': None,
            'started_at': start, 'finished_at': finish, 'actor': deepcopy(actor), 'runtime': deepcopy(runtime),
            'controller': 'code', 'model': None, 'revision': None, 'code_commit': 'd' * 40, 'cases': [], 'cleanup': [],
            'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(e.SCRIPT_BOUNDARY),
            'qualification_added': False, 'input_sent': False, 'mutation_sent': False, **fields}

    def attempt(kind, value, start):
        path = paths['entry'].parent / ('item_actionbar_' + kind + '_attempt.json')
        marker = {'schema': 'client442_item_actionbar_consumed_attempt_v1', 'operation': 'actionbars.drag_item',
            'kind': kind, 'consumed': True, 'input_replay_allowed': False, 'created_at': start,
            'entry_source': value['entry_source'], 'preparation_source': value['preparation_source'],
            'actor': actor, 'runtime': runtime, 'native_session': 'scout',
            'operation_output': str(batch / ('operation' if kind == 'clear' else 'placed') / 'episode.json'),
            'input_intent': value['clear_intent' if kind == 'clear' else 'drag_intent']}
        path.write_text(json.dumps(marker))
        return s.bound(path)

    refs = {k: s.bound(path) for k, path in prior_paths.items()}
    resume = {'schema': 'client442_item_actionbar_scout_resume_v1', 'phase': 'item_actionbar_scout_launched',
        'installed': True, 'completed': True, 'failure': None, 'started_at': 1000, 'launch_finished_at': 1001,
        'finished_at': 1001, 'predecessor': refs,
        'predecessor_dvc_pointer': prior['dvc_pointer'], 'all_offline_snapshot': baseline, 'origin_actor': actor,
        'runtime': runtime, 'previous_runtime': prior['closure']['runtime'], 'available_memory_kib_before': 6 * 1024 * 1024,
        'launch_monitor': monitor, 'checks': dict.fromkeys(('native_unchanged', 'bridge_unchanged', 'fresh_scout',
            'all_six_saved_snapshots', 'primary_stopped', 'HDMI_1', 'private_input'), True)}
    resume_ref = write('resume', resume, False)
    selection = trial('selection', 'item_actionbar_scout_captured', 1002, 1003,
        frame=frame('selection'), all_offline_snapshot=baseline)
    selection_ref = write('selection', selection)
    selection_review = {'reviewed': True, 'control': 'Harnesstwo', 'source': selection_ref,
        'frame': selection['frame'], 'selected_character': 'Harnesstwo', 'selected_level': 1}
    select_ref = write('selection_review', selection_review, False)
    authentication = {'event': 'world_authenticated', 'account_id': 2, 'session': 'scout', 'time': 1000.5}
    ready = trial('ready', 'item_actionbar_scout_ready', 1080, 1081, predecessor=refs,
        predecessor_dvc_pointer=prior['dvc_pointer'], all_offline_snapshot=baseline, native_session='scout',
        resume_source=resume_ref, selection_source=selection_ref, realm_authentication=authentication,
        frame=frame('ready'), checks=dict.fromkeys(('original_selection', 'fresh_enumeration', 'all_six_offline'), True),
        screen_review={**select_ref, 'frame': selection['frame']})
    ready_ref = write('ready', ready)
    binding = {'rate': 1, 'xp_cap': 400, 'rest_cap': 300, 'wilderness_bubble': .031,
        'config_source': {'path': str(root / 'config/worldserver.conf'), 'sha256': s.CONFIG_HASH},
        'native_formula_source': {'path': str(repo / s.FORMULA), 'sha256': s.FORMULA_HASH},
        'formula_snippets': list(s.FORMULA_SNIPPETS), 'native_float_storage_sources':
            [{'path': str(repo / path), 'sha256': sha} for path, sha in s.FLOAT_SOURCES.items()]}
    exact_before = p.float32(24.8683)
    exact_after, text = p.native_rest(exact_before, 100)
    before_precision = trial('before_precision', 'item_actionbar_rest_precision_complete', 1090, 1091,
        source=ready_ref, before=baseline, after=baseline, query=p.PRECISION_QUERY,
        row=precise(baseline['2']['native'], exact_before), rest_sources=binding,
        checks=dict.fromkeys(e.PRECISION_CHECKS, True))
    before_ref = write('before_precision', before_precision)
    state = {'player': 'Harnesstwo', 'guid': 'Player-1-00000002', 'level': 1, 'xp': 0, 'xp_max': 400,
        'xp_exhaustion': 2 * int(exact_after), 'panels': [], 'bags': [], 'cursor_info': False,
        'world_position': [-8914.86, -135.609, 80.4425, 5.83261], 'target': {'exists': False, 'guid': '', 'name': ''}}
    empty = {'guid': 0, 'id': 0, 'count': 0}
    resources = {'money': 0, 'equipment': [deepcopy(empty) for _ in range(19)],
        'backpack': [{'guid': c.ITEM_NATIVE_GUID, 'id': c.ITEM_ID, 'count': 1}] + [deepcopy(empty) for _ in range(15)],
        'bags': [[deepcopy(empty) for _ in range(36)] for _ in range(4)]}
    original = {'pose': {'stand': 0, 'sheath': 1}, 'afk': False, 'selection': 0,
        'health': 60, 'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0}
    creation = native_packet(owner_fields(), time=1100.4)
    owner = c.native_replay([creation], 'scout', 1099, 1101)
    entry = trial('entry', 'item_actionbar_entered', 1099, 1101, preparation_source=ready_ref,
        precision_source=before_ref, all_offline_snapshot=baseline, native_session='scout',
        native_before_entry=baseline['2']['native'], entered_native={**baseline['2']['native'], 'online': 1},
        login_packets=login_packets(), owner_packets=owner['packets'], native_owner_proof=owner,
        saved=baseline['2']['saved'], resources=resources, active_spec=0, public=stock_public(baseline['2']['saved']['actions']),
        state=state, frame=frame('entry'), native_original=original)
    entry_ref = write('entry', entry)
    base = {'snapshot': baseline, 'saved': entry['saved'], 'resources': resources, 'public': entry['public'],
        'state': state, 'frame': entry['frame'], 'active_spec': 0, 'entry_source': entry_ref,
        'precision_source': before_ref, 'native_state': original, 'native_original': original}
    common = {'preparation_source': ready_ref, 'fixture_source': ready_ref, 'entry_source': entry_ref,
        'precision_source': before_ref, 'baseline': base, 'native_session': 'scout'}
    button = stock_public(base['saved']['actions'])['actions'][2]
    bag = {'name': 'ContainerFrame1Item16', 'x': 1, 'y': 1, 'text': ''}
    recon = trial('recon', 'item_actionbar_reconciled', 1102, 1103, **common, button=button, slot0=74,
        source_control=bag, public=base['public'], state={**state, 'bags': [0]}, frame=frame('recon'))
    recon_ref = write('recon', recon)
    drag_ready = trial('drag_ready', 'item_actionbar_drag_ready', 1103.1, 1103.5, **common,
        source=recon_ref, button=button, slot0=74, source_control=bag, public=base['public'],
        state=recon['state'], frame=frame('drag_ready'))
    drag_ready_ref = write('drag_ready', drag_ready)
    review_common = {'reviewed': True, 'control': button['button'], 'slot0': 74, 'item': 6948, 'item_guid': 41,
        'public_button': button, 'pickup_point_inside_button': True, 'fixture_source_sha256': ready_ref['sha256']}
    drag_review = {**review_common, 'source': drag_ready_ref, 'frame': drag_ready['frame'], 'point': [10, 10],
        'destination_point': [200, 680], 'destination_point_inside_button': True, 'source_control': bag,
        'stock_grid_cell_reviewed': True, 'stock_grid_source': c.GRID_SOURCE}
    drag_review_ref = write('drag_review', drag_review, False)
    drag_packets = [{**r, 'time': r['time'] + 1094} for r in action_packets()]
    placed_saved = {**base['saved'], 'actions': sorted(base['saved']['actions'] + [[0, 74, 6948, 128]])}
    placed_public = stock_public(placed_saved['actions'])
    placement = c.addition_guard(base['saved']['actions'], placed_saved['actions'], drag_packets, 'scout', 1104, 1105, 0, placed_public)
    placed = trial('placed', 'item_actionbar_placed', 1104, 1105, **common, source=drag_ready_ref,
        drag_started_at=1104, drag_finished_at=1104.9, drag_packets=drag_packets, drag_input_sent=True, input_sent=True,
        drag_intent={'source': drag_ready_ref, 'review': drag_review_ref, 'slot0': 74, 'item': 6948,
            'item_guid': 41, 'start': [10, 10], 'end': [200, 680]},
        screen_review={**drag_review_ref, 'frame': drag_ready['frame']},
        geometry_proof={'exact_pixels': True, 'reviewed_frame': drag_ready['frame']},
        stock_grid_sources=[c.GRID_SOURCE],
        placement=placement, placement_saved=placed_saved, placement_resources=resources,
        public_after_placement=placed_public, cursor_after_placement=False,
        cases=[{'id': 'actionbars.drag_item', 'status': 'item_actionbar_drag_pass', 'selected': 'drag',
            'selection_source': 'code', 'request': None, 'response': None, 'oracle': {'placement': placement}}])
    placed['drag_attempt_source'] = attempt('drag', placed, 1104)
    placed_ref = write('placed', placed)
    clear_button = placed_public['actions'][2]
    clear_ready = trial('clear_ready', 'item_actionbar_clear_ready', 1106, 1107, **common, source=placed_ref,
        drag_source=placed_ref, placement=placement, button=clear_button, slot0=74, source_control=bag,
        public=placed_public, state=recon['state'], frame=frame('clear_ready'))
    clear_ready_ref = write('clear_ready', clear_ready)
    clear_review = {**review_common, 'public_button': clear_button, 'source': clear_ready_ref,
        'frame': clear_ready['frame'], 'point': [200, 680], 'empty_point': [900, 500],
        'empty_point_reviewed': True, 'empty_point_world_space': True}
    clear_review_ref = write('clear_review', clear_review, False)
    clear_packets = [{**r, 'time': r['time'] + 1100} for r in action_packets(clear=True)]
    cleared = c.clear_guard(placement, base['saved']['actions'], clear_packets, 'scout', 1110, 1111, base['public'])
    from tools.client_compatibility.hunter_learn_autobar import PICKUP_SOURCE, BINDING_SOURCE
    operation = trial('operation', 'item_actionbar_restored', 1110, 1112, **common, source=clear_ready_ref,
        drag_source=placed_ref, placement=placement, clear_started_at=1110, clear_finished_at=1110.9,
        clear_packets=clear_packets, clear_input_sent=True, input_sent=True,
        clear_intent={'source': clear_ready_ref, 'review': clear_review_ref, 'slot0': 74, 'item': 6948,
            'item_guid': 41, 'start': [200, 680], 'end': [900, 500]},
        screen_review={**clear_review_ref, 'frame': clear_ready['frame']},
        geometry_proof={'exact_pixels': True, 'reviewed_frame': clear_ready['frame']},
        stock_pickup_sources=[PICKUP_SOURCE, BINDING_SOURCE], cursor_cancel_input_sent=True,
        cursor_cancel_source=clear_review_ref, cursor_cancel_input={'kind': 'click', 'value': [900, 500], 'button': 3},
        cursor_after_cancel=False, after_saved=base['saved'], after_resources=resources,
        public_after_clear=base['public'], clear_proof=cleared, restored_public=base['public'],
        restored_native_state=original, actionbar_restored=True, layout_restoration_checks=dict.fromkeys(e.LAYOUT_CHECKS, True),
        restoration_checks={'full_saved_baseline': True, 'full_resources_baseline': True, 'protected_actors': True})
    operation['clear_attempt_source'] = attempt('clear', operation, 1110)
    operation_ref = write('operation', operation)
    snapshot = deepcopy(baseline)
    snapshot['2']['native'].update(rest_bonus=text, logout_time=1116, totaltime=120, leveltime=120)
    logout = [{'session': 'scout', 'time': 1115 + i * .1, 'name': n, 'direction': d, 'body': b}
        for i, (n, d, b) in enumerate((('CMSG_LOGOUT_REQUEST', 'to_native', ''),
            ('SMSG_LOGOUT_COMPLETE', 'from_native', ''), ('SMSG_LOGOUT_COMPLETE', 'to_client', '00')))]
    park = trial('park', 'item_actionbar_parked', 1114, 1117, preparation_source=ready_ref, source=operation_ref,
        entry_source=entry_ref, native_session='scout', logout_started_at=1114.9, logout_finished_at=1116.9,
        logout_packets=logout, all_offline_snapshot=snapshot, checks=dict.fromkeys(e.PARK_CHECKS, True), frame=frame('park'))
    park_ref = write('park', park)
    after_precision = trial('after_precision', 'item_actionbar_rest_precision_complete', 1120, 1121,
        source=park_ref, before=snapshot, after=snapshot, query=p.PRECISION_QUERY,
        row=precise(snapshot['2']['native'], exact_after), rest_sources=binding, checks=dict.fromkeys(e.PRECISION_CHECKS, True))
    after_ref = write('after_precision', after_precision)
    final_review = {'reviewed': True, 'control': 'Harnesstwo', 'source': park_ref, 'frame': park['frame'],
        'selected_character': 'Harnesstwo', 'selected_level': 1}
    final_review_ref = write('final_review', final_review, False)
    roles = {'preparation': ready_ref, 'entry': entry_ref, 'operation': operation_ref, 'park': park_ref,
        'before_precision': before_ref, 'after_precision': after_ref}
    store = e.Sources({}, {}, local=True)
    result, restored_snapshot, _ = e.lifecycle(store, roles)
    final = trial('final', e.PHASE, 1125, 1126, sources=roles, proof=result,
        before=snapshot, after=snapshot, all_offline_snapshot=snapshot, predecessor=refs,
        primary_stop_source=refs['primary_stop'], shutdown_checks=dict.fromkeys(e.SHUTDOWN_CHECKS, True),
        action='stop_parked_scout_after_item_roundtrip', stop_attempted=True, game_before={'pid': 21, 'start_ticks': '2100'},
        screen_review={**final_review_ref, 'frame': park['frame']}, frame=frame('final'))
    write('final', final)
    publication.carry(batch, paths['ready'])
    wire = [*login_packets(), creation, *drag_packets, *clear_packets, *logout,
        {'session': 'scout', 'time': 1114.99, 'name': 'CMSG_LOGOUT_REQUEST', 'direction': 'from_client', 'body': ''}]
    events = [authentication, {'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical', 'time': 1100.15}]
    for row in wire:
        physical = 'scout' if row['direction'] in ('to_native', 'from_native') or row['name'] in ('CMSG_PLAYER_LOGIN', 'SMSG_LOGOUT_COMPLETE') else 'physical'
        events.append({'event': 'native_packet' if row['direction'] in ('to_native', 'from_native') else 'modern_packet',
            'session': physical, 'time': row['time'] - .01, 'name': row['name'], 'direction': row['direction'], 'bytes': len(bytes.fromhex(row['body']))})
    return batch, paths, values, wire, events


def archive_fixture(batch, wire, events, extra=None):
    files = {str(path.relative_to(e.lab.ROOT)): path.read_bytes() for path in sorted(batch.rglob('*')) if path.is_file()}
    rows = [{'path': name, 'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest()} for name, raw in files.items()]
    files.update({member: b''.join((json.dumps(row) + '\n').encode() for row in data)
        for member, data in zip(e.TRACKING_MEMBERS, (wire, events))})
    if extra:
        files.update(extra)
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w:gz') as tar:
        for name, raw in files.items():
            info = tarfile.TarInfo(name)
            info.size = len(raw)
            tar.addfile(info, io.BytesIO(raw))
    raw = stream.getvalue()
    checkpoint = {'bytes': len(raw), 'sha256': hashlib.sha256(raw).hexdigest(), 'file_manifest': rows}
    return raw, checkpoint


def reviewed(batch, wire, events, extra=None):
    raw, checkpoint = archive_fixture(batch, wire, events, extra)
    data, digests, tracking, count = reviewer.inspect_archive(io.BytesIO(raw), checkpoint, str(batch.relative_to(e.lab.ROOT)) + '/')
    return e.proof(data, digests, tracking)


def test_whole_actual_tarstream_proves_one_nonfixed_item_drag_clear_and_restored_pause(tmp_path, monkeypatch):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    result = reviewed(batch, wire, events)
    assert result['operation'] == 'actionbars.drag_item' and result['slot0'] == 74
    assert result['native_item_requests'] == result['native_clear_requests'] == 1
    assert result['both_owned_clients_stopped'] and result['actual_packet_journals_verified']
    assert result['rest']['matches'][0]['native_login_second'] == 1100


@pytest.mark.parametrize('stage', ['selection', 'drag_ready', 'clear_ready', 'park'])
def test_exact_reviewed_source_png_cannot_borrow_identical_bytes_from_another_episode(tmp_path, monkeypatch, stage):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    owned_image = paths[stage].parent / 'screen.png'
    identical_other = paths['entry'].parent / 'screen.png'
    assert owned_image != identical_other and owned_image.read_bytes() == identical_other.read_bytes()
    owned_image.unlink()
    assert identical_other.is_file()
    with pytest.raises(RuntimeError, match='exact reviewed source PNG'):
        reviewed(batch, wire, events)
    with pytest.raises(RuntimeError, match='ordinary immutable file'):
        store = e.Sources({}, {}, local=True)
        if stage == 'park':
            e.screen_review(store, values['final'], s.bound(paths['park']), 'Harnesstwo')
        else: e.lifecycle(store, values['final']['sources'])


@pytest.mark.parametrize('field,bad,original', [('UNIT_FIELD_HEALTH', 59, 60),
    ('UNIT_FIELD_POWER1', 1, 0), ('PLAYER_XP', 1, 0),
    ('PLAYER_FLAGS', 0x20, 0), ('PLAYER_REST_STATE_EXPERIENCE', 26, 24)])
def test_transient_native_owner_drift_during_logout_cannot_be_hidden_by_final_restoration(tmp_path, monkeypatch, field, bad, original):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    # /logout submission starts1114.9; request1115.0; native completion1115.1.
    # Both updates are during the formerly omitted submission/countdown interval.
    wire.extend([native_packet({c.INDEX[field]: bad}, creation=False, time=1115.02),
        native_packet({c.INDEX[field]: original}, creation=False, time=1115.08)])
    wire.sort(key=lambda p: p['time'])
    assert values['park']['all_offline_snapshot']['2']['native']['health'] == 60
    with pytest.raises(RuntimeError, match='native owner health'):
        reviewed(batch, wire, events)


@pytest.mark.parametrize('fault', ['missing_native_drag', 'duplicate_drag', 'extra_clear', 'hidden_use',
    'metadata_only_open_item', 'metadata_only_inventory_alias', 'extra_login', 'second_instance', 'wrong_physical',
    'missing_metadata', 'missing_logout', 'bool_packet_time', 'intermediate_health', 'intermediate_resting'])
def test_actual_journal_faults_cannot_qualify_a_receipt_claim(tmp_path, monkeypatch, fault):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    if fault == 'missing_native_drag': wire = [r for r in wire if not (r['name'] == c.ACTION and r['direction'] == 'to_native' and r['time'] < 1110)]
    elif fault == 'duplicate_drag': wire.append(deepcopy(next(r for r in wire if r['name'] == c.ACTION)))
    elif fault == 'extra_clear': wire.append({**next(r for r in wire if r['name'] == c.ACTION), 'time': 1112, 'body': struct.pack('<IB', 0, 74).hex()})
    elif fault == 'hidden_use': wire.append({'session': 'scout', 'time': 1112, 'name': 'CMSG_USE_ITEM', 'direction': 'to_native', 'body': ''})
    elif fault.startswith('metadata_only'): events.append({'event': 'modern_packet', 'session': 'physical', 'time': 1112, 'direction': 'from_client', 'name': 'CMSG_OPEN_ITEM' if fault.endswith('open_item') else 'CMSG_AUTO_STORE_BAG_ITEM', 'bytes': 1})
    elif fault == 'extra_login': wire.append({**wire[0], 'time': 1118})
    elif fault == 'second_instance': events.append({'event': 'instance_authenticated', 'account_id': 2, 'session': 'other', 'time': 1119})
    elif fault == 'wrong_physical': next(r for r in events if r.get('name') == c.ACTION and r['direction'] == 'from_client')['session'] = 'scout'
    elif fault == 'missing_metadata': events = [r for r in events if not (r.get('name') == c.ACTION and r.get('direction') == 'to_native')]
    elif fault == 'missing_logout': wire = [r for r in wire if not (r['name'] == 'SMSG_LOGOUT_COMPLETE' and r['direction'] == 'to_client')]
    elif fault == 'bool_packet_time': next(r for r in wire if r['name'] == c.ACTION)['time'] = True
    else:
        field = 'UNIT_FIELD_HEALTH' if fault == 'intermediate_health' else 'PLAYER_FLAGS'
        wire.append(native_packet({c.INDEX[field]: 59 if fault == 'intermediate_health' else 0x20}, creation=False, time=1108))
        wire.sort(key=lambda r: r['time'])
    with pytest.raises(RuntimeError): reviewed(batch, wire, events)


@pytest.mark.parametrize('member', ['unlisted.json', 'unlisted.png'])
def test_unmanifested_batch_json_or_png_is_rejected(tmp_path, monkeypatch, member):
    batch, _, _, wire, events = fixture(tmp_path, monkeypatch)
    with pytest.raises(RuntimeError, match='unmanifested'):
        reviewed(batch, wire, events, {str(batch.relative_to(e.lab.ROOT)) + '/' + member: b'{}'})


@pytest.mark.parametrize('flag', ['recovery_only', 'failed_whole_excluded', 'settlement_only', 'failed_repair_excluded'])
def test_failed_housekeeping_final_can_never_be_admitted(tmp_path, monkeypatch, flag):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    values['final'][flag] = True
    paths['final'].write_text(json.dumps(values['final']))
    with pytest.raises(RuntimeError): reviewed(batch, wire, events)


def test_carried_actual_pointer_bytes_reject_source_substitution(tmp_path, monkeypatch):
    batch, _, _, wire, events = fixture(tmp_path, monkeypatch)
    path = batch / 'ancestry/predecessor_dvc_pointer.json'
    value = json.loads(path.read_text())
    value['raw_hex'] = b'outs:\n- md5: '.hex()
    path.write_text(json.dumps(value))
    manifest = batch / 'ancestry_manifest.json'
    value = json.loads(manifest.read_text())
    value['pointer_observation'] = s.bound(path)
    manifest.write_text(json.dumps(value))
    with pytest.raises(RuntimeError): reviewed(batch, wire, events)


@pytest.mark.parametrize('fault', ['missing_grid_review', 'wrong_grid_source', 'missing_grid_source',
    'wrong_marker_intent', 'marker_too_late', 'marker_replay_allowed', 'extra_marker'])
def test_hidden_empty_stock_grid_and_durable_attempt_authority_are_required(tmp_path, monkeypatch, fault):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    store = e.Sources({}, {}, local=True)
    if fault in ('missing_grid_review', 'wrong_grid_source'):
        review = values['drag_review']
        if fault == 'missing_grid_review': review.pop('stock_grid_cell_reviewed')
        else: review['stock_grid_source'] = {**c.GRID_SOURCE, 'sha256': '0' * 64}
        paths['drag_review'].write_text(json.dumps(review))
        values['placed']['screen_review'].update(s.bound(paths['drag_review']))
        values['placed']['drag_intent']['review'] = s.bound(paths['drag_review'])
    elif fault == 'missing_grid_source':
        values['placed'].pop('stock_grid_sources')
    else:
        marker = Path(values['placed']['drag_attempt_source']['path'])
        content = json.loads(marker.read_text())
        if fault == 'wrong_marker_intent': content['input_intent']['slot0'] = 75
        elif fault == 'marker_too_late': content['created_at'] = 1106
        elif fault == 'marker_replay_allowed': content['input_replay_allowed'] = True
        else:
            (paths['entry'].parent / 'extra_attempt.json').write_text(json.dumps(content))
        marker.write_text(json.dumps(content))
        values['placed']['drag_attempt_source'] = s.bound(marker)
    if fault == 'extra_marker':
        with pytest.raises(RuntimeError, match='durable drag marker'): reviewed(batch, wire, events)
    elif 'grid' in fault:
        with pytest.raises(RuntimeError, match='grid'):
            e.input_review(store, values['placed'], s.bound(paths['drag_ready']), s.bound(paths['ready']), values['drag_ready'])
    else:
        with pytest.raises(RuntimeError, match='durable exact one-attempt'):
            e.consumed_attempt(store, values['placed'], s.bound(paths['placed']), s.bound(paths['entry']), s.bound(paths['ready']))

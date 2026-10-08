"""Actual-shaped failed history is excluded and closes with portable byte epochs."""
from copy import deepcopy
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tarfile

import pytest

from tools.client_compatibility import bag_swap_failed_sources as s
from tools.client_compatibility import bag_swap_failed_contract as history_contract
from tools.client_compatibility.world.tests.test_bag_swap_failed_contract import lobby_fixture as recorded
from tools.client_compatibility.world.tests.test_item_actionbar_preservation import precision


class Store:
    def __init__(self, root):
        self.root, self.data, self.digests, self.raw_journals, self.files = root, {}, {}, {}, {}

    def put(self, name, value):
        member = 'evidence/unit/' + name
        raw = json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()
        self.data[member], self.digests[member] = deepcopy(value), hashlib.sha256(raw).hexdigest()
        self.files[member] = raw
        return {'path': str(self.root / member), 'sha256': self.digests[member]}

    def get(self, ref, successful=True):
        s.reference(ref)
        member = str(Path(ref['path']).relative_to(self.root))
        assert self.digests[member] == ref['sha256']
        value = self.data[member]
        if successful:
            assert value['completed'] is True and value['failure'] is None
        return value

    def image(self, name, template):
        image = deepcopy(template)
        member = 'evidence/unit/' + name
        image['file'] = Path(name).name
        self.files[member] = b'\x89PNG\r\n\x1a\n' + name.encode()
        self.digests[member] = image['sha256'] = hashlib.sha256(self.files[member]).hexdigest()
        return image

    def journal(self, name, rows):
        member = 'evidence/unit/' + name
        raw = b''.join((json.dumps(row, sort_keys=True) + '\n').encode() for row in rows)
        self.digests[member] = hashlib.sha256(raw).hexdigest()
        self.files[member] = raw
        self.raw_journals[member] = deepcopy(rows)
        return {'path': str(self.root / member), 'sha256': self.digests[member]}


def code_epoch(store, repo, commit, role, members):
    refs, carried, raw_rows = [], [], []
    for i, member in enumerate(members):
        # Native formula bytes are genuinely pinned; other synthetic code members
        # are opaque epoch fixtures, never represented as an experiment receipt.
        raw = ((Path(__file__).resolve().parents[4] / member).read_bytes() if member == s.FORMULA else
            (commit + '\n' + member + '\n').encode())
        ref = {'path': str(repo / member), 'sha256': hashlib.sha256(raw).hexdigest()}
        refs.append(ref)
        carried.append(store.put(f'code/{role}/{i:03d}.json', {'schema': s.CODE_SCHEMA,
            'code_commit': commit, 'original_path': ref['path'], 'sha256': ref['sha256'],
            'bytes': len(raw), 'raw_hex': raw.hex()}))
        raw_rows.append({**ref, 'bytes': len(raw), 'raw_hex': raw.hex()})
    return {'role': role, 'code_commit': commit, 'source_ref': None, 'committed_sources': refs,
        'carried_sources': carried}, raw_rows


def fixture(tmp_path, monkeypatch):
    wire = recorded()
    captured_rows = [row for row in wire['rows'] if row['time'] <= 1791423505.]
    captured_events = [row for row in wire['events'] if row['time'] <= 1791423505.]
    store, repo = Store(tmp_path / 'lab'), tmp_path / 'repo'
    original, _ = code_epoch(store, repo, s.C1, 'original', s.OLD_MEMBERS)
    h06, _ = code_epoch(store, repo, s.H06, 'h06', s.H_MEMBERS)
    h07, retained = code_epoch(store, repo, s.H07, 'h07', s.H_MEMBERS)
    current, _ = code_epoch(store, repo, 'f' * 40, 'current', sorted(set(s.OLD_MEMBERS) | s.CURRENT_REQUIRED))
    ready, failed = deepcopy(wire['ready']), deepcopy(wire['F'])
    ready['committed_sources'] = deepcopy(original['committed_sources'])
    ready['frame'] = store.image('ready/screen.png', ready['frame'])
    ready_ref = store.put('ready/episode.json', ready)
    baseline = ready['all_offline_snapshot']
    binding = {'rate': 1, 'xp_cap': 400, 'rest_cap': 300, 'wilderness_bubble': .031,
        'config_source': {'path': str(store.root / 'config/worldserver.conf'), 'sha256': s.CONFIG_HASH},
        'native_formula_source': {'path': str(repo / s.FORMULA), 'sha256': s.FORMULA_HASH},
        'formula_snippets': list(s.FORMULA_SNIPPETS), 'native_float_storage_sources':
            [{'path': str(repo / p), 'sha256': sha} for p, sha in s.FLOAT_SOURCES.items()]}
    def trial(phase, start, finish, commit=s.C1, refs=None, **kwargs):
        return {'schema': s.SCHEMA, 'phase': phase, 'completed': True, 'failure': None,
            'started_at': start, 'finished_at': finish, 'code_commit': commit,
            'committed_sources': deepcopy(refs or original['committed_sources']),
            'actor': deepcopy(ready['actor']), 'runtime': deepcopy(ready['runtime']), 'controller': 'code',
            'model': None, 'revision': None, 'qualification_added': False,
            'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(s.SCRIPT),
            'input_sent': False, 'mutation_sent': False, 'cases': [], 'cleanup': [], **kwargs}
    p = trial('bags_swap_rest_precision_complete', failed['started_at'] - 10, failed['started_at'] - 9,
        source=ready_ref, before=baseline, after=baseline, query=s.preservation.PRECISION_QUERY,
        row=precision(baseline['2']['native'], 52.72333526611328), rest_sources=binding,
        checks=dict.fromkeys(s.PRECISION_CHECKS, True))
    p_ref = store.put('precision/episode.json', p)
    failed.update(committed_sources=deepcopy(original['committed_sources']), preparation_source=ready_ref, precision_source=p_ref)
    f_ref = store.put('failed/episode.json', failed)
    original_image = store.image('failed/bags_swap_entered.png', ready['frame'])
    original_image_ref = {'path': str(store.root / 'evidence/unit/failed/bags_swap_entered.png'),
        'sha256': original_image['sha256']}
    empty = {'guid': 0, 'id': 0, 'count': 0}
    resources = {'money': baseline['2']['native']['money'], 'equipment': [deepcopy(empty) for _ in range(19)],
        'backpack': [deepcopy(empty) for _ in range(16)], 'bags': [[deepcopy(empty) for _ in range(36)] for _ in range(4)]}
    for row in baseline['2']['inventory']:
        item = {'guid': (0x4000 << 48) | row[3], 'id': row[5], 'count': row[9]}
        if row[2] < 19: resources['equipment'][row[2]] = item
        else: resources['backpack'][row[2] - 23] = item
    resources_ref = store.put('resources/facts.json', {'observed_at': 1791421203., 'input_sent': False,
        'mutation_sent': False, 'entry_source': f_ref, 'actor': ready['actor'], 'runtime': ready['runtime'],
        'session': ready['native_session'], 'before': baseline, 'resources': resources,
        'frame': store.image('resources/current.png', ready['frame'])})
    h1 = trial(None, 1791422839.5, 1791422839.8, commit=s.H06, completed=False, failure='RuntimeError: initial pose guard')
    for key in ('phase', 'input_sent', 'mutation_sent', 'committed_sources'):
        h1.pop(key)
    h1_ref = store.put('h06/episode.json', h1)
    h2 = trial('bags_swap_idle_housekeeping_started', 1791423029.5, 1791423033.5, commit=s.H07,
        completed=False, failure='RuntimeError: actor is offline', ordinary_inputs=[],
        committed_source_bytes=retained, preparation_source=ready_ref, original_entry_source=f_ref,
        original_failed_image=original_image_ref, original_resources_source=resources_ref)
    h2_ref = store.put('h07/episode.json', h2)
    original['source_ref'], h06['source_ref'], h07['source_ref'] = ready_ref, h1_ref, h2_ref
    history = history_contract.failed_history(captured_rows, captured_events, ready, failed, 1791423505.)
    login_second = int(history['login_sync']['login_packets'][1]['time'])
    exact_after, text = s.preservation.native_rest(52.72333526611328, login_second - baseline['2']['native']['logout_time'])
    now = deepcopy(baseline)
    now['2']['native'].update(rest_bonus=text, logout_time=int(history['logout']['complete']['time']),
        totaltime=baseline['2']['native']['totaltime'] + 1900, leveltime=baseline['2']['native']['leveltime'] + 1900)
    lobby = {'observed_at': 1791423400., 'input_sent': False, 'mutation_sent': False,
        'frame': store.image('lobby/screen.png', ready['frame'])}
    lobby_ref = store.put('lobby/facts.json', lobby)
    offline_ref = store.put('offline/facts.json', {'observed_at': 1791423067., 'failed_capture_source': h2_ref,
        'baseline': baseline, 'current': now, 'diff': {'2': {}}, 'input_sent': False, 'mutation_sent': False})
    attestation = {'schema': 'client442_root_failed_entry_no_input_attestation_v1', 'attested_at': 1791423441.,
        'sources': {'preparation': ready_ref, 'original_failed_entry': f_ref, 'failed_idle_capture06': h1_ref,
            'failed_idle_capture07': h2_ref, 'current_offline_preservation': offline_ref, 'owned_selection': lobby_ref},
        'ordinary_enter_world_was_sent': True, 'original_failed_entry_finished_at': failed['finished_at'],
        'root_gameplay_input_after_original_failed_entry': False, 'root_idle_cleanup_input_sent': False,
        'root_swap_input_sent': False, 'root_logout_input_sent': False, 'bag_attempt_markers_found': [],
        'original_failed_entry_and_failed_idle_captures_excluded': True, 'qualification_added': False,
        'custom_script_permission': 'blocked_by_user', 'softTargetInteract': deepcopy(s.SCRIPT)}
    attest_ref = store.put('attestation.json', attestation)
    # Explicit unit-only authority adapter. Runtime has no receipt, environment
    # or archive-selected override of the immutable actual historical pins.
    monkeypatch.setattr(s, '_HISTORICAL_SOURCES', {'preparation': ready_ref, 'precision': p_ref,
        'failed_entry': f_ref, 'h06': h1_ref, 'h07': h2_ref, 'lobby': lobby_ref,
        'attestation': attest_ref, 'offline': offline_ref, 'failed_image': original_image_ref, 'resources': resources_ref})
    monkeypatch.setattr(s, '_H06_SOURCE_HASHES', tuple(ref['sha256'] for ref in h06['committed_sources']))
    exact = {'query': s.preservation.PRECISION_QUERY, 'row': precision(now['2']['native'], exact_after),
        'before': now, 'after': now, 'source': None, 'input_sent': False, 'mutation_sent': False}
    common = {'original_preparation_source': ready_ref, 'original_entry_source': f_ref, 'before_precision_source': p_ref,
        'failed_housekeeping_sources': [h1_ref, h2_ref], 'lobby_source': lobby_ref, 'no_input_attestation_source': attest_ref,
        'predecessor': ready['predecessor'], 'authority_source': ready['authority_source'],
        'runtime_authority_source': ready['runtime_authority_source'], 'native_session': ready['native_session'],
        'primary_stop_source': ready['predecessor']['primary_stop'],
        'before': now, 'after': now, 'all_offline_snapshot': now, 'excluded_failed_entry': True, 'operations_admitted': 0,
        'code_epochs': {'schema': s.EPOCH_SCHEMA, 'epochs': [original, h06, h07, current]}, 'failed_history': history,
        'journal_sources': {'packets': store.journal('journals/packets.jsonl', captured_rows),
            'events': store.journal('journals/events.jsonl', captured_events)}}
    capture = trial(s.CAPTURE_PHASE, 1791423500., 1791423510., commit='f' * 40, refs=current['committed_sources'],
        exact_precision=exact, frame=store.image('capture/screen.png', ready['frame']), **common)
    capture_ref = store.put('capture/episode.json', capture)
    review_ref = store.put('review/review.json', {'reviewed': True, 'control': 'Harnesstwo', 'source': capture_ref,
        'frame': capture['frame'], 'selected_character': 'Harnesstwo', 'selected_level': 1})
    closed = trial(s.PHASE, 1791423520., 1791423530., commit='f' * 40, refs=current['committed_sources'],
        exact_precision={**exact, 'source': capture_ref}, capture_source=capture_ref, review_source=review_ref,
        frame=store.image('closed/screen.png', ready['frame']), shutdown_checks=dict.fromkeys(s.STOP_CHECKS, True),
        stop_attempted=True, game_before={'pid': ready['frame']['monitor']['input_isolation']['game_pid'], 'start_ticks': '12345'},
        **common)
    closed['failed_history'] = history_contract.failed_history(wire['rows'], wire['events'], ready, failed, 1791423525.)
    closed['journal_sources'] = {'packets': store.journal('closed_journals/packets.jsonl', wire['rows']),
        'events': store.journal('closed_journals/events.jsonl', wire['events'])}
    closed['closing_frame_source'] = {'path': str(store.root / 'evidence/unit/closed/screen.png'), 'sha256': closed['frame']['sha256']}
    closed_ref = store.put('closed/episode.json', closed)
    return store, store.get(capture_ref, False), store.get(closed_ref, False), ready_ref


def test_serialized_actual_shaped_capture_and_pause_are_excluded_and_preserve_one_exact_rest(tmp_path, monkeypatch):
    store, capture, closed, _ = fixture(tmp_path, monkeypatch)
    def forbidden(*args, **kwargs): raise AssertionError('portable proof read live files or Git')
    monkeypatch.setattr(Path, 'read_bytes', forbidden)
    monkeypatch.setattr(subprocess, 'check_output', forbidden)
    before = deepcopy(store.data)
    captured = s.validate_failed_capture(store, capture)
    result = s.validate_failed_pause(store, closed)
    assert captured['both_owned_clients_stopped'] is False and captured['shutdown_checks'] == 0
    assert result['operations_admitted'] == 0 and result['excluded_failed_entry'] is True
    assert result['shutdown_checks'] == 8 and result['all_six_offline'] is True
    assert result['source_code_epochs']['member_counts'][:3] == [35, 12, 12]
    assert result['native_rest']['matches'][0]['native_login_second'] == 1791421132
    assert closed['before']['2']['native']['logout_time'] == 1791422949
    assert closed['finished_at'] > closed['failed_history']['until']
    assert closed['failed_history']['post_close_audit']['source_packet_count'] == 13
    assert closed['failed_history']['post_close_audit']['source_event_count'] == 110
    assert store.data == before


@pytest.mark.parametrize('fault', ['old_code_raw', 'h06_code_raw', 'h07_code_raw', 'current_code_raw', 'h07_vector',
    'invent_h06_vector', 'current_missing_member', 'wrong_epoch_label', 'rest_bits', 'rest_twice', 'protected_pet',
    'inventory_charge', 'native_pose', 'online', 'audit_time_as_logout', 'original_float', 'missing_journal',
    'extra_gameplay', 'history_claim', 'ready_png', 'capture_png', 'close_png', 'close_png_source', 'primary_monitor',
    'foreign_child', 'review_source', 'root_input_attestation', 'bag_attempt', 'missing_stop', 'operation_qualification'])
def test_failed_pause_refuses_code_rest_fulljournal_png_and_exclusion_drift(tmp_path, fault, monkeypatch):
    store, capture, closed, ready_ref = fixture(tmp_path, monkeypatch)
    if fault.endswith('_code_raw'):
        role = fault.removesuffix('_code_raw')
        i = {'old': 0, 'h06': 1, 'h07': 2, 'current': 3}[role]
        ref = closed['code_epochs']['epochs'][i]['carried_sources'][0]
        envelope = store.get(ref, False)
        envelope['raw_hex'] = '00' * envelope['bytes']
    elif fault == 'h07_vector': store.get(closed['failed_housekeeping_sources'][1], False)['committed_source_bytes'].pop()
    elif fault == 'invent_h06_vector': store.get(closed['failed_housekeeping_sources'][0], False)['committed_source_bytes'] = []
    elif fault == 'current_missing_member': closed['code_epochs']['epochs'][3]['carried_sources'].pop()
    elif fault == 'wrong_epoch_label': closed['code_epochs']['epochs'][1]['code_commit'] = s.H07
    elif fault == 'rest_bits': closed['exact_precision']['row']['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'rest_twice':
        row = closed['exact_precision']['row']
        exact, text = s.preservation.native_rest(row['exact_rest_bonus'], 10)
        row.update(exact_rest_bonus=exact, exact_rest_bonus_float32_bits=s.preservation.float32_bits(exact), rest_bonus=text)
        closed['before']['2']['native']['rest_bonus'] = closed['after']['2']['native']['rest_bonus'] = text
        closed['all_offline_snapshot']['2']['native']['rest_bonus'] = text
        closed['exact_precision']['before']['2']['native']['rest_bonus'] = closed['exact_precision']['after']['2']['native']['rest_bonus'] = text
    elif fault == 'protected_pet': closed['before']['6']['pets'][0]['curhealth'] -= 1
    elif fault == 'inventory_charge': closed['before']['2']['inventory'][0][11] = '1 0 0 '
    elif fault == 'native_pose': closed['before']['2']['native']['orientation'] += .1
    elif fault == 'online': closed['before']['2']['native']['online'] = 1
    elif fault == 'audit_time_as_logout': closed['before']['2']['native']['logout_time'] = int(closed['finished_at'])
    elif fault == 'original_float': store.get(closed['before_precision_source'], False)['row']['exact_rest_bonus_float32_bits'] = '00000000'
    elif fault == 'missing_journal': store.raw_journals.pop(str(Path(closed['journal_sources']['events']['path']).relative_to(store.root)))
    elif fault == 'extra_gameplay':
        member = str(Path(closed['journal_sources']['packets']['path']).relative_to(store.root))
        store.raw_journals[member].append({'session': closed['native_session'], 'time': 1791422000.,
            'name': 'CMSG_CAST_SPELL', 'direction': 'from_client', 'body': '0000'})
    elif fault == 'history_claim': closed['failed_history']['native_original']['rest_threshold'] += 1
    elif fault in ('ready_png', 'capture_png', 'close_png'):
        ref = ready_ref if fault == 'ready_png' else closed['capture_source'] if fault == 'capture_png' else None
        image = store.get(ref, False)['frame'] if ref else closed['frame']
        path = (Path(ref['path']).parent if ref else store.root / 'evidence/unit/closed') / image['file']
        store.digests[str(path.relative_to(store.root))] = '0' * 64
    elif fault == 'close_png_source': closed['closing_frame_source']['path'] = closed['capture_source']['path']
    elif fault == 'primary_monitor': closed['frame']['monitor']['monitor']['name'] = 'DP-1'
    elif fault == 'foreign_child': closed['frame']['monitor']['input_isolation']['game_pid'] += 1
    elif fault == 'review_source': store.get(closed['review_source'], False)['source'] = ready_ref
    elif fault == 'root_input_attestation': store.get(closed['no_input_attestation_source'], False)['root_logout_input_sent'] = True
    elif fault == 'bag_attempt': store.put('attempt.json', {'schema': 'client442_bag_swap_consumed_attempt_v1'})
    elif fault == 'missing_stop': closed['shutdown_checks']['owned_game_absent'] = False
    else: closed['operations_admitted'] = 1
    with pytest.raises(RuntimeError): s.validate_failed_pause(store, closed)


def test_capture_preflight_refuses_the_same_unpreserved_state_before_stop(tmp_path, monkeypatch):
    store, capture, _, _ = fixture(tmp_path, monkeypatch)
    capture['before']['2']['native']['health'] -= 1
    with pytest.raises(RuntimeError): s.validate_failed_capture(store, capture)


@pytest.mark.parametrize('key,value', [('input_sent', True), ('operations_admitted', 1),
    ('excluded_failed_entry', False), ('native_session', 'foreign')])
def test_pause_revalidates_the_independent_capture_preflight(tmp_path, monkeypatch, key, value):
    store, capture, closed, _ = fixture(tmp_path, monkeypatch)
    capture[key] = value
    with pytest.raises(RuntimeError): s.validate_failed_pause(store, closed)


@pytest.mark.parametrize('role,field', [('original', 'original_preparation_source'),
    ('h06', 'failed_housekeeping_sources'), ('h07', 'failed_housekeeping_sources')])
def test_coedited_historical_vectors_and_raw_bytes_cannot_keep_actual_epoch_labels(tmp_path, monkeypatch, role, field):
    store, _, closed, _ = fixture(tmp_path, monkeypatch)
    epoch = next(e for e in closed['code_epochs']['epochs'] if e['role'] == role)
    envelope = deepcopy(store.get(epoch['carried_sources'][0], False))
    raw = b'co-edited source bytes'
    envelope.update(raw_hex=raw.hex(), bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
    epoch['carried_sources'][0] = store.put('coedited-code.json', envelope)
    epoch['committed_sources'][0]['sha256'] = envelope['sha256']
    old_ref = closed[field] if role == 'original' else closed[field][0 if role == 'h06' else 1]
    historical = deepcopy(store.get(old_ref, False))
    if role == 'original': historical['committed_sources'] = epoch['committed_sources']
    elif role == 'h07': historical['committed_source_bytes'][0] = {**epoch['committed_sources'][0],
        'bytes': len(raw), 'raw_hex': raw.hex()}
    else: historical['failure'] += ' coedited'
    new_ref = store.put('coedited-historical.json', historical)
    epoch['source_ref'] = new_ref
    if role == 'original': closed[field] = new_ref
    else: closed[field][0 if role == 'h06' else 1] = new_ref
    with pytest.raises(RuntimeError, match='immutable actual historical'):
        s.validate_failed_pause(store, closed)


def test_complete_serialized_tar_rebinds_all_json_png_and_full_journal_bytes(tmp_path, monkeypatch):
    store, capture, closed, _ = fixture(tmp_path, monkeypatch)
    manifest = {member: {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
        for member, raw in store.files.items()}
    archive = io.BytesIO()
    with tarfile.open(fileobj=archive, mode='w:gz') as handle:
        for member, raw in store.files.items():
            info = tarfile.TarInfo(member)
            info.size = len(raw)
            handle.addfile(info, io.BytesIO(raw))
    rebound = Store(store.root)
    with tarfile.open(fileobj=io.BytesIO(archive.getvalue()), mode='r:gz') as handle:
        for member in handle:
            assert member.isfile() and member.name not in rebound.files
            raw = handle.extractfile(member).read()
            assert manifest[member.name] == {'sha256': hashlib.sha256(raw).hexdigest(), 'bytes': len(raw)}
            rebound.files[member.name], rebound.digests[member.name] = raw, manifest[member.name]['sha256']
            if member.name.endswith('.json'): rebound.data[member.name] = json.loads(raw)
            elif member.name.endswith('.jsonl'): rebound.raw_journals[member.name] = [json.loads(line) for line in raw.splitlines()]
    assert set(rebound.files) == set(manifest)
    captured = rebound.data['evidence/unit/capture/episode.json']
    paused = rebound.data['evidence/unit/closed/episode.json']
    assert s.validate_failed_capture(rebound, captured)['all_six_preserved'] is True
    assert s.validate_failed_pause(rebound, paused)['both_owned_clients_stopped'] is True


def test_coedited_h06_bytes_and_hash_vector_refused_without_touching_pinned_failed_receipt(tmp_path, monkeypatch):
    store, _, closed, _ = fixture(tmp_path, monkeypatch)
    epoch = closed['code_epochs']['epochs'][1]
    envelope = deepcopy(store.get(epoch['carried_sources'][0], False))
    raw = b'fabricated historical H06 member bytes\n'
    sha = hashlib.sha256(raw).hexdigest()
    envelope.update(raw_hex=raw.hex(), bytes=len(raw), sha256=sha)
    epoch['committed_sources'][0]['sha256'] = sha
    epoch['carried_sources'][0] = store.put('coedited-h06-member.json', envelope)
    assert closed['failed_housekeeping_sources'][0] == s._HISTORICAL_SOURCES['h06']
    with pytest.raises(RuntimeError, match='immutable actual historical Git object'):
        s.validate_failed_pause(store, closed)


@pytest.mark.parametrize('fault', ['short_capture_audit', 'short_pause_audit', 'outside_audit_row',
    'missing_capture_prefix', 'offline_diagnostic_boundary', 'offline_diagnostic_input', 'missing_failed_png',
    'missing_resources', 'resources_frame', 'original_money', 'post_close_gameplay'])
def test_failed_pause_requires_current_audit_and_actual_root_offline_preservation(tmp_path, monkeypatch, fault):
    store, capture, closed, _ = fixture(tmp_path, monkeypatch)
    if fault == 'short_capture_audit': capture['failed_history']['audit_until'] = capture['started_at'] - 1
    elif fault == 'short_pause_audit': closed['failed_history']['audit_until'] = closed['started_at'] - 1
    elif fault == 'outside_audit_row':
        member = str(Path(closed['journal_sources']['events']['path']).relative_to(store.root))
        store.raw_journals[member].append({'session': 'other', 'event': 'metadata',
            'time': closed['failed_history']['audit_until'] + 1})
    elif fault == 'post_close_gameplay':
        member = str(Path(closed['journal_sources']['packets']['path']).relative_to(store.root))
        store.raw_journals[member].append({'session': closed['native_session'], 'time': closed['failed_history']['until'] + 1,
            'name': 'CMSG_CAST_SPELL', 'direction': 'from_client', 'body': '0000'})
    elif fault == 'missing_capture_prefix':
        original = str(Path(capture['journal_sources']['events']['path']).relative_to(store.root))
        capture['journal_sources']['events'] = store.journal('journals/capture_extra_event.jsonl',
            store.raw_journals[original] + [{'session': 'other', 'event': 'metadata', 'time': 1791423401.}])
    elif fault == 'missing_failed_png':
        store.digests.pop(str(Path(s._HISTORICAL_SOURCES['failed_image']['path']).relative_to(store.root)))
    elif fault == 'missing_resources':
        ref = s._HISTORICAL_SOURCES['resources']
        # A missing retained JSON is a source retrieval failure, not admission.
        store.data.pop(str(Path(ref['path']).relative_to(store.root)))
    elif fault == 'resources_frame':
        facts = store.get(s._HISTORICAL_SOURCES['resources'], False)
        member = str((Path(s._HISTORICAL_SOURCES['resources']['path']).parent / facts['frame']['file']).relative_to(store.root))
        store.digests[member] = '0' * 64
    elif fault == 'original_money': store.get(s._HISTORICAL_SOURCES['resources'], False)['resources']['money'] += 1
    else:
        offline = store.get(s._HISTORICAL_SOURCES['offline'], False)
        if fault == 'offline_diagnostic_input': offline['input_sent'] = True
        else: offline['current']['2']['native']['totaltime'] -= 1
    with pytest.raises((RuntimeError, KeyError)): s.validate_failed_pause(store, closed)


def test_coedited_current_vector_cannot_omit_the_actual_runtime_controller(tmp_path, monkeypatch):
    store, capture, closed, _ = fixture(tmp_path, monkeypatch)
    path = 'tools/client_compatibility/interaction_bag_swap_failed_entry_pause.py'
    for value in (capture, closed):
        epoch = value['code_epochs']['epochs'][3]
        index = next(i for i, ref in enumerate(epoch['committed_sources']) if ref['path'].endswith('/' + path))
        epoch['committed_sources'].pop(index)
        epoch['carried_sources'].pop(index)
        value['committed_sources'] = deepcopy(epoch['committed_sources'])
    with pytest.raises(RuntimeError, match='complete current closed helper byte vector'):
        s.validate_failed_pause(store, closed)


@pytest.mark.parametrize('wrong_git_byte', [False, True])
def test_carry_epochs_reads_actual_four_commits_before_writing_exact_portable_bytes(tmp_path, monkeypatch, wrong_git_byte):
    store, capture, _, ready_ref = fixture(tmp_path, monkeypatch)
    for member, raw in store.files.items():
        path = store.root / member
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(raw)
    raw_objects = {}
    expected_calls = []
    for epoch in capture['code_epochs']['epochs']:
        for copy in epoch['carried_sources']:
            envelope = store.get(copy, False)
            relative = str(Path(envelope['original_path']).relative_to(s._repo(store.get(ready_ref, False))))
            key = (epoch['code_commit'], relative)
            expected_calls.append(key)
            raw_objects[key] = bytes.fromhex(envelope['raw_hex'])
    calls = []
    def git(argv, *, cwd):
        assert argv[:2] == ['git', 'show'] and Path(cwd) == s._repo(store.get(ready_ref, False))
        key = tuple(argv[2].split(':', 1))
        calls.append(key)
        return b'wrong actual Git bytes' if wrong_git_byte and key == (s.H06, s.H_MEMBERS[0]) else raw_objects[key]
    monkeypatch.setattr(subprocess, 'check_output', git)
    out = store.root / 'evidence/unit/carried_epochs'
    args = (store.get(ready_ref, False), capture['failed_housekeeping_sources'], out)
    kwargs = {'preparation_ref': ready_ref, 'current': capture, 'root': store.root}
    if wrong_git_byte:
        with pytest.raises(RuntimeError, match='actual H06 Git bytes'):
            s.carry_epochs(*args, **kwargs)
        assert not out.exists()
    else:
        epochs = s.carry_epochs(*args, **kwargs)
        for epoch in epochs['epochs']:
            for ref in epoch['carried_sources']:
                path = Path(ref['path'])
                raw = path.read_bytes()
                assert hashlib.sha256(raw).hexdigest() == ref['sha256']
                member = str(path.relative_to(store.root))
                store.data[member], store.digests[member] = json.loads(raw), ref['sha256']
                assert path.stat().st_mode & 0o777 == 0o600
        capture['code_epochs'] = epochs
        assert s.validate_epochs(store, store.get(ready_ref, False),
            [store.get(ref, False) for ref in capture['failed_housekeeping_sources']], capture)['all_raw_code_bytes_verified'] is True
    assert calls == expected_calls


def test_failed_source_import_has_no_live_sql_ui_network_or_unshipped_renewal():
    script = '''
import importlib,sys
class Block:
    def find_spec(self,fullname,path=None,target=None):
        if fullname.startswith(('Crypto','google','PIL','pymysql','requests','urllib.request',
            'tools.client_compatibility.interaction_','tools.client_compatibility.lab_runtime',
            'tools.client_compatibility.bag_swap_renewal')):
            raise AssertionError('live dependency imported: '+fullname)
sys.meta_path.insert(0,Block())
importlib.import_module('tools.client_compatibility.bag_swap_failed_sources')
'''
    subprocess.run([sys.executable, '-B', '-c', script], cwd=Path(__file__).resolve().parents[4], check=True,
        capture_output=True, env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1'})

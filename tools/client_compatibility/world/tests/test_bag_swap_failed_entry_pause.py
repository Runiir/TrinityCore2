"""The excluded offline pause must keep its actual child and refuse inputs."""
from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_bag_swap_failed_entry_pause as m
from tools.client_compatibility.world.tests.test_bag_swap_operation import monitor
from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture


def test_offline_current_full_six_saved_state_accepts_only_accounting_and_rest(monkeypatch):
    before, after, *_ = fixture()
    monkeypatch.setattr(m, 'continuation', lambda: SimpleNamespace(snapshot=lambda: deepcopy(after)))
    assert m.offline_state({'all_offline_snapshot': before}) == after


@pytest.mark.parametrize('fault', ['online', 'owner_health', 'owner_inventory', 'owner_saved', 'owner_pet',
    'peer_health', 'owner_pose', 'bool_accounting', 'backward_accounting', 'missing_native'])
def test_offline_current_rejects_mutation_and_incomplete_state(monkeypatch, fault):
    before, after, *_ = fixture()
    if fault == 'online': after['2']['native']['online'] = 1
    elif fault == 'owner_health': after['2']['native']['health'] -= 1
    elif fault == 'owner_inventory': after['2']['inventory'][0][9] = 2
    elif fault == 'owner_saved': after['2']['saved']['spells'] = [[12, 1]]
    elif fault == 'owner_pet': after['2']['pets'] = [{'id': 1}]
    elif fault == 'peer_health': after['4']['native']['health'] = 1
    elif fault == 'owner_pose': after['2']['native']['orientation'] += .1
    elif fault == 'bool_accounting': after['2']['native']['latency'] = False
    elif fault == 'backward_accounting': after['2']['native']['totaltime'] = 0
    else: after['2']['native'].pop('latency')
    monkeypatch.setattr(m, 'continuation', lambda: SimpleNamespace(snapshot=lambda: deepcopy(after)))
    with pytest.raises(RuntimeError):
        m.offline_state({'all_offline_snapshot': before})


def review_setup(tmp_path, monkeypatch):
    root = tmp_path / 'lab'
    out = root / 'evidence/capture'
    out.mkdir(parents=True)
    monkeypatch.setattr(m.lab, 'ROOT', root)
    image = out / 'selected.png'
    image.write_bytes(b'actual source-owned image bytes')
    frame = {'file': image.name, 'sha256': m.bound(image)['sha256'], 'monitor': monitor()}
    captured = {'frame': frame}
    source = out / 'episode.json'
    source.write_text(json.dumps(captured))
    ref = m.bound(source)
    path = out / 'review.json'
    path.write_text(json.dumps({'reviewed': True, 'control': 'Harnesstwo', 'source': ref, 'frame': frame,
        'selected_character': 'Harnesstwo', 'selected_level': 1}))
    t = SimpleNamespace(receipt={}, persist=lambda: None)
    monkeypatch.setattr(m, 'continuation', lambda: SimpleNamespace(focus=monitor))
    return t, path, ref, captured, image


def test_fresh_review_rebinds_actual_source_and_png_bytes(tmp_path, monkeypatch):
    t, path, ref, captured, _ = review_setup(tmp_path, monkeypatch)
    result = m.review(t, path, ref, captured)
    assert result['source'] == ref
    assert t.receipt['review_source'] == m.bound(path)


def test_local_capture_preflight_reads_actual_json_png_and_complete_journal_bytes(tmp_path, monkeypatch):
    root = tmp_path / 'lab'
    out = root / 'evidence/capture'
    out.mkdir(parents=True)
    monkeypatch.setattr(m.lab, 'ROOT', root)
    image = out / 'screen.png'
    image.write_bytes(b'\x89PNG\r\n\x1a\nowned source pixels')
    journals = {}
    for role in ('packets', 'events'):
        path = out / (role + '.jsonl')
        path.write_text(json.dumps({'time': 12, 'kind': role}) + '\n')
        journals[role] = m.bound(path)
    source = out / 'episode.json'
    source.write_text(json.dumps({'frame': {'file': image.name, 'sha256': m.bound(image)['sha256']},
        'journal_sources': journals}))
    store = m.LocalSources()
    value = store.get(m.bound(source))
    assert value['journal_sources'] == journals
    assert store.digests[str(image.relative_to(root))] == m.bound(image)['sha256']
    assert store.raw_journals[str((out / 'packets.jsonl').relative_to(root))] == [{'time': 12, 'kind': 'packets'}]
    image.write_bytes(b'replaced after capture')
    with pytest.raises(RuntimeError, match='PNG bytes changed'):
        m.LocalSources().get(m.bound(source))


@pytest.mark.parametrize('bad_time', ['missing', None, float('nan'), float('inf'), float('-inf')])
@pytest.mark.parametrize('attribution', ['native_session', 'physical_session', 'foreign_account2', 'foreign_guid2'])
def test_journal_collector_rejects_malformed_attributed_time_before_filtering(tmp_path, monkeypatch, bad_time, attribution):
    from tools.client_compatibility.observation import journal
    root = tmp_path / 'lab'
    out = root / 'evidence/capture'
    out.mkdir(parents=True)
    monkeypatch.setattr(m.lab, 'ROOT', root)
    ready = {'native_session': 'native'}
    failed = {'started_at': 10., 'entry_input_finished_at': 12.}
    auth = {'time': 11., 'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical'}
    row = {'event': 'instance_authenticated', 'session': 'foreign', 'account_id': 3}
    if attribution == 'native_session': row['session'] = 'native'
    elif attribution == 'physical_session': row['session'] = 'physical'
    elif attribution == 'foreign_account2': row['account_id'] = 2
    else: row['guid'] = 2
    if bad_time != 'missing': row['time'] = bad_time
    monkeypatch.setattr(journal, 'entries', lambda path: iter([auth, row] if path.name == 'modern_world.jsonl' else []))
    calls = []
    monkeypatch.setattr(m, 'history_contract', lambda: SimpleNamespace(failed_history=lambda *args: calls.append(args)))
    with pytest.raises(RuntimeError, match='attributable journal time'):
        m.journal_history(SimpleNamespace(out=out), ready, failed, 20.)
    assert calls == []


@pytest.mark.parametrize('fault', ['png_changed', 'png_missing', 'old_png', 'changed_source',
    'wrong_character', 'wrong_level', 'wrong_pid', 'wrong_display', 'wrong_window'])
def test_review_refuses_changed_images_labels_and_owned_child(tmp_path, monkeypatch, fault):
    t, path, ref, captured, image = review_setup(tmp_path, monkeypatch)
    if fault == 'png_changed': image.write_bytes(b'replaced')
    elif fault == 'png_missing': image.unlink()
    elif fault == 'old_png': monkeypatch.setattr(m.time, 'time', lambda: image.stat().st_mtime + 121)
    elif fault in ('changed_source', 'wrong_character', 'wrong_level'):
        value = json.loads(path.read_text())
        if fault == 'changed_source': value['source']['sha256'] = 'a' * 64
        elif fault == 'wrong_character': value['selected_character'] = 'Harnessone'
        else: value['selected_level'] = True
        path.write_text(json.dumps(value))
    else:
        current = monitor()
        key = {'wrong_pid': 'game_pid', 'wrong_display': 'display', 'wrong_window': 'window_id'}[fault]
        current['input_isolation'][key] = ':7' if key == 'display' else 777
        monkeypatch.setattr(m, 'continuation', lambda: SimpleNamespace(focus=lambda: current))
    with pytest.raises(RuntimeError):
        m.review(t, path, ref, captured)


def pause_setup(tmp_path, monkeypatch):
    out = tmp_path / 'pause'
    out.mkdir()
    before, *_ = fixture()
    frame = {'file': 'capture.png', 'sha256': 'a' * 64, 'monitor': monitor()}
    ready = {'actor': {'guid': 2}, 'runtime': {'client': {'pid': 22}, 'worldserver': {'pid': 44},
        'modern_world': {'pid': 55}}, 'frame': frame, 'all_offline_snapshot': before}
    ref = {'path': str(tmp_path / 'original.json'), 'sha256': 'b' * 64}
    captured = {'schema': m.SCHEMA, 'phase': m.CAPTURE_PHASE, 'completed': True, 'input_sent': False,
        'mutation_sent': False, 'excluded_failed_entry': True, 'qualification_added': False,
        'code_commit': 'c' * 40, 'committed_sources': [], 'before': before, 'frame': frame,
        'exact_precision': {'row': {'actual': 'float'}, 'source': None}}
    fields = ('original_preparation_source', 'original_entry_source', 'before_precision_source', 'lobby_source',
        'no_input_attestation_source', 'authority_source', 'runtime_authority_source', 'primary_stop_source')
    captured.update({k: ref for k in fields})
    captured.update(failed_housekeeping_sources=[ref, ref], predecessor={}, native_session='actual', code_epochs={})
    t = SimpleNamespace(out=out, fixture=ready['actor'], receipt={'runtime': ready['runtime'],
        'code_commit': captured['code_commit'], 'committed_sources': []}, persist=lambda: None)
    stops, focuses = [], []
    def focus():
        value = monitor()
        focuses.append(value)
        return value
    from contextlib import nullcontext
    c = SimpleNamespace(focus=focus, shot=lambda p: {'file': p.name, 'sha256': 'd' * 64, 'monitor': monitor()},
        snapshot=lambda: deepcopy(before), scout_peer_primary=nullcontext, gone=lambda *args: True,
        identity=lambda key: ready['runtime'][key], registration=lambda: ready['actor'])
    monkeypatch.setattr(m, 'continuation', lambda: c)
    monkeypatch.setattr(m, 'bound', lambda p: ref)
    loads = iter((captured, ready, {}))
    monkeypatch.setattr(m, 'load', lambda value, success=None: next(loads))
    monkeypatch.setattr(m, 'current_sources', lambda t: None)
    monkeypatch.setattr(m, 'owner', lambda *args: ({}, {'after': before['1']}, c.focus()))
    monkeypatch.setattr(m, 'offline_state', lambda *args: deepcopy(before))
    monkeypatch.setattr(m, 'review', lambda *args: {})
    monkeypatch.setattr(m, 'capture_preflight', lambda *args: None)
    monkeypatch.setattr(m, 'read_precision', lambda *args: {'actual': 'float'})
    monkeypatch.setattr(m, 'journal_history', lambda *args: ({'honest_full_history': True}, {}))
    monkeypatch.setattr(m.lab, 'proc_start', lambda pid: '12345')
    monkeypatch.setattr(m.lab, 'stop', lambda kind: stops.append(kind))
    monkeypatch.setattr(m.lab, 'owned_process', lambda kind: None)
    return t, captured, c, stops, focuses


def test_pause_rechecks_exact_captured_child_before_stop_and_records_all_eight_checks(tmp_path, monkeypatch):
    t, captured, _, stops, focuses = pause_setup(tmp_path, monkeypatch)
    m.pause(t, tmp_path / 'capture.json', tmp_path / 'review.json')
    assert stops == ['client']
    assert len(focuses) == 3
    assert t.receipt['game_before']['pid'] == captured['frame']['monitor']['input_isolation']['game_pid']
    assert t.receipt['phase'] == m.PAUSE_PHASE
    assert t.receipt['shutdown_checks'] == dict.fromkeys(m.STOP_CHECKS, True)


@pytest.mark.parametrize('when', ['closing_frame', 'after_closing_frame', 'late_before_stop'])
@pytest.mark.parametrize('field', ['game_pid', 'display', 'window_id'])
def test_pause_refuses_replaced_child_at_each_final_boundary(tmp_path, monkeypatch, when, field):
    t, _, c, stops, _ = pause_setup(tmp_path, monkeypatch)
    def changed():
        value = monitor()
        value['input_isolation'][field] = ':7' if field == 'display' else 77
        return value
    if when == 'closing_frame':
        c.shot = lambda path: {'file': path.name, 'sha256': 'd' * 64, 'monitor': changed()}
    else:
        calls = 0
        def focus():
            nonlocal calls
            calls += 1
            return changed() if calls == (2 if when == 'after_closing_frame' else 3) else monitor()
        c.focus = focus
    with pytest.raises(RuntimeError):
        m.pause(t, tmp_path / 'capture.json', tmp_path / 'review.json')
    assert stops == []


def test_pause_refuses_current_whole_source_preflight_before_stop(tmp_path, monkeypatch):
    t, _, _, stops, _ = pause_setup(tmp_path, monkeypatch)
    def refuse(*args):
        raise RuntimeError('actual archived source or native history differs')
    monkeypatch.setattr(m, 'capture_preflight', refuse)
    with pytest.raises(RuntimeError, match='archived source'):
        m.pause(t, tmp_path / 'capture.json', tmp_path / 'review.json')
    assert stops == []


def test_pause_refuses_a_changed_offline_boundary_after_long_journal_replay(tmp_path, monkeypatch):
    t, captured, _, stops, _ = pause_setup(tmp_path, monkeypatch)
    calls = 0
    def state(*args):
        nonlocal calls
        calls += 1
        value = deepcopy(captured['before'])
        if calls == 3:
            value['2']['native']['online'] = 1
        return value
    monkeypatch.setattr(m, 'offline_state', state)
    with pytest.raises(RuntimeError, match='immediately before stop'):
        m.pause(t, tmp_path / 'capture.json', tmp_path / 'review.json')
    assert stops == []


def test_trial_failure_stays_excluded_and_keeps_actual_error():
    t = SimpleNamespace(receipt={}, persist=lambda: None)
    def fail():
        raise RuntimeError('actual closure refusal')
    with pytest.raises(RuntimeError, match='actual closure refusal'):
        m.run_trial(t, fail)
    assert t.receipt['completed'] is False
    assert t.receipt['qualification_added'] is False
    assert t.receipt['input_sent'] is False
    assert t.receipt['failure'] == 'RuntimeError: actual closure refusal'
    assert 'finished_at' in t.receipt


def test_trial_success_does_not_invent_any_housekeeping_or_bag_input():
    t = SimpleNamespace(receipt={}, persist=lambda: None)
    m.run_trial(t, lambda: t.receipt.update(completed=True, phase=m.CAPTURE_PHASE))
    assert t.receipt['operations_admitted'] == 0
    assert t.receipt['input_sent'] is t.receipt['mutation_sent'] is False
    assert t.receipt['softTargetInteract']['original_restored'] is False

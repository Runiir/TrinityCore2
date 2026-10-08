"""A parked scout's exact physical child remains the stop authority."""
from copy import deepcopy
import importlib
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_bag_swap_continuation as m
from tools.client_compatibility import bag_swap_evidence as evidence
from tools.client_compatibility.world.tests.test_bag_swap_operation import monitor


def test_memory_guard_precedes_bulky_actual_predecessor_stream(monkeypatch):
    calls = []
    monkeypatch.setattr(m, 'available_memory_kib', lambda: 6 * 1024 * 1024 - 1)
    monkeypatch.setattr(m, 'sources', lambda: SimpleNamespace(source_bundle=lambda *args: calls.append(args)))
    with pytest.raises(RuntimeError, match='before parsing'):
        m.start(Path('/private/resume'), Path('/private/output'), Path('/private/closure'),
            Path('/private/remote'), Path('/private/checkpoint'))
    assert calls == []


def test_close_live_lifecycle_never_loads_or_replays_large_predecessor_graph(tmp_path, monkeypatch):
    from tools.client_compatibility.world.tests.test_bag_swap_full_unit import complete_fixture
    data, _, _, _, expected, _ = complete_fixture(tmp_path, monkeypatch)
    closure = next(value for value in data.values() if value.get('phase') == evidence.PHASE)
    ready = evidence.Sources(data, {}).data[next(member for member, value in data.items()
        if value.get('phase') == 'bags_swap_scout_ready')]
    original = evidence.Sources.get
    def get(store, ref, successful=True):
        assert ref != ready['authority_source'], 'live close must not parse the full predecessor graph'
        return original(store, ref, successful)
    monkeypatch.setattr(evidence.Sources, 'get', get)
    def replay(*args, **kwargs):
        raise AssertionError('live close must not replay the full predecessor graph')
    monkeypatch.setattr(evidence, 'validate_bundle', replay)
    result, final, _ = evidence.local_lifecycle(closure['sources'])
    assert result == expected and final == closure['after']


def setup(tmp_path, monkeypatch):
    root = tmp_path / 'lab'
    directory = root / 'evidence/swap'
    directory.mkdir(parents=True)
    monkeypatch.setattr(m.lab, 'ROOT', root)
    keys = ('preparation', 'entry', 'operation', 'park', 'before_precision', 'after_precision')
    paths = {}
    for key in keys:
        path = directory / key / 'episode.json'
        path.parent.mkdir()
        path.write_text('{}')
        paths[key] = path
    runtime = {'client': {'pid': 22, 'start_ticks': '2200'}, 'worldserver': {'pid': 44, 'start_ticks': '4400'},
        'modern_world': {'pid': 55, 'start_ticks': '5500'}}
    actor = {'guid': 2}
    snapshot = {str(g): {'native': {'online': 0}} for g in range(1, 7)}
    old_frame = {'file': 'park.png', 'sha256': 'a' * 64, 'monitor': monitor()}
    ready = {'runtime': runtime, 'actor': actor, 'code_commit': 'c' * 40,
        'authority_source': {'path': str(directory / 'authority.json'), 'sha256': 'a' * 64},
        'predecessor': {'primary_stop': {'path': str(directory / 'original_stop.json'), 'sha256': 'b' * 64}}}
    current = [{**ready} for _ in keys]
    current[3]['frame'] = old_frame
    writes, stops = [], []
    out = directory / 'close'
    out.mkdir()
    t = SimpleNamespace(out=out, fixture=actor, receipt={'started_at': 100, 'code_commit': 'c' * 40,
        'runtime': runtime, 'actor': actor, 'completed': False, 'failure': None})
    t.persist = lambda: writes.append(deepcopy(t.receipt))
    monkeypatch.setattr(evidence, 'local_lifecycle', lambda refs: ({'bounded_joint_proof': True}, snapshot, current))
    monkeypatch.setattr(m, 'runtime', lambda: runtime)
    monkeypatch.setattr(m, 'registration', lambda: actor)
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(snapshot))
    monkeypatch.setattr(m, 'primary_stopped', lambda path: {'after': snapshot['1']})
    monkeypatch.setattr(m, 'review', lambda *args: ({'source': m.sources().bound(paths['park']),
        'selected_character': 'Harnesstwo', 'selected_level': 1}, {}))
    monkeypatch.setattr(m, 'focus', lambda: monitor())
    monkeypatch.setattr(m, 'shot', lambda path: {'file': path.name, 'sha256': 'd' * 64, 'monitor': monitor()})
    monkeypatch.setattr(m.lab, 'proc_start', lambda pid: '2300')
    monkeypatch.setattr(m.lab, 'stop', lambda kind: stops.append(kind))
    monkeypatch.setattr(m.lab, 'owned_process', lambda kind: None)
    monkeypatch.setattr(m, 'gone', lambda *args: True)
    monkeypatch.setattr(m, 'identity', lambda kind: runtime[kind])
    monkeypatch.setattr(m, 'final_logout_history', lambda *args: {'whole_replay': True})
    return t, paths, stops, writes


def close(t, paths):
    return m.close_pause(t, paths['preparation'], paths['entry'], paths['operation'], paths['park'],
        paths['before_precision'], paths['after_precision'], Path('/private/review.json'))


def test_close_binds_parked_child_at_focus_frame_and_immediately_before_stop(tmp_path, monkeypatch):
    t, paths, stops, writes = setup(tmp_path, monkeypatch)
    close(t, paths)
    assert stops == ['client'] and t.receipt['phase'] == 'bags_swap_closed_paused'
    assert t.receipt['game_before'] == {'pid': 23, 'start_ticks': '2300'}
    assert set(t.receipt['shutdown_checks']) == set(m.PAUSE_CHECKS)
    assert all(value is True for value in t.receipt['shutdown_checks'].values())
    assert writes[-2]['stop_attempted'] is True


def test_pre_stop_whole_logout_history_failure_prevents_client_stop(tmp_path, monkeypatch):
    t, paths, stops, _ = setup(tmp_path, monkeypatch)
    def changed(*args):
        raise RuntimeError('whole owner history changed')
    monkeypatch.setattr(m, 'final_logout_history', changed)
    with pytest.raises(RuntimeError, match='whole owner history changed'):
        close(t, paths)
    assert stops == []


def test_whole_native_logout_replay_includes_owner_and_items_through_actual_completion(tmp_path, monkeypatch):
    from tools.client_compatibility.world.tests.test_bag_swap_evidence import fixture
    from tools.client_compatibility import bag_swap_contract as contract
    _, _, _, current, _, wire, _ = fixture(tmp_path, monkeypatch)
    ready, entry, _, park, _, _ = current
    ordered = m.logout_packets(wire, 'scout', 1103, 1103.3)
    raw, replay = m.whole_logout_history(wire, entry, 'scout', ordered)
    assert replay == contract.native_replay(wire, 'scout', entry['started_at'], 1103.2, rest_threshold=24)
    assert raw[-1]['name'] == 'SMSG_LOGOUT_COMPLETE' and raw[-1]['direction'] == 'from_native'
    park.update(logout_packets=ordered, raw_native_logout_history=raw, native_logout_proof=replay)
    monkeypatch.setattr(m, 'packets', lambda: wire)
    assert m.final_logout_history(ready, entry, park) == replay
    park['raw_native_logout_history'] = raw[:-1]
    with pytest.raises(RuntimeError, match='whole owner/item history'):
        m.final_logout_history(ready, entry, park)


@pytest.mark.parametrize('field,value', [('game_pid', 24), ('display', ':4'), ('window_id', 10)])
@pytest.mark.parametrize('stage', ['first_focus', 'closing_png', 'final_focus'])
def test_replacement_pid_display_or_window_cannot_become_stop_authority(tmp_path, monkeypatch, field, value, stage):
    t, paths, stops, _ = setup(tmp_path, monkeypatch)
    replaced = monitor()
    replaced['input_isolation'][field] = value
    if stage == 'closing_png':
        monkeypatch.setattr(m, 'shot', lambda path: {'file': path.name, 'sha256': 'd' * 64, 'monitor': replaced})
    else:
        calls = [0]
        def focus():
            calls[0] += 1
            return replaced if (stage == 'first_focus' or calls[0] == 3) else monitor()
        monkeypatch.setattr(m, 'focus', focus)
    with pytest.raises(RuntimeError, match='original game PID'):
        close(t, paths)
    assert stops == [] and t.receipt['completed'] is False


@pytest.mark.parametrize('error', [KeyboardInterrupt, SystemExit, RuntimeError])
def test_first_failure_remains_closed_and_input_is_not_replayed(tmp_path, error):
    writes = []
    t = SimpleNamespace(receipt={'completed': False, 'failure': None}, persist=lambda: writes.append(True))
    called = []
    def operation():
        called.append(True)
        raise error('stopped')
    if error is RuntimeError:
        m.execute_trial(t, operation)
    else:
        with pytest.raises(error):
            m.execute_trial(t, operation)
    assert called == [True] and t.receipt['completed'] is False
    assert t.receipt['failure'].startswith(error.__name__ + ':') and t.receipt['finished_at'] > 0 and writes


@pytest.mark.parametrize('module', ['interaction_bag_swap', 'interaction_bag_swap_continuation',
    'bag_swap_evidence', 'checkpoint_bag_swap', 'review_bag_swap_checkpoint'])
def test_help_is_pure_without_auth_ui_sql_or_protocol_stack(module):
    code = """import importlib, runpy, sys
name = 'tools.client_compatibility.' + sys.argv[1]
before = set(sys.modules)
sys.argv = [name, '--help']
try:
    runpy.run_module(name, run_name='__main__')
except SystemExit as error:
    assert error.code == 0
assert not any(n.startswith(('google.protobuf', 'tools.client_compatibility.auth', 'PIL', 'tools.second_client')) for n in set(sys.modules) - before)
"""
    result = subprocess.run([sys.executable, '-c', code, module], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr


def test_import_is_pure():
    before = set(sys.modules)
    importlib.reload(m)
    assert not any(n.startswith(('google.protobuf', 'tools.client_compatibility.auth')) for n in set(sys.modules) - before)

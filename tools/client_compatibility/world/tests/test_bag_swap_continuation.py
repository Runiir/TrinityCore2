"""A parked scout's exact physical child remains the stop authority."""
from copy import deepcopy
import importlib
import json
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


def test_final_all_six_snapshot_is_rechecked_after_history_before_stop(tmp_path, monkeypatch):
    t, paths, stops, _ = setup(tmp_path, monkeypatch)
    original = m.snapshot()
    changed = deepcopy(original)
    changed['2']['native']['online'] = 1
    reads = iter([original, changed])
    monkeypatch.setattr(m, 'snapshot', lambda: next(reads))
    with pytest.raises(RuntimeError, match='immediately before client stop'):
        close(t, paths)
    assert stops == []


def test_live_journals_retain_only_fresh_bounded_rows_and_validate_before_filter(monkeypatch):
    events = [{'event': 'world_authenticated', 'account_id': 2, 'session': 'owner', 'time': 100},
        {'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical', 'time': 101},
        {'event': 'modern_packet', 'session': 'physical', 'time': 102}]
    def metadata():
        yield from ({'session': 'older', 'time': i} for i in range(100))
        yield from events
        yield {'session': 'physical', 'time': 110}
    def packets():
        yield from ({'session': 'other', 'time': i} for i in range(100000))
        yield {'session': 'owner', 'time': 99}
        yield {'session': 'owner', 'time': 102, 'body': '00'}
        yield {'session': 'physical', 'time': 103, 'body': '01'}
        yield {'session': 'owner', 'time': 110}
    monkeypatch.setattr(m, 'metadata', metadata)
    monkeypatch.setattr(m, 'packets', packets)
    assert m.history_events(None, 100, 105) == events
    assert m.history_packets('owner', 100, 105, instance='physical') == [
        {'session': 'owner', 'time': 102, 'body': '00'}, {'session': 'physical', 'time': 103, 'body': '01'}]


@pytest.mark.parametrize('kind', ['events', 'packets'])
@pytest.mark.parametrize('attribution', [{'session': 'owner'}, {'session': 'physical'},
    {'session': 'foreign', 'account_id': 2}, {'session': 'foreign', 'guid': 2}])
@pytest.mark.parametrize('bad', [None, True, '1', float('nan'), float('inf'), -float('inf')])
def test_live_journal_malformed_attributable_time_refuses_before_range_filter(monkeypatch, kind, attribution, bad):
    auth = {'event': 'instance_authenticated', 'account_id': 2, 'session': 'physical', 'time': 101}
    malformed = {**attribution, 'time': bad, 'event': 'modern_packet'}
    monkeypatch.setattr(m, 'metadata', lambda: iter([auth, malformed] if kind == 'events' else [auth]))
    monkeypatch.setattr(m, 'packets', lambda: iter([malformed]))
    with pytest.raises(RuntimeError, match='attributable'):
        if kind == 'events':
            m.history_events('owner', 100, 105)
        else:
            m.history_packets('owner', 100, 105, instance='physical')


def fresh_entry_history():
    from tools.client_compatibility.world.tests.test_bag_swap_contract import fresh_roundtrip
    from tools.client_compatibility.bag_swap_login_sync import login_sync
    value = fresh_roundtrip()
    until = value['until'] - 4
    entry = {'native_session': value['session'], 'started_at': value['since'], 'finished_at': until,
        'native_before_entry': dict(zip(('position_x', 'position_y', 'position_z', 'orientation'), value['baseline_pose']))}
    entry['login_sync'] = login_sync(value['rows'], value['events'], value['session'], value['since'], until,
        value['baseline_pose'])
    entry['native_owner_proof'] = m.native_replay(value['rows'], value['session'], value['since'], until,
        login_sync=entry['login_sync'])
    return entry, value


def test_fresh_whole_logout_rederives_boot_from_actual_raw_and_both_session_metadata(monkeypatch):
    from tools.client_compatibility import bag_swap_contract as contract
    entry, value = fresh_entry_history()
    monkeypatch.setattr(m, 'metadata', lambda: iter(value['events']))
    ordered = m.logout_packets(value['rows'], value['session'], entry['finished_at'], value['until'])
    raw, replay = m.whole_logout_history(value['rows'], entry, value['session'], ordered)
    source, destination = contract.SOURCE['guid'], contract.DESTINATION['guid']
    assert replay['native_inventory_states'] == [[source, destination], [destination, source], [source, destination]]
    assert raw[-1]['name'] == 'SMSG_LOGOUT_COMPLETE'
    assert m.entry_settlement(entry, value['rows'], value['events'], required=True) == entry['login_sync']


@pytest.mark.parametrize('fault', ['later_physical_movement', 'duplicate_forward_event', 'wrong_pose', 'wrong_sync'])
def test_fresh_whole_logout_refuses_unbound_boot_or_later_physical_movement(monkeypatch, fault):
    entry, value = fresh_entry_history()
    if fault == 'later_physical_movement':
        value['events'].append({'session': entry['login_sync']['instance_session'], 'time': entry['finished_at'] + .5,
            'event': 'modern_packet', 'name': 'CMSG_MOVE_HEARTBEAT', 'direction': 'from_client', 'bytes': 54})
    elif fault == 'duplicate_forward_event':
        value['events'].append(deepcopy(next(row for row in value['events'] if row.get('event') == 'movement_forwarded')))
    elif fault == 'wrong_pose':
        entry['native_before_entry']['position_x'] += 1
    else:
        entry['login_sync']['instance_session'] = 'different'
    monkeypatch.setattr(m, 'metadata', lambda: iter(value['events']))
    ordered = m.logout_packets(value['rows'], value['session'], entry['finished_at'], value['until'])
    with pytest.raises(RuntimeError):
        m.whole_logout_history(value['rows'], entry, value['session'], ordered)


@pytest.mark.parametrize('fault', [None, 'protected_actor', 'owner_health'])
def test_fresh_enter_producer_retains_actual_boot_and_honest_online_accounting(tmp_path, monkeypatch, fault):
    from tools.client_compatibility import bag_swap_contract as contract
    from tools.client_compatibility.bag_swap_login_sync import login_sync
    from tools.client_compatibility.world.tests.test_bag_swap_login_sync import fresh_login
    from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture
    from tools.client_compatibility.world.tests.test_item_actionbar_contract import public
    from tools.client_compatibility.world.tests.test_bag_swap_contract import resources
    value = fresh_login()
    before, _, *_ = fixture()
    before['2']['native']['rest_bonus'] = 53.4382
    before['2']['native']['logout_time'] = int(value['since']) - 10
    after = deepcopy(before)
    after['2']['native'].update(online=1, rest_bonus=53.5, latency=100,
        totaltime=before['2']['native']['totaltime'] + 10, leveltime=before['2']['native']['leveltime'] + 10)
    if fault == 'protected_actor': after['5']['native']['online'] = 1
    elif fault == 'owner_health': after['2']['native']['health'] -= 1
    preparation, precision = tmp_path / 'ready.json', tmp_path / 'precision.json'
    preparation.write_text('{}')
    precision.write_text('{}')
    root = tmp_path / 'lab'
    out = root / 'evidence/entry'
    out.mkdir(parents=True)
    monkeypatch.setattr(m.lab, 'ROOT', root)
    image = {'file': 'entered.png', 'sha256': 'a' * 64, 'monitor': monitor(),
        'movement': {'dead': False, 'in_combat': False, 'speed': 0}}
    ready = {'frame': image, 'native_session': value['session'], 'all_offline_snapshot': before}
    authority = root / 'evidence/runtime_authority.json'
    authority.write_text(json.dumps({'schema': m.sources().RUNTIME_SCHEMA}) + '\n')
    ready['runtime_authority_source'] = m.sources().bound(authority)
    private_json = m.sources().private_json
    monkeypatch.setattr(m.sources(), 'private_json', lambda path, successful=True:
        private_json(path, successful, root=root))
    threshold = contract.native_replay(value['rows'], value['session'], value['since'], value['until'],
        login_sync=login_sync(*(value[k] for k in ('rows', 'events', 'session', 'since', 'until', 'baseline_pose'))))['rest_threshold']
    state = {'player': 'Harnesstwo', 'level': 1, 'guid': 'Player-0-2', 'xp': 0, 'xp_max': 400,
        'xp_exhaustion': 2 * threshold, 'bags': [], 'panels': [], 'cursor_info': {}}
    inputs, writes = [], []
    t = SimpleNamespace(out=out, fixture={'guid': 2}, guid='Player-0-2',
        receipt={'started_at': value['since'], 'native_session': value['session'],
            'runtime': {'client': {'pid': 22}}, 'completed': False, 'failure': None},
        io=SimpleNamespace(click=lambda *args, **kwargs: inputs.append(args)), observe=lambda *args, **kwargs: (state, image))
    t.persist = lambda: writes.append(deepcopy(t.receipt))
    monkeypatch.setattr(m, 'prepared', lambda *args: ready)
    monkeypatch.setattr(m, 'precision_source', lambda *args: {'finished_at': value['since'] - 1})
    monkeypatch.setattr(m, 'review', lambda *args: ({'source': m.sources().bound(preparation),
        'selected_character': 'Harnesstwo', 'selected_level': 1, 'point': [640, 660]}, {}))
    monkeypatch.setattr(m, 'focus', monitor)
    monkeypatch.setattr(m.time, 'time', lambda: value['until'])
    monkeypatch.setattr(m.time, 'sleep', lambda seconds: None)
    monkeypatch.setattr(m, 'session', lambda actor: value['session'])
    monkeypatch.setattr(m, 'packets', lambda: iter(value['rows']))
    monkeypatch.setattr(m, 'metadata', lambda: iter(value['events']))
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(after))
    monkeypatch.setattr(m, 'oracle', lambda owner: {'current': True})
    monkeypatch.setattr(m, 'resources', lambda native: resources())
    monkeypatch.setattr(m, 'bars', lambda *args: public(before['2']['saved']['actions']))
    monkeypatch.setattr(m, 'native_baseline', lambda trial: {'pose': {'stand': 0, 'sheath': 0},
        'afk': False, 'selection': {'native_guid': 0}})
    if fault:
        with pytest.raises(RuntimeError): m.enter(t, preparation, precision, tmp_path / 'review.json')
        assert t.receipt['completed'] is False and t.receipt['failure']
    else:
        m.enter(t, preparation, precision, tmp_path / 'review.json')
        assert t.receipt['completed'] is True and t.receipt['phase'] == 'bags_swap_entered'
        assert t.receipt['entered_native'] == after['2']['native']
        assert t.receipt['online_preservation']['rest_attribution_pending'] is True
        assert t.receipt['raw_entry_packets'] == value['rows'] and t.receipt['raw_entry_events'] == value['events']
        assert m.entry_settlement(t.receipt, value['rows'], value['events'], required=True) == t.receipt['login_sync']
    assert inputs == [(640, 660)] and writes
    assert t.receipt['raw_entry_packets'] == value['rows'] and t.receipt['raw_entry_events'] == value['events']


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


def initialized_start(tmp_path, monkeypatch, *, indexed=True):
    """Run the real initializer/start with every live dependency explicitly fake."""
    import types
    from tools.client_compatibility import checkpoint_interactions as initializer
    from tools.client_compatibility import bag_swap_indexed_sources as provider
    from tools.client_compatibility import bag_swap_fresh_sources as historical_provider
    from tools.client_compatibility import checkpoint_bag_swap as publication
    from tools.client_compatibility import bag_swap_projection as projection
    from tools.client_compatibility.world.tests.test_bag_swap_indexed_sources import core
    root = tmp_path / 'lab'
    (root / 'evidence').mkdir(parents=True)
    batch = root / 'evidence/ui174'
    old = core(root)
    old['closure']['owned_game_identity']['pid'] = 2147483647
    old['closure']['owned_game_identity']['frame']['monitor']['input_isolation']['game_pid'] = 2147483647
    if not indexed:
        old['closure']['game_before'] = {'pid': 2147483647, 'start_ticks': '99999'}
    calls, writes = [], []
    state = {'extra_client': None, 'current_snapshot': deepcopy(old['snapshot']), 'launches': 0, 'now': 104.0}
    monkeypatch.setattr(m.lab, 'ROOT', root)
    monkeypatch.setattr(m.lab, 'REPO', tmp_path / 'repo')
    monkeypatch.setenv('CLIENT442_ACTOR', 'scout')
    monkeypatch.setattr(m.lab, 'owned_process', lambda kind: old['runtime']['worldserver'])
    monkeypatch.setattr(m.subprocess, 'check_output', lambda *a, **k: 'd' * 40)
    monkeypatch.setattr(m.time, 'time', lambda: state['now'])
    initializer.initialize(batch)
    calls.append('initialize')
    state['now'] = 105.0
    refs = {'batch_source': m.sources().bound(batch / 'batch.json'),
        'native_server_before_source': m.sources().bound(batch / 'native_server_before.json')}
    monkeypatch.setattr(m, 'available_memory_kib', lambda: 12 * 1024 * 1024)
    monkeypatch.setattr(m, 'snapshot', lambda: calls.append('snapshot') or deepcopy(state['current_snapshot']))
    monkeypatch.setattr(m, 'registration', lambda: calls.append('registration') or old['origin_actor'])
    monkeypatch.setattr(m, 'identity', lambda kind: calls.append(kind) or old['runtime'][kind])
    monkeypatch.setattr(m, 'primary_stopped', lambda path: calls.append('primary_stop') or True)
    monkeypatch.setattr(m, 'gone', lambda *a: True)
    absent = types.ModuleType('tools.client_compatibility.review_hunter_revive_prerequisites')
    def absent_clients():
        calls.append('both_clients_absent')
        if state['extra_client']:
            raise RuntimeError('both clients stopped: ' + state['extra_client'])
    absent.absent_clients = absent_clients
    monkeypatch.setitem(sys.modules, absent.__name__, absent)
    monkeypatch.setattr(provider, 'read_admission_pins', lambda *a, **k: {'actual': 'fake'})
    monkeypatch.setattr(provider, 'preflight_bundle', lambda *a, **k: calls.append('bounded_preflight') or
        {key: old[key] for key in provider.CORE_FIELDS}, raising=False)
    selected = provider if indexed else historical_provider
    def stream(*a, **k):
        calls.append('parent_stream')
        return deepcopy(old)
    monkeypatch.setattr(selected, 'source_bundle', stream)
    if not indexed:
        monkeypatch.setattr(m.sources(), 'private_json', lambda *a, **k: {'schema': 'historical'})
    def write_source(directory, name, value):
        path = Path(directory) / name
        path.write_text(json.dumps(value) + '\n')
        return m.sources().bound(path)
    def carry(*a, **k):
        calls.append('carry')
        return write_source(batch, 'carry.json', {})
    monkeypatch.setattr(selected, 'carry_authority', carry)
    monkeypatch.setattr(selected, 'write_cache', lambda directory, *a:
        write_source(directory, 'authority.json', {}))
    monkeypatch.setattr(selected, 'write_runtime', lambda directory, *a:
        write_source(directory, 'runtime_authority.json', {}))
    def epoch(directory, *a):
        return write_source(directory, 'epoch.json', {'schema': provider.EPOCH_SCHEMA,
            'code_commit': 'd' * 40, 'committed_sources': []})
    monkeypatch.setattr(provider, 'current_code_epoch', epoch)
    monkeypatch.setattr(publication, 'current_code_epoch', epoch)
    monkeypatch.setattr(projection, 'source_identities', lambda *a: [])
    monkeypatch.setattr(m, 'persist', lambda directory, report: writes.append(deepcopy(report)))
    fresh = deepcopy(old['runtime'])
    fresh['client'] = {'pid': 1234, 'start_ticks': '98765'}
    def launch():
        calls.append('launch')
        state['launches'] += 1
    monkeypatch.setattr(m, 'launch', launch)
    monkeypatch.setattr(m, 'runtime', lambda: fresh)
    monkeypatch.setattr(m, 'focus', lambda: {'second_monitor_verified': True, 'monitor': {'name': 'HDMI-1'},
        'input_isolation': {'actor': 'scout', 'host_activation_sent': False}})
    monkeypatch.setattr(m, 'shot', lambda path: {'file': path.name, 'sha256': 'a' * 64})
    def start():
        return m.start(batch / 'resume', batch / 'start', 'closure', 'remote', 'checkpoint',
            indexed_pins='pins' if indexed else None)
    return batch, old, calls, state, writes, refs, start, selected


def test_initialize_then_indexed_start_checks_current_state_before_stream_and_before_launch(tmp_path, monkeypatch):
    batch, _, calls, state, writes, refs, start, _ = initialized_start(tmp_path, monkeypatch)
    report = start()
    first = calls.index('parent_stream')
    second = calls.index('carry')
    launch = calls.index('launch')
    for check in ('both_clients_absent', 'snapshot', 'registration', 'worldserver', 'modern_world', 'primary_stop'):
        assert check in calls[:first] and check in calls[second + 1:launch]
    assert calls[0] == 'initialize' and calls.count('launch') == 1
    assert report['completed'] is True and report['installed'] is True
    assert {key: report[key] for key in refs} == refs
    assert writes[-1]['launch_attempted'] is True
    assert m.sources().bound(batch / 'batch.json') == refs['batch_source']
    assert m.sources().bound(batch / 'native_server_before.json') == refs['native_server_before_source']


@pytest.mark.parametrize('fault', ['missing_batch', 'missing_native', 'wrong_schema', 'extra_field', 'wrong_native',
    'wrong_commit', 'late_initialize', 'before_predecessor', 'bool_time', 'wrong_actor'])
def test_indexed_start_refuses_uninitialized_or_rebound_originals_before_parent_stream(tmp_path, monkeypatch, fault):
    batch, _, calls, state, _, _, start, _ = initialized_start(tmp_path, monkeypatch)
    if fault == 'missing_batch': (batch / 'batch.json').unlink()
    elif fault == 'missing_native': (batch / 'native_server_before.json').unlink()
    elif fault == 'wrong_actor': monkeypatch.setenv('CLIENT442_ACTOR', 'primary')
    else:
        path = batch / ('native_server_before.json' if fault == 'wrong_native' else 'batch.json')
        value = json.loads(path.read_text())
        if fault == 'wrong_schema': value['schema'] = 'other'
        elif fault == 'extra_field': value['fabricated'] = True
        elif fault == 'wrong_native': value['pid'] += 1
        elif fault == 'wrong_commit': value['code_commit'] = 'e' * 40
        elif fault == 'late_initialize': value['started_at'] = state['now'] + 1
        elif fault == 'before_predecessor': value['started_at'] = 100
        else: value['started_at'] = True
        path.write_text(json.dumps(value))
    with pytest.raises(RuntimeError): start()
    assert 'parent_stream' not in calls and state['launches'] == 0 and not (batch / 'resume').exists()


@pytest.mark.parametrize('fault', ['snapshot', 'worldserver', 'modern_world', 'registration', 'primary_stop',
    'primary_client', 'scout_client', 'memory'])
def test_failed_current_preflight_never_streams_parent_or_creates_resume(tmp_path, monkeypatch, fault):
    batch, old, calls, state, _, _, start, _ = initialized_start(tmp_path, monkeypatch)
    if fault == 'snapshot': state['current_snapshot']['2']['native']['online'] = 1
    elif fault in ('worldserver', 'modern_world'):
        monkeypatch.setattr(m, 'identity', lambda kind: {'pid': 10000, 'start_ticks': '1'} if kind == fault else old['runtime'][kind])
    elif fault == 'registration': monkeypatch.setattr(m, 'registration', lambda: {'guid': 5})
    elif fault == 'primary_stop': monkeypatch.setattr(m, 'primary_stopped', lambda *a: False)
    elif fault in ('primary_client', 'scout_client'): state['extra_client'] = fault
    else: monkeypatch.setattr(m, 'available_memory_kib', lambda: 5 * 1024 * 1024)
    with pytest.raises(RuntimeError): start()
    assert 'parent_stream' not in calls and state['launches'] == 0 and not (batch / 'resume').exists()


@pytest.mark.parametrize('new_client', ['primary', 'scout'])
def test_client_appearing_during_carry_blocks_every_launch_side_effect(tmp_path, monkeypatch, new_client):
    _, _, calls, state, writes, _, start, selected = initialized_start(tmp_path, monkeypatch)
    carry = selected.carry_authority
    def changed(*a, **k):
        result = carry(*a, **k)
        state['extra_client'] = new_client
        return result
    monkeypatch.setattr(selected, 'carry_authority', changed)
    with pytest.raises(RuntimeError, match='both clients stopped'): start()
    assert calls.count('both_clients_absent') == 2 and state['launches'] == 0
    assert writes[-1]['completed'] is False and writes[-1]['launch_attempted'] is False
    assert writes[-1]['failure'].startswith('RuntimeError: both clients stopped')


@pytest.mark.parametrize('fault', ['batch', 'native', 'snapshot', 'memory'])
def test_originals_and_current_state_are_rechecked_after_all_source_work(tmp_path, monkeypatch, fault):
    batch, _, _, state, writes, _, start, selected = initialized_start(tmp_path, monkeypatch)
    epoch = selected.current_code_epoch
    def changed(*a, **k):
        result = epoch(*a, **k)
        if fault in ('batch', 'native'):
            path = batch / ('batch.json' if fault == 'batch' else 'native_server_before.json')
            path.write_text(path.read_text() + ' ')
        elif fault == 'snapshot': state['current_snapshot']['3']['native']['online'] = 1
        else: monkeypatch.setattr(m, 'available_memory_kib', lambda: 5 * 1024 * 1024)
        return result
    monkeypatch.setattr(selected, 'current_code_epoch', changed)
    with pytest.raises(RuntimeError): start()
    assert state['launches'] == 0 and writes[-1]['launch_attempted'] is False


def test_create_resume_cannot_invent_a_missing_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(m.lab, 'ROOT', tmp_path)
    batch = tmp_path / 'evidence/ui174'
    with pytest.raises(RuntimeError, match='existing ordinary batch'):
        m.create_resume(batch / 'resume', batch / 'start')
    assert not batch.exists()


def test_valid_historical_no_pin_start_still_uses_original_provider_and_no_new_bindings(tmp_path, monkeypatch):
    _, _, calls, state, _, _, start, _ = initialized_start(tmp_path, monkeypatch, indexed=False)
    report = start()
    assert report['completed'] is True and state['launches'] == 1
    assert 'bounded_preflight' not in calls and calls.index('parent_stream') < calls.index('both_clients_absent')
    assert 'batch_source' not in report and 'native_server_before_source' not in report



def execute_mocked_start(tmp_path):
    """Driver coverage only: real initialize/start, fake live/source dependencies."""
    with pytest.MonkeyPatch.context() as patch:
        batch, _, calls, state, _, refs, start, _ = initialized_start(Path(tmp_path), patch)
        report = start()
        assert report['completed'] is True and state['launches'] == 1
        assert calls.index('initialize') < calls.index('parent_stream') < calls.index('launch')
        assert {key: report[key] for key in refs} == refs
        return {'fake_live_dependencies': True, 'live_authority': False, 'qualification_added': False,
            'initialize_called': True, 'start_called': True, 'launch_mock_called': True,
            'batch_directory': str(batch), 'calls': calls, 'initialization_refs': refs}

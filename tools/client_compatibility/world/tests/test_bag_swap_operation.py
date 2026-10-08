"""Interrupted physical input is consumed once; persistence remains native."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from tools.client_compatibility import interaction_bag_swap as op
from tools.client_compatibility import owned_input
from tools.client_compatibility.world.tests.test_bag_swap_contract import packets, resources


def monitor(game=23, display=':3', window=9):
    return {'second_monitor_verified': True, 'monitor': {'name': 'HDMI-1'}, 'pid': 22,
        'input_isolation': {'actor': 'scout', 'host_activation_sent': False,
            'game_pid': game, 'display': display, 'window_id': window}}


class Trial:
    def __init__(self, path):
        self.out = path
        path.mkdir()
        self.fixture = {'guid': 2}
        self.receipt = {'started_at': 19, 'actor': self.fixture, 'runtime': {'client': {'pid': 22}},
            'preparation_source': {'path': '/private/ready/episode.json', 'sha256': 'a' * 64},
            'native_session': 'scout', 'completed': False, 'failure': None, 'cases': []}
        self.writes, self.inputs = [], []

    def persist(self):
        self.writes.append(deepcopy(self.receipt))

    def execute(self, action):
        self.inputs.append(deepcopy(action))


def setup(tmp_path, monkeypatch, *, reverse=False):
    root = tmp_path / 'lab'
    entry = root / 'evidence/entry/episode.json'
    entry.parent.mkdir(parents=True)
    entry.write_text('{"immutable":"entry"}')
    actual_bound = op.bound
    monkeypatch.setattr(op, 'bound', lambda path: actual_bound(path) if Path(path).is_file() else
        {'path': str(path), 'sha256': 'a' * 64})
    monkeypatch.setattr(op.lab, 'ROOT', root)
    t = Trial(root / 'evidence/output')
    frame = {'file': 'screen.png', 'sha256': 'b' * 64, 'monitor': monitor()}
    base = {'entry_source': op.bound(entry), 'resources': resources(), 'frame': frame}
    old = {'baseline': base, 'frame': frame}
    clock = [20.0]
    raw = packets(reverse=reverse, start=21)
    monkeypatch.setattr(op.time, 'time', lambda: clock[0])
    monkeypatch.setattr(op, 'prior', lambda *args, **kwargs: ({}, 'scout', old))
    monkeypatch.setattr(op, 'current', lambda *args, **kwargs: {'snapshot': {'saved': True},
        'resources': resources(swapped=not reverse), 'state': {'bags': [0], 'cursor_info': []},
        'frame': frame, 'public': {}, 'native_state': {}})
    monkeypatch.setattr(op, 'reviewed_points', lambda *args, **kwargs: ([100, 100], [200, 100]))
    monkeypatch.setattr(op, 'runtime_helpers', lambda: SimpleNamespace(screen_geometry=lambda *args: {'exact_pixels': True}))
    monkeypatch.setattr(op, 'guard', lambda *args, **kwargs: {'no_forbidden_input': True})
    monkeypatch.setattr(op, 'packets', lambda *args: raw)
    monkeypatch.setattr(op, 'native_effect', lambda *args, **kwargs: {'time': 21.3, 'guids': [33, 41]})
    monkeypatch.setattr(op, 'delivered_slots', lambda *args, **kwargs: {'public_guid_delivery': True, 'delivery': {'time': 21.4}})
    monkeypatch.setattr(owned_input, 'focus', lambda: monitor())
    def autosave(*args):
        assert len(t.inputs) == 1
        assert (entry.parent / 'bag_swap_forward_attempt.json').is_file()
        t.receipt['autosave'] = {'saveall_sent': False, 'sql_write_sent': False, 'persisted': True}
        return {'native_saved_forward': True}
    monkeypatch.setattr(op, 'autosave', autosave)
    original = t.execute
    def execute(action):
        kind = 'reverse' if reverse else 'forward'
        assert t.writes[-1][kind + '_input_sent'] is True
        marker = entry.parent / ('bag_swap_' + kind + '_attempt.json')
        assert json.loads(marker.read_text())['consumed'] is True
        original(action)
        clock[0] = 22.0
    t.execute = execute
    return t, base, old, entry


@pytest.mark.parametrize('reverse', [False, True])
def test_one_input_consumes_exact_attempt_before_execution_and_never_calls_saveall(tmp_path, monkeypatch, reverse):
    t, _, _, entry = setup(tmp_path, monkeypatch, reverse=reverse)
    op.drag(t, Path('/private/prep'), Path('/private/stage'), Path('/private/review'), reverse=reverse)
    assert len(t.inputs) == 1 and t.receipt['completed'] is True
    kind = 'reverse' if reverse else 'forward'
    assert t.receipt['phase'] == 'bags_swap_' + kind
    marker = json.loads((entry.parent / ('bag_swap_' + kind + '_attempt.json')).read_text())
    assert marker['input_replay_allowed'] is False and marker['input_intent']['source_slot'] == (2 if reverse else 1)
    assert not hasattr(op, 'server_save')
    from tools.client_compatibility.interaction_metrics import choice_counts
    assert choice_counts([{'controller': 'code', 'cases': t.receipt['cases']}])['code_choices_executed'] == 1
    assert t.receipt['cases'][0]['selection_source'] == 'code'
    if reverse:
        assert 'autosave' not in t.receipt
    else:
        assert t.receipt['autosave']['saveall_sent'] is False


@pytest.mark.parametrize('failure', [RuntimeError, KeyboardInterrupt, SystemExit])
def test_interrupted_forward_retains_consumed_input_and_refuses_any_drag_replay(tmp_path, monkeypatch, failure):
    t, _, _, entry = setup(tmp_path, monkeypatch)
    retained = []
    monkeypatch.setattr(op, 'retain_raw', lambda *args: retained.append(args))
    original = t.execute
    def execute(action):
        original(action)
        raise failure('interrupted after input')
    t.execute = execute
    with pytest.raises(failure):
        op.drag(t, Path('/private/prep'), Path('/private/stage'), Path('/private/review'))
    assert len(t.inputs) == len(retained) == 1
    assert t.receipt['phase'] == 'bags_swap_forward_attempted'
    assert (entry.parent / 'bag_swap_forward_attempt.json').is_file()
    with pytest.raises(RuntimeError, match='already consumed'):
        op.drag(t, Path('/private/prep'), Path('/private/stage'), Path('/private/review'))
    assert len(t.inputs) == 1


@pytest.mark.parametrize('field,value', [('game_pid', 24), ('display', ':4'), ('window_id', 10)])
def test_replaced_physical_child_after_review_consumes_attempt_but_sends_no_input(tmp_path, monkeypatch, field, value):
    t, _, _, entry = setup(tmp_path, monkeypatch)
    current = monitor()
    current['input_isolation'][field] = value
    monkeypatch.setattr(owned_input, 'focus', lambda: current)
    monkeypatch.setattr(op, 'retain_raw', lambda *args: None)
    with pytest.raises(RuntimeError, match='original game PID'):
        op.drag(t, Path('/private/prep'), Path('/private/stage'), Path('/private/review'))
    assert t.inputs == [] and (entry.parent / 'bag_swap_forward_attempt.json').exists()


def test_partial_durable_marker_never_authorizes_a_replayed_input(tmp_path, monkeypatch):
    t, base, _, entry = setup(tmp_path, monkeypatch)
    (entry.parent / 'bag_swap_forward_attempt.json').write_bytes(b'{')
    with pytest.raises(RuntimeError, match='already consumed'):
        op.consumed_attempt(t, base, 'scout', 'forward', {'kind': 'drag'})
    assert t.inputs == []


def test_imports_remain_pure():
    before = set(sys.modules)
    importlib.reload(op)
    assert not any(name.startswith(('google.protobuf', 'tools.client_compatibility.auth')) for name in set(sys.modules) - before)


def current_setup(tmp_path, monkeypatch):
    from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture
    from tools.client_compatibility.world.tests.test_item_actionbar_contract import public
    before, now, *_ = fixture()
    now['2']['native']['online'] = 1
    native = {'health': 60, 'max_health': 60, 'power': 0, 'xp': 0, 'next_xp': 400, 'summon': 0,
        'selection': 0, 'pose': {'stand': 0, 'sheath': 1}, 'afk': False}
    state = {'player': 'Harnesstwo', 'level': 1, 'world_position': [1, 2, 3, 4], 'bags': [], 'bag_items': []}
    frame = {'file': 'closed.png', 'sha256': 'a' * 64, 'monitor': monitor(), 'movement': {}}
    bars = public(before['2']['saved']['actions'])
    base = {'snapshot': before, 'resources': resources(), 'native_state': native, 'state': state,
        'frame': frame, 'public': bars, 'saved': before['2']['saved'], 'active_spec': 0}
    t = SimpleNamespace(receipt={'runtime': {'client': {'pid': 22}}}, observe=lambda label: (state, frame))
    monkeypatch.setattr(op, 'snapshot', lambda: now)
    monkeypatch.setattr(op, 'resources', lambda owner: resources())
    monkeypatch.setattr(op, 'native_state', lambda owner: native)
    monkeypatch.setattr(op, 'detail', lambda *args: bars)
    return t, base


def test_current_final_closed_layout_preserves_native_inventory_and_actions_without_open_bag(tmp_path, monkeypatch):
    t, base = current_setup(tmp_path, monkeypatch)
    assert op.current(t, base, 'scout', swapped=False, closed_layout=True)['state']['bags'] == []
    with pytest.raises(RuntimeError, match='must be open'):
        op.current(t, base, 'scout', swapped=False)


def test_closed_layout_cannot_mask_native_inventory_change(tmp_path, monkeypatch):
    t, base = current_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(op, 'resources', lambda owner: resources(swapped=True))
    with pytest.raises(RuntimeError):
        op.current(t, base, 'scout', swapped=False, closed_layout=True)


@pytest.mark.parametrize('elapsed,accepted', [(149.9, True), (150, True), (150.01, False)])
def test_first_saved_read_after_autosave_deadline_cannot_pass(tmp_path, monkeypatch, elapsed, accepted):
    from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture
    before, now, *_ = fixture(True)
    now['2']['native']['online'] = 1
    root, repo = tmp_path / 'lab', tmp_path / 'repo'
    config = root / 'config/worldserver.conf'
    config.parent.mkdir(parents=True)
    config.write_text('PlayerSaveInterval = 90000\n')
    player = repo / 'src/server/game/Entities/Player/Player.cpp'
    player.parent.mkdir(parents=True)
    player.write_text('m_nextSave = urand(m_nextSave / 2, m_nextSave * 3 / 2);\n'
        'm_nextSave = sWorld->getIntConfig(CONFIG_INTERVAL_SAVE);\n')
    monkeypatch.setattr(op.lab, 'ROOT', root)
    monkeypatch.setattr(op.lab, 'REPO', repo)
    ticks = iter([0, elapsed])
    monkeypatch.setattr(op.time, 'monotonic', lambda: next(ticks))
    monkeypatch.setattr(op, 'snapshot', lambda: now)
    monkeypatch.setattr(op, 'resources', lambda owner: resources(True))
    monkeypatch.setattr(op, 'guard', lambda *args: None)
    t = SimpleNamespace(receipt={}, persist=lambda: None)
    if accepted:
        assert op.autosave(t, {'snapshot': before, 'resources': resources()}, 'scout') == now
    else:
        with pytest.raises(RuntimeError, match='bounded timer'):
            op.autosave(t, {'snapshot': before, 'resources': resources()}, 'scout')


def review_context_setup(tmp_path, monkeypatch):
    """Real preparation/context/review guards with private files and runtime facts."""
    from tools.client_compatibility import actors
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    from tools.client_compatibility import interaction_owned_class_fixture as fixture
    from tools.client_compatibility import item_actionbar_sources as source_files
    from tools.client_compatibility.world.tests.test_bag_swap_preservation import fixture as preserved_fixture
    before, *_ = preserved_fixture()
    now = deepcopy(before)
    now['2']['native']['online'] = 1
    root = tmp_path / 'lab'
    directory = root / 'evidence/current'
    directory.mkdir(parents=True)
    monkeypatch.setattr(op.lab, 'ROOT', root)
    monkeypatch.setattr(source_files, 'ROOT', root)
    t = Trial(directory / 'operation')
    t.fixture = {'guid': 2, 'account_id': 2}
    vector = [{'path': '/synthetic/repo/controller.py', 'sha256': 'a' * 64}]
    t.receipt.update(actor=t.fixture, committed_sources=deepcopy(vector))
    authority = directory / 'offline_authority.json'
    authority.write_text(json.dumps({'snapshot': before}))
    ready = {'completed': True, 'failure': None, 'phase': 'bags_swap_scout_ready',
        'started_at': 17, 'finished_at': 18,
        'actor': t.fixture, 'runtime': t.receipt['runtime'], 'native_session': 'scout',
        'checks': dict.fromkeys(('identity', 'runtime', 'preservation'), True),
        'all_offline_snapshot': before, 'committed_sources': deepcopy(vector),
        'authority_source': op.bound(authority), 'runtime_authority_source': op.bound(authority),
        'predecessor': {'primary_stop': {'path': str(directory / 'primary_stop.json'), 'sha256': 'b' * 64}}}
    preparation = directory / 'preparation/episode.json'
    preparation.parent.mkdir()
    preparation.write_text(json.dumps(ready))
    preparation_ref = op.bound(preparation)
    # This boundary supplies the mocked offline authority file; preparation and
    # the shared screen-review helper themselves execute without replacement.
    monkeypatch.setattr(continuation, 'source_report', lambda report: json.loads(authority.read_text()))
    monkeypatch.setattr(continuation, 'registration', lambda: t.fixture)
    monkeypatch.setattr(continuation, 'runtime', lambda: t.receipt['runtime'])
    monkeypatch.setattr(continuation, 'snapshot', lambda: now)
    monkeypatch.setattr(continuation, 'primary_stopped', lambda path: True)
    monkeypatch.setattr(actors, 'session_entry', lambda actor: {'session': 'scout'})
    monkeypatch.setattr(op, 'source_identities', lambda repo: deepcopy(vector))
    image = directory / 'screen.png'
    image.write_bytes(b'mocked-pixels-for-real-owned-review-contract')
    frame = {'file': image.name, 'sha256': fixture.lab.sha256(image), 'monitor': monitor()}
    review = directory / 'review.json'
    review.write_text(json.dumps({'reviewed': True, 'control': 'MainMenuBarBackpackButton',
        'fixture_source_sha256': preparation_ref['sha256'], 'frame': frame, 'point': [1216, 681]}))
    monkeypatch.setattr(fixture.owned_input, 'focus', lambda: monitor())
    return t, preparation, ready, review, preparation_ref


def test_context_binds_one_preparation_ref_before_real_runtime_screen_review(tmp_path, monkeypatch):
    t, preparation, ready, review, ref = review_context_setup(tmp_path, monkeypatch)
    original_bound, reads = op.bound, []
    def checked(path):
        reads.append(Path(path))
        return original_bound(path)
    monkeypatch.setattr(op, 'bound', checked)
    assert op.context(t, preparation) == (ready, 'scout')
    assert reads == [preparation]
    assert t.writes[-1]['fixture_source'] == t.writes[-1]['preparation_source'] == ref
    assert op.runtime_helpers().reviewed(t, review, 'MainMenuBarBackpackButton')['point'] == [1216, 681]
    assert t.receipt['screen_review']['path'] == str(review)
    assert t.inputs == []


@pytest.mark.parametrize('fault', ['changed_preparation', 'review_source_hash', 'replaced_focus'])
def test_real_context_review_rejects_changed_source_hash_or_focus(tmp_path, monkeypatch, fault):
    t, preparation, ready, review, _ = review_context_setup(tmp_path, monkeypatch)
    if fault == 'changed_preparation':
        preparation.write_text(json.dumps({**ready, 'captured_note': 'changed after review'}))
    elif fault == 'review_source_hash':
        value = json.loads(review.read_text())
        value['fixture_source_sha256'] = 'f' * 64
        review.write_text(json.dumps(value))
    else:
        monkeypatch.setattr(owned_input, 'focus', lambda: monitor(game=24))
    op.context(t, preparation)
    with pytest.raises(RuntimeError, match='fresh reviewed owned class screen differs'):
        op.runtime_helpers().reviewed(t, review, 'MainMenuBarBackpackButton')
    assert 'screen_review' not in t.receipt and t.inputs == []


@pytest.mark.parametrize('fault', ['preparation_phase', 'owner_session', 'committed_sources'])
def test_context_alias_does_not_bypass_existing_preparation_or_source_guards(tmp_path, monkeypatch, fault):
    t, preparation, ready, _, _ = review_context_setup(tmp_path, monkeypatch)
    if fault == 'preparation_phase': ready['phase'] = 'unrelated'
    elif fault == 'owner_session': ready['native_session'] = 'other'
    else: ready['committed_sources'][0]['sha256'] = 'f' * 64
    preparation.write_text(json.dumps(ready))
    expected = {'preparation_phase': 'closed current original scout preparation differs',
        'owner_session': 'fresh prepared owner session', 'committed_sources': 'frozen controller/source identities'}
    with pytest.raises(RuntimeError, match=expected[fault]): op.context(t, preparation)
    assert 'fixture_source' not in t.receipt and t.inputs == []


def failure_context_setup(tmp_path, monkeypatch):
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    t = Trial(tmp_path / 'failure')
    calls, intervals, clock_calls = [], [], []
    values = {'packets': [{'time': 20.5, 'name': 'CMSG_SWAP_INV_ITEM', 'payload': '01'}],
        'events': [{'time': 20.6, 'event': 'modern_packet', 'physical_session': 'instance'}],
        'snapshot': {'saved': True}, 'resources': {'items': []},
        'native_state': {'orientation': 1.0}, 'rendered': ({'bags': [0]}, {'file': 'failure.png'})}
    def clock():
        clock_calls.append(True)
        return 22.0 + len(clock_calls) - 1
    monkeypatch.setattr(op.time, 'time', clock)
    for key in values:
        def read(*args, key=key):
            calls.append(key)
            if key in ('packets', 'events'): intervals.append((key, args))
            return deepcopy(values[key])
        if key == 'events': monkeypatch.setattr(continuation, 'history_events', read)
        elif key == 'rendered': t.observe = read
        else: monkeypatch.setattr(op, key, read)
    return t, continuation, values, calls, intervals, clock_calls


def test_failure_raw_retains_unfiltered_metadata_and_packets_for_one_exact_interval(tmp_path, monkeypatch):
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    actual_history_events = continuation.history_events
    t, continuation, values, calls, intervals, clock_calls = failure_context_setup(tmp_path, monkeypatch)
    # Use the actual bounded metadata reader, including both boundary rows and
    # complete physical/native context that a session or packet-name filter loses.
    events = [{'time': 19.9, 'event': 'older'},
        {'time': 20.0, 'event': 'instance_authenticated', 'session': 'physical', 'account_id': 2},
        {'time': 20.4, 'event': 'modern_packet', 'session': 'realm', 'physical_session': 'physical',
            'name': 'CMSG_OTHER', 'direction': 'from_client', 'native': {'opcode': 17}},
        {'time': 21.0, 'event': 'native_change', 'session': 'physical', 'guid': 2, 'details': {'saved': True}},
        {'time': 22.0, 'event': 'other_actor', 'session': 'unrelated', 'account_id': 7, 'opaque': ['full', 'context']},
        {'time': 22.1, 'event': 'later'}]
    monkeypatch.setattr(continuation, 'metadata', lambda: iter(deepcopy(events)))
    def read_events(*args):
        calls.append('events')
        intervals.append(('events', args))
        return actual_history_events(*args)
    monkeypatch.setattr(continuation, 'history_events', read_events)
    op.retain_raw(t, 'realm', 20.0, 'forward_failure')
    raw = t.receipt['raw_forward_failure']
    assert raw['packets'] == values['packets'] and raw['events'] == events[1:-1]
    assert intervals == [('packets', ('realm', 20.0, 22.0)), ('events', ('realm', 20.0, 22.0))]
    assert clock_calls == [True] and raw['since'] == 20.0 and raw['until'] == raw['observed_at'] == 22.0
    assert calls == ['packets', 'events', 'snapshot', 'resources', 'native_state', 'rendered']
    assert raw['input_replayed'] is False and t.inputs == [] and t.writes == [t.receipt]
    assert t.receipt['completed'] is False and t.receipt['cases'] == []


@pytest.mark.parametrize('failed, error_type', [('packets', RuntimeError), ('events', RuntimeError),
    ('events', KeyboardInterrupt), ('events', SystemExit), ('snapshot', RuntimeError),
    ('resources', RuntimeError), ('native_state', RuntimeError), ('rendered', RuntimeError)])
def test_failure_raw_keeps_explicit_independent_read_failures_and_remaining_context(tmp_path, monkeypatch, failed, error_type):
    t, continuation, values, calls, intervals, clock_calls = failure_context_setup(tmp_path, monkeypatch)
    def fail(*args):
        calls.append(failed)
        if failed in ('packets', 'events'): intervals.append((failed, args))
        raise error_type('diagnostic unavailable')
    if failed == 'events': monkeypatch.setattr(continuation, 'history_events', fail)
    elif failed == 'rendered': t.observe = fail
    else: monkeypatch.setattr(op, failed, fail)
    op.retain_raw(t, 'realm', 20.0, 'reverse_failure')
    raw = t.receipt['raw_reverse_failure']
    assert failed not in raw and raw[failed + '_failure'] == error_type.__name__ + ': diagnostic unavailable'
    assert all(raw[key] == value for key, value in values.items() if key != failed)
    assert calls == ['packets', 'events', 'snapshot', 'resources', 'native_state', 'rendered']
    assert intervals == [('packets', ('realm', 20.0, 22.0)), ('events', ('realm', 20.0, 22.0))]
    assert clock_calls == [True] and raw['since'] == 20.0 and raw['until'] == 22.0
    assert raw['input_replayed'] is False and t.inputs == [] and t.writes == [t.receipt]


@pytest.mark.parametrize('invalid', ['interval', 'attributable_time'])
def test_failure_raw_records_authoritative_metadata_validation_failure(tmp_path, monkeypatch, invalid):
    from tools.client_compatibility import interaction_bag_swap_continuation as continuation
    actual_history_events = continuation.history_events
    t, continuation, values, _, _, clock_calls = failure_context_setup(tmp_path, monkeypatch)
    monkeypatch.setattr(continuation, 'history_events', actual_history_events)
    monkeypatch.setattr(continuation, 'metadata', lambda: iter([{'event': 'modern_packet',
        'session': 'realm', 'physical_session': 'physical', 'time': 'malformed'}]))
    op.retain_raw(t, 'realm', 23.0 if invalid == 'interval' else 20.0, 'forward_failure')
    raw = t.receipt['raw_forward_failure']
    message = ('bounded metadata interval differs' if invalid == 'interval' else
        'malformed attributable packet metadata cannot be filtered out')
    assert raw['events_failure'] == 'RuntimeError: ' + message and 'events' not in raw
    assert raw['packets'] == values['packets'] and raw['snapshot'] == values['snapshot']
    assert clock_calls == [True] and raw['input_replayed'] is False and t.inputs == []
    assert t.writes == [t.receipt]

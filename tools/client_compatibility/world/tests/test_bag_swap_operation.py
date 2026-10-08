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

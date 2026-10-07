"""Producer boundaries retain exact source authority and interrupted raw facts."""
from copy import deepcopy
import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from tools.client_compatibility import interaction_item_actionbar_continuation as m
from tools.client_compatibility import item_actionbar_contract as c
from tools.client_compatibility.world.tests.test_item_actionbar_evidence import fixture
from tools.client_compatibility.world.tests.test_item_actionbar_contract import native_packet


class Trial:
    def __init__(self, path, source, start=1099):
        self.out = path
        path.mkdir()
        self.fixture = deepcopy(source['actor'])
        self.guid = 'Player-1-00000002'
        self.receipt = {'started_at': start, 'completed': False, 'failure': None,
            'runtime': deepcopy(source['runtime']), 'actor': self.fixture}
        self.writes = []
        self.io = self
        self.clicks = []
    def persist(self):
        self.writes.append(deepcopy(self.receipt))
    def click(self, *point, **kwargs):
        self.clicks.append(point)
    def observe(self, *args, **kwargs):
        return deepcopy(self.state), deepcopy(self.frame)


def setup_entry(tmp_path, monkeypatch):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    t = Trial(batch / 'test_enter', values['ready'])
    t.state, t.frame = values['entry']['state'], {**values['entry']['frame'], 'movement': {'dead': False, 'in_combat': False, 'speed': 0}}
    live = deepcopy(values['ready']['all_offline_snapshot'])
    now = [1100.0]
    monkeypatch.setattr(m.time, 'time', lambda: now[0])
    monkeypatch.setattr(m.time, 'sleep', lambda _: None)
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(live))
    monkeypatch.setattr(m, 'registration', lambda: t.fixture)
    monkeypatch.setattr(m, 'runtime', lambda: t.receipt['runtime'])
    monkeypatch.setattr(m, 'primary_stopped', lambda _: {'after': live['1']})
    monkeypatch.setattr(m, 'session', lambda _: 'scout')
    monkeypatch.setattr(m, 'oracle', lambda _: None)
    monkeypatch.setattr(m, 'resources', lambda _: values['entry']['resources'])
    monkeypatch.setattr(m.sources(), 'rest_sources', lambda: values['before_precision']['rest_sources'])
    checked = {'source': m.sources().bound(paths['ready']), 'selected_character': 'Harnesstwo',
        'selected_level': 1, 'point': [640, 660]}
    monkeypatch.setattr(m, 'review', lambda *_: (checked, values['ready']))
    current_wire = [r for r in wire if r['time'] <= 1100.4]
    monkeypatch.setattr(m, 'packets', lambda: iter(current_wire))
    def click(*args, **kwargs):
        assert t.writes[-1]['entry_input_started_at'] == 1100.0
        assert t.writes[-1]['input_sent'] is True
        t.clicks.append(args)
        live['2']['native']['online'] = 1
        now[0] = 1100.5
    t.click = click
    def bars(*args):
        # A benign sparse update arrives after the early observation cutoff.
        current_wire.append(native_packet({c.INDEX['PLAYER_FLAGS']: 0}, creation=False, time=1100.6))
        now[0] = 1100.7
        return values['entry']['public']
    monkeypatch.setattr(m, 'bars', bars)
    monkeypatch.setattr(m, 'native_baseline', lambda _: values['entry']['native_original'])
    return t, paths, values, current_wire, now


def test_entry_seals_complete_native_window_after_final_diagnostics(tmp_path, monkeypatch):
    t, paths, values, raw, now = setup_entry(tmp_path, monkeypatch)
    m.enter(t, paths['ready'], paths['before_precision'], tmp_path / 'review.json')
    assert len(t.clicks) == 1 and t.receipt['completed'] is True
    assert t.receipt['finished_at'] == 1100.7
    proof = c.native_replay(raw, 'scout', t.receipt['started_at'], t.receipt['finished_at'])
    assert t.receipt['native_owner_proof'] == proof
    assert t.receipt['owner_packets'] == proof['packets'] and len(proof['packets']) == 2


@pytest.mark.parametrize('failure', [KeyboardInterrupt, SystemExit, RuntimeError])
def test_entry_interrupt_retains_input_intent_and_raw_without_replay(tmp_path, monkeypatch, failure):
    t, paths, _, raw, now = setup_entry(tmp_path, monkeypatch)
    def interrupted(*_args, **_kwargs):
        raise failure('lost observation')
    t.observe = interrupted
    with pytest.raises(failure): m.enter(t, paths['ready'], paths['before_precision'], tmp_path / 'review.json')
    assert len(t.clicks) == 1 and t.receipt['completed'] is False
    assert t.receipt['failure'].startswith(failure.__name__ + ':')
    assert t.receipt['entry_input_finished_at'] == 1100.5 and len(t.receipt['raw_entry_packets']) == 5


@pytest.mark.parametrize('fault', ['health', 'hunter_pet', 'saved_actions', 'inventory', 'online_peer'])
def test_online_preparation_refuses_owner_or_protected_drift(tmp_path, monkeypatch, fault):
    t, paths, values, raw, now = setup_entry(tmp_path, monkeypatch)
    changed = deepcopy(values['ready']['all_offline_snapshot'])
    changed['2']['native']['online'] = 1
    if fault == 'health': changed['2']['native']['health'] = 59
    elif fault == 'hunter_pet': changed['6']['pets'][0]['curhealth'] = 277
    elif fault == 'saved_actions': changed['2']['saved']['spells'] = [[6948, 1, 0]]
    elif fault == 'inventory': changed['2']['inventory'][0][9] = 2
    else: changed['3']['native']['online'] = 1
    monkeypatch.setattr(m, 'snapshot', lambda: changed)
    with pytest.raises(RuntimeError): m.prepared(t, paths['ready'], online=True)
    assert not t.clicks


@pytest.mark.parametrize('fault', ['bad_modern_guid', 'missing_native_creation', 'resting', 'pet'])
def test_entry_refuses_unattributable_login_or_native_owner(tmp_path, monkeypatch, fault):
    t, paths, values, raw, now = setup_entry(tmp_path, monkeypatch)
    if fault == 'bad_modern_guid': raw[0]['body'] = '00'
    elif fault == 'missing_native_creation': raw[:] = [r for r in raw if r['name'] != 'SMSG_UPDATE_OBJECT']
    elif fault == 'resting': raw.append(native_packet({c.INDEX['PLAYER_FLAGS']: 0x20}, creation=False, time=1100.45))
    else: raw.append(native_packet({c.INDEX['UNIT_FIELD_SUMMON']: 16}, creation=False, time=1100.45))
    with pytest.raises(RuntimeError): m.enter(t, paths['ready'], paths['before_precision'], tmp_path / 'review.json')
    assert len(t.clicks) == 1 and t.receipt['completed'] is False


@pytest.mark.parametrize('fault', ['snapshot', 'protected', 'frame'])
def test_completed_logout_later_failure_keeps_durable_timestamp_packets_and_offline_facts(tmp_path, monkeypatch, fault):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    t = Trial(batch / 'test_park', values['ready'], start=1114)
    ready = deepcopy(values['ready'])
    online = deepcopy(ready['all_offline_snapshot'])
    online['2']['native']['online'] = 1
    offline = deepcopy(values['park']['all_offline_snapshot'])
    current = [online]
    now = [1114.9]
    monkeypatch.setattr(m.time, 'time', lambda: now[0])
    monkeypatch.setattr(m, 'prepared', lambda *_args, **_kwargs: ready)
    monkeypatch.setattr(m, 'packets', lambda: iter(wire))
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(current[0]))
    def logout(_):
        assert t.writes[-1]['logout_started_at'] == 1114.9
        current[0] = offline
        now[0] = 1116
        if fault == 'snapshot':
            monkeypatch.setattr(m, 'snapshot', lambda: (_ for _ in ()).throw(KeyboardInterrupt('snapshot lost')))
        elif fault == 'protected':
            offline['6']['pets'][0]['curhealth'] = 277
    monkeypatch.setattr(m, 'logout', logout)
    monkeypatch.setattr(m, 'shot', lambda _: (_ for _ in ()).throw(RuntimeError('frame lost')))
    with pytest.raises(BaseException): m.park(t, paths['ready'], paths['operation'])
    assert t.receipt['logout_started_at'] == 1114.9 and t.receipt['logout_finished_at'] == 1116
    assert len(t.receipt['raw_logout_packets']) == 4
    if fault != 'snapshot': assert t.receipt['all_offline_snapshot'] == offline


def test_modules_remain_importable_without_ui_auth_protocol_or_pillow(tmp_path):
    code = """import importlib,sys
class Block:
 def find_spec(self,name,path=None,target=None):
  if name.startswith(('PIL','google','Crypto','tools.second_client','tools.client_compatibility.auth','tools.client_compatibility.interaction_trial','tools.client_compatibility.world.control')): raise RuntimeError(name)
sys.meta_path.insert(0,Block())
for name in ('interaction_item_actionbar_continuation','item_actionbar_evidence','checkpoint_item_actionbar','review_item_actionbar_checkpoint'):
 importlib.import_module('tools.client_compatibility.'+name)
print('pure import boundary passed')
"""
    result = subprocess.run([sys.executable, '-B', '-c', code], text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == 'pure import boundary passed'


@pytest.mark.parametrize('failure', [KeyboardInterrupt, SystemExit, RuntimeError])
def test_outer_writer_closes_actual_failure_and_retains_sealed_entry(tmp_path, monkeypatch, failure):
    t = Trial(tmp_path / 'trial', {'actor': {'guid': 2}, 'runtime': {}})
    monkeypatch.setattr(m.time, 'time', lambda: 1200)
    def failed():
        t.receipt.update(phase='item_actionbar_entry_started', input_sent=True, raw_entry_packets=[{'body': '2003'}])
        raise failure('retained interruption')
    if failure is RuntimeError:
        m.execute_trial(t, failed)
    else:
        with pytest.raises(failure): m.execute_trial(t, failed)
    assert t.receipt['completed'] is False and t.receipt['finished_at'] == 1200
    assert t.receipt['failure'] == failure.__name__ + ': retained interruption'
    assert t.writes[-1]['raw_entry_packets'] == [{'body': '2003'}]
    t.receipt.update(finished_at=1199, completed=True, failure=None)
    m.execute_trial(t, lambda: None)
    assert t.receipt['finished_at'] == 1199


@pytest.mark.parametrize('failure', [None, 'snapshot_after_stop'])
def test_closed_pause_stops_once_and_retains_source_intent_before_stop(tmp_path, monkeypatch, failure):
    batch, paths, values, wire, events = fixture(tmp_path, monkeypatch)
    t = Trial(batch / 'test_pause', values['ready'], start=1125)
    snapshot = deepcopy(values['park']['all_offline_snapshot'])
    stopped = []
    monkeypatch.setattr(m, 'registration', lambda: t.fixture)
    monkeypatch.setattr(m, 'runtime', lambda: t.receipt['runtime'])
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(snapshot))
    monkeypatch.setattr(m, 'primary_stopped', lambda _: {'after': snapshot['1']})
    monkeypatch.setattr(m, 'review', lambda *_: ({'source': m.sources().bound(paths['park']),
        'selected_character': 'Harnesstwo', 'selected_level': 1}, values['park']))
    monkeypatch.setattr(m, 'focus', lambda: values['park']['frame']['monitor'])
    monkeypatch.setattr(m.lab, 'proc_start', lambda _: '2100')
    monkeypatch.setattr(m, 'gone', lambda *_: True)
    monkeypatch.setattr(m, 'identity', lambda k: t.receipt['runtime'][k])
    monkeypatch.setattr(m.lab, 'owned_process', lambda _: None)
    monkeypatch.setattr(m, 'shot', lambda _: values['park']['frame'])
    def stop(kind):
        assert t.writes[-1]['stop_attempted'] is True and t.writes[-1]['sources']['operation'] == m.sources().bound(paths['operation'])
        stopped.append(kind)
        if failure:
            monkeypatch.setattr(m, 'snapshot', lambda: (_ for _ in ()).throw(KeyboardInterrupt('after stop snapshot')))
    monkeypatch.setattr(m.lab, 'stop', stop)
    call = lambda: m.close_pause(t, paths['ready'], paths['entry'], paths['operation'], paths['park'],
        paths['before_precision'], paths['after_precision'], tmp_path / 'review.json')
    if failure:
        with pytest.raises(KeyboardInterrupt): m.execute_trial(t, call)
        assert t.receipt['completed'] is False and t.receipt['failure'].startswith('KeyboardInterrupt:')
    else:
        m.execute_trial(t, call)
        assert t.receipt['completed'] is True and t.receipt['phase'] == 'item_actionbar_closed_paused'
        assert t.receipt['before'] == t.receipt['after'] == snapshot
        assert all(t.receipt['shutdown_checks'].values())
    assert stopped == ['client'] and t.receipt['stop_finished_at'] <= t.receipt['finished_at']


@pytest.mark.parametrize('fault', [None, 'query_interrupt', 'after_read_drift'])
def test_precision_is_one_source_bound_read_and_retains_interrupted_authority(tmp_path, monkeypatch, fault):
    from contextlib import contextmanager
    batch, paths, values, _, _ = fixture(tmp_path, monkeypatch)
    t = Trial(batch / 'precision_producer', values['ready'])
    original = deepcopy(values['ready']['all_offline_snapshot'])
    current = deepcopy(original)
    row = deepcopy(values['before_precision']['row'])
    row.pop('exact_rest_bonus_float32_bits')
    statements = []
    class Cursor:
        description = [(key,) for key in row]
        def execute(self, query):
            statements.append(query)
            assert t.writes[-1]['before'] == original
            assert t.writes[-1]['query'] == m.PRECISION_QUERY
            if fault == 'query_interrupt': raise KeyboardInterrupt('lost precise read')
        def fetchall(self):
            if fault == 'after_read_drift': current['6']['pets'][0]['curhealth'] = 277
            return [tuple(row.values())]
        def __enter__(self): return self
        def __exit__(self, *_): return False
    class Connection:
        def cursor(self): return Cursor()
    @contextmanager
    def connection(): yield Connection()
    monkeypatch.setattr(m.lab, 'connection', connection)
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(current))
    monkeypatch.setattr(m, 'runtime', lambda: t.receipt['runtime'])
    monkeypatch.setattr(m.sources(), 'rest_sources', lambda: values['before_precision']['rest_sources'])
    if fault == 'query_interrupt':
        with pytest.raises(KeyboardInterrupt): m.execute_trial(t, lambda: m.precision(t, paths['ready']))
    else: m.execute_trial(t, lambda: m.precision(t, paths['ready']))
    assert statements == [m.PRECISION_QUERY] and t.receipt['input_sent'] is False and t.receipt['mutation_sent'] is False
    if fault:
        assert t.receipt['completed'] is False and t.receipt['failure']
        assert t.receipt['before'] == original and t.receipt['source'] == m.sources().bound(paths['ready'])
    else:
        assert t.receipt['phase'] == 'item_actionbar_rest_precision_complete'
        assert t.receipt['row'] == values['before_precision']['row'] and t.receipt['before'] == t.receipt['after']


@pytest.mark.parametrize('fault', [None, 'armed_probe', 'wrong_failure'])
def test_failed_housekeeping_pause_keeps_first_failure_without_drag_or_clear_replay(tmp_path, monkeypatch, fault):
    batch, paths, values, _, _ = fixture(tmp_path, monkeypatch)
    t = Trial(batch / 'excluded_pause', values['ready'], start=1125)
    failed_path = batch / 'first_failed' / 'episode.json'
    failed_path.parent.mkdir()
    failure = {'completed': False, 'failure': 'RuntimeError: original drag postcondition', 'started_at': 1104,
        'finished_at': 1105, 'actor': deepcopy(t.fixture), 'runtime': deepcopy(t.receipt['runtime']),
        'preparation_source': m.sources().bound(paths['ready'])}
    if fault == 'wrong_failure': failure['actor']['guid'] = 6
    failed_path.write_text(json.dumps(failure))
    parked = deepcopy(values['park'])
    parked.update(recovery_only=True, failed_whole_excluded=True, gameplay_input_replayed=False,
        first_failure_source=m.sources().bound(failed_path))
    paths['park'].write_text(json.dumps(parked))
    precision = deepcopy(values['after_precision'])
    precision['source'] = m.sources().bound(paths['park'])
    paths['after_precision'].write_text(json.dumps(precision))
    snap = parked['all_offline_snapshot']
    stopped = []
    monkeypatch.setattr(m, 'registration', lambda: t.fixture)
    monkeypatch.setattr(m, 'runtime', lambda: t.receipt['runtime'])
    monkeypatch.setattr(m, 'snapshot', lambda: deepcopy(snap))
    monkeypatch.setattr(m.sources(), 'rest_sources', lambda: values['before_precision']['rest_sources'])
    monkeypatch.setattr(m, 'review', lambda *_: ({'source': m.sources().bound(paths['park']),
        'selected_character': 'Harnesstwo', 'selected_level': 1}, parked))
    monkeypatch.setattr(m, 'primary_stopped', lambda _: {'after': snap['1']})
    monkeypatch.setattr(m, 'focus', lambda: parked['frame']['monitor'])
    monkeypatch.setattr(m.lab, 'proc_start', lambda _: '2100')
    monkeypatch.setattr(m.lab, 'stop', lambda kind: stopped.append(kind))
    monkeypatch.setattr(m.lab, 'owned_process', lambda _: None)
    monkeypatch.setattr(m, 'gone', lambda *_: True)
    monkeypatch.setattr(m, 'identity', lambda k: t.receipt['runtime'][k])
    monkeypatch.setattr(m, 'shot', lambda _: parked['frame'])
    if fault == 'armed_probe':
        probe = m.lab.ROOT / 'run/owned_entry_request_probe.json'
        probe.parent.mkdir()
        probe.write_text('{}')
    m.execute_trial(t, lambda: m.pause_recovery(t, paths['ready'], paths['park'],
        paths['before_precision'], paths['after_precision'], tmp_path / 'review.json'))
    if fault:
        assert not stopped and not t.clicks and t.receipt['completed'] is False and t.receipt['failure']
    else:
        assert stopped == ['client'] and not t.clicks
        assert t.receipt['phase'] == 'item_actionbar_recovery_closed_paused'
        assert t.receipt['recovery_only'] is t.receipt['failed_whole_excluded'] is True
        assert t.receipt['first_failure_source'] == m.sources().bound(failed_path)
        assert t.receipt['gameplay_input_replayed'] is False and t.receipt['input_sent'] is False
        assert t.receipt['before'] == t.receipt['after'] == snap

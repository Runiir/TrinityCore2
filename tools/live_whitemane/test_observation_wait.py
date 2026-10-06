from types import SimpleNamespace
import pytest
from . import observation_wait as waiting,runtime


def test_transient_tile_loss_recovers_without_renewing_inactivity(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime,'owned_process',lambda:{'pid':1})
    session={'last_progress_at':10}
    attempts=iter([RuntimeError('local public tiles unavailable: stale local M tile'),
        RuntimeError('local public tiles unavailable: local tiles did not produce fresh M, A and UI generations'),
        {'fresh':True}])
    def observe(_):
        value=next(attempts)
        if isinstance(value,Exception):raise value
        return value
    monkeypatch.setattr(waiting,'observe',observe)
    monkeypatch.setattr(waiting,'time',SimpleNamespace(time=lambda:20,sleep=lambda _:None))
    records=[];monkeypatch.setattr(runtime,'write',lambda path,data:records.append(data))
    assert waiting.sample(tmp_path/'before.png',session)=={'fresh':True}
    assert session['last_progress_at']==10
    assert [r['status'] for r in records]==['waiting','waiting','recovered']
    assert all(r['inputs_sent']==0 for r in records)


def test_missing_frames_still_reach_the_original_inactivity_limit(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime,'owned_process',lambda:{'pid':1})
    clock=iter([1799,1799,1799,1800])
    monkeypatch.setattr(waiting,'time',SimpleNamespace(time=lambda:next(clock),sleep=lambda _:None))
    def observe(_):raise RuntimeError('local public tiles unavailable: stale local M tile')
    monkeypatch.setattr(waiting,'observe',observe)
    monkeypatch.setattr(runtime,'write',lambda *_:None)
    with pytest.raises(waiting.InactiveObservation):waiting.sample(tmp_path/'before.png',{'last_progress_at':0})


def test_other_errors_are_not_hidden_by_an_observation_wait(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(runtime,'owned_process',lambda:{'pid':1})
    monkeypatch.setattr(waiting,'time',SimpleNamespace(time=lambda:20,sleep=lambda _:None))
    def observe(_):raise RuntimeError('owned local telemetry window changed or is obscured')
    monkeypatch.setattr(waiting,'observe',observe)
    with pytest.raises(RuntimeError,match='window changed'):
        waiting.sample(tmp_path/'before.png',{'last_progress_at':10})

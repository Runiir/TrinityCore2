"""A delayed panel close must never turn into repeated Escape input."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_trial as module


def trial(states,monkeypatch):
    t=module.Trial.__new__(module.Trial);events=[]
    t.receipt={'cleanup':[]};t.persist=lambda:None
    t.io=SimpleNamespace(key=events.append)
    samples=iter(states);t.observe=lambda label:(next(samples),{'file':label+'.png'})
    monkeypatch.setattr(module.time,'sleep',lambda seconds:None)
    return t,events


def state(sequence,visible):
    return {'sequence':sequence,'panels':['FriendsFrame'] if visible else [],'bags':[],
        'chat_edit_open':False,'spell_targeting':False}


def test_delayed_cleanup_waits_for_change_and_confirms_empty_without_second_escape(monkeypatch):
    t,events=trial([state(1,True),state(2,True),state(3,False),state(4,False)],monkeypatch)
    t.clean_panels()
    assert events==['Escape']
    assert len(t.receipt['cleanup'][0]['settling'])==2


def test_cleanup_timeout_refuses_to_replay_escape(monkeypatch):
    t,events=trial([state(1,True),state(2,True)],monkeypatch)
    ticks=iter([0,13]);monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    with pytest.raises(RuntimeError,match='refusing to replay Escape'):t.clean_panels()
    assert events==['Escape']

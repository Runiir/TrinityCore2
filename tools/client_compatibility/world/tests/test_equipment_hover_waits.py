"""A pending hover-only control must not trigger a missing or ambiguous click."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_equipment_set_roundtrip as module


def fixture(monkeypatch,rows):
    samples=iter(rows);inputs=[]
    monkeypatch.setattr(module,'controls',lambda _:next(samples))
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    t=SimpleNamespace(receipt={},persist=lambda:None,execute=inputs.append,
        observe=lambda label:({'sequence':1},{'file':label+'.png'}))
    return t,inputs


def button():
    return {'equipment_set_button':'edit','equipment_set_id':0,'x':32000,'y':19000}


def test_pending_button_waits_without_replaying_row_hover(monkeypatch):
    t,inputs=fixture(monkeypatch,[[],[],[button()]])
    module.hover_button(t,'edit',0,'edit_hover')
    assert inputs==[{'kind':'hover','value':module.point(button())}]
    assert len(t.receipt['button_visibility_waits']['edit_hover'])==2
    assert all(not r['input_replayed'] for r in t.receipt['button_visibility_waits']['edit_hover'])


def test_ambiguous_owned_buttons_send_no_input(monkeypatch):
    t,inputs=fixture(monkeypatch,[[button(),button()]])
    with pytest.raises(RuntimeError,match='one visible owned'):module.hover_button(t,'edit',0,'edit_hover')
    assert not inputs


def test_missing_button_timeout_sends_no_input(monkeypatch):
    t,inputs=fixture(monkeypatch,[[]]);ticks=iter([0,13])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    with pytest.raises(RuntimeError,match='one visible owned'):module.hover_button(t,'edit',0,'edit_hover')
    assert not inputs

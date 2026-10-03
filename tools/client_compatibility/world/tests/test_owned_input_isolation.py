"""Prevent cross-actor/PID-reuse input and reject a host-display fallback."""
import pytest
from tools.client_compatibility import owned_input,lab_runtime as lab
from tools.second_client import place_window


def test_adapter_rejects_actor_switch_and_restarted_client_before_input(monkeypatch):
    adapter=owned_input.Inputs.__new__(owned_input.Inputs)
    adapter.actor='primary';adapter.runtime={'pid':123,'start_ticks':'456'}
    monkeypatch.setattr(lab,'actor_name',lambda:'primary')
    monkeypatch.setattr(lab,'owned_process',lambda kind:{'pid':123,'start_ticks':'456'})
    adapter.validate()
    monkeypatch.setattr(lab,'actor_name',lambda:'scout')
    with pytest.raises(RuntimeError,match='different actor'):adapter.validate()
    monkeypatch.setattr(lab,'actor_name',lambda:'primary')
    monkeypatch.setattr(lab,'owned_process',lambda kind:{'pid':123,'start_ticks':'789'})
    with pytest.raises(RuntimeError,match='client lifetime'):adapter.validate()


def test_private_focus_rejects_host_display_without_opening_it(monkeypatch):
    from Xlib import display
    monkeypatch.setenv('DISPLAY',':0')
    monkeypatch.setattr(lab,'owned_process',lambda kind:{'pid':123,'start_ticks':'456'})
    monkeypatch.setattr(lab,'client_environment',lambda:{'DISPLAY':':0.0'})
    calls=[]
    def placement(pid,**kwargs):
        calls.append(kwargs);return {'monitor':{'name':'HDMI-1'}}
    monkeypatch.setattr(place_window,'place',placement)
    monkeypatch.setattr(display,'Display',lambda *a,**kw:pytest.fail('host display opened for input'))
    with pytest.raises(RuntimeError,match='refusing the host desktop'):owned_input._focus()
    assert calls==[{'timeout':1,'reposition':False}]

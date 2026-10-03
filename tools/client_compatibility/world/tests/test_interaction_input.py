"""Pending chat recovery may submit only the exact selected command, once."""
from contextlib import nullcontext
import pytest
from tools.client_compatibility import interaction_trial as module


@pytest.mark.parametrize('text,settled',[('/invite Harnesstwo',True),('/invite Harnesstwo ',True),('/invite Harnesstwo',False),('/quit',False)])
def test_chat_recovery_does_not_submit_changed_text(monkeypatch,text,settled):
    trial=module.Trial.__new__(module.Trial);trial.receipt={'cases':[]};events=[]
    class Inputs:
        def key(self,value,**kwargs):events.append(('key',value))
        def type(self,value):events.append(('type',value))
    trial.io=Inputs()
    states=iter([{'chat_edit_open':True,'chat_edit_text':text},{'chat_edit_open':not settled}])
    trial.observe=lambda label:(next(states),{'file':label})
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    # These cases exercise the name-completion fallback after the normal
    # submission wait expires. Delayed partial observations have a separate test.
    ticks=iter([0,13]);monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    action={'kind':'chat','value':'/invite Harnesstwo'}
    if text=='/quit':
        with pytest.raises(RuntimeError,match='refusing to submit'):trial.execute(action)
        assert events.count(('key','Return'))==2
    elif not settled:
        with pytest.raises(RuntimeError,match='retry did not settle'):trial.execute(action)
        assert events.count(('key','Return'))==3
    else:
        receipt=trial.execute(action);assert len(receipt)==1
        assert events.count(('key','Return'))==3
    assert events.count(('type','/invite Harnesstwo'))==1


@pytest.mark.parametrize('hold',[.01,2.01,float('nan')])
def test_mouse_hold_outside_bound_never_reaches_input(monkeypatch,hold):
    trial=module.Trial.__new__(module.Trial);events=[]
    from types import SimpleNamespace
    trial.io=SimpleNamespace(click=lambda *args,**kwargs:events.append((args,kwargs)))
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    with pytest.raises(ValueError,match='click hold'):
        trial.execute({'kind':'click','value':[10,20],'hold':hold})
    assert events==[]


def test_bounded_stock_rotation_hold_reaches_only_selected_control(monkeypatch):
    trial=module.Trial.__new__(module.Trial);events=[]
    from types import SimpleNamespace
    trial.io=SimpleNamespace(click=lambda *args,**kwargs:events.append((args,kwargs)))
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    assert trial.execute({'kind':'click','value':[10,20],'hold':.6})==[]
    assert events==[((10,20),{'button':1,'modifiers':(),'hold':.6})]

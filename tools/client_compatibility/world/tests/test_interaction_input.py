"""Pending chat recovery may submit only the exact selected command, once."""
from contextlib import nullcontext
import pytest
from tools.client_compatibility import interaction_trial as module


@pytest.mark.parametrize('text,settled',[('/invite Harnesstwo',True),('/invite Harnesstwo',False),('/quit',False)])
def test_chat_recovery_does_not_submit_changed_text(monkeypatch,text,settled):
    trial=module.Trial.__new__(module.Trial);trial.receipt={'cases':[]};events=[]
    class Inputs:
        def key(self,value,**kwargs):events.append(('key',value))
        def type(self,value):events.append(('type',value))
    trial.io=Inputs()
    states=iter([{'chat_edit_open':True,'chat_edit_text':text},{'chat_edit_open':not settled}])
    trial.observe=lambda label:(next(states),{'file':label})
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
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

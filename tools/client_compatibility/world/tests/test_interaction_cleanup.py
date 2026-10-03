"""A delayed panel close must never turn into repeated Escape input."""
from types import SimpleNamespace
from contextlib import nullcontext
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


def test_pending_glyph_cancel_is_progress_even_when_the_panel_stays_open(monkeypatch):
    pending=state(1,True);pending['pending_glyph']=483
    t,events=trial([pending,state(2,True),state(3,False),state(4,False)],monkeypatch)
    t.clean_panels()
    assert events==['Escape','Escape']


def test_delayed_partial_chat_observation_does_not_resubmit_or_fail(monkeypatch):
    partial={'chat_edit_open':True,'chat_edit_text':'/cleartar'}
    t,_=trial([partial,{'chat_edit_open':False}],monkeypatch)
    t.receipt['cases']=[];events=[]
    t.io=SimpleNamespace(key=lambda key,**kwargs:events.append(('key',key)),
        type=lambda text:events.append(('text',text)))
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    transport=t.execute({'kind':'chat','value':'/cleartarget'})
    assert events==[('key','Return'),('text','/cleartarget'),('key','Return')]
    assert transport[0]['input_replayed'] is False


@pytest.mark.parametrize('opens',[True,False])
def test_panel_open_wait_uses_one_input_and_keeps_timeout_failed(monkeypatch,opens):
    states=[state(1,False),state(2,False)]
    if opens:states += [state(3,False),state(4,True)]
    t,_=trial(states,monkeypatch);t.receipt['cases']=[];t.controller='code'
    inputs=[];t.execute=lambda action:inputs.append(action) or []
    ticks=iter([0,1,2] if opens else [0,13])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    result=t.step('panel.open','Open friends.',{'open':{'kind':'key','value':'o'}},
        lambda b,a,s:{'status':'panel_open_pass' if 'FriendsFrame' in a['panels'] else 'client_or_protocol_failure'},
        diagnostic_action='open',await_state=lambda s:'FriendsFrame' in s['panels'])
    assert inputs==[{'kind':'key','value':'o'}]
    assert result['input_replayed_while_settling'] is False
    assert result['status']==('panel_open_pass' if opens else 'client_or_protocol_failure')

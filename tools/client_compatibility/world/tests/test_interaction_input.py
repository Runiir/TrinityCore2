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
    trial.persist=lambda:None
    states=iter([{'chat_edit_open':True,'chat_edit_text':text},{'chat_edit_open':not settled}])
    def observe(label,seconds=28):
        if label.endswith('_chat_open'):state={'chat_edit_open':True,'chat_edit_text':''}
        elif '_chat_pre_submit' in label:state={'chat_edit_open':True,'chat_edit_text':'/invite Harnesstwo'}
        else:state=next(states)
        return state,{'file':label}
    trial.observe=observe
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    # These cases exercise the name-completion fallback after the normal
    # submission wait expires. Delayed partial observations have a separate test.
    ticks=iter([0,0,0,13]);monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
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


@pytest.mark.parametrize('text',['invite Harnesstwo','/quit',''])
def test_changed_command_is_never_submitted_in_the_first_place(monkeypatch,text):
    trial=module.Trial.__new__(module.Trial);trial.receipt={'cases':[]};trial.persist=lambda:None
    events=[]
    from types import SimpleNamespace
    trial.io=SimpleNamespace(key=lambda value,**kw:events.append(('key',value)),
        type=lambda value:events.append(('type',value)))
    states=iter([{'chat_edit_open':True,'chat_edit_text':''},{'chat_edit_open':True,'chat_edit_text':text}])
    trial.observe=lambda label,seconds=28:(next(states),{'file':label})
    ticks=iter([0,0,13]);monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    with pytest.raises(RuntimeError,match='refusing submission'):
        trial.execute({'kind':'chat','value':'/invite Harnesstwo'})
    assert events==[('key','Return'),('type','/invite Harnesstwo')]
    assert not any(r['submitted'] for r in trial.receipt['chat_submission_checks'])


def test_delayed_edit_and_partial_text_wait_without_replaying_input(monkeypatch):
    trial=module.Trial.__new__(module.Trial);trial.receipt={'cases':[]};trial.persist=lambda:None
    events=[]
    from types import SimpleNamespace
    trial.io=SimpleNamespace(key=lambda value,**kw:events.append(('key',value)),
        type=lambda value:events.append(('type',value)))
    states=iter([{'chat_edit_open':False},{'chat_edit_open':True,'chat_edit_text':''},
        {'chat_edit_open':True,'chat_edit_text':'/invite'},
        {'chat_edit_open':True,'chat_edit_text':'/invite Harnesstwo'},{'chat_edit_open':False}])
    trial.observe=lambda label,seconds=28:(next(states),{'file':label})
    ticks=iter(range(10));monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    assert trial.execute({'kind':'chat','value':'/invite Harnesstwo'})==[]
    assert events==[('key','Return'),('type','/invite Harnesstwo'),('key','Return')]
    assert [r['open'] for r in trial.receipt['chat_open_checks']]==[False,True]
    assert [r['submitted'] for r in trial.receipt['chat_submission_checks']]==[False,True]


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


@pytest.mark.parametrize('mode',['state','chat','controls'])
@pytest.mark.parametrize('text',['/tcui chat','cui chat'])
def test_diagnostic_observes_complete_prefix_before_submission_from_any_mode(monkeypatch,mode,text):
    trial=module.Trial.__new__(module.Trial);trial.receipt={'cases':[]};trial.persist=lambda:None
    events=[]
    from types import SimpleNamespace
    trial.io=SimpleNamespace(key=lambda value,**kw:events.append(('key',value)),
        type=lambda value:events.append(('type',value)))
    states=iter([{'chat_edit_open':False}, {'chat_edit_open':True,'chat_edit_focused':True},
        {'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_text':text},
        {'chat_edit_open':False}])
    def observe(label,**kwargs):
        assert kwargs=={'mode':None}
        return {'mode':mode,**next(states)},{'file':label}
    trial.observe=observe
    ticks=iter([0,0,13]);monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    if text=='/tcui chat':
        trial.submit_chat('/tcui chat',any_mode=True)
        assert events.count(('key','Return'))==2
        assert trial.receipt['chat_submission_checks'][-1]['submitted']
    else:
        with pytest.raises(RuntimeError,match='refusing submission'):
            trial.submit_chat('/tcui chat',any_mode=True)
        assert events.count(('key','Return'))==1
        assert not trial.receipt['chat_submission_checks'][-1]['submitted']


@pytest.mark.parametrize('expired,text',[(False,'/tcui state'),(True,'/tcui state'),(True,'/quit')])
def test_diagnostic_waits_for_close_and_retries_only_exact_pending_text(monkeypatch,expired,text):
    trial=module.Trial.__new__(module.Trial);trial.receipt={'cases':[]};trial.persist=lambda:None
    events=[]
    from types import SimpleNamespace
    trial.io=SimpleNamespace(key=lambda value,**kw:events.append(('key',value)),
        type=lambda value:events.append(('type',value)))
    states=iter([{'chat_edit_open':False},{'chat_edit_open':True,'chat_edit_focused':True},
        {'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_text':'/tcui state'},
        {'chat_edit_open':True,'chat_edit_focused':True,'chat_edit_text':text},
        {'chat_edit_open':False}])
    trial.observe=lambda label,**kw:(next(states),{'file':label})
    ticks=iter([0,0,0,13 if expired else 0,13])
    monkeypatch.setattr(module.time,'monotonic',lambda:next(ticks))
    monkeypatch.setattr(module.time,'sleep',lambda _:None)
    monkeypatch.setattr(module.owned_input,'lease',nullcontext)
    if text=='/quit':
        with pytest.raises(RuntimeError,match='refusing to submit'):
            trial.submit_chat('/tcui state',any_mode=True)
        assert events.count(('key','Return'))==2
    else:
        trial.submit_chat('/tcui state',any_mode=True)
        assert events.count(('key','Return'))==(3 if expired else 2)
    assert events.count(('type','/tcui state'))==1

from types import SimpleNamespace
from contextlib import contextmanager
import pytest
from tools.client_compatibility.interaction_chat_player_actions import report_identity,expected_names
from tools.client_compatibility import interaction_private_clipboard as clipboard
from tools.client_compatibility import interaction_chat_player_actions as actions


@pytest.mark.parametrize('change',[None,'name','guid','missing_close','two_close','ready_submit','missing_submit'])
def test_report_cancel_requires_one_owned_close_and_a_disabled_submit(change):
    close={'report_action':'close','report_player_name':'Harnesstwo-Client442Lab',
        'report_player_guid':'Player-1-00000002'}
    submit={'report_action':'submit','enabled':False};rows=[close,submit]
    if change=='name':close['report_player_name']='Someoneelse'
    if change=='guid':close['report_player_guid']='Player-1-00000003'
    if change=='missing_close':rows=[submit]
    if change=='two_close':rows.append(dict(close))
    if change=='ready_submit':submit['enabled']=True
    if change=='missing_submit':rows=[close]
    assert all(report_identity(rows,{'Harnesstwo','Harnesstwo-Client442Lab'}).values())==(change is None)


@pytest.mark.parametrize('sender,guid',[('Someoneelse',2),('Harnesstwo-Client442Lab',3)])
def test_player_action_rejects_a_foreign_seed(sender,guid):
    with pytest.raises(RuntimeError):expected_names({'observed_sender':sender,'expected_native_guid':guid})


@pytest.mark.parametrize('actor,nested',[('scout',':2'),('primary',':3')])
def test_clipboard_mismatch_never_opens_or_reads_a_selection(monkeypatch,actor,nested):
    monkeypatch.setattr(clipboard.owned_input,'focus',lambda:{'input_isolation':{'actor':actor,'display':nested}})
    def forbidden(*args):raise AssertionError('foreign display must not be opened')
    monkeypatch.setattr(clipboard.display,'Display',forbidden)
    t=SimpleNamespace(fixture={'actor':'primary'},io=SimpleNamespace(initialization={'display':':2'}))
    with pytest.raises(RuntimeError,match='clipboard display differs'):clipboard.copied_name(t,{'Harnesstwo'})


@pytest.mark.parametrize('replaced,exact,after,passes',[
    (True,True,['ContextMenu'],True),(True,True,[],True),
    (False,True,['ContextMenu'],False),(True,False,['ContextMenu'],False),
    (True,True,['ReportFrame'],False)])
def test_copy_must_replace_its_guard_but_stock_menu_may_remain_open(monkeypatch,replaced,exact,after,passes):
    @contextmanager
    def fixture(t):yield {'owner_window':123,'marker':'TC442UI:copy_guard_12345678'}
    def copied(t,expected,previous=None):
        if previous is None:return {'exact_owned_name':True,'owner_window':123}
        assert previous==123
        return {'exact_owned_name':exact,'owned_guard_replaced':replaced}
    monkeypatch.setattr(actions,'marker',fixture);monkeypatch.setattr(actions,'copied_name',copied)
    results=[]
    def clicked(t,label,text,oracle):
        result={'id':label,**oracle({'panels':['ContextMenu']},{'panels':after},True)}
        results.append(result);return result
    monkeypatch.setattr(actions,'menu_click',clicked)
    t=SimpleNamespace(receipt={},persist=lambda:None)
    seed={'observed_sender':'Harnesstwo-Client442Lab','expected_native_guid':2}
    if passes:
        actions.copy(t,seed);assert results[0]['status']=='owned_player_name_copy_pass'
    else:
        with pytest.raises(RuntimeError):actions.copy(t,seed)
        assert results[0]['status']=='client_or_protocol_failure'

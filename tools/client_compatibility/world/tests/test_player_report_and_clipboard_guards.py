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


def test_delayed_report_open_and_close_wait_without_repeating_input(monkeypatch):
    rows=[{'name':'ReportClose','report_action':'close','report_player_name':'Harnesstwo',
        'report_player_guid':'Player-1-00000002','kind':'Button','enabled':True,'x':100,'y':200},
        {'report_action':'submit','enabled':False}]
    menu={'text':'Report Player','kind':'MenuItem','enabled':True,'x':100,'y':300}
    monkeypatch.setattr(actions,'target',lambda t,label,predicate:menu if label.startswith('fixture.') else rows[0])
    monkeypatch.setattr(actions,'controls',lambda t:rows)
    monkeypatch.setattr(actions,'owned_report_context',lambda t,seed:True)
    monkeypatch.setattr(actions.time,'sleep',lambda seconds:None)
    sent=[]
    def step(label,goal,choices,oracle,diagnostic_action=None,await_state=None):
        sent.append(label)
        opening=label=='fixture.open_owned_player_report'
        before={'panels':['ContextMenu'] if opening else ['ReportFrame']}
        early={'panels':before['panels']}
        settled={'panels':['ReportFrame'] if opening else []}
        assert await_state is not None and not await_state(early) and await_state(settled)
        return oracle(before,settled,diagnostic_action)
    t=SimpleNamespace(receipt={},persist=lambda:None,step=step,
        io=SimpleNamespace(move=lambda *args:None),observe=lambda label:({'panels':['ReportFrame']},{'file':'report.png'}))
    actions.report(t,{'observed_sender':'Harnesstwo-Client442Lab','expected_native_guid':2})
    assert sent==['fixture.open_owned_player_report','chat.report_ui_cancel']
    assert t.receipt['owned_report_ui']['submitted'] is False


@pytest.mark.parametrize('guid,context,valid',[(None,False,False),(None,True,True),
    ('Player-1-00000002',True,True),('Player-1-00000003',True,False),('',True,False)])
def test_missing_form_guid_requires_attributed_context_and_never_accepts_foreign_guid(guid,context,valid):
    assert actions.report_guid_matches({'report_player_guid':guid},context)==valid


@pytest.mark.parametrize('change',[None,'foreign_link','wrong_frame','wrong_token','failed_native','missing_native','duplicate_event'])
def test_report_chat_context_requires_exact_native_seed_hover_and_public_event(change):
    seed={'expected_native_guid':2,'observed_sender':'Harnesstwo-Client442Lab','token':'TC442UI:reply_seed_12345678','checks':{'native':True}}
    link={'frame':'ChatFrame1','data':'player:Harnesstwo-Client442Lab:440:WHISPER'}
    event={'event':'CHAT_MSG_WHISPER','text':seed['token'],'sender':seed['observed_sender']};events=[event]
    if change=='foreign_link':link['data']='player:Someoneelse:440:WHISPER'
    if change=='wrong_frame':link['frame']='ChatFrame2'
    if change=='wrong_token':event['text']='TC442UI:reply_seed_87654321'
    if change=='failed_native':seed['checks']['native']=False
    if change=='missing_native':seed['checks']={}
    if change=='duplicate_event':events.append(dict(event))
    t=SimpleNamespace(receipt={'player_link_pointer_settled':{'pointer':{'chat_link':link}},'player_menu':{'state':{'chat_probes':events}}})
    assert actions.owned_report_context(t,seed)==(change is None)

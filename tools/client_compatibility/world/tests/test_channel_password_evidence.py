"""Gate evidence needs matching native and modern notices for the owned actor."""
import pytest
from types import SimpleNamespace
from tools.client_compatibility import interaction_channel_password as gate
from tools.client_compatibility.interaction_channel_password import notice,password_prompt
from tools.client_compatibility.world.buffer import Writer,player_high


@pytest.mark.parametrize('kind,guid',[(4,0),(7,1)])
def test_password_notice_requires_both_wire_directions_and_exact_actor(kind,guid):
    name='TC442UIChannel1234abcd'
    native=Writer().pack('B',kind).raw(name.encode()+b'\0')
    if kind==7:native.pack('Q',guid)
    modern=Writer().bits(kind,6).bits(len(name),7).bits(0,6).guid(guid,player_high() if guid else 0)
    modern.guid().pack('I',0x01010001).guid().pack('II',0x01010001,0).raw(name.encode())
    rows=[{'direction':d,'name':'SMSG_CHANNEL_NOTIFY','body':body.finish().hex()}
        for d,body in [('from_native',native),('to_client',modern)]]
    assert notice(rows,name,kind,guid)['matches']
    assert not notice(rows[:1],name,kind,guid)['matches']
    assert not notice(rows,'TC442UIChannel99999999',kind,guid)['matches']
    if kind==7:assert not notice(rows,name,kind,2)['matches']


def test_rejection_cancels_owned_modal_before_any_chat_diagnostic(monkeypatch):
    name='TC442UIChannel1234abcd'
    cancel={'name':'StaticPopup1Button2','text':'Cancel',
        'context':"Please enter a password for '"+name+"'."}
    state={'panels':['StaticPopup1'],'controls':[cancel],
        'edit_fields':[{'name':'StaticPopup1EditBox','focused':True,'text':''}]}
    assert password_prompt(state,name)
    assert not password_prompt(state,'TC442UIChannel99999999')
    assert not password_prompt({**state,'edit_fields':[{'name':'StaticPopup1EditBox',
        'focused':True,'text':'/tcui chat'}]},name)
    modal=False;calls=[]
    def detail(t,label):
        assert not modal, 'a slash diagnostic would enter the password field'
        calls.append(label);return {'channels':{'rows':[]}}
    def step(case,goal,actions,oracle,**kwargs):
        nonlocal modal
        modal=True;assert kwargs['await_state'](state)
        return oracle({},state,'join')
    def click(t,label,goal,predicate,oracle,**kwargs):
        nonlocal modal
        assert modal and predicate(cancel)
        assert calls==['password_join_before']
        modal=False;after={'panels':[]};assert kwargs['await_state'](after)
        return oracle(state,after,True)
    monkeypatch.setattr(gate,'detail',detail)
    monkeypatch.setattr(gate,'click',click)
    monkeypatch.setattr(gate.actors,'session_entry',lambda f:{'session':'owned'})
    monkeypatch.setattr(gate,'Cursor',lambda p:SimpleNamespace(poll=lambda:iter(())))
    monkeypatch.setattr(gate,'packets',lambda *a:[{'direction':d,'name':n} for d,n in
        [('from_client','CMSG_CHAT_JOIN_CHANNEL'),('to_native','CMSG_JOIN_CHANNEL')]])
    monkeypatch.setattr(gate,'notice',lambda *a:{'matches':True,'decoded':[]})
    t=SimpleNamespace(fixture={'guid':2},receipt={},step=step,
        observe=lambda label:(state,{'file':'owned_modal.png'}),persist=lambda:None)
    gate.join(t,name,'',True)
    assert calls==['password_join_before','password_rejection_membership'] and not modal

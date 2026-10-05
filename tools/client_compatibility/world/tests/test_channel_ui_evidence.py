"""A stock panel may fetch its selected roster before the explicit row click."""
from types import SimpleNamespace
from tools.client_compatibility import interaction_channel_ui as ui


def test_opening_panel_roster_is_retained_when_selected_row_sends_nothing(monkeypatch):
    name='TC442UIChannel1234abcd';pending=[];opened=False
    class Cursor:
        def __init__(self,path):pass
        def poll(self):
            rows=pending.copy();pending.clear();return iter(rows)
    def detail(t,label):
        return {'channel_list':{'received_sequence':1 if opened else 0,'roster':{
            'channels':[{'name':name,'members':[{'name':'Harnessone','is_player':True}]}] if opened else []}}}
    def click(t,label,goal,predicate,oracle,**kwargs):
        nonlocal opened
        if label=='fixture.open_channels_ui':
            opened=True
            for direction,opcode in [('from_client','CMSG_CHAT_CHANNEL_DISPLAY_LIST'),
                ('from_native','SMSG_CHANNEL_LIST'),('to_client','SMSG_CHANNEL_LIST')]:
                pending.append({'session':'owned','time':11,'name':opcode,'direction':direction,
                    'body':name.encode().hex()})
        else:
            assert predicate({'kind':'Button','text':'5. '+name})
        result=oracle({}, {'panels':['ChannelFrame']}, True)
        t.receipt.setdefault('results',[]).append(result);return result
    monkeypatch.setattr(ui,'Cursor',Cursor)
    monkeypatch.setattr(ui,'detail',detail)
    monkeypatch.setattr(ui,'controls',lambda t:[])
    monkeypatch.setattr(ui,'click',click)
    monkeypatch.setattr(ui.time,'time',lambda:10)
    monkeypatch.setattr(ui.actors,'session_entry',lambda f:{'session':'owned'})
    t=SimpleNamespace(fixture={'character_name':'Harnessone'},receipt={},persist=lambda:None,
        observe=lambda label:({'panels':['ChannelFrame']},{'file':'owned.png'}))
    ui.inspect(t,name,'ChatFrameChannelButton',True)
    row=t.receipt['results'][-1]
    assert row['status']=='owned_stock_channel_roster_pass'
    assert len(row['oracle']['packets'])==3

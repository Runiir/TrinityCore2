"""Fresh cursor rows retain the same native attribution gates as historical reads."""
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_reply_chat as module


@pytest.mark.parametrize('change',[None,'session','old','guid','text','public'])
def test_fresh_delivery_requires_current_owned_native_and_public_message(monkeypatch,change):
    token='TC442UI:reply_seed_12345678'
    state={'chat_probes':[{'event':'CHAT_MSG_WHISPER','text':token,'sender':'Harnesstwo-Client442Lab'}]}
    row={'session':7,'time':101,'direction':'from_native','name':'SMSG_MESSAGECHAT',
        'body':(b'\x00'*5+(2).to_bytes(8,'little')+token.encode()).hex()}
    if change=='session':row['session']=8
    if change=='old':row['time']=99
    if change=='guid':row['body']=(b'\x00'*5+(3).to_bytes(8,'little')+token.encode()).hex()
    if change=='text':row['body']=b'other'.hex()
    if change=='public':state['chat_probes']=[]
    def forbidden(*args):raise AssertionError('fresh delivery must not rescan historical journals')
    monkeypatch.setattr(module,'entries',forbidden)
    t=SimpleNamespace(receipt={},persist=lambda:None,observe=lambda *args,**kwargs:(state,{}))
    if change is None:
        result=module.delivered(t,7,100,token,'CHAT_MSG_WHISPER','received',2,packet_rows=[row])
        assert all(result['checks'].values())
    else:
        with pytest.raises(RuntimeError,match='owned whisper delivery differs'):
            module.delivered(t,7,100,token,'CHAT_MSG_WHISPER','received',2,packet_rows=[row])

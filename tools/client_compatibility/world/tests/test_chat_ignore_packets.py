"""Ignored-whisper feedback matches pinned modern/native layouts and owned capture."""
import json,struct
import pytest
from tools.client_compatibility.world.buffer import Writer,Reader,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,stateful,action


def request(guid=2,reason=0,high=None):
    return Writer().guid(guid,player_high() if high is None else high).pack('B',reason).finish()


def translated(codec,name,body,fn='chat_request'):
    return stateful(codec,{'guid':1,'map':1418},[action(fn,name,body)])[0]


def legacy_feedback(body):
    r=Reader(bytes.fromhex(body));reason=r.unpack('B')[0];present={i:r.bits(1) for i in [5,2,6,4,7,0,1,3]}
    octets=bytearray(8)
    for i in [0,6,5,1,4,3,7,2]:
        if present[i]:octets[i]=r.unpack('B')[0]^1
    r.end();return int.from_bytes(octets,'little'),reason


def notice(guid=1,text=None,kind=25,target=None,gm=False):
    text=text if text is not None else (b'Harnessone' if guid==1 else b'Harnesstwo')
    w=Writer().pack('BiQI',kind,0,guid,0)
    if gm:w.pack('I',len(text)+1).raw(text+b'\0')
    return w.pack('QI',guid if target is None else target,len(text)+1).raw(text+b'\0').pack('B',2).finish()


def captured(codec,name,body):
    return result(codec,op='public_chat_probe',name=name,body=body.hex())


@pytest.mark.parametrize('guid,reason',[(1,0),(2,0),(0x01020304,1),(0xffffffff,255)])
def test_modern_feedback_preserves_local_sender_and_reason_in_native_bit_xor_order(codec,guid,reason):
    answer=translated(codec,'CMSG_CHAT_REPORT_IGNORED',request(guid,reason))
    assert isinstance(answer,list) and answer[0]=='CMSG_CHAT_IGNORED'
    assert legacy_feedback(answer[1])==(guid,reason)
    if guid==2:assert len(request(guid,reason))==6 and bytes.fromhex(answer[1])==b'\0\4\3'


@pytest.mark.parametrize('body',[request(0),request(2**32),request(high=2<<58),
    request(high=player_high()+(1<<42)),request()+b'private',request()[:-1],b''])
def test_invalid_foreign_or_noncanonical_feedback_is_rejected(codec,body):
    answer=translated(codec,'CMSG_CHAT_REPORT_IGNORED',body)
    assert isinstance(answer,dict) and 'error' in answer


@pytest.mark.parametrize('guid',[1,2])
def test_only_default_owned_feedback_is_captured_in_both_directions(codec,guid):
    assert captured(codec,'CMSG_CHAT_REPORT_IGNORED',request(guid))
    name,body=translated(codec,'CMSG_CHAT_REPORT_IGNORED',request(guid))
    assert captured(codec,name,bytes.fromhex(body))
    for other in [request(3),request(guid,1),request(guid)+b'private',request(guid)[:-1]]:
        assert not captured(codec,'CMSG_CHAT_REPORT_IGNORED',other)


@pytest.mark.parametrize('guid,gm',[(1,False),(2,False),(1,True)])
def test_owned_native_and_modern_ignore_notice_are_captured_without_arbitrary_chat(codec,guid,gm):
    name='SMSG_GM_MESSAGECHAT' if gm else 'SMSG_MESSAGECHAT';body=notice(guid,gm=gm)
    assert captured(codec,name,body)
    translated_name,encoded=translated(codec,name,body,fn='chat_response')
    assert translated_name=='SMSG_CHAT' and captured(codec,translated_name,bytes.fromhex(encoded))


@pytest.mark.parametrize('change',[{'guid':3},{'text':b'Harnessone private'},{'text':b'Harnesstwo'},
    {'kind':7},{'target':2},{'target':0}])
def test_foreign_or_unrelated_notice_text_is_never_captured(codec,change):
    body=notice(**change);assert not captured(codec,'SMSG_MESSAGECHAT',body)
    name,encoded=translated(codec,'SMSG_MESSAGECHAT',body,fn='chat_response')
    assert not captured(codec,name,bytes.fromhex(encoded))


def test_trailing_or_truncated_ignored_notices_are_not_captured(codec):
    body=notice()
    for changed in [body+b'private',body[:-1]]:assert not captured(codec,'SMSG_MESSAGECHAT',changed)


def test_journal_capture_retains_only_owned_feedback_and_notice(codec,tmp_path):
    (tmp_path/'evidence').mkdir();(tmp_path/'logs').mkdir()
    for name,body in [('CMSG_CHAT_REPORT_IGNORED',request()),('CMSG_CHAT_REPORT_IGNORED',request(3)),
        ('CMSG_CHAT_IGNORED',b'\0\4\3'),('SMSG_MESSAGECHAT',notice()),
        ('SMSG_MESSAGECHAT',notice(text=b'private text'))]:
        result(codec,op='packet_diagnostic',root=str(tmp_path),name=name,body=body.hex())
    path=tmp_path/'evidence/world_packets.jsonl';rows=[json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []
    assert [(r['name'],bytes.fromhex(r['body'])) for r in rows]==[
        ('CMSG_CHAT_REPORT_IGNORED',request()),('CMSG_CHAT_IGNORED',b'\0\4\3'),('SMSG_MESSAGECHAT',notice())]

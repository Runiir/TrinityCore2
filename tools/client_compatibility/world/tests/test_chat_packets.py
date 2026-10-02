"""Ordinary local chat wire layouts, independent native/modern decoding and privacy."""
import json,struct
import pytest
from tools.client_compatibility.world.buffer import Writer,Reader,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,stateful,action


def call(codec,fn,name,body):return stateful(codec,{'guid':1,'map':0},[action(fn,name,body)])[0]


@pytest.mark.parametrize('suffix,secure',[('SAY',True),('YELL',False),('PARTY',True),('RAID',True),('RAID_WARNING',True),('GUILD',False),('OFFICER',False),('INSTANCE_CHAT',True)])
def test_chat_messages_preserve_language_and_text_in_native_nine_bit_layout(codec,suffix,secure):
    message=b'TC442UI:chat_primary';w=Writer().pack('i',7).bits(len(message),11)
    if secure:w.bits(1,1)
    body=w.raw(message).finish()
    name,encoded=call(codec,'chat_request','CMSG_CHAT_MESSAGE_'+suffix,body)
    assert name=='CMSG_MESSAGECHAT_'+('BATTLEGROUND' if suffix=='INSTANCE_CHAT' else suffix)
    r=Reader(bytes.fromhex(encoded));assert r.unpack('i')==(7,) and r.bits(9)==len(message)
    assert r.raw(len(message))==message;r.end()
    assert 'error' in codec(op='stateful',character={'guid':1,'map':0},actions=[action('chat_request','CMSG_CHAT_MESSAGE_'+suffix,body+b'x')])


@pytest.mark.parametrize('suffix',['AFK','DND','EMOTE'])
def test_language_free_status_and_emote_messages(codec,suffix):
    name,body=call(codec,'chat_request','CMSG_CHAT_MESSAGE_'+suffix,Writer().bits(6,11).raw(b'absent').finish())
    r=Reader(bytes.fromhex(body));assert name=='CMSG_MESSAGECHAT_'+suffix and r.bits(9)==6 and r.raw(6)==b'absent';r.end()


def test_whisper_preserves_target_and_message_and_strips_same_realm_suffix(codec):
    target=b'Harnesstwo-Client442Lab';text=b'TC442UI:whisper_primary'
    body=Writer().pack('i',7).guid(2,player_high()).pack('I',0x01010001).bits(len(target)+1,7).bits(len(text)+1,11).raw(target+b'\0'+text+b'\0').finish()
    name,encoded=call(codec,'chat_request','CMSG_CHAT_MESSAGE_WHISPER',body)
    r=Reader(bytes.fromhex(encoded));assert name=='CMSG_MESSAGECHAT_WHISPER' and r.unpack('i')==(7,)
    assert r.bits(10)==10 and r.bits(9)==len(text) and r.raw(10)==b'Harnesstwo' and r.raw(len(text))==text;r.end()
    bad=Writer().pack('i',7).guid().pack('I',42).bits(2,7).bits(2,11).raw(b'a\0b\0').finish()
    assert 'error' in codec(op='stateful',character={'guid':1},actions=[action('chat_request','CMSG_CHAT_MESSAGE_WHISPER',bad)])


def test_channel_swaps_native_channel_and_text_order(codec):
    body=Writer().pack('i',7).guid().bits(7,9).bits(5,11).bits(0,1).raw(b'TestLabhello').finish()
    name,encoded=call(codec,'chat_request','CMSG_CHAT_MESSAGE_CHANNEL',body)
    r=Reader(bytes.fromhex(encoded));assert name=='CMSG_MESSAGECHAT_CHANNEL' and r.unpack('i')==(7,)
    assert r.bits(10)==7 and r.bits(9)==5 and r.raw(5)==b'hello' and r.raw(7)==b'TestLab';r.end()


def modern_chat(body):
    r=Reader(bytes.fromhex(body));kind,lang=r.unpack('Bi');sender=r.guid();guild=r.guid();account=r.guid();target=r.guid()
    addresses=r.unpack('II');achievement,flags,display,spell=r.unpack('iHfi')
    sizes=[r.bits(n) for n in [11,11,5,7,12]];bits=[r.bits(1) for _ in range(4)]
    strings=[r.raw(n).decode() for n in sizes];r.end()
    return kind,lang,sender,target,addresses,achievement,flags,display,bits,strings


@pytest.mark.parametrize('kind',[0,1,3,7,9,17,48])
def test_native_chat_has_real_sender_target_text_flags_and_achievement(codec,kind):
    w=Writer().pack('BiQI',kind,7,1,0)
    if kind==17:w.raw(b'TestLab\0')
    w.pack('QI',2,8).raw(b'message\0').pack('B',3)
    if kind==48:w.pack('I',123)
    name,body=call(codec,'chat_response','SMSG_MESSAGECHAT',w.finish());assert name=='SMSG_CHAT'
    values=modern_chat(body)
    assert values[:5]==(kind,7,(1,player_high()),(2,player_high()),(0x01010001,0x01010001))
    assert values[5:9]==(123 if kind==48 else 0,3,0,[0,0,0,0])
    assert values[9]==['','','','TestLab' if kind==17 else '','message']


def test_npc_chat_retains_speaker_name_and_boss_display_bits(codec):
    guid=(0xf13<<52)|(123<<32)|99
    body=Writer().pack('BiQI',41,0,guid,0).pack('I',7).raw(b'Speaker\0').pack('QI',1,5).raw(b'Look\0').pack('BfB',0,4.5,1).finish()
    # Speaker is seven letters plus terminator, so an incorrect counted size is rejected.
    assert 'error' in codec(op='stateful',character={'guid':1,'map':0},actions=[action('chat_response','SMSG_MESSAGECHAT',body)])
    body=Writer().pack('BiQI',41,0,guid,0).pack('I',8).raw(b'Speaker\0').pack('QI',1,5).raw(b'Look\0').pack('BfB',0,4.5,1).finish()
    _,body=call(codec,'chat_response','SMSG_MESSAGECHAT',body);values=modern_chat(body)
    assert values[7]==4.5 and values[8]==[1,0,0,0] and values[9]==['Speaker','','','','Look']


def test_chat_diagnostics_capture_only_complete_public_probe_tokens(codec,tmp_path):
    (tmp_path/'evidence').mkdir();(tmp_path/'logs').mkdir()
    for text in [b'ordinary private text',b'TC442UI:public followed by private text',b'TC442UI:public\0private',b'TC442UI:public']:
        result(codec,op='packet_diagnostic',root=str(tmp_path),name='CMSG_CHAT_MESSAGE_SAY',body=text.hex())
    rows=[json.loads(x) for x in (tmp_path/'evidence/world_packets.jsonl').read_text().splitlines()]
    assert len(rows)==1 and bytes.fromhex(rows[0]['body'])==b'TC442UI:public'

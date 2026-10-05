"""Native channel authority and pinned modern layouts decoded independently."""
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,stateful,action


def call(codec,fn,name,body):
    return stateful(codec,{'guid':1,'map':0,'race':1},[action(fn,name,body)])[0]


def test_join_preserves_channel_flags_and_password_without_terminators(codec):
    body=Writer().pack('I',0).bits(1,1).bits(0,1).bits(22,7).bits(6,7).raw(b'TC442UIChannel1234abcdsecret').finish()
    name,encoded=call(codec,'chat_request','CMSG_CHAT_JOIN_CHANNEL',body)
    assert name=='CMSG_JOIN_CHANNEL'
    r=Reader(bytes.fromhex(encoded));assert r.unpack('I')==(0,)
    assert (r.bits(1),r.bits(1),r.bits(8),r.bits(8))==(1,0,22,6)
    assert r.raw(28)==b'TC442UIChannel1234abcdsecret';r.end()
    for bad in [body[:-1],body+b'x',Writer().pack('I',0).bits(0,2).bits(0,7).bits(0,7).finish()]:
        assert 'error' in codec(op='stateful',character={'guid':1},actions=[action('chat_request','CMSG_CHAT_JOIN_CHANNEL',bad)])


@pytest.mark.parametrize('modern,native,has_id',[
    ('CMSG_CHAT_LEAVE_CHANNEL','CMSG_LEAVE_CHANNEL',True),
    ('CMSG_CHAT_CHANNEL_LIST','CMSG_CHAT_CHANNEL_LIST',False),
    ('CMSG_CHAT_CHANNEL_DISPLAY_LIST','CMSG_CHAT_CHANNEL_DISPLAY_LIST',False)])
def test_leave_and_list_keep_exact_name(codec,modern,native,has_id):
    w=Writer()
    if has_id:w.pack('I',7)
    body=w.bits(7,7).raw(b'TestLab').finish()
    name,encoded=call(codec,'chat_request',modern,body);assert name==native
    r=Reader(bytes.fromhex(encoded))
    if has_id:assert r.unpack('I')==(7,)
    assert r.bits(8)==7 and r.raw(7)==b'TestLab';r.end()


def test_owned_channel_owner_query_and_native_notice_capture(codec):
    channel=b'TC442UIChannel1234abcd'
    body=Writer().bits(22,7).raw(channel).finish()
    name,encoded=call(codec,'chat_request','CMSG_CHAT_CHANNEL_OWNER',body)
    assert name=='CMSG_CHAT_CHANNEL_OWNER'
    r=Reader(bytes.fromhex(encoded));assert r.bits(8)==22 and r.raw(22)==channel;r.end()
    for request in [body,bytes.fromhex(encoded)]:
        assert codec(op='public_channel_probe',name=name,body=request.hex())['result'] is True
    native=b'\x0b'+channel+b'\0Harnessone\0'
    name,encoded=call(codec,'chat_response','SMSG_CHANNEL_NOTIFY',native)
    for packet in [native,bytes.fromhex(encoded)]:
        assert codec(op='public_channel_probe',name=name,body=packet.hex())['result'] is True
        assert codec(op='public_channel_probe',name=name,body=(packet+b'x').hex())['result'] is False
    foreign=b'\x0b'+channel+b'\0Foreignname\0'
    assert codec(op='public_channel_probe',name=name,body=foreign.hex())['result'] is False


def test_capture_channel_lists_accepts_only_owned_members_and_exact_bounds(codec):
    native=Writer().pack('B',1).raw(b'TC442UIChannel1234abcd\0').pack('BIQB',1,1,1,3).finish()
    name,encoded=call(codec,'chat_response','SMSG_CHANNEL_LIST',native)
    for packet in [native,bytes.fromhex(encoded)]:
        assert codec(op='public_channel_probe',name=name,body=packet.hex())['result'] is True
        assert codec(op='public_channel_probe',name=name,body=(packet+b'x').hex())['result'] is False
    foreign=Writer().pack('B',1).raw(b'TC442UIChannel1234abcd\0').pack('BIQB',1,1,9,3).finish()
    assert codec(op='public_channel_probe',name=name,body=foreign.hex())['result'] is False


def test_native_join_becomes_dedicated_modern_join_with_stable_channel_identity(codec):
    body=b'\x02TC442UIChannel1234abcd\0'+bytes([1])+bytes(8)
    name,encoded=call(codec,'chat_response','SMSG_CHANNEL_NOTIFY',body)
    assert name=='SMSG_CHANNEL_NOTIFY_JOINED'
    r=Reader(bytes.fromhex(encoded));assert (r.bits(7),r.bits(11))==(22,0)
    assert r.unpack('IBIQ')==(1,0,0,0)
    low,high=r.guid();assert low and high>>58==26 and (high>>42)&0x1fff==1
    assert r.raw(22)==b'TC442UIChannel1234abcd';r.end()
    assert call(codec,'chat_response','SMSG_CHANNEL_NOTIFY',body)==[name,encoded]
    other=b'\x02TC442UIChannel1234abce\0'+bytes([1])+bytes(8)
    assert call(codec,'chat_response','SMSG_CHANNEL_NOTIFY',other)[1]!=encoded


@pytest.mark.parametrize('password',[b'',b'secret'])
def test_capture_accepts_only_exact_owned_name_and_empty_password(codec,password):
    name=b'TC442UIChannel1234abcd'
    body=Writer().pack('I',0).bits(0,2).bits(len(name),7).bits(len(password),7).raw(name+password).finish()
    assert codec(op='public_channel_probe',name='CMSG_CHAT_JOIN_CHANNEL',body=body.hex())['result']==(not password)
    assert codec(op='public_channel_probe',name='CMSG_CHAT_JOIN_CHANNEL',body=(body+b'x').hex())['result'] is False
    foreign=Writer().pack('I',0).bits(0,2).bits(7,7).bits(0,7).raw(b'Private').finish()
    assert codec(op='public_channel_probe',name='CMSG_CHAT_JOIN_CHANNEL',body=foreign.hex())['result'] is False


def test_native_leave_is_authoritative_and_retains_suspend_flag(codec):
    body=b'\x03TestLab\0'+bytes(4)+b'\0'
    name,encoded=call(codec,'chat_response','SMSG_CHANNEL_NOTIFY',body)
    assert name=='SMSG_CHANNEL_NOTIFY_LEFT';r=Reader(bytes.fromhex(encoded))
    assert (r.bits(7),r.bits(1))==(7,0) and r.unpack('I')==(0,) and r.raw(7)==b'TestLab';r.end()


def test_native_member_list_expands_guids_and_keeps_flags(codec):
    body=Writer().pack('B',1).raw(b'TestLab\0').pack('BI',1,2).pack('QBQB',1,3,2,0).finish()
    name,encoded=call(codec,'chat_response','SMSG_CHANNEL_LIST',body)
    assert name=='SMSG_CHANNEL_LIST';r=Reader(bytes.fromhex(encoded))
    assert (r.bits(1),r.bits(7))==(1,7) and r.unpack('II')==(1,2) and r.raw(7)==b'TestLab'
    for guid,flags in [(1,3),(2,0)]:
        assert r.guid()==(guid,player_high()) and r.unpack('IB')==(0x01010001,flags)
    r.end()
    assert 'error' in codec(op='stateful',character={'guid':1},actions=[action('chat_response','SMSG_CHANNEL_LIST',body[:-1])])


def test_owner_change_notification_preserves_native_sender(codec):
    name,encoded=call(codec,'chat_response','SMSG_CHANNEL_NOTIFY',b'\x08TestLab\0'+(1).to_bytes(8,'little'))
    assert name=='SMSG_CHANNEL_NOTIFY';r=Reader(bytes.fromhex(encoded))
    assert (r.bits(6),r.bits(7),r.bits(6))==(8,7,0) and r.guid()==(1,player_high())
    assert r.guid()==(0,0) and r.unpack('I')==(0x01010001,) and r.guid()==(0,0)
    assert r.unpack('II')==(0x01010001,0) and r.raw(7)==b'TestLab';r.end()


@pytest.mark.parametrize('name',['SMSG_USERLIST_ADD','SMSG_USERLIST_UPDATE','SMSG_USERLIST_REMOVE'])
def test_native_userlist_identity_count_and_roles(codec,name):
    w=Writer().pack('Q',2)
    if name!='SMSG_USERLIST_REMOVE':w.pack('B',3)
    body=w.pack('BI',1,2).raw(b'TestLab\0').finish()
    actual,encoded=call(codec,'chat_response',name,body);assert actual==name
    r=Reader(bytes.fromhex(encoded));assert r.guid()==(2,player_high())
    if name!='SMSG_USERLIST_REMOVE':assert r.unpack('B')==(3,)
    assert r.unpack('II')==(1,2) and r.bits(7)==7 and r.raw(7)==b'TestLab';r.end()

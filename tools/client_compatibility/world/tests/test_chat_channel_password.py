"""Password wire widths and diagnostics restricted to a public disposable value."""
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,stateful,action

CHANNEL=b'TC442UIChannel1234abcd'
PASSWORD=b'TC442TestPass1'


@pytest.mark.parametrize('password',[b'',PASSWORD,b'x'*127])
def test_password_request_preserves_native_eight_seven_lengths(codec,password):
    body=Writer().bits(len(CHANNEL),7).bits(len(password),7).raw(CHANNEL+password).finish()
    replies=stateful(codec,{'guid':1},[action('chat_request','CMSG_CHAT_CHANNEL_PASSWORD',body)])
    assert replies[0][0]=='CMSG_CHAT_CHANNEL_PASSWORD'
    r=Reader(bytes.fromhex(replies[0][1]));assert (r.bits(8),r.bits(7))==(len(CHANNEL),len(password))
    assert r.raw(len(CHANNEL)+len(password))==CHANNEL+password;r.end()
    for bad in [body[:-1],body+b'x']:
        answer=stateful(codec,{'guid':1},[action('chat_request','CMSG_CHAT_CHANNEL_PASSWORD',bad)])
        assert 'error' in answer[0]


@pytest.mark.parametrize('width',[7,8])
@pytest.mark.parametrize('password',[b'',PASSWORD,b'arbitraryPrivate'])
def test_password_capture_excludes_arbitrary_secrets(codec,width,password):
    body=Writer().bits(len(CHANNEL),width).bits(len(password),7).raw(CHANNEL+password).finish()
    expected=password in [b'',PASSWORD]
    assert codec(op='public_channel_probe',name='CMSG_CHAT_CHANNEL_PASSWORD',body=body.hex())['result'] is expected
    assert not codec(op='public_channel_probe',name='CMSG_CHAT_CHANNEL_PASSWORD',body=(body+b'x').hex())['result']


def test_disposable_password_join_capture_in_both_wire_versions(codec):
    for password in [PASSWORD,b'arbitraryPrivate']:
        modern=Writer().pack('I',0).bits(0,2).bits(len(CHANNEL),7).bits(len(password),7).raw(CHANNEL+password).finish()
        native=stateful(codec,{'guid':1},[action('chat_request','CMSG_CHAT_JOIN_CHANNEL',modern)])[0]
        for name,body in [('CMSG_CHAT_JOIN_CHANNEL',modern),('CMSG_JOIN_CHANNEL',bytes.fromhex(native[1]))]:
            assert codec(op='public_channel_probe',name=name,body=body.hex())['result'] is (password==PASSWORD)


@pytest.mark.parametrize('kind',[4,7])
def test_owned_password_notification_and_rejection_capture(codec,kind):
    native=Writer().pack('B',kind).raw(CHANNEL+b'\0')
    if kind==7:native.pack('Q',1)
    native=native.finish();reply=stateful(codec,{'guid':1},[action('chat_response','SMSG_CHANNEL_NOTIFY',native)])[0]
    assert reply[0]=='SMSG_CHANNEL_NOTIFY';modern=bytes.fromhex(reply[1]);r=Reader(modern)
    assert (r.bits(6),r.bits(7),r.bits(6))==(kind,len(CHANNEL),0)
    assert r.guid()==((1,player_high()) if kind==7 else (0,0)) and r.guid()==(0,0)
    assert r.unpack('I')==(0x01010001,) and r.guid()==(0,0)
    assert r.unpack('II')==(0x01010001,0) and r.raw(len(CHANNEL))==CHANNEL;r.end()
    for body in [native,modern]:
        assert codec(op='public_channel_probe',name='SMSG_CHANNEL_NOTIFY',body=body.hex())['result']
        assert not codec(op='public_channel_probe',name='SMSG_CHANNEL_NOTIFY',body=(body+b'x').hex())['result']
    if kind==7:
        foreign=Writer().pack('B',7).raw(CHANNEL+b'\0').pack('Q',9).finish()
        foreign_reply=stateful(codec,{'guid':1},[action('chat_response','SMSG_CHANNEL_NOTIFY',foreign)])[0]
        for body in [foreign,bytes.fromhex(foreign_reply[1])]:
            assert not codec(op='public_channel_probe',name='SMSG_CHANNEL_NOTIFY',body=body.hex())['result']

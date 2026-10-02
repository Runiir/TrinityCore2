"""Guild membership wire translation preserves server identities and outcomes."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_guild_packets import call,HIGH
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec


def test_member_requests_map_to_native_authoritative_commands(codec):
    target=b'Harnesstwo-Client442 Lab'
    w=Writer().bits(len(target),9).bits(0,1).raw(target)
    name,body=call(codec,'guild_request','CMSG_GUILD_INVITE_BY_NAME',w.finish())
    r=Reader(bytes.fromhex(body));size=r.bits(7);r.align()
    assert name=='CMSG_GUILD_INVITE' and r.raw(size)==b'Harnesstwo';r.end()
    extra=Writer().bits(10,9).bits(1,1).raw(b'Harnesstwo').pack('i',99).finish()
    assert call(codec,'guild_request','CMSG_GUILD_INVITE_BY_NAME',extra)[0]=='CMSG_GUILD_INVITE'
    for modern,native,packet in [
        ('CMSG_ACCEPT_GUILD_INVITE','CMSG_GUILD_ACCEPT',Writer().guid(1,HIGH).finish()),
        ('CMSG_GUILD_DECLINE_INVITATION','CMSG_GUILD_DECLINE',Writer().guid(1,HIGH).bits(0,1).finish()),
        ('CMSG_GUILD_LEAVE','CMSG_GUILD_LEAVE',b''),('CMSG_GUILD_DELETE','CMSG_GUILD_DISBAND',b'')]:
        assert call(codec,'guild_request',modern,packet)==[native,'']
    assert 'error' in call(codec,'guild_request','CMSG_ACCEPT_GUILD_INVITE',Writer().guid(1,player_high()).finish())


def native_invite():
    fresh=struct.pack('<Q',(0x1ff<<52)|258);old=b'\0'*8
    title=b'Harness Ui Test';inviter=b'Harnessone'
    w=Writer().pack('6I',1,3,4,1,5,2)
    w.bits(bool(fresh[3]),1).bits(bool(fresh[2]),1).bits(0,8).bits(bool(fresh[1]),1)
    for i in [6,4,1,5,7,2]:w.bits(bool(old[i]),1)
    for i in [7,0,6]:w.bits(bool(fresh[i]),1)
    w.bits(len(title),8).bits(0,1).bits(0,1).bits(bool(fresh[5]),1).bits(len(inviter),7).bits(bool(fresh[4]),1).flush()
    def byte(o,i):
        if o[i]:w.pack('B',o[i]^1)
    byte(fresh,1);byte(old,3);byte(fresh,6);byte(old,2);byte(old,1);byte(fresh,0)
    byte(fresh,7);byte(fresh,2);w.raw(inviter)
    for i in [7,6,5,0]:byte(old,i)
    byte(fresh,4);w.raw(title);byte(fresh,5);byte(fresh,3);byte(old,4)
    return w.finish()


def test_invite_response_keeps_names_emblem_and_guild_guid(codec):
    packet=native_invite();name,body=call(codec,'guild_response','SMSG_GUILD_INVITE',packet)
    r=Reader(bytes.fromhex(body));a=r.bits(6);b=r.bits(7);c=r.bits(7);r.align()
    assert name=='SMSG_GUILD_INVITE' and r.unpack('II')==(1,1) and r.guid()==(258,HIGH)
    assert r.unpack('I')==(0,) and r.guid()==(0,0) and r.unpack('6I')==(1,2,3,4,5,0)
    assert r.raw(a)==b'Harnessone' and r.raw(b)==b'Harness Ui Test' and r.raw(c)==b'';r.end()
    assert 'error' in call(codec,'guild_response','SMSG_GUILD_INVITE',packet[:-1])


def test_guild_text_commands_keep_independent_native_bit_widths(codec):
    for modern,native,width in [('CMSG_GUILD_UPDATE_MOTD_TEXT','CMSG_GUILD_MOTD',11),
                                ('CMSG_GUILD_UPDATE_INFO_TEXT','CMSG_GUILD_INFO_TEXT',12)]:
        text=b'TC442UI:text';packet=Writer().bits(len(text),11).raw(text).finish()
        name,body=call(codec,'guild_request',modern,packet);r=Reader(bytes.fromhex(body));size=r.bits(width);r.align()
        assert name==native and r.raw(size)==text;r.end()


def test_guild_events_keep_join_leave_presence_and_motd_semantics(codec):
    for event,expected in [(4,'SMSG_GUILD_EVENT_PLAYER_JOINED'),(5,'SMSG_GUILD_EVENT_PLAYER_LEFT'),
                           (16,'SMSG_GUILD_EVENT_PRESENCE_CHANGE'),(17,'SMSG_GUILD_EVENT_PRESENCE_CHANGE')]:
        packet=Writer().pack('BB',event,1).raw(b'Harnesstwo\0').pack('Q',258).finish()
        name,body=call(codec,'guild_response','SMSG_GUILD_EVENT',packet);r=Reader(bytes.fromhex(body))
        assert name==expected
        if event==5:assert r.bits(1)==0;size=r.bits(6);r.align()
        assert r.guid()==(258,player_high()) and r.unpack('I')==(1,)
        if event!=5:
            size=r.bits(6)
            if event in [16,17]:assert r.bits(1)==(event==16)
            r.align()
        assert r.raw(size)==b'Harnesstwo';r.end()
    packet=Writer().pack('BB',3,1).raw(b'TC442UI:motd\0').pack('Q',0).finish()
    name,body=call(codec,'guild_response','SMSG_GUILD_EVENT',packet);r=Reader(bytes.fromhex(body));size=r.bits(11);r.align()
    assert name=='SMSG_GUILD_EVENT_MOTD' and r.raw(size)==b'TC442UI:motd';r.end()
    assert call(codec,'guild_response','SMSG_GUILD_EVENT',struct.pack('<BBQ',9,0,0))==['SMSG_GUILD_EVENT_DISBANDED','']


def test_public_and_officer_note_requests_preserve_guid_text_and_flag(codec):
    for public,text in [(1,b'TC442UI:note'),(0,b'')]:
        packet=Writer().guid(258,player_high()).bits(len(text),8).bits(public,1).raw(text).finish()
        name,body=call(codec,'guild_request','CMSG_GUILD_SET_MEMBER_NOTE',packet)
        r=Reader(bytes.fromhex(body));octets=[0]*8
        for i in [1,4,5,3,0,7]:octets[i]=r.bits(1)
        assert r.bits(1)==(not public);octets[6]=r.bits(1);size=r.bits(8);octets[2]=r.bits(1);r.align()
        for i in [4,5,0,3,1,6,7]:
            if octets[i]:octets[i]=r.unpack('B')[0]^1
        assert r.raw(size)==text
        if octets[2]:octets[2]=r.unpack('B')[0]^1
        r.end();assert name=='CMSG_GUILD_SET_NOTE' and int.from_bytes(bytes(octets),'little')==258


def test_note_updates_preserve_empty_clear_and_officer_visibility_flag(codec):
    for public,text in [(0,b'TC442UI:officer'),(1,b'')]:
        octets=struct.pack('<Q',258);w=Writer()
        for i in [7,2,3]:w.bits(bool(octets[i]),1)
        w.bits(len(text),8)
        for i in [5,0,6,4]:w.bits(bool(octets[i]),1)
        w.bits(not public,1).bits(bool(octets[1]),1).flush()
        def byte(i):
            if octets[i]:w.pack('B',octets[i]^1)
        for i in [3,0,2,5]:byte(i)
        w.raw(text)
        for i in [7,6,1,4]:byte(i)
        name,body=call(codec,'guild_response','SMSG_GUILD_MEMBER_UPDATE_NOTE',w.finish())
        r=Reader(bytes.fromhex(body));assert name=='SMSG_GUILD_MEMBER_UPDATE_NOTE' and r.guid()==(258,player_high())
        size=r.bits(8);assert r.bits(1)==public;r.align();assert r.raw(size)==text;r.end()

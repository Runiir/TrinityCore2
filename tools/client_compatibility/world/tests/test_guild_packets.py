"""Guild names/ranks and bit-packed legacy rosters preserve visible member facts."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action

HIGH=(28<<58)|(1<<42)


def call(codec,fn,name,body):
    return result(codec,op='stateful',character={'guid':1},snapshot=None,last_logout_guid=0,
                  gameobjects=[],units=[],identities=[{'guid':1,'race':1},{'guid':258,'race':3}],
                  actions=[action(fn,name,body)])[0]


def test_installed_guild_query_empty_player_uses_owned_native_member(codec):
    body=bytes.fromhex('01a00104700000')
    assert call(codec,'guild_request','CMSG_QUERY_GUILD_INFO',body)==[
        'CMSG_GUILD_QUERY',struct.pack('<QQ',(0x1ff<<52)|1,1).hex()]
    assert call(codec,'guild_request','CMSG_GUILD_GET_ROSTER',b'')==['CMSG_GUILD_GET_ROSTER','']
    assert 'error' in call(codec,'guild_request','CMSG_QUERY_GUILD_INFO',body+b'x')
    assert 'error' in call(codec,'guild_request','CMSG_QUERY_GUILD_INFO',Writer().guid(1,player_high()).guid().finish())


def test_query_response_retains_rank_ids_orders_and_guild_identity(codec):
    w=Writer().pack('Q',(0x1ff<<52)|1).raw(b'Harness Ui Test\0')
    for i in range(10):w.raw((['Guild Master','Officer'][i] if i<2 else '').encode()+b'\0')
    w.pack('10I',1,0,*([0]*8)).pack('10I',0,1,*([0]*8)).pack('6I',1,2,3,4,5,2)
    name,body=call(codec,'guild_response','SMSG_QUERY_GUILD_INFO_RESPONSE',w.finish())
    r=Reader(bytes.fromhex(body));assert name=='SMSG_QUERY_GUILD_INFO_RESPONSE' and r.guid()==(1,HIGH)
    assert r.bits(1)==1;r.align();assert r.guid()==(1,HIGH) and r.unpack('7I')==(1,2,1,2,3,4,5)
    n=r.bits(7);r.align()
    for expected in [(0,1,'Guild Master'),(1,0,'Officer')]:
        assert r.unpack('2I')==expected[:2];size=r.bits(7);r.align();assert r.raw(size).decode()==expected[2]
    assert r.raw(n)==b'Harness Ui Test';r.end()


def native_roster():
    # Independent legacy GuildRoster::Write order, including XOR GUID octets,
    # interleaved profession Step/Rank/DbID, trailing packed date, and notes.
    rows=[(1,b'Harnessone',b'TC442UI:note',b'TC442UI:officer'),(258,b'Harnesstwo',b'',b'')]
    w=Writer().bits(4,11).bits(len(rows),18)
    for guid,name,note,officer in rows:
        octets=struct.pack('<Q',guid)
        for i in [3,4]:w.bits(bool(octets[i]),1)
        w.bits(1,1).bits(0,1).bits(len(note),8).bits(len(officer),8).bits(bool(octets[0]),1).bits(len(name),7)
        for i in [1,2,6,5,7]:w.bits(bool(octets[i]),1)
    w.bits(4,12).flush()
    for guid,name,note,officer in rows:
        octets=struct.pack('<Q',guid)
        def byte(i):
            if octets[i]:w.pack('B',octets[i]^1)
        w.pack('BI',1,99);byte(0);w.pack('QII',11,0,123)
        w.pack('6I',8,525,171,7,450,185);byte(2);w.pack('BIQ',1,3,22);byte(7)
        w.pack('I',42).raw(note);byte(3);w.pack('BI',85,0);byte(5);byte(4)
        w.pack('B',0);byte(1);w.pack('f',0.5).raw(officer);byte(6);w.raw(name)
    return w.raw(b'info').raw(b'motd').pack('4I',2,3500,0x12345678,0).finish()


def test_roster_preserves_two_guid_shapes_professions_notes_and_native_date(codec):
    packet=native_roster();decoded=result(codec,op='native_guild_roster',body=packet.hex())
    assert [m['guid'] for m in decoded['members']]==[1,258]
    assert decoded['members'][0]['professions']==[[171,525,8],[185,450,7]]
    assert decoded['members'][0]['note']=='TC442UI:note' and decoded['members'][1]['note']==''
    name,body=call(codec,'guild_response','SMSG_GUILD_ROSTER',packet);assert name=='SMSG_GUILD_ROSTER'
    r=Reader(bytes.fromhex(body));assert r.unpack('4I')==(2,0x12345678,0,2)
    assert r.bits(11)==4 and r.bits(11)==4;r.align()
    for guid,race,note,officer in [(1,1,b'TC442UI:note',b'TC442UI:officer'),(258,3,b'',b'')]:
        assert r.guid()==(guid,player_high()) and r.unpack('4if')==(0,3,123,99,0.5)
        assert r.unpack('6i')==(171,525,8,185,450,7)
        assert r.unpack('IBBBBQB')==(1,1,85,1,0,0,race)
        n=r.bits(6);a=r.bits(8);b=r.bits(8);assert r.bits(1)==1;r.align()
        assert r.unpack('ffI')==(0,0,0)
        assert r.raw(n).decode() in ['Harnessone','Harnesstwo'] and r.raw(a)==note and r.raw(b)==officer
    assert r.raw(8)==b'motdinfo';r.end()
    assert 'error' in codec(op='native_guild_roster',body=packet[:-1].hex())


def test_command_error_order_is_result_then_command(codec):
    body=Writer().pack('I',1).raw(b'Harnesstwo\0').pack('I',6).finish()
    name,encoded=call(codec,'guild_response','SMSG_GUILD_COMMAND_RESULT',body)
    r=Reader(bytes.fromhex(encoded));assert r.unpack('2i')==(6,1)
    size=r.bits(8);r.align();assert r.raw(size)==b'Harnesstwo';r.end()

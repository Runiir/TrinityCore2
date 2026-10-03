"""Independent mail readers and malformed-body checks for both protocol generations."""
import math
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

GUID=(0xf11<<52)|(197135<<32)|220045
GO={'guid':GUID,'kind':5,'map':0,'fields':{str(INDEX['GAMEOBJECT_BYTES_1']):19<<8}}


def call(codec, name, body, fn='mail_response', gameobjects=None, units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
        gameobjects=[GO] if gameobjects is None else gameobjects,units=units or [],
        actions=[{'fn':fn,'name':name,'body':body.hex()}])[0]


def item(position=0, guid=17, entry=64394, count=5, prop=-3, seed=2**32-1, charges=-1,
         maximum=12, durability=9, unlocked=1, enchanted=True):
    enchants=[(0,0,0)]*10
    if enchanted:enchants[2]=(44,123,2**32-1)
    return (struct.pack('<BII',position,guid,entry)+b''.join(struct.pack('<3I',*enchant) for enchant in enchants)+
            struct.pack('<iIIiIIB',prop,seed,count,charges,maximum,durability,unlocked))


def entry(id=4, type_=0, sender=2, cod=125, money=300, stationery=41, flags=1,
          days=29.5, template=0, subject=b'Protocol trial', body=b'Ordinary mail body', attachments=None, size_adjust=-4):
    attachments=[item()] if attachments is None else attachments
    sender_data=struct.pack('<Q' if type_==0 else '<I',sender)
    data=(struct.pack('<IB',id,type_)+sender_data+struct.pack('<QIIQIfI',cod,0,stationery,money,flags,days,template)+
          subject+b'\0'+body+b'\0'+bytes([len(attachments)])+b''.join(attachments))
    return struct.pack('<H',len(data)+2+size_adjust)+data


def catalog(entries=None, total=None):
    rows=[entry()] if entries is None else entries
    return struct.pack('<IB',len(rows) if total is None else total,len(rows))+b''.join(rows)


def parse_item(r):
    values=r.unpack('BQiiIi');entry_id,seed,prop=r.unpack('iIi')
    assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align()
    enchant_count=r.bits(4);assert r.bits(2)==0;unlocked=r.bits(1);r.align()
    enchants=[r.unpack('iIiB') for _ in range(enchant_count)]
    return values,(entry_id,seed,prop),unlocked,enchants


def parse_entry(r):
    id,type_,cod,stationery,money,flags,days,template,count=r.unpack('QIQIQIfII')
    sender=r.guid() if type_==0 else r.unpack('I')[0]
    subject_size=r.bits(8);body_size=r.bits(13);r.align()
    items=[parse_item(r) for _ in range(count)]
    return {'id':id,'type':type_,'cod':cod,'stationery':stationery,'money':money,'flags':flags,'days':days,
            'template':template,'sender':sender,'items':items,'subject':r.raw(subject_size),'body':r.raw(body_size)}


def test_visible_gameobject_and_creature_mailboxes_preserve_native_authority(codec):
    body=Writer().guid(*modern_guid(GUID,0)).finish()
    assert call(codec,'CMSG_MAIL_GET_LIST',body,'mail_request')==['CMSG_GET_MAIL_LIST',struct.pack('<Q',GUID).hex()]
    for objects in [[],[{**GO,'kind':3}],[{**GO,'fields':{str(INDEX['GAMEOBJECT_BYTES_1']):3<<8}}]]:
        assert 'error' in call(codec,'CMSG_MAIL_GET_LIST',body,'mail_request',gameobjects=objects)
    npc=(0xf13<<52)|(123<<32)|18
    unit={'guid':npc,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):0x04000000}}
    request=Writer().guid(*modern_guid(npc,0)).finish()
    assert call(codec,'CMSG_MAIL_GET_LIST',request,'mail_request',units=[unit])[1]==struct.pack('<Q',npc).hex()
    for invalid in [Writer().guid(1,player_high()).finish(),body[:-1],body+b'x']:
        assert 'error' in call(codec,'CMSG_MAIL_GET_LIST',invalid,'mail_request')


def test_mailbox_open_is_native_authorized_and_uses_normal_interaction_kind(codec):
    response=call(codec,'SMSG_SHOW_MAILBOX',struct.pack('<Q',GUID));assert response[0]=='SMSG_NPC_INTERACTION_OPEN_RESULT'
    r=Reader(bytes.fromhex(response[1]));assert r.guid()==modern_guid(GUID,0);assert r.unpack('i')==(17,)
    assert r.bits(1)==1;r.end()
    assert 'error' in call(codec,'SMSG_SHOW_MAILBOX',struct.pack('<Q',GUID),gameobjects=[])


@pytest.mark.parametrize('adjust',[-4,0])
def test_mail_list_preserves_money_body_attachment_identity_and_enchants(codec,adjust):
    response=call(codec,'SMSG_MAIL_LIST_RESULT',catalog([entry(size_adjust=adjust)],total=7))
    assert response[0]=='SMSG_MAIL_LIST_RESULT';r=Reader(bytes.fromhex(response[1]));assert r.unpack('Ii')==(1,7)
    mail=parse_entry(r);r.end()
    assert mail=={'id':4,'type':0,'cod':125,'stationery':41,'money':300,'flags':1,'days':29.5,'template':0,
                 'sender':(2,player_high()),'items':[((0,17,5,-1,12,9),(64394,2**32-1,-3),1,[(44,123,-1,2)])],
                 'subject':b'Protocol trial','body':b'Ordinary mail body'}


def test_mail_types_multiple_entries_empty_inbox_and_maximum_strings(codec):
    rows=[entry(id=type_,type_=type_,sender=16128,attachments=[],subject=b'S'*255,body=b'T'*8191) for type_ in [2,3,4]]
    # Native packets cannot exceed 32767 bytes, even when the modern strings fit.
    response=call(codec,'SMSG_MAIL_LIST_RESULT',catalog(rows));r=Reader(bytes.fromhex(response[1]))
    assert r.unpack('Ii')==(3,3)
    mails=[parse_entry(r) for _ in rows];r.end();assert [m['type'] for m in mails]==[2,3,4]
    assert all(m['sender']==16128 and len(m['body'])==8191 and len(m['subject'])==255 for m in mails)
    assert call(codec,'SMSG_MAIL_LIST_RESULT',catalog([]))==['SMSG_MAIL_LIST_RESULT','0000000000000000']


@pytest.mark.parametrize('changes',[{'id':0},{'type_':1},{'type_':6},{'days':math.nan},{'days':math.inf},
    {'size_adjust':-5},{'subject':b'S'*256},{'body':b'T'*8192},{'sender':2**40}])
def test_mail_catalog_rejects_unrepresentable_metadata(codec,changes):
    assert 'error' in call(codec,'SMSG_MAIL_LIST_RESULT',catalog([entry(**changes)]))


@pytest.mark.parametrize('changes',[{'position':1},{'guid':0},{'entry':0},{'count':0},{'unlocked':2},
    {'maximum':4,'durability':5},{'maximum':2**31},{'entry':2**31},{'count':2**31}])
def test_mail_catalog_rejects_malformed_attachments(codec,changes):
    assert 'error' in call(codec,'SMSG_MAIL_LIST_RESULT',catalog([entry(attachments=[item(**changes)])]))


def test_mail_catalog_rejects_duplicate_ids_bad_count_truncation_and_trailing_bytes(codec):
    for body in [catalog([entry(),entry()]),catalog(total=0),b'\x00'*4+b'\x33',catalog([entry(attachments=[item()]*13)]),
                 catalog([entry(body=b'x'*8100,attachments=[]) for _ in range(5)])]:
        assert 'error' in call(codec,'SMSG_MAIL_LIST_RESULT',body)
    body=catalog()
    for length in range(len(body)):
        assert 'error' in call(codec,'SMSG_MAIL_LIST_RESULT',body[:length])
    assert 'error' in call(codec,'SMSG_MAIL_LIST_RESULT',body+b'x')


def test_next_mail_time_reads_are_empty_and_preserve_sender_times(codec):
    assert call(codec,'CMSG_QUERY_NEXT_MAIL_TIME',b'','mail_request')==['MSG_QUERY_NEXT_MAIL_TIME','']
    assert 'error' in call(codec,'CMSG_QUERY_NEXT_MAIL_TIME',b'x','mail_request')
    native=struct.pack('<fI',0.,2)+struct.pack('<QIIIf',2,0,0,41,-5.)+struct.pack('<QIIIf',0,32216,3,61,25.)
    response=call(codec,'MSG_QUERY_NEXT_MAIL_TIME',native);assert response[0]=='SMSG_MAIL_QUERY_NEXT_TIME_RESULT'
    r=Reader(bytes.fromhex(response[1]));assert r.unpack('fI')==(0.,2)
    assert r.guid()==(2,player_high());assert r.unpack('fIBI')==(-5.,0,0,41)
    assert r.guid()==(0,0);assert r.unpack('fIBI')==(25.,32216,3,61);r.end()
    for body in [native[:-1],native+b'x',struct.pack('<fI',math.nan,0),struct.pack('<fI',0.,3)]:
        assert 'error' in call(codec,'MSG_QUERY_NEXT_MAIL_TIME',body)
    assert call(codec,'SMSG_RECEIVED_MAIL',bytes(4))==['SMSG_NOTIFY_RECEIVED_MAIL','00000000']
    assert 'error' in call(codec,'SMSG_RECEIVED_MAIL',struct.pack('<I',1))


def test_early_mail_read_deduplicates_and_releases_once_without_mutation(codec):
    mail={'fn':'mail','name':'MSG_QUERY_NEXT_MAIL_TIME','body':''}
    rows=result(codec,op='login_quest_reads',actions=[mail,mail,{'fn':'release'},{'fn':'release'}])
    assert [r['queued'] for r in rows]==[1,1,0,0]
    assert rows[2]['packets']==[['MSG_QUERY_NEXT_MAIL_TIME','']] and rows[3]['packets']==[]
    for invalid in [{**mail,'name':'CMSG_SEND_MAIL'},{**mail,'body':'00'}]:
        assert 'error' in codec(op='login_quest_reads',actions=[invalid])


def test_public_mail_sender_queries_work_before_and_after_catalog_and_logout(codec):
    query=struct.pack('<I',16128)
    actions=[{'fn':'creature_query','name':'CMSG_QUERY_CREATURE','body':query.hex()},
             {'fn':'mail_response','name':'SMSG_MAIL_LIST_RESULT','body':catalog([entry(type_=3,sender=16128)]).hex()},
             {'fn':'creature_query','name':'CMSG_QUERY_CREATURE','body':query.hex()},
             {'fn':'creature_query','name':'CMSG_QUERY_CREATURE','body':struct.pack('<I',99).hex()},
             {'fn':'logout_complete','name':'SMSG_LOGOUT_COMPLETE','body':''},
             {'fn':'creature_query','name':'CMSG_QUERY_CREATURE','body':query.hex()}]
    rows=result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
                gameobjects=[],units=[],actions=actions)
    assert rows[0]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',16128,0).hex()]
    assert rows[2]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',16128,0).hex()]
    assert rows[3]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',99,0).hex()]
    assert rows[4] is None
    # The codec is not a live session. The service's require_world gate still
    # rejects any cache request without an authenticated, entered actor.
    assert rows[5]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',16128,0).hex()]


def test_malformed_mail_catalog_cannot_disable_public_template_queries(codec):
    valid=catalog([entry(type_=3,sender=16128)])
    invalid=catalog([entry(type_=3,sender=32216),entry(type_=3,sender=32216)])
    actions=[{'fn':'mail_response','name':'SMSG_MAIL_LIST_RESULT','body':body.hex()} for body in [valid,invalid]]
    actions.extend({'fn':'creature_query','name':'CMSG_QUERY_CREATURE','body':struct.pack('<I',entry_).hex()}
                   for entry_ in [32216,16128])
    rows=result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
                gameobjects=[],units=[],actions=actions)
    assert 'error' in rows[1] and rows[2]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',32216,0).hex()]
    assert rows[3]==['CMSG_QUERY_CREATURE',struct.pack('<IQ',16128,0).hex()]


def test_actual_three_reward_letters_keep_attachment_identity_and_subjects(codec):
    # UI14 mailbox_open_01 native 1579-byte catalog. SHA-256:
    # 90bd725aad281f207eacc1da9693d52aa5b674717b36da4c5bb3d9b003599762
    body=bytes.fromhex(
        '030000000323020300000003d87d000000000000000000000000000029000000000000000000000000000000e209e441000000004d6f756e7461696e206f2720'
        '4d6f756e7473004927766520686561726420796f757220737461626c657320617265206e6561726c7920617320657874656e73697665206173206d696e652c20'
        '6e6f772e20496d70726573736976652120506572686170732077652063616e2068656c70206f6e6520616e6f746865722e2e2049277665206f6e6520746f6f20'
        '6d616e7920647261676f6e6861776b732c20616e6420686f70656420796f7520636f756c6420676976652074686973206f6e65206120686f6d652e204e617475'
        '72616c6c7920697473206265656e20747261696e65642061732061206d6f756e7420616e64206e6f7420612068756e74696e67207065742c20616e6420796f75'
        '276c6c2066696e64206974206173206c6f79616c20616e6420746972656c65737320617320616e79206f7468657220737465656420492072616973652e202442'
        '20596f75727320616761696e2c4d65690001001d0000002baf000000000000000000000000000000000000000000000000000000000000000000000000000000'
        '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        '00000000000000000000000000000000000000000000000000000001000000ffffffff0000000000000000000f020200000003d87d0000000000000000000000'
        '00000029000000000000000000000000000000d609e441000000004c656164696e672074686520436176616c7279004920636f756c646e27742068656c702062'
        '757420746f206e6f7469636520686f7720676f6f6420796f7520617265207769746820746865206c69766573746f636b2e205769746820616c6c207468652061'
        '637469766974792061726f756e6420686572652c20627573696e65737320686173206265656e20626574746572207468616e206576657220666f72206d652e20'
        '4920646f6e277420737570706f736520796f752764206d696e64206c6f6f6b696e67206166746572207468697320416c62696e6f204472616b6520666f72206d'
        '653f20492073696d706c7920646f6e2774206861766520656e6f756768207370617265206d696e7574657320696e207468652064617920746f20636172652066'
        '6f7220616c6c206f6620746865736520616e696d616c732e20596f7572732c204d65690001001c00000092ac0000000000000000000000000000000000000000'
        '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        '0000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000001000000ffffffff000000000000000000e8'
        '010100000003003f000000000000000000000000000029000000000000000000000000000000614be341000000004c6576656c20383000436f6e67726174756c'
        '6174696f6e73206f6e20796f757220636f6e76696374696f6e20746f20726561636820746865203830746820736561736f6e206f6620616476656e747572652e'
        '20596f752061726520756e646f75627465646c792064656469636174656420746f20746865206361757365206f662072696464696e6720417a65726f7468206f'
        '6620746865206576696c73207768696368206861766520706c61677565642075732e24422442416e64207768696c6520746865206a6f75726e65792074687573'
        '2066617220686173206265656e206e6f206d696e6f7220666561742c20746865207472756520626174746c65206c6965732061686561642e2442244246696768'
        '74206f6e212442244252686f6e696e0001000b000000d2a100000000000000000000000000000000000000000000000000000000000000000000000000000000'
        '00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000'
        '00000000000000000000000000000000000000000000000000000100000000000000000000000000000000'
    )
    response=call(codec,'SMSG_MAIL_LIST_RESULT',body)
    r=Reader(bytes.fromhex(response[1])); assert r.unpack('Ii')==(3,3)
    mails=[parse_entry(r) for _ in range(3)];r.end()
    assert [m['id'] for m in mails]==[3,2,1]
    assert [m['subject'] for m in mails]==[b"Mountain o' Mounts",b"Leading the Cavalry",b"Level 80"]
    assert [m['sender'] for m in mails]==[32216,32216,16128]
    assert [m['items'][0][0][1] for m in mails]==[29,28,11]
    assert [m['items'][0][1][0] for m in mails]==[44843,44178,41426]

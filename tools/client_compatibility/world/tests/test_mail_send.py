"""Independent legacy mail reader verifies modern send and return translations."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer,player_high
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_mail_actions import action,setup,run
from tools.client_compatibility.world.tests.test_mail_packets import GUID,GO

ITEM=(0x4000<<48)|0x12345678
ITEM_HIGH=(3<<58)|(1<<42)


@pytest.mark.parametrize('name',['CMSG_SEND_MAIL','CMSG_MAIL_RETURN_TO_SENDER','CMSG_MAIL_GET_LIST','CMSG_MAIL_DELETE'])
@pytest.mark.parametrize('created,active_world,in_world',[(c,a,w) for c in [False,True] for a in [False,True] for w in [False,True]])
def test_mail_channel_requires_its_owned_active_character(codec,name,created,active_world,in_world):
    answer=codec(op='mail_context',name=name,created=created,active_world=active_world,in_world=in_world)
    allowed=created and active_world and (in_world or name in ['CMSG_SEND_MAIL','CMSG_MAIL_RETURN_TO_SENDER'])
    assert (answer.get('result') is True)==allowed
    if not allowed:assert 'error' in answer


def send(target=b'Harnesstwo',subject=b'Protocol letter',body=b'Ordinary text',money=0,cod=0,stationery=41,items=()):
    w=Writer().guid(*modern_guid(GUID,0)).pack('iqq',stationery,money,cod)
    w.bits(len(target),9).bits(len(subject),9).bits(len(body),11).bits(len(items),5).flush()
    w.raw(target).raw(subject).raw(body)
    for position,low,high in items:w.pack('B',position).guid(low,high)
    return w.finish()


def request(codec,body,items=()):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
                  gameobjects=[GO],units=[],inventory_items=[{'guid':id,'kind':1,'fields':{}} for id in items],
                  actions=setup()+[action('mail_request','CMSG_SEND_MAIL',body)])[-1]


def legacy_send(body):
    r=Reader(body);package,stationery,cod,money=r.unpack('IIQQ')
    body_length=r.bits(12);subject_length=r.bits(9);count=r.bits(5);box=[0]*8;items=[]
    def masks(guid,order):
        for i in order:guid[i]=r.bits(1)
    def octets(guid,order):
        for i in order:
            if guid[i]:guid[i]=r.unpack('B')[0]^1
    masks(box,[0])
    for _ in range(count):
        guid=[0]*8;masks(guid,[2,6,3,7,1,0,4,5]);items.append(guid)
    masks(box,[3,4]);target_length=r.bits(7);masks(box,[2,6,1,7,5]);r.align();octets(box,[4])
    attached=[]
    for guid in items:
        octets(guid,[6,1,7,2]);position=r.unpack('B')[0];octets(guid,[3,0,4,5])
        attached.append((position,int.from_bytes(bytes(guid),'little')))
    octets(box,[7,3,6,5]);subject=r.raw(subject_length);target=r.raw(target_length)
    octets(box,[2,0]);message=r.raw(body_length);octets(box,[1]);r.end()
    return {'package':package,'stationery':stationery,'cod':cod,'money':money,'mailbox':int.from_bytes(bytes(box),'little'),
            'target':target,'subject':subject,'body':message,'attachments':attached}


@pytest.mark.parametrize('money,cod',[(0,0),(12345,777),(2**63-1,2**63-1)])
def test_send_preserves_strings_mailbox_money_and_cod(codec,money,cod):
    row=request(codec,send(money=money,cod=cod));assert row[0]=='CMSG_SEND_MAIL'
    assert legacy_send(bytes.fromhex(row[1]))=={'package':0,'stationery':41,'cod':cod,'money':money,'mailbox':GUID,
        'target':b'Harnesstwo','subject':b'Protocol letter','body':b'Ordinary text','attachments':[]}


def test_live_client_removes_local_realm_suffix_before_serializing(codec):
    # UI17 mail_return_02: ordinary autocomplete displays the local realm, but
    # the captured Realm-channel SendMail packet already contains a bare name.
    body=bytes.fromhex('03a7d12dc083c0042c29000000010000000000000000000000000000000505814800'
        '4861726e65737374776f3434322055492072657475726e203061313436316538'
        '4f776e656420636f6d7061746962696c697479206c65747465722e2052657475726e20747269616c2e')
    live_guid=0xf113020f00002dd1
    box=Writer().guid(*modern_guid(live_guid,0)).finish()
    row=result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
        gameobjects=[dict(GO,guid=live_guid)],units=[],actions=[
            action('mail_request','CMSG_MAIL_GET_LIST',box),setup()[1],
            action('mail_request','CMSG_SEND_MAIL',body)])[-1]
    assert row[0]=='CMSG_SEND_MAIL'
    parsed=legacy_send(bytes.fromhex(row[1]));assert parsed['mailbox']==live_guid
    assert parsed['target']==b'Harnesstwo' and parsed['money']==1 and parsed['cod']==0
    assert parsed['subject']==b'442 UI return 0a1461e8'
    assert parsed['body']==b'Owned compatibility letter. Return trial.'


def test_owned_attachments_and_maximum_native_strings(codec):
    items=[(0,ITEM&0xffffffff,ITEM_HIGH),(11,17,ITEM_HIGH)]
    row=request(codec,send(target=b'T'*127,subject=b'S'*511,body=b'B'*2047,items=items),[ITEM,(0x4000<<48)|17])
    parsed=legacy_send(bytes.fromhex(row[1]));assert parsed['attachments']==[(0,ITEM),(11,(0x4000<<48)|17)]
    assert len(parsed['target'])==127 and len(parsed['subject'])==511 and len(parsed['body'])==2047


def test_modern_attachment_limit_reaches_native_gameplay_validation(codec):
    native_items=[(0x4000<<48)|i for i in range(1,17)]
    row=request(codec,send(items=[(i,i+1,ITEM_HIGH) for i in range(16)]),native_items)
    assert len(legacy_send(bytes.fromhex(row[1]))['attachments'])==16
    assert 'error' in request(codec,send(items=[(i,i+1,ITEM_HIGH) for i in range(17)]),native_items)


@pytest.mark.parametrize('changes',[{'target':b''},{'target':b'T'*128},{'money':-1},{'cod':-1},
    {'stationery':-1},{'body':b'A\0B'},{'subject':b'A\0B'},{'target':b'A\0B'},
    {'items':[(0,17,ITEM_HIGH)]},{'items':[(0,ITEM&0xffffffff,player_high())]},
    {'items':[(0,ITEM&0xffffffff,ITEM_HIGH)]*2},{'items':[(0,17,ITEM_HIGH)]*13}])
def test_invalid_metadata_and_foreign_or_duplicate_inventory_are_rejected(codec,changes):
    assert 'error' in request(codec,send(**changes),[ITEM])


def test_truncated_and_trailing_send_bodies_cannot_mutate_native_mail(codec):
    body=send(items=[(0,ITEM&0xffffffff,ITEM_HIGH)])
    for invalid in [body[:i] for i in range(len(body))]+[body+b'x']:
        assert 'error' in request(codec,invalid,[ITEM])


def test_return_uses_catalog_mailbox_and_owned_id_and_preserves_sender(codec):
    body=Writer().pack('Q',4).guid(2,player_high()).finish()
    row=run(codec,setup()+[action('mail_request','CMSG_MAIL_RETURN_TO_SENDER',body)])[-1]
    assert row==['CMSG_MAIL_RETURN_TO_SENDER',struct.pack('<QIQ',GUID,4,2).hex()]
    for invalid in [body[:-1],body+b'x',Writer().pack('Q',5).guid(2,player_high()).finish(),
                    Writer().pack('Q',4).guid(2,ITEM_HIGH).finish()]:
        assert 'error' in run(codec,setup()+[action('mail_request','CMSG_MAIL_RETURN_TO_SENDER',invalid)])[-1]
    result_body=struct.pack('<III',4,3,0)
    rows=run(codec,setup()+[action('mail_response','SMSG_SEND_MAIL_RESULT',result_body),
                           action('mail_request','CMSG_MAIL_RETURN_TO_SENDER',body)])
    assert 'error' in rows[-1]

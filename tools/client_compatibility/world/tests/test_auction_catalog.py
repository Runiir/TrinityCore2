"""Pinned modern auction reads preserve native catalogs and opening authority."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_auction_packets import GUID,UNIT,IDENTITY


def action(fn,name,body):return {'fn':fn,'name':name,'body':body.hex()}
OPEN=action('auction_response','MSG_AUCTION_HELLO',struct.pack('<QIB',GUID,2,1))


def calls(codec,rows):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
        units=[UNIT],gameobjects=[],actions=rows)


def request(owned=False,ids=(),tainted=False):
    w=Writer().raw(IDENTITY).pack('I',0).bits(tainted,1)
    if not owned:w.bits(len(ids),7)
    w.bits(2,2).flush()
    for id_ in ids:w.pack('I',id_)
    for sort in [1,0]:w.pack('B',sort).bits(0,1).flush()
    return w.finish()


@pytest.mark.parametrize('owned',[False,True])
def test_catalog_request_requires_native_opening_and_preserves_native_fields(codec,owned):
    name='CMSG_AUCTION_LIST_OWNED_ITEMS' if owned else 'CMSG_AUCTION_LIST_BIDDED_ITEMS'
    native='CMSG_AUCTION_LIST_OWNER_ITEMS' if owned else 'CMSG_AUCTION_LIST_BIDDER_ITEMS'
    body=request(owned,ids=[] if owned else [9,10])
    expected=struct.pack('<QI',GUID,0)+(b'' if owned else struct.pack('<III',2,9,10))
    replies=calls(codec,[action('auction_request',name,body),OPEN,action('auction_request',name,body),
        action('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),action('auction_request',name,body)])
    assert 'error' in replies[0];assert replies[2]==[native,expected.hex()];assert 'error' in replies[4]


def test_live_initial_bids_request_uses_the_captured_sort_bit_alignment(codec):
    guid=0xf130220f0000763a;unit={**UNIT,'guid':guid}
    replies=result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,units=[unit],gameobjects=[],actions=[
        action('auction_response','MSG_AUCTION_HELLO',bytes.fromhex('3a7600000f2230f10200000001')),
        action('auction_request','CMSG_AUCTION_LIST_BIDDED_ITEMS',bytes.fromhex('03a73a76c08308042000000000008001000000'))])
    assert replies[1]==['CMSG_AUCTION_LIST_BIDDER_ITEMS',struct.pack('<QII',guid,0,0).hex()]


@pytest.mark.parametrize('owned',[False,True])
def test_empty_native_catalogs_grant_only_attributable_current_results(codec,owned):
    native='SMSG_AUCTION_OWNER_LIST_RESULT' if owned else 'SMSG_AUCTION_BIDDER_LIST_RESULT'
    modern='SMSG_AUCTION_LIST_OWNED_ITEMS_RESULT' if owned else 'SMSG_AUCTION_LIST_BIDDED_ITEMS_RESULT'
    body=struct.pack('<III',0,0,0 if owned else 300);a=action('auction_response',native,body)
    replies=calls(codec,[a,OPEN,a,action('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),a,OPEN,
        action('logout_complete','SMSG_LOGOUT_COMPLETE',b''),a])
    assert replies[0] is None and replies[4] is None and replies[-1] is None
    assert replies[2]==[modern,(struct.pack('<III',0,0,0) if owned else struct.pack('<II',0,300)).hex()+'00']


def native_row(id_=9,entry=39,owner=1,bidder=2,bid=123,enchant=True):
    w=Writer().pack('II',id_,entry)
    for slot in range(10):w.pack('III',3456 if enchant and slot==4 else 0,500 if enchant and slot==4 else 0,2 if enchant and slot==4 else 0)
    return w.pack('iIIiIQQQQiQQ',-7,12345,5,-1,0,owner,100,6,456,7200000,bidder,bid).finish()


def test_full_native_row_retains_money_owner_instance_enchants_and_442_extra_field(codec):
    row=native_row();assert len(row)==200
    body=struct.pack('<I',1)+row+struct.pack('<II',1,300)
    reply=calls(codec,[OPEN,action('auction_response','SMSG_AUCTION_BIDDER_LIST_RESULT',body)])[1]
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('II')==(1,300);assert r.bits(1)==0;r.align()
    assert r.bits(1)==1 and r.bits(4)==1 and r.bits(2)==0
    assert [r.bits(1) for _ in range(10)]==[1,1,1,0,1,0,0,0,1,1];r.align()
    assert r.unpack('iIi')==(39,12345,-7);assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align()
    assert r.unpack('4i')==(5,-1,0,9);assert r.guid()==(1,0x0800040000000000)
    assert r.unpack('iBI')==(7200000,0,0) # Extra uint32 exists from Classic 4.4.2.
    assert r.unpack('3IB')==(3456,500,2,4);assert r.unpack('3Q')==(100,6,456)
    assert r.guid()==(2,0x0800040000000000);assert r.unpack('Q')==(123,);r.end()


def test_invalid_counts_rows_truncation_and_trailing_bytes_are_rejected(codec):
    valid=struct.pack('<I',1)+native_row()+struct.pack('<II',1,300)
    for body in [valid[:-1],valid+b'x',struct.pack('<III',4097,0,0),
                 struct.pack('<I',1)+native_row(id_=0)+struct.pack('<II',1,300),
                 struct.pack('<I',2)+native_row()+native_row(entry=40)+struct.pack('<II',2,300),
                 struct.pack('<I',1)+native_row()+struct.pack('<II',0,300)]:
        assert 'error' in calls(codec,[OPEN,action('auction_response','SMSG_AUCTION_BIDDER_LIST_RESULT',body)])[1]
    for body in [request()[:-1],request()+b'x',request(tainted=True),request(ids=[0]),request(ids=[9,9])]:
        assert 'error' in calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_LIST_BIDDED_ITEMS',body)])[1]


def test_native_requested_current_bid_overlap_keeps_one_complete_auction(codec):
    body=struct.pack('<I',2)+native_row()+native_row()+struct.pack('<II',2,300)
    reply=calls(codec,[OPEN,action('auction_response','SMSG_AUCTION_BIDDER_LIST_RESULT',body)])[1]
    single=calls(codec,[OPEN,action('auction_response','SMSG_AUCTION_BIDDER_LIST_RESULT',
        struct.pack('<I',1)+native_row()+struct.pack('<II',1,300))])[1]
    assert reply==single

"""Captured sale search and independent 60895 item-result wire checks."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_auction_packets import GUID,UNIT,IDENTITY
from tools.client_compatibility.world.tests.test_auction_catalog import OPEN,action
from tools.client_compatibility.world.tests.test_auction_browse import ITEMS,calls,row,response

CAPTURE=bytes.fromhex('03a73d8cc0830804202700000000000000000000004004000300')


def request(bucket=False,id_=39,offset=0,level=1,sorts=((4,False),(3,False)),suffix=0,pet=0):
    w=Writer().raw(IDENTITY)
    if bucket:
        w.pack('IB',offset,0).bits(0,1).bits(len(sorts),2).flush()
        w.bits(id_,20).bits(bool(pet),1).bits(level,11).bits(bool(suffix),1).flush()
        if pet:w.pack('H',pet)
        if suffix:w.pack('H',suffix)
    else:w.pack('3I',id_,suffix,offset).bits(0,1).bits(len(sorts),2).flush()
    for kind,reverse in sorts:w.pack('B',kind).bits(reverse,1).flush()
    return w.finish()


def query(body=None,bucket=False):
    return action('auction_request','CMSG_AUCTION_LIST_ITEMS_BY_BUCKET_KEY' if bucket else 'CMSG_AUCTION_LIST_ITEMS_BY_ITEM_ID',
                  request(bucket) if body is None else body)


def read_key(r):
    id_=r.bits(20);assert r.bits(1)==0;level=r.bits(11);assert r.bits(1)==0;r.align()
    return id_,level


def read_result(reply):
    assert reply[0]=='SMSG_AUCTION_LIST_ITEMS_RESULT'
    r=Reader(bytes.fromhex(reply[1]));count,unknown,delay=r.unpack('3I');assert unknown==0;rows=[]
    for _ in range(count):
        assert r.bits(1)==1;enchants=r.bits(4);assert r.bits(2)==0;minimum=r.bits(1);increment=r.bits(1)
        buyout=r.bits(1);assert r.bits(1)==0;assert r.bits(1)==1;assert r.bits(1)==0
        assert r.bits(1)==1;assert r.bits(1)==0;bidder=r.bits(1);bid=r.bits(1);r.align()
        entry,seed,property_=r.unpack('iIi');assert property_==0;assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align()
        quantity,charges,flags,auction=r.unpack('4i');owner=r.guid();duration,delete,extra=r.unpack('iBI');assert (delete,extra)==(0,0)
        for __ in range(enchants):r.unpack('3IB')
        min_bid=r.unpack('Q')[0] if minimum else 0;min_increment=r.unpack('Q')[0] if increment else 0
        buy=r.unpack('Q')[0] if buyout else 0
        if bidder:r.guid()
        current=r.unpack('Q')[0] if bid else 0
        assert read_key(r)[0]==entry
        rows.append((auction,entry,quantity,buy,min_bid,current))
    assert r.bits(2)==2;more=r.bits(1);r.align();key=read_key(r);total=r.unpack('I')[0];r.end()
    return delay,more,key,total,rows


def test_captured_sale_query_routes_to_native_and_returns_complete_empty_item_results(codec):
    guid=0xf130220f00008c3d
    replies=result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,units=[{**UNIT,'guid':guid}],gameobjects=[],auction_items=ITEMS,
        actions=[action('auction_response','MSG_AUCTION_HELLO',struct.pack('<QIB',guid,2,1)),query(CAPTURE),response()])
    expected=struct.pack('<QI',guid,0)+b"Recruit's Pants\0"+struct.pack('<BB4IBBBB',0,0,*([0xffffffff]*4),0,0,0,0)
    assert replies[1]==['CMSG_AUCTION_LIST_ITEMS',expected.hex()]
    assert read_result(replies[2])==(300,0,(39,0),0,[])


@pytest.mark.parametrize('bucket',[False,True])
def test_native_pages_are_completed_then_filtered_sorted_and_keyed(codec,bucket):
    replies=calls(codec,[OPEN,query(bucket=bucket),response([row(id_=9,buyout=600)],total=3),
        response([row(id_=10,buyout=400),row(id_=11,entry=40)],total=3)])
    assert replies[2][0]=='CMSG_AUCTION_LIST_ITEMS';assert replies[3] is None
    delay,more,key,total,rows=read_result(replies[4]);assert (delay,more,key,total)==(300,0,(39,1 if bucket else 0),2)
    assert [r[0] for r in rows]==[10,9] and [r[3] for r in rows]==[400,600]


def test_bucket_level_filters_native_base_level_and_offset_applies_after_filtering(codec):
    assert read_result(calls(codec,[OPEN,query(request(True,level=2),True),response([row()])])[-1])[3]==0
    rows=[row(id_=9,buyout=600),row(id_=10,buyout=400)]
    assert [r[0] for r in read_result(calls(codec,[OPEN,query(request(offset=1)),response(rows)])[-1])[-1]]==[9]


def test_search_requires_opening_and_does_not_override_pending_catalogs(codec):
    replies=calls(codec,[query(),OPEN,query(),query(),action('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),response(),query()])
    assert 'error' in replies[0] and replies[3] is None and replies[-2] is None and 'error' in replies[-1]


@pytest.mark.parametrize('body,bucket',[(request(suffix=1),False),(request(True,pet=1),True),
    (request(sorts=((5,False),)),False)])
def test_valid_unsupported_suffix_pet_and_time_filters_are_not_mistranslated(codec,body,bucket):
    assert calls(codec,[OPEN,query(body,bucket)])[-1] is None


def test_whole_native_stack_does_not_pretend_to_be_a_modern_partial_commodity(codec):
    items={'39':{**ITEMS['39'],'stackable':20}}
    assert calls(codec,[OPEN,query()],items=items)[-1] is None


def test_large_filtered_item_results_preserve_real_has_more_and_total(codec):
    rows=[row(id_=i,buyout=i) for i in range(1,502)]
    reply=calls(codec,[OPEN,query(),response(rows)])[-1]
    delay,more,key,total,shown=read_result(reply)
    assert (delay,more,key,total,len(shown))==(300,1,(39,0),501,50)
    assert shown[0][0]==1 and shown[-1][0]==50


@pytest.mark.parametrize('bucket',[False,True])
def test_malformed_request_prefixes_and_trailing_data_reject(codec,bucket):
    body=request(bucket)
    for malformed in [body[:n] for n in range(len(body))]+[body+b'x',request(bucket,id_=0)]:
        assert 'error' in calls(codec,[OPEN,query(malformed,bucket)])[-1]


def test_random_native_property_cannot_be_silently_used_as_modern_suffix(codec):
    body=bytearray(row());struct.pack_into('<i',body,128,-7)
    assert 'error' in calls(codec,[OPEN,query(),response([body])])[-1]


def test_owned_populated_rows_append_native_base_bucket_key(codec):
    body=struct.pack('<I',1)+row()+struct.pack('<II',1,0)
    reply=calls(codec,[OPEN,action('auction_response','SMSG_AUCTION_OWNER_LIST_RESULT',body)])[-1]
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('3I')==(1,0,0);assert r.bits(1)==0;r.align()
    encoded=bytes.fromhex(reply[1])[13:]
    # Independent item parser also checks the HasBucketKey bit and terminal key.
    search=Writer().pack('3I',1,0,0).raw(encoded).bits(2,2).bits(0,1).flush().bits(39,20).bits(0,1).bits(1,11).bits(0,1).flush().pack('I',1).finish()
    assert read_result(['SMSG_AUCTION_LIST_ITEMS_RESULT',search.hex()])[4][0][1]==39


def test_bid_sort_uses_native_current_bid_and_price_sort_falls_back_to_minimum(codec):
    a=bytearray(row(id_=9,buyout=0));b=bytearray(row(id_=10,buyout=0))
    struct.pack_into('<Q',a,156,900);struct.pack_into('<Q',b,156,100)
    # Both have no current bid, so Bid ties use deterministic newest ID.
    for sorts,expected in [(((3,False),),[10,9]),(((0,True),),[9,10])]:
        result_=read_result(calls(codec,[OPEN,query(request(sorts=sorts)),response([a,b])])[-1])
        assert [r[0] for r in result_[-1]]==expected

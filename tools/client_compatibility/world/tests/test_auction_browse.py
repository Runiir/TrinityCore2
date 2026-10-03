"""Native browse authority, complete pagination and 60895 bucket contents."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_auction_packets import GUID,UNIT,IDENTITY
from tools.client_compatibility.world.tests.test_auction_catalog import OPEN,action,native_row

CAPTURE=bytes.fromhex('03a78f86c0830804200000000000000000c00f00000000000001ffffffff0a0874633434326d697373696e67653131353434393000000100')
ITEMS={'39':{'name':"Recruit's Pants",'level':1,'required_level':0,'quality':1,'stackable':1,'class':4,'subclass':0,'inventory_type':7},
       '40':{'name':"Recruit's Boots",'level':5,'required_level':2,'quality':1,'stackable':1,'class':4,'subclass':0,'inventory_type':8}}


def request(offset=0,filters=4032,minimum=0,maximum=0,classes=(),sorts=((0,False),(1,False))):
    w=Writer().raw(IDENTITY).pack('IBBBBIIBI',offset,minimum,maximum,0,0,filters,0,1,0xffffffff)
    w.bits(0,1).bits(0,8).bits(len(classes),3).bits(len(sorts),2).flush()
    for class_,subs in classes:
        w.pack('i',class_).bits(len(subs),5).flush()
        for mask,subclass in subs:w.pack('Qi',mask,subclass)
    for type_,reverse in sorts:w.pack('B',type_).bits(reverse,1).flush()
    return w.finish()


def row(id_=9,entry=39,count=1,owner=1,buyout=450):
    body=bytearray(native_row(id_=id_,entry=entry,owner=owner,bidder=0,bid=0,enchant=False))
    struct.pack_into('<i',body,128,0);struct.pack_into('<I',body,136,count);struct.pack_into('<Q',body,172,buyout)
    return bytes(body)


def response(rows=(),total=None,delay=300):
    return action('auction_response','SMSG_AUCTION_LIST_RESULT',struct.pack('<I',len(rows))+b''.join(rows)+
        struct.pack('<II',len(rows) if total is None else total,delay))


def calls(codec,actions,items=ITEMS):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'kind':4,'fields':{}},
        units=[UNIT],gameobjects=[],auction_items=items,actions=actions)


def read_buckets(reply):
    assert reply[0]=='SMSG_AUCTION_LIST_BUCKETS_RESULT';r=Reader(bytes.fromhex(reply[1]));count,delay,a,b=r.unpack('4I')
    assert (a,b)==(0,0);assert r.bits(1)==0;more=bool(r.bits(1));r.align();rows=[]
    for _ in range(count):
        id_=r.bits(20);assert r.bits(1)==0;level=r.bits(11);assert r.bits(1)==0;r.align()
        quantity,required,price,appearances=r.unpack('iiQI');assert appearances==0;assert r.bits(4)==0
        own=bool(r.bits(1));assert r.bits(1)==0;r.align();rows.append((id_,level,quantity,required,price,own))
    r.end();return delay,more,rows


def test_captured_default_query_is_backed_by_native_search(codec):
    guid=0xf130220f0000868f
    replies=result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,units=[{**UNIT,'guid':guid}],gameobjects=[],actions=[
        action('auction_response','MSG_AUCTION_HELLO',struct.pack('<QIB',guid,2,1)),
        action('auction_request','CMSG_AUCTION_BROWSE_QUERY',CAPTURE),response()])
    expected=struct.pack('<QI',guid,0)+b'tc442missinge1154490\0'+struct.pack('<BB4IBBBB',0,0,*([0xffffffff]*4),0,0,0,0)
    assert replies[1]==['CMSG_AUCTION_LIST_ITEMS',expected.hex()]
    assert read_buckets(replies[2])==(300,False,[])


def test_browse_requires_current_native_open_and_close_clears_pending_results(codec):
    query=action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request())
    replies=calls(codec,[query,OPEN,query,action('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),response(),query])
    assert 'error' in replies[0] and 'error' in replies[-1];assert replies[-2] is None
    assert replies[2][0]=='CMSG_AUCTION_LIST_ITEMS'


def test_all_native_pages_are_collected_before_grouping_prices_and_quantities(codec):
    replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request()),
        response([row()],total=3),response([row(id_=10,owner=2,buyout=400),row(id_=11,entry=40,buyout=500)],total=3)])
    assert replies[2][0]=='CMSG_AUCTION_LIST_ITEMS' # Callback requests the next native page.
    r=Reader(bytes.fromhex(replies[2][1]));assert r.unpack('QI')==(GUID,1)
    assert replies[3] is None
    assert read_buckets(replies[4])==(300,False,[(39,1,2,0,400,True),(40,5,1,2,500,True)])


def test_filters_use_native_item_metadata_and_bucket_offset_follows_filtering(codec):
    query=request(offset=1,classes=((4,((1<<7,0),)),),sorts=((0,True),))
    replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',query),
        response([row(),row(id_=10,entry=40)])])
    assert read_buckets(replies[2])==(300,False,[]) # Only pants match; offset is a bucket offset.
    replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request(minimum=1,maximum=2)),
        response([row(),row(id_=10,entry=40)])])
    assert read_buckets(replies[2])[2]==[(40,5,1,2,450,True)]


def test_sort_reverse_and_quality_none_preserve_modern_semantics(codec):
    for filters,expected in [(4032,[40,39]),(0,[])]:
        replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request(filters=filters,sorts=((2,True),))),
            response([row(),row(id_=10,entry=40)])])
        assert [b[0] for b in read_buckets(replies[2])[2]]==expected


def test_stackable_native_whole_stack_prices_are_not_silently_rounded(codec):
    items={**ITEMS,'39':{**ITEMS['39'],'stackable':20}}
    for price in [450,451]:
        replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request()),response([row(count=5,buyout=price)])],items)
        if price==450:assert read_buckets(replies[2])[2][0][4]==90
        else:assert 'error' in replies[2]


def test_inflight_search_is_not_replaced_by_an_unattributable_legacy_response(codec):
    query=action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request())
    replies=calls(codec,[OPEN,query,query,response(),response()])
    assert replies[2] is None and replies[-1] is None;assert read_buckets(replies[3])[2]==[]


@pytest.mark.parametrize('case',['duplicate','changed','no_progress','missing_metadata','trailing'])
def test_native_catalog_failures_do_not_become_fake_complete_empty_lists(codec,case):
    actions=[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request())];items=ITEMS
    if case=='duplicate':actions += [response([row()],2),response([row()],2)]
    if case=='changed':actions += [response([row()],2),response([row(id_=10)],3)]
    if case=='no_progress':actions += [response([],1)]
    if case=='missing_metadata':actions += [response([row()])];items={}
    if case=='trailing':
        malformed=response();malformed['body']+='00';actions.append(malformed)
    assert 'error' in calls(codec,actions,items)[-1]


def test_unsupported_valid_filters_do_not_disconnect_or_forward_native_queries(codec):
    replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',request(filters=4032|2)),response()])
    assert replies[1:] == [None,None]


def test_malformed_requests_do_not_grant_a_native_browse(codec):
    valid=request()
    for body in [valid[:-1],valid+b'x',request(classes=((-1,()),)),request(classes=((4,((1,-1),)),))]:
        replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_BROWSE_QUERY',body),response()])
        assert 'error' in replies[1];assert replies[2] is None


def test_native_sparse_metadata_uses_actual_133_column_name_and_level_offsets(codec):
    row=[0]*133;row[0]=39;row[1]=1;row[9]=7;row[12]=5;row[13]=2;row[22]=1;row[99]=1
    strings=b"\0Recruit's Pants\0";head=struct.pack('<4s11I',b'WDB2',1,133,532,len(strings),0,15595,0,0,0,1,0)
    body=head+struct.pack('<133I',*row)+strings
    meta=result(codec,op='auction_sparse',body=body.hex())['39']
    assert meta=={'name':"Recruit's Pants",'level':5,'required_level':2,'quality':1,'stackable':1,'inventory_type':7}
    for malformed in [body[:-1],body+b'x',body[:48]+struct.pack('<133I',*{**dict(enumerate(row)),99:999}.values())+strings]:
        assert 'error' in codec(op='auction_sparse',body=malformed.hex())

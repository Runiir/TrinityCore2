"""Owned reads and native page chains decoded against the pinned 60895 layout."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Writer,Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result,action
from tools.client_compatibility.world.tests.test_item_use_packets import fixture,ITEM,ITEM_HIGH
from tools.client_compatibility.world.objects import INDEX


def run(codec,actions,**kw):
    return result(codec,op='stateful',actions=actions,**fixture(**kw))


def query(page=18,low=50,high=ITEM_HIGH):
    return action('item_text_request','CMSG_QUERY_PAGE_TEXT',Writer().pack('I',page).guid(low,high).finish())


def page(id=18,text='Dear Noble Sir,\n',next=0):
    return action('item_text_response','SMSG_PAGE_TEXT_QUERY_RESPONSE',
                  struct.pack('<I',id)+text.encode()+b'\0'+struct.pack('<I',next))


def read_result(name='SMSG_READ_ITEM_OK',guid=ITEM):
    return action('item_text_response',name,struct.pack('<Q',guid))


def decoded(packet):
    assert packet[0]=='SMSG_QUERY_PAGE_TEXT_RESPONSE'
    r=Reader(bytes.fromhex(packet[1]));root,=r.unpack('I');assert r.bits(1)==1
    n,=r.unpack('I');out=[]
    for _ in range(n):
        id,next,condition,flags=r.unpack('IIiB');length=r.bits(12)
        assert (condition,flags)==(0,0)
        out.append((id,next,r.raw(length).decode()))
    r.end();return root,out


def test_owned_book_read_translates_position_and_correlated_success(codec):
    assert run(codec,[action('item_text_request','CMSG_READ_ITEM',bytes([255,25])),read_result()])==[
        ['CMSG_READ_ITEM','ff19'],['SMSG_READ_ITEM_RESULT_OK',Writer().guid(50,ITEM_HIGH).finish().hex()]]
    assert run(codec,[action('item_text_request','CMSG_READ_ITEM',bytes([30,2])),read_result()],bag=19,slot=2)[0]==[
        'CMSG_READ_ITEM','1302']
    assert run(codec,[read_result(),read_result('SMSG_READ_ITEM_FAILED')])==[None,None]


@pytest.mark.parametrize('body,kw',[(b'\xff\x19',{'owner':2}),(b'\xff\x18',{}),(b'\xff\x3b',{}),
    (bytes([87,2]),{}),(bytes([30,17]),{'bag':19,'slot':2}),(b'\xff',{}),(b'\xff\x19x',{})])
def test_reads_reject_unowned_empty_banked_and_malformed_slots(codec,body,kw):
    assert 'error' in run(codec,[action('item_text_request','CMSG_READ_ITEM',body)],**kw)[0]


def test_two_native_pages_emit_one_complete_modern_chain_with_utf8_lengths(codec):
    first='Dear Noble Sir,\n';second='Warm regards, Stalvan. é'
    out=run(codec,[query(),page(18,first,19),page(19,second)])
    assert out[:2]==[['CMSG_PAGE_TEXT_QUERY',struct.pack('<IQ',18,ITEM).hex()],None]
    assert decoded(out[2])==(18,[(18,19,first),(19,0,second)])


def test_queued_duplicate_and_overlapping_public_cache_reads_stay_ordered(codec):
    out=run(codec,[query(),query(),query(19,0,0),page(18,'A',19),page(19,'B'),
        page(18,'A2',19),page(19,'B2'),page(19,'B3'),page(19,'unsolicited')])
    assert out[2]==['CMSG_PAGE_TEXT_QUERY',struct.pack('<IQ',19,0).hex()]
    assert out[3] is None and out[5] is None and out[8] is None
    assert [decoded(out[i]) for i in (4,6,7)]==[(18,[(18,19,'A'),(19,0,'B')]),
        (18,[(18,19,'A2'),(19,0,'B2')]),(19,[(19,0,'B3')])]


@pytest.mark.parametrize('request',[query(0),query(0x80000001),query(low=51),query(high=ITEM_HIGH^(1<<42)),
    query(low=0,high=ITEM_HIGH),query(low=0x100000000),
    action('item_text_request','CMSG_QUERY_PAGE_TEXT',b'\x12'),
    {**query(),'body':query()['body']+'00'}])
def test_page_queries_reject_bad_ids_guids_and_bodies(codec,request):
    assert 'error' in run(codec,[request])[0]


@pytest.mark.parametrize('reply',[page(19),page(18,'x'*4096),page(18,next=18),page(18,next=0x80000001),
    action('item_text_response','SMSG_PAGE_TEXT_QUERY_RESPONSE',b'\x12'),
    {**page(),'body':page()['body']+'00'}])
def test_page_replies_reject_malformed_out_of_order_and_oversized_chains(codec,reply):
    assert 'error' in run(codec,[query(),reply])[1]


def test_cycle_clears_pending_chains_and_no_partial_chain_escapes(codec):
    out=run(codec,[query(),page(18,'A',19),page(19,'B',18),page(18)])
    assert out[1] is None and 'error' in out[2] and out[3] is None
    out=run(codec,[query(1),*[page(i,'A',i+1) for i in range(1,65)],page(65)])
    assert all(x is None for x in out[1:65]) and 'error' in out[65]


def test_queue_bound_failure_and_logout_do_not_leak_authority(codec):
    assert 'error' in run(codec,[*[query(i) for i in range(1,18)]])[-1]
    request=action('item_text_request','CMSG_READ_ITEM',bytes([255,25]))
    out=run(codec,[request,read_result('SMSG_READ_ITEM_FAILED'),read_result(),query(),
        action('logout_complete','SMSG_LOGOUT_COMPLETE',b''),page(),read_result(),query(),request])
    assert out[1:3]==[None,None] and out[4:7]==[None,None,None]
    assert all('error' in x for x in out[7:])
    # Separate codec state starts with neither pending pages nor read permission.
    assert run(codec,[page(),read_result()])==[None,None]


def test_wrong_native_item_does_not_consume_the_owned_read(codec):
    out=run(codec,[action('item_text_request','CMSG_READ_ITEM',b'\xff\x19'),read_result(guid=ITEM+1),read_result()])
    assert out[1] is None and out[2][0]=='SMSG_READ_ITEM_RESULT_OK'

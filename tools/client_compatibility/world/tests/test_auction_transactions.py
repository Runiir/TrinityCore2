"""Captured ordinary sale input and native-authoritative auction outcomes."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_auction_packets import GUID,UNIT,IDENTITY
from tools.client_compatibility.world.tests.test_auction_catalog import OPEN,action,native_row
from tools.client_compatibility.world.tests.test_auction_browse import ITEMS

ITEM=(0x4000<<48)|4
HIGH=(3<<58)|(1<<42)
CAPTURE=bytes.fromhex('03a75ca6c08308042000000000000000001027000000000000a00500000201a004040c01000000')


def owned(owner=1,count=1):
    return {'guid':ITEM,'kind':1,'fields':{str(INDEX[k]):v for k,v in
        [('ITEM_FIELD_OWNER',owner),('ITEM_FIELD_STACK_COUNT',count),('OBJECT_FIELD_ENTRY',39)]}}


def calls(codec,actions,item=None,unit=UNIT,items=ITEMS):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,units=[unit],gameobjects=[],
        inventory_items=[owned() if item is None else item],auction_items=items,actions=actions)


def sale(bid=0,buyout=10000,duration=1440,amount=1,taint=False,low=4,high=HIGH):
    return Writer().raw(IDENTITY).pack('qqi',bid,buyout,duration).bits(taint,1).bits(1,6).flush().guid(low,high).pack('I',amount).finish()


def test_captured_buyout_only_sale_routes_one_owned_native_item(codec):
    guid=0xf130220f0000a65c
    replies=calls(codec,[action('auction_response','MSG_AUCTION_HELLO',struct.pack('<QIB',guid,2,1)),
        action('auction_request','CMSG_AUCTION_SELL_ITEM',CAPTURE)],unit={**UNIT,'guid':guid})
    assert replies[1]==['CMSG_AUCTION_SELL_ITEM',struct.pack('<QIQIQQI',guid,1,ITEM,1,10000,10000,1440).hex()]


@pytest.mark.parametrize('bid,buyout',[(5000,10000),(5000,0),(0,10000)])
def test_bid_and_buyout_fields_remain_native_gameplay_prices(codec,bid,buyout):
    reply=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_SELL_ITEM',sale(bid,buyout))])[-1]
    assert reply==['CMSG_AUCTION_SELL_ITEM',struct.pack('<QIQIQQI',GUID,1,ITEM,1,bid or buyout,buyout,1440).hex()]


def test_sale_needs_native_opening_and_current_owned_item(codec):
    request=action('auction_request','CMSG_AUCTION_SELL_ITEM',sale())
    assert 'error' in calls(codec,[request])[0]
    assert 'error' in calls(codec,[OPEN,request],item=owned(owner=2))[-1]
    assert 'error' in calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_SELL_ITEM',sale(low=5))])[-1]
    assert 'error' in calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_SELL_ITEM',sale(high=0))])[-1]


@pytest.mark.parametrize('body',[sale(bid=-1),sale(buyout=-1),sale(buyout=0),sale(duration=1)])
def test_invalid_sale_metadata_rejects_without_native_mutation(codec,body):
    assert 'error' in calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_SELL_ITEM',body)])[-1]


def test_unsupported_commodity_quantity_and_taint_do_not_become_plain_item_sales(codec):
    for body,item,items in [(sale(amount=2),owned(),ITEMS),(sale(),owned(count=2),ITEMS),
        (sale(),owned(),{'39':{**ITEMS['39'],'stackable':20}}),(sale(taint=True),owned(),ITEMS)]:
        assert calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_SELL_ITEM',body)],item=item,items=items)[-1] is None


def cancel(id_=9,entry=39):return Writer().raw(IDENTITY).pack('2I',id_,entry).bits(0,1).finish()
def bid(id_=9,amount=10000):return Writer().raw(IDENTITY).pack('IQ',id_,amount).bits(0,1).finish()


def test_cancel_and_bid_preserve_native_auction_identity_and_amount(codec):
    replies=calls(codec,[OPEN,action('auction_request','CMSG_AUCTION_REMOVE_ITEM',cancel()),
        action('auction_request','CMSG_AUCTION_PLACE_BID',bid())])
    assert replies[1:]==[['CMSG_AUCTION_REMOVE_ITEM',struct.pack('<QI',GUID,9).hex()],
        ['CMSG_AUCTION_PLACE_BID',struct.pack('<QIQ',GUID,9,10000).hex()]]


@pytest.mark.parametrize('name,body',[('CMSG_AUCTION_SELL_ITEM',sale()),('CMSG_AUCTION_REMOVE_ITEM',cancel()),
    ('CMSG_AUCTION_PLACE_BID',bid())])
def test_transaction_truncations_trailing_and_closed_authority_reject(codec,name,body):
    for bad in [body[:i] for i in range(len(body))]+[body+b'x']:
        assert 'error' in calls(codec,[OPEN,action('auction_request',name,bad)])[-1]
    assert 'error' in calls(codec,[OPEN,action('bank_close','CMSG_CLOSE_INTERACTION',IDENTITY),
        action('auction_request',name,body)])[-1]


@pytest.mark.parametrize('command,error,extra,expected',[(0,0,b'',(0,0,0,0)),(1,0,b'',(0,0,0,0)),
    (2,0,struct.pack('<Q',500),(0,0,500,0)),(0,1,struct.pack('<I',36),(37,0,0,0)),
    (2,5,struct.pack('<3Q',2,10000,500),(0,2,500,10000)),(2,10,b'',(0,0,0,0))])
def test_native_outcomes_keep_real_errors_bidders_and_money(codec,command,error,extra,expected):
    body=struct.pack('<3I',9,command,error)+extra
    reply=calls(codec,[action('auction_response','SMSG_AUCTION_COMMAND_RESULT',body)])[0]
    assert reply[0]=='SMSG_AUCTION_COMMAND_RESULT';r=Reader(bytes.fromhex(reply[1]));bag,bidder,increment,money=expected
    assert r.unpack('4I')==(9,command,error,bag);assert r.guid()==(bidder,(2<<58)|(1<<42) if bidder else 0)
    assert r.unpack('2QI')==(increment,money,0);r.end()
    for bad in [body[:-1],body+b'x']:
        assert 'error' in calls(codec,[action('auction_response','SMSG_AUCTION_COMMAND_RESULT',bad)])[0]


def test_buyout_only_native_row_has_no_fake_bid_price(codec):
    row=bytearray(native_row(enchant=False,bidder=0,bid=0));struct.pack_into('<Q',row,156,456)
    body=struct.pack('<I',1)+row+struct.pack('<II',1,0)
    reply=calls(codec,[OPEN,action('auction_response','SMSG_AUCTION_OWNER_LIST_RESULT',body)])[-1]
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('3I')==(1,0,0);r.bits(1);r.align()
    r.bits(1);r.bits(4);r.bits(2);assert r.bits(1)==0 and r.bits(1)==0 and r.bits(1)==1

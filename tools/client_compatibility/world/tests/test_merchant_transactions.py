"""Vendor transactions preserve native identity, money and private buyback arrays."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT,call
from tools.client_compatibility.world.tests.test_inventory_packets import native_item,mask,read_block,ITEM_HIGH,NATIVE_ITEM
from tools.client_compatibility.world.tests.test_interaction_packets import HIGH


def request(codec,body,name='CMSG_SELL_ITEM',owner=1,include=True):
    fields={INDEX['OBJECT_FIELD_ENTRY']:39,INDEX['ITEM_FIELD_OWNER']:owner,
        INDEX['ITEM_FIELD_STACK_COUNT']:1}
    actions=[]
    if include:actions.append({'fn':'object_updates','name':'SMSG_UPDATE_OBJECT','body':native_item(fields,True).hex()})
    actions.append({'fn':'merchant_request','name':name,'body':body.hex()})
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'map':0,'fields':{}},
        gameobjects=[],units=[UNIT],actions=actions)[-1]


def sell(amount=0,low=10,high=ITEM_HIGH):
    return Writer().guid(*modern_guid(GUID,0)).guid(low,high).pack('I',amount).finish()


def test_sell_preserves_native_owned_item_and_whole_or_partial_amount(codec):
    for amount in [0,1,0xffffffff]:
        assert request(codec,sell(amount))==['CMSG_SELL_ITEM',struct.pack('<QQI',GUID,NATIVE_ITEM,amount).hex()]


def test_sell_rejects_unknown_item_owner_and_all_incomplete_requests(codec):
    for low,high in [(0,0),(11,ITEM_HIGH),(10,HIGH),(2**32,ITEM_HIGH)]:
        assert 'error' in request(codec,sell(low=low,high=high))
    assert 'error' in request(codec,sell(),owner=2)
    assert 'error' in request(codec,sell(),include=False)
    body=sell()
    for n in range(len(body)):assert 'error' in request(codec,body[:n])
    assert 'error' in request(codec,body+b'x')


def test_buyback_maps_only_the_twelve_modern_slots(codec):
    for slot in range(94,106):
        body=Writer().guid(*modern_guid(GUID,0)).pack('I',slot).finish()
        assert request(codec,body,'CMSG_BUY_BACK_ITEM',include=False)==['CMSG_BUYBACK_ITEM',struct.pack('<QI',GUID,slot-20).hex()]
    for slot in [0,74,93,106,255,0xffffffff]:
        body=Writer().guid(*modern_guid(GUID,0)).pack('I',slot).finish()
        assert 'error' in request(codec,body,'CMSG_BUY_BACK_ITEM',include=False)
    body=Writer().guid(*modern_guid(GUID,0)).pack('I',94).finish()
    for n in range(len(body)):assert 'error' in request(codec,body[:n],'CMSG_BUY_BACK_ITEM',include=False)
    assert 'error' in request(codec,body+b'x','CMSG_BUY_BACK_ITEM',include=False)


def test_requests_require_visible_native_vendor_flags(codec):
    body=Writer().guid(*modern_guid(GUID,0)).finish()
    for kind,flags in [(3,1),(4,641)]:
        unit={**UNIT,'kind':kind,'fields':{str(INDEX['UNIT_NPC_FLAGS']):flags}}
        assert 'error' in call(codec,body,[unit],fn='merchant_request',name='CMSG_LIST_INVENTORY')


def test_sell_errors_keep_semantic_result_and_guid_list(codec):
    for reason in range(1,8):
        name,body=call(codec,struct.pack('<QQB',GUID,NATIVE_ITEM,reason),fn='merchant_response',name='SMSG_SELL_ITEM')
        assert name=='SMSG_SELL_RESPONSE';r=Reader(bytes.fromhex(body))
        assert r.guid()==modern_guid(GUID,0);assert r.unpack('Ii')==(1,reason)
        assert r.guid()==(10,ITEM_HIGH);r.end()
    name,body=call(codec,struct.pack('<QQB',0,0,3),fn='merchant_response',name='SMSG_SELL_ITEM')
    r=Reader(bytes.fromhex(body));assert r.guid()==(0,0);assert r.unpack('Ii')==(0,3);r.end()


def test_sell_error_bounds_and_unknown_visible_vendor(codec):
    body=struct.pack('<QQB',GUID,NATIVE_ITEM,2)
    for n in range(len(body)):assert 'error' in call(codec,body[:n],fn='merchant_response',name='SMSG_SELL_ITEM')
    for suffix in [b'x']:
        assert 'error' in call(codec,body+suffix,fn='merchant_response',name='SMSG_SELL_ITEM')
    for reason in [0,8,255]:
        assert 'error' in call(codec,struct.pack('<QQB',GUID,NATIVE_ITEM,reason),fn='merchant_response',name='SMSG_SELL_ITEM')
    assert call(codec,body,[],fn='merchant_response',name='SMSG_SELL_ITEM') is None


def test_coinage_delta_combines_both_halves_without_public_leak(codec):
    start=INDEX['PLAYER_FIELD_COINAGE'];fields={start:0xfffffffe,start+1:0x12345678}
    for half in [start,start+1]:
        value=result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed={half:fields[half]})
        r=read_block(value,(1,HIGH),1<<7);assert mask(r,46,True)=={0,31};r.align()
        assert r.unpack('Q')==(0x12345678fffffffe,);r.end()
        assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':fields},changed={half:fields[half]},visibility=0)==''


def test_buyback_sparse_price_timestamp_and_slot_order(codec):
    price=INDEX['PLAYER_FIELD_BUYBACK_PRICE_1'];stamp=INDEX['PLAYER_FIELD_BUYBACK_TIMESTAMP_1']
    slot=INDEX['PLAYER_FIELD_INV_SLOT_HEAD']+74*2
    values={slot:NATIVE_ITEM&0xffffffff,slot+1:NATIVE_ITEM>>32,price:1,stamp:108025,
        price+11:0xffffffff,stamp+11:0xffffffff}
    value=result(codec,op='inventory_update',snapshot={'guid':1,'fields':values},changed=values)
    r=read_block(value,(1,HIGH),1<<7)
    assert mask(r,46,True)=={131,226,320,321,332,333,344};r.align()
    assert r.guid()==(10,ITEM_HIGH);assert r.unpack('IqIq')==(1,108025,0xffffffff,0xffffffff);r.end()
    assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':values},changed=values,visibility=0)==''
    # Clearing only timestamps or prices must not emit the companion value.
    value=result(codec,op='inventory_update',snapshot={'guid':1,'fields':{stamp:0}},changed={stamp:0})
    r=read_block(value,(1,HIGH),1<<7);assert mask(r,46,True)=={320,333};r.align();assert r.unpack('q')==(0,);r.end()


def test_create_buyback_prices_and_timestamps_use_the_native_values(codec):
    fields={INDEX['PLAYER_FIELD_BUYBACK_PRICE_1']:1,INDEX['PLAYER_FIELD_BUYBACK_TIMESTAMP_1']:108025,
        INDEX['PLAYER_FIELD_BUYBACK_TIMESTAMP_1']+11:0xffffffff}
    values=result(codec,op='object_values',snapshot={'guid':1,'fields':fields},character={'guid':1,'name':'Harnessone','gender':0})
    assert values['ActivePlayerData']['BuybackPrice']==[1]+[0]*11
    assert values['ActivePlayerData']['BuybackTimestamp']==[108025]+[0]*10+[0xffffffff]

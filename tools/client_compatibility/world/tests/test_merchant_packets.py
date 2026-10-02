"""Legacy vendor mask decoding, modern catalogs and native visible-NPC authority."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

GUID=(0xf13<<52)|(1285<<32)|42
UNIT={'guid':GUID,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):641}}
ITEM={'muid':1,'id':159,'type':1,'price':18,'quantity':-1,'stack':5,'ext':0,'cond':0}


def native(items=None,reason=0):
    items=[ITEM] if items is None else items;octets=GUID.to_bytes(8,'little')
    w=Writer().bits(bool(octets[1]),1).bits(bool(octets[0]),1).bits(len(items),21)
    for i in [3,6,5,2,7]:w.bits(bool(octets[i]),1)
    for item in items:w.bits(not item['ext'],1).bits(not item['cond'],1)
    w.bits(bool(octets[4]),1).flush()
    for item in items:
        w.pack('2i',item['muid'],7)
        if item['ext']:w.pack('i',item['ext'])
        w.pack('iiII',item['id'],item['type'],item['price'],5)
        if item['cond']:w.pack('i',item['cond'])
        w.pack('iI',item['quantity'],item['stack'])
    for i in [5,4,1,0,6]:
        if octets[i]:w.pack('B',octets[i]^1)
    w.pack('B',reason)
    for i in [2,3,7]:
        if octets[i]:w.pack('B',octets[i]^1)
    return w.finish()


def call(codec,body,units=None,fn='merchant_response',name='SMSG_VENDOR_INVENTORY'):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,gameobjects=[],
        units=[UNIT] if units is None else units,actions=[{'fn':fn,'name':name,'body':body.hex()}])[0]


def decoded(reply):
    assert reply[0]=='SMSG_VENDOR_INVENTORY';r=Reader(bytes.fromhex(reply[1]))
    assert r.guid()==modern_guid(GUID,0);reason,count=r.unpack('iI');items=[]
    for _ in range(count):
        price,muid,type_,stack,quantity,ext,cond=r.unpack('QI5i')
        assert r.bits(3)==0;r.align();id_,seed,property_=r.unpack('3i')
        assert (seed,property_)==(0,0);assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align()
        items.append(dict(price=price,muid=muid,type=type_,stack=stack,quantity=quantity,ext=ext,cond=cond,id=id_))
    r.end();return reason,items


def test_vendor_inventory_preserves_native_catalog_and_empty_reason(codec):
    assert decoded(call(codec,native()))==(0,[ITEM])
    assert decoded(call(codec,native([],reason=2)))==(2,[])


def test_extended_currency_and_condition_payloads_do_not_shift_fields(codec):
    items=[{**ITEM,'price':0xffffffff,'quantity':7,'ext':234,'cond':567},
        {**ITEM,'muid':2,'id':384,'type':2,'price':0,'quantity':0,'ext':19}]
    assert decoded(call(codec,native(items)))==(0,items)


def test_vendor_response_requires_current_native_visible_vendor(codec):
    assert call(codec,native(),[]) is None
    for kind,flags in [(4,641),(3,1)]:
        unit={**UNIT,'kind':kind,'fields':{str(INDEX['UNIT_NPC_FLAGS']):flags}}
        assert call(codec,native(),[unit]) is None


def test_direct_list_request_preserves_guid_without_discovery_authority(codec):
    body=Writer().guid(*modern_guid(GUID,0)).finish()
    assert call(codec,body,fn='merchant_request',name='CMSG_LIST_INVENTORY')==['CMSG_LIST_INVENTORY',struct.pack('<Q',GUID).hex()]
    assert 'error' in call(codec,body,[],fn='merchant_request',name='CMSG_LIST_INVENTORY')
    assert 'error' in call(codec,body+b'x',fn='merchant_request',name='CMSG_LIST_INVENTORY')


def test_vendor_body_bounds_and_all_truncated_prefixes(codec):
    body=native([{**ITEM,'ext':234,'cond':567}])
    for n in range(len(body)):assert 'error' in call(codec,body[:n])
    assert 'error' in call(codec,body+b'x')
    excessive=Writer().bits(0,2).bits(256,21).finish()
    assert 'error' in call(codec,excessive)


def test_invalid_native_items_are_rejected(codec):
    for key,value in [('id',0),('muid',0),('type',3),('stack',0),('quantity',-2),('ext',-1),('cond',-1)]:
        assert 'error' in call(codec,native([{**ITEM,key:value}]))

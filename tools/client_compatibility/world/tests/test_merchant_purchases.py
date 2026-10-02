"""Native purchase routing and response layouts for visible owned vendor sessions."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT,call
from tools.client_compatibility.world.tests.test_inventory_packets import native_item,ITEM_HIGH,NATIVE_ITEM
from tools.client_compatibility.world.tests.test_interaction_packets import HIGH


def buy(container=(0,0),quantity=5,muid=1,slot=255,type_=1,item=159,seed=0,property_=0,bonus=0,mods=0):
    return Writer().guid(*modern_guid(GUID,0)).guid(*container).pack('IIBi3i',quantity,muid,slot,type_,item,seed,property_).bits(bonus,1).flush().bits(mods,6).flush().finish()


def request(codec,body,container=None):
    actions=[]
    if container:actions.append({'fn':'object_updates','name':'SMSG_UPDATE_OBJECT','body':container.hex()})
    actions.append({'fn':'merchant_request','name':'CMSG_BUY_ITEM','body':body.hex()})
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'map':0,'fields':{}},
        gameobjects=[],units=[UNIT],actions=actions)[-1]


def test_purchase_preserves_native_bundle_units_and_auto_placement(codec):
    expected=struct.pack('<QBIIIQB',GUID,1,159,1,5,0,255).hex()
    assert request(codec,buy())==['CMSG_BUY_ITEM',expected]
    expected=struct.pack('<QBIIIQB',GUID,2,384,3,7,0,255).hex()
    assert request(codec,buy(quantity=7,muid=3,type_=2,item=384))==['CMSG_BUY_ITEM',expected]


def test_purchase_explicit_backpack_placement_uses_native_position(codec):
    body=buy(container=(1,HIGH),slot=50)
    assert request(codec,body)==['CMSG_BUY_ITEM',struct.pack('<QBIIIQB',GUID,1,159,1,5,1,38).hex()]
    body=buy(container=(1,HIGH))
    assert request(codec,body)==['CMSG_BUY_ITEM',struct.pack('<QBIIIQB',GUID,1,159,1,5,1,255).hex()]
    for slot in [19,29,34,51,58,106]:assert 'error' in request(codec,buy(container=(1,HIGH),slot=slot))


def bag(owner=1):
    # Container create type and native movement prefix follow the inventory fixture.
    fields={INDEX['OBJECT_FIELD_ENTRY']:21841,INDEX['ITEM_FIELD_OWNER']:owner,INDEX['CONTAINER_FIELD_NUM_SLOTS']:16}
    body=native_item(fields,True)
    return body[:10]+bytes([2])+body[11:]


def test_purchase_owned_container_checks_kind_owner_and_slot(codec):
    body=buy(container=(10,ITEM_HIGH),slot=15)
    assert request(codec,body,bag())==['CMSG_BUY_ITEM',struct.pack('<QBIIIQB',GUID,1,159,1,5,NATIVE_ITEM,15).hex()]
    assert 'error' in request(codec,body)
    assert 'error' in request(codec,body,native_item({INDEX['ITEM_FIELD_OWNER']:1},True))
    assert 'error' in request(codec,body,bag(owner=2))
    assert 'error' in request(codec,buy(container=(10,ITEM_HIGH),slot=36),bag())
    assert 'error' in request(codec,buy(container=(2,HIGH)))
    assert 'error' in request(codec,buy(slot=0))


def test_purchase_rejects_unsupported_item_instances_and_incomplete_payloads(codec):
    for changes in [dict(quantity=0),dict(muid=0),dict(type_=3),dict(item=0),dict(seed=1),dict(property_=-1),dict(bonus=1),dict(mods=1)]:
        assert 'error' in request(codec,buy(**changes))
    body=buy()
    for n in range(len(body)):assert 'error' in request(codec,body[:n])
    assert 'error' in request(codec,body+b'x')


def test_purchase_success_preserves_native_count_and_stock(codec):
    for available in [-1,0,7]:
        reply=call(codec,struct.pack('<QIiI',GUID,1,available,5),fn='merchant_response',name='SMSG_BUY_ITEM')
        assert reply[0]=='SMSG_BUY_SUCCEEDED';r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(GUID,0)
        assert r.unpack('IiI')==(1,available,5);r.end()


def test_purchase_failure_preserves_native_item_id_and_semantic_enum(codec):
    for reason in [0,1,2,4,5,7,8,11,12]:
        reply=call(codec,struct.pack('<QIB',GUID,159,reason),fn='merchant_response',name='SMSG_BUY_FAILED')
        r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(GUID,0);assert r.unpack('Ii')==(159,reason);r.end()
    reply=call(codec,struct.pack('<QIB',0,0,0),fn='merchant_response',name='SMSG_BUY_FAILED')
    r=Reader(bytes.fromhex(reply[1]));assert r.guid()==(0,0);assert r.unpack('Ii')==(0,0);r.end()


def test_native_purchase_response_bounds_and_visibility(codec):
    for name,body in [('SMSG_BUY_ITEM',struct.pack('<QIiI',GUID,1,-1,5)),('SMSG_BUY_FAILED',struct.pack('<QIB',GUID,159,2))]:
        for n in range(len(body)):assert 'error' in call(codec,body[:n],fn='merchant_response',name=name)
        assert 'error' in call(codec,body+b'x',fn='merchant_response',name=name)
        assert call(codec,body,[],fn='merchant_response',name=name) is None
    for muid,available,quantity in [(0,-1,5),(1,-2,5),(1,-1,0)]:
        assert 'error' in call(codec,struct.pack('<QIiI',GUID,muid,available,quantity),fn='merchant_response',name='SMSG_BUY_ITEM')
    assert 'error' in call(codec,struct.pack('<QIB',GUID,159,255),fn='merchant_response',name='SMSG_BUY_FAILED')

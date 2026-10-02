"""Native acquisition notifications retain quantity, visibility and slot meaning."""
import struct
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_interaction_packets import HIGH


def native(player=1,pushed=1,created=0,chat=1,bag=255,slot=25,id=159,seed=0,property_=0,quantity=5,total=5):
    return struct.pack('<QIIIBIIIiII',player,pushed,created,chat,bag,slot,id,seed,property_,quantity,total)


def call(codec,body,name='SMSG_ITEM_PUSH_RESULT'):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        gameobjects=[],units=[],actions=[{'fn':'item_notification','name':name,'body':body.hex()}])[0]


def decode(reply):
    assert reply[0]=='SMSG_ITEM_PUSH_RESULT'
    r=Reader(bytes.fromhex(reply[1]));player=r.guid();bag=r.unpack('B')[0]
    fields=r.unpack('7iBi');item_guid=r.guid()
    flags=(r.bits(1),r.bits(1),r.bits(1),r.bits(3),r.bits(1),r.bits(1));r.align()
    item=r.unpack('3i');assert r.bits(1)==0;r.align();assert r.bits(6)==0;r.align();r.end()
    return player,bag,fields,item_guid,flags,item


def test_real_native_vendor_push_preserves_stock_chat_contract(codec):
    body=bytes.fromhex('0100000000000000010000000000000001000000ff190000009f00000000000000000000000500000005000000')
    assert decode(call(codec,body))==((1,HIGH),255,(37,0,5,5,0,0,0,0,0),(0,0),(1,0,0,1,0,0),(159,0,0))


def test_notification_root_and_container_positions_preserve_stacking_sentinel(codec):
    for old,modern in [(0,0),(18,18),(19,30),(22,33),(23,35),(38,50),(39,59),(73,93),(85,105),(0xffffffff,-1)]:
        assert decode(call(codec,native(slot=old)))[1:3]==(255,(modern,0,5,5,0,0,0,0,0))
    for bag,modern in [(19,30),(22,33),(67,87),(73,93)]:
        for slot in [0,35,0xffffffff]:
            assert decode(call(codec,native(bag=bag,slot=slot)))[1:3]==(modern,(slot if slot!=0xffffffff else -1,0,5,5,0,0,0,0,0))


def test_notification_group_broadcast_and_creation_visibility_flags(codec):
    for pushed,created,chat in [(0,0,1),(1,1,1),(1,0,0)]:
        decoded=decode(call(codec,native(player=2,pushed=pushed,created=created,chat=chat,quantity=3,total=12,seed=0xffffffff,property_=-7)))
        assert decoded[0]==(2,HIGH)
        assert decoded[2][2:4]==(3,12)
        assert decoded[3]==(0,0)  # Native wire supplies no GUID, including stack additions.
        assert decoded[4]==(pushed,created,0,chat,0,0)
        assert decoded[5]==(159,-1,-7)


def test_notification_bounds_reject_unrepresentable_values_and_trailing_bytes(codec):
    body=native()
    for changes in [dict(player=0),dict(player=2**32),dict(pushed=2),dict(created=2),dict(chat=2),
        dict(id=0),dict(id=2**31),dict(quantity=0),dict(quantity=2**31),dict(total=2**31),dict(total=4),
        dict(slot=86),dict(bag=18),dict(bag=23),dict(bag=74),dict(bag=19,slot=36)]:
        assert 'error' in call(codec,native(**changes))
    for n in range(len(body)):assert 'error' in call(codec,body[:n])
    assert 'error' in call(codec,body+b'x')
    assert call(codec,body,'SMSG_UNRELATED') is None

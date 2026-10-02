import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_interaction_packets import call,HIGH

ITEM_HIGH=(3<<58)|(1<<42)
NATIVE_ITEM=(0x4000<<48)|10


def hint(*positions):
    w=Writer().bits(len(positions),2).flush()
    for bag,slot in positions:w.pack('2B',bag,slot)
    return w


def test_backpack_swap_uses_native_16_slot_storage_and_two_ui_hints(codec):
    packet=hint((255,35),(255,50)).pack('2B',50,35).finish()
    assert call(codec,'inventory_request','CMSG_SWAP_INV_ITEM',packet)==['CMSG_SWAP_INV_ITEM','2617']
    for slot in [19,29,34,51,58,106,255]:
        assert 'error' in call(codec,'inventory_request','CMSG_SWAP_INV_ITEM',hint().pack('2B',slot,35).finish())
    assert 'error' in call(codec,'inventory_request','CMSG_SWAP_INV_ITEM',packet+b'x')


def test_cross_bag_swap_auto_equip_and_auto_store_orders(codec):
    packet=hint().pack('4B',30,255,2,35).finish()
    assert call(codec,'inventory_request','CMSG_SWAP_ITEM',packet)==['CMSG_SWAP_ITEM','1302ff17']
    packet=hint().pack('2B',255,35).finish()
    assert call(codec,'inventory_request','CMSG_AUTO_EQUIP_ITEM',packet)==['CMSG_AUTOEQUIP_ITEM','ff17']
    packet=hint().pack('3B',31,255,35).finish()
    assert call(codec,'inventory_request','CMSG_AUTO_STORE_BAG_ITEM',packet)==['CMSG_AUTOSTORE_BAG_ITEM','ff1714']
    assert 'error' in call(codec,'inventory_request','CMSG_SWAP_ITEM',hint().pack('4B',30,255,36,35).finish())


def test_split_quantity_and_native_source_destination_mapping(codec):
    packet=hint().pack('4Bi',255,35,30,2,3).finish()
    assert call(codec,'inventory_request','CMSG_SPLIT_ITEM',packet)==['CMSG_SPLIT_ITEM',struct.pack('<4BI',255,23,19,2,3).hex()]
    for amount in [0,-1]:
        assert 'error' in call(codec,'inventory_request','CMSG_SPLIT_ITEM',hint().pack('4Bi',255,35,30,2,amount).finish())
    # A client cannot auto-equip a fabricated item GUID merely by describing it.
    packet=hint().guid(10,ITEM_HIGH).pack('B',0).finish()
    assert 'error' in call(codec,'inventory_request','CMSG_AUTO_EQUIP_ITEM_SLOT',packet)


def test_inventory_failure_maps_semantic_enum_and_preserves_item(codec):
    packet=struct.pack('<BQQB',36,NATIVE_ITEM,0,0) # Native ITEM_LOCKED=36, modern=37.
    name,body=call(codec,'inventory_response','SMSG_INVENTORY_CHANGE_FAILURE',packet)
    assert name=='SMSG_INVENTORY_CHANGE_FAILURE'
    r=Reader(bytes.fromhex(body));assert r.unpack('i')==(37,);assert r.guid()==(10,ITEM_HIGH)
    assert r.guid()==(0,0);assert r.unpack('B')==(0,);r.end()
    assert 'error' in call(codec,'inventory_response','SMSG_INVENTORY_CHANGE_FAILURE',packet[:-1])


def read_block(value,guid,roots):
    r=Reader(bytes.fromhex(value));assert r.unpack('B')==(0,);assert r.guid()==guid
    assert r.unpack('I')[0]==len(r.data)-r.pos
    assert r.unpack('BBBI')==(1,0,3,roots)
    return r


def mask(r,width,first32=False):
    present=r.unpack('I')[0]|r.bits(width-32)<<32 if first32 else r.bits(width)
    parts={i:r.bits(32) for i in range(width) if present&(1<<i)}
    return {i*32+b for i,part in parts.items() for b in range(32) if part&(1<<b)}


def test_backpack_sparse_slot_delta_and_equipment_visual_are_separate_roots(codec):
    start=INDEX['PLAYER_FIELD_INV_SLOT_HEAD'];visible=INDEX['PLAYER_VISIBLE_ITEM_1_ENTRYID']
    values={start:0,start+1:0,start+38*2:NATIVE_ITEM&0xffffffff,start+38*2+1:NATIVE_ITEM>>32,visible:0}
    body=result(codec,op='inventory_update',snapshot={'guid':1,'fields':values},changed=values)
    r=read_block(body,(1,HIGH),(1<<6)|(1<<7))
    assert mask(r,5)=={68,69};assert r.bits(1)==0;r.align()
    assert r.bits(4)==3;assert r.unpack('i')==(0,)
    assert mask(r,46,True)=={131,132,182};r.align()
    assert r.guid()==(0,0);assert r.guid()==(10,ITEM_HIGH);r.end()
    assert result(codec,op='inventory_update',snapshot={'guid':1,'fields':values},changed={})==''


def test_stack_and_container_updates_preserve_guids_and_array_mask(codec):
    values={INDEX['ITEM_FIELD_STACK_COUNT']:3,INDEX['ITEM_FIELD_CONTAINED']:1,
        INDEX['CONTAINER_FIELD_SLOT_1']+35*2:NATIVE_ITEM&0xffffffff,
        INDEX['CONTAINER_FIELD_SLOT_1']+35*2+1:NATIVE_ITEM>>32}
    body=result(codec,op='item_update',snapshot={'guid':NATIVE_ITEM,'kind':2,'fields':values},changed=values)
    r=read_block(body,(10,ITEM_HIGH),(1<<1)|(1<<2))
    assert mask(r,2)=={0,4,7};r.align();assert r.guid()==(1,HIGH);assert r.unpack('I')==(3,)
    assert mask(r,2)=={2,38};r.align();assert r.guid()==(10,ITEM_HIGH);r.end()


def test_item_signed_charge_and_enchant_nested_masks(codec):
    values={INDEX['ITEM_FIELD_SPELL_CHARGES']:0xffffffff,
        INDEX['ITEM_FIELD_ENCHANTMENT_1_1']+12*3+2:0xffff}
    body=result(codec,op='item_update',snapshot={'guid':NATIVE_ITEM,'kind':1,'fields':values},changed=values)
    r=read_block(body,(10,ITEM_HIGH),1<<1)
    assert mask(r,2)=={23,24,29,42};r.align();assert r.unpack('i')==(-1,)
    assert r.bits(5)==9;assert r.unpack('h')==(-1,);r.end()

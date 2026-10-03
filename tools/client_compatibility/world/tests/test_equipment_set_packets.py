"""Independent 4.4.2 WPP reader contracts and authoritative 4.3.4 set requests."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

ITEM_HIGH=(3<<58)|(1<<42)
NATIVE_ITEM=(0x4000<<48)|10


def packed(value):
    body=value.to_bytes(8,'little');return bytes([sum(1<<i for i,v in enumerate(body) if v)])+bytes(v for v in body if v)


def native_list():
    return struct.pack('<I',1)+packed(9)+struct.pack('<I',0)+b'Fixture\0' + b'134400\0'+packed(NATIVE_ITEM)+packed(1)+packed(0)*17


def modern_save(guid=0,index=0,kind=0,foreign=False,assigned=False):
    w=Writer().pack('iQII',kind,guid,index,2)
    w.guid(11 if foreign else 10,ITEM_HIGH).pack('i',0)
    for _ in range(18):w.guid().pack('i',0)
    w.pack('6i',0,0,0,0,0,0).bits(assigned,1).bits(7,8).bits(6,9).flush()
    if assigned:w.pack('i',0)
    return w.raw(b'Fixture134400').finish()


def execute(codec,actions,items=True):
    return result(codec,op='stateful',character={'guid':1},snapshot=None,gameobjects=[],units=[],
        inventory_items=[{'guid':NATIVE_ITEM}] if items else [],
        actions=[{'fn':fn,'name':name,'body':body.hex()} for fn,name,body in actions])


def test_native_list_has_modern_type_guid_mask_and_per_row_bit_boundary(codec):
    name,body=execute(codec,[('equipment_response','SMSG_EQUIPMENT_SET_LIST',native_list())])[0]
    assert name=='SMSG_LOAD_EQUIPMENT_SET'
    r=Reader(bytes.fromhex(body));assert r.unpack('I')==(1,)
    assert r.unpack('iQII')==(0,9,0,2)
    for i in range(19):
        assert r.guid()==((10,ITEM_HIGH) if i==0 else (0,0));assert r.unpack('i')==(0,)
    assert r.unpack('6i')==(0,0,0,0,0,0)
    assert r.bits(1)==0;assert r.bits(8)==7;assert r.bits(9)==6;r.align()
    assert r.raw(7)==b'Fixture';assert r.raw(6)==b'134400';r.end()


def test_stock_save_acknowledgement_and_owned_delete_use_native_set_identity(codec):
    actions=[('equipment_request','CMSG_SAVE_EQUIPMENT_SET',modern_save()),
        ('equipment_response','SMSG_EQUIPMENT_SET_SAVED',struct.pack('<I',0)+packed(9)),
        ('equipment_request','CMSG_SAVE_EQUIPMENT_SET',modern_save(guid=9)),
        ('equipment_request','CMSG_DELETE_EQUIPMENT_SET',struct.pack('<Q',9))]
    replies=execute(codec,actions)
    expected=packed(0)+struct.pack('<I',0)+b'Fixture\0'+b'134400\0'+packed(NATIVE_ITEM)+packed(1)+packed(0)*17
    assert replies[0]==['CMSG_EQUIPMENT_SET_SAVE',expected.hex()]
    assert replies[1]==['SMSG_EQUIPMENT_SET_ID',struct.pack('<iIQ',0,0,9).hex()]
    assert replies[2]==['CMSG_EQUIPMENT_SET_SAVE',(packed(9)+expected[1:]).hex()]
    assert replies[3]==['CMSG_EQUIPMENT_SET_DELETE',packed(9).hex()]


def test_save_rejects_foreign_items_later_services_invalid_index_and_tail(codec):
    for body in [modern_save(foreign=True),modern_save(kind=1),modern_save(index=10),
            modern_save(assigned=True),modern_save()+b'x',modern_save()[:-1],modern_save(guid=9)]:
        reply=execute(codec,[('equipment_request','CMSG_SAVE_EQUIPMENT_SET',body)])[0]
        assert 'error' in reply
    assert 'error' in execute(codec,[('equipment_request','CMSG_SAVE_EQUIPMENT_SET',modern_save())],items=False)[0]
    assert 'error' in execute(codec,[('equipment_request','CMSG_DELETE_EQUIPMENT_SET',struct.pack('<Q',9))])[0]


def modern_use():
    w=Writer().bits(0,2).flush().guid(10,ITEM_HIGH).pack('2B',255,0)
    w.guid(1,0).pack('2B',0,0)
    for _ in range(17):w.guid().pack('2B',0,0)
    return w.pack('Q',9).finish()


def test_use_remaps_inventory_sources_and_attributes_native_result_to_set(codec):
    actions=[('equipment_response','SMSG_EQUIPMENT_SET_LIST',native_list()),
        ('equipment_request','CMSG_USE_EQUIPMENT_SET',modern_use()),
        ('equipment_response','SMSG_EQUIPMENT_SET_USE_RESULT',b'\0')]
    replies=execute(codec,actions)
    expected=packed(NATIVE_ITEM)+bytes([255,0])+packed(1)+bytes(2)+(packed(0)+bytes(2))*17
    assert replies[1]==['CMSG_EQUIPMENT_SET_USE',expected.hex()]
    assert replies[2]==['SMSG_USE_EQUIPMENT_SET_RESULT',struct.pack('<iQ',0,9).hex()]
    assert 'error' in execute(codec,[('equipment_request','CMSG_USE_EQUIPMENT_SET',modern_use())])[0]
    assert 'error' in execute(codec,[('equipment_response','SMSG_EQUIPMENT_SET_USE_RESULT',b'\0')])[0]


def test_native_empty_list_and_invalid_count_or_tail(codec):
    assert execute(codec,[('equipment_response','SMSG_EQUIPMENT_SET_LIST',bytes(4))])[0]==['SMSG_LOAD_EQUIPMENT_SET','00000000']
    for body in [struct.pack('<I',11),native_list()+b'x',native_list()[:-1]]:
        assert 'error' in execute(codec,[('equipment_response','SMSG_EQUIPMENT_SET_LIST',body)])[0]

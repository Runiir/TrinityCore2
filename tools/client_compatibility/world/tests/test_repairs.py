"""Repair-all and item repair retain native authority and owned identities."""
import struct
from tools.client_compatibility.world.buffer import Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT
from tools.client_compatibility.world.tests.test_inventory_packets import native_item,ITEM_HIGH,NATIVE_ITEM
from tools.client_compatibility.world.tests.test_interaction_packets import HIGH

REPAIR={**UNIT,'fields':{str(INDEX['UNIT_NPC_FLAGS']):4225}}


def body(item=(0,0),guild=0):
    return Writer().guid(*modern_guid(GUID,0)).guid(*item).bits(guild,1).flush().finish()


def call(codec,request,units=None,owner=1,include=False):
    actions=[]
    if include:actions.append({'fn':'object_updates','name':'SMSG_UPDATE_OBJECT',
        'body':native_item({INDEX['ITEM_FIELD_OWNER']:owner},True).hex()})
    actions.append({'fn':'repair_request','name':'CMSG_REPAIR_ITEM','body':request.hex()})
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        gameobjects=[],units=[REPAIR] if units is None else units,actions=actions)[-1]


def test_repair_all_preserves_guild_choice_without_fabricating_item(codec):
    for guild in [0,1]:
        assert call(codec,body(guild=guild))==['CMSG_REPAIR_ITEM',struct.pack('<QQB',GUID,0,guild).hex()]


def test_item_repair_requires_owned_native_identity(codec):
    request=body((10,ITEM_HIGH))
    assert call(codec,request,include=True)==['CMSG_REPAIR_ITEM',struct.pack('<QQB',GUID,NATIVE_ITEM,0).hex()]
    assert 'error' in call(codec,request)
    assert 'error' in call(codec,request,owner=2,include=True)
    for item in [(0,ITEM_HIGH),(10,HIGH),(2**32,ITEM_HIGH),(11,ITEM_HIGH)]:
        assert 'error' in call(codec,body(item),include=True)


def test_repair_requires_visible_service_and_complete_pinned_layout(codec):
    request=body()
    assert 'error' in call(codec,request,units=[])
    assert 'error' in call(codec,request,units=[UNIT])
    assert 'error' in call(codec,request,units=[{**REPAIR,'kind':4}])
    for n in range(len(request)):assert 'error' in call(codec,request[:n])
    assert 'error' in call(codec,request+b'x')

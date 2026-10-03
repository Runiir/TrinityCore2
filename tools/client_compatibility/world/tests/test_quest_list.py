"""Captured Guard Thomas offer list decoded independently from the 4.4.2 layout."""
import struct
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

BODY=bytes.fromhex('77160000050130f14772656574696e67732c20246e2e000000000000000000023400000002000000'
    '0a000000080000000050726f74656374207468652046726f6e74696572000a670000020000000a0000000800040000'
    '4865726f27732043616c6c3a205765737466616c6c2100')
GUID=int.from_bytes(BODY[:8],'little')
UNIT={'guid':GUID,'kind':3,'map':0,'fields':{str(INDEX['UNIT_NPC_FLAGS']):2}}


def call(codec,body=BODY,units=None):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot=None,gameobjects=[],
        units=[UNIT] if units is None else units,actions=[{'fn':'quest_response',
            'name':'SMSG_QUEST_GIVER_QUEST_LIST_MESSAGE','body':body.hex()}])[0]


def test_captured_quest_list_preserves_eligible_quests_and_greeting(codec):
    reply=call(codec);assert reply[0]=='SMSG_QUEST_GIVER_QUEST_LIST_MESSAGE'
    r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(GUID,0)
    assert r.unpack('3I')==(0,0,2);length=r.bits(11);r.align();quests=[]
    for _ in range(2):
        fields=r.unpack('3I2i4I');repeatable=r.bits(1);assert r.bits(3)==0
        size=r.bits(9);r.align();title=r.raw(size).decode();quests.append((fields,repeatable,title))
    assert quests==[((52,0,2,10,10,0,8,0,0),0,'Protect the Frontier'),
        ((26378,0,2,10,10,0,0x40008,0,0),0,"Hero's Call: Westfall!")]
    assert r.raw(length)==b'Greetings, $n.';r.end()


def test_quest_list_validates_all_prefixes_and_visible_service(codec):
    for n in range(len(BODY)):assert 'error' in call(codec,BODY[:n])
    assert 'error' in call(codec,BODY+b'x')
    for units in [[],[{**UNIT,'kind':4}],[{**UNIT,'fields':{str(INDEX['UNIT_NPC_FLAGS']):1}}]]:
        assert call(codec,units=units) is None


def test_quest_list_rejects_duplicate_quests_unknown_bool_and_excessive_count(codec):
    prefix=struct.pack('<Q',GUID)+b'\0'+struct.pack('<2IB',0,0,2)
    row=struct.pack('<IIiIB',52,2,10,8,0)+b'Title\0'
    assert 'error' in call(codec,prefix+row*2)
    assert 'error' in call(codec,prefix[:-1]+b'\x41')
    assert 'error' in call(codec,prefix[:-1]+b'\x01'+row[:16]+b'\x02'+row[17:])

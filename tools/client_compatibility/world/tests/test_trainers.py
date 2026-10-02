"""Trainer catalog wire order, native prerequisites and greeting boundaries."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result
from tools.client_compatibility.world.tests.test_merchant_packets import GUID,UNIT
from tools.client_compatibility.world.objects import INDEX

TRAINER={**UNIT,'fields':{str(INDEX['UNIT_NPC_FLAGS']):51}}


def call(codec,body,units=None,fn='trainer_response',name='SMSG_TRAINER_LIST'):
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':{}},
        gameobjects=[],units=[TRAINER] if units is None else units,
        actions=[{'fn':fn,'name':name,'body':body.hex()}])[0]


def spell(id=100,usable=1,cost=950,level=20,skill=171,rank=50,abilities=(99,0,-1),dialog=0,button=0):
    return struct.pack('<IBIBII3iII',id,usable,cost,level,skill,rank,*abilities,dialog,button)


def catalog(spells=None,greeting=b'Hello, warrior!',type_=0,id=7,count=None):
    spells=[spell()] if spells is None else spells
    return struct.pack('<QIII',GUID,type_,id,len(spells) if count is None else count)+b''.join(spells)+greeting+b'\0'


def decode(reply):
    assert reply[0]=='SMSG_TRAINER_LIST';r=Reader(bytes.fromhex(reply[1]))
    assert r.guid()==modern_guid(GUID,0);type_,id,count=r.unpack('3I')
    rows=[r.unpack('i3I3iIBB') for _ in range(count)]
    length=r.bits(11);r.align();greeting=r.raw(length);r.end()
    return (type_,id,count),rows,greeting


def test_trainer_hello_uses_visible_service_and_native_guid(codec):
    body=Writer().guid(*modern_guid(GUID,0)).finish()
    assert call(codec,body,fn='trainer_request',name='CMSG_TRAINER_LIST')==['CMSG_TRAINER_LIST',struct.pack('<Q',GUID).hex()]
    for units in [[],[UNIT],[{**TRAINER,'kind':4}]]:assert 'error' in call(codec,body,units,fn='trainer_request',name='CMSG_TRAINER_LIST')
    for n in range(len(body)):assert 'error' in call(codec,body[:n],fn='trainer_request',name='CMSG_TRAINER_LIST')
    assert 'error' in call(codec,body+b'x',fn='trainer_request',name='CMSG_TRAINER_LIST')


def test_trainer_learning_request_preserves_native_identity_and_rejects_foreign_npc(codec):
    body=Writer().guid(*modern_guid(GUID,0)).pack('2i',16,3127).finish()
    assert call(codec,body,fn='trainer_request',name='CMSG_TRAINER_BUY_SPELL')==['CMSG_TRAINER_BUY_SPELL',struct.pack('<QII',GUID,16,3127).hex()]
    for units in [[],[UNIT],[{**TRAINER,'kind':4}]]:
        assert 'error' in call(codec,body,units,fn='trainer_request',name='CMSG_TRAINER_BUY_SPELL')
    for n in range(len(body)):assert 'error' in call(codec,body[:n],fn='trainer_request',name='CMSG_TRAINER_BUY_SPELL')
    for id_,spell_ in [(0,3127),(-1,3127),(16,0),(16,-1)]:
        invalid=Writer().guid(*modern_guid(GUID,0)).pack('2i',id_,spell_).finish()
        assert 'error' in call(codec,invalid,fn='trainer_request',name='CMSG_TRAINER_BUY_SPELL')
    assert 'error' in call(codec,body+b'x',fn='trainer_request',name='CMSG_TRAINER_BUY_SPELL')


def test_trainer_failure_maps_native_skill_rejection_to_modern_unavailable(codec):
    for reason,expected in [(0,0),(1,1),(2,0)]:
        body=struct.pack('<QII',GUID,3127,reason)
        reply=call(codec,body,name='SMSG_TRAINER_BUY_FAILED');r=Reader(bytes.fromhex(reply[1]))
        assert reply[0]=='SMSG_TRAINER_BUY_FAILED';assert r.guid()==modern_guid(GUID,0)
        assert r.unpack('2i')==(3127,expected);r.end()
        assert call(codec,body,[],name='SMSG_TRAINER_BUY_FAILED') is None
    for changes in [(0,0),(2**31,0),(3127,3)]:
        assert 'error' in call(codec,struct.pack('<QII',GUID,*changes),name='SMSG_TRAINER_BUY_FAILED')
    for n in range(16):assert 'error' in call(codec,body[:n],name='SMSG_TRAINER_BUY_FAILED')
    assert 'error' in call(codec,body+b'x',name='SMSG_TRAINER_BUY_FAILED')


def test_legacy_trainer_completion_is_validated_without_inventing_modern_ack(codec):
    body=struct.pack('<QI',GUID,3127)
    assert call(codec,body,fn='trainer_completion',name='SMSG_TRAINER_BUY_SUCCEEDED') is None
    for n in range(len(body)):
        assert 'error' in call(codec,body[:n],fn='trainer_completion',name='SMSG_TRAINER_BUY_SUCCEEDED')
    for bad in [body+b'x',struct.pack('<QI',0,3127),struct.pack('<QI',GUID,0)]:
        assert 'error' in call(codec,bad,fn='trainer_completion',name='SMSG_TRAINER_BUY_SUCCEEDED')


def test_learned_spell_updates_modern_spellbook_with_normal_notifications(codec):
    body=struct.pack('<II',3127,0)
    reply=call(codec,body,fn='initialize',name='SMSG_LEARNED_SPELL')
    assert reply==['SMSG_LEARNED_SPELLS','010000000000000000370c000000']
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('2I')==(1,0)
    assert r.bits(1)==0;r.align();assert r.unpack('i')==(3127,)
    assert r.bits(4)==0;r.align();r.end()
    for n in range(len(body)):assert 'error' in call(codec,body[:n],fn='initialize',name='SMSG_LEARNED_SPELL')
    for bad in [body+b'x',struct.pack('<II',0,0),struct.pack('<II',3127,1),struct.pack('<II',2**31,0)]:
        assert 'error' in call(codec,bad,fn='initialize',name='SMSG_LEARNED_SPELL')


def test_trainer_catalog_preserves_state_cost_requirements_and_order(codec):
    body=catalog(spells=[spell(usable=state,dialog=1,button=1) for state in [0,1,2]],greeting='Bienvenue, guerrier émérite!'.encode())
    header,rows,greeting=decode(call(codec,body))
    assert header==(0,7,3)
    assert rows==[(100,950,171,50,99,0,-1,0,state,20) for state in [0,1,2]]
    assert greeting=='Bienvenue, guerrier émérite!'.encode()


def test_captured_row_variant_preserves_its_tail_without_truncating_greeting(codec):
    row=struct.pack('<IBIBII3iI',100,1,950,20,171,50,99,0,-1,0xffffffff)
    greeting=b'Hello, warrior!'
    body=struct.pack('<QIII',GUID,0,7,1)+row+greeting+b'\0'
    header,rows,text=decode(call(codec,body))
    assert header==(0,7,1);assert rows==[(100,950,171,50,99,0,-1,0xffffffff,1,20)]
    assert text==greeting


def test_trainer_empty_catalog_types_and_greeting_limit(codec):
    for type_ in range(4):assert decode(call(codec,catalog([],b'',type_=type_)))==((type_,7,0),[],b'')
    assert decode(call(codec,catalog([],b'x'*2047)))[2]==b'x'*2047
    for greeting in [b'x'*2048,b'x\0y']:
        assert 'error' in call(codec,catalog([],greeting))


def test_trainer_catalog_requires_native_visible_trainer(codec):
    for units in [[],[UNIT],[{**TRAINER,'kind':4}]]:assert call(codec,catalog(),units) is None


def test_trainer_catalog_rejects_bad_counts_states_and_incomplete_data(codec):
    for changes in [dict(type_=4),dict(id=0),dict(id=2**31),dict(count=4097),dict(count=2)]:
        assert 'error' in call(codec,catalog(**changes))
    for changes in [dict(id=0),dict(id=2**31),dict(usable=3),dict(dialog=2),dict(button=2)]:
        assert 'error' in call(codec,catalog([spell(**changes)]))
    body=catalog()
    # Byte 55 is independently a complete 34-byte row plus empty CString.
    # A correctly framed alternate packet cannot be distinguished from that
    # prefix by its body alone. Every other cut here is incomplete in both forms.
    for n in range(len(body)):
        if n==55:
            assert decode(call(codec,body[:n]))==((0,7,1),[(100,950,171,50,99,0,-1,0,1,20)],b'')
        else:assert 'error' in call(codec,body[:n])
    assert 'error' in call(codec,body+b'x')


def test_actual_running_backend_uses_34_byte_trainer_rows(codec):
    # Owned UI11 catalog, preserved in the DVC evidence with its native identity.
    body=bytes.fromhex(
        '1d190100671530f100000000100000002b00000047000000008602000000000000000000000000000000000000000000'
        '0000000000004e0000000043050000000000000000000000000000000000000000000000000000006400000000390000'
        '00000000000000000000000000000000000000000000000000006301000000fe03000000000000000000000000000000'
        '000000000000000000000000d5010000002eb2010000000000000000000000000000000000000000000000000000a402'
        '000000f726000000000000000000000047000000000000000000000000000000ee02000000aa37000000000000000000'
        '00000000000000000000000000000000000004030000000e010000000000000000000000000000000000000000000000'
        '000000004d03000000ed120000000000000000000000000000000000000000000000000000006703000000ee4d000000'
        '0000000000000000470000000000000000000000000000006e04000000a15e0000000000000000000000000000000000'
        '0000000000000000000088040000007f5300000000000000000000000000000000000000000000000000000089040000'
        '005d48000000000000000000000000000000000000000000000000000000b8050000005d480000000000000000000000'
        '000000000000000000000000000000009006000000882c00000000000000000000009a09000000000000000000000000'
        '0000b3060000004416000000000000000000000000000000000000000000000000000000b7060000001e590100000000'
        '0000000000009a0900000000000000000000000000009a09000000d51b00000000000000000000000000000000000000'
        '0000000000000000050a000000d51b000000000000000000000047000000000000000000000000000000370c00000186'
        '02000000000000000000000000000000000000000000000000000000530d000000a42c02000000000000000000000000'
        '00000000000000000000000000007e140000003b3d000000000000000000000000000000000000000000000000000000'
        'bc14000000a507000000000000000000000000000000000000000000000000000000c7180000000c0200000000000000'
        '000000000000000000000000000000000000000090190000007c16040000000000000000000000000000000000000000'
        '00000000000098190000001932000000000000000000000000000000000000000000000000000000ac19000000aa3700'
        '0000000000000000000047000000000000000000000000000000111a0000005c0d000000000000000000000000000000'
        '000000000000000000000000d81c000000960f000000000000000000000000000000000000000000000000000000da1c'
        '000000550a00000000000000000000000000000000000000000000000000000086310000003264000000000000000000'
        '000000000000000000000000000000000000434800000010590000000000000000000000000000000000000000000000'
        '00000000064f000000962c0100000000000000000000000000000000000000000000000000001c4f0000007f53000000'
        '00000000000000009a090000000000000000000000000000705d000000a6850100000000000000000000000000000000'
        '000000000000000000007c8600000086000000000000000000000000000000000000000000000000000000008ed90000'
        '003cb20200000000000000000000000000000000000000000000000000009be10000005c0d0000000000000000000000'
        '000000000000000000000000000000007efb000000706f02000000000000000000000000000000000000000000000000'
        '00004a510100005c64030000000000000000000000000000000000000000000000000000cc55010000d4370300000000'
        '00000000000000000000000000000000000000000000d5550100017f5300000000000000000000000000000000000000'
        '0000000000000000b67c0100006cbd03000000000000000000000000000000000000000000000000000048656c6c6f2c'
        '2077617272696f72212020526561647920666f7220736f6d6520747261696e696e673f00'
    )
    native=int.from_bytes(body[:8],"little");unit={**TRAINER,"guid":native}
    reply=call(codec,body,[unit]);r=Reader(bytes.fromhex(reply[1]))
    assert r.guid()==modern_guid(native,0);assert r.unpack("3I")== (0,16,43)
    rows=[r.unpack("i3I3iIBB") for _ in range(43)]
    assert rows[0]==(71,646,0,0,0,0,0,0,0,0)
    assert rows[5]==(676,9975,0,0,71,0,0,0,0,0)
    assert {row[8] for row in rows}=={0,1}
    length=r.bits(11);r.align();assert r.raw(length)==b"Hello, warrior!  Ready for some training?";r.end()

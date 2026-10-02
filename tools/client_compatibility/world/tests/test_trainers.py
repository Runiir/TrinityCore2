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


def test_trainer_catalog_preserves_state_cost_requirements_and_order(codec):
    body=catalog(spells=[spell(usable=state,dialog=1,button=1) for state in [0,1,2]],greeting='Bienvenue, guerrier émérite!'.encode())
    header,rows,greeting=decode(call(codec,body))
    assert header==(0,7,3)
    assert rows==[(100,950,171,50,99,0,-1,0,state,20) for state in [0,1,2]]
    assert greeting=='Bienvenue, guerrier émérite!'.encode()


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
    for n in range(len(body)):assert 'error' in call(codec,body[:n])
    assert 'error' in call(codec,body+b'x')

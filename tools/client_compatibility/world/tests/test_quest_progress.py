"""Captured ordinary Prowler kill notification and modern credit widths."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.gameobjects import modern_guid
from tools.client_compatibility.world.objects import INDEX
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

BODY=bytes.fromhex('34000000760000000100000008000000e25e0000760030f1')


def call(codec,body=BODY,name='SMSG_QUEST_UPDATE_ADD_CREDIT',active=True):
    fields={str(INDEX['PLAYER_QUEST_LOG_1_1']):52} if active else {}
    return result(codec,op='stateful',character={'guid':1,'map':0},snapshot={'guid':1,'fields':fields},
        gameobjects=[],units=[],actions=[{'fn':'quest_response','name':name,'body':body.hex()}])[0]


def test_captured_wolf_credit_keeps_victim_and_quest_and_narrows_counts(codec):
    reply=call(codec);assert reply[0]=='SMSG_QUEST_UPDATE_ADD_CREDIT'
    r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(int.from_bytes(BODY[16:],'little'),0)
    assert r.unpack('IIHHB')==(52,118,1,8,0);r.end()
    # Native credit can use a kill-credit entry distinct from the victim entry.
    body=struct.pack('<4IQ',52,1922,1,8,int.from_bytes(BODY[16:],'little'))
    assert call(codec,body)[0]=='SMSG_QUEST_UPDATE_ADD_CREDIT'


def test_gameobject_credit_removes_native_high_bit_and_preserves_type(codec):
    guid=(0xf11<<52)|(1234<<32)|15
    reply=call(codec,struct.pack('<4IQ',52,0x800004d2,2,3,guid))
    r=Reader(bytes.fromhex(reply[1]));assert r.guid()==modern_guid(guid,0)
    assert r.unpack('IIHHB')==(52,1234,2,3,2);r.end()


@pytest.mark.parametrize('values',[(0,118,1,8),(0x80000000,118,1,8),(52,0,1,8),
    (52,118,0,8),(52,118,1,0),(52,118,9,8),(52,118,1,65536)])
def test_invalid_credit_cannot_wrap_modern_widths(codec,values):
    assert 'error' in call(codec,struct.pack('<4IQ',*values,int.from_bytes(BODY[16:],'little')))


def test_credit_checks_exact_body_owned_quest_and_victim_type(codec):
    for size in range(len(BODY)):assert 'error' in call(codec,BODY[:size])
    assert 'error' in call(codec,BODY+b'x')
    assert call(codec,active=False) is None
    assert 'error' in call(codec,struct.pack('<4IQ',52,118,1,8,1))
    assert 'error' in call(codec,struct.pack('<4IQ',52,0x80000076,1,8,int.from_bytes(BODY[16:],'little')))
    assert call(codec,BODY[:16]+bytes(8))[0]=='SMSG_QUEST_UPDATE_ADD_CREDIT'


def test_completion_is_exact_and_only_for_the_owned_active_quest(codec):
    assert call(codec,struct.pack('<I',52),'SMSG_QUEST_UPDATE_COMPLETE')==['SMSG_QUEST_UPDATE_COMPLETE','34000000']
    assert call(codec,struct.pack('<I',52),'SMSG_QUEST_UPDATE_COMPLETE',False) is None
    for body in [b'',b'\0'*4,b'\x34\0\0',b'\x34\0\0\0x']:
        assert 'error' in call(codec,body,'SMSG_QUEST_UPDATE_COMPLETE')

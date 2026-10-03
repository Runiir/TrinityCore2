"""Captured Battle socket cast, with unchanged native spell/socket authority."""
import struct
from types import SimpleNamespace
import pytest
from tools.client_compatibility.world import casting
from tools.client_compatibility.world.buffer import Writer, Reader, player_high
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec, stateful, action

CAPTURE = bytes.fromhex('01870502e938bc0100000000000000a4e30000c64f050000000000000000000000000000000000000000000000000000800000000000000000')


def request(slot=1, targets=0x08000000, unit=(0,0), item=(0,0)):
    w=Writer().guid(5,0xbc38e90200000000).pack('iiiIff',slot,0,58276,348102,0,0)
    w.guid().pack('IIIB',0,0,0,0).bits(0,5).bits(0,1).bits(0,2).bits(0,1).flush()
    return w.bits(targets,28).bits(0,4).bits(0,7).guid(*unit).guid(*item).finish()


def test_captured_glyph_target_bit_moves_but_cast_spell_and_socket_do_not(codec):
    owner=SimpleNamespace(character={'guid':1,'map':0})
    encoded,spell=casting.request(owner,CAPTURE)
    assert spell==58276 and encoded==struct.pack('<BiiBI',1,58276,1,0,0x20000)
    assert stateful(codec,owner.character,[action('cast_request','CMSG_CAST_SPELL',CAPTURE)])==[
        ['CMSG_CAST_SPELL',encoded.hex()]]


@pytest.mark.parametrize('body',[request(-1),request(9),request(0x7fffffff),request(targets=0x08000002),
    request(unit=(1,player_high())),request(item=(1,player_high())),CAPTURE[:-1],CAPTURE+b'x'])
def test_invalid_glyph_socket_target_shapes_are_rejected(codec,body):
    assert 'error' in stateful(codec,{'guid':1,'map':0},[action('cast_request','CMSG_CAST_SPELL',body)])[0]


def test_native_glyph_start_and_completion_restore_modern_target_flag(codec):
    owner=SimpleNamespace(character={'guid':1,'map':0})
    casting.request(owner,CAPTURE)
    start=b'\x01\x01\x01\x01'+struct.pack('<BiIII',1,58276,2,0,3000)+struct.pack('<I',0x20000)
    go=b'\x01\x01\x01\x01'+struct.pack('<BiIII',1,58276,0x40100,0,0)+struct.pack('<BQB',1,1,0)+struct.pack('<I',0x20000)
    rows=stateful(codec,owner.character,[action('cast_request','CMSG_CAST_SPELL',CAPTURE),
        action('cast_response','SMSG_SPELL_START',start),action('cast_response','SMSG_SPELL_GO',go)])
    for row,name,body in [(rows[1],'SMSG_SPELL_START',start),(rows[2],'SMSG_SPELL_GO',go)]:
        expected=casting.response(owner,name,body)
        assert row==[name,expected.hex()]
        r=Reader(expected)
        for _ in range(4):r.guid()
        r.unpack('iIIIIIfBiiiB');r.guid()
        r.bits(16);r.bits(16);r.bits(16);r.bits(9);r.bits(1);r.bits(16);r.bits(2);r.align()
        assert r.bits(28)==0x08000000
    ordinary=request(targets=0)
    assert 'error' in stateful(codec,owner.character,[action('cast_request','CMSG_CAST_SPELL',ordinary),
        action('cast_response','SMSG_SPELL_START',start)])[1]

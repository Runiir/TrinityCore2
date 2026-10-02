"""CUF initialization and modern settings persistence through the native layout."""
import struct
from tools.client_compatibility.world.buffer import Reader,Writer
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_interaction_packets import call


def test_empty_profiles_initialize_modern_ui(codec):
    assert call(codec,'party_profiles','SMSG_LOAD_CUF_PROFILES',bytes(3))==['SMSG_LOAD_CUF_PROFILES','00000000']
    assert call(codec,'party_profiles','CMSG_SAVE_CUF_PROFILES',bytes(4))==['CMSG_SAVE_CUF_PROFILES','000000']


def test_native_profile_flag_order_and_geometry(codec):
    # Native load wire has a name length between two groups of booleans.
    w=Writer().bits(1,20)
    for i in range(19):w.bits(i in [0,1,2,6,10,11,14,16,17],1)
    w.bits(7,8)
    for i in range(6):w.bits(i in [1,2,4],1)
    w.flush().pack('3HBH3BHB',15,36,18,2,11,1,3,2,72,4).raw(b'Default')
    reply=call(codec,'party_profiles','SMSG_LOAD_CUF_PROFILES',w.finish())
    r=Reader(bytes.fromhex(reply[1]));assert r.unpack('I')==(1,);assert r.bits(7)==7
    # Keep, pets, assist, dispels, power, border, colors, horizontal, nonboss,
    # dynamic, locked, shown, activation 2/3/5/10/15/25/40/PVP/PVE.
    assert [r.bits(1) for _ in range(21)]==[1,1,0,0,1,1,1,1,0,1,1,1,1,0,1,1,0,0,0,0,0]
    assert r.unpack('2H5B3H')==(36,72,2,3,1,2,4,11,18,15)
    assert r.raw(7)==b'Default';r.end()


def test_modern_profile_save_native_option_positions(codec):
    w=Writer().pack('I',1).bits(4,7)
    for i in range(21):w.bits(i in [0,4,7,9,10,11,12,15,20],1)
    w.pack('2H5B3H',40,80,2,3,1,2,4,11,18,15).raw(b'Test')
    reply=call(codec,'party_profiles','CMSG_SAVE_CUF_PROFILES',w.finish())
    r=Reader(bytes.fromhex(reply[1]));assert r.bits(20)==1
    first=[r.bits(1) for _ in range(21)]
    assert first==[1,1,1,0,1,0,1,0,0,0,0,0,1,1,0,0,0,0,0,0,1]
    assert r.bits(8)==4;assert [r.bits(1) for _ in range(4)]==[1,1,0,1]
    assert r.unpack('B')==(1,);assert r.raw(4)==b'Test'
    assert r.unpack('4H3BHB')==(18,40,80,11,3,2,2,15,4);r.end()


def test_profile_count_truncation_and_extra_bytes_rejected(codec):
    for name,body in [('SMSG_LOAD_CUF_PROFILES',Writer().bits(6,20).finish()),
        ('CMSG_SAVE_CUF_PROFILES',struct.pack('<I',6)),('SMSG_LOAD_CUF_PROFILES',bytes(2)),
        ('CMSG_SAVE_CUF_PROFILES',bytes(4)+b'x')]:
        assert 'error' in call(codec,'party_profiles',name,body)

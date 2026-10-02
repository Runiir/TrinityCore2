import struct
from tools.client_compatibility.world.buffer import Writer,Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_interaction_packets import call,HIGH


def test_poll_request_and_native_informer(codec):
    assert call(codec,'party_roles','CMSG_INITIATE_ROLE_POLL',b'\0')==['CMSG_ROLE_POLL_BEGIN','']
    # Poll from native player GUID 1: only octet zero is present, XOR byte is zero.
    expected=Writer().pack('B',0).guid(1,HIGH).finish()
    assert call(codec,'party_roles','SMSG_ROLE_POLL_BEGIN',b'\x02\0')==['SMSG_ROLE_POLL_INFORM',expected.hex()]
    assert 'error' in call(codec,'party_roles','CMSG_INITIATE_ROLE_POLL',b'\x80\x01')


def test_tank_and_damage_roles_use_native_guid_sequence(codec):
    for role in [0,2,4,8]:
        body=Writer().bits(0,1).guid(2,HIGH).pack('B',role).finish()
        assert call(codec,'party_roles','CMSG_SET_ROLE',body)==['CMSG_SET_ROLE',(struct.pack('<I',role)+b'\x02\x03').hex()]
    for role in [16,128]:
        assert 'error' in call(codec,'party_roles','CMSG_SET_ROLE',Writer().bits(0,1).guid(2,HIGH).pack('B',role).finish())


def test_native_role_change_identity_and_old_new_order(codec):
    # From GUID 1, target GUID 2. Their zero octets need no bytes on the wire.
    flags=[False,True]+[False]*13+[True]
    w=Writer()
    for flag in flags:w.bits(flag,1)
    w.pack('BIBI',3,8,0,2)
    expected=Writer().pack('B',0).guid(1,HIGH).guid(2,HIGH).pack('2B',2,8).finish()
    assert call(codec,'party_roles','SMSG_ROLE_CHANGED_INFORM',w.finish())==['SMSG_ROLE_CHANGED_INFORM',expected.hex()]
    assert 'error' in call(codec,'party_roles','SMSG_ROLE_CHANGED_INFORM',w.finish()[:-1])

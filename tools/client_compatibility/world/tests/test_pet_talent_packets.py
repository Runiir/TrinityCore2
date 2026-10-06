"""Native pet catalogs are distinct from player specs and cannot terminate a valid login."""
import struct
import pytest
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec
from tools.client_compatibility.world.tests.test_talent_packets import call


@pytest.mark.parametrize('points,rows',[(0,[]),(3,[]),(1,[(122,0),(124,4)])])
def test_native_pet_catalog_preserves_points_and_ranks_with_pet_discriminator(codec,points,rows):
    # Empty payload 010000000000 is captured in UI111/class_enter01.
    body=struct.pack('<BIB',1,points,len(rows))+b''.join(struct.pack('<IB',*row) for row in rows)
    packet=call(codec,'SMSG_TALENTS_INFO',body)
    assert isinstance(packet,list) and packet[0]=='SMSG_UPDATE_TALENT_DATA'
    r=Reader(bytes.fromhex(packet[1]));assert r.unpack('IBI')==(points,0,1)
    assert r.unpack('BIBIBI')==(len(rows),len(rows),0,0,0,0)
    for row in rows:assert r.unpack('II')==row
    assert r.bits(1)==1;r.end()


@pytest.mark.parametrize('body',[b'\1',bytes.fromhex('010000000000')+b'x',
    struct.pack('<BIB',1,101,0),struct.pack('<BIB',1,0,101),
    struct.pack('<BIBIB',1,0,1,0,0),struct.pack('<BIBIB',1,0,1,122,5),
    struct.pack('<BIBIBIB',1,0,2,122,0,122,1)])
def test_pet_talent_catalog_rejects_bad_widths_counts_ranks_and_duplicates(codec,body):
    assert 'error' in call(codec,'SMSG_TALENTS_INFO',body)

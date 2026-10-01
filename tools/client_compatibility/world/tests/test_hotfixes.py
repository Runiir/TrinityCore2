from types import SimpleNamespace
import pytest
from tools.client_compatibility.world import hotfixes
from tools.client_compatibility.world.buffer import Reader,Writer


def test_reviewed_portal_record_is_advertised_and_sent_through_standard_hotfix():
    row=hotfixes.records()[0];r=Reader(hotfixes.available());r.unpack('I')
    assert r.unpack('I')==(1,) and r.unpack('iI')==(row['push_id'],row['unique_id']);r.end()
    sent=[];session=SimpleNamespace(send=lambda n,b:sent.append((n,b)))
    hotfixes.request(session,Writer().pack('IIIi',60895,0,1,row['push_id']).finish())
    name,body=sent[0];assert name=='SMSG_HOTFIX_MESSAGE';r=Reader(body)
    assert r.unpack('I')==(1,)
    assert r.unpack('IIIiI')==(row['push_id'],row['unique_id'],0x1A5081E1,4354,55)
    assert r.bits(3)==1 and r.unpack('I')==(55,)
    payload=r.raw(55);r.end();data=Reader(payload)
    assert data.raw(1)==b'\0';x,y,z=data.unpack('3f')
    assert abs(x+11908.9)<.01 and abs(y+3209.1)<.01 and abs(z+14.7905)<.01
    assert data.unpack('I')==(4354,)
    with pytest.raises(ValueError):hotfixes.request(session,Writer().pack('IIIi',60895,0,1,1).finish())

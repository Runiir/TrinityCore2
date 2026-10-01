from types import SimpleNamespace
import pytest
from tools.client_compatibility.world import hotfixes
from tools.client_compatibility.world.buffer import Reader,Writer


def test_reviewed_portal_record_is_advertised_and_sent_through_standard_hotfix():
    rows=hotfixes.records();row=next(row for row in rows if row['record_id']==4354)
    r=Reader(hotfixes.available());r.unpack('I');assert r.unpack('I')==(2,)
    assert [r.unpack('iI') for _ in rows]==[(row['push_id'],row['unique_id']) for row in rows];r.end()
    sent=[];session=SimpleNamespace(send=lambda n,b:sent.append((n,b)))
    hotfixes.request(session,Writer().pack('IIIi',60895,0,1,row['push_id']).finish())
    name,body=sent[0];assert name=='SMSG_HOTFIX_CONNECT';r=Reader(body)
    assert r.unpack('I')==(1,)
    assert r.unpack('IIIiI')==(row['push_id'],row['unique_id'],0x1A5081E1,4354,55)
    assert r.bits(3)==1 and r.unpack('I')==(55,)
    payload=r.raw(55);r.end();data=Reader(payload)
    assert data.raw(1)==b'\0';x,y,z=data.unpack('3f')
    assert abs(x+11908.9)<.01 and abs(y+3209.1)<.01 and abs(z+14.7905)<.01
    assert data.unpack('I')==(4354,)
    with pytest.raises(ValueError):hotfixes.request(session,Writer().pack('IIIi',60895,0,1,1).finish())


def test_return_portal_hotfix_matches_native_portal_and_two_record_response():
    rows=hotfixes.records();sent=[];session=SimpleNamespace(send=lambda n,b:sent.append((n,b)))
    hotfixes.request(session,Writer().pack('IIIii',60895,0,2,*[row['push_id'] for row in rows]).finish())
    r=Reader(sent[0][1]);assert r.unpack('I')==(2,)
    for row in rows:
        assert r.unpack('IIIiI')==(row['push_id'],row['unique_id'],0x1A5081E1,row['record_id'],55)
        assert r.bits(3)==1;r.align()
    assert r.unpack('I')==(110,);r.raw(110);r.end()
    data=Reader(hotfixes.lookup(0x1A5081E1,4352));data.raw(1);x,y,z=data.unpack('3f')
    assert abs(x+247.677)<.01 and abs(y-895.675)<.01 and abs(z-144.362)<.01

from types import SimpleNamespace
import struct
import pytest
from tools.client_compatibility.world import hotfixes
from tools.client_compatibility.world.buffer import Reader,Writer


def test_reviewed_portal_record_is_advertised_and_sent_through_standard_hotfix():
    rows=hotfixes.records();row=next(row for row in rows if row['record_id']==4354)
    r=Reader(hotfixes.available());r.unpack('I');assert r.unpack('I')==(4,)
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
    rows=[r for r in hotfixes.records() if r['table_hash']==0x1A5081E1]
    sent=[];session=SimpleNamespace(send=lambda n,b:sent.append((n,b)))
    hotfixes.request(session,Writer().pack('IIIii',60895,0,2,*[row['push_id'] for row in rows]).finish())
    r=Reader(sent[0][1]);assert r.unpack('I')==(2,)
    for row in rows:
        assert r.unpack('IIIiI')==(row['push_id'],row['unique_id'],0x1A5081E1,row['record_id'],55)
        assert r.bits(3)==1;r.align()
    assert r.unpack('I')==(110,);r.raw(110);r.end()
    data=Reader(hotfixes.lookup(0x1A5081E1,4352));data.raw(1);x,y,z=data.unpack('3f')
    assert abs(x+247.677)<.01 and abs(y-895.675)<.01 and abs(z-144.362)<.01


def test_return_portal_contact_box_covers_observed_collision_without_changing_center():
    row=next(r for r in hotfixes.records() if r['record_id']==4352)
    original=bytes.fromhex(row['original_data']);contact=bytes.fromhex(row['data'])
    assert contact[:35]==original[:35] and contact[39:]==original[39:]
    y=struct.unpack_from('<f',contact,5)[0]
    width=struct.unpack_from('<f',contact,35)[0]
    assert abs(width-8.611)<.001
    assert y-width/2<892.2908<y+width/2
    assert row['push_id']==60895003


def test_private_native_table_matches_client_contact_bounds():
    from tools.client_compatibility import lab_runtime as lab,portal_geometry
    original=(lab.BASE/'data/dbc/enUS/AreaTrigger.dbc').read_bytes()
    contact=portal_geometry.patch(original)
    _,count,_,size,_=struct.unpack_from('<4s4I',contact)
    offset=next(20+i*size for i in range(count) if struct.unpack_from('<I',contact,20+i*size)[0]==4352)
    assert contact[:offset+40]==original[:offset+40] and contact[offset+44:]==original[offset+44:]
    assert contact[offset+40:offset+44]==hotfixes.lookup(0x1A5081E1,4352)[35:39]
    with pytest.raises(ValueError):portal_geometry.patch(b'unreviewed table')

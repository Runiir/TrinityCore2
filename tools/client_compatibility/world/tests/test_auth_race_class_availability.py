"""Read auth availability independently, including the realm tail after rows."""
import pytest
from tools.client_compatibility.world import characters
from tools.client_compatibility.world.buffer import Reader
from .test_native_bridge_codec import codec,result


def read(body):
    r=Reader(bytes.fromhex(body));assert r.unpack('I')==(0,)
    assert (r.bits(1),r.bits(1))==(1,0)
    realm,count,rested,active,account,kick,races,templates,currency,clock=r.unpack('IIIBBIIIIq')
    assert (realm,count,rested,active,account,kick,templates,currency)==(0x01010001,1,0,3,3,0,0,0)
    found=[]
    for _ in range(races):
        race,classes=r.unpack('BI')
        for _ in range(classes):found.append((race,*r.unpack('BBBB')))
    assert r.bits(6)==0 and r.unpack('III')==(0,0,0) and r.bits(3)==0
    assert r.unpack('I')==(0x01010001,)
    assert (r.bits(1),r.bits(1))==(1,0)
    n,m=r.bits(8),r.bits(8)
    assert r.raw(n+m)==b'Client442 LabClient442Lab';r.end()
    return found


def test_auth_advertises_native_pairs_without_synthetic_combinations(codec):
    rows=[{'race':3,'class':6,'expansion':2},{'race':1,'class':1,'expansion':0},
        {'race':3,'class':1,'expansion':0},{'race':22,'class':1,'expansion':3}]
    expected=[(1,1,0,0,0),(3,1,0,0,0),(3,6,2,2,2),(22,1,3,3,3)]
    assert read(result(codec,op='auth_success',race_classes=rows))==expected
    assert read(characters.auth_success(rows).hex())==expected
    assert read(result(codec,op='auth_success',race_classes=[]))==[]


@pytest.mark.parametrize('row',[{'race':0,'class':1,'expansion':0},
    {'race':3,'class':256,'expansion':0},{'race':3,'class':1,'expansion':4}])
def test_invalid_availability_fails_before_auth_response(codec,row):
    assert 'error' in codec(op='auth_success',race_classes=[row])
    with pytest.raises(ValueError):characters.auth_success([row])


def test_duplicate_availability_is_rejected(codec):
    rows=[{'race':3,'class':1,'expansion':0}]*2
    assert 'error' in codec(op='auth_success',race_classes=rows)
    with pytest.raises(ValueError):characters.auth_success(rows)

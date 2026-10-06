"""Native rename/abandon permissions reach the stock client, including removal."""
import pytest
from tools.client_compatibility.world.buffer import Reader
from tools.client_compatibility.world.objects import INDEX,field_values
from tools.client_compatibility.world.tests.test_native_bridge_codec import codec,result

PET=(0xf14<<52)|(42717<<32)|76
CHAR={'guid':6,'name':'Harnesshunt','gender':0,'map':0}


@pytest.mark.parametrize('flags',[0,1,2,3,255])
def test_native_pet_permission_byte_is_not_pvp_or_sheath_flags(codec,flags):
    s={'guid':PET,'map':0,'kind':3,'fields':{INDEX['UNIT_FIELD_BYTES_2']:0x05001107|(flags<<16)}}
    cpp=result(codec,op='object_values',snapshot=s,character=CHAR)['UnitData']
    py=field_values(s,CHAR)['UnitData']
    assert cpp['PetFlags']==py['PetFlags']==flags
    assert [cpp[k] for k in ('SheatheState','PvpFlags','ShapeshiftForm')]==[7,17,5]


@pytest.mark.parametrize('flags',[0,1,2,3])
def test_permission_updates_include_zero_and_exact_pinned_mask80(codec,flags):
    changed={INDEX['UNIT_FIELD_BYTES_2']:flags<<16}
    s={'guid':PET,'map':0,'kind':3,'fields':changed}
    body=bytes.fromhex(result(codec,op='unit_update',snapshot=s,character=CHAR,changed=changed,visibility=0))
    r=Reader(body);assert r.unpack('B')==(0,);r.guid();size=r.unpack('I')[0]
    data=Reader(r.raw(size));r.end();assert data.unpack('BBBI')==(0,0,3,32)
    presence=data.bits(8);masks={i:data.bits(32) for i in range(8) if presence&(1<<i)}
    assert masks=={2:1|(1<<14)|(1<<15)|(1<<16)|(1<<17)}
    assert data.unpack('4B')==(0,0,flags,0);data.end()

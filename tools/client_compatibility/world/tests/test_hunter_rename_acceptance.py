"""A successful one-time name cannot hide unrelated retained pet changes."""
from copy import deepcopy
import struct
import pytest
from tools.client_compatibility.interaction_hunter_rename_acceptance import renamed_pet_unchanged,native_name,modern_name
from tools.client_compatibility.world.buffer import Writer


@pytest.mark.parametrize('fault',('none','name','renamed','owner','slot','entry','health','actionbar','clock_back','clock_future'))
def test_name_persistence_allows_only_name_rename_bit_and_save_clock(fault):
    before=[{'name':'Wolf','renamed':0,'owner':6,'slot':0,'entry':42717,'curhealth':278,'abdata':'native','savetime':100}]
    after=[{**deepcopy(before[0]),'name':'Harnesswolf','renamed':1,'savetime':101}]
    changes={'name':'Otherwolf','renamed':0,'owner':5,'slot':1,'entry':416,'health':0,'actionbar':'changed',
        'clock_back':99,'clock_future':103}
    keys={'health':'curhealth','actionbar':'abdata','clock_back':'savetime','clock_future':'savetime'}
    if fault!='none':after[0][keys.get(fault,fault)]=changes[fault]
    assert renamed_pet_unchanged(before,after,102)==(fault=='none')


def test_native_and_modern_name_timestamps_have_their_pinned_widths():
    native=struct.pack('<I',4)+b'Harnesswolf\0'+struct.pack('<IB',1791328588,0)
    modern=(Writer().guid(77,2882308159566362432).bits(1,1).bits(11,8).bits(0,1)
        .bits(0,35).pack('q',1791328588).raw(b'Harnesswolf').finish())
    assert native_name({'body':native.hex()})=={'pet_number':4,'name':'Harnesswolf','timestamp':1791328588}
    assert modern_name({'body':modern.hex()})=={'guid':[77,2882308159566362432],
        'name':'Harnesswolf','timestamp':1791328588}
    for parser,body in ((native_name,native),(modern_name,modern)):
        for invalid in (body[:-1],body+b'extra',b''):
            with pytest.raises(ValueError):parser({'body':invalid.hex()})

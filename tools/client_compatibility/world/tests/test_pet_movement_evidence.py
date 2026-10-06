"""Foreign, late, mismatched or absent movement cannot qualify an owned Follow."""
import struct
from types import SimpleNamespace
import pytest
from tools.client_compatibility.pet_movement_evidence import movement_pairs,follow_motion_checks,xyz
from tools.client_compatibility.world import creature_movement

PET=0xf14001a000000017


def rows():
    octets=PET.to_bytes(8,'little');packed=bytes([sum(1<<i for i,v in enumerate(octets) if v)])+bytes(v for v in octets if v)
    body=packed+struct.pack('<B3fIBIII',0,0,0,0,7,0,0x400000,1000,1)+struct.pack('<3f',8,0,0)
    owner=SimpleNamespace(visible_units={PET:{'map':0,'movement':{'position':[0,0,0,0]}}})
    client=creature_movement.response(owner,'SMSG_ON_MONSTER_MOVE',body)[1]
    return [{'session':'owned','time':10,'name':'SMSG_ON_MONSTER_MOVE','direction':'from_native','body':body.hex()},
        {'session':'owned','time':10.1,'name':'SMSG_ON_MONSTER_MOVE','direction':'to_client','body':client.hex()}]


def point(x):return {'available':True,'x':x,'y':0,'z':0,'map':0}


def test_owned_native_path_requires_exact_same_window_client_delivery_and_public_endpoint():
    pairs=movement_pairs(rows(),'owned',PET,0,9,11)
    assert len(pairs)==1 and pairs[0]['endpoint']==[8,0,0] and pairs[0]['client']
    assert all(follow_motion_checks(pairs,point(0),point(8),[10,0,0]).values())


@pytest.mark.parametrize('change',['foreign_native','foreign_client','outside','late','bad_client','missing_client','wrong_pet'])
def test_foreign_late_changed_and_absent_paths_fail_follow_evidence(change):
    source=rows();guid=PET
    if change=='foreign_native':source[0]['session']='foreign'
    elif change=='foreign_client':source[1]['session']='foreign'
    elif change=='outside':source[0]['time']=8
    elif change=='late':source[1]['time']=12.1
    elif change=='bad_client':source[1]['body']=source[1]['body'][:-2]+'01'
    elif change=='missing_client':source.pop()
    else:guid=PET+1
    pairs=movement_pairs(source,'owned',guid,0,9,13)
    assert not all(follow_motion_checks(pairs,point(0),point(8),[10,0,0]).values())


@pytest.mark.parametrize('value',[{'available':False},point(float('nan')),point(float('inf')),point(20000)])
def test_unavailable_or_invalid_public_position_is_not_a_motion_outcome(value):
    with pytest.raises(ValueError):xyz(value)


@pytest.mark.parametrize('after,owner',[(point(0),[10,0,0]),(point(3),[10,0,0]),(point(8),[20,0,0])])
def test_native_path_without_matching_public_displacement_or_owner_position_fails(after,owner):
    pairs=movement_pairs(rows(),'owned',PET,0,9,11)
    assert not all(follow_motion_checks(pairs,point(0),after,owner).values())

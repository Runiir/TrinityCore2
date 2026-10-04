"""A mode bit alone must not qualify the actual walk/run displacement."""
import pytest
from tools.client_compatibility.interaction_ground_modes import cadence


def case(speed,flags):
    return {'oracle':{'native_after':[speed*1.2,0,0,0,0],'request_pairs':[
        {'modern':{'name':'CMSG_MOVE_START_FORWARD'},'movement':{'time':1000,'position':[0,0,0,0],'flags':flags|1}},
        {'modern':{'name':'CMSG_MOVE_STOP'},'movement':{'time':2200,'position':[speed*1.2,0,0,0],'flags':flags}}]}}


@pytest.mark.parametrize('speed,flags,walking',[(2.5,0x100,True),(7,0,False)])
def test_native_cadence_requires_mode_and_displacement(speed,flags,walking):
    assert all(cadence(case(speed,flags),walking)['checks'].values())


@pytest.mark.parametrize('speed,flags',[(7,0x100),(2.5,0)])
def test_walk_mode_without_walk_displacement_is_not_a_pass(speed,flags):
    assert not all(cadence(case(speed,flags),True)['checks'].values())

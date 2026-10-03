"""Moving-unit positions must advance beyond the captured spline origin."""
import struct
import pytest
from tools.client_compatibility.observation.spline_pose import estimate,path


def spline(**kw):
    return dict(position=[0,0,0],points=[[8,0,0]],deltas=b'',flags=0,duration=4000,observed_at=100,**kw)


def test_linear_position_uses_elapsed_time_and_clamps_to_path():
    row=spline()
    assert estimate(row,99)==[0,0,0]
    assert estimate(row,102)==[4,0,0]
    assert estimate(row,104)==[8,0,0]
    assert estimate(row,1000)==[8,0,0]


def test_signed_native_quarter_yard_waypoint_deltas():
    # Middle=(4,0,0), waypoint=(3,2,-1), delta=(1,-2,1).
    packed=(4&2047)|((-8&2047)<<11)|((4&1023)<<22)
    row=spline();row['deltas']=struct.pack('<I',packed)
    assert path(row)==[[0,0,0],[3,2,-1],[8,0,0]]
    assert estimate(row,104)==[8,0,0]
    assert estimate(row,102)!=[0,0,0]
    with pytest.raises(struct.error):path({**row,'deltas':b'x'})


def test_stop_zero_distance_and_uncompressed_polyline():
    row=spline();row.update(points=[],duration=0)
    assert estimate(row,1000)==[0,0,0]
    row.update(points=[[0,0,0]],duration=4000)
    assert estimate(row,102)==[0,0,0]
    row.update(points=[[0,4,0],[4,4,0]],flags=0x400000)
    assert estimate(row,102)==[0,4,0]

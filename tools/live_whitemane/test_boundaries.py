import math
import subprocess
from . import boundaries,runtime

U=[[0,0],[100,0],[100,100],[70,100],[70,30],[30,30],[30,100],[0,100]]


def setup(monkeypatch):
    monkeypatch.setattr(boundaries,'sites',lambda:{'1':{'map':1,'polygon':U}})
    row={'archaeology':{'site_id':1,'world':{'instance':1,'north':15,'west':70}},
        'movement':{'facing_radians':0}}
    guide={'source':'Survey telescope','world':{'instance':1,'north':85,'west':70},
        'distance_yards':70,'arrived':False,'color':'red','arrival_tolerance_yards':6}
    return row,guide


def test_line_stops_at_first_exit_even_when_its_endpoint_is_inside(monkeypatch):
    row,guide=setup(monkeypatch)
    result=boundaries.constrain(row,guide)
    assert result['boundary_clipped'] and result['distance_yards']==7
    assert result['world']['north']==22 and result['world']['west']==70
    assert boundaries.inside_segment(U,[15,70],[22,70])
    assert not boundaries.inside_segment(U,[15,70],[85,70])


def test_same_saved_marker_is_approached_around_the_concavity(monkeypatch):
    row,guide=setup(monkeypatch);guide['source']='GatherMate marker'
    result=boundaries.constrain(row,guide)
    route=[[15,70],*result['boundary_route']]
    assert result['unclipped_world']==guide['world']
    assert not result['arrived'] and not result['original_marker_arrival_confirmed']
    assert result['world']!=guide['world'] and result['world']['west']==22
    assert all(boundaries.inside_segment(U,a,b) for a,b in zip(route,route[1:]))
    # After the first corner, recomputation retains the original marker.
    row['archaeology']['world']=result['world']
    next_leg=boundaries.constrain(row,guide)
    assert next_leg['unclipped_world']==guide['world']
    assert next_leg['world']['north']>result['world']['north']


def test_a_zero_length_clipped_line_is_already_reached(monkeypatch):
    row,guide=setup(monkeypatch)
    guide.update(world=dict(row['archaeology']['world']),distance_yards=0)
    assert boundaries.constrain(row,guide)['arrived']


def test_concave_route_is_orientation_independent():
    forward=boundaries.interior_route(U,[15,70],[85,70])
    reverse=boundaries.interior_route(U[::-1],[15,70],[85,70])
    assert forward==reverse and forward[-1]==[85,70]


def test_addon_first_exit_and_inside_endpoint_agree():
    subprocess.run(['lua','tools/live_whitemane/test_boundary.lua'],cwd=runtime.REPO,check=True)

import math
import pytest
from tools.client_compatibility import ground_navigation as ground,lab_runtime as lab,site_boundaries
from tools.client_compatibility.swim_navigation import available,dry_arrival


provisioned=pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')


@provisioned
def test_clean_water_connects_to_dry_shore_without_admitting_hazardous_liquids():
    start=[-2452,4961,28.5];goal=[-2468,4964,30]
    with pytest.raises(RuntimeError,match='no connected walkable route'):
        ground.route(530,start,goal)
    route=ground.route(530,start,goal,allow_swimming=True)
    assert route['water_polygons']>0 and not route['ground_only']
    assert route['complete'] and route['goal_terrain']=='ground'
    assert route['allowed_terrain_flags']==1|4
    assert not route['allowed_terrain_flags']&8  # NAV_MAGMA_SLIME
    assert route['points'][-1][2]>32


@provisioned
def test_trial48_extends_the_underwater_survey_goal_to_a_dry_in_site_endpoint():
    start=[-2459.08251953125,4956.09814453125,29.055362701416016,.13508033752441406]
    tcp={'player':{'position':start},'tool':{'map':530,'heading_radians':.06834596395492554}}
    plan=ground.walk_plan(tcp,3.5,[371],allow_swimming=True)
    assert math.dist(plan['requested_goal'][:2],start[:2])>7
    assert plan['points'][-1][2]>32
    polygon=site_boundaries.sites()[371]['polygon']
    assert all(site_boundaries.inside_segment(polygon,a,b) for a,b in zip(plan['points'],plan['points'][1:]))


def test_arrival_requires_actual_dry_addon_state():
    goal=[0,0,4];extra=dict(swimming=False,falling=False,mounted=False,flying=False)
    assert dry_arrival([.5,0,4],goal,extra)
    assert not dry_arrival([.5,0,4],goal,{**extra,'swimming':True})
    assert not dry_arrival([.5,0,4],goal,{**extra,'falling':True})
    assert not dry_arrival([2,0,4],goal,extra)


def test_water_transit_stops_on_boundary_combat_or_health_loss():
    movement=dict(in_world=True,dead=False,in_combat=False,on_taxi=False,health_percent=100)
    extra=dict(mounted=False,flying=False)
    polygon=[[0,0],[10,0],[10,10],[0,10]]
    available(movement,extra,[5,5,0],polygon)
    with pytest.raises(RuntimeError,match='digsite'):available(movement,extra,[12,5,0],polygon)
    with pytest.raises(RuntimeError,match='unavailable'):available({**movement,'in_combat':True},extra,[5,5,0],polygon)
    with pytest.raises(RuntimeError,match='health'):available({**movement,'health_percent':49},extra,[5,5,0],polygon)

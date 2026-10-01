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


@provisioned
def test_shallow_submerged_feet_are_not_accepted_as_a_dry_survey_stance():
    # Trial 51 stopped swimming when touching the pond floor, but its feet
    # were still below the public water surface and six yards below the find.
    tcp={'player':{'position':[-2457.881591796875,4958.9521484375,26.857702255249023,2.931098461151123]}}
    plan=ground.dry_cast_plan(tcp,{'world_map':530,'swimming':False,'digsite_ids':[371]})
    assert plan and plan['goal_source']=='public_player_facing_and_site_polygon'
    assert plan['points'][-1][2]>29
    dry={'player':{'position':[-2468,4964,32.96785,0]}}
    assert ground.dry_cast_plan(dry,{'world_map':530,'swimming':False,'digsite_ids':[371]}) is None


@provisioned
def test_trial57_dry_ruin_height_mismatch_does_not_trigger_a_shore_move():
    for start in [[2727.27392578125,3131.229248046875,150.65481567382812,3.506],
                  [2716.355224609375,3132.70458984375,138.6723175048828,3.779]]:
        assert not ground.water_at(530,start)['water_above_feet']
        assert ground.dry_cast_plan({'player':{'position':start}},
            {'world_map':530,'swimming':False,'digsite_ids':[355]}) is None


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
    with pytest.raises(RuntimeError,match='combat'):available({**movement,'in_combat':True},extra,[5,5,0],polygon)
    with pytest.raises(RuntimeError,match='health'):available({**movement,'health_percent':49},extra,[5,5,0],polygon)

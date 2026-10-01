import pytest
from tools.client_compatibility import ground_navigation as ground,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_coilskar_wall_routes_on_lower_floor_and_retains_the_detour():
    # Trial 43 repeatedly approached the solid wall from these actual feet.
    # Its old route began on a mesh surface 1.5 yards overhead.
    origin=[-2928.4126,1636.82165,55.0864]
    goal=[-2927.5,1633.5,55.0864]
    route=ground.route(530,origin,goal)
    assert route['excluded_obstructed_polygons']>0
    assert route['points'][0][2]<origin[2]+.8
    assert min(p[0] for p in route['points'])<origin[0]-4
    assert route['obstruction_origins']
    moved=[-2929.42554,1638.44226,55.2]
    next_route=ground.route(530,moved,goal,route['obstruction_origins'])
    assert next_route['excluded_obstructed_polygons']>0
    assert next_route['points'][1]==route['points'][1]


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_grangolvar_low_bridge_remains_available_for_a_bounded_hop():
    # Trial 47 incorrectly remembered a 1.08-yard low step as a tall wall,
    # removing the bridge needed to leave the lower bank.
    old_feet=[-2459.01514,4949.354,33.8216782]
    route=ground.route(530,[-2459.0859375,4954.52294921875,29.9314365],
        [-2455.59,4954.69,29.9314365],[old_feet])
    assert not route['obstruction_origins'] and route['excluded_obstructed_polygons']==0
    assert route['complete'] and max(p[2] for p in route['points'])>34

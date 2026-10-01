"""Regression fixtures from the live Outland hillside slide."""
import json
import subprocess
import pytest
from tools.client_compatibility import ground_navigation as ground,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_landing_rejects_steep_detail_and_covered_flat_ground():
    goal=[-315.518066,3182.38916,120.252457]
    # A flat polygon below the hill is covered; its exposed faces are too
    # steep to stand on. The stricter landing guard must reject this column.
    with pytest.raises(RuntimeError,match='no public walkable ground'):
        ground.landing_point(530,goal)


def test_survey_flight_respects_explicit_landing_radius():
    from tools.client_compatibility import travel_trial
    movement=dict(in_world=True,dead=False,in_combat=False,on_taxi=False)
    extra=dict(casting=False,mounted=True,flying=False,falling=False)
    facts=dict(position=[107,200,20,0],map=0,transferring=False)
    state=travel_trial.state(dict(mode='flight',map=0,position=[100,200,20],arrival_radius=1.5),movement,extra,facts,{'nodes':[]})
    assert not state['destination_reached'] and not state['near_destination']


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_bonechewer_landing_stays_on_the_ground_component_that_supported_survey():
    origin=[-2907.88159,3512.58374,-24.695236]
    goal=[-2912.7998,3491.19995,-4.86794662]
    point=ground.landing_point(530,goal,start=origin)
    # The failed trial landed on a disconnected roof at Z34.458.
    assert point[2]<10
    path=ground.route(530,origin,point)
    assert abs(path['points'][-1][2]-point[2])<2


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_coilskar_flight_can_cross_a_slope_excluded_from_walking():
    # Actual trial 40 yellow bearing. The destination is 16 yards downhill;
    # the filtered walking corridor is unavailable, but flat connected ground
    # exists at the public bearing for a mounted flight.
    origin=[-2873.942626953125,1676.2451171875,59.17497634887695]
    goal=[-2853.34468157961,1672.1555394110421,59.17497634887695]
    with pytest.raises(RuntimeError,match='no connected walkable route'):
        ground.route(530,origin,goal)
    point=ground.landing_point(530,goal,start=origin)
    assert point[2]<origin[2]-10
    assert abs(point[0]-goal[0])<.01 and abs(point[1]-goal[1])<30


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_coilskar_landing_rejects_the_surface_that_kept_sliding():
    origin=[-2821.588623046875,1667.5943603515625,18.123668670654297]
    goal=[-2867.19995,1664,55.6613159]
    result=subprocess.run([str(ground.binary()),str(lab.BASE/'data/mmaps'),'530','--landing',
        *map(str,goal),'30',*map(str,origin)],capture_output=True,text=True,check=True)
    landing=json.loads(result.stdout)
    assert 0<=landing['detail_slope_degrees']<=20
    assert abs(landing['position'][0]-goal[0])+abs(landing['position'][1]-goal[1])>1

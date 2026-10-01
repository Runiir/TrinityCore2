import math
import pytest
from tools.client_compatibility import lab_runtime as lab,site_boundaries
from tools.client_compatibility.loot_pose import plan


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')
def test_trial51_bank_find_stance_preserves_elevation_and_dry_terrain():
    # A blind 3.5-yard backstep dropped the actual character into water,
    # six yards below its already visible find and outside interaction reach.
    start=[-2443.22509765625,4955.91943359375,32.44786834716797,1.8818082809448242]
    find=[*start[:2],32.54786682128906]
    route=plan(530,start,find,site_boundaries.sites()[371]['polygon'])
    assert not route['water_polygons']
    assert abs(route['points'][-1][2]-find[2])<=1.25
    assert 2.5<math.dist(route['points'][-1],find)<=4.75

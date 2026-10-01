import math
import pytest
from tools.client_compatibility import ground_escape as escape,ground_navigation as ground,site_boundaries,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')
def test_trial58_mesh_corner_has_short_dry_sideways_candidates():
    tcp={'player':{'position':[2716.33935546875,3132.69189453125,138.6610107421875,4.351]},
         'tool':{'map':530,'heading_radians':4.311063766479492}}
    with pytest.raises(RuntimeError):ground.walk_plan(tcp,3.5,[355],allow_swimming=True)
    site=site_boundaries.sites()[355];routes=escape.candidates(tcp,site)
    assert 1<=len(routes)<=4
    for route in routes:
        assert not route['water_polygons']
        assert abs(route['points'][-1][2]-tcp['player']['position'][2])<=1.25
        assert math.dist(route['points'][-1][:2],tcp['player']['position'][:2])>=1.5

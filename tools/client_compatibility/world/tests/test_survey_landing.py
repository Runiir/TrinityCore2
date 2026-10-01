import math
import pytest
from tools.client_compatibility import survey_landing,ground_navigation as ground,site_boundaries,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper absent')
def test_trial66_flat_point_with_steep_overlapping_terrain_is_rejected():
    start=[-3273.335205078125,911.30078125,40.77760696411133]
    heading=4.326226711273193;site=site_boundaries.sites()[391]
    # The former acceptance looked only at one flat detail face. Its public
    # supporting column also contains a 52-degree face at that elevation.
    surface=ground.probe_surface(530,[-3269.06665,872.799927,19.6610985])
    assert surface['detail_slope_degrees']>35
    with pytest.raises(RuntimeError,match='no progressive'):
        survey_landing.select(site,start,heading,21)


def test_backward_flat_surface_is_rejected(monkeypatch):
    site={'map':530,'polygon':[[-100,-100],[100,-100],[100,100],[-100,100]]}
    monkeypatch.setattr(ground,'landing_point',lambda *a,**kw:[-5,0,0])
    with pytest.raises(RuntimeError,match='no progressive'):
        survey_landing.select(site,[0,0,0],0,21)

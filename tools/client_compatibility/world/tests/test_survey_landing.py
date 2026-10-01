import math
import pytest
from tools.client_compatibility import survey_landing,ground_navigation as ground,site_boundaries,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper absent')
def test_trial66_yellow_cliff_has_a_shorter_progressive_landing():
    start=[-3273.335205078125,911.30078125,40.77760696411133]
    heading=4.326226711273193;site=site_boundaries.sites()[391]
    point,record=survey_landing.select(site,start,heading,21)
    assert site_boundaries.inside_segment(site['polygon'],start,point)
    assert (point[0]-start[0])*math.cos(heading)+(point[1]-start[1])*math.sin(heading)>=1.5
    assert record['attempts'][-1]['accepted']
    assert math.dist(start[:2],point[:2])>=3


def test_backward_flat_surface_is_rejected(monkeypatch):
    site={'map':530,'polygon':[[-100,-100],[100,-100],[100,100],[-100,100]]}
    monkeypatch.setattr(ground,'landing_point',lambda *a,**kw:[-5,0,0])
    with pytest.raises(RuntimeError,match='no progressive'):
        survey_landing.select(site,[0,0,0],0,21)

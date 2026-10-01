import pytest
from tools.client_compatibility import site_landing,site_boundaries,ground_navigation as ground,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper absent')
def test_trial68_dragonmaw_center_has_a_nearby_dry_flat_arrival():
    site=site_boundaries.sites()[399];origin=ground.ground_point(530,site['center'])
    with pytest.raises(RuntimeError):ground.landing_point(530,origin,start=origin)
    point,record=site_landing.select(site,origin)
    assert site_boundaries.inside_segment(site['polygon'],origin,point)
    assert not ground.water_at(530,point)['water_above_feet']
    assert record['attempts'][-1]['accepted'] and record['dry_arrival_required']


def test_flat_pond_floor_is_rejected_as_a_flight_arrival(monkeypatch):
    site={'map':530,'polygon':[[-100,-100],[100,-100],[100,100],[-100,100]]}
    monkeypatch.setattr(ground,'landing_point',lambda *a,**kw:[0,0,0])
    monkeypatch.setattr(ground,'water_at',lambda *a:{'water_above_feet':True})
    with pytest.raises(RuntimeError,match='no dry flat arrival'):site_landing.select(site,[0,0,0])

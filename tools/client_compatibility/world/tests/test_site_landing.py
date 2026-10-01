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
    assert record['safe_patch']['radius_yards']==1.5
    assert all(abs(s['physical_surface']['terrain_height']-s['position'][2])<=1.5
        for s in record['safe_patch']['samples'])


@pytest.mark.skipif(not (lab.BASE/'data/maps/5303931.map').exists(),reason='public terrain absent')
def test_dragonmaw_flat_roof_is_not_an_initial_survey_ground():
    point=[-4198,385.416656,118.10009]
    assert ground.safe_landing_patch(530,point)
    with pytest.raises(RuntimeError,match='raised|detached'):ground.site_ground_patch(530,point)


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper absent')
def test_trial69_tiny_flat_ledge_beside_the_slide_face_is_rejected():
    with pytest.raises(RuntimeError):ground.safe_landing_patch(530,[-4189.9458,407.542633,79.019104])


def test_flat_pond_floor_is_rejected_as_a_flight_arrival(monkeypatch):
    site={'map':530,'polygon':[[-100,-100],[100,-100],[100,100],[-100,100]]}
    monkeypatch.setattr(ground,'landing_point',lambda *a,**kw:[0,0,0])
    monkeypatch.setattr(ground,'water_at',lambda *a:{'water_above_feet':True})
    with pytest.raises(RuntimeError,match='no dry flat arrival'):site_landing.select(site,[0,0,0])

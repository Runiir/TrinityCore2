import pytest
from tools.client_compatibility import archaeology_loop as loop,site_boundaries,site_landing,ground_navigation as ground,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper absent')
def test_trial70_cannot_resume_surveying_on_the_known_cliff():
    site=site_boundaries.sites()[399]
    extra=dict(mounted=False,flying=False,falling=False,swimming=False)
    assert not loop.ready_at_site({'map':530,'position':[-4189.383789,407.6394,77.9956]},extra,site)
    origin=ground.ground_point(530,site['center']);point,_=site_landing.select(site,origin)
    assert loop.ready_at_site({'map':530,'position':point},extra,site)


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper absent')
def test_water_restart_enters_the_swimming_adapter_instead_of_remounting():
    site=site_boundaries.sites()[371]
    extra=dict(mounted=False,flying=False,falling=False,swimming=False)
    assert loop.ready_at_site({'map':530,'position':[-2459.85034,4961.87646,27.95905]},extra,site)

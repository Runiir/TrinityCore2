import math
import pytest
from tools.client_compatibility import ground_navigation as ground,site_boundaries


def fixture(monkeypatch,polygon,center):
    site={'id':387,'polygon':polygon,'center':center,'map':530,'source':'public fixture'}
    monkeypatch.setattr(site_boundaries,'active_site',lambda *args:site)
    monkeypatch.setattr(site_boundaries,'sites',lambda:{387:site})
    def blocked(*args):raise RuntimeError('no connected walkable route')
    monkeypatch.setattr(ground,'route',blocked)


def test_mounted_ray_does_not_require_a_walkable_corridor(monkeypatch):
    fixture(monkeypatch,[[0,0],[20,0],[20,20],[0,20]],[10,10])
    tcp={'player':{'position':[2,2,60,0]},'tool':{'map':530,'heading_radians':0}}
    ray=ground.survey_ray(tcp,7,[387])
    assert ray['points']==[[2,2,60],[9,2,60]]
    assert not ray['ground_only'] and ray['boundary_guard']['whole_corridor_inside']
    with pytest.raises(RuntimeError,match='no connected walkable route'):
        ground.survey_detour(tcp,7,[387])


def test_concave_mounted_ray_uses_inward_heading_when_clipped(monkeypatch):
    polygon=[[0,0],[10,0],[10,10],[7,10],[7,3],[3,3],[3,10],[0,10]]
    fixture(monkeypatch,polygon,[1,3])
    tcp={'player':{'position':[1,8,20,0]},'tool':{'map':530,'heading_radians':0}}
    ray=ground.survey_ray(tcp,8,[387])
    assert ray['boundary_guard']['inward_recovery']
    assert abs(ray['heading_radians']+math.pi/2)<.001
    assert site_boundaries.inside_segment(polygon,*ray['points'])

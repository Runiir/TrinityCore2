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
        assert abs(route['points'][-1][2]-tcp['player']['position'][2])<=1.5
        assert math.dist(route['points'][-1][:2],tcp['player']['position'][:2])>=1.5


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')
def test_baari_side_slope_is_rejected_despite_small_endpoint_rise():
    tcp={'player':{'position':[-3271.083251953125,901.8927001953125,35.43161392211914,4.558446884155273]},
         'tool':{'map':530,'heading_radians':4.538603782653809}}
    with pytest.raises(RuntimeError):ground.walk_plan(tcp,3.5,[391],allow_swimming=True)
    routes=escape.candidates(tcp,site_boundaries.sites()[391])
    assert not routes
    surface=ground.probe_surface(530,tcp['player']['position'])
    assert surface['detail_slope_degrees']>35


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')
def test_trial64_slide_face_is_rejected_before_the_short_probe():
    start=[-3270.639404,900.496826,34.00499]
    with pytest.raises(RuntimeError,match='steep'):
        ground.safe_walk_segment(530,start,[-3269.2394,900.511,33.6])


def test_small_step_down_can_settle_before_accepting_the_probe(monkeypatch,tmp_path):
    from tools.client_compatibility import archaeology_inputs,travel_inputs
    from tools.client_compatibility.observation import transport
    position=[0.,0.,0.,0.];falls=iter([True,False])
    site={'id':1,'map':530,'source':'fixture','polygon':[[-10,-10],[10,-10],[10,10],[-10,10]]}
    class Observer:
        def poll(self):return {'position':position.copy()}
    class Inputs:
        def key(self,key,hold):position[:3]=[0,1.4,-.94]
    monkeypatch.setattr(escape.time,'sleep',lambda _:None)
    monkeypatch.setattr(transport,'Observer',Observer)
    monkeypatch.setattr(travel_inputs,'face',lambda *_:[])
    monkeypatch.setattr(escape.site_boundaries,'active_site',lambda *_:site)
    monkeypatch.setattr(escape,'candidates',lambda *_:[{'points':[[0,0,0],[0,3,0]],'water_polygons':0}])
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(
        {'in_world':True,'health_percent':100,'dead':False,'in_combat':False,'on_taxi':False},
        {'falling':next(falls),'swimming':False,'mounted':False,'flying':False}))
    _,route=escape.execute(Inputs(),{'player':{'position':position},'tool':{'map':530}},[1],tmp_path/'latest.png')
    assert route['after'][:3]==[0,1.4,-.94] and route['boundary_guard']['observed_after_inside']

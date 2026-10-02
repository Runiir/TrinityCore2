import copy
import json
import time
import pytest
from tools.client_compatibility import green_flight as flight,survey_landing,model_collision
from tools.client_compatibility import site_boundaries,validate_travel
from tools.client_compatibility.collision_recovery import Recovery


@pytest.fixture
def scene(monkeypatch):
    site={'id':1,'map':530,'polygon':[[-50,-50],[50,-50],[50,50],[-50,50]]}
    monkeypatch.setattr(site_boundaries,'active_site',lambda *a:site)
    monkeypatch.setattr(site_boundaries,'sites',lambda:{1:site})
    monkeypatch.setattr(survey_landing,'select',lambda *a,**kw:([7,0,0],{'selected':[7,0,0]}))
    monkeypatch.setattr(model_collision,'supporting_surface',lambda *a:{'highest_surface':4})
    monkeypatch.setattr(model_collision,'clear_body_segment',lambda *a:True)
    tcp={'player':{'position':[0,0,0,0]},'tool':{'map':530,'color':'green',
        'heading_radians':0,'seen_at':time.time(),'visible':True}}
    movement={'in_world':True,'health_percent':100,'dead':False,'in_combat':False,'on_taxi':False}
    extra={k:False for k in ['mounted','flying','falling','swimming','indoors','casting']}
    extra['digsite_ids']=[1]
    return tcp,movement,extra


def test_short_public_recovery_and_envelope(scene):
    route=flight.plan(*scene,None,'ground_routes_exhausted')
    assert route['legs'][0]['ceiling']==12
    flight.check_position(route['green_terrain_recovery'],[7,0,12])
    with pytest.raises(RuntimeError,match='envelope'):
        flight.check_position(route['green_terrain_recovery'],[24,0,12])


@pytest.mark.parametrize('condition',['combat','water','indoors','stale_tool','spent_budget','red'])
def test_unsafe_or_non_green_recovery_is_rejected(scene,condition):
    tcp,movement,extra=copy.deepcopy(scene);recovery=None
    if condition=='combat':movement['in_combat']=True
    if condition in ['water','indoors']:extra['swimming' if condition=='water' else 'indoors']=True
    if condition=='stale_tool':tcp['tool']['seen_at']-=30
    if condition=='spent_budget':recovery={'green_flights_used':2}
    if condition=='red':tcp['tool']['color']='red'
    with pytest.raises(RuntimeError):flight.plan(tcp,movement,extra,recovery,'ground_routes_exhausted')


def test_tall_or_occluded_obstacle_cannot_trigger_blind_flight(scene,monkeypatch):
    monkeypatch.setattr(model_collision,'supporting_surface',lambda *a:{'highest_surface':50})
    with pytest.raises(RuntimeError,match='height budget'):flight.plan(*scene,None,'ground_routes_exhausted')
    monkeypatch.setattr(model_collision,'supporting_surface',lambda *a:{'highest_surface':4})
    monkeypatch.setattr(model_collision,'clear_body_segment',lambda *a:False)
    with pytest.raises(RuntimeError,match='intersects'):flight.plan(*scene,None,'ground_routes_exhausted')


def test_receipt_requires_completed_matching_flight(scene,tmp_path):
    plan=flight.plan(*scene,None,'ground_routes_exhausted')
    route={'green_terrain_recovery':plan['green_terrain_recovery'],'mounted_travel_episode':'flight',
        'dry_unmounted_arrival':True,'after':[7,0,0]}
    (tmp_path/'flight').mkdir()
    child={'completed':True,'plan':plan,'steps':[{'facts':{'position':[7,0,12]}}]}
    target=tmp_path/'flight/episode.json';target.write_text(json.dumps(child))
    validate_travel.validate_green_recovery(route,tmp_path)
    child['completed']=False;target.write_text(json.dumps(child))
    with pytest.raises(ValueError,match='completed matching'):validate_travel.validate_green_recovery(route,tmp_path)
    with pytest.raises(ValueError,match='invalid authorized'):validate_travel.validate_green_recovery({},tmp_path)


def test_flight_budget_survives_restored_ground_progress():
    recovery=Recovery()
    step={'index':0,'action':'forward_short','tcp':{'player':{'position':[0,0,0]}},
        'input':{'hold_seconds':None,'ground_route':{'green_terrain_recovery':{'schema':'green_terrain_recovery_v1'}}}}
    recovery.update([step],{'player':{'position':[7,0,0]}})
    recovery.update([step],{'player':{'position':[7,0,0]}})
    assert recovery.for_action('forward_short')['green_flights_used']==1
    assert recovery.for_action('survey') is None


@pytest.mark.parametrize('failure',[None,'terrain','unrelated'])
def test_normal_green_stays_on_foot_and_only_terrain_failure_can_fly(scene,tmp_path,monkeypatch,failure):
    from PIL import Image
    from tools.client_compatibility import archaeology_inputs as inputs,ground_navigation
    from tools.client_compatibility.ground_escape import TerrainBlocked
    tcp,_,extra=scene;path=tmp_path/'frame.png';Image.new('RGB',(1,1)).save(path)
    monkeypatch.setattr(inputs.ctl,'Input',lambda:object())
    monkeypatch.setattr(inputs.travel,'decode_image',lambda image:extra)
    monkeypatch.setattr(inputs.time,'sleep',lambda seconds:None)
    calls=[]
    def walk(*args,**kwargs):
        calls.append('walk')
        if failure=='terrain':raise TerrainBlocked('all safe ground probes exhausted')
        if failure=='unrelated':raise RuntimeError('lost owned observations')
        return .5,{'walking':True}
    def fly(*args):calls.append('flight');return None,{'green_terrain_recovery':True}
    monkeypatch.setattr(ground_navigation,'walk',walk)
    monkeypatch.setattr(flight,'execute',fly)
    if failure=='unrelated':
        with pytest.raises(RuntimeError,match='lost owned'):inputs.execute('forward_short',tcp,path,mounted_moves=True)
        assert calls==['walk']
    else:
        inputs.execute('forward_short',tcp,path,mounted_moves=True)
        assert calls==(['walk','flight'] if failure=='terrain' else ['walk'])

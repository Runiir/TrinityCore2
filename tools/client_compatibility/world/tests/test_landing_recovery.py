from tools.client_compatibility import landing_recovery as recovery
from tools.client_compatibility import site_boundaries
import math
import pytest


def test_alternative_landing_respects_concave_boundary_and_ground_connection(monkeypatch):
    site={'id':377,'map':530,'polygon':[[-10,-10],[10,-10],[10,10],[2,10],[2,2],[-10,2]]}
    monkeypatch.setattr(recovery.site_boundaries,'sites',lambda:{377:site})
    calls=[]
    def flat(map_id,point,radius,start):
        calls.append((map_id,start));return point
    monkeypatch.setattr(recovery.ground_navigation,'landing_point',flat)
    facts={'map':530,'position':[0,0,9,0]};origin=[-3,0,0]
    point,bounds=recovery.alternative(facts,{'digsite_ids':[377]},{'position':[0,0,0],'ground_connection_origin':origin})
    assert bounds==[site] and math.dist(point[:2],facts['position'][:2])>=4
    assert site_boundaries.inside_segment(site['polygon'],facts['position'],point)
    assert calls and all(c==(530,origin) for c in calls)
    monkeypatch.setattr(recovery.ground_navigation,'landing_point',lambda *a,**kw:[100,100,0])
    with pytest.raises(RuntimeError):recovery.alternative(facts,{'digsite_ids':[377]},{'position':[0,0,0]})


def test_trial52_roof_contact_is_not_ground_arrival():
    from tools.client_compatibility import travel_trial,travel_policy
    facts=dict(map=530,position=[-841.319580078125,7606.60009765625,58.38827133178711,4.4956],transferring=False)
    leg=dict(mode='flight',map=530,position=[-840.99469,7605.43457,46.9462395],
        ceiling=230,arrival_radius=3,landing_height_tolerance=2)
    movement=dict(in_world=True,dead=False,in_combat=False,on_taxi=False)
    extra=dict(casting=False,mounted=True,flying=False,falling=False)
    state=travel_trial.state(leg,movement,extra,facts,{'nodes':[]})
    assert not state['near_destination'] and not state['destination_reached']
    assert travel_policy.model_state(state)['location']=='along route'
    assert travel_policy.label(state)=='takeoff'
    assert recovery.wrong_floor(facts,extra,leg)
    extra['flying']=True
    assert not recovery.wrong_floor(facts,extra,leg)
    assert travel_trial.state(leg,movement,extra,facts,{'nodes':[]})['near_destination']


def test_trial55_pillar_slide_still_requires_wrong_floor_escape():
    leg=dict(map=530,position=[-230.654724,3051.86646,-62.0737801],
        arrival_radius=3,landing_height_tolerance=2,landing_avoidance_frozen=True)
    facts=dict(map=530,position=[-227.19841,3049.65576,-24.85821,2.598])
    extra=dict(mounted=True,flying=False,falling=False)
    assert math.dist(facts['position'][:2],leg['position'][:2])>3
    assert recovery.wrong_floor(facts,extra,leg)
    leg['landing_avoidance_frozen']=False
    assert not recovery.wrong_floor(facts,extra,leg)


def test_trial67_grounded_below_target_also_needs_an_alternative_landing():
    leg=dict(map=530,position=[-3265.8667,992.533203,50.327755],arrival_radius=1.5,
        landing_height_tolerance=2,landing_avoidance_frozen=True)
    facts=dict(map=530,position=[-3266.5732421875,990.7905883789062,46.334110260009766,1.8284])
    extra=dict(mounted=True,flying=False,falling=False)
    assert recovery.wrong_floor(facts,extra,leg)
    assert not recovery.wrong_floor(facts,{**extra,'flying':True},leg)


def test_trial55_correct_floor_slide_needs_short_ground_adjustment():
    from tools.client_compatibility import ground_landing
    leg=dict(map=530,position=[-230.654724,3051.86646,-62.0737801],
        arrival_radius=3,landing_height_tolerance=2,landing_avoidance_frozen=True)
    facts=dict(map=530,position=[-232.576263,3047.990479,-61.541405,.5309])
    extra=dict(mounted=True,flying=False,falling=False,swimming=False)
    assert ground_landing.needed(facts,extra,leg)
    assert not recovery.wrong_floor(facts,extra,leg)
    extra['flying']=True
    assert not ground_landing.needed(facts,extra,leg)


def test_trial55_ground_adjustment_physically_enters_arrival_radius(monkeypatch,tmp_path):
    from tools.client_compatibility import ground_landing,archaeology_inputs,travel_inputs
    position=[-232.576263,3047.990479,-61.541405,.5309]
    goal=[-230.654724,3051.86646,-62.0737801]
    leg=dict(map=530,position=goal,arrival_radius=3,landing_height_tolerance=2,landing_avoidance_frozen=True)
    class Observer:
        def poll(self):return {'map':530,'position':position.copy()}
    class Inputs:
        def key(self,key,hold):
            assert key=='w'
            position[0]+=math.cos(position[3])*hold*14
            position[1]+=math.sin(position[3])*hold*14
    def face(_,observer,target):
        position[3]=math.atan2(target[1]-position[1],target[0]-position[0]);return []
    monkeypatch.setattr(ground_landing.time,'sleep',lambda _:None)
    monkeypatch.setattr(travel_inputs,'face',face)
    monkeypatch.setattr(ground_landing.ground_navigation,'route',lambda *_:{'points':[position[:3],goal[:]]})
    monkeypatch.setattr(ground_landing.site_boundaries,'sites',lambda:{})
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(
        {'in_world':True,'dead':False,'in_combat':False,'on_taxi':False,'health_percent':100},
        {'mounted':True,'flying':False,'falling':False,'swimming':False,'digsite_ids':[]}))
    result=ground_landing.finish(Inputs(),leg,Observer(),tmp_path/'latest.png')
    assert math.dist(result['after']['position'][:2],goal[:2])<3
    assert result['physical_keys'] and len(result['observed_positions'])>=2


@pytest.mark.skipif(not (recovery.ground_navigation.lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')
def test_trial52_roof_escape_keeps_the_original_floor_component():
    facts={'map':530,'position':[-841.319580078125,7606.60009765625,58.38827133178711,4.4956]}
    leg={'position':[-840.99469,7605.43457,46.9462395],
         'ground_connection_origin':[-837.2716674804688,7626.10205078125,46.15624237060547]}
    point,bounds=recovery.alternative(facts,{'digsite_ids':[365]},leg)
    assert point[2]<50 and math.dist(point[:2],facts['position'][:2])>=4
    assert bounds and site_boundaries.inside_segment(bounds[0]['polygon'],facts['position'],point)

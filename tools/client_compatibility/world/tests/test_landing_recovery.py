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


@pytest.mark.skipif(not (recovery.ground_navigation.lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private navmesh helper is absent')
def test_trial52_roof_escape_keeps_the_original_floor_component():
    facts={'map':530,'position':[-841.319580078125,7606.60009765625,58.38827133178711,4.4956]}
    leg={'position':[-840.99469,7605.43457,46.9462395],
         'ground_connection_origin':[-837.2716674804688,7626.10205078125,46.15624237060547]}
    point,bounds=recovery.alternative(facts,{'digsite_ids':[365]},leg)
    assert point[2]<50 and math.dist(point[:2],facts['position'][:2])>=4
    assert bounds and site_boundaries.inside_segment(bounds[0]['polygon'],facts['position'],point)

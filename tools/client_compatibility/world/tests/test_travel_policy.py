from tools.client_compatibility import travel_policy,travel_trial


def test_public_route_arrival_is_not_a_taxi_menu_or_a_nearby_wrong_floor():
    leg={'mode':'taxi','map':0,'position':[100,200,20],'destination':45}
    movement={'in_world':True,'dead':False,'in_combat':False,'on_taxi':False}
    extra=dict(casting=False,mounted=False,flying=False,falling=False)
    facts=dict(position=[100,200,60,0],map=0,transferring=False)
    s=travel_trial.state(leg,movement,extra,facts,{'nodes':[{'id':45}]})
    assert not s['destination_reached'] and travel_policy.label(s)=='taxi'
    facts['position'][2]=20
    s=travel_trial.state(leg,movement,extra,facts,{'nodes':[]})
    assert s['destination_reached'] and travel_policy.label(s)=='arrived'


def test_travel_safety_waits_on_taxi_or_during_transfer():
    s=dict(mode='portal',available=False,casting=False,on_taxi=False)
    assert travel_policy.label(s)=='observe'
    s.update(available=True,on_taxi=True)
    assert travel_policy.label(s)=='observe'


def test_grounded_confirmed_flight_arrival_does_not_request_another_climb():
    leg={'mode':'flight','map':0,'position':[100,200,20],'ceiling':230}
    movement={'in_world':True,'dead':False,'in_combat':False,'on_taxi':False}
    extra=dict(casting=False,mounted=True,flying=False,falling=False)
    facts=dict(position=[107,200,20,0],map=0,transferring=False)
    s=travel_trial.state(leg,movement,extra,facts,{'nodes':[]})
    assert s['destination_reached'] and s['near_destination']
    assert travel_policy.label(s)=='dismount'
    extra['mounted']=False
    s=travel_trial.state(leg,movement,extra,facts,{'nodes':[]})
    assert travel_policy.label(s)=='arrived'

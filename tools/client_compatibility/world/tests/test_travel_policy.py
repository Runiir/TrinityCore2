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

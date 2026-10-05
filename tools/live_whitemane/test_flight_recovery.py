import copy
from tools.client_compatibility import travel_policy
from tools.live_whitemane import flight
from tools.live_whitemane.smooth_move import GroundContact


def observation(north, *, flying=False, mounted=True):
    return {'observed_at':1, 'movement':{
        'in_world':True, 'health_percent':100, 'dead':False,
        'in_combat':False, 'on_taxi':False, 'facing_radians':0},
        'archaeology':{'world':{'instance':1,'north':north,'west':0},
            'casting':False, 'mounted':mounted, 'flying':flying,
            'falling':False, 'grounded':not flying}}


def test_terrain_contact_releases_input_then_requests_a_new_model_choice(monkeypatch, tmp_path):
    ground=observation(0)
    air=observation(0,flying=True)
    contact=observation(40)
    near_air=observation(100,flying=True)
    near_ground=observation(100)
    arrived=observation(100,mounted=False)
    observations=iter([ground,air,air,contact,air,air,near_air,
                       near_air,near_ground,near_ground,arrived,arrived])
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    monkeypatch.setattr(flight,'observe',lambda _:copy.deepcopy(next(observations)))
    monkeypatch.setattr(flight.time,'sleep',lambda _:None)
    requests=[]
    def choose(state, which, physical_state):
        requests.append(copy.deepcopy(physical_state))
        return travel_policy.label(physical_state),{},state,{}
    monkeypatch.setattr(flight,'choose',choose)
    monkeypatch.setattr(flight.inputs,'execute',lambda *args:{'arguments':args[-1]})
    from tools.live_whitemane import archaeology_probe
    monkeypatch.setattr(archaeology_probe,'command',lambda text:[{'command':text}])
    calls=[]
    def walk(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1:raise GroundContact(contact)
        return []
    monkeypatch.setattr(flight,'walk',walk)
    monkeypatch.setattr(flight,'descend',lambda *args,**kwargs:[])
    step={}
    flight.fly(tmp_path,ground,{'endpoint':arrived['archaeology']['world'],'site_id':183},step)
    phases=step['travel_decisions']
    assert [p['action'] for p in phases]==['takeoff','cruise','takeoff','cruise','land','dismount','arrived']
    assert phases[1]['outcome']=='terrain_contact_reobserve'
    assert phases[1]['inputs_released']
    assert requests[2]['mounted'] and not requests[2]['flying']
    assert not requests[2]['at_route_height']
    assert len(calls)==2
    assert phases[2]['inputs'][0]['arguments']['hold']==2

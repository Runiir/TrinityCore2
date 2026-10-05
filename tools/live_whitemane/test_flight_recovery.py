import copy
import pytest
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
    ground=observation(0);ground['owned_pose']={'height_yards':100}
    air=observation(0,flying=True)
    air['owned_pose']={'height_yards':100}
    contact=observation(40);contact['owned_pose']={'height_yards':100}
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
    calls=[]
    def walk(*args,**kwargs):
        calls.append(kwargs)
        if len(calls)==1:raise GroundContact(contact)
        return []
    monkeypatch.setattr(flight,'walk',walk)
    monkeypatch.setattr(flight,'descend',lambda *args,**kwargs:[])
    monkeypatch.setattr(flight.clearance,'plan',lambda *args,**kwargs:{'ceiling_yards':100})
    ascents=[]
    def ascend(*args,**kwargs):
        ascents.append(args[1])
        return []
    monkeypatch.setattr(flight,'ascend',ascend)
    step={}
    flight.fly(tmp_path,ground,{'endpoint':arrived['archaeology']['world'],'site_id':183},step)
    phases=step['travel_decisions']
    assert [p['action'] for p in phases]==['takeoff','cruise','takeoff','cruise','land','dismount','arrived']
    assert phases[1]['outcome']=='terrain_contact_reobserve'
    assert phases[1]['inputs_released']
    assert requests[2]['mounted'] and not requests[2]['flying']
    assert not requests[2]['at_route_height']
    assert len(calls)==2
    assert ascents==[100,100]
    assert not phases[2]['inputs']
    assert phases[-2]['inputs']==[{'arguments':{'key':'shift+space','hold':.15}}]


@pytest.mark.parametrize('mounted,action,error',[
    (False,'mount','mount input did not produce mounted state'),
    (True,'dismount','dismount input did not produce unmounted state')])
def test_failed_toggle_stops_after_one_press(monkeypatch,tmp_path,mounted,action,error):
    before=observation(0,mounted=mounted)
    before['owned_pose']={'height_yards':100}
    target={'instance':1,'north':100 if action=='mount' else 0,'west':0}
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    monkeypatch.setattr(flight,'observe',lambda _:copy.deepcopy(before))
    monkeypatch.setattr(flight.time,'sleep',lambda _:None)
    monkeypatch.setattr(flight.clearance,'plan',lambda *_ ,**__:{'ceiling_yards':100})
    monkeypatch.setattr(flight,'choose',lambda *_,**__:(action,{}, {},{}))
    inputs=[]
    def execute(title,kind,args):
        inputs.append((kind,args));return {'arguments':args}
    monkeypatch.setattr(flight.inputs,'execute',execute)
    with pytest.raises(RuntimeError,match=error):
        flight.fly(tmp_path,before,{'endpoint':target},{})
    assert inputs==[('key',{'key':'shift+space','hold':.15})]

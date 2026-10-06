import copy
import pytest
from tools.client_compatibility import travel_policy
from tools.live_whitemane import flight
from tools.live_whitemane.smooth_move import GroundContact


def fresh_observer(monkeypatch,rows):
    clock=[0];sequence=[0]
    monkeypatch.setattr(flight.time,'monotonic',lambda:clock[0])
    monkeypatch.setattr(flight.time,'sleep',lambda seconds:clock.__setitem__(0,clock[0]+seconds))
    def observe(_):
        row=copy.deepcopy(next(rows));sequence[0]+=1
        for section in ('movement','archaeology'):row[section]['sequence']=sequence[0]
        return row
    monkeypatch.setattr(flight,'observe',observe)


def observation(north, *, flying=False, mounted=True):
    return {'observed_at':1, 'movement':{
        'in_world':True, 'health_percent':100, 'dead':False,
        'in_combat':False, 'on_taxi':False, 'facing_radians':0},
        'archaeology':{'world':{'instance':1,'north':north,'west':0},
            'casting':False, 'mounted':mounted, 'flying':flying,
            'falling':False, 'grounded':not flying}}


@pytest.mark.parametrize('mode_transition',[False,True])
def test_terrain_contact_releases_input_then_requests_a_new_model_choice(monkeypatch, tmp_path,mode_transition):
    ground=observation(0);ground['owned_pose']={'height_yards':100}
    air=observation(0,flying=True)
    air['owned_pose']={'height_yards':100}
    contact=observation(40);contact['owned_pose']={'height_yards':100}
    near_air=observation(100,flying=True)
    near_ground=observation(100)
    arrived=observation(100,mounted=False)
    rows=[ground,air,air,contact,air,air,near_air,
          near_air,near_ground,near_ground,near_ground,arrived,arrived]
    if mode_transition:
        transitional=copy.deepcopy(ground)
        transitional['owned_pose'].update(height_yards=110,movement_mode_transition=True)
        rows.insert(0,transitional)
    observations=iter(rows)
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    fresh_observer(monkeypatch,observations)
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
    monkeypatch.setattr(flight.clearance,'plan',lambda *args,**kwargs:{
        'ceiling_yards':100,'takeoff_height_yards':100,
        'path':[{'north':0,'west':0,'height_yards':100,'along_yards':0},
                {'north':100,'west':0,'height_yards':100,'along_yards':100}]})
    ascents=[]
    def ascend(*args,**kwargs):
        ascents.append(args[1])
        return []
    monkeypatch.setattr(flight,'ascend',ascend)
    step={}
    flight.fly(tmp_path,ground,{'endpoint':arrived['archaeology']['world'],'site_id':183},step)
    phases=step['travel_decisions']
    if mode_transition:
        assert phases[0]['outcome']=='awaiting_synchronized_flight_facts'
        assert not phases[0]['inputs']
        phases=phases[1:]
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
    import itertools
    fresh_observer(monkeypatch,itertools.repeat(before))
    monkeypatch.setattr(flight.clearance,'plan',lambda *_ ,**__:{
        'ceiling_yards':100,'takeoff_height_yards':100,'path':[]})
    monkeypatch.setattr(flight,'choose',lambda *_,**__:(action,{}, {},{}))
    inputs=[]
    def execute(title,kind,args):
        inputs.append((kind,args));return {'arguments':args}
    monkeypatch.setattr(flight.inputs,'execute',execute)
    with pytest.raises(RuntimeError,match=error):
        flight.fly(tmp_path,before,{'endpoint':target},{})
    assert inputs==[('key',{'key':'shift+space','hold':.15})]


def test_combat_landing_uses_laya_phases_and_only_toggles_on_ground(monkeypatch,tmp_path):
    air=observation(0,flying=True);ground=observation(0);foot=observation(0,mounted=False)
    for r in (air,ground,foot):r['movement']['in_combat']=True
    observations=iter([air,ground,ground,ground,foot,foot])
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    fresh_observer(monkeypatch,observations)
    monkeypatch.setattr(flight,'choose',lambda state,which,physical_state:(travel_policy.label(physical_state),{},state,{}))
    descents=[]
    def descend(folder,target,**kwargs):descents.append((target,kwargs));return []
    monkeypatch.setattr(flight,'descend',descend)
    monkeypatch.setattr(flight.inputs,'execute',lambda *args:{'arguments':args[-1]})
    step={};target=air['archaeology']['world']
    flight.fly(tmp_path,air,{'endpoint':target},step,combat_landing=True)
    assert [p['action'] for p in step['travel_decisions']]==['land','dismount','arrived']
    assert descents==[(target,{'site_id':None,'allow_combat':True})]
    assert step['travel_decisions'][1]['inputs'][0]['arguments']['key']=='shift+space'
    with pytest.raises(RuntimeError,match='current position'):
        flight.fly(tmp_path,air,{'endpoint':dict(target,north=10)},{},combat_landing=True)


def test_interrupted_digsite_landing_surveys_on_ground_instead_of_remounting(monkeypatch,tmp_path):
    ground=observation(12.24);foot=observation(12.24,mounted=False)
    for r in (ground,foot):r['archaeology'].update(site_id=315,can_survey=True)
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    fresh_observer(monkeypatch,iter([ground,ground,ground,foot,foot]))
    monkeypatch.setattr(flight,'choose',lambda state,which,physical_state:
        (travel_policy.label(physical_state),{},state,{}))
    monkeypatch.setattr(flight.inputs,'execute',lambda *args:{'arguments':args[-1]})
    monkeypatch.setattr(flight.clearance,'plan',lambda *_ ,**__:pytest.fail('ground facts do not need height'))
    step={}
    flight.fly(tmp_path,ground,{'endpoint':{'instance':1,'north':0,'west':0},
        'site_id':315,'resume_to_survey_on_ground':True},step)
    assert step['travel_decisions']==[]
    assert step['grounded_Survey_auto_dismount_handoff']['mounted']
    assert step['grounded_digsite_reobserve']['old_endpoint_distance_yards']==12.24
    assert not step['grounded_digsite_reobserve']['destination_arrival_confirmed']


def test_digsite_landing_drift_does_not_start_another_takeoff(monkeypatch,tmp_path):
    air=observation(.49,flying=True);ground=observation(1.2);foot=observation(1.2,mounted=False)
    for r in (air,ground,foot):r['archaeology'].update(site_id=315,can_survey=True)
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    fresh_observer(monkeypatch,iter([air,ground,ground,ground,foot,foot]))
    monkeypatch.setattr(flight,'choose',lambda state,which,physical_state:
        (travel_policy.label(physical_state),{},state,{}))
    monkeypatch.setattr(flight.inputs,'execute',lambda *args:{'arguments':args[-1]})
    monkeypatch.setattr(flight,'descend',lambda *_,**__:[])
    monkeypatch.setattr(flight.clearance,'plan',lambda *_ ,**__:pytest.fail('do not plan another ascent after landing'))
    step={}
    flight.fly(tmp_path,air,{'endpoint':{'instance':1,'north':0,'west':0},
        'site_id':315,'arrival_tolerance_yards':.5},step)
    assert [p['action'] for p in step['travel_decisions']]==['land']
    assert step['grounded_digsite_reobserve']['old_endpoint_distance_yards']==1.2


@pytest.mark.parametrize('digsite_descent',[False,True])
def test_grounded_descent_accepts_two_fresh_facts_past_estimated_endpoint(monkeypatch,tmp_path,digsite_descent):
    from . import smooth_move
    from tools.client_compatibility import native_input_adapter
    from types import SimpleNamespace
    (tmp_path/'run').mkdir();monkeypatch.setattr(smooth_move.runtime,'ROOT',tmp_path)
    monkeypatch.setattr(smooth_move.inputs,'focus',lambda _: {})
    events=[];sequence=[0]
    class Sender:
        initialization={}
        X=SimpleNamespace(KeyPress='press',KeyRelease='release')
        XK=SimpleNamespace(string_to_keysym=lambda key:key)
        def _keycode(self,key):return key,0
        def _send(self,*args):events.append(args)
        def close(self):pass
    monkeypatch.setattr(native_input_adapter,'Input',Sender)
    def observe(_):
        sequence[0]+=1;r=observation(12.24,flying=digsite_descent and sequence[0]==1)
        r['movement']['sequence']=r['archaeology']['sequence']=sequence[0]
        r['archaeology'].update(can_survey=True,site_id=315)
        return r
    monkeypatch.setattr(smooth_move,'observe',observe)
    monkeypatch.setattr(smooth_move.time,'sleep',lambda _:None)
    monkeypatch.setattr(smooth_move,'check_point',lambda *_:None)
    rows=smooth_move.descend(tmp_path,{'instance':1,'north':0,'west':0},
        site_id=315 if digsite_descent else None)
    assert len(rows)==(3 if digsite_descent else 2) and all(r['grounded'] for r in rows[-2:])
    assert events==([('press','x'),('release','x')] if digsite_descent else [])

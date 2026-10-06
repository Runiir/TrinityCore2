import copy
import math
import pytest
from . import terrain_context,clearance,fast_waypoint,flight,laya_ui
from .test_farm_loop import row
from .test_fast_waypoint import setup_route
from .test_flight_recovery import observation


def test_outdoor_WMO_can_still_have_a_roof_and_blocked_ascent(monkeypatch):
    r=row();r['owned_pose']={'height_yards':177.3897}
    monkeypatch.setattr(terrain_context.model_collision,'column',lambda *_:{
        'support_height':177.3911,'collision_height':186.2662,'area':{'mogp_flags':9}})
    monkeypatch.setattr(terrain_context.terrain_geometry,'height',lambda *_:152.0703)
    checks=[]
    def clear(_,a,b):checks.append((a,b));return b[2]==a[2]
    monkeypatch.setattr(terrain_context.model_collision,'clear_body_segment',clear)
    facts=terrain_context.facts(r,{'instance':1,'north':100,'west':0})
    assert facts['departure_floor_agrees'] and not facts['reference_WMO_indoors']
    assert facts['reference_support_is_raised']
    assert facts['observed_height_above_reference_raw_terrain_yards']==pytest.approx(25.3194)
    assert not facts['reference_climb_clear'] and facts['reference_forward_clear']
    assert facts['live_asset_match_verified'] is False
    assert checks[-1][1][0]==8


def test_missing_reference_data_is_unknown_without_fabricating_clearance(monkeypatch):
    r=row();r['owned_pose']={'height_yards':10}
    def absent(*_):raise FileNotFoundError('missing reference tile')
    monkeypatch.setattr(terrain_context.model_collision,'column',absent)
    facts=terrain_context.facts(r)
    assert not facts['available'] and 'reference_climb_clear' not in facts
    assert 'missing reference tile' in facts['reference_error']
    r['owned_pose']=None
    assert not terrain_context.facts(r)['available']


def path_setup(monkeypatch):
    r=row();r['archaeology'].update(can_survey=True,site_id=179,flying=False)
    r['owned_pose']={'height_yards':10}
    monkeypatch.setattr(terrain_context.boundaries,'sites',lambda:{'179':{
        'map':1,'polygon':[[-10,-10],[60,-10],[60,60],[-10,60]]}})
    monkeypatch.setattr(terrain_context.model_collision,'clear_body_segment',lambda *_:True)
    monkeypatch.setattr(terrain_context.ground_navigation,'route',lambda *_:{
        'complete':True,'ground_only':True,'points':[[0,0,10],[0,5,10],[40,5,10]]})
    return r,{'instance':1,'north':40,'west':5}


def test_detour_prefix_keeps_original_destination_and_stays_in_the_site(monkeypatch):
    r,target=path_setup(monkeypatch)
    route=terrain_context.detour(r,target)
    assert route['available'] and route['length_yards']==24
    assert route['original_destination']==target and not route['prefix_reaches_original_destination']
    assert [(p['north'],p['west']) for p in route['points']]==[(0,5),(19,5)]


def test_later_wall_keeps_a_checked_prefix_without_claiming_destination_arrival(monkeypatch):
    r,target=path_setup(monkeypatch)
    monkeypatch.setattr(terrain_context.model_collision,'clear_body_segment',
        lambda _,start,end:end[0]<=10)
    route=terrain_context.detour(r,target,maximum_yards=150,allow_clear_prefix=True)
    assert route['available'] and route['points'][-1]['north']==0
    assert route['points'][-1]['west']==5
    assert route['original_destination']==target
    assert not route['reference_path_complete'] and not route['prefix_reaches_original_destination']
    assert route['stopped_before_unchecked_continuation']


def test_approach_requires_measured_departure_floor_agreement(monkeypatch):
    r,target=path_setup(monkeypatch);r['archaeology']['grounded']=True
    monkeypatch.setattr(terrain_context,'facts',lambda *_:{'departure_floor_agrees':False})
    monkeypatch.setattr(terrain_context,'detour',lambda *_ ,**__:pytest.fail('other floor must not route'))
    assert not terrain_context.approach(r,target)['available']


def test_known_artifact_height_routes_to_that_floor_and_rejects_a_roof_projection(monkeypatch):
    r,target=path_setup(monkeypatch);target['height_yards']=0
    calls=[]
    def route(_,start,goal):
        calls.append(goal)
        return {'complete':True,'ground_only':True,'points':[start,[40,5,10]]}
    monkeypatch.setattr(terrain_context.ground_navigation,'route',route)
    result=terrain_context.detour(r,target)
    assert calls==[[40,5,0]] and not result['available']
    assert 'artifact to a different floor' in result['reference_error']


@pytest.mark.parametrize('bad',['other_floor','wall','outside_site'])
def test_detour_does_not_admit_a_different_floor_wall_or_outside_segment(monkeypatch,bad):
    r,target=path_setup(monkeypatch)
    if bad=='other_floor':
        monkeypatch.setattr(terrain_context.ground_navigation,'route',lambda *_:{
            'complete':True,'ground_only':True,'points':[[0,0,20],[40,5,20]]})
    elif bad=='wall':monkeypatch.setattr(terrain_context.model_collision,'clear_body_segment',lambda *_:False)
    else:monkeypatch.setattr(terrain_context.boundaries,'sites',lambda:{'179':{
        'map':1,'polygon':[[-1,-1],[2,-1],[2,2],[-1,2]]}})
    route=terrain_context.detour(r,target)
    assert not route['available'] and route.get('reference_error')


@pytest.mark.parametrize('automatic',[False,True])
def test_retained_detour_passes_a_corner_with_one_input_device_and_model_intent(monkeypatch,tmp_path,automatic):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,0)
    r['archaeology'].update(flying=False,mounted=False,grounded=True)
    r['archaeology']['world']['west']=5
    r['movement']['facing_radians']=-math.pi/2
    count=[0]
    def observe(_):
        count[0]+=1;now[0]+=.1;controllers[0].tick()
        fresh=copy.deepcopy(r);fresh['observed_at']=now[0]
        fresh['movement'].update(sequence=count[0],client_uptime_ms=count[0]*100)
        fresh['archaeology']['sequence']=count[0]
        if count[0]>=5:fresh['archaeology']['world']['west']=0
        if count[0]>=5:fresh['movement']['facing_radians']=0
        if count[0]>=8:fresh['archaeology']['world']['north']=5
        return fresh
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    points=[{'instance':1,'north':0,'west':0},{'instance':1,'north':5,'west':0}]
    target={'instance':1,'north':10,'west':0} if automatic else points[-1]
    if automatic:
        monkeypatch.setattr(terrain_context,'approach',lambda row,goal:{'available':True,
            'points':points,'prefix_reaches_original_destination':False,'original_destination':goal})
    result=fast_waypoint.walk(tmp_path,target,tolerance=.5,
        guidance={} if automatic else {'ground_route':points},
        approved_intent=('forward_long' if automatic else 'follow_detour',{}, {},{}))
    assert result[-1]['outcome']==('ground_route_prefix_reached' if automatic else 'waypoint_arrived')
    assert result[-1]['retained_original_destination']==target and not calls
    assert events.count(('press','Up'))==events.count(('release','Up'))==1
    assert events.count(('button_press',3))==events.count(('button_release',3))==1


def test_blocked_ascent_is_given_to_laya_before_repeating_takeoff(monkeypatch,tmp_path):
    start=observation(0,flying=True);start['owned_pose']={'height_yards':10}
    moved=observation(4,flying=True);moved['owned_pose']={'height_yards':10}
    frames=iter([start,moved,moved]);monkeypatch.setattr(flight,'observe',lambda _:copy.deepcopy(next(frames)))
    monkeypatch.setattr(flight.runtime,'ROOT',tmp_path)
    monkeypatch.setattr(flight.clearance,'plan',lambda *_ ,**__: {
        'takeoff_height_yards':20,'reference_departure_column_clear':False})
    from . import escape_route
    alternatives={'step_left':{'target':{'instance':1,'north':4,'west':0},'reference_collision_clear':True}}
    monkeypatch.setattr(escape_route,'candidates',lambda *_:alternatives)
    monkeypatch.setattr(terrain_context,'facts',lambda *_:{'reference_climb_clear':False,'live_asset_match_verified':False})
    monkeypatch.setattr(terrain_context,'detour',lambda *_:{'available':False})
    monkeypatch.setattr(terrain_context,'move',lambda folder,row,action,*args: [{'Laya_selected':action}])
    monkeypatch.setattr(flight,'ascend',lambda *_ ,**__:pytest.fail('Laya did not select ascent'))
    calls=[]
    def choose(state,instructions,options):
        calls.append(state);assert not state['terrain']['reference_climb_clear']
        assert {'step_left','takeoff','cruise','land'}<=options.keys()
        return 'step_left',{},{}
    monkeypatch.setattr(laya_ui,'choose',choose)
    monkeypatch.setattr(flight,'choose',lambda *_ ,**__:('arrived',{}, {},{}))
    step={};flight.fly(tmp_path,start,{'endpoint':{'instance':1,'north':10,'west':0}},step)
    assert len(calls)==1 and step['travel_decisions'][0]['action']=='step_left'

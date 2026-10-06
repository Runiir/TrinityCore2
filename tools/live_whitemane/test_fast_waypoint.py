import copy
import math
import pytest
from types import SimpleNamespace
from . import fast_waypoint,sticky_input,camera_input,recovery
from .test_flight_recovery import observation


def setup_route(monkeypatch,tmp_path,north=6.398):
    (tmp_path/'run').mkdir();monkeypatch.setattr(fast_waypoint.runtime,'ROOT',tmp_path)
    r=observation(north,flying=True)
    r.update(source='test_public_observation',channel_ages={'M':.075},farm_ui={'move_speeds':{'flight':29.26}})
    r['movement'].update(speed=0,position_available=True,facing_radians=math.pi)
    r['archaeology'].update(swimming=False)
    now=[0.0];events=[];controllers=[]
    sender=SimpleNamespace(X=SimpleNamespace(KeyPress='press',KeyRelease='release',ButtonPress='button_press',ButtonRelease='button_release'),
        XK=SimpleNamespace(string_to_keysym=lambda x:x),_keycode=lambda x:(x,None),
        _send=lambda event,key:events.append((event,key)),close=lambda:None,initialization={},
        move=lambda x,y:None,relative=lambda x,y:events.append(('relative',(x,y))))
    monkeypatch.setattr(camera_input,'Input',lambda:sender)
    monkeypatch.setattr(fast_waypoint.inputs,'focus',lambda _: {})
    monkeypatch.setattr(fast_waypoint,'time',SimpleNamespace(time=lambda:now[0],monotonic=lambda:now[0],sleep=lambda _:None))
    def sticky(sender):
        controller=sticky_input.StickyInput(sender,clock=lambda:now[0],threaded=False)
        controllers.append(controller);return controller
    monkeypatch.setattr(fast_waypoint,'StickyInput',sticky)
    calls=[]
    def decide(*_,**__):
        calls.append(True);return 'cruise',{}, {},{}
    monkeypatch.setattr(fast_waypoint,'decision',decide)
    return r,now,events,controllers,calls


@pytest.mark.parametrize('approved',[False,True])
def test_stationary_near_arrival_retries_after_position_updates_with_a_measured_pulse(monkeypatch,tmp_path,approved):
    # The live failure stayed at 6.398 yards from a six-yard flight endpoint.
    # Its 33-ms pulses could disappear between client updates.
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        result=copy.deepcopy(r);result['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        result['archaeology']['sequence']=index[0];result['observed_at']=now[0]
        result['owned_pose']={'pitch_radians':0,'client_uptime_ms':index[0]*100}
        if index[0]>=6:result['archaeology']['world']['north']=4
        return result
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True,
        approved_intent=('cruise',{}, {},{}) if approved else None)
    assert rows[2]['calculated_pulse_seconds']==.1
    assert events.count(('press','Up'))==2
    assert rows[-1]['distance_yards']==4
    assert events.count(('button_press',3))==1 and events.count(('button_release',3))==1
    assert all(key not in ('Left','Right') for event,key in events if event=='press')
    assert len(calls)==(0 if approved else 1)


@pytest.mark.parametrize('interrupt,error',[
    ('survey','new Survey'),('falling','terrain falling')])
def test_changed_route_or_terrain_releases_forward_and_camera(monkeypatch,tmp_path,interrupt,error):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,100)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        row=copy.deepcopy(r)
        row['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        row['archaeology'].update(sequence=index[0],successful_surveys=5)
        if index[0]>=4:
            if interrupt=='survey':row['archaeology']['successful_surveys']=6
            else:row['archaeology']['falling']=True
        row['observed_at']=now[0]
        row['owned_pose']={'pitch_radians':0,'client_uptime_ms':index[0]*100}
        return row
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    with pytest.raises(RuntimeError,match=error) as failed:
        fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True,
            guidance={'source':'Survey telescope'})
    assert events.count(('press','Up'))==1
    assert events.count(('release','Up'))==1
    assert events.count(('button_press',3))==1
    assert events.count(('button_release',3))==1
    assert len(calls)==1
    assert recovery.retryable(failed.value)


@pytest.mark.parametrize('initial_swimming',[True,False])
def test_water_entry_or_exit_releases_retained_movement_for_a_new_mode_choice(monkeypatch,tmp_path,initial_swimming):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,100)
    r['archaeology'].update(flying=False,mounted=False,grounded=not initial_swimming,swimming=initial_swimming)
    count=[0]
    def observe(_):
        count[0]+=1;now[0]+=.1;controllers[0].tick()
        fresh=copy.deepcopy(r);fresh['observed_at']=now[0]
        fresh['movement'].update(sequence=count[0],client_uptime_ms=count[0]*100)
        fresh['archaeology']['sequence']=count[0]
        if initial_swimming:fresh['owned_pose']={'pitch_radians':0,'client_uptime_ms':count[0]*100}
        if count[0]>=4:fresh['archaeology'].update(swimming=not initial_swimming,grounded=initial_swimming)
        return fresh
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    with pytest.raises(RuntimeError,match='swimming changed') as failed:
        fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},
            approved_intent=('forward_long',{}, {},{}))
    assert not calls and recovery.retryable(failed.value)
    assert events.count(('press','Up'))==events.count(('release','Up'))==1
    assert events.count(('button_press',3))==events.count(('button_release',3))==1


def test_a_new_artifact_interrupts_the_retained_approach_for_a_model_choice(monkeypatch,tmp_path):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,100)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        row=copy.deepcopy(r)
        row['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        row['archaeology']['sequence']=index[0];row['observed_at']=now[0]
        row['owned_pose']={'pitch_radians':0,'client_uptime_ms':index[0]*100}
        if index[0]>=4:row['farm_ui']['soft_interact']={'name':next(iter(fast_waypoint.FIND_NAMES))}
        return row
    def decide(*_,**__):
        calls.append(True);return 'loot',{}, {},{}
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    monkeypatch.setattr(fast_waypoint,'decision',decide)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True,
        approved_intent=('cruise',{}, {},{}))
    assert len(calls)==1 and rows[-1]['action']=='loot'
    assert events.count(('press','Up'))==1 and events.count(('release','Up'))==1
    assert events.count(('button_release',3))==1


def test_steep_descent_keeps_forward_held_with_delayed_public_map_samples(monkeypatch,tmp_path):
    # Live step 34 descended at -1.42 radians. Full speed was incorrectly
    # subtracted from horizontal distance, causing repeated 33-ms presses.
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,16.4)
    r['movement']['speed']=29.26;r['farm_ui']['frame_rate']=30
    from . import flight_path
    monkeypatch.setattr(flight_path,'aim',lambda *_:{'pitch_radians':-1.42})
    count=[0]
    def observe(_):
        count[0]+=1;now[0]+=.1;controllers[0].tick()
        fresh=copy.deepcopy(r);fresh['observed_at']=now[0]
        fresh['movement'].update(sequence=count[0],client_uptime_ms=count[0]*100)
        fresh['archaeology']['sequence']=count[0]
        fresh['owned_pose']={'pitch_radians':-1.42,'height_yards':100,'client_uptime_ms':count[0]*100}
        fresh['channel_ages']['A']=[.075,.175,.3,.375][count[0]%4]
        fresh['archaeology']['world']['north']=16.4-max(0,count[0]-2)*.44 if count[0]<18 else 5.5
        if count[0]>=19:fresh['movement']['speed']=0
        return fresh
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    result=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True,
        guidance={'flight_path':[{}]},approved_intent=('cruise',{}, {},{}))
    assert result[-1]['outcome']=='waypoint_arrived' and not calls
    assert events.count(('press','Up'))==events.count(('release','Up'))==1
    assert max(x['horizontal_progress_speed'] for x in result if 'horizontal_progress_speed' in x)<5


def test_short_on_foot_fall_releases_forward_then_resumes_the_same_intent(monkeypatch,tmp_path):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,20)
    r['archaeology'].update(flying=False,mounted=False,grounded=True)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        row=copy.deepcopy(r);row['observed_at']=now[0]
        row['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        row['archaeology'].update(sequence=index[0],falling=index[0] in (4,5))
        if index[0]>=7:row['archaeology']['world']['north']=0
        return row
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},tolerance=.5,
        approved_intent=('forward_long',{}, {},{}))
    assert sum(r.get('outcome')=='awaiting_ground' for r in rows)==2
    assert events.count(('press','Up'))==2 and events.count(('release','Up'))==2
    assert not calls and rows[-1]['outcome']=='waypoint_arrived'


def test_retained_input_survives_slow_but_valid_public_frames(monkeypatch,tmp_path):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,100)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        sequence=1+index[0]//10
        row=copy.deepcopy(r);row['observed_at']=now[0]
        row['movement'].update(sequence=sequence,client_uptime_ms=sequence*1000)
        row['archaeology']['sequence']=sequence
        row['owned_pose']={'pitch_radians':0,'client_uptime_ms':sequence*1000}
        if index[0]>=30:row['archaeology']['world']['north']=0
        return row
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True)
    assert rows[-1]['outcome']=='waypoint_arrived'
    assert controllers[0].interrupted is None
    assert events.count(('press','Up'))==1 and events.count(('release','Up'))==1
    assert events.count(('button_press',3))==1 and events.count(('button_release',3))==1
    assert len(calls)==1


def test_camera_probe_waits_for_public_mouse_look_activation(monkeypatch,tmp_path):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,20)
    r['farm_ui']['frame_rate']=1
    r['archaeology'].update(flying=False,mounted=False,grounded=True)
    r['movement']['facing_radians']=0
    count=[0];yaw=[0];sender=camera_input.Input()
    def relative(x,y):
        assert count[0]>=15
        events.append(('relative',(x,y)));yaw[0]-=x*.006
    sender.relative=relative
    def observe(_):
        count[0]+=1;now[0]+=.1;controllers[0].tick()
        fresh=copy.deepcopy(r);fresh['observed_at']=now[0]
        fresh['movement'].update(sequence=count[0],client_uptime_ms=count[0]*100,
            facing_radians=yaw[0])
        fresh['archaeology']['sequence']=count[0]
        fresh['farm_ui']['camera_input']={'mouselooking':3 in controllers[0].buttons and count[0]>=15,
            'right_down':3 in controllers[0].buttons and count[0]>=15}
        if count[0]>=23:fresh['archaeology']['world']['north']=0
        return fresh
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},tolerance=.5,
        approved_intent=('interact',{}, {},{}))
    assert not calls and rows[-1]['outcome']=='waypoint_arrived'
    assert sum(row.get('outcome')=='awaiting_camera_mouse_look' for row in rows)>=10
    assert events.count(('button_press',3))==events.count(('button_release',3))==1


def test_stationary_flight_pitch_feedback_does_not_deadlock_before_forward(monkeypatch,tmp_path):
    from . import flight_path
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,20)
    state={'actual_pitch':-1.2,'reported_pitch':-1.2,'pose_tick':0,'index':0,'forward_frames':0}
    sender=camera_input.Input()
    def relative(x,y):
        events.append(('relative',(x,y)));state['actual_pitch']-=y*.006
        if x:
            state['reported_pitch']=state['actual_pitch'];state['pose_tick']=state['index']*100
    sender.relative=relative
    monkeypatch.setattr(flight_path,'aim',lambda *_:{'pitch_radians':.8})
    def observe(_):
        state['index']+=1;now[0]+=.1;controllers[0].tick()
        row=copy.deepcopy(r);row['observed_at']=now[0]
        row['movement'].update(sequence=state['index'],client_uptime_ms=state['index']*100)
        row['archaeology']['sequence']=state['index']
        row['owned_pose']={'pitch_radians':state['reported_pitch'],'client_uptime_ms':state['pose_tick'],'height_yards':100}
        if 'Up' in controllers[0].held:
            state['forward_frames']+=1
            if state['forward_frames']>=2:row['archaeology']['world']['north']=0
        return row
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True,
        guidance={'flight_path':[{}]},approved_intent=('cruise',{}, {},{}))
    assert rows[-1]['outcome']=='waypoint_arrived' and now[0]<2
    assert abs(state['reported_pitch']-.8)<.1
    assert any(delta[0] and delta[1] for event,delta in events if event=='relative')
    assert events.count(('press','Up'))==events.count(('release','Up'))==1 and not calls

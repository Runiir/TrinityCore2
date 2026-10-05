import copy
import math
import pytest
from types import SimpleNamespace
from . import fast_waypoint,sticky_input,camera_input
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


def test_stationary_near_arrival_retries_after_position_updates_with_a_measured_pulse(monkeypatch,tmp_path):
    # The live failure stayed at 6.398 yards from a six-yard flight endpoint.
    # Its 33-ms pulses could disappear between client updates.
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        result=copy.deepcopy(r);result['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        result['archaeology']['sequence']=index[0];result['observed_at']=now[0]
        result['owned_pose']={'pitch_radians':0,'client_uptime_ms':index[0]*100}
        if index[0]==6:result['archaeology']['world']['north']=4
        return result
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True)
    assert rows[2]['calculated_pulse_seconds']==.1
    assert events.count(('press','Up'))==2
    assert rows[-1]['distance_yards']==4
    assert events.count(('button_press',3))==1 and events.count(('button_release',3))==1
    assert all(key not in ('Left','Right') for event,key in events if event=='press')
    assert len(calls)==1


def test_new_survey_releases_the_held_forward_route_and_camera(monkeypatch,tmp_path):
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,100)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        row=copy.deepcopy(r)
        row['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        row['archaeology'].update(sequence=index[0],successful_surveys=5 if index[0]<4 else 6)
        row['observed_at']=now[0]
        row['owned_pose']={'pitch_radians':0,'client_uptime_ms':index[0]*100}
        return row
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    with pytest.raises(RuntimeError,match='new Survey'):
        fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True,
            guidance={'source':'Survey telescope'})
    assert events.count(('press','Up'))==1
    assert events.count(('release','Up'))==1
    assert events.count(('button_press',3))==1
    assert events.count(('button_release',3))==1
    assert len(calls)==1

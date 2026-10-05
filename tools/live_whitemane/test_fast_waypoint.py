import copy
import math
from types import SimpleNamespace
from . import fast_waypoint,sticky_input
from .test_flight_recovery import observation


def test_stationary_near_arrival_retries_after_position_updates_with_a_measured_pulse(monkeypatch,tmp_path):
    # The live failure stayed at 6.398 yards from a six-yard flight endpoint.
    # Its 33-ms pulses could disappear between client updates.
    (tmp_path/'run').mkdir();monkeypatch.setattr(fast_waypoint.runtime,'ROOT',tmp_path)
    r=observation(6.398,flying=True)
    r.update(source='test_public_observation',channel_ages={'M':.075},farm_ui={'move_speeds':{'flight':29.26}})
    r['movement'].update(speed=0,position_available=True,facing_radians=math.pi)
    r['archaeology'].update(swimming=False)
    now=[0.0];events=[];controllers=[]
    sender=SimpleNamespace(X=SimpleNamespace(KeyPress='press',KeyRelease='release'),
        XK=SimpleNamespace(string_to_keysym=lambda x:x),_keycode=lambda x:(x,None),
        _send=lambda event,key:events.append((event,key)),close=lambda:None,initialization={})
    from tools.client_compatibility import native_input_adapter
    monkeypatch.setattr(native_input_adapter,'Input',lambda:sender)
    monkeypatch.setattr(fast_waypoint.inputs,'focus',lambda _: {})
    monkeypatch.setattr(fast_waypoint,'time',SimpleNamespace(time=lambda:now[0],monotonic=lambda:now[0],sleep=lambda _:None))
    def sticky(sender):
        controller=sticky_input.StickyInput(sender,clock=lambda:now[0],threaded=False)
        controllers.append(controller);return controller
    monkeypatch.setattr(fast_waypoint,'StickyInput',sticky)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        result=copy.deepcopy(r);result['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        result['archaeology']['sequence']=index[0];result['observed_at']=now[0]
        if index[0]==4:result['archaeology']['world']['north']=4
        return result
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    monkeypatch.setattr(fast_waypoint,'decision',lambda *_,**__:('cruise',{}, {},{}))
    rows=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},flying=True)
    assert rows[2]['calculated_pulse_seconds']==.1
    assert events.count(('press','Up'))==2
    assert rows[-1]['distance_yards']==4

from types import SimpleNamespace
import pytest
from .sticky_input import StickyInput


def controller():
    events=[];now=[0]
    sender=SimpleNamespace(X=SimpleNamespace(KeyPress='press',KeyRelease='release',ButtonPress='button_press',ButtonRelease='button_release'),
        XK=SimpleNamespace(string_to_keysym=lambda name:name),_keycode=lambda name:(name,None),
        _send=lambda event,key:events.append((event,key)),close=lambda:events.append(('close',None)))
    return StickyInput(sender,clock=lambda:now[0],threaded=False),events,now


def test_same_command_remains_held_until_replacement_or_calculated_turn_end():
    sticky,events,now=controller()
    sticky.hold('Up',True);sticky.hold('Up',True)
    sticky.hold('Left',True,.1)
    now[0]=.1;sticky.tick()
    assert events==[('press','Up'),('press','Left'),('release','Left')]
    assert set(sticky.held)=={'Up'}
    sticky.close();assert events[-2:]==[('release','Up'),('close',None)]


def test_missing_decisions_release_all_inputs_without_waiting_for_inference():
    sticky,events,now=controller();sticky.hold('Up',True);sticky.hold('Right',True)
    now[0]=.36;sticky.tick()
    assert sticky.interrupted and not sticky.held
    with pytest.raises(RuntimeError,match='expired'):sticky.renew()
    with pytest.raises(RuntimeError,match='expired'):sticky.hold('Up',True)
    sticky.close();assert events==[('press','Up'),('press','Right'),('release','Up'),('release','Right'),('close',None)]


def test_watchdog_releases_mouselook_and_forward_together():
    sticky,events,now=controller();sticky.hold('Up',True);sticky.button(3,True);sticky.button(3,True)
    now[0]=.36;sticky.tick()
    assert sticky.interrupted and not sticky.held and not sticky.buttons
    assert events==[('press','Up'),('button_press',3),('release','Up'),('button_release',3)]


def test_camera_handoff_releases_even_when_python_forgot_the_pressed_button():
    sticky,events,now=controller();sticky.button(3,True);sticky.buttons.clear()
    def released():
        assert events[-1]==('button_release',3) and ('close',None) not in events
        events.append(('client_confirmed',False))
    sticky.close(after_release=released,release_camera=True)
    assert events==[('button_press',3),('button_release',3),('client_confirmed',False),('close',None)]


def test_a_continuous_command_accepts_an_earlier_stop_without_resending_keydown():
    sticky,events,now=controller()
    sticky.hold('Up',True)
    now[0]=.1;sticky.renew();sticky.hold('Up',True,.1)
    now[0]=.15;sticky.hold('Up',True,.2)
    assert events==[('press','Up')]
    now[0]=.21;sticky.tick()
    assert events==[('press','Up'),('release','Up')]
    assert not sticky.interrupted


def test_waiting_for_the_first_observation_has_no_active_input_to_expire():
    sticky,events,now=controller()
    now[0]=1;sticky.tick()
    assert sticky.interrupted is None and not events
    sticky.renew();sticky.hold('Up',True)
    now[0]=1.36;sticky.tick()
    assert sticky.interrupted and events==[('press','Up'),('release','Up')]


def test_a_fresh_continuous_hold_cancels_the_old_pulse_but_keeps_the_feed_lease():
    sticky,events,now=controller();sticky.hold('Up',True,.1)
    now[0]=.05;sticky.renew();sticky.hold('Up',True)
    now[0]=.15;sticky.tick()
    assert events==[('press','Up')] and 'Up' in sticky.held
    now[0]=.41;sticky.tick()
    assert events==[('press','Up'),('release','Up')] and sticky.interrupted


@pytest.mark.parametrize('failed',[False,True])
def test_sender_survives_until_client_release_feedback_even_if_feedback_fails(failed):
    sticky,events,now=controller();sticky.hold('Up',True);sticky.button(3,True)
    def released():
        assert not sticky.held and not sticky.buttons
        assert ('close',None) not in events
        events.append(('observed_release',None))
        if failed:raise RuntimeError('feed unavailable')
    if failed:
        with pytest.raises(RuntimeError,match='feed unavailable'):sticky.close(after_release=released)
    else:sticky.close(after_release=released)
    assert events[-4:]==[('release','Up'),('button_release',3),('observed_release',None),('close',None)]

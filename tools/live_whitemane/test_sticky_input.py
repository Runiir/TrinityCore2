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

from types import SimpleNamespace
import pytest
from .sticky_input import StickyInput


def controller():
    events=[];now=[0]
    sender=SimpleNamespace(X=SimpleNamespace(KeyPress='press',KeyRelease='release'),
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

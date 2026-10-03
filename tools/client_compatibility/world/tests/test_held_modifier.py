"""Screenshot failures must release only the owned private modifier."""
from contextlib import nullcontext
from types import SimpleNamespace
import pytest
from tools.client_compatibility import owned_input


def adapter(monkeypatch,held=False):
    t=owned_input.Inputs.__new__(owned_input.Inputs);events=[];keys=bytearray(32)
    if held:keys[6]=1<<2
    t.prepare=lambda:events.append('prepare')
    t.raw=SimpleNamespace(MODIFIERS={'shift':'Shift_L'},XK=SimpleNamespace(string_to_keysym=lambda s:s),
        X=SimpleNamespace(KeyPress=2,KeyRelease=3),_keycode=lambda s:(50,False),
        display=SimpleNamespace(query_keymap=lambda:keys),_send=lambda *args:events.append(args))
    monkeypatch.setattr(owned_input,'lease',nullcontext)
    monkeypatch.setattr(owned_input.time,'sleep',lambda s:None)
    return t,events


def test_exception_during_capture_releases_the_private_shift(monkeypatch):
    t,events=adapter(monkeypatch)
    with pytest.raises(ValueError,match='capture failed'):
        with t.hold_modifier('shift'):raise ValueError('capture failed')
    assert events==['prepare',(2,50),(3,50)]


def test_already_held_modifier_is_preserved_without_input(monkeypatch):
    t,events=adapter(monkeypatch,True)
    with pytest.raises(RuntimeError,match='already held'):
        with t.hold_modifier('shift'):pytest.fail('entered held modifier')
    assert events==['prepare']


def test_invalid_modifier_does_not_prepare_or_send_input(monkeypatch):
    t,events=adapter(monkeypatch)
    with pytest.raises(ValueError,match='unsupported'):
        with t.hold_modifier('super'):pytest.fail('entered invalid modifier')
    assert events==[]


def test_overlong_capture_releases_before_reporting_timeout(monkeypatch):
    t,events=adapter(monkeypatch);ticks=iter([0,21])
    monkeypatch.setattr(owned_input.time,'monotonic',lambda:next(ticks))
    with pytest.raises(RuntimeError,match='exceeded'):
        with t.hold_modifier('shift'):pass
    assert events==['prepare',(2,50),(3,50)]

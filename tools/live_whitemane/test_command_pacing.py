from types import SimpleNamespace
from . import inputs


def test_command_typing_obeys_observed_frames_and_preserves_separate_repeated_keys(monkeypatch):
    from tools.second_client import ctl
    monkeypatch.setattr(ctl,'key_for_char',lambda c:(c,False))
    sleeps=[];taps=[]
    monkeypatch.setattr(inputs.time,'sleep',sleeps.append)
    sender=SimpleNamespace(XK=SimpleNamespace(string_to_keysym=lambda c:c),
        _keycode=lambda c:(c,False),_tap=lambda keys,hold:taps.append((keys,hold)))
    inputs.type_command(sender,'/run aa',1/30)
    assert len(taps)==7 and all(hold==1/30 for _,hold in taps)
    assert taps[-2:]==[(['a'],1/30)]*2 and sleeps==[1/30]*7

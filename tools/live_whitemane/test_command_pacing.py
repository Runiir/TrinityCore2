from types import SimpleNamespace
import pytest
from . import inputs,runtime,resources
from tools.client_compatibility import native_input_adapter


@pytest.mark.parametrize('steps,button',[(2,5),(-2,4)])
def test_wheel_input_preserves_notches_and_client_frames_without_any_typing(monkeypatch,tmp_path,steps,button):
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    monkeypatch.setattr(inputs,'focus',lambda _: {'owned':True})
    monkeypatch.setattr(resources,'check',lambda:None)
    monkeypatch.setattr(resources,'append_action',lambda _:None)
    events=[]
    sender=SimpleNamespace(initialization={},X=SimpleNamespace(ButtonPress='down',ButtonRelease='up'),
        move=lambda x,y:events.append(('move',x,y)),_send=lambda *args:events.append(args),
        key=lambda *_ ,**__:pytest.fail('wheel must never open chat'),
        close=lambda:events.append(('close',)))
    monkeypatch.setattr(native_input_adapter,'Input',lambda:sender)
    monkeypatch.setattr(inputs.time,'sleep',lambda seconds:events.append(('wait',seconds)))
    inputs.execute('World of Warcraft','scroll',{'steps':steps,'frame_period_seconds':1/30})
    assert events==[('move',640,150),('wait',1/30),('down',button),('up',button),('wait',1/30),
        ('down',button),('up',button),('wait',1/30),('wait',.15),('close',)]

from types import SimpleNamespace
from . import inputs,runtime,resources
from tools.client_compatibility import native_input_adapter


def test_survey_button_leaves_a_minimap_frame_before_press_without_a_hover_delay(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    monkeypatch.setattr(inputs,'focus',lambda _: {'owned':True})
    monkeypatch.setattr(resources,'check',lambda:None)
    monkeypatch.setattr(resources,'append_action',lambda _:None)
    events=[]
    sender=SimpleNamespace(initialization={},X=SimpleNamespace(ButtonPress='down',ButtonRelease='up'),
        move=lambda x,y:events.append(('move',x,y)),_send=lambda *args:events.append(args),
        close=lambda:events.append(('close',)))
    monkeypatch.setattr(native_input_adapter,'Input',lambda:sender)
    monkeypatch.setattr(inputs.time,'sleep',lambda seconds:events.append(('wait',seconds)))
    inputs.execute('World of Warcraft','button',{'button':8,'x':640,'y':270,'frame_period_seconds':1/30})
    assert events==[('move',640,270),('wait',1/30),('down',8),('wait',.15),('up',8),('close',)]

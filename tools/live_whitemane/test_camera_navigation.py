import math
import pytest
from . import camera_navigation,camera_input,runtime


@pytest.mark.parametrize('sensitivity',[-.006,.004])
@pytest.mark.parametrize('ground_view,starting_pitch',[(False,-1.5),(True,math.pi/4)])
@pytest.mark.parametrize('preferred_zoom',[None,20])
def test_ground_camera_uses_a_view_preset_without_steering_body_pitch(
        monkeypatch,tmp_path,sensitivity,ground_view,starting_pitch,preferred_zoom):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    commands=[];monkeypatch.setattr(camera_navigation.inputs,'execute',lambda *args:commands.append(args) or {'completed':True})
    zoom_restored=[]
    monkeypatch.setattr(camera_navigation.camera_zoom,'goal',lambda _:preferred_zoom)
    monkeypatch.setattr(camera_navigation.camera_zoom,'restore',lambda folder,row,desired,**kw:
        zoom_restored.append((desired,kw['save_preset'])) or {'confirmed':True})
    monkeypatch.setattr(camera_navigation.time,'sleep',lambda _:None)
    actual={'yaw':0,'pitch':starting_pitch,'sequence':0};deltas=[]
    class Sender:
        initialization={}
        def move(self,*_):pass
    class Sticky:
        def __init__(self,sender,**_):pass
        def renew(self):pass
        def button(self,*_):pass
        def relative(self,x,y):
            deltas.append((x,y));actual['yaw']-=x*.006;actual['pitch']+=y*sensitivity
        def close(self):pass
    monkeypatch.setattr(camera_input,'Input',Sender)
    monkeypatch.setattr(camera_navigation,'StickyInput',Sticky)
    monkeypatch.setattr(camera_navigation,'observation_lease',lambda _:1)
    def row():
        return {'observed_at':actual['sequence'],'movement':{
            'sequence':actual['sequence'],'client_uptime_ms':actual['sequence']*100,
            'facing_radians':actual['yaw'],'in_world':True,'dead':False,
            'in_combat':False,'on_taxi':False,'speed':0},
            'archaeology':{'casting':False,'flying':False,'falling':False},
            'owned_pose':{'pitch_radians':actual['pitch'],'client_uptime_ms':actual['sequence']*100}}
    def observe(_):actual['sequence']+=1;return row()
    monkeypatch.setattr(camera_navigation,'observe',observe)
    rows=camera_navigation.align(tmp_path/'camera',row(),ground_view=ground_view)
    assert actual['pitch']==starting_pitch and all(y==0 for _,y in deltas)
    assert abs(actual['yaw'])<=.18 and len(rows)>=2
    assert commands[0][2]['text']==('/run ResetView(4)SetView(4)' if ground_view else '/run ResetView(2)SetView(2)')
    assert zoom_restored==([] if preferred_zoom is None else [(20,4 if ground_view else 2)])


def test_ground_turn_does_not_require_or_steer_a_stale_body_pitch(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    monkeypatch.setattr(camera_navigation.inputs,'execute',lambda *_:pytest.fail('ground yaw turn should not reset the view'))
    from . import camera_input
    state={'yaw':0,'sequence':0};deltas=[]
    class Sender:
        initialization={}
        def move(self,*_):pass
    class Sticky:
        def __init__(self,*_,**__):pass
        def renew(self):pass
        def button(self,*_):pass
        def relative(self,x,y):deltas.append((x,y));state['yaw']-=x*.006
        def close(self):pass
    monkeypatch.setattr(camera_input,'Input',Sender);monkeypatch.setattr(camera_navigation,'StickyInput',Sticky)
    def row():
        state['sequence']+=1
        return {'observed_at':state['sequence'],'movement':{'sequence':state['sequence'],
            'client_uptime_ms':state['sequence']*100,'facing_radians':state['yaw'],
            'in_world':True,'dead':False,'in_combat':False,'on_taxi':False,'speed':0},
            'archaeology':{'world':{'instance':1,'north':0,'west':0},'casting':False,'flying':False,'falling':False},
            'owned_pose':{'pitch_radians':-1.0856,'client_uptime_ms':100}}
    monkeypatch.setattr(camera_navigation,'observe',lambda _:row())
    monkeypatch.setattr(camera_navigation.time,'sleep',lambda _:None)
    camera_navigation.align(tmp_path/'camera',row(),{'instance':1,'north':0,'west':10})
    assert abs(state['yaw']-math.pi/2)<.18 and all(y==0 for _,y in deltas)


def test_interrupted_yaw_does_not_reset_the_same_submitted_camera_preset_again(monkeypatch,tmp_path):
    import json
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before={'runtime':{'pid':1},'movement':{'facing_radians':0,'client_uptime_ms':100,'sequence':1},
        'archaeology':{'flying':False,'falling':False}}
    commands=[]
    monkeypatch.setattr(camera_navigation.inputs,'execute',lambda *a:commands.append(a[-1]['text']) or {'completed':True})
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    class Sender:
        initialization={}
        def move(self,*_):pass
    class Sticky:
        def __init__(self,*_,**__):pass
        def renew(self):pass
        def button(self,*_):pass
        def relative(self,*_):pass
        def close(self):pass
    monkeypatch.setattr(camera_input,'Input',Sender);monkeypatch.setattr(camera_navigation,'StickyInput',Sticky)
    stopped={'movement':{'in_world':True,'dead':False,'in_combat':False,'on_taxi':False,'speed':7},
        'archaeology':{'casting':False}}
    monkeypatch.setattr(camera_navigation,'observe',lambda _:stopped)
    for index in range(2):
        with pytest.raises(RuntimeError,match='player state'):
            camera_navigation.align(tmp_path/str(index),before)
    assert commands==['/run ResetView(2)SetView(2)','/run SetView(2)']
    assert json.loads((tmp_path/'run/camera_presets.json').read_text())['camera_pose_measured'] is False

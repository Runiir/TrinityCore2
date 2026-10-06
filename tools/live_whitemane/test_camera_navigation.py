import math
import pytest
from . import camera_navigation,camera_input,runtime


@pytest.mark.parametrize('sensitivity',[-.006,.004])
@pytest.mark.parametrize('ground_view,starting_pitch',[(False,-1.5),(True,math.pi/4)])
def test_camera_pitch_is_absolute_feedback_not_an_accumulating_ground_delta(
        monkeypatch,tmp_path,sensitivity,ground_view,starting_pitch):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
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
    target=math.pi/4 if ground_view else 0
    assert abs(actual['pitch']-target)<=.03 and rows[-1]['desired_pitch_radians']==target
    if ground_view:assert all(y==0 for _,y in deltas)
    else:assert any(y for _,y in deltas)

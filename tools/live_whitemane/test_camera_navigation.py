import math
import pytest
from . import camera_navigation,camera_input,runtime,camera_recovery


@pytest.mark.parametrize('sensitivity',[-.006,.004])
@pytest.mark.parametrize('ground_view,starting_pitch',[(False,-1.5),(True,math.pi/4)])
@pytest.mark.parametrize('preferred_zoom',[None,20])
@pytest.mark.parametrize('mouselook_after',[None,3])
def test_ground_camera_uses_the_macro_without_steering_body_pitch(
        monkeypatch,tmp_path,sensitivity,ground_view,starting_pitch,preferred_zoom,mouselook_after):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    commands=[];monkeypatch.setattr(camera_recovery,'use',lambda *args:commands.append(args) or {'executed':True})
    zoom_restored=[]
    monkeypatch.setattr(camera_navigation.camera_zoom,'goal',lambda _:preferred_zoom)
    monkeypatch.setattr(camera_navigation.camera_zoom,'restore',lambda folder,row,desired,**kw:
        zoom_restored.append(desired) or {'confirmed':True})
    monkeypatch.setattr(camera_navigation.time,'sleep',lambda _:None)
    actual={'yaw':0,'pitch':starting_pitch,'sequence':0,'released':False};deltas=[]
    class Sender:
        initialization={}
        def move(self,*_):pass
    class Sticky:
        def __init__(self,sender,**_):pass
        def renew(self):pass
        def button(self,*_):pass
        def relative(self,x,y):
            if mouselook_after is not None:assert actual['sequence']>=mouselook_after
            deltas.append((x,y));actual['yaw']-=x*.006;actual['pitch']+=y*sensitivity
        def close(self,after_release=None,*,release_camera=False):
            assert release_camera
            actual['released']=True
            if after_release:after_release()
    monkeypatch.setattr(camera_input,'Input',Sender)
    monkeypatch.setattr(camera_navigation,'StickyInput',Sticky)
    monkeypatch.setattr(camera_navigation,'observation_lease',lambda _:1)
    def row():
        value={'observed_at':actual['sequence'],'movement':{
            'sequence':actual['sequence'],'client_uptime_ms':actual['sequence']*100,
            'facing_radians':actual['yaw'],'in_world':True,'dead':False,
            'in_combat':False,'on_taxi':False,'speed':0},
            'archaeology':{'casting':False,'flying':False,'falling':False},
            'owned_pose':{'pitch_radians':actual['pitch'],'client_uptime_ms':actual['sequence']*100}}
        if mouselook_after is not None:value['farm_ui']={'camera_input':{
            'mouselooking':actual['sequence']>=mouselook_after and not actual['released'],
            'right_down':actual['sequence']>=mouselook_after and not actual['released']}}
        return value
    def observe(_):actual['sequence']+=1;return row()
    monkeypatch.setattr(camera_navigation,'observe',observe)
    rows=camera_navigation.align(tmp_path/'camera',row(),ground_view=ground_view)
    assert actual['pitch']==starting_pitch and all(y==0 for _,y in deltas)
    assert abs(actual['yaw'])<=.18 and len(rows)>=2
    assert len(commands)==1 and commands[0][0].name=='reset_macro'
    assert zoom_restored==([] if preferred_zoom is None else [20])


def test_ground_turn_does_not_require_or_steer_a_stale_body_pitch(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    monkeypatch.setattr(camera_recovery,'use',lambda *_:pytest.fail('ground yaw turn should not reset the view'))
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
        def close(self,after_release=None,*,release_camera=False):
            assert release_camera
            if after_release:after_release()
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


def test_camera_recovery_resets_a_suspect_saved_angle_without_reusing_the_portal_view(monkeypatch,tmp_path):
    import json
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    before={'runtime':{'pid':1},'movement':{'facing_radians':0,'client_uptime_ms':100,'sequence':1},
        'archaeology':{'flying':False,'falling':False}}
    commands=[]
    monkeypatch.setattr(camera_recovery,'use',lambda *a:commands.append('macro') or {'executed':True})
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    class Sender:
        initialization={}
        def move(self,*_):pass
    class Sticky:
        def __init__(self,*_,**__):pass
        def renew(self):pass
        def button(self,*_):pass
        def relative(self,*_):pass
        def close(self,after_release=None,*,release_camera=False):
            assert release_camera
            if after_release:after_release()
    monkeypatch.setattr(camera_input,'Input',Sender);monkeypatch.setattr(camera_navigation,'StickyInput',Sticky)
    stopped={'movement':{'in_world':True,'dead':False,'in_combat':False,'on_taxi':False,'speed':7},
        'archaeology':{'casting':False}}
    monkeypatch.setattr(camera_navigation,'observe',lambda _:stopped)
    for index in range(2):
        with pytest.raises(RuntimeError,match='player state'):
            camera_navigation.align(tmp_path/str(index),before)
    assert commands==['macro']*2
    assert json.loads((tmp_path/'run/camera_presets.json').read_text())['camera_pose_measured'] is False


def test_portal_retry_retains_the_macro_view_and_uses_only_wheel_zoom(monkeypatch,tmp_path):
    (tmp_path/'run').mkdir();monkeypatch.setattr(runtime,'ROOT',tmp_path)
    actual={'yaw':0,'zoom':20,'sequence':0};commands=[]
    def macro(*args):
        commands.append('macro');actual['zoom']=20
        return {'executed':True}
    def execute(title,action,arguments):
        assert action=='scroll'
        commands.append('wheel');actual['zoom']+=arguments['steps']*1.5
        return {'completed':True}
    monkeypatch.setattr(camera_recovery,'use',macro)
    monkeypatch.setattr(camera_navigation.inputs,'execute',execute)
    monkeypatch.setattr(camera_navigation.inputs,'focus',lambda _: {})
    monkeypatch.setattr(camera_navigation.camera_zoom,'goal',lambda _:20)
    monkeypatch.setattr(camera_navigation.time,'sleep',lambda _:None)
    class Sender:
        initialization={}
        def move(self,*_):pass
    class Sticky:
        def __init__(self,*_,**__):pass
        def renew(self):pass
        def button(self,*_):pass
        def relative(self,x,y):actual['yaw']-=x*.006
        def close(self,after_release=None,*,release_camera=False):
            assert release_camera
            if after_release:after_release()
    monkeypatch.setattr(camera_input,'Input',Sender)
    monkeypatch.setattr(camera_navigation,'StickyInput',Sticky)
    monkeypatch.setattr(camera_navigation,'observation_lease',lambda _:1)
    def observe(_=None):
        actual['sequence']+=1
        return {'runtime':{'pid':7},'observed_at':actual['sequence'],
            'movement':{'sequence':actual['sequence'],'client_uptime_ms':actual['sequence']*100,
                'facing_radians':actual['yaw'],'in_world':True,'dead':False,
                'in_combat':False,'on_taxi':False,'speed':0},
            'archaeology':{'world':{'instance':732,'north':0,'west':0},
                'casting':False,'flying':False,'falling':False},
            'farm_ui':{'camera_zoom':actual['zoom'],'frame_rate':30}}
    monkeypatch.setattr(camera_navigation,'observe',observe)
    monkeypatch.setattr(camera_navigation.camera_zoom,'observe',observe)
    for attempt in range(2):
        camera_navigation.align(tmp_path/str(attempt),observe(),
            {'instance':732,'north':8,'west':0},reset_view=True,zoom_target=5.55)
    assert commands[0]=='macro' and commands.count('macro')==1
    assert all(command in ('macro','wheel') for command in commands)
    assert abs(actual['zoom']-5.55)<=1

from types import SimpleNamespace
import pytest
from tools.live_whitemane import smooth_move


@pytest.mark.parametrize('loss',['none','transient','sustained','slow_frames'])
def test_continuous_ascent_releases_on_measured_height_or_missing_telemetry(monkeypatch,tmp_path,loss):
    from tools.client_compatibility import native_input_adapter
    from tools.second_client import ctl
    (tmp_path/'run').mkdir()
    monkeypatch.setattr(smooth_move.runtime,'ROOT',tmp_path)
    monkeypatch.setattr(smooth_move.inputs,'focus',lambda _: {})
    monkeypatch.setattr(smooth_move,'check_point',lambda *_:None)
    monkeypatch.setattr(smooth_move.time,'sleep',lambda _:None)
    monkeypatch.setattr(native_input_adapter,'lab',native_input_adapter.lab)
    monkeypatch.setattr(native_input_adapter,'control',native_input_adapter.control)
    monkeypatch.setattr(ctl,'_launcher_env',ctl._launcher_env)
    events=[]
    class Sender:
        initialization={}
        X=SimpleNamespace(KeyPress='press',KeyRelease='release')
        XK=SimpleNamespace(string_to_keysym=lambda _:1)
        def _keycode(self,_):return 1,None
        def _send(self,event,_):events.append(event)
        def close(self):events.append('closed')
    monkeypatch.setattr(native_input_adapter,'Input',Sender)
    heights=iter([10]+[None]*6 if loss=='sustained' else [10,None,30] if loss=='transient'
        else [10]*12+[20]*12+[30] if loss=='slow_frames' else [10,20,30])
    def observe(_):
        height=next(heights)
        return {'observed_at':1,'movement':{'in_world':True,'dead':False,'in_combat':False,
            'on_taxi':False,'health_percent':100},'archaeology':{
            'casting':False,'mounted':True,'falling':False,'swimming':False,
            'flying':True,'world':{'instance':1,'north':0,'west':0}},
            'owned_pose':None if height is None else {'height_yards':height,'age_seconds':0,'client_uptime_ms':height*100}}
    monkeypatch.setattr(smooth_move,'observe',observe)
    if loss=='sustained':
        with pytest.raises(RuntimeError,match='height observation'):
            smooth_move.ascend(tmp_path,30,site_id=183)
    else:
        rows=smooth_move.ascend(tmp_path,30,site_id=183)
        assert [r['height_gap_yards'] for r in rows]==([20,0] if loss=='transient'
            else [20]*12+[10]*12+[0] if loss=='slow_frames' else [20,10,0])
    assert events==['press','release','closed']


def test_takeoff_brakes_before_a_half_second_heartbeat_and_does_not_repeat_on_stale_height(monkeypatch,tmp_path):
    from tools.client_compatibility import native_input_adapter
    from tools.second_client import ctl
    (tmp_path/'run').mkdir()
    monkeypatch.setattr(smooth_move.runtime,'ROOT',tmp_path)
    monkeypatch.setattr(smooth_move.inputs,'focus',lambda _: {})
    sleeps=[]
    monkeypatch.setattr(smooth_move.time,'sleep',sleeps.append)
    monkeypatch.setattr(native_input_adapter,'lab',native_input_adapter.lab)
    monkeypatch.setattr(native_input_adapter,'control',native_input_adapter.control)
    monkeypatch.setattr(ctl,'_launcher_env',ctl._launcher_env)
    events=[]
    class Sender:
        initialization={}
        X=SimpleNamespace(KeyPress='press',KeyRelease='release')
        XK=SimpleNamespace(string_to_keysym=lambda _:1)
        def _keycode(self,_):return 1,None
        def _send(self,event,_):events.append(event)
        def close(self):events.append('closed')
    monkeypatch.setattr(native_input_adapter,'Input',Sender)
    samples=iter([(17,1000,False,False,0),(17,2000,True,True,.195),
        (17,2000,True,True,.4),(24,2300,True,True,.01),(25,2400,True,False,.01)])
    def observe(_):
        height,tick,flying,ascending,age=next(samples)
        return {'observed_at':tick/1000,'movement':{'in_world':True,'dead':False,'in_combat':False,
            'on_taxi':False,'health_percent':100},'archaeology':{'casting':False,'mounted':True,
            'falling':False,'swimming':False,'flying':flying,'world':{'instance':1,'north':0,'west':0}},
            'farm_ui':{'move_speeds':{'flight':29.26}},'owned_pose':{'height_yards':height,
                'client_uptime_ms':tick,'flying':flying,'ascending':ascending,'age_seconds':age}}
    monkeypatch.setattr(smooth_move,'observe',observe)
    rows=smooth_move.ascend(tmp_path,25)
    assert events==['press','release','closed']
    assert rows[1]['calculated_final_hold_seconds']==pytest.approx(8/29.26-.195)
    assert rows[-1]['height_gap_yards']==0

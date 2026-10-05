from types import SimpleNamespace
import pytest
from tools.live_whitemane import smooth_move


@pytest.mark.parametrize('lose_height',[False,True])
def test_continuous_ascent_releases_on_measured_height_or_missing_telemetry(monkeypatch,tmp_path,lose_height):
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
    heights=iter([10,None if lose_height else 20,30])
    def observe(_):
        height=next(heights)
        return {'observed_at':1,'movement':{'in_world':True,'dead':False,'in_combat':False,
            'on_taxi':False,'health_percent':100},'archaeology':{
            'casting':False,'mounted':True,'falling':False,'swimming':False,
            'flying':True,'world':{'instance':1,'north':0,'west':0}},
            'owned_pose':None if height is None else {'height_yards':height,'age_seconds':0}}
    monkeypatch.setattr(smooth_move,'observe',observe)
    if lose_height:
        with pytest.raises(RuntimeError,match='height observation'):
            smooth_move.ascend(tmp_path,30,site_id=183)
    else:
        rows=smooth_move.ascend(tmp_path,30,site_id=183)
        assert [r['height_gap_yards'] for r in rows]==[20,10,0]
    assert events==['press','release','closed']

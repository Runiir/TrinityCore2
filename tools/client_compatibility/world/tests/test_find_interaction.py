import json
import pytest
from tools.client_compatibility import find_interaction as subject


def test_occlusion_retries_are_bounded_and_failure_views_are_retained(monkeypatch,tmp_path):
    from PIL import Image
    from tools.client_compatibility import archaeology_inputs
    path=tmp_path/'latest.png';Image.new('RGB',(1,1)).save(path)
    position=[0.,0.,0.,0.];calls=[]
    class Observer:
        def poll(self):return {'position':position.copy()}
    monkeypatch.setattr(subject,'zoom',lambda *_:{'before':8,'after':8})
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(None,{'digsite_ids':[1]}))
    def missing(_,path,timeout):
        calls.append(timeout);raise RuntimeError('occluded')
    monkeypatch.setattr(archaeology_inputs,'locate_find',missing)
    monkeypatch.setattr(subject.site_boundaries,'active_site',lambda *_:{'polygon':[]})
    def stance(*args,**kwargs):
        assert len(kwargs['excluded_stances'])==len(calls)
        position[0]+=4;return {'physical_keys':[{'key':'w'}]}
    monkeypatch.setattr(subject.loot_pose,'approach',stance)
    with pytest.raises(RuntimeError,match='occluded'):
        subject.locate(None,Observer(),{'map':530},path)
    trace=json.loads(next(tmp_path.glob('find_localization_*.json')).read_text())
    assert calls==[12,12,12] and len(trace['views'])==3
    assert trace['finished_at'] and not trace['completed']
    assert all((tmp_path/v['frame']).exists() for v in trace['views'])


def test_zoom_uses_observed_camera_distance_and_stops_close(monkeypatch):
    from tools.client_compatibility import archaeology_inputs
    values=iter([15,10,8]);buttons=[]
    monkeypatch.setattr(subject.time,'sleep',lambda _:None)
    monkeypatch.setattr(archaeology_inputs,'screenshot',lambda _:(None,{'camera_zoom':next(values)}))
    class Inputs:
        def click(self,x,y,button,hold):buttons.append(button)
    result=subject.zoom(Inputs(),None)
    assert buttons==[4,4] and result['before']==15 and result['after']==8

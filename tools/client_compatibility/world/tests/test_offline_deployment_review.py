import copy,json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_offline_bridge_deploy as module


@pytest.mark.parametrize('fault',[None,'source_hash','source_failed','actor','runtime','image_hash',
    'monitor','input_actor','game_pid','stale','selection'])
def test_offline_review_is_bound_to_current_owned_closed_screen(tmp_path,monkeypatch,fault):
    root=tmp_path/'evidence/screen';root.mkdir(parents=True);source=root/'episode.json'
    image=root/'screen.png';image.write_bytes(b'owned selection image')
    fixture={'actor':'scout','guid':2};runtime={'client':{'pid':12},'modern_world':{'pid':14}}
    monitor={'second_monitor_verified':True,'pid':12,'input_isolation':{'actor':'scout','game_pid':13}}
    frame={'file':'screen.png','sha256':module.lab.sha256(image),'monitor':copy.deepcopy(monitor)}
    e={'completed':True,'failure':None,'finished_at':1,'actor':copy.deepcopy(fixture),
        'runtime':copy.deepcopy(runtime),'frame':copy.deepcopy(frame)}
    if fault=='source_failed':e['completed']=False;e['failure']='failed'
    if fault=='actor':e['actor']['guid']=1
    if fault=='runtime':e['runtime']['modern_world']['pid']=15
    source.write_text(json.dumps(e))
    d={'reviewed':True,'control':'Harnesstwo','source':{'path':str(source),'sha256':module.lab.sha256(source)},'frame':frame}
    if fault=='source_hash':d['source']['sha256']='changed'
    if fault=='image_hash':frame['sha256']='changed'
    if fault=='monitor':frame['monitor']['second_monitor_verified']=False
    if fault=='input_actor':frame['monitor']['input_isolation']['actor']='primary'
    if fault=='game_pid':frame['monitor']['input_isolation']['game_pid']=99
    if fault=='selection':d['control']='Harnessctrl'
    if fault=='stale':monkeypatch.setattr(module.time,'time',lambda:image.stat().st_mtime+121)
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    monkeypatch.setattr(module.owned_input,'focus',lambda:monitor)
    t=SimpleNamespace(fixture=fixture,receipt={'runtime':runtime},persist=lambda:None)
    p=root/'review.json';p.write_text(json.dumps(d))
    if fault is None:assert module.review(t,p,'Harnesstwo')==(d,e)
    else:
        with pytest.raises(RuntimeError):module.review(t,p,'Harnesstwo')

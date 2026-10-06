import json
import pytest
from tools.client_compatibility import interaction_retained_class_fixture as module


@pytest.mark.parametrize('fault',[None,'hash','actor','runtime','source','unfinished','failure','input','check'])
def test_interrupted_logout_requires_bound_closed_failure_and_complete_recovery(tmp_path,monkeypatch,fault):
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    p=tmp_path/'evidence/park/episode.json';p.parent.mkdir(parents=True)
    failed={'actor':{'guid':5},'runtime':{'client':1},'fixture_source':{'sha256':'preparation'},
        'completed':False,'finished_at':10,'failure':'InterruptedError: parking process terminated by SIGTERM (exit 143)'}
    if fault=='actor':failed['actor']={'guid':4}
    if fault=='runtime':failed['runtime']={'client':2}
    if fault=='source':failed['fixture_source']={'sha256':'other'}
    if fault=='unfinished':failed.pop('finished_at')
    if fault=='failure':failed['failure']='other'
    p.write_text(json.dumps(failed))
    park={'actor':{'guid':5},'runtime':{'client':1},'fixture_source':{'sha256':'preparation'},'input_sent':False,
        'checks':dict.fromkeys(('original_character','original_saved_rows','native_worldserver','class_offline',
            'ordinary_logout','native_logout','delivered_logout'),True),
        'interrupted_source':{'path':str(p),'sha256':module.lab.sha256(p)}}
    if fault=='hash':park['interrupted_source']['sha256']='changed'
    if fault=='input':park['input_sent']=True
    if fault=='check':park['checks']['delivered_logout']=False
    assert module.parking_restored(park)==(fault is None)

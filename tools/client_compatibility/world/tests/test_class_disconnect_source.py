import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_class_disconnect_recovery as recovery


@pytest.mark.parametrize('change',[None,'actor','runtime','phase','source','unfinished','completed','failure'])
def test_only_exact_closed_owned_entry_failure_can_restore_registration(tmp_path,monkeypatch,change):
    monkeypatch.setattr(recovery.lab,'ROOT',tmp_path)
    root=tmp_path/'evidence';root.mkdir();prep=root/'preparation.json';prep.write_text('{}')
    path=root/'episode.json';t=SimpleNamespace(fixture={'guid':4},receipt={'runtime':{'client':{'pid':3}}})
    e={'completed':False,'finished_at':42,'failure':'RuntimeError: UI observation did not become decodable',
        'phase':'owned_class_entry_started','actor':t.fixture,'runtime':t.receipt['runtime'],
        'fixture_source':{'sha256':recovery.lab.sha256(prep)}}
    if change=='actor':e['actor']={'guid':5}
    elif change=='runtime':e['runtime']={'client':{'pid':4}}
    elif change=='phase':e['phase']='other'
    elif change=='source':e['fixture_source']['sha256']='other'
    elif change=='unfinished':e.pop('finished_at')
    elif change=='completed':e['completed']=True
    elif change=='failure':e['failure']='other'
    path.write_text(json.dumps(e))
    if change:
        with pytest.raises(RuntimeError):recovery.failed_source(t,path,prep)
    else:assert recovery.failed_source(t,path,prep)==e

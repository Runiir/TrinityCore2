import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_owned_language_fixture as fixture


@pytest.mark.parametrize('change',[None,'source','image','monitor','actor','game_lifetime'])
def test_owned_lobby_review_rejects_unbound_evidence(tmp_path,monkeypatch,change):
    monkeypatch.setattr(fixture.lab,'ROOT',tmp_path)
    monkeypatch.setattr(fixture.lab,'owned_process',lambda kind:{'pid':99})
    monkeypatch.setattr(fixture.owned_input,'focus',lambda:{'input_isolation':{'game_pid':101}})
    p=tmp_path/'evidence';p.mkdir();image=p/'review.png';image.write_bytes(b'owned retained frame')
    d={'fixture_source_sha256':'a'*64,'frame':{'file':image.name,'sha256':fixture.lab.sha256(image),
        'monitor':{'second_monitor_verified':True,'pid':99,'input_isolation':{'actor':'scout','game_pid':101}}}}
    if change=='source':d['fixture_source_sha256']='b'*64
    elif change=='image':image.write_bytes(b'changed frame')
    elif change=='monitor':d['frame']['monitor']['second_monitor_verified']=False
    elif change=='actor':d['frame']['monitor']['input_isolation']['actor']='primary'
    elif change=='game_lifetime':d['frame']['monitor']['input_isolation']['game_pid']=102
    path=p/'review.json';path.write_text(json.dumps(d))
    t=SimpleNamespace(receipt={'fixture_source':{'sha256':'a'*64}},persist=lambda:None)
    if change is None:
        fixture.reviewed(t,path);assert t.receipt['reviewed_lobby']['frame']==d['frame']
    else:
        with pytest.raises(RuntimeError,match='reviewed owned lobby frame differs'):fixture.reviewed(t,path)

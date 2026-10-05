import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_settings_search_recovery as module


@pytest.mark.parametrize('change',[
    {},{'completed':True},{'finished_at':None},{'actor':{'guid':1}},
    {'runtime':{'worldserver':{'pid':2}}},{'cases':[]},
    {'binding_baseline':{'binding_probe':'TOGGLE_VOICE_SELF_MUTE'}},
])
def test_search_recovery_requires_closed_owned_unmodified_binding_source(tmp_path,monkeypatch,change):
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    p=tmp_path/'evidence/search/episode.json';p.parent.mkdir(parents=True)
    old={'completed':False,'finished_at':123,'actor':{'guid':2},'runtime':{'worldserver':{'pid':1}},
        'failure':'RuntimeError: panel cleanup did not change state; refusing to replay Escape',
        'cases':[{'id':'fixture.voice_binding_search_'+term,'status':'ui_edit_pass'} for term in ['voice','mute']],
        'settings_details':{'original_settings':{'state':{'settings_probe':{'unapplied':False,'search':''}}}}}
    old.update(change);p.write_text(json.dumps(old))
    trial=SimpleNamespace(fixture={'guid':2},receipt={'runtime':{'worldserver':{'pid':1}}})
    if change:
        with pytest.raises(RuntimeError,match='closed search failure'):module.source(trial,p)
    else:
        saved,layout=module.source(trial,p)
        assert saved==old and layout['search']==''

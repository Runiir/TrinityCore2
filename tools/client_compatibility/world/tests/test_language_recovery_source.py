import copy,json
import pytest
from tools.client_compatibility import interaction_language_recovery as recovery


def receipt():
    native={k:True for k in ['resources','stats','spells','actions','pose','afk','position','group',
        'no_lua_errors','no_blocked_actions']}
    native['spells']=False
    return {'actor':{'guid':1},'completed':False,'finished_at':1,'failure':None,
        'language_lifecycle_schema':'client442_language_lifecycle_v1',
        'phase':'await_offline_language_cleanup',
        'language_restoration':{'checks':{'original_spells':False,'original_skills':False,
            'original_native_skills':False,'original_languages':True,'original_target':True}},
        'language_fixture_baseline':{'spells':[[100,1,0]]},
        'language_fixture_trained':{'spells':[[100,1,0],[672,1,0]]},
        'native_restoration':{'checks':native},'fixture_permissions':[{'restored':True}]}


def write(tmp_path,monkeypatch,data):
    monkeypatch.setattr(recovery.lab,'ROOT',tmp_path)
    p=tmp_path/'evidence/episode.json';p.parent.mkdir();p.write_text(json.dumps(data))
    return p


def test_exact_staged_spell_and_skill_deferment_is_accepted(tmp_path,monkeypatch):
    d=receipt();assert recovery.source(write(tmp_path,monkeypatch,d))==d


@pytest.mark.parametrize('change',['other_spell','target','native_resource','missing_native_check','permission'])
def test_cleanup_refuses_unrelated_or_incomplete_changes(tmp_path,monkeypatch,change):
    d=copy.deepcopy(receipt())
    if change=='other_spell':d['language_fixture_trained']['spells'].append([101,1,0])
    elif change=='target':d['language_restoration']['checks']['original_target']=False
    elif change=='native_resource':d['native_restoration']['checks']['resources']=False
    elif change=='missing_native_check':del d['native_restoration']['checks']['pose']
    else:d['fixture_permissions'][0]['restored']=False
    with pytest.raises(RuntimeError,match='restoration evidence differs'):
        recovery.source(write(tmp_path,monkeypatch,d))

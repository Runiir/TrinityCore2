"""Player-link inputs require a closed owned seed and both actor restorations."""
import json
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_chat_player_menu as module


@pytest.mark.parametrize('change',[None,'runtime','sender','unfinished','peer_guid','peer_restore'])
def test_player_link_rejects_foreign_or_unrestored_seed(tmp_path,monkeypatch,change):
    monkeypatch.setattr(module.lab,'ROOT',tmp_path)
    fixture={'actor':'primary','guid':1};runtime={'client':{'pid':123,'start_ticks':456}}
    restore={'checks':{str(i):True for i in range(10)}}
    seed={'expected_native_guid':2,'checks':{'native_delivery':True}}
    primary={'completed':True,'finished_at':1,'actor':fixture,'runtime':runtime,
        'player_link_seed':seed,'native_restoration':restore}
    peer={'completed':True,'actor':{'guid':2},'native_restoration':json.loads(json.dumps(restore))}
    if change=='runtime':primary['runtime']={}
    if change=='sender':seed['expected_native_guid']=3
    if change=='unfinished':primary['completed']=False
    if change=='peer_guid':peer['actor']['guid']=3
    if change=='peer_restore':peer['native_restoration']['checks']['0']=False
    cohort=tmp_path/'evidence/cohort'
    for name,data in [('primary',primary),('scout',peer)]:
        path=cohort/name/'episode.json';path.parent.mkdir(parents=True);path.write_text(json.dumps(data))
    t=SimpleNamespace(fixture=fixture,receipt={'runtime':runtime})
    if change is None:assert module.seed_source(t,cohort/'primary/episode.json')==seed
    else:
        with pytest.raises(RuntimeError,match='closed owned chat seed'):
            module.seed_source(t,cohort/'primary/episode.json')


@pytest.mark.parametrize('change',[None,'primary','peer','actor','sender','native','checks'])
def test_live_seed_uses_native_fixture_guid_and_requires_both_owned_baselines(change):
    t=SimpleNamespace(guid='Player-1-00000001',fixture={'actor':'primary','guid':1},
        receipt={'native_baseline':{'spells':[]}})
    peer=SimpleNamespace(guid='Player-1-00000002',fixture={'actor':'scout','guid':2},
        receipt={'native_baseline':{'spells':[]}})
    seed={'expected_native_guid':2,'checks':{'native_delivery':True}}
    if change=='primary':t.fixture['guid']=3
    if change=='peer':peer.fixture['guid']=3
    if change=='actor':peer.fixture['actor']='primary'
    if change=='sender':seed['expected_native_guid']=1
    if change=='native':peer.receipt={}
    if change=='checks':seed['checks']['native_delivery']=False
    assert module.live_seed_valid(t,peer,seed)==(change is None)

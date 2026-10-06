"""Normal reentry must bind the entire completed one-time name and logout chain."""
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_hunter_rename_persistence as module


@pytest.mark.parametrize('fault',('none','same_transport','old_entry','overlap','missing_offline',
    'missing_request','missing_native','stale_request','late_native','wrong_direction','unfinished'))
def test_persistence_uses_fresh_character_login_instead_of_transport_identity(fault):
    old={'finished_at':2,'native_session':'same'}
    entry={'started_at':3,'finished_at':6,'native_before_entry':{'online':0},'native_session':'new',
        'login_packets':[{'name':'CMSG_PLAYER_LOGIN','direction':'from_client','time':4},
            {'name':'SMSG_LOGIN_VERIFY_WORLD','direction':'from_native','time':5}]}
    if fault=='same_transport':entry['native_session']='same'
    elif fault=='old_entry':entry['started_at']=1
    elif fault=='overlap':entry['started_at']=2
    elif fault=='missing_offline':entry['native_before_entry']={}
    elif fault=='missing_request':entry['login_packets'].pop(0)
    elif fault=='missing_native':entry['login_packets'].pop()
    elif fault=='stale_request':entry['login_packets'][0]['time']=1
    elif fault=='late_native':entry['login_packets'][1]['time']=7
    elif fault=='wrong_direction':entry['login_packets'][1]['direction']='to_client'
    elif fault=='unfinished':entry['finished_at']=0
    assert module.fresh_entry(entry,old)==(fault in ('none','same_transport'))


@pytest.mark.parametrize('fault',('none','wrong_actor','wrong_runtime','wrong_fixture','wrong_phase',
    'partial_rename','false_rename','partial_restoration','false_restoration','missing_menu','missing_name',
    'missing_protection','source_hash','overlapping_logout','changed_pet','changed_saved'))
def test_only_the_complete_same_fixture_rename_can_supply_persistence(monkeypatch,fault):
    fixture={'guid':6};runtime={'modern_world':1};saved={'spells':[1515,79682]}
    pet=[{'name':'Harnesswolf','renamed':1,'savetime':100,'owner':6}]
    sources=[{'path':str(Path('/owned')/p/'episode.json'),'sha256':p} for p in ('prep','park','finish')]
    old={'sources':deepcopy(sources),'retained_class_pets':deepcopy(pet),'natural_saved':deepcopy(saved)}
    e={'actor':deepcopy(fixture),'runtime':deepcopy(runtime),'phase':'hunter_renamed',
        'fixture_source':{'sha256':'prep'},'rename_checks':dict.fromkeys(range(18),True),
        'restoration_checks':dict.fromkeys(range(13),True),'pet_menu':{'checks':dict.fromkeys(range(4),True)},
        'public_pet':{'name':'Harnesswolf'},'protected_checks':dict.fromkeys((f'actor_{g}_unchanged' for g in range(1,6)),True),
        'finished_at':2,'restored_pets':deepcopy(pet),'baseline_saved':deepcopy(saved)}
    park={'started_at':3,'finished_at':4,'retained_class_pets':deepcopy(pet)}
    finish={'started_at':5,'finished_at':6}
    if fault=='wrong_actor':e['actor']['guid']=5
    elif fault=='wrong_runtime':e['runtime']['modern_world']=2
    elif fault=='wrong_fixture':e['fixture_source']['sha256']='foreign'
    elif fault=='wrong_phase':e['phase']='hunter_rename_filled'
    elif fault=='partial_rename':e['rename_checks'].pop(17)
    elif fault=='false_rename':e['rename_checks'][17]=False
    elif fault=='partial_restoration':e['restoration_checks'].pop(12)
    elif fault=='false_restoration':e['restoration_checks'][12]=False
    elif fault=='missing_menu':e['pet_menu']['checks'].pop(3)
    elif fault=='missing_name':e['public_pet']['name']='Wolf'
    elif fault=='missing_protection':e['protected_checks'].pop('actor_1_unchanged')
    elif fault=='source_hash':old['sources'][1]['sha256']='foreign'
    elif fault=='overlapping_logout':park['started_at']=1
    elif fault=='changed_pet':park['retained_class_pets'][0]['owner']=5
    elif fault=='changed_saved':old['natural_saved']['spells']=[1515]
    receipts={'rename':e,'prep':{},'park':park,'finish':finish}
    monkeypatch.setattr(module,'closed',lambda p:receipts['rename' if p.name=='rename.json' else p.parent.name])
    monkeypatch.setattr(module.lab,'sha256',lambda p:p.parent.name)
    t=SimpleNamespace(fixture=fixture,receipt={'runtime':runtime})
    if fault=='none':assert module.source(t,old,Path('/owned/rename.json'))==e
    else:
        with pytest.raises(RuntimeError):module.source(t,old,Path('/owned/rename.json'))

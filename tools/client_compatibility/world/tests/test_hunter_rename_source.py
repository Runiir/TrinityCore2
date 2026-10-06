"""Rename dialog staging requires the complete current owned pet-menu proof."""
from copy import deepcopy
from types import SimpleNamespace
from pathlib import Path
import pytest
from tools.client_compatibility import interaction_hunter_rename as module


@pytest.mark.parametrize('fault',('none','foreign_actor','foreign_runtime','old_session','wrong_phase',
    'wrong_fixture','partial_catalog','false_catalog','partial_restoration','false_restoration',
    'player_menu','missing_rename'))
def test_rename_cannot_open_from_a_foreign_or_incomplete_menu(monkeypatch,fault):
    t=SimpleNamespace(fixture={'guid':6},receipt={'runtime':{'client':1},'fixture_source':{'sha256':'current'}})
    e={'actor':deepcopy(t.fixture),'runtime':deepcopy(t.receipt['runtime']),'native_session':'owned',
        'phase':'hunter_pet_menu_recon','fixture_source':deepcopy(t.receipt['fixture_source']),
        'checks':dict.fromkeys(range(6),True),'restoration_checks':dict.fromkeys(range(13),True),
        'pet_menu':{'checks':dict.fromkeys(('owned_menu_title','player_menu_absent','stock_rename_visible'),True)}}
    if fault=='foreign_actor':e['actor']['guid']=5
    elif fault=='foreign_runtime':e['runtime']['client']=2
    elif fault=='old_session':e['native_session']='previous'
    elif fault=='wrong_phase':e['phase']='hunter_rename_dialog_open'
    elif fault=='wrong_fixture':e['fixture_source']['sha256']='old'
    elif fault=='partial_catalog':e['checks'].pop(5)
    elif fault=='false_catalog':e['checks'][5]=False
    elif fault=='partial_restoration':e['restoration_checks'].pop(12)
    elif fault=='false_restoration':e['restoration_checks'][12]=False
    elif fault=='player_menu':e['pet_menu']['checks']['player_menu_absent']=False
    elif fault=='missing_rename':e['pet_menu']['checks']['stock_rename_visible']=False
    monkeypatch.setattr(module,'closed',lambda path:e)
    if fault=='none':assert module.menu_source(t,Path('closed-episode'),'owned')==e
    else:
        with pytest.raises(RuntimeError):module.menu_source(t,Path('closed-episode'),'owned')

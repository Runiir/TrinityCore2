"""Cleanup never blindly toggles an enabled or unattributable autocast switch."""
import copy,json,time
from pathlib import Path
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_pet_autocast as m
from tools.client_compatibility.interaction_pet_command_probe import expected_guid

F=json.loads((Path(__file__).parent/'fixtures/native_trained_pet_autocast_ui130.json').read_text())


def setup(monkeypatch,disabled=()):
    pet={'guid':F['native_pet_guid'],'map':0};catalog={'guid':pet['guid'],'packet':copy.deepcopy(F['actual_reload_native_catalog'])}
    data=m.native_catalog(catalog);bar=copy.deepcopy(F['public_baseline_bar'])
    for spell in disabled:
        slot={3110:4,6307:5}[spell];data['buttons'][slot-1]['action_type']=0x81
        bar[slot-1]['autocast_enabled']=False
    sample={'probe':{'owner_guid':'Player-1-00000005','pet_guid':expected_guid(pet),'actions':bar},'ui_clean':True}
    t=SimpleNamespace(guid='Player-1-00000005',receipt={'baseline':{'pet':{'abdata':F['saved_baseline_abdata']},
        'public_bar':copy.deepcopy(F['public_baseline_bar'])}},persist=lambda:None,clean_panels=lambda:None)
    actions=[]
    def execute(action):
        assert action=={'kind':'chat','value':'/reload'};catalog['packet']['time']=time.time();actions.append(action)
    t.execute=execute;o=SimpleNamespace(pet=pet,catalogs=[catalog],session='owned',poll=lambda:None,present=lambda:True)
    monkeypatch.setattr(m,'read',lambda *a:sample);monkeypatch.setattr(m,'entries',lambda *a:[])
    monkeypatch.setattr(m,'info_pairs',lambda *a:[{'native':{}}]);monkeypatch.setattr(m,'catalog_delivery',lambda *a:[{}])
    monkeypatch.setattr(m,'native_catalog',lambda *a:data)
    calls=[];monkeypatch.setattr(m,'switch',lambda t,o,s,w,label:calls.append((s,w,label)))
    return t,o,data,sample,calls,actions


@pytest.mark.parametrize('disabled',[(),(3110,),(6307,)])
def test_cleanup_switches_only_the_one_observed_disabled_original_spell(monkeypatch,disabled):
    t,o,d,p,calls,actions=setup(monkeypatch,disabled);m.restore_switches(t,o)
    assert calls==[(s,True,'fixture.autocast_restore_'+str(s)) for s in disabled]
    assert actions==[{'kind':'chat','value':'/reload'}] and t.receipt['autocast_failure_restore']['cleanup_only']


@pytest.mark.parametrize('fault',['foreign_owner','foreign_pet','lost_pet','lua_error','native_query_missing',
    'catalog_delivery_missing','public_disagrees','two_disabled','uncaptured_bar_change','wrong_react'])
def test_cleanup_refuses_a_toggle_without_fresh_matching_owned_native_and_public_state(monkeypatch,fault):
    t,o,d,p,calls,actions=setup(monkeypatch,(3110,6307) if fault=='two_disabled' else (3110,))
    if fault=='foreign_owner':p['probe']['owner_guid']='Player-1-00000004'
    elif fault=='foreign_pet':p['probe']['pet_guid']='Pet-0-1-0-0-416-0000000001'
    elif fault=='lost_pet':o.present=lambda:False
    elif fault=='lua_error':p['ui_clean']=False
    elif fault=='native_query_missing':monkeypatch.setattr(m,'info_pairs',lambda *a:[{'native':None}])
    elif fault=='catalog_delivery_missing':monkeypatch.setattr(m,'catalog_delivery',lambda *a:[])
    elif fault=='public_disagrees':p['probe']['actions'][3]['autocast_enabled']=True
    elif fault=='uncaptured_bar_change':d['buttons'][0]['spell_id']=1
    elif fault=='wrong_react':d['react']=1
    with pytest.raises(RuntimeError):m.restore_switches(t,o)
    assert calls==[] and actions==[{'kind':'chat','value':'/reload'}]

import copy
import pytest
from . import farm_loop,farm_policy,farm_actions
from .dig_policy import SolveBatches
from .test_farm_loop import row


def test_direct_tol_barad_spell_uses_one_click_and_observed_arrival(monkeypatch,tmp_path):
    r=row();r['archaeology']['falling']=False
    r['farm_ui']['actionbars']=[{'kind':'spell','id':5000028,'label':'Tol Barad','enabled':True}]
    destination=copy.deepcopy(r);destination['movement']['map_id']=245
    destination['archaeology']['world']={'instance':732,'north':-601.4,'west':1382.0}
    destination['farm_ui']['flyout']={}
    calls=[]
    def click(folder,before,collection,goal,expected):
        calls.append(collection);assert expected['id']==5000028
        return {'executed':True,'after':destination}
    monkeypatch.setattr(farm_loop,'click_choice',click)
    assert farm_loop.teleport(tmp_path,r)['completed']
    assert calls==[['actionbars']]
    assert 'teleport' in farm_policy.legal_actions(r,SolveBatches())
    assert 'teleport' not in farm_policy.legal_actions(destination,SolveBatches())


def test_already_arrived_destination_needs_no_click(monkeypatch,tmp_path):
    r=row();r['movement']['map_id']=245
    monkeypatch.setattr(farm_loop,'click_choice',lambda *_:pytest.fail('already arrived'))
    assert farm_loop.teleport(tmp_path,r)['already_at_destination']


def test_no_visible_ui_input_remains_a_wait_without_calling_a_singleton_head(monkeypatch,tmp_path):
    r=row();r['farm_ui']['flyout']={}
    monkeypatch.setattr(farm_actions.laya_ui,'choose',lambda *_:pytest.fail('only wait is legal'))
    monkeypatch.setattr(farm_actions.inputs,'execute',lambda *_:pytest.fail('no visible button'))
    result=farm_actions.click_choice(tmp_path/'empty',r,['flyout'],'Teleport to Tol Barad')
    assert result['choice']=='wait' and result['executed'] is False


def test_tol_barad_world_facts_offer_its_portal_before_cross_world_flight():
    r=row();r['movement']['map_id']=245;r['archaeology'].update(falling=False,
        world={'instance':732,'north':-601,'west':1382})
    r['minimap_finds']={'clear':True}
    r['farm_ui']['actionbars']=[{'kind':'spell','id':5000028,'label':'Tol Barad'}]
    r['farm_ui']['route'].update(portal={'from':{'instance':732,'north':-580,'west':1382}},
        site={'point':{'instance':1,'north':-9732,'west':-38}},
        origin={'point':{'instance':1,'north':2040,'west':-4356}},exit={'id':79})
    assert set(farm_policy.legal_actions(r,SolveBatches()))=={'wait','portal'}

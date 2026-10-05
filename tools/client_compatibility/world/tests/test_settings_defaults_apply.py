"""Category defaults refuse any expansion beyond the owned checkbox fixture."""
import copy
import pytest
from tools.client_compatibility import interaction_settings_defaults_apply as defaults


def baseline():
    return {'cvars':{'colorblindMode':'0','colorblindSimulator':'0','colorblindWeaknessFactor':'0.5',
        'RenderScale':'1','softTargetInteract':'1'},
        'values':{'colorblindMode':False,'colorblindSimulator':0,'colorblindWeaknessFactor':.5,
            'PROXY_RESOLUTION':'1280x720'},'display_state':{'window_size':{'width':1280,'height':720}},
        'unapplied':False,'discard_dialogs':[],'defaults_dialogs':[],'search':'',
        'category':{'id':8,'name':'Colorblind Mode'},
        'colorblind_defaults':[{'variable':'colorblindMode','value':False,'default':False},
            {'variable':'colorblindSimulator','value':0,'default':0},
            {'variable':'colorblindWeaknessFactor','value':.5,'default':.5}]}


def enabled(old):
    now=copy.deepcopy(old);now['values']['colorblindMode']=True;now['cvars']['colorblindMode']='1'
    now['colorblind_defaults'][0]['value']=True;return now


def test_source_backed_immediate_default_only_restores_mode():
    old=baseline();defaults.fixture(old);defaults.catalog(old,old,False)
    now=enabled(old);defaults.catalog(now,old,True)
    assert all(defaults.checks(now,old,True).values())
    assert all(defaults.checks(copy.deepcopy(old),old,False).values())


@pytest.mark.parametrize('change',['original_mode','filter','missing_strength','strength_bool','strength_nan',
    'strength_disagree','pending','discard','defaults'])
def test_unverified_fixture_is_refused_before_mutation(change):
    old=baseline()
    if change=='original_mode':old['cvars']['colorblindMode']='1'
    elif change=='filter':old['values']['colorblindSimulator']=1
    elif change=='missing_strength':old['cvars'].pop('colorblindWeaknessFactor')
    elif change=='strength_bool':old['values']['colorblindWeaknessFactor']=False
    elif change=='strength_nan':old['cvars']['colorblindWeaknessFactor']='nan'
    elif change=='strength_disagree':old['values']['colorblindWeaknessFactor']=.75
    elif change=='pending':old['unapplied']=True
    elif change=='discard':old['discard_dialogs']=[{'which':'GAME_SETTINGS_CONFIRM_DISCARD'}]
    else:old['defaults_dialogs']=[{'which':'GAME_SETTINGS_APPLY_DEFAULTS'}]
    with pytest.raises(RuntimeError):defaults.fixture(old)


@pytest.mark.parametrize('change',['extra','duplicate','missing','mode_default','filter_default',
    'strength_default','missing_default','wrong_mode','strength_bool'])
def test_reset_that_could_change_another_setting_is_refused(change):
    old=baseline();now=enabled(old);rows=now['colorblind_defaults']
    if change=='extra':rows.append({'variable':'RenderScale','value':1,'default':.5})
    elif change=='duplicate':rows[2]['variable']='colorblindMode'
    elif change=='missing':rows.pop()
    elif change=='mode_default':rows[0]['default']=True
    elif change=='filter_default':rows[1]['default']=1
    elif change=='strength_default':rows[2]['default']=.75
    elif change=='missing_default':rows[2].pop('default')
    elif change=='wrong_mode':rows[0]['value']=False
    else:rows[2]['value']=True
    with pytest.raises(RuntimeError):defaults.catalog(now,old,True)


@pytest.mark.parametrize('change',['display','native','other_proxy','missing_cvar','pending'])
def test_partial_default_cannot_pass_when_display_or_other_values_change(change):
    old=baseline();now=copy.deepcopy(old)
    if change=='display':now['display_state']['window_size']['width']=1920
    elif change=='native':now['cvars']['softTargetInteract']='0'
    elif change=='other_proxy':now['values']['PROXY_RESOLUTION']='1920x1080'
    elif change=='missing_cvar':now['cvars'].pop('RenderScale')
    else:now['unapplied']=True
    assert not all(defaults.checks(now,old,False).values())


@pytest.mark.parametrize('index',[1,True,False,0,4,3.0,'3'])
def test_all_settings_and_invalid_choices_fail_before_observation_or_input(index):
    with pytest.raises(ValueError):defaults.choose(object(),index,'forbidden')


@pytest.mark.parametrize('change',['other_popup','two_popups','invalid_name','absent'])
def test_only_exact_defaults_popup_is_accepted(change):
    row={'name':'StaticPopup1','which':'GAME_SETTINGS_APPLY_DEFAULTS'}
    rows=[row]
    if change=='other_popup':row['which']='GAME_SETTINGS_CONFIRM_DISCARD'
    elif change=='two_popups':rows.append(dict(row,name='StaticPopup2'))
    elif change=='invalid_name':row['name']='StaticPopup4'
    else:rows=[]
    with pytest.raises(RuntimeError):defaults.popup({'defaults_dialogs':rows})


def test_wrong_current_category_refuses_before_control_lookup(monkeypatch):
    from types import SimpleNamespace
    old=baseline();now=enabled(old);now['defaults_dialogs']=[{'name':'StaticPopup1','which':'GAME_SETTINGS_APPLY_DEFAULTS'}]
    t=SimpleNamespace(defaults_layout=old,defaults_category={'id':5,'name':'Controls'})
    monkeypatch.setattr(defaults,'detail',lambda *args:now)
    monkeypatch.setattr(defaults,'target',lambda *args:pytest.fail('looked up a control for the wrong category'))
    with pytest.raises(RuntimeError,match='category or search'):defaults.choose(t,3,'wrong')

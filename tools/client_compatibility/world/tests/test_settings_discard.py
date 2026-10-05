"""A settings choice must belong to the exact stock discard confirmation."""
import pytest
from tools.client_compatibility.interaction_settings_discard import dialog,select,cleanup


def test_exact_stock_settings_discard_confirmation_is_identified():
    assert dialog({'discard_dialogs':[{'name':'StaticPopup2','which':'GAME_SETTINGS_CONFIRM_DISCARD'}]})=='StaticPopup2'


@pytest.mark.parametrize('rows',[None,{},[],[{'name':'StaticPopup1','which':'GAME_SETTINGS_APPLY_DEFAULTS'}],
    [{'name':'StaticPopup4','which':'GAME_SETTINGS_CONFIRM_DISCARD'}],
    [{'name':'StaticPopup1Button1','which':'GAME_SETTINGS_CONFIRM_DISCARD'}],
    [{'name':'StaticPopup1','which':'GAME_SETTINGS_CONFIRM_DISCARD'}]*2])
def test_absent_foreign_or_ambiguous_confirmation_is_rejected(rows):
    with pytest.raises(RuntimeError):dialog({'discard_dialogs':rows})


@pytest.mark.parametrize('index',[2,0,-1,True,'1'])
def test_apply_and_exit_and_invalid_choices_are_refused_before_input(index):
    with pytest.raises(ValueError):select(None,index,'refused')


@pytest.mark.parametrize('visible',[True,False])
def test_cleanup_reads_layout_only_after_settings_are_visible(monkeypatch,visible):
    from types import SimpleNamespace
    from tools.client_compatibility import interaction_settings_discard as module
    calls=[];opened=visible
    def open_search(t):
        nonlocal opened
        opened=True;calls.append('open');return {}
    def detail(t,label):
        assert opened;calls.append('detail');return {'discard_dialogs':{}}
    monkeypatch.setattr(module,'open_search',open_search);monkeypatch.setattr(module,'detail',detail)
    monkeypatch.setattr(module,'restore',lambda t,layout:calls.append('restore'))
    trial=SimpleNamespace(observe=lambda label:({'panels':['SettingsPanel'] if visible else []},{}),
        clean_panels=lambda:calls.append('clean'),receipt={})
    cleanup(trial,{})
    assert calls==(['detail','restore'] if visible else ['clean','open','detail','restore'])

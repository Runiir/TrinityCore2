"""A native toggle failure still restores unrelated settings and preserves its cause."""
from copy import deepcopy
from types import SimpleNamespace
import pytest
from tools.client_compatibility import interaction_extra_bar as extra


def test_native_failure_does_not_strand_grid_search_or_panels(monkeypatch):
    layout={'search':'','category':1,'cvars':{'alwaysShowActionBars':'0'},
        'values':{extra.VARIABLE:False}}
    current=deepcopy(layout);closed=[]
    bar={'frames':{'MultiBarBottomLeft':False},'toggles':[False], 'actions':[]}
    t=SimpleNamespace(fixture={'guid':2},receipt={},persist=lambda:None,
        clean_panels=lambda:None,observe=lambda label:({'observer_version':73,'panels':['SettingsPanel']},None))
    monkeypatch.setattr(extra.actors,'session_entry',lambda f:{'session':'owned'})
    monkeypatch.setattr(extra,'Inventory',lambda *a:SimpleNamespace(poll=lambda:None))
    monkeypatch.setattr(extra,'resources',lambda o:{'money':0})
    monkeypatch.setattr(extra,'known',lambda g:[])
    monkeypatch.setattr(extra,'saved_actions',lambda g:[])
    monkeypatch.setattr(extra,'mask',lambda o:0)
    monkeypatch.setattr(extra,'bars',lambda *a:deepcopy(bar))
    monkeypatch.setattr(extra,'open_search',lambda t:1)
    monkeypatch.setattr(extra,'settings',lambda *a:deepcopy(current))
    monkeypatch.setattr(extra,'search',lambda t,s,label:current.update(search=s))
    monkeypatch.setattr(extra,'toggle',lambda t,v,value,label:current['cvars'].update({v:value}))
    monkeypatch.setattr(extra,'close',lambda t,label:closed.append(label))
    def fail_native(t,oracle,wanted,label):
        current['values'][extra.VARIABLE]=wanted
        raise RuntimeError('native enable failed' if wanted else 'native restore failed')
    monkeypatch.setattr(extra,'toggle_extra',fail_native)
    with pytest.raises(RuntimeError,match='native enable failed'):extra.suite(t)
    assert current==layout
    assert closed==['extra_bar.restore_close']
    assert t.receipt['cleanup_failures']==['RuntimeError: native restore failed']
    assert t.receipt['execution_failure']=='RuntimeError: native enable failed'
    assert t.receipt['layout_restored'] and t.receipt['bar_restored']
    assert t.receipt['native_resources_preserved']

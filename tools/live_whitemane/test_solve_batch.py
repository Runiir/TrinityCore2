import copy
from types import SimpleNamespace
import pytest
from . import solve_batch


def snapshot(spell=100,race=8):
    return {'archaeology':{'casting':False,'races':[{'index':8,'project_spell':200}]},
        'farm_ui':{'journal':{'race':race,'project':{'spell':spell}}}}


def test_currency_change_waits_for_the_matching_visible_project(monkeypatch,tmp_path):
    frames=iter([snapshot(),snapshot(200)])
    monkeypatch.setattr(solve_batch,'observe',lambda _:copy.deepcopy(next(frames)))
    now=[0]
    def sleep(seconds):now[0]+=seconds
    monkeypatch.setattr(solve_batch,'time',SimpleNamespace(monotonic=lambda:now[0],sleep=sleep))
    row=solve_batch.settled_project(snapshot(),8,tmp_path)
    assert row['farm_ui']['journal']['project']['spell']==200 and now[0]==.2


def test_a_different_selected_race_is_rejected_without_input(monkeypatch,tmp_path):
    monkeypatch.setattr(solve_batch,'observe',lambda _:pytest.fail('must reject the wrong race'))
    with pytest.raises(RuntimeError,match='journal selection'):
        solve_batch.settled_project(snapshot(200,10),8,tmp_path)


def test_a_project_that_never_settles_stops_before_any_solve(monkeypatch,tmp_path):
    now=[0]
    def sleep(seconds):now[0]+=seconds
    monkeypatch.setattr(solve_batch,'time',SimpleNamespace(monotonic=lambda:now[0],sleep=sleep))
    monkeypatch.setattr(solve_batch,'observe',lambda _:snapshot())
    with pytest.raises(RuntimeError,match='journal selection'):
        solve_batch.settled_project(snapshot(),8,tmp_path)
    assert 3<=now[0]<3.2


def test_keystone_choice_only_offers_the_requested_visible_socket(monkeypatch,tmp_path):
    from . import farm_actions,runtime
    from .test_farm_loop import row
    r=row();r['farm_ui']['journal']={'keystones':[
        {'index':1,'label':'Socket 1','enabled':True,'x':.4,'y':.5},
        {'index':2,'label':'Socket 2','enabled':True,'x':.5,'y':.5}]}
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    monkeypatch.setattr(farm_actions,'observe',lambda _:copy.deepcopy(r))
    def choose(state,instructions,options):
        assert set(options)=={'button_1','wait'}
        return 'button_1',{},{}
    monkeypatch.setattr(farm_actions.laya_ui,'choose',choose)
    events=[];monkeypatch.setattr(farm_actions.inputs,'execute',lambda *args:events.append(args) or {'completed':True})
    monkeypatch.setattr(farm_actions.time,'sleep',lambda _:None)
    result=farm_actions.click_choice(tmp_path/'socket',r,['journal','keystones'],
        'Add keystone in socket 2',{'index':2},matching_only=True)
    assert result['selected']['index']==2 and events[0][-1]['x']==640


def test_mismatched_ui_selection_returns_to_recovery_instead_of_stopping_farm():
    from . import recovery
    assert recovery.retryable(RuntimeError('Laya selected a control inconsistent with the requested goal'))
    assert recovery.retryable(RuntimeError('RuntimeError: Laya selected a control inconsistent with the requested goal'))

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

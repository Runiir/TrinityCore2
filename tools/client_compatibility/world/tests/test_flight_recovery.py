import math
from tools.client_compatibility import flight_recovery as recovery,travel_trial


def test_escape_stays_inside_observed_polygon_and_has_terrain_clearance(monkeypatch):
    site={'id':343,'map':530,'polygon':[[-10,-10],[10,-10],[10,10],[-10,10]]}
    monkeypatch.setattr(recovery.site_boundaries,'sites',lambda:{343:site})
    monkeypatch.setattr(recovery.ground_navigation,'ground_point',lambda m,xy,**kw:[*xy[:2],10])
    facts={'map':530,'position':[0,0,60,0]}
    goal,ground,sites=recovery.candidate(facts,{'digsite_ids':[343]},math.pi)
    assert [s['id'] for s in sites]==[343] and math.isclose(goal[0],-9) and recovery.site_boundaries.contains(site['polygon'],goal)
    monkeypatch.setattr(recovery.ground_navigation,'ground_point',lambda m,xy,**kw:[*xy[:2],55])
    import pytest
    with pytest.raises(RuntimeError):recovery.candidate(facts,{'digsite_ids':[343]},math.pi)


def test_climb_watchdog_ignores_horizontal_collision_jitter():
    leg={'ceiling':240};facts={'position':[0,0,200]}
    a=travel_trial.progress_metric('takeoff',leg,facts,{}, {})
    b=travel_trial.progress_metric('takeoff',leg,{'position':[1,-5,200.01]}, {}, {})
    assert a[0]==b[0] and abs(a[1]-b[1])<.5


def test_interrupted_physical_hold_releases_all_pressed_keys(monkeypatch):
    from tools.second_client import ctl
    from types import SimpleNamespace
    import pytest
    sent=[];inputs=SimpleNamespace(X=SimpleNamespace(KeyPress=2,KeyRelease=3),_send=lambda *v:sent.append(v))
    def interrupt(_):raise KeyboardInterrupt()
    monkeypatch.setattr(ctl.time,'sleep',interrupt)
    with pytest.raises(KeyboardInterrupt):ctl.Input._tap(inputs,[50,25],2)
    assert sent==[(2,50),(2,25),(3,25),(3,50)]

import pytest
from tools.client_compatibility import combat_landing as c


def test_only_healthy_settled_low_level_attackers_allow_combat_landing():
    movement={'in_world':True,'in_combat':True,'dead':False,'on_taxi':False,'health_percent':99}
    extra={'mounted':True,'flying':True,'falling':False,'swimming':False,'indoors':False}
    facts={'attacking_units':[1],'visible_hostiles':[{'guid':1,'level':64,'max_health':5715}]}
    assert c.permitted(movement,extra,facts,85)
    for key in ['dead','on_taxi']:
        assert not c.permitted({**movement,key:True},extra,facts,85)
    for key in ['falling','swimming','indoors']:
        assert not c.permitted(movement,{**extra,key:True},facts,85)
    assert not c.permitted({**movement,'health_percent':79},extra,facts,85)
    assert not c.permitted(movement,extra,{**facts,'attacking_units':[]},85)
    assert not c.permitted(movement,extra,{**facts,'visible_hostiles':[{'guid':1,'level':84,'max_health':5715}]},85)


def test_trial86_airborne_recovery_uses_collision_ceiling_and_soil_patch(monkeypatch):
    site={'map':530,'id':377};start=[-2915.587646,3468.089844,41.764389]
    goal=[-2906.20166,3472.58105,1.08957255]
    monkeypatch.setattr(c.site_boundaries,'active_site',lambda *a:site)
    monkeypatch.setattr(c.site_landing,'select',lambda *a:(goal,{'safe_patch':True}))
    monkeypatch.setattr(c.model_collision,'supporting_surface',lambda *a:{'highest_surface':48})
    checked=[]
    monkeypatch.setattr(c.model_collision,'clear_body_segment',lambda m,a,b:checked.append([a,b]) or True)
    _,selected,plan=c.flight_plan({'map':530,'position':start},{'digsite_ids':[377]})
    assert selected==goal and plan['ceiling']==58
    assert checked==[[[*start[:2],58],[*goal[:2],58]]]
    monkeypatch.setattr(c.model_collision,'clear_body_segment',lambda *a:False)
    with pytest.raises(RuntimeError,match='obstructed'):c.flight_plan({'map':530,'position':start},{'digsite_ids':[377]})
    monkeypatch.setattr(c.model_collision,'supporting_surface',lambda *a:{'highest_surface':200})
    with pytest.raises(RuntimeError,match='excessive'):c.flight_plan({'map':530,'position':start},{'digsite_ids':[377]})


def test_mounted_escape_exceeds_old_continent_leash_and_rejects_blocked_ascent(monkeypatch):
    from tools.client_compatibility import combat_recovery as r
    from types import SimpleNamespace
    position=[0,0,0,0];movement={'dead':False,'health_percent':99}
    extra={'mounted':True,'falling':False,'swimming':False}
    observer=SimpleNamespace(poll=lambda:{'map':530,'position':position[:]})
    def key(name,hold):
        assert name=='space' and hold<=1.5
        position[2]+=hold*28.7
    monkeypatch.setattr(r.archaeology_inputs,'screenshot',lambda p:(movement,extra))
    monkeypatch.setattr(r.model_collision,'clear_body_segment',lambda *a:True)
    monkeypatch.setattr(r.site_boundaries,'contains',lambda *a:True)
    monkeypatch.setattr(r.time,'sleep',lambda *a:None)
    facts={'map':530,'position':[0,0,0,0]}
    keys,observations=r.ascend(SimpleNamespace(key=key),movement,extra,facts,observer,None,{'polygon':[]})
    assert position[2]>=118 and len(keys)==3 and len(observations)==4
    monkeypatch.setattr(r.model_collision,'clear_body_segment',lambda *a:False)
    with pytest.raises(RuntimeError,match='obstruction'):
        r.ascend(SimpleNamespace(key=key),movement,extra,facts,observer,None,{'polygon':[]})

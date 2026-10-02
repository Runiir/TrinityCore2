from tools.client_compatibility import hostile_avoidance as h
from tools.client_compatibility.world.objects import INDEX


def test_visible_living_hostiles_only_and_vertical_clearance(monkeypatch):
    player=[1,1,0,1,1,8,*([0]*8)]
    enemy=[2,14,0,8,8,1,*([0]*8)]
    monkeypatch.setattr(h,'factions',lambda:{1:player,2:enemy})
    unit={'map':0,'movement':{'position':[10,20,3,0]},'fields':{
        INDEX['UNIT_FIELD_FACTIONTEMPLATE']:2,INDEX['UNIT_FIELD_LEVEL']:58,
        INDEX['UNIT_FIELD_HEALTH']:100}}
    hostiles=h.visible_hostiles({123:unit},0,1,85)
    assert len(hostiles)==1 and hostiles[0]['clearance_radius']==9.5
    assert not h.clear([10,20,3],hostiles)
    assert h.clear([10,20,30],hostiles) and h.clear([30,20,3],hostiles)
    unit['fields'][INDEX['UNIT_FIELD_HEALTH']]=0
    assert h.visible_hostiles({123:unit},0,1,85)==[]


def test_trial76_avoidance_cannot_reverse_the_public_bearing():
    import math
    p={'start':[-4208.1352539,335.0686951,117.666542],'heading_radians':math.pi,
        'minimum_bearing_progress':4}
    assert not h.progressive([-4204.76221,335.592987,117.837929],p)
    assert h.progressive([-4218.62061,341.333252,118.52877],p)


def test_unknown_health_strong_enemy_and_low_player_health_prevent_combat_fallback():
    normal=[{'level':69,'max_health':4057}]
    assert h.low_threat(normal,85,True)
    assert not h.low_threat(normal,85,False)
    assert not h.low_threat(normal*4,85,True)
    assert not h.low_threat([{'level':69}],85,True)
    assert not h.low_threat([{'level':73,'max_health':5000000}],85,True)


def test_no_clear_progressive_alternative_retains_a_valid_goal_only_for_low_threats(monkeypatch):
    import pytest
    monkeypatch.setattr(h.site_boundaries,'sites',lambda:{})
    def absent(*a,**kw):raise RuntimeError('no alternative terrain')
    monkeypatch.setattr(h.ground_navigation,'ground_point',absent)
    goal=[10,0,0];hostiles=[{'position':goal,'clearance_radius':9.5,'level':69,'max_health':4057}]
    progress={'start':[0,0,0],'heading_radians':0,'minimum_bearing_progress':5}
    point,record=h.landing(530,goal,hostiles,[],progress=progress,player_level=85,healthy=True)
    assert point==goal and record['survey_progress']==progress
    with pytest.raises(RuntimeError):h.landing(530,goal,hostiles,[],progress=progress,player_level=85,healthy=False)


def test_aggro_avoidance_requires_connected_flat_ground(monkeypatch):
    import math
    import pytest
    site={'id':377,'map':530,'polygon':[[-30,-30],[30,-30],[30,30],[-30,30]]}
    monkeypatch.setattr(h.site_boundaries,'sites',lambda:{377:site})
    monkeypatch.setattr(h.ground_navigation,'ground_point',lambda m,xy:[*xy,0])
    origins=[]
    def flat(m,point,radius,start):
        origins.append(start);return point
    monkeypatch.setattr(h.ground_navigation,'landing_point',flat)
    monkeypatch.setattr(h.ground_navigation,'site_ground_patch',lambda *a:None)
    goal=[0,0,0];hostiles=[{'position':[0,0,0],'clearance_radius':9.5}]
    point,record=h.landing(530,goal,hostiles,[377],[0,0,100])
    assert math.dist(point[:2],goal[:2])>9.5 and origins and all(p==goal for p in origins)
    assert record['position']==point
    def covered(*a):raise RuntimeError('buried navigation floor')
    monkeypatch.setattr(h.ground_navigation,'site_ground_patch',covered)
    with pytest.raises(RuntimeError):h.landing(530,goal,hostiles,[377],[0,0,100])
    monkeypatch.setattr(h.ground_navigation,'site_ground_patch',lambda *a:None)
    def disconnected(*a,**kw):raise RuntimeError('disconnected roof')
    monkeypatch.setattr(h.ground_navigation,'landing_point',disconnected)
    with pytest.raises(RuntimeError):h.landing(530,goal,hostiles,[377],[0,0,100])

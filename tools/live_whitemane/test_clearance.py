import copy
import math
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.live_whitemane import own_pose, clearance, guide


def test_owned_movement_height_is_typed_and_unsupported_layouts_are_rejected():
    player=(9,2<<58|7<<42)
    payload=Writer().guid(*player).pack('4I6f2I',0x1200000,0,0,1234,
        -4170,-2220,80,1.2,0,0,0,1).bits(0,8).finish()
    result=own_pose.parse(payload,player)
    assert result['height_yards']==80 and result['ascending'] and result['flying']
    with pytest.raises(ValueError):own_pose.parse(payload,(8,player[1]))
    with pytest.raises(ValueError):own_pose.parse(payload+b'x',player)
    with pytest.raises(ValueError):own_pose.parse(payload[:-1]+b'\x40',player)


def test_descent_does_not_report_ascent_and_pitch_is_preserved():
    player=(9,2<<58|7<<42)
    payload=Writer().guid(*player).pack('4I6f2I',0x1400000,0,0,1234,
        -4170,-2220,80,1.2,-.4,0,0,1).bits(0,8).finish()
    result=own_pose.parse(payload,player)
    assert result['descending'] and not result['ascending']
    assert result['pitch_radians']==pytest.approx(-.4)


def test_stale_or_unmatched_pose_cannot_supply_flight_height():
    row={'runtime':{'pid':1},'movement':{'speed':20},'archaeology':{
        'world':{'instance':1,'north':0,'west':0},'grounded':False,'flying':True,'falling':False}}
    pose={'runtime':row['runtime'],'observed_at':10,'north':0,'west':0,'flying':True,'falling':False}
    assert own_pose.match(row,pose,now=11)['instance']==1
    assert own_pose.match(row,pose,now=13) is None
    assert own_pose.match(row,{**pose,'north':100},now=11) is None
    assert own_pose.match(row,{**pose,'runtime':{'pid':2}},now=11) is None


def test_ascent_time_follows_actual_height_gap_and_measured_speed():
    samples=[{'client_uptime_ms':1000+i*500,'height_yards':10+i*10,'ascending':True} for i in range(4)]
    pose={**samples[-1],'samples':samples}
    assert clearance.vertical_speed(pose)==20
    assert clearance.remaining_seconds(pose,60)==1
    assert clearance.remaining_seconds(pose,80)==2
    faster=copy.deepcopy(pose)
    for i,s in enumerate(faster['samples']):s['height_yards']=10+i*15
    assert clearance.vertical_speed(faster)==30
    assert clearance.remaining_seconds({**faster,'height_yards':40},60)==pytest.approx(2/3)
    assert clearance.remaining_seconds({'height_yards':40,'samples':[]},60) is None


def test_vertical_rate_handles_old_flag_but_rejects_horizontal_or_downward_motion():
    samples=[{'client_uptime_ms':1000+i*500,'height_yards':10+i*10,
              'ascending':False,'north':0,'west':0} for i in range(4)]
    assert clearance.vertical_speed({'samples':samples})==20
    horizontal=copy.deepcopy(samples)
    for i,s in enumerate(horizontal):s['north']=i*5
    assert clearance.vertical_speed({'samples':horizontal}) is None
    descending=copy.deepcopy(samples)
    for i,s in enumerate(descending):s['height_yards']=50-i*10
    assert clearance.vertical_speed({'samples':descending}) is None


def test_corridor_ceiling_clears_the_highest_reference_surface(monkeypatch):
    def surface(_,p):return {'terrain_height':10+p[0]/2,'model_collision_height':None,'highest_surface':10+p[0]/2}
    monkeypatch.setattr(clearance.model_collision,'supporting_surface',surface)
    monkeypatch.setattr(clearance.model_collision,'column',lambda *_:{'support_height':10})
    row={'owned_pose':{'height_yards':10},'archaeology':{
        'world':{'instance':1,'north':0,'west':0},'grounded':True}}
    result=clearance.plan(row,{'instance':1,'north':20,'west':0})
    assert result['required_climb_yards']==18
    assert result['ceiling_yards']==28
    assert not result['live_client_terrain_asset_match_verified']
    with pytest.raises(RuntimeError,match='departure floor'):
        clearance.plan({**row,'owned_pose':{'height_yards':100}}, {'instance':1,'north':20,'west':0})


def test_red_endpoint_arrival_matches_flight_braking_radius():
    row={'movement':{'facing_radians':0},'archaeology':{
        'world':{'instance':1,'north':0,'west':0},'visible_markers':[]}}
    session={'marker_fallback':True,'telescope_target':{
        'world':{'instance':1,'north':5.5,'west':0},'color':'red','source':'Survey telescope'}}
    result,_=guide.select(row,session,None)
    assert result['arrived']


@pytest.mark.parametrize('clear,ceiling',[(True,13),(False,58)])
def test_near_site_flight_stays_below_an_overhead_roof_only_when_body_path_is_clear(monkeypatch,clear,ceiling):
    def surface(_,point):return {'terrain_height':10,'model_collision_height':50,'highest_surface':50}
    monkeypatch.setattr(clearance.model_collision,'supporting_surface',surface)
    monkeypatch.setattr(clearance.model_collision,'column',lambda *_:{'support_height':10})
    segments=[]
    def check(_,a,b):segments.append((a,b));return clear
    monkeypatch.setattr(clearance.model_collision,'clear_body_segment',check)
    row={'owned_pose':{'height_yards':10},'archaeology':{
        'world':{'instance':1,'north':0,'west':0},'grounded':True,'can_survey':True}}
    result=clearance.plan(row,{'instance':1,'north':60,'west':0})
    assert result['ceiling_yards']==ceiling
    assert result['near_ground_route_clear']==clear
    assert max(math.dist(a[:2],b[:2]) for a,b in segments)<=40


def test_clearance_does_not_climb_over_a_roof_beyond_the_flight_arrival_radius(monkeypatch):
    def surface(_,p):
        roof=60 if p[0]>15 else 10
        return {'terrain_height':10,'model_collision_height':roof,'highest_surface':roof}
    monkeypatch.setattr(clearance.model_collision,'supporting_surface',surface)
    monkeypatch.setattr(clearance.model_collision,'column',lambda *_:{'support_height':10})
    monkeypatch.setattr(clearance.model_collision,'clear_body_segment',lambda *_:True)
    r={'owned_pose':{'height_yards':10},'archaeology':{
        'world':{'instance':1,'north':0,'west':0},'grounded':True,'can_survey':True}}
    p=clearance.plan(r,{'instance':1,'north':20,'west':0},arrival_tolerance=6)
    assert p['planned_horizontal_yards']==14 and p['ceiling_yards']==13
    assert max(c['north'] for c in p['columns'])==14


def test_a_real_high_corridor_is_not_rejected_by_an_arbitrary_climb_cutoff(monkeypatch):
    def surface(_,point):
        height=5.75 if point[0]==0 else 119.09
        return {'terrain_height':height,'model_collision_height':None,'highest_surface':height}
    monkeypatch.setattr(clearance.model_collision,'supporting_surface',surface)
    monkeypatch.setattr(clearance.model_collision,'column',lambda *_:{'support_height':5.75})
    row={'owned_pose':{'height_yards':5.75},'archaeology':{
        'world':{'instance':1,'north':0,'west':0},'grounded':True}}
    result=clearance.plan(row,{'instance':1,'north':191,'west':0})
    assert result['required_climb_yards']==pytest.approx(121.34)
    assert result['ceiling_yards']==pytest.approx(127.09)
    monkeypatch.setattr(clearance.model_collision,'supporting_surface',lambda *_:{'highest_surface':float('nan')})
    row['archaeology']['grounded']=False
    with pytest.raises(RuntimeError,match='finite reference surface'):
        clearance.plan(row,{'instance':1,'north':191,'west':0})

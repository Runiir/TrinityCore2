import copy
import pytest
from tools.client_compatibility.world.buffer import Writer
from tools.live_whitemane import own_pose, clearance, guide


def test_owned_movement_height_is_typed_and_unsupported_layouts_are_rejected():
    player=(9,2<<58|7<<42)
    payload=Writer().guid(*player).pack('4I6f2I',0x1400000,0,0,1234,
        -4170,-2220,80,1.2,0,0,0,1).bits(0,8).finish()
    result=own_pose.parse(payload,player)
    assert result['height_yards']==80 and result['ascending'] and result['flying']
    with pytest.raises(ValueError):own_pose.parse(payload,(8,player[1]))
    with pytest.raises(ValueError):own_pose.parse(payload+b'x',player)
    with pytest.raises(ValueError):own_pose.parse(payload[:-1]+b'\x40',player)


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

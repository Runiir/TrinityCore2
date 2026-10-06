import math
from tools.client_compatibility.observation.telemetry import checksum
from . import guide, snapshot
from .motion import turn_duration


def test_pickup_visits_the_new_marker_at_the_collected_spot_but_not_nearby_uncollected_spots():
    session={'marker_target':None,'marker_fallback':True}
    row={'archaeology':{'visible_markers':[
        {'marker_id':'nearby','distance_yards':2},
        {'marker_id':'just_collected','distance_yards':.08}]}}
    guide.pickup(session,row)
    assert session['visited_marker_ids']==['just_collected']
    guide.pickup(session,row)
    assert session['visited_marker_ids']==['just_collected']


def test_arrow_timestamp_does_not_replace_survey_uptime_and_altitude_is_not_terrain_height():
    flags=32|128|256|1024
    length=snapshot.HEADER.size+snapshot.ARROW.size+4+2+2
    payload=snapshot.HEADER.pack(b'TCA1',length,42,17000,flags,1,
        10000000,10000000,3,12000,1,321,0,0,0,0)
    payload+=snapshot.ARROW.pack(10000000,10000000,0,13100,1791200000)
    payload+=(10004500).to_bytes(4,'big')+checksum(b'Troll Archaeology Find').to_bytes(2,'big')
    payload+=checksum(payload).to_bytes(2,'big')
    result=snapshot.decode(payload)
    assert result['last_survey_uptime_ms']==12000
    assert result['arrow']['observed_at']==1791200000
    assert result['altitude_yards']==45
    assert result['height_above_ground_yards'] is None
    assert result['grounded']


def test_marker_endpoint_survives_motion_and_changed_minimap_order():
    session={}
    row={'movement':{'facing_radians':0},'archaeology':{'world':{'instance':1,'north':0,'west':0},
         'visible_markers':[{'marker_id':'first','distance_yards':20,'heading_radians':0}],
         'arrow':None}}
    first,_=guide.select(row,session,None)
    row['archaeology']['world']['north']=15
    row['archaeology']['visible_markers']=[{'marker_id':'other','distance_yards':2,'heading_radians':math.pi}]
    second,_=guide.select(row,session,None)
    assert second['marker_id']=='first'
    assert second['world']==first['world']
    assert second['distance_yards']==5


def test_failed_marker_survey_latches_telescope_until_confirmed_pickup():
    session={'visited_marker_ids':[],'marker_target':{'marker_id':'old'}}
    route={'source':'GatherMate marker','arrived':True,'marker_id':'old'}
    guide.marker_survey_outcome(session,route,{'entry':206590},False)
    assert not session.get('marker_fallback')
    guide.marker_survey_outcome(session,route,{'entry':206590},False)
    assert session['marker_fallback']
    assert session['marker_target'] is None
    guide.pickup(session)
    assert not session['marker_fallback']


def test_measured_turn_crossing_zero_times_one_full_turn():
    steps=[{'index':1,'completed':True,'action':'turn_left',
        'before':{'movement':{'facing_radians':6.0}},'after':{'movement':{'facing_radians':(6.0+.99)%math.tau}},
        'inputs':[{'arguments':{'key':'Left','hold':.3}}]}]
    duration,calibration=turn_duration(2.2,steps)
    assert abs(duration-2/3)<.00001
    assert abs(calibration['radians_per_second']-3.3)<.00001
    assert duration>.3

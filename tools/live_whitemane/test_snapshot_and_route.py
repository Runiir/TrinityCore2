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


def test_one_positive_telescope_at_a_marker_moves_search_on_without_a_second_survey():
    session={'visited_marker_ids':[],'marker_target':{'marker_id':'old'}}
    route={'source':'GatherMate marker','arrived':True,'marker_id':'old'}
    guide.marker_survey_outcome(session,route,{'entry':206590},False)
    assert session['marker_fallback']
    assert session['marker_target'] is None
    assert session['visited_marker_ids']==session['failed_marker_ids']==['old']
    guide.pickup(session)
    assert not session['marker_fallback']
    assert 'failed_marker_ids' not in session


def test_interrupted_flight_keeps_an_untested_marker_eligible():
    target={'marker_id':'untested','world':{'instance':1,'north':20,'west':0}}
    session={'marker_target':target,'marker_fallback':False,'telescope_target':{},'last_green_endpoint':{}}
    guide.reobserve(session)
    assert session=={'marker_target':target,'marker_fallback':False,'walked_since_survey':True}


def test_delayed_matching_marker_replaces_cached_green_short_step():
    origin={'instance':1,'north':0,'west':0}
    row={'movement':{'facing_radians':0},'archaeology':{'world':origin,
        'visible_markers':[{'marker_id':'saved','distance_yards':math.hypot(26.49,2),
            'heading_radians':math.atan2(2,26.49)}],
        'arrow':{'observed_at':100,'boundary_verified':True,'origin':origin,
            'heading_radians':0,'endpoint':{'instance':1,'north':40,'west':0}}},
        'farm_ui':{'survey_guidance':{'at':94.4,'candidate_matches':True,'candidate_along_yards':29.2}}}
    tool={'entry':204272,'observed_at':100,'facing_radians':0}
    session={'marker_fallback':True}
    assert guide.select(row,session,tool)[0]['distance_yards']==3
    row['archaeology']['arrow']['endpoint']['north']=26.49
    row['farm_ui']['survey_guidance'].update(at=100,candidate_along_yards=26.49)
    route,_=guide.select(row,session,tool)
    assert route['source']=='GatherMate marker' and route['marker_id']=='saved'
    assert route['world']['north']==26.49 and abs(route['world']['west']-2)<1e-9
    assert route['recorded_marker_matches'] and route['distance_yards']>26
    assert 'telescope_target' not in session


def test_delayed_candidate_outside_displayed_markers_upgrades_the_addon_endpoint():
    origin={'instance':1,'north':0,'west':0}
    row={'movement':{'facing_radians':0},'archaeology':{'world':origin,'visible_markers':[],
        'arrow':{'observed_at':100,'boundary_verified':True,
            'endpoint':{'instance':1,'north':26.49,'west':0}}},'farm_ui':{}}
    tool={'entry':204272,'observed_at':100,'facing_radians':0};session={'marker_fallback':True}
    assert guide.select(row,session,tool)[0]['distance_yards']==3
    row['farm_ui']['survey_guidance']={'at':100,'candidate_matches':True}
    route,_=guide.select(row,session,tool)
    assert route['distance_yards']==26.49 and route['recorded_marker_matches']


def test_a_failed_marker_is_not_reselected_by_the_same_bearing():
    origin={'instance':1,'north':0,'west':0}
    row={'movement':{'facing_radians':0},'archaeology':{'world':origin,
        'visible_markers':[{'marker_id':'failed','distance_yards':20,'heading_radians':0}],
        'arrow':{'observed_at':100,'boundary_verified':True,'origin':origin,'heading_radians':0,
            'endpoint':{'instance':1,'north':20,'west':0}}},
        'farm_ui':{'survey_guidance':{'at':100,'candidate_matches':True,'candidate_along_yards':20}}}
    session={'marker_fallback':True,'failed_marker_ids':['failed'],'visited_marker_ids':['failed']}
    route,_=guide.select(row,session,{'entry':204272,'observed_at':100,'facing_radians':0})
    assert route['source']=='Survey telescope' and session.get('marker_target') is None


def test_measured_turn_crossing_zero_times_one_full_turn():
    steps=[{'index':1,'completed':True,'action':'turn_left',
        'before':{'movement':{'facing_radians':6.0}},'after':{'movement':{'facing_radians':(6.0+.99)%math.tau}},
        'inputs':[{'arguments':{'key':'Left','hold':.3}}]}]
    duration,calibration=turn_duration(2.2,steps)
    assert abs(duration-2/3)<.00001
    assert abs(calibration['radians_per_second']-3.3)<.00001
    assert duration>.3

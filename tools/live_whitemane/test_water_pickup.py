import copy
from types import SimpleNamespace
import pytest
from . import guide,pending_find,pickup_intent,survey_find,swim_vertical,dig_decisions,camera_input,sticky_input
from .test_farm_loop import row
from .test_fast_waypoint import setup_route


def submerged(height=10,find_height=5):
    r=row();r['movement']['facing_radians']=0
    r['archaeology'].update(swimming=True,casting=False,falling=False,site_id=179,
        looted_finds=0,successful_surveys=1,loot_open=False)
    r['owned_pose']={'height_yards':height,'client_uptime_ms':100}
    r['visible_find']={'world':dict(r['archaeology']['world']), 'height_yards':find_height,
        'distance_yards':0,'observed_at':1,
        'source':'owned_authenticated_visible_find_create_after_own_survey'}
    return r


def test_same_horizontal_point_is_not_underwater_interaction_range():
    r=submerged();assert not survey_find.in_range(r)
    target,_=guide.select(r,{'reapproach_find':True},None)
    assert target['height_error_yards']==-5 and not target['arrived']
    r['owned_pose']['height_yards']=5.2
    assert survey_find.in_range(r) and guide.select(r,{'reapproach_find':True},None)[0]['arrived']


def test_underwater_range_error_keeps_owned_find_depth_and_interrupts_old_loot(monkeypatch,tmp_path):
    monkeypatch.setattr(pending_find.runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    r=submerged();session={}
    value=pending_find.latch(r,approach=r['visible_find'])
    pickup_intent.offer(session,r,value,'loot',{}, {},{})
    assert pickup_intent.retained(session,r,value) is None
    pending_find.out_of_range(r,session)
    assert session['pickup_approach']['height_yards']==5
    assert pending_find.load(r)['approach']['source']==r['visible_find']['source']


def test_depth_correction_uses_the_ui_head_and_keeps_all_legal_depth_actions(monkeypatch):
    state={'task':'collect the pending find','available':True,'casting':False,'artifact_visible':True,
        'instrument_current':False,'swimming':True,'artifact_height_error_yards':-5,
        'guide_arrived':False,'telescope':{'distance_yards':0,'heading_relative_to_player':'aligned'},
        'pickup':{'uncollected':True,'interaction_in_range':False}}
    monkeypatch.setattr(dig_decisions.decisions,'choose',lambda *_:pytest.fail('horizontal-only head'))
    def choose(context,instructions,options):
        assert context['swimming'] and context['artifact_height_error_yards']==-5
        assert {'swim_up','swim_down','loot'}<=options.keys() and 'swim down' in instructions
        return 'swim_down',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='swim_down'


@pytest.mark.parametrize('action,sign,key',[('swim_down',-1,'x'),('swim_up',1,'space')])
def test_selected_swim_adjustment_retains_input_and_stops_at_observed_find_height(monkeypatch,tmp_path,action,sign,key):
    r,now,events,controllers,_=setup_route(monkeypatch,tmp_path)
    before=submerged(10,10+sign*4)
    monkeypatch.setattr(swim_vertical.inputs,'focus',lambda _: {})
    monkeypatch.setattr(swim_vertical,'time',SimpleNamespace(time=lambda:now[0],monotonic=lambda:now[0],sleep=lambda _:None))
    def sticky(sender):
        controller=sticky_input.StickyInput(sender,clock=lambda:now[0],threaded=False)
        controllers.append(controller);return controller
    monkeypatch.setattr(swim_vertical,'StickyInput',sticky)
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1
        if controllers:controllers[0].tick()
        fresh=copy.deepcopy(before);fresh['observed_at']=now[0]
        fresh['owned_pose'].update(client_uptime_ms=index[0]*100,
            height_yards=10+sign*min(4,max(0,index[0]-1)*.5))
        return fresh
    monkeypatch.setattr(swim_vertical,'observe',observe)
    target={'world':{'height_yards':10+sign*4}}
    outcome=swim_vertical.move(tmp_path,action,target,before)
    assert outcome['completed'] and outcome['outcome']=='target_depth_reached'
    assert outcome['target_source']=='owned visible find' and outcome['fixed_hold_seconds'] is None
    assert events.count(('press',key))==events.count(('release',key))==1


def test_unknown_depth_probe_does_not_claim_success_without_observed_motion(monkeypatch,tmp_path):
    _,now,events,controllers,_=setup_route(monkeypatch,tmp_path)
    before=submerged();monkeypatch.setattr(swim_vertical.inputs,'focus',lambda _: {})
    monkeypatch.setattr(swim_vertical,'time',SimpleNamespace(time=lambda:now[0],monotonic=lambda:now[0],sleep=lambda _:None))
    def sticky(sender):
        controller=sticky_input.StickyInput(sender,clock=lambda:now[0],threaded=False)
        controllers.append(controller);return controller
    monkeypatch.setattr(swim_vertical,'StickyInput',sticky)
    def observe(_):
        now[0]+=.1
        if controllers:controllers[0].tick()
        fresh=copy.deepcopy(before);fresh['owned_pose']['client_uptime_ms']=int(now[0]*1000)
        return fresh
    monkeypatch.setattr(swim_vertical,'observe',observe)
    outcome=swim_vertical.move(tmp_path,'swim_down',None,before)
    assert not outcome['completed'] and outcome['outcome']=='no_observed_depth_progress'
    assert outcome['target_height_yards']==7 and outcome['target_source']=='local depth probe'
    assert events.count(('press','x'))==events.count(('release','x'))==1


def test_swimming_still_requires_owned_height_before_any_depth_input(tmp_path):
    before=submerged();before['owned_pose']=None
    with pytest.raises(RuntimeError,match='owned height'):
        swim_vertical.move(tmp_path,'swim_down',None,before)


def test_horizontal_swimming_retains_forward_without_trying_to_mount(monkeypatch,tmp_path):
    from . import fast_waypoint
    r,now,events,controllers,calls=setup_route(monkeypatch,tmp_path,20)
    r['archaeology'].update(flying=False,mounted=False,grounded=False,swimming=True)
    r['farm_ui']['move_speeds']['swim']=5
    index=[0]
    def observe(_):
        index[0]+=1;now[0]+=.1;controllers[0].tick()
        fresh=copy.deepcopy(r);fresh['observed_at']=now[0]
        fresh['movement'].update(sequence=index[0],client_uptime_ms=index[0]*100)
        fresh['archaeology']['sequence']=index[0]
        fresh['owned_pose']={'pitch_radians':0,'client_uptime_ms':index[0]*100}
        if index[0]>=8:fresh['archaeology']['world']['north']=0
        return fresh
    monkeypatch.setattr(fast_waypoint,'observe',observe)
    outcome=fast_waypoint.walk(tmp_path,{'instance':1,'north':0,'west':0},tolerance=.5,
        approved_intent=('forward_long',{}, {},{}))
    assert outcome[-1]['outcome']=='waypoint_arrived' and not calls
    assert events.count(('press','Up'))==events.count(('release','Up'))==1
    assert not any(key in ('space','shift+space') for event,key in events if event=='press')

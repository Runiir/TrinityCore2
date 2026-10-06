import copy
import pytest
from . import pending_find,dig_context,dig_decisions,guide,runtime,survey_find
from .test_farm_loop import row


@pytest.fixture
def collected(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path);(tmp_path/'run').mkdir()
    value=row();value['movement']['facing_radians']=0
    value['archaeology'].update(site_id=331,can_survey=True,successful_surveys=9,looted_finds=3)
    value['farm_ui']['survey']={'ready':True}
    value['owned_pose']={'height_yards':20}
    pending_find.confirm_pickup(value)
    return value


def test_observed_collection_exposes_an_untried_survey_and_a_failed_cast_keeps_it(collected):
    state=dig_context.model_state(collected,None,False,None,[])
    assert state['artifact_collected_at_current_position']
    assert state['survey_at_pickup_position_untried']
    assert state['successful_survey_since_pickup'] is False
    failed={'action':'survey','completed':False,'failure':'Survey did not succeed'}
    assert dig_context.model_state(collected,None,False,None,[failed])['survey_at_pickup_position_untried']
    collected['archaeology']['successful_surveys']+=1
    facts=pending_find.pickup_position_facts(collected)
    assert facts['successful_survey_since_pickup'] and not facts['survey_at_pickup_position_untried']


@pytest.mark.parametrize('change',['move','height','site','replacement','reset','client'])
def test_pickup_fact_cannot_follow_the_player_to_another_position_or_generation(collected,change):
    if change=='move':collected['archaeology']['world']['north']+=2
    elif change=='height':collected['owned_pose']['height_yards']+=2
    elif change=='site':collected['archaeology']['site_id']=332
    elif change=='replacement':collected['archaeology']['can_survey']=False
    elif change=='reset':collected['archaeology']['successful_surveys']=0
    else:collected['runtime']={'pid':2}
    assert not pending_find.pickup_position_facts(collected)['survey_at_pickup_position_untried']


@pytest.mark.parametrize('choice',['survey','forward_short','observe'])
def test_post_pickup_keeps_movement_legal_and_accepts_layas_choice(collected,monkeypatch,choice):
    target={'source':'GatherMate marker','world':{'instance':1,'north':15,'west':0},
        'color':'green','distance_yards':15,'arrived':False,'heading_relative_to_player':'aligned'}
    state=dig_context.model_state(collected,target,False,None,[])
    monkeypatch.setattr(dig_decisions.decisions,'choose',lambda *_:pytest.fail('new fact would be discarded'))
    def choose(context,instructions,options):
        assert context['survey_at_pickup_position_untried'] and 'in place' in instructions
        assert context['current_position']['survey_since_collection'] is False
        assert context['telescope']==state['telescope'] and context['recent_outcomes']==state['recent_outcomes']
        assert set(options)=={'observe','inspect','camera_forward','camera_ground','survey','forward_short','forward_long'}
        return choice,{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]==choice


def test_pending_artifact_still_requires_pickup_before_resurvey(collected,monkeypatch):
    state=dig_context.model_state(collected,None,True,{'out_of_range':True},[])
    def choose(context,instructions,options):
        assert 'loot' in options and 'survey' not in options
        return 'loot',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='loot'


def test_observed_find_height_on_land_does_not_count_a_roof_as_artifact_arrival(collected):
    collected['visible_find']={'world':copy.deepcopy(collected['archaeology']['world']),
        'height_yards':5,'distance_yards':0,'source':'owned_authenticated_visible_find_create_after_own_survey'}
    target,_=guide.select(collected,{'reapproach_find':True},None)
    assert target['distance_yards']==0 and target['height_error_yards']==-15
    assert not target['arrived']
    assert not survey_find.in_range(collected)


def test_missing_pickup_receipt_cannot_invent_a_collection(monkeypatch,tmp_path):
    monkeypatch.setattr(runtime,'ROOT',tmp_path)
    assert not pending_find.pickup_position_facts(row())['survey_at_pickup_position_untried']

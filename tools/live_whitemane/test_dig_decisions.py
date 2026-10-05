from . import dig_decisions,dig_context,guide
from .test_farm_loop import row
import math
import pytest


def test_digging_receives_feedback_and_cannot_offer_a_spell_on_cooldown(monkeypatch):
    state={'available':True,'casting':False,'artifact_visible':False,'can_survey':True,
        'survey_ready':False,'telescope':{'color':'green','distance_yards':14.39},
        'recent_outcomes':[{'action':'survey','moved_yards':0,'pickup_confirmed':False}]}
    def choose(observed,instructions,options):
        assert observed['recent_outcomes']==state['recent_outcomes']
        assert 'survey' not in options and 'forward_short' in options
        return 'forward_short',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='forward_short'


def test_stalled_turns_sample_the_unmodified_model_distribution(monkeypatch):
    options={'turn_right':'Turn', 'loot':'Interact', 'observe':'Wait'}
    response={'answers':{'action':{'choice':'turn_right',
        'probabilities':{'turn_right':.4,'loot':.3,'observe':.3}}}}
    def sample(actions,weights,k):
        assert actions==list(options) and weights==[.4,.3,.3] and k==1
        return ['loot']
    monkeypatch.setattr(dig_decisions.random,'choices',sample)
    assert dig_decisions.explore('turn_right',response,options,
        {'consecutive_turns_without_approach':40})=='loot'
    assert response['answers']['action']['choice']=='turn_right'
    assert response['policy_selection']['selected_action']=='loot'
    assert response['policy_selection']['actions_removed']==[]


def test_normal_decisions_keep_the_model_choice(monkeypatch):
    monkeypatch.setattr(dig_decisions.random,'choices',lambda *a,**k:pytest.fail('unexpected sampling'))
    assert dig_decisions.explore('loot',{}, {}, {'consecutive_turns_without_approach':2})=='loot'


@pytest.mark.parametrize('probabilities',[{'turn_right':1.0},{'turn_right':float('nan'),'loot':.5}])
def test_exploration_rejects_incomplete_or_invalid_model_probabilities(probabilities):
    response={'answers':{'action':{'probabilities':probabilities}}}
    with pytest.raises(RuntimeError,match='complete legal action distribution'):
        dig_decisions.explore('turn_right',response,{'turn_right':'Turn','loot':'Interact'},
            {'consecutive_turns_without_approach':3})


def test_context_reports_wrong_turn_and_keeps_pickup_range_unknown():
    before=row();before['archaeology']['world']={'instance':1,'north':0,'west':0}
    before['movement']['facing_radians']=0
    after=row();after['archaeology']['world']=before['archaeology']['world']
    after['movement']['facing_radians']=-.2
    target={'source':'last green Survey endpoint','world':{'instance':1,'north':1,'west':1},
        'color':'green','arrived':False,'distance_yards':math.sqrt(2),'heading_relative_to_player':'left'}
    step={'action':'turn_right','completed':True,'before':before,'after':after,'guide':target,
        'walked_yards':0,'confirmed_looted_find':False}
    state=dig_context.model_state(after,target,True,{'out_of_range':False},[step]*4)
    recent=state['recent_outcomes'][-1]
    assert recent['bearing_improvement_degrees']<0
    assert state['consecutive_turns_without_approach']==4
    assert state['consecutive_actions_without_progress']==4
    assert state['pickup_range']=='unknown' and state['guide_position_is_estimate']
    step['walked_yards']=.5
    assert dig_context.model_state(after,target,True,{'out_of_range':False},[step])[
        'consecutive_turns_without_approach']==0


def test_a_forward_command_without_displacement_does_not_clear_stall_feedback():
    before=row();before['archaeology']['world']={'instance':1,'north':0,'west':0}
    before['movement']['facing_radians']=0
    target={'source':'GatherMate marker','world':{'instance':1,'north':2,'west':0},
        'color':'green','arrived':True,'distance_yards':2,'heading_relative_to_player':'aligned'}
    step={'action':'forward_long','completed':True,'before':before,'after':before,'guide':target,
        'walked_yards':0,'confirmed_looted_find':False}
    state=dig_context.model_state(before,target,False,None,[step]*4)
    assert state['guide_arrived'] and state['consecutive_actions_without_progress']==4
    assert state['consecutive_turns_without_approach']==0


def test_pickup_guide_exposes_its_actual_arrival_tolerance():
    before=row();before['archaeology']['world']={'instance':1,'north':0,'west':0}
    before['movement']['facing_radians']=0
    session={'reapproach_find':True,'pickup_approach':{'world':{'instance':1,'north':.93,'west':0}}}
    target,_=guide.select(before,session,None)
    assert not target['arrived'] and target['arrival_tolerance_yards']==.5

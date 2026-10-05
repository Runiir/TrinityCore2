from . import pending_find,farm_policy,interact,dig_context,dig_decisions
from .dig_policy import SolveBatches
from .test_farm_loop import row


def test_uncollected_find_retains_pickup_even_after_site_replacement():
    r=row();r['archaeology'].update(can_survey=False,site_id=None,falling=False)
    r['pending_find']={'out_of_range':False,'approach':{'world':r['archaeology']['world']}}
    r['archaeology']['races'][0].update(fragments=180,cost=35)
    actions=farm_policy.legal_actions(r,SolveBatches())
    assert set(actions)=={'wait','minimap','dig'}
    facts=pending_find.facts(r,r['pending_find'])
    assert facts['uncollected'] and not facts['travel_ready']
    assert facts['exit_pickup_on']=='fragment gain or pickup counter increase'


def test_solve_choices_start_at_150_and_continue_an_existing_batch():
    r=row();r['archaeology'].update(mounted=False,flying=False,falling=False)
    race=r['archaeology']['races'][0];race.update(fragments=149,cost=35)
    batches=SolveBatches();name='solve_'+str(race['index'])
    assert name not in farm_policy.legal_actions(r,batches)
    race['fragments']=150
    assert name in farm_policy.legal_actions(r,batches)
    race['fragments']=40;batches.active_races.add(race['index'])
    assert name in farm_policy.legal_actions(r,batches)


def test_pickup_scan_covers_small_ground_objects_between_coarse_rows():
    points=interact.search_points(100)
    assert len(points)==100 and len(set(points))==100
    assert any(592<=x<=608 and 516<=y<=528 for x,y in points)


def test_a_tooltip_search_miss_is_given_to_laya_as_an_unfinished_pickup():
    r=row();pending={'out_of_range':False,'approach':None,'gathering_starts':2}
    r['farm_ui']['gathering']={'starts':2}
    step={'action':'loot','completed':False,'failure':'no matching public tooltip in bounded interaction search'}
    state=dig_context.model_state(r,None,True,pending,[step]*4)
    assert state['pickup']['state']=='locate' and not state['pickup']['gather_cast_seen']
    assert state['recent_outcomes'][-1]['outcome']=='tooltip_search_missed'
    assert state['consecutive_actions_without_progress']==4


def test_survey_is_a_next_state_action_after_the_pending_find_is_collected(monkeypatch):
    state={'available':True,'casting':False,'artifact_visible':True,'can_survey':True,
        'survey_ready':True,'telescope':None,'pickup':{'uncollected':True}}
    def choose(_,instructions,options):
        assert 'loot' in options and 'survey' not in options
        return 'loot',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='loot'


def test_combat_fact_preempts_pickup_and_preserves_it_for_after_combat():
    r=row();r['movement']['in_combat']=True
    r['archaeology'].update(falling=False,can_survey=False)
    r['pending_find']={'out_of_range':False}
    assert set(farm_policy.legal_actions(r,SolveBatches()))=={'wait','minimap','combat'}
    r['movement']['in_combat']=False
    assert 'dig' in farm_policy.legal_actions(r,SolveBatches())


def test_completed_waypoint_returns_to_locating_the_uncollected_object(monkeypatch):
    state={'available':True,'casting':False,'artifact_visible':False,'can_survey':True,
        'survey_ready':True,'telescope':{'color':'green'},'guide_arrived':True,
        'pickup':{'uncollected':True}}
    def choose(_,instructions,options):
        assert 'loot' in options and 'survey' not in options
        assert 'forward_short' not in options and 'forward_long' not in options
        return 'loot',{},{}
    monkeypatch.setattr(dig_decisions.laya_ui,'choose',choose)
    assert dig_decisions.choose(state)[0]=='loot'

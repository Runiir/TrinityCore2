from . import dig_decisions


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

from tools.client_compatibility.bridge_archaeology_probe import confined_survey_stall


def observed(x,colour='yellow',finds=None):
    return {'session':'owned','player':{'position':[x,0,5,0]},
        'tool':{'color':colour},'finds':finds or []}


def history(points):
    return [{'index':i,'action':'forward_long','session':'owned','site':207,
        'tcp':observed(x)} for i,x in enumerate(points)]


def test_repeated_backtracking_without_lantern_progress_stops():
    stall=confined_survey_stall(history([0,3,0,3,0,3]),observed(0),207)
    assert stall['forward_step_indices']==list(range(6))
    assert stall['diameter_yards']==3


def test_a_legitimate_long_detour_continues():
    assert confined_survey_stall(history([0,3,6,9,12,15]),observed(18),207) is None


def test_lantern_improvement_and_artifact_visibility_clear_stall():
    steps=history([0,3,0,3,0,3])
    assert confined_survey_stall(steps,observed(0,'green'),207) is None
    assert confined_survey_stall(steps,observed(0,finds=[{'guid':1}]),207) is None


def test_another_site_or_session_does_not_supply_stall_history():
    steps=history([0,3,0,3,0,3])
    assert confined_survey_stall(steps,observed(0),144) is None
    steps[-2]['session']='old'
    assert confined_survey_stall(steps,observed(0),207) is None

import math
import pytest
from tools.client_compatibility import ground_navigation as ground,lab_runtime as lab
from tools.client_compatibility.collision_recovery import Recovery


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_grangolvar_detour_survives_a_new_survey_bearing():
    # Actual trial 44 bank approach. The ground corridor first moves south,
    # then returns north to the lower floor. Replanning the short ray after
    # every Survey reversed this detour before it reached the corner.
    origin=[-2433.069091796875,4959.64404296875,33.883575439453125,1.2974700927734375]
    tcp={'player':{'position':origin},'tool':{'map':530,'heading_radians':1.3226885795593262}}
    plan=ground.walk_plan(tcp,3.5,[371])
    assert plan['detour_committed']
    assert plan['points'][1][1]<4950 and plan['points'][-1][1]>4962
    plan['remaining_ground_points']=plan['points'][1:]
    r=Recovery();step={'index':0,'action':'forward_short','tcp':tcp,
        'input':{'hold_seconds':.5,'ground_route':plan}}
    moved=[-2432.544677734375,4956.33251953125,34.68336868286133,1.4985326528549194]
    r.update([step],{'player':{'position':moved}})
    observed={'player':{'position':moved},'tool':{'map':530,'heading_radians':1.576128363609314}}
    fresh=ground.walk_plan(observed,3.5,[371])
    assert fresh['points'][-1][1]>4959 and not fresh['detour_committed']
    retained=ground.walk_plan(observed,3.5,[371],r.for_action('forward_short'))
    assert retained['retained_survey_detour'] and retained['points'][0][1]<4950
    # Once the corner is reached, continue to the committed lower-floor goal.
    observed['player']['position']=[-2432.0647,4949.3789,34.7655,1.45]
    next_plan=ground.walk_plan(observed,3.5,[371],r.for_action('forward_short'))
    assert len(next_plan['points'])==1 and next_plan['points'][0][1]>4962
    assert math.dist(next_plan['points'][0][:2],plan['points'][-1][:2])<.001

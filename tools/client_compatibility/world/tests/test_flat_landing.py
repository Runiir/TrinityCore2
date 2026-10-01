"""Regression fixtures from the live Outland hillside slide."""
import json
import subprocess
import pytest
from tools.client_compatibility import ground_navigation as ground,lab_runtime as lab


@pytest.mark.skipif(not (lab.ROOT/'build/dep/recastnavigation/Detour/libDetour.a').exists(),reason='private public-navmesh helper is not provisioned')
def test_landing_rejects_steep_detail_and_covered_flat_ground():
    goal=[-315.518066,3182.38916,120.252457]
    result=subprocess.run([str(ground.binary()),str(lab.BASE/'data/mmaps'),'530','--landing',
        *map(str,goal),'20'],capture_output=True,text=True,check=True)
    landing=json.loads(result.stdout)
    assert 0<=landing['detail_slope_degrees']<=40
    assert ground.ground_point(530,landing['position'])==landing['position']
    assert landing['position'][2]<110


def test_survey_flight_respects_explicit_landing_radius():
    from tools.client_compatibility import travel_trial
    movement=dict(in_world=True,dead=False,in_combat=False,on_taxi=False)
    extra=dict(casting=False,mounted=True,flying=False,falling=False)
    facts=dict(position=[107,200,20,0],map=0,transferring=False)
    state=travel_trial.state(dict(mode='flight',map=0,position=[100,200,20],arrival_radius=1.5),movement,extra,facts,{'nodes':[]})
    assert not state['destination_reached'] and not state['near_destination']

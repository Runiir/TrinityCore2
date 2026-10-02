import pytest
from tools.client_compatibility import takeoff_exit as exit,model_collision,lab_runtime as lab


FOOT=[-4205.197265625,469.1246032714844,30.728389739990234]
EXTRA={'digsite_ids':[399],'mounted':True,'flying':False,'falling':False,'swimming':False}


@pytest.mark.skipif(not (lab.BASE/'data/maps/5303931.map').exists(),reason='public terrain absent')
def test_trial73_grounded_overhang_has_a_connected_clear_ground_exit():
    facts={'map':530,'position':FOOT}
    assert exit.needed(facts,EXTRA)
    hover=[-4204.46826171875,468.3486633300781,35.43946075439453]
    assert exit.needed({'map':530,'position':hover},{**EXTRA,'flying':True})
    plan=exit.select(facts,EXTRA)
    assert plan['site_id']==399 and plan['point'][2]<33
    assert plan['safe_patch']['raw_terrain_height_tolerance_yards']==1.5
    assert all(model_collision.clear_body_segment(530,a,b) for a,b in
        zip([FOOT,*plan['route']['points']],plan['route']['points']))
    assert not exit.needed({'map':530,'position':plan['point']},EXTRA)


@pytest.mark.skipif(not (lab.BASE/'data/vmaps/530.vmtree').exists(),reason='public collision absent')
def test_trial73_overhead_model_blocks_a_vertical_body_segment():
    assert not model_collision.clear_body_segment(530,FOOT,[FOOT[0],FOOT[1],FOOT[2]+20])


def test_ground_exit_does_not_accept_combat_or_airborne_state():
    facts={'map':530,'position':[0,0,0]};site={'polygon':[[-5,-5],[5,-5],[5,5],[-5,5]]}
    movement={'in_world':True,'health_percent':100,'dead':False,'in_combat':True,'on_taxi':False}
    with pytest.raises(RuntimeError,match='unavailable'):exit.available(movement,EXTRA,facts,530,site)
    movement['in_combat']=False
    with pytest.raises(RuntimeError,match='settled'):exit.available(movement,{**EXTRA,'falling':True},facts,530,site)

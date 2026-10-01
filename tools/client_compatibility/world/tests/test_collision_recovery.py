import pytest
from tools.client_compatibility.collision_recovery import Recovery


def attempt(index,position):
    return {'index':index,'action':'forward_short','input':{'hold_seconds':.5},
            'tcp':{'player':{'position':position}}}


def test_blocked_movement_recovers_then_stops_repeating():
    r=Recovery();history=[];tcp={'player':{'position':[0,0,1,0]}}
    for i in range(2):
        history.append(attempt(i,[0,0,1,0]));r.update(history,tcp)
    assert r.for_action('survey') is None
    for i in range(3):assert r.for_action('forward_short')['attempt']==i+1
    with pytest.raises(RuntimeError):r.for_action('forward_short')
    history.append(attempt(2,[0,0,1,0]));r.update(history,{'player':{'position':[3,0,1,0]}})
    assert r.for_action('forward_short') is None


def test_height_change_without_horizontal_progress_is_blocked():
    r=Recovery();r.update([attempt(0,[0,0,1,0])],{'player':{'position':[0,0,6,0]}})
    r.update([attempt(1,[0,0,6,0])],{'player':{'position':[0,0,7,0]}})
    assert r.for_action('forward_short')['attempt']==1


def test_small_mesh_corner_displacement_is_real_progress():
    r=Recovery()
    for i in range(3):
        step=attempt(i,[0,0,1,0]);step['input']['hold_seconds']=.04
        r.update([step],{'player':{'position':[.25,0,1,0]}})
    assert r.for_action('forward_short') is None

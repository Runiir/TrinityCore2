import pytest
from .camera_steering import CameraSteering


def test_camera_waits_for_observed_yaw_and_learns_signed_mouse_sensitivity():
    camera=CameraSteering()
    pixels,_=camera.update(0,1000,.5,20,1)
    assert pixels==-8
    assert camera.update(0,1100,.5,20,1)[0]==0
    pixels,info=camera.update(.08,1200,.42,20,1)
    assert camera.samples[0]==pytest.approx(-.01)
    assert info['calibration_basis']=='observed yaw' and pixels<0


def test_one_delayed_opposite_sample_does_not_reverse_camera_direction():
    camera=CameraSteering()
    camera.update(0,1000,.5,20,1)
    camera.update(.08,1100,-.1,20,1)
    assert camera.pending is None
    pixels,_=camera.update(.08,1200,.02,20,1)
    assert pixels==0
    pixels,_=camera.update(.08,1300,-.15,20,1)
    assert pixels==0
    pixels,_=camera.update(.08,1400,-.15,20,1)
    assert pixels>0


def test_missing_mouse_yaw_fails_without_unbounded_pointer_motion():
    camera=CameraSteering();camera.update(0,1000,.5,20,1)
    with pytest.raises(RuntimeError,match='observed yaw'):
        camera.update(0,2100,.5,20,1)

import pytest
from .camera_steering import CameraSteering


def test_camera_waits_for_observed_yaw_and_learns_signed_mouse_sensitivity():
    camera=CameraSteering()
    pixels,_=camera.update(0,1000,.5,20,1)
    assert pixels==-8
    assert camera.update(0,1100,.5,20,1)[0]==0
    assert camera.update(.08,1200,.42,20,1)[0]==0
    pixels,info=camera.update(.08,1300,.42,20,1)
    assert camera.samples[0]==pytest.approx(-.01)
    assert info['calibration_basis']=='observed yaw' and pixels<0


def test_one_delayed_opposite_sample_does_not_reverse_camera_direction():
    camera=CameraSteering()
    camera.update(0,1000,.5,20,1)
    camera.update(.08,1100,-.1,20,1)
    camera.update(.08,1150,-.1,20,1)
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


def test_calibrated_camera_aims_at_the_bearing_in_one_relative_delta():
    camera=CameraSteering()
    camera.update(0,1000,2.5,100,1)
    assert camera.update(.031416,1100,2.468584,100,1)[0]==0
    pixels,info=camera.update(.031416,1150,2.468584,100,1)
    assert pixels < -600
    assert abs(pixels*info['radians_per_pixel']-2.468584)<.025
    assert camera.update(.031416,1200,2.468584,100,1)[0]==0


def test_partial_camera_feedback_cannot_calibrate_or_dispatch_the_next_delta():
    camera=CameraSteering();camera.update(0,1000,1,100,1)
    assert camera.update(.005,1100,.995,100,1)[0]==0
    assert camera.update(.08,1200,.92,100,1)[0]==0
    assert not camera.samples
    pixels,info=camera.update(.08,1300,.92,100,1)
    assert pixels<0 and info['radians_per_pixel']==pytest.approx(-.01)


def test_conflicting_pitch_rates_never_produce_a_zero_sensitivity():
    camera=CameraSteering(minimum_deadband=.01,maximum_deadband=.03)
    camera.samples.extend([.0117809847,-.0049185609,.0002718462,-.0001150487,
        .00006135914,-.00006135914])
    pixels,info=camera.update(-1.47,1000,1.47,1,.03)
    assert pixels<0 and info['radians_per_pixel']<0

import math
from . import escape_route
from .test_farm_loop import row


def test_recovery_offers_short_sides_without_treating_reference_geometry_as_live_truth(monkeypatch):
    r=row();r['movement']['facing_radians']=0;r['owned_pose']={'height_yards':100}
    calls=[]
    def clear(instance,start,end):calls.append((instance,start,end));return len(calls)%2==0
    monkeypatch.setattr(escape_route.model_collision,'clear_body_segment',clear)
    points=escape_route.candidates(r,{'instance':1,'north':100,'west':0})
    assert set(points)=={'step_left','step_right','step_back','step_forward'}
    assert points['step_left']['target']['west']==4
    assert points['step_right']['target']['west']==-4
    assert points['step_forward']['target']['north']==4
    for point in points.values():
        assert math.hypot(point['target']['north'],point['target']['west'])==4
        assert point['reference_matches_live_assets'] is False
    assert len(calls)==4

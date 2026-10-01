from tools.client_compatibility import landing_recovery as recovery
from tools.client_compatibility import site_boundaries
import math
import pytest


def test_alternative_landing_respects_concave_boundary_and_ground_connection(monkeypatch):
    site={'id':377,'map':530,'polygon':[[-10,-10],[10,-10],[10,10],[2,10],[2,2],[-10,2]]}
    monkeypatch.setattr(recovery.site_boundaries,'sites',lambda:{377:site})
    calls=[]
    def flat(map_id,point,radius,start):
        calls.append((map_id,start));return point
    monkeypatch.setattr(recovery.ground_navigation,'landing_point',flat)
    facts={'map':530,'position':[0,0,9,0]};origin=[-3,0,0]
    point,bounds=recovery.alternative(facts,{'digsite_ids':[377]},{'position':[0,0,0],'ground_connection_origin':origin})
    assert bounds==[site] and math.dist(point[:2],facts['position'][:2])>=4
    assert site_boundaries.inside_segment(site['polygon'],facts['position'],point)
    assert calls and all(c==(530,origin) for c in calls)
    monkeypatch.setattr(recovery.ground_navigation,'landing_point',lambda *a,**kw:[100,100,0])
    with pytest.raises(RuntimeError):recovery.alternative(facts,{'digsite_ids':[377]},{'position':[0,0,0]})

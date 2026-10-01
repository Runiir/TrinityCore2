import math
from tools.client_compatibility.site_boundaries import contains, inside_segment, clip_distance


def test_concave_corridor_cannot_leave_and_reenter_site():
    polygon = [[0,0],[10,0],[10,10],[7,10],[7,3],[3,3],[3,10],[0,10]]
    assert contains(polygon, [1,8]) and contains(polygon, [9,8])
    assert not inside_segment(polygon, [1,8], [9,8])
    assert clip_distance(polygon, [1,8], 0, 8) == 1
    assert inside_segment(polygon, [1,8], [2,8])


def test_clipped_walk_stops_before_edge_and_allows_inward_movement():
    polygon = [[0,0],[10,0],[10,10],[0,10]]
    assert clip_distance(polygon, [9.5,5], 0, 7) == 0
    assert clip_distance(polygon, [9.5,5], math.pi, 7) == 7
    assert inside_segment(polygon, [0,5], [4,5])
    assert not contains(polygon, [-.01,5])

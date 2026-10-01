"""Constrain local survey walks to an observed active public digsite polygon."""
from functools import lru_cache
import math
from .observation.map_data import catalog


def contains(polygon, point):
    x, y = point[:2]; inside = False
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        ax, ay = a; bx, by = b
        cross = (bx-ax)*(y-ay)-(by-ay)*(x-ax)
        if abs(cross) < 1e-7 and min(ax,bx) <= x <= max(ax,bx) and min(ay,by) <= y <= max(ay,by):
            return True
        if (ay > y) != (by > y) and x < ax+(y-ay)*(bx-ax)/(by-ay): inside = not inside
    return inside


def crossings(polygon, start, end):
    dx, dy = end[0]-start[0], end[1]-start[1]
    values = [0., 1.]
    for a, b in zip(polygon, polygon[1:]+polygon[:1]):
        ex, ey = b[0]-a[0], b[1]-a[1]
        den = dx*ey-dy*ex
        if abs(den) < 1e-10: continue
        ax, ay = a[0]-start[0], a[1]-start[1]
        t, u = (ax*ey-ay*ex)/den, (ax*dy-ay*dx)/den
        if 0 <= t <= 1 and 0 <= u <= 1: values.append(t)
    return sorted(set(values))


def inside_segment(polygon, start, end):
    if not contains(polygon, start) or not contains(polygon, end): return False
    cuts = crossings(polygon, start, end)
    for a, b in zip(cuts, cuts[1:]):
        t = (a+b)/2
        if not contains(polygon, [start[i]+t*(end[i]-start[i]) for i in range(2)]): return False
    return True


def clip_distance(polygon, start, heading, distance):
    """Stop before the first exit, including concave exits/reentries."""
    end = [start[0]+math.cos(heading)*distance, start[1]+math.sin(heading)*distance]
    cuts = crossings(polygon, start, end)
    for a, b in zip(cuts, cuts[1:]):
        t = (a+b)/2
        if not contains(polygon, [start[i]+t*(end[i]-start[i]) for i in range(2)]):
            return max(0., a*distance-1.)
    return distance


@lru_cache(maxsize=1)
def sites(): return catalog()['sites']


def active_site(map_id, start, observed_ids):
    matches = [s for sid, s in sites().items() if sid in observed_ids and s['map'] == map_id and contains(s['polygon'], start)]
    if len(matches) != 1: raise RuntimeError('survey walk is not inside one observed active digsite')
    return matches[0]

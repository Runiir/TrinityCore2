"""The floor a native fall lands on under the Nefarian orb ledge.

MotionMaster::MoveFall (and ProbeLedgeDrop's landing, the same query) takes
Map::GetHeight from 1.5 yd above the member with an unlimited search: the
highest of the static height and DynamicMapTree::getHeight. The dynamic query
asks each gameobject model for its FIRST hit (GameObjectModel::intersectRay
with stopAtFirstHit), and a bounding interval hierarchy returns the first
triangle hit in the first leaf it reaches, which need not be the nearest.

This module ports that query exactly (BoundingIntervalHierarchy.h
intersectRay, WorldModel::IntersectRay, GroupModel::IntersectRay,
IntersectTriangle) onto the platform's own collision model (GO 207834,
displayId 10363, data/vmaps/Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo)
at its raised stop frame, and pins what round 5 showed live
(blackwing_descent_10n_nefarian_c0): below the lip the first hit is the
ring top (8.5) south of the platform's axis and the model's underside
(-1.632, local z -8.666) north of it. The declared drop line lies on the axis
(+1.26e-4 yd local, past the flip at +3.4e-5): the nine members that fell
from the start point landed at 8.519; the hunter settled 0.32 yd north had
its first footprint-clear candidate rejected with
ledge_drop_landing_height_mismatch.
"""

from __future__ import annotations

import functools
import math
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
VMO = ROOT / "data/vmaps/Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo"
# Spawn 235179 at z -6.86794 plus the raised stop frame 0 offset 13.90172,
# rotated by pi: quaternion (0, 0, 1, 1.26759e-06).
ORIGIN = (-107.213, -224.62, -6.86794 + 13.90172)
QUAT_W = 1.26759e-06
Z_OFFSET_FIND_HEIGHT = 1.5
MAX_FALL_DISTANCE = 250000.0
LEDGE_Z = 41.104  # where the members stood (static ledge floor)
RING_TOP = 8.51
UNDERSIDE = -1.632


class _Bih:
    def __init__(self, lo, hi, tree, objects):
        self.lo, self.hi, self.tree, self.objects = lo, hi, tree, objects

    def intersect(self, org, direction, max_dist, callback, stop):
        imin, imax = -1.0, -1.0
        inv = [0.0, 0.0, 0.0]
        for i in range(3):
            inv[i] = math.copysign(math.inf, direction[i]) if direction[i] == 0.0 else 1.0 / direction[i]
            if abs(direction[i]) > 1e-5:  # G3D::fuzzyNe
                t1, t2 = (self.lo[i] - org[i]) * inv[i], (self.hi[i] - org[i]) * inv[i]
                if t1 > t2:
                    t1, t2 = t2, t1
                imin = max(imin, t1)
                if t2 < imax or imax < 0.0:
                    imax = t2
                if imax <= 0 or imin >= max_dist[0]:
                    return
        if imin > imax:
            return
        imin, imax = max(imin, 0.0), min(imax, max_dist[0])
        sign = [1 if math.copysign(1.0, d) < 0 else 0 for d in direction]
        front = [s + 1 for s in sign]
        back = [(s ^ 1) + 1 for s in sign]
        front3 = [s * 3 for s in sign]
        back3 = [(s ^ 1) * 3 for s in sign]
        plane = lambda bits: struct.unpack("<f", struct.pack("<I", bits))[0]
        tree, stack, node = self.tree, [], 0
        while True:
            while True:
                tn = tree[node]
                axis, bvh2, offset = (tn >> 30) & 3, (tn >> 29) & 1, tn & 0x1FFFFFFF
                if not bvh2 and axis < 3:
                    tf = (plane(tree[node + front[axis]]) - org[axis]) * inv[axis]
                    tb = (plane(tree[node + back[axis]]) - org[axis]) * inv[axis]
                    if tf < imin and tb > imax:
                        break
                    far = offset + back3[axis]
                    node = far
                    if tf < imin:
                        imin = tb if tb >= imin else imin
                        continue
                    node = offset + front3[axis]
                    if tb > imax:
                        imax = tf if tf <= imax else imax
                        continue
                    stack.append((far, tb if tb >= imin else imin, imax))
                    imax = tf if tf <= imax else imax
                    continue
                if not bvh2:  # leaf
                    for k in range(tree[node + 1]):
                        if callback(org, direction, self.objects[offset + k], max_dist) and stop:
                            return
                    break
                if axis > 2:
                    return
                tf = (plane(tree[node + front[axis]]) - org[axis]) * inv[axis]
                tb = (plane(tree[node + back[axis]]) - org[axis]) * inv[axis]
                node = offset
                imin = tf if tf >= imin else imin
                imax = tb if tb <= imax else imax
                if imin > imax:
                    break
            while True:
                if not stack:
                    return
                node, imin, imax = stack.pop()
                imax = min(imax, max_dist[0])
                if imin <= imax:
                    break


def _read_bih(data: bytes, offset: int):
    lo = struct.unpack("<3f", data[offset:offset + 12])
    hi = struct.unpack("<3f", data[offset + 12:offset + 24])
    (size,) = struct.unpack("<I", data[offset + 24:offset + 28])
    offset += 28
    tree = struct.unpack(f"<{size}I", data[offset:offset + 4 * size])
    offset += 4 * size
    (count,) = struct.unpack("<I", data[offset:offset + 4])
    offset += 4
    objects = struct.unpack(f"<{count}I", data[offset:offset + 4 * count])
    return _Bih(lo, hi, tree, objects), offset + 4 * count


@functools.lru_cache(maxsize=1)
def _model():
    if not VMO.exists():
        pytest.skip(f"{VMO.name} is not materialized locally")
    data = VMO.read_bytes()
    assert data[:8] == b"VMAP_4.8" and data[8:12] == b"WMOD" and data[20:24] == b"GMOD"
    (count,) = struct.unpack("<I", data[24:28])
    offset, groups = 28, []
    for _ in range(count):
        offset += 32  # group bound, mogp flags, group WMO id
        assert data[offset:offset + 4] == b"VERT"
        (vert_count,) = struct.unpack("<I", data[offset + 8:offset + 12])
        offset += 12
        if not vert_count:
            groups.append(None)
            continue
        verts = [struct.unpack("<3f", data[offset + 12 * i:offset + 12 * i + 12]) for i in range(vert_count)]
        offset += 12 * vert_count
        assert data[offset:offset + 4] == b"TRIM"
        (tri_count,) = struct.unpack("<I", data[offset + 8:offset + 12])
        offset += 12
        tris = [struct.unpack("<3I", data[offset + 12 * i:offset + 12 * i + 12]) for i in range(tri_count)]
        offset += 12 * tri_count
        assert data[offset:offset + 4] == b"MBIH"
        mesh, offset = _read_bih(data, offset + 4)
        assert data[offset:offset + 4] == b"LIQU"
        (liquid,) = struct.unpack("<I", data[offset + 4:offset + 8])
        offset += 8 + liquid
        groups.append((verts, tris, mesh))
    assert data[offset:offset + 4] == b"GBIH"
    group_tree, _ = _read_bih(data, offset + 4)
    return groups, group_tree


def _triangle(org, direction, a, b, c, max_dist) -> bool:
    sub = lambda u, v: (u[0] - v[0], u[1] - v[1], u[2] - v[2])
    cross = lambda u, v: (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    dot = lambda u, v: u[0] * v[0] + u[1] * v[1] + u[2] * v[2]
    e1, e2 = sub(b, a), sub(c, a)
    p = cross(direction, e2)
    det = dot(e1, p)
    if abs(det) < 1e-5:
        return False
    f, s = 1.0 / det, sub(org, a)
    u = f * dot(s, p)
    if u < 0.0 or u > 1.0:
        return False
    q = cross(s, e1)
    v = f * dot(direction, q)
    if v < 0.0 or u + v > 1.0:
        return False
    t = f * dot(e2, q)
    if 0.0 < t < max_dist[0]:
        max_dist[0] = t
        return True
    return False


def _model_ray(org, direction, max_dist, stop: bool) -> bool:
    groups, group_tree = _model()

    def group_ray(group, o, d, dist):
        verts, tris, mesh = group
        hit = [False]

        def on_triangle(o2, d2, entry, dist2):
            a, b, c = tris[entry]
            if _triangle(o2, d2, verts[a], verts[b], verts[c], dist2):
                hit[0] = True
            return hit[0]

        mesh.intersect(o, d, dist, on_triangle, stop)
        return hit[0]

    if len(groups) == 1:
        return group_ray(groups[0], org, direction, max_dist)
    hit = [False]

    def on_group(o, d, entry, dist):
        if groups[entry] is not None and group_ray(groups[entry], o, d, dist):
            hit[0] = True
        return hit[0]

    group_tree.intersect(org, direction, max_dist, on_group, stop)
    return hit[0]


def _local_y(x: float, y: float) -> float:
    # iInvRot * (world - origin) for the pi rotation (quaternion w epsilon).
    return -2.0 * QUAT_W * (x - ORIGIN[0]) - (y - ORIGIN[1])


def fall_landing(x: float, y: float, first_hit: bool = True) -> float | None:
    """Map::GetHeight's platform part as MoveFall asks it from the ledge."""
    top = LEDGE_Z + Z_OFFSET_FIND_HEIGHT
    org = (-(x - ORIGIN[0]) + 2.0 * QUAT_W * (y - ORIGIN[1]), _local_y(x, y), top - ORIGIN[2])
    # iInvRot * (0, 0, -1): +0 in x, -0 in y (the sign picks the BIH child order).
    max_dist = [MAX_FALL_DISTANCE]
    return top - max_dist[0] if _model_ray(org, (0.0, -0.0, -1.0), max_dist, first_hit) else None


def test_the_nine_fell_where_the_first_hit_is_the_ring_top() -> None:
    landing = fall_landing(-157.05, -224.62)
    assert landing is not None and abs(landing - RING_TOP) <= 0.05  # live: 8.51892
    assert abs(fall_landing(-157.05, -224.62, first_hit=False) - landing) < 1e-6


def test_north_of_the_axis_the_first_hit_is_the_platform_underside() -> None:
    # The hunter's first footprint-clear candidate (2.0 yd toward the step-off point).
    for x, y in ((-157.048, -224.541), (-156.800, -224.571), (-156.551, -224.601), (-157.05, -224.0)):
        assert abs(fall_landing(x, y) - UNDERSIDE) < 0.01, (x, y)
        # The nearest floor is the ring top all the same: only the first hit differs.
        assert abs(fall_landing(x, y, first_hit=False) - RING_TOP) <= 0.05, (x, y)
    # South of the axis, where the hunter's search now falls (2.75 yd out).
    for x, y in ((-156.303, -224.632), (-157.05, -225.0), (-156.4, -224.7)):
        assert abs(fall_landing(x, y) - RING_TOP) <= 0.05, (x, y)


def test_the_declared_line_sits_just_past_the_flip() -> None:
    # The first hit flips between local y +3.0e-5 and +4.0e-5 below the lip;
    # the declared line (world y -224.62) is at +1.26e-4.
    x = -157.05
    local_x = -(x - ORIGIN[0])
    below = (local_x, 3.0e-5, LEDGE_Z + Z_OFFSET_FIND_HEIGHT - ORIGIN[2])
    above = (local_x, 4.0e-5, below[2])
    for org, expected in ((below, UNDERSIDE), (above, RING_TOP)):
        dist = [MAX_FALL_DISTANCE]
        assert _model_ray(org, (0.0, -0.0, -1.0), dist, True)
        assert abs(below[2] + ORIGIN[2] - dist[0] - expected) <= 0.05
    assert 1.2e-4 < _local_y(x, -224.62) < 1.3e-4


# Round 3 (E1, round-2 live evidence): the mage, the warlock and the Disc
# priest stood on the pillar-1 rim at local (-15.8, -32.4), offset z 9.37, in
# all three runs and no step-off was ever committed. Pillar 1 lies wholly in
# the platform's north half (local y < 0), where the unlimited first-hit query
# MoveFall and ProbeLedgeDrop ask returns the model's underside, never the
# ring: ChooseStepOff ends every candidate with
# ledge_drop_landing_height_mismatch, and ExecuteFall would refuse too. The
# shared-runtime patch request (round 3 handoff) bounds both queries to the
# declared drop: Z_OFFSET_FIND_HEIGHT + (z - declared landing) + tolerance,
# the nearest floor a real fall lands on. A bounded first-hit query reaches
# the same leaf order but no triangle beyond the bound, so wherever the
# unlimited query already found the declared floor the bounded one returns
# it unchanged.
FOOTPRINT_RADIUS = 0.389
MIN_LEDGE_DROP = 4.0
SURFACE_TOLERANCE = 0.6
LANDING_TOLERANCE = 1.0
RING_LOCAL = 1.439
PILLARS = {1: (-20.47418, -34.21686), 2: (-20.44454, 34.39596)}


def _world(lx: float, ly: float, lz: float) -> tuple[float, float, float]:
    return (ORIGIN[0] - lx, ORIGIN[1] - ly, ORIGIN[2] + lz)


def _height(x: float, y: float, z: float, max_dist: float, first_hit: bool = True) -> float | None:
    """Map::GetHeight's platform part from world z (the caller adds any offset)."""
    org = (-(x - ORIGIN[0]) + 2.0 * QUAT_W * (y - ORIGIN[1]), _local_y(x, y), z - ORIGIN[2])
    dist = [max_dist]
    return z - dist[0] if _model_ray(org, (0.0, -0.0, -1.0), dist, first_hit) else None


def bounded_search_yards(z: float, declared: float, tolerance: float) -> float:
    """The patch's LedgeDropLandingSearchYards."""
    return Z_OFFSET_FIND_HEIGHT + max(0.0, z - declared) + tolerance


def _rim_candidates(pillar: int, lx: float, ly: float, lz: float):
    cx, cy = PILLARS[pillar]
    heading = math.atan2(ly - cy, lx - cx)
    for i in range(1, 17):  # SurfaceSampleStepYards 0.25 up to MaxStepOffYards 4
        step = 0.25 * i
        px, py = lx + math.cos(heading) * step, ly + math.sin(heading) * step
        x, y, z = _world(px, py, lz)
        # Past the lip: no floor within the surface tolerance under the step,
        # and the whole footprint clear of any floor within a walkable drop.
        supported = _height(x, y, z + SURFACE_TOLERANCE, 2 * SURFACE_TOLERANCE, False) is not None
        footprint = any(
            _height(x + (0 if k < 0 else FOOTPRINT_RADIUS * math.cos(k * math.pi / 4)),
                    y + (0 if k < 0 else FOOTPRINT_RADIUS * math.sin(k * math.pi / 4)),
                    z + SURFACE_TOLERANCE, SURFACE_TOLERANCE + MIN_LEDGE_DROP) is not None
            for k in range(-1, 8))
        yield step, (x, y, z), supported or footprint


def test_pillar_one_rim_every_step_off_lands_on_the_underside_unbounded() -> None:
    declared = ORIGIN[2] + RING_LOCAL
    past_lip = 0
    for _, (x, y, z), on_lip in _rim_candidates(1, -15.8, -32.4, 9.37):
        if on_lip:
            continue
        past_lip += 1
        landing = _height(x, y, z + Z_OFFSET_FIND_HEIGHT, MAX_FALL_DISTANCE)
        assert landing is not None and abs(landing - UNDERSIDE) < 0.01, (x, y, landing)
        assert abs(landing - declared) > LANDING_TOLERANCE  # ledge_drop_landing_height_mismatch
    assert past_lip >= 10


def test_pillar_one_rim_bounded_search_lands_on_the_ring() -> None:
    declared = ORIGIN[2] + RING_LOCAL
    admitted = []
    for step, (x, y, z), on_lip in _rim_candidates(1, -15.8, -32.4, 9.37):
        if on_lip:
            continue
        landing = _height(x, y, z + Z_OFFSET_FIND_HEIGHT,
                          bounded_search_yards(z, declared, LANDING_TOLERANCE))
        assert landing is not None and abs(landing - declared) <= LANDING_TOLERANCE, (step, landing)
        admitted.append(step)
    # The first footprint-clear candidate is within MaxStepOffYards, just past the wall.
    assert admitted and admitted[0] <= 1.5
    # The fall from there (ExecuteFall, the same bound from the step-off point) too.
    _, (x, y, z), _ = next(c for c in _rim_candidates(1, -15.8, -32.4, 9.37) if c[0] == admitted[0])
    fall = _height(x, y, z + Z_OFFSET_FIND_HEIGHT, bounded_search_yards(z, declared, LANDING_TOLERANCE))
    assert fall is not None and abs(fall - declared) <= LANDING_TOLERANCE
    assert z - fall < 14.57  # under the fall-damage threshold


def test_bounded_search_changes_nothing_where_the_first_hit_was_right() -> None:
    # Pillar 2 (south half), mirrored rim point: the unlimited first hit is
    # already the ring or skirt; the bounded query returns the same height.
    declared = ORIGIN[2] + RING_LOCAL
    compared = 0
    for _, (x, y, z), on_lip in _rim_candidates(2, -15.8, 32.4, 9.37):
        if on_lip:
            continue
        unbounded = _height(x, y, z + Z_OFFSET_FIND_HEIGHT, MAX_FALL_DISTANCE)
        bounded = _height(x, y, z + Z_OFFSET_FIND_HEIGHT,
                          bounded_search_yards(z, declared, LANDING_TOLERANCE))
        assert unbounded is not None and abs(unbounded - declared) <= LANDING_TOLERANCE
        assert bounded is not None and abs(bounded - unbounded) < 1e-4
        compared += 1
    assert compared >= 10
    # The orb-ledge drop of round 5 (south of the axis): unchanged as well.
    x, y = -157.05, -224.62
    top = LEDGE_Z + Z_OFFSET_FIND_HEIGHT
    bounded = _height(x, y, top, bounded_search_yards(LEDGE_Z, RING_TOP, LANDING_TOLERANCE))
    assert bounded is not None and abs(bounded - fall_landing(x, y)) < 1e-4


def _local_ray(org, direction, max_dist=200.0):
    norm = math.sqrt(sum(c * c for c in direction))
    direction = tuple(c / norm for c in direction)
    dist = [max_dist]
    return dist[0] if _model_ray(org, direction, dist, False) else None


def test_the_platform_is_a_closed_body_with_hollow_pillar_shafts() -> None:
    """Round 3 (E2): why no lawful step leaves a pillar shaft (BotNefarianPlatformBody.h)."""
    body = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/"
            "BotNefarianPlatformBody.h").read_text()
    underside = float(body.split("PlatformUndersideLocalZ = ")[1].split("f;")[0])
    body_radius = float(body.split("PlatformBodyRadius = ")[1].split("f;")[0])
    shaft_radius = float(body.split("PillarShaftRadius = ")[1].split("f;")[0])
    assert abs(underside - (UNDERSIDE - ORIGIN[2])) < 0.01
    for pillar, (cx, cy) in PILLARS.items():
        for dx, dy, lz in ((0.9, 0.6, 3.4), (-1.2, 0.4, 3.9), (0.0, 0.0, 3.0)):
            org = (cx + dx, cy + dy, lz)
            down = _local_ray(org, (0.0, -0.0, -1.0))
            up = _local_ray(org, (0.0, 0.0, 1.0))
            # Nothing under the shaft until the bottom; the top closes it above.
            assert down is not None and abs(lz - down - underside) < 0.01, (pillar, org)
            assert up is not None and abs(lz + up - 9.925) < 0.01, (pillar, org)
            # The wall closes it on every heading at the recorded heights.
            for heading in range(0, 360, 30):
                h = math.radians(heading)
                wall = _local_ray(org, (math.cos(h), math.sin(h), 0.0), 20.0)
                assert wall is not None and wall < 7.0, (pillar, org, heading)
    # The shaft radius the plan uses is inside the wall on every heading from
    # the skirt to the rim.
    for pillar, (cx, cy) in {0: (40.50549, -0.06254366), **PILLARS}.items():
        for lz in (2.4, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0):
            for heading in range(0, 360, 5):
                h = math.radians(heading)
                wall = _local_ray((cx, cy, lz), (math.cos(h), math.sin(h), 0.0), 20.0)
                assert wall is not None and wall > shaft_radius + 0.1, (pillar, lz, heading, wall)
    # Under the walk surface the outer wall closes the body on every heading.
    for lz in (-2.0, -5.0, -8.0):
        for heading in range(0, 360, 15):
            h = math.radians(heading)
            wall = _local_ray((0.0, 0.0, lz), (math.cos(h), math.sin(h), 0.0))
            assert wall is not None and body_radius < wall < 71.5, (lz, heading, wall)

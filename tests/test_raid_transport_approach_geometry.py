"""The proposed transport approach rows checked against the client geometry.

The lower-wing elevator's board point lies on the platform's own model past
the end of the static corridor floor; the Nefarian platform lies 33 yd below
the orb ledge. The approach rows (patch requests to the scenario config) must
describe what a player could really do there:

- every approach start stands on the static navmesh and on static ground;
- the elevator walk from its start to the board point has a floor (the static
  corridor or the platform's top at its top rest) under every sample, within
  the floor tolerance of the straight segment's own height;
- the Nefarian step-off point is past the static lip with its whole footprint
  over the void, nothing blocks the level step, and the floor straight below
  is the raised platform's own surface at the declared landing height.

Sources: data/mmaps (Detour tiles), data/vmaps (static WMO spawns and the
platform models), TransportAnimation.dbc offsets pinned in
tests/test_raid_transport_board_points.py.
"""

from __future__ import annotations

import functools
import math
import struct
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
MMAPS = ROOT / "data/mmaps"
VMAPS = ROOT / "data/vmaps"
MAP_ID = 669
MID = 0.5 * 64.0 * 533.33333333

# Proposed rows (identical to the patch request for validation_scenarios_cata_001.json).
ELEVATOR = {
    "origin": (-241.349, -224.605, 186.551), "orientation": 0.0,
    "model": "Blackwingv2_Elevator01.wmo.vmo",
    "start": (-251.0, -224.605, 190.163), "board": (-247.349, -224.605, 190.028),
    # Bottom rest: origin 186.551 - 112.6704; the car's own top at its centre.
    "bottom_origin_z": 73.8806, "disembark": (-241.349, -224.605, 77.087),
}
NEFARIAN = {
    # Stationary spawn z -6.86794 plus the stop frame 0 offset 13.90172.
    "origin": (-107.213, -224.62, -6.86794 + 13.90172), "orientation": 3.14159,
    "model": "Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo",
    "start": (-158.8, -224.62, 41.3544), "step_off": (-156.4, -224.62, 41.3544),
    "landing_z": 8.51,
}
FLOOR_TOLERANCE = 0.5
MIN_LEDGE_DROP = 4.0
PLAYER_RADIUS = 0.389


def _require(path: Path) -> Path:
    if not path.exists():
        pytest.skip(f"{path.name} is not materialized locally")
    return path


def _navmesh_polys() -> list[list[tuple[float, float, float]]]:
    polys = []
    for tile in sorted(_require(MMAPS).glob(f"{MAP_ID}*.mmtile")):
        data = tile.read_bytes()[20:]
        header = struct.unpack("<5iI9i3f3f3f f", data[:100])
        poly_count, vert_count = header[6], header[7]
        offset = 100
        raw = struct.unpack(f"<{vert_count * 3}f", data[offset:offset + vert_count * 12])
        offset += vert_count * 12
        # Detour stores (y, z, x) of the world position.
        verts = [(raw[3 * i + 2], raw[3 * i], raw[3 * i + 1]) for i in range(vert_count)]
        for _ in range(poly_count):
            poly = struct.unpack("<I6H6HHBB", data[offset:offset + 32])
            offset += 32
            polys.append([verts[poly[1 + k]] for k in range(poly[14])])
    return polys


def _navmesh_heights(polys, x: float, y: float) -> list[float]:
    heights = []
    for poly in polys:
        inside = False
        for (x1, y1, _), (x2, y2, _) in zip(poly, poly[1:] + poly[:1]):
            if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
                inside = not inside
        if inside:
            heights.append(sum(point[2] for point in poly) / len(poly))
    return heights


@functools.lru_cache(maxsize=None)
def _vmo_triangles(path: Path):
    data = _require(path).read_bytes()
    assert data[:8] == b"VMAP_4.8" and data[8:12] == b"WMOD"
    offset = 20
    triangles = []
    if data[offset:offset + 4] != b"GMOD":
        return triangles
    (count,) = struct.unpack("<I", data[offset + 4:offset + 8])
    offset += 8
    for _ in range(count):
        offset += 32
        assert data[offset:offset + 4] == b"VERT"
        (vert_count,) = struct.unpack("<I", data[offset + 8:offset + 12])
        offset += 12
        if not vert_count:
            continue
        verts = [struct.unpack("<3f", data[offset + 12 * i:offset + 12 * i + 12]) for i in range(vert_count)]
        offset += 12 * vert_count
        (tri_count,) = struct.unpack("<I", data[offset + 8:offset + 12])
        offset += 12
        for i in range(tri_count):
            a, b, c = struct.unpack("<3I", data[offset + 12 * i:offset + 12 * i + 12])
            triangles.append((verts[a], verts[b], verts[c]))
        offset += 12 * tri_count
        assert data[offset:offset + 4] == b"MBIH"
        offset += 4 + 24
        (tree,) = struct.unpack("<I", data[offset:offset + 4])
        offset += 4 + 4 * tree
        (objects,) = struct.unpack("<I", data[offset:offset + 4])
        offset += 4 + 4 * objects
        assert data[offset:offset + 4] == b"LIQU"
        (liquid,) = struct.unpack("<I", data[offset + 4:offset + 8])
        offset += 8 + liquid
    return triangles


def _heights(triangles, x: float, y: float) -> list[float]:
    heights = []
    for a, b, c in triangles:
        den = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(den) < 1e-9:
            continue
        l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / den
        l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / den
        l3 = 1.0 - l1 - l2
        if min(l1, l2, l3) >= -1e-6:
            heights.append(l1 * a[2] + l2 * b[2] + l3 * c[2])
    return heights


@functools.lru_cache(maxsize=None)
def _static_spawns():
    """(name, rotation matrix, position, scale) of every static map spawn."""
    seen, spawns = set(), []
    for tile in sorted(_require(VMAPS).glob(f"{MAP_ID:03d}_*.vmtile")):
        data = tile.read_bytes()
        (count,) = struct.unpack("<I", data[8:12])
        offset = 12
        for _ in range(count):
            flags, _, spawn_id = struct.unpack("<BBI", data[offset:offset + 6])
            offset += 6
            pos = struct.unpack("<3f", data[offset:offset + 12])
            rot = struct.unpack("<3f", data[offset + 12:offset + 24])
            (scale,) = struct.unpack("<f", data[offset + 24:offset + 28])
            offset += 28 + (24 if flags & 2 else 0)
            (name_length,) = struct.unpack("<I", data[offset:offset + 4])
            name = data[offset + 4:offset + 4 + name_length].split(b"\0")[0].decode()
            offset += 4 + name_length
            if spawn_id in seen:
                continue
            seen.add(spawn_id)
            # ModelInstance: fromEulerAnglesZYX(rot.y, rot.x, rot.z) = Rz*Ry*Rx.
            rz, ry, rx = (math.radians(rot[1]), math.radians(rot[0]), math.radians(rot[2]))
            cz, sz, cy, sy, cx, sx = (math.cos(rz), math.sin(rz), math.cos(ry), math.sin(ry),
                                      math.cos(rx), math.sin(rx))
            matrix = ((cz * cy, cz * sy * sx - sz * cx, cz * sy * cx + sz * sx),
                      (sz * cy, sz * sy * sx + cz * cx, sz * sy * cx - cz * sx),
                      (-sy, cy * sx, cy * cx))
            spawns.append((name, matrix, pos, scale))
    return tuple(spawns)


def _static_triangles(box: tuple[float, float, float, float]):
    """World-space triangles of the map's static spawns (WMOs and collidable
    doodads; doodads without collision have no extracted model) inside box."""
    xmin, xmax, ymin, ymax = box
    triangles = []
    for name, matrix, pos, scale in _static_spawns():
        path = VMAPS / (name + ".vmo")
        if not path.exists():
            continue

        def world(v, matrix=matrix, pos=pos, scale=scale):
            p = [scale * c for c in v]
            q = [sum(matrix[r][k] * p[k] for k in range(3)) + pos[r] for r in range(3)]
            return (MID - q[0], MID - q[1], q[2])

        for a, b, c in _vmo_triangles(path):
            corners = (world(a), world(b), world(c))
            if max(p[0] for p in corners) < xmin or min(p[0] for p in corners) > xmax \
                    or max(p[1] for p in corners) < ymin or min(p[1] for p in corners) > ymax:
                continue
            triangles.append(corners)
    return triangles


def _local(row: dict, x: float, y: float) -> tuple[float, float]:
    ox, oy, _ = row["origin"]
    c, s = math.cos(row["orientation"]), math.sin(row["orientation"])
    return (x - ox) * c + (y - oy) * s, (y - oy) * c - (x - ox) * s


def _platform_top(row: dict, triangles, x: float, y: float) -> float | None:
    lx, ly = _local(row, x, y)
    tops = [z for z in _heights(triangles, lx, ly) if z > -8.0]
    return row["origin"][2] + max(tops) if tops else None


def test_approach_starts_stand_on_the_static_navmesh_and_ground() -> None:
    polys = _navmesh_polys()
    statics = _static_triangles((-260.0, -150.0, -230.0, -219.0))
    for row, end in ((ELEVATOR, "board"), (NEFARIAN, "step_off")):
        x, y, z = row["start"]
        assert any(abs(h - z) <= 0.6 for h in _navmesh_heights(polys, x, y)), row["start"]
        assert any(z - FLOOR_TOLERANCE <= h <= z + 0.1 for h in _heights(statics, x, y)), row["start"]
        # The approach ends where the static navmesh does not reach.
        ex, ey, ez = row[end]
        assert not any(abs(h - ez) <= 3.0 for h in _navmesh_heights(polys, ex, ey)), row[end]


def test_elevator_surface_walk_has_a_floor_under_every_sample_at_the_top_rest() -> None:
    model = _vmo_triangles(VMAPS / ELEVATOR["model"])
    statics = _static_triangles((-256.0, -244.0, -227.0, -222.0))
    (sx, sy, sz), (bx, by, bz) = ELEVATOR["start"], ELEVATOR["board"]
    length = math.hypot(bx - sx, by - sy)
    steps = math.ceil(length / 0.25)
    kinds = []
    for i in range(steps + 1):
        t = i / steps
        x, y, z = sx + (bx - sx) * t, sy + (by - sy) * t, sz + (bz - sz) * t
        static = any(abs(h - z) <= FLOOR_TOLERANCE for h in _heights(statics, x, y))
        top = _platform_top(ELEVATOR, model, x, y)
        platform = top is not None and abs(top - z) <= FLOOR_TOLERANCE
        assert static or platform, (x, z)
        kinds.append((static, platform))
    # Static corridor at the start, the platform's own surface alone at the end.
    assert kinds[0][0] and kinds[-1] == (False, True)
    assert length + 1.0 <= 12.0


def test_elevator_bottom_disembark_needs_the_surface_walk_to_the_car_centre() -> None:
    model = _vmo_triangles(VMAPS / ELEVATOR["model"])
    statics = _static_triangles((-256.0, -236.0, -227.0, -222.0))
    bottom = dict(ELEVATOR, origin=(ELEVATOR["origin"][0], ELEVATOR["origin"][1],
                                    ELEVATOR["bottom_origin_z"]))
    bx, by, _ = ELEVATOR["board"]
    dx, dy, dz = ELEVATOR["disembark"]
    # Where riders board (local x -6) the car's top is more than the floor
    # tolerance above the pit floor: leaving there is not proven.
    ride_z = _platform_top(bottom, model, bx, by)
    assert ride_z - max(h for h in _heights(statics, bx, by) if h < ride_z) > FLOOR_TOLERANCE
    # At the declared disembark point (the car's own top at its centre) the
    # static floor is within tolerance, so the leave report is proven there.
    assert abs(_platform_top(bottom, model, dx, dy) - dz) <= 0.01
    assert dz - max(h for h in _heights(statics, dx, dy) if h < dz) <= FLOOR_TOLERANCE
    # The passenger's straight walk between them stays on the car's surface.
    steps = math.ceil(math.hypot(dx - bx, dy - by) / 0.25)
    for i in range(steps + 1):
        t = i / steps
        x, y, z = bx + (dx - bx) * t, by + (dy - by) * t, ride_z + (dz - ride_z) * t
        top = _platform_top(bottom, model, x, y)
        assert top is not None and abs(top - z) <= FLOOR_TOLERANCE, (x, z, top)


def test_nefarian_step_off_clears_the_lip_and_lands_on_the_raised_platform() -> None:
    model = _vmo_triangles(VMAPS / NEFARIAN["model"])
    statics = _static_triangles((-162.0, -152.0, -228.0, -221.0))
    (sx, sy, sz), (tx, ty, tz) = NEFARIAN["start"], NEFARIAN["step_off"]
    assert tz == sz and 0.0 < math.hypot(tx - sx, ty - sy) + 1.0 <= 4.0
    # Level step: static ledge floor first, then the void, never floor again.
    profile = []
    for i in range(11):
        x = sx + (tx - sx) * i / 10
        profile.append(any(abs(h - sz) <= FLOOR_TOLERANCE for h in _heights(statics, x, sy)))
    assert profile[0] and not profile[-1]
    assert profile == sorted(profile, reverse=True)
    # Nothing to climb over along the step (no railing or brazier).
    for a, b, c in statics:
        for p in (a, b, c):
            if min(sx, tx) <= p[0] <= max(sx, tx) and abs(p[1] - sy) <= 1.0:
                assert not (sz + 0.3 < p[2] < sz + 2.2), p
    # The whole footprint where the fall starts is over the void.
    for i in range(-1, 8):
        x = tx + (0.0 if i < 0 else PLAYER_RADIUS * math.cos(i * math.pi / 4))
        y = ty + (0.0 if i < 0 else PLAYER_RADIUS * math.sin(i * math.pi / 4))
        assert not any(tz - MIN_LEDGE_DROP < h <= tz + FLOOR_TOLERANCE for h in _heights(statics, x, y)), (x, y)
        top = _platform_top(NEFARIAN, model, x, y)
        assert top is not None and abs(top - NEFARIAN["landing_z"]) <= 0.1, (x, y, top)
    # Straight below: the raised platform's surface, above any static floor
    # (the lava bed lies ~28 yd lower), at the declared landing height.
    landing = _platform_top(NEFARIAN, model, tx, ty)
    assert abs(landing - NEFARIAN["landing_z"]) <= 0.05
    assert all(h < landing - 1.0 for h in _heights(statics, tx, ty))
    # Native fall damage (Player::HandleFall) leaves the declared margin.
    damage = 0.018 * (sz - landing) - 0.2426
    assert 0.34 < damage < 0.36 and 1.0 - damage >= 0.2 + 0.4

    # The executor's own choice from the approach start: the first point
    # along the heading whose footprint has left the lip, within 4 yd.
    heading = ((tx - sx) / math.hypot(tx - sx, ty - sy), (ty - sy) / math.hypot(tx - sx, ty - sy))

    def footprint_clear(x: float, y: float) -> bool:
        for i in range(-1, 8):
            px = x + (0.0 if i < 0 else PLAYER_RADIUS * math.cos(i * math.pi / 4))
            py = y + (0.0 if i < 0 else PLAYER_RADIUS * math.sin(i * math.pi / 4))
            if any(sz - MIN_LEDGE_DROP < h <= sz + FLOOR_TOLERANCE for h in _heights(statics, px, py)):
                return False
        return True

    first = next(0.25 * k for k in range(1, 17)
                 if footprint_clear(sx + heading[0] * 0.25 * k, sy + heading[1] * 0.25 * k))
    assert first <= 4.0
    fx, fy = sx + heading[0] * first, sy + heading[1] * first
    assert abs(_platform_top(NEFARIAN, model, fx, fy) - NEFARIAN["landing_z"]) <= 0.1

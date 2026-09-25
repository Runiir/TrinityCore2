"""The Nefarian platform floor, sampled from its collision model.

GO 207834 (displayId 10363) collides with
data/vmaps/Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo. Its floor is
committed as a radial profile (every 5 degrees, every 0.5 yards) in
experiments/configs/cata_raid_encounters/blackwing_descent/
nefarian_platform_floor_profile_v1.json, with the model's sha256.

This module
- re-derives part of the profile from the .vmo when the local data directory
  has it (data/ is not in git), so the committed samples stay sourced;
- checks the strategy's floor constants (BotNefarianGeometry.h) against the
  samples;
- provides ``probe_leg``, an emulation of package T's surface-walk checks
  (ProbeSegment + ValidateSurfaceWalk + the body sweep) against the samples,
  which tests/test_nefarian_movement.py applies to every emitted leg.

The pillar blocks are judged by ``pillar_footprints`` (per pillar and heading,
the extent of the block and its skirt, sampled every 0.05 yd), not by the
radial grid, which is 3.5 yd wide at the pillars' radius.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import struct
from functools import lru_cache
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
PROFILE = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_platform_floor_profile_v1.json"
GEOMETRY = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianGeometry.h"
VMO = ROOT / "data/vmaps/Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo"

# BotValidationRouteNativeApproach.h
SAMPLE_STEP = 0.25
MAX_WALK = 12.0
MAX_UNSUPPORTED_SPAN = 0.389
BODY_RADIUS = 0.389
PILLAR_INTERIOR = -5.0  # the ray from local z 4 inside a block finds its underside (-8.666)
PILLAR_SKIRT = 1.6  # the skirt around a block rises to local z 2.2; the ring is 1.439


@lru_cache(maxsize=1)
def profile() -> dict:
    return json.loads(PROFILE.read_text(encoding="utf-8"))


def _cell_value(heading_index: int, radius_index: int) -> float | None:
    data = profile()
    headings = data["headings_deg"]
    row = data["floor_local_z"][heading_index % len(headings)]
    return row[radius_index]


@lru_cache(maxsize=1)
def _footprints() -> tuple:
    footprints = profile()["pillar_footprints"]
    step = footprints["headings_deg"][1] - footprints["headings_deg"][0]
    margin = footprints["interpolation_margin"]
    return tuple((cx, cy, max(radii) + margin, tuple(radii), step, margin)
                 for (cx, cy), radii in zip(footprints["centres"], footprints["blocked_radius"]))


def _in_footprint(x: float, y: float) -> bool:
    """Inside a pillar block or its skirt (pillar_footprints, derived from the
    model at 0.05 yd; conservative between the 5-degree headings)."""
    for cx, cy, reach, radii, step, margin in _footprints():
        dx, dy = x - cx, y - cy
        if dx * dx + dy * dy > reach * reach:
            continue
        heading = math.degrees(math.atan2(dy, dx)) % 360.0
        low = int(heading // step) % len(radii)
        if math.hypot(dx, dy) < max(radii[low], radii[(low + 1) % len(radii)]) + margin:
            return True
    return False


def _pillar_cell(value: float | None) -> bool:
    return value is not None and (value < PILLAR_INTERIOR or value > PILLAR_SKIRT)


def floor_at(x: float, y: float) -> float | None:
    """Model floor at a local point; None inside a pillar footprint, off the
    model, or across a discontinuity. Outside the footprints, profile cells
    that belong to a pillar (its block or skirt) are left out of the
    interpolation: the radial grid is 3.5 yd wide at r 40, far coarser than
    the pillar edge."""
    if _in_footprint(x, y):
        return None
    data = profile()
    step_h = data["headings_deg"][1] - data["headings_deg"][0]
    step_r = data["radii"][1] - data["radii"][0]
    radius = math.hypot(x, y)
    if radius > data["radii"][-1]:
        return None
    heading = math.degrees(math.atan2(y, x)) % 360.0
    hi = int(heading // step_h)
    ri = min(int(radius // step_r), len(data["radii"]) - 2)
    th = (heading - hi * step_h) / step_h
    tr = (radius - ri * step_r) / step_r
    corners = [(_cell_value(hi, ri), (1 - th) * (1 - tr)), (_cell_value(hi + 1, ri), th * (1 - tr)),
               (_cell_value(hi, ri + 1), (1 - th) * tr), (_cell_value(hi + 1, ri + 1), th * tr)]
    if any(value is None for value, _ in corners):
        return None
    usable = [(value, weight) for value, weight in corners if not _pillar_cell(value)]
    total = sum(weight for _, weight in usable)
    if not usable or total <= 1e-6:
        return None
    values = [value for value, _ in usable]
    if max(values) - min(values) > 0.5:
        return None
    return sum(value * weight for value, weight in usable) / total


def _blocked(x: float, y: float) -> bool:
    return _in_footprint(x, y)


def probe_leg(start: tuple[float, float, float], end: tuple[float, float, float],
              tolerance: float) -> str:
    """Package T's verdict for one Walk leg, against the sampled model:
    'surface_walk_verified' or the first refusal reason."""
    length = math.hypot(end[0] - start[0], end[1] - start[1])
    if not length > 0.0 or length > MAX_WALK:
        return "surface_walk_length_invalid"
    steps = max(1, math.ceil(length / SAMPLE_STEP))
    side_x = -(end[1] - start[1]) / length * BODY_RADIUS
    side_y = (end[0] - start[0]) / length * BODY_RADIUS
    supported = []
    for i in range(steps + 1):
        t = i / steps
        x = start[0] + (end[0] - start[0]) * t
        y = start[1] + (end[1] - start[1]) * t
        z = start[2] + (end[2] - start[2]) * t
        for side in (1.0, -1.0):
            if _blocked(x + side * side_x, y + side * side_y) or _blocked(x, y):
                return "surface_walk_blocked"
        floor = floor_at(x, y)
        supported.append(floor is not None and abs(floor - z) <= tolerance)
    if not supported[0]:
        return "surface_walk_start_unsupported"
    if not supported[-1]:
        return "surface_walk_end_unsupported"
    spacing = length / steps
    last = 0.0
    for i, ok in enumerate(supported):
        if not ok:
            continue
        along = i * spacing
        if along - last - spacing > MAX_UNSUPPORTED_SPAN + 1e-4:
            return "surface_walk_unsupported_span"
        last = along
    return "surface_walk_verified"


def _header_constant(name: str) -> float:
    text = GEOMETRY.read_text(encoding="utf-8")
    match = re.search(rf"constexpr float {name} = (-?[0-9.]+)f;", text)
    assert match, name
    return float(match.group(1))


def _read_vmo_triangles(path: Path) -> list[tuple]:
    raw = path.read_bytes()
    pos = 0

    def take(fmt):
        nonlocal pos
        values = struct.unpack_from(fmt, raw, pos)
        pos += struct.calcsize(fmt)
        return values

    def chunk(tag: bytes):
        nonlocal pos
        assert raw[pos:pos + len(tag)] == tag, (tag, pos)
        pos += len(tag)

    chunk(b"VMAP_4.8")
    chunk(b"WMOD")
    take("<2I")
    chunk(b"GMOD")
    (groups,) = take("<I")
    triangles = []
    for _ in range(groups):
        take("<6f2I")
        chunk(b"VERT")
        take("<I")
        (count,) = take("<I")
        if not count:
            continue
        verts = [take("<3f") for _ in range(count)]
        chunk(b"TRIM")
        take("<I")
        (tcount,) = take("<I")
        for _ in range(tcount):
            a, b, c = take("<3I")
            triangles.append((verts[a], verts[b], verts[c]))
        chunk(b"MBIH")
        take("<6f")
        (tree,) = take("<I")
        pos += 4 * tree
        (objects,) = take("<I")
        pos += 4 * objects
        chunk(b"LIQU")
        (liquid,) = take("<I")
        pos += liquid
    return triangles


def _ray_down(triangles, x, y, top):
    best = None
    for a, b, c in triangles:
        d = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if abs(d) < 1e-9:
            continue
        l1 = ((b[1] - c[1]) * (x - c[0]) + (c[0] - b[0]) * (y - c[1])) / d
        l2 = ((c[1] - a[1]) * (x - c[0]) + (a[0] - c[0]) * (y - c[1])) / d
        l3 = 1.0 - l1 - l2
        if min(l1, l2, l3) < -1e-6:
            continue
        z = l1 * a[2] + l2 * b[2] + l3 * c[2]
        if z <= top + 1e-6 and (best is None or z > best):
            best = z
    return best


def test_profile_is_sourced_from_the_platform_model() -> None:
    data = profile()
    assert data["schema"] == "nefarian_platform_floor_profile_v1"
    assert data["source"]["triangles"] == 992
    assert len(data["headings_deg"]) == 72 and len(data["radii"]) == 121
    if not VMO.is_file():
        pytest.skip("data/vmaps is local-only; the committed samples carry the model's sha256")
    assert hashlib.sha256(VMO.read_bytes()).hexdigest() == data["source"]["sha256"]
    triangles = _read_vmo_triangles(VMO)
    assert len(triangles) == data["source"]["triangles"]
    for heading_index in (0, 3, 24, 50):
        heading = data["headings_deg"][heading_index]
        for radius_index in range(0, len(data["radii"]), 4):
            radius = data["radii"][radius_index]
            x = math.cos(math.radians(heading)) * radius
            y = math.sin(math.radians(heading)) * radius
            z = _ray_down(triangles, x, y, data["probe_top_local_z"])
            expected = data["floor_local_z"][heading_index][radius_index]
            assert (z is None) == (expected is None)
            if z is not None:
                assert abs(round(z, 3) - expected) <= 0.001, (heading, radius)
    for heading in (0.0, 120.7, 239.1):
        x = math.cos(math.radians(heading)) * 40.5
        y = math.sin(math.radians(heading)) * 40.5
        assert abs(_ray_down(triangles, x, y, 20.0) - data["pillar_top_local_z"]) < 0.01


def test_strategy_floor_model_matches_the_samples() -> None:
    data = profile()
    flat = _header_constant("FloorFlatLocalZ")
    start = _header_constant("RampStartRadius")
    slope = _header_constant("RampSlope")
    ring = _header_constant("RingLocalZ")
    end = start + (ring - flat) / slope

    def model(radius: float) -> float:
        if radius <= start:
            return flat
        if radius >= end:
            return ring
        return flat + (radius - start) * slope

    pillars = [(40.50549, -0.06254366), (-20.47418, -34.21686), (-20.44454, 34.39596)]
    worst = 0.0
    for heading, row in zip(data["headings_deg"], data["floor_local_z"]):
        for radius, z in zip(data["radii"], row):
            x = math.cos(math.radians(heading)) * radius
            y = math.sin(math.radians(heading)) * radius
            if z is None or min(math.hypot(x - px, y - py) for px, py in pillars) < 7.5:
                continue
            worst = max(worst, abs(z - model(radius)))
    assert worst <= 0.25, worst
    # The old route anchor (local 25, 0 at z -0.46235) is 0.54 below the floor.
    assert abs(floor_at(25.0, 0.0) - 0.074) < 0.01
    assert floor_at(25.0, 0.0) - (-0.46235) > 0.5


def test_probe_recognises_lawful_and_refused_legs() -> None:
    lawful = probe_leg((0.0, 0.0, -0.546), (9.0, 0.0, -0.546), 0.6)
    assert lawful == "surface_walk_verified"
    # A level leg from the flat centre up the ramp ends under the floor.
    assert probe_leg((17.0, 0.0, -0.546), (26.5, 0.0, -0.546), 0.6) == "surface_walk_end_unsupported"
    # The same leg ending at the model floor height passes.
    assert probe_leg((17.0, 5.0, -0.546), (26.0, 5.0, 0.36), 0.6) == "surface_walk_verified"
    # Through pillar 0.
    assert probe_leg((32.0, 0.0, 1.35), (49.0, 0.0, 1.439), 0.6) != "surface_walk_verified"


def test_pillar_footprints_cover_every_obstacle_sample() -> None:
    data = profile()
    footprints = data["pillar_footprints"]
    assert len(footprints["centres"]) == 3
    assert all(len(row) == len(footprints["headings_deg"]) == 72
               for row in footprints["blocked_radius"])
    # Every sample of the radial profile that is not plain floor (a block
    # interior, a skirt above the ring band, or no surface inside the rim)
    # lies inside a footprint: the platform has no other obstacle.
    low, high = footprints["ring_band"]
    for heading, row in zip(data["headings_deg"], data["floor_local_z"]):
        for radius, z in zip(data["radii"], row):
            if radius > 57.5:
                continue
            x = math.cos(math.radians(heading)) * radius
            y = math.sin(math.radians(heading)) * radius
            obstacle = z is None or z < PILLAR_INTERIOR or z > high
            if obstacle:
                assert _in_footprint(x, y), (heading, radius, z)
    # Pillars stand wholly on the ring, clear of the ramp.
    for (cx, cy), radii in zip(footprints["centres"], footprints["blocked_radius"]):
        assert math.hypot(cx, cy) - max(radii) > _header_constant("RampStartRadius") + (
            _header_constant("RingLocalZ") - _header_constant("FloorFlatLocalZ")) / _header_constant("RampSlope")
    # The strategy's path clearance keeps the body sweep outside every footprint.
    widest = max(max(radii) for radii in footprints["blocked_radius"]) + footprints["interpolation_margin"]
    path_clearance = float(re.search(r"constexpr float PillarPathClearance = ([0-9.]+)f;",
                                     GEOMETRY.read_text(encoding="utf-8")).group(1))
    assert path_clearance - BODY_RADIUS > widest, (path_clearance, widest)
    if not VMO.is_file():
        pytest.skip("data/vmaps is local-only; the committed footprints carry the model's sha256")
    triangles = _read_vmo_triangles(VMO)
    step = footprints["radial_step"]
    for pillar, heading_index in ((0, 0), (0, 36), (1, 12), (2, 60)):
        cx, cy = footprints["centres"][pillar]
        heading = math.radians(footprints["headings_deg"][heading_index])
        last = 0.0
        for i in range(int(9.0 / step) + 1):
            distance = i * step
            z = _ray_down(triangles, cx + math.cos(heading) * distance,
                          cy + math.sin(heading) * distance, data["probe_top_local_z"])
            if z is None or not low <= z <= high:
                last = distance
        assert abs(round(last + step, 2) - footprints["blocked_radius"][pillar][heading_index]) < 1e-6

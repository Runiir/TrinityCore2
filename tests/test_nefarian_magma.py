"""The phase 2 magma, the lowering timeline and the swim-then-hop pillar ascent.

User raid experience 2026-09-26: the raid swims up in the rising magma beside
its pillars and hops onto the pillar tops once they are level with the
surface. This module checks that against native data:
- the magma surface comes from the arena WMO's liquid (Blackwingv2.wmo.vmo,
  re-derived here when data/vmaps is present) and is flat at world z 2.7713;
- the pillar tops stop 0.286 above it and never go under; the floor goes under
  on the timeline TransportAnimation.dbc gives;
- the per-slot pillar profile in BotNefarianMagma.h matches the samples of the
  platform model committed in nefarian_magma_v1.json and bounds them from above;
- every slot's hop (BotNefarianMagma.h PlanHop) is the client's jump: its rise
  is under the jump apex, its horizontal speed under the run speed, and an
  independent re-computation of its arc clears the sampled pillar surface;
- the magma damage of the ascent.
"""

from __future__ import annotations

import hashlib
import json
import math
import struct
from pathlib import Path

import pytest

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/nefarian_magma_v1.json"
VMAPS = ROOT / "data/vmaps"
MID = 0.5 * 64.0 * 533.33333333
TILE = 533.33333 / 128.0

JUMP_VELOCITY = 7.95577
GRAVITY = 19.2911
RUN_SPEED = 7.0
BODY = 0.389

PROGRAM = PRELUDE + r'''
int main()
{
    std::printf("CONST %.4f %.3f %.5f %.4f %.3f\n", MagmaSurfaceZ, FloatDepthYards,
        JumpVelocity, JumpGravity, SwimStationRadius);
    for (int ms : { 0, 200, 1000, 5000, 9000, 13133, 13333 })
        std::printf("ORIGIN %d %.5f\n", ms, LoweringOriginZ(float(ms)));
    std::printf("REACH ring %.1f centre %.1f float %.1f top %.1f\n",
        LoweringReachesMs(RingLocalZ, MagmaSurfaceZ),
        LoweringReachesMs(FloorFlatLocalZ, MagmaSurfaceZ),
        LoweringReachesMs(RingLocalZ, MagmaSurfaceZ - FloatDepthYards),
        LoweringReachesMs(PlatformFrame::PillarTopLocalZ, MagmaSurfaceZ));
    for (uint32 ticks : { 1u, 8u, 9u, 100u })
        std::printf("DAMAGE %u %.0f\n", ticks, MagmaDamage(ticks));
    for (uint8 p = 0; p < 3; ++p)
        for (uint8 s = 0; s < 6; ++s)
        {
            PillarSlotProfile const& profile = SlotProfile(p, s);
            std::printf("PROFILE %u %u %.2f %.2f %.2f\n", p, s, profile.FlatRadius,
                profile.FlatEnvelopeRadius, profile.WallRadius);
            for (int i = 0; i <= 80; ++i)
                std::printf("ENV %u %u %d %.4f\n", p, s, i,
                    PillarSurfaceEnvelope(p, s, float(i) * 0.1f));
            for (float depth : { 1.0f, FloatDepthYards, 1.35f })
            {
                HopPlan const hop = PlanHop(p, s, SwimStationRadius, MagmaSurfaceZ - depth,
                    PlatformFrame::LoweredOriginZ);
                std::printf("HOP %u %u %.2f %d %s %.4f %.4f %.4f %.4f %.4f %.4f %d %.6f %.4f\n",
                    p, s, depth, hop.Ok ? 1 : 0, std::string(hop.Reason).c_str(),
                    hop.LandingRadius, hop.LandingLocalZ, hop.RiseYards, hop.AirTimeSeconds,
                    hop.SpeedXY, hop.MinClearanceYards, hop.DurationMs, hop.SplineVelocity,
                    hop.LaunchVerticalSpeed);
            }
            std::printf("SLOT %u %u %.4f %.4f %.4f %.4f\n", p, s,
                Distance(PillarSlot(p, s), PillarCenters[p]),
                Distance(PillarRadial(p, s, SwimStationRadius), PillarCenters[p]),
                Distance(PillarBase(p, s), PillarRadial(p, s, SwimStationRadius)),
                Length(PillarBase(p, s)));
        }
    return 0;
}
'''


def data() -> dict:
    return json.loads(DATA.read_text(encoding="utf-8"))


_OUTPUT: dict[str, str] = {}


def output(tmp_path_factory) -> list[list[str]]:
    if "text" not in _OUTPUT:
        _OUTPUT["text"] = _compile_and_run(tmp_path_factory.mktemp("magma"), PROGRAM)
    return [line.split() for line in _OUTPUT["text"].splitlines()]


def rows(tmp_path_factory, tag: str) -> list[list[str]]:
    return [row[1:] for row in output(tmp_path_factory) if row and row[0] == tag]


def _read_liquid_group(path: Path, index: int) -> dict:
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
    for group in range(groups):
        take("<6f2I")
        chunk(b"VERT")
        take("<I")
        (count,) = take("<I")
        if not count:
            continue
        pos += 12 * count
        chunk(b"TRIM")
        take("<I")
        (triangles,) = take("<I")
        pos += 12 * triangles
        chunk(b"MBIH")
        take("<6f")
        (tree,) = take("<I")
        pos += 4 * tree
        (objects,) = take("<I")
        pos += 4 * objects
        chunk(b"LIQU")
        (size,) = take("<I")
        if not size:
            continue
        start = pos
        tiles_x, tiles_y = take("<2I")
        corner = take("<3f")
        (liquid_type,) = take("<I")
        heights = take(f"<{(tiles_x + 1) * (tiles_y + 1)}f")
        flags = take(f"<{tiles_x * tiles_y}B")
        pos = start + size
        if group == index:
            return {"tiles": (tiles_x, tiles_y), "corner": corner, "type": liquid_type,
                    "heights": heights, "flags": flags}
    raise AssertionError("liquid group not found")


def _liquid_height(group: dict, spawn: list[float], world_x: float, world_y: float) -> float | None:
    """WmoLiquid::GetLiquidHeight, then ModelInstance::GetLiquidLevel."""
    model_x = MID - world_x - spawn[0]
    model_y = MID - world_y - spawn[1]
    tiles_x, tiles_y = group["tiles"]
    tx_f = (model_x - group["corner"][0]) / TILE
    ty_f = (model_y - group["corner"][1]) / TILE
    tx, ty = int(tx_f), int(ty_f)
    if tx_f < 0 or ty_f < 0 or tx >= tiles_x or ty >= tiles_y:
        return None
    if group["flags"][tx + ty * tiles_x] & 0x0F == 0x0F:
        return None
    dx, dy = tx_f - tx, ty_f - ty
    row = tiles_x + 1
    h = group["heights"]
    if dx > dy:
        sx = h[tx + 1 + ty * row] - h[tx + ty * row]
        sy = h[tx + 1 + (ty + 1) * row] - h[tx + 1 + ty * row]
    else:
        sx = h[tx + 1 + (ty + 1) * row] - h[tx + (ty + 1) * row]
        sy = h[tx + (ty + 1) * row] - h[tx + ty * row]
    return h[tx + ty * row] + dx * sx + dy * sy + spawn[2]


def test_magma_surface_is_sourced_from_the_arena_model(tmp_path_factory) -> None:
    magma = data()["magma_surface"]
    (constants,) = rows(tmp_path_factory, "CONST")
    assert float(constants[0]) == pytest.approx(magma["level_world_z"], abs=1e-4)
    assert all(sample["surface_z"] == magma["level_world_z"] for sample in magma["samples"])
    assert magma["liquid_type_chain"]["area_5094_override"] == [0, 0, 404, 0]
    wmo = VMAPS / "Blackwingv2.wmo.vmo"
    if not wmo.is_file():
        pytest.skip("data/vmaps is local-only; the committed samples carry the model's sha256")
    assert hashlib.sha256(wmo.read_bytes()).hexdigest() == magma["source"]["sha256"]
    group = _read_liquid_group(wmo, magma["group_index"])
    assert group["type"] == magma["liquid_type"] == 19
    spawn = magma["source"]["spawn_internal_position"]
    for sample in magma["samples"]:
        level = _liquid_height(group, spawn, *sample["world"])
        assert level == pytest.approx(sample["surface_z"], abs=1e-3), sample["name"]


def test_lowering_timeline_and_the_pillar_tops(tmp_path_factory) -> None:
    lowering = data()["lowering"]
    keys = dict((int(ms), offset) for ms, offset in lowering["animation_keys_ms_offset"])
    origin = {int(ms): float(z) for ms, z in rows(tmp_path_factory, "ORIGIN")}
    lowered, raised = lowering["lowered_origin_z"], lowering["raised_origin_z"]
    assert origin[0] == pytest.approx(raised, abs=1e-3)
    assert origin[13333] == pytest.approx(lowered, abs=1e-3)
    # Linear between the 13133 and 200 ms keys (path progress = 13333 - t).
    for ms in (1000, 5000, 9000):
        progress = 13333 - ms
        expected = lowered + keys[13133] * (progress - 200) / (13133 - 200)
        assert origin[ms] == pytest.approx(expected, abs=1e-3)
    (reach,) = rows(tmp_path_factory, "REACH")
    ring, centre, floating, top = (float(reach[i]) for i in (1, 3, 5, 7))
    assert ring == pytest.approx(5504, abs=5) and centre == pytest.approx(3658, abs=5)
    assert floating > ring
    assert top == pytest.approx(13333)  # never
    magma = data()["magma_surface"]["level_world_z"]
    top_at_stop = lowered + data()["pillar"]["top_local_z"]
    assert top_at_stop - magma == pytest.approx(0.286, abs=1e-3)
    assert lowered + min(keys.values()) + data()["pillar"]["top_local_z"] > magma


def test_magma_damage_model(tmp_path_factory) -> None:
    damage = {int(n): float(d) for n, d in rows(tmp_path_factory, "DAMAGE")}
    assert damage[1] == 5000
    assert damage[8] == 5000 * 8 + 125 * 8 * 7 == 47000
    assert damage[9] == 54000
    # Stacks cap at 99 (SpellAuraOptions 5778).
    assert damage[100] == sum(5000 + 250 * min(k, 99) for k in range(100))
    # The ascent: the ring goes under 5.5 s after the platform starts down,
    # the hop lands about 0.6 s after the 13.33 s stop: 8 ticks.
    (reach,) = rows(tmp_path_factory, "REACH")
    in_magma = (13333 + 600 - float(reach[1])) / 1000.0
    assert 8 <= in_magma < 9


def test_slot_profile_matches_the_model_samples(tmp_path_factory) -> None:
    slots = data()["pillar"]["slots"]
    profiles = {(int(p), int(s)): tuple(float(v) for v in rest)
                for p, s, *rest in rows(tmp_path_factory, "PROFILE")}
    envelope = {}
    for p, s, i, z in rows(tmp_path_factory, "ENV"):
        envelope[(int(p), int(s), int(i))] = float(z)
    for p in range(3):
        for s in range(6):
            sampled = slots[p][s]
            assert profiles[(p, s)] == (sampled["flat_radius_own"], sampled["flat_radius_envelope"],
                                        sampled["wall_radius_envelope"])
            for i, z in enumerate(sampled["envelope_local_z"]):
                if z is None:
                    continue
                # The strategy's envelope bounds the sampled surface from above
                # (0.03 for the 0.1-yard sampling of the rim).
                assert envelope[(p, s, i)] >= z - 0.03, (p, s, i, envelope[(p, s, i)], z)


def _sampled_surface(slot: dict, radius: float) -> float:
    values = slot["envelope_local_z"]
    if radius > 8.0:
        return 1.439
    index = max(0, radius) / 0.1
    low = int(index)
    high = min(low + 1, len(values) - 1)
    present = [v for v in (values[low], values[high]) if v is not None]
    return max(present) if present else -100.0


def test_every_slot_hop_is_the_client_jump(tmp_path_factory) -> None:
    info = data()
    slots = info["pillar"]["slots"]
    lowered = info["lowering"]["lowered_origin_z"]
    magma = info["magma_surface"]["level_world_z"]
    station = float(rows(tmp_path_factory, "CONST")[0][4])
    hops = rows(tmp_path_factory, "HOP")
    assert len(hops) == 3 * 6 * 3
    for (p, s, depth, ok, reason, landing, landing_z, rise, air, speed, clearance,
         duration_ms, velocity, launch) in hops:
        p, s = int(p), int(s)
        assert ok == "1", (p, s, depth, reason)
        landing, landing_z, rise, air, speed = map(float, (landing, landing_z, rise, air, speed))
        # Just above the waterline at the lowered stop, on the rim.
        assert 0.0 < lowered + landing_z - magma <= 0.06
        slot = slots[p][s]
        assert slot["flat_radius_own"] < landing < slot["wall_radius_envelope"]
        # The client's jump: rise under the apex, horizontal under the run speed.
        assert rise < JUMP_VELOCITY ** 2 / (2 * GRAVITY)
        assert 0.0 < speed <= RUN_SPEED
        # The executed spline (MotionMaster::MoveJumpWithGravity through
        # Movement::MoveSpline): 1 + trunc(3D length * 1000 / velocity) ms,
        # the ballistic air time rounded down; launched at most at the client's
        # jump speed.
        from_z = magma - float(depth)
        ballistic = (JUMP_VELOCITY + math.sqrt(JUMP_VELOCITY ** 2 - 2 * GRAVITY * rise)) / GRAVITY
        length = math.hypot(station - landing, rise)
        duration_ms, velocity, launch = int(duration_ms), float(velocity), float(launch)
        assert duration_ms == math.floor(ballistic * 1000)
        assert duration_ms == 1 + int(length * (1000.0 / velocity))
        assert air == pytest.approx(duration_ms / 1000.0, abs=1e-6)
        assert launch <= JUMP_VELOCITY + 1e-3 and launch > JUMP_VELOCITY - 0.05
        # Independent check of that arc against the sampled pillar surface.
        worst = 100.0
        for i in range(401):
            t = air * i / 400
            radius = station - speed * t
            if t > air / 2 and radius - landing < BODY + 0.05:
                continue
            feet = from_z + rise * t / air + 0.5 * GRAVITY * t * (air - t)
            surface = lowered + max(_sampled_surface(slot, radius + k * BODY)
                                    for k in (-1, -0.5, 0, 0.5, 1))
            worst = min(worst, feet - surface)
        assert worst > 0.05, (p, s, depth, worst)


def test_slot_stations_and_feet(tmp_path_factory) -> None:
    info = data()
    for p, s, slot_r, station_r, foot_to_station, foot_arena_r in rows(tmp_path_factory, "SLOT"):
        slot = info["pillar"]["slots"][int(p)][int(s)]
        # The slot is on the flat top with the whole body.
        assert float(slot_r) + BODY <= slot["flat_radius_own"]
        # The station keeps the body outside the skirt (6.0) and the wall.
        assert float(station_r) - BODY > 6.05
        # One swim leg from the foot, and the foot is a floor spot.
        assert float(foot_to_station) <= 12.0
        assert float(foot_arena_r) <= 57.0

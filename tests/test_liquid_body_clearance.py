"""The lava swim and the hop onto a Nefarian pillar keep the whole body out of the model.

Round-3 fix pass (packet liquid_clearance; audit of packet fall_clearance):
ExecuteSwim and ExecuteHop swept only the body's centre line (line of sight
at 0.15, half and 0.9 of the height, no lateral radius, the end point
unproven), so a swim beside the pillar skirt or a hop whose arc grazed the
wall edge could end with the side of the body inside GO 207834's model.

Now (Bots/BotLiquidBodyClearance.h, on Movement/Spline/PassengerBodyTrajectory.h)
the swim proves the body cylinder (knee to head, full radius) along its
segment and at its end, and the hop proves the jump the REAL
Movement::MoveSpline runs (every 5 ms, reduced to chords, the body grown in
radius, knee and head by the chord deviation and the arc's bulge) and the
landing footprint,
choosing a nearby landing on the same rim when the requested one is
obstructed.

The oracle is independent of the rays: the exact overlap of the body
cylinder with every model triangle (tests/test_passenger_fall_body_clearance.py),
at every 5 ms of the real swim and jump splines and at their ends, in the
platform's frame, also while the platform lowers under a swimmer.
"""

from __future__ import annotations

import os
import re
import subprocess
from pathlib import Path

import pytest

from tests import test_nefarian_ledge_drop_floor_query as vmo
from tests.test_bot_native_fall_spline_state import STUB_CREATURE, STUB_LOG
from tests.test_nefarian_strategy import INCLUDES
from tests.test_nefarian_strategy import PRELUDE
from tests.test_passenger_fall_body_clearance import PROGRAM as FALL_PROGRAM
from tests.test_passenger_spline_collision import _triangles_file


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
SPLINE = GAME / "Movement/Spline"
CLEARANCE = GAME / "Bots/BotLiquidBodyClearance.h"
EXECUTOR = GAME / "Bots/BotWorldPopulationMgrNativePathTransportLiquid.cpp"
ASCENT = GAME / "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianAscent.h"

# The fall test's mesh loader, ray query and exact cylinder-triangle oracle,
# reused verbatim (everything before its fall-spline section).
ORACLE = FALL_PROGRAM[:FALL_PROGRAM.index("// ---- The real fall spline")]
ORACLE = ORACLE.replace('#include "Bots/BotLedgeDropBodyClearance.h"\n',
                        '#include "Bots/BotLiquidBodyClearance.h"\n')
ORACLE = ORACLE.replace("namespace Route = BotValidationRouteNative;\n", "")
ORACLE = ORACLE.replace("namespace Clear = BotLedgeDropBodyClearance;\n",
                        "namespace Clear = BotLiquidBodyClearance;\n"
                        "namespace Liquid = BotValidationRouteNativeLiquid;\n")

PROGRAM = ORACLE + r'''
// ---- The platform's frame: the model is in the elevator's local frame; a
// swimmer that is not a passenger keeps its world height while the platform
// moves, so its local height is world z minus the origin.

// The old centre-line sweep (SweepClear): line of sight at 0.15, half and
// 0.9 of the height along the centre line, no radius.
static bool OldSweepClear(Vector3 const& from, Vector3 const& to)
{
    for (float const lift : { 0.15f, 0.5f * Height, 0.9f * Height })
    {
        Vector3 const a(from.x, from.y, from.z + lift), b(to.x, to.y, to.z + lift);
        if ((b - a).length() > 1e-4f && Blocked(a, (b - a).direction(), (b - a).length()))
            return false;
    }
    return true;
}

static bool OldHopClear(Vector3 const& from, Vector3 const& to, Liquid::SplineJump const& jump)
{
    Vector3 previous = from;
    for (uint32 i = 1; i <= Liquid::JumpSamples; ++i)
    {
        float const t = jump.DurationSeconds * float(i) / float(Liquid::JumpSamples);
        float const along = t / jump.DurationSeconds;
        Vector3 const point(from.x + (to.x - from.x) * along, from.y + (to.y - from.y) * along,
            Liquid::SplineJumpFeetZ(from.z, to.z - from.z, jump.DurationSeconds, t));
        if (!OldSweepClear(previous, point))
            return false;
        previous = point;
    }
    return true;
}

// The real splines: MoveSplineInit::MoveTo at the swim speed, and
// MotionMaster::MoveJumpWithGravity (Parabolic, vertical acceleration =
// gravity, velocity = the planned 3D speed).
static Movement::MoveSplineInitArgs SwimArgs(Vector3 const& from, Vector3 const& to)
{
    Movement::MoveSplineInitArgs args;
    args.path = { from, to };
    args.velocity = Nef::SwimSpeedYardsPerSecond;
    return args;
}

static Movement::MoveSplineInitArgs JumpArgs(Vector3 const& from, Vector3 const& to, float velocity)
{
    Movement::MoveSplineInitArgs args;
    args.path = { from, to };
    args.velocity = velocity;
    args.flags.Parabolic = true;
    args.parabolic_amplitude = 0.0f;
    args.vertical_acceleration = Liquid::JumpGravity;
    args.effect_start_time_percent = 0.0f;
    return args;
}

// A MoveSpline is not movable: initialized in place.
struct Run
{
    Movement::MoveSpline Spline;
    explicit Run(Movement::MoveSplineInitArgs const& args) { Spline.Initialize(args); }
};

struct Oracle { float Depth = 0.0f; float EndDepth = 0.0f; int Samples = 0; float MaxSampleError = 0.0f; };

// Every 5 ms of the spline and its end; `lift(ms)` is how far the swimmer's
// local height has risen by the platform's own motion (0 when it keeps still).
template <class Lift>
static Oracle OracleSpline(Movement::MoveSpline const& spline, Lift&& lift)
{
    Oracle oracle;
    Movement::Location const a = spline.ComputePosition(0);
    Movement::Location const b = spline.ComputePosition(spline.Duration());
    // Every triangle within the radius of the path's plan box (the jump's
    // apex is at most 1.7 over its ends; the platform's own rise is lift()).
    float const low = std::min(a.z, b.z) - 1.0f, high = std::max(a.z, b.z) + Height + 12.0f;
    std::vector<Tri const*> near;
    for (Tri const& t : mesh)
        if (t.hi.x >= std::min(a.x, b.x) - Radius && t.lo.x <= std::max(a.x, b.x) + Radius
            && t.hi.y >= std::min(a.y, b.y) - Radius && t.lo.y <= std::max(a.y, b.y) + Radius
            && t.hi.z >= low && t.lo.z <= high)
            near.push_back(&t);
    for (int32 t = 0;; t += 5)
    {
        int32 const at = std::min(t, spline.Duration());
        Movement::Location const p = spline.ComputePosition(at);
        float const depth = Overlap(Vector3(p.x, p.y, p.z + lift(at)), near);
        oracle.Depth = std::max(oracle.Depth, depth);
        ++oracle.Samples;
        if (at == spline.Duration())
        {
            oracle.EndDepth = depth;
            break;
        }
    }
    return oracle;
}

static float const Still = 0.0f;
static auto const Static = [](int32) { return Still; };

// Near() covers the axis' neighbourhood only: widen it for a long segment.
static std::vector<Tri const*> NearAll()
{
    std::vector<Tri const*> all;
    for (Tri const& t : mesh)
        all.push_back(&t);
    return all;
}

static float OverlapAt(Vector3 const& feet) { static std::vector<Tri const*> const all = NearAll(); return Overlap(feet, all); }

// ---- The executor's hop probe on the model, landing by landing.
static float const FloorTolerance = 0.3f; // AscentStep::FloorToleranceYards

static bool FloorWithin(float x, float y, float z, float tolerance)
{
    float floor;
    return FloorBelow(x, y, z + tolerance, 2.0f * tolerance, floor);
}

static Clear::HopCandidate ProbeHop(Vector3 const& from, Vector3 const& landing, Vector3& resolved)
{
    Clear::HopCandidate candidate;
    float floor = 0.0f;
    resolved = landing;
    if (!FloorBelow(landing.x, landing.y, landing.z + 0.6f, 1.2f, floor))
    {
        candidate.Reason = "native_liquid_hop_landing_off_platform";
        return candidate;
    }
    resolved.z = floor;
    Liquid::SplineJump const jump = Liquid::PlanSplineJump(
        std::hypot(resolved.x - from.x, resolved.y - from.y), resolved.z - from.z, 7.0f);
    if (!jump.Ok)
    {
        candidate.Reason = "native_" + jump.Reason;
        return candidate;
    }
    candidate.Admissible = true;
    long const before = rays;
    Clear::TrajectoryProof const proof = Clear::ProveHop(from, resolved, jump, Radius, Height, Blocked);
    candidate.BodyClear = proof.Clear();
    candidate.Rays = proof.Proof.Rays;
    CHECK(long(proof.Proof.Rays) == rays - before);
    for (int k = 0; k < Body::InnerDirections; ++k)
    {
        float const angle = 6.28318531f * float(k) / float(Body::InnerDirections);
        ++candidate.InnerPoints;
        candidate.InnerSupported += FloorWithin(resolved.x + 0.5f * Radius * std::cos(angle),
            resolved.y + 0.5f * Radius * std::sin(angle), resolved.z, FloorTolerance);
    }
    return candidate;
}

// BotNefarianAscent.h SwimStationToleranceYards: a swimmer this near its
// station hops from where it floats.
static float const StationTolerance = 0.75f;

static Vector3 LocalAt(Nef::LocalPoint p, float z) { return Vector3(p.X, p.Y, z); }

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::size_t count = 0;
    in >> count;
    mesh.resize(count);
    for (Tri& t : mesh)
    {
        in >> t.a.x >> t.a.y >> t.a.z >> t.b.x >> t.b.y >> t.b.z >> t.c.x >> t.c.y >> t.c.z;
        t.lo = t.a.min(t.b).min(t.c);
        t.hi = t.a.max(t.b).max(t.c);
    }
    CHECK(count > 100);

    // The swimmer's heights in the platform frame. It floats where the ring
    // is FloatDepthYards under the surface (origin 0.132) and swims to its
    // station at that world height; the platform then lowers 7.0 yards under
    // it to the lowered stop, where the station is local 8.439.
    float const floatWorld = Nef::MagmaSurfaceZ - Nef::FloatDepthYards;
    float const floatOrigin = floatWorld - Nef::RingLocalZ;
    float const stationLocal = floatWorld - Nef::PlatformFrame::LoweredOriginZ;
    float const lowerRate = Nef::RaisedOffset * 1000.0f / (Nef::LinearToMs - Nef::LinearFromMs);
    std::printf("float_origin=%.4f station_local=%.4f lower_rate=%.4f\n", floatOrigin, stationLocal, lowerRate);

    // 1. Every pillar/slot swim leg from the foot to the station, proven at
    // launch; the oracle checks the real spline in the still frame and while
    // the platform keeps lowering under it, and the hold at the station all
    // the way down to the lowered stop.
    int swims = 0, swimClear = 0, swimOverlap = 0, swimUnsound = 0;
    uint32 swimMaxRays = 0;
    float swimMaxDepth = 0.0f, holdMaxDepth = 0.0f;
    double swimMs = 0.0;
    for (int pillar = 0; pillar < 3; ++pillar)
        for (int slot = 0; slot < 6; ++slot)
        {
            Vector3 const foot = LocalAt(Nef::PillarBase(uint8(pillar), uint8(slot)), Nef::RingLocalZ);
            Vector3 const station = LocalAt(Nef::PillarRadial(uint8(pillar), uint8(slot), Nef::SwimStationRadius),
                Nef::RingLocalZ);
            auto const t0 = std::chrono::steady_clock::now();
            Clear::TrajectoryProof const proof = Clear::ProveSwim(foot, station, Radius, Height, Blocked);
            swimMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
            swimMaxRays = std::max(swimMaxRays, proof.Proof.Rays);
            Run const run(SwimArgs(foot, station));
            Movement::MoveSpline const& spline = run.Spline;
            Oracle const still = OracleSpline(spline, Static);
            Oracle const lowering = OracleSpline(spline, [&](int32 ms) { return lowerRate * float(ms) / 1000.0f; });
            ++swims;
            swimClear += proof.Clear();
            bool const overlap = still.Depth > 1e-4f;
            swimOverlap += overlap;
            swimUnsound += proof.Clear() && overlap;
            swimMaxDepth = std::max({ swimMaxDepth, still.Depth, lowering.Depth });
            CHECK(proof.Clear());
            CHECK(still.Depth <= 1e-4f && lowering.Depth <= 1e-4f);
            for (float z = Nef::RingLocalZ; z <= stationLocal + 1e-3f; z += 0.05f)
                holdMaxDepth = std::max(holdMaxDepth, OverlapAt(Vector3(station.x, station.y, z)));
            // A depth correction at the station at the lowered stop.
            Vector3 const deep(station.x, station.y, stationLocal - 0.5f);
            Vector3 const held(station.x, station.y, stationLocal);
            CHECK(Clear::ProveSwim(deep, held, Radius, Height, Blocked).Clear());
        }
    std::printf("swims legs=%d clear=%d overlapping=%d unsound=%d max_depth=%.4f hold_max_depth=%.4f max_rays=%u mean_ms=%.3f\n",
        swims, swimClear, swimOverlap, swimUnsound, swimMaxDepth, holdMaxDepth, swimMaxRays, swimMs / swims);
    CHECK(holdMaxDepth <= 1e-4f);

    // 2. Negative control: a swim past the skirt where the model's skirt
    // reaches farthest (pillar 2, 305 degrees), its centre line outside every
    // part of it (radius 6.1), at a height where the skirt is between the
    // knee and the head. The old centre-line sweep admits it; the body
    // overlaps the skirt; the new proof refuses it.
    {
        Nef::LocalPoint const centre = Nef::PillarCenters[2];
        float const heading = Nef::DegToRad(305.0f);
        float const r = 6.1f;
        Nef::LocalPoint const mid = Nef::Offset(centre, heading, r);
        float const across = heading + 0.5f * Nef::Pi;
        float const z = Nef::RingLocalZ - 0.1f;
        Vector3 const a = LocalAt(Nef::Offset(mid, across, -1.0f), z);
        Vector3 const b = LocalAt(Nef::Offset(mid, across, 1.0f), z);
        bool const old = OldSweepClear(a, b);
        Clear::TrajectoryProof const proof = Clear::ProveSwim(a, b, Radius, Height, Blocked);
        Oracle const oracle = OracleSpline(Run(SwimArgs(a, b)).Spline, Static);
        std::printf("swim_control old=%d new=%d kind=%d overlap=%.4f\n", old, proof.Clear(), int(proof.Proof.Kind), oracle.Depth);
        CHECK(old && !proof.Clear() && oracle.Depth > 0.05f);
        // The end point alone: a radial swim in that stops with the side of
        // the body in the skirt (its centre line never meets it).
        Vector3 const out = LocalAt(Nef::Offset(centre, heading, r + 1.5f), z);
        Vector3 const in = LocalAt(mid, z);
        Clear::TrajectoryProof const stop = Clear::ProveSwim(out, in, Radius, Height, Blocked);
        Oracle const end = OracleSpline(Run(SwimArgs(out, in)).Spline, Static);
        std::printf("swim_end_control old=%d new=%d kind=%d end_overlap=%.4f\n", OldSweepClear(out, in),
            stop.Clear(), int(stop.Proof.Kind), end.EndDepth);
        CHECK(OldSweepClear(out, in) && !stop.Clear() && end.EndDepth > 0.05f);
    }

    // 3. Every pillar/slot hop from its station at the lowered stop onto the
    // rim just above the waterline, and from every origin the station
    // tolerance admits: whatever the proof admits jumps with zero overlap at
    // every 5 ms of the real jump spline and at its landing.
    int hops = 0, hopProved = 0, hopOverlap = 0, hopUnsound = 0, hopConservative = 0, oldAdmitsOverlap = 0;
    int chosen = 0, refused = 0, shifted = 0, requestedClear = 0;
    uint32 hopMaxRays = 0, chooseMaxRays = 0;
    double hopMs = 0.0;
    float sampleError = 0.0f;
    std::size_t maxChords = 0;
    float maxInflation = 0.0f;
    for (int pillar = 0; pillar < 3; ++pillar)
        for (int slot = 0; slot < 6; ++slot)
        {
            float const heading = Nef::PillarSlotHeading(uint8(pillar), uint8(slot));
            Nef::LocalPoint const centre = Nef::PillarCenters[pillar];
            Vector3 const requested = LocalAt(Nef::PillarRadial(uint8(pillar), uint8(slot),
                Nef::HopLandingRadius(uint8(pillar), uint8(slot))), Nef::HopLandingLocalZ);
            int origins = 0;
            for (float radial = -0.75f; radial <= 0.75f + 1e-3f; radial += 0.25f)
                for (float lateral = -0.75f; lateral <= 0.75f + 1e-3f; lateral += 0.25f)
                    for (float depth : { -0.15f, 0.0f, 0.15f })
                    {
                        if (std::hypot(radial, lateral) > StationTolerance + 1e-3f)
                            continue;
                        Nef::LocalPoint const o = Nef::Offset(Nef::Offset(centre, heading,
                            Nef::SwimStationRadius + radial), heading + 0.5f * Nef::Pi, lateral);
                        Vector3 const from = LocalAt(o, stationLocal + depth);
                        ++origins;
                        // The requested landing: proof against the oracle.
                        Vector3 landing;
                        Clear::HopCandidate const probe = ProbeHop(from, requested, landing);
                        if (!probe.Admissible)
                            continue;
                        Liquid::SplineJump const jump = Liquid::PlanSplineJump(
                            std::hypot(landing.x - from.x, landing.y - from.y), landing.z - from.z, 7.0f);
                        Run const run(JumpArgs(from, landing, jump.Velocity));
                        Movement::MoveSpline const& spline = run.Spline;
                        CHECK(spline.Duration() == jump.DurationMs);
                        // The sampled arc is the spline's.
                        std::vector<Vector3> const samples = Clear::HopSamples(from, landing, jump);
                        for (std::size_t i = 0; i < samples.size(); ++i)
                        {
                            int32 const ms = std::min<int32>(int32(i) * Body::SampleStepMs, spline.Duration());
                            Movement::Location const p = spline.ComputePosition(ms);
                            sampleError = std::max(sampleError, (Vector3(p.x, p.y, p.z) - samples[i]).length());
                        }
                        Oracle const oracle = OracleSpline(spline, Static);
                        auto const t0 = std::chrono::steady_clock::now();
                        Clear::TrajectoryProof const proof = Clear::ProveHop(from, landing, jump, Radius, Height, Blocked);
                        hopMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
                        hopMaxRays = std::max(hopMaxRays, proof.Proof.Rays);
                        maxChords = std::max(maxChords, proof.Chords);
                        maxInflation = std::max(maxInflation, proof.InflationYards);
                        ++hops;
                        bool const overlap = oracle.Depth > 1e-4f;
                        hopOverlap += overlap;
                        hopProved += proof.Clear();
                        hopConservative += !proof.Clear() && !overlap;
                        if (proof.Clear() && overlap)
                        {
                            ++hopUnsound;
                            std::fprintf(stderr, "UNSOUND hop pillar=%d slot=%d radial=%.2f lateral=%.2f depth=%.2f overlap=%.4f\n",
                                pillar, slot, radial, lateral, depth, oracle.Depth);
                        }
                        oldAdmitsOverlap += OldHopClear(from, landing, jump) && overlap;
                        requestedClear += proof.Clear() && Clear::FootprintSupported(probe);
                        // The chooser: the requested landing or a nearby one.
                        Clear::HopChoice const choice = Clear::ChooseClearHop([&](std::size_t index)
                        {
                            Vector3 resolved;
                            return ProbeHop(from, Clear::OffsetLanding(from, requested, Clear::HopLandingOffsets[index]), resolved);
                        });
                        chooseMaxRays = std::max(chooseMaxRays, choice.Rays);
                        if (!choice.Ok)
                        {
                            ++refused;
                            std::printf("hop_refused pillar=%d slot=%d radial=%.2f lateral=%.2f depth=%.2f reason=%s\n",
                                pillar, slot, radial, lateral, depth, choice.Reason.c_str());
                            continue;
                        }
                        ++chosen;
                        shifted += choice.Index != 0;
                        Vector3 picked;
                        ProbeHop(from, Clear::OffsetLanding(from, requested, Clear::HopLandingOffsets[choice.Index]), picked);
                        CHECK((picked - requested).length() <= Clear::MaxLandingShiftYards);
                        Liquid::SplineJump const pickedJump = Liquid::PlanSplineJump(
                            std::hypot(picked.x - from.x, picked.y - from.y), picked.z - from.z, 7.0f);
                        Oracle const pickedOracle = OracleSpline(Run(JumpArgs(from, picked, pickedJump.Velocity)).Spline, Static);
                        CHECK(pickedOracle.Depth <= 1e-4f && pickedOracle.EndDepth <= 1e-4f);
                    }
            CHECK(origins >= 20);
        }
    std::printf("hops cases=%d proved=%d overlapping=%d unsound=%d conservative=%d old_admits_overlapping=%d "
        "max_rays=%u mean_ms=%.3f max_chords=%zu max_inflation=%.4f sample_error=%.6f\n",
        hops, hopProved, hopOverlap, hopUnsound, hopConservative, oldAdmitsOverlap, hopMaxRays,
        hops ? hopMs / hops : 0.0, maxChords, maxInflation, sampleError);
    std::printf("hop_choices chosen=%d refused=%d shifted=%d requested_clear=%d choose_max_rays=%u\n",
        chosen, refused, shifted, requestedClear, chooseMaxRays);
    CHECK(hopUnsound == 0 && swimUnsound == 0);
    CHECK(sampleError < 1e-3f);

    // 4. A hop arc reduced to chords keeps the whole body under a ceiling
    // (round-3 v4 review): the chord reduction's inflation grows the body up
    // and down as well as sideways (Body::MakeBody), so the head still meets
    // a ceiling the arc reaches between the chords' top and its own. One
    // second of native gravity over level ground, true apex 2.411388, retained
    // apex 2.405360; the ceiling at the head height of the midpoint.
    {
        std::vector<Tri> const saved = mesh;
        Liquid::SplineJump jump;
        jump.Ok = true;
        jump.DurationMs = 1000;
        jump.DurationSeconds = 1.0f;
        Vector3 const from(0, 0, 0), to(7, 0, 0);
        std::vector<Vector3> const samples = Clear::HopSamples(from, to, jump);
        Body::Chords const chords = Body::ReduceToChords(samples);
        float sampledApex = -1e9f, retainedApex = -1e9f;
        for (Vector3 const& p : samples)
            sampledApex = std::max(sampledApex, p.z);
        for (std::size_t i : chords.Kept)
            retainedApex = std::max(retainedApex, samples[i].z);
        auto plate = [](float z) -> std::vector<Tri>
        {
            return { { Vector3(-3, -3, z), Vector3(12, -3, z), Vector3(12, 3, z), {}, {} },
                     { Vector3(-3, -3, z), Vector3(12, 3, z), Vector3(-3, 3, z), {}, {} } };
        };
        struct Both { bool Reduced; bool Full; };
        auto prove = [&](float ceiling)
        {
            mesh = plate(ceiling);
            Clear::TrajectoryProof const reduced = Clear::ProveHop(from, to, jump, Radius, Height, Blocked);
            Body::Proof const full = Body::ProveTrajectory(samples, Body::MakeBody(Radius, Height), Blocked);
            return Both{ reduced.Clear(), full.Clear() };
        };
        std::printf("hop_arc samples=%zu chords=%zu sampled_apex=%.6f retained_apex=%.6f inflation=%.6f\n",
            samples.size(), chords.Kept.size() - 1, sampledApex, retainedApex, chords.InflationYards);
        CHECK(std::fabs(sampledApex - 2.411388f) < 1e-3f);
        CHECK(sampledApex - retainedApex > 0.004f && chords.InflationYards >= sampledApex - retainedApex);
        float const mid = 0.5f * (sampledApex + retainedApex) + Height;
        Both const hit = prove(mid);
        std::printf("hop_ceiling z=%.6f full_clear=%d reduced_clear=%d\n", mid, hit.Full, hit.Reduced);
        CHECK(!hit.Full && !hit.Reduced);
        int met = 0, unsound = 0, conservative = 0;
        for (float z = retainedApex + Height - 0.02f; z <= sampledApex + Height + 0.08f; z += 0.001f)
        {
            Both const c = prove(z);
            met += !c.Full;
            unsound += !c.Full && c.Reduced;
            conservative += c.Full && !c.Reduced;
        }
        std::printf("hop_ceiling_sweep met=%d unsound=%d conservative=%d\n", met, unsound, conservative);
        CHECK(met > 5 && unsound == 0);
        Both const open = prove(sampledApex + Height + chords.InflationYards + 0.02f);
        std::printf("hop_ceiling_open full_clear=%d reduced_clear=%d\n", open.Full, open.Reduced);
        CHECK(open.Full && open.Reduced);
        mesh = saved;
    }
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run(tmp_path: Path, program: str) -> str:
    stub = tmp_path / "stub"
    stub.mkdir(exist_ok=True)
    (stub / "Log.h").write_text(STUB_LOG)
    (stub / "Creature.h").write_text(STUB_CREATURE)
    source = tmp_path / "program.cpp"
    source.write_text(program)
    binary = tmp_path / "program"
    includes = [stub, GAME, SPLINE, GAME / "Entities/Object/Updates", ROOT / "dep/g3dlite/include",
                ROOT / "dep/fmt/include"] + [ROOT / include for include in INCLUDES]
    command = ["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(SPLINE / name) for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary), str(_triangles_file(tmp_path))], cwd=ROOT, capture_output=True,
                         text=True, timeout=900)
    if os.environ.get("LIQUID_CLEARANCE_VERBOSE"):
        print(run.stdout)
        print(run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> str:
    vmo._model()
    return _compile_and_run(tmp_path_factory.mktemp("liquid_body"), PROGRAM)


def test_every_pillar_slot_swim_and_the_station_hold_are_clear(output: str) -> None:
    swims = re.search(r"swims legs=(\d+) clear=(\d+) overlapping=(\d+) unsound=(\d+) max_depth=(\S+) "
                      r"hold_max_depth=(\S+)", output)
    assert swims and int(swims.group(1)) == 18 and int(swims.group(2)) == 18, output
    assert int(swims.group(3)) == 0 and float(swims.group(5)) == 0.0 and float(swims.group(6)) == 0.0, output
    assert "failures=0" in output, output


def test_the_centre_line_sweep_admitted_a_swim_with_the_body_in_the_skirt(output: str) -> None:
    control = re.search(r"swim_control old=1 new=0 kind=[12] overlap=(\S+)", output)
    assert control and float(control.group(1)) > 0.05, output
    end = re.search(r"swim_end_control old=1 new=0 kind=1 end_overlap=(\S+)", output)
    assert end and float(end.group(1)) > 0.05, output


def test_every_pillar_slot_hop_the_proof_admits_is_clear_of_the_model(output: str) -> None:
    hops = re.search(r"hops cases=(\d+) proved=(\d+) overlapping=(\d+) unsound=(\d+) conservative=(\d+) "
                     r"old_admits_overlapping=(\d+) max_rays=(\d+)", output)
    assert hops, output
    cases, proved, overlapping, unsound, _, old, _ = (int(g) for g in hops.groups())
    assert cases >= 18 * 20 and unsound == 0, output
    # The old 24-sample centre-line sweep admitted every hop that overlaps.
    assert overlapping > 0 and old == overlapping, output
    choices = re.search(r"hop_choices chosen=(\d+) refused=(\d+) shifted=(\d+) requested_clear=(\d+)", output)
    assert choices and int(choices.group(1)) + int(choices.group(2)) == cases, output
    # Only origins nearer the pillar than the strategy's hop gate are refused.
    for line in re.findall(r"hop_refused .*", output):
        radial = float(re.search(r"radial=(\S+)", line).group(1))
        assert radial < -0.25 - 1e-6, line
    assert "failures=0" in output, output


def test_a_reduced_hop_arc_still_meets_a_ceiling_the_arc_reaches(output: str) -> None:
    # The body grows up and down with the chord inflation, not only sideways:
    # one second of native gravity, true apex 2.411388, retained apex below.
    arc = re.search(r"hop_arc samples=\d+ chords=\d+ sampled_apex=(\S+) retained_apex=(\S+) inflation=(\S+)", output)
    assert arc and float(arc.group(1)) == pytest.approx(2.411388, abs=1e-3), output
    assert float(arc.group(2)) < float(arc.group(1)) - 0.004
    ceiling = re.search(r"hop_ceiling z=(\S+) full_clear=0 reduced_clear=0", output)
    assert ceiling and float(ceiling.group(1)) == pytest.approx(4.4397, abs=2e-3), output
    assert re.search(r"hop_ceiling_sweep met=\d+ unsound=0 ", output), output
    assert re.search(r"hop_ceiling_open full_clear=1 reduced_clear=1", output), output
    assert "failures=0" in output, output


# ---- Emerge: the platform rising into a swimmer (phase 3 raise).
#
# The strategy's own decisions (BotNefarianAscent.h) replayed against the
# real model while the platform rises: the swimmer moves along each swim the
# executor would launch (its static body proof at launch, as ExecuteSwim),
# and boards when the executor's Emerge would accept it (the floor within its
# tolerance of the feet and the body clear, as ExecuteEmerge). The oracle
# checks the exact body overlap at every 5 ms, in the platform's frame, until
# the swimmer is aboard.
STRATEGY_PRELUDE = PRELUDE + r'''
static Blackboard AscentBoard(float originZ)
{
    Blackboard board = PlatformBoard(originZ);
    for (ActorSnapshot& player : board.Players)
        player.Position = LocalToWorld({ 0.0f, 0.0f }, FloorLocalZAt({ 0.0f, 0.0f }), originZ);
    return board;
}
'''
EMERGE = STRATEGY_PRELUDE + r'''
#include "Bots/BotLiquidBodyClearance.h"
#include <fstream>
#include <vector>

namespace Clear = BotLiquidBodyClearance;
namespace Body = Movement::BodyTrajectory;

struct P3
{
    float x, y, z;
    P3 operator+(P3 const& o) const { return { x + o.x, y + o.y, z + o.z }; }
    P3 operator-(P3 const& o) const { return { x - o.x, y - o.y, z - o.z }; }
    P3 operator*(float f) const { return { x * f, y * f, z * f }; }
    float dot(P3 const& o) const { return x * o.x + y * o.y + z * o.z; }
    P3 cross(P3 const& o) const { return { y * o.z - z * o.y, z * o.x - x * o.z, x * o.y - y * o.x }; }
};
struct Tri { P3 a, b, c, lo, hi; };
static std::vector<Tri> mesh;
static float const Radius = 0.389f;
static float const Height = 2.0313f;

static bool Hit(P3 const& o, P3 const& d, Tri const& t, float& dist)
{
    P3 const e1 = t.b - t.a, e2 = t.c - t.a, p = d.cross(e2);
    float const det = e1.dot(p);
    if (std::fabs(det) < 1e-5f)
        return false;
    float const f = 1.0f / det;
    P3 const s = o - t.a;
    float const u = f * s.dot(p);
    if (u < 0.0f || u > 1.0f)
        return false;
    P3 const q = s.cross(e1);
    float const v = f * d.dot(q);
    if (v < 0.0f || u + v > 1.0f)
        return false;
    float const h = f * e2.dot(q);
    if (h > 0.0f && h < dist)
    {
        dist = h;
        return true;
    }
    return false;
}

static float Nearest(P3 const& o, P3 const& d, float maxDistance)
{
    float dist = maxDistance;
    bool hit = false;
    for (Tri const& t : mesh)
        hit = Hit(o, d, t, dist) || hit;
    return hit ? dist : -1.0f;
}

static bool Blocked(P3 const& o, P3 const& d, float length) { return Nearest(o, d, length) >= 0.0f; }

// The oracle: exact overlap of the body cylinder (knee to head) with the model.
static std::vector<P3> ClipZ(std::vector<P3> poly, float z, bool keepAbove)
{
    std::vector<P3> out;
    for (std::size_t i = 0; i < poly.size(); ++i)
    {
        P3 const p = poly[i], q = poly[(i + 1) % poly.size()];
        bool const pin = keepAbove ? p.z >= z : p.z <= z;
        bool const qin = keepAbove ? q.z >= z : q.z <= z;
        if (pin)
            out.push_back(p);
        if (pin != qin)
            out.push_back(p + (q - p) * ((z - p.z) / (q.z - p.z)));
    }
    return out;
}

static float PlanDistance(std::vector<P3> const& poly, float x, float y)
{
    int positive = 0, negative = 0;
    float best = 1e9f;
    for (std::size_t i = 0; i < poly.size(); ++i)
    {
        P3 const p = poly[i], q = poly[(i + 1) % poly.size()];
        float const ex = q.x - p.x, ey = q.y - p.y;
        float const cross = ex * (y - p.y) - ey * (x - p.x);
        positive += cross > 0.0f;
        negative += cross < 0.0f;
        float const lengthSq = ex * ex + ey * ey;
        float t = lengthSq > 0.0f ? ((x - p.x) * ex + (y - p.y) * ey) / lengthSq : 0.0f;
        t = std::clamp(t, 0.0f, 1.0f);
        best = std::min(best, std::hypot(p.x + ex * t - x, p.y + ey * t - y));
    }
    if (poly.size() >= 3 && (positive == 0 || negative == 0) && positive + negative > 0)
        return 0.0f;
    return best;
}

static float Overlap(P3 const& feet)
{
    float const low = feet.z + Body::KneeYards, high = feet.z + Height;
    float depth = 0.0f;
    for (Tri const& t : mesh)
    {
        if (t.hi.z < low || t.lo.z > high || t.hi.x < feet.x - Radius || t.lo.x > feet.x + Radius
            || t.hi.y < feet.y - Radius || t.lo.y > feet.y + Radius)
            continue;
        std::vector<P3> poly = ClipZ(ClipZ({ t.a, t.b, t.c }, low, true), high, false);
        if (poly.empty())
            continue;
        depth = std::max(depth, Radius - PlanDistance(poly, feet.x, feet.y));
    }
    return depth;
}

static float FloorAt(float x, float y, float z, float search)
{
    float const hit = Nearest({ x, y, z }, { 0.0f, 0.0f, -1.0f }, search);
    return hit < 0.0f ? -1000.0f : z - hit;
}

// The raise: the lowering reversed, from the lowered stop at t = 0.
static float RaiseOrigin(float ms) { return LoweringOriginZ(std::max(0.0f, StopChangeMs - ms)); }

static P3 LocalFeet(Vector3 const& world, float origin)
{
    LocalPoint const l = WorldToLocal(world);
    return { l.X, l.Y, world.Z - origin };
}

struct Replay
{
    bool Boarded = false;
    bool Missed = false;
    float MaxDepth = 0.0f;       // the oracle, every 5 ms until aboard
    float BoardDepth = 0.0f;
    int Decisions = 0;
    int SwimRefusals = 0;
    int EmergeRefusals = 0;
    std::string LastHold;
};

static Replay ReplayRaise(LocalPoint start, float startFeet, float gapSeconds, float startMs = 0.0f)
{
    AdaptiveNefarianStrategy strategy;
    NativeFacts swimmer;
    swimmer.PillarAscentSupported = true;
    Vector3 at = LocalToWorld(start, 0.0f, 0.0f);
    at.Z = startFeet;
    Vector3 target = at;
    float speed = 0.0f;
    Replay replay;
    float const stepMs = 5.0f;
    float const gapMs = gapSeconds * 1000.0f;
    float nextDecision = startMs;
    for (float t = startMs; t < startMs + 30000.0f; t += stepMs)
    {
        float const origin = RaiseOrigin(t);
        float const depth = Overlap(LocalFeet(at, origin));
        replay.MaxDepth = std::max(replay.MaxDepth, depth);
        if (origin >= PlatformFrame::RaisedOriginZ - 0.01f)
            break;
        if (t + 1e-3f >= nextDecision)
        {
            nextDecision += gapMs;
            ++replay.Decisions;
            Blackboard board = AscentBoard(origin);
            board.Summons.resize(1);
            FindPlayer(board, 1).Position = at;
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(1), "tank", &swimmer);
            replay.LastHold = std::string(HoldReason(plan.MovementHold));
            if (replay.LastHold == "nefarian_rising_floor_missed")
                replay.Missed = true;
            if (plan.Ascent && plan.Ascent->Stage == AscentStage::Board)
            {
                // ExecuteEmerge: the floor within the tolerance of the feet,
                // the body standing here clear (the ray proof).
                P3 const feet = LocalFeet(at, origin);
                float const floor = FloorAt(feet.x, feet.y, feet.z + plan.Ascent->FloorToleranceYards,
                    2.0f * plan.Ascent->FloorToleranceYards);
                std::uint32_t rays = 0;
                if (floor > -999.0f && Clear::BodyClearAt(feet, Radius, Height, Blocked, rays))
                {
                    replay.Boarded = true;
                    replay.BoardDepth = depth;
                    return replay;
                }
                ++replay.EmergeRefusals;
            }
            if (plan.Ascent && plan.Ascent->Stage == AscentStage::Swim)
            {
                // ExecuteSwim: the body proof at launch, in the frame now.
                Vector3 const to = plan.Ascent->World;
                if (Clear::ProveSwim(LocalFeet(at, origin), LocalFeet(to, origin), Radius, Height,
                        Blocked).Clear())
                {
                    target = to;
                    speed = plan.Ascent->SwimSpeedYardsPerSecond > 0.0f
                        ? plan.Ascent->SwimSpeedYardsPerSecond : SwimSpeedYardsPerSecond;
                }
                else
                {
                    ++replay.SwimRefusals;
                    target = at;
                    speed = 0.0f;
                }
            }
        }
        float const dx = target.X - at.X, dy = target.Y - at.Y, dz = target.Z - at.Z;
        float const left = std::sqrt(dx * dx + dy * dy + dz * dz);
        float const move = std::min(left, speed * stepMs / 1000.0f);
        if (left > 1e-5f)
            at = { at.X + dx * move / left, at.Y + dy * move / left, at.Z + dz * move / left };
    }
    return replay;
}

static void Print(char const* what, float r, float gap, Replay const& replay)
{
    std::printf("EMERGE %s r=%.2f gap=%.1f boarded=%d missed=%d max_depth=%.4f board_depth=%.4f "
        "decisions=%d swim_refusals=%d emerge_refusals=%d hold=%s\n", what, r, gap, replay.Boarded,
        replay.Missed, replay.MaxDepth, replay.BoardDepth, replay.Decisions, replay.SwimRefusals,
        replay.EmergeRefusals, replay.LastHold.c_str());
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    std::ifstream in(argv[1]);
    std::size_t count = 0;
    in >> count;
    mesh.resize(count);
    for (Tri& t : mesh)
    {
        in >> t.a.x >> t.a.y >> t.a.z >> t.b.x >> t.b.y >> t.b.z >> t.c.x >> t.c.y >> t.c.z;
        t.lo = { std::min({ t.a.x, t.b.x, t.c.x }), std::min({ t.a.y, t.b.y, t.c.y }), std::min({ t.a.z, t.b.z, t.c.z }) };
        t.hi = { std::max({ t.a.x, t.b.x, t.c.x }), std::max({ t.a.y, t.b.y, t.c.y }), std::max({ t.a.z, t.b.z, t.c.z }) };
    }
    CHECK(count > 100, "the model");
    float const floatFeet = MagmaSurfaceZ - FloatDepthYards;

    // 1. Every station, from the raise start, at native and slow cadences.
    int stationRuns = 0, stationClean = 0;
    for (uint8 pillar = 0; pillar < 3; ++pillar)
        for (uint8 slot = 0; slot < 6; ++slot)
            for (float gap : { 0.1f, 0.5f, 1.0f })
            {
                Replay const replay = ReplayRaise(PillarRadial(pillar, slot, SwimStationRadius), floatFeet, gap);
                ++stationRuns;
                bool const clean = replay.Boarded && replay.MaxDepth <= 1e-4f;
                stationClean += clean;
                if (!clean)
                    Print("station", SwimStationRadius, gap, replay);
                CHECK(clean, "a swimmer at its station boards the rising ring with its body clear");
            }
    std::printf("EMERGE stations runs=%d clean=%d\n", stationRuns, stationClean);

    // 2. The open floor: ring, ramp and centre, from the float depth.
    for (LocalPoint const at : { Polar(DegToRad(60.0f), 40.0f), Polar(DegToRad(60.0f), 27.0f),
            Polar(DegToRad(60.0f), 12.0f) })
        for (float gap : { 0.1f, 0.5f, 0.8f, 1.0f, 1.2f })
        {
            Replay const replay = ReplayRaise(at, floatFeet, gap);
            Print("open", Length(at), gap, replay);
            CHECK(replay.Boarded && replay.MaxDepth <= 1e-4f, "the open floor boards clear");
        }

    // 3. Beside a rising pillar, just outside its skirt (radius 6.1-6.5 on
    // several headings): before the fix the ride boarded there with the skirt
    // inside the body; now the swimmer moves out first.
    // Pillar 2 at 305 degrees is where the model's skirt reaches farthest.
    int besideRuns = 0, besideClean = 0;
    for (uint8 pillar = 0; pillar < 3; ++pillar)
        for (float heading : { 0.0f, 60.0f, 125.0f, 180.0f, 245.0f, 305.0f })
            for (float r : { 6.1f, 6.3f, 6.5f })
                for (float gap : { 0.1f, 0.5f, 1.0f })
                {
                    Replay const replay = ReplayRaise(Offset(PillarCenters[pillar], DegToRad(heading), r),
                        floatFeet, gap);
                    ++besideRuns;
                    bool const clean = replay.Boarded && replay.MaxDepth <= 1e-4f;
                    besideClean += clean;
                    if (!clean)
                        Print("beside", r, gap, replay);
                    CHECK(clean, "a swimmer beside a pillar moves clear and boards with its body clear");
                }
    std::printf("EMERGE beside runs=%d clean=%d\n", besideRuns, besideClean);

    // 4. The surface boundary of the earlier re-reviews: feet at the surface
    // limit, the floor 0.46 under them and rising.
    for (LocalPoint const at : { Polar(DegToRad(60.0f), 40.0f), Polar(DegToRad(60.0f), 27.0f),
            Polar(DegToRad(60.0f), 12.0f) })
        for (float gap : { 0.1f, 0.5f, 0.8f, 1.0f, 1.2f })
        {
            float const feet = MagmaSurfaceZ - 0.05f;
            float const startMs = StopChangeMs - LoweringReachesMs(FloorLocalZAt(at), feet - 0.46f);
            Replay const replay = ReplayRaise(at, feet, gap, startMs);
            Print("surface", Length(at), gap, replay);
            CHECK(replay.Boarded == !replay.Missed, "it boards or reports the typed miss");
            if (replay.Boarded)
                CHECK(replay.MaxDepth <= 1e-4f, "a boarded swimmer never had the floor in its body");
            if (gap <= 0.5f)
                CHECK(replay.Boarded, "at the native combat cadence it boards");
        }

    // 4b. A late swimmer at the float depth that the floor reaches soon
    // (it floated late, or missed its hop): the ride has little room under
    // the surface. Before the round-3 fix it rode at the fixed closing
    // speed, reached the surface first and was left with the 0.7 s band of
    // the full rise; now it closes fast enough to meet the band below it.
    int lateRuns = 0, lateClean = 0;
    for (LocalPoint const at : { Polar(DegToRad(60.0f), 40.0f), Polar(DegToRad(60.0f), 27.0f),
            Polar(DegToRad(60.0f), 12.0f), PillarRadial(0, 0, SwimStationRadius) })
        for (float below : { 2.0f, 1.6f, 1.2f })
            for (float gap : { 0.1f, 0.5f, 0.8f, 1.0f })
            {
                float const startMs = StopChangeMs - LoweringReachesMs(FloorLocalZAt(at), floatFeet - below);
                Replay const replay = ReplayRaise(at, floatFeet, gap, startMs);
                ++lateRuns;
                bool const clean = replay.Boarded && replay.MaxDepth <= 1e-4f;
                lateClean += clean;
                Print("late", Length(at), gap, replay);
                std::printf("EMERGE late_case below=%.1f gap=%.1f clean=%d\n", below, gap, clean);
                CHECK(clean || gap > 0.5f, "at the native combat cadence the late swimmer boards clear");
                CHECK(replay.Boarded != replay.Missed, "it boards or reports the typed miss");
            }
    std::printf("EMERGE late runs=%d clean=%d\n", lateRuns, lateClean);

    // 5. Negative controls. The old ride gate (nearest > PillarSkirtRadius)
    // admitted a swimmer 6.1 yards from pillar 2 at 305 degrees; boarding in
    // the lower part of the band there puts the skirt inside the body. The
    // executor's Emerge now refuses every such height (and admits the rest).
    {
        LocalPoint const beside = Offset(PillarCenters[2], DegToRad(305.0f), 6.1f);
        float nearest = 0.0f;
        NearestPillar(beside, nearest);
        CHECK(nearest > PillarSkirtRadius && nearest <= RisingFloorPillarClearRadius,
            "the old gate admitted the ride here; the new one does not");
        float worst = 0.0f;
        int overlapping = 0, refused = 0, unsound = 0, bands = 0;
        for (float gap = RisingFloorBoardMinYards; gap <= RisingFloorBoardMaxYards + 1e-3f; gap += 0.05f)
        {
            P3 const feet{ beside.X, beside.Y, RingLocalZ + gap };
            float const depth = Overlap(feet);
            worst = std::max(worst, depth);
            std::uint32_t rays = 0;
            bool const clear = Clear::BodyClearAt(feet, Radius, Height, Blocked, rays);
            overlapping += depth > 1e-4f;
            refused += !clear;
            unsound += clear && depth > 1e-4f;
            ++bands;
        }
        std::printf("EMERGE control beside=6.1 max_band_overlap=%.4f overlapping=%d executor_refused=%d "
            "unsound=%d bands=%d\n", worst, overlapping, refused, unsound, bands);
        CHECK(worst > 0.2f && overlapping > 0 && unsound == 0,
            "the band beside the skirt reaches into the body, and the executor refuses it");
        // And the open ring is not refused (the check is not a blanket refusal).
        LocalPoint const open = PillarRadial(1, 2, SwimStationRadius);
        std::uint32_t rays = 0;
        CHECK(Clear::BodyClearAt(P3{ open.X, open.Y, RingLocalZ - 0.3f }, Radius, Height, Blocked, rays)
            && Overlap(P3{ open.X, open.Y, RingLocalZ - 0.3f }) <= 1e-4f, "the station boards");
    }
    // 6. The strategy's own gates. At the lowered stop a swimmer within the
    // station tolerance but nearer the pillar than the hop gate swims out to
    // its station first (the body proof refuses a hop from there), and one
    // at the gate hops. During the raise a swimmer beside a pillar swims
    // straight out to the station radius.
    {
        DutyPlan const duty = BuildNefarianDutyPlan(CanonicalBoard());
        uint8 const pillar = uint8(duty.PillarOf(Bot(1)));
        uint8 const slot = duty.SlotOf(Bot(1));
        NativeFacts swimmer;
        swimmer.PillarAscentSupported = true;
        AdaptiveNefarianStrategy strategy;
        auto stageAt = [&](float radius, float origin, Vector3* world)
        {
            Blackboard board = AscentBoard(origin);
            if (origin != PlatformFrame::LoweredOriginZ)
                board.Summons.resize(1);
            Vector3 at = LocalToWorld(PillarRadial(pillar, slot, radius), 0.0f, 0.0f);
            at.Z = floatFeet;
            FindPlayer(board, 1).Position = at;
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(1), "tank", &swimmer);
            if (world && plan.Ascent)
                *world = plan.Ascent->World;
            return plan.Ascent ? int(plan.Ascent->Stage) : -1;
        };
        int const inner = stageAt(SwimStationRadius - 0.5f, PlatformFrame::LoweredOriginZ, nullptr);
        int const gate = stageAt(SwimStationRadius - 0.2f, PlatformFrame::LoweredOriginZ, nullptr);
        Vector3 out{};
        int const beside = stageAt(6.1f, PlatformFrame::LoweredOriginZ + 1.0f, &out);
        float const outRadius = Distance(WorldToLocal(out), PillarCenters[pillar]);
        std::printf("EMERGE gates inner=%d gate=%d beside=%d out_radius=%.3f\n", inner, gate, beside, outRadius);
        CHECK(inner == int(AscentStage::Swim) && gate == int(AscentStage::Hop),
            "the hop leaves from no nearer the pillar than the gate");
        CHECK(beside == int(AscentStage::Swim) && Near(outRadius, SwimStationRadius, 0.01f),
            "beside a rising pillar: straight out to the station radius");
    }
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run_strict(tmp_path: Path, program: str) -> str:
    source = tmp_path / "emerge.cpp"
    binary = tmp_path / "emerge"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-O2", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary), str(_triangles_file(tmp_path))], cwd=ROOT, capture_output=True,
                         text=True, timeout=1800)
    if os.environ.get("LIQUID_CLEARANCE_VERBOSE"):
        print(run.stdout)
        print(run.stderr)
    assert run.returncode == 0, run.stdout + run.stderr[-6000:]
    return run.stdout


@pytest.fixture(scope="module")
def emerge(tmp_path_factory: pytest.TempPathFactory) -> str:
    vmo._model()
    return _compile_and_run_strict(tmp_path_factory.mktemp("liquid_emerge"), EMERGE)


def test_the_rising_platform_never_passes_through_a_swimmer(emerge: str) -> None:
    """Every station, the open floor and every spot beside a pillar board the
    rising platform with the body clear at every 5 ms, at every cadence."""
    stations = re.search(r"EMERGE stations runs=(\d+) clean=(\d+)", emerge)
    assert stations and stations.group(1) == stations.group(2) == "54", emerge
    beside = re.search(r"EMERGE beside runs=(\d+) clean=(\d+)", emerge)
    assert beside and beside.group(1) == beside.group(2) == "162", emerge
    opened = re.findall(r"EMERGE open .*", emerge)
    assert len(opened) == 15 and all("boarded=1" in line and "max_depth=0.0000" in line for line in opened), emerge
    for line in re.findall(r"EMERGE (?:surface|late) r=.*", emerge):
        if "boarded=1" in line:
            assert "max_depth=0.0000" in line, line
    assert "failures=0" in emerge, emerge


def test_a_late_swimmer_rides_to_the_band_before_the_surface(emerge: str) -> None:
    """Round 3: with the floor under 2 yards below a swimmer at the float depth
    the fixed-speed ride reached the surface first; a late decision then let
    the floor pass through the body (44 of these 48 replays clean before the
    fix, typed misses at 0.8-1.0 s cadences). Now every one at the native
    combat cadence boards clear, and more at the slow ones."""
    late = re.search(r"EMERGE late runs=(\d+) clean=(\d+)", emerge)
    assert late and int(late.group(1)) == 48 and int(late.group(2)) >= 46, emerge
    for below, gap, clean in re.findall(r"EMERGE late_case below=(\S+) gap=(\S+) clean=(\d)", emerge):
        if float(gap) <= 0.5:
            assert clean == "1", (below, gap)


def test_emerge_refuses_a_body_the_rising_skirt_already_reached(emerge: str) -> None:
    control = re.search(r"EMERGE control beside=6.1 max_band_overlap=(\S+) overlapping=(\d+) "
                        r"executor_refused=(\d+) unsound=(\d+)", emerge)
    assert control and float(control.group(1)) > 0.2 and int(control.group(2)) > 0, emerge
    assert int(control.group(4)) == 0, emerge


def test_the_strategy_hops_from_the_gate_and_moves_clear_of_a_rising_pillar(emerge: str) -> None:
    # AscentStage: Float 0, Swim 1, Hop 2, Board 3.
    gates = re.search(r"EMERGE gates inner=(-?\d+) gate=(-?\d+) beside=(-?\d+) out_radius=(\S+)", emerge)
    assert gates and gates.groups()[:3] == ("1", "2", "1"), emerge
    assert abs(float(gates.group(4)) - 6.7) < 0.01, emerge


def _code(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_the_liquid_executor_proves_the_whole_body_before_every_launch() -> None:
    code = _code(EXECUTOR)
    assert "SweepClear(" not in code, "the centre-line sweep is gone"
    query = code[code.index("struct BodyQuery"):code.index("float BodyRadius(")]
    assert "LINEOFSIGHT_ALL_CHECKS" in query and "Transport->m_model->intersectRay(" in query
    swim = code[code.index("Outcome ExecuteSwim("):code.index("Outcome ExecuteHop(")]
    order = [swim.index("native_liquid_swim_leaves_liquid"), swim.index("Clear::ProveSwim(from, to,"),
             swim.index("return Outcome::Retryable(Clear::SwimBodyObstructedReason);"),
             swim.index("LaunchMoveSpline(")]
    assert order == sorted(order)
    # A running swim to the same point at the same speed is not re-proven.
    assert swim.index('"native_liquid_swim_in_progress"') < swim.index("Clear::ProveSwim(")
    hop = code[code.index("Outcome ExecuteHop("):code.index("Outcome ExecuteEmerge(")]
    order = [hop.index("if (!Boarding::TransportStationaryMs(transport))"),
             hop.index("Clear::ChooseClearHop("), hop.index("Clear::ProveHop(from, landing, jump, radius,"),
             hop.index("return Outcome::Retryable(choice.Reason);"),
             hop.index("MoveJumpWithGravity(")]
    assert order == sorted(order)
    assert "(end - to).length() <= Clear::MaxLandingShiftYards" in hop
    emerge = code[code.index("Outcome ExecuteEmerge("):code.index("namespace BotTransportLiquidMovement")]
    order = [emerge.index("Clear::BodyClearAt("),
             emerge.index("return Outcome::Retryable(Clear::EmergeBodyObstructedReason);"),
             emerge.index("ReportSwimState(bot, submerged, transport)")]
    assert order == sorted(order)
    dispatch = code[code.index("BotActionArbitration::Outcome Execute("):]
    assert "ExecuteSwim(bot, transport, action)" in dispatch
    assert 'Outcome::Unsafe("native_liquid_transport_invalid")' in dispatch
    for path in (EXECUTOR, CLEARANCE, ASCENT):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path
    header = CLEARANCE.read_text(encoding="utf-8")
    assert re.findall(r'#include [<"]([^>"]+)[>"]', header) == [
        "Bots/BotValidationRouteNativeLiquid.h", "Movement/Spline/PassengerBodyTrajectory.h",
        "cmath", "cstddef", "cstdint", "string", "vector"]

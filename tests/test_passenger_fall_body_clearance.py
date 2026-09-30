"""A native fall off a Nefarian pillar keeps the whole body out of the model.

Round-3 v2 runtime review (P2, packet fall_clearance): LaunchFallOnto falls
straight down with the Falling flag, which MoveSplineInit's passenger sweep
exempts, and the step-off's landing proof checked only the floor under the
body's centre. On the elevator's own collision model (GO 207834, the vmo port
of tests/test_nefarian_ledge_drop_floor_query.py) the canonical pillar-1
slot-2 descent from the rim (radius 5, local z 9.3205) was admitted at the
first one-yard step: the centre lands on the ring (1.439) while the pillar
skirt stands at 2.106 0.38 yd from the axis, inside the 0.389 yd body.

Now (Movement/Spline/PassengerBodyTrajectory.h, Bots/BotLedgeDropBodyClearance.h)
the step-off proves the fall of the body cylinder (knee to head, full radius)
and its landing footprint, moves on to a candidate farther out when anything
is in the way, and refuses with ledge_drop_fall_body_obstructed when none is
clear; MoveSplineInit proves every player passenger's Falling or Parabolic
spline, sampled as the REAL Movement::MoveSpline runs it, the same way.

The oracle here is independent of the rays: the exact overlap of the body
cylinder with every model triangle (each triangle clipped to the knee-head
slab, its distance from the axis in plan), at every 5 ms of the real fall
spline and at its end.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests import test_nefarian_ledge_drop_floor_query as vmo
from tests.test_bot_native_fall_spline_state import STUB_CREATURE, STUB_LOG
from tests.test_nefarian_strategy import INCLUDES
from tests.test_passenger_spline_collision import _triangles_file


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
SPLINE = GAME / "Movement/Spline"
TRAJECTORY = SPLINE / "PassengerBodyTrajectory.h"
CHOOSER = GAME / "Bots/BotLedgeDropBodyClearance.h"
LAUNCH = SPLINE / "MoveSplineInit.cpp"
EXECUTOR = GAME / "Bots/BotWorldPopulationMgrNativePathTransportSurface.cpp"

PROGRAM = r'''
#include "Movement/Spline/PassengerBodyTrajectory.h"
#include "Bots/BotLedgeDropBodyClearance.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMagma.h"
#include "MoveSpline.h"
#include "MoveSplineInitArgs.h"

#include <G3D/Matrix4.h>
#include <G3D/Vector3.h>
#include <G3D/Vector4.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <fstream>
#include <string>
#include <vector>

namespace Trinity
{
void Assert(char const*, int, char const*, char const*) { std::abort(); }
void Assert(char const*, int, char const*, char const*, char const*, ...) { std::abort(); }
void Abort(char const*, int, char const*) { std::abort(); }
void Abort(char const*, int, char const*, char const*, ...) { std::abort(); }
}
// Built at static initialization by Spline.cpp; a linear fall never
// evaluates them (tests/test_passenger_spline_trajectory.py compiles G3D's
// own bodies where it does).
G3D::Matrix4::Matrix4(float, float, float, float, float, float, float, float,
    float, float, float, float, float, float, float, float) { }
G3D::Vector4 G3D::Vector4::operator*(const G3D::Matrix4&) const { return Vector4(); }
std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using G3D::Vector3;
namespace Body = Movement::BodyTrajectory;
namespace Route = BotValidationRouteNative;
namespace Clear = BotLedgeDropBodyClearance;
namespace Nef = BotEncounter::Nefarian;

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

struct Tri { Vector3 a, b, c; Vector3 lo, hi; };
static std::vector<Tri> mesh;
static long rays = 0;

// WorldModel IntersectTriangle, two-sided.
static bool TriangleHit(Vector3 const& o, Vector3 const& d, Tri const& t, float& dist)
{
    Vector3 const e1 = t.b - t.a, e2 = t.c - t.a, p = d.cross(e2);
    float const det = e1.dot(p);
    if (std::fabs(det) < 1e-5f)
        return false;
    float const f = 1.0f / det;
    Vector3 const s = o - t.a;
    float const u = f * s.dot(p);
    if (u < 0.0f || u > 1.0f)
        return false;
    Vector3 const q = s.cross(e1);
    float const v = f * d.dot(q);
    if (v < 0.0f || u + v > 1.0f)
        return false;
    float const hit = f * e2.dot(q);
    if (hit > 0.0f && hit < dist)
    {
        dist = hit;
        return true;
    }
    return false;
}

static float Nearest(Vector3 const& o, Vector3 const& d, float maxDistance)
{
    ++rays;
    float dist = maxDistance;
    bool hit = false;
    for (Tri const& t : mesh)
        hit = TriangleHit(o, d, t, dist) || hit;
    return hit ? dist : -1.0f;
}

static bool Blocked(Vector3 const& o, Vector3 const& d, float length) { return Nearest(o, d, length) >= 0.0f; }

// Map::GetHeight's model part: the nearest surface under (x, y, z) within `search`.
static bool FloorBelow(float x, float y, float z, float search, float& floor)
{
    float const hit = Nearest(Vector3(x, y, z), Vector3(0, 0, -1), search);
    if (hit < 0.0f)
        return false;
    floor = z - hit;
    return true;
}

static float const Radius = 0.389f;
static float const Height = 2.0313f; // a human male's collision height
static float const Tolerance = 0.6f; // FloorToleranceYards of the descent

// ---- The oracle: exact overlap of the body cylinder (axis at feet.xy,
// knee to head) with the model. Each triangle is clipped to the slab and its
// plan distance from the axis compared with the radius.
static std::vector<Vector3> ClipZ(std::vector<Vector3> poly, float z, bool keepAbove)
{
    std::vector<Vector3> out;
    for (std::size_t i = 0; i < poly.size(); ++i)
    {
        Vector3 const p = poly[i], q = poly[(i + 1) % poly.size()];
        bool const pin = keepAbove ? p.z >= z : p.z <= z;
        bool const qin = keepAbove ? q.z >= z : q.z <= z;
        if (pin)
            out.push_back(p);
        if (pin != qin)
            out.push_back(p + (q - p) * ((z - p.z) / (q.z - p.z)));
    }
    return out;
}

static float PlanDistance(std::vector<Vector3> const& poly, float x, float y)
{
    // Inside the projected polygon (same side of every edge)?
    int positive = 0, negative = 0;
    float best = 1e9f;
    for (std::size_t i = 0; i < poly.size(); ++i)
    {
        Vector3 const p = poly[i], q = poly[(i + 1) % poly.size()];
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

static float Overlap(Vector3 const& feet, std::vector<Tri const*> const& near)
{
    float const low = feet.z + Body::KneeYards, high = feet.z + Height;
    float depth = 0.0f;
    for (Tri const* t : near)
    {
        if (t->hi.z < low || t->lo.z > high)
            continue;
        std::vector<Vector3> poly = ClipZ(ClipZ({ t->a, t->b, t->c }, low, true), high, false);
        if (poly.empty())
            continue;
        depth = std::max(depth, Radius - PlanDistance(poly, feet.x, feet.y));
    }
    return depth;
}

static std::vector<Tri const*> Near(float x, float y, float low, float high)
{
    std::vector<Tri const*> near;
    for (Tri const& t : mesh)
        if (t.hi.x >= x - Radius && t.lo.x <= x + Radius && t.hi.y >= y - Radius && t.lo.y <= y + Radius
            && t.hi.z >= low && t.lo.z <= high)
            near.push_back(&t);
    return near;
}

// ---- The real fall spline MotionMaster::MoveFall / LaunchFallOnto emits.
static Movement::MoveSplineInitArgs FallArgs(Vector3 const& from, float floorZ)
{
    Movement::MoveSplineInitArgs args;
    args.path = { from, Vector3(from.x, from.y, floorZ) };
    args.velocity = 7.0f;
    args.flags.Falling = true; // MoveSplineInit::SetFall
    return args;
}

struct FallCheck { float Depth = 0.0f; int FirstOverlapMs = -1; float EndZ = 0.0f; int Samples = 0; };

static FallCheck OracleFall(Vector3 const& from, float floorZ)
{
    Movement::MoveSpline spline;
    spline.Initialize(FallArgs(from, floorZ));
    std::vector<Tri const*> const near = Near(from.x, from.y, floorZ - 1.0f, from.z + Height + 1.0f);
    FallCheck check;
    for (int32 t = 0;; t += 5)
    {
        int32 const at = std::min(t, spline.Duration());
        Movement::Location const p = spline.ComputePosition(at);
        float const depth = Overlap(Vector3(p.x, p.y, p.z), near);
        if (depth > 1e-4f && check.FirstOverlapMs < 0)
            check.FirstOverlapMs = at;
        check.Depth = std::max(check.Depth, depth);
        check.EndZ = p.z;
        ++check.Samples;
        if (at == spline.Duration())
            break;
    }
    return check;
}

// ---- ProbeLedgeDrop on the model (the executor's own probe, point for point).
static Route::ApproachContract Contract()
{
    Route::ApproachContract drop;
    drop.Mode = Route::ApproachMode::LedgeDrop;
    drop.LandingZ = Nef::RingLocalZ;
    drop.LandingToleranceYards = 1.0f;
    drop.LandOnTransport = true;
    drop.MinHealthAfterFallPct = 0.2f;
    return drop;
}

static bool FloorWithin(float x, float y, float z, float tolerance)
{
    float floor;
    return FloorBelow(x, y, z + tolerance, 2.0f * tolerance, floor);
}

static Route::LedgeDropProbe ProbeLedgeDrop(Vector3 const& from, Vector3 const& stepOff)
{
    Route::LedgeDropProbe probe;
    float const length = std::hypot(stepOff.x - from.x, stepOff.y - from.y);
    uint32 const steps = std::max<uint32>(1, uint32(std::ceil(length / Route::SurfaceSampleStepYards)));
    for (uint32 i = 0; i <= steps; ++i)
    {
        float const t = float(i) / float(steps);
        Vector3 const p = from + (stepOff - from) * t;
        Route::SurfaceSample sample;
        sample.Along = length * t;
        sample.TransportFloor = FloorWithin(p.x, p.y, p.z, Tolerance);
        float below;
        if (!sample.Supported())
            sample.ShallowFloorBelow = FloorBelow(p.x, p.y, p.z, Route::MinLedgeDropYards, below)
                && below > p.z - Route::MinLedgeDropYards;
        probe.Step.push_back(sample);
    }
    probe.StepLengthYards = length;
    probe.StepZ = stepOff.z;
    // BodySweepClear: centre, half and full radius both sides, knee to 0.9 height.
    float const sx = length > 0.0f ? -(stepOff.y - from.y) / length * Radius : 0.0f;
    float const sy = length > 0.0f ? (stepOff.x - from.x) / length * Radius : 0.0f;
    probe.StepCollisionFree = true;
    for (float const lift : Route::BodySweepLifts(Height))
        for (float const side : Route::BodySweepSideFractions)
        {
            Vector3 const a(from.x + side * sx, from.y + side * sy, from.z + lift);
            Vector3 const b(stepOff.x + side * sx, stepOff.y + side * sy, stepOff.z + lift);
            if (Blocked(a, (b - a).direction(), (b - a).length()))
                probe.StepCollisionFree = false;
        }
    for (int i = -1; i < 8; ++i)
    {
        float const angle = float(i) * 3.14159265f / 4.0f;
        float const x = stepOff.x + (i < 0 ? 0.0f : Radius * std::cos(angle));
        float const y = stepOff.y + (i < 0 ? 0.0f : Radius * std::sin(angle));
        float floor;
        if (FloorBelow(x, y, stepOff.z + Tolerance, Tolerance + Route::MinLedgeDropYards, floor)
            && floor > stepOff.z - Route::MinLedgeDropYards)
            ++probe.FootprintSupported;
    }
    // The bounded landing query (LedgeDropLandingSearchYards) from 1.5 yd up.
    float const search = 1.5f + std::max(0.0f, stepOff.z - Nef::RingLocalZ) + 1.0f;
    probe.LandingFound = FloorBelow(stepOff.x, stepOff.y, stepOff.z + 1.5f, search, probe.LandingZ);
    probe.LandingOnTransport = probe.LandingFound;
    probe.HealthPct = 1.0f;
    return probe;
}

// ---- ProbeFallBody on the model (model only: the elevator has no static
// geometry around the pillar).
static Clear::FallBodyProbe ProbeFallBody(Vector3 const& start, float landingZ)
{
    Clear::FallBodyProbe probe;
    Body::Body const body = Body::MakeBody(Radius, Height);
    Body::Proof const proof = Body::ProveTrajectory(std::vector<Vector3>{ start,
        Vector3(start.x, start.y, landingZ) }, body, Blocked);
    probe.Rays = proof.Rays;
    probe.LandingClear = proof.Kind != Body::Obstruction::Landing;
    probe.PathClear = proof.Kind != Body::Obstruction::Path && probe.LandingClear;
    for (int k = 0; k < Body::InnerDirections; ++k)
    {
        float const angle = 6.28318531f * float(k) / float(Body::InnerDirections);
        ++probe.InnerPoints;
        probe.InnerSupported += FloorWithin(start.x + 0.5f * body.Radius * std::cos(angle),
            start.y + 0.5f * body.Radius * std::sin(angle), landingZ, Tolerance);
    }
    return probe;
}

struct Descent { Vector3 Rim; float Heading; };

static Descent RimOf(int pillar, int slot)
{
    float const heading = Nef::PillarSlotHeading(uint8(pillar), uint8(slot));
    Nef::LocalPoint const rim = Nef::Offset(Nef::PillarCenters[pillar], heading, Nef::DescentRimRadius);
    float const z = Nef::PlatformFrame::PillarTopLocalZ
        - Nef::PillarRimSlope * (Nef::DescentRimRadius - Nef::SlotProfile(uint8(pillar), uint8(slot)).FlatRadius);
    return { Vector3(rim.X, rim.Y, z), heading };
}

static Vector3 At(Descent const& d, float step)
{
    return Vector3(d.Rim.x + std::cos(d.Heading) * step, d.Rim.y + std::sin(d.Heading) * step, d.Rim.z);
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
        t.lo = t.a.min(t.b).min(t.c);
        t.hi = t.a.max(t.b).max(t.c);
    }
    CHECK(count > 100);
    Route::ApproachContract const drop = Contract();

    // 1. The review's reproduction: pillar 1, slot 2, from the rim.
    Descent const review = RimOf(1, 2);
    std::printf("review rim local=(%.4f, %.4f, %.4f)\n", review.Rim.x, review.Rim.y, review.Rim.z);
    CHECK(std::fabs(review.Rim.z - 9.3205f) < 1e-3f);
    auto probeAt = [](Descent const& d) { return [&d](float step) { return ProbeLedgeDrop(d.Rim, At(d, step)); }; };
    auto bodyAt = [](Descent const& d)
    {
        return [&d](float step, Route::LedgeDropProbe const& probe) { return ProbeFallBody(At(d, step), probe.LandingZ); };
    };
    {
        // Before: the centre's floor alone admits the first yard.
        Route::StepOffChoice const before = Route::ChooseStepOff(drop, probeAt(review));
        Vector3 const off = At(review, before.StepYards);
        Route::LedgeDropProbe const probe = ProbeLedgeDrop(review.Rim, off);
        FallCheck const fall = OracleFall(off, probe.LandingZ);
        std::printf("before ok=%d reason=%s step=%.2f dest=(%.6f, %.6f) landing=%.6f overlap=%.3f first_overlap_ms=%d end_z=%.6f\n",
            before.Verdict.Ok, before.Verdict.Reason.c_str(), before.StepYards, off.x, off.y, probe.LandingZ,
            fall.Depth, fall.FirstOverlapMs, fall.EndZ);
        CHECK(before.Verdict.Ok && std::fabs(before.StepYards - 1.0f) < 1e-3f);
        CHECK(fall.Depth > 0.05f);
        // The body proof sees it (the skirt inside the radius at the landing).
        Clear::FallBodyProbe const body = ProbeFallBody(off, probe.LandingZ);
        CHECK(!body.LandingClear);
        CHECK(Clear::ValidateFallBody(body).Reason == Clear::BodyObstructedReason);
        // The skirt 0.38 yd from the axis toward the pillar, above the knee.
        Vector3 const inward(off.x - 0.38f * std::cos(review.Heading), off.y - 0.38f * std::sin(review.Heading), 0);
        float skirt = 0.0f;
        CHECK(FloorBelow(inward.x, inward.y, 5.0f, 5.0f, skirt));
        std::printf("skirt_at_0.38=%.3f knee=%.3f\n", skirt, probe.LandingZ + Body::KneeYards);
        CHECK(skirt > probe.LandingZ + Body::KneeYards);
    }
    {
        // After: the first candidate whose whole fall is clear, farther out.
        Clear::Choice const after = Clear::ChooseClearStepOff(drop, probeAt(review), bodyAt(review));
        Vector3 const off = At(review, after.Step.StepYards);
        Route::LedgeDropProbe const probe = ProbeLedgeDrop(review.Rim, off);
        FallCheck const fall = OracleFall(off, probe.LandingZ);
        std::printf("after ok=%d step=%.2f landing=%.4f overlap=%.4f samples=%d end_z=%.4f body_proofs=%u rays=%u\n",
            after.Step.Verdict.Ok, after.Step.StepYards, probe.LandingZ, fall.Depth, fall.Samples, fall.EndZ,
            after.BodyProofs, after.Rays);
        CHECK(after.Step.Verdict.Ok && after.Step.StepYards > 1.0f);
        CHECK(fall.Depth <= 1e-4f);
        // The spline stops within its last millisecond of the floor (the
        // review's 1.455430 over 1.438741), inside the proved column.
        CHECK(fall.EndZ >= probe.LandingZ && fall.EndZ - probe.LandingZ < 0.05f);
    }
    // 2. Positive control: the declared step-off (radius 7) falls clear.
    {
        Vector3 const off = At(review, Nef::DescentStepOffRadius - Nef::DescentRimRadius);
        Route::LedgeDropProbe const probe = ProbeLedgeDrop(review.Rim, off);
        CHECK(Route::ValidateLedgeDrop(drop, probe).Ok);
        Clear::FallBodyProbe const body = ProbeFallBody(off, probe.LandingZ);
        CHECK(Clear::ValidateFallBody(body).Ok);
        CHECK(OracleFall(off, probe.LandingZ).Depth <= 1e-4f);
        std::printf("control rays=%u inner=%u/%u\n", body.Rays, body.InnerSupported, body.InnerPoints);
    }

    // 3. Every pillar, slot and candidate: whatever the proof admits falls
    // with zero overlap at every sample and at the landing; every choice too.
    int candidates = 0, proved = 0, overlapping = 0, unsound = 0, conservative = 0;
    int admittedBefore = 0, overlappingBefore = 0, admitted = 0, refused = 0;
    uint32 maxRays = 0;
    double proofMs = 0.0;
    for (int pillar = 0; pillar < 3; ++pillar)
        for (int slot = 0; slot < 6; ++slot)
        {
            Descent const d = RimOf(pillar, slot);
            for (float step = Route::SurfaceSampleStepYards; step <= Route::MaxStepOffYards + 1e-3f;
                step += Route::SurfaceSampleStepYards)
            {
                Vector3 const off = At(d, step);
                Route::LedgeDropProbe const probe = ProbeLedgeDrop(d.Rim, off);
                if (!probe.LandingFound)
                    continue;
                ++candidates;
                long const before = rays;
                auto const t0 = std::chrono::steady_clock::now();
                Clear::FallBodyProbe const body = ProbeFallBody(off, probe.LandingZ);
                proofMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
                CHECK(long(body.Rays) == rays - before - long(body.InnerPoints));
                maxRays = std::max(maxRays, body.Rays);
                bool const clear = body.PathClear && body.LandingClear;
                FallCheck const fall = OracleFall(off, probe.LandingZ);
                bool const overlap = fall.Depth > 1e-4f;
                overlapping += overlap;
                proved += clear;
                if (clear && overlap)
                {
                    ++unsound;
                    std::fprintf(stderr, "UNSOUND pillar=%d slot=%d step=%.2f depth=%.4f\n", pillar, slot, step, fall.Depth);
                }
                conservative += !clear && !overlap;
            }
            Route::StepOffChoice const before = Route::ChooseStepOff(drop, probeAt(d));
            if (before.Verdict.Ok)
            {
                ++admittedBefore;
                Vector3 const off = At(d, before.StepYards);
                overlappingBefore += OracleFall(off, ProbeLedgeDrop(d.Rim, off).LandingZ).Depth > 1e-4f;
            }
            Clear::Choice const after = Clear::ChooseClearStepOff(drop, probeAt(d), bodyAt(d));
            if (after.Step.Verdict.Ok)
            {
                ++admitted;
                Vector3 const off = At(d, after.Step.StepYards);
                Route::LedgeDropProbe const probe = ProbeLedgeDrop(d.Rim, off);
                FallCheck const fall = OracleFall(off, probe.LandingZ);
                CHECK(fall.Depth <= 1e-4f);
                CHECK(Clear::ValidateFallBody(ProbeFallBody(off, probe.LandingZ)).Ok);
                std::printf("choice pillar=%d slot=%d before=%.2f after=%.2f landing=%.3f\n", pillar, slot,
                    before.Verdict.Ok ? before.StepYards : -1.0f, after.Step.StepYards, probe.LandingZ);
            }
            else
            {
                ++refused;
                std::printf("refused pillar=%d slot=%d reason=%s\n", pillar, slot, after.Step.Verdict.Reason.c_str());
                CHECK(!after.Step.Verdict.Reason.empty());
            }
        }
    std::printf("sweep candidates=%d proved=%d overlapping=%d unsound=%d conservative=%d max_rays=%u mean_proof_ms=%.3f\n",
        candidates, proved, overlapping, unsound, conservative, maxRays, candidates ? proofMs / candidates : 0.0);
    std::printf("choices before_admitted=%d before_overlapping=%d after_admitted=%d after_refused=%d\n",
        admittedBefore, overlappingBefore, admitted, refused);
    CHECK(candidates >= 18 * 8);
    CHECK(unsound == 0);
    CHECK(overlapping > 0 && overlappingBefore > 0);
    CHECK(admitted + refused == 18);

    // 4. MoveSplineInit's proof of the effect spline as the server runs it:
    // sampled, reduced to one exact vertical chord, the review's fall refused
    // and the chosen one launched.
    {
        Clear::Choice const after = Clear::ChooseClearStepOff(drop, probeAt(review), bodyAt(review));
        for (float step : { 1.0f, after.Step.StepYards })
        {
            Vector3 const off = At(review, step);
            float const landing = ProbeLedgeDrop(review.Rim, off).LandingZ;
            Movement::MoveSpline spline;
            spline.Initialize(FallArgs(off, landing));
            std::vector<Vector3> const samples = Body::SampleSpline<Vector3>(spline);
            Body::Chords const chords = Body::ReduceToChords(samples);
            std::vector<Vector3> trajectory;
            for (std::size_t i : chords.Kept)
                trajectory.push_back(samples[i]);
            Body::Proof const proof = Body::ProveTrajectory(trajectory,
                Body::MakeBody(Radius, Height, chords.InflationYards), Blocked);
            std::printf("spline step=%.2f samples=%zu chords=%zu inflation=%.5f clear=%d rays=%u\n", step,
                samples.size(), chords.Kept.size() - 1, chords.InflationYards, proof.Clear(), proof.Rays);
            CHECK(chords.Kept.size() == 2 && chords.InflationYards < 1e-3f);
            CHECK(proof.Clear() == (step != 1.0f));
        }
    }
    // A jump arc (Parabolic, as MoveJump launches it) over a bar under its
    // apex: the chord from start to end passes under the bar, the arc hits
    // it; the proof of the sampled chords sees it, and the same arc with the
    // bar removed is clear.
    {
        Vector3 const from(40.0f, 0.0f, 1.44f), to(48.0f, 0.0f, 1.44f);
        Movement::MoveSplineInitArgs args;
        args.path = { from, to };
        args.velocity = 10.0f;
        args.flags.Parabolic = true;
        args.parabolic_amplitude = 3.0f;
        Movement::MoveSpline spline;
        spline.Initialize(args);
        std::vector<Vector3> const samples = Body::SampleSpline<Vector3>(spline);
        Body::Chords const chords = Body::ReduceToChords(samples);
        std::vector<Vector3> trajectory;
        float apex = 0.0f;
        for (std::size_t i : chords.Kept)
            trajectory.push_back(samples[i]);
        for (Vector3 const& p : samples)
            apex = std::max(apex, p.z);
        std::vector<Tri> const saved = mesh;
        // A thin horizontal plate at the apex's head height, across the arc.
        float const bar = apex + 1.0f;
        mesh = { { Vector3(43.8f, -3, bar), Vector3(44.2f, -3, bar), Vector3(44.2f, 3, bar), {}, {} },
                 { Vector3(43.8f, -3, bar), Vector3(44.2f, 3, bar), Vector3(43.8f, 3, bar), {}, {} } };
        Body::Body const body = Body::MakeBody(Radius, Height, chords.InflationYards);
        Body::Proof const hit = Body::ProveTrajectory(trajectory, body, Blocked);
        Body::Proof const chord = Body::ProveTrajectory(std::vector<Vector3>{ from, to }, body, Blocked);
        mesh.clear();
        Body::Proof const open = Body::ProveTrajectory(trajectory, body, Blocked);
        mesh = saved;
        std::printf("jump apex=%.3f chords=%zu inflation=%.4f hit=%d chord_only=%d open=%d\n", apex,
            chords.Kept.size() - 1, chords.InflationYards, int(hit.Kind), int(chord.Kind), int(open.Kind));
        CHECK(apex > from.z + 2.5f && chords.Kept.size() > 3 && chords.InflationYards < 0.1f);
        CHECK(hit.Kind == Body::Obstruction::Path && chord.Clear() && open.Clear());
    }
    // A purely vertical fall past a vertical wall inside the radius, which
    // the walk sweep (lateral offsets perpendicular to horizontal motion)
    // never sees.
    {
        std::vector<Tri> const saved = mesh;
        mesh = { { Vector3(0.3f, -5, -5), Vector3(0.3f, 5, -5), Vector3(0.3f, 5, 5), {}, {} },
                 { Vector3(0.3f, -5, -5), Vector3(0.3f, 5, 5), Vector3(0.3f, -5, 5), {}, {} } };
        std::vector<Vector3> const fall{ Vector3(0, 0, 3), Vector3(0, 0, -3) };
        CHECK(!Body::ProveTrajectory(fall, Body::MakeBody(Radius, Height), Blocked).Clear());
        mesh = { { Vector3(0.4f, -5, -5), Vector3(0.4f, 5, -5), Vector3(0.4f, 5, 5), {}, {} },
                 { Vector3(0.4f, -5, -5), Vector3(0.4f, 5, 5), Vector3(0.4f, -5, 5), {}, {} } };
        CHECK(Body::ProveTrajectory(fall, Body::MakeBody(Radius, Height), Blocked).Clear());
        mesh = saved;
    }
    // 5. The round-5 orb-ledge drop onto the raised ring top (a static
    // ledge, not a passenger): the model's part of the body proof along the
    // 33-yard fall and the landing footprint, at the candidates live members
    // took (world y -224.62, x past the lip at -157.65; the model's pi
    // rotation about its raised origin).
    {
        float const originX = -107.213f, originY = -224.62f, originZ = -6.86794f + 13.90172f;
        for (float x : { -157.05f, -156.8f, -156.4f })
        {
            Vector3 const start(-(x - originX), 0.0f, 41.3544f - originZ);
            float landing = 0.0f;
            CHECK(FloorBelow(start.x, start.y, start.z + 1.5f, 1.5f + (start.z - (8.51f - originZ)) + 1.0f, landing));
            Clear::FallBodyProbe const body = ProbeFallBody(start, landing);
            std::printf("orb_ledge x=%.2f landing=%.3f clear=%d inner=%u/%u rays=%u\n", x, landing + originZ,
                body.PathClear && body.LandingClear, body.InnerSupported, body.InnerPoints, body.Rays);
            CHECK(std::fabs(landing + originZ - 8.51f) < 0.1f);
            CHECK(Clear::ValidateFallBody(body).Ok);
            CHECK(OracleFall(start, landing).Depth <= 1e-4f);
            (void)originY;
        }
    }
    // 6. An arc reduced to chords proves the body the arc itself sweeps
    // (round-3 v4 review). The chords' deviation grows the body in every
    // direction, not only its radius: a parabola's apex rises straight above
    // its chord, so a ceiling between the chords' top and the arc's top must
    // still be met by the head (and a rope-like dip under its chord by the
    // knee). `Full` is the unreduced proof of every 5 ms sample, `Reduced` the
    // chords of ReduceToChords with the inflated body, as MoveSplineInit proves
    // an effect spline.
    {
        std::vector<Tri> const saved = mesh;
        struct ArcProof
        {
            Body::Proof Reduced, Full;
            Body::Chords Chords;
            float SampledTop = -1e9f, RetainedTop = -1e9f, SampledBottom = 1e9f, RetainedBottom = 1e9f;
        };
        auto plate = [](float z) -> std::vector<Tri>
        {
            return { { Vector3(-3, -3, z), Vector3(12, -3, z), Vector3(12, 3, z), {}, {} },
                     { Vector3(-3, -3, z), Vector3(12, 3, z), Vector3(-3, 3, z), {}, {} } };
        };
        auto prove = [](std::vector<Vector3> const& samples, float radius, float height)
        {
            ArcProof proof;
            proof.Chords = Body::ReduceToChords(samples);
            std::vector<Vector3> trajectory;
            for (std::size_t i : proof.Chords.Kept)
                trajectory.push_back(samples[i]);
            for (Vector3 const& p : samples)
            {
                proof.SampledTop = std::max(proof.SampledTop, p.z);
                proof.SampledBottom = std::min(proof.SampledBottom, p.z);
            }
            for (Vector3 const& p : trajectory)
            {
                proof.RetainedTop = std::max(proof.RetainedTop, p.z);
                proof.RetainedBottom = std::min(proof.RetainedBottom, p.z);
            }
            proof.Reduced = Body::ProveTrajectory(trajectory,
                Body::MakeBody(radius, height, proof.Chords.InflationYards), Blocked);
            proof.Full = Body::ProveTrajectory(samples, Body::MakeBody(radius, height), Blocked);
            return proof;
        };
        // The body grows by the inflation in every direction.
        {
            Body::Body const plain = Body::MakeBody(Radius, Height);
            Body::Body const grown = Body::MakeBody(Radius, Height, 0.05f);
            std::printf("inflated_body radius=%.4f knee=%.4f top=%.4f\n", grown.Radius, grown.Knee, grown.Top);
            CHECK(std::fabs(grown.Radius - (plain.Radius + 0.05f)) < 1e-6f);
            CHECK(std::fabs(grown.Top - (plain.Top + 0.05f)) < 1e-6f);
            CHECK(std::fabs(grown.Knee - (plain.Knee - 0.05f)) < 1e-6f);
            CHECK(Body::MakeBody(Radius, Height, -1.0f).Top == plain.Top);
        }
        // a. One second of native gravity over level ground (the spline the
        // liquid hop and MoveJumpWithGravity run): the retained apex sits
        // below the true one; a ceiling at the head height of the midpoint
        // between them is met by the arc and must be met by the chords.
        {
            float const length = 7.0f;
            Movement::MoveSplineInitArgs args;
            args.path = { Vector3(0, 0, 0), Vector3(length, 0, 0) };
            args.velocity = length * 1000.0f / 999.5f;
            args.flags.Parabolic = true;
            args.vertical_acceleration = 19.2911f;
            Movement::MoveSpline spline;
            spline.Initialize(args);
            CHECK(spline.Duration() == 1000);
            std::vector<Vector3> const samples = Body::SampleSpline<Vector3>(spline);
            ArcProof const probe = prove(samples, Radius, Height);
            float const gap = probe.SampledTop - probe.RetainedTop;
            std::printf("arc_gravity samples=%zu chords=%zu sampled_apex=%.6f retained_apex=%.6f inflation=%.6f\n",
                samples.size(), probe.Chords.Kept.size() - 1, probe.SampledTop, probe.RetainedTop,
                probe.Chords.InflationYards);
            CHECK(std::fabs(probe.SampledTop - 2.411388f) < 1e-3f);
            CHECK(gap > 0.004f && probe.Chords.InflationYards >= gap);
            mesh = plate(0.5f * (probe.SampledTop + probe.RetainedTop) + Height);
            ArcProof const hit = prove(samples, Radius, Height);
            std::printf("arc_gravity_ceiling z=%.6f full=%d reduced=%d\n", 0.5f * (probe.SampledTop + probe.RetainedTop)
                + Height, int(hit.Full.Kind), int(hit.Reduced.Kind));
            CHECK(!hit.Full.Clear() && !hit.Reduced.Clear());
            // Every ceiling the dense samples meet, the chords meet.
            int met = 0, unsound = 0, conservative = 0;
            for (float z = probe.RetainedTop + Height - 0.02f; z <= probe.SampledTop + Height + 0.08f; z += 0.001f)
            {
                mesh = plate(z);
                ArcProof const c = prove(samples, Radius, Height);
                met += !c.Full.Clear();
                unsound += !c.Full.Clear() && c.Reduced.Clear();
                conservative += c.Full.Clear() && !c.Reduced.Clear();
            }
            std::printf("arc_gravity_sweep met=%d unsound=%d conservative=%d\n", met, unsound, conservative);
            CHECK(met > 5 && unsound == 0);
            // A ceiling clear of the inflated head is not met: the arc is clear.
            mesh = plate(probe.SampledTop + Height + probe.Chords.InflationYards + 0.02f);
            ArcProof const open = prove(samples, Radius, Height);
            std::printf("arc_gravity_open full=%d reduced=%d\n", int(open.Full.Kind), int(open.Reduced.Kind));
            CHECK(open.Full.Clear() && open.Reduced.Clear());
        }
        // b. The second review's arc: 201 samples of x = 0.75 t, z = 5 t (1 - t),
        // radius 0.389, height 2, a ceiling at 3.225 under the apex's head (3.25).
        {
            std::vector<Vector3> samples;
            for (int i = 0; i <= 200; ++i)
            {
                float const t = float(i) / 200.0f;
                samples.push_back(Vector3(0.75f * t, 0.0f, 5.0f * t * (1.0f - t)));
            }
            mesh = plate(3.225f);
            ArcProof const hit = prove(samples, 0.389f, 2.0f);
            std::printf("arc_review2 chords=%zu inflation=%.6f full=%d reduced=%d\n", hit.Chords.Kept.size() - 1,
                hit.Chords.InflationYards, int(hit.Full.Kind), int(hit.Reduced.Kind));
            CHECK(!hit.Full.Clear() && !hit.Reduced.Clear());
            mesh = plate(3.25f + hit.Chords.InflationYards + 0.02f);
            ArcProof const open = prove(samples, 0.389f, 2.0f);
            std::printf("arc_review2_open full=%d reduced=%d\n", int(open.Full.Kind), int(open.Reduced.Kind));
            CHECK(open.Full.Clear() && open.Reduced.Clear());
        }
        // c. The other way: a dip under its chord (the path sags, the knee goes
        // low). A plate between the dip's knee and the retained knee is met by
        // the arc; the chords' body reaches down by the inflation to meet it.
        {
            std::vector<Vector3> samples;
            for (int i = 0; i <= 200; ++i)
            {
                float const t = float(i) / 200.0f;
                samples.push_back(Vector3(0.75f * t, 0.0f, -5.0f * t * (1.0f - t)));
            }
            ArcProof const probe = prove(samples, Radius, Height);
            float const gap = probe.RetainedBottom - probe.SampledBottom;
            std::printf("arc_dip sampled_bottom=%.6f retained_bottom=%.6f inflation=%.6f\n", probe.SampledBottom,
                probe.RetainedBottom, probe.Chords.InflationYards);
            CHECK(gap > 0.004f && probe.Chords.InflationYards >= gap);
            mesh = plate(probe.SampledBottom + Body::KneeYards + 0.5f * gap);
            ArcProof const hit = prove(samples, Radius, Height);
            std::printf("arc_dip_plate full=%d reduced=%d\n", int(hit.Full.Kind), int(hit.Reduced.Kind));
            CHECK(!hit.Full.Clear() && !hit.Reduced.Clear());
            // A plate under every knee (by more than the inflation) is no obstacle.
            mesh = plate(probe.SampledBottom + Body::KneeYards - probe.Chords.InflationYards - 0.02f);
            ArcProof const under = prove(samples, Radius, Height);
            std::printf("arc_dip_under full=%d reduced=%d\n", int(under.Full.Kind), int(under.Reduced.Kind));
            CHECK(under.Full.Clear() && under.Reduced.Clear());
        }
        // d. Random parabolas under random ceilings: the chords never pass a
        // ceiling the dense samples meet.
        {
            std::uint32_t state = 12345u;
            auto uniform = [&state](float lo, float hi)
            {
                state = state * 1664525u + 1013904223u;
                return lo + (hi - lo) * float(state >> 8) / float(1u << 24);
            };
            int arcs = 0, met = 0, unsound = 0, conservative = 0;
            for (int n = 0; n < 160; ++n)
            {
                float const duration = uniform(0.3f, 2.5f);
                float const gravity = uniform(8.0f, 26.0f);
                float const run = uniform(0.0f, 12.0f);
                float const rise = uniform(-2.0f, 2.0f);
                int const count = std::max(3, int(duration * 200.0f) + 1);
                std::vector<Vector3> samples;
                float apex = -1e9f;
                for (int i = 0; i < count; ++i)
                {
                    float const t = duration * float(i) / float(count - 1);
                    float const z = rise * t / duration + 0.5f * gravity * t * (duration - t);
                    samples.push_back(Vector3(run * t / duration, 0.0f, z));
                    apex = std::max(apex, z);
                }
                ArcProof const probe = prove(samples, Radius, Height);
                mesh = plate(apex + Height + uniform(-0.15f, 0.05f) + probe.Chords.InflationYards * uniform(0.0f, 1.0f));
                ArcProof const c = prove(samples, Radius, Height);
                ++arcs;
                met += !c.Full.Clear();
                unsound += !c.Full.Clear() && c.Reduced.Clear();
                conservative += c.Full.Clear() && !c.Reduced.Clear();
            }
            std::printf("arc_random arcs=%d met=%d unsound=%d conservative=%d\n", arcs, met, unsound, conservative);
            CHECK(met > 20 && unsound == 0);
        }
        mesh = saved;
    }
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run(tmp_path: Path) -> str:
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "Log.h").write_text(STUB_LOG)
    (stub / "Creature.h").write_text(STUB_CREATURE)
    source = tmp_path / "program.cpp"
    source.write_text(PROGRAM)
    binary = tmp_path / "program"
    includes = [stub, GAME, SPLINE, GAME / "Entities/Object/Updates", ROOT / "dep/g3dlite/include",
                ROOT / "dep/fmt/include"] + [ROOT / include for include in INCLUDES]
    command = ["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(SPLINE / name) for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary), str(_triangles_file(tmp_path))], cwd=ROOT, capture_output=True,
                         text=True, timeout=600)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> str:
    vmo._model()
    return _compile_and_run(tmp_path_factory.mktemp("fall_body"))


def test_the_reviewed_pillar_one_slot_two_fall_embedded_the_body_and_now_moves_out(output: str) -> None:
    before = re.search(r"before ok=1 reason=ledge_drop_verified step=1.00 dest=\((-?\d+\.\d+), (-?\d+\.\d+)\) "
                       r"landing=(-?\d+\.\d+) overlap=(\d+\.\d+) first_overlap_ms=(\d+)", output)
    assert before, output
    # The review's numbers on the same model.
    assert float(before.group(1)) == pytest.approx(-14.895720, abs=1e-3)
    assert float(before.group(2)) == pytest.approx(-32.007610, abs=1e-3)
    assert float(before.group(3)) == pytest.approx(1.438741, abs=1e-3)
    assert float(before.group(4)) > 0.05
    after = re.search(r"after ok=1 step=(\d+\.\d+) landing=(-?\d+\.\d+) overlap=(\d+\.\d+)", output)
    assert after and float(after.group(1)) > 1.0 and float(after.group(3)) == 0.0, output
    assert "failures=0" in output, output


def test_every_pillar_slot_and_candidate_the_proof_admits_falls_clear(output: str) -> None:
    sweep = re.search(r"sweep candidates=(\d+) proved=(\d+) overlapping=(\d+) unsound=(\d+)", output)
    assert sweep and int(sweep.group(4)) == 0 and int(sweep.group(3)) > 0, output
    choices = re.search(r"choices before_admitted=(\d+) before_overlapping=(\d+) after_admitted=(\d+) "
                        r"after_refused=(\d+)", output)
    assert choices and int(choices.group(2)) > 0, output
    assert int(choices.group(3)) + int(choices.group(4)) == 18
    assert "failures=0" in output, output


def test_the_orb_ledge_drop_still_falls_clear_onto_the_ring_top(output: str) -> None:
    assert len(re.findall(r"orb_ledge x=\S+ landing=8\.[45]\d+ clear=1 inner=[4-8]/8", output)) == 3, output
    assert "failures=0" in output, output


def test_the_effect_spline_proof_samples_the_real_spline(output: str) -> None:
    assert re.search(r"spline step=1.00 samples=\d+ chords=1 inflation=0.0000\d clear=0", output), output
    assert re.search(r"jump apex=\S+ chords=\d+ inflation=\S+ hit=2 chord_only=0 open=0", output), output
    assert "failures=0" in output, output


def test_a_reduced_arc_grows_the_body_in_every_direction_not_only_its_radius(output: str) -> None:
    # MakeBody(radius, height, inflation): wider, the head higher, the knee lower.
    body = re.search(r"inflated_body radius=(\S+) knee=(\S+) top=(\S+)", output)
    assert body, output
    assert float(body.group(1)) == pytest.approx(0.389 + 0.05, abs=1e-4)
    assert float(body.group(2)) == pytest.approx(0.5 - 0.05, abs=1e-4)
    assert float(body.group(3)) == pytest.approx(2.0313 + 0.05, abs=1e-4)
    # One second of native gravity: the review's true apex 2.411388 against a
    # retained apex below it, and the ceiling at the head height of the midpoint.
    gravity = re.search(r"arc_gravity samples=\d+ chords=\d+ sampled_apex=(\S+) retained_apex=(\S+) inflation=(\S+)",
                        output)
    assert gravity and float(gravity.group(1)) == pytest.approx(2.411388, abs=1e-3), output
    assert float(gravity.group(2)) < float(gravity.group(1)) - 0.004
    ceiling = re.search(r"arc_gravity_ceiling z=(\S+) full=([12]) reduced=([12])", output)
    assert ceiling and float(ceiling.group(1)) == pytest.approx(4.4397, abs=2e-3), output
    assert re.search(r"arc_gravity_sweep met=\d+ unsound=0 ", output), output
    assert re.search(r"arc_gravity_open full=0 reduced=0", output), output
    # The second review: 201 samples of x = .75 t, z = 5 t (1 - t), ceiling 3.225.
    assert re.search(r"arc_review2 chords=\d+ inflation=\S+ full=[12] reduced=[12]", output), output
    assert re.search(r"arc_review2_open full=0 reduced=0", output), output
    # The dip under its chord, and every random parabola under a random ceiling.
    assert re.search(r"arc_dip_plate full=[12] reduced=[12]", output), output
    assert re.search(r"arc_dip_under full=0 reduced=0", output), output
    assert re.search(r"arc_random arcs=160 met=\d+ unsound=0 ", output), output
    assert "failures=0" in output, output


def _code(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_launch_proves_player_passenger_falls_and_jumps_before_initializing() -> None:
    code = _code(LAUNCH)
    prove = code[code.index("PassengerClip ProvePassengerEffectSpline("):code.index("namespace Movement\n{")]
    assert "if (!unit->IsPlayer() || unit->GetVehicle() || !unit->GetTransport())" in prove
    assert "if (!(args.flags.Falling || args.flags.Parabolic) || args.flags.Animation" in prove
    assert prove.index("if (!object || !object->m_model)") < prove.index("return PassengerClip::Refused;")
    for needle in ("run.Initialize(args);", "SampleSpline<G3D::Vector3>(run)",
                   "transport->CalculatePassengerPosition(point.x, point.y, point.z);",
                   "ReduceToChords(samples)", "chords.InflationYards), blocked);"):
        assert needle in prove, needle
    launch = code[code.index("int32 MoveSplineInit::Launch()"):code.index("void MoveSplineInit::Stop()")]
    order = [launch.index("args.Validate(unit)"),
             launch.index("if (transport && ProvePassengerEffectSpline(unit, args) == PassengerClip::Refused)"),
             launch.index("move_spline.Initialize(args);")]
    assert order == sorted(order)
    refused = launch[order[1]:launch.index("return 0;", order[1])]
    assert "unit->StopMoving();" in refused and "recordLaunch(false);" in refused


def test_the_executor_proves_the_body_before_every_step_off_and_fall() -> None:
    code = _code(EXECUTOR)
    step = code[code.index("Outcome ExecuteStepOff("):code.index("Outcome LaunchNativeFall(")]
    assert "BotLedgeDropBodyClearance::ChooseClearStepOff(drop," in step
    assert "Route::ChooseStepOff(" not in step
    fall = code[code.index("Outcome ExecuteFall("):code.index("Outcome ExecuteLand(")]
    order = [fall.index("native_ledge_drop_fall_landing_mismatch"),
             fall.index("BotLedgeDropBodyClearance::ValidateFallBody("),
             fall.index("return LaunchFallOnto(bot, floor);")]
    assert order == sorted(order)
    # A fall continued after a landing without floor is proven too, onto the
    # floor MoveFall's own query finds.
    refall = code[code.index("Outcome LaunchNativeFall("):code.index("Outcome LaunchFallOnto(")]
    order = [refall.index("MAX_FALL_DISTANCE"), refall.index("ValidateFallBody("),
             refall.index("bot->GetMotionMaster()->MoveFall();")]
    assert order == sorted(order)
    probe = code[code.index("BotLedgeDropBodyClearance::FallBodyProbe ProbeFallBody("):]
    probe = probe[:probe.index("\n}\n")]
    # Static geometry, every gameobject and the transport's own model.
    assert "LINEOFSIGHT_ALL_CHECKS" in probe and "transport->m_model->intersectRay(" in probe
    assert "landingZ + bot->GetHoverOffset()" in probe
    for path in (TRAJECTORY, CHOOSER, LAUNCH, EXECUTOR):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
    header = TRAJECTORY.read_text(encoding="utf-8")
    assert re.findall(r'#include [<"]([^>"]+)[>"]', header) == ["algorithm", "cmath", "cstddef", "cstdint",
                                                               "vector"]

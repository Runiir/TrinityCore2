"""A passenger's walk or chase spline keeps the whole body out of its transport.

Round-3 v3 runtime review (P2, packet walk_clearance): ClipPath
(Movement/Spline/PassengerSplineCollision.h) ends a path a radius short of
the first hit of rays cast along each segment, which measures along the
segment, not across the body. On the Nefarian elevator's own collision model
(GO 207834, the vmo port of tests/test_nefarian_ledge_drop_floor_query.py),
in transport-local coordinates, a walk from (33.255489, -0.062544, 1.405969)
toward (34.755489, -0.062544, 2.116569) came back Clipped at (34.581470,
-0.062544, 2.034131) and the real MoveSpline ended there with 0.044 yd of the
body (knee to head) in the pillar-0 skirt.

Now MoveSplineInit proves the kept path with the body cylinder of
Movement/Spline/PassengerBodyTrajectory.h (PassengerWalkProof.h SettleWalk):
along every piece and at every knot and the end, moving the end back until
it is proved, or refusing. The oracle here is independent of the rays: the
exact overlap of the body cylinder with every model triangle (each clipped
to the knee-head slab, its plan distance from the axis), at every 5 ms of the
REAL Movement::MoveSpline the launch initializes and at its end.
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
PROOF = SPLINE / "PassengerWalkProof.h"
LAUNCH = SPLINE / "MoveSplineInit.cpp"

PROGRAM = r'''
#include "Movement/Spline/PassengerWalkProof.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMagma.h"
#include "MoveSpline.h"
#include "MoveSplineInitArgs.h"

#include <G3D/Matrix4.h>
#include <G3D/Vector3.h>
#include <G3D/Vector4.h>

#include <algorithm>
#include <chrono>
#include <cmath>
#include <cstdint>
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
// Built at static initialization by Spline.cpp; a linear spline never
// evaluates them (every swept passenger spline is emitted linear).
G3D::Matrix4::Matrix4(float, float, float, float, float, float, float, float,
    float, float, float, float, float, float, float, float) { }
G3D::Vector4 G3D::Vector4::operator*(const G3D::Matrix4&) const { return Vector4(); }
std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using G3D::Vector3;
namespace Body = Movement::BodyTrajectory;
namespace Collision = Movement::PassengerCollision;
namespace Walk = Movement::PassengerWalk;
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

// GameObjectModel::intersectRay without stopAtFirstHit: the nearest hit.
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

static float Top(float x, float y, float from = 14.0f)
{
    float const hit = Nearest(Vector3(x, y, from), Vector3(0, 0, -1), 40.0f);
    return hit < 0.0f ? -1000.0f : from - hit;
}

static float const Radius = 0.389f;
static float const Height = 2.0313f; // a human male's collision height

// ---- The oracle: exact overlap of the body cylinder (axis at feet.xy, knee
// to head) with the model's triangles.
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

static std::vector<Tri const*> Near(std::vector<Vector3> const& path)
{
    Vector3 lo = path[0], hi = path[0];
    for (Vector3 const& p : path)
    {
        lo = lo.min(p);
        hi = hi.max(p);
    }
    std::vector<Tri const*> near;
    for (Tri const& t : mesh)
        if (t.hi.x >= lo.x - Radius && t.lo.x <= hi.x + Radius && t.hi.y >= lo.y - Radius
            && t.lo.y <= hi.y + Radius && t.hi.z >= lo.z && t.lo.z <= hi.z + Height)
            near.push_back(&t);
    return near;
}

struct Walked { float Depth = 0.0f; float EndDepth = 0.0f; int FirstOverlapMs = -1; int DurationMs = 0; int Samples = 0; Vector3 End; };

// The positions the server moves the unit through: the real MoveSpline the
// launch initializes, every 5 ms and at its end.
static Walked Run(std::vector<Vector3> const& path)
{
    Walked walked;
    walked.End = path.back();
    std::vector<Tri const*> const near = Near(path);
    if (path.size() < 2)
    {
        walked.Depth = walked.EndDepth = Overlap(path[0], near);
        return walked;
    }
    Movement::MoveSplineInitArgs args;
    args.path.assign(path.begin(), path.end());
    args.velocity = 7.0f;
    Movement::MoveSpline spline;
    spline.Initialize(args);
    walked.DurationMs = spline.Duration();
    for (int32 t = 0;; t += 5)
    {
        int32 const at = std::min(t, spline.Duration());
        Movement::Location const p = spline.ComputePosition(at);
        float const depth = Overlap(Vector3(p.x, p.y, p.z), near);
        if (depth > 1e-4f && walked.FirstOverlapMs < 0)
            walked.FirstOverlapMs = at;
        walked.Depth = std::max(walked.Depth, depth);
        ++walked.Samples;
        if (at == spline.Duration())
        {
            walked.EndDepth = depth;
            walked.End = Vector3(p.x, p.y, p.z);
            break;
        }
    }
    return walked;
}

// What the launch emitted before (the sweep's clip, linear) and now (the
// sweep's clip, then the body proof), as spline points; one point = refused.
struct Emission { std::vector<Vector3> Path; Collision::Result Clip; Walk::Settled Settled; long Rays = 0; };

static Emission Before(std::vector<Vector3> path)
{
    Emission e;
    e.Clip = Collision::ClipPath(path, Radius, Height, Nearest);
    if (e.Clip.Kind == Collision::Verdict::Blocked)
        path.resize(1);
    else
        Collision::ApplyClip(path, e.Clip);
    e.Path = path;
    return e;
}

static Emission After(std::vector<Vector3> path)
{
    Emission e;
    long const before = rays;
    e.Clip = Collision::ClipPath(path, Radius, Height, Nearest);
    long const sweep = rays;
    e.Settled = Walk::SettleWalk(path, e.Clip, Body::MakeBody(Radius, Height), Blocked);
    CHECK(long(e.Settled.Rays) == rays - sweep || e.Clip.Kind == Collision::Verdict::Blocked);
    e.Rays = rays - before;
    if (e.Settled.Clip.Kind == Collision::Verdict::Blocked)
        path.resize(1);
    else
        Collision::ApplyClip(path, e.Settled.Clip);
    e.Path = path;
    return e;
}

// The launch as MoveSplineInit runs it: ProveWalk (a stationary path casts
// nothing; any other is swept and proved, as After). Rays: all of them.
static Emission Launched(std::vector<Vector3> path)
{
    Emission e;
    long const before = rays;
    e.Settled = Walk::ProveWalk(path, Radius, Height, Nearest, Blocked);
    e.Rays = rays - before;
    e.Clip = e.Settled.Clip;
    if (e.Settled.Clip.Kind == Collision::Verdict::Blocked)
        path.resize(1);
    else
        Collision::ApplyClip(path, e.Settled.Clip);
    e.Path = path;
    return e;
}

static float Length(std::vector<Vector3> const& path)
{
    float length = 0.0f;
    for (std::size_t i = 0; i + 1 < path.size(); ++i)
        length += (path[i + 1] - path[i]).length();
    return length;
}

static std::uint32_t seed = 20260930u;
static float Uniform(float lo, float hi)
{
    seed = seed * 1664525u + 1013904223u;
    return lo + (hi - lo) * float(seed >> 8) / float(1u << 24);
}

int main(int argc, char** argv)
{
    if (argc < 2)
        return 2;
    if (argc > 2) // another draw of the randomized walks
        seed = std::uint32_t(std::strtoul(argv[2], nullptr, 10));
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

    // 1. The review's reproduction: up the ring into the pillar-0 skirt.
    std::vector<Vector3> const review{ Vector3(33.255489f, -0.062544f, 1.405969f),
                                       Vector3(34.755489f, -0.062544f, 2.116569f) };
    {
        CHECK(Overlap(review[0], Near(review)) <= 1e-4f);
        Emission const before = Before(review);
        Walked const walked = Run(before.Path);
        std::printf("review before kind=%d end=(%.6f, %.6f, %.6f) duration_ms=%d end_depth=%.6f depth=%.6f\n",
            int(before.Clip.Kind), before.Path.back().x, before.Path.back().y, before.Path.back().z,
            walked.DurationMs, walked.EndDepth, walked.Depth);
        CHECK(before.Clip.Kind == Collision::Verdict::Clipped);
        CHECK(walked.EndDepth > 0.04f);
        Emission const after = After(review);
        Walked const proved = Run(after.Path);
        std::printf("review after kind=%d end=(%.6f, %.6f, %.6f) kept=%.4f backed_off=%d duration_ms=%d depth=%.6f "
            "samples=%d rays=%ld\n", int(after.Settled.Clip.Kind), after.Path.back().x, after.Path.back().y,
            after.Path.back().z, after.Settled.Clip.KeptYards, after.Settled.BackedOff, proved.DurationMs,
            proved.Depth, proved.Samples, after.Rays);
        CHECK(after.Settled.Clip.Kind == Collision::Verdict::Clipped && after.Settled.BackedOff);
        CHECK(proved.Depth <= 1e-4f && proved.EndDepth <= 1e-4f);
        CHECK(after.Path.back().x < before.Path.back().x && after.Path.back().x > review[0].x + 0.5f);

        // Standing where the old clip left it (0.044 yd in the skirt): it
        // may walk back out, ending clear, but not on or further in.
        std::vector<Vector3> const out{ before.Path.back(), review[0] };
        Emission const escape = After(out);
        Walked const left = Run(escape.Path);
        std::printf("escape kind=%d escape=%d end_depth=%.6f\n", int(escape.Settled.Clip.Kind),
            escape.Settled.Escape, left.EndDepth);
        CHECK(escape.Settled.Clip.Kind != Collision::Verdict::Blocked && escape.Settled.Escape);
        CHECK(left.EndDepth <= 1e-4f);
        Emission const deeper = After({ before.Path.back(), Vector3(36.0f, -0.062544f, 2.7f) });
        CHECK(deeper.Settled.Clip.Kind == Collision::Verdict::Blocked);
    }

    // 2. Positive controls: walks on the open platform and across a pillar
    // top are emitted unchanged, Clear, with no back-off.
    {
        int controls = 0;
        long controlRays = 0;
        float controlYards = 0.0f;
        auto onFloor = [](float x, float y) { return Vector3(x, y, Top(x, y)); };
        for (std::vector<Vector3> const& path : std::vector<std::vector<Vector3>>{
                 { onFloor(0.0f, 0.0f), onFloor(10.0f, 0.0f) },
                 { onFloor(-5.0f, 5.0f), onFloor(5.0f, 12.0f), onFloor(15.0f, 12.0f) },
                 { onFloor(20.0f, -15.0f), onFloor(25.0f, 15.0f) },
                 { onFloor(0.0f, 0.0f), onFloor(0.3f, 0.0f) },
                 { Vector3(Nef::PillarCenters[1].X - 2.0f, Nef::PillarCenters[1].Y, Nef::PlatformFrame::PillarTopLocalZ),
                   Vector3(Nef::PillarCenters[1].X + 2.0f, Nef::PillarCenters[1].Y, Nef::PlatformFrame::PillarTopLocalZ) } })
        {
            Emission const e = After(path);
            Walked const walked = Run(e.Path);
            CHECK(e.Settled.Clip.Kind == Collision::Verdict::Clear && !e.Settled.BackedOff && !e.Settled.Escape);
            CHECK(e.Path.size() == path.size());
            for (std::size_t i = 0; i < path.size() && i < e.Path.size(); ++i)
                CHECK(e.Path[i] == path[i]);
            CHECK(walked.Depth <= 1e-4f);
            ++controls;
            controlRays += long(e.Settled.Rays);
            controlYards += Length(path);
        }
        std::printf("controls=%d clear rays=%ld yards=%.2f\n", controls, controlRays, controlYards);
    }

    // 3. Randomized walks around every pillar, its top, rim, wall and skirt,
    // and the ring: whatever is emitted is walked with zero overlap at every
    // 5 ms sample and at its end.
    int walks = 0, clear = 0, clipped = 0, blocked = 0, backedOff = 0, beforeOverlapping = 0;
    int overlapping = 0, beforeBlocked = 0, launchMismatch = 0;
    float worstBefore = 0.0f, worstAfter = 0.0f;
    long totalRays = 0, maxRays = 0, sweepRays = 0;
    double totalYards = 0.0, proofMs = 0.0;
    for (int pillar = 0; pillar < 3; ++pillar)
    {
        Nef::LocalPoint const c = Nef::PillarCenters[pillar];
        int made = 0;
        while (made < 400)
        {
            float const heading = Uniform(0.0f, 6.2831853f);
            // Tops (0-4.5), rims and walls, the skirt (5.4-6.05), the ring.
            float const radius = made % 4 == 0 ? Uniform(0.0f, 4.5f) : Uniform(5.2f, 11.0f);
            Vector3 start(c.X + radius * std::cos(heading), c.Y + radius * std::sin(heading), 0.0f);
            start.z = Top(start.x, start.y);
            if (start.z < -100.0f || Overlap(start, Near({ start })) > 0.0f)
                continue;
            std::vector<Vector3> path{ start };
            int const knots = made % 3 == 0 ? 2 : 1;
            for (int k = 0; k < knots; ++k)
            {
                // Mostly toward the pillar (into the skirt and wall).
                float const toward = std::atan2(c.Y - path.back().y, c.X - path.back().x);
                float const h = made % 5 == 0 ? Uniform(0.0f, 6.2831853f) : toward + Uniform(-1.2f, 1.2f);
                float const length = Uniform(0.3f, made % 2 ? 3.0f : 9.0f);
                Vector3 next(path.back().x + length * std::cos(h), path.back().y + length * std::sin(h), 0.0f);
                // A surface the navmesh or the executor could hand over: the
                // top surface, or the start's own height.
                next.z = made % 7 == 0 ? path.back().z : Top(next.x, next.y);
                if (next.z < -100.0f)
                    next.z = path.back().z;
                path.push_back(next);
            }
            ++made;
            ++walks;
            Emission const before = Before(path);
            Walked const old = Run(before.Path);
            beforeOverlapping += old.Depth > 1e-4f;
            beforeBlocked += before.Path.size() == 1;
            worstBefore = std::max(worstBefore, old.Depth);
            auto const t0 = std::chrono::steady_clock::now();
            long const r0 = rays;
            Collision::Result const sweep = Collision::ClipPath(path, Radius, Height, Nearest);
            sweepRays += rays - r0;
            (void)sweep;
            Emission const after = After(path);
            proofMs += std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
            // The launch's ProveWalk is the same verdict at the same cost for
            // every walk that moves (none of these is stationary).
            Emission const launched = Launched(path);
            if (launched.Settled.Clip.Kind != after.Settled.Clip.Kind || launched.Rays != after.Rays
                || std::fabs(launched.Settled.Clip.KeptYards - after.Settled.Clip.KeptYards) > 1e-6f
                || launched.Path != after.Path || launched.Settled.Stationary)
            {
                ++launchMismatch;
                std::fprintf(stderr, "LAUNCH MISMATCH pillar=%d walk=%d\n", pillar, made);
            }
            Walked const now = Run(after.Path);
            clear += after.Settled.Clip.Kind == Collision::Verdict::Clear;
            clipped += after.Settled.Clip.Kind == Collision::Verdict::Clipped;
            blocked += after.Settled.Clip.Kind == Collision::Verdict::Blocked;
            backedOff += after.Settled.BackedOff;
            totalRays += after.Rays;
            maxRays = std::max(maxRays, after.Rays);
            totalYards += Length(path);
            worstAfter = std::max(worstAfter, now.Depth);
            if (now.Depth > 1e-4f || now.EndDepth > 1e-4f)
            {
                ++overlapping;
                std::fprintf(stderr, "OVERLAP pillar=%d walk=%d depth=%.5f at_ms=%d kind=%d escape=%d path=",
                    pillar, made, now.Depth, now.FirstOverlapMs, int(after.Settled.Clip.Kind), after.Settled.Escape);
                for (Vector3 const& p : path)
                    std::fprintf(stderr, "(%.4f,%.4f,%.4f)", p.x, p.y, p.z);
                std::fprintf(stderr, "\n");
            }
            // Never longer than the sweep's clip; a Clear path stays whole.
            CHECK(after.Settled.Clip.KeptYards <= before.Clip.KeptYards + 1e-3f
                || before.Clip.Kind == Collision::Verdict::Blocked);
            if (after.Settled.Clip.Kind == Collision::Verdict::Clear)
                CHECK(after.Path.size() == path.size() && after.Path.back() == path.back());
        }
    }
    std::printf("sweep walks=%d clear=%d clipped=%d blocked=%d backed_off=%d overlapping=%d worst=%.6f\n",
        walks, clear, clipped, blocked, backedOff, overlapping, worstAfter);
    std::printf("before overlapping=%d blocked=%d worst=%.6f\n", beforeOverlapping, beforeBlocked, worstBefore);
    std::printf("cost mean_rays=%.1f max_rays=%ld sweep_mean_rays=%.1f rays_per_yard=%.1f mean_ms=%.3f\n",
        double(totalRays) / walks, maxRays, double(sweepRays) / walks, double(totalRays) / totalYards,
        proofMs / walks);
    std::printf("launch_mismatch=%d\n", launchMismatch);
    CHECK(walks == 1200);
    CHECK(overlapping == 0);
    CHECK(launchMismatch == 0);
    CHECK(beforeOverlapping > 0);
    CHECK(clear > 0 && clipped > 0);

    // 4. The bounded cost: a clear 20-yard level walk and a single piece.
    {
        std::vector<Vector3> const path{ Vector3(0.0f, -10.0f, Top(0.0f, -10.0f)), Vector3(0.0f, 10.0f, Top(0.0f, 10.0f)) };
        Emission const e = After(path);
        int const columns = int(std::ceil(Length(path) / Walk::ColumnStepYards)) - 1;
        std::size_t const levels = Body::Levels(Body::KneeYards, Height).size();
        std::printf("level_walk kind=%d rays=%u expected=%zu levels=%zu\n", int(e.Settled.Clip.Kind), e.Settled.Rays,
            25 * levels + 25 * columns + 25 + 16 * levels, levels);
        CHECK(e.Settled.Clip.Kind == Collision::Verdict::Clear);
        CHECK(e.Settled.Rays == 25 * levels + 25 * std::size_t(columns) + 25 + 16 * levels);
    }

    // 5. A facing (Unit::SetFacingTo*) launches a spline from where the unit
    // stands to where it stands (round-3 v4 review). The body proof alone
    // costs 121 rays for it and refuses it outright when the body already
    // overlaps a wall, so a bot standing in a skirt could not turn to its
    // target. ProveWalk casts nothing for a path that moves nothing, and
    // proves any motion in full.
    {
        Vector3 const inWall = Before(review).Path.back();        // 0.044 yd in the skirt
        Vector3 const inOpen(0.0f, 0.0f, Top(0.0f, 0.0f));
        CHECK(Overlap(inWall, Near({ inWall })) > 0.04f && Overlap(inOpen, Near({ inOpen })) <= 1e-4f);
        struct Place { char const* Name; Vector3 From; };
        for (Place const& place : { Place{ "open", inOpen }, Place{ "wall", inWall } })
        {
            std::vector<Vector3> const still{ place.From, place.From };
            // What the launch did before: the sweep and then the body proof.
            Emission const old = After(still);
            Emission const now = Launched(still);
            std::printf("facing %s old_kind=%d old_rays=%ld new_kind=%d new_rays=%ld stationary=%d unchanged=%d\n",
                place.Name, int(old.Settled.Clip.Kind), old.Rays, int(now.Settled.Clip.Kind), now.Rays,
                now.Settled.Stationary, now.Path == still);
            CHECK(now.Rays == 0 && now.Settled.Rays == 0 && now.Settled.Stationary);
            CHECK(now.Settled.Clip.Kind == Collision::Verdict::Clear && now.Path == still);
            // The body proof alone: 121 rays in the open (25 footprint rays
            // and 16 radial rays at each of the 6 levels), a refusal in the wall.
            if (place.From == inWall)
                CHECK(old.Settled.Clip.Kind == Collision::Verdict::Blocked && old.Settled.Rays > 0);
            else
                CHECK(old.Settled.Clip.Kind == Collision::Verdict::Clear && old.Settled.Rays == 121);
        }
        // The world-to-transport round trip of a standing unit's own position
        // and any number of points, horizontal and vertical alike: still no
        // motion.
        for (std::vector<Vector3> const& path : std::vector<std::vector<Vector3>>{
                 { inWall, inWall + Vector3(3e-5f, -2e-5f, 1e-5f) },
                 { inWall, inWall, inWall },
                 { inWall, inWall + Vector3(0.0f, 0.0f, 0.0009f) },
                 { inWall, inWall + Vector3(0.0005f, 0.0005f, 0.0005f) } })
        {
            Emission const now = Launched(path);
            CHECK(Walk::IsStationary(path) && now.Rays == 0 && now.Settled.Clip.Kind == Collision::Verdict::Clear);
            CHECK(now.Path == path);
        }
        // Any motion is proved in full: a facing that also corrects the
        // position, horizontally or vertically, at one point or the last, in
        // the open or in the wall, costs and decides what the body proof does.
        int moving = 0;
        for (std::vector<Vector3> const& path : std::vector<std::vector<Vector3>>{
                 { inOpen, inOpen + Vector3(0.02f, 0.0f, 0.0f) },
                 { inOpen, inOpen + Vector3(0.0f, -0.02f, 0.0f) },
                 { inOpen, inOpen + Vector3(0.0f, 0.0f, 0.02f) },
                 { inOpen, inOpen + Vector3(0.0011f, 0.0f, 0.0f) },
                 { inOpen, inOpen + Vector3(0.0f, 0.0f, 0.0011f) },
                 { inOpen, inOpen, inOpen + Vector3(0.05f, 0.0f, 0.0f) },
                 { inOpen, inOpen + Vector3(0.05f, 0.0f, 0.0f), inOpen },
                 { inWall, inWall + Vector3(0.02f, 0.0f, 0.0f) },
                 { inWall, Vector3(inWall.x + 0.05f, inWall.y, inWall.z + 0.02f) } })
        {
            CHECK(!Walk::IsStationary(path));
            Emission const now = Launched(path);
            Emission const old = After(path);
            std::printf("moving kind=%d old_kind=%d rays=%ld old_rays=%ld stationary=%d\n", int(now.Settled.Clip.Kind),
                int(old.Settled.Clip.Kind), now.Rays, old.Rays, now.Settled.Stationary);
            CHECK(!now.Settled.Stationary && now.Rays > 0 && now.Rays == old.Rays);
            CHECK(now.Settled.Clip.Kind == old.Settled.Clip.Kind && now.Path == old.Path);
            ++moving;
        }
        // Walking further into the wall from where the body already stands
        // in it is still refused: only a path that moves nothing is exempt.
        Emission const deeper = Launched({ inWall, Vector3(inWall.x + 0.3f, inWall.y, inWall.z + 0.14f) });
        std::printf("facing_deeper kind=%d moving=%d\n", int(deeper.Settled.Clip.Kind), moving);
        CHECK(deeper.Settled.Clip.Kind == Collision::Verdict::Blocked && !deeper.Settled.Stationary);
        CHECK(!Walk::IsStationary(std::vector<Vector3>{ inWall }));
        CHECK(!Walk::IsStationary(std::vector<Vector3>{ inWall, Vector3(NAN, 0.0f, 0.0f) }));
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
    command = ["g++", "-std=c++20", "-O2", "-Wall", "-Wextra", "-Werror=unused-variable",
               "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(SPLINE / name) for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary), str(_triangles_file(tmp_path))], cwd=ROOT, capture_output=True,
                         text=True, timeout=1200)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


@pytest.fixture(scope="module")
def output(tmp_path_factory: pytest.TempPathFactory) -> str:
    vmo._model()
    return _compile_and_run(tmp_path_factory.mktemp("walk_body"))


def test_the_reviewed_clipped_walk_into_the_skirt_now_ends_clear(output: str) -> None:
    before = re.search(r"review before kind=1 end=\((-?\d+\.\d+), (-?\d+\.\d+), (-?\d+\.\d+)\) "
                       r"duration_ms=(\d+) end_depth=(\d+\.\d+)", output)
    assert before, output
    # The review's numbers on the same model.
    assert float(before.group(1)) == pytest.approx(34.581470, abs=1e-4)
    assert float(before.group(3)) == pytest.approx(2.034131, abs=1e-4)
    assert float(before.group(5)) == pytest.approx(0.044174, abs=2e-3)
    after = re.search(r"review after kind=1 end=\((-?\d+\.\d+), \S+ \S+\) kept=\S+ backed_off=1 "
                      r"duration_ms=\d+ depth=(\d+\.\d+)", output)
    assert after and float(after.group(2)) == 0.0, output
    assert float(after.group(1)) < float(before.group(1))
    assert re.search(r"escape kind=[01] escape=1 end_depth=0\.000000", output), output
    assert "failures=0" in output, output


def test_randomized_walks_around_every_pillar_and_skirt_never_overlap(output: str) -> None:
    sweep = re.search(r"sweep walks=(\d+) clear=(\d+) clipped=(\d+) blocked=(\d+) backed_off=(\d+) "
                      r"overlapping=(\d+)", output)
    assert sweep and int(sweep.group(1)) == 1200 and int(sweep.group(6)) == 0, output
    assert int(sweep.group(2)) > 0 and int(sweep.group(3)) > 0
    before = re.search(r"before overlapping=(\d+)", output)
    assert before and int(before.group(1)) > 0, output
    assert "failures=0" in output, output


def test_clear_walks_are_unchanged_and_the_cost_is_bounded(output: str) -> None:
    assert re.search(r"controls=5 clear", output), output
    assert re.search(r"level_walk kind=0 rays=\d+ expected=\d+ levels=6", output), output
    assert "failures=0" in output, output


def test_a_facing_spline_casts_no_ray_and_is_never_refused_but_any_motion_is_proved(output: str) -> None:
    # The body proof alone spent 121 rays on a facing in the open and refused
    # one from a body already in the skirt; the launch's ProveWalk casts nothing
    # for a path that moves nothing and emits it unchanged.
    assert re.search(r"facing open old_kind=0 old_rays=121 new_kind=0 new_rays=0 stationary=1 unchanged=1", output), output
    assert re.search(r"facing wall old_kind=2 old_rays=\d+ new_kind=0 new_rays=0 stationary=1 unchanged=1", output), output
    # Any motion is proved in full, at the same cost and verdict as before, and
    # every walk of the randomized sweep is decided exactly as before.
    moving = re.findall(r"moving kind=(\d) old_kind=(\d) rays=(\d+) old_rays=(\d+) stationary=0", output)
    assert len(moving) == 9 and all(kind == old and rays == old_rays and int(rays) > 0
                                    for kind, old, rays, old_rays in moving), output
    assert "launch_mismatch=0" in output, output
    assert re.search(r"facing_deeper kind=2 moving=9", output), output
    assert "failures=0" in output, output


def _code(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_launch_body_proves_every_swept_walk_before_emitting_it() -> None:
    code = _code(LAUNCH)
    clip = code[code.index("PassengerClip ClipPassengerSpline("):code.index("PassengerClip ProvePassengerEffectSpline(")]
    # One pure ProveWalk decides: nothing for a path that moves nothing, else
    # the sweep, then the body proof; the launch refuses (logged) or emits.
    order = [clip.index("Movement::PassengerWalk::ProveWalk(world, radius,"),
             clip.index("if (settled.SweepBlocked)"),
             clip.index("if (proved.Kind == Verdict::Blocked)"),
             clip.index("EmitProvedPath(args, proved);"),
             clip.rindex("return PassengerClip::Emitted;")]
    assert order == sorted(order)
    for refusal in (order[1], order[2]):
        refused = clip[refusal:clip.index("return PassengerClip::Refused;", refusal)]
        assert "TC_LOG_DEBUG(\"movement.spline\"" in refused
    # The proof uses the unit's own radius and height, the nearest-hit sweep
    # and the boolean model ray.
    assert "ProveWalk(world, radius, unit->GetCollisionHeight(), nearestHit, blocked);" in " ".join(clip.split())
    assert "true, phase, VMAP::ModelIgnoreFlags::Nothing);" in clip
    assert "ClipPath(" not in clip and "SettleWalk(" not in clip
    assert code.count("EmitProvedPath(") == 1
    # ProveWalk itself: the stationary exit first, then the sweep, its refusal,
    # the body proof with the unit's own radius and height.
    header_code = _code(PROOF)
    walk = header_code[header_code.index("Settled ProveWalk("):]
    order = [walk.index("if (IsStationary(path))"), walk.index("Collision::ClipPath(path, radius, collisionHeight, hit)"),
             walk.index("if (sweep.Kind == Collision::Verdict::Blocked)"),
             walk.index("SettleWalk(path, sweep, Body::MakeBody(radius, collisionHeight), blocked)")]
    assert order == sorted(order)
    stationary = walk[order[0]:order[1]]
    assert "settled.Stationary = true;" in stationary and "return settled;" in stationary
    assert "StationaryYards = Body::VerticalYards" in header_code
    header = PROOF.read_text(encoding="utf-8")
    assert re.findall(r'#include [<"]([^>"]+)[>"]', header) == [
        "PassengerBodyTrajectory.h", "PassengerSplineCollision.h", "algorithm", "cmath", "cstddef", "cstdint",
        "vector"]
    for path in (PROOF, LAUNCH, SPLINE / "PassengerSplineCollision.h", SPLINE / "PassengerBodyTrajectory.h"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000

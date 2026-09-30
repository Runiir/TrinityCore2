"""The passenger clip's proof covers the body and the trajectory actually walked.

Round-3 shared-runtime review, two P2 findings on the transport-passenger
clip (Movement/Spline/PassengerSplineCollision.h, MoveSplineInit.cpp):

1. The forward rays searched only the segment length while the body stops
   its collision radius short of a hit. A wall just past a short segment's
   end, within the radius of it, was missed: radius 0.389, wall 0.5 yd
   ahead, a 0.2 yd move came back Clear and left the body 0.3 yd from the
   wall. The rays now reach the radius past the end; travel stays capped at
   the requested length.
2. The sweep proves the straight segments between the path's points, but a
   Catmullrom spline through the same points is a curve: control points
   (10,0), (0.5,1), (0.5,2), (10,3) are swept Clear against a wall at x=0,
   and the curve reaches x=-0.6875 between the middle two. A swept spline is
   now emitted with linear interpolation (EmitProvedPath), so the server
   walks exactly the polyline that was proved, at no extra ray cost.

Both are checked against a synthetic wall (no elevator model needed); the
trajectory check runs the REAL Movement::MoveSpline (MoveSpline.cpp,
Spline.cpp and MovementUtil.cpp compiled as they are), with G3D's own
Matrix4 constructor and Vector4 * Matrix4 product, which the Catmull-Rom
evaluator multiplies by.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests.test_bot_native_fall_spline_state import STUB_CREATURE, STUB_LOG


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
SPLINE = GAME / "Movement/Spline"
HEADER = SPLINE / "PassengerSplineCollision.h"
LAUNCH = SPLINE / "MoveSplineInit.cpp"
G3D_SOURCE = ROOT / "dep/g3dlite/source"

WALL = r'''
#include "Movement/Spline/PassengerSplineCollision.h"

#include <G3D/Vector3.h>

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <vector>

using namespace Movement::PassengerCollision;
using G3D::Vector3;

static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

struct Tri { Vector3 a, b, c; };
// A wall in the plane x = 0, facing +x, tall and wide enough for every ray.
static std::vector<Tri> const mesh{
    { { 0, -50, -50 }, { 0, 50, -50 }, { 0, 50, 50 } },
    { { 0, -50, -50 }, { 0, 50, 50 }, { 0, -50, 50 } },
};
static float longestSearch = 0.0f;
static int rays = 0;

// WorldModel IntersectTriangle, two-sided; every triangle, so the nearest.
static float Nearest(Vector3 const& o, Vector3 const& d, float maxDistance)
{
    ++rays;
    longestSearch = std::max(longestSearch, maxDistance);
    float best = maxDistance;
    bool hit = false;
    for (Tri const& t : mesh)
    {
        Vector3 const e1 = t.b - t.a, e2 = t.c - t.a, p = d.cross(e2);
        float const det = e1.dot(p);
        if (std::fabs(det) < 1e-5f)
            continue;
        float const f = 1.0f / det;
        Vector3 const s = o - t.a;
        float const u = f * s.dot(p);
        if (u < 0.0f || u > 1.0f)
            continue;
        Vector3 const q = s.cross(e1);
        float const v = f * d.dot(q);
        if (v < 0.0f || u + v > 1.0f)
            continue;
        float const distance = f * e2.dot(q);
        if (distance > 0.0f && distance < best)
        {
            best = distance;
            hit = true;
        }
    }
    return hit ? best : -1.0f;
}

static float const Radius = 0.389f;   // DEFAULT_PLAYER_BOUNDING_RADIUS
static float const Height = 2.0313f;  // a human male's collision height
'''

BODY_PROGRAM = WALL + r'''
static std::vector<Vector3> Emit(std::vector<Vector3> path, Result& r)
{
    r = ClipPath(path, Radius, Height, Nearest);
    if (r.Kind == Verdict::Blocked)
        return { path.front() };
    ApplyClip(path, r);
    return path;
}

int main()
{
    // The review's reproduction: wall 0.5 yd ahead, a 0.2 yd move. The
    // requested end is 0.3 yd from the wall, inside the body's radius.
    {
        Result r;
        longestSearch = 0.0f;
        std::vector<Vector3> const emitted = Emit({ { 0.5f, 0, 0 }, { 0.3f, 0, 0 } }, r);
        std::printf("short_move kind=%d kept=%.3f end_x=%.3f\n", int(r.Kind), r.KeptYards, emitted.back().x);
        CHECK(r.Kind == Verdict::Clipped);
        CHECK(std::fabs(r.KeptYards - 0.111f) < 1e-3f);
        CHECK(emitted.back().x >= Radius - 1e-3f);
        // The rays reach the radius past the end, and no further.
        CHECK(std::fabs(longestSearch - (0.2f + Radius)) < 1e-4f);
    }
    // Negative control: the longer move toward the same wall clipped at
    // 0.111 yd before the fix already, and still does.
    {
        Result r;
        std::vector<Vector3> const emitted = Emit({ { 0.5f, 0, 0 }, { -0.5f, 0, 0 } }, r);
        std::printf("long_move kind=%d kept=%.3f end_x=%.3f\n", int(r.Kind), r.KeptYards, emitted.back().x);
        CHECK(r.Kind == Verdict::Clipped);
        CHECK(std::fabs(r.KeptYards - 0.111f) < 1e-3f);
    }
    // A short move whose end keeps the radius from the wall is unchanged:
    // the longer search never lets the body travel past the requested end.
    {
        Result r;
        std::vector<Vector3> const path{ { 1.0f, 0, 0 }, { 0.8f, 0, 0 } };
        rays = 0;
        std::vector<Vector3> const emitted = Emit(path, r);
        CHECK(r.Kind == Verdict::Clear);
        CHECK(emitted.size() == 2 && emitted.back() == path.back());
        CHECK(std::fabs(r.KeptYards - 0.2f) < 1e-4f);
        // The cost is unchanged: 5 lifts x (centre + 4 sides x (probe +
        // forward)) = 45 rays per segment; only the forward reach grew.
        std::printf("rays_per_segment=%d\n", rays);
        CHECK(Lifts(Height).size() == 5 && rays == 45);
    }
    // A navmesh corner 0.3 yd off the wall, then along it: the corner itself
    // overlaps the wall, so the path ends the radius short of it.
    {
        Result r;
        std::vector<Vector3> const emitted = Emit({ { 2.0f, 0, 0 }, { 0.3f, 0, 0 }, { 0.3f, 5.0f, 0 } }, r);
        std::printf("corner kind=%d points=%zu end_x=%.3f\n", int(r.Kind), emitted.size(), emitted.back().x);
        CHECK(r.Kind == Verdict::Clipped);
        CHECK(emitted.size() == 2);
        for (Vector3 const& point : emitted)
            CHECK(point.x >= Radius - 1e-3f);
    }
    // Every start and move length toward the wall: no emitted end inside
    // the radius, and nothing clipped whose requested end keeps it.
    int cases = 0, clear = 0, clipped = 0, blocked = 0;
    for (int start = 40; start <= 300; start += 5)
    {
        for (int move = 10; move <= 250; move += 5)
        {
            float const x0 = start / 100.0f, x1 = x0 - move / 100.0f;
            Result r;
            std::vector<Vector3> const emitted = Emit({ { x0, 0, 0 }, { x1, 0, 0 } }, r);
            ++cases;
            clear += r.Kind == Verdict::Clear;
            clipped += r.Kind == Verdict::Clipped;
            blocked += r.Kind == Verdict::Blocked;
            if (r.Kind != Verdict::Blocked)
                CHECK(emitted.back().x >= Radius - 1e-3f);
            if (x1 > Radius + 1e-3f)
                CHECK(r.Kind == Verdict::Clear && emitted.back().x == x1);
            else
                CHECK(r.Kind != Verdict::Clear);
        }
    }
    std::printf("sweep cases=%d clear=%d clipped=%d blocked=%d\n", cases, clear, clipped, blocked);
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''

TRAJECTORY_PROGRAM = WALL + r'''
#include "MoveSpline.h"
#include "Errors.h"
#include <G3D/Matrix4.h>
#include <G3D/Vector4.h>
#include <cstdlib>

// Link stubs: assertions abort.
namespace Trinity
{
void Assert(char const*, int, char const*, char const*) { std::abort(); }
void Assert(char const*, int, char const*, char const*, char const*, ...) { std::abort(); }
void Abort(char const*, int, char const*) { std::abort(); }
void Abort(char const*, int, char const*, char const*, ...) { std::abort(); }
}
// G3D's own definitions (dep/g3dlite/source/Matrix4.cpp, Vector4.cpp): the
// Catmull-Rom evaluator (Spline.cpp C_Evaluate) multiplies by them.
G3D::Matrix4::Matrix4(
    float r1c1, float r1c2, float r1c3, float r1c4,
    float r2c1, float r2c2, float r2c3, float r2c4,
    float r3c1, float r3c2, float r3c3, float r3c4,
    float r4c1, float r4c2, float r4c3, float r4c4) {
    elt[0][0] = r1c1;  elt[0][1] = r1c2;  elt[0][2] = r1c3;  elt[0][3] = r1c4;
    elt[1][0] = r2c1;  elt[1][1] = r2c2;  elt[1][2] = r2c3;  elt[1][3] = r2c4;
    elt[2][0] = r3c1;  elt[2][1] = r3c2;  elt[2][2] = r3c3;  elt[2][3] = r3c4;
    elt[3][0] = r4c1;  elt[3][1] = r4c2;  elt[3][2] = r4c3;  elt[3][3] = r4c4;
}
G3D::Vector4 G3D::Vector4::operator*(const G3D::Matrix4& M) const {
    Vector4 result;
    for (int i = 0; i < 4; ++i) {
        result[i] = 0.0f;
        for (int j = 0; j < 4; ++j) {
            result[i] += (*this)[j] * M[j][i];
        }
    }
    return result;
}

// Distance of p from the polyline through the path's points.
static float OffPolyline(std::vector<Vector3> const& path, Vector3 const& p)
{
    float best = 1e9f;
    for (std::size_t i = 0; i + 1 < path.size(); ++i)
    {
        Vector3 const a = path[i], ab = path[i + 1] - path[i];
        float const t = std::clamp((p - a).dot(ab) / std::max(ab.squaredLength(), 1e-12f), 0.0f, 1.0f);
        best = std::min(best, (a + ab * t - p).length());
    }
    return best;
}

struct Walk { float MinX = 1e9f; float MaxOff = 0.0f; int Samples = 0; };

// The positions the server moves the unit through (MoveSpline::
// ComputePosition), every 5 ms of the spline.
static Walk Walked(Movement::MoveSplineInitArgs const& args, std::vector<Vector3> const& polyline)
{
    Movement::MoveSpline spline;
    spline.Initialize(args);
    Walk walk;
    for (int32 t = 0; t <= spline.Duration(); t += 5)
    {
        Movement::Location const p = spline.ComputePosition(t);
        walk.MinX = std::min(walk.MinX, p.x);
        walk.MaxOff = std::max(walk.MaxOff, OffPolyline(polyline, Vector3(p.x, p.y, p.z)));
        ++walk.Samples;
    }
    return walk;
}

static Movement::MoveSplineInitArgs SmoothArgs(std::vector<Vector3> const& path)
{
    Movement::MoveSplineInitArgs args;
    args.path.assign(path.begin(), path.end());
    args.velocity = 7.0f;
    Vector3 const first = path[1] - path[0];
    args.initialOrientation = std::atan2(first.y, first.x);
    args.flags.Catmullrom = true; // MoveSplineInit::SetSmooth
    return args;
}

int main()
{
    // The review's reproduction: every straight segment is clear of the wall
    // by more than the body's radius.
    std::vector<Vector3> const bend{ { 10, 0, 0 }, { 0.5f, 1, 0 }, { 0.5f, 2, 0 }, { 10, 3, 0 } };
    Result const proof = ClipPath(bend, Radius, Height, Nearest);
    CHECK(proof.Kind == Verdict::Clear);

    // Negative control, the emission before the fix (the clip applied, the
    // Catmull-Rom interpolation kept): the unit walks through the wall.
    {
        Movement::MoveSplineInitArgs args = SmoothArgs(bend);
        ApplyClip(args.path, proof);
        CHECK(args.flags.isSmooth());
        Walk const walk = Walked(args, bend);
        std::printf("catmullrom min_x=%.4f max_off=%.4f samples=%d\n", walk.MinX, walk.MaxOff, walk.Samples);
        CHECK(walk.MinX < -0.6f);
    }
    // The emission now: exactly the proved polyline, the body clear of the
    // wall at every sample.
    {
        Movement::MoveSplineInitArgs args = SmoothArgs(bend);
        EmitProvedPath(args, proof);
        CHECK(args.flags.isLinear());
        CHECK(args.path.size() == bend.size());
        for (std::size_t i = 0; i < bend.size(); ++i)
            CHECK(args.path[i] == bend[i]);
        Walk const walk = Walked(args, bend);
        std::printf("proved min_x=%.4f max_off=%.4f samples=%d\n", walk.MinX, walk.MaxOff, walk.Samples);
        CHECK(walk.MaxOff < 1e-3f);
        CHECK(walk.MinX >= 0.5f - 1e-3f);
        CHECK(walk.MinX >= Radius);
    }
    // A clipped smooth path: truncated at the wall and walked straight.
    {
        std::vector<Vector3> const through{ { 10, 0, 0 }, { 3, 1, 0 }, { -2, 2, 0 }, { 5, 8, 0 } };
        Result const clip = ClipPath(through, Radius, Height, Nearest);
        CHECK(clip.Kind == Verdict::Clipped && clip.LastSegment == 1);
        Movement::MoveSplineInitArgs args = SmoothArgs(through);
        EmitProvedPath(args, clip);
        CHECK(args.flags.isLinear());
        CHECK(args.path.size() == 3);
        std::vector<Vector3> const kept(args.path.begin(), args.path.end());
        Walk const walk = Walked(args, kept);
        std::printf("clipped min_x=%.4f max_off=%.4f\n", walk.MinX, walk.MaxOff);
        CHECK(walk.MaxOff < 1e-3f);
        CHECK(walk.MinX >= Radius - 1e-3f);
    }
    // A linear spline stays linear; no other flag changes.
    {
        Movement::MoveSplineInitArgs args;
        args.path.assign(bend.begin(), bend.end());
        args.flags.Flying = true;
        args.flags.UncompressedPath = true;
        Movement::MoveSplineFlag const before = args.flags;
        EmitProvedPath(args, proof);
        CHECK(args.flags.Raw == before.Raw);
    }
    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run(tmp_path: Path, program: str, sources: list[Path]) -> str:
    stub = tmp_path / "stub"
    stub.mkdir()
    (stub / "Log.h").write_text(STUB_LOG)
    (stub / "Creature.h").write_text(STUB_CREATURE)
    source = tmp_path / "program.cpp"
    source.write_text(program)
    binary = tmp_path / "program"
    includes = [stub, GAME, SPLINE, GAME / "Entities/Object", GAME / "Entities/Object/Updates",
                ROOT / "src/common", ROOT / "src/common/Utilities", ROOT / "src/common/Debugging",
                ROOT / "src/common/Logging", ROOT / "dep/g3dlite/include", ROOT / "dep/fmt/include"]
    command = ["g++", "-std=c++20", "-O1", "-Wall", "-Wextra", "-ffunction-sections", "-fdata-sections"]
    for include in includes:
        command += ["-I", str(include)]
    command += [str(source)] + [str(path) for path in sources]
    subprocess.run(command + ["-Wl,--gc-sections", "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


def test_a_short_segment_cannot_end_with_the_body_in_a_wall_past_it(tmp_path: Path) -> None:
    out = _compile_and_run(tmp_path, BODY_PROGRAM, [])
    assert "short_move kind=1 kept=0.111 end_x=0.389" in out, out
    assert "long_move kind=1 kept=0.111" in out, out
    assert "rays_per_segment=45" in out, out
    assert "failures=0" in out, out


def test_a_swept_smooth_spline_is_walked_along_the_proved_polyline(tmp_path: Path) -> None:
    out = _compile_and_run(tmp_path, TRAJECTORY_PROGRAM,
                           [SPLINE / name for name in ("MoveSpline.cpp", "Spline.cpp", "MovementUtil.cpp")])
    # The negative control reproduced the review's crossing (x = -0.6875).
    match = re.search(r"catmullrom min_x=(-?\d+\.\d+)", out)
    assert match and float(match.group(1)) == pytest.approx(-0.6875, abs=0.01), out
    assert "failures=0" in out, out


def test_the_g3d_definitions_compiled_above_are_g3d_own() -> None:
    matrix = (G3D_SOURCE / "Matrix4.cpp").read_text(encoding="utf-8")
    vector = (G3D_SOURCE / "Vector4.cpp").read_text(encoding="utf-8")
    assert "elt[0][0] = r1c1;  elt[0][1] = r1c2;  elt[0][2] = r1c3;  elt[0][3] = r1c4;" in matrix
    assert "elt[3][0] = r4c1;  elt[3][1] = r4c2;  elt[3][2] = r4c3;  elt[3][3] = r4c4;" in matrix
    assert "result[i] += (*this)[j] * M[j][i];" in vector
    # The server picks the evaluator by isSmooth(), which is the Catmullrom
    # flag alone: clearing it is what makes the server walk straight.
    move_spline = (SPLINE / "MoveSpline.cpp").read_text(encoding="utf-8")
    assert move_spline.count("modes[args.flags.isSmooth()]") == 2
    flags = (SPLINE / "MoveSplineFlag.h").read_text(encoding="utf-8")
    assert "constexpr bool isSmooth() const { return Raw.HasFlag(MoveSplineFlagEnum::Catmullrom); }" in flags


def _code(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_launch_emits_the_proved_path_for_swept_passenger_splines_only() -> None:
    code = _code(LAUNCH)
    clip = code[code.index("PassengerClip ClipPassengerSpline("):code.index("namespace Movement\n{")]
    # Every swept, emitted path (Clear or Clipped) goes out as proved; a
    # blocked one is refused first, and the scope and collision-disabled
    # exits return before the sweep, leaving their splines untouched.
    order = [clip.index("return PassengerClip::NotApplicable;"),
             clip.index("if (!object->m_model->isCollisionEnabled())\n            return PassengerClip::Emitted;"),
             clip.index("Movement::PassengerWalk::ProveWalk(world, radius,"),
             clip.index("if (settled.SweepBlocked)"),
             clip.index("if (proved.Kind == Verdict::Blocked)"),
             clip.index("EmitProvedPath(args, proved);"),
             clip.rindex("return PassengerClip::Emitted;")]
    assert order == sorted(order)
    assert code.count("EmitProvedPath(") == 1 and "ApplyClip(" not in code
    header = _code(HEADER)
    emit = header[header.index("void EmitProvedPath("):]
    emit = emit[:emit.index("\n}\n")]
    assert "ApplyClip(args.path, result);" in emit and "args.flags.Catmullrom = false;" in emit

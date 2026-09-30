"""A transport passenger's server spline respects its transport's collision.

BWD 10N round 2 (round 3 handoff, E2): the rogue (3 of 3 runs) and both
tanks (2 of 3) sat inside the hollow pillar shafts of the Nefarian elevator
(GO 207834), within 1.5 yd of a pillar centre at local z 3-4. A passenger's
chase or point path is built on the static navmesh, which holds no
gameobject model; WorldObject::UpdateAllowedPositionZ returns at once for a
passenger ("TODO: Allow transports to be part of dynamic vmap tree"), and
MoveSplineInit moved those world points into the transport frame with no
collision test, so the spline walked through the pillar wall or top.

MoveSplineInit::Launch now sweeps a player passenger's emitted path against
its own transport's model (Movement/Spline/PassengerSplineCollision.h) and
ends it at the first surface in its way. The pure clip is compiled here
against the elevator's own collision model (the vmo port of
tests/test_nefarian_ledge_drop_floor_query.py, nearest hit on every
triangle, which is GameObjectModel::intersectRay without stopAtFirstHit) and
the plan's own shaft test (BotNefarianPlatformBody.h InsidePillarShaft).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from tests import test_nefarian_ledge_drop_floor_query as vmo
from tests.test_nefarian_strategy import INCLUDES


ROOT = Path(__file__).resolve().parents[1]
GAME = ROOT / "src/server/game"
HEADER = GAME / "Movement/Spline/PassengerSplineCollision.h"
LAUNCH = GAME / "Movement/Spline/MoveSplineInit.cpp"


def _triangles_file(tmp_path: Path) -> Path:
    groups, _ = vmo._model()
    lines = []
    for group in groups:
        if group is None:
            continue
        verts, tris, _ = group
        for a, b, c in tris:
            lines.append(" ".join(f"{v:.6f}" for v in (*verts[a], *verts[b], *verts[c])))
    path = tmp_path / "elevator_triangles.txt"
    path.write_text(f"{len(lines)}\n" + "\n".join(lines) + "\n")
    return path


PROGRAM = r'''
#include "Movement/Spline/PassengerSplineCollision.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPlatformBody.h"

#include <cmath>
#include <cstdio>
#include <fstream>
#include <string>
#include <vector>

using namespace Movement::PassengerCollision;
using BotEncounter::Nefarian::InsidePillarShaft;
using BotEncounter::Nefarian::LocalPoint;
using BotEncounter::Nefarian::PillarCenters;
using BotEncounter::Nefarian::PlatformFrame;
using BotEncounter::Nefarian::PillarShaftRadius;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

struct V { float x, y, z; };
struct Tri { V a, b, c; };
static std::vector<Tri> mesh;
static int failures = 0;
#define CHECK(c) do { if (!(c)) { std::fprintf(stderr, "FAIL %d %s\n", __LINE__, #c); ++failures; } } while (0)

static V Sub(V p, V q) { return { p.x - q.x, p.y - q.y, p.z - q.z }; }
static V Cross(V p, V q) { return { p.y * q.z - p.z * q.y, p.z * q.x - p.x * q.z, p.x * q.y - p.y * q.x }; }
static float Dot(V p, V q) { return p.x * q.x + p.y * q.y + p.z * q.z; }
static float Len(V p) { return std::sqrt(Dot(p, p)); }

// WorldModel IntersectTriangle, two-sided; every triangle, so the nearest.
static bool TriangleHit(V o, V d, Tri const& t, float& dist)
{
    V const e1 = Sub(t.b, t.a), e2 = Sub(t.c, t.a), p = Cross(d, e2);
    float const det = Dot(e1, p);
    if (std::fabs(det) < 1e-5f)
        return false;
    float const f = 1.0f / det;
    V const s = Sub(o, t.a);
    float const u = f * Dot(s, p);
    if (u < 0.0f || u > 1.0f)
        return false;
    V const q = Cross(s, e1);
    float const v = f * Dot(d, q);
    if (v < 0.0f || u + v > 1.0f)
        return false;
    float const hit = f * Dot(e2, q);
    if (hit > 0.0f && hit < dist)
    {
        dist = hit;
        return true;
    }
    return false;
}

static bool collision = true;
static float Nearest(V const& o, V const& d, float maxDistance)
{
    if (!collision)
        return -1.0f;
    float dist = maxDistance;
    bool hit = false;
    for (Tri const& t : mesh)
        hit = TriangleHit(o, d, t, dist) || hit;
    return hit ? dist : -1.0f;
}

// Every surface crossing of the straight line (not only the nearest).
static int Crossings(V a, V b)
{
    V const d0 = Sub(b, a);
    float const length = Len(d0);
    if (length < 1e-4f)
        return 0;
    V const d{ d0.x / length, d0.y / length, d0.z / length };
    int count = 0;
    for (Tri const& t : mesh)
    {
        float dist = length;
        if (TriangleHit(a, d, t, dist))
            ++count;
    }
    return count;
}

static float SurfaceBelow(float x, float y, float fromZ)
{
    float const hit = Nearest({ x, y, fromZ }, { 0.0f, 0.0f, -1.0f }, 60.0f);
    return hit < 0.0f ? -1000.0f : fromZ - hit;
}

static float const Radius = 0.389f;
static float const Height = 2.0313f; // a human male's collision height

static std::vector<V> Emit(std::vector<V> path, Result* out = nullptr)
{
    Result const r = ClipPath(path, Radius, Height, Nearest);
    if (out)
        *out = r;
    if (r.Kind == Verdict::Blocked)
        return { path.front() };
    ApplyClip(path, r);
    return path;
}

// What a client could not do along the emitted path: stand inside a shaft,
// or pass through any surface at the knee or above.
static int Violations(std::vector<V> const& emitted)
{
    int bad = 0;
    for (std::size_t i = 0; i + 1 < emitted.size(); ++i)
    {
        V const a = emitted[i], b = emitted[i + 1];
        float const length = Len(Sub(b, a));
        int const steps = std::max(1, int(std::ceil(length / 0.1f)));
        for (int s = 0; s <= steps; ++s)
        {
            float const t = float(s) / float(steps);
            V const p{ a.x + (b.x - a.x) * t, a.y + (b.y - a.y) * t, a.z + (b.z - a.z) * t };
            if (InsidePillarShaft(LocalPoint{ p.x, p.y }, p.z))
                ++bad;
        }
        for (float lift : Lifts(Height))
            bad += Crossings({ a.x, a.y, a.z + lift }, { b.x, b.y, b.z + lift });
    }
    if (emitted.size() == 1 && InsidePillarShaft(LocalPoint{ emitted[0].x, emitted[0].y }, emitted[0].z))
        ++bad;
    return bad;
}

struct Recorded { int Pillar; float Dx, Dy, Z; };
// test_nefarian_stranded.py / test_nefarian_hop_ownership.py (round 2 live).
static Recorded const recorded[] = {
    { 0, 0.9f, 0.6f, 3.4f }, { 0, -1.2f, 0.4f, 3.9f }, { 2, 1.0f, -0.8f, 3.1f },
    { 2, -0.5f, 1.3f, 4.0f }, { 0, 1.1f, 0.3f, 3.5f }, { 2, -0.4f, 1.2f, 3.2f },
    { 2, 0.2f, -1.4f, 3.9f },
};

static std::vector<std::vector<V>> RoundTwoPaths()
{
    std::vector<std::vector<V>> paths;
    float const magma = 9.64f;     // MagmaSurfaceZ at the lowered stop, local
    float const swimZ = magma - 1.2f;
    for (Recorded const& r : recorded)
    {
        LocalPoint const c = PillarCenters[r.Pillar];
        V const inside{ c.X + r.Dx, c.Y + r.Dy, r.Z };
        float const h = std::atan2(r.Dy, r.Dx);
        auto at = [&](float radius, float z) { return V{ c.X + radius * std::cos(h), c.Y + radius * std::sin(h), z }; };
        // From the pillar top, toward the recorded point below it.
        V const top = at(2.5f, SurfaceBelow(at(2.5f, 0).x, at(2.5f, 0).y, 30.0f));
        paths.push_back({ top, inside });
        // From the lowered floor beyond the skirt.
        V const floorOut = at(9.0f, SurfaceBelow(at(9.0f, 0).x, at(9.0f, 0).y, 5.0f));
        paths.push_back({ floorOut, inside });
        // From the swim station (a swimmer that boarded, as the rogue did).
        paths.push_back({ at(6.7f, swimZ), inside });
        // A chase target across the pillar: floor to floor through it.
        V const across = V{ c.X - 9.0f * std::cos(h), c.Y - 9.0f * std::sin(h), 0.0f };
        paths.push_back({ floorOut, V{ across.x, across.y, SurfaceBelow(across.x, across.y, 5.0f) } });
        // A navmesh path with a corner inside the pillar (two segments).
        paths.push_back({ floorOut, inside, top });
    }
    return paths;
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
        in >> t.a.x >> t.a.y >> t.a.z >> t.b.x >> t.b.y >> t.b.z >> t.c.x >> t.c.y >> t.c.z;
    CHECK(count > 100);

    std::vector<std::vector<V>> const paths = RoundTwoPaths();
    // Negative control: without the transport's collision, the round-2
    // paths enter the shaft and pass through the pillar.
    collision = false;
    int unclipped = 0, unclippedPaths = 0;
    for (std::vector<V> const& path : paths)
    {
        int const v = Violations(path);
        unclipped += v;
        unclippedPaths += v > 0;
        CHECK(Emit(path).size() == path.size());
    }
    collision = true;
    CHECK(unclippedPaths == int(paths.size()));
    std::printf("unclipped_paths_with_violations=%d/%zu samples=%d\n", unclippedPaths, paths.size(),
        unclipped);

    // With it: every emitted path stops outside the wall; nothing enters.
    int clipped = 0, blocked = 0;
    for (std::vector<V> const& path : paths)
    {
        Result r;
        std::vector<V> const emitted = Emit(path, &r);
        CHECK(r.Kind != Verdict::Clear);
        clipped += r.Kind == Verdict::Clipped;
        blocked += r.Kind == Verdict::Blocked;
        CHECK(Violations(emitted) == 0);
        V const end = emitted.back();
        float const toCentre = std::hypot(end.x - PillarCenters[0].X, end.y - PillarCenters[0].Y);
        float const toCentre2 = std::hypot(end.x - PillarCenters[2].X, end.y - PillarCenters[2].Y);
        CHECK(std::min(toCentre, toCentre2) > PillarShaftRadius || end.z > PlatformFrame::PillarTopLocalZ - 0.6f);
    }
    std::printf("clipped=%d blocked=%d\n", clipped, blocked);

    // Already inside (the recorded positions): no emitted movement leaves
    // the shaft on any heading, up included (the top closes it at 9.925).
    for (Recorded const& r : recorded)
    {
        LocalPoint const c = PillarCenters[r.Pillar];
        V const inside{ c.X + r.Dx, c.Y + r.Dy, r.Z };
        for (int heading = 0; heading < 360; heading += 20)
        {
            float const h = float(heading) * 3.14159265f / 180.0f;
            for (float rise : { -3.0f, 0.0f, 3.0f, 8.0f })
            {
                std::vector<V> const emitted = Emit({ inside,
                    V{ inside.x + 12.0f * std::cos(h), inside.y + 12.0f * std::sin(h), inside.z + rise } });
                V const end = emitted.back();
                // Inside the wall (the model closes the shaft within 7 yd on
                // every heading, test_nefarian_ledge_drop_floor_query.py).
                CHECK(std::hypot(end.x - c.X, end.y - c.Y) < 7.0f);
                CHECK(Crossings({ inside.x, inside.y, inside.z + 0.5f }, { end.x, end.y, end.z + 0.5f }) == 0);
                CHECK(end.z < PlatformFrame::PillarTopLocalZ);
            }
        }
        std::vector<V> const up = Emit({ inside, V{ inside.x, inside.y, inside.z + 20.0f } });
        CHECK(up.back().z < PlatformFrame::PillarTopLocalZ);
        // The magma (9.64 local at the lowered stop) lies under the top.
        float const ceiling = inside.z + Nearest(inside, { 0.0f, 0.0f, 1.0f }, 50.0f);
        CHECK(std::fabs(ceiling - PlatformFrame::PillarTopLocalZ) < 0.01f && ceiling > 9.64f);
    }

    // Unchanged where nothing is in the way: the open lowered floor, a walk
    // across a pillar top, a zero-length turn, a single point.
    auto onFloor = [](float x, float y) { return V{ x, y, SurfaceBelow(x, y, 5.0f) }; };
    for (std::vector<V> const& path : std::vector<std::vector<V>>{
             { onFloor(0.0f, 0.0f), onFloor(10.0f, 0.0f) },
             { onFloor(-5.0f, 5.0f), onFloor(5.0f, 12.0f), onFloor(15.0f, 12.0f) },
             { V{ PillarCenters[1].X - 2.0f, PillarCenters[1].Y, PlatformFrame::PillarTopLocalZ },
               V{ PillarCenters[1].X + 2.0f, PillarCenters[1].Y, PlatformFrame::PillarTopLocalZ } },
             { onFloor(3.0f, 3.0f), onFloor(3.0f, 3.0f) } })
    {
        Result r;
        std::vector<V> const emitted = Emit(path, &r);
        CHECK(r.Kind == Verdict::Clear);
        CHECK(emitted.size() == path.size());
        for (std::size_t i = 0; i < path.size(); ++i)
            CHECK(Len(Sub(emitted[i], path[i])) == 0.0f);
    }

    // A member standing against the pillar wall may walk away from it (the
    // side rays that start behind the wall say nothing about moving on) but
    // not into it.
    for (int pillar = 0; pillar < 3; ++pillar)
    {
        LocalPoint const c = PillarCenters[pillar];
        float const h = std::atan2(-c.Y, -c.X); // toward the platform centre
        V const out = onFloor(c.X + 9.0f * std::cos(h), c.Y + 9.0f * std::sin(h));
        Result first;
        std::vector<V> const toWall = Emit({ out, V{ c.X, c.Y, out.z } }, &first);
        CHECK(first.Kind == Verdict::Clipped);
        V const against = toWall.back();
        Result away;
        Emit({ against, out }, &away);
        CHECK(away.Kind == Verdict::Clear);
        Result into;
        Emit({ against, V{ c.X, c.Y, against.z } }, &into);
        CHECK(into.Kind == Verdict::Blocked);
        std::vector<V> const tangent = Emit({ against,
            V{ against.x - 3.0f * std::sin(h), against.y + 3.0f * std::cos(h), against.z } });
        CHECK(Violations(tangent) == 0);
    }

    // No step-by-step sinking: a spline launched from where a clipped
    // descent through the top ended goes no deeper.
    {
        LocalPoint const c = PillarCenters[2];
        V start{ c.X + 2.0f, c.Y, SurfaceBelow(c.X + 2.0f, c.Y, 30.0f) };
        V const below{ c.X, c.Y + 1.0f, 3.5f };
        for (int launch = 0; launch < 20; ++launch)
        {
            std::vector<V> const emitted = Emit({ start, below });
            start = emitted.back();
        }
        // Under the knee height, inside the executor's floor tolerance.
        CHECK(start.z > PlatformFrame::PillarTopLocalZ - FirstLiftYards);
        CHECK(!InsidePillarShaft(LocalPoint{ start.x, start.y }, start.z));
        // Feet already 0.55 yd under the top (within the floor tolerance;
        // the first knee ray starts under the surface): the higher rays
        // still keep the member from going deeper, into the shaft.
        V const sunk{ c.X + 2.0f, c.Y, SurfaceBelow(c.X + 2.0f, c.Y, 30.0f) - 0.55f };
        CHECK(!InsidePillarShaft(LocalPoint{ sunk.x, sunk.y }, sunk.z));
        for (V const& target : { below, V{ c.X - 1.0f, c.Y, 6.0f }, V{ c.X + 2.0f, c.Y + 0.5f, 3.0f } })
        {
            std::vector<V> const emitted = Emit({ sunk, target });
            CHECK(Violations(emitted) == 0);
            CHECK(emitted.back().z > sunk.z - 0.1f);
        }
    }

    // The clip keeps a spline launchable: a clipped tail under a spline
    // segment's minimum ends the path at its last whole point.
    {
        std::vector<V> path{ { 0, 0, 0 }, { 5, 0, 0 }, { 10, 0, 0 } };
        Result r;
        r.Kind = Verdict::Clipped; r.LastSegment = 1; r.EndFraction = 0.01f;
        ApplyClip(path, r);
        CHECK(path.size() == 2 && path.back().x == 5.0f);
        std::vector<V> path2{ { 0, 0, 0 }, { 5, 0, 0 }, { 10, 0, 0 } };
        r.EndFraction = 0.5f;
        ApplyClip(path2, r);
        CHECK(path2.size() == 3 && path2.back().x == 7.5f);
    }

    std::printf("failures=%d\n", failures);
    return failures ? 1 : 0;
}
'''


def _compile_and_run(tmp_path: Path, triangles: Path) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(PROGRAM)
    command = ["g++", "-std=c++17", "-O1", "-Wall", "-Wextra", "-Werror", "-I", str(GAME)]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    run = subprocess.run([str(binary), str(triangles)], cwd=ROOT, capture_output=True, text=True)
    assert run.returncode == 0, run.stdout + run.stderr
    return run.stdout


def test_round_two_paths_stop_at_the_pillar_and_nothing_else_changes(tmp_path: Path) -> None:
    out = _compile_and_run(tmp_path, _triangles_file(tmp_path))
    # The negative control ran: every replayed path violates without the clip.
    assert "unclipped_paths_with_violations=35/35" in out, out
    assert "failures=0" in out, out


def _code(path: Path) -> str:
    text = re.sub(r"//[^\n]*", "", path.read_text(encoding="utf-8"))
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def test_launch_clips_the_emitted_path_of_player_passengers_only() -> None:
    code = _code(LAUNCH)
    clip = code[code.index("PassengerClip ClipPassengerSpline("):code.index("namespace Movement\n{")]
    # Scope: player passengers of a gameobject transport, not a vehicle
    # seat; the effects' own trajectories are left alone.
    assert "if (!unit->IsPlayer() || unit->GetVehicle() || !unit->GetTransport())\n" \
        "            return PassengerClip::NotApplicable;" in clip
    assert "args.flags.Falling || args.flags.Parabolic || args.flags.Animation" in clip
    # Fail closed on an unresolved transport or model.
    assert clip.index("if (!object || !object->m_model)") < clip.index("return PassengerClip::Refused;")
    # Nearest hit (not the BIH's first), in world space at the transport's
    # current position, with the unit's own radius and height.
    assert "transport->CalculatePassengerPosition(point.x, point.y, point.z);" in clip
    assert "distance,\n                false, phase, VMAP::ModelIgnoreFlags::Nothing)" in clip
    assert "float const radius = unit->GetFloatValue(UNIT_FIELD_BOUNDINGRADIUS);" in clip
    # (the sweep and the body proof are one pure ProveWalk: PassengerWalkProof.h)
    assert "ProveWalk(world, radius, unit->GetCollisionHeight(), nearestHit, blocked);" in " ".join(clip.split())
    # Clipped or not, the swept spline is emitted as proved (linear;
    # tests/test_passenger_spline_trajectory.py) once the body is proved along
    # it (tests/test_passenger_walk_body_clearance.py).
    assert "EmitProvedPath(args, proved);" in clip

    launch = code[code.index("int32 MoveSplineInit::Launch()"):code.index("void MoveSplineInit::Stop()")]
    # The final path is swept: after the first vertex is corrected to where
    # the unit is now, before validation, initialization and the packet.
    order = [launch.index("args.path[0] = real_position;"),
             launch.index("if (transport && ClipPassengerSpline(unit, args) == PassengerClip::Refused)"),
             launch.index("args.Validate(unit)"), launch.index("move_spline.Initialize(args);"),
             launch.index("unit->SendMessageToSet(")]
    assert order == sorted(order)
    refused = launch[order[1]:launch.index("return 0;", order[1])]
    assert "unit->StopMoving();" in refused and "recordLaunch(false);" in refused
    # Nothing else in the core path changes for units that are not passengers.
    assert code.count("ClipPassengerSpline(") == 2


def test_pure_header_is_pure_and_matches_the_executor_sweep() -> None:
    header = HEADER.read_text(encoding="utf-8")
    includes = re.findall(r'#include [<"]([^>"]+)[>"]', header)
    assert includes == ["algorithm", "cmath", "cstddef", "vector"]
    approach = (GAME / "Bots/BotValidationRouteNativeApproach.h").read_text(encoding="utf-8")
    for name in ("BodySweepFirstLiftYards = 0.5f", "BodySweepLiftStepYards = 0.35f",
                 "BodySweepSideFractions[] = { 0.0f, 0.5f, -0.5f, 1.0f, -1.0f }"):
        assert name in approach
    for name in ("FirstLiftYards = 0.5f", "LiftStepYards = 0.35f",
                 "SideFractions[] = { 0.0f, 0.5f, -0.5f, 1.0f, -1.0f }"):
        assert name in header
    for path in (HEADER, LAUNCH):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000


@pytest.fixture(autouse=True)
def _model_available() -> None:
    vmo._model()

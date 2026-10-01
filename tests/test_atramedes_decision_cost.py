"""BWD 10N round 4 (Atramedes): the dodge search's per-decision cost, cut without changing a decision.

Live r03 (diag_r3.md question 1) put 1-2.4 s world ticks at the air-phase start and end under host load and
suspected the dodge field and kite-path search (BotAtramedesDodge.h, BotAtramedesKitePath.h). The standalone
benchmark below (``pixi run python -m tests.test_atramedes_decision_cost``) times every strategy decision of the
replay harness's air phases (bombs and fire, 3 seeds, every first target, both spawn delays, both phases), and
again with 250 fire patches left on the ring (a long fight's lingering trails). Round 4 measurements (-O2, one
core, host load about 2):

    replay       air decision mean 5.6 -> 4.5 us, p99 33 -> 20 us, max 93 -> 63 us; 10-bot snapshot mean 71 -> 59 us
    250 patches  air decision mean 21.5 -> 10.4 us, p99 148 -> 49 us, max 339 -> 124 us; snapshot mean 255 -> 126 us

so the strategy's search cannot by itself make a 1 s tick; the live stalls track host contention.
The cuts are exact: a candidate whose score cannot beat the best is skipped before its costly checks (SafeStep,
DetourPoint, LeastCostStep), the cheapest test runs first, a path's zones outside its bounding box are skipped,
and a run that starts outside a circle heading away returns 0 without a square root. The replay outputs
(tests/test_atramedes_raid_sound.py, tests/test_atramedes_kiter_sound_bound.py) are byte-identical before and
after, and the test here holds the optimized search bitwise equal to the round-3 reference on random fields.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tests.test_atramedes_strategy import INCLUDES, ROOT

EQUIVALENCE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include <cassert>
#include <chrono>
#include <cstdio>
#include <cstring>

using namespace BotEncounter;
namespace A = BotEncounter::Atramedes;
namespace D = BotEncounter::Atramedes::Dodge;
namespace G = BotEncounter::Atramedes::Geometry;

// The round-3 search (before the round-4 early exits), verbatim.
namespace Ref
{
inline float SecondsInside(Vector3 const& from, Vector3 const& to, Vector3 const& center, float radius, float speed)
{
    float const dx = to.X - from.X;
    float const dy = to.Y - from.Y;
    float const length = std::sqrt(dx * dx + dy * dy);
    float const fx = from.X - center.X;
    float const fy = from.Y - center.Y;
    if (length < 0.01f)
        return fx * fx + fy * fy <= radius * radius ? 0.25f : 0.0f;
    float const a = length * length;
    float const b = 2.0f * (fx * dx + fy * dy);
    float const c = fx * fx + fy * fy - radius * radius;
    float const discriminant = b * b - 4.0f * a * c;
    if (discriminant <= 0.0f)
        return 0.0f;
    float const root = std::sqrt(discriminant);
    float const enter = std::max(0.0f, (-b - root) / (2.0f * a));
    float const leave = std::min(1.0f, (-b + root) / (2.0f * a));
    return leave > enter ? (leave - enter) * length / std::max(speed, 0.1f) : 0.0f;
}

inline float PathCost(D::Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    float cost = 0.0f;
    for (D::Zone const& zone : field.Zones)
    {
        float const inside = Ref::SecondsInside(from, to, zone.Center,
            zone.Fire ? A::FirePatchRadius + 0.5f : A::SonarBombRadius, speed);
        if (inside > 0.0f)
            cost += zone.Fire ? inside * D::FireSecondYards : D::BombCrossYards;
    }
    return cost;
}

inline std::optional<Vector3> SafeStep(D::Field const& field, ActorSnapshot const& self,
    D::Constraint const& constraint, std::optional<Vector3> const& home = std::nullopt)
{
    float const speed = A::Mobility::RunSpeed(self);
    Vector3 const& from = self.Position;
    std::optional<Vector3> best;
    float bestScore = 0.0f;
    auto consider = [&](Vector3 const& point)
    {
        if (!D::Usable(field, constraint, point))
            return;
        float score = G::Distance2d(from, point) + Ref::PathCost(field, from, point, speed)
            + (home ? 0.25f * G::Distance2d(point, *home) : 0.0f);
        if (!D::DiskSafeWalk(field, from, point, speed))
            score += D::DiskMeetYards;
        if (constraint.RingCenter)
            score += D::RingInnerYards * (constraint.RingMax - G::Distance2d(*constraint.RingCenter, point));
        if (!best || score < bestScore)
        {
            best = point;
            bestScore = score;
        }
    };
    if (constraint.RingCenter)
    {
        float const bearing = G::Bearing(*constraint.RingCenter, from);
        for (float radius : { constraint.RingMax, (constraint.RingMin + constraint.RingMax) / 2.0f,
                 constraint.RingMin })
            for (int step = 0; step <= 45; ++step)
                for (int side : { 1, -1 })
                    consider(G::PointAt(*constraint.RingCenter,
                        bearing + float(side * step) * 4.0f * G::Pi / 180.0f, radius, from.Z));
        return best;
    }
    for (float radius : { 1.5f, 3.0f, 4.5f, 6.0f, 7.5f, 9.0f, 10.5f, 12.0f, 14.0f, 16.0f, 18.0f, 21.0f, 24.0f })
        for (int step = 0; step < 32; ++step)
            consider(G::PointAt(from, float(step) * G::TwoPi / 32.0f, radius, from.Z));
    return best;
}

inline std::optional<Vector3> DetourPoint(D::Field const& field, ActorSnapshot const& self, Vector3 const& destination)
{
    float const speed = A::Mobility::RunSpeed(self);
    if (Ref::PathCost(field, self.Position, destination, speed) <= 0.0f)
        return destination;
    float const remaining = G::Distance2d(self.Position, destination);
    std::optional<Vector3> best;
    float bestScore = 0.0f;
    for (float radius : { 4.0f, 8.0f, 12.0f })
        for (int step = 0; step < 32; ++step)
        {
            Vector3 const point = G::PointAt(self.Position, float(step) * G::TwoPi / 32.0f, radius, self.Position.Z);
            if (!A::ArenaFloor::Solid(point.X, point.Y) || !D::Clear(field, point, 0.0f)
                || Ref::PathCost(field, self.Position, point, speed) > 0.0f
                || G::Distance2d(point, destination) > remaining - D::DetourProgressYards)
                continue;
            float const score = radius + G::Distance2d(point, destination)
                + 0.5f * Ref::PathCost(field, point, destination, speed);
            if (!best || score < bestScore)
            {
                best = point;
                bestScore = score;
            }
        }
    return best;
}

inline Vector3 LeastCostStep(D::Field const& field, ActorSnapshot const& self, Vector3 const& destination)
{
    float const speed = A::Mobility::RunSpeed(self);
    float const remaining = G::Distance2d(self.Position, destination);
    Vector3 best = destination;
    float bestScore = remaining + Ref::PathCost(field, self.Position, destination, speed);
    for (float radius : { 4.0f, 8.0f, 12.0f })
        for (int step = 0; step < 32; ++step)
        {
            Vector3 const point = G::PointAt(self.Position, float(step) * G::TwoPi / 32.0f, radius, self.Position.Z);
            if (!A::ArenaFloor::Solid(point.X, point.Y) || !D::Clear(field, point, 0.0f)
                || G::Distance2d(point, destination) > remaining - D::DetourProgressYards)
                continue;
            float const score = radius + Ref::PathCost(field, self.Position, point, speed)
                + G::Distance2d(point, destination) + 0.5f * Ref::PathCost(field, point, destination, speed);
            if (score < bestScore)
            {
                best = point;
                bestScore = score;
            }
        }
    return best;
}
}

struct Random
{
    uint32 State;
    uint32 Next() { State ^= State << 13; State ^= State >> 17; State ^= State << 5; return State; }
    float Unit() { return float(Next() % 100000) / 100000.0f; }
};

static Vector3 OnRing(Random& random, float inner, float outer)
{
    return G::PointAt(A::ArenaCenter, random.Unit() * G::TwoPi, inner + random.Unit() * (outer - inner),
        A::ArenaCenter.Z);
}

static bool Same(std::optional<Vector3> const& left, std::optional<Vector3> const& right)
{
    if (!left || !right)
        return !left && !right;
    return std::memcmp(&*left, &*right, sizeof(Vector3)) == 0;
}

struct Case
{
    D::Field Field;
    ActorSnapshot Self;
    D::Constraint Constraint;
    std::optional<Vector3> Home;
    Vector3 Destination;
};

static std::vector<Case> Cases(uint32 seed, int count, int patches)
{
    Random random{ seed };
    std::vector<Case> cases;
    for (int index = 0; index < count; ++index)
    {
        Case one;
        for (int patch = 0; patch < patches; ++patch)
            one.Field.Zones.push_back({ OnRing(random, 20.0f, 60.0f), D::PatchClearYards, true, false });
        for (int bomb = 0; bomb < int(random.Next() % 4); ++bomb)
            one.Field.Zones.push_back({ OnRing(random, 20.0f, 60.0f), D::BombClearYards, false, true });
        if (random.Next() % 2)
            one.Field.Flames.push_back({ OnRing(random, 20.0f, 60.0f), OnRing(random, 20.0f, 60.0f), D::FlameClearYards });
        if (random.Next() % 3 == 0)
            one.Field.Lanes.push_back({ A::ArenaCenter, random.Unit() * G::TwoPi, D::LaneClearYards });
        one.Self.Guid = ObjectGuid(HighGuid::Player, uint32(index + 1));
        one.Self.Kind = ActorKind::Player;
        one.Self.Alive = true;
        one.Self.Position = OnRing(random, 20.0f, 60.0f);
        switch (random.Next() % 3)
        {
            case 0:
                break;
            case 1:
                one.Constraint.RingCenter = A::ArenaCenter;
                one.Constraint.RingMax = A::MeleeRangeYards - 1.25f;
                one.Constraint.RingMin = one.Constraint.RingMax - 4.0f;
                one.Self.Position = G::PointAt(A::ArenaCenter, random.Unit() * G::TwoPi, one.Constraint.RingMax - 1.0f,
                    A::ArenaCenter.Z);
                break;
            default:
                one.Constraint.Anchor = Vector3{ A::ShieldSpawns[0].X, A::ShieldSpawns[0].Y, A::ShieldSpawns[0].Z };
                one.Constraint.AnchorReach = A::ShieldClickDistance - 1.0f;
                break;
        }
        if (random.Next() % 2)
            one.Home = OnRing(random, 20.0f, 60.0f);
        one.Destination = OnRing(random, 20.0f, 60.0f);
        cases.push_back(one);
    }
    return cases;
}

int main()
{
    // Bitwise-equal choices on random fields (none to 250 patches, bombs, a flame path, a disk lane; free, melee
    // ring and relay reach constraints).
    int checked = 0;
    for (int patches : { 0, 5, 40, 250 })
        for (Case const& one : Cases(7u + uint32(patches), 150, patches))
        {
            assert(Same(D::SafeStep(one.Field, one.Self, one.Constraint, one.Home),
                Ref::SafeStep(one.Field, one.Self, one.Constraint, one.Home)));
            assert(Same(D::DetourPoint(one.Field, one.Self, one.Destination),
                Ref::DetourPoint(one.Field, one.Self, one.Destination)));
            assert(Same(D::LeastCostStep(one.Field, one.Self, one.Destination),
                Ref::LeastCostStep(one.Field, one.Self, one.Destination)));
            for (int trial = 0; trial < 8; ++trial)
            {
                Vector3 const to = G::PointAt(one.Self.Position, float(trial), 3.0f * float(trial), A::ArenaCenter.Z);
                float const now = D::PathCost(one.Field, one.Self.Position, to, 7.0f);
                float const before = Ref::PathCost(one.Field, one.Self.Position, to, 7.0f);
                assert(std::memcmp(&now, &before, sizeof(float)) == 0);
                for (D::Zone const& zone : one.Field.Zones)
                {
                    float const a = A::KitePath::SecondsInside(one.Self.Position, to, zone.Center, zone.Radius, 7.0f);
                    float const b = Ref::SecondsInside(one.Self.Position, to, zone.Center, zone.Radius, 7.0f);
                    assert(std::memcmp(&a, &b, sizeof(float)) == 0);
                }
            }
            ++checked;
        }
    // The cost with 250 patches: the same searches, interleaved rounds so host load hits both alike.
    std::vector<Case> const heavy = Cases(99u, 60, 250);
    using Clock = std::chrono::steady_clock;
    double now = 0.0;
    double before = 0.0;
    float sink = 0.0f;
    for (int round = 0; round < 5; ++round)
    {
        auto const a = Clock::now();
        for (Case const& one : heavy)
        {
            if (auto step = D::SafeStep(one.Field, one.Self, one.Constraint, one.Home))
                sink += step->X;
            if (auto step = D::DetourPoint(one.Field, one.Self, one.Destination))
                sink += step->X;
            sink += D::LeastCostStep(one.Field, one.Self, one.Destination).X;
        }
        auto const b = Clock::now();
        for (Case const& one : heavy)
        {
            if (auto step = Ref::SafeStep(one.Field, one.Self, one.Constraint, one.Home))
                sink += step->X;
            if (auto step = Ref::DetourPoint(one.Field, one.Self, one.Destination))
                sink += step->X;
            sink += Ref::LeastCostStep(one.Field, one.Self, one.Destination).X;
        }
        auto const c = Clock::now();
        now += std::chrono::duration<double, std::micro>(b - a).count();
        before += std::chrono::duration<double, std::micro>(c - b).count();
    }
    std::printf("checked %d cases; 250 patches: %.1f us per search set now, %.1f us before (x%.2f) %f\n", checked,
        now / (5.0 * double(heavy.size())), before / (5.0 * double(heavy.size())), before / now, double(sink) * 0.0);
    assert(now < 0.7 * before);
    std::puts("decision cost ok");
    return 0;
}
'''


def _compile_and_run(tmp_path: Path, program: str, flags: list[str]) -> str:
    source, binary = tmp_path / "program.cpp", tmp_path / "program"
    source.write_text(program, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", *flags, *INCLUDES,
                    str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    print(result.stdout)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


def test_dodge_search_is_unchanged_and_cheaper(tmp_path: Path) -> None:
    output = _compile_and_run(tmp_path, EQUIVALENCE, ["-O2"])
    assert "checked 600 cases" in output and "decision cost ok" in output


# ---- the standalone replay benchmark (not a test: `pixi run python -m tests.test_atramedes_decision_cost`) ----

BENCH_PRELUDE = r'''
#include <chrono>
#include <map>
#include <string>
static std::vector<double> g_air;
static std::vector<double> g_snapshot;
static double g_step = 0.0;
template <typename... Args>
static AdaptiveAtramedesPlan TimedPropose(Blackboard const& board, Args&&... args)
{
    auto const start = std::chrono::steady_clock::now();
    AdaptiveAtramedesPlan plan = AdaptiveAtramedesStrategy().Propose(board, std::forward<Args>(args)...);
    double const us = std::chrono::duration<double, std::micro>(std::chrono::steady_clock::now() - start).count();
    if (!board.Summons.empty() && board.Summons.front().Flying)
    {
        g_air.push_back(us);
        g_step += us;
    }
    return plan;
}
'''

BENCH_MAIN = r'''
static void Report(char const* name, std::vector<double> values)
{
    if (values.empty())
        return;
    std::sort(values.begin(), values.end());
    double sum = 0.0;
    for (double value : values)
        sum += value;
    std::printf("%-30s n=%7zu mean=%8.1f us p50=%8.1f p99=%8.1f max=%9.1f\n", name, values.size(),
        sum / double(values.size()), values[values.size() / 2], values[values.size() * 99 / 100], values.back());
}

int main()
{
    std::vector<uint32> const beforePhase1 = AfterGroundSearing(AllShieldIds(), 100.0f);
    for (uint32 seed : { 1u, 2u, 3u })
        for (float delay : { 7.0f, 3.0f })
            for (uint32 slot = Tank; slot <= Warlock; ++slot)
            {
                ReplayOptions options;
                options.Mobility = true;
                options.Bombs = options.FirePatches = true;
                options.Seed = seed;
                AirReplay const one = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks), delay, false,
                    beforePhase1, 100.0f, 31.0f, options);
                ReplayOptions later = options;
                later.IceBlockReady = false;
                later.DashRemainingMs = 56000;
                later.Seed = seed + 17;
                ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks), delay, false,
                    AfterGroundSearing(one.ShieldsLeft, 60.0f), 60.0f, 31.0f, later);
            }
    Report("air decision", g_air);
    Report("air snapshot (10 bots)", g_snapshot);
    return 0;
}
'''


def benchmark_program(lingering_patches: int = 0) -> str:
    """The replay harness with every strategy decision timed (air phases, bombs and fire)."""
    from tests.test_atramedes_raid_sound import HARNESS
    harness = HARNESS.replace("AdaptiveAtramedesStrategy().Propose(", "TimedPropose(")
    anchor = "namespace G = BotEncounter::Atramedes::Geometry;\n"
    harness = harness.replace(anchor, anchor + BENCH_PRELUDE, 1)
    harness = harness.replace("""    for (float t = 0.25f; t <= seconds + 0.001f; t += 0.25f)
    {
        ++board.Revision;""", """    for (float t = 0.25f; t <= seconds + 0.001f; t += 0.25f)
    {
        if (g_step > 0.0)
            g_snapshot.push_back(g_step);
        g_step = 0.0;
        ++board.Revision;""", 1)
    if lingering_patches:
        harness = harness.replace("""    ActorSnapshot& target = Member(board, targetSlot);
    AddFlame(board, target, target.Position, 0);""", f"""    {{
        ReplayRandom scatter{{ 99u + targetSlot }};
        for (int index = 0; index < {lingering_patches}; ++index)
        {{
            float const angle = float(scatter.Next() % 3600) / 3600.0f * G::TwoPi;
            float const radius = 30.0f + float(scatter.Next() % 3000) / 100.0f;
            Vector3 const at = G::PointAt(A::ArenaCenter, angle, radius, 75.0f);
            board.Summons.push_back(MakeUnit(A::RoaringFlamePatchEntry, 20000 + index, at.X, at.Y, ActorKind::Summon));
        }}
    }}
    ActorSnapshot& target = Member(board, targetSlot);
    AddFlame(board, target, target.Position, 0);""", 1)
    assert "TimedPropose(" in harness and "g_snapshot.push_back" in harness
    return harness + BENCH_MAIN


def main(folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    for patches in (0, 250):
        source, binary = folder / f"bench_{patches}.cpp", folder / f"bench_{patches}"
        source.write_text(benchmark_program(patches), encoding="utf-8")
        subprocess.run(["g++", "-std=c++17", "-O2", "-w", *INCLUDES, str(source), "-o", str(binary)],
                       check=True, cwd=ROOT)
        print(f"-- {patches} lingering fire patches")
        print(subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True, check=True).stdout, end="")
        source.unlink()
        binary.unlink()


if __name__ == "__main__":
    main(Path(sys.argv[1]) if len(sys.argv) > 1 else Path.home() / ".cache" / "atramedes_decision_cost")

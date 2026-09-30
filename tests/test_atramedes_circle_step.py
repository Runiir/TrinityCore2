"""BWD 10N round 3 fix (Atramedes): a circling step never walks through fire.

Reviewer finding: BotAtramedesDodge.h ClearCircleStep accepted a step from its end point alone (endpoint
Clear plus DiskSafeWalk). DetourPoint and PathCost, by contrast, price the chord. A floor-valid kite at r=35,
arc=12 with one fire patch at the chord midpoint has a clear start and end but crosses the patch for a second
(+5 Sound per patch second); GroundKiteMove calls ClearCircleStep directly, so the ground kiter walked
through fire. The user's rule (user raid experience 2026-09-30: "the bots dodge everything") forbids it.

The fix: the chord is judged by the predicate the detours use (Dodge::PathClear, PathCost == 0). A step
whose chord crosses fire or a Sonar Bomb zone is taken only when no clear-ended step with a clear chord
exists: then a run ahead holds while it stands clear, else the clear-ended step that crosses the least.

The program drives the production header with the strategy test's snapshot helpers:
- the reviewer's case, at every bearing and both circling directions: the step is changed and its chord
  clear (the endpoint-only rule would have kept the plain step: asserted as the premise);
- controls: no hazard, fire beside the chord and fire behind the walker leave the plain step unchanged;
- no clear chord exists (a fire curtain across every clear-ended step): a run ahead holds, a kite takes the
  least-cost step; standing in fire the step is never worse than the plain step;
- the production callers: GroundKiteMove (the Sonic Breath kite) and SonicBreathBeamExit's run ahead of the
  sweep (a ranged and a melee bystander, the melee one held to its ring), through the strategy's plan, with
  their controls;
- one predicate for every candidate (final review): SafeSegment = usable end (clear, on the floor, no disk
  met) + a chord that crosses no fire or bomb; the plain step is judged like the alternates, so a plain step
  off the hall floor is not taken while a floor-valid one exists.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from tests.test_atramedes_strategy import INCLUDES, PROGRAM, ROOT

HARNESS = PROGRAM[:PROGRAM.index("// ---- end of the air-phase replay harness ----")]
ATRAMEDES = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"

RULES = r'''
namespace D = BotEncounter::Atramedes::Dodge;

static Vector3 To(AdaptiveAtramedesPlan const& plan)
{
    return { MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f };
}

static Vector3 Mid(Vector3 const& a, Vector3 const& b)
{
    return { (a.X + b.X) / 2.0f, (a.Y + b.Y) / 2.0f, 75.0f };
}

// A chord's end and walk are clean: clear of the field, floor-valid, no fire or bomb crossed.
static bool CleanStep(D::Field const& field, Vector3 const& from, Vector3 const& to, float speed)
{
    return D::Clear(field, to, 0.0f) && A::ArenaFloor::Solid(to.X, to.Y) && D::PathClear(field, from, to, speed);
}

static float BaseSpeed() { return A::Mobility::BaseRunSpeed; }

// The reviewer's case, everywhere on the circle.
static void TestCircleStepChordAvoidsFire()
{
    Vector3 const boss = A::TankAnchor;
    float const radius = 35.0f;
    float const arc = 12.0f;
    int cases = 0;
    for (int degrees = 0; degrees < 360; degrees += 15)
        for (int direction : { 1, -1 })
        {
            Vector3 const self = G::PointAt(boss, float(degrees) * G::Pi / 180.0f, radius, 75.0f);
            Vector3 const plain = G::TangentialStep(boss, self, radius, arc, direction);
            if (!A::ArenaFloor::Solid(self.X, self.Y) || !A::ArenaFloor::Solid(plain.X, plain.Y))
                continue;
            ++cases;
            D::Field field;
            field.Zones.push_back({ Mid(self, plain), D::PatchClearYards, true });
            // The premise: the start and the end are clear, the chord is fire.
            assert(D::Clear(field, self, 0.0f) && D::Clear(field, plain, 0.0f));
            assert(D::DiskSafeWalk(field, self, plain, BaseSpeed()));
            assert(D::PathCost(field, self, plain, BaseSpeed()) >= D::FireSecondYards - 0.01f);
            assert(!D::PathClear(field, self, plain, BaseSpeed()));
            for (float speed : { BaseSpeed(), 7.0f })
            {
                Vector3 const step = D::ClearCircleStep(field, boss, self, radius, arc, direction, 28.0f, 42.0f,
                    speed);
                assert(G::Distance2d(step, plain) > 1.0f);
                assert(CleanStep(field, self, step, speed));
                float const r = G::Distance2d(boss, step);
                assert(r >= 28.0f - 0.01f && r <= 42.0f + 0.01f);
            }
            // A Sonar Bomb zone on the chord is the same (+20): a longer arc, the bomb 4.5 yd outside the chord
            // (inside its 6 yd, so the walk is in it; both ends are out of its 7.5 yd).
            Vector3 const far = G::TangentialStep(boss, self, radius, 18.0f, direction);
            if (!A::ArenaFloor::Solid(far.X, far.Y))
                continue;
            D::Field bomb;
            bomb.Zones.push_back({ G::PointAt(Mid(self, far), G::Bearing(boss, Mid(self, far)), 4.5f, 75.0f),
                D::BombClearYards, false });
            assert(D::Clear(bomb, self, 0.0f) && D::Clear(bomb, far, 0.0f) && !D::PathClear(bomb, self, far, BaseSpeed()));
            Vector3 const around = D::ClearCircleStep(bomb, boss, self, radius, 18.0f, direction, 28.0f, 42.0f);
            assert(G::Distance2d(around, far) > 1.0f && CleanStep(bomb, self, around, BaseSpeed()));
        }
    assert(cases >= 40);
}

// Controls: the plain step is unchanged when its chord is clean.
static void TestCircleStepUnchangedWithoutFireOnTheChord()
{
    Vector3 const boss = A::TankAnchor;
    float const radius = 35.0f;
    float const arc = 12.0f;
    int cases = 0;
    for (int degrees = 0; degrees < 360; degrees += 15)
        for (int direction : { 1, -1 })
        {
            Vector3 const self = G::PointAt(boss, float(degrees) * G::Pi / 180.0f, radius, 75.0f);
            Vector3 const plain = G::TangentialStep(boss, self, radius, arc, direction);
            if (!A::ArenaFloor::Solid(self.X, self.Y) || !A::ArenaFloor::Solid(plain.X, plain.Y))
                continue;
            ++cases;
            auto step = [&](D::Field const& field)
            {
                return D::ClearCircleStep(field, boss, self, radius, arc, direction, 28.0f, 42.0f);
            };
            // No hazard at all.
            D::Field const empty;
            assert(G::Distance2d(step(empty), plain) < 0.001f);
            // Fire beside the chord: 8 yd off its midpoint (clear of the walk and of both ends).
            Vector3 const mid = Mid(self, plain);
            float const along = G::Bearing(self, plain);
            D::Field beside;
            beside.Zones.push_back({ G::PointAt(mid, along + G::Pi / 2.0f, 8.0f, 75.0f), D::PatchClearYards, true });
            assert(D::Clear(beside, plain, 0.0f) && D::PathClear(beside, self, plain, BaseSpeed()));
            assert(G::Distance2d(step(beside), plain) < 0.001f);
            // Fire behind the walker and past the end: the chord never reaches it.
            D::Field behind;
            behind.Zones.push_back({ G::PointAt(self, along + G::Pi, 8.0f, 75.0f), D::PatchClearYards, true });
            behind.Zones.push_back({ G::PointAt(plain, along, 10.0f, 75.0f), D::PatchClearYards, true });
            assert(D::Clear(behind, plain, 0.0f) && D::PathClear(behind, self, plain, BaseSpeed()));
            assert(G::Distance2d(step(behind), plain) < 0.001f);
            // A patch under the end point still moves the step off it (the end is the old rule's case).
            D::Field under;
            under.Zones.push_back({ plain, D::PatchClearYards, true });
            Vector3 const off = D::ClearCircleStep(under, boss, self, radius, arc, direction, 28.0f, 42.0f);
            assert(G::Distance2d(off, plain) > 1.0f && CleanStep(under, self, off, BaseSpeed()));
        }
    assert(cases >= 40);
}

// Fire across every clear-ended step: none has a clear chord.
static void TestCircleStepWithoutAClearChord()
{
    Vector3 const boss = A::TankAnchor;
    float const radius = 35.0f;
    float const arc = 12.0f;
    int cases = 0;
    for (int degrees = 0; degrees < 360; degrees += 30)
        for (int direction : { 1, -1 })
        {
            Vector3 const self = G::PointAt(boss, float(degrees) * G::Pi / 180.0f, radius, 75.0f);
            if (!A::ArenaFloor::Solid(self.X, self.Y))
                continue;
            // A curtain of patches 6 yd ahead of the walker along its circle, from radius 14 to 56.
            float const ahead = G::Bearing(boss, self) + float(direction) * 6.0f / radius;
            D::Field curtain;
            for (float r = 14.0f; r <= 56.0f; r += 3.0f)
                curtain.Zones.push_back({ G::PointAt(boss, ahead, r, 75.0f), D::PatchClearYards, true });
            if (!D::Clear(curtain, self, 0.0f))
                continue;
            // Every clear-ended, floor-valid, disk-safe step of the grid crosses the curtain.
            float least = 1e9f;
            int endsClear = 0;
            Vector3 const plain = G::TangentialStep(boss, self, radius, arc, direction);
            std::vector<Vector3> grid{ plain };
            for (float shift : { 0.0f, 3.0f, -3.0f, 6.0f, -6.0f, 9.0f, -9.0f })
                for (float step : { arc, arc * 1.5f, arc * 0.66f, arc * 0.33f })
                    if (radius + shift >= 28.0f && radius + shift <= 42.0f)
                        grid.push_back(G::TangentialStep(boss, self, radius + shift, step, direction));
            for (Vector3 const& point : grid)
                if (A::ArenaFloor::Solid(point.X, point.Y) && D::Clear(curtain, point, 0.0f))
                {
                    ++endsClear;
                    assert(!D::PathClear(curtain, self, point, BaseSpeed()));
                    least = std::min(least, D::PathCost(curtain, self, point, BaseSpeed()));
                }
            if (!endsClear || !A::ArenaFloor::Solid(plain.X, plain.Y))
                continue;
            ++cases;
            // A run ahead (the beam is still behind) holds while it stands clear rather than cross fire.
            Vector3 const hold = D::ClearCircleStep(curtain, boss, self, radius, arc, direction, 28.0f, 42.0f,
                BaseSpeed(), true);
            assert(G::Distance2d(hold, self) < 0.001f);
            // A kite cannot hold: the clear-ended step that crosses the least.
            Vector3 const kite = D::ClearCircleStep(curtain, boss, self, radius, arc, direction, 28.0f, 42.0f);
            assert(D::Clear(curtain, kite, 0.0f) && A::ArenaFloor::Solid(kite.X, kite.Y));
            assert(D::PathCost(curtain, self, kite, BaseSpeed()) <= least + 0.001f);
            assert(D::PathCost(curtain, self, kite, BaseSpeed()) <= D::PathCost(curtain, self, plain, BaseSpeed()));
        }
    assert(cases >= 10);
    // Standing in fire no step is clear-chorded (the walk starts inside): never worse than the plain step,
    // the run ahead cannot hold there, and the end is clear.
    Vector3 const self = G::PointAt(boss, 1.0f, radius, 75.0f);
    Vector3 const plain = G::TangentialStep(boss, self, radius, arc, 1);
    D::Field inside;
    inside.Zones.push_back({ self, D::PatchClearYards, true });
    assert(!D::Clear(inside, self, 0.0f));
    for (bool mayHold : { false, true })
    {
        Vector3 const step = D::ClearCircleStep(inside, boss, self, radius, arc, 1, 28.0f, 42.0f, BaseSpeed(), mayHold);
        assert(G::Distance2d(step, self) > 1.0f && D::Clear(inside, step, 0.0f));
        assert(D::PathCost(inside, self, step, BaseSpeed()) <= D::PathCost(inside, self, plain, BaseSpeed()));
    }
}

static Blackboard BreathBoard(Vector3 const& kiterAt, Vector3 const& flameAt)
{
    Blackboard board = Board();
    Member(board, Balance).Position = kiterAt;
    ActorSnapshot flames = MakeUnit(A::TrackingFlamesEntry, 91, flameAt.X, flameAt.Y, ActorKind::Summon);
    board.Summons.push_back(flames);
    AddAura(Member(board, Balance), A::TrackingAura, flames.Guid);
    CastOnBoss(board, A::SonicBreathChannelSpells.front());
    return board;
}

// The production callers, through the strategy's plan.
static void TestSonicBreathKiteAvoidsFireOnItsChord()
{
    Vector3 const kiterAt{ 172.0f, -254.0f, 75.0f };
    Blackboard board = BreathBoard(kiterAt, { 171.0f, -251.0f, 75.0f });
    AdaptiveAtramedesPlan const free = Plan(board, Balance);
    assert(Mechanic(free) == "sonic_breath_kite");
    Vector3 const plain = To(free);
    Vector3 const mid = Mid(kiterAt, plain);
    float const along = G::Bearing(kiterAt, plain);
    float const speed = A::Mobility::RunSpeed(Member(board, Balance));

    // Controls: fire 9 yd off the chord leaves the kite alone, and so does a patch past its end.
    for (Vector3 const& at : { G::PointAt(mid, along + G::Pi / 2.0f, 9.0f, 75.0f),
             G::PointAt(plain, along, 12.0f, 75.0f) })
    {
        Blackboard quiet = board;
        quiet.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, 960, at.X, at.Y, ActorKind::Summon));
        AdaptiveAtramedesPlan const same = Plan(quiet, Balance);
        assert(Mechanic(same) == "sonic_breath_kite" && G::Distance2d(To(same), plain) < 0.001f);
    }

    // The reviewer's case: a Searing Flame patch at the chord midpoint. Its end and start are clear.
    board.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, 961, mid.X, mid.Y, ActorKind::Summon));
    A::Facts const facts = A::BuildFacts(board);
    D::Field const field = D::BuildField(board, facts, Member(board, Balance), { false, true });
    assert(D::Clear(field, kiterAt, 0.0f) && D::Clear(field, plain, 0.0f) && !D::PathClear(field, kiterAt, plain, speed));
    AdaptiveAtramedesPlan const dodged = Plan(board, Balance);
    assert(Mechanic(dodged) == "sonic_breath_kite");
    Vector3 const step = To(dodged);
    assert(G::Distance2d(step, plain) > 1.0f && CleanStep(field, kiterAt, step, speed));
    float const r = G::Distance2d(Boss(board).Position, step);
    assert(r >= A::GroundKiteMinRadius - 0.01f && r <= A::GroundKiteMaxRadius + 0.01f);
}

// SonicBreathBeamExit's run ahead of the sweep (GroundKiteMove's sibling caller of ClearCircleStep): a ranged
// bystander and a melee one, whose step stays on the melee ring.
static void RunAheadAvoidsFireOnItsChord(uint32 slot, float radius, bool melee)
{
    Vector3 const flameAt{ 171.0f, -251.0f, 75.0f };
    Blackboard board = BreathBoard({ 172.0f, -254.0f, 75.0f }, flameAt);
    Vector3 const boss = Boss(board).Position;
    float const beam = G::Bearing(boss, flameAt);
    // A bystander ahead of the sweep: find where the strategy runs it on.
    Vector3 self{};
    Vector3 plain{};
    bool found = false;
    for (float degrees = 5.0f; degrees <= 120.0f && !found; degrees += 5.0f)
        for (float sign : { 1.0f, -1.0f })
        {
            Vector3 const at = G::PointAt(boss, beam + sign * degrees * G::Pi / 180.0f, radius, 75.0f);
            Member(board, slot).Position = at;
            AdaptiveAtramedesPlan const plan = Plan(board, slot);
            if (Mechanic(plan) == "sonic_breath_run_ahead" && G::Distance2d(To(plan), at) > 5.0f)
            {
                self = at;
                plain = To(plan);
                found = true;
                break;
            }
        }
    assert(found);
    Vector3 const mid = Mid(self, plain);
    float const along = G::Bearing(self, plain);
    float const speed = A::Mobility::RunSpeed(Member(board, slot));
    A::Facts const facts = A::BuildFacts(board);
    D::Constraint const ring = melee ? D::MeleeRing(facts) : D::Constraint{};
    // Control: fire 9 yd off the chord leaves the run alone.
    {
        Blackboard quiet = board;
        Vector3 const at = G::PointAt(mid, along + G::Pi / 2.0f, 9.0f, 75.0f);
        quiet.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, 962, at.X, at.Y, ActorKind::Summon));
        AdaptiveAtramedesPlan const same = Plan(quiet, slot);
        assert(Mechanic(same) == "sonic_breath_run_ahead" && G::Distance2d(To(same), plain) < 0.001f);
    }
    // Fire at the chord midpoint (a melee bystander's ring leaves only one inward radius to go around it, so the
    // patch sits 2 yd outside the chord there): its start and end are clear, its walk is fire.
    Vector3 const fire = melee ? G::PointAt(mid, G::Bearing(boss, mid), 2.0f, 75.0f) : mid;
    board.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, 963, fire.X, fire.Y, ActorKind::Summon));
    D::Field field = D::BuildField(board, A::BuildFacts(board), Member(board, slot));
    field.SonicBreath.reset();
    assert(D::Clear(field, self, 0.0f) && D::Clear(field, plain, 0.0f) && !D::PathClear(field, self, plain, speed));
    AdaptiveAtramedesPlan const dodged = Plan(board, slot);
    assert(MoveOf(dodged) && Mechanic(dodged) == "sonic_breath_run_ahead");
    Vector3 const step = To(dodged);
    assert(G::Distance2d(step, plain) > 1.0f && CleanStep(field, self, step, speed));
    // A melee bystander stays on the melee ring.
    assert(!melee || ring.Allows(step));
    assert(melee == ring.RingCenter.has_value());
}

static void TestRunAheadAvoidsFireOnItsChord()
{
    RunAheadAvoidsFireOnItsChord(Elemental, 22.0f, false);
    RunAheadAvoidsFireOnItsChord(Rogue, A::MeleeSlotRadius, true);
}

// The floor is judged for every candidate, the plain step first: a plain step off the hall floor is not taken
// while a floor-valid step exists (no hazard at all).
static void TestPlainStepOffTheFloorIsNotTaken()
{
    Vector3 const boss{ 214.531f, -223.918f, 75.0f };
    float const radius = 35.0f;
    float const arc = 12.0f;
    int cases = 0;
    for (int degrees = 0; degrees < 360; degrees += 5)
        for (int direction : { 1, -1 })
        {
            Vector3 const self = G::PointAt(boss, float(degrees) * G::Pi / 180.0f, radius, 75.0f);
            Vector3 const plain = G::TangentialStep(boss, self, radius, arc, direction);
            if (!A::ArenaFloor::Solid(self.X, self.Y) || A::ArenaFloor::Solid(plain.X, plain.Y))
                continue;
            D::Field const empty;
            Vector3 const step = D::ClearCircleStep(empty, boss, self, radius, arc, direction, 28.0f, 42.0f);
            bool exists = false;
            for (float shift : { 0.0f, 3.0f, -3.0f, 6.0f, -6.0f, 9.0f, -9.0f })
                for (float part : { arc, arc * 1.5f, arc * 0.66f, arc * 0.33f })
                    if (radius + shift >= 28.0f && radius + shift <= 42.0f)
                    {
                        Vector3 const other = G::TangentialStep(boss, self, radius + shift, part, direction);
                        exists = exists || D::SafeSegment(empty, self, other, BaseSpeed());
                    }
            if (!exists)
                continue;
            ++cases;
            assert(G::Distance2d(step, plain) > 0.5f && D::SafeSegment(empty, self, step, BaseSpeed()));
            assert(A::ArenaFloor::Solid(step.X, step.Y));
        }
    assert(cases >= 3);
    // The same predicate judges the candidates of a hazard: a step is safe only with a usable end and a clear chord.
    Vector3 const self = G::PointAt(A::TankAnchor, 0.5f, 35.0f, 75.0f);
    Vector3 const far = G::TangentialStep(A::TankAnchor, self, 35.0f, 12.0f, 1);
    D::Field fire;
    fire.Zones.push_back({ Mid(self, far), D::PatchClearYards, true });
    assert(D::SegmentEndUsable(fire, self, far, BaseSpeed()) && !D::SafeSegment(fire, self, far, BaseSpeed()));
    D::Field none;
    assert(D::SafeSegment(none, self, far, BaseSpeed()));
    Vector3 const wall{ 300.0f, -224.0f, 75.0f };
    assert(!D::SegmentEndUsable(none, self, wall, BaseSpeed()) && !D::SafeSegment(none, self, wall, BaseSpeed()));
}

static void RunRules()
{
    TestCircleStepChordAvoidsFire();
    TestCircleStepUnchangedWithoutFireOnTheChord();
    TestCircleStepWithoutAClearChord();
    TestSonicBreathKiteAvoidsFireOnItsChord();
    TestRunAheadAvoidsFireOnItsChord();
    TestPlainStepOffTheFloorIsNotTaken();
    std::puts("circle step rules ok");
}

int main()
{
    RunRules();
    return 0;
}
'''


def compile_and_run(tmp_path: Path, include_first: list[str] | None = None) -> subprocess.CompletedProcess:
    source = tmp_path / "circle_step.cpp"
    binary = tmp_path / "circle_step"
    source.write_text(HARNESS + RULES, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-Wno-unused-function", "-O1",
                    *(include_first or []), *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    return subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)


def test_circle_step_never_walks_through_fire(tmp_path: Path) -> None:
    result = compile_and_run(tmp_path)
    print(result.stdout)
    assert result.returncode == 0, result.stdout[-4000:] + result.stderr[-4000:]
    assert "circle step rules ok" in result.stdout


def test_circle_step_shares_the_detour_predicate() -> None:
    dodge = (ATRAMEDES / "BotAtramedesDodge.h").read_text(encoding="utf-8")
    predicate = dodge[dodge.index("inline bool PathClear("):]
    predicate = predicate[:predicate.index("\n}\n")]
    assert "PathCost(field, from, to, speed) <= 0.0f" in predicate
    circle = dodge[dodge.index("inline Vector3 ClearCircleStep("):]
    circle = circle[:circle.index("\n}\n")]
    assert "SafeSegment(field, self, point, speed)" in circle and "ArenaFloor::Solid(" not in circle
    # One predicate for the initial and every alternate candidate: the floor, the end, the disks and the chord.
    safe = dodge[dodge.index("inline bool SegmentEndUsable("):dodge.index("inline Vector3 ClearCircleStep(")]
    assert "Clear(field, to, 0.0f) && ArenaFloor::Solid(to.X, to.Y)" in safe and "DiskSafeWalk(field, from, to, speed)" in safe
    assert "SegmentEndUsable(field, from, to, speed) && PathClear(field, from, to, speed)" in safe
    # One predicate: the detours use it too, and no copy of the "chord costs nothing" test remains.
    for name in ("DetourPoint", "RunnerStep"):
        body = dodge[dodge.index(f" {name}("):]
        body = body[:body.index("\n}\n")]
        assert "PathClear(" in body and "PathCost(field, self.Position, point, speed) > 0.0f" not in body, name
    assert "PathCost(field, self.Position, destination, speed) <= 0.0f" not in dodge
    assert len(dodge.splitlines()) < 1000

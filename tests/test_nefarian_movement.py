"""Movement checks for the Nefarian's End strategy on the GO 207834 surface.

Package T's transport-surface walk accepts one straight leg of at most
MaxSurfaceWalkYards (12). These programs drive the canonical 10N raid through
the encounter with a native chase model (a dragon moves straight at its tank
and stops at its melee reach, and only turns while the tank stays inside that
reach), applying each emitted leg as the bot's new position, and check:
- every submitted TransportSurfaceMove is a Walk ending on the elevator,
  within MaxSurfaceWalkYards of the bot, clear of the pillars, and crosses the
  centre-to-ring rise only radially;
- the legs converge on the goals, from the route's board point (local 25, 0)
  and from the ledge-drop landing on the ring (local 49.2, 0);
- the tanks leave the dragons at their ends more than 50 yards apart (out of
  Children of Deathwing range), holding them without oscillating;
- the planner converges between every pair of standing spots.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


MOVEMENT = PRELUDE + r'''
#include "Bots/BotValidationRouteNativeApproach.h"

static float const MaxWalk = BotValidationRouteNative::MaxSurfaceWalkYards;
static char const* const Names[] = { "", "DK", "Feral", "Hunter", "Mage", "Holy", "Ret",
    "Disc", "Rogue", "Resto", "Lock" };

struct Sim
{
    Blackboard Board;
    float OriginZ = PlatformFrame::RaisedOriginZ;
    int Legs = 0;
    int Violations = 0;
};

static void PlaceAll(Sim& sim, LocalPoint at, float localZ)
{
    for (ActorSnapshot& player : sim.Board.Players)
        player.Position = LocalToWorld(at, localZ, sim.OriginZ);
}

static ActorSnapshot* FindCreature(Blackboard& board, uint32 entry)
{
    for (ActorSnapshot& actor : board.Summons)
        if (actor.Entry == entry && actor.Alive)
            return &actor;
    return nullptr;
}

// Native chase: straight at the tank, stop at the melee reach; a tank inside
// the reach only turns the dragon.
static void Chase(Sim& sim, uint32 entry, uint32 tankSlot, float reach)
{
    ActorSnapshot* dragon = FindCreature(sim.Board, entry);
    if (!dragon || dragon->Flying)
        return;
    LocalPoint position = WorldToLocal(dragon->Position);
    LocalPoint const tank = WorldToLocal(FindPlayer(sim.Board, tankSlot).Position);
    float const distance = Distance(position, tank);
    if (distance > reach)
        position = StepToward(position, tank, distance - (reach - 1.0f));
    dragon->Position = LocalToWorld(position, FloorLocalZAt(position), sim.OriginZ);
    dragon->Facing = NormalizeSigned(AngleOf({ tank.X - position.X, tank.Y - position.Y })
        + PlatformFrame::Orientation);
}

// One decision per bot; each emitted leg is checked and then walked.
static int Tick(Sim& sim, char const* phase)
{
    AdaptiveNefarianStrategy strategy;
    int moved = 0;
    for (uint32 slot = 1; slot <= 10; ++slot)
    {
        ActorSnapshot& bot = FindPlayer(sim.Board, slot);
        AdaptiveNefarianPlan const plan = strategy.Propose(sim.Board, bot.Guid, bot.Role);
        if (!plan.Movement)
            continue;
        auto const* walk = std::get_if<BotNativeAction::TransportSurfaceMove>(
            &plan.Movement->Action);
        LocalPoint const from = WorldToLocal(bot.Position);
        bool ok = walk && walk->Kind == BotNativeAction::TransportSurfaceMove::Stage::Walk
            && walk->EndOnTransport && walk->Transport == sim.Board.Interactables[0].Guid;
        LocalPoint const to = walk ? WorldToLocal({ walk->X, walk->Y, walk->Z }) : from;
        float const length = Distance(from, to);
        ok = ok && length <= MaxWalk && length <= MaxLegYards + 0.01f
            && SegmentClearOfPillars(from, to);
        PlatformRegion const a = RegionOf(from);
        PlatformRegion const b = RegionOf(to);
        if (ok && a != b && Length(from) > 1.0f)
            ok = plan.MovementLeg && plan.MovementLeg->CrossesRise
                && AngularGap(AngleOf(from), AngleOf(to)) < DegToRad(2.0f);
        if (ok && a == PlatformRegion::Ring && b == PlatformRegion::Ring)
            ok = SegmentStaysOnRing(from, to);
        if (!ok)
        {
            ++sim.Violations;
            std::fprintf(stderr, "bad leg %s %s (%.1f,%.1f)->(%.1f,%.1f) len %.2f purpose %s\n",
                phase, Names[slot], from.X, from.Y, to.X, to.Y, length,
                plan.Movement->Id.Mechanic.c_str());
            continue;
        }
        bot.Position = { walk->X, walk->Y, walk->Z };
        ++sim.Legs;
        ++moved;
    }
    return moved;
}

static int Settle(Sim& sim, char const* phase, int maxTicks, bool chaseOnyxia,
    bool chaseNefarian)
{
    for (int tick = 0; tick < maxTicks; ++tick)
    {
        int const moved = Tick(sim, phase);
        if (chaseOnyxia)
            Chase(sim, OnyxiaEntry, 2, OnyxiaMeleeReach);
        if (chaseNefarian)
            Chase(sim, NefarianEntry, 1, NefarianMeleeReach);
        if (!moved)
            return tick;
    }
    return -1;
}

static void RunEncounter(LocalPoint entry, float entryLocalZ, char const* label)
{
    Sim sim;
    sim.Board = CanonicalBoard();
    PlaceAll(sim, entry, entryLocalZ);
    ActorSnapshot onyxia = MakeCreature(OnyxiaEntry, 11, { 0.1f, 0.05f }, 0.0f);
    AddAura(onyxia, SpellOnyxiaFeignDeath);
    onyxia.Attackable = false;
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f, 60.0f);
    nefarian.Flying = true;
    nefarian.Attackable = false;
    sim.Board.Summons = { onyxia, nefarian };

    std::string phase = std::string(label) + ":pre_engage";
    CHECK(Settle(sim, phase.c_str(), 40, false, false) >= 0, phase.c_str());

    ActorSnapshot* ony = FindCreature(sim.Board, OnyxiaEntry);
    ony->Auras.clear();
    ony->InCombat = true;
    ony->Attackable = true;
    ony->VictimGuid = Bot(2);
    phase = std::string(label) + ":onyxia_only";
    CHECK(Settle(sim, phase.c_str(), 80, true, false) >= 0, phase.c_str());
    ArenaLayout const layout = BuildArenaLayout(BuildNefarianDutyPlan(sim.Board));
    LocalPoint const onyxiaAt = WorldToLocal(FindCreature(sim.Board, OnyxiaEntry)->Position);
    CHECK(DragonAtEnd(onyxiaAt, layout.OnyxiaEndAngle), "Onyxia is held at her end");

    ActorSnapshot* nef = FindCreature(sim.Board, NefarianEntry);
    nef->Flying = false;
    nef->Attackable = true;
    nef->InCombat = true;
    nef->VictimGuid = Bot(1);
    nef->Position = LocalToWorld({ -0.3f, 0.5f }, PlatformFrame::FloorLocalZ, sim.OriginZ);
    phase = std::string(label) + ":both_dragons";
    CHECK(Settle(sim, phase.c_str(), 120, true, true) >= 0, phase.c_str());
    LocalPoint const o = WorldToLocal(FindCreature(sim.Board, OnyxiaEntry)->Position);
    LocalPoint const n = WorldToLocal(FindCreature(sim.Board, NefarianEntry)->Position);
    CHECK(DragonAtEnd(o, layout.OnyxiaEndAngle) && DragonAtEnd(n, layout.NefarianEndAngle),
        "both dragons are held at their ends");
    CHECK(Distance(o, n) > ChildrenOfDeathwingRange + 2.0f,
        "the dragons end more than 50 yards apart (Children of Deathwing off)");
    // Literal floor, independent of the strategy's own gate: at opposite ends
    // two dragons at r >= 27 within 15 degrees stay beyond 50 yards.
    CHECK(Length(o) >= 27.0f && Length(n) >= 27.0f, "each dragon ends at r 27 or more");
    std::printf("%s: onyxia r %.1f, nefarian r %.1f, separation %.1f yd, %d legs\n", label,
        Length(o), Length(n), Distance(o, n), sim.Legs);
    // Stable hold: more decisions move nobody and the dragons keep still.
    CHECK(Settle(sim, phase.c_str(), 5, true, true) == 0, "no oscillation once settled");
    CHECK(Distance(o, WorldToLocal(FindCreature(sim.Board, OnyxiaEntry)->Position)) < 0.01f,
        "Onyxia stays put while held");

    // Phase 2 without a pillar ascent: typed blocker, teams hold the feet.
    FindCreature(sim.Board, OnyxiaEntry)->Alive = false;
    phase = std::string(label) + ":platform_ascent";
    CHECK(Settle(sim, phase.c_str(), 40, false, false) >= 0, phase.c_str());
    AdaptiveNefarianStrategy strategy;
    for (uint32 slot = 1; slot <= 10; ++slot)
    {
        AdaptiveNefarianPlan const plan = strategy.Propose(sim.Board, Bot(slot),
            FindPlayer(sim.Board, slot).Role);
        CHECK(plan.Blocked == "pillar_ascent_unsupported" && plan.MovementSurface
            && plan.MovementSurface->Purpose == MovePurpose::PillarFoot,
            "every bot holds its pillar foot under the typed blocker");
    }

    // Phase 3: Nefarian lands at the centre; the raid re-forms on his wing.
    sim.Board.Summons.clear();
    ActorSnapshot landed = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    landed.InCombat = true;
    landed.VictimGuid = Bot(1);
    sim.Board.Summons = { landed };
    phase = std::string(label) + ":nefarian_ground";
    CHECK(Settle(sim, phase.c_str(), 60, false, false) >= 0, phase.c_str());
    CHECK(sim.Violations == 0, "every leg was a lawful surface walk");
}

static void TestPlannerCoverage()
{
    int failures_ = 0;
    int runs = 0;
    for (float fromRadius : { 0.0f, 12.0f, 25.0f, 33.5f, 49.2f, 55.0f })
        for (int fromAngle = 0; fromAngle < 360; fromAngle += 20)
            for (float toRadius : { 5.0f, 20.0f, 26.0f, 34.0f, 50.0f })
                for (int toAngle = 0; toAngle < 360; toAngle += 20)
                {
                    LocalPoint from = SnapToStandingArea(Polar(DegToRad(float(fromAngle)), fromRadius));
                    LocalPoint const goal = SnapToStandingArea(Polar(DegToRad(float(toAngle)), toRadius));
                    float z = FloorLocalZAt(from);
                    ++runs;
                    bool arrived = false;
                    for (int leg = 0; leg < 40; ++leg)
                    {
                        std::optional<PathLeg> const next = NextLeg(from, z, goal);
                        if (!next)
                        {
                            arrived = Distance(from, goal) <= LegArrivalYards + 0.01f;
                            break;
                        }
                        if (Distance(from, next->To) > MaxLegYards + 0.01f
                            || !SegmentClearOfPillars(from, next->To))
                            break;
                        from = next->To;
                        z = next->LocalZ;
                    }
                    if (!arrived)
                        ++failures_;
                }
    CHECK(failures_ == 0, "the planner converges between standing spots");
    std::printf("planner: %d runs, %d without convergence\n", runs, failures_);
}

int main()
{
    // The M1 encounter anchor / descent board point, and the ledge-drop landing.
    RunEncounter({ 25.0f, 0.0f }, PlatformFrame::FloorLocalZ, "board_point");
    RunEncounter({ 49.2f, 0.0f }, RingLocalZ, "ledge_landing");
    TestPlannerCoverage();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_nefarian_movement_legs_and_dragon_separation(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, MOVEMENT)

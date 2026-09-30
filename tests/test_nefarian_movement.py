"""Movement checks for the Nefarian's End strategy on the GO 207834 surface.

Package T's transport-surface walk accepts one straight leg of at most
MaxSurfaceWalkYards (12). These programs drive the canonical 10N raid through
the encounter with a native chase model (a dragon moves straight at its tank
and stops at its melee reach, and only turns while the tank stays inside that
reach), applying each emitted leg as the bot's new position, and check:
- every submitted TransportSurfaceMove is a Walk ending on the elevator,
  within MaxSurfaceWalkYards of the bot and clear of the pillars, and package
  T's surface-walk checks accept it against the sampled collision model
  (tests/test_nefarian_platform_profile.py probe_leg), starting each leg from
  the height the previous one ended at;
- the legs converge on the goals, from the route's board point (local 25, 0)
  and from the ledge-drop landing on the ring (local 49.2, 0);
- the tanks leave the dragons at their ends more than 50 yards apart (out of
  Children of Deathwing range), holding them without oscillating;
- the planner converges between every pair of standing spots.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_platform_profile import probe_leg
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
        if (!ok)
        {
            ++sim.Violations;
            std::fprintf(stderr, "bad leg %s %s (%.1f,%.1f)->(%.1f,%.1f) len %.2f purpose %s\n",
                phase, Names[slot], from.X, from.Y, to.X, to.Y, length,
                plan.Movement->Id.Mechanic.c_str());
            continue;
        }
        // Every leg goes to the Python probe (tests/test_nefarian_platform_profile.py),
        // which checks it against the sampled collision model, not FloorLocalZAt.
        std::printf("LEG %s %u %.4f %.4f %.4f %.4f %.4f %.4f %.3f\n", phase, slot,
            from.X, from.Y, bot.Position.Z - sim.OriginZ, to.X, to.Y,
            walk->Z - sim.OriginZ, walk->FloorToleranceYards);
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

    // Phase 2 on the raised floor: every team walks to its pillar's feet
    // (the swim-and-hop ascent from there is tests/test_nefarian_strategy.py
    // TestAscent). Without the swimmer's stages the plan also carries the
    // typed blocker.
    FindCreature(sim.Board, OnyxiaEntry)->Alive = false;
    phase = std::string(label) + ":platform_ascent";
    CHECK(Settle(sim, phase.c_str(), 40, false, false) >= 0, phase.c_str());
    AdaptiveNefarianStrategy strategy;
    DutyPlan const duty = BuildNefarianDutyPlan(sim.Board);
    for (uint32 slot = 1; slot <= 10; ++slot)
    {
        AdaptiveNefarianPlan const plan = strategy.Propose(sim.Board, Bot(slot),
            FindPlayer(sim.Board, slot).Role);
        CHECK(plan.Blocked == (RuntimePillarAscentSupported() ? "" : "pillar_ascent_unsupported")
            && plan.MovementSurface
            && plan.MovementSurface->Purpose == (RuntimePillarAscentSupported()
                ? MovePurpose::PillarAscent : MovePurpose::PillarFoot),
            "every bot heads for its pillar foot");
        int const pillar = duty.PillarOf(Bot(slot));
        CHECK(Distance(WorldToLocal(FindPlayer(sim.Board, slot).Position),
            PillarBase(uint8(pillar), duty.SlotOf(Bot(slot)))) <= 1.6f,
            "every bot reached its pillar foot on the raised floor");
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
    for (float fromRadius : { 0.0f, 12.0f, 25.0f, 30.0f, 33.5f, 49.2f, 55.0f })
        for (int fromAngle = 0; fromAngle < 360; fromAngle += 20)
            for (float toRadius : { 5.0f, 20.0f, 26.0f, 30.0f, 34.0f, 50.0f })
                for (int toAngle = 0; toAngle < 360; toAngle += 20)
                {
                    LocalPoint from = SnapToStandingArea(Polar(DegToRad(float(fromAngle)), fromRadius));
                    LocalPoint const goal = SnapToStandingArea(Polar(DegToRad(float(toAngle)), toRadius));
                    ++runs;
                    bool arrived = false;
                    float fromZ = FloorLocalZAt(from);
                    for (int leg = 0; leg < 40; ++leg)
                    {
                        std::optional<PathLeg> const next = NextLeg(from, goal);
                        if (!next)
                        {
                            arrived = Distance(from, goal) <= LegArrivalYards + 0.01f;
                            break;
                        }
                        if (Distance(from, next->To) > MaxLegYards + 0.01f
                            || !SegmentClearOfPillars(from, next->To))
                            break;
                        std::printf("LEGC %.2f %.2f %.2f %.2f %.2f %.2f %.2f\n", from.X, from.Y,
                            fromZ, next->To.X, next->To.Y, next->LocalZ,
                            next->FloorToleranceYards);
                        from = next->To;
                        fromZ = next->LocalZ;
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
    // Heights are the sampled model floor there (0.074 at the board point,
    // 1.439 on the ring), not the strategy's own floor model.
    RunEncounter({ 25.0f, 0.0f }, 0.074f, "board_point");
    RunEncounter({ 49.2f, 0.0f }, 1.439f, "ledge_landing");
    TestPlannerCoverage();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_nefarian_movement_legs_and_dragon_separation(tmp_path: Path) -> None:
    output = _compile_and_run(tmp_path, MOVEMENT)
    legs = [line.split() for line in output.splitlines() if line.startswith("LEG ")]
    assert len(legs) > 200
    refusals = {}
    for _, phase, slot, fx, fy, fz, tx, ty, tz, tolerance in legs:
        verdict = probe_leg((float(fx), float(fy), float(fz)),
                            (float(tx), float(ty), float(tz)), float(tolerance))
        if verdict != "surface_walk_verified":
            refusals.setdefault(verdict, []).append((phase, slot, fx, fy, tx, ty))
    assert not refusals, {reason: rows[:5] for reason, rows in refusals.items()}

    # Every distinct leg of the planner coverage (all 13,608 pairs of standing
    # spots), probed the same way.
    coverage = {tuple(line.split()[1:]) for line in output.splitlines()
                if line.startswith("LEGC ")}
    assert len(coverage) > 1000
    coverage_refusals = {}
    for fx, fy, fz, tx, ty, tz, tolerance in coverage:
        verdict = probe_leg((float(fx), float(fy), float(fz)),
                            (float(tx), float(ty), float(tz)), float(tolerance))
        if verdict != "surface_walk_verified":
            coverage_refusals.setdefault(verdict, []).append((fx, fy, fz, tx, ty, tz))
    assert not coverage_refusals, {reason: (len(rows), rows[:5])
                                   for reason, rows in coverage_refusals.items()}


# Round 3 (E3, E4). Bone warriors (user tactic, authoritative: the Feral kites
# them with Nature's Grasp and keeps them out of Nefarian's front). Round 2's
# warriors stayed active for 150-260 s and climbed the pillar-1 ramp to the
# casters on its rim. This chase model runs phase 3 with Hail of Bones'
# four warriors on their victims: a warrior walks straight at its victim at
# the run speed and stops in melee reach; Animate Bones costs 3 energy a
# second (collapse at 1, about 33 s); Nefarian faces his tank and breathes
# every 18 s, and his breath refills and re-animates every warrior in its
# cone (spell_nefarians_end_shadowflame_breath). The bots act on their plans:
# walking legs at the run speed, the handler's taunt (8 s cooldown) and
# Nature's Grasp (roots the next warrior that reaches it for 10 s), the
# shackler's Shackle Undead. The acceptance observation
# (BotNefarianWarriorWatch.h) must stay empty: no warrior active past 45 s,
# none on a pillar.
WARRIORS = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianWarriorWatch.h"
#include <map>

struct WarriorSim
{
    Blackboard Board;
    std::map<uint64, float> Energy;
    std::map<uint64, uint64> HeldUntil;
    std::map<uint32, uint64> TauntReadyAt;
    bool GraspArmed = false;
    uint64 NowMs = 0;
    int Refills = 0;
    int Collapses = 0;
};

static ActorSnapshot* Warrior(WarriorSim& sim, ObjectGuid guid)
{
    for (ActorSnapshot& actor : sim.Board.Summons)
        if (actor.Guid == guid)
            return &actor;
    return nullptr;
}

static void RemoveAura(ActorSnapshot& actor, uint32 spellId)
{
    actor.Auras.erase(std::remove_if(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; }), actor.Auras.end());
}

static void Place(ActorSnapshot& actor, LocalPoint at)
{
    actor.Position = LocalToWorld(at, FloorLocalZAt(at), PlatformFrame::RaisedOriginZ);
}

static LocalPoint Toward(LocalPoint from, LocalPoint to, float step)
{
    float const distance = Distance(from, to);
    if (distance <= step || distance < 1e-4f)
        return to;
    return { from.X + (to.X - from.X) * step / distance, from.Y + (to.Y - from.Y) * step / distance };
}

static void BotsAct(WarriorSim& sim)
{
    AdaptiveNefarianStrategy strategy;
    std::vector<std::pair<uint32, AdaptiveNefarianPlan>> plans;
    for (uint32 slot = 1; slot <= 10; ++slot)
        plans.emplace_back(slot, strategy.Propose(sim.Board, Bot(slot), FindPlayer(sim.Board, slot).Role));
    for (auto const& [slot, plan] : plans)
    {
        ActorSnapshot& bot = FindPlayer(sim.Board, slot);
        for (BotNativeAction::Candidate const& action : plan.Actions)
        {
            auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
            if (!cast)
                continue;
            if (action.Id.Mechanic == "bone_warrior_taunt" && sim.NowMs >= sim.TauntReadyAt[slot])
                if (ActorSnapshot* warrior = Warrior(sim, cast->Target);
                    warrior && Distance3(warrior->Position, bot.Position) <= 30.0f)
                {
                    warrior->VictimGuid = bot.Guid;
                    sim.TauntReadyAt[slot] = sim.NowMs + 8000;
                }
            if (action.Id.Mechanic == "bone_warrior_natures_grasp")
                sim.GraspArmed = true;
            if (action.Id.Mechanic == "bone_warrior_shackle")
                if (ActorSnapshot* warrior = Warrior(sim, cast->Target); warrior && !HasAura(*warrior, 9484))
                {
                    AddAura(*warrior, 9484);
                    sim.HeldUntil[warrior->Guid.GetRawValue()] = sim.NowMs + 30000;
                }
        }
        // Damage breaks a shackle or a root on the handler's target.
        if (ActorSnapshot* target = Warrior(sim, plan.DamageTarget); target && target->Entry == BoneWarriorEntry)
        {
            RemoveAura(*target, 9484);
            RemoveAura(*target, SpellNaturesGraspRoot);
        }
        auto const* walk = plan.Movement
            ? std::get_if<BotNativeAction::TransportSurfaceMove>(&plan.Movement->Action) : nullptr;
        if (walk && walk->Kind == BotNativeAction::TransportSurfaceMove::Stage::Walk)
            Place(bot, Toward(WorldToLocal(bot.Position), WorldToLocal({ walk->X, walk->Y, walk->Z }),
                RunSpeedYardsPerSecond));
    }
}

static void WarriorsAct(WarriorSim& sim)
{
    for (ActorSnapshot& warrior : sim.Board.Summons)
    {
        if (warrior.Entry != BoneWarriorEntry)
            continue;
        uint64 const key = warrior.Guid.GetRawValue();
        if (sim.HeldUntil[key] && sim.NowMs >= sim.HeldUntil[key])
        {
            RemoveAura(warrior, 9484);
            RemoveAura(warrior, SpellNaturesGraspRoot);
            sim.HeldUntil[key] = 0;
        }
        if (!IsActiveBoneWarrior(warrior))
            continue;
        sim.Energy[key] -= 3.0f;
        if (sim.Energy[key] <= 1.0f)
        {
            AddAura(warrior, SpellBoneFeignDeath);
            warrior.Selectable = false;
            warrior.VictimGuid = ObjectGuid();
            ++sim.Collapses;
            continue;
        }
        if (IsBoneWarriorHeld(warrior))
            continue;
        ActorSnapshot const* victim = sim.Board.FindActor(warrior.VictimGuid);
        if (!victim)
            continue;
        LocalPoint const at = WorldToLocal(warrior.Position);
        LocalPoint const to = WorldToLocal(victim->Position);
        float const reach = BoneWarriorMeleeReach - 0.6f;
        if (Distance(at, to) > reach)
            Place(warrior, Toward(at, to, std::min(RunSpeedYardsPerSecond, Distance(at, to) - reach)));
        // Nature's Grasp roots the first warrior that reaches the handler.
        if (sim.GraspArmed && victim->Guid == Bot(2)
            && Distance3(warrior.Position, victim->Position) <= BoneWarriorMeleeReach)
        {
            AddAura(warrior, SpellNaturesGraspRoot);
            sim.HeldUntil[key] = sim.NowMs + 10000;
            sim.GraspArmed = false;
        }
    }
}

static void NefarianActs(WarriorSim& sim, int second)
{
    ActorSnapshot* nefarian = nullptr;
    for (ActorSnapshot& actor : sim.Board.Summons)
        if (actor.Entry == NefarianEntry)
            nefarian = &actor;
    LocalPoint const body = WorldToLocal(nefarian->Position);
    LocalPoint const tank = WorldToLocal(FindPlayer(sim.Board, 1).Position);
    nefarian->Facing = NormalizeSigned(AngleOf({ tank.X - body.X, tank.Y - body.Y })
        + PlatformFrame::Orientation);
    if (second % 18 != 9)
        return;
    DragonPose const pose = PoseOf(*nefarian);
    for (ActorSnapshot& warrior : sim.Board.Summons)
        if (warrior.Entry == BoneWarriorEntry && InFrontCone(pose, WorldToLocal(warrior.Position), 0.0f))
        {
            sim.Energy[warrior.Guid.GetRawValue()] = 100.0f;
            RemoveAura(warrior, SpellBoneFeignDeath);
            warrior.Selectable = true;
            ++sim.Refills;
        }
}

static void TestWarriorsStayOutOfTheFront()
{
    WarriorSim sim;
    sim.Board = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    sim.Board.Summons = { nefarian };
    ArenaLayout const layout = BuildArenaLayout(BuildNefarianDutyPlan(sim.Board));
    // Everyone starts on the floor where the descent lands, then the raid
    // forms up for 20 s before the warriors wake.
    for (ActorSnapshot& player : sim.Board.Players)
        Place(player, Polar(layout.NefarianGroundFacing + Pi / 2.0f, 30.0f));
    for (int second = 0; second < 20; ++second)
    {
        BotsAct(sim);
        NefarianActs(sim, 0);
    }
    // Hail of Bones' four warriors, each on a victim: the tank in front (the
    // worst case), the rim casters' pillar feet and the hunter.
    struct Spawn { LocalPoint At; uint32 Victim; };
    Spawn const spawns[] = {
        { Offset(WorldToLocal(FindPlayer(sim.Board, 1).Position), layout.NefarianGroundFacing, 3.0f), 1 },
        { PillarBase(1, 0), 4 }, { PillarBase(1, 3), 10 }, { PillarBase(0, 2), 3 },
    };
    uint32 counter = 40;
    for (Spawn const& spawn : spawns)
    {
        ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, counter++, spawn.At);
        warrior.InCombat = true;
        warrior.VictimGuid = Bot(spawn.Victim);
        sim.Energy[warrior.Guid.GetRawValue()] = 100.0f;
        sim.Board.Summons.push_back(warrior);
    }
    WarriorWatch watch;
    std::vector<WarriorViolation> violations;
    for (int second = 0; second < 150; ++second)
    {
        sim.NowMs = uint64(second) * 1000;
        sim.Board.ObservedAtMs = 1790000000000ull + sim.NowMs;
        BotsAct(sim);
        WarriorsAct(sim);
        NefarianActs(sim, second);
        std::vector<WarriorViolation> const found = watch.Observe(ObserveEncounter(sim.Board),
            sim.Board.ObservedAtMs);
        violations.insert(violations.end(), found.begin(), found.end());
        for (ActorSnapshot const& warrior : sim.Board.Summons)
            if (warrior.Entry == BoneWarriorEntry)
            {
                float distance = 0.0f;
                NearestPillar(WorldToLocal(warrior.Position), distance);
                CHECK(distance >= PillarSkirtRadius, "no warrior walks onto a pillar structure");
            }
    }
    std::printf("WARRIORS refills %d collapses %d violations %zu\n", sim.Refills, sim.Collapses,
        violations.size());
    for (WarriorViolation const& violation : violations)
        std::printf("VIOLATION %s warrior %u active %llu ms\n",
            std::string(WarriorViolationName(violation.Kind)).c_str(),
            violation.Warrior.GetCounter(), static_cast<unsigned long long>(violation.ActiveMs));
    CHECK(violations.empty(), "E3: no warrior stays active past 45 s or reaches a pillar");
    CHECK(sim.Collapses >= 4, "every warrior collapses");
}

// The acceptance observation itself: once per warrior and kind, a collapse
// ends the active span, a wake starts a new one, and a warrior on a pillar
// structure is named.
//
// The reporter observes every decision, so the watch sees a warrior in steps
// well inside WarriorObservationGapMs; a longer silence breaks its spans
// (tests/test_nefarian_observation_clock.py).
static std::vector<WarriorViolation> ObserveTo(WarriorWatch& watch, Blackboard const& board,
    uint64& clock, uint64 to)
{
    std::vector<WarriorViolation> all;
    while (clock < to)
    {
        clock = std::min(clock + 1000, to);
        std::vector<WarriorViolation> const found = watch.Observe(ObserveEncounter(board), clock);
        all.insert(all.end(), found.begin(), found.end());
    }
    return all;
}

static void TestWarriorWatch()
{
    Blackboard board = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    nefarian.InCombat = true;
    ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, 40, { 10.0f, 0.0f });
    board.Summons = { nefarian, warrior };
    WarriorWatch watch;
    uint64 const t0 = 1790000000000ull;
    uint64 clock = t0;
    CHECK(watch.Observe(ObserveEncounter(board), t0).empty(), "a fresh warrior is not a violation");
    CHECK(ObserveTo(watch, board, clock, t0 + WarriorActiveLimitMs).empty(), "45 s is the limit");
    std::vector<WarriorViolation> over = ObserveTo(watch, board, clock, t0 + WarriorActiveLimitMs + 1000);
    CHECK(over.size() == 1 && over[0].Kind == WarriorViolationKind::ActiveOverLimit
        && over[0].ActiveMs == WarriorActiveLimitMs + 1000, "past 45 s active: reported");
    CHECK(ObserveTo(watch, board, clock, t0 + 60000).empty(), "reported once");
    AddAura(board.Summons[1], SpellBoneFeignDeath);
    board.Summons[1].Selectable = false;
    CHECK(ObserveTo(watch, board, clock, t0 + 61000).empty(), "a collapse ends the span");
    RemoveAura(board.Summons[1], SpellBoneFeignDeath);
    board.Summons[1].Selectable = true;
    CHECK(ObserveTo(watch, board, clock, t0 + 62000).empty(), "a refill starts a new span");
    CHECK(ObserveTo(watch, board, clock, t0 + 62000 + WarriorActiveLimitMs + 1).size() == 1,
        "and the new span is judged on its own");
    CHECK(!watch.CoverageBroken(), "observed at a steady cadence: coverage stays whole");
    // On pillar 1's rim (local z 9.3): reported; at the pillar's foot: not.
    // (The watch's clock only goes forward: an older snapshot is skipped,
    // tests/test_nefarian_observation_scope.py.)
    ActorSnapshot climber = MakeCreature(BoneWarriorEntry, 41, PillarRadial(1, 0, DescentRimRadius),
        0.0f, 9.3f);
    ActorSnapshot foot = MakeCreature(BoneWarriorEntry, 42, PillarBase(1, 0));
    board.Summons.push_back(climber);
    board.Summons.push_back(foot);
    std::vector<WarriorViolation> const pillar = ObserveTo(watch, board, clock, t0 + 108000);
    CHECK(pillar.size() == 1 && pillar[0].Kind == WarriorViolationKind::OnPillar
        && pillar[0].Warrior == climber.Guid, "a warrior on the rim is reported, one at the foot is not");
}

// E4: the hunter's formation spot keeps Spell::GetMinMaxRange's melee-extended
// minimum range from its dragon (5 + the dragon's melee reach), inside the
// sight range; a caster's does not carry one.
static void TestStandoffFormation()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { -4.0f, 3.0f }, 0.7f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    board.Summons = { nefarian };
    for (ActorSnapshot& player : board.Players)
        Place(player, { 8.0f, 6.0f });
    float const minRange = StandoffSpellMinRangeYards + NefarianMeleeReach;
    for (int tick = 0; tick < 30; ++tick)
        for (uint32 slot : { 3u, 4u })
        {
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(slot), "dps");
            auto const* walk = plan.Movement
                ? std::get_if<BotNativeAction::TransportSurfaceMove>(&plan.Movement->Action) : nullptr;
            if (walk)
                Place(FindPlayer(board, slot), WorldToLocal({ walk->X, walk->Y, walk->Z }));
        }
    LocalPoint const body = WorldToLocal(nefarian.Position);
    AdaptiveNefarianPlan const hunter = strategy.Propose(board, Bot(3), "dps");
    float const hunterRange = Distance(WorldToLocal(FindPlayer(board, 3).Position), body);
    std::printf("STANDOFF hunter %.2f (min %.2f) mage %.2f\n", hunterRange, minRange,
        Distance(WorldToLocal(FindPlayer(board, 4).Position), body));
    CHECK(hunter.DamageTarget == nefarian.Guid && !hunter.Movement
        && hunterRange >= minRange && hunterRange <= SightRangeYards,
        "the hunter settles outside Nefarian's minimum range, within sight range");
    CHECK(hunter.MovementSurface && Near(hunter.MovementSurface->SightMinRangeYards,
        minRange + StandoffMarginYards), "its goal carries the minimum range");
    AdaptiveNefarianPlan const mage = strategy.Propose(board, Bot(4), "dps");
    CHECK(mage.MovementSurface && mage.MovementSurface->SightMinRangeYards == 0.0f,
        "a caster has no minimum range");
    // Inside the minimum range the hunter's spot no longer serves: a
    // correction leg outward, even inside the arrival tolerance.
    Place(FindPlayer(board, 3), Offset(body, AngleOf({ WorldToLocal(FindPlayer(board, 3).Position).X - body.X,
        WorldToLocal(FindPlayer(board, 3).Position).Y - body.Y }), minRange - 1.0f));
    AdaptiveNefarianPlan const inside = strategy.Propose(board, Bot(3), "dps");
    auto const* out = inside.Movement
        ? std::get_if<BotNativeAction::TransportSurfaceMove>(&inside.Movement->Action) : nullptr;
    CHECK(out && Distance(WorldToLocal({ out->X, out->Y, out->Z }), body) > minRange - 1.0f,
        "inside the minimum range the hunter steps back out");
    // Phase 1 against Onyxia: 5 + her melee reach.
    CHECK(Near(StandoffMinRange(MovementContext{ board, ObserveEncounter(board),
        BuildNefarianDutyPlan(board), BuildArenaLayout(BuildNefarianDutyPlan(board)),
        FindPlayer(board, 3), nullptr }, nefarian.Guid), minRange + StandoffMarginYards),
        "the Nefarian standoff range");
    CHECK(Near(StandoffSpellMinRangeYards + OnyxiaMeleeReach, 25.83f, 0.01f)
        && Near(minRange, 27.83f, 0.01f), "Spell::GetMinMaxRange's extended minimum ranges");
}

int main()
{
    TestWarriorWatch();
    TestStandoffFormation();
    TestWarriorsStayOutOfTheFront();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_nefarian_bone_warriors_and_standoff_formation(tmp_path: Path) -> None:
    output = _compile_and_run(tmp_path, WARRIORS)
    assert "WARRIORS" in output and "STANDOFF" in output


def test_nefarian_bone_warriors_under_sanitizers(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, WARRIORS, sanitize=True)

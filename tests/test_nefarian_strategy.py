"""Header-only checks for the Nefarian's End adaptive strategy.

The C++ program below includes the production headers from
src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian and
exercises phase detection, the capability duty plan for the canonical 10N
composition, platform geometry, the phase 1 Electrocute budget, Blast Nova
interrupts, bone warrior control, tank leading and the movement goals handed
to the transport-surface movement layer.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "src/server/game",
    "src/server/game/Entities/Object",
    "src/common",
    "src/common/Utilities",
    "src/common/Logging",
    "src/common/Debugging",
]


def _compile_and_run(tmp_path: Path, program: str) -> None:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include <cstdio>
#include <string>

using namespace BotEncounter;
using namespace BotEncounter::Nefarian;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

static bool Near(float left, float right, float tolerance = 0.05f)
{
    return std::fabs(left - right) <= tolerance;
}

static ObjectGuid Bot(uint32 slot) { return ObjectGuid(HighGuid::Player, uint32(30500 + slot)); }

static ActorSnapshot MakePlayer(uint32 slot, char const* role, char const* spec,
    LocalPoint at, float localZ = PlatformFrame::FloorLocalZ,
    float originZ = PlatformFrame::RaisedOriginZ)
{
    ActorSnapshot actor;
    actor.Guid = Bot(slot);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = spec;
    actor.Position = LocalToWorld(at, localZ, originZ);
    actor.Alive = true;
    actor.HealthPct = 100.0f;
    return actor;
}

static ActorSnapshot MakeCreature(uint32 entry, uint32 counter, LocalPoint at,
    float localFacing = 0.0f, float localZ = PlatformFrame::FloorLocalZ,
    float originZ = PlatformFrame::RaisedOriginZ)
{
    ActorSnapshot actor;
    actor.Guid = ObjectGuid(HighGuid::Unit, entry, counter);
    actor.Entry = entry;
    actor.Kind = ActorKind::Summon;
    actor.Position = LocalToWorld(at, localZ, originZ);
    actor.Facing = NormalizeSigned(localFacing + PlatformFrame::Orientation);
    actor.Alive = actor.Attackable = actor.Selectable = true;
    actor.HealthPct = 100.0f;
    return actor;
}

static ActorSnapshot MakeElevator(float originZ)
{
    ActorSnapshot elevator;
    elevator.Guid = ObjectGuid(HighGuid::GameObject, ElevatorEntry, uint32(235179));
    elevator.Entry = ElevatorEntry;
    elevator.Kind = ActorKind::Interactable;
    elevator.Position = { PlatformFrame::OriginX, PlatformFrame::OriginY, originZ };
    elevator.Alive = true;
    return elevator;
}

static void AddAura(ActorSnapshot& actor, uint32 spellId, uint8 stacks = 1)
{
    AuraSnapshot aura;
    aura.SpellId = spellId;
    aura.Stacks = stacks;
    actor.Auras.push_back(aura);
}

// Canonical composition (experiments/configs/raid_compositions/blackwing_descent_10n.json)
// with the Nefarian spec selection: Feral tank and Restoration shaman.
static Blackboard CanonicalBoard(float originZ = PlatformFrame::RaisedOriginZ)
{
    Blackboard board;
    board.CurrentScope = Scope{ "blackwing_descent_10n_nefarian_c0", 3, 0, 5,
        "bwd.nefarian.encounter", 669, 2, "tank_swap_adds_raid_aoe" };
    board.Revision = 40;
    board.ObservedAtMs = 1790000000000ull;
    board.Route.NodeId = "bwd.nefarian.encounter";
    board.Players = {
        MakePlayer(1, "tank", "blood_death_knight", { 0.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(2, "tank", "feral_druid_tank", { 1.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(3, "dps", "beast_mastery_hunter", { 2.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(4, "dps", "fire_mage", { 3.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(5, "healer", "holy_paladin", { 4.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(6, "dps", "retribution_paladin", { 5.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(7, "healer", "discipline_priest", { 6.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(8, "dps", "assassination_rogue", { 7.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(9, "healer", "restoration_shaman", { 8.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
        MakePlayer(10, "dps", "demonology_warlock", { 9.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
    };
    board.Interactables = { MakeElevator(originZ) };
    return board;
}

static ActorSnapshot& FindPlayer(Blackboard& board, uint32 slot)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid == Bot(slot))
            return player;
    return board.Players.front();
}

static void TestGeometry()
{
    Vector3 const top = LocalToWorld(PillarCenters[0], PlatformFrame::PillarTopLocalZ,
        PlatformFrame::LoweredOriginZ);
    CHECK(Near(top.X, -147.718f) && Near(top.Y, -224.557f) && Near(top.Z, 3.057f),
        "pillar 0 top in world frame at the lowered stop");
    LocalPoint const board = WorldToLocal({ -132.2132f, -224.6203f, 6.5714f });
    CHECK(Near(board.X, 25.0f) && Near(board.Y, 0.0f), "route board point is local (25,0)");
    LocalPoint const back = WorldToLocal(LocalToWorld({ -12.5f, 31.0f }, 0.0f, 0.0f));
    CHECK(Near(back.X, -12.5f) && Near(back.Y, 31.0f), "local/world round trip");
    CHECK(Near(PlatformFrame::RaisedOriginZ + PlatformFrame::FloorLocalZ, 6.5714f, 0.001f),
        "raised floor matches the route board height");

    DragonPose const dragon{ { 0.0f, 0.0f }, 0.0f };
    CHECK(InFrontCone(dragon, { 20.0f, 0.0f }), "ahead is in the breath cone");
    CHECK(!InFrontCone(dragon, { 0.0f, 20.0f }), "the wing is outside the breath cone");
    CHECK(InRearCone(dragon, { -20.0f, 0.0f }), "behind is in the tail lash cone");
    CHECK(!InRearCone(dragon, { 0.0f, -20.0f }), "the wing is outside the tail lash cone");
    CHECK(InDischargeFlank(dragon, { 0.0f, 20.0f }), "Lightning Discharge hits the wing");
    CHECK(!InDischargeFlank(dragon, { -20.0f, 0.0f }), "Lightning Discharge spares the back cone");
    CHECK(!InDischargeFlank(dragon, { 20.0f, 0.0f }), "Lightning Discharge spares the front cone");
    CHECK(!InDischargeFlank(dragon, { 0.0f, 70.0f }), "Lightning Discharge radius is 60 yards");
    for (uint8 pillar = 0; pillar < 3; ++pillar)
        for (uint8 slot = 0; slot < 4; ++slot)
        {
            LocalPoint const spot = PillarSlot(pillar, slot);
            CHECK(Distance(spot, PillarCenters[pillar]) < PrototypeMeleeReach - 2.0f,
                "pillar slots stay in the prototype's melee reach");
            CHECK(OnFloorArea(PillarBase(pillar, slot)), "pillar bases are floor spots");
        }
}

static void TestDutyPlan()
{
    Blackboard const board = CanonicalBoard();
    DutyPlan const plan = BuildNefarianDutyPlan(board);
    std::string const json = NefarianDutyPlanJson(plan);
    std::string const expected = "{\"applies\":true,\"nefarian_tank\":30501,"
        "\"onyxia_tank\":30502,\"shackler\":30507,\"pillars\":["
        "{\"members\":[30505,30508,30502,30510],\"healer\":30505,\"interrupt\":30508,\"backup\":30505},"
        "{\"members\":[30507,30501,30504],\"healer\":30507,\"interrupt\":30501,\"backup\":30504},"
        "{\"members\":[30509,30506,30503],\"healer\":30509,\"interrupt\":30506,\"backup\":30509}],"
        "\"controllers\":[30505,30506,30503,30509,30510,30504]}";
    CHECK(json == expected, json.c_str());

    ArenaLayout const layout = BuildArenaLayout(plan);
    CHECK(Near(layout.OnyxiaEndAngle, DegToRad(30.0f), 0.01f), "Onyxia's end beside pillar 0");
    CHECK(AngularGap(layout.NefarianEndAngle, PillarAngle(1)) < DegToRad(30.0f),
        "Nefarian's end beside his tank's pillar");
    LocalPoint const onyxiaEnd = Polar(layout.OnyxiaEndAngle, 29.0f);
    LocalPoint const nefarianEnd = Polar(layout.NefarianEndAngle, 29.0f);
    CHECK(Distance(onyxiaEnd, nefarianEnd) > ChildrenOfDeathwingRange,
        "the two ends are beyond Children of Deathwing range");

    // A dead member keeps its pillar; its duty moves to a living teammate.
    Blackboard withDead = CanonicalBoard();
    FindPlayer(withDead, 8).Alive = false;
    DutyPlan const reduced = BuildNefarianDutyPlan(withDead);
    CHECK(reduced.PillarOf(Bot(8)) == 0, "dead rogue keeps pillar 0");
    CHECK(reduced.Pillars[0].PrimaryInterrupter == Bot(5), "holy paladin takes pillar 0 interrupts");
    CHECK(reduced.Pillars[0].BackupInterrupter == Bot(2), "feral tank backs up pillar 0");

    // External humans never receive a duty.
    Blackboard withHuman = CanonicalBoard();
    withHuman.ExternalPlayers.push_back(MakePlayer(40, "tank", "protection_paladin", { 0.0f, 5.0f }));
    CHECK(NefarianDutyPlanJson(BuildNefarianDutyPlan(withHuman)) == expected,
        "external players do not change the plan");
}

static void AddDragons(Blackboard& board, bool landed)
{
    ActorSnapshot onyxia = MakeCreature(OnyxiaEntry, 11, Polar(DegToRad(30.0f), 29.0f),
        DegToRad(125.0f));
    onyxia.InCombat = true;
    onyxia.VictimGuid = Bot(2);
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12,
        landed ? Polar(DegToRad(-150.0f), 29.0f) : LocalPoint{ 0.0f, 0.0f },
        DegToRad(-55.0f), landed ? PlatformFrame::FloorLocalZ : 60.0f);
    nefarian.Flying = !landed;
    nefarian.InCombat = landed;
    nefarian.VictimGuid = landed ? Bot(1) : ObjectGuid();
    board.Summons.push_back(onyxia);
    board.Summons.push_back(nefarian);
}

static void TestPhases()
{
    Blackboard board = CanonicalBoard();
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::Inactive, "no dragons: inactive");

    AddDragons(board, false);
    board.Summons[0].InCombat = false;
    AddAura(board.Summons[0], SpellOnyxiaFeignDeath);
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::PreEngage, "feign-dead Onyxia: pre-engage");
    board.Summons[0].Auras.clear();
    board.Summons[0].InCombat = true;
    CHECK(ObserveEncounter(board).CurrentPhase == Phase::OnyxiaOnly, "Onyxia engaged, Nefarian airborne");

    Blackboard both = CanonicalBoard();
    AddDragons(both, true);
    CHECK(ObserveEncounter(both).CurrentPhase == Phase::BothDragons, "Nefarian landed");

    Blackboard wrongNode = both;
    wrongNode.Route.NodeId = "bwd.nefarian.descent";
    CHECK(ObserveEncounter(wrongNode).CurrentPhase == Phase::Inactive, "other route node: inactive");

    Blackboard corpse = both;
    corpse.Summons[0].Alive = false;
    CHECK(ObserveEncounter(corpse).CurrentPhase == Phase::PlatformAscent, "Onyxia's corpse: ascend");

    Blackboard hold = CanonicalBoard(PlatformFrame::LoweredOriginZ);
    ActorSnapshot flying = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f, 40.0f,
        PlatformFrame::LoweredOriginZ);
    flying.Flying = true;
    flying.InCombat = true;
    AddAura(flying, SpellPhaseTwoHealthAura);
    hold.Summons.push_back(flying);
    for (uint8 pillar = 0; pillar < 3; ++pillar)
    {
        ActorSnapshot prototype = MakeCreature(PrototypeEntry, 20 + pillar,
            PillarCenters[pillar], 0.0f, PlatformFrame::PillarTopLocalZ,
            PlatformFrame::LoweredOriginZ);
        prototype.InCombat = true;
        hold.Summons.push_back(prototype);
    }
    CHECK(ObserveEncounter(hold).CurrentPhase == Phase::PlatformHold, "prototypes, floor lowered");

    Blackboard lowering = hold;
    lowering.Interactables = { MakeElevator(0.0f) };
    CHECK(ObserveEncounter(lowering).CurrentPhase == Phase::PlatformAscent, "floor still moving down");

    Blackboard returning = hold;
    returning.Summons.resize(1);
    returning.Interactables = { MakeElevator(0.0f) };
    CHECK(ObserveEncounter(returning).CurrentPhase == Phase::PlatformReturn,
        "prototypes dead, floor rising: stay on the pillar");

    Blackboard landing = returning;
    landing.Interactables = { MakeElevator(PlatformFrame::RaisedOriginZ) };
    CHECK(ObserveEncounter(landing).CurrentPhase == Phase::NefarianLanding,
        "floor raised, Nefarian airborne: leave the pillars");

    Blackboard ground = landing;
    ground.Summons[0].Flying = false;
    ground.Summons[0].Auras.clear();
    CHECK(ObserveEncounter(ground).CurrentPhase == Phase::NefarianGround, "phase 3");
    ground.Summons[0].Alive = false;
    CHECK(ObserveEncounter(ground).CurrentPhase == Phase::Done, "Nefarian dead: done");
}

static void TestPhaseOneTarget()
{
    Blackboard board = CanonicalBoard();
    AddDragons(board, true);
    ActorSnapshot& onyxia = board.Summons[0];
    ActorSnapshot& nefarian = board.Summons[1];
    onyxia.HealthPct = 50.0f;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board)) == onyxia.Guid, "Onyxia first");
    onyxia.HealthPct = 10.0f;
    onyxia.AlternatePower = 20;
    nefarian.HealthPct = 95.0f;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board)) == nefarian.Guid,
        "Onyxia low: spend two Electrocutes on Nefarian");
    onyxia.AlternatePower = 65;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board)) == onyxia.Guid,
        "charge near overload: finish Onyxia");
    onyxia.AlternatePower = 20;
    nefarian.HealthPct = 72.0f;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board)) == onyxia.Guid,
        "Nefarian at the budget floor: finish Onyxia");

    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const tank = strategy.Propose(board, Bot(2), "tank");
    CHECK(tank.OwnsNode && tank.DamageTarget == onyxia.Guid, "Onyxia tank keeps Onyxia");
    AdaptiveNefarianPlan const healer = strategy.Propose(board, Bot(7), "healer");
    CHECK(healer.OwnsNode && healer.DamageTarget.IsEmpty() && !healer.SuppressOffense,
        "healers keep their native healing");
}

static Blackboard PlatformBoard(float originZ)
{
    Blackboard board = CanonicalBoard(originZ);
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f, 40.0f, originZ);
    nefarian.Flying = true;
    nefarian.InCombat = true;
    AddAura(nefarian, SpellPhaseTwoHealthAura);
    board.Summons.push_back(nefarian);
    for (uint8 pillar = 0; pillar < 3; ++pillar)
    {
        ActorSnapshot prototype = MakeCreature(PrototypeEntry, 20 + pillar, PillarCenters[pillar],
            0.0f, PlatformFrame::PillarTopLocalZ, originZ);
        prototype.InCombat = true;
        board.Summons.push_back(prototype);
    }
    // Pillar 1 team on its pillar top: disc priest, death knight, mage.
    uint8 slot = 0;
    for (uint32 member : { 7u, 1u, 4u })
        FindPlayer(board, member).Position = LocalToWorld(PillarSlot(1, slot++),
            PlatformFrame::PillarTopLocalZ, originZ);
    return board;
}

static void TestInterrupts()
{
    Blackboard board = PlatformBoard(PlatformFrame::LoweredOriginZ);
    CastSnapshot nova;
    nova.SpellId = 80734;
    nova.Interruptible = true;
    board.Summons[2].Cast = nova; // pillar 1 prototype
    EncounterView const view = ObserveEncounter(board);
    DutyPlan const plan = BuildNefarianDutyPlan(board);
    ActorSnapshot const& knight = FindPlayer(board, 1);
    ActorSnapshot const& mage = FindPlayer(board, 4);

    InterruptDecision const primary = DecideBlastNovaInterrupt(board, view, plan, knight, nullptr);
    CHECK(primary.Target == board.Summons[2].Guid && primary.SpellId == 47528,
        "death knight Mind Freezes his pillar's Blast Nova");
    CHECK(DecideBlastNovaInterrupt(board, view, plan, mage, nullptr).Target.IsEmpty(),
        "backup waits while the primary can interrupt");

    NativeFacts late;
    late.Casts.push_back({ board.Summons[2].Guid, 80734, 4000, 2000 });
    InterruptDecision const backup = DecideBlastNovaInterrupt(board, view, plan, mage, &late);
    CHECK(backup.SpellId == 2139 && backup.Reason == "blast_nova_backup_primary_late",
        "backup Counterspells after 2 s of the 4 s cast");

    Blackboard dead = board;
    FindPlayer(dead, 1).Alive = false;
    EncounterView const deadView = ObserveEncounter(dead);
    DutyPlan const deadPlan = BuildNefarianDutyPlan(dead);
    InterruptDecision const replacement = DecideBlastNovaInterrupt(dead, deadView, deadPlan,
        FindPlayer(dead, 4), nullptr);
    CHECK(replacement.SpellId == 2139, "mage interrupts when the death knight is dead");

    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const plan1 = strategy.Propose(board, Bot(1), "tank");
    CHECK(plan1.InterruptTarget == board.Summons[2].Guid && plan1.Actions.size() == 1
        && plan1.Actions[0].ActionPriority == BotActionArbitration::Priority::Interrupt,
        "legacy interrupt target and exact Mind Freeze candidate");
    CHECK(plan1.DamageTarget == board.Summons[2].Guid, "platform team damages its prototype");

    Blackboard quiet = board;
    quiet.Summons[2].Cast->Interruptible = false;
    CHECK(strategy.Propose(quiet, Bot(1), "tank").InterruptTarget.IsEmpty(),
        "no interrupt on an uninterruptible cast");

    Blackboard cleared = board;
    cleared.Summons.erase(cleared.Summons.begin() + 2);
    AdaptiveNefarianPlan const helper = strategy.Propose(cleared, Bot(4), "dps");
    CHECK(!helper.DamageTarget.IsEmpty() && helper.DamageTarget != cleared.Summons[0].Guid,
        "a cleared pillar helps with another prototype, never Nefarian");
    Blackboard allDead = cleared;
    allDead.Summons.resize(1);
    allDead.Interactables = { MakeElevator(PlatformFrame::LoweredOriginZ) };
    AdaptiveNefarianPlan const idle = strategy.Propose(allDead, Bot(4), "dps");
    CHECK(idle.DamageTarget.IsEmpty() && idle.SuppressOffense
        && idle.SuppressReason == "nefarian_platform_no_prototype",
        "no Nefarian damage in phase 2 once every prototype is dead");
}

static void TestBoneWarriorControl()
{
    Blackboard board = CanonicalBoard();
    AddDragons(board, true);
    ActorSnapshot first = MakeCreature(BoneWarriorEntry, 31, { 4.0f, 2.0f });
    ActorSnapshot second = MakeCreature(BoneWarriorEntry, 32, { 6.0f, -2.0f });
    AddAura(second, 79330, 5);
    first.VictimGuid = Bot(5);
    second.VictimGuid = Bot(3);
    board.Summons.push_back(first);
    board.Summons.push_back(second);
    EncounterView const view = ObserveEncounter(board);
    DutyPlan const plan = BuildNefarianDutyPlan(board);

    ControlDecision const shackle = DecideBoneWarriorControl(board, view, plan, FindPlayer(board, 7));
    CHECK(shackle.SpellId == SpellShackleUndead && shackle.Target == second.Guid,
        "shackle the most empowered warrior");
    ControlDecision const stun = DecideBoneWarriorControl(board, view, plan, FindPlayer(board, 5));
    CHECK(stun.SpellId == 853 && stun.Target == first.Guid, "holy paladin stuns warrior 1");
    CHECK(DecideBoneWarriorControl(board, view, plan, FindPlayer(board, 6)).Target.IsEmpty(),
        "nobody damages the shackler's candidate");
    CHECK(DecideBoneWarriorControl(board, view, plan, FindPlayer(board, 3)).Target.IsEmpty(),
        "one controller per warrior per snapshot");

    Blackboard noShackler = board;
    FindPlayer(noShackler, 7).Alive = false;
    EncounterView const noShacklerView = ObserveEncounter(noShackler);
    DutyPlan const noShacklerPlan = BuildNefarianDutyPlan(noShackler);
    ControlDecision const secondStun = DecideBoneWarriorControl(noShackler, noShacklerView,
        noShacklerPlan, FindPlayer(noShackler, 6));
    CHECK(secondStun.SpellId == 853 && secondStun.Target == second.Guid,
        "without a living priest the ret stuns warrior 2");

    Blackboard held = board;
    AddAura(held.Summons[2], 853);
    AddAura(held.Summons[3], SpellShackleUndead);
    EncounterView const heldView = ObserveEncounter(held);
    CHECK(DecideBoneWarriorControl(held, heldView, plan, FindPlayer(held, 5)).Target.IsEmpty(),
        "no control over a held warrior");
    CHECK(DecideBoneWarriorControl(held, heldView, plan, FindPlayer(held, 7)).Target.IsEmpty(),
        "one shackle at a time");

    Blackboard collapsed = noShackler;
    AddAura(collapsed.Summons[2], SpellBoneFeignDeath);
    collapsed.Summons[2].Selectable = false;
    EncounterView const collapsedView = ObserveEncounter(collapsed);
    CHECK(DecideBoneWarriorControl(collapsed, collapsedView, noShacklerPlan,
        FindPlayer(collapsed, 5)).Target == second.Guid, "collapsed warriors are ignored");

    // The chased hunter kites; tanks never kite.
    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const hunter = strategy.Propose(board, Bot(3), "dps");
    CHECK(hunter.MovementSurface && hunter.MovementSurface->Purpose == MovePurpose::Kite,
        "chased hunter kites");
    CHECK(hunter.Movement && hunter.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival, "kiting is survival movement");
}

static void TestTankSpots()
{
    float const goal = DegToRad(30.0f);
    TankSpot const lead = PlanTankSpot({ 0.0f, 0.0f }, goal, OnyxiaMeleeReach, false);
    CHECK(lead.Step == TankStep::LeadOut && Near(Length(lead.Point), TankRunRadius, 0.01f),
        "lead the dragon out from the centre");
    CHECK(!NearPillar(lead.Point), "lead point is clear of the pillars");

    LocalPoint const pulled = Polar(AngleOf(lead.Point), 12.0f);
    TankSpot const orbit = PlanTankSpot(pulled, goal, OnyxiaMeleeReach, false);
    CHECK(orbit.Step == TankStep::Orbit, "orbit toward the dragon's end");
    CHECK(Distance(orbit.Point, pulled) > OnyxiaMeleeReach, "orbit point pulls the dragon");

    LocalPoint const atEnd = Polar(goal, 29.0f);
    TankSpot const hold = PlanTankSpot(atEnd, goal, OnyxiaMeleeReach, false);
    CHECK(hold.Step == TankStep::Hold && Distance(hold.Point, atEnd) < OnyxiaMeleeReach - 3.0f,
        "hold inside reach so the dragon only turns");
    LocalPoint const toTank{ hold.Point.X - atEnd.X, hold.Point.Y - atEnd.Y };
    float const tangential = std::fabs(NormalizeSigned(AngleOf(toTank) - goal));
    CHECK(tangential > DegToRad(60.0f) && tangential < DegToRad(120.0f),
        "held dragon faces along the wall");

    TankSpot const turn = PlanTankSpot(atEnd, goal, OnyxiaMeleeReach, true);
    CHECK(turn.Step == TankStep::Discharge && Near(Length(turn.Point), 34.0f, 0.1f),
        "Lightning Discharge: step outward so her tail faces the raid");
    DragonPose const turned{ atEnd, goal };
    CHECK(!InDischargeFlank(turned, { 0.0f, 0.0f }), "the raid at the centre is then in her back cone");
}

static void TestPlatformMovement()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard ascent = CanonicalBoard();
    AddDragons(ascent, true);
    ascent.Summons[0].Alive = false;
    AdaptiveNefarianPlan const base = strategy.Propose(ascent, Bot(1), "tank");
    CHECK(base.Phase == Phase::PlatformAscent && base.MovementSurface
        && base.MovementSurface->Target == Surface::Floor
        && base.MovementSurface->Pillar == 1, "floor still up: wait at the pillar's foot");

    Blackboard sinking = ascent;
    sinking.Interactables = { MakeElevator(2.0f) };
    AdaptiveNefarianPlan const foot = strategy.Propose(sinking, Bot(1), "tank");
    CHECK(foot.MovementSurface && foot.MovementSurface->Purpose == MovePurpose::PillarFoot
        && foot.MovementSurface->Target == Surface::Floor,
        "without a pillar ascent the team holds the pillar's foot");
    NativeFacts ascentFacts;
    ascentFacts.PillarAscentSupported = true;
    AdaptiveNefarianPlan const top = strategy.Propose(sinking, Bot(1), "tank", &ascentFacts);
    CHECK(top.MovementSurface && top.MovementSurface->Target == Surface::PillarTop
        && top.MovementSurface->Urgent, "floor sinking: climb the pillar now");
    Vector3 const expected = LocalToWorld(PillarSlot(1, 1), PlatformFrame::PillarTopLocalZ, 2.0f);
    CHECK(top.Movement && Near(top.MovementSurface->World.Z, expected.Z)
        && Near(top.MovementSurface->World.X, expected.X), "pillar top follows the platform");
    auto const* walk = std::get_if<BotNativeAction::TransportSurfaceMove>(&top.Movement->Action);
    CHECK(walk && Near(walk->X, expected.X) && Near(walk->Z, expected.Z) && walk->EndOnTransport
        && walk->Transport == sinking.Interactables[0].Guid
        && walk->Kind == BotNativeAction::TransportSurfaceMove::Stage::Walk,
        "platform movement is a transport-surface walk");
    Vector3 const ring = LocalToWorld({ 34.0f, 0.0f }, RingLocalZ, PlatformFrame::RaisedOriginZ);
    CHECK(Near(FloorLocalZAt({ 34.0f, 0.0f }), RingLocalZ) && Near(ring.Z, 8.47378f, 0.01f),
        "outer ring floor height (world 8.47 raised)");

    Blackboard landing = PlatformBoard(PlatformFrame::RaisedOriginZ);
    landing.Summons.resize(1);
    AdaptiveNefarianPlan const down = strategy.Propose(landing, Bot(1), "tank");
    CHECK(down.Phase == Phase::NefarianLanding && down.MovementSurface
        && down.MovementSurface->Purpose == MovePurpose::PillarDescent
        && down.MovementSurface->Target == Surface::Floor, "floor raised: leave the pillar");

    Blackboard ground = landing;
    ground.Summons[0].Flying = false;
    ground.Summons[0].Auras.clear();
    ground.Summons[0].Position = LocalToWorld({ 0.0f, 0.0f }, PlatformFrame::FloorLocalZ,
        PlatformFrame::RaisedOriginZ);
    for (ActorSnapshot& player : ground.Players)
        player.Position = LocalToWorld({ 0.0f, 16.0f }, PlatformFrame::FloorLocalZ,
            PlatformFrame::RaisedOriginZ);
    ActorSnapshot fire = MakeCreature(ShadowblazeEntry, 50, { 1.5f, 16.0f });
    fire.Attackable = false;
    ground.Summons.push_back(fire);
    AdaptiveNefarianPlan const escape = strategy.Propose(ground, Bot(4), "dps");
    CHECK(escape.MovementSurface && escape.MovementSurface->Purpose == MovePurpose::FireEscape
        && Distance(escape.MovementSurface->Local, { 1.5f, 16.0f }) >= ShadowblazeRadius + 4.0f,
        "leave the Shadowblaze fire");
    CHECK(escape.DamageTarget == ground.Summons[0].Guid, "phase 3 damage on Nefarian");
}

int main()
{
    TestGeometry();
    TestDutyPlan();
    TestPhases();
    TestPhaseOneTarget();
    TestInterrupts();
    TestBoneWarriorControl();
    TestTankSpots();
    TestPlatformMovement();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_nefarian_strategy_decisions(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM)

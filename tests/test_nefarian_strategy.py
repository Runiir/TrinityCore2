"""Header-only checks for the Nefarian's End adaptive strategy.

The C++ program below includes the production headers from
src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian and
exercises phase detection, the capability duty plan for the canonical 10N
composition, platform geometry, the phase 1 Electrocute budget, Blast Nova
interrupts, bone warrior control, tank leading and the movement goals handed
to the transport-surface movement layer. PRELUDE (fixtures) is shared with
tests/test_nefarian_movement.py.
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


def _compile_and_run(tmp_path: Path, program: str) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-4000:]
    return result.stdout


PRELUDE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include <cstdio>
#include <string>

using namespace BotEncounter;
using namespace BotEncounter::Nefarian;

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

[[maybe_unused]] static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

[[maybe_unused]] static bool Near(float left, float right, float tolerance = 0.05f)
{
    return std::fabs(left - right) <= tolerance;
}

[[maybe_unused]] static ObjectGuid Bot(uint32 slot) { return ObjectGuid(HighGuid::Player, uint32(30500 + slot)); }

[[maybe_unused]] static ActorSnapshot MakePlayer(uint32 slot, char const* role, char const* spec,
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

[[maybe_unused]] static ActorSnapshot MakeCreature(uint32 entry, uint32 counter, LocalPoint at,
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

[[maybe_unused]] static ActorSnapshot MakeElevator(float originZ)
{
    ActorSnapshot elevator;
    elevator.Guid = ObjectGuid(HighGuid::GameObject, ElevatorEntry, uint32(235179));
    elevator.Entry = ElevatorEntry;
    elevator.Kind = ActorKind::Interactable;
    elevator.Position = { PlatformFrame::OriginX, PlatformFrame::OriginY, originZ };
    elevator.Alive = true;
    return elevator;
}

[[maybe_unused]] static void AddAura(ActorSnapshot& actor, uint32 spellId, uint8 stacks = 1)
{
    AuraSnapshot aura;
    aura.SpellId = spellId;
    aura.Stacks = stacks;
    actor.Auras.push_back(aura);
}

// Canonical composition (experiments/configs/raid_compositions/blackwing_descent_10n.json)
// with the Nefarian spec selection: Feral tank and Restoration shaman.
[[maybe_unused]] static Blackboard CanonicalBoard(float originZ = PlatformFrame::RaisedOriginZ)
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
        MakePlayer(3, "dps", "survival_hunter", { 2.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
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

[[maybe_unused]] static ActorSnapshot& FindPlayer(Blackboard& board, uint32 slot)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid == Bot(slot))
            return player;
    return board.Players.front();
}

[[maybe_unused]] static void AddDragons(Blackboard& board, bool landed)
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

[[maybe_unused]] static Blackboard PlatformBoard(float originZ)
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

'''


PROGRAM = PRELUDE + r'''
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
    // Collision model floor (nefarian_platform_floor_profile_v1.json): flat
    // centre -0.546, a 10-degree ramp from r 21.17 to r 32.43, ring +1.439.
    CHECK(Near(FloorLocalZAt({ 5.0f, 0.0f }), -0.546f, 0.001f), "flat centre floor");
    CHECK(Near(FloorLocalZAt({ 25.0f, 0.0f }), 0.11f, 0.05f), "the ramp at r 25");
    CHECK(Near(FloorLocalZAt({ 45.0f, 20.0f }), 1.439f, 0.001f), "the outer ring");
    CHECK(Near(PlatformFrame::RaisedOriginZ + FloorLocalZAt({ 25.0f, 0.0f }), 7.14f, 0.05f)
        && PlatformFrame::RaisedOriginZ + FloorLocalZAt({ 25.0f, 0.0f }) - 6.5714f > 0.5f,
        "the raised floor at the board point is 0.5+ yd above the old route anchor z 6.5714");

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

// Plans and the duty-plan status read one capability source, so the status
// "blocked" field always matches the bots' plans.
static std::string StatusBlocked(Blackboard const& board)
{
    std::string const json = BuildNefarianDutyPlanStatusJson(&board);
    std::string const key = "\"blocked\":\"";
    std::size_t const at = json.find(key);
    if (at == std::string::npos)
        return "<absent>";
    std::size_t const end = json.find('"', at + key.size());
    return json.substr(at + key.size(), end - at - key.size());
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
        "\"controllers\":[30505,30506,30504,30503,30509]}";
    CHECK(json == expected, json.c_str());
    CHECK(std::find(plan.Controllers.begin(), plan.Controllers.end(), Bot(10))
        == plan.Controllers.end(),
        "the Demonology warlock is no controller (Curse of Exhaustion is Affliction's)");

    ArenaLayout const layout = BuildArenaLayout(plan);
    CHECK(Near(layout.OnyxiaEndAngle, DegToRad(30.0f), 0.01f), "Onyxia's end beside pillar 0");
    CHECK(AngularGap(layout.NefarianEndAngle, PillarAngle(1)) < DegToRad(30.0f),
        "Nefarian's end beside his tank's pillar");
    CHECK(Near(AngularGap(layout.OnyxiaEndAngle, layout.NefarianEndAngle), Pi, 0.01f),
        "the dragons' ends are opposite (separation is proven by the chase model in "
        "test_nefarian_movement.py)");
    CHECK(Near(2.0f * DragonHoldMinRadius * std::cos(DegToRad(DragonGoalAngleToleranceDeg)),
        53.1f, 0.1f) && 53.1f > ChildrenOfDeathwingRange,
        "the hold gate keeps opposite dragons beyond 50 yards");

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

    // A loose Onyxia is taunted back only by a tank that knows its taunt.
    Blackboard loose = board;
    loose.Summons[0].VictimGuid = Bot(5);
    auto taunts = [](AdaptiveNefarianPlan const& plan)
    {
        return std::count_if(plan.Actions.begin(), plan.Actions.end(),
            [](BotNativeAction::Candidate const& action)
            {
                auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
                return cast && cast->SpellId == 6795 && action.Id.Mechanic == "onyxia_taunt";
            });
    };
    CHECK(taunts(strategy.Propose(loose, Bot(2), "tank")) == 1, "the Onyxia tank Growls");
    NativeFacts growl;
    growl.Readiness.push_back({ Bot(2), 6795, true, true });
    CHECK(taunts(strategy.Propose(loose, Bot(2), "tank", &growl)) == 1,
        "the same with the observer reporting Growl known and ready");
    NativeFacts noGrowl;
    noGrowl.Readiness.push_back({ Bot(2), 6795, true, false });
    CHECK(taunts(strategy.Propose(loose, Bot(2), "tank", &noGrowl)) == 0,
        "no taunt the tank does not know");
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

    NativeFacts noMindFreeze;
    noMindFreeze.Readiness.push_back({ Bot(1), 47528, true, false });
    CHECK(DecideBlastNovaInterrupt(board, view, plan, knight, &noMindFreeze).Target.IsEmpty(),
        "a primary that does not know its interrupt is skipped");
    CHECK(DecideBlastNovaInterrupt(board, view, plan, mage, &noMindFreeze).SpellId == 2139,
        "and the backup interrupts at once");

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

    // A controller whose spell is on cooldown hands the warrior on: Hammer of
    // Justice (60 s) to the next stun, then the root, then a cooldown-free snare.
    NativeFacts cooldowns;
    cooldowns.Readiness.push_back({ Bot(5), 853, false });
    CHECK(DecideBoneWarriorControl(board, view, plan, FindPlayer(board, 5), &cooldowns)
        .Target.IsEmpty(), "holy paladin's Hammer of Justice is on cooldown");
    ControlDecision const handed = DecideBoneWarriorControl(board, view, plan,
        FindPlayer(board, 6), &cooldowns);
    CHECK(handed.SpellId == 853 && handed.Target == first.Guid, "the ret takes warrior 1");
    cooldowns.Readiness.push_back({ Bot(6), 853, false });
    ControlDecision const rooted = DecideBoneWarriorControl(board, view, plan,
        FindPlayer(board, 4), &cooldowns);
    CHECK(rooted.SpellId == 122 && rooted.Target == first.Guid, "then the mage's Frost Nova");
    cooldowns.Readiness.push_back({ Bot(4), 122, false });
    ControlDecision const snared = DecideBoneWarriorControl(board, view, plan,
        FindPlayer(board, 3), &cooldowns);
    CHECK(snared.SpellId == 5116 && snared.Target == first.Guid,
        "then the hunter's Concussive Shot");
    CHECK(DecideBoneWarriorControl(board, view, plan, FindPlayer(board, 10), &cooldowns)
        .Target.IsEmpty(), "the Demonology warlock is never handed a control spell");

    // An Affliction warlock's Curse of Exhaustion is the cooldown-free snare,
    // taken before the snares with a cooldown - but only while the native
    // observer reports the spell known.
    Blackboard affliction = board;
    FindPlayer(affliction, 10).ClassSpec = "affliction_warlock";
    EncounterView const afflictionView = ObserveEncounter(affliction);
    DutyPlan const afflictionPlan = BuildNefarianDutyPlan(affliction);
    CHECK(afflictionPlan.Controllers.size() == 6 && afflictionPlan.Controllers[3] == Bot(10),
        "the Affliction warlock ranks after the root, before the snares with a cooldown");
    ControlDecision const cursed = DecideBoneWarriorControl(affliction, afflictionView,
        afflictionPlan, FindPlayer(affliction, 10), &cooldowns);
    CHECK(cursed.SpellId == 18223 && cursed.Target == first.Guid,
        "the Affliction warlock's Curse of Exhaustion");
    NativeFacts untaught = cooldowns;
    untaught.Readiness.push_back({ Bot(10), 18223, true, false });
    CHECK(DecideBoneWarriorControl(affliction, afflictionView, afflictionPlan,
        FindPlayer(affliction, 10), &untaught).Target.IsEmpty(),
        "a controller that does not know its spell is skipped");
    ControlDecision const passed = DecideBoneWarriorControl(affliction, afflictionView,
        afflictionPlan, FindPlayer(affliction, 3), &untaught);
    CHECK(passed.SpellId == 5116 && passed.Target == first.Guid,
        "and the warrior goes to the next controller that knows its spell");
    CHECK(ControlFor("demonology_warlock").SpellId == 0
        && ControlFor("destruction_warlock").SpellId == 0
        && ControlFor("affliction_warlock").SpellId == 18223,
        "Curse of Exhaustion only for Affliction");

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
    CHECK(lead.Step == TankStep::LeadOut && Near(Length(lead.Point), TankPullRadius, 0.01f)
        && AngularGap(AngleOf(lead.Point), goal) < DegToRad(1.0f),
        "pull the dragon out from the centre to the ring beyond its end");
    CHECK(RadialClear(AngleOf(lead.Point)), "the pull heading clears the pillars");

    TankSpot const shortEnd = PlanTankSpot(Polar(goal, 22.0f), goal, OnyxiaMeleeReach, false);
    CHECK(shortEnd.Step == TankStep::Pull, "a dragon at r 22 is pulled again, never held");
    TankSpot const offEnd = PlanTankSpot(Polar(goal + DegToRad(20.0f), 30.0f), goal,
        OnyxiaMeleeReach, false);
    CHECK(offEnd.Step == TankStep::Pull
        && NormalizeSigned(AngleOf(offEnd.Point) - goal) < 0.0f,
        "a dragon past its end is pulled back beyond it");

    LocalPoint const atEnd = Polar(goal, 30.0f);
    TankSpot const hold = PlanTankSpot(atEnd, goal, OnyxiaMeleeReach, false);
    CHECK(hold.Step == TankStep::Hold && Distance(hold.Point, atEnd) < OnyxiaMeleeReach - 3.0f,
        "hold inside reach so the dragon only turns");
    CHECK(OnFloorArea(hold.Point), "the hold spot is a ring standing spot");
    LocalPoint const toTank{ hold.Point.X - atEnd.X, hold.Point.Y - atEnd.Y };
    float const offRadial = AngularGap(AngleOf(toTank), goal);
    CHECK(offRadial > DegToRad(50.0f) && offRadial < DegToRad(80.0f),
        "held dragon faces along the wall, turned slightly outward");
    DragonPose const held{ atEnd, AngleOf(toTank) };
    CHECK(!InRearCone(held, { 0.0f, 0.0f }) && !InFrontCone(held, { 0.0f, 0.0f }),
        "the raid at the centre is on the held dragon's flank");

    TankSpot const turn = PlanTankSpot(atEnd, goal, OnyxiaMeleeReach, true);
    CHECK(turn.Step == TankStep::Discharge && Near(Length(turn.Point), 37.0f, 0.1f),
        "Lightning Discharge: step outward so her tail faces the raid");
    DragonPose const turned{ atEnd, goal };
    CHECK(!InDischargeFlank(turned, { 0.0f, 0.0f }), "the raid at the centre is then in her back cone");
}

static bool observedAscentDefault()
{
    NativeFacts const facts;
    return facts.PillarAscentSupported;
}

static TransportPlacement Placement(Blackboard const& board, uint32 slot, float localZ)
{
    ActorSnapshot const* bot = board.FindActor(Bot(slot));
    LocalPoint const local = WorldToLocal(bot->Position);
    TransportPlacement placement;
    placement.Actor = Bot(slot);
    placement.Transport = board.Interactables[0].Guid;
    placement.TransportEntry = ElevatorEntry;
    placement.Offset = { local.X, local.Y, localZ };
    return placement;
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
        && base.MovementSurface->Pillar == 1, "floor still up: head for the pillar's foot");
    CHECK(base.Blocked == "pillar_ascent_unsupported",
        "phase 2 without a pillar ascent is a typed capability blocker");
    CHECK(BuildNefarianDutyPlanStatusJson(&ascent).find(
        "\"blocked\":\"pillar_ascent_unsupported\"") != std::string::npos,
        "the duty-plan status publishes the blocker");
    Blackboard both = CanonicalBoard();
    AddDragons(both, true);
    CHECK(strategy.Propose(both, Bot(1), "tank").Blocked.empty()
        && BuildNefarianDutyPlanStatusJson(&both).find("\"blocked\":\"\"") != std::string::npos,
        "phase 1 has no blocker");

    auto const* baseWalk = base.Movement
        ? std::get_if<BotNativeAction::TransportSurfaceMove>(&base.Movement->Action) : nullptr;
    CHECK(baseWalk && baseWalk->EndOnTransport
        && baseWalk->Kind == BotNativeAction::TransportSurfaceMove::Stage::Walk
        && baseWalk->Transport == ascent.Interactables[0].Guid
        && Distance(WorldToLocal({ baseWalk->X, baseWalk->Y, baseWalk->Z }),
            WorldToLocal(FindPlayer(ascent, 1).Position)) <= MaxLegYards + 0.01f,
        "platform movement is one short transport-surface walk");

    Blackboard sinking = ascent;
    sinking.Interactables = { MakeElevator(2.0f) };
    AdaptiveNefarianPlan const foot = strategy.Propose(sinking, Bot(1), "tank");
    CHECK(foot.MovementSurface && foot.MovementSurface->Purpose == MovePurpose::PillarFoot
        && foot.MovementSurface->Target == Surface::Floor && foot.Blocked == "pillar_ascent_unsupported",
        "without a pillar ascent the team holds the pillar's foot");
    NativeFacts ascentFacts;
    ascentFacts.PillarAscentSupported = true;
    ascentFacts.Placements.push_back(Placement(sinking, 1, PlatformFrame::FloorLocalZ));
    AdaptiveNefarianPlan const top = strategy.Propose(sinking, Bot(1), "tank", &ascentFacts);
    CHECK(top.Blocked.empty() && top.MovementSurface
        && top.MovementSurface->Target == Surface::PillarTop && top.MovementSurface->Urgent,
        "with a declared ascent: climb the pillar now");
    Vector3 const expected = LocalToWorld(PillarSlot(1, 1), PlatformFrame::PillarTopLocalZ, 2.0f);
    CHECK(Near(top.MovementSurface->World.Z, expected.Z)
        && Near(top.MovementSurface->World.X, expected.X), "pillar top follows the platform");
    CHECK(top.MovementLeg && Distance(top.MovementLeg->To,
            WorldToLocal(FindPlayer(sinking, 1).Position)) <= MaxLegYards + 0.01f,
        "the ascent is approached in short legs");

    // Leaving a pillar top needs StepOff/Fall/Land: typed blocker, no walk.
    Blackboard landing = PlatformBoard(PlatformFrame::RaisedOriginZ);
    landing.Summons.resize(1);
    NativeFacts onTop;
    onTop.Placements.push_back(Placement(landing, 1, PlatformFrame::PillarTopLocalZ));
    AdaptiveNefarianPlan const down = strategy.Propose(landing, Bot(1), "tank", &onTop);
    CHECK(down.Phase == Phase::NefarianLanding && down.MovementSurface
        && down.MovementSurface->Purpose == MovePurpose::PillarDescent
        && down.Blocked == "pillar_descent_unsupported"
        && down.MovementHold == "pillar_descent_unsupported" && !down.Movement,
        "pillar descent is a typed blocker until StepOff/Fall/Land is wired");
    // Height alone never says "pillar top" (a bot in the magma over the
    // lowered platform would look the same).
    AdaptiveNefarianPlan const noFacts = strategy.Propose(landing, Bot(1), "tank");
    CHECK(noFacts.Blocked.empty() && noFacts.MovementHold == "nefarian_not_on_platform"
        && !noFacts.Movement, "without a placement the bot is not treated as on a pillar");

    Blackboard unobserved = both;
    unobserved.Interactables.clear();
    AdaptiveNefarianPlan const hold = strategy.Propose(unobserved, Bot(4), "dps");
    CHECK(!hold.Movement && hold.MovementHold == "nefarian_elevator_unobserved",
        "an unobserved elevator never falls back to an ordinary move");

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
    CHECK(escape.Movement && escape.Movement->ActionPriority
        == BotActionArbitration::Priority::Survival, "the escape outranks casts");
    CHECK(escape.DamageTarget == ground.Summons[0].Guid, "phase 3 damage on Nefarian");

    // The same leg already in flight is not relaunched every decision.
    NativeFacts inFlight;
    Vector3 const legEnd = LocalToWorld(escape.MovementLeg->To, escape.MovementLeg->LocalZ,
        PlatformFrame::RaisedOriginZ);
    inFlight.Motion.push_back({ Bot(4), true, legEnd });
    inFlight.Placements.push_back(Placement(ground, 4, PlatformFrame::FloorLocalZ));
    AdaptiveNefarianPlan const flying = strategy.Propose(ground, Bot(4), "dps", &inFlight);
    CHECK(!flying.Movement && flying.MovementHold == "nefarian_leg_in_flight",
        "a running walk to the same leg end is left alone");

    // A long walk: the planned leg end slides forward as the bot advances,
    // so the walk still running toward the first leg end is kept.
    Blackboard far = ground;
    far.Summons.pop_back();
    LocalPoint const farStart{ -45.0f, 0.0f };
    FindPlayer(far, 4).Position = LocalToWorld(farStart, FloorLocalZAt(farStart),
        PlatformFrame::RaisedOriginZ);
    AdaptiveNefarianPlan const longWalk = strategy.Propose(far, Bot(4), "dps");
    CHECK(longWalk.Movement && longWalk.MovementLeg
        && Distance(longWalk.MovementLeg->To, farStart) > MaxLegYards - 0.1f
        && Distance(longWalk.MovementSurface->Local, farStart) > MaxLegYards + 2.0f,
        "a long walk starts with a full leg toward a farther goal");
    LocalPoint const firstEnd = longWalk.MovementLeg->To;
    LocalPoint const midway{ (farStart.X + firstEnd.X) / 2.0f,
        (farStart.Y + firstEnd.Y) / 2.0f };
    FindPlayer(far, 4).Position = LocalToWorld(midway, FloorLocalZAt(midway),
        PlatformFrame::RaisedOriginZ);
    AdaptiveNefarianPlan const fromMidway = strategy.Propose(far, Bot(4), "dps");
    CHECK(fromMidway.MovementLeg
        && Distance(fromMidway.MovementLeg->To, farStart) > Distance(firstEnd, farStart) + 0.5f,
        "the leg planned from midway ends past the first leg end");
    NativeFacts sliding;
    sliding.Motion.push_back({ Bot(4), true, LocalToWorld(firstEnd,
        longWalk.MovementLeg->LocalZ, PlatformFrame::RaisedOriginZ) });
    sliding.Placements.push_back(Placement(far, 4, FloorLocalZAt(midway)));
    AdaptiveNefarianPlan const along = strategy.Propose(far, Bot(4), "dps", &sliding);
    CHECK(!along.Movement && along.MovementHold == "nefarian_leg_in_flight",
        "the running walk toward the same goal is kept while the leg end slides");
    // A running walk in another direction (an old goal) is replaced.
    NativeFacts stale;
    LocalPoint const elsewhere = Offset(midway, AngleOf({ firstEnd.X - midway.X,
        firstEnd.Y - midway.Y }) + DegToRad(60.0f), 4.0f);
    stale.Motion.push_back({ Bot(4), true, LocalToWorld(elsewhere,
        FloorLocalZAt(elsewhere), PlatformFrame::RaisedOriginZ) });
    stale.Placements = sliding.Placements;
    AdaptiveNefarianPlan const turned = strategy.Propose(far, Bot(4), "dps", &stale);
    CHECK(turned.Movement && turned.MovementHold.empty(),
        "a running walk toward another point is relaunched");

    // Status and plans agree in every phase (default facts, as the observer
    // builds them, and no facts at all).
    for (Blackboard const* sample : { &both, &ascent, &sinking, &landing, &ground })
    {
        NativeFacts const observed;
        std::string const status = StatusBlocked(*sample);
        for (uint32 slot = 1; slot <= 10; ++slot)
        {
            ActorSnapshot const* bot = sample->FindActor(Bot(slot));
            AdaptiveNefarianPlan const withFacts = strategy.Propose(*sample, Bot(slot),
                bot->Role, &observed);
            AdaptiveNefarianPlan const without = strategy.Propose(*sample, Bot(slot), bot->Role);
            if (withFacts.Blocked != "pillar_descent_unsupported")
                CHECK(std::string(withFacts.Blocked) == status, "status and plan agree (facts)");
            CHECK(std::string(without.Blocked) == status, "status and plan agree (no facts)");
        }
    }
    CHECK(observedAscentDefault() == RuntimePillarAscentSupported(),
        "the observer's facts default to the runtime capability");

    Blackboard stunned = ground;
    AddAura(FindPlayer(stunned, 4), 77827);
    CHECK(strategy.Propose(stunned, Bot(4), "dps").MovementHold == "nefarian_movement_stunned",
        "no walk while stunned by Tail Lash");
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

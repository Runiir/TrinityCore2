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

import os
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


SANITIZERS = ["-fsanitize=address,undefined", "-fsanitize-address-use-after-scope",
              "-fno-omit-frame-pointer", "-fno-sanitize-recover=all", "-g", "-O1"]


def _compile_and_run(tmp_path: Path, program: str, sanitize: bool = False) -> str:
    source = tmp_path / "program.cpp"
    binary = tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    if sanitize:
        command += SANITIZERS
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    env = dict(os.environ, ASAN_OPTIONS="detect_leaks=0:detect_stack_use_after_return=1",
               UBSAN_OPTIONS="print_stacktrace=1")
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True, env=env)
    assert result.returncode == 0, result.stderr[-4000:]
    return result.stdout


PRELUDE = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotAdaptiveNefarianStrategy.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianPickupMemory.h"
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
// with the Nefarian spec selection the user's comp needs (user raid
// experience 2026-09-26: 2 tanks, 2 healers, 6 DPS): Feral tank and
// Elemental shaman.
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
        MakePlayer(9, "dps", "elemental_shaman", { 8.0f, 0.0f }, PlatformFrame::FloorLocalZ, originZ),
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
    // Pillar 2 team on its pillar top: death knight, elemental shaman, hunter.
    uint8 slot = 0;
    for (uint32 member : { 1u, 9u, 3u })
        FindPlayer(board, member).Position = LocalToWorld(PillarSlot(2, slot++),
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
        "{\"members\":[30505,30508,30504],\"healer\":30505,\"interrupt\":30508,\"backup\":30505,\"off_healer\":0},"
        "{\"members\":[30507,30506,30502,30510],\"healer\":30507,\"interrupt\":30506,\"backup\":30502,\"off_healer\":0},"
        "{\"members\":[30501,30509,30503],\"healer\":0,\"interrupt\":30501,\"backup\":30509,\"off_healer\":30509}],"
        "\"warrior_handler\":30502}";
    CHECK(json == expected, json.c_str());
    CHECK(plan.PillarOf(plan.NefarianTank) == 2 && plan.Pillars[2].Healer.IsEmpty(),
        "two healers: the Blood death knight takes the pillar without a healer");
    CHECK(plan.WarriorHandler == Bot(2), "the Feral Onyxia tank handles the bone warriors");
    CHECK(plan.Pillars[2].OffHealer == Bot(9), "the Elemental shaman off-heals the healerless pillar");

    // Stable teams: the Blood DK dies, the Feral takes the Nefarian tank duty,
    // and nobody changes pillar.
    Blackboard tankDead = CanonicalBoard();
    FindPlayer(tankDead, 1).Alive = false;
    DutyPlan const promoted = BuildNefarianDutyPlan(tankDead);
    CHECK(promoted.NefarianTank == Bot(2) && promoted.OnyxiaTank.IsEmpty(),
        "the Feral is promoted to the Nefarian tank");
    for (std::size_t pillar = 0; pillar < 3; ++pillar)
        CHECK(promoted.Pillars[pillar].Members == plan.Pillars[pillar].Members,
            "a tank's death never reshuffles the pillar teams");
    CHECK(promoted.Pillars[2].PrimaryInterrupter == Bot(9)
        && promoted.Pillars[2].OffHealer == Bot(9),
        "the shaman interrupts and off-heals pillar 2 when the death knight is dead");
    for (uint32 dead : { 5u, 7u, 9u, 2u })
    {
        Blackboard withDeath = CanonicalBoard();
        FindPlayer(withDeath, dead).Alive = false;
        DutyPlan const after = BuildNefarianDutyPlan(withDeath);
        for (std::size_t pillar = 0; pillar < 3; ++pillar)
            CHECK(after.Pillars[pillar].Members == plan.Pillars[pillar].Members,
                "no death reshuffles the pillar teams");
    }

    ArenaLayout const layout = BuildArenaLayout(plan);
    CHECK(AngularGap(layout.OnyxiaEndAngle, PillarAngle(plan.PillarOf(plan.OnyxiaTank)))
        < DegToRad(32.0f), "Onyxia's end beside her tank's pillar");
    CHECK(AngularGap(layout.NefarianEndAngle, PillarAngle(plan.PillarOf(plan.NefarianTank)))
        < DegToRad(32.0f), "Nefarian's end beside his tank's pillar");
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
    CHECK(reduced.Pillars[0].BackupInterrupter == Bot(4), "the mage backs up pillar 0");

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
    // User raid experience 2026-09-26: Bloodlust and burn Onyxia from the
    // pull; no Electrocute pacing in 10N.
    onyxia.HealthPct = 10.0f;
    onyxia.AlternatePower = 20;
    nefarian.HealthPct = 95.0f;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board)) == onyxia.Guid,
        "the raid burns Onyxia even when she is low and Nefarian is open");
    CHECK(PhaseOnePacingFor(nullptr) == PhaseOnePacing::OnyxiaBurn,
        "normal difficulty burns Onyxia");
    // Heroic keeps the Electrocute budget as a fallback.
    PhaseOnePacing const budget = PhaseOnePacing::ElectrocuteBudget;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board), budget) == nefarian.Guid,
        "heroic: Onyxia low, spend two Electrocutes on Nefarian");
    onyxia.AlternatePower = 65;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board), budget) == onyxia.Guid,
        "heroic: charge near overload, finish Onyxia");
    onyxia.AlternatePower = 20;
    nefarian.HealthPct = 72.0f;
    CHECK(PhaseOneDamageTarget(ObserveEncounter(board), budget) == onyxia.Guid,
        "heroic: Nefarian at the budget floor, finish Onyxia");
    nefarian.HealthPct = 95.0f;
    NativeFacts heroic;
    heroic.Heroic = true;
    CHECK(PhaseOnePacingFor(&heroic) == PhaseOnePacing::ElectrocuteBudget, "heroic pacing");
    {
        AdaptiveNefarianStrategy burn;
        CHECK(burn.Propose(board, Bot(4), "dps").DamageTarget == onyxia.Guid,
            "a DPS burns Onyxia on normal");
        CHECK(burn.Propose(board, Bot(4), "dps", &heroic).DamageTarget == nefarian.Guid,
            "a DPS follows the Electrocute budget on heroic");
    }
    onyxia.HealthPct = 50.0f;

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
    board.Summons[3].Cast = nova; // pillar 2 prototype
    EncounterView const view = ObserveEncounter(board);
    DutyPlan const plan = BuildNefarianDutyPlan(board);
    ActorSnapshot const& knight = FindPlayer(board, 1);
    ActorSnapshot const& shaman = FindPlayer(board, 9);

    InterruptDecision const primary = DecideBlastNovaInterrupt(board, view, plan, knight, nullptr);
    CHECK(primary.Target == board.Summons[3].Guid && primary.SpellId == 47528,
        "death knight Mind Freezes his pillar's Blast Nova");
    CHECK(DecideBlastNovaInterrupt(board, view, plan, shaman, nullptr).Target.IsEmpty(),
        "backup waits while the primary can interrupt");

    NativeFacts late;
    late.Casts.push_back({ board.Summons[3].Guid, 80734, 4000, 2000 });
    InterruptDecision const backup = DecideBlastNovaInterrupt(board, view, plan, shaman, &late);
    CHECK(backup.SpellId == 57994 && backup.Reason == "blast_nova_backup_primary_late",
        "the Elemental shaman Wind Shears after 2 s of the 4 s cast");

    Blackboard dead = board;
    FindPlayer(dead, 1).Alive = false;
    EncounterView const deadView = ObserveEncounter(dead);
    DutyPlan const deadPlan = BuildNefarianDutyPlan(dead);
    InterruptDecision const replacement = DecideBlastNovaInterrupt(dead, deadView, deadPlan,
        FindPlayer(dead, 9), nullptr);
    CHECK(replacement.SpellId == 57994, "the shaman interrupts when the death knight is dead");

    NativeFacts noMindFreeze;
    noMindFreeze.Readiness.push_back({ Bot(1), 47528, true, false });
    CHECK(DecideBlastNovaInterrupt(board, view, plan, knight, &noMindFreeze).Target.IsEmpty(),
        "a primary that does not know its interrupt is skipped");
    CHECK(DecideBlastNovaInterrupt(board, view, plan, shaman, &noMindFreeze).SpellId == 57994,
        "and the backup interrupts at once");

    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const plan1 = strategy.Propose(board, Bot(1), "tank");
    CHECK(plan1.InterruptTarget == board.Summons[3].Guid && plan1.Actions.size() == 1
        && plan1.Actions[0].ActionPriority == BotActionArbitration::Priority::Interrupt,
        "legacy interrupt target and exact Mind Freeze candidate");
    CHECK(plan1.DamageTarget == board.Summons[3].Guid, "platform team damages its prototype");

    Blackboard quiet = board;
    quiet.Summons[3].Cast->Interruptible = false;
    CHECK(strategy.Propose(quiet, Bot(1), "tank").InterruptTarget.IsEmpty(),
        "no interrupt on an uninterruptible cast");

    Blackboard cleared = board;
    cleared.Summons.erase(cleared.Summons.begin() + 3);
    AdaptiveNefarianPlan const helper = strategy.Propose(cleared, Bot(9), "dps");
    CHECK(!helper.DamageTarget.IsEmpty() && helper.DamageTarget != cleared.Summons[0].Guid,
        "a cleared pillar helps with another prototype, never Nefarian");
    Blackboard allDead = cleared;
    allDead.Summons.resize(1);
    allDead.Interactables = { MakeElevator(PlatformFrame::LoweredOriginZ) };
    AdaptiveNefarianPlan const idle = strategy.Propose(allDead, Bot(9), "dps");
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

    ControlDecision const shackle = DecideShackle(board, view, plan, FindPlayer(board, 7));
    CHECK(shackle.SpellId == SpellShackleUndead && shackle.Target == second.Guid,
        "shackle the most empowered warrior");
    CHECK(DecideShackle(board, view, plan, FindPlayer(board, 5)).Target.IsEmpty(),
        "only the shackler controls (no stun/snare rotation)");

    Blackboard onHandler = board;
    onHandler.Summons[3].VictimGuid = Bot(2);
    EncounterView const onHandlerView = ObserveEncounter(onHandler);
    CHECK(DecideShackle(onHandler, onHandlerView, plan, FindPlayer(onHandler, 7)).Target
        == first.Guid, "a warrior on the handler is left to the handler");

    Blackboard held = board;
    AddAura(held.Summons[3], SpellShackleUndead);
    EncounterView const heldView = ObserveEncounter(held);
    CHECK(DecideShackle(held, heldView, plan, FindPlayer(held, 7)).Target.IsEmpty(),
        "one shackle at a time");
    Blackboard rooted = board;
    AddAura(rooted.Summons[3], SpellNaturesGraspRoot);
    EncounterView const rootedView = ObserveEncounter(rooted);
    CHECK(DecideShackle(rooted, rootedView, plan, FindPlayer(rooted, 7)).Target == first.Guid,
        "a warrior rooted by Nature's Grasp is not shackled");

    Blackboard collapsed = board;
    AddAura(collapsed.Summons[3], SpellBoneFeignDeath);
    collapsed.Summons[3].Selectable = false;
    EncounterView const collapsedView = ObserveEncounter(collapsed);
    CHECK(DecideShackle(collapsed, collapsedView, plan, FindPlayer(collapsed, 7)).Target
        == first.Guid, "collapsed warriors are ignored");
    NativeFacts noShackle;
    noShackle.Readiness.push_back({ Bot(7), SpellShackleUndead, true, false });
    CHECK(DecideShackle(board, view, plan, FindPlayer(board, 7), &noShackle).Target.IsEmpty(),
        "no shackle the priest does not know");

    CHECK(WarriorRootFor("feral_druid_tank") == SpellNaturesGrasp
        && WarriorRootFor("balance_druid") == SpellNaturesGrasp
        && WarriorRootFor("blood_death_knight") == 0, "Nature's Grasp is the druids'");
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
    CHECK(WarriorPointSafe(view, hunter.MovementSurface->Local),
        "the kite never leads the warrior in front of Nefarian");
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
        && base.MovementSurface->Pillar == 2, "floor still up: head for the pillar's foot");
    // The runtime answer (RuntimePillarAscentSupported) decides: without the
    // swimmer's stages phase 2 is a typed capability blocker, published in the
    // status too; with them there is none.
    std::string const expectedBlocker = RuntimePillarAscentSupported()
        ? "" : "pillar_ascent_unsupported";
    CHECK(base.Blocked == expectedBlocker, "phase 2 blocker follows the runtime capability");
    CHECK(BuildNefarianDutyPlanStatusJson(&ascent).find(
        "\"blocked\":\"" + expectedBlocker + "\"") != std::string::npos,
        "the duty-plan status publishes the same");
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
    NativeFacts noAscent;
    noAscent.PillarAscentSupported = false;
    noAscent.Placements.push_back(Placement(sinking, 1, PlatformFrame::FloorLocalZ));
    AdaptiveNefarianPlan const heldFoot = strategy.Propose(sinking, Bot(1), "tank", &noAscent);
    CHECK(heldFoot.MovementSurface && heldFoot.MovementSurface->Purpose == MovePurpose::PillarFoot
        && heldFoot.MovementSurface->Target == Surface::Floor
        && heldFoot.Blocked == "pillar_ascent_unsupported",
        "without a pillar ascent the team holds the pillar's foot");
    CHECK(foot.MovementSurface && foot.MovementSurface->Target == Surface::Floor
        && foot.Blocked == expectedBlocker, "no facts: the runtime capability decides");
    // Height alone never says "on a pillar" (a bot in the magma over the
    // lowered platform would look the same).
    Blackboard landing = PlatformBoard(PlatformFrame::RaisedOriginZ);
    landing.Summons.resize(1);
    AdaptiveNefarianPlan const noFacts = strategy.Propose(landing, Bot(1), "tank");
    CHECK(noFacts.Blocked.empty() && noFacts.MovementHold == "nefarian_not_on_platform"
        && !noFacts.Movement, "without a placement the bot is not treated as on a pillar");

    Blackboard unobserved = both;
    unobserved.Interactables.clear();
    AdaptiveNefarianPlan const hold = strategy.Propose(unobserved, Bot(4), "dps");
    CHECK(!hold.Movement && HoldReason(hold.MovementHold) == "nefarian_elevator_unobserved",
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
    CHECK(turned.Movement && (turned.MovementHold.empty() || IsPlatformHold(turned.MovementHold)),
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
            CHECK(std::string(withFacts.Blocked) == status, "status and plan agree (facts)");
            CHECK(std::string(without.Blocked) == status, "status and plan agree (no facts)");
        }
    }
    CHECK(observedAscentDefault() == RuntimePillarAscentSupported(),
        "the observer's facts default to the runtime capability");

    Blackboard stunned = ground;
    AddAura(FindPlayer(stunned, 4), 77827);
    CHECK(HoldReason(strategy.Propose(stunned, Bot(4), "dps").MovementHold) == "nefarian_movement_stunned",
        "no walk while stunned by Tail Lash");
}

// Placement of a bot as a passenger at a local point and height.
static TransportPlacement PlacementAt(Blackboard const& board, uint32 slot, LocalPoint at,
    float localZ)
{
    TransportPlacement placement;
    placement.Actor = Bot(slot);
    placement.Transport = board.Interactables[0].Guid;
    placement.TransportEntry = ElevatorEntry;
    placement.Offset = { at.X, at.Y, localZ };
    return placement;
}

static Blackboard AscentBoard(float originZ)
{
    Blackboard board = PlatformBoard(originZ);
    for (ActorSnapshot& player : board.Players)
        player.Position = LocalToWorld({ 0.0f, 0.0f }, FloorLocalZAt({ 0.0f, 0.0f }), originZ);
    return board;
}

// The phase 2 swim-and-hop ascent (user raid experience 2026-09-26), step by
// step, for the Blood death knight (pillar 2, slot 0).
static void TestAscent()
{
    AdaptiveNefarianStrategy strategy;
    DutyPlan const duty = BuildNefarianDutyPlan(CanonicalBoard());
    uint8 const pillar = uint8(duty.PillarOf(Bot(1)));
    uint8 const slot = duty.SlotOf(Bot(1));
    CHECK(pillar == 2 && slot == 0, "the death knight's pillar and slot");
    auto facts = [](Blackboard const& board, std::optional<TransportPlacement> placement)
    {
        NativeFacts result;
        result.PillarAscentSupported = true;
        if (placement)
            result.Placements.push_back(*placement);
        (void)board;
        return result;
    };
    auto place = [](Blackboard& board, LocalPoint at, float worldZ)
    {
        Vector3 world = LocalToWorld(at, 0.0f, 0.0f);
        world.Z = worldZ;
        FindPlayer(board, 1).Position = world;
    };

    // 1. Floor still up: walk to the foot on the slot heading.
    Blackboard raised = AscentBoard(PlatformFrame::RaisedOriginZ);
    raised.Summons[0].Flying = true;
    NativeFacts const onFloor = facts(raised, PlacementAt(raised, 1, { 0.0f, 0.0f },
        FloorLocalZAt({ 0.0f, 0.0f })));
    AdaptiveNefarianPlan const walk = strategy.Propose(raised, Bot(1), "tank", &onFloor);
    CHECK(walk.Blocked.empty() && walk.MovementSurface
        && walk.MovementSurface->Purpose == MovePurpose::PillarAscent
        && Distance(walk.MovementSurface->Local, PillarBase(pillar, slot)) < 0.01f
        && walk.Movement && !walk.Ascent, "floor up: walk to the pillar's foot");

    // 2. Sinking, feet not yet at the float depth: wait.
    LocalPoint const foot = PillarBase(pillar, slot);
    float const floorLocal = FloorLocalZAt(foot);
    float const shallowOrigin = MagmaSurfaceZ - 0.5f - floorLocal;
    Blackboard wading = AscentBoard(shallowOrigin);
    place(wading, foot, shallowOrigin + floorLocal);
    NativeFacts const wadeFacts = facts(wading, PlacementAt(wading, 1, foot, floorLocal));
    AdaptiveNefarianPlan const wade = strategy.Propose(wading, Bot(1), "tank", &wadeFacts);
    CHECK(!wade.Ascent && !wade.Movement && wade.MovementHold == "nefarian_wading_until_float_depth",
        "in shallow magma: keep standing until it is deep enough to swim");

    // 3. Deep enough: float (stop standing on the platform).
    float const deepOrigin = MagmaSurfaceZ - FloatDepthYards - 0.05f - floorLocal;
    Blackboard deep = AscentBoard(deepOrigin);
    place(deep, foot, deepOrigin + floorLocal);
    NativeFacts const deepFacts = facts(deep, PlacementAt(deep, 1, foot, floorLocal));
    AdaptiveNefarianPlan const floating = strategy.Propose(deep, Bot(1), "tank", &deepFacts);
    CHECK(floating.Ascent && floating.Ascent->Stage == AscentStage::Float
        && floating.Ascent->Transport == deep.Interactables[0].Guid && !floating.Movement,
        "feet 1.2 yd under the surface: float");

    // 4. Swimming: swim to the station beside the wall at the float depth.
    NativeFacts const swimmer = facts(deep, std::nullopt);
    AdaptiveNefarianPlan const swim = strategy.Propose(deep, Bot(1), "tank", &swimmer);
    LocalPoint const station = PillarRadial(pillar, slot, SwimStationRadius);
    CHECK(swim.Ascent && swim.Ascent->Stage == AscentStage::Swim
        && Distance(WorldToLocal(swim.Ascent->World), station) < 0.01f
        && Near(swim.Ascent->World.Z, MagmaSurfaceZ - FloatDepthYards, 0.001f),
        "swim to the station at the float depth");
    CHECK(Distance(foot, station) <= MaxSwimLegYards, "the foot is one swim leg from the station");

    // 5. At the station while the platform still sinks: hold.
    Blackboard holding = AscentBoard(0.0f);
    place(holding, station, MagmaSurfaceZ - FloatDepthYards);
    AdaptiveNefarianPlan const hold = strategy.Propose(holding, Bot(1), "tank", &swimmer);
    CHECK(!hold.Ascent && hold.MovementHold == "nefarian_float_hold_for_pillar",
        "float at the station until the platform stops");

    // 6. Lowered stop: hop onto the rim just above the waterline.
    Blackboard lowered = AscentBoard(PlatformFrame::LoweredOriginZ);
    place(lowered, station, MagmaSurfaceZ - FloatDepthYards);
    AdaptiveNefarianPlan const hop = strategy.Propose(lowered, Bot(1), "tank", &swimmer);
    Vector3 const landing = LocalToWorld(PillarRadial(pillar, slot, HopLandingRadius(pillar, slot)),
        HopLandingLocalZ, PlatformFrame::LoweredOriginZ);
    CHECK(hop.Ascent && hop.Ascent->Stage == AscentStage::Hop
        && Near(hop.Ascent->World.X, landing.X, 0.01f) && Near(hop.Ascent->World.Y, landing.Y, 0.01f)
        && Near(hop.Ascent->World.Z, landing.Z, 0.01f)
        && hop.Ascent->HopSpeedXY > 0.0f && hop.Ascent->HopSpeedXY <= RunSpeedYardsPerSecond,
        "hop from the station onto the rim");
    CHECK(landing.Z > MagmaSurfaceZ && landing.Z - MagmaSurfaceZ < 0.1f,
        "the landing is just above the waterline");

    // 6b. Mid-hop: the jump spline runs toward the landing. The request is
    // kept (the executor answers it with progress, holding the movement, GCD
    // and cast lanes), even for a healer with an injured teammate in reach.
    Blackboard midHop = AscentBoard(PlatformFrame::LoweredOriginZ);
    Vector3 airborne = LocalToWorld(PillarRadial(pillar, slot, 5.5f), 0.0f, 0.0f);
    airborne.Z = MagmaSurfaceZ + 0.6f;
    FindPlayer(midHop, 1).Position = airborne;
    NativeFacts inFlightHop = swimmer;
    inFlightHop.Motion.push_back({ Bot(1), true, landing });
    AdaptiveNefarianPlan const flying = strategy.Propose(midHop, Bot(1), "tank", &inFlightHop);
    CHECK(flying.Ascent && flying.Ascent->Stage == AscentStage::Hop
        && Near(flying.Ascent->World.X, landing.X, 0.01f), "the hop in flight keeps its request");
    uint8 const priestPillar = uint8(duty.PillarOf(Bot(7)));
    uint8 const priestSlot = duty.SlotOf(Bot(7));
    Vector3 const priestLanding = LocalToWorld(PillarRadial(priestPillar, priestSlot,
        HopLandingRadius(priestPillar, priestSlot)), HopLandingLocalZ, PlatformFrame::LoweredOriginZ);
    Vector3 priestAir = LocalToWorld(PillarRadial(priestPillar, priestSlot, 5.5f), 0.0f, 0.0f);
    priestAir.Z = MagmaSurfaceZ + 0.6f;
    FindPlayer(midHop, 7).Position = priestAir;
    for (ObjectGuid member : duty.Pillars[priestPillar].Members)
        if (member.GetCounter() != Bot(7).GetCounter())
            FindPlayer(midHop, member.GetCounter() - 30500).HealthPct = 35.0f;
    NativeFacts priestFacts;
    priestFacts.PillarAscentSupported = true;
    priestFacts.Motion.push_back({ Bot(7), true, priestLanding });
    AdaptiveNefarianPlan const healer = strategy.Propose(midHop, Bot(7), "healer", &priestFacts);
    CHECK(healer.Ascent && healer.Ascent->Stage == AscentStage::Hop,
        "a healer mid-hop keeps the hop (Survival) above any heal");

    // 7. Landed on the rim, not yet a passenger: board.
    Blackboard landed = AscentBoard(PlatformFrame::LoweredOriginZ);
    FindPlayer(landed, 1).Position = landing;
    AdaptiveNefarianPlan const board = strategy.Propose(landed, Bot(1), "tank", &swimmer);
    CHECK(board.Ascent && board.Ascent->Stage == AscentStage::Board, "board on the rim");

    // 8. A passenger on the rim walks up to its slot on the flat top.
    LocalPoint const rim = PillarRadial(pillar, slot, HopLandingRadius(pillar, slot));
    NativeFacts const aboard = facts(landed, PlacementAt(landed, 1, rim, HopLandingLocalZ));
    AdaptiveNefarianPlan const up = strategy.Propose(landed, Bot(1), "tank", &aboard);
    auto const* upWalk = up.Movement
        ? std::get_if<BotNativeAction::TransportSurfaceMove>(&up.Movement->Action) : nullptr;
    Vector3 const slotWorld = LocalToWorld(PillarSlot(pillar, slot),
        PlatformFrame::PillarTopLocalZ, PlatformFrame::LoweredOriginZ);
    CHECK(upWalk && upWalk->Kind == BotNativeAction::TransportSurfaceMove::Stage::Walk
        && Near(upWalk->X, slotWorld.X, 0.01f) && Near(upWalk->Z, slotWorld.Z, 0.01f)
        && !up.Ascent, "walk up the rim to the slot");
    NativeFacts const atSlot = facts(landed, PlacementAt(landed, 1, PillarSlot(pillar, slot),
        PlatformFrame::PillarTopLocalZ));
    Blackboard onSlot = landed;
    FindPlayer(onSlot, 1).Position = slotWorld;
    AdaptiveNefarianPlan const stay = strategy.Propose(onSlot, Bot(1), "tank", &atSlot);
    CHECK(!stay.Movement && !stay.Ascent && stay.DamageTarget == onSlot.Summons[3].Guid,
        "on the slot: stay and damage the pillar's prototype");

    // A late swimmer that the rising floor reaches boards it.
    Blackboard rising = AscentBoard(MagmaSurfaceZ - FloatDepthYards - RingLocalZ - 0.2f);
    rising.Summons.resize(1);
    place(rising, station, MagmaSurfaceZ - FloatDepthYards);
    AdaptiveNefarianPlan const lifted = strategy.Propose(rising, Bot(1), "tank", &swimmer);
    CHECK(lifted.Phase == Phase::PlatformReturn && lifted.Ascent
        && lifted.Ascent->Stage == AscentStage::Board,
        "the rising floor reaches a swimmer: board it");

    // A late swimmer far from its station: every swim leg, depth correction
    // included, stays inside the executor's 12-yard limit.
    Blackboard late = AscentBoard(0.0f);
    LocalPoint const far = Offset(station, AngleOf(station), 20.0f);
    place(late, far, MagmaSurfaceZ - 2.9f);
    AdaptiveNefarianPlan const lateSwim = strategy.Propose(late, Bot(1), "tank", &swimmer);
    Vector3 const lateFrom = FindPlayer(late, 1).Position;
    CHECK(lateSwim.Ascent && lateSwim.Ascent->Stage == AscentStage::Swim, "a late swimmer swims");
    if (lateSwim.Ascent)
    {
        Vector3 const to = lateSwim.Ascent->World;
        float const length = std::sqrt((to.X - lateFrom.X) * (to.X - lateFrom.X)
            + (to.Y - lateFrom.Y) * (to.Y - lateFrom.Y) + (to.Z - lateFrom.Z) * (to.Z - lateFrom.Z));
        CHECK(length <= MaxSwimLegYards - SwimLegMarginYards + 1e-3f,
            "the 3D swim leg is within the executor's limit");
        CHECK(Distance(WorldToLocal(to), station) < Distance(far, station),
            "and heads for the station");
    }
}

// The rising floor (phase 3 raise) reaches a swimmer that missed its pillar.
// Replayed at decision gaps that skip a plain 0.74-second contact window:
// the swimmer meets the floor and rides up just slower than it, so a later
// decision still finds the floor within the boarding band.
static int ReplayRisingFloor(float decisionGapSeconds, bool& missed,
    float startFeet = MagmaSurfaceZ - FloatDepthYards, float startFloorBelow = -1.0f,
    std::optional<LocalPoint> startAt = std::nullopt)
{
    AdaptiveNefarianStrategy strategy;
    DutyPlan const duty = BuildNefarianDutyPlan(CanonicalBoard());
    uint8 const pillar = uint8(duty.PillarOf(Bot(1)));
    LocalPoint const station = startAt ? *startAt
        : PillarRadial(pillar, duty.SlotOf(Bot(1)), SwimStationRadius);
    NativeFacts swimmer;
    swimmer.PillarAscentSupported = true;
    // The swimmer's world position, moved along each submitted swim at its
    // speed until the next decision (the spline runs in between).
    Vector3 at = LocalToWorld(station, 0.0f, 0.0f);
    at.Z = startFeet;
    Vector3 target = at;
    float speed = 0.0f;
    // The raise starts at the lowered stop, or where the floor under the
    // station is `startFloorBelow` under the feet.
    float startMs = 0.0f;
    if (startFloorBelow >= 0.0f)
        startMs = StopChangeMs - LoweringReachesMs(FloorLocalZAt(station),
            startFeet - startFloorBelow);
    missed = false;
    for (int step = 0; step < 200; ++step)
    {
        float const t = startMs + float(step) * decisionGapSeconds * 1000.0f;
        // Raise: the reverse of the lowering, origin(t) = lowering(13.333 - t).
        float const origin = LoweringOriginZ(std::max(0.0f, StopChangeMs - t));
        if (origin >= PlatformFrame::RaisedOriginZ - 0.01f)
            break;
        Blackboard board = AscentBoard(origin);
        board.Summons.resize(1);
        FindPlayer(board, 1).Position = at;
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(1), "tank", &swimmer);
        if (plan.MovementHold == "nefarian_rising_floor_missed")
        {
            missed = true;
            return -1;
        }
        if (plan.Ascent && plan.Ascent->Stage == AscentStage::Board)
            return step;
        if (plan.Ascent && plan.Ascent->Stage == AscentStage::Swim)
        {
            target = plan.Ascent->World;
            speed = plan.Ascent->SwimSpeedYardsPerSecond > 0.0f
                ? plan.Ascent->SwimSpeedYardsPerSecond : SwimSpeedYardsPerSecond;
        }
        float const dx = target.X - at.X;
        float const dy = target.Y - at.Y;
        float const dz = target.Z - at.Z;
        float const left = std::sqrt(dx * dx + dy * dy + dz * dz);
        float const move = std::min(left, speed * decisionGapSeconds);
        if (left > 1e-4f)
            at = { at.X + dx * move / left, at.Y + dy * move / left, at.Z + dz * move / left };
    }
    return -2;
}

static void TestRisingFloorReplay()
{
    for (float gap : { 0.1f, 0.5f, 0.8f, 1.0f, 1.2f })
    {
        bool missed = false;
        int const boarded = ReplayRisingFloor(gap, missed);
        std::printf("RISING gap %.1f boarded %d missed %d\n", gap, boarded, missed ? 1 : 0);
        CHECK(boarded >= 0 && !missed,
            "the swimmer boards the rising floor even when decisions skip a 0.74 s window");
    }
    // The re-review's boundary: feet at the surface limit (2.7213), the floor
    // 0.46 under them and rising; the next decision comes late.
    for (float gap : { 0.1f, 0.5f, 0.8f, 1.2f })
    {
        bool missed = false;
        int const boarded = ReplayRisingFloor(gap, missed, MagmaSurfaceZ - 0.05f, 0.46f);
        std::printf("RISING surface gap %.1f boarded %d missed %d\n", gap, boarded, missed ? 1 : 0);
        CHECK(boarded >= 0 && !missed,
            "a swimmer at the surface with the floor just below still boards after a late decision");
    }
    // The ring cases (second and third re-reviews): the same surface boundary
    // (feet 2.7213, the floor 0.46 under them) over the flat ring (r 40), the
    // ramp (r 27) and the flat centre (r 12). The board band is the lawful one
    // (the emerge report is made where the swimmer is), so where the floor
    // closes at the full rise a late decision is a typed miss, never anything
    // else; over the ramp the inward swim keeps it open.
    for (LocalPoint const at : { Polar(DegToRad(60.0f), 40.0f), Polar(DegToRad(60.0f), 27.0f),
            Polar(DegToRad(60.0f), 12.0f) })
    {
        float nearest = 0.0f;
        NearestPillar(at, nearest);
        CHECK(nearest > PillarSkirtRadius, "the ring case is clear of every pillar");
        bool const ramp = FloorSlopeOutward(at) > 0.0f;
        for (float gap : { 0.1f, 0.5f, 0.8f, 1.0f, 1.2f })
        {
            bool missed = false;
            int const boarded = ReplayRisingFloor(gap, missed, MagmaSurfaceZ - 0.05f, 0.46f, at);
            std::printf("RISING ring r %.0f gap %.1f boarded %d missed %d\n", Length(at), gap,
                boarded, missed ? 1 : 0);
            CHECK((boarded >= 0) != missed, "it boards or reports the typed miss");
            if (ramp || gap <= 0.5f)
                CHECK(boarded >= 0, "over the ramp, or with decisions inside the band, it boards");
            if (!ramp && gap >= 0.8f)
                CHECK(missed, "over flat floor a decision after the 0.7 s band is a typed miss");
        }
    }
    CHECK(FloorSlopeOutward(Polar(0.0f, 40.0f)) == 0.0f
        && FloorSlopeOutward(Polar(0.0f, 27.0f)) > 0.17f
        && FloorSlopeOutward(Polar(0.0f, 12.0f)) == 0.0f, "the floor slope under the swimmer");
}

// Phase 3: off the pillar before Nefarian lands (Shadow of Cowardice).
static void TestDescent()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard landing = AscentBoard(PlatformFrame::RaisedOriginZ);
    landing.Summons.resize(1); // Nefarian airborne, prototypes dead
    uint8 const pillar = 2;
    uint8 const slot = 0;
    auto at = [&landing](LocalPoint local, float localZ)
    {
        FindPlayer(landing, 1).Position = LocalToWorld(local, localZ,
            PlatformFrame::RaisedOriginZ);
        NativeFacts facts;
        facts.PillarAscentSupported = true;
        facts.Placements.push_back(PlacementAt(landing, 1, local, localZ));
        return facts;
    };
    auto stage = [](AdaptiveNefarianPlan const& plan)
    {
        auto const* move = plan.Movement
            ? std::get_if<BotNativeAction::TransportSurfaceMove>(&plan.Movement->Action) : nullptr;
        return move;
    };

    NativeFacts const top = at(PillarSlot(pillar, slot), PlatformFrame::PillarTopLocalZ);
    AdaptiveNefarianPlan const rim = strategy.Propose(landing, Bot(1), "tank", &top);
    auto const* rimWalk = stage(rim);
    CHECK(rim.Phase == Phase::NefarianLanding && rimWalk
        && rimWalk->Kind == BotNativeAction::TransportSurfaceMove::Stage::Walk
        && Near(Distance(WorldToLocal({ rimWalk->X, rimWalk->Y, rimWalk->Z }),
            PillarCenters[pillar]), DescentRimRadius, 0.01f)
        && rim.Movement->ActionPriority == BotActionArbitration::Priority::Survival
        && rim.Blocked.empty(), "walk out to the rim");

    LocalPoint const rimPoint = PillarRadial(pillar, slot, DescentRimRadius);
    NativeFacts const onRim = at(rimPoint, 9.3f);
    AdaptiveNefarianPlan const stepOffPlan = strategy.Propose(landing, Bot(1), "tank", &onRim);
    auto const* stepOff = stage(stepOffPlan);
    CHECK(stepOff && stepOff->Kind == BotNativeAction::TransportSurfaceMove::Stage::StepOff
        && Near(stepOff->LandingZ, PlatformFrame::RaisedOriginZ + RingLocalZ, 0.001f)
        && stepOff->LandOnTransport, "step off the rim onto the ring");

    NativeFacts const overVoid = at(PillarRadial(pillar, slot,
        DescentOverVoidRadius(pillar, slot) + 0.05f), 9.2f);
    AdaptiveNefarianPlan const fallPlan = strategy.Propose(landing, Bot(1), "tank", &overVoid);
    auto const* fall = stage(fallPlan);
    CHECK(fall && fall->Kind == BotNativeAction::TransportSurfaceMove::Stage::Fall,
        "over the void: fall");
    CHECK(9.3f - RingLocalZ < 14.57f, "the drop is under the fall-damage threshold");

    NativeFacts falling = overVoid;
    falling.Falls.push_back({ Bot(1), true, false });
    AdaptiveNefarianPlan const landPlan = strategy.Propose(landing, Bot(1), "tank", &falling);
    auto const* land = stage(landPlan);
    CHECK(land && land->Kind == BotNativeAction::TransportSurfaceMove::Stage::Land,
        "a running fall ends with its landing");

    NativeFacts const risingTop = at(PillarSlot(pillar, slot), PlatformFrame::PillarTopLocalZ);
    Blackboard rising = landing;
    rising.Interactables = { MakeElevator(0.0f) };
    FindPlayer(rising, 1).Position = LocalToWorld(PillarSlot(pillar, slot),
        PlatformFrame::PillarTopLocalZ, 0.0f);
    AdaptiveNefarianPlan const wait = strategy.Propose(rising, Bot(1), "tank", &risingTop);
    CHECK(!wait.Movement && wait.Phase == Phase::PlatformReturn,
        "the floor still rising: stay on the pillar");

    NativeFacts const landed = at(PillarRadial(pillar, slot, 6.4f), RingLocalZ);
    AdaptiveNefarianPlan const after = strategy.Propose(landing, Bot(1), "tank", &landed);
    CHECK(after.MovementSurface && after.MovementSurface->Purpose != MovePurpose::PillarDescent,
        "landed on the ring: back to the floor plan");
}

// The warrior handler (the Feral Onyxia tank) in phase 3: Nature's Grasp and a
// kite that never leads a warrior in front of Nefarian.
static void TestWarriorHandler()
{
    AdaptiveNefarianStrategy strategy;
    for (int facingDeg = 0; facingDeg < 360; facingDeg += 30)
    {
        Blackboard ground = CanonicalBoard();
        ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f },
            DegToRad(float(facingDeg)));
        nefarian.InCombat = true;
        nefarian.VictimGuid = Bot(1);
        ground.Summons = { nefarian };
        EncounterView const view0 = ObserveEncounter(ground);
        DutyPlan const duty = BuildNefarianDutyPlan(ground);
        ArenaLayout const layout = BuildArenaLayout(duty);
        float const raidSign = PhaseThreeWingSign(view0, layout);
        LocalPoint const pen = Offset({ 0.0f, 0.0f },
            GroundFacing(view0, layout) - raidSign * Pi / 2.0f, HandlerPenRadius);
        FindPlayer(ground, 2).Position = LocalToWorld(pen, FloorLocalZAt(pen),
            PlatformFrame::RaisedOriginZ);
        ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, 31,
            Offset(pen, AngleOf(pen), 2.0f));
        warrior.VictimGuid = Bot(2);
        ground.Summons.push_back(warrior);
        NativeFacts facts;
        facts.Placements.push_back(PlacementAt(ground, 2, pen, FloorLocalZAt(pen)));
        AdaptiveNefarianPlan const plan = strategy.Propose(ground, Bot(2), "tank", &facts);
        EncounterView const view = ObserveEncounter(ground);
        CHECK(plan.MovementSurface && plan.MovementSurface->Purpose == MovePurpose::Kite
            && WarriorPointSafe(view, plan.MovementSurface->Local)
            && Distance(plan.MovementSurface->Local, pen) > 3.0f,
            "the handler kites the warrior around the pen, clear of Nefarian's front");
        DragonPose const pose = PoseOf(*view.Nefarian);
        CHECK(!InFrontCone(pose, pen, WarriorFrontMarginDeg), "the pen is off Nefarian's front");
        float const off = OffFacing(pose.Position, pose.Facing, plan.MovementSurface->Local);
        CHECK(off >= DegToRad(BreathHalfAngleDeg + WarriorFrontMarginDeg)
            && off <= Pi - DegToRad(TailLashHalfAngleDeg),
            "the kite point is on Nefarian's flank: 15 degrees clear of the breath, off the tail");
        CHECK(!WarriorPointSafe(view, Offset(pose.Position, pose.Facing, 20.0f))
            && !WarriorPointSafe(view, Offset(pose.Position, pose.Facing + DegToRad(55.0f), 20.0f))
            && WarriorPointSafe(view, Offset(pose.Position, pose.Facing + DegToRad(90.0f), 20.0f)),
            "a warrior is never led into or near the breath cone");
        bool const grasp = std::any_of(plan.Actions.begin(), plan.Actions.end(),
            [](BotNativeAction::Candidate const& action)
            {
                auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
                return cast && cast->SpellId == SpellNaturesGrasp && cast->Target == Bot(2);
            });
        CHECK(grasp, "Nature's Grasp once a warrior attacks the handler");
        CHECK(plan.DamageTarget == warrior.Guid, "the handler holds the warrior's attention");

        NativeFacts untaught = facts;
        untaught.Readiness.push_back({ Bot(2), SpellNaturesGrasp, true, false });
        CHECK(!DecideNaturesGrasp(view, duty, FindPlayer(ground, 2), &untaught),
            "no Nature's Grasp the druid does not know");
        Blackboard buffed = ground;
        AddAura(FindPlayer(buffed, 2), SpellNaturesGrasp);
        EncounterView const buffedView = ObserveEncounter(buffed);
        CHECK(!DecideNaturesGrasp(buffedView, duty, FindPlayer(buffed, 2), &facts),
            "not while it is still up");
    }
}

// Review regressions: a rooted warrior is never hit; no movement of a bot
// that leads warriors (the handler, or a chased bot) crosses Nefarian's front,
// fire escapes included.
static void TestWarriorHazards()
{
    AdaptiveNefarianStrategy strategy;
    CHECK(IsBoneWarriorHeld([] { ActorSnapshot w; w.Auras.push_back({ SpellNaturesGraspRoot,
        ObjectGuid{}, 1, 0 }); return w; }()), "Entangling Roots holds a warrior");

    Blackboard ground = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    ground.Summons = { nefarian };
    LocalPoint const handlerAt{ 12.0f, -20.8f };
    FindPlayer(ground, 2).Position = LocalToWorld(handlerAt, FloorLocalZAt(handlerAt),
        PlatformFrame::RaisedOriginZ);
    ActorSnapshot rooted = MakeCreature(BoneWarriorEntry, 31, { 13.0f, -23.0f });
    rooted.VictimGuid = Bot(2);
    AddAura(rooted, SpellNaturesGraspRoot);
    ground.Summons.push_back(rooted);
    NativeFacts facts;
    facts.Placements.push_back(PlacementAt(ground, 2, handlerAt, FloorLocalZAt(handlerAt)));
    AdaptiveNefarianPlan const holding = strategy.Propose(ground, Bot(2), "tank", &facts);
    CHECK(holding.DamageTarget != rooted.Guid && holding.SuppressOffense,
        "the handler never hits its rooted warrior (roots break on damage)");

    // The review's replay: Nefarian at the centre facing 0, the handler at
    // (12, -20.8) with a warrior on it, a Shadowblaze fire at (8, -24).
    Blackboard fire = ground;
    fire.Summons.back().Auras.clear();
    ActorSnapshot flame = MakeCreature(ShadowblazeEntry, 50, { 8.0f, -24.0f });
    flame.Attackable = false;
    fire.Summons.push_back(flame);
    EncounterView const view = ObserveEncounter(fire);
    AdaptiveNefarianPlan const escape = strategy.Propose(fire, Bot(2), "tank", &facts);
    CHECK(!escape.MovementSurface
        || WarriorPathSafe(view, handlerAt, escape.MovementSurface->Local),
        "the handler's fire escape never leads its warrior through Nefarian's front");
    CHECK(!escape.MovementLeg || WarriorPathNoDeeper(view, handlerAt, escape.MovementLeg->To),
        "nor does the leg it walks now");
    CHECK(!(escape.MovementSurface && Distance(escape.MovementSurface->Local, { 17.37f, -16.50f }) < 1.0f),
        "the reviewed unsafe destination is gone");

    // A chased DPS near a fire, in every Nefarian facing: its escape or kite
    // path never crosses his front with the warrior behind it.
    for (int facingDeg = 0; facingDeg < 360; facingDeg += 30)
    {
        Blackboard chased = CanonicalBoard();
        ActorSnapshot turned = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f },
            DegToRad(float(facingDeg)));
        turned.InCombat = true;
        turned.VictimGuid = Bot(1);
        LocalPoint const at = Polar(DegToRad(float(facingDeg) + 70.0f), 20.0f);
        FindPlayer(chased, 3).Position = LocalToWorld(at, FloorLocalZAt(at),
            PlatformFrame::RaisedOriginZ);
        ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, 31, Offset(at, 0.0f, 3.0f));
        warrior.VictimGuid = Bot(3);
        ActorSnapshot blaze = MakeCreature(ShadowblazeEntry, 50, Offset(at, 1.0f, 1.0f));
        blaze.Attackable = false;
        chased.Summons = { turned, warrior, blaze };
        NativeFacts chasedFacts;
        chasedFacts.Placements.push_back(PlacementAt(chased, 3, at, FloorLocalZAt(at)));
        AdaptiveNefarianPlan const plan = strategy.Propose(chased, Bot(3), "dps", &chasedFacts);
        EncounterView const chasedView = ObserveEncounter(chased);
        CHECK(!plan.MovementSurface
            || WarriorPathSafe(chasedView, at, plan.MovementSurface->Local),
            "a chased bot's destination path stays off Nefarian's front");
        CHECK(!plan.MovementLeg || WarriorPathNoDeeper(chasedView, at, plan.MovementLeg->To),
            "and so does its leg");
    }
}

// Re-review: a handler already inside the exclusion margin (or Nefarian
// turning onto it) must still get an escape out of it, never deeper in; and a
// running walk into the exclusion is never kept.
static void TestWarriorEscape()
{
    AdaptiveNefarianStrategy strategy;
    for (float offDeg : { 55.0f, 30.0f, -55.0f, 150.0f })
    {
        Blackboard ground = CanonicalBoard();
        ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
        nefarian.InCombat = true;
        nefarian.VictimGuid = Bot(1);
        LocalPoint const at = Polar(DegToRad(offDeg), 24.0f);
        FindPlayer(ground, 2).Position = LocalToWorld(at, FloorLocalZAt(at),
            PlatformFrame::RaisedOriginZ);
        ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, 31, Offset(at, DegToRad(offDeg), 2.0f));
        warrior.VictimGuid = Bot(2);
        ActorSnapshot blaze = MakeCreature(ShadowblazeEntry, 50, Offset(at, DegToRad(offDeg + 90.0f), 1.0f));
        blaze.Attackable = false;
        ground.Summons = { nefarian, warrior, blaze };
        NativeFacts facts;
        facts.Placements.push_back(PlacementAt(ground, 2, at, FloorLocalZAt(at)));
        EncounterView const view = ObserveEncounter(ground);
        CHECK(!WarriorPointSafe(view, at), "the handler starts inside the exclusion");
        AdaptiveNefarianPlan const plan = strategy.Propose(ground, Bot(2), "tank", &facts);
        CHECK(plan.MovementSurface && plan.Movement && plan.MovementLeg,
            "an actual escape destination and leg are emitted");
        if (plan.MovementSurface && plan.MovementLeg)
        {
            CHECK(WarriorPointSafe(view, plan.MovementSurface->Local)
                && WarriorPathSafe(view, at, plan.MovementSurface->Local)
                && WarriorPathNoDeeper(view, at, plan.MovementLeg->To),
                "it leaves the exclusion monotonically, never deeper");
            CHECK(WarriorDanger(view, plan.MovementLeg->To) <= WarriorDanger(view, at) + 1e-4f,
                "its first leg goes no deeper");
        }
    }

    // The re-review's retention replay: a walk running from the handler into
    // Nefarian's rear exclusion is not kept as nefarian_leg_in_flight.
    Blackboard ground = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    LocalPoint const handler{ -11.27f, 21.19f };
    LocalPoint const running{ -20.49f, 23.45f };
    FindPlayer(ground, 2).Position = LocalToWorld(handler, FloorLocalZAt(handler),
        PlatformFrame::RaisedOriginZ);
    ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, 31, Offset(handler, 0.0f, 3.0f));
    warrior.VictimGuid = Bot(2);
    ground.Summons = { nefarian, warrior };
    NativeFacts facts;
    facts.Placements.push_back(PlacementAt(ground, 2, handler, FloorLocalZAt(handler)));
    facts.Motion.push_back({ Bot(2), true, LocalToWorld(running, FloorLocalZAt(running),
        PlatformFrame::RaisedOriginZ) });
    EncounterView const view = ObserveEncounter(ground);
    CHECK(!WarriorPathSafe(view, handler, running), "the running walk enters the exclusion");
    AdaptiveNefarianPlan const plan = strategy.Propose(ground, Bot(2), "tank", &facts);
    CHECK(plan.MovementHold != "nefarian_leg_in_flight", "an unsafe running walk is not kept");
    CHECK((plan.Movement && plan.MovementLeg && WarriorPathNoDeeper(view, handler, plan.MovementLeg->To))
        || (!plan.Movement && plan.MovementHold == WarriorStopHold),
        "a safe leg replaces it, or it is stopped");
}

// The second re-review's temporal cases.
static void PlaceAt(ActorSnapshot& actor, LocalPoint point)
{
    actor.Position = LocalToWorld(point, FloorLocalZAt(point), PlatformFrame::RaisedOriginZ);
}

static Blackboard WarriorGround(LocalPoint self, LocalPoint warriorAt, uint32 victim)
{
    Blackboard board = CanonicalBoard();
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    ActorSnapshot warrior = MakeCreature(BoneWarriorEntry, 31, warriorAt);
    warrior.InCombat = true;
    warrior.VictimGuid = Bot(victim);
    board.Summons = { nefarian, warrior };
    PlaceAt(FindPlayer(board, victim), self);
    return board;
}

static NativeFacts StandingFacts(Blackboard const& board, uint32 member)
{
    NativeFacts facts;
    LocalPoint const at = WorldToLocal(board.FindActor(Bot(member))->Position);
    facts.Placements.push_back(PlacementAt(board, member, at, FloorLocalZAt(at)));
    return facts;
}

static void TestWarriorTemporal()
{
    AdaptiveNefarianStrategy strategy;

    // P1.1: a 9.5-yard leg generated with Nefarian facing -90 degrees is
    // running when he turns to 0: it is stopped, with the movement lane.
    {
        LocalPoint const self{ -24.930241f, -28.678965f };
        LocalPoint const end{ -26.480778f, -19.306362f };
        Blackboard board = WarriorGround(self, Offset(self, 0.0f, 2.0f), 2);
        ActorSnapshot fire = MakeCreature(ShadowblazeEntry, 50, Offset(self, 0.0f, 1.0f));
        fire.Attackable = false;
        board.Summons.push_back(fire);
        EncounterView const view = ObserveEncounter(board);
        CHECK(SegmentWalkable(self, end) && !WarriorPathNoDeeper(view, self, end),
            "the running leg now leads the warrior deeper into the exclusion");
        NativeFacts moving = StandingFacts(board, 2);
        moving.Motion.push_back({ Bot(2), true, LocalToWorld(end, FloorLocalZAt(end),
            PlatformFrame::RaisedOriginZ) });
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank", &moving);
        std::printf("TEMPORAL stop hold=%s movement=%d\n", std::string(plan.MovementHold).c_str(),
            plan.Movement ? 1 : 0);
        CHECK(plan.MovementHold == WarriorStopHold
            || (plan.Movement && plan.MovementLeg
                && WarriorPathNoDeeper(view, self, plan.MovementLeg->To)),
            "the unsafe running walk is stopped or replaced by a lawful leg");
        CHECK(plan.MovementHold != "nefarian_leg_in_flight"
            && plan.MovementHold != "nefarian_warrior_path_unsafe",
            "never kept, never a diagnostic alone");
        // Standing, with no lawful leg: the hold is renewed (the lease keeps
        // combat range movement from walking it in).
        NativeFacts still = StandingFacts(board, 2);
        AdaptiveNefarianPlan const standing = strategy.Propose(board, Bot(2), "tank", &still);
        CHECK(standing.MovementHold == WarriorStopHold
            || (standing.Movement && standing.MovementLeg
                && WarriorPathNoDeeper(view, self, standing.MovementLeg->To)),
            "standing, it stays held or takes a lawful leg");
        CHECK(standing.MovementHold != "nefarian_warrior_path_unsafe",
            "the refused leg is never a bare diagnostic");
    }

    // P1.2: Nefarian on the Blood DK at (14, 0), a warrior on the DK as well.
    // The tank keeps its tank hold at every step; the handler taunts the
    // warrior off it.
    {
        Blackboard board = WarriorGround({ 14.0f, 0.0f }, { 15.0f, 0.0f }, 1);
        for (int step = 0; step < 8; ++step)
        {
            NativeFacts facts = StandingFacts(board, 1);
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(1), "tank", &facts);
            CHECK(plan.MovementSurface && plan.MovementSurface->Purpose == MovePurpose::TankHold,
                "the dragon's tank keeps its tank hold with a warrior on it");
            if (!plan.MovementLeg)
                break;
            LocalPoint const self = WorldToLocal(FindPlayer(board, 1).Position);
            LocalPoint const next = StepToward(self, plan.MovementLeg->To, 2.0f);
            PlaceAt(FindPlayer(board, 1), next);
            PlaceAt(board.Summons[1], Offset(next, 0.0f, 1.0f));
            board.Summons[0].Facing = AngleOf(next) + PlatformFrame::Orientation;
        }
        Blackboard handled = WarriorGround({ 14.0f, 0.0f }, { 15.0f, 0.0f }, 1);
        NativeFacts handlerFacts = StandingFacts(handled, 2);
        AdaptiveNefarianPlan const handler = strategy.Propose(handled, Bot(2), "tank",
            &handlerFacts);
        bool const taunt = std::any_of(handler.Actions.begin(), handler.Actions.end(),
            [&](BotNativeAction::Candidate const& action)
            {
                auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
                return cast && cast->Target == handled.Summons[1].Guid
                    && action.Id.Mechanic == "bone_warrior_taunt";
            });
        DutyPlan const handledDuty = BuildNefarianDutyPlan(handled);
        NativeFacts shacklerFacts = StandingFacts(handled, uint32(handledDuty.Shackler.GetCounter() - 30500));
        AdaptiveNefarianPlan const shackler = strategy.Propose(handled, handledDuty.Shackler,
            "healer", &shacklerFacts);
        bool const shackle = std::any_of(shackler.Actions.begin(), shackler.Actions.end(),
            [&](BotNativeAction::Candidate const& action)
            {
                auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
                return cast && cast->Target == handled.Summons[1].Guid;
            });
        std::printf("TEMPORAL tank warrior taunt=%d shackle=%d\n", taunt ? 1 : 0, shackle ? 1 : 0);
        CHECK((handler.DamageTarget == handled.Summons[1].Guid && taunt) || shackle,
            "the Feral handler taunts the warrior off the dragon's tank, or it is shackled");
        // The shackler alive but Shackle Undead not ready: the warrior is not
        // left reserved to nobody; the handler takes and taunts it.
        NativeFacts noShackle = StandingFacts(handled, 2);
        noShackle.Readiness.push_back({ handledDuty.Shackler, SpellShackleUndead, false, true });
        AdaptiveNefarianPlan const covering = strategy.Propose(handled, Bot(2), "tank", &noShackle);
        bool const covered = std::any_of(covering.Actions.begin(), covering.Actions.end(),
            [&](BotNativeAction::Candidate const& action)
            {
                auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
                return cast && cast->Target == handled.Summons[1].Guid
                    && action.Id.Mechanic == "bone_warrior_taunt";
            });
        CHECK(covering.DamageTarget == handled.Summons[1].Guid && covered,
            "with Shackle unavailable the handler taunts the warrior");
    }

    // P2.3: the handler with a pursuing warrior, replayed with moving facts
    // and partial steps: no reversal between kite and pen.
    for (float start : { -80.0f, -90.0f, -100.0f })
    {
        Blackboard board = WarriorGround(Polar(DegToRad(start), 24.0f),
            Polar(DegToRad(start + 12.0f), 24.0f), 2);
        std::optional<LocalPoint> destination;
        LocalPoint previous{};
        bool had = false;
        int reversals = 0;
        for (int t = 0; t < 40; ++t)
        {
            LocalPoint const self = WorldToLocal(FindPlayer(board, 2).Position);
            LocalPoint const add = WorldToLocal(board.Summons[1].Position);
            NativeFacts facts = StandingFacts(board, 2);
            if (destination)
                facts.Motion.push_back({ Bot(2), true, LocalToWorld(*destination,
                    FloorLocalZAt(*destination), PlatformFrame::RaisedOriginZ) });
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank", &facts);
            if (plan.Movement && plan.MovementLeg)
                destination = plan.MovementLeg->To;
            if (!destination)
            {
                PlaceAt(board.Summons[1], StepToward(add, self, 1.0f));
                previous = {};
                had = false;
                continue;
            }
            LocalPoint const next = StepToward(self, *destination, 1.75f);
            LocalPoint const delta{ next.X - self.X, next.Y - self.Y };
            if (had && delta.X * previous.X + delta.Y * previous.Y < -0.5f)
                ++reversals;
            previous = delta;
            had = true;
            PlaceAt(FindPlayer(board, 2), next);
            PlaceAt(board.Summons[1], StepToward(add, next, 1.0f));
            if (Distance(next, *destination) < 0.01f)
                destination.reset();
        }
        std::printf("HANDLER replay start %.0f reversals %d\n", start, reversals);
        CHECK(reversals == 0, "the handler never reverses between kite and pen");
    }

    // P2.4: a rooted warrior nearest the handler never masks an unheld one.
    {
        Blackboard board = WarriorGround({ 0.0f, -24.0f }, { 0.0f, -22.0f }, 2);
        AddAura(board.Summons[1], SpellNaturesGraspRoot);
        ActorSnapshot unheld = MakeCreature(BoneWarriorEntry, 32, { 0.0f, -19.0f });
        unheld.VictimGuid = Bot(2);
        board.Summons.push_back(unheld);
        EncounterView const view = ObserveEncounter(board);
        CHECK(ChasingBoneWarrior(view, FindPlayer(board, 2), HandlerKiteTriggerYards)
            == view.BoneWarriors[1], "the unheld warrior is the chaser");
        NativeFacts facts = StandingFacts(board, 2);
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank", &facts);
        CHECK(plan.MovementSurface && plan.MovementSurface->Purpose == MovePurpose::Kite
            && plan.Movement, "the handler kites the unheld warrior past the rooted one");
    }
}

#include "Bots/BotMovementArbiter.h"

// Fourth-pass review: the handler cornered where it stands, an unheld
// pursuer beside it, the priest dead, taunt and Nature's Grasp unavailable,
// its damage target a warrior 34 yards away. The hold is renewed every
// decision, moving or not, so the Hazard lease never lapses under it and
// combat range recovery never chases the distant target; a lawful way out
// releases it.
static void TestCorneredHold()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    LocalPoint const self = Polar(DegToRad(-120.0f), 24.0f);
    PlaceAt(FindPlayer(board, 2), self);
    FindPlayer(board, 7).Alive = false;
    ActorSnapshot nefarian = MakeCreature(NefarianEntry, 12, { 0.0f, 0.0f }, 0.0f);
    nefarian.InCombat = true;
    nefarian.VictimGuid = Bot(1);
    ActorSnapshot near = MakeCreature(BoneWarriorEntry, 31, Polar(DegToRad(-110.0f), 24.0f));
    near.InCombat = true;
    near.VictimGuid = Bot(2);
    ActorSnapshot far = MakeCreature(BoneWarriorEntry, 32, { 15.0f, 0.0f });
    far.InCombat = true;
    far.VictimGuid = Bot(3);
    board.Summons = { nefarian, near, far };
    NativeFacts facts = StandingFacts(board, 2);
    ActorSnapshot const& handler = FindPlayer(board, 2);
    facts.Readiness.push_back({ Bot(2), TauntFor(handler.ClassSpec).SpellId, false, true });
    facts.Readiness.push_back({ Bot(2), WarriorRootFor(handler.ClassSpec), false, true });
    NativeFacts moving = facts;
    LocalPoint const end = Polar(DegToRad(-140.0f), 24.0f);
    moving.Motion.push_back({ Bot(2), true, LocalToWorld(end, FloorLocalZAt(end),
        PlatformFrame::RaisedOriginZ) });

    // The lease the stop candidate renews (1.5 s, Hazard), and the combat
    // range request profile range recovery would make toward the far target.
    using BotMovementArbitration::Apply;
    using BotMovementArbitration::Decision;
    using BotMovementArbitration::Evaluate;
    using BotMovementArbitration::Owner;
    using BotMovementArbitration::Request;
    BotMovementArbitration::Scope const scope{ 1, 0, 0, 669, 1 };
    BotMovementArbitration::Lease lease;
    for (int step = 0; step < 5; ++step)
    {
        uint64 const now = 1000 + uint64(step) * 1000;
        board.ObservedAtMs = now;
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank",
            step ? &facts : &moving);
        std::printf("CORNER t=%d hold=%s movement=%d target_far=%d\n", step,
            std::string(plan.MovementHold).c_str(), plan.Movement ? 1 : 0,
            plan.DamageTarget == far.Guid ? 1 : 0);
        CHECK(!plan.Movement && plan.MovementHold == WarriorStopHold,
            "the cornered handler's hold is renewed every decision, moving or not");
        if (plan.MovementHold == WarriorStopHold)
        {
            Request hold;
            hold.MovementOwner = Owner::Hazard;
            hold.MovementPriority = BotMovementArbitration::Priority::Hazard;
            hold.ExpiresAtMs = now + 1500;
            hold.MovementScope = scope;
            Apply(lease, hold);
        }
        Request range;
        range.MovementOwner = Owner::CombatRange;
        range.MovementPriority = BotMovementArbitration::Priority::Combat;
        range.ExpiresAtMs = now + 1500;
        range.MovementScope = scope;
        range.DynamicTargetGuid = far.Guid.GetRawValue();
        CHECK(Evaluate(lease, range, now + 900) == Decision::PreserveExisting,
            "combat range recovery toward the distant target stays blocked across lease expiry");
    }

    // A lawful way out releases it: the pursuer rooted (held), nothing chases.
    Blackboard released = board;
    AddAura(released.Summons[1], SpellNaturesGraspRoot);
    AdaptiveNefarianPlan const free = strategy.Propose(released, Bot(2), "tank", &facts);
    std::printf("CORNER released hold=%s movement=%d\n", std::string(free.MovementHold).c_str(),
        free.Movement ? 1 : 0);
    CHECK(free.MovementHold != WarriorStopHold, "the hold ends when the pursuer is held");
    CHECK(!free.MovementSurface || !free.MovementSurface->WarriorHold, "no cornered goal remains");
}

// Round 7 (first live attempt): bots on the raised platform are held by the
// plan whenever it has no leg for them, so native combat range, chase and
// route walks (static navmesh paths under the transport) cannot take them
// off it; and casters and healers stand where no pillar blocks their lines.
static void TestPlatformHold()
{
    AdaptiveNefarianStrategy strategy;
    for (bool landed : { false, true })
    {
        Blackboard board = CanonicalBoard();
        AddDragons(board, landed);
        for (uint32 member = 1; member <= 10; ++member)
        {
            // First decision: where the plan sends it; then standing there.
            NativeFacts first = StandingFacts(board, member);
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(member), "", &first);
            if (!plan.MovementSurface || plan.MovementSurface->Target != Surface::Floor)
                continue;
            Blackboard arrived = board;
            PlaceAt(FindPlayer(arrived, member), plan.MovementSurface->Local);
            NativeFacts standing = StandingFacts(arrived, member);
            AdaptiveNefarianPlan const held = strategy.Propose(arrived, Bot(member), "", &standing);
            CHECK(IsPlatformHold(held.MovementHold) || held.MovementHold == WarriorStopHold
                || held.MovementHold == LegInFlightHold,
                "a bot on the platform always carries a hold: alone, or beside its leg as the fallback");
            CHECK(!held.Ascent, "no ascent on the raised platform");
            // Its own leg running: the lease is kept, the leg is not stopped.
            if (plan.Movement && plan.MovementLeg)
            {
                NativeFacts moving = first;
                LocalPoint const to = plan.MovementLeg->To;
                moving.Motion.push_back({ Bot(member), true,
                    LocalToWorld(to, FloorLocalZAt(to), PlatformFrame::RaisedOriginZ) });
                AdaptiveNefarianPlan const flight = strategy.Propose(board, Bot(member), "", &moving);
                CHECK(flight.MovementHold == LegInFlightHold
                    || (flight.Movement && IsPlatformHold(flight.MovementHold)),
                    "a running leg of the plan keeps its lease, or a new leg carries the fallback");
            }
        }
    }
    // Off the platform (no elevator placement, feet in the bowl under it):
    // not held there.
    Blackboard below = CanonicalBoard();
    AddDragons(below, true);
    FindPlayer(below, 4).Position = LocalToWorld({ -27.0f, 1.3f }, 0.0f, 0.0f);
    FindPlayer(below, 4).Position.Z = -1.63f;
    NativeFacts none;
    AdaptiveNefarianPlan const off = strategy.Propose(below, Bot(4), "dps", &none);
    CHECK(!IsPlatformHold(off.MovementHold), "a bot off the platform is not held as if on it");

    // Pillar sight: every ranged or healer spot sees its target and, for a
    // healer, both tanks, past the pillars (the first attempt's mage lost
    // sight of Onyxia and was walked off the platform).
    CHECK(!PillarSightClear(Polar(0.0f, 30.0f), Polar(0.0f, 50.0f)), "a pillar blocks that line");
    CHECK(PillarSightClear(Polar(DegToRad(60.0f), 20.0f), { 0.0f, 0.0f }), "a clear line");
    int checked = 0;
    for (int onyxiaDeg = 0; onyxiaDeg < 360; onyxiaDeg += 45)
    {
        Blackboard board = CanonicalBoard();
        AddDragons(board, true);
        board.Summons[0].Position = LocalToWorld(Polar(DegToRad(float(onyxiaDeg)), 26.0f),
            FloorLocalZAt(Polar(DegToRad(float(onyxiaDeg)), 26.0f)), PlatformFrame::RaisedOriginZ);
        for (uint32 member : { 3u, 4u, 5u, 7u, 9u, 10u })
        {
            NativeFacts facts = StandingFacts(board, member);
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(member), "", &facts);
            if (!plan.MovementSurface || plan.MovementSurface->Purpose != MovePurpose::Formation)
                continue;
            ActorSnapshot const& bot = FindPlayer(board, member);
            EncounterView const view = ObserveEncounter(board);
            DutyPlan const duty = BuildNefarianDutyPlan(board);
            ArenaLayout const layout = BuildArenaLayout(duty);
            MovementContext const context{ board, view, duty, layout, bot, &facts };
            std::vector<LocalPoint> const targets = SightTargets(context, plan.DamageTarget,
                IsHealerSpec(bot.ClassSpec, bot.Role));
            bool const clear = std::all_of(targets.begin(), targets.end(), [&](LocalPoint target)
                { return PillarSightClear(plan.MovementSurface->Local, target); });
            if (!clear)
                std::printf("SIGHT blocked onyxia %d member %u\n", onyxiaDeg, member);
            CHECK(clear, "a ranged or healer spot sees its targets past the pillars");
            ++checked;
        }
    }
    std::printf("SIGHT checked %d spots\n", checked);
    CHECK(checked > 20, "the sight fixture covers the ranged and healers");
}

// Round 7 review and pull analysis.
// - A proposed leg always carries the platform hold as its fallback.
// - A caster or healer inside its arrival tolerance but without a clear line
//   (or out of range) finishes the leg instead of holding.
// - Healers stand within heal range of the tank that fights now, also while
//   the Feral leads Onyxia out to the ring.
// - The pull: damage dealers hold fire until a tank has Onyxia; her tank,
//   landed behind a pillar (r06), walks to where it sees her and taunts.
static void TestRoundSevenPositions()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, true);
    for (uint32 member = 1; member <= 10; ++member)
    {
        NativeFacts facts = StandingFacts(board, member);
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(member), "", &facts);
        if (plan.Movement)
            CHECK(IsPlatformHold(plan.MovementHold) || plan.MovementHold == WarriorStopHold,
                "a proposed leg on the platform carries the platform hold as its fallback");
    }

    int arrivals = 0;
    int ranged = 0;
    for (bool landed : { false, true })
        for (int deg = 0; deg < 360; deg += 30)
            for (float radius : { 20.0f, 29.0f, 42.0f })
            {
                Blackboard b = CanonicalBoard();
                AddDragons(b, landed);
                LocalPoint dragon = Polar(DegToRad(float(deg)), radius);
                PlaceAt(b.Summons[0], dragon);
                DutyPlan const duty = BuildNefarianDutyPlan(b);
                ArenaLayout const layout = BuildArenaLayout(duty);
                if (!landed)
                {
                    // Onyxia's lead-out: her tank at r 52 on her end angle.
                    PlaceAt(FindPlayer(b, 2), Polar(layout.OnyxiaEndAngle, 52.0f));
                    dragon = Polar(layout.OnyxiaEndAngle, radius);
                    PlaceAt(b.Summons[0], dragon);
                }
                for (uint32 member : { 3u, 4u, 5u, 7u, 9u, 10u })
                {
                    NativeFacts f = StandingFacts(b, member);
                    AdaptiveNefarianPlan const plan = strategy.Propose(b, Bot(member), "", &f);
                    if (!plan.MovementSurface || plan.MovementSurface->Purpose != MovePurpose::Formation
                        || plan.MovementSurface->Sight.empty())
                        continue;
                    LocalPoint const goal = plan.MovementSurface->Local;
                    ++ranged;
                    CHECK(SpotServes(goal, plan.MovementSurface->Sight),
                        "the spot sees every target within range");
                    if (IsHealerSpec(FindPlayer(b, member).ClassSpec, FindPlayer(b, member).Role))
                    {
                        ObjectGuid const fighting = landed ? duty.NefarianTank : duty.OnyxiaTank;
                        LocalPoint const tank = WorldToLocal(FindPlayer(b, fighting.GetCounter() - 30500).Position);
                        if (Distance(goal, tank) > SightRangeYards + 0.01f)
                            std::printf("RANGE landed %d deg %d r %.0f healer %u goal (%.1f,%.1f) tank (%.1f,%.1f) %.1f\n",
                                int(landed), deg, radius, member, goal.X, goal.Y, tank.X, tank.Y, Distance(goal, tank));
                        CHECK(Distance(goal, tank) <= SightRangeYards + 0.01f,
                            "a healer stands within heal range of the tank that fights now");
                    }
                    for (int offset = 0; offset < 360; offset += 45)
                    {
                        Blackboard near = b;
                        LocalPoint const self = Offset(goal, DegToRad(float(offset)), 2.9f);
                        PlaceAt(FindPlayer(near, member), self);
                        NativeFacts nf = StandingFacts(near, member);
                        AdaptiveNefarianPlan const held = strategy.Propose(near, Bot(member), "", &nf);
                        if (!SpotServes(self, plan.MovementSurface->Sight)
                            && held.MovementSurface
                            && Distance(held.MovementSurface->Local, goal) < 0.5f)
                        {
                            ++arrivals;
                            CHECK(held.Movement && held.MovementLeg,
                                "inside the arrival tolerance with a blocked line it finishes the leg");
                        }
                    }
                }
            }
    std::printf("ROUND7 ranged spots %d blocked arrivals %d\n", ranged, arrivals);
    CHECK(ranged > 50 && arrivals > 0, "the fixture covers casters, healers and blocked arrivals");
}

// The r06 pull, replayed: the warlock lands first, Onyxia is still
// feign-dead; the Feral lands behind pillar 0 at (-154.78, -220.95, 8.10).
static void TestOnyxiaPullReplay()
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, false);
    ActorSnapshot& onyxia = board.Summons[0];
    PlaceAt(onyxia, { 0.0f, 0.0f });
    onyxia.InCombat = false;
    onyxia.VictimGuid = ObjectGuid();
    DutyPlan const duty = BuildNefarianDutyPlan(board);
    // Before the pull no damage dealer may open on her.
    for (uint32 member : { 3u, 4u, 6u, 8u, 9u, 10u })
    {
        NativeFacts facts = StandingFacts(board, member);
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(member), "dps", &facts);
        CHECK(plan.SuppressOffense && plan.SuppressReason == HoldFirePreEngage
            && plan.DamageTarget.IsEmpty(), "pre-pull: damage dealers hold fire");
    }
    // Pulled by something else (the r06 warlock): still no damage until a
    // tank has her; healers heal.
    onyxia.InCombat = true;
    onyxia.VictimGuid = Bot(10);
    for (uint32 member : { 3u, 4u, 6u, 8u, 9u, 10u })
    {
        NativeFacts facts = StandingFacts(board, member);
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(member), "dps", &facts);
        CHECK(plan.SuppressOffense && plan.SuppressReason == HoldFireForOnyxiaTank
            && plan.DamageTarget.IsEmpty(), "damage dealers wait for her tank");
    }
    // The Feral, landed behind pillar 0, walks to where it sees her.
    ActorSnapshot& feral = FindPlayer(board, 2);
    feral.Position = { -154.781f, -220.952f, 8.10035f };
    LocalPoint self = WorldToLocal(feral.Position);
    CHECK(!PillarSightClear(self, { 0.0f, 0.0f }), "r06: the Feral landed without sight of Onyxia");
    float walked = 0.0f;
    int steps = 0;
    for (; steps < 20; ++steps)
    {
        NativeFacts facts = StandingFacts(board, 2);
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank", &facts);
        if (PillarSightClear(self, { 0.0f, 0.0f }) && Distance(self, { 0.0f, 0.0f }) <= OnyxiaTauntReachYards)
        {
            bool const taunt = std::any_of(plan.Actions.begin(), plan.Actions.end(),
                [](BotNativeAction::Candidate const& action)
                { return action.Id.Mechanic == "onyxia_taunt"; });
            CHECK(taunt, "in sight and range it taunts her");
            break;
        }
        if (!plan.Movement)
            std::printf("PULL step %d self (%.1f,%.1f) d %.1f sight %d hold %s goal %d\n", steps, self.X, self.Y,
                Distance(self, { 0.0f, 0.0f }), int(PillarSightClear(self, { 0.0f, 0.0f })),
                std::string(plan.MovementHold).c_str(), plan.MovementSurface ? int(plan.MovementSurface->Purpose) : -1);
        CHECK(plan.Movement && plan.MovementLeg, "until then it walks toward its pickup spot");
        if (!plan.MovementLeg)
            break;
        LocalPoint const next = plan.MovementLeg->To;
        walked += Distance(self, next);
        self = next;
        PlaceAt(feral, self);
    }
    std::printf("PULL feral walked %.1f yd in %d legs (about %.1f s at 7 yd/s)\n", walked, steps,
        walked / 7.0f);
    CHECK(walked / 7.0f < 6.0f, "the Feral has sight of Onyxia within a few seconds");
    // Once she attacks her tank the damage dealers burn her.
    onyxia.VictimGuid = Bot(2);
    for (uint32 member : { 3u, 4u, 6u, 8u, 9u, 10u })
    {
        NativeFacts facts = StandingFacts(board, member);
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(member), "dps", &facts);
        CHECK(plan.DamageTarget == onyxia.Guid && !plan.SuppressOffense,
            "the tank has her: everyone burns Onyxia");
    }
    // Her tank dead: the Blood DK picks her up and the damage dealers wait
    // for it; with both tanks dead nobody is left to wait for.
    onyxia.VictimGuid = Bot(10);
    feral.Alive = false;
    NativeFacts facts = StandingFacts(board, 4);
    CHECK(strategy.Propose(board, Bot(4), "dps", &facts).SuppressReason == HoldFireForOnyxiaTank,
        "with the Feral dead the damage dealers wait for the Blood DK");
    NativeFacts dkFacts = StandingFacts(board, 1);
    AdaptiveNefarianPlan const dk = strategy.Propose(board, Bot(1), "tank", &dkFacts);
    CHECK(dk.DamageTarget == onyxia.Guid, "the Blood DK takes Onyxia");
    FindPlayer(board, 1).Alive = false;
    CHECK(strategy.Propose(board, Bot(4), "dps", &facts).DamageTarget == onyxia.Guid,
        "with both tanks dead the damage dealers do not wait");
    (void)duty;
}

// Round 7 review: the pickup keeps its movement until Onyxia targets her
// tank, and stands still in reach so the taunt runs (100 ms decisions; a
// proposed leg claims movement, GCD and cast, as in the kernel).
static int PickupReplay(LocalPoint start, bool nativeBlockedFirst, int& moves, int& decisions)
{
    AdaptiveNefarianStrategy strategy;
    Blackboard board = CanonicalBoard();
    AddDragons(board, false);
    ActorSnapshot& onyxia = board.Summons[0];
    PlaceAt(onyxia, { 0.0f, 0.0f });
    onyxia.InCombat = true;
    onyxia.VictimGuid = Bot(5); // on a healer
    ActorSnapshot& feral = FindPlayer(board, 2);
    PlaceAt(feral, start);
    LocalPoint self = start;
    std::optional<LocalPoint> running;
    std::optional<LocalPoint> blocked;
    moves = 0;
    for (decisions = 1; decisions <= 100; ++decisions)
    {
        NativeFacts facts = StandingFacts(board, 2);
        if (running)
            facts.Motion.push_back({ Bot(2), true, LocalToWorld(*running, FloorLocalZAt(*running),
                PlatformFrame::RaisedOriginZ) });
        if (nativeBlockedFirst && (!blocked || Distance(self, *blocked) < 4.0f))
        {
            if (!blocked)
                blocked = self;
            facts.OutOfSight.push_back(onyxia.Guid);
        }
        AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank", &facts);
        bool const taunt = std::any_of(plan.Actions.begin(), plan.Actions.end(),
            [](BotNativeAction::Candidate const& action) { return action.Id.Mechanic == "onyxia_taunt"; });
        if (plan.Movement && plan.MovementLeg)
        {
            if (!running || Distance(*running, plan.MovementLeg->To) > 0.5f)
                ++moves;
            running = plan.MovementLeg->To;
        }
        else if (taunt && facts.InSight(onyxia.Guid)
            && PillarSightClear(self, { 0.0f, 0.0f }) && Distance(self, { 0.0f, 0.0f }) <= 30.0f)
        {
            onyxia.VictimGuid = Bot(2); // Growl lands
            return decisions;
        }
        if (running)
        {
            self = StepToward(self, *running, 0.7f);
            PlaceAt(feral, self);
            if (Distance(self, *running) < 0.05f)
                running.reset();
        }
    }
    return -1;
}

static void TestPickupArbitration()
{
    int moves = 0;
    int decisions = 0;
    int const inReach = PickupReplay(Polar(DegToRad(30.0f), 27.8f), false, moves, decisions);
    std::printf("PICKUP r27.8 taunt at decision %d moves %d\n", inReach, moves);
    CHECK(inReach == 1 && moves == 0, "in reach and sight: no move, the taunt runs at once");
    int const outside = PickupReplay(Polar(DegToRad(30.0f), 29.0f), false, moves, decisions);
    std::printf("PICKUP r29 taunt at decision %d moves %d\n", outside, moves);
    CHECK(outside > 0 && outside <= 30 && moves == 1, "just outside: one move in, then the taunt");
    int const behind = PickupReplay(WorldToLocal({ -154.781f, -220.952f, 8.10035f }), false, moves,
        decisions);
    std::printf("PICKUP r06 landing taunt at decision %d moves %d\n", behind, moves);
    CHECK(behind > 0 && behind <= 80 && moves <= 8, "from the r06 landing spot: a few legs around the pillar, then the taunt");
    int const recovered = PickupReplay(Polar(DegToRad(30.0f), 26.0f), true, moves, decisions);
    std::printf("PICKUP native blocked taunt at decision %d moves %d\n", recovered, moves);
    CHECK(recovered > 0 && moves >= 1 && moves <= 3,
        "a spot the native line of sight rejects is left for another (bounded)");
}

// Round 7 review: corrections under a yard, a dragon's core, and the pull
// without the Feral.
static void TestRoundSevenReview()
{
    AdaptiveNefarianStrategy strategy;
    int corrections = 0;
    for (bool landed : { false, true })
        for (int deg = 0; deg < 360; deg += 30)
            for (float radius : { 20.0f, 29.0f, 42.0f })
            {
                Blackboard b = CanonicalBoard();
                AddDragons(b, landed);
                PlaceAt(b.Summons[0], Polar(DegToRad(float(deg)), radius));
                for (uint32 member : { 3u, 4u, 5u, 7u, 9u, 10u })
                {
                    NativeFacts f = StandingFacts(b, member);
                    AdaptiveNefarianPlan const plan = strategy.Propose(b, Bot(member), "", &f);
                    if (!plan.MovementSurface || plan.MovementSurface->Sight.empty())
                        continue;
                    LocalPoint const goal = plan.MovementSurface->Local;
                    for (float offset : { 0.3f, 0.6f, 0.9f })
                        for (int bearing = 0; bearing < 360; bearing += 45)
                        {
                            LocalPoint const self = Offset(goal, DegToRad(float(bearing)), offset);
                            if (SpotServes(self, plan.MovementSurface->Sight))
                                continue;
                            Blackboard near = b;
                            PlaceAt(FindPlayer(near, member), self);
                            NativeFacts nf = StandingFacts(near, member);
                            AdaptiveNefarianPlan const held = strategy.Propose(near, Bot(member), "", &nf);
                            if (!held.MovementSurface || Distance(held.MovementSurface->Local, goal) > 0.5f)
                                continue;
                            ++corrections;
                            CHECK(held.Movement && held.MovementLeg,
                                "a correction under a yard is walked when the spot does not serve");
                        }
                }
            }
    std::printf("REVIEW short corrections %d\n", corrections);
    CHECK(corrections > 0, "the short-correction fixture has cases");

    // A non-tank inside a dragon's core (1.5 yd from Nefarian's centre) is
    // never held there: it leaves, whatever the dragon casts.
    Blackboard core = CanonicalBoard();
    AddDragons(core, true);
    LocalPoint const nefarian = WorldToLocal(core.Summons[1].Position);
    LocalPoint const inCore = Offset(nefarian, 0.0f, 1.5f);
    PlaceAt(FindPlayer(core, 4), inCore);
    NativeFacts coreFacts = StandingFacts(core, 4);
    AdaptiveNefarianPlan const leave = strategy.Propose(core, Bot(4), "dps", &coreFacts);
    CHECK(leave.Movement && leave.MovementLeg
        && Distance(leave.MovementLeg->To, nefarian) > Distance(inCore, nefarian),
        "a non-tank in a dragon's core walks out of it");
    CHECK(leave.MovementSurface && Distance(leave.MovementSurface->Local, nefarian)
        >= DragonCoreClearanceYards, "to a spot outside the core");

    // Pre-pull without the Feral: the Blood DK pulls; with no tank alive the
    // damage dealers do.
    for (bool missing : { false, true })
    {
        Blackboard pre = CanonicalBoard();
        AddDragons(pre, false);
        pre.Summons[0].InCombat = false;
        pre.Summons[0].VictimGuid = ObjectGuid();
        if (missing)
            pre.Players.erase(std::remove_if(pre.Players.begin(), pre.Players.end(),
                [](ActorSnapshot const& p) { return p.Guid == Bot(2); }), pre.Players.end());
        else
            FindPlayer(pre, 2).Alive = false;
        NativeFacts dkFacts = StandingFacts(pre, 1);
        AdaptiveNefarianPlan const dk = strategy.Propose(pre, Bot(1), "tank", &dkFacts);
        CHECK(dk.DamageTarget == pre.Summons[0].Guid && !dk.SuppressOffense,
            "the Feral dead or missing: the Blood DK pulls Onyxia");
        NativeFacts dpsFacts = StandingFacts(pre, 4);
        CHECK(strategy.Propose(pre, Bot(4), "dps", &dpsFacts).SuppressReason == HoldFirePreEngage,
            "the damage dealers still wait for the pull");
        FindPlayer(pre, 1).Alive = false;
        CHECK(strategy.Propose(pre, Bot(4), "dps", &dpsFacts).DamageTarget == pre.Summons[0].Guid,
            "no tank alive: the damage dealers do not wait (no deadlock)");
    }
}



// Round 7 delta review: the Blood DK standing in for a dead Feral keeps
// Onyxia until she dies (no Nefarian taunt meanwhile), then is the full
// Nefarian tank through his landing and phase 3.
static void TestDeathKnightFallbackDuty()
{
    AdaptiveNefarianStrategy strategy;
    auto taunts = [](AdaptiveNefarianPlan const& plan, char const* mechanic)
    {
        return std::any_of(plan.Actions.begin(), plan.Actions.end(),
            [mechanic](BotNativeAction::Candidate const& action) { return action.Id.Mechanic == mechanic; });
    };
    // Both dragons alive, Nefarian landed, the Feral dead: the DK holds Onyxia.
    Blackboard both = CanonicalBoard();
    AddDragons(both, true);
    FindPlayer(both, 2).Alive = false;
    both.Summons[0].VictimGuid = Bot(4);
    both.Summons[1].VictimGuid = Bot(6);
    NativeFacts facts = StandingFacts(both, 1);
    AdaptiveNefarianPlan const holding = strategy.Propose(both, Bot(1), "tank", &facts);
    CHECK(holding.DamageTarget == both.Summons[0].Guid, "both alive: the DK fights Onyxia");
    CHECK(taunts(holding, "onyxia_taunt") && !taunts(holding, "nefarian_taunt"),
        "both alive: it taunts Onyxia, not Nefarian");
    CHECK(holding.MovementSurface && holding.MovementSurface->Purpose == MovePurpose::TankLead,
        "both alive: it picks Onyxia up");

    // Onyxia dead (her corpse gone) and Nefarian on the ground (phase 3):
    // the DK is the full Nefarian tank again.
    Blackboard ground = CanonicalBoard();
    AddDragons(ground, true);
    FindPlayer(ground, 2).Alive = false;
    ground.Summons.erase(ground.Summons.begin()); // Onyxia gone
    ActorSnapshot& nefarian = ground.Summons[0];
    nefarian.VictimGuid = Bot(6);
    EncounterView const view = ObserveEncounter(ground);
    std::printf("DKFALLBACK phase %s\n", std::string(PhaseName(view.CurrentPhase)).c_str());
    NativeFacts groundFacts = StandingFacts(ground, 1);
    AdaptiveNefarianPlan const tanking = strategy.Propose(ground, Bot(1), "tank", &groundFacts);
    CHECK(tanking.MovementSurface && tanking.MovementSurface->Purpose == MovePurpose::TankHold,
        "Onyxia gone: the DK takes Nefarian's tank hold");
    CHECK(taunts(tanking, "nefarian_taunt") && !taunts(tanking, "onyxia_taunt"),
        "Onyxia gone: it taunts Nefarian");
}

// Round 7 delta review: the pickup is bounded across decisions. With the
// native line of sight blocked everywhere, and with its legs never admitted,
// the budget runs out, the tank holds with a typed state, and the damage
// dealers start on Onyxia; a moving victim never resets the budget.
static void TestPickupExhaustion()
{
    for (bool legsAdmitted : { true, false })
    {
        AdaptiveNefarianStrategy strategy;
        PickupMemory memory;
        Blackboard board = CanonicalBoard();
        AddDragons(board, false);
        ActorSnapshot& onyxia = board.Summons[0];
        PlaceAt(onyxia, { 0.0f, 0.0f });
        onyxia.InCombat = true;
        ActorSnapshot& feral = FindPlayer(board, 2);
        LocalPoint self = Polar(DegToRad(30.0f), 34.0f);
        PlaceAt(feral, self);
        std::optional<LocalPoint> running;
        int moves = 0;
        int movesAfter = 0;
        int exhaustedAt = -1;
        uint32 const victims[] = { 5u, 7u, 4u, 9u };
        for (int decision = 0; decision < 1000; ++decision)
        {
            board.ObservedAtMs = 1790000000000ull + uint64(decision) * 100;
            onyxia.VictimGuid = Bot(victims[decision % 4]); // a moving victim
            NativeFacts facts = StandingFacts(board, 2);
            facts.OutOfSight.push_back(onyxia.Guid); // the native line of sight always fails
            if (running)
                facts.Motion.push_back({ Bot(2), true, LocalToWorld(*running, FloorLocalZAt(*running),
                    PlatformFrame::RaisedOriginZ) });
            PickupState const state = memory.Observe(Bot(2), onyxia.Guid, true, feral.Position,
                running.has_value(), false, board.ObservedAtMs);
            facts.Pickups.push_back(state);
            AdaptiveNefarianPlan const plan = strategy.Propose(board, Bot(2), "tank", &facts);
            if (state.Exhausted && exhaustedAt < 0)
            {
                exhaustedAt = decision;
                CHECK(HoldReason(plan.MovementHold) == PickupExhaustedHold && !plan.Movement,
                    "exhausted: the tank holds with the typed state");
                NativeFacts dps = StandingFacts(board, 4);
                dps.Pickups.push_back(memory.Find(Bot(2), onyxia.Guid, board.ObservedAtMs));
                CHECK(strategy.Propose(board, Bot(4), "dps", &dps).DamageTarget == onyxia.Guid,
                    "exhausted: the damage dealers start on Onyxia");
            }
            if (plan.Movement && plan.MovementLeg)
            {
                if (!running || Distance(*running, plan.MovementLeg->To) > 0.5f)
                {
                    ++moves;
                    if (exhaustedAt >= 0)
                        ++movesAfter;
                }
                running = plan.MovementLeg->To;
            }
            if (running && legsAdmitted)
            {
                self = StepToward(self, *running, 0.7f);
                PlaceAt(feral, self);
                if (Distance(self, *running) < 0.05f)
                    running.reset();
            }
            else if (!legsAdmitted)
                running.reset();
        }
        std::printf("EXHAUST admitted %d exhausted at decision %d moves %d\n", int(legsAdmitted),
            exhaustedAt, moves);
        CHECK(exhaustedAt >= 0 && exhaustedAt <= int(PickupBudgetMs / 100),
            "the budget runs out within 10 s whatever the victim does");
        CHECK(movesAfter == 0, "exhausted: no further pickup moves");
        CHECK(moves <= (legsAdmitted ? 16 : int(PickupStallDecisions) + 1),
            "a bounded number of pickup moves");
        if (!legsAdmitted)
            CHECK(exhaustedAt <= int(PickupStallDecisions),
                "legs never admitted and no sight: exhausted after about 3 s");
    }
}

// Pillar care: pre-ascent shields and top-ups, then the off-healer on the
// healerless pillar (coordinator default, pending the user).
static void TestPillarCare()
{
    Blackboard ascent = CanonicalBoard();
    AddDragons(ascent, true);
    ascent.Summons[0].Alive = false;
    EncounterView const view = ObserveEncounter(ascent);
    DutyPlan const duty = BuildNefarianDutyPlan(ascent);
    HealDecision const shield = DecidePreAscentCare(ascent, view, duty, FindPlayer(ascent, 7), nullptr);
    CHECK(shield.SpellId == SpellPowerWordShield && duty.PillarOf(shield.Target) == 2,
        "the priest shields the healerless pillar first before the floor sinks");
    Blackboard shielded = ascent;
    for (uint32 slot : { 1u, 9u, 3u })
        AddAura(FindPlayer(shielded, slot), SpellPowerWordShield);
    EncounterView const shieldedView = ObserveEncounter(shielded);
    HealDecision const next = DecidePreAscentCare(shielded, shieldedView, duty,
        FindPlayer(shielded, 7), nullptr);
    CHECK(next.SpellId == SpellPowerWordShield && duty.PillarOf(next.Target) != 2,
        "then everyone else");
    FindPlayer(ascent, 3).HealthPct = 70.0f;
    HealDecision const topUp = DecidePreAscentCare(ascent, view, duty, FindPlayer(ascent, 5), nullptr);
    CHECK(topUp.SpellId == 19750 && topUp.Target == Bot(3), "the Holy paladin tops up the hunter");
    Blackboard lowered = ascent;
    lowered.Interactables = { MakeElevator(PlatformFrame::LoweredOriginZ) };
    EncounterView const loweredView = ObserveEncounter(lowered);
    CHECK(DecidePreAscentCare(lowered, loweredView, duty, FindPlayer(lowered, 7), nullptr)
        .Target.IsEmpty(), "no pre-ascent care once the floor is down");

    Blackboard platform = PlatformBoard(PlatformFrame::LoweredOriginZ);
    EncounterView const platformView = ObserveEncounter(platform);
    FindPlayer(platform, 3).HealthPct = 60.0f;
    FindPlayer(platform, 1).HealthPct = 70.0f;
    HealDecision const heal = DecideOffHeal(platform, platformView, duty, FindPlayer(platform, 9), nullptr);
    CHECK(heal.SpellId == 8004 && heal.Target == Bot(3), "the shaman Healing Surges the lowest teammate");
    CHECK(DecideOffHeal(platform, platformView, duty, FindPlayer(platform, 4), nullptr).Target.IsEmpty(),
        "only the healerless pillar's off-healer off-heals");
    // Range and line of sight: an unreachable Blood DK at 30% never blocks a
    // reachable hunter at 50%.
    Blackboard spread = platform;
    FindPlayer(spread, 1).HealthPct = 30.0f;
    FindPlayer(spread, 3).HealthPct = 50.0f;
    Vector3 far = FindPlayer(spread, 9).Position;
    far.X += 45.0f;
    FindPlayer(spread, 1).Position = far;
    EncounterView const spreadView = ObserveEncounter(spread);
    HealDecision const reachable = DecideOffHeal(spread, spreadView, duty, FindPlayer(spread, 9), nullptr);
    CHECK(reachable.Target == Bot(3), "the out-of-range DK does not block the hunter's heal");
    Blackboard blocked = platform;
    FindPlayer(blocked, 1).HealthPct = 30.0f;
    FindPlayer(blocked, 3).HealthPct = 50.0f;
    EncounterView const blockedView = ObserveEncounter(blocked);
    NativeFacts sight;
    sight.OutOfSight.push_back(Bot(1));
    CHECK(DecideOffHeal(blocked, blockedView, duty, FindPlayer(blocked, 9), &sight).Target == Bot(3),
        "nor does one out of line of sight");
    NativeFacts noSurge;
    noSurge.Readiness.push_back({ Bot(9), 8004, true, false });
    CHECK(DecideOffHeal(platform, platformView, duty, FindPlayer(platform, 9), &noSurge).Target.IsEmpty(),
        "no heal the shaman does not know");

    // Interrupts come first.
    Blackboard casting = platform;
    CastSnapshot nova;
    nova.SpellId = 80734;
    nova.Interruptible = true;
    casting.Summons[3].Cast = nova;
    FindPlayer(casting, 1).Alive = false; // the shaman is the pillar's interrupter now
    AdaptiveNefarianStrategy strategy;
    AdaptiveNefarianPlan const busy = strategy.Propose(casting, Bot(9), "dps");
    CHECK(busy.InterruptTarget == casting.Summons[3].Guid && busy.Actions.size() == 1
        && std::get_if<BotNativeAction::CastSpell>(&busy.Actions[0].Action)->SpellId == 57994,
        "a due Wind Shear comes before any heal");
    AdaptiveNefarianPlan const healing = strategy.Propose(platform, Bot(9), "dps");
    CHECK(std::any_of(healing.Actions.begin(), healing.Actions.end(),
        [](BotNativeAction::Candidate const& action)
        {
            auto const* cast = std::get_if<BotNativeAction::CastSpell>(&action.Action);
            return cast && cast->SpellId == 8004;
        }), "otherwise the shaman heals");
}

// The healerless pillar's survival through phase 2 is modelled with finite
// mana, cast completion, movement windows and a phase length tied to the
// last prototype in tests/test_nefarian_phase_two_survival.py.

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
    TestAscent();
    TestDescent();
    TestWarriorHandler();
    TestRisingFloorReplay();
    TestWarriorHazards();
    TestWarriorEscape();
    TestWarriorTemporal();
    TestCorneredHold();
    TestPlatformHold();
    TestRoundSevenPositions();
    TestOnyxiaPullReplay();
    TestPickupArbitration();
    TestRoundSevenReview();
    TestDeathKnightFallbackDuty();
    TestPickupExhaustion();
    TestPillarCare();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    return failures ? 1 : 0;
}
'''


def test_nefarian_strategy_decisions(tmp_path: Path) -> None:
    _compile_and_run(tmp_path, PROGRAM)


def test_nefarian_strategy_decisions_under_sanitizers(tmp_path: Path) -> None:
    """The same replay under AddressSanitizer (use-after-scope included) and
    UndefinedBehaviorSanitizer: no plan is read after its lifetime."""
    _compile_and_run(tmp_path, PROGRAM, sanitize=True)

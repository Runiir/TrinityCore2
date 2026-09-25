"""Header-only decision tests for the Atramedes (BWD 10N) adaptive strategy.

The C++ program below drives the production headers
(Content/Raids/BlackwingDescent/Encounters/Atramedes/*.h) with synthetic
encounter snapshots of the canonical 10N composition and checks every duty:
gong ownership by capability, Searing Flame / Sound / air-rescue gongs through
the native spellclick, Sonic Breath and Roaring Flame Breath kiting, hazard
exits (beam, disks, bombs, fire, flame), tank anchor drag, the ranged arc and
the air spread ring. Nothing here links the worldserver.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
ATRAMEDES = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes"
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]

PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAdaptiveAtramedesStrategy.h"
#include <cassert>
#include <cmath>
#include <cstdio>
#include <string>
#include <variant>

using namespace BotEncounter;
namespace A = BotEncounter::Atramedes;
namespace G = BotEncounter::Atramedes::Geometry;

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ObjectGuid UnitGuid(uint32 entry, uint32 counter) { return ObjectGuid(HighGuid::Unit, entry, counter); }

static ActorSnapshot MakePlayer(uint32 counter, char const* role, char const* spec, float x, float y)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = spec;
    actor.Position = { x, y, 75.0f };
    actor.Alive = true;
    actor.InCombat = true;
    actor.Health = actor.MaxHealth = 150000;
    actor.HealthPct = 100.0f;
    actor.MaxAlternatePower = 100;
    return actor;
}

static ActorSnapshot MakeUnit(uint32 entry, uint32 counter, float x, float y, ActorKind kind)
{
    ActorSnapshot actor;
    actor.Guid = UnitGuid(entry, counter);
    actor.Entry = entry;
    actor.Kind = kind;
    actor.Position = { x, y, 75.0f };
    actor.Alive = true;
    return actor;
}

enum Slot : uint32
{
    Tank = 11003001, Balance, Hunter, Mage, HolyPaladin, Retribution,
    Discipline, Rogue, Elemental, Warlock
};

static Vector3 OwnerStand()
{
    // Duty shield rank 0: spawn 250130 (181.769, -253.035) is nearest the anchor.
    A::ShieldFact shield{ UnitGuid(42954, 250130), { 181.769f, -253.035f, 76.7294f } };
    return A::ShieldStandPoint(shield);
}

static Blackboard Board()
{
    Blackboard board;
    board.Route.NodeId = "bwd.atramedes.encounter";
    board.ObservedAtMs = 5000;
    board.Revision = 17;
    board.CurrentScope.CohortId = "blackwing_descent_10n_atramedes_c0";
    board.CurrentScope.AttemptId = 3;
    board.CurrentScope.MapId = 669;
    Vector3 const stand = OwnerStand();
    board.Players = {
        MakePlayer(Tank, "tank", "blood_death_knight", 150.0f, -224.5f),
        MakePlayer(Balance, "dps", "balance_druid", 135.0f, -206.0f),
        MakePlayer(Hunter, "dps", "beast_mastery_hunter", stand.X, stand.Y),
        MakePlayer(Mage, "dps", "fire_mage", 131.0f, -229.0f),
        MakePlayer(HolyPaladin, "healer", "holy_paladin", 146.0f, -238.0f),
        MakePlayer(Retribution, "dps", "retribution_paladin", 165.0f, -240.0f),
        MakePlayer(Discipline, "healer", "discipline_priest", 146.0f, -212.0f),
        MakePlayer(Rogue, "dps", "assassination_rogue", 166.0f, -209.0f),
        MakePlayer(Elemental, "dps", "elemental_shaman", 140.0f, -222.0f),
        MakePlayer(Warlock, "dps", "demonology_warlock", 136.0f, -243.0f),
    };
    ActorSnapshot boss = MakeUnit(A::BossEntry, 1, 172.0f, -224.5f, ActorKind::Hostile);
    boss.InCombat = true;
    boss.ReactAggressive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.VictimGuid = PlayerGuid(Tank);
    board.Hostiles.push_back(boss);
    for (A::ShieldSpawn const& spawn : A::ShieldSpawns)
    {
        ActorSnapshot shield = MakeUnit(spawn.Entry, spawn.SpawnId, spawn.X, spawn.Y,
            ActorKind::Interactable);
        shield.Position.Z = spawn.Z;
        shield.Selectable = true;
        shield.Interactable = true;
        board.Interactables.push_back(shield);
    }
    return board;
}

static ActorSnapshot& Member(Blackboard& board, uint32 counter)
{
    for (ActorSnapshot& player : board.Players)
        if (player.Guid == PlayerGuid(counter))
            return player;
    assert(false);
    return board.Players.front();
}

static ActorSnapshot& Boss(Blackboard& board) { return board.Hostiles.front(); }

static AdaptiveAtramedesPlan Plan(Blackboard const& board, uint32 counter, char const* role = "dps")
{
    return AdaptiveAtramedesStrategy().Propose(board, PlayerGuid(counter), role);
}

static BotNativeAction::Move const* MoveOf(AdaptiveAtramedesPlan const& plan)
{
    return plan.Movement ? std::get_if<BotNativeAction::Move>(&plan.Movement->Action) : nullptr;
}

static BotNativeAction::SpellClick const* ClickOf(AdaptiveAtramedesPlan const& plan)
{
    return plan.Interaction ? std::get_if<BotNativeAction::SpellClick>(&plan.Interaction->Action) : nullptr;
}

static std::string Mechanic(AdaptiveAtramedesPlan const& plan)
{
    return plan.Movement ? plan.Movement->Id.Mechanic : std::string();
}

static void AddAura(ActorSnapshot& actor, uint32 spellId, ObjectGuid caster)
{
    AuraSnapshot aura;
    aura.SpellId = spellId;
    aura.CasterGuid = caster;
    actor.Auras.push_back(aura);
}

static void CastOnBoss(Blackboard& board, uint32 spellId)
{
    CastSnapshot cast;
    cast.SpellId = spellId;
    cast.Channeled = true;
    Boss(board).Cast = cast;
}

static uint32 CountClicks(Blackboard const& board)
{
    uint32 clicks = 0;
    for (ActorSnapshot const& player : board.Players)
        if (ClickOf(AdaptiveAtramedesStrategy().Propose(board, player.Guid, player.Role.c_str())))
            ++clicks;
    return clicks;
}

static void TestScopeAndOwnership()
{
    Blackboard board = Board();
    board.Route.NodeId = "bwd.atramedes.regroup";
    assert(!Plan(board, Balance).OwnsNode);
    board = Board();
    board.Hostiles.clear();
    assert(!Plan(board, Balance).OwnsNode);
    board = Board();
    AdaptiveAtramedesPlan plan = Plan(board, Balance);
    assert(plan.OwnsNode);
    assert(plan.DamageTarget == Boss(board).Guid);
    Member(board, Balance).Alive = false;
    assert(!Plan(board, Balance).OwnsNode);
}

static void TestDutiesByCapability()
{
    Blackboard board = Board();
    A::DutyPlan duties = A::BuildDutyPlan(board);
    assert(duties.Applies);
    assert(duties.Tank == PlayerGuid(Tank));
    assert(duties.GongOwner == PlayerGuid(Hunter));
    assert(duties.GongBackup == PlayerGuid(Mage));
    // Ranged arc: healers and ranged dps, never tank, melee or the owner.
    assert(duties.RangedOrder.size() == 6);
    for (ObjectGuid guid : duties.RangedOrder)
        assert(guid != PlayerGuid(Tank) && guid != PlayerGuid(Hunter)
            && guid != PlayerGuid(Retribution) && guid != PlayerGuid(Rogue));
    // A dead owner hands the duty on without a roster slot table.
    Member(board, Hunter).Alive = false;
    duties = A::BuildDutyPlan(board);
    assert(duties.GongOwner == PlayerGuid(Mage));
    assert(duties.GongBackup == PlayerGuid(Elemental));
    assert(A::BuildAtramedesDutyPlanStatusJson(nullptr) == "{\"applies\":false}");
}

static void TestSearingFlameGong()
{
    Blackboard board = Board();
    // Quiet ground phase: the owner holds its shield, nobody strikes.
    assert(CountClicks(board) == 0);
    CastOnBoss(board, A::SearingFlameSpell);
    AdaptiveAtramedesPlan owner = Plan(board, Hunter);
    BotNativeAction::SpellClick const* click = ClickOf(owner);
    assert(click && click->Target == UnitGuid(42954, 250130));
    assert(owner.GongReason == "searing_flame");
    assert(owner.Interaction->Id.Strategy == "adaptive_atramedes");
    assert(owner.Interaction->ExpiresAtMs == board.ObservedAtMs + 750);
    assert(CountClicks(board) == 1);

    // Vertigo already landed: never strike twice.
    AddAura(Boss(board), A::VertigoAura, UnitGuid(42954, 250130));
    assert(CountClicks(board) == 0);

    // Owner away from every shield: it runs back with survival priority.
    board = Board();
    CastOnBoss(board, A::SearingFlameSpell);
    Member(board, Hunter).Position = { 140.0f, -225.0f, 75.0f };
    AdaptiveAtramedesPlan away = Plan(board, Hunter);
    assert(!ClickOf(away));
    assert(Mechanic(away) == "gong_approach");
    assert(away.Movement->ActionPriority == BotActionArbitration::Priority::Survival);

    // The owner tracked by Sonic Breath keeps kiting; the backup strikes.
    board = Board();
    CastOnBoss(board, A::SearingFlameSpell);
    ActorSnapshot flames = MakeUnit(A::TrackingFlamesEntry, 90, 176.0f, -249.0f, ActorKind::Summon);
    board.Summons.push_back(flames);
    AddAura(Member(board, Hunter), A::TrackingAura, flames.Guid);
    Member(board, Mage).Position = { 180.0f, -193.0f, 75.0f };
    assert(!ClickOf(Plan(board, Hunter)));
    AdaptiveAtramedesPlan backup = Plan(board, Mage);
    assert(ClickOf(backup) && ClickOf(backup)->Target == UnitGuid(42956, 250131));
    assert(CountClicks(board) == 1);
}

static void TestSoundGongs()
{
    Blackboard board = Board();
    Member(board, Warlock).AlternatePower = 92;
    assert(Plan(board, Hunter).GongReason == "sound_emergency");
    assert(CountClicks(board) == 1);

    board = Board();
    Member(board, Warlock).AlternatePower = 82;
    MechanicTimerSnapshot timer;
    timer.SpellId = A::SearingFlameSpell;
    timer.RemainingMs = 10000;
    Boss(board).MechanicTimers.push_back(timer);
    // Searing Flame is due soon and its gong resets every bar anyway.
    assert(CountClicks(board) == 0);
    Boss(board).MechanicTimers.front().RemainingMs = 30000;
    assert(Plan(board, Hunter).GongReason == "sound_high");
    assert(CountClicks(board) == 1);

    // No Sound Bar (max 0) reads as silence.
    board = Board();
    Member(board, Warlock).AlternatePower = 95;
    Member(board, Warlock).MaxAlternatePower = 0;
    assert(CountClicks(board) == 0);
}

static void TestSonicBreathKiteAndBeam()
{
    Blackboard board = Board();
    Vector3 const boss = Boss(board).Position;
    // Tracked player south-east of the boss; the raid is to the west.
    Member(board, Balance).Position = { 172.0f, -254.0f, 75.0f };
    ActorSnapshot flames = MakeUnit(A::TrackingFlamesEntry, 91, 171.0f, -251.0f, ActorKind::Summon);
    board.Summons.push_back(flames);
    AddAura(Member(board, Balance), A::TrackingAura, flames.Guid);
    CastOnBoss(board, A::SonicBreathChannelSpell);

    AdaptiveAtramedesPlan kiter = Plan(board, Balance);
    assert(kiter.Duty == "sonic_breath_kiter");
    BotNativeAction::Move const* move = MoveOf(kiter);
    assert(move && move->PreemptCasting);
    assert(Mechanic(kiter) == "sonic_breath_kite");
    Vector3 const to{ move->X, move->Y, move->Z };
    float const radius = G::Distance2d(boss, to);
    assert(radius >= A::GroundKiteMinRadius - 0.1f && radius <= A::GroundKiteMaxRadius + 0.1f);
    // Away from the raid (west): the kite turns east of south, i.e. its x grows.
    assert(to.X > Member(board, Balance).Position.X);

    // A player standing in the beam steps back behind it.
    Member(board, Discipline).Position = { 172.5f, -244.0f, 75.0f };
    AdaptiveAtramedesPlan inBeam = Plan(board, Discipline, "healer");
    assert(Mechanic(inBeam) == "sonic_breath_beam_exit");
    Vector3 const exit{ MoveOf(inBeam)->X, MoveOf(inBeam)->Y, 75.0f };
    float const exitOffset = G::AngleDelta(G::Bearing(boss, exit), G::Bearing(boss, flames.Position));
    // The kiter runs counter-clockwise (east), so behind the beam is clockwise.
    assert(exitOffset < 0.0f);

    // A player far behind the beam and outside the sweep is left alone.
    Member(board, Mage).Position = { 131.0f, -229.0f, 75.0f };
    assert(Mechanic(Plan(board, Mage)).rfind("sonic_breath", 0) != 0);

    // A Tracking aura whose caster is gone never pins a bot into kiting.
    Blackboard stray = Board();
    AddAura(Member(stray, Balance), A::TrackingAura, UnitGuid(A::TrackingFlamesEntry, 99));
    assert(A::BuildFacts(stray).GroundKiter.IsEmpty());
    assert(Plan(stray, Balance).Duty != "sonic_breath_kiter");
}

static void TestSonarPulseLanes()
{
    Blackboard board = Board();
    Vector3 const boss = Boss(board).Position;
    // A disk 6 yd out from the boss heading west, straight at the Elemental.
    Member(board, Elemental).Position = { 140.0f, -224.5f, 75.0f };
    board.Summons.push_back(MakeUnit(A::SonarPulseEntry, 70, 166.0f, -224.5f, ActorKind::Summon));
    AdaptiveAtramedesPlan plan = Plan(board, Elemental);
    assert(Mechanic(plan) == "sonar_pulse_exit");
    Vector3 const exit{ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f };
    G::RayOffset const offset = G::OffsetFromRay({ 166.0f, -224.5f, 75.0f },
        G::Bearing(boss, { 166.0f, -224.5f, 75.0f }), exit);
    assert(offset.Lateral >= A::SonarPulseRadius + A::HazardMargin);

    // Behind the disk (east of it) there is nothing to dodge.
    board = Board();
    board.Summons.push_back(MakeUnit(A::SonarPulseEntry, 71, 150.0f, -224.5f, ActorKind::Summon));
    Member(board, Elemental).Position = { 175.0f, -210.0f, 75.0f };
    assert(Mechanic(Plan(board, Elemental)) != "sonar_pulse_exit");
}

static Blackboard AirBoard()
{
    Blackboard board = Board();
    ActorSnapshot& boss = Boss(board);
    boss.Position = { 130.655f, -226.637f, 113.21f };
    boss.Flying = true;
    boss.ReactAggressive = false;
    boss.VictimGuid = ObjectGuid();
    return board;
}

static void TestAirPhaseTargetsAndSpread()
{
    Blackboard board = AirBoard();
    AdaptiveAtramedesPlan rogue = Plan(board, Rogue);
    assert(rogue.SuppressOffense && rogue.DamageTarget.IsEmpty());
    AdaptiveAtramedesPlan tank = Plan(board, Tank, "tank");
    assert(tank.SuppressOffense);
    AdaptiveAtramedesPlan mage = Plan(board, Mage);
    assert(!mage.SuppressOffense && mage.DamageTarget == Boss(board).Guid);

    A::DutyPlan const duties = A::BuildDutyPlan(board);
    A::Facts const facts = A::BuildFacts(board);
    std::vector<Vector3> slots;
    for (ActorSnapshot const& player : board.Players)
        slots.push_back(*A::AirSlot(facts, duties, player));
    for (std::size_t i = 0; i < slots.size(); ++i)
        for (std::size_t j = i + 1; j < slots.size(); ++j)
            assert(G::Distance2d(slots[i], slots[j]) >= 10.0f);

    // A Sonar Bomb marker on the Warlock sends it out of the 6 yd blast.
    Vector3 const at = Member(board, Warlock).Position;
    board.Summons.push_back(MakeUnit(A::SonarBombMarkerEntry, 50, at.X + 1.0f, at.Y, ActorKind::Summon));
    AdaptiveAtramedesPlan bomb = Plan(board, Warlock);
    assert(Mechanic(bomb) == "sonar_bomb_exit");
    Vector3 const exit{ MoveOf(bomb)->X, MoveOf(bomb)->Y, 75.0f };
    assert(G::Distance2d(exit, { at.X + 1.0f, at.Y, 75.0f }) >= A::SonarBombRadius + 1.5f);

    // Its air slot avoids the marker too.
    A::Facts const marked = A::BuildFacts(board);
    Vector3 const slot = *A::AirSlot(marked, duties, Member(board, Warlock));
    assert(A::FootprintClear(marked, slot));

    // Healers keep slack in the air for native healing movement; ranged
    // damage dealers return to their spread slot.
    Blackboard slack = AirBoard();
    A::DutyPlan const slackDuties = A::BuildDutyPlan(slack);
    A::Facts const slackFacts = A::BuildFacts(slack);
    Vector3 const healerSlot = *A::AirSlot(slackFacts, slackDuties, Member(slack, HolyPaladin));
    Member(slack, HolyPaladin).Position = { healerSlot.X + 8.0f, healerSlot.Y, 75.0f };
    assert(!Plan(slack, HolyPaladin, "healer").Movement);
    Vector3 const mageSlot = *A::AirSlot(slackFacts, slackDuties, Member(slack, Mage));
    Member(slack, Mage).Position = { mageSlot.X + 8.0f, mageSlot.Y, 75.0f };
    assert(Mechanic(Plan(slack, Mage)) == "air_phase_spread");
}

static void TestAirKiteAndRescue()
{
    Blackboard board = AirBoard();
    ActorSnapshot& kiter = Member(board, Mage);
    kiter.Position = { 110.0f, -250.0f, 75.0f };
    ActorSnapshot flame = MakeUnit(A::ReverberatingFlameEntry, 80, 95.0f, -225.0f, ActorKind::Summon);
    board.Summons.push_back(flame);
    AddAura(kiter, A::TrackingAura, flame.Guid);

    AdaptiveAtramedesPlan run = Plan(board, Mage);
    assert(run.Duty == "roaring_flame_breath_kiter");
    assert(Mechanic(run) == "roaring_flame_breath_kite");
    Vector3 const next{ MoveOf(run)->X, MoveOf(run)->Y, 75.0f };
    // The flame is clockwise-behind; the kiter continues counter-clockwise.
    assert(G::AngleDelta(G::Bearing(A::ArenaCenter, next),
        G::Bearing(A::ArenaCenter, kiter.Position)) > 0.0f);

    // Caught near a shield: the kiter strikes it itself.
    board.Summons.back().Position = { 112.0f, -263.0f, 75.0f };
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AdaptiveAtramedesPlan rescue = Plan(board, Mage);
    assert(rescue.GongReason == "air_breath_rescue");
    assert(ClickOf(rescue) && ClickOf(rescue)->Target == UnitGuid(42956, 250122));
    assert(CountClicks(board) == 1);

    // Caught away from every shield: a bot already beside one strikes the
    // shield farthest from the flame; the kiter keeps running.
    Member(board, Mage).Position = { 120.0f, -240.0f, 75.0f };
    board.Summons.back().Position = { 118.0f, -236.0f, 75.0f };
    Member(board, Warlock).Position = { 180.0f, -197.0f, 75.0f };
    assert(!ClickOf(Plan(board, Mage)));
    AdaptiveAtramedesPlan relay = Plan(board, Warlock);
    assert(ClickOf(relay) && ClickOf(relay)->Target == UnitGuid(42956, 250131));
    assert(CountClicks(board) == 1);

    // Other players keep clear of the flame.
    Member(board, Elemental).Position = { 121.0f, -233.0f, 75.0f };
    assert(Mechanic(Plan(board, Elemental)) == "reverberating_flame_exit");
}

static void TestFireTankAndArc()
{
    Blackboard board = Board();
    Vector3 const at = Member(board, Discipline).Position;
    board.Summons.push_back(MakeUnit(A::SearingFlamePatchEntry, 60, at.X + 1.0f, at.Y, ActorKind::Summon));
    assert(Mechanic(Plan(board, Discipline, "healer")) == "roaring_flame_exit");

    // Just landed west of centre: the tank drags past the anchor.
    board = Board();
    Boss(board).Position = { 124.575f, -224.797f, 75.45f };
    AdaptiveAtramedesPlan tank = Plan(board, Tank, "tank");
    assert(Mechanic(tank) == "tank_anchor_drag");
    Vector3 const drag{ MoveOf(tank)->X, MoveOf(tank)->Y, 75.0f };
    assert(drag.X > A::TankAnchor.X);
    // Not the victim: no drag.
    Boss(board).VictimGuid = PlayerGuid(Rogue);
    assert(Mechanic(Plan(board, Tank, "tank")) != "tank_anchor_drag");

    // A ranged bot far from its arc slot walks back at mechanic priority.
    board = Board();
    Member(board, Balance).Position = { 200.0f, -180.0f, 75.0f };
    AdaptiveAtramedesPlan arc = Plan(board, Balance);
    assert(Mechanic(arc) == "ranged_arc");
    assert(arc.Movement->ActionPriority == BotActionArbitration::Priority::Mechanic);
    assert(!MoveOf(arc)->PreemptCasting);
    // Melee keep native melee positioning on the ground.
    assert(!Plan(board, Rogue).Movement);
}

static void TestPurity()
{
    Blackboard board = Board();
    CastOnBoss(board, A::SearingFlameSpell);
    Member(board, Elemental).AlternatePower = 50;
    AdaptiveAtramedesPlan first = Plan(board, Hunter);
    AdaptiveAtramedesPlan second = Plan(board, Hunter);
    assert(ClickOf(first) && ClickOf(second) && ClickOf(first)->Target == ClickOf(second)->Target);
    assert(first.Interaction->Id.EventGeneration == board.Revision);
    assert(first.Interaction->Id.ScopeKey == board.CurrentScope.Key());
}

int main()
{
    TestScopeAndOwnership();
    TestDutiesByCapability();
    TestSearingFlameGong();
    TestSoundGongs();
    TestSonicBreathKiteAndBeam();
    TestSonarPulseLanes();
    TestAirPhaseTargetsAndSpread();
    TestAirKiteAndRescue();
    TestFireTankAndArc();
    TestPurity();
    std::puts("atramedes strategy ok");
    return 0;
}
'''


def test_atramedes_strategy_decisions(tmp_path: Path) -> None:
    source = tmp_path / "atramedes_strategy.cpp"
    binary = tmp_path / "atramedes_strategy"
    source.write_text(PROGRAM, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O0",
                    *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
    assert "atramedes strategy ok" in result.stdout


def test_atramedes_headers_stay_bounded_and_header_only() -> None:
    headers = sorted(ATRAMEDES.glob("*"))
    assert headers, "Atramedes content directory is empty"
    for path in headers:
        assert path.suffix == ".h", f"{path.name}: the strategy stays header-only"
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000
    # The content layout test allows exactly one BotAdaptive*Strategy.h per boss.
    assert [p.name for p in ATRAMEDES.glob("BotAdaptive*Strategy.h")] == [
        "BotAdaptiveAtramedesStrategy.h"]


def test_strategy_keeps_the_dispatch_contract() -> None:
    header = (ATRAMEDES / "BotAdaptiveAtramedesStrategy.h").read_text(encoding="utf-8")
    for field in ("bool OwnsNode", "ObjectGuid DamageTarget",
                  "std::optional<BotNativeAction::Candidate> Movement",
                  "std::optional<BotNativeAction::Candidate> Interaction"):
        assert field in header
    assert "AdaptiveAtramedesPlan Propose(Blackboard const& board, ObjectGuid botGuid," in header
    dispatch = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp").read_text(
        encoding="utf-8")
    assert "atramedesStrategy.Propose(*Cohort().EncounterSnapshot," in dispatch
    # Shield strikes use the native spellclick intent only.
    gong = (ATRAMEDES / "BotAdaptiveAtramedesStrategy.h").read_text(encoding="utf-8")
    assert "BotNativeAction::SpellClick{ gong.Shield->Guid }" in gong
    for forbidden in ("Teleport", "NearTeleportTo", "AddAura(", "SetPower(", "CastSpell("):
        for path in ATRAMEDES.glob("*.h"):
            assert forbidden not in path.read_text(encoding="utf-8"), (path.name, forbidden)

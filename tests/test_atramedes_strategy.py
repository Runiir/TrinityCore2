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
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstdio>
#include <map>
#include <optional>
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
    boss.Health = boss.MaxHealth = 26111168;
    boss.HealthPct = 100.0f;
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

static void AddTimer(ActorSnapshot& boss, uint32 spellId, uint32 remainingMs)
{
    MechanicTimerSnapshot timer;
    timer.SpellId = spellId;
    timer.RemainingMs = remainingMs;
    boss.MechanicTimers.push_back(timer);
}

// Keeps the last `count` shield spawns (250131, 250130, ... backwards), so
// the gong owner's duty shield (250130) survives down to two.
static void KeepShields(Blackboard& board, std::size_t count)
{
    std::size_t const size = board.Interactables.size();
    if (count < size)
        board.Interactables.erase(board.Interactables.begin(),
            board.Interactables.begin() + std::ptrdiff_t(size - count));
}

// Moves `position` up to `step` yards toward `target` (the native movement
// of one decision interval).
static void Advance(Vector3& position, Vector3 const& target, float step)
{
    float const dx = target.X - position.X;
    float const dy = target.Y - position.Y;
    float const length = std::sqrt(dx * dx + dy * dy);
    if (length <= step)
    {
        position.X = target.X;
        position.Y = target.Y;
        return;
    }
    position.X += dx / length * step;
    position.Y += dy / length * step;
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
    AddAura(Boss(board), A::VertigoAuras.front(), UnitGuid(42954, 250130));
    assert(CountClicks(board) == 0);

    // Owner away from every shield: it runs back with survival priority.
    board = Board();
    CastOnBoss(board, A::SearingFlameSpell);
    Member(board, Hunter).Position = { 140.0f, -225.0f, 75.0f };
    AdaptiveAtramedesPlan away = Plan(board, Hunter);
    assert(!ClickOf(away));
    assert(Mechanic(away) == "gong_approach");
    assert(away.Movement->ActionPriority == BotActionArbitration::Priority::Survival);

    // The owner tracked by an active Sonic Breath keeps kiting; the backup
    // strikes a Sound emergency.
    board = Board();
    CastOnBoss(board, A::SonicBreathChannelSpells.front());
    ActorSnapshot flames = MakeUnit(A::TrackingFlamesEntry, 90, 176.0f, -249.0f, ActorKind::Summon);
    board.Summons.push_back(flames);
    AddAura(Member(board, Hunter), A::TrackingAura, flames.Guid);
    Member(board, Warlock).AlternatePower = 94;
    Member(board, Mage).Position = { 180.0f, -193.0f, 75.0f };
    assert(!ClickOf(Plan(board, Hunter)));
    AdaptiveAtramedesPlan backup = Plan(board, Mage);
    assert(ClickOf(backup) && ClickOf(backup)->Target == UnitGuid(42956, 250131));
    assert(CountClicks(board) == 1);
    // Once the breath is over the Tracking Flames lingers (10 s), but the
    // owner is on gong duty again.
    Boss(board).Cast.reset();
    assert(A::GroundGonger(board, A::BuildFacts(board), A::BuildDutyPlan(board))
        == PlayerGuid(Hunter));
}

static void TestSoundGongs()
{
    Blackboard board = Board();
    Member(board, Warlock).AlternatePower = 92;
    assert(Plan(board, Hunter).GongReason == "sound_emergency");
    assert(CountClicks(board) == 1);

    // Shield budget. On the ground at full health without published timers
    // two shields stay in reserve: this phase's Searing Flame (unknown counts
    // as pending) and the next ground phase's.
    A::ShieldReserve const reserve = A::SearingFlameReserve(A::BuildFacts(board));
    assert(reserve.CurrentPhase == 1 && reserve.NextPhase == 1 && reserve.Total() == 2);
    // A 90-Sound emergency may spend the next ground phase's shield: only
    // this phase's Searing Flame outranks a Devastation death.
    KeepShields(board, 2);
    assert(Plan(board, Hunter).GongReason == "sound_emergency");
    assert(CountClicks(board) == 1);
    KeepShields(board, 1);
    assert(CountClicks(board) == 0);
    assert(Plan(board, Hunter).GongReason == "sound_emergency_at_reserve");
    // Searing Flame may take the last shield (250131): the owner runs to it.
    CastOnBoss(board, A::SearingFlameSpell);
    AdaptiveAtramedesPlan last = Plan(board, Hunter);
    assert(last.GongReason == "searing_flame" && Mechanic(last) == "gong_approach");
    // Published timers without a Searing Flame timer: this phase's is spent.
    board = Board();
    AddTimer(Boss(board), A::TakeOffSpell, 40000);
    assert(A::SearingFlameReserve(A::BuildFacts(board)).Total() == 1);
    Boss(board).HealthPct = 45.0f;
    assert(A::SearingFlameReserve(A::BuildFacts(board)).Total() == 0);
    AddTimer(Boss(board), A::SearingFlameSpell, 20000);
    assert(A::SearingFlameReserve(A::BuildFacts(board)).Total() == 1);

    board = Board();
    Member(board, Warlock).AlternatePower = 82;
    AddTimer(Boss(board), A::TakeOffSpell, 60000);
    AddTimer(Boss(board), A::SearingFlameSpell, 10000);
    // Searing Flame is due soon and its gong resets every bar anyway.
    assert(CountClicks(board) == 0);
    Boss(board).MechanicTimers.back().RemainingMs = 30000;
    assert(Plan(board, Hunter).GongReason == "sound_high");
    assert(CountClicks(board) == 1);
    // An elective gong keeps one spare above the reserve (2 here).
    KeepShields(board, 3);
    assert(CountClicks(board) == 0);
    assert(Plan(board, Hunter).GongReason == "sound_high_at_reserve");
    Member(board, Warlock).AlternatePower = 91;
    assert(Plan(board, Hunter).GongReason == "sound_emergency");
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
    CastOnBoss(board, A::SonicBreathChannelSpells.front());

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
    Vector3 const elementalSlot = *A::AirSlot(slackFacts, slackDuties, Member(slack, Elemental));
    Member(slack, Elemental).Position = { elementalSlot.X + 8.0f, elementalSlot.Y, 75.0f };
    assert(Mechanic(Plan(slack, Elemental)) == "air_phase_spread");

    // The gong owner and backup wait at relay shields on opposite rows
    // (north row, south row) instead of the spread ring.
    A::DutyPlan const relayDuties = A::BuildDutyPlan(slack);
    assert(relayDuties.GongOwner == PlayerGuid(Hunter) && relayDuties.GongBackup == PlayerGuid(Mage));
    std::optional<A::ShieldFact> const north = A::AirRelayShield(slackFacts, 0);
    std::optional<A::ShieldFact> const south = A::AirRelayShield(slackFacts, 1);
    assert(north && south && north->Position.Y > A::ArenaCenter.Y && south->Position.Y < A::ArenaCenter.Y);
    AdaptiveAtramedesPlan owner = Plan(slack, Hunter);
    assert(Mechanic(owner) == "air_relay_station");
    Vector3 const station{ MoveOf(owner)->X, MoveOf(owner)->Y, 75.0f };
    assert(G::Distance3d(station, north->Position) <= A::ShieldClickDistance);
}

static ActorSnapshot& AddFlame(Blackboard& board, ActorSnapshot& kiter, Vector3 at,
    uint8 stacks)
{
    ActorSnapshot flame = MakeUnit(A::ReverberatingFlameEntry, 80, at.X, at.Y, ActorKind::Summon);
    CastSnapshot channel;
    channel.SpellId = A::TrackingAura;
    channel.TargetGuid = kiter.Guid;
    channel.Channeled = true;
    flame.Cast = channel;
    if (stacks)
    {
        AuraSnapshot speed;
        speed.SpellId = 78218;
        speed.CasterGuid = flame.Guid;
        speed.Stacks = stacks;
        flame.Auras.push_back(speed);
    }
    AddAura(kiter, A::TrackingAura, flame.Guid);
    board.Summons.push_back(flame);
    return board.Summons.back();
}

static void TestAirKiteAndRescue()
{
    Blackboard board = AirBoard();
    ActorSnapshot& kiter = Member(board, Mage);
    kiter.Position = { 110.0f, -250.0f, 75.0f };
    AddFlame(board, kiter, { 95.0f, -225.0f, 75.0f }, 0);

    AdaptiveAtramedesPlan run = Plan(board, Mage);
    assert(run.Duty == "roaring_flame_breath_kiter");
    assert(Mechanic(run) == "roaring_flame_breath_kite");
    Vector3 const next{ MoveOf(run)->X, MoveOf(run)->Y, 75.0f };
    // The flame is clockwise-behind; the kiter continues counter-clockwise.
    assert(G::AngleDelta(G::Bearing(A::ArenaCenter, next),
        G::Bearing(A::ArenaCenter, Member(board, Mage).Position)) > 0.0f);

    // The flame is summoned within 4 yd of its target. A target that gets
    // out of the 5 yd breath before the flame outpaces it (spawned 4.5 yd
    // away) is caught again later: no shield now. One spawned 3 yd away never
    // gets out (peak separation 3 + 2^2/2 = 5 yd): contact now.
    board = AirBoard();
    Member(board, Hunter).Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    ActorSnapshot& spawned = AddFlame(board, Member(board, Mage), { 105.5f, -271.0f, 75.0f }, 0);
    float const later = A::FlameTimeToContact(spawned, Member(board, Mage));
    assert(later > 3.5f && later < 4.0f);
    assert(CountClicks(board) == 0);
    board.Summons.back().Position = { 107.0f, -271.0f, 75.0f };
    assert(A::FlameTimeToContact(board.Summons.back(), Member(board, Mage)) == 0.0f);
    assert(Plan(board, Mage).GongReason == "air_breath_rescue");
    assert(CountClicks(board) == 1);

    // Accelerated (6 stacks, 11 yd/s) and 9 yd behind: contact within 1 s.
    // With nobody else beside a shield (the gong owner has left its stand
    // for its air slot), the kiter strikes the shield beside it, which lies
    // ahead of it.
    board = AirBoard();
    Member(board, Hunter).Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    ActorSnapshot& fast = AddFlame(board, Member(board, Mage), { 104.5f, -263.8f, 75.0f }, 6);
    assert(A::FlameTimeToContact(fast, Member(board, Mage)) < A::RescueLeadSeconds);
    assert(A::AirKiteDirection(A::BuildFacts(board), Member(board, Mage)) == 1);
    AdaptiveAtramedesPlan rescue = Plan(board, Mage);
    assert(rescue.GongReason == "air_breath_rescue");
    assert(ClickOf(rescue) && ClickOf(rescue)->Target == UnitGuid(42956, 250122));
    assert(CountClicks(board) == 1);
    // Farther from contact (15.6 yd, 4 stacks: 3.0 s), but the next shield
    // ahead (250125) is 3.2 s away: strike now rather than be caught between.
    board.Summons.back().Position = { 100.0f, -259.0f, 75.0f };
    board.Summons.back().Auras.back().Stacks = 4;
    A::Facts const early = A::BuildFacts(board);
    float const earlyContact = A::FlameTimeToContact(board.Summons.back(), Member(board, Mage));
    assert(earlyContact > A::RescueLeadSeconds);
    assert(earlyContact < A::SecondsToNextShield(early, Member(board, Mage), early.Shields.front(), 1)
        + A::RescueLeadSeconds);
    assert(ClickOf(Plan(board, Mage)) && CountClicks(board) == 1);
    // Slower (2 stacks: 4.6 s): the next shield is reachable, keep kiting.
    board.Summons.back().Auras.back().Stacks = 2;
    assert(CountClicks(board) == 0);
    assert(Mechanic(Plan(board, Mage)) == "roaring_flame_breath_kite");

    // A relay striker beside a shield far from the flame beats the kiter's
    // own shield: the flame's detour is longer.
    board = AirBoard();
    Member(board, Hunter).Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Mage), { 104.5f, -263.8f, 75.0f }, 6);
    Member(board, Warlock).Position = { 180.0f, -197.0f, 75.0f };
    assert(!ClickOf(Plan(board, Mage)));
    AdaptiveAtramedesPlan relay = Plan(board, Warlock);
    assert(ClickOf(relay) && ClickOf(relay)->Target == UnitGuid(42956, 250131));
    assert(CountClicks(board) == 1);

    // Budget: in the air at full health one shield stays for the next ground
    // phase's Searing Flame, so the last shield is never spent on a rescue.
    KeepShields(board, 1);
    assert(A::SearingFlameReserve(A::BuildFacts(board)).Total() == 1);
    assert(CountClicks(board) == 0);
    assert(Plan(board, Mage).GongReason == "air_breath_rescue_at_reserve");
    Boss(board).HealthPct = 25.0f;
    assert(A::SearingFlameReserve(A::BuildFacts(board)).Total() == 0);

    // A shield behind the kiter (toward the flame) is never its rescue: with
    // no other strike in reach it runs for the nearest shield ahead.
    board = AirBoard();
    Boss(board).HealthPct = 25.0f;
    KeepShields(board, 0);
    auto addShield = [&board](uint32 spawn, float bearingDeg)
    {
        Vector3 const at = G::PointAt(A::ArenaCenter, bearingDeg * G::Pi / 180.0f, 20.0f, 75.0f);
        ActorSnapshot shield = MakeUnit(42956, spawn, at.X, at.Y, ActorKind::Interactable);
        shield.Selectable = true;
        shield.Interactable = true;
        board.Interactables.push_back(shield);
    };
    addShield(250198, 90.0f);   // 25 degrees behind the kiter, in reach
    addShield(250199, 150.0f);  // 35 degrees ahead, out of reach
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    // Kiter 25 degrees counter-clockwise past the first shield (radius 20).
    Vector3 const past = G::PointAt(A::ArenaCenter, 115.0f * G::Pi / 180.0f, 20.0f, 75.0f);
    Member(board, Mage).Position = past;
    // Flame 6.9 yd behind (20 degrees), 11 yd/s: contact within 1 s.
    Vector3 const chaser = G::PointAt(A::ArenaCenter, 95.0f * G::Pi / 180.0f, 20.0f, 75.0f);
    AddFlame(board, Member(board, Mage), chaser, 6);
    A::Facts const facts = A::BuildFacts(board);
    assert(!A::ShieldAhead(facts.Shields.front(), Member(board, Mage),
        A::AirKiteDirection(facts, Member(board, Mage))));
    AdaptiveAtramedesPlan approach = Plan(board, Mage);
    assert(approach.GongReason == "air_breath_rescue");
    assert(!ClickOf(approach) && Mechanic(approach) == "gong_approach");
    assert(approach.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
    Vector3 const toward{ MoveOf(approach)->X, MoveOf(approach)->Y, 75.0f };
    assert(G::Distance2d(toward, facts.Shields.back().Position) <= A::ShieldStandInset + 0.01f);
    assert(CountClicks(board) == 0);
    // Once the flame is on top of the kiter, "behind" means nothing (a faster
    // flame's predictive follow overshoots): the shield in reach is struck.
    board.Summons.back().Position = G::PointAt(A::ArenaCenter, 112.0f * G::Pi / 180.0f, 20.0f, 75.0f);
    AdaptiveAtramedesPlan onTop = Plan(board, Mage);
    assert(ClickOf(onTop) && ClickOf(onTop)->Target == UnitGuid(42956, 250198));

    // The tank is a legal air target (Atramedes has no victim in the air): as
    // the kiter it strikes like anyone else.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Tank).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Tank), { 104.5f, -263.8f, 75.0f }, 6);
    AdaptiveAtramedesPlan tankRescue = Plan(board, Tank, "tank");
    assert(tankRescue.Duty == "roaring_flame_breath_kiter");
    assert(ClickOf(tankRescue) && ClickOf(tankRescue)->Target == UnitGuid(42956, 250122));
    assert(CountClicks(board) == 1);

    // A 90-Sound emergency still gongs while the rescue budget is spent:
    // contact is true, the last shield is the next phase's, and the Warlock
    // would die to Devastation.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    KeepShields(board, 1);
    Member(board, Mage).Position = { 177.0f, -193.0f, 75.0f };
    AddFlame(board, Member(board, Mage), { 172.0f, -186.0f, 75.0f }, 6);
    Member(board, Warlock).AlternatePower = 93;
    assert(A::SearingFlameReserve(A::BuildFacts(board)).Total() == 1);
    AdaptiveAtramedesPlan loud = Plan(board, Mage);
    assert(loud.GongReason == "sound_emergency");
    assert(ClickOf(loud) && ClickOf(loud)->Target == UnitGuid(42956, 250131));

    // During a redirect the flame is interrupted: no Tracking channel and no
    // Tracking aura, so nobody is the kiter and no second shield is spent.
    board = AirBoard();
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    ActorSnapshot& waiting = AddFlame(board, Member(board, Mage), { 108.0f, -270.0f, 75.0f }, 8);
    waiting.Cast.reset();
    Member(board, Mage).Auras.clear();
    assert(A::BuildFacts(board).AirKiter.IsEmpty());
    assert(CountClicks(board) == 0);

    // Other players keep clear of the flame.
    board = AirBoard();
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Mage), { 118.0f, -236.0f, 75.0f }, 0);
    Member(board, Elemental).Position = { 121.0f, -233.0f, 75.0f };
    assert(Mechanic(Plan(board, Elemental)) == "reverberating_flame_exit");
}

// Kites an air breath for `seconds` at 0.25 s steps: the kiter runs at
// 7 yd/s, the flame follows at 5 yd/s. The kiter's bearing around the arena
// centre must keep one direction.
static void TestAirKiteKeepsDirection()
{
    Blackboard board = AirBoard();
    Member(board, Mage).Position = { 110.0f, -250.0f, 75.0f };
    AddFlame(board, Member(board, Mage), { 108.0f, -247.0f, 75.0f }, 0);
    float previous = G::Bearing(A::ArenaCenter, Member(board, Mage).Position);
    int direction = 0;
    for (int step = 1; step <= 24; ++step)
    {
        ++board.Revision;
        AdaptiveAtramedesPlan plan = Plan(board, Mage);
        assert(Mechanic(plan) == "roaring_flame_breath_kite");
        Advance(Member(board, Mage).Position, { MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f }, 1.75f);
        Advance(board.Summons.back().Position, Member(board, Mage).Position, 1.25f);
        float const bearing = G::Bearing(A::ArenaCenter, Member(board, Mage).Position);
        float const delta = G::AngleDelta(bearing, previous);
        int const sign = delta > 0.0f ? 1 : -1;
        if (!direction)
            direction = sign;
        assert(sign == direction && std::fabs(delta) > 0.0f);
        previous = bearing;
    }
}

// Native-follow replay of one air phase. Every bot follows its own plan at
// 7 yd/s (0.25 s decision steps); spellclicks execute the native effects
// (shield used, 78168 on the striker, every Sound bar to 0, the flame
// interrupted: 2 s wait, flight to the struck shield, Building Speed reset,
// then Tracking on the striker). The flame relaunches a predictive follow
// every 400 ms at 5 yd/s + 1 per Building Speed stack (one a second up to
// `stackCap`) and its 5 yd breath ticks every 0.5 s (+3 Sound).
struct AirReplay
{
    float FirstContactS = -1.0f;
    float FirstStrikeS = -1.0f;
    float WorstStrikeDelayS = 0.0f;
    int Strikes = 0;
    int MaxConsecutiveKiterTicks = 0;
    int KiterTicks = 0;
    int OtherTicks = 0;
    uint32 MaxSound = 0;
    bool DoubleClick = false;
};

static void MoveBots(Blackboard& board, std::map<ObjectGuid, Vector3> const& destinations)
{
    for (ActorSnapshot& player : board.Players)
    {
        auto itr = destinations.find(player.Guid);
        if (player.Alive && itr != destinations.end())
            Advance(player.Position, itr->second, 1.75f);
    }
}

static AirReplay ReplayAirPhase(uint32 targetSlot, float stackCap, bool solo = false,
    float seconds = 31.0f)
{
    Blackboard board = AirBoard();
    // Solo: everyone else is dead, so no relay exists and the target must
    // reach a shield on its own.
    if (solo)
        for (ActorSnapshot& player : board.Players)
            if (player.Guid != PlayerGuid(targetSlot))
                player.Alive = false;
    // Settle the air formation (relay stations, spread ring) before the breath.
    for (int step = 0; step < 40; ++step)
    {
        std::map<ObjectGuid, Vector3> destinations;
        for (ActorSnapshot const& player : board.Players)
            if (BotNativeAction::Move const* move = MoveOf(AdaptiveAtramedesStrategy().Propose(
                    board, player.Guid, player.Role.c_str())))
                destinations[player.Guid] = { move->X, move->Y, 75.0f };
        MoveBots(board, destinations);
    }
    ActorSnapshot& target = Member(board, targetSlot);
    Vector3 const spawn = G::PointAt(target.Position, G::Bearing(target.Position, A::ArenaCenter),
        3.0f, 75.0f);
    AddFlame(board, target, spawn, 0);
    board.Summons.back().Auras.push_back({ 78218, board.Summons.back().Guid, 0, 0 });
    ObjectGuid const flameGuid = board.Summons.back().Guid;
    auto flame = [&board, flameGuid]() -> ActorSnapshot&
    {
        for (ActorSnapshot& actor : board.Summons)
            if (actor.Guid == flameGuid)
                return actor;
        assert(false);
        return board.Summons.front();
    };
    ObjectGuid tracked = target.Guid;
    ObjectGuid nextTarget;
    Vector3 shieldPos;
    bool toShield = false;
    float waitUntil = -1.0f;
    float stacks = 0.0f;
    float nextRelaunch = 0.0f;
    float nextTick = 0.5f;
    Vector3 aim = flame().Position;
    std::map<ObjectGuid, Vector3> previous;
    std::map<ObjectGuid, float> clashUntil;
    float contactOpen = -1.0f;
    int consecutive = 0;
    AirReplay result;
    for (float t = 0.25f; t <= seconds + 0.001f; t += 0.25f)
    {
        ++board.Revision;
        board.ObservedAtMs += 250;
        for (ActorSnapshot& player : board.Players)
            previous[player.Guid] = player.Position;
        A::Facts const facts = A::BuildFacts(board);
        if (ActorSnapshot const* kiter = A::FindLivingPlayer(board, facts.AirKiter))
            if (ActorSnapshot const* marker = A::MarkerOf(facts.ReverberatingFlames, *kiter))
                if (A::FlameTimeToContact(*marker, *kiter) <= A::RescueLeadSeconds)
                {
                    if (contactOpen < 0.0f)
                        contactOpen = t;
                    if (result.FirstContactS < 0.0f)
                        result.FirstContactS = t;
                }
        std::map<ObjectGuid, Vector3> destinations;
        ObjectGuid clicker;
        ObjectGuid clicked;
        for (ActorSnapshot const& player : board.Players)
        {
            if (!player.Alive)
                continue;
            AdaptiveAtramedesPlan plan = AdaptiveAtramedesStrategy().Propose(
                board, player.Guid, player.Role.c_str());
            if (BotNativeAction::SpellClick const* click = ClickOf(plan))
            {
                if (!clicker.IsEmpty())
                    result.DoubleClick = true;
                else
                {
                    clicker = player.Guid;
                    clicked = click->Target;
                }
            }
            else if (BotNativeAction::Move const* move = MoveOf(plan))
                destinations[player.Guid] = { move->X, move->Y, 75.0f };
        }
        if (!clicker.IsEmpty())
        {
            auto shield = std::find_if(board.Interactables.begin(), board.Interactables.end(),
                [clicked](ActorSnapshot const& actor) { return actor.Guid == clicked; });
            assert(shield != board.Interactables.end());
            shieldPos = shield->Position;
            board.Interactables.erase(shield);
            for (ActorSnapshot& player : board.Players)
            {
                player.AlternatePower = 0;
                player.Auras.erase(std::remove_if(player.Auras.begin(), player.Auras.end(),
                    [](AuraSnapshot const& aura) { return aura.SpellId == A::TrackingAura; }),
                    player.Auras.end());
            }
            AddAura(Member(board, clicker.GetCounter()), A::AirClashAura, clicked);
            clashUntil[clicker] = t + 15.0f;
            flame().Cast.reset();
            tracked.Clear();
            nextTarget = clicker;
            toShield = true;
            waitUntil = t + 2.0f;
            ++result.Strikes;
            if (result.FirstStrikeS < 0.0f)
                result.FirstStrikeS = t;
            if (contactOpen >= 0.0f)
                result.WorstStrikeDelayS = std::max(result.WorstStrikeDelayS, t - contactOpen);
            contactOpen = -1.0f;
        }
        MoveBots(board, destinations);
        for (auto& [guid, until] : clashUntil)
            if (until <= t)
                for (ActorSnapshot& player : board.Players)
                    if (player.Guid == guid)
                        player.Auras.erase(std::remove_if(player.Auras.begin(), player.Auras.end(),
                            [](AuraSnapshot const& aura) { return aura.SpellId == A::AirClashAura; }),
                            player.Auras.end());

        // Flame movement.
        float const speed = 5.0f + std::floor(stacks);
        if (toShield && t >= waitUntil)
        {
            Advance(flame().Position, shieldPos, speed * 0.25f);
            if (G::Distance2d(flame().Position, shieldPos) <= 0.5f)
            {
                toShield = false;
                stacks = 0.0f;
                tracked = nextTarget;
                ActorSnapshot& next = Member(board, tracked.GetCounter());
                CastSnapshot channel;
                channel.SpellId = A::TrackingAura;
                channel.TargetGuid = tracked;
                channel.Channeled = true;
                flame().Cast = channel;
                AddAura(next, A::TrackingAura, flameGuid);
                aim = next.Position;
                nextRelaunch = t;
            }
        }
        else if (!tracked.IsEmpty())
        {
            ActorSnapshot& chased = Member(board, tracked.GetCounter());
            if (t >= nextRelaunch)
            {
                Vector3 const before = previous[tracked];
                aim = { chased.Position.X + (chased.Position.X - before.X) / 0.25f * 0.4f,
                    chased.Position.Y + (chased.Position.Y - before.Y) / 0.25f * 0.4f, 75.0f };
                nextRelaunch = t + 0.4f;
            }
            Advance(flame().Position, aim, speed * 0.25f);
        }
        stacks = std::min(stackCap, stacks + 0.25f);
        flame().Auras.back().Stacks = uint8(std::floor(stacks));

        // Breath ticks.
        if (t + 0.001f >= nextTick)
        {
            nextTick += 0.5f;
            bool kiterHit = false;
            for (ActorSnapshot& player : board.Players)
            {
                if (!player.Alive || G::Distance2d(player.Position, flame().Position) > A::FlameBreathRadius)
                    continue;
                player.AlternatePower = std::min<uint32>(100, player.AlternatePower + 3);
                if (player.Guid == tracked)
                {
                    kiterHit = true;
                    ++result.KiterTicks;
                }
                else
                    ++result.OtherTicks;
            }
            consecutive = kiterHit ? consecutive + 1 : 0;
            result.MaxConsecutiveKiterTicks = std::max(result.MaxConsecutiveKiterTicks, consecutive);
        }
        for (ActorSnapshot const& player : board.Players)
            result.MaxSound = std::max(result.MaxSound, player.AlternatePower);
    }
    return result;
}

// Every target of a 31 s air phase, the tank included, with the server's
// Building Speed cap (10) and an uncapped 99-stack stress: every catch is
// struck within 3 s of contact, the kiter is never in the breath for more
// than 2 s at a time, nobody nears 90 Sound, and 2-4 shields are spent. The
// solo runs (no living relay) bound the kiter's own run to a shield.
static void TestAirReplayFromEverySlot()
{
    auto show = [](char const* kind, float cap, uint32 slot, AirReplay const& run)
    {
        std::printf("air replay %s cap=%.0f slot=%u contact=%.2f strike=%.2f worst=%.2f"
            " strikes=%d maxRun=%d kiterTicks=%d otherTicks=%d maxSound=%u\n", kind, cap,
            slot, run.FirstContactS, run.FirstStrikeS, run.WorstStrikeDelayS, run.Strikes,
            run.MaxConsecutiveKiterTicks, run.KiterTicks, run.OtherTicks, run.MaxSound);
    };
    for (float cap : { float(A::BuildingSpeedMaxStacks), 99.0f })
    {
        for (uint32 slot = Tank; slot <= Warlock; ++slot)
        {
            AirReplay const run = ReplayAirPhase(slot, cap);
            show("raid", cap, slot, run);
            assert(run.FirstContactS >= 0.0f && run.FirstStrikeS >= 0.0f);
            assert(run.WorstStrikeDelayS <= 3.0f);
            assert(run.MaxConsecutiveKiterTicks <= 4);
            assert(run.MaxSound < A::SoundEmergency);
            assert(!run.DoubleClick);
            assert(run.Strikes >= 2 && run.Strikes <= 4);
        }
        for (uint32 slot : { uint32(Tank), uint32(Rogue) })
        {
            AirReplay const run = ReplayAirPhase(slot, cap, true);
            show("solo", cap, slot, run);
            assert(run.FirstStrikeS >= 0.0f && run.WorstStrikeDelayS <= 4.5f);
            assert(run.MaxConsecutiveKiterTicks <= 4);
            assert(run.MaxSound < A::SoundEmergency);
            assert(run.Strikes <= 5);
        }
    }
}

struct GroundKiteRun
{
    int Direction = 0;
    int Reversals = 0;
    float MinTickGapRad = 10.0f;
};

// Kites a Sonic Breath for 8 s (2 s cast + 6 s channel) at 0.25 s steps:
// the kiter runs at 7 yd/s toward each proposed point, the Tracking Flames
// (41879, 5 yd/s) follows it in a straight line from its summon point on the
// kiter. Records bearing reversals around the boss and, at every channel
// tick (t = 3..8 s), the angle between the beam and the kiter.
static GroundKiteRun SimulateGroundKite(uint32 slot, Vector3 start)
{
    Blackboard board = Board();
    Member(board, slot).Position = start;
    ActorSnapshot marker = MakeUnit(A::TrackingFlamesEntry, 91, start.X, start.Y, ActorKind::Summon);
    CastSnapshot channel;
    channel.SpellId = A::TrackingAura;
    channel.TargetGuid = PlayerGuid(slot);
    channel.Channeled = true;
    marker.Cast = channel;
    board.Summons.push_back(marker);
    AddAura(Member(board, slot), A::TrackingAura, marker.Guid);
    CastOnBoss(board, 78098);
    Vector3 const boss = Boss(board).Position;
    GroundKiteRun run;
    float previous = G::Bearing(boss, start);
    for (int step = 1; step <= 32; ++step)
    {
        ++board.Revision;
        board.ObservedAtMs += 250;
        AdaptiveAtramedesPlan plan = Plan(board, slot);
        assert(Mechanic(plan) == "sonic_breath_kite");
        Vector3& self = Member(board, slot).Position;
        Advance(self, { MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f }, 1.75f);
        Advance(board.Summons.back().Position, self, 1.25f);
        float const bearing = G::Bearing(boss, self);
        float const delta = G::AngleDelta(bearing, previous);
        int const sign = delta > 0.0f ? 1 : -1;
        if (!run.Direction)
            run.Direction = sign;
        else if (sign != run.Direction)
            ++run.Reversals;
        previous = bearing;
        if (step >= 12 && step % 4 == 0)
            run.MinTickGapRad = std::min(run.MinTickGapRad, std::fabs(G::AngleDelta(
                bearing, G::Bearing(boss, board.Summons.back().Position))));
    }
    return run;
}

static void TestSonicBreathKiteKeepsDirection()
{
    // The gong owner at its duty-shield stand point (the reviewer's case).
    GroundKiteRun owner = SimulateGroundKite(Hunter, OwnerStand());
    // A flank melee slot, 22 yd north of the boss.
    GroundKiteRun flank = SimulateGroundKite(Rogue, { 172.0f, -202.5f, 75.0f });
    // Exactly opposite the raid centroid, where "away from the raid" is a tie.
    Blackboard board = Board();
    std::optional<Vector3> const centroid = A::RaidCentroid(board, PlayerGuid(Elemental),
        PlayerGuid(Tank));
    Vector3 const boss = Boss(board).Position;
    Vector3 const opposite = G::PointAt(boss, G::Bearing(*centroid, boss), 30.0f, 75.0f);
    GroundKiteRun tie = SimulateGroundKite(Elemental, opposite);
    for (GroundKiteRun const& run : { owner, flank, tie })
    {
        assert(run.Reversals == 0);
        assert(run.MinTickGapRad > A::SonicBreathHalfAngleRad);
    }

    // The breath is over (no cast or channel): the tracked player stops.
    Blackboard after = Board();
    ActorSnapshot marker = MakeUnit(A::TrackingFlamesEntry, 92, 176.0f, -249.0f, ActorKind::Summon);
    after.Summons.push_back(marker);
    AddAura(Member(after, Balance), A::TrackingAura, marker.Guid);
    // Its Tracking Flames channel lasts 10 s, but it is not a kiter (nor
    // excluded from gong duty) once the breath is over.
    assert(A::BuildFacts(after).GroundKiter.IsEmpty());
    assert(Mechanic(Plan(after, Balance)) != "sonic_breath_kite");
}

static void TestDifficultyVariants()
{
    // 25N/10H/25H spell IDs read the same as 10N.
    Blackboard board = Board();
    CastOnBoss(board, 92404);
    assert(A::BuildFacts(board).SonicBreathActive);
    CastOnBoss(board, A::SearingFlameSpell);
    AddAura(Boss(board), 92390, UnitGuid(42954, 250130));
    assert(A::BuildFacts(board).BossStunned);
    assert(CountClicks(board) == 0);
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
    TestAirKiteKeepsDirection();
    TestSonicBreathKiteKeepsDirection();
    TestDifficultyVariants();
    TestAirReplayFromEverySlot();
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

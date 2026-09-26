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
        MakePlayer(Hunter, "dps", "survival_hunter", stand.X, stand.Y),
        MakePlayer(Mage, "dps", "fire_mage", 131.0f, -229.0f),
        MakePlayer(HolyPaladin, "healer", "holy_paladin", 146.0f, -238.0f),
        MakePlayer(Retribution, "dps", "retribution_paladin", 165.0f, -240.0f),
        MakePlayer(Discipline, "healer", "discipline_priest", 146.0f, -212.0f),
        MakePlayer(Rogue, "dps", "assassination_rogue", 166.0f, -209.0f),
        MakePlayer(Elemental, "dps", "elemental_shaman", 140.0f, -222.0f),
        MakePlayer(Warlock, "dps", "demonology_warlock", 136.0f, -243.0f),
    };
    // As the server builds it: Atramedes is an instance TempSummon (the bell
    // intro and the post-wipe respawn), filed under Summons.
    ActorSnapshot boss = MakeUnit(A::BossEntry, 1, 172.0f, -224.5f, ActorKind::Summon);
    boss.InCombat = true;
    boss.ReactAggressive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.VictimGuid = PlayerGuid(Tank);
    boss.Health = boss.MaxHealth = 26111168;
    boss.HealthPct = 100.0f;
    board.Summons.push_back(boss);
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

// The boss is the first summon (flames are pushed after it).
static ActorSnapshot& Boss(Blackboard& board) { return board.Summons.front(); }

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
    board.Summons.clear();
    assert(!Plan(board, Balance).OwnsNode);
    // Round 4: the native summon was invisible to a Hostiles-only lookup, the
    // plan never owned the node and the route failed closed on the boss.
    board = Board();
    assert(Boss(board).Kind == ActorKind::Summon && board.Hostiles.empty());
    assert(A::FindBoss(board) == &board.Summons.front());
    assert(A::BuildDutyPlan(board).Applies);
    AdaptiveAtramedesPlan plan = Plan(board, Balance);
    assert(plan.OwnsNode);
    assert(plan.DamageTarget == Boss(board).Guid);
    assert(Plan(board, Tank, "tank").DamageTarget == Boss(board).Guid);
    // The respawned, idle Atramedes (not in combat): the route walks back
    // and pulls; the plan owns only an engaged boss.
    {
        Blackboard idle = Board();
        Boss(idle).InCombat = false;
        Boss(idle).VictimGuid = ObjectGuid();
        for (ActorSnapshot const& player : idle.Players)
        {
            AdaptiveAtramedesPlan const quiet = AdaptiveAtramedesStrategy().Propose(idle,
                player.Guid, player.Role.c_str());
            assert(!quiet.OwnsNode && quiet.DamageTarget.IsEmpty() && !quiet.Movement
                && !quiet.Interaction);
        }
    }
    // Found in either list.
    {
        Blackboard hostile = Board();
        hostile.Hostiles.push_back(hostile.Summons.front());
        hostile.Summons.erase(hostile.Summons.begin());
        assert(Plan(hostile, Balance).OwnsNode);
    }
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

    // The ground strike keeps the in-range relay shields for the air: in
    // reach of relay shield 250128 (nearest) and of 250130, the owner
    // strikes 250130.
    board = Board();
    CastOnBoss(board, A::SearingFlameSpell);
    Member(board, Hunter).Position = { 174.5f, -258.7f, 75.0f };
    BotNativeAction::SpellClick const* kept = ClickOf(Plan(board, Hunter));
    assert(kept && kept->Target == UnitGuid(42954, 250130));
    // Only a relay shield in reach: it is struck (Searing Flame outranks it).
    Member(board, Hunter).Position = { 166.0f, -259.0f, 75.0f };
    BotNativeAction::SpellClick const* spent = ClickOf(Plan(board, Hunter));
    assert(spent && spent->Target.GetCounter() == 250128);

    // Standby: while this ground phase's Searing Flame is pending (or the
    // schedule is unknown) the owner holds non-relay shield 250130; once it
    // is spent (published schedule without its timer) the owner waits at the
    // first air relay station, 250128's, and holds there.
    board = Board();
    Member(board, Hunter).Position = { 150.0f, -240.0f, 75.0f };
    assert(Mechanic(Plan(board, Hunter)) == "gong_owner_standby");
    AddTimer(Boss(board), A::TakeOffSpell, 60000);
    AddTimer(Boss(board), A::SearingFlameSpell, 20000);
    assert(Mechanic(Plan(board, Hunter)) == "gong_owner_standby");
    Boss(board).MechanicTimers.pop_back();
    AdaptiveAtramedesPlan airStandby = Plan(board, Hunter);
    assert(Mechanic(airStandby) == "gong_owner_air_standby");
    A::Facts const standbyFacts = A::BuildFacts(board);
    std::vector<A::ShieldFact> const standbyRelays = A::RelayShields(standbyFacts);
    assert(!standbyRelays.empty() && standbyRelays.front().Guid.GetCounter() == 250128);
    Vector3 const airStation = A::AirStationPoint(standbyRelays.front());
    assert(G::Distance2d({ MoveOf(airStandby)->X, MoveOf(airStandby)->Y, 75.0f },
        airStation) < 0.1f);
    Member(board, Hunter).Position = { airStation.X + 0.5f, airStation.Y, 75.0f };
    assert(!MoveOf(Plan(board, Hunter)));
    // The boss dragged out of spell range of the station: back to 250130.
    Boss(board).Position = { 110.0f, -180.0f, 75.0f };
    assert(Mechanic(Plan(board, Hunter)) == "gong_owner_standby");
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

// Round 4, the first live pull: Atramedes (a native summon) landed at
// (214.53, -223.92) and aggroed the raid still stacked on the bell gather
// point (231.6, -224.4), 17 yd away inside his 20 yd reach. With the plan
// blind to the summon nobody moved: one Sonic Breath hit all ten for four
// ticks and Devastation followed on all of them. From that exact snapshot
// the plan now spreads everyone and splits the breath.
static void TestRound4BellStack()
{
    Blackboard board = Board();
    Vector3 const bell{ 231.6f, -224.4f, 75.0f };
    Boss(board).Position = { 214.531f, -223.918f, 74.7668f };
    for (ActorSnapshot& player : board.Players)
        player.Position = bell;
    A::DutyPlan const duties = A::BuildDutyPlan(board);
    assert(Mechanic(Plan(board, Tank, "tank")) == "tank_anchor_drag");
    for (uint32 slot : { Balance, Mage, Elemental, Warlock })
        assert(Mechanic(Plan(board, slot)) == "ranged_arc");
    for (uint32 slot : { HolyPaladin, Discipline })
        assert(Mechanic(Plan(board, slot, "healer")) == "ranged_arc");
    for (uint32 slot : { Retribution, Rogue })
        assert(Mechanic(Plan(board, slot)) == "melee_max_range");
    assert(duties.GongOwner == PlayerGuid(Hunter));
    assert(Mechanic(Plan(board, Hunter)) == "gong_owner_standby");
    // Every non-tank plan damages him.
    for (ActorSnapshot const& player : board.Players)
        assert(AdaptiveAtramedesStrategy().Propose(board, player.Guid, player.Role.c_str())
            .DamageTarget == Boss(board).Guid);

    // The first Sonic Breath on that stack: the tracked Elemental kites and
    // everyone else in the beam leaves it.
    ActorSnapshot flames = MakeUnit(A::TrackingFlamesEntry, 92, bell.X, bell.Y, ActorKind::Summon);
    board.Summons.push_back(flames);
    AddAura(Member(board, Elemental), A::TrackingAura, flames.Guid);
    CastOnBoss(board, A::SonicBreathChannelSpells.front());
    assert(Mechanic(Plan(board, Elemental)) == "sonic_breath_kite");
    int exits = 0;
    for (ActorSnapshot const& player : board.Players)
    {
        if (player.Guid == PlayerGuid(Elemental) || player.Guid == PlayerGuid(Tank))
            continue;
        std::string const mechanic = Mechanic(AdaptiveAtramedesStrategy().Propose(board,
            player.Guid, player.Role.c_str()));
        assert(mechanic == "sonic_breath_beam_exit" || mechanic == "gong_approach");
        exits += mechanic == "sonic_breath_beam_exit";
    }
    assert(exits >= 7);
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

static ActorSnapshot& AddFlame(Blackboard& board, ActorSnapshot& kiter, Vector3 at,
    uint8 stacks);

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

    // Relay stations must keep the relays (the best ranged damage dealers)
    // casting at the hovering boss (Spell::CheckRange is 3D, 40 + 1.5 + 20 =
    // 61.5 yd) and in click reach of their shield (native 5 + 1.5 + 6 = 12.5
    // yd, used with 1 yd margin), over the whole 1 yd hold area. On the native
    // spawns five stations qualify, nearest the hover point first.
    assert(A::ShieldClickDistance <= 12.5f - 1.0f);
    A::DutyPlan const relayDuties = A::BuildDutyPlan(slack);
    assert(relayDuties.GongOwner == PlayerGuid(Hunter) && relayDuties.GongBackup == PlayerGuid(Mage));
    std::vector<A::ShieldFact> const relays = A::RelayShields(slackFacts);
    std::vector<uint32> relayIds;
    for (A::ShieldFact const& relay : relays)
        relayIds.push_back(relay.Guid.GetCounter());
    assert((relayIds == std::vector<uint32>{ 250128, 250126, 250125, 250122, 250129 }));
    for (A::ShieldFact const& shield : slackFacts.Shields)
    {
        Vector3 const station = A::AirStationPoint(shield);
        bool const inRange = G::Distance3d(station, A::HoverPoint) + A::RelayStationTolerance
            <= A::RangedEnvelope - A::RelayRangeMargin;
        bool const inReach = G::Distance3d(station, shield.Position) + A::RelayStationTolerance
            <= A::ShieldClickDistance;
        assert(inReach);
        assert((inRange && inReach) == (std::find(relayIds.begin(), relayIds.end(),
            shield.Guid.GetCounter()) != relayIds.end()));
    }
    // Owner at the station nearest the hover point (250128), backup at the
    // in-range one farthest from it (250129, north-east).
    AdaptiveAtramedesPlan owner = Plan(slack, Hunter);
    assert(Mechanic(owner) == "air_relay_station");
    Vector3 const station{ MoveOf(owner)->X, MoveOf(owner)->Y, 75.0f };
    assert(G::Distance3d(station, A::HoverPoint) + A::RelayStationTolerance <= A::RangedEnvelope);
    assert(G::Distance3d(station, relays.front().Position) + A::RelayStationTolerance
        <= A::ShieldClickDistance);
    std::optional<A::ShieldFact> const backupShield = A::AirRelayShieldFor(slack, slackFacts,
        relayDuties, PlayerGuid(Mage));
    assert(backupShield && backupShield->Guid.GetCounter() == 250129);
    assert(Mechanic(Plan(slack, Mage)) == "air_relay_station");
    // A kiting owner leaves its station; the backup keeps its own (already
    // there) while a second station exists ...
    ActorSnapshot& ownerKiter = Member(slack, Hunter);
    AddFlame(slack, ownerKiter, { ownerKiter.Position.X + 20.0f, ownerKiter.Position.Y, 75.0f }, 0);
    A::Facts const kiting = A::BuildFacts(slack);
    assert(kiting.AirKiter == PlayerGuid(Hunter));
    assert(!A::AirRelayShieldFor(slack, kiting, relayDuties, PlayerGuid(Hunter)));
    std::optional<A::ShieldFact> const kept = A::AirRelayShieldFor(slack, kiting, relayDuties,
        PlayerGuid(Mage));
    assert(kept && kept->Guid.GetCounter() == 250129);
    // ... and takes the single station over when it is the only one.
    Blackboard single = slack;
    single.Interactables.erase(std::remove_if(single.Interactables.begin(),
        single.Interactables.end(), [](ActorSnapshot const& shield)
        {
            uint32 const id = shield.Guid.GetCounter();
            return id != 250128 && id != 250130 && id != 250131 && id != 250123;
        }), single.Interactables.end());
    A::Facts const singleFacts = A::BuildFacts(single);
    assert(A::RelayShields(singleFacts).size() == 1);
    std::optional<A::ShieldFact> const taken = A::AirRelayShieldFor(single, singleFacts,
        relayDuties, PlayerGuid(Mage));
    assert(taken && taken->Guid.GetCounter() == 250128);

    // Sparse fallback: with 3 or fewer shields left, none in range and the
    // budget still allowing an air rescue, the owner guards the shield
    // nearest the hover point (250130) out of range.
    Blackboard sparse = AirBoard();
    KeepShields(sparse, 2);
    A::Facts const sparseFacts = A::BuildFacts(sparse);
    assert(sparseFacts.Shields.size() > A::SearingFlameReserve(sparseFacts).Total());
    std::vector<A::ShieldFact> const fallback = A::RelayShields(sparseFacts);
    assert(fallback.size() == 1 && fallback.front().Guid == UnitGuid(42954, 250130));
    Vector3 const guard = A::AirStationPoint(fallback.front());
    assert(!A::StationInRange(guard));
    Member(sparse, Hunter).Position = { guard.X + 3.0f, guard.Y, 75.0f };
    assert(Mechanic(Plan(sparse, Hunter)) == "air_relay_station_out_of_range");
    // Held within tolerance like any station (no move every decision).
    Member(sparse, Hunter).Position = guard;
    assert(!Plan(sparse, Hunter).Movement);
    // No fallback when the reserve forbids the strike it would guard.
    KeepShields(sparse, 1);
    A::Facts const reserved = A::BuildFacts(sparse);
    assert(reserved.Shields.size() <= A::SearingFlameReserve(reserved).Total());
    assert(A::RelayShields(reserved).empty());
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
    // Farther from contact (15.6 yd, 5 stacks: 2.5 s), but the next shield
    // ahead (250125) is 2.8 s from reach: strike now rather than be caught
    // between shields.
    board.Summons.back().Position = { 100.0f, -259.0f, 75.0f };
    board.Summons.back().Auras.back().Stacks = 5;
    A::Facts const early = A::BuildFacts(board);
    float const earlyContact = A::FlameTimeToContact(board.Summons.back(), Member(board, Mage));
    assert(earlyContact > A::RescueLeadSeconds);
    assert(earlyContact < A::SecondsToNextShield(early, Member(board, Mage), early.Shields.front(), 1)
        + A::RescueLeadSeconds);
    assert(!A::RelayInReach(board, early, A::BuildDutyPlan(board)));
    assert(ClickOf(Plan(board, Mage)) && CountClicks(board) == 1);
    // Slower (2 stacks: 4.6 s): the next shield is reachable, keep kiting.
    board.Summons.back().Auras.back().Stacks = 2;
    assert(CountClicks(board) == 0);
    assert(Mechanic(Plan(board, Mage)) == "roaring_flame_breath_kite");
    // A passer-by beside a shield (the Warlock at 250131) is not a relay and
    // does not suppress the lone-kiter early strike ...
    board.Summons.back().Auras.back().Stacks = 5;
    Member(board, Warlock).Position = { 180.0f, -197.0f, 75.0f };
    assert(!A::RelayInReach(board, A::BuildFacts(board), A::BuildDutyPlan(board)));
    assert(CountClicks(board) == 1);
    // ... but the gong owner at its assigned station does: it strikes at
    // contact instead, so nothing is spent early.
    A::DutyPlan const earlyDuties = A::BuildDutyPlan(board);
    std::optional<A::ShieldFact> const ownerShield = A::AirRelayShieldFor(board,
        A::BuildFacts(board), earlyDuties, PlayerGuid(Hunter));
    assert(ownerShield);
    Member(board, Hunter).Position = A::AirStationPoint(*ownerShield);
    assert(A::RelayInReach(board, A::BuildFacts(board), earlyDuties));
    assert(CountClicks(board) == 0);

    // Two strikers still carry the 15 s air Resonating Clash aura: the one
    // whose aura expires last struck last and is the flame's next target.
    board = AirBoard();
    board.Summons.push_back(MakeUnit(A::ReverberatingFlameEntry, 81, 120.0f, -240.0f,
        ActorKind::Summon));
    Member(board, Balance).Auras.push_back({ A::AirClashAura, UnitGuid(42956, 250122), 0, 9000 });
    Member(board, Warlock).Auras.push_back({ A::AirClashAura, UnitGuid(42954, 250130), 0, 17000 });
    A::Facts const redirect = A::BuildFacts(board);
    assert(redirect.AirKiter.IsEmpty());
    assert(A::AirRedirectRunner(board, redirect)->Guid == PlayerGuid(Warlock));
    assert(Mechanic(Plan(board, Warlock)) == "air_redirect_run");
    assert(Mechanic(Plan(board, Balance)) != "air_redirect_run");

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

    // A striker in reach of relay shield 250128 and of 250130 strikes 250130
    // even though 250128 lies farther from the flame: the few in-range relay
    // shields are the next air phase's first catches.
    {
        Blackboard keep = AirBoard();
        for (ActorSnapshot& player : keep.Players)
            player.Position = A::ArenaCenter;
        Member(keep, Mage).Position = { 185.0f, -235.0f, 75.0f };
        AddFlame(keep, Member(keep, Mage), { 185.0f, -241.0f, 75.0f }, 6);
        Member(keep, Warlock).Position = { 174.5f, -258.7f, 75.0f };
        A::Facts const keepFacts = A::BuildFacts(keep);
        std::vector<A::ShieldFact> const keepRelays = A::RelayShields(keepFacts);
        assert(std::any_of(keepRelays.begin(), keepRelays.end(),
            [](A::ShieldFact const& shield) { return shield.Guid.GetCounter() == 250128; }));
        AdaptiveAtramedesPlan keeper = Plan(keep, Warlock);
        assert(keeper.GongReason == "air_breath_rescue");
        assert(ClickOf(keeper) && ClickOf(keeper)->Target == UnitGuid(42954, 250130));
        assert(CountClicks(keep) == 1);
    }

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

// Native-follow replay of one air phase from the ground formation at liftoff.
// Every bot follows its own plan at 7 yd/s (0.25 s decision steps). At
// liftoff Atramedes is put at his hover point; the bots walk to their air
// positions until the flame spawns ON the target (78213 summons at its
// position) `flameDelayS` later (the native takeoff takes about 7 s).
// Spellclicks execute the native effects (shield used, 78168 on the striker,
// every Sound bar to 0, the flame interrupted: 2 s wait, flight to the struck
// shield, Building Speed reset, then Tracking on the striker). The flame
// relaunches a predictive follow every 400 ms at 5 yd/s + 1 per Building
// Speed stack (one a second up to `stackCap`) and its 5 yd breath ticks every
// 0.5 s (+3 Sound).
// Replay variants (user raid experience, 2026-09-25): the canonical roster's
// mobility published as spell timers (all ready), the mage's Ice Block ready
// or on its cooldown, or no mage at all.
struct ReplayOptions
{
    bool Mobility = false;
    bool IceBlockReady = true;
    bool NoMage = false;
    // A later air phase (about 124 s after the previous one): Dash (180 s)
    // is still cooling down.
    uint32 DashRemainingMs = 0;
};

struct AirReplay
{
    int IceStrikes = 0;
    int IceBlocks = 0;
    int Extensions = 0;
    bool BlinkAfterIce = false;
    uint32 MageSoundWhileIced = 0;
    float FirstContactS = -1.0f;
    float FirstStrikeS = -1.0f;
    float FirstCatchDelayS = 0.0f;
    int FirstCatchTicks = 0;
    float WorstSteadyDelayS = 0.0f;
    int MaxSteadyConsecutiveTicks = 0;
    int Strikes = 0;
    int KiterTicks = 0;
    int OtherTicks = 0;
    uint32 MaxSound = 0;
    bool DoubleClick = false;
    std::vector<uint32> ShieldsLeft;
    std::vector<std::string> StrikeReasons;
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

// One decision step without a flame: every bot moves along its plan.
static void StepPlans(Blackboard& board)
{
    ++board.Revision;
    board.ObservedAtMs += 250;
    std::map<ObjectGuid, Vector3> destinations;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive)
            if (BotNativeAction::Move const* move = MoveOf(AdaptiveAtramedesStrategy().Propose(
                    board, player.Guid, player.Role.c_str())))
                destinations[player.Guid] = { move->X, move->Y, 75.0f };
    MoveBots(board, destinations);
}

static std::vector<uint32> AllShieldIds()
{
    std::vector<uint32> ids;
    for (A::ShieldSpawn const& spawn : A::ShieldSpawns)
        ids.push_back(spawn.SpawnId);
    return ids;
}

static void KeepShieldIds(Blackboard& board, std::vector<uint32> const& shields)
{
    board.Interactables.erase(std::remove_if(board.Interactables.begin(), board.Interactables.end(),
        [&shields](ActorSnapshot const& shield)
        {
            return std::find(shields.begin(), shields.end(), shield.Guid.GetCounter()) == shields.end();
        }), board.Interactables.end());
}

// A ground phase's Searing Flame, played by the strategy: the ground
// formation settles, Atramedes channels Searing Flame and the shield the
// gong owner strikes is spent.
static std::vector<uint32> AfterGroundSearing(std::vector<uint32> shields, float bossHealthPct)
{
    Blackboard board = Board();
    Boss(board).HealthPct = bossHealthPct;
    Boss(board).Position = A::TankAnchor;
    KeepShieldIds(board, shields);
    for (int step = 0; step < 32; ++step)
        StepPlans(board);
    CastOnBoss(board, A::SearingFlameSpell);
    for (int step = 0; step < 40; ++step)
    {
        for (ActorSnapshot const& player : board.Players)
            if (BotNativeAction::SpellClick const* click = ClickOf(AdaptiveAtramedesStrategy().Propose(
                    board, player.Guid, player.Role.c_str())))
            {
                shields.erase(std::find(shields.begin(), shields.end(), click->Target.GetCounter()));
                return shields;
            }
        StepPlans(board);
    }
    assert(false && "Searing Flame never gonged");
    return shields;
}

namespace M = BotEncounter::Atramedes::Mobility;

// The spells the canonical roster trains (4.3.4 DBC rows in
// BotAtramedesMobility.h): hunter Disengage, mage
// Blink and Ice Block, balance druid Cat Form, Dash and Stampeding Roar,
// rogue Sprint. The others have none that helps a chased player.
static void PublishMobility(Blackboard& board, ReplayOptions const& options)
{
    AddTimer(Member(board, Hunter), M::DisengageSpell, 0);
    AddTimer(Member(board, Mage), M::BlinkSpell, 0);
    AddTimer(Member(board, Mage), M::IceBlockSpell, options.IceBlockReady ? 0 : 200000);
    for (uint32 spell : { M::CatFormSpell, M::StampedingRoarSpell })
        AddTimer(Member(board, Balance), spell, 0);
    AddTimer(Member(board, Balance), M::DashSpell, options.DashRemainingMs);
    AddTimer(Member(board, Rogue), M::SprintSpell, 0);
}

static MechanicTimerSnapshot* TimerOf(ActorSnapshot& actor, uint32 spellId)
{
    for (MechanicTimerSnapshot& timer : actor.MechanicTimers)
        if (timer.SpellId == spellId)
            return &timer;
    return nullptr;
}

static BotNativeAction::CastSpell const* CastOf(AdaptiveAtramedesPlan const& plan)
{
    return plan.Interaction ? std::get_if<BotNativeAction::CastSpell>(&plan.Interaction->Action)
        : nullptr;
}

static BotNativeAction::DirectionalMobility const* LeapOf(AdaptiveAtramedesPlan const& plan)
{
    return plan.Interaction
        ? std::get_if<BotNativeAction::DirectionalMobility>(&plan.Interaction->Action)
        : nullptr;
}

static void EraseAura(ActorSnapshot& actor, uint32 spellId)
{
    actor.Auras.erase(std::remove_if(actor.Auras.begin(), actor.Auras.end(),
        [spellId](AuraSnapshot const& aura) { return aura.SpellId == spellId; }),
        actor.Auras.end());
}

static AirReplay ReplayAirPhase(uint32 targetSlot, float stackCap, float flameDelayS,
    bool solo = false, std::vector<uint32> const& shields = AllShieldIds(),
    float bossHealthPct = 100.0f, float seconds = 31.0f, ReplayOptions const& options = {})
{
    Blackboard board = Board();
    Boss(board).HealthPct = bossHealthPct;
    KeepShieldIds(board, shields);
    if (options.Mobility)
        PublishMobility(board, options);
    if (options.NoMage)
        Member(board, Mage).Alive = false;
    // Solo: everyone else is dead, so no relay exists and the target must
    // reach a shield on its own.
    if (solo)
        for (ActorSnapshot& player : board.Players)
            if (player.Guid != PlayerGuid(targetSlot))
                player.Alive = false;
    // The ground formation at liftoff, after this ground phase's Searing
    // Flame (published schedule without its timer): the owner at its air
    // standby, the ranged arc around the boss on the tank anchor.
    Boss(board).Position = A::TankAnchor;
    AddTimer(Boss(board), A::TakeOffSpell, 30000);
    for (int step = 0; step < 32; ++step)
        StepPlans(board);
    ActorSnapshot& liftoff = Boss(board);
    liftoff.MechanicTimers.clear();
    liftoff.Position = A::HoverPoint;
    liftoff.Flying = true;
    liftoff.ReactAggressive = false;
    liftoff.VictimGuid = ObjectGuid();
    for (float t = 0.25f; t <= flameDelayS + 0.001f; t += 0.25f)
        StepPlans(board);

    ActorSnapshot& target = Member(board, targetSlot);
    AddFlame(board, target, target.Position, 0);
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
    uint32 mageSoundAtIce = 0;
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
            if (ActorSnapshot const* marker = A::KiterFlame(facts, *kiter))
            {
                float const ttc = A::IsIced(*kiter) ? std::numeric_limits<float>::infinity()
                    : A::FlameTimeToContact(*marker, *kiter);
                if (ttc <= A::RescueLeadSeconds)
                {
                    if (contactOpen < 0.0f)
                        contactOpen = t;
                    if (result.FirstContactS < 0.0f)
                        result.FirstContactS = t;
                }
                // Out of reach again (a kite extension, an Ice Block): the
                // catch is over without a strike.
                else if (ttc > A::RescueLeadSeconds + 1.0f)
                    contactOpen = -1.0f;
            }
        if (ActorSnapshot const* mage = A::FindLivingPlayer(board, PlayerGuid(Mage)))
        {
            if (A::FindAura(*mage, A::IceBlockAura))
                result.MageSoundWhileIced = std::max(result.MageSoundWhileIced,
                    mage->AlternatePower - std::min(mage->AlternatePower, mageSoundAtIce));
            else
                mageSoundAtIce = mage->AlternatePower;
        }
        std::map<ObjectGuid, Vector3> destinations;
        std::vector<std::pair<ObjectGuid, uint32>> casts;
        std::vector<std::pair<ObjectGuid, BotNativeAction::DirectionalMobility>> leaps;
        ObjectGuid clicker;
        ObjectGuid clicked;
        std::string clickReason;
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
                    clickReason = std::string(plan.GongReason);
                }
                continue;
            }
            if (BotNativeAction::CastSpell const* cast = CastOf(plan))
                casts.emplace_back(player.Guid, cast->SpellId);
            if (BotNativeAction::DirectionalMobility const* leap = LeapOf(plan))
                leaps.emplace_back(player.Guid, *leap);
            if (BotNativeAction::Move const* move = MoveOf(plan))
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
            ActorSnapshot& striker = Member(board, clicker.GetCounter());
            striker.Auras.erase(std::remove_if(striker.Auras.begin(), striker.Auras.end(),
                [](AuraSnapshot const& aura) { return aura.SpellId == A::AirClashAura; }),
                striker.Auras.end());
            AuraSnapshot clash;
            clash.SpellId = A::AirClashAura;
            clash.CasterGuid = clicked;
            clash.ExpiresAtMs = board.ObservedAtMs + 15000;
            striker.Auras.push_back(clash);
            clashUntil[clicker] = t + 15.0f;
            result.StrikeReasons.push_back(clickReason);
            if (clickReason == "air_ice_block_rescue")
                ++result.IceStrikes;
            flame().Cast.reset();
            tracked.Clear();
            nextTarget = clicker;
            toShield = true;
            waitUntil = t + 2.0f;
            ++result.Strikes;
            float const delay = contactOpen >= 0.0f ? t - contactOpen : 0.0f;
            if (result.FirstStrikeS < 0.0f)
            {
                result.FirstStrikeS = t;
                result.FirstCatchDelayS = delay;
            }
            else
                result.WorstSteadyDelayS = std::max(result.WorstSteadyDelayS, delay);
            contactOpen = -1.0f;
        }
        // Native player casts: known and off cooldown, the form a spell needs.
        for (auto const& [guid, spellId] : casts)
        {
            ActorSnapshot& caster = Member(board, guid.GetCounter());
            MechanicTimerSnapshot* timer = TimerOf(caster, spellId);
            if (!timer || timer->RemainingMs > 0)
                continue;
            if (spellId == M::IceBlockSpell)
            {
                if (A::FindAura(caster, A::HypothermiaAura))
                    continue;
                // Immunity with SPELL_ATTR1_DISPEL_AURAS_ON_IMMUNITY strips
                // the physical Tracking aura and ends the flame's channel;
                // the flame keeps following (MoveFollow).
                EraseAura(caster, A::TrackingAura);
                if (tracked == caster.Guid)
                    flame().Cast.reset();
                caster.Auras.push_back({ A::IceBlockAura, caster.Guid, 0, board.ObservedAtMs + 10000 });
                caster.Auras.push_back({ A::HypothermiaAura, caster.Guid, 0, board.ObservedAtMs + 30000 });
                timer->RemainingMs = 300000;
                ++result.IceBlocks;
                continue;
            }
            if (spellId == M::CatFormSpell)
            {
                if (!A::FindAura(caster, M::CatFormSpell))
                    caster.Auras.push_back({ M::CatFormSpell, caster.Guid, 0, 0 });
                continue;
            }
            M::Ability const* ability = M::Find(spellId);
            if (!ability || ability->Type != M::Kind::Speed
                || (ability->RequiredForm && !A::FindAura(caster, ability->RequiredForm)))
                continue;
            caster.Auras.push_back({ spellId, caster.Guid, 0,
                ability->DurationMs ? board.ObservedAtMs + ability->DurationMs : 0 });
            timer->RemainingMs = ability->CooldownMs;
            ++result.Extensions;
        }
        for (auto const& [guid, leap] : leaps)
        {
            ActorSnapshot& caster = Member(board, guid.GetCounter());
            MechanicTimerSnapshot* timer = TimerOf(caster, leap.SpellId);
            M::Ability const* ability = M::Find(leap.SpellId);
            if (!timer || timer->RemainingMs > 0 || !ability || A::FindAura(caster, A::IceBlockAura))
                continue;
            float const dx = leap.X - caster.Position.X;
            float const dy = leap.Y - caster.Position.Y;
            float const length = std::max(0.01f, std::sqrt(dx * dx + dy * dy));
            caster.Position.X += dx / length * ability->Yards;
            caster.Position.Y += dy / length * ability->Yards;
            timer->RemainingMs = ability->CooldownMs;
            ++result.Extensions;
            if (leap.SpellId == M::BlinkSpell && A::FindAura(caster, A::HypothermiaAura))
                result.BlinkAfterIce = true;
            destinations.erase(guid);
        }
        // Run speed from the auras; an iced player does not move.
        for (ActorSnapshot& player : board.Players)
        {
            auto itr = destinations.find(player.Guid);
            if (player.Alive && itr != destinations.end()
                && !A::FindAura(player, A::IceBlockAura))
                Advance(player.Position, itr->second, M::RunSpeed(player) * 0.25f);
        }
        for (ActorSnapshot& player : board.Players)
        {
            for (MechanicTimerSnapshot& timer : player.MechanicTimers)
                timer.RemainingMs = timer.RemainingMs > 250 ? timer.RemainingMs - 250 : 0;
            player.Auras.erase(std::remove_if(player.Auras.begin(), player.Auras.end(),
                [&board](AuraSnapshot const& aura)
                {
                    return aura.SpellId != A::AirClashAura && aura.ExpiresAtMs
                        && aura.ExpiresAtMs <= board.ObservedAtMs;
                }), player.Auras.end());
        }
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
                // An iced target is immune to Tracking: the flame only follows.
                if (!A::FindAura(next, A::IceBlockAura))
                {
                    CastSnapshot channel;
                    channel.SpellId = A::TrackingAura;
                    channel.TargetGuid = tracked;
                    channel.Channeled = true;
                    flame().Cast = channel;
                    AddAura(next, A::TrackingAura, flameGuid);
                }
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
                // Ice Block: immune to the fire damage and its Sound energize.
                if (A::FindAura(player, A::IceBlockAura))
                    continue;
                player.AlternatePower = std::min<uint32>(100, player.AlternatePower + 3);
                if (player.Guid == tracked)
                {
                    kiterHit = true;
                    ++result.KiterTicks;
                    if (result.FirstStrikeS < 0.0f)
                        ++result.FirstCatchTicks;
                }
                else
                    ++result.OtherTicks;
            }
            consecutive = kiterHit ? consecutive + 1 : 0;
            if (result.FirstStrikeS >= 0.0f)
                result.MaxSteadyConsecutiveTicks = std::max(result.MaxSteadyConsecutiveTicks,
                    consecutive);
        }
        for (ActorSnapshot const& player : board.Players)
            result.MaxSound = std::max(result.MaxSound, player.AlternatePower);
    }
    for (ActorSnapshot const& shield : board.Interactables)
        result.ShieldsLeft.push_back(shield.Guid.GetCounter());
    return result;
}

// Every target of successive 31 s air phases, the tank included, from the
// ground formation at liftoff with the flame spawned on the target after the
// native takeoff (7 s) and after 3 s, at the server's Building Speed cap (10)
// and an uncapped 99-stack stress. Each air phase follows a ground Searing
// Flame gonged by the strategy.
//   Phase 1: ten shields less one Searing Flame, boss at 100%.
//   Phase 2: the shields left after phase 1 less one Searing Flame, boss 60%.
//   Phase 3: three shields left, boss at 25% (no reserve): the three shields
//            farthest from the hover point (no station in range) for every
//            target, and every one of the 120 three-shield sets with the
//            target rotating over the roster, at the server cap.
// Bounds: the first catch of every phase is struck within 3 s of contact
// with at most 2 s (4 ticks) of breath before it and one click at a time;
// in phases 1-2 every later catch within 3 s and never more than 2 s of
// breath at a time, and nobody nears 90 Sound. The solo runs (no living
// relay) bound the kiter's own run to a shield.
static void TestAirReplayFromEverySlot()
{
    auto show = [](char const* kind, float cap, float delay, uint32 slot, AirReplay const& run)
    {
        std::printf("air replay %s cap=%.0f flame=%.0fs slot=%u contact=%.2f strike=%.2f"
            " first=%.2f/%d steady=%.2f/%d strikes=%d kiterTicks=%d otherTicks=%d maxSound=%u"
            " left=%zu\n", kind, cap, delay, slot, run.FirstContactS, run.FirstStrikeS,
            run.FirstCatchDelayS, run.FirstCatchTicks, run.WorstSteadyDelayS,
            run.MaxSteadyConsecutiveTicks, run.Strikes, run.KiterTicks, run.OtherTicks,
            run.MaxSound, run.ShieldsLeft.size());
    };
    auto firstCatchBound = [](AirReplay const& run)
    {
        assert(run.FirstContactS >= 0.0f && run.FirstStrikeS >= 0.0f);
        assert(run.FirstCatchDelayS <= 3.0f && run.FirstCatchTicks <= 4);
        assert(!run.DoubleClick);
    };
    std::vector<uint32> const beforePhase1 = AfterGroundSearing(AllShieldIds(), 100.0f);
    // The ground Searing Flame keeps the in-range relay shields.
    assert(beforePhase1.size() == 9);
    assert(std::find(beforePhase1.begin(), beforePhase1.end(), 250130) == beforePhase1.end());
    std::vector<uint32> const farthest{ 250123, 250127, 250131 };
    for (float cap : { float(A::BuildingSpeedMaxStacks), 99.0f })
        for (float delay : { 7.0f, 3.0f })
        {
            for (uint32 slot = Tank; slot <= Warlock; ++slot)
            {
                AirReplay const first = ReplayAirPhase(slot, cap, delay, false, beforePhase1);
                show("phase1", cap, delay, slot, first);
                firstCatchBound(first);
                assert(first.WorstSteadyDelayS <= 3.0f && first.MaxSteadyConsecutiveTicks <= 4);
                assert(first.MaxSound < A::SoundEmergency);
                assert(first.Strikes >= 2 && first.Strikes <= 4);

                std::vector<uint32> const second = AfterGroundSearing(first.ShieldsLeft, 60.0f);
                AirReplay const phase2 = ReplayAirPhase(slot, cap, delay, false, second, 60.0f);
                show("phase2", cap, delay, slot, phase2);
                firstCatchBound(phase2);
                assert(phase2.WorstSteadyDelayS <= 3.0f && phase2.MaxSteadyConsecutiveTicks <= 4);
                assert(phase2.MaxSound < A::SoundEmergency);
                assert(phase2.Strikes >= 2 && phase2.Strikes <= 4);

                AirReplay const phase3 = ReplayAirPhase(slot, cap, delay, false, farthest, 25.0f);
                show("phase3", cap, delay, slot, phase3);
                firstCatchBound(phase3);
                assert(phase3.Strikes <= 3);
            }
            for (uint32 slot : { uint32(Tank), uint32(Rogue) })
            {
                AirReplay const run = ReplayAirPhase(slot, cap, delay, true);
                show("solo", cap, delay, slot, run);
                assert(run.FirstStrikeS >= 0.0f && run.FirstCatchDelayS <= 6.0f);
                assert(run.FirstCatchTicks <= 12);
                assert(run.WorstSteadyDelayS <= 4.5f && run.MaxSteadyConsecutiveTicks <= 4);
                assert(run.MaxSound < A::SoundEmergency);
                assert(run.Strikes <= 5);
            }
        }
    std::vector<uint32> const all = AllShieldIds();
    uint32 rotation = 0;
    for (std::size_t a = 0; a < all.size(); ++a)
        for (std::size_t b = a + 1; b < all.size(); ++b)
            for (std::size_t c = b + 1; c < all.size(); ++c)
                for (float delay : { 7.0f, 3.0f })
                {
                    uint32 const slot = Tank + rotation++ % 10;
                    AirReplay const phase3 = ReplayAirPhase(slot,
                        float(A::BuildingSpeedMaxStacks), delay, false,
                        { all[a], all[b], all[c] }, 25.0f);
                    firstCatchBound(phase3);
                    assert(phase3.Strikes <= 3);
                }
    std::printf("air replay phase3 three-shield sets=%u\n", rotation / 2);
}

// The user's air tactics (user raid experience, 2026-09-25) decision by
// decision: the third gonger by mobility, the chased player's extensions,
// and the mage Ice Block play. Spell readiness is only what the snapshot
// publishes (player MechanicTimers); nothing is assumed.
static void TestAirAbilities()
{
    using BotNativeAction::CastSpell;
    using BotNativeAction::DirectionalMobility;
    auto castOf = [](AdaptiveAtramedesPlan const& plan) -> CastSpell const*
    {
        return plan.Interaction ? std::get_if<CastSpell>(&plan.Interaction->Action) : nullptr;
    };
    auto leapOf = [](AdaptiveAtramedesPlan const& plan) -> DirectionalMobility const*
    {
        return plan.Interaction ? std::get_if<DirectionalMobility>(&plan.Interaction->Action)
            : nullptr;
    };

    // Third gonger: from the spec table while nothing is published (the
    // balance druid, Dash and Stampeding Roar, before the rogue's Sprint),
    // then from the published spells.
    Blackboard board = AirBoard();
    A::DutyPlan duties = A::BuildDutyPlan(board);
    assert(duties.GongOwner == PlayerGuid(Hunter) && duties.GongBackup == PlayerGuid(Mage));
    assert(duties.GongThird == PlayerGuid(Balance));
    AddTimer(Member(board, Rogue), M::SprintSpell, 45000);
    assert(A::BuildDutyPlan(board).GongThird == PlayerGuid(Rogue));
    // Dash without Cat Form is unusable; with it, Dash (70%, 8 s scored)
    // ties Sprint and the melee rogue keeps the duty; Stampeding Roar too
    // puts the druid ahead.
    AddTimer(Member(board, Balance), M::DashSpell, 0);
    assert(A::BuildDutyPlan(board).GongThird == PlayerGuid(Rogue));
    AddTimer(Member(board, Balance), M::CatFormSpell, 0);
    assert(A::BuildDutyPlan(board).GongThird == PlayerGuid(Rogue));
    AddTimer(Member(board, Balance), M::StampedingRoarSpell, 90000);
    assert(A::BuildDutyPlan(board).GongThird == PlayerGuid(Balance));
    // The third takes a station far from the owner's and the backup's.
    duties = A::BuildDutyPlan(board);
    A::Facts facts = A::BuildFacts(board);
    std::optional<A::ShieldFact> const third = A::AirRelayShieldFor(board, facts, duties,
        duties.GongThird);
    assert(third);
    for (ObjectGuid relay : { duties.GongOwner, duties.GongBackup })
    {
        std::optional<A::ShieldFact> const other = A::AirRelayShieldFor(board, facts, duties, relay);
        assert(other && other->Guid != third->Guid
            && G::Distance2d(other->Position, third->Position) > 30.0f);
    }

    // A chased rogue with Sprint ready: 3 s from contact it sprints (speed
    // buffs gain over their whole 8 s) while kiting on; a speed buff never
    // pre-empts the kite's movement lane.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Rogue).Position = { 110.0f, -271.0f, 75.0f };
    AddTimer(Member(board, Rogue), M::SprintSpell, 0);
    AddFlame(board, Member(board, Rogue), { 101.0f, -260.0f, 75.0f }, 4);
    facts = A::BuildFacts(board);
    float const approach = A::FlameTimeToContact(*A::KiterFlame(facts, Member(board, Rogue)),
        Member(board, Rogue));
    assert(approach > A::RescueLeadSeconds && approach <= A::SpeedBuffLeadSeconds);
    AdaptiveAtramedesPlan sprint = Plan(board, Rogue);
    assert(castOf(sprint) && castOf(sprint)->SpellId == M::SprintSpell);
    assert(Mechanic(sprint) == "roaring_flame_breath_kite" && !MoveOf(sprint)->PreemptCasting);
    assert(CountClicks(board) == 0);
    // Sprint running: faster, contact later, nothing more to cast.
    Member(board, Rogue).Auras.push_back({ M::SprintSpell, Member(board, Rogue).Guid, 0, 0 });
    Member(board, Rogue).MechanicTimers.back().RemainingMs = 60000;
    assert(A::FlameTimeToContact(*A::KiterFlame(A::BuildFacts(board), Member(board, Rogue)),
        Member(board, Rogue)) > approach);
    assert(!Plan(board, Rogue).Interaction);

    // A chased mage whose Ice Block is not published: Blink only at contact
    // (a leap waits), and the strike is held back for it.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddTimer(Member(board, Mage), M::BlinkSpell, 0);
    AddFlame(board, Member(board, Mage), { 101.0f, -260.0f, 75.0f }, 4);
    assert(!Plan(board, Mage).Interaction);
    board.Summons.back().Position = { 104.5f, -263.8f, 75.0f };
    board.Summons.back().Auras.back().Stacks = 6;
    facts = A::BuildFacts(board);
    assert(A::FlameTimeToContact(*A::KiterFlame(facts, Member(board, Mage)),
        Member(board, Mage)) <= A::RescueLeadSeconds);
    A::GongDecision const held = A::DecideGong(board, facts, A::BuildDutyPlan(board));
    assert(!held.Required && held.Withheld == "kiter_mobility_extension");
    AdaptiveAtramedesPlan blink = Plan(board, Mage);
    assert(leapOf(blink) && leapOf(blink)->SpellId == M::BlinkSpell);
    assert(leapOf(blink)->Facing == BotNativeAction::DirectionalMobilityFacing::Forward);
    assert(!blink.Movement && CountClicks(board) == 0);
    // Blink spent: the rescue strikes.
    Member(board, Mage).MechanicTimers.back().RemainingMs = 15000;
    assert(CountClicks(board) == 1);

    // A druid out of Cat Form shifts first, then Dashes.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Balance).Position = { 110.0f, -271.0f, 75.0f };
    for (uint32 spell : { M::CatFormSpell, M::DashSpell })
        AddTimer(Member(board, Balance), spell, 0);
    AddFlame(board, Member(board, Balance), { 101.0f, -260.0f, 75.0f }, 4);
    AdaptiveAtramedesPlan shift = Plan(board, Balance);
    assert(castOf(shift) && castOf(shift)->SpellId == M::CatFormSpell);
    // Readiness includes the global cooldown (published with the timers):
    // with the shapeshift on the GCD, Dash is out of reach this tick and a
    // strike held back for it would wait on a rejected cast.
    {
        Blackboard gcd = board;
        for (MechanicTimerSnapshot& timer : Member(gcd, Balance).MechanicTimers)
            if (timer.SpellId == M::CatFormSpell)
                timer.RemainingMs = 1200;
        assert(!castOf(Plan(gcd, Balance)));
        assert(M::ReadyAbilities(Member(gcd, Balance)).empty());
    }
    Member(board, Balance).Auras.push_back({ M::CatFormSpell, Member(board, Balance).Guid, 0, 0 });
    assert(castOf(Plan(board, Balance)) && castOf(Plan(board, Balance))->SpellId == M::DashSpell);

    // The Ice Block rescue. The mage (the gong backup) at its relay station
    // with Ice Block published ready takes the strike at contact.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    AddTimer(Member(board, Mage), M::IceBlockSpell, 0);
    AddTimer(Member(board, Mage), M::BlinkSpell, 0);
    duties = A::BuildDutyPlan(board);
    std::optional<A::ShieldFact> const station = A::AirRelayShieldFor(board,
        A::BuildFacts(board), duties, PlayerGuid(Mage));
    assert(station);
    Member(board, Mage).Position = A::AirStationPoint(*station);
    Member(board, Warlock).Position = { 110.0f, -271.0f, 75.0f };
    AddFlame(board, Member(board, Warlock), { 104.5f, -263.8f, 75.0f }, 6);
    facts = A::BuildFacts(board);
    A::GongDecision const ice = A::DecideGong(board, facts, duties);
    assert(ice.Required && ice.Reason == "air_ice_block_rescue");
    assert(ice.Clicker == PlayerGuid(Mage));
    assert(ClickOf(Plan(board, Mage)) && CountClicks(board) == 1);
    // Not assumed: without its published timer, or under Hypothermia, the
    // rescue is the ranked strike.
    {
        Blackboard unknown = board;
        Member(unknown, Mage).MechanicTimers.clear();
        assert(A::DecideGong(unknown, A::BuildFacts(unknown), duties).Reason == "air_breath_rescue");
        Blackboard cold = board;
        AddAura(Member(cold, Mage), A::HypothermiaAura, PlayerGuid(Mage));
        assert(A::DecideGong(cold, A::BuildFacts(cold), duties).Reason == "air_breath_rescue");
    }

    // Bait: the mage struck (newest Resonating Clash) and the flame is being
    // redirected: it holds still and stops casting, no Ice Block yet.
    board.Summons.back().Cast.reset();
    for (ActorSnapshot& player : board.Players)
        A::FindAura(player, A::TrackingAura) ? (void)player.Auras.clear() : (void)0;
    Member(board, Mage).Auras.push_back({ A::AirClashAura, station->Guid, 0,
        board.ObservedAtMs + 15000 });
    facts = A::BuildFacts(board);
    assert(facts.AirKiter.IsEmpty());
    AdaptiveAtramedesPlan bait = Plan(board, Mage);
    assert(!bait.Movement && !bait.Interaction);
    // Still casting at the boss: the survival Ice Block pre-empts it later.
    assert(!bait.SuppressOffense && bait.DamageTarget == Boss(board).Guid);
    // The flame has reached the shield and tracks the mage; 12 yd away: wait.
    ActorSnapshot& redirected = board.Summons.back();
    redirected.Position = G::PointAt(Member(board, Mage).Position, 0.0f, 12.0f, 75.0f);
    CastSnapshot channel;
    channel.SpellId = A::TrackingAura;
    channel.TargetGuid = PlayerGuid(Mage);
    channel.Channeled = true;
    redirected.Cast = channel;
    redirected.Auras.back().Stacks = 0;
    assert(A::BuildFacts(board).AirKiter == PlayerGuid(Mage));
    assert(!Plan(board, Mage).Interaction && !Plan(board, Mage).Movement);
    assert(CountClicks(board) == 0);
    // Close: Ice Block.
    redirected.Position = G::PointAt(Member(board, Mage).Position, 0.0f, 7.0f, 75.0f);
    AdaptiveAtramedesPlan block = Plan(board, Mage);
    assert(castOf(block) && castOf(block)->SpellId == M::IceBlockSpell && !block.Movement);
    assert(block.Interaction->ActionPriority == BotActionArbitration::Priority::Survival);

    // Iced: the block removed Tracking and ended the channel; the flame still
    // follows the mage (UntrackedAirKiter). Nobody strikes, the mage holds.
    redirected.Cast.reset();
    redirected.Position = Member(board, Mage).Position;
    Member(board, Mage).Auras.push_back({ A::IceBlockAura, PlayerGuid(Mage), 0, board.ObservedAtMs + 10000 });
    Member(board, Mage).Auras.push_back({ A::HypothermiaAura, PlayerGuid(Mage), 0, board.ObservedAtMs + 30000 });
    Member(board, Mage).MechanicTimers.front().RemainingMs = 300000;
    facts = A::BuildFacts(board);
    assert(facts.AirKiter == PlayerGuid(Mage) && facts.AirKiterUntracked);
    assert(A::KiterFlame(facts, Member(board, Mage)) == &board.Summons.back());
    assert(!A::DecideGong(board, facts, A::BuildDutyPlan(board)).Required);
    AdaptiveAtramedesPlan iced = Plan(board, Mage);
    assert(!iced.Movement && !iced.Interaction && iced.SuppressOffense);
    assert(CountClicks(board) == 0);

    // Out of the block with the flame (10 stacks) on it: Blink away at once,
    // and the strike is held back for it.
    Member(board, Mage).Auras.erase(std::remove_if(Member(board, Mage).Auras.begin(),
        Member(board, Mage).Auras.end(), [](AuraSnapshot const& aura)
        {
            return aura.SpellId == A::IceBlockAura || aura.SpellId == A::AirClashAura;
        }), Member(board, Mage).Auras.end());
    redirected.Auras.back().Stacks = 10;
    facts = A::BuildFacts(board);
    assert(facts.AirKiter == PlayerGuid(Mage) && facts.AirKiterUntracked);
    assert(A::DecideGong(board, facts, A::BuildDutyPlan(board)).Withheld == "kiter_mobility_extension");
    AdaptiveAtramedesPlan out = Plan(board, Mage);
    assert(leapOf(out) && leapOf(out)->SpellId == M::BlinkSpell);
    // A newer striker has the flame: the mage is no longer its target.
    Member(board, Warlock).Auras.push_back({ A::AirClashAura, station->Guid, 0,
        board.ObservedAtMs + 15000 });
    assert(A::BuildFacts(board).AirKiter.IsEmpty());

    // The chased mage itself with Ice Block ready: it blocks, no shield.
    board = AirBoard();
    for (ActorSnapshot& player : board.Players)
        player.Position = A::ArenaCenter;
    Member(board, Mage).Position = { 110.0f, -271.0f, 75.0f };
    AddTimer(Member(board, Mage), M::IceBlockSpell, 0);
    AddTimer(Member(board, Mage), M::BlinkSpell, 0);
    AddFlame(board, Member(board, Mage), { 107.0f, -271.0f, 75.0f }, 0);
    A::GongDecision const self = A::DecideGong(board, A::BuildFacts(board), A::BuildDutyPlan(board));
    assert(!self.Required && self.Withheld == "kiter_ice_block");
    AdaptiveAtramedesPlan selfBlock = Plan(board, Mage);
    assert(castOf(selfBlock) && castOf(selfBlock)->SpellId == M::IceBlockSpell);
    assert(!selfBlock.Movement && CountClicks(board) == 0);
}

// The user's air tactics (user raid experience, 2026-09-25) on the canonical
// roster with its mobility published as spell timers: every target, the
// flame spawned 7 s and 3 s after liftoff, the server stack cap.
//   ice:     the mage's Ice Block ready (the fight's first air phase);
//   no ice:  Ice Block and Dash cooling down (a later air phase);
//   no mage: the mage dead, so no Ice Block and no Blink.
// Each variant also runs as a second air phase, from the shields left after
// its first one and a ground Searing Flame.
// Bounds: at most 2 shields per 31 s air phase with the native 7 s spawn;
// with the 3 s stress spawn at most 3, and at least 90% of those runs at 2
// (a hunter caught before the relays reach their stations has only
// Disengage since Aspect of the Cheetah was dropped); the first catch
// within 3 s of contact and 4 ticks; later catches within 3 s and 2 s of
// breath (3 s spawn: 4 s and 4 s, when a chased mage with Blink spent has
// no relay in reach yet); nobody near 90 Sound; one click at a time. With Ice Block ready it
// is used at most once (the rescue strike, or the chased mage itself), the
// iced mage gains no Sound, and with the 7 s spawn the mage blinks out of
// the block (with the 3 s spawn it may not reach its station in time).
static void TestAirMobilityReplay()
{
    std::vector<uint32> const beforePhase1 = AfterGroundSearing(AllShieldIds(), 100.0f);
    int iceStrikes = 0;
    int runs = 0;
    int stressRuns = 0;
    int stressAtTwo = 0;
    for (int variant = 0; variant < 3; ++variant)
    {
        ReplayOptions options;
        options.Mobility = true;
        options.IceBlockReady = variant == 0;
        options.NoMage = variant == 2;
        options.DashRemainingMs = variant == 1 ? 56000 : 0;
        for (float delay : { 7.0f, 3.0f })
            for (uint32 slot = Tank; slot <= Warlock; ++slot)
            {
                if (options.NoMage && slot == Mage)
                    continue;
                AirReplay const first = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks),
                    delay, false, beforePhase1, 100.0f, 31.0f, options);
                ReplayOptions later = options;
                later.IceBlockReady = false;
                later.DashRemainingMs = 56000;
                std::vector<uint32> const second = AfterGroundSearing(first.ShieldsLeft, 60.0f);
                AirReplay const next = ReplayAirPhase(slot, float(A::BuildingSpeedMaxStacks),
                    delay, false, second, 60.0f, 31.0f, later);
                for (AirReplay const* run : { &first, &next })
                {
                    ++runs;
                    assert(run->Strikes >= 1 && run->Strikes <= (delay >= 7.0f ? 2 : 3));
                    if (delay < 7.0f)
                    {
                        ++stressRuns;
                        stressAtTwo += run->Strikes <= 2;
                    }
                    assert(!run->DoubleClick);
                    assert(run->FirstContactS >= 0.0f && run->FirstStrikeS >= 0.0f);
                    assert(run->FirstCatchDelayS <= 3.0f && run->FirstCatchTicks <= 4);
                    if (delay >= 7.0f)
                        assert(run->WorstSteadyDelayS <= 3.0f && run->MaxSteadyConsecutiveTicks <= 4);
                    else
                        assert(run->WorstSteadyDelayS <= 4.0f && run->MaxSteadyConsecutiveTicks <= 8);
                    assert(run->MaxSound < A::SoundEmergency);
                    assert(run->MageSoundWhileIced == 0);
                }
                assert(next.IceBlocks == 0 && next.IceStrikes == 0);
                if (variant == 0)
                {
                    // Once at most; with the 7 s spawn always (with the 3 s
                    // spawn the mage may not reach its station in time).
                    assert(first.IceBlocks <= 1 && first.IceStrikes <= 1);
                    assert(first.IceBlocks == 1 || delay < 7.0f);
                    assert(first.IceStrikes == 1 || slot == Mage || delay < 7.0f);
                    if (delay >= 7.0f)
                        assert(first.BlinkAfterIce);
                    iceStrikes += first.IceStrikes;
                }
                else
                    assert(first.IceBlocks == 0 && first.IceStrikes == 0);
                // The chased players use their mobility.
                assert(first.Extensions + next.Extensions >= 1);
            }
    }
    assert(iceStrikes >= 15);
    assert(stressAtTwo * 10 >= stressRuns * 9);
    std::printf("air mobility replay runs=%d ice_strikes=%d stress_at_two=%d/%d\n", runs,
        iceStrikes, stressAtTwo, stressRuns);
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
    // Melee hold a slot at maximum melee range (TestMeleeMaxRange).
    assert(Mechanic(Plan(board, Rogue)) == "melee_max_range");
}

// Melee at maximum range (user raid experience, 2026-09-25): Atramedes'
// combat reach is 20 (creature_model_info 34547), so melee range is
// 1.5 + 20 + 4/3 = 22.83 yd centre to centre. The slots stand 1.25 yd
// inside it, behind the boss, and a Sonar Pulse is dodged around the boss at
// the same distance, still in melee range.
static void TestMeleeMaxRange()
{
    assert(std::fabs(A::MeleeRangeYards - 22.8333f) < 0.001f);
    Blackboard board = Board();
    Vector3 const boss = Boss(board).Position;
    for (uint32 slot : { Retribution, Rogue })
    {
        AdaptiveAtramedesPlan const plan = Plan(board, slot);
        assert(Mechanic(plan) == "melee_max_range");
        assert(plan.Movement->ActionPriority == BotActionArbitration::Priority::Mechanic);
        Vector3 const at{ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f };
        float const range = G::Distance2d(boss, at);
        assert(range > A::MeleeRangeYards - 1.5f && range < A::MeleeRangeYards - 1.0f);
        // Behind the boss as seen from the tank (the tank is west of him).
        assert(at.X > boss.X);
        Member(board, slot).Position = at;
    }
    assert(G::Distance2d(Member(board, Retribution).Position, Member(board, Rogue).Position) > 6.0f);
    // At the slot: hold.
    assert(!Plan(board, Rogue).Movement);

    // A disk leaving the boss straight at the rogue: it steps around the boss
    // at its own distance, out of the lane and still in melee range.
    Vector3 const rogue = Member(board, Rogue).Position;
    float const lane = G::Bearing(boss, rogue);
    Vector3 const disk = G::PointAt(boss, lane, 4.0f, 75.0f);
    board.Summons.push_back(MakeUnit(A::SonarPulseEntry, 72, disk.X, disk.Y, ActorKind::Summon));
    AdaptiveAtramedesPlan const dodge = Plan(board, Rogue);
    assert(Mechanic(dodge) == "sonar_pulse_melee_exit");
    assert(dodge.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
    Vector3 const exit{ MoveOf(dodge)->X, MoveOf(dodge)->Y, 75.0f };
    assert(G::Distance2d(boss, exit) <= A::MeleeRangeYards - 1.0f);
    G::RayOffset const cleared = G::OffsetFromRay(disk, lane, exit);
    assert(cleared.Lateral >= A::SonarPulseRadius + A::HazardMargin);
    // The step is short: an arc of about 8 yd, not a run out of range.
    assert(G::Distance2d(rogue, exit) < 10.0f);
    // A ranged player in the same lane side-steps straight (no melee range
    // to keep), and a melee player already out of melee range does too.
    Member(board, Elemental).Position = G::PointAt(boss, lane, 30.0f, 75.0f);
    assert(Mechanic(Plan(board, Elemental)) == "sonar_pulse_exit");
    Member(board, Rogue).Position = G::PointAt(boss, lane, 30.0f, 75.0f);
    assert(Mechanic(Plan(board, Rogue)) == "sonar_pulse_exit");
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
    TestMeleeMaxRange();
    TestRound4BellStack();
    TestAirAbilities();
    TestAirMobilityReplay();
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
    # The strategy is header-only; the one translation unit is the kernel
    # adapter that carries the route's engagement edge
    # (tests/test_atramedes_route_observation.py).
    sources = [path.name for path in headers if path.suffix != ".h"]
    assert sources == ["BotWorldPopulationMgrAtramedesCandidates.cpp"], sources
    for path in headers:
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

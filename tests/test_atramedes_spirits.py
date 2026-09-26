"""Header-only decision tests for the Dark Iron spirit packs before Atramedes.

Round 2 wiped on bwd.atramedes.north_spirits: the whole raid stood inside
the four-spirit pack (ranged within 1-10 yd of every spirit for 60 s), every
Thunderclap (15 yd) hit about eight players, and Moltenfist died first, so
the other three gained Thunderclap. The C++ program below drives the
production headers with that geometry and checks the kill order, the ranged
standoff half circle and that the plan leaves the route in charge.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
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
#include <vector>

using namespace BotEncounter;
namespace A = BotEncounter::Atramedes;
namespace S = BotEncounter::Atramedes::Spirits;
namespace G = BotEncounter::Atramedes::Geometry;

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ObjectGuid UnitGuid(uint32 entry, uint32 counter) { return ObjectGuid(HighGuid::Unit, entry, counter); }

enum Slot : uint32
{
    Tank = 11003001, Balance, Hunter, Mage, HolyPaladin, Retribution,
    Discipline, Rogue, Elemental, Warlock
};

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
    return actor;
}

static ActorSnapshot MakeSpirit(uint32 entry, uint32 counter, float x, float y)
{
    ActorSnapshot actor;
    actor.Guid = UnitGuid(entry, counter);
    actor.Entry = entry;
    actor.Kind = ActorKind::Hostile;
    actor.Position = { x, y, 75.0f };
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    actor.InCombat = true;
    actor.VictimGuid = PlayerGuid(Tank);
    return actor;
}

// Round 2 geometry: bots provisioned on the pack centre (147.9, -189.3),
// spirits where the combat log saw them.
static Blackboard NorthBoard(bool engaged = true)
{
    Blackboard board;
    board.Route.NodeId = std::string(S::NorthNode);
    board.ObservedAtMs = 5000;
    board.Revision = 3;
    board.Players = {
        MakePlayer(Tank, "tank", "blood_death_knight", 148.0f, -189.0f),
        MakePlayer(Balance, "dps", "balance_druid", 154.0f, -186.0f),
        MakePlayer(Hunter, "dps", "survival_hunter", 154.0f, -186.0f),
        MakePlayer(Mage, "dps", "fire_mage", 154.0f, -186.0f),
        MakePlayer(HolyPaladin, "healer", "holy_paladin", 154.0f, -189.0f),
        MakePlayer(Retribution, "dps", "retribution_paladin", 148.0f, -189.0f),
        MakePlayer(Discipline, "healer", "discipline_priest", 154.0f, -189.0f),
        MakePlayer(Rogue, "dps", "assassination_rogue", 148.0f, -189.0f),
        MakePlayer(Elemental, "dps", "elemental_shaman", 148.0f, -189.0f),
        MakePlayer(Warlock, "dps", "demonology_warlock", 154.0f, -186.0f),
    };
    board.Hostiles = {
        MakeSpirit(S::Shadowforge, 56, 153.0f, -190.0f),
        MakeSpirit(S::Anvilrage, 55, 144.0f, -186.0f),
        MakeSpirit(S::Moltenfist, 21, 142.5f, -187.0f),
        MakeSpirit(S::Corehammer, 43, 152.5f, -192.5f),
    };
    for (ActorSnapshot& spirit : board.Hostiles)
        spirit.InCombat = engaged;
    return board;
}

static Blackboard SouthBoard()
{
    Blackboard board = NorthBoard();
    board.Route.NodeId = std::string(S::SouthNode);
    board.Hostiles = {
        MakeSpirit(S::Ironstar, 60, 142.0f, -257.0f),
        MakeSpirit(S::Burningeye, 61, 151.0f, -257.0f),
        MakeSpirit(S::Thaurissan, 62, 143.0f, -263.0f),
        MakeSpirit(S::Angerforge, 63, 152.0f, -262.0f),
    };
    for (ActorSnapshot& player : board.Players)
        player.Position = { 147.0f, -259.0f, 75.0f };
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

static ActorSnapshot& Spirit(Blackboard& board, uint32 entry)
{
    for (ActorSnapshot& hostile : board.Hostiles)
        if (hostile.Entry == entry)
            return hostile;
    assert(false);
    return board.Hostiles.front();
}

static AdaptiveAtramedesPlan Plan(Blackboard const& board, uint32 counter, char const* role = "dps")
{
    return AdaptiveAtramedesStrategy().Propose(board, PlayerGuid(counter), role);
}

static BotNativeAction::Move const* MoveOf(AdaptiveAtramedesPlan const& plan)
{
    return plan.Movement ? std::get_if<BotNativeAction::Move>(&plan.Movement->Action) : nullptr;
}

static std::string Mechanic(AdaptiveAtramedesPlan const& plan)
{
    return plan.Movement ? plan.Movement->Id.Mechanic : std::string();
}

static std::vector<uint32> const StandoffSlots{ Balance, Hunter, Mage, HolyPaladin,
    Discipline, Elemental, Warlock };

static void TestNothingBeforeThePull()
{
    Blackboard const board = NorthBoard(false);
    for (ActorSnapshot const& player : board.Players)
    {
        AdaptiveAtramedesPlan const plan = AdaptiveAtramedesStrategy().Propose(board,
            player.Guid, player.Role.c_str());
        assert(!plan.OwnsNode && plan.DamageTarget.IsEmpty() && !plan.Movement);
    }
    // Any other node (the regroup, the bell) is not a spirit node.
    Blackboard regroup = NorthBoard();
    regroup.Route.NodeId = "bwd.atramedes.regroup";
    assert(Plan(regroup, Mage).DamageTarget.IsEmpty() && !Plan(regroup, Mage).Movement);
}

static void TestNorthKillOrder()
{
    Blackboard board = NorthBoard();
    // The route keeps the node. The tank's target is the kill-order spirit:
    // on a trash route the shared group focus is the tank's own target
    // (FindValidationRouteGroupFocusTarget), so this is what the raid hits.
    AdaptiveAtramedesPlan const tank = Plan(board, Tank, "tank");
    assert(!tank.OwnsNode && !tank.Movement);
    assert(tank.DamageTarget == UnitGuid(S::Corehammer, 43));
    assert(tank.Duty == "spirit_tank");
    for (uint32 slot : { Balance, Hunter, Mage, Retribution, Rogue, Elemental, Warlock,
            HolyPaladin, Discipline })
        assert(Plan(board, slot).DamageTarget == UnitGuid(S::Corehammer, 43));
    // Corehammer first (Burden of the Crown then buffs the raid), Moltenfist
    // before Shadowforge so Chain Lightning is never handed on.
    Spirit(board, S::Corehammer).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Anvilrage, 55));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Anvilrage, 55));
    Spirit(board, S::Anvilrage).Alive = false;
    assert(Plan(board, Rogue).DamageTarget == UnitGuid(S::Moltenfist, 21));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Moltenfist, 21));
    Spirit(board, S::Moltenfist).Alive = false;
    assert(Plan(board, Warlock).DamageTarget == UnitGuid(S::Shadowforge, 56));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Shadowforge, 56));
    // The route's shared focus defers to the same target
    // (spirit_kill_order_focus.patch): empty off the spirit nodes and before
    // the pull.
    assert(S::OrderedKillTarget(board) == UnitGuid(S::Shadowforge, 56));
    assert(S::OrderedKillTarget(NorthBoard(false)).IsEmpty());
    {
        Blackboard regroup = NorthBoard();
        regroup.Route.NodeId = "bwd.atramedes.regroup";
        assert(S::OrderedKillTarget(regroup).IsEmpty());
    }
    // An unattackable spirit is skipped.
    board = NorthBoard();
    Spirit(board, S::Corehammer).Attackable = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Anvilrage, 55));
}

static void TestSouthKillOrder()
{
    Blackboard board = SouthBoard();
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Angerforge, 63));
    assert(Plan(board, Tank, "tank").DamageTarget == UnitGuid(S::Angerforge, 63));
    Spirit(board, S::Angerforge).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Thaurissan, 62));
    Spirit(board, S::Thaurissan).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Burningeye, 61));
    Spirit(board, S::Burningeye).Alive = false;
    assert(Plan(board, Mage).DamageTarget == UnitGuid(S::Ironstar, 60));
}

// Every standoff slot, for the round 2 geometry of each pack.
static void CheckSlots(Blackboard const& board, Vector3 const& otherPack)
{
    S::Pack const pack = S::BuildPack(board);
    std::vector<Vector3> slots;
    for (uint32 slot : StandoffSlots)
    {
        std::optional<Vector3> const at = S::StandoffSlot(board, pack, PlayerGuid(Tank),
            PlayerGuid(slot));
        assert(at);
        for (ActorSnapshot const* spirit : pack.Engaged)
        {
            float const distance = G::Distance2d(spirit->Position, *at);
            // Outside Thunderclap (15 yd + 1.5 player reach), inside 40 yd
            // spell range of every spirit.
            assert(distance >= S::DangerRadius);
            assert(distance >= S::ThunderclapRadius + 1.5f);
            assert(distance <= 38.0f);
        }
        // Far from the other pack (20 yd aggro + its 6 yd spread + margin)
        // and on the arena floor inside the shield ring.
        assert(G::Distance2d(*at, otherPack) >= 35.0f);
        assert(G::Distance2d(*at, A::ArenaCenter) <= 50.0f);
        slots.push_back(*at);
    }
    // Chain Lightning jumps 12.5 yd: no two ranged within that.
    for (std::size_t i = 0; i < slots.size(); ++i)
        for (std::size_t j = i + 1; j < slots.size(); ++j)
            assert(G::Distance2d(slots[i], slots[j]) > S::ChainJumpRadius);
}

static void TestStandoff()
{
    Blackboard board = NorthBoard();
    CheckSlots(board, { 146.87f, -259.78f, 75.0f });
    CheckSlots(SouthBoard(), { 147.92f, -189.29f, 75.0f });

    // Inside the pack (the round 2 positions): every ranged and healer leaves
    // with survival priority, pre-empting a cast.
    S::Pack const pack = S::BuildPack(board);
    for (uint32 slot : StandoffSlots)
    {
        AdaptiveAtramedesPlan const plan = Plan(board, slot,
            slot == HolyPaladin || slot == Discipline ? "healer" : "dps");
        assert(plan.Duty == "spirit_ranged");
        assert(Mechanic(plan) == "spirit_thunderclap_exit");
        assert(plan.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
        assert(MoveOf(plan)->PreemptCasting);
        std::optional<Vector3> const at = S::StandoffSlot(board, pack, PlayerGuid(Tank),
            PlayerGuid(slot));
        assert(G::Distance2d({ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f }, *at) < 0.01f);
    }
    // Melee stay in melee range.
    for (uint32 slot : { Retribution, Rogue })
    {
        AdaptiveAtramedesPlan const plan = Plan(board, slot);
        assert(plan.Duty == "spirit_melee" && !plan.Movement);
        assert(!plan.DamageTarget.IsEmpty());
    }

    // At the slot: hold (no move every decision).
    std::optional<Vector3> const mageSlot = S::StandoffSlot(board, pack, PlayerGuid(Tank),
        PlayerGuid(Mage));
    Member(board, Mage).Position = { mageSlot->X + 2.0f, mageSlot->Y, 75.0f };
    assert(!Plan(board, Mage).Movement);
    // Off the slot but outside the Thunderclap: a positioning move only.
    Member(board, Mage).Position = { mageSlot->X + 8.0f, mageSlot->Y, 75.0f };
    assert(S::NearestSpiritDistance(pack, Member(board, Mage).Position) >= S::DangerRadius);
    AdaptiveAtramedesPlan const drift = Plan(board, Mage);
    assert(Mechanic(drift) == "spirit_ranged_standoff");
    assert(drift.Movement->ActionPriority == BotActionArbitration::Priority::Mechanic);
    assert(!MoveOf(drift)->PreemptCasting);

    // Slots do not shift when a ranged dies.
    Member(board, Balance).Alive = false;
    std::optional<Vector3> const after = S::StandoffSlot(board, pack, PlayerGuid(Tank),
        PlayerGuid(Mage));
    assert(G::Distance2d(*after, *mageSlot) < 0.01f);
    // A dead bot plans nothing.
    assert(!Plan(board, Balance).Movement && Plan(board, Balance).DamageTarget.IsEmpty());
}

// Round 3: Burningeye died second and his Whirlwind (80652, 5 s, 80651
// every second, 56.5k) went to Thaurissan and Ironstar; the rogue and the
// retribution paladin stood in it and died, and their long runback stalled
// the route. 80651 reaches 4 yd (TargetB radius, 2D, no hitbox; the tank at
// 4.37-4.56 yd took 0 of 13 ticks) and melee range to a spirit is
// 1.5 + 3.375 + 4/3 = 6.21 yd: melee hold a 5.4 yd ring around their target,
// outside every pulse and still hitting; the tank stays.
static void AddWhirlwind(Blackboard const& board, ActorSnapshot& spirit)
{
    AuraSnapshot whirl;
    whirl.SpellId = S::WhirlwindAura;
    whirl.CasterGuid = spirit.Guid;
    whirl.ExpiresAtMs = board.ObservedAtMs + 5000;
    spirit.Auras.push_back(whirl);
}

static bool ClearOfWhirlwinds(Blackboard const& board, Vector3 const& point)
{
    for (ActorSnapshot const& spirit : board.Hostiles)
        for (AuraSnapshot const& aura : spirit.Auras)
            if (spirit.Alive && aura.SpellId == S::WhirlwindAura
                && G::Distance2d(spirit.Position, point) < S::WhirlwindClearYards)
                return false;
    return true;
}

static void TestWhirlwindExit()
{
    assert(S::WhirlwindRadius == 4.0f && S::ThunderclapRadius == 20.0f);
    assert(std::fabs(S::SpiritMeleeRange - 6.2083f) < 0.001f);
    assert(S::WhirlwindDangerYards > S::WhirlwindRadius);
    assert(S::WhirlwindClearYards > S::WhirlwindDangerYards);
    assert(S::WhirlwindHoldYards >= 5.25f && S::WhirlwindHoldYards <= 5.5f);
    assert(S::WhirlwindHoldYards < S::SpiritMeleeRange - 0.5f);

    // Burningeye whirlwinds beside the kill target (Angerforge, 5.1 yd away):
    // melee between them take the ring around Angerforge, clear of the pulse.
    Blackboard board = SouthBoard();
    ActorSnapshot& burningeye = Spirit(board, S::Burningeye);
    ActorSnapshot const& angerforge = Spirit(board, S::Angerforge);
    Member(board, Retribution).Position = { 151.5f, -259.5f, 75.0f };
    Member(board, Rogue).Position = { burningeye.Position.X + 2.0f, burningeye.Position.Y, 75.0f };
    Member(board, Tank).Position = { burningeye.Position.X - 2.0f, burningeye.Position.Y, 75.0f };
    assert(!Plan(board, Rogue).Movement && !Plan(board, Retribution).Movement);
    AddWhirlwind(board, burningeye);
    for (uint32 slot : { Retribution, Rogue })
    {
        AdaptiveAtramedesPlan const plan = Plan(board, slot);
        assert(Mechanic(plan) == "spirit_whirlwind_ring");
        assert(plan.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
        Vector3 const ring{ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f };
        assert(ClearOfWhirlwinds(board, ring));
        assert(G::Distance2d(ring, burningeye.Position) > S::WhirlwindRadius + 0.75f);
        float const reach = G::Distance2d(ring, angerforge.Position);
        assert(reach > S::WhirlwindHoldYards - 0.01f && reach < S::SpiritMeleeRange);
        assert(plan.DamageTarget == angerforge.Guid);
        // At the ring: no move (the native chase keeps it, in melee range).
        Member(board, slot).Position = ring;
        assert(!Plan(board, slot).Movement);
    }
    // Hysteresis: 4.8 yd from the pulse (outside the 4.75 trigger): hold.
    Member(board, Rogue).Position = G::PointAt(burningeye.Position,
        G::Bearing(burningeye.Position, angerforge.Position) + 1.2f, 4.8f, 75.0f);
    assert(!Plan(board, Rogue).Movement);
    // The tank holds the pack; Whirlwind over: back to native melee.
    assert(!Plan(board, Tank, "tank").Movement);
    burningeye.Auras.clear();
    Member(board, Retribution).Position = { burningeye.Position.X + 1.0f, burningeye.Position.Y, 75.0f };
    assert(!Plan(board, Retribution).Movement);

    // Round 3's case: Whirlwind handed on to Thaurissan (the kill target) and
    // Ironstar, 6.1 yd apart. From anywhere near them the ring point is clear
    // of both and in melee range of Thaurissan, and it holds (no ping-pong).
    board = SouthBoard();
    Spirit(board, S::Angerforge).Alive = false;
    Spirit(board, S::Burningeye).Alive = false;
    AddWhirlwind(board, Spirit(board, S::Thaurissan));
    AddWhirlwind(board, Spirit(board, S::Ironstar));
    ActorSnapshot const& thaurissan = Spirit(board, S::Thaurissan);
    int moves = 0;
    for (float x = 139.0f; x <= 146.0f; x += 1.0f)
        for (float y = -265.0f; y <= -255.0f; y += 1.0f)
        {
            Member(board, Rogue).Position = { x, y, 75.0f };
            AdaptiveAtramedesPlan const plan = Plan(board, Rogue);
            if (!plan.Movement)
            {
                // Clear, or between the trigger (4.75) and the clearance
                // (5.0): hold. Inside a pulse it always moves.
                ActorSnapshot const* ironstar = &Spirit(board, S::Ironstar);
                for (ActorSnapshot const* spirit : { &thaurissan, ironstar })
                    assert(G::Distance2d(spirit->Position, Member(board, Rogue).Position)
                        >= S::WhirlwindDangerYards);
                continue;
            }
            ++moves;
            assert(Mechanic(plan) == "spirit_whirlwind_ring");
            Vector3 const ring{ MoveOf(plan)->X, MoveOf(plan)->Y, 75.0f };
            assert(ClearOfWhirlwinds(board, ring));
            assert(G::Distance2d(ring, thaurissan.Position) < S::SpiritMeleeRange);
            Member(board, Rogue).Position = ring;
            assert(!Plan(board, Rogue).Movement);
        }
    assert(moves >= 20);

    // No clear ring point: three whirlwinding spirits 3 yd around the target
    // cover its whole 5.4 yd ring. Leave radially from their centroid, clear
    // of every pulse.
    board = SouthBoard();
    ActorSnapshot& target = Spirit(board, S::Angerforge);
    Vector3 const centre = target.Position;
    uint32 const others[] = { S::Thaurissan, S::Burningeye, S::Ironstar };
    for (int i = 0; i < 3; ++i)
    {
        ActorSnapshot& other = Spirit(board, others[i]);
        other.Position = G::PointAt(centre, float(i) * 2.0f * G::Pi / 3.0f, 3.0f, 75.0f);
        AddWhirlwind(board, other);
    }
    Member(board, Rogue).Position = G::PointAt(centre, 0.5f, 1.0f, 75.0f);
    AdaptiveAtramedesPlan const out = Plan(board, Rogue);
    assert(Mechanic(out) == "spirit_whirlwind_exit");
    Vector3 const exit{ MoveOf(out)->X, MoveOf(out)->Y, 75.0f };
    assert(ClearOfWhirlwinds(board, exit));
    Member(board, Rogue).Position = exit;
    assert(!Plan(board, Rogue).Movement);
}

// Round 5: the tank dragged the north pack 14 yd south, to about
// (150, -203); the fixed half circle toward the arena centre put both
// healers 26 yd from the idle south pack, which joined the fight
// (validation_route_future_encounter_contamination). The ring now keeps
// every ranged and healer slot 35 yd from every idle spirit.
static void TestStandoffAvoidsTheIdlePack()
{
    Blackboard board = NorthBoard();
    for (ActorSnapshot& spirit : board.Hostiles)
        spirit.Position = { spirit.Position.X + 2.0f, spirit.Position.Y - 13.0f, 75.0f };
    Blackboard const south = SouthBoard();
    for (ActorSnapshot spirit : south.Hostiles)
    {
        spirit.InCombat = false;
        board.Hostiles.push_back(spirit);
    }
    S::Pack const pack = S::BuildPack(board);
    assert(pack.Engaged.size() == 4 && pack.Idle.size() == 4);
    assert(S::IdleSafeYards >= 35.0f && S::StandoffRoomRadius <= 48.0f);
    std::vector<Vector3> slots;
    for (uint32 slot : StandoffSlots)
    {
        std::optional<Vector3> const at = S::StandoffSlot(board, pack, PlayerGuid(Tank),
            PlayerGuid(slot));
        assert(at);
        for (ActorSnapshot const* idle : pack.Idle)
            assert(G::Distance2d(idle->Position, *at) >= 35.0f);
        for (ActorSnapshot const* spirit : pack.Engaged)
        {
            float const distance = G::Distance2d(spirit->Position, *at);
            assert(distance >= S::DangerRadius && distance <= 38.0f);
        }
        assert(G::Distance2d(*at, A::ArenaCenter) <= 48.01f);
        slots.push_back(*at);
    }
    for (std::size_t i = 0; i < slots.size(); ++i)
        for (std::size_t j = i + 1; j < slots.size(); ++j)
            assert(G::Distance2d(slots[i], slots[j]) > S::ChainJumpRadius);
    // The healers leave the round 5 spots for them.
    Member(board, Discipline).Position = { 142.0f, -228.0f, 75.0f };
    AdaptiveAtramedesPlan const disc = Plan(board, Discipline, "healer");
    assert(disc.Movement);
    Vector3 const to{ MoveOf(disc)->X, MoveOf(disc)->Y, 75.0f };
    for (ActorSnapshot const* idle : pack.Idle)
        assert(G::Distance2d(idle->Position, to) >= 35.0f);
}

// Review of round 6: the 30 degree pass fell back to the nearest valid
// point, often one already taken; with the engaged pack dragged 24 yd some
// pair stood under 15 yd apart in 370 of 824 positions, down to 0 yd.
// Drag each pack +-24 yd in 2 yd steps, the other idle: while every engaged
// spirit is in the room, the seven slots are valid (off the pillar holes,
// 35 yd from the idle pack, outside Thunderclap, in spell range) and more
// than Chain Lightning's 12.5 yd jump apart. Dragged into the walls they
// stay valid and apart.
static void TestStandoffDragSweep()
{
    int inRoom = 0;
    for (int tankAlive = 0; tankAlive < 2; ++tankAlive)
    for (int north = 0; north < 2; ++north)
        for (int dx = -24; dx <= 24; dx += 2)
            for (int dy = -24; dy <= 24; dy += 2)
            {
                Blackboard board = north ? NorthBoard() : SouthBoard();
                bool room = true;
                for (ActorSnapshot& spirit : board.Hostiles)
                {
                    spirit.Position = { spirit.Position.X + float(dx),
                        spirit.Position.Y + float(dy), 75.0f };
                    room = room && G::Distance2d(spirit.Position, A::ArenaCenter) <= 48.0f;
                }
                // The tank drags the pack.
                Vector3& tank = Member(board, Tank).Position;
                tank = { tank.X + float(dx), tank.Y + float(dy), 75.0f };
                for (ActorSnapshot spirit : (north ? SouthBoard() : NorthBoard()).Hostiles)
                {
                    spirit.InCombat = false;
                    board.Hostiles.push_back(spirit);
                }
                S::Pack const pack = S::BuildPack(board);
                assert(pack.Engaged.size() == 4 && pack.Idle.size() == 4);
                // Heal reach: 38 yd of the living tank; with none, 33 yd of
                // the pack centre (the tank stands up to 5 yd beyond it).
                Member(board, Tank).Alive = tankAlive;
                S::HealReach const reach = S::HealReachFor(board, pack, PlayerGuid(Tank));
                Vector3 const anchor = tankAlive ? tank : pack.Center;
                assert(G::Distance2d(reach.Anchor, anchor) < 0.01f);
                assert(reach.Yards == (tankAlive ? 38.0f : 33.0f));
                std::vector<Vector3> const slots = S::StandoffSlots(pack, reach,
                    StandoffSlots.size());
                assert(slots.size() == StandoffSlots.size());
                std::optional<Vector3> const mage = S::StandoffSlot(board, pack,
                    PlayerGuid(Tank), PlayerGuid(Mage));
                assert(mage && G::Distance2d(*mage, slots[2]) < 0.01f);
                for (Vector3 const& at : slots)
                {
                    assert(A::ArenaFloor::Solid(at.X, at.Y));
                    // Healers keep the tank in heal range (40 yd + reaches).
                    assert(G::Distance2d(at, anchor) <= reach.Yards + 0.011f);
                    assert(G::Distance2d(at, A::ArenaCenter) <= 48.01f);
                    for (ActorSnapshot const* idle : pack.Idle)
                        assert(G::Distance2d(idle->Position, at) >= 35.0f);
                    for (ActorSnapshot const* spirit : pack.Engaged)
                    {
                        float const distance = G::Distance2d(spirit->Position, at);
                        assert(distance >= 21.5f && distance <= 40.0f);
                    }
                }
                for (std::size_t i = 0; i < slots.size(); ++i)
                    for (std::size_t j = i + 1; j < slots.size(); ++j)
                        assert(G::Distance2d(slots[i], slots[j]) > (room ? 12.5f : 7.0f));
                inRoom += room;
            }
    assert(inRoom >= 1500);
}

// Heal reach. Round 5's drag with the tank left 13 yd behind the pack
// (148, -189): every slot stays within 38 yd of it, still apart and clear
// of both packs. With the tank at the pack, as it drags, the bound leaves
// the ring layout alone.
static void TestStandoffHealReach()
{
    Blackboard board = NorthBoard();
    for (ActorSnapshot& spirit : board.Hostiles)
        spirit.Position = { spirit.Position.X + 2.0f, spirit.Position.Y - 13.0f, 75.0f };
    for (ActorSnapshot spirit : SouthBoard().Hostiles)
    {
        spirit.InCombat = false;
        board.Hostiles.push_back(spirit);
    }
    S::Pack const pack = S::BuildPack(board);
    Vector3 const behind = Member(board, Tank).Position;
    assert(G::Distance2d(behind, pack.Center) > 12.0f);
    std::vector<Vector3> const slots = S::StandoffSlots(pack,
        S::HealReachFor(board, pack, PlayerGuid(Tank)), StandoffSlots.size());
    S::HealReach unbounded{ behind, 1000.0f };
    bool moved = false;
    std::vector<Vector3> const loose = S::StandoffSlots(pack, unbounded, StandoffSlots.size());
    for (std::size_t i = 0; i < slots.size(); ++i)
    {
        assert(G::Distance2d(slots[i], behind) <= 38.01f);
        moved = moved || G::Distance2d(slots[i], loose[i]) > 0.01f;
        for (ActorSnapshot const* idle : pack.Idle)
            assert(G::Distance2d(idle->Position, slots[i]) >= 35.0f);
        for (std::size_t j = i + 1; j < slots.size(); ++j)
            assert(G::Distance2d(slots[i], slots[j]) > S::ChainJumpRadius);
    }
    // Unbounded, some slot would have been out of the tank's heal range.
    assert(moved);
    bool beyond = false;
    for (Vector3 const& at : loose)
        beyond = beyond || G::Distance2d(at, behind) > 38.01f;
    assert(beyond);

    // The tank at the dragged pack: the same layout as unbounded.
    Member(board, Tank).Position = pack.Center;
    std::vector<Vector3> const withTank = S::StandoffSlots(pack,
        S::HealReachFor(board, pack, PlayerGuid(Tank)), StandoffSlots.size());
    unbounded.Anchor = pack.Center;
    std::vector<Vector3> const free = S::StandoffSlots(pack, unbounded, StandoffSlots.size());
    for (std::size_t i = 0; i < withTank.size(); ++i)
        assert(G::Distance2d(withTank[i], free[i]) < 0.001f);

    // The main tank dead: the pack centre, 33 yd.
    Member(board, Tank).Alive = false;
    S::HealReach const none = S::HealReachFor(board, pack, PlayerGuid(Tank));
    assert(G::Distance2d(none.Anchor, pack.Center) < 0.01f && none.Yards == 33.0f);
    for (Vector3 const& at : S::StandoffSlots(pack, none, StandoffSlots.size()))
        assert(G::Distance2d(at, pack.Center) <= 33.01f);
}

// No valid point at all: two engaged spirits 81 yd apart on the south rim,
// so no point is within 40 yd of both. The slots come from the 30 yd ring
// around them, on the floor (in the room, off the pillar holes) and clear
// of both, never off the mesh.
static void TestStandoffWithNoValidPoint()
{
    Blackboard board = NorthBoard();
    board.Hostiles.resize(2);
    board.Hostiles[0].Position = G::PointAt(A::ArenaCenter, 208.0f * G::Pi / 180.0f, 46.0f, 75.0f);
    board.Hostiles[1].Position = G::PointAt(A::ArenaCenter, 332.0f * G::Pi / 180.0f, 46.0f, 75.0f);
    for (ActorSnapshot const& spirit : board.Hostiles)
        assert(A::ArenaFloor::Solid(spirit.Position.X, spirit.Position.Y));
    assert(G::Distance2d(board.Hostiles[0].Position, board.Hostiles[1].Position) > 81.0f);
    Member(board, Tank).Position = board.Hostiles[0].Position;
    S::Pack const pack = S::BuildPack(board);
    S::HealReach const reach = S::HealReachFor(board, pack, PlayerGuid(Tank));
    // The ring around the pair leaves the room to the south.
    bool offFloor = false;
    for (int step = 0; step < 180; ++step)
        offFloor = offFloor || !S::OnStandoffFloor(G::PointAt(pack.Center,
            float(step) * G::TwoPi / 180.0f, S::StandoffRadius, 75.0f));
    assert(offFloor);
    std::vector<Vector3> const slots = S::StandoffSlots(pack, reach, StandoffSlots.size());
    assert(slots.size() == StandoffSlots.size());
    for (std::size_t i = 0; i < slots.size(); ++i)
    {
        assert(!S::StandoffPointValid(pack, reach, slots[i]));
        assert(A::ArenaFloor::Solid(slots[i].X, slots[i].Y));
        assert(G::Distance2d(slots[i], A::ArenaCenter) <= 48.01f);
        assert(S::ClearOfSpirits(pack, slots[i]));
        for (std::size_t j = i + 1; j < slots.size(); ++j)
            assert(G::Distance2d(slots[i], slots[j]) > 5.0f);
    }
}

// Every ranged bot of a snapshot takes its slot from one layout: the
// cascade runs once per distinct input, and a hit is the cascade's answer.
static void TestStandoffSlotCache()
{
    Blackboard board = SouthBoard();
    for (ActorSnapshot& spirit : board.Hostiles)
        spirit.Position = { spirit.Position.X + 16.0f, spirit.Position.Y - 10.0f, 75.0f };
    for (ActorSnapshot spirit : NorthBoard().Hostiles)
    {
        spirit.InCombat = false;
        board.Hostiles.push_back(spirit);
    }
    S::StandoffSlotCache& cache = S::StandoffSlotCacheForThread();
    auto check = [&cache](Blackboard const& snapshot, uint64 misses)
    {
        S::Pack const pack = S::BuildPack(snapshot);
        std::vector<Vector3> const direct = S::StandoffSlots(pack,
            S::HealReachFor(snapshot, pack, PlayerGuid(Tank)), StandoffSlots.size());
        uint64 const before = cache.Misses;
        for (std::size_t i = 0; i < StandoffSlots.size(); ++i)
        {
            std::optional<Vector3> const at = S::StandoffSlot(snapshot, pack, PlayerGuid(Tank),
                PlayerGuid(StandoffSlots[i]));
            assert(at && G::Distance2d(*at, direct[i]) == 0.0f);
        }
        assert(cache.Misses - before == misses);
    };
    check(board, 1);
    // The same snapshot again: no cascade.
    check(board, 0);
    // Any input moved (an idle spirit by 0.01 yd, the tank): a new layout.
    board.Hostiles.back().Position.X += 0.01f;
    check(board, 1);
    Member(board, Tank).Position.Y -= 0.5f;
    check(board, 1);
    // More snapshots than entries, twice over: always the cascade's answer.
    std::vector<Blackboard> boards;
    for (int i = 1; i <= 11; ++i)
    {
        boards.push_back(board);
        for (ActorSnapshot& spirit : boards.back().Hostiles)
            if (spirit.InCombat)
                spirit.Position.X -= float(i);
    }
    for (int round = 0; round < 2; ++round)
        for (Blackboard const& snapshot : boards)
            check(snapshot, 1);
}

// Pillar holes: (176, -194) has no navmesh. A point beside it still has a
// bilinear height from the other three cells but is not a standoff point.
static void TestStandoffAvoidsPillarHoles()
{
    Blackboard const board = NorthBoard();
    S::Pack const pack = S::BuildPack(board);
    S::HealReach const reach = S::HealReachFor(board, pack, PlayerGuid(Tank));
    assert(A::ArenaFloor::Height(175.0f, -195.0f));
    assert(!A::ArenaFloor::Solid(175.0f, -195.0f));
    assert(!S::StandoffPointValid(pack, reach, { 175.0f, -195.0f, 75.0f }));
    assert(A::ArenaFloor::Solid(173.0f, -200.0f));
    assert(S::StandoffPointValid(pack, reach, { 173.0f, -200.0f, 75.0f }));
    // Nor off the table, where there is no floor at all.
    assert(!A::ArenaFloor::Solid(90.0f, -225.0f));
}

static void TestStrayPull()
{
    // A south spirit pulled during the north pack is danger and a target
    // after the north order.
    Blackboard board = NorthBoard();
    ActorSnapshot stray = SouthBoard().Hostiles.front();
    stray.Position = { 150.0f, -214.0f, 75.0f };
    board.Hostiles.push_back(stray);
    for (uint32 entry : S::NorthKillOrder)
        Spirit(board, entry).Alive = false;
    assert(Plan(board, Mage).DamageTarget == stray.Guid);
    Member(board, Mage).Position = { 151.0f, -210.0f, 75.0f };
    assert(Mechanic(Plan(board, Mage)) == "spirit_thunderclap_exit");
}

int main()
{
    TestNothingBeforeThePull();
    TestNorthKillOrder();
    TestSouthKillOrder();
    TestStandoff();
    TestWhirlwindExit();
    TestStandoffAvoidsTheIdlePack();
    TestStandoffDragSweep();
    TestStandoffHealReach();
    TestStandoffWithNoValidPoint();
    TestStandoffSlotCache();
    TestStandoffAvoidsPillarHoles();
    TestStrayPull();
    std::puts("atramedes spirits ok");
    return 0;
}
'''


def test_atramedes_spirit_packs(tmp_path: Path) -> None:
    source = tmp_path / "atramedes_spirits.cpp"
    binary = tmp_path / "atramedes_spirits"
    source.write_text(PROGRAM, encoding="utf-8")
    subprocess.run(["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-O0",
                    *INCLUDES, str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], check=True, cwd=ROOT, capture_output=True, text=True)
    assert "atramedes spirits ok" in result.stdout


def test_spirit_nodes_match_the_route_rows() -> None:
    import json

    scenarios = json.loads((ROOT / "experiments/configs/validation_scenarios_cata_001.json")
                           .read_text(encoding="utf-8"))
    header = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
              "Atramedes/BotAtramedesSpirits.h").read_text(encoding="utf-8")
    rows = [row for group in ("scenarios", "diagnostic_scenarios")
            for scenario in scenarios[group] for row in scenario.get("route") or []
            if str(row.get("node_id", "")).endswith("_spirits")
            and str(row.get("node_id", "")).startswith("bwd.atramedes.")]
    assert rows
    for row in rows:
        assert f'"{row["node_id"]}"' in header
        for entry in row["pack_target_entries"]:
            assert str(entry) in header


def test_spirit_ability_radii_match_the_client_rows() -> None:
    """80651 and 80649 hit with their TargetB radius (SpellEffectInfo::CalcRadius)."""
    import struct

    dbc = ROOT / "data/dbc/enUS"
    if not (dbc / "SpellEffect.dbc").is_file():
        import pytest
        pytest.skip("4.3.4 client DBC files are not extracted in this checkout")

    def rows(name: str) -> list[bytes]:
        data = (dbc / name).read_bytes()
        magic, count, fields, size, _ = struct.unpack_from("<4s4i", data)
        assert magic == b"WDBC" and size == fields * 4
        return [data[20 + i * size:20 + (i + 1) * size] for i in range(count)]

    def u32(row: bytes, index: int) -> int:
        return struct.unpack_from("<I", row, index * 4)[0]

    radii = {u32(row, 0): struct.unpack_from("<f", row, 4)[0] for row in rows("SpellRadius.dbc")}
    effects = {(u32(row, 24), u32(row, 25)): row for row in rows("SpellEffect.dbc")}
    header = (ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/"
              "Atramedes/BotAtramedesSpirits.h").read_text(encoding="utf-8")
    for spell, constant in ((80651, "WhirlwindRadius"), (80649, "ThunderclapRadius")):
        effect = effects[(spell, 0)]
        # TargetA 22 SRC_CASTER, TargetB 15 UNIT_SRC_AREA_ENEMY.
        assert (u32(effect, 22), u32(effect, 23)) == (22, 15)
        radius = radii[u32(effect, 16)]
        assert f"{constant} = {radius:.1f}f" in header
    assert radii[u32(effects[(80651, 0)], 16)] == 4.0
    assert radii[u32(effects[(80649, 0)], 16)] == 20.0

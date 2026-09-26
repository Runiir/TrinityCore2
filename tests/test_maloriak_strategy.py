"""Header-only replay of the adaptive Maloriak strategy decisions.

The program below builds cohort blackboards for the canonical BWD 10N
composition (Blood DK and Feral tanks, Holy Paladin and Discipline Priest
healers, Hunter, Mage, Retribution, Rogue, Elemental Shaman, Warlock) and
checks the duty, target and movement proposals phase by phase.
"""

from __future__ import annotations

import re
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

PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotAdaptiveMaloriakStrategy.h"
#include "Bots/BotWorldPopulationMgrRaidConsumables.h"
#include "Bots/BotEncounterLatches.h"
#include <cmath>
#include <cstdio>
#include <string>
#include <variant>

std::string ObjectGuid::ToString() const { return std::to_string(GetRawValue()); }

using namespace BotEncounter;
namespace M = BotEncounter::Maloriak;

static int failures = 0;
#define CHECK(condition) do { if (!(condition)) { std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, #condition); ++failures; } } while (0)

static ObjectGuid PlayerGuid(uint32 counter) { return ObjectGuid(HighGuid::Player, counter); }
static ObjectGuid UnitGuid(uint32 entry, uint32 counter) { return ObjectGuid(HighGuid::Unit, entry, counter); }

static Vector3 const BossAt{ -105.8f, -455.0f, 73.6f };

static ActorSnapshot Player(uint32 counter, char const* role, char const* spec, float x, float y)
{
    ActorSnapshot actor;
    actor.Guid = PlayerGuid(counter);
    actor.Kind = ActorKind::Player;
    actor.Role = role;
    actor.ClassSpec = spec;
    actor.Position = { x, y, 73.6f };
    actor.Alive = true;
    actor.Attackable = true;
    actor.Selectable = true;
    actor.HealthPct = 100.0f;
    actor.InCombat = true;
    return actor;
}

enum Slot { DK, FERAL, HUNTER, MAGE, HOLY, RET, DISC, ROGUE, SHAMAN, LOCK };

static Blackboard Canonical()
{
    Blackboard board;
    board.CurrentScope.CohortId = "blackwing_descent_10n_maloriak_c0";
    board.CurrentScope.AttemptId = 1;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.NodeId = "bwd.maloriak.encounter";
    board.Revision = 7;
    board.ObservedAtMs = 100000;
    board.NativeBossState = "in_progress";
    board.Route.NodeId = "bwd.maloriak.encounter";
    board.Players = {
        Player(30401, "tank", "blood_death_knight", -105.8f, -452.0f),
        Player(30402, "tank", "feral_druid_tank", -130.0f, -434.0f),
        Player(30403, "dps", "beast_mastery_hunter", -115.0f, -437.0f),
        Player(30404, "dps", "fire_mage", -108.0f, -436.0f),
        Player(30405, "healer", "holy_paladin", -100.0f, -437.0f),
        Player(30406, "dps", "retribution_paladin", -103.0f, -457.0f),
        Player(30407, "healer", "discipline_priest", -95.0f, -440.0f),
        Player(30408, "dps", "assassination_rogue", -108.5f, -457.5f),
        Player(30409, "dps", "elemental_shaman", -120.0f, -445.0f),
        Player(30410, "dps", "demonology_warlock", -90.0f, -445.0f),
    };
    ActorSnapshot boss;
    boss.Guid = UnitGuid(41378, 69);
    boss.Entry = 41378;
    boss.Kind = ActorKind::Hostile;
    boss.Position = BossAt;
    boss.Facing = 1.5708f;
    boss.Alive = true;
    boss.Attackable = true;
    boss.Selectable = true;
    boss.InCombat = true;
    boss.ReactAggressive = true;
    boss.HealthPct = 80.0f;
    boss.VictimGuid = PlayerGuid(30401);
    board.Hostiles = { boss };
    return board;
}

static ActorSnapshot& Boss(Blackboard& board) { return board.Hostiles.front(); }
static ObjectGuid G(Slot slot) { return PlayerGuid(30401 + uint32(slot)); }

static ActorSnapshot Add(uint32 entry, uint32 counter, float x, float y, bool selectable, float health)
{
    ActorSnapshot actor;
    actor.Guid = UnitGuid(entry, counter);
    actor.Entry = entry;
    actor.Kind = ActorKind::Summon;
    actor.Position = { x, y, 73.6f };
    actor.Alive = true;
    actor.Selectable = selectable;
    actor.Attackable = selectable;
    actor.HealthPct = health;
    actor.InCombat = selectable;
    return actor;
}

static AdaptiveMaloriakPlan Plan(Blackboard const& board, Slot slot,
    EncounterLatchView const* latches = nullptr)
{
    AdaptiveMaloriakStrategy strategy;
    return strategy.Propose(board, G(slot), board.Players[slot].Role, latches);
}

// The cohort publisher: a new revision, then one latch update from it.
[[maybe_unused]] static void Publish(Blackboard& board, EncounterLatchStore& store, uint64 stepMs = 0)
{
    board.Revision += 1;
    board.ObservedAtMs += stepMs;
    store.BeginPublication(EncounterLatchScopeKey(board.CurrentScope.Key(),
        board.CurrentScope.ServerEpoch, board.CurrentScope.EncounterEpoch),
        board.Revision, board.ObservedAtMs);
    if (board.Route.NodeId == M::EncounterNode)
        M::UpdateEncounterLatches(board, store.Module(M::LatchModule));
}

static Vector3 Destination(AdaptiveMaloriakPlan const& plan)
{
    if (!plan.Movement)
        return Vector3{ 9999.0f, 9999.0f, 0.0f };
    auto const* move = std::get_if<BotNativeAction::Move>(&plan.Movement->Action);
    return move ? Vector3{ move->X, move->Y, move->Z } : Vector3{};
}

static float Dist(Vector3 const& a, Vector3 const& b) { return M::Distance2d(a, b); }

// Angle in degrees between the boss front (toward the Blood DK) and a point.
static float AngleFromFront(Blackboard const& board, Vector3 const& point)
{
    Vector3 const tank = board.Players[DK].Position;
    float const ux = tank.X - BossAt.X, uy = tank.Y - BossAt.Y;
    float const px = point.X - BossAt.X, py = point.Y - BossAt.Y;
    float const dot = (ux * px + uy * py) / (std::sqrt(ux * ux + uy * uy) * std::sqrt(px * px + py * py));
    return std::acos(std::fmax(-1.0f, std::fmin(1.0f, dot))) * 180.0f / 3.14159265f;
}

static bool Interrupts(Blackboard const& board, Slot slot, uint32 spellId)
{
    AdaptiveMaloriakPlan const plan = Plan(board, slot);
    return plan.InterruptTarget == Boss(const_cast<Blackboard&>(board)).Guid && plan.InterruptSpellId == spellId;
}

int main()
{
    // Route gate: the lab trash node is not the encounter.
    {
        Blackboard board = Canonical();
        board.Route.NodeId = "bwd.maloriak.lab_trash";
        CHECK(!Plan(board, MAGE).OwnsNode);
    }

    // Pre-pull: only the Blood DK pulls; the raid holds on the entrance
    // line outside aggro range, the Feral tank waits at the add spot.
    {
        Blackboard board = Canonical();
        board.NativeBossState = "not_in_progress";
        Boss(board).InCombat = false;
        Boss(board).VictimGuid = ObjectGuid();
        Boss(board).Position = { -105.79f, -462.58f, 73.54f };
        // The pull waits until the raid stands on the entrance line.
        board.Players[HOLY].Position = { -105.0f, -380.0f, 76.8f };
        AdaptiveMaloriakPlan const hold = Plan(board, DK);
        CHECK(hold.OwnsNode && hold.SuppressOffense && hold.DamageTarget.IsEmpty());
        CHECK(std::string(hold.SuppressReason) == "prepull_formation_staging");
        {
            std::vector<ActorSnapshot*> nonTanks;
            for (ActorSnapshot& player : board.Players)
                if (player.Role != "tank")
                    nonTanks.push_back(&player);
            for (std::size_t index = 0; index < nonTanks.size(); ++index)
                nonTanks[index]->Position = M::StagingSlot(index, nonTanks.size());
        }
        AdaptiveMaloriakPlan const tank = Plan(board, DK);
        CHECK(tank.OwnsNode && !tank.SuppressOffense);
        CHECK(tank.DamageTarget == Boss(board).Guid);
        CHECK(std::string(tank.Duty) == "pull_tank");
        // Round 3: the shared pre-pot stage (PrepotStageReady) opens only on
        // an unsuppressed pull owner or on "prepull_pull_owner_wait". Every
        // holder reports the closed pull gate, so no 25 s potion is spent
        // while the raid is still dead, healing or off the entrance line.
        {
            auto prepotReady = [&board](Slot slot)
            {
                AdaptiveMaloriakPlan const plan = Plan(board, slot);
                return BotWorldPopulationMgrRaidConsumables::PrepotStageReady(
                    plan.OwnsNode, plan.SuppressOffense, plan.SuppressReason);
            };
            for (Slot slot : { DK, FERAL, HUNTER, HOLY, ROGUE, LOCK })
            {
                CHECK(prepotReady(slot));
                if (slot != DK)
                    CHECK(std::string(Plan(board, slot).SuppressReason) == "prepull_pull_owner_wait");
            }
            board.Route.PullPermitted = false;
            for (Slot slot : { DK, FERAL, MAGE, DISC })
            {
                CHECK(!prepotReady(slot));
                CHECK(std::string(Plan(board, slot).SuppressReason) == "prepull_pull_timer_wait");
            }
            board.Route.PullPermitted = true;
            board.Players[RET].HealthPct = 60.0f;
            for (Slot slot : { DK, SHAMAN, HOLY })
            {
                CHECK(!prepotReady(slot));
                CHECK(std::string(Plan(board, slot).SuppressReason) == "prepull_health_recovery");
            }
            board.Players[RET].HealthPct = 100.0f;
            for (Slot slot : { DK, FERAL, RET })
                CHECK(prepotReady(slot));
        }
        board.Route.PullPermitted = false;
        CHECK(std::string(Plan(board, DK).SuppressReason) == "prepull_pull_timer_wait");
        board.Route.PullPermitted = true;
        board.Players[LOCK].HealthPct = 50.0f;
        CHECK(std::string(Plan(board, DK).SuppressReason) == "prepull_health_recovery");
        board.Players[LOCK].HealthPct = 100.0f;
        board.Players[LOCK].Alive = false;
        CHECK(std::string(Plan(board, DK).SuppressReason) == "prepull_raid_dead_wait");
        CHECK(std::string(Plan(board, MAGE).SuppressReason) == "prepull_raid_dead_wait");
        board.Players[LOCK].Alive = true;
        std::vector<Vector3> staged;
        for (Slot slot : { HUNTER, MAGE, HOLY, RET, DISC, ROGUE, SHAMAN, LOCK })
        {
            board.Players[slot].Position = { -105.0f, -415.0f, 77.0f };
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(plan.SuppressOffense && plan.DamageTarget.IsEmpty());
            CHECK(std::string(plan.SuppressReason) == "prepull_formation_staging");
            CHECK(!BotWorldPopulationMgrRaidConsumables::PrepotStageReady(
                plan.OwnsNode, plan.SuppressOffense, plan.SuppressReason));
            CHECK(plan.Movement.has_value());
            Vector3 const at = Destination(plan);
            CHECK(Dist(at, Boss(board).Position) > 27.0f);
            for (Vector3 const& other : staged)
                CHECK(Dist(at, other) > 3.9f);
            staged.push_back(at);
        }
        AdaptiveMaloriakPlan const feral = Plan(board, FERAL);
        CHECK(feral.SuppressOffense);
        board.Players[FERAL].Position = { -105.0f, -415.0f, 77.0f };
        AdaptiveMaloriakPlan const feralMoving = Plan(board, FERAL);
        CHECK(feralMoving.Movement.has_value());
        CHECK(Dist(Destination(feralMoving), M::AddAnchorWest) < 0.01f);
    }

    // Arcane Storm: the lowest-GUID short melee interrupter owns the cast,
    // the next joins after 0.8 s of channel, everyone capable after 2 s.
    {
        Blackboard board = Canonical();
        Boss(board).Cast = CastSnapshot{ 77896, ObjectGuid(), board.ObservedAtMs, false, true };
        CHECK(Interrupts(board, RET, 77896));
        CHECK(!Interrupts(board, ROGUE, 77896));
        CHECK(!Interrupts(board, SHAMAN, 77896));
        CHECK(!Interrupts(board, MAGE, 77896));
        CHECK(std::string(Plan(board, RET).InterruptLane) == "arcane_storm");
        Boss(board).Auras.push_back({ 77896, Boss(board).Guid, 1, board.ObservedAtMs + 5000 });
        CHECK(Interrupts(board, RET, 77896) && Interrupts(board, ROGUE, 77896));
        CHECK(!Interrupts(board, SHAMAN, 77896));
        Boss(board).Auras.back().ExpiresAtMs = board.ObservedAtMs + 3500;
        CHECK(Interrupts(board, SHAMAN, 77896) && Interrupts(board, DK, 77896));
        CHECK(Interrupts(board, MAGE, 77896));
        CHECK(!Interrupts(board, HUNTER, 77896));
        CHECK(!Interrupts(board, HOLY, 77896));
        // A frozen or out-of-reach interrupter is skipped.
        Boss(board).Auras.back().ExpiresAtMs = board.ObservedAtMs + 6000;
        board.Players[RET].Auras.push_back({ 77699, ObjectGuid(), 1, board.ObservedAtMs + 20000 });
        CHECK(Interrupts(board, ROGUE, 77896));
        board.Players[RET].Auras.clear();
        board.Players[RET].Position = { -105.8f, -430.0f, 73.6f };
        CHECK(Interrupts(board, ROGUE, 77896) && !Interrupts(board, RET, 77896));
    }

    // User tactic (2026-09-26): Release Aberrations is never interrupted,
    // however many Aberrations are loose; every release is admitted (the
    // dispatch vetoes generic interrupts of it) in phase one.
    {
        Blackboard board = Canonical();
        Boss(board).Cast = CastSnapshot{ 77569, ObjectGuid(), board.ObservedAtMs, false, true };
        for (uint32 index = 0; index < 18; ++index)
            board.Summons.push_back(Add(41440, 200 + index, -140.0f, -430.0f, index < 3, 100.0f));
        for (Slot slot : { DK, FERAL, HUNTER, MAGE, RET, ROGUE, SHAMAN, LOCK, HOLY, DISC })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(!plan.InterruptTarget && !plan.InterruptSpellId);
            CHECK(plan.ReleaseAdmitted);
        }
        for (uint32 index = 3; index < 12; ++index)
            board.Summons[index].Selectable = board.Summons[index].Attackable = true;
        for (Slot slot : { RET, ROGUE, SHAMAN, MAGE })
            CHECK(!Interrupts(board, slot, 77569) && Plan(board, slot).ReleaseAdmitted);
        // Heroic Dark phase with Vile Swills: still never interrupted.
        Boss(board).Auras.push_back({ 92716, Boss(board).Guid, 1, 0 });
        board.Summons.push_back(Add(49811, 900, -120.0f, -440.0f, true, 100.0f));
        CHECK(!Interrupts(board, ROGUE, 77569));
        // Arcane Storm is the boss's own cast and is still interrupted.
        board.Summons.pop_back();
        Boss(board).Auras.pop_back();
        Boss(board).Cast = CastSnapshot{ 77896, ObjectGuid(), board.ObservedAtMs, false, true };
        CHECK(Interrupts(board, RET, 77896));
        // Phase two admits nothing (Release All Minions is not interruptible).
        Boss(board).Cast.reset();
        Boss(board).HealthPct = 24.0f;
        CHECK(!Plan(board, MAGE).ReleaseAdmitted);
    }

    // Remedy: Spellsteal first, Purge after 1.5 s, every dispeller after 3 s.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 77912, Boss(board).Guid, 1, board.ObservedAtMs + 9500 });
        CHECK(Plan(board, MAGE).DispelTarget == Boss(board).Guid);
        CHECK(!Plan(board, SHAMAN).DispelTarget);
        Boss(board).Auras.back().ExpiresAtMs = board.ObservedAtMs + 8000;
        CHECK(Plan(board, SHAMAN).DispelTarget == Boss(board).Guid);
        CHECK(!Plan(board, HUNTER).DispelTarget);
        Boss(board).Auras.back().ExpiresAtMs = board.ObservedAtMs + 6500;
        CHECK(Plan(board, HUNTER).DispelTarget == Boss(board).Guid);
        CHECK(Plan(board, DISC).DispelTarget == Boss(board).Guid);
        CHECK(!Plan(board, LOCK).DispelTarget);
        CHECK(!Plan(board, ROGUE).DispelTarget);
    }

    // Red: everyone but a Consuming Flames target stacks inside the
    // Scorching Blast cone in front of the boss.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78896, Boss(board).Guid, 1, board.ObservedAtMs + 30000 });
        CHECK(std::string(Plan(board, MAGE).Phase) == "red");
        for (Slot slot : { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK, RET, ROGUE })
        {
            board.Players[slot].Position = { -105.8f, -475.0f, 73.6f };
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(plan.Movement.has_value());
            CHECK(plan.Movement->Id.Mechanic == "red_cone_stack");
            CHECK(plan.Movement->ActionPriority == BotActionArbitration::Priority::Mechanic);
            CHECK(AngleFromFront(board, Destination(plan)) < 30.0f);
        }
        board.Players[MAGE].Auras.push_back({ 77786, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        AdaptiveMaloriakPlan const flames = Plan(board, MAGE);
        CHECK(flames.Movement && flames.Movement->Id.Mechanic == "consuming_flames_leave_cone");
        CHECK(AngleFromFront(board, Destination(flames)) > 150.0f);
        // A ranged player already in its slot keeps casting.
        board.Players[MAGE].Auras.clear();
        board.Players[MAGE].Position = Destination(Plan(board, MAGE));
        CHECK(!Plan(board, MAGE).Movement);
    }

    // Blue: the raid spreads behind the boss at least five yards apart;
    // ranged damage dealers break Flash Freeze, others clear the shatter.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, board.ObservedAtMs + 30000 });
        std::vector<Vector3> slots;
        for (Slot slot : { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK, RET, ROGUE })
        {
            Vector3 const home = board.Players[slot].Position;
            board.Players[slot].Position = { -105.8f, -430.0f, 73.6f };
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            board.Players[slot].Position = home;
            CHECK(plan.Movement && plan.Movement->Id.Mechanic == "blue_spread");
            Vector3 const at = Destination(plan);
            CHECK(AngleFromFront(board, at) > 75.0f);
            CHECK(Dist(at, board.Players[DK].Position) > 5.0f);
            for (Vector3 const& other : slots)
                CHECK(Dist(at, other) > 5.0f);
            slots.push_back(at);
        }
        ActorSnapshot block = Add(41576, 300, -108.0f, -436.0f, true, 100.0f);
        board.Summons.push_back(block);
        board.Players[MAGE].Auras.push_back({ 77699, Boss(board).Guid, 1, board.ObservedAtMs + 30000 });
        board.Players[MAGE].HealthPct = 40.0f;
        AdaptiveMaloriakPlan const frozen = Plan(board, MAGE);
        CHECK(frozen.OwnsNode && frozen.DamageTarget.IsEmpty() && !frozen.Movement);
        CHECK(std::string(frozen.Duty) == "flash_frozen");
        for (Slot slot : { HUNTER, SHAMAN, LOCK })
            CHECK(Plan(board, slot).DamageTarget == block.Guid);
        CHECK(Plan(board, ROGUE).DamageTarget == Boss(board).Guid);
        CHECK(Plan(board, HOLY).PriorityHealTarget == G(MAGE));
        CHECK(!Plan(board, DISC).PriorityHealTarget);  // one spot healer
        board.Players[DK].HealthPct = 40.0f;
        CHECK(!Plan(board, HOLY).PriorityHealTarget);  // a low tank comes first
        board.Players[DK].HealthPct = 100.0f;
        board.Players[LOCK].HealthPct = 20.0f;
        CHECK(!Plan(board, HOLY).PriorityHealTarget);  // someone clearly lower
        board.Players[LOCK].HealthPct = 100.0f;
        board.Players[DISC].Position = { -106.0f, -433.0f, 73.6f };
        AdaptiveMaloriakPlan const clear = Plan(board, DISC);
        CHECK(clear.Movement && clear.Movement->Id.Mechanic == "flash_freeze_shatter_clearance");
        CHECK(Dist(Destination(clear), block.Position) >= 7.9f);
        // Biting Chill: step away from the nearest ally.
        board.Players[ROGUE].Auras.push_back({ 77760, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        board.Players[RET].Position = { -107.0f, -457.0f, 73.6f };
        AdaptiveMaloriakPlan const chill = Plan(board, ROGUE);
        CHECK(chill.Movement && chill.Movement->Id.Mechanic == "biting_chill_isolation");
    }

    // Add control: Aberrations are burned as they come (in the slime window
    // too), the off-tank picks up and taunts loose adds, then kites them.
    {
        Blackboard board = Canonical();
        board.Summons.push_back(Add(41440, 401, -128.0f, -436.0f, true, 80.0f));
        board.Summons.push_back(Add(41440, 402, -129.0f, -433.0f, true, 50.0f));
        board.Summons.push_back(Add(41440, 403, -131.0f, -435.0f, true, 90.0f));
        for (ActorSnapshot& add : board.Summons)
            add.VictimGuid = G(FERAL);
        // Green in 10 s: no wait, the weakest is burned now.
        Boss(board).MechanicTimers.push_back({ 77937, 10000, false, FactSource::NativeInstanceState });
        CHECK(Plan(board, MAGE).DamageTarget == board.Summons[1].Guid);
        CHECK(std::string(Plan(board, MAGE).Duty) == "aberration_burn");
        Boss(board).MechanicTimers.clear();
        Boss(board).Auras.push_back({ 92917, Boss(board).Guid, 1, board.ObservedAtMs + 30000 });
        Boss(board).Auras.push_back({ 77615, ObjectGuid(), 1, board.ObservedAtMs + 14000 });
        AdaptiveMaloriakPlan const burn = Plan(board, MAGE);
        CHECK(burn.DamageTarget == board.Summons[1].Guid);
        CHECK(std::string(burn.Duty) == "aberration_slime_burn");
        CHECK(Plan(board, ROGUE).DamageTarget == board.Summons[1].Guid);
        CHECK(!Plan(board, ROGUE).Movement);
        // Holding them at the add spot, the off-tank kites: off the loop it
        // joins it first (review item 9: kite at the anchor).
        AdaptiveMaloriakPlan const hold = Plan(board, FERAL);
        CHECK(std::string(hold.Duty) == "off_tank_kite");
        CHECK(hold.DamageTarget == board.Summons[1].Guid && !hold.TauntTarget);
        CHECK(hold.Movement && hold.Movement->Id.Mechanic == "off_tank_kite");
        CHECK(Dist(Destination(hold), M::KiteLoopWest[0]) < 0.01f);
        board.Players[FERAL].Position = { -105.0f, -440.0f, 73.6f };
        AdaptiveMaloriakPlan const drag = Plan(board, FERAL);
        CHECK(drag.Movement && drag.Movement->Id.Mechanic == "off_tank_kite");
        board.Summons[2].VictimGuid = G(HOLY);
        AdaptiveMaloriakPlan const pickup = Plan(board, FERAL);
        CHECK(std::string(pickup.Duty) == "off_tank_pickup");
        CHECK(pickup.DamageTarget == board.Summons[2].Guid && pickup.TauntTarget == board.Summons[2].Guid);
    }

    // Idle off-tank waits at the add spot while chamber creatures remain;
    // a passive (cauldron-walking) boss suspends the formations.
    {
        Blackboard board = Canonical();
        board.Summons.push_back(Add(41440, 450, -140.0f, -430.0f, false, 100.0f));
        board.Players[FERAL].Position = { -105.0f, -440.0f, 73.6f };
        AdaptiveMaloriakPlan const wait = Plan(board, FERAL);
        CHECK(wait.SuppressOffense && std::string(wait.Duty) == "off_tank_add_spot_wait");
        CHECK(wait.Movement && wait.Movement->Id.Mechanic == "off_tank_add_anchor");
        board.Summons.clear();
        AdaptiveMaloriakPlan const assist = Plan(board, FERAL);
        CHECK(!assist.SuppressOffense && assist.DamageTarget == Boss(board).Guid);
        Boss(board).Auras.push_back({ 78896, Boss(board).Guid, 1, board.ObservedAtMs + 1000 });
        board.Players[MAGE].Position = { -105.8f, -475.0f, 73.6f };
        CHECK(Plan(board, MAGE).Movement.has_value());
        Boss(board).ReactAggressive = false;
        CHECK(!Plan(board, MAGE).Movement);
    }

    // Each Aberration is killed as it comes (user tactic), with no wait for
    // Green (review item 10: burn before Green).
    {
        Blackboard board = Canonical();
        board.Summons.push_back(Add(41440, 500, -130.0f, -434.0f, true, 100.0f));
        CHECK(Plan(board, LOCK).DamageTarget == board.Summons.back().Guid);
        CHECK(std::string(Plan(board, LOCK).Duty) == "aberration_burn");
        for (uint32 index = 1; index < 5; ++index)
            board.Summons.push_back(Add(41440, 500 + index, -130.0f, -434.0f, true, 100.0f - index));
        CHECK(Plan(board, LOCK).DamageTarget == board.Summons[4].Guid);
        Boss(board).MechanicTimers.push_back({ 77937, 10000, false, FactSource::NativeInstanceState });
        CHECK(Plan(board, LOCK).DamageTarget == board.Summons[4].Guid);
        Boss(board).MechanicTimers.clear();
        // A leaping Aberration (released, still immune) is not a target yet.
        for (ActorSnapshot& add : board.Summons)
            add.Attackable = false;
        CHECK(Plan(board, LOCK).DamageTarget == Boss(board).Guid);
    }

    // User tactic (2026-09-26): the hard switch at 30%. Every damage dealer
    // leaves the boss for the Aberrations until the chambers are empty and
    // the loose ones are dead; the Blood DK main tank keeps full damage;
    // nobody dispels Remedy during the switch; afterwards Remedy is dispelled
    // again and the raid burns.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        for (uint32 index = 0; index < 18; ++index)
            board.Summons.push_back(Add(41440, 1000 + index, -140.0f, -430.0f, false, 100.0f));
        // 31%: no switch; damage dealers stay on the boss, Remedy is stolen.
        Boss(board).HealthPct = 31.0f;
        Boss(board).Auras.push_back({ 77912, Boss(board).Guid, 1, board.ObservedAtMs + 9500 });
        AdaptiveMaloriakPlan const before = Plan(board, MAGE);
        CHECK(!before.AddSwitchWindow && !before.AddSwitchRestricts);
        CHECK(before.DamageTarget == Boss(board).Guid && !before.SuppressOffense);
        CHECK(before.DispelTarget == Boss(board).Guid);

        // 30% with 12 in the chambers and three loose: every damage dealer on
        // the adds, the DK on the boss, nobody on Remedy (every dispeller,
        // even after 3 s).
        Boss(board).HealthPct = 30.0f;
        Boss(board).Auras.back().ExpiresAtMs = board.ObservedAtMs + 5000;
        for (uint32 index = 0; index < 6; ++index)
            board.Summons[index].Alive = index >= 3;
        for (uint32 index = 3; index < 6; ++index)
            board.Summons[index].Selectable = board.Summons[index].Attackable = true;
        CHECK(M::Observe(board).ReserveAberrations == 12);
        for (Slot slot : { HUNTER, MAGE, RET, ROGUE, SHAMAN, LOCK })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(plan.AddSwitchWindow && plan.AddSwitchRestricts);
            CHECK(plan.DamageTarget != Boss(board).Guid);
            CHECK(plan.DamageTarget == board.Summons[3].Guid
                || plan.DamageTarget == board.Summons[4].Guid
                || plan.DamageTarget == board.Summons[5].Guid);
            CHECK(!plan.SuppressOffense);
            CHECK(std::string(plan.Duty) == "aberration_burn");
        }
        for (Slot slot : { HUNTER, MAGE, SHAMAN, DISC, HOLY, RET, ROGUE, LOCK, FERAL, DK })
            CHECK(!Plan(board, slot).DispelTarget);
        AdaptiveMaloriakPlan const dk = Plan(board, DK);
        CHECK(dk.AddSwitchWindow && !dk.AddSwitchRestricts);
        CHECK(dk.DamageTarget == Boss(board).Guid && !dk.SuppressOffense);
        CHECK(std::string(dk.Duty) == "main_tank");
        CHECK(Plan(board, FERAL).AddSwitchRestricts);
        // Healers are off the boss too.
        for (Slot slot : { HOLY, DISC })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(plan.AddSwitchRestricts && plan.SuppressOffense);
            CHECK(std::string(plan.SuppressReason) == "add_switch_wait");
        }
        // The DK keeps damaging through the whole switch, even at 26%.
        Boss(board).HealthPct = 26.0f;
        CHECK(Plan(board, DK).DamageTarget == Boss(board).Guid && !Plan(board, DK).SuppressOffense);

        // Loose ones dead, nine still in the chambers: damage dealers wait off
        // the boss for the next release.
        for (uint32 index = 3; index < 6; ++index)
            board.Summons[index].Alive = false;
        AdaptiveMaloriakPlan const wait = Plan(board, LOCK);
        CHECK(wait.AddSwitchWindow && wait.AddSwitchRestricts && wait.SuppressOffense);
        CHECK(std::string(wait.SuppressReason) == "add_switch_wait");
        CHECK(!wait.DispelTarget && !Plan(board, MAGE).DispelTarget);

        // The last release is out: the switch holds until its adds are dead.
        for (uint32 index = 6; index < 18; ++index)
            board.Summons[index].Selectable = board.Summons[index].Attackable = true;
        CHECK(M::Observe(board).ReserveAberrations == 0);
        CHECK(Plan(board, LOCK).AddSwitchWindow);
        CHECK(Plan(board, LOCK).DamageTarget != Boss(board).Guid);
        CHECK(!Plan(board, MAGE).DispelTarget);

        // Chambers empty, every Aberration dead: Remedy is dispelled again
        // and everyone burns the boss.
        for (uint32 index = 6; index < 18; ++index)
            board.Summons[index].Alive = false;
        AdaptiveMaloriakPlan const burn = Plan(board, MAGE);
        CHECK(!burn.AddSwitchWindow && !burn.AddSwitchRestricts);
        CHECK(burn.DamageTarget == Boss(board).Guid && !burn.SuppressOffense);
        CHECK(burn.DispelTarget == Boss(board).Guid);
        CHECK(Plan(board, SHAMAN).DispelTarget == Boss(board).Guid);
        CHECK(Plan(board, HOLY).DamageTarget == Boss(board).Guid && !Plan(board, HOLY).SuppressOffense);

        // Phase two starts with only the Prime Subjects; no switch there.
        Boss(board).HealthPct = 24.0f;
        CHECK(!Plan(board, MAGE).AddSwitchWindow);
        // Before the pull there is no switch either.
        Blackboard idle = Canonical();
        Boss(idle).InCombat = false;
        idle.NativeBossState = "not_started";
        Boss(idle).HealthPct = 20.0f;
        CHECK(!Plan(idle, MAGE).AddSwitchWindow);
    }

    // Review P1 (remedy_rebound): the switch is a cohort latch. Remedy is
    // left on Maloriak, so he heals back above 30%; the switch holds (no
    // restriction lift, no purge re-armed) until the adds are gone, and the
    // cap and the reset end it. One effective state for everything.
    {
        EncounterLatchStore store;
        Blackboard board = Canonical();
        for (uint32 index = 0; index < 9; ++index)
            board.Summons.push_back(Add(41440, 1300 + index, -140.0f, -430.0f, false, 100.0f));
        Boss(board).Auras.push_back({ 77912, Boss(board).Guid, 1, board.ObservedAtMs + 5000 });
        Boss(board).HealthPct = 31.0f;
        Publish(board, store);
        CHECK(!Plan(board, MAGE, &store.View()).AddSwitchWindow);
        CHECK(Plan(board, MAGE, &store.View()).DispelTarget == Boss(board).Guid);
        Boss(board).HealthPct = 29.9f;
        Publish(board, store, 1000);
        uint64 const enteredAt = board.ObservedAtMs;
        AdaptiveMaloriakPlan const first = Plan(board, MAGE, &store.View());
        CHECK(first.AddSwitchWindow && first.AddSwitchRestricts && !first.DispelTarget);
        // Remedy heals him to 30.1%: still the switch.
        Boss(board).HealthPct = 30.1f;
        Boss(board).Auras.back().ExpiresAtMs = board.ObservedAtMs + 3000;
        Publish(board, store, 1000);
        AdaptiveMaloriakPlan const rebound = Plan(board, MAGE, &store.View());
        CHECK(rebound.AddSwitchWindow && rebound.AddSwitchRestricts);
        CHECK(!rebound.DispelTarget && !Plan(board, SHAMAN, &store.View()).DispelTarget);
        CHECK(std::string(rebound.SuppressReason) == "add_switch_wait");
        EncounterLatch const* entered = store.View().Module(M::LatchModule)->Find(M::AddSwitchEnteredLatch);
        CHECK(entered && entered->SetAtMs == enteredAt);
        // Without the published view (a stale revision) the unlatched
        // condition applies; the runtime always passes the current view.
        CHECK(!Plan(board, MAGE).AddSwitchWindow);
        // The cap: 180 s after the entry the switch ends everywhere at once.
        Publish(board, store, M::AddSwitchCapMs - 2000);
        CHECK(Plan(board, MAGE, &store.View()).AddSwitchWindow);
        Publish(board, store, 1000);
        AdaptiveMaloriakPlan const capped = Plan(board, MAGE, &store.View());
        CHECK(!capped.AddSwitchWindow && !capped.AddSwitchRestricts && capped.AddSwitchCapReleased);
        CHECK(capped.DispelTarget == Boss(board).Guid && capped.DamageTarget == Boss(board).Guid);
        CHECK(!capped.SuppressOffense);
        // A wipe (disengage) clears the latch for the next pull.
        Boss(board).InCombat = false;
        board.NativeBossState = "not_started";
        Publish(board, store, 1000);
        Boss(board).InCombat = true;
        board.NativeBossState = "in_progress";
        Boss(board).HealthPct = 29.0f;
        Publish(board, store, 1000);
        AdaptiveMaloriakPlan const again = Plan(board, MAGE, &store.View());
        CHECK(again.AddSwitchWindow && !again.AddSwitchCapReleased);
    }

    // User refinement: the pause at 30% happens only if adds remain. With
    // the chambers empty and nothing alive at 30%, no pause: burn straight
    // through and keep dispelling Remedy; it never pauses later either.
    {
        EncounterLatchStore store;
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 77912, Boss(board).Guid, 1, board.ObservedAtMs + 9500 });
        Boss(board).HealthPct = 29.0f;
        Publish(board, store);
        AdaptiveMaloriakPlan const mage = Plan(board, MAGE, &store.View());
        CHECK(!mage.AddSwitchWindow && !mage.AddSwitchRestricts);
        CHECK(mage.DamageTarget == Boss(board).Guid && !mage.SuppressOffense);
        CHECK(mage.DispelTarget == Boss(board).Guid);
        CHECK(Plan(board, LOCK, &store.View()).DamageTarget == Boss(board).Guid);
        EncounterLatch const* released = store.View().Module(M::LatchModule)->Find(M::AddSwitchReleasedLatch);
        CHECK(released && released->Value == uint64(M::AddSwitchRelease::NothingLeft));
        Publish(board, store, 1000);
        CHECK(!Plan(board, MAGE, &store.View()).AddSwitchWindow);
    }

    // User refinement: during the pause the damage dealers burn one
    // Aberration at a time; only the Feral holds the rest.
    {
        EncounterLatchStore store;
        Blackboard board = Canonical();
        board.Summons.push_back(Add(41440, 1400, -133.0f, -452.0f, true, 70.0f));
        board.Summons.push_back(Add(41440, 1401, -134.0f, -453.0f, true, 40.0f));
        board.Summons.push_back(Add(41440, 1402, -133.0f, -454.0f, true, 90.0f));
        for (ActorSnapshot& add : board.Summons)
            add.VictimGuid = G(FERAL);
        board.Summons.push_back(Add(41440, 1403, -140.0f, -430.0f, false, 100.0f));
        Boss(board).HealthPct = 28.0f;
        Publish(board, store);
        for (Slot slot : { HUNTER, MAGE, RET, ROGUE, SHAMAN, LOCK })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot, &store.View());
            CHECK(plan.DamageTarget == board.Summons[1].Guid);
        }
        CHECK(Plan(board, FERAL, &store.View()).DamageTarget != Boss(board).Guid);
        CHECK(Plan(board, DK, &store.View()).DamageTarget == Boss(board).Guid);
        board.Summons[1].Alive = false;
        Publish(board, store, 1000);
        for (Slot slot : { HUNTER, MAGE, RET, ROGUE, SHAMAN, LOCK })
            CHECK(Plan(board, slot, &store.View()).DamageTarget == board.Summons[0].Guid);
    }

    // Threat onto the Feral off-tank (user tactic): the hunter's
    // Misdirection and the rogue's Tricks of the Trade arm only while their
    // own next target is a loose Aberration (review item 6: during the
    // release cast nothing is attackable yet, and a redirect armed then
    // would carry boss attacks and boss threat to the Feral).
    {
        Blackboard board = Canonical();
        for (uint32 index = 0; index < 6; ++index)
            board.Summons.push_back(Add(41440, 1100 + index, -140.0f, -430.0f, false, 100.0f));
        CHECK(!Plan(board, HUNTER).ThreatRedirectTarget && !Plan(board, ROGUE).ThreatRedirectTarget);
        Boss(board).Cast = CastSnapshot{ 77569, ObjectGuid(), board.ObservedAtMs, false, true };
        for (Slot slot : { HUNTER, ROGUE, MAGE, LOCK, SHAMAN, DK, FERAL, HOLY })
            CHECK(!Plan(board, slot).ThreatRedirectTarget);
        // Released and leaping (not attackable yet): still nothing.
        board.Summons[0].Selectable = true;
        CHECK(!Plan(board, HUNTER).ThreatRedirectTarget && !Plan(board, ROGUE).ThreatRedirectTarget);
        Boss(board).Cast.reset();
        // Landed and not on the bear: the hunter and the rogue burn it and
        // redirect onto the Feral; the shaman slows the one nearest the boss.
        board.Summons[0].Attackable = true;
        board.Summons[1].Selectable = board.Summons[1].Attackable = true;
        board.Summons[0].Position = { -125.0f, -445.0f, 73.6f };
        board.Summons[1].Position = { -140.0f, -430.0f, 73.6f };
        board.Summons[0].VictimGuid = G(HOLY);
        board.Summons[1].VictimGuid = G(MAGE);
        AdaptiveMaloriakPlan const hunter = Plan(board, HUNTER);
        CHECK(hunter.DamageTarget == board.Summons[0].Guid || hunter.DamageTarget == board.Summons[1].Guid);
        CHECK(hunter.ThreatRedirectTarget == G(FERAL) && hunter.ThreatRedirectSpellId == M::MisdirectionSpell);
        AdaptiveMaloriakPlan const rogue = Plan(board, ROGUE);
        CHECK(rogue.ThreatRedirectTarget == G(FERAL) && rogue.ThreatRedirectSpellId == M::TricksOfTheTradeSpell);
        for (Slot slot : { MAGE, LOCK, SHAMAN, DK, FERAL, HOLY })
            CHECK(!Plan(board, slot).ThreatRedirectTarget);
        CHECK(Plan(board, SHAMAN).SlowTarget == board.Summons[0].Guid);
        board.Summons[0].Auras.push_back({ M::FrostShockSpell, G(SHAMAN), 1, board.ObservedAtMs + 8000 });
        // The other one is 25 yards from the shaman: out of Frost Shock's
        // range (review item 7), so no slow until it comes closer.
        CHECK(!Plan(board, SHAMAN).SlowTarget);
        board.Summons[1].Position = { -130.0f, -440.0f, 73.6f };
        CHECK(Plan(board, SHAMAN).SlowTarget == board.Summons[1].Guid);
        board.Summons[1].Position = { -140.0f, -430.0f, 73.6f };
        CHECK(!Plan(board, MAGE).SlowTarget);
        // An Aberration running at the hunter: Freeze Trap when nobody hits
        // it (not the raid's burn focus), Ice Trap when it is the focus;
        // nothing when it is far away or on someone else.
        board.Summons[1].VictimGuid = G(HUNTER);
        board.Summons[1].HealthPct = 100.0f;
        board.Summons[0].HealthPct = 50.0f;
        board.Summons[1].Position = { board.Players[HUNTER].Position.X + 8.0f,
            board.Players[HUNTER].Position.Y, 73.6f };
        AdaptiveMaloriakPlan const freeze = Plan(board, HUNTER);
        CHECK(freeze.TrapTarget == board.Summons[1].Guid && freeze.TrapSpellId == M::FreezeTrapSpell);
        board.Summons[1].HealthPct = 40.0f;
        AdaptiveMaloriakPlan const ice = Plan(board, HUNTER);
        CHECK(ice.TrapTarget == board.Summons[1].Guid && ice.TrapSpellId == M::IceTrapSpell);
        board.Summons[1].Position = { -140.0f, -430.0f, 73.6f };
        CHECK(!Plan(board, HUNTER).TrapTarget);
        board.Summons[1].Position = { board.Players[ROGUE].Position.X + 5.0f,
            board.Players[ROGUE].Position.Y, 73.6f };
        board.Summons[1].VictimGuid = G(ROGUE);
        CHECK(!Plan(board, HUNTER).TrapTarget && !Plan(board, ROGUE).TrapTarget);
        board.Summons[1].VictimGuid = G(MAGE);
        // Everything on the bear: no redirect; the shaman's Frost Shock and
        // the hunter's Ice Trap (at the kite loop's trap corner) now cover
        // the kited pack (review item 9).
        board.Summons[0].VictimGuid = G(FERAL);
        board.Summons[1].VictimGuid = G(FERAL);
        board.Summons[0].Auras.clear();
        CHECK(!Plan(board, HUNTER).ThreatRedirectTarget && !Plan(board, ROGUE).ThreatRedirectTarget);
        // (the one nearer Maloriak first)
        CHECK(Plan(board, SHAMAN).SlowTarget == board.Summons[1].Guid);
        AdaptiveMaloriakPlan const kiteTrap = Plan(board, HUNTER);
        CHECK(kiteTrap.TrapSpellId == M::IceTrapSpell && !kiteTrap.TrapTarget.IsEmpty());
        CHECK(kiteTrap.Movement && kiteTrap.Movement->Id.Mechanic == "hunter_kite_trap_corner");
        board.Players[HUNTER].Position = kiteTrap.TrapPoint;
        CHECK(!Plan(board, HUNTER).Movement || Plan(board, HUNTER).Movement->Id.Mechanic != "hunter_kite_trap_corner");
        // In Red the hunter keeps the cone stack instead.
        Boss(board).Auras.push_back({ M::FireImbuedSpell, Boss(board).Guid, 1, 0 });
        CHECK(!Plan(board, HUNTER).TrapTarget);
        Boss(board).Auras.pop_back();
        // No living off-tank: nobody to redirect to.
        board.Summons[0].VictimGuid = G(HOLY);
        board.Players[FERAL].Alive = false;
        CHECK(!Plan(board, HUNTER).ThreatRedirectTarget);
    }

    // Review adversarial checks. Red: a ranged damage dealer burning a pack
    // keeps the Scorching Blast cone stack; a melee one fights at the adds.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ M::FireImbuedSpell, Boss(board).Guid, 1, 0 });
        board.Players[MAGE].Position = { -105.8f, -475.0f, 73.6f };
        AdaptiveMaloriakPlan const before = Plan(board, MAGE);
        CHECK(before.Movement && before.Movement->Id.Mechanic == "red_cone_stack");
        for (uint32 index = 0; index < 3; ++index)
            board.Summons.push_back(Add(41440, 990 + index, -130.0f, -434.0f, true, 100.0f));
        AdaptiveMaloriakPlan const after = Plan(board, MAGE);
        CHECK(after.DamageTarget != Boss(board).Guid);
        CHECK(after.Movement && after.Movement->Id.Mechanic == "red_cone_stack");
        AdaptiveMaloriakPlan const healer = Plan(board, HOLY);
        CHECK(!healer.Movement || healer.Movement->Id.Mechanic == "red_cone_stack");
        board.Players[ROGUE].Position = { -105.8f, -475.0f, 73.6f };
        AdaptiveMaloriakPlan const rogue = Plan(board, ROGUE);
        CHECK(rogue.DamageTarget != Boss(board).Guid && !rogue.Movement);
        // Consuming Flames still leaves the cone while burning adds.
        board.Players[MAGE].Auras.push_back({ 77786, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        AdaptiveMaloriakPlan const flames = Plan(board, MAGE);
        CHECK(flames.Movement && flames.Movement->Id.Mechanic == "consuming_flames_leave_cone");
    }

    // Freeze vs Frost Shock: never the same add; an add someone hits (here
    // the off-tank's pickup) gets an Ice Trap, not a Freeze Trap.
    {
        Blackboard board = Canonical();
        board.Summons.push_back(Add(41440, 990, -140.0f, -440.0f, true, 40.0f));
        board.Summons.back().VictimGuid = G(FERAL);
        board.Summons.push_back(Add(41440, 991, -114.0f, -437.0f, true, 100.0f));
        board.Summons.back().VictimGuid = G(HUNTER);
        AdaptiveMaloriakPlan const hunter = Plan(board, HUNTER);
        AdaptiveMaloriakPlan const shaman = Plan(board, SHAMAN);
        CHECK(hunter.TrapSpellId != M::FreezeTrapSpell || hunter.TrapTarget != shaman.SlowTarget);
        CHECK(hunter.TrapTarget == board.Summons[1].Guid && hunter.TrapSpellId == M::IceTrapSpell);
        CHECK(Plan(board, FERAL).DamageTarget == board.Summons[1].Guid);
        // A frozen add is left alone: no pickup, no Frost Shock, no burn
        // while anything else is left.
        board.Summons[1].Auras.push_back({ M::FreezingTrapAuraSpell, G(HUNTER), 1, board.ObservedAtMs + 20000 });
        board.Summons[1].VictimGuid = ObjectGuid();
        CHECK(Plan(board, FERAL).DamageTarget != board.Summons[1].Guid);
        CHECK(Plan(board, SHAMAN).SlowTarget != board.Summons[1].Guid);
        CHECK(Plan(board, LOCK).DamageTarget == board.Summons[0].Guid);
        // An unhit add running at the hunter (not the focus, not the pickup,
        // no DoT) is frozen, and the shaman does not Frost Shock it.
        board.Summons[1].Auras.clear();
        board.Summons[1].VictimGuid = G(HUNTER);
        board.Summons.push_back(Add(41440, 992, -125.0f, -445.0f, true, 100.0f));
        board.Summons.back().VictimGuid = G(HOLY);
        AdaptiveMaloriakPlan const freeze = Plan(board, HUNTER);
        CHECK(freeze.TrapTarget == board.Summons[1].Guid && freeze.TrapSpellId == M::FreezeTrapSpell);
        CHECK(Plan(board, SHAMAN).SlowTarget != board.Summons[1].Guid);
        // A DoT on it (someone is damaging it): Ice Trap instead.
        board.Summons[1].Auras.push_back({ 172, G(LOCK), 1, board.ObservedAtMs + 18000 });
        CHECK(Plan(board, HUNTER).TrapSpellId == M::IceTrapSpell);
    }

    // The kite: paced round the flank loop, away from Maloriak and clear of
    // hazards; the off-tank waits at a waypoint for a straggling pack.
    {
        Blackboard board = Canonical();
        board.Players[FERAL].Position = M::KiteLoopWest[0];
        for (uint32 index = 0; index < 3; ++index)
        {
            board.Summons.push_back(Add(41440, 995 + index, M::KiteLoopWest[0].X + 1.0f,
                M::KiteLoopWest[0].Y, true, 100.0f));
            board.Summons.back().VictimGuid = G(FERAL);
        }
        AdaptiveMaloriakPlan const step = Plan(board, FERAL);
        CHECK(step.Movement && step.Movement->Id.Mechanic == "off_tank_kite");
        CHECK(Dist(Destination(step), M::KiteLoopWest[1]) < 0.01f);
        CHECK(step.NaturesGrasp);
        // Mid-leg it keeps going forward, not back.
        board.Players[FERAL].Position = { -134.0f, -446.0f, 73.6f };
        CHECK(Dist(Destination(Plan(board, FERAL)), M::KiteLoopWest[1]) < 0.01f);
        // A straggler: wait at the waypoint.
        board.Players[FERAL].Position = M::KiteLoopWest[1];
        board.Summons[2].Position = { -125.0f, -446.0f, 73.6f };
        // Review item 4: the wait is an explicit, renewed hold where the
        // off-tank stands (it keeps the mechanic movement lease).
        AdaptiveMaloriakPlan const wait = Plan(board, FERAL);
        CHECK(wait.Movement && wait.Movement->Id.Mechanic == "off_tank_kite_hold");
        CHECK(Dist(Destination(wait), M::KiteLoopWest[1]) < 0.01f);
        CHECK(std::string(wait.Duty) == "off_tank_kite");
        for (ActorSnapshot& add : board.Summons)
            add.Position = M::KiteLoopWest[1];
        CHECK(Dist(Destination(Plan(board, FERAL)), M::KiteLoopWest[2]) < 0.01f);
        // Every waypoint keeps the boss at 20 yards or more and avoids an
        // Absolute Zero sphere on the path.
        for (Vector3 const& point : M::KiteLoopWest)
            CHECK(Dist(point, Boss(board).Position) >= M::KiteBossClearance);
        board.Summons.push_back(Add(M::AbsoluteZeroEntry, 999, M::KiteLoopWest[2].X,
            M::KiteLoopWest[2].Y, true, 100.0f));
        CHECK(Dist(Destination(Plan(board, FERAL)), M::KiteLoopWest[2]) > 1.0f);
        board.Summons.pop_back();
        // Nature's Grasp only while it is not up already.
        board.Players[FERAL].Auras.push_back({ M::NaturesGraspSpell, G(FERAL), 3, board.ObservedAtMs + 30000 });
        CHECK(!Plan(board, FERAL).NaturesGrasp);
    }

    // Re-review item 2: kite paths, not only endpoints, keep Maloriak and the
    // hazards at their clearance; a join that cannot is an explicit hold.
    {
        auto pathClearance = [](Vector3 from, Vector3 to, Vector3 point)
        {
            return M::SegmentDistance(from, to, point);
        };
        // Boss between the pack and the far loop: no path through him.
        Blackboard board = Canonical();
        Boss(board).Position = { -124.0f, -453.0f, 73.6f };
        Vector3 const start{ -138.0f, -453.0f, 73.6f };
        M::Observation observation = M::Observe(board);
        M::KiteDecision decision = M::KiteStep(M::ResolveKite(observation, start), start, {},
            Boss(board).Position, M::CollectFormationHazards(observation));
        CHECK(!decision.Move || pathClearance(start, decision.Destination, Boss(board).Position)
            >= std::min(M::KiteBossClearance, Dist(start, Boss(board).Position) - 0.3f));
        // The full plan: an explicit hold where the off-tank stands.
        board.Players[FERAL].Position = start;
        board.Summons.push_back(Add(41440, 1500, -139.0f, -453.0f, true, 60.0f));
        board.Summons.back().VictimGuid = G(FERAL);
        AdaptiveMaloriakPlan const blocked = Plan(board, FERAL);
        CHECK(blocked.Movement);
        CHECK(blocked.Movement->Id.Mechanic == "off_tank_kite_hold"
            || pathClearance(start, Destination(blocked), Boss(board).Position) >= 14.0f);
        // A Flash Freeze block across the join: never walked through.
        Blackboard ice = Canonical();
        ice.Players[FERAL].Position = { -138.0f, -420.0f, 73.6f };
        ice.Summons.push_back(Add(41440, 1501, -138.0f, -421.0f, true, 50.0f));
        ice.Summons.back().VictimGuid = G(FERAL);
        ice.Summons.push_back(Add(M::FlashFreezeEntry, 1502, -138.0f, -433.0f, true, 100.0f));
        AdaptiveMaloriakPlan const joined = Plan(ice, FERAL);
        CHECK(joined.Movement);
        CHECK(joined.Movement->Id.Mechanic == "off_tank_kite_hold"
            || pathClearance(ice.Players[FERAL].Position, Destination(joined),
                ice.Summons.back().Position) >= M::ShatterDanger);
        // A dropped corner makes a diagonal leg: jet fire by one corner drops
        // it, and jet fire on the diagonal between its neighbours makes the
        // loop unusable rather than walked through.
        Blackboard sphere = Canonical();
        Vector3 const legMiddle{ (M::KiteLoopWest[0].X + M::KiteLoopWest[2].X) / 2.0f,
            (M::KiteLoopWest[0].Y + M::KiteLoopWest[2].Y) / 2.0f, 73.6f };
        sphere.Summons.push_back(Add(M::MagmaJetFireEntry, 1503, -139.0f, -445.0f, true, 100.0f));
        sphere.Summons.push_back(Add(M::MagmaJetFireEntry, 1504, legMiddle.X, legMiddle.Y, true, 100.0f));
        M::Observation const sphereView = M::Observe(sphere);
        M::KiteGeometry const west = M::BuildKiteLoop(M::KiteLoopWest, Boss(sphere).Position,
            M::CollectFormationHazards(sphereView));
        CHECK(west.Waypoints.size() != 3);
        for (std::size_t index = 0; index < west.Waypoints.size(); ++index)
            CHECK(M::KitePathClear(west.Waypoints[index],
                west.Waypoints[(index + 1) % west.Waypoints.size()], Boss(sphere).Position,
                M::CollectFormationHazards(sphereView)));
    }

    // Re-review item 3: a loop with two usable waypoints is rejected (its
    // two legs overlap), so the off-tank never turns round mid-leg.
    {
        Blackboard board = Canonical();
        Boss(board).Position = { -110.0f, -453.0f, 73.6f };
        M::Observation const observation = M::Observe(board);
        std::vector<M::FormationHazard> const hazards = M::CollectFormationHazards(observation);
        CHECK(M::BuildKiteLoop(M::KiteLoopWest, Boss(board).Position, hazards).Waypoints.empty());
        Vector3 const first{ -138.0f, -460.0f, 73.6f };
        Vector3 const later{ -138.0f, -457.0f, 73.6f };
        M::KiteDecision const a = M::KiteStep(M::ResolveKite(observation, first), first, {},
            Boss(board).Position, hazards);
        M::KiteDecision const b = M::KiteStep(M::ResolveKite(observation, later), later, {},
            Boss(board).Position, hazards);
        CHECK(a.Move == b.Move);
        CHECK(!a.Move || Dist(a.Destination, b.Destination) < 0.01f);
        M::KiteGeometry two;
        two.Waypoints = { { -138.0f, -446.0f, 73.6f }, { -138.0f, -460.0f, 73.6f } };
        two.Center = { -138.0f, -453.0f, 73.6f };
        CHECK(!M::KiteStep(two, later, {}, Boss(board).Position, hazards).Move);
    }

    // Re-review item 4: rooted Aberrations. One rooted beside the off-tank
    // holds the kite (an explicit hold); one rooted far behind is left to
    // rejoin and the rest go on.
    {
        Blackboard board = Canonical();
        board.Players[FERAL].Position = M::KiteLoopWest[1];
        for (uint32 index = 0; index < 2; ++index)
        {
            board.Summons.push_back(Add(41440, 1510 + index, M::KiteLoopWest[1].X,
                M::KiteLoopWest[1].Y + 1.0f, true, 100.0f));
            board.Summons.back().VictimGuid = G(FERAL);
        }
        board.Summons[0].Auras.push_back({ 19975, G(FERAL), 1, board.ObservedAtMs + 20000 });
        AdaptiveMaloriakPlan const rooted = Plan(board, FERAL);
        CHECK(rooted.Movement && rooted.Movement->Id.Mechanic == "off_tank_kite_hold");
        board.Summons[0].Position = M::KiteLoopWest[3];
        AdaptiveMaloriakPlan const onward = Plan(board, FERAL);
        CHECK(onward.Movement && onward.Movement->Id.Mechanic == "off_tank_kite");
        CHECK(Dist(Destination(onward), M::KiteLoopWest[2]) < 0.01f);
    }

    // Re-review items 5-7 in Blue with the pack kited on the west loop: the
    // hunter holds its trap post (no return to its fan slot), a chilled
    // hunter keeps its isolation, and the fan leans west so the shaman's
    // slot is within Frost Shock range of the pack and every fan slot
    // reaches every waypoint within 40 yards; the same on the east loop.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ M::FrostImbuedSpell, Boss(board).Guid, 1, 0 });
        board.Players[FERAL].Position = M::KiteLoopWest[1];
        board.Summons.push_back(Add(41440, 1520, M::KiteLoopWest[1].X, M::KiteLoopWest[1].Y, true, 60.0f));
        board.Summons.back().VictimGuid = G(FERAL);
        AdaptiveMaloriakPlan const toPost = Plan(board, HUNTER);
        CHECK(toPost.Movement && toPost.Movement->Id.Mechanic == "hunter_kite_trap_corner");
        Vector3 const post = Destination(toPost);
        board.Players[HUNTER].Position = post;
        AdaptiveMaloriakPlan const atPost = Plan(board, HUNTER);
        CHECK(atPost.Movement && atPost.Movement->Id.Mechanic == "hunter_kite_trap_post_hold");
        CHECK(Dist(Destination(atPost), post) <= M::KiteTrapTolerance);
        CHECK(atPost.TrapSpellId == M::IceTrapSpell);
        // Biting Chill: isolation first, never the trap post.
        board.Players[HUNTER].Position = { -123.0f, -460.0f, 73.6f };
        board.Players[HUNTER].Auras.push_back({ M::BitingChillSpell, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        AdaptiveMaloriakPlan const chilled = Plan(board, HUNTER);
        CHECK(!chilled.Movement || chilled.Movement->Id.Mechanic.rfind("hunter_kite_trap", 0) != 0);
        board.Players[HUNTER].Auras.clear();
        board.Players[HUNTER].Position = post;
        // Frost Shock reach: the shaman's Blue slot on the west flank.
        board.Players[SHAMAN].Position = { -90.0f, -470.0f, 73.6f };
        AdaptiveMaloriakPlan const shaman = Plan(board, SHAMAN);
        CHECK(shaman.Movement && shaman.Movement->Id.Mechanic == "blue_spread");
        CHECK(Dist(Destination(shaman), board.Summons[0].Position) <= M::FrostShockRangeYards);
        for (bool east : { false, true })
        {
            Blackboard side = board;
            auto const& loop = east ? M::KiteLoopEast : M::KiteLoopWest;
            side.Players[FERAL].Position = loop[1];
            side.Summons[0].Position = loop[1];
            M::BossFrame const frame = M::ResolveFrame(Boss(side), &side.Players[DK]);
            M::Observation const observation = M::Observe(side);
            M::KiteGeometry const kite = M::ResolveKite(observation, loop[1]);
            CHECK(!kite.Waypoints.empty());
            float const sign = M::ToFramePolar(frame, kite.Center).Angle >= 0.0f ? 1.0f : -1.0f;
            std::vector<Vector3> fan;
            for (std::size_t position = 0; position < 6; ++position)
                fan.push_back(M::BiasedBackRangedSlot(frame, position, 6, sign));
            for (Vector3 const& slot : fan)
                for (Vector3 const& waypoint : kite.Waypoints)
                    CHECK(Dist(slot, waypoint) <= 40.0f);
            for (std::size_t i = 0; i < fan.size(); ++i)
                for (std::size_t j = i + 1; j < fan.size(); ++j)
                    CHECK(Dist(fan[i], fan[j]) >= M::SpreadYards);
            for (Vector3 const& waypoint : kite.Waypoints)
                CHECK(Dist(fan.back(), waypoint) <= M::FrostShockRangeYards);
        }
    }

    // Kite re-review 2, item 1: the trap post keeps the Blue spread from the
    // off-tank holding a rooted pack at the loop's far corner, and a Biting
    // Chill target's isolation, chilled Feral included: it moves to another
    // corner, or is suspended when none is clear.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ M::FrostImbuedSpell, Boss(board).Guid, 1, 0 });
        board.Players[FERAL].Position = { -138.0f, -446.0f, 73.6f };
        board.Summons.push_back(Add(41440, 1530, -138.0f, -446.0f, true, 50.0f));
        board.Summons.back().VictimGuid = G(FERAL);
        board.Summons.back().Auras.push_back({ 53313, G(FERAL), 1, board.ObservedAtMs + 20000 });
        for (bool chilled : { true, false })
        {
            Blackboard side = board;
            if (chilled)
                side.Players[FERAL].Auras.push_back({ M::BitingChillSpell, Boss(side).Guid, 1,
                    side.ObservedAtMs + 9000 });
            AdaptiveMaloriakPlan const feral = Plan(side, FERAL);
            CHECK(feral.Movement && feral.Movement->Id.Mechanic == "off_tank_kite_hold");
            AdaptiveMaloriakPlan hunter = Plan(side, HUNTER);
            if (hunter.Movement)
                side.Players[HUNTER].Position = Destination(hunter);
            hunter = Plan(side, HUNTER);
            float const gap = Dist(Destination(Plan(side, FERAL)), Destination(hunter));
            CHECK(!hunter.Movement || gap >= (chilled ? M::TrapPostChillYards : M::SpreadYards));
            CHECK(!hunter.Movement || Dist(side.Players[HUNTER].Position, side.Players[FERAL].Position)
                >= M::SpreadYards);
        }
        // A chilled raid member 6.5 yards from the next corner: that corner
        // is too close for the Biting Chill isolation (8 yards); another one.
        Blackboard chill = board;
        chill.Players[MAGE].Position = { -131.5f, -460.0f, 73.6f };
        chill.Players[MAGE].Auras.push_back({ M::BitingChillSpell, Boss(chill).Guid, 1, chill.ObservedAtMs + 9000 });
        AdaptiveMaloriakPlan const around = Plan(chill, HUNTER);
        CHECK(around.Movement && around.Movement->Id.Mechanic == "hunter_kite_trap_corner");
        CHECK(Dist(Destination(around), chill.Players[MAGE].Position) >= M::TrapPostChillYards);
        CHECK(Dist(Destination(around), chill.Players[FERAL].Position) >= M::SpreadYards);
        // Delta review: the hunter holds where it stands only while that spot
        // itself keeps the spread (5 yd) and a chilled neighbour's isolation
        // (8 yd); inside the 3-yd arrival tolerance but too close, it steps
        // onto the validated corner.
        for (bool chilledHoly : { false, true })
        {
            Blackboard held = board;
            held.Players[FERAL].Position = { -138.0f, -460.0f, 73.6f };
            held.Summons[0].Position = held.Players[FERAL].Position;
            held.Players[HOLY].Position = { -138.0f, chilledHoly ? -454.1f : -451.1f, 73.6f };
            if (chilledHoly)
                held.Players[HOLY].Auras.push_back({ M::BitingChillSpell, Boss(held).Guid, 1,
                    held.ObservedAtMs + 9000 });
            held.Players[HUNTER].Position = { -138.0f, -448.9f, 73.6f };
            AdaptiveMaloriakPlan const hunter = Plan(held, HUNTER);
            Vector3 const place = hunter.Movement ? Destination(hunter) : held.Players[HUNTER].Position;
            CHECK(Dist(place, held.Players[HOLY].Position)
                >= (chilledHoly ? M::TrapPostChillYards : M::SpreadYards));
            CHECK(!hunter.Movement || hunter.Movement->Id.Mechanic != "hunter_kite_trap_post_hold"
                || Dist(place, held.Players[HUNTER].Position) < 0.01f);
        }
        // Every corner crowded: the post is suspended (no trap post move).
        Blackboard crowded = board;
        crowded.Players[MAGE].Position = M::KiteLoopWest[0];
        crowded.Players[HOLY].Position = M::KiteLoopWest[2];
        crowded.Players[DISC].Position = M::KiteLoopWest[3];
        AdaptiveMaloriakPlan const suspended = Plan(crowded, HUNTER);
        CHECK(!suspended.Movement || suspended.Movement->Id.Mechanic.rfind("hunter_kite_trap", 0) != 0);
        CHECK(suspended.TrapTarget.IsEmpty());
    }

    // Kite re-review 2, item 2: the Feral holds west because the east join
    // crosses the room past Maloriak; the fan leans west (where the pack
    // is), so the shaman stays within Frost Shock range and the healers
    // within 40 yards of the pack.
    {
        Blackboard board = Canonical();
        Boss(board).Position = { -108.4f, -453.0f, 73.6f };
        Boss(board).Auras.push_back({ M::FrostImbuedSpell, Boss(board).Guid, 1, 0 });
        board.Players[DK].Position = M::MainTankSpot;
        board.Players[FERAL].Position = { -138.0f, -446.0f, 73.6f };
        board.Summons.push_back(Add(41440, 1540, -138.0f, -446.0f, true, 50.0f));
        board.Summons.back().VictimGuid = G(FERAL);
        AdaptiveMaloriakPlan const feral = Plan(board, FERAL);
        CHECK(feral.Movement && feral.Movement->Id.Mechanic == "off_tank_kite_hold");
        // From an east-side spot the shaman is sent to the west flank.
        board.Players[SHAMAN].Position = { -90.0f, -461.0f, 73.6f };
        AdaptiveMaloriakPlan const shaman = Plan(board, SHAMAN);
        CHECK(shaman.Movement && shaman.Movement->Id.Mechanic == "blue_spread");
        CHECK(Dist(Destination(shaman), board.Summons[0].Position) <= M::FrostShockRangeYards);
        board.Players[SHAMAN].Position = Destination(shaman);
        CHECK(Plan(board, SHAMAN).SlowTarget == board.Summons[0].Guid);
        for (Slot slot : { HOLY, DISC, MAGE, LOCK })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            Vector3 const place = plan.Movement ? Destination(plan) : board.Players[slot].Position;
            CHECK(Dist(place, board.Summons[0].Position) <= 40.0f);
        }
    }

    // Kite re-review 2, note: a leg that cuts past the cauldron is refused
    // (native path smoothing would take it into the cauldron's radius).
    {
        CHECK(!M::KitePathClear({ -100.0f, -496.0f, 73.6f }, { -128.0f, -460.0f, 73.6f },
            { -80.0f, -460.0f, 73.6f }, {}));
        CHECK(M::KitePathClear(M::KiteLoopWest[0], M::KiteLoopWest[1],
            { -105.8f, -455.0f, 73.6f }, {}));
    }

    // Stopping the bot's own cast for a purge or interrupt: never a heal in
    // progress while anyone is below 50%; damage casts and non-healers yield.
    {
        CHECK(M::OwnCastYieldsToDuty(false, true, 10.0f));
        CHECK(M::OwnCastYieldsToDuty(true, false, 10.0f));
        CHECK(!M::OwnCastYieldsToDuty(true, true, 49.9f));
        CHECK(M::OwnCastYieldsToDuty(true, true, 50.0f));
    }

    // Ranged hysteresis (r03: healers re-pathed on almost every decision as
    // the boss-tank frame turned). A healer on its Blue slot keeps its place
    // when the tank walks 15 degrees around the boss, but not when another
    // player stands within 5 yards or the place falls in front of the boss.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        AdaptiveMaloriakPlan const first = Plan(board, HOLY);
        CHECK(first.Movement.has_value());
        Vector3 const slot = Destination(first);
        board.Players[HOLY].Position = slot;
        CHECK(!Plan(board, HOLY).Movement);
        Vector3 const bossAt = Boss(board).Position;
        Vector3 const tankAt = board.Players[DK].Position;
        float const turned = std::atan2(tankAt.Y - bossAt.Y, tankAt.X - bossAt.X)
            + 15.0f * 3.14159265f / 180.0f;
        board.Players[DK].Position = { bossAt.X + 3.0f * std::cos(turned),
            bossAt.Y + 3.0f * std::sin(turned), tankAt.Z };
        AdaptiveMaloriakPlan const turnedPlan = Plan(board, HOLY);
        CHECK(!turnedPlan.Movement);
        board.Players[DISC].Position = { slot.X + 2.0f, slot.Y, slot.Z };
        CHECK(Plan(board, HOLY).Movement.has_value());
        board.Players[DISC].Position = { -95.0f, -440.0f, 73.6f };
        board.Players[HOLY].Position = { bossAt.X, bossAt.Y + 12.0f, bossAt.Z };
        CHECK(Plan(board, HOLY).Movement.has_value());
    }

    // Round 5 (r04): Maloriak fought at the cauldron's north rim and the
    // raid behind him (south) had no line of sight across the cauldron; both
    // healers healed nothing for 60 s. The r04 lines with both ends outside
    // the cauldron footprint: blocked ones passed at most 8.58 yards from its
    // centre, clear ones at least 9.02 yards.
    {
        Vector3 const rim{ -106.678f, -475.444f, 73.46f };
        for (Vector3 const blocked : { Vector3{ -103.0f, -493.1f, 73.5f }, Vector3{ -115.1f, -491.3f, 73.5f },
                 Vector3{ -94.0f, -493.2f, 73.5f }, Vector3{ -93.1f, -485.4f, 73.5f },
                 Vector3{ -98.7f, -484.6f, 74.2f }, Vector3{ -104.3f, -478.0f, 73.5f } })
            CHECK(!M::CauldronLineClear(blocked, rim));
        for (Vector3 const clear : { Vector3{ -123.8f, -469.9f, 73.4f }, Vector3{ -123.4f, -482.2f, 73.4f },
                 Vector3{ -88.7f, -474.8f, 73.4f } })
            CHECK(M::CauldronLineClear(clear, rim));

        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        Boss(board).Position = rim;
        board.Players[DK].Position = { -105.8f, -469.0f, 73.5f };
        // The main tank leads him off the rim to the tank spot.
        AdaptiveMaloriakPlan const tank = Plan(board, DK);
        CHECK(tank.Movement && tank.Movement->Id.Mechanic == "main_tank_spot");
        CHECK(Dist(Destination(tank), M::MainTankSpot) < 0.01f);
        CHECK(tank.DamageTarget == Boss(board).Guid);
        // Until he follows, every formation move keeps line of sight.
        board.Players[HOLY].Position = { -115.1f, -491.3f, 73.5f };
        board.Players[DISC].Position = { -103.0f, -493.1f, 73.5f };
        std::vector<Vector3> rangedSpots;
        for (Slot slot : { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK, RET, ROGUE })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            if (plan.Movement)
                CHECK(M::CauldronLineClear(Destination(plan), rim));
            if (plan.Movement && slot != RET && slot != ROGUE)
                rangedSpots.push_back(Destination(plan));
        }
        // Shifted ranged slots keep the Blue spread from each other.
        for (std::size_t left = 0; left < rangedSpots.size(); ++left)
            for (std::size_t right = left + 1; right < rangedSpots.size(); ++right)
                CHECK(Dist(rangedSpots[left], rangedSpots[right]) >= 4.99f);
        CHECK(Plan(board, HOLY).Movement.has_value());
        CHECK(Plan(board, DISC).Movement.has_value());
        // At the spot the tank holds it (the same destination) while the
        // boss is still at the rim or passive at the cauldron, so combat
        // range movement cannot drag it back (review: 3-4 owner swaps per
        // visit at the 4-yard tolerance edge); with the boss in melee it
        // proposes nothing. A hazard on the spot or phase two keeps it where
        // it is.
        for (Vector3 const at : { M::MainTankSpot,
                 Vector3{ M::MainTankSpot.X, M::MainTankSpot.Y - 3.9f, 73.6f } })
        {
            board.Players[DK].Position = at;
            AdaptiveMaloriakPlan const hold = Plan(board, DK);
            CHECK(hold.Movement && hold.Movement->Id.Mechanic == "main_tank_spot");
            CHECK(hold.Movement && Dist(Destination(hold), M::MainTankSpot) < 0.01f);
            Boss(board).ReactAggressive = false;
            AdaptiveMaloriakPlan const passive = Plan(board, DK);
            CHECK(passive.Movement && passive.Movement->Id.Mechanic == "main_tank_spot");
            Boss(board).ReactAggressive = true;
        }
        {
            Blackboard passive = Canonical();
            passive.Hostiles.front().Auras.push_back({ 78895, passive.Hostiles.front().Guid, 1, 0 });
            passive.Hostiles.front().Position = rim;
            passive.Hostiles.front().ReactAggressive = false;
            passive.Players[DK].Position = M::MainTankSpot;
            AdaptiveMaloriakPlan const hold = Plan(passive, DK);
            CHECK(hold.Movement && hold.Movement->Id.Mechanic == "main_tank_spot");
        }
        board.Players[DK].Position = M::MainTankSpot;
        Boss(board).Position = { M::MainTankSpot.X, M::MainTankSpot.Y - 3.5f, 73.6f };
        CHECK(!Plan(board, DK).Movement);
        // Delta review: the aggro-loss guard needs an aggressive boss and a
        // real victim. A passive boss with a stale victim (another player)
        // and an aggressive boss with no victim both leave the walk to the
        // spot in place, and neither is a taunt.
        {
            Blackboard stale = Canonical();
            stale.Hostiles.front().Auras.push_back({ 78895, stale.Hostiles.front().Guid, 1, 0 });
            stale.Hostiles.front().Position = rim;
            stale.Players[DK].Position = { -105.8f, -469.0f, 73.5f };
            stale.Hostiles.front().ReactAggressive = false;
            stale.Hostiles.front().VictimGuid = G(HOLY);
            AdaptiveMaloriakPlan const passive = Plan(stale, DK);
            CHECK(passive.Movement && passive.Movement->Id.Mechanic == "main_tank_spot");
            CHECK(passive.TauntTarget.IsEmpty());
            stale.Hostiles.front().ReactAggressive = true;
            stale.Hostiles.front().VictimGuid = ObjectGuid();
            AdaptiveMaloriakPlan const noVictim = Plan(stale, DK);
            CHECK(noVictim.Movement && noVictim.Movement->Id.Mechanic == "main_tank_spot");
            CHECK(noVictim.TauntTarget.IsEmpty());
        }
        // Re-review: an aggressive boss on a healer 35 yd from the spot is
        // an aggro loss (Dark Command reaches 30 yd): no walk to or hold of
        // the spot, from the spot or from anywhere else.
        {
            Blackboard loss = Canonical();
            loss.Hostiles.front().Auras.push_back({ 78895, loss.Hostiles.front().Guid, 1, 0 });
            loss.Players[HOLY].Position = { M::MainTankSpot.X, M::MainTankSpot.Y - 35.0f, 73.6f };
            loss.Hostiles.front().Position = { M::MainTankSpot.X, M::MainTankSpot.Y - 32.5f, 73.6f };
            loss.Hostiles.front().VictimGuid = G(HOLY);
            for (Vector3 const at : { M::MainTankSpot, Vector3{ -105.8f, -469.0f, 73.5f } })
            {
                loss.Players[DK].Position = at;
                AdaptiveMaloriakPlan const plan = Plan(loss, DK);
                CHECK(!plan.Movement || plan.Movement->Id.Mechanic != "main_tank_spot");
                CHECK(plan.DamageTarget == loss.Hostiles.front().Guid);
            }
            // Back on the tank, the walk to the spot resumes.
            loss.Hostiles.front().VictimGuid = G(DK);
            loss.Players[DK].Position = { -105.8f, -469.0f, 73.5f };
            AdaptiveMaloriakPlan const resumed = Plan(loss, DK);
            CHECK(resumed.Movement && resumed.Movement->Id.Mechanic == "main_tank_spot");
        }
        Boss(board).Position = rim;
        board.Players[DK].Position = { -105.8f, -469.0f, 73.5f };
        board.Summons.push_back(Add(41576, 950, M::MainTankSpot.X + 3.0f, M::MainTankSpot.Y, true, 100.0f));
        AdaptiveMaloriakPlan const blockedSpot = Plan(board, DK);
        CHECK(!blockedSpot.Movement || blockedSpot.Movement->Id.Mechanic != "main_tank_spot");
        board.Summons.pop_back();
        Boss(board).HealthPct = 20.0f;
        Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
        AdaptiveMaloriakPlan const two = Plan(board, DK);
        CHECK(!two.Movement || two.Movement->Id.Mechanic != "main_tank_spot");
    }

    // Review major 2: phase two starting at the rim with the tank east-north-
    // east (a Magma Jets sidestep turns the frame); every ranged player behind
    // the cauldron gets a move that sees the boss, and the moves keep 2.5 yd.
    {
        Blackboard board = Canonical();
        Vector3 const rim{ -106.678f, -475.444f, 73.46f };
        Boss(board).Position = rim;
        Boss(board).HealthPct = 20.0f;
        Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
        float const ene = 22.5f * 3.14159265f / 180.0f;
        board.Players[DK].Position = { rim.X + 8.0f * std::cos(ene), rim.Y + 8.0f * std::sin(ene), 73.5f };
        Slot const ranged[] = { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK };
        float x = -115.0f;
        for (Slot slot : ranged)
        {
            board.Players[slot].Position = { x, -494.0f, 73.5f };
            CHECK(!M::CauldronLineClear(board.Players[slot].Position, rim));
            x += 5.0f;
        }
        std::vector<Vector3> spots;
        for (Slot slot : ranged)
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(plan.Movement.has_value());
            if (!plan.Movement)
                continue;
            CHECK(plan.Movement->Id.Mechanic == "phase_two_spread");
            CHECK(M::CauldronLineClear(Destination(plan), rim));
            spots.push_back(Destination(plan));
        }
        for (std::size_t left = 0; left < spots.size(); ++left)
            for (std::size_t right = left + 1; right < spots.size(); ++right)
                CHECK(Dist(spots[left], spots[right]) >= 2.49f);
    }

    // Review major 2 and the room-wall nit: sweeps that need each ranged pass.
    // (a) boss at (-116, -482) with the tank north: the 220-degree back-arc
    // pass keeps the full 5-yd spread; (b) boss beside the cauldron at
    // (-96, -486): only the last-resort pass (2.5 yd from the slots already
    // placed) finds every player a point in sight; (c) boss in the north-west
    // corner: fan slots clamped onto the same wall point must not both stand.
    {
        struct Case { Vector3 Boss; float TankDeg; bool PhaseTwo; float Spread; };
        for (Case const& test : { Case{ { -116.0f, -482.0f, 73.5f }, 90.0f, false, 4.99f },
                 Case{ { -96.0f, -486.0f, 73.5f }, 30.0f, true, 2.49f },
                 Case{ { -136.0f, -418.0f, 73.5f }, 0.0f, false, 4.99f } })
        {
            Blackboard board = Canonical();
            Boss(board).Position = test.Boss;
            if (test.PhaseTwo)
            {
                Boss(board).HealthPct = 20.0f;
                Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
            }
            else
                Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
            float const tank = test.TankDeg * 3.14159265f / 180.0f;
            board.Players[DK].Position = { test.Boss.X + 3.0f * std::cos(tank),
                test.Boss.Y + 3.0f * std::sin(tank), 73.5f };
            Vector3 park{ -144.0f, -414.0f, 73.6f };
            for (Vector3 const corner : { Vector3{ -69.0f, -414.0f, 73.6f },
                     Vector3{ -144.0f, -494.0f, 73.6f }, Vector3{ -69.0f, -494.0f, 73.6f } })
                if (Dist(corner, test.Boss) > Dist(park, test.Boss))
                    park = corner;
            std::vector<Vector3> spots;
            for (Slot slot : { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK })
                board.Players[slot].Position = park;
            for (Slot slot : { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK })
            {
                AdaptiveMaloriakPlan const plan = Plan(board, slot);
                CHECK(plan.Movement.has_value());
                if (!plan.Movement)
                    continue;
                CHECK(M::CauldronLineClear(Destination(plan), test.Boss));
                spots.push_back(Destination(plan));
            }
            for (std::size_t left = 0; left < spots.size(); ++left)
                for (std::size_t right = left + 1; right < spots.size(); ++right)
                    CHECK(Dist(spots[left], spots[right]) >= test.Spread);
        }
    }

    // Review minor 5: the cauldron alone never holds melee offense, and a
    // boss standing inside its radius drops the constraint.
    {
        Blackboard board = Canonical();
        Vector3 const rim{ -106.678f, -475.444f, 73.46f };
        Boss(board).Auras.push_back({ 78896, Boss(board).Guid, 1, 0 });
        Boss(board).Position = rim;
        // Tank on the cauldron side: the whole front cone is shadowed.
        board.Players[DK].Position = { rim.X + 0.3f, rim.Y - 3.0f, 73.5f };
        for (Slot slot : { RET, ROGUE })
        {
            AdaptiveMaloriakPlan const plan = Plan(board, slot);
            CHECK(!plan.SuppressOffense);
            CHECK(std::string(plan.SuppressReason) != "melee_ring_hazard_hold");
        }
        Boss(board).Auras.back() = { 78895, Boss(board).Guid, 1, 0 };
        for (Slot slot : { RET, ROGUE })
            CHECK(!Plan(board, slot).SuppressOffense);
        Vector3 const inside{ M::CauldronCenter.X, M::CauldronCenter.Y + 8.0f, 73.5f };
        CHECK(!M::CauldronConstrains(inside) && M::CauldronConstrains(rim));
        M::BossFrame frame;
        frame.Boss = inside;
        frame.Ux = 0.0f;
        frame.Uy = 1.0f;
        Vector3 const shadowed{ M::CauldronCenter.X, M::CauldronCenter.Y - 12.0f, 73.5f };
        CHECK(!M::CauldronLineClear(shadowed, inside));
        CHECK(M::FormationPointClear(frame, shadowed, {}));
        // A real hazard around the whole ring still holds melee.
        std::vector<M::FormationHazard> const ring{ { rim, 10.0f } };
        M::BossFrame atRim;
        atRim.Boss = rim;
        CHECK(M::MeleeRingBlocked(atRim, M::SlotArc::Back, ring));
        CHECK(!M::MeleeRingBlocked(atRim, M::SlotArc::Back, {}));
        // Facing the cauldron the whole front of the ring is shadowed; with
        // no hazard (or one far away) that is still no hold.
        M::BossFrame facingCauldron;
        facingCauldron.Boss = rim;
        facingCauldron.Ux = 0.0f;
        facingCauldron.Uy = -1.0f;
        CHECK(!M::FormationPointClear(facingCauldron, M::FramePolar(facingCauldron, M::MeleeRingRadius, 0.0f), {}));
        CHECK(!M::MeleeRingBlocked(facingCauldron, M::SlotArc::FrontCone, {}));
        std::vector<M::FormationHazard> const far{ { { -70.0f, -420.0f, 73.5f }, 2.0f } };
        CHECK(!M::MeleeRingBlocked(facingCauldron, M::SlotArc::FrontCone, far));
    }

    // Review minor 6: a ranged player 6 yd from its clear slot, in the arc and
    // spread from everyone, but with the cauldron between it and the boss,
    // does not keep its place.
    {
        Blackboard board = Canonical();
        Vector3 const rim{ -106.678f, -475.444f, 73.46f };
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        Boss(board).Position = rim;
        board.Players[DK].Position = { -105.8f, -469.0f, 73.5f };
        board.Players[DISC].Position = { -140.0f, -414.0f, 73.6f };
        AdaptiveMaloriakPlan const far = Plan(board, DISC);
        CHECK(far.Movement.has_value());
        Vector3 const slot = Destination(far);
        CHECK(M::CauldronLineClear(slot, rim));
        M::BossFrame const frame = M::ResolveFrame(Boss(board), &board.Players[DK]);
        bool found = false;
        for (int degrees = 0; degrees < 360 && !found; degrees += 5)
        {
            float const radians = float(degrees) * 3.14159265f / 180.0f;
            Vector3 const place{ slot.X + 6.0f * std::cos(radians), slot.Y + 6.0f * std::sin(radians), 73.5f };
            M::FramePolarCoords const polar = M::ToFramePolar(frame, place);
            if (M::CauldronLineClear(place, rim) || polar.Radius < 8.0f || polar.Radius > 30.0f
                || !M::ArcAdmits(M::SlotArc::Back, polar.Angle))
                continue;
            bool spread = true;
            for (ActorSnapshot const& player : board.Players)
                if (player.Guid != G(DISC) && Dist(player.Position, place) < 5.0f)
                    spread = false;
            if (!spread)
                continue;
            found = true;
            board.Players[DISC].Position = place;
            CHECK(!M::RangedPlaceAcceptable(frame, place, slot, M::SlotArc::Back, {}, {}, 5.0f));
            AdaptiveMaloriakPlan const moved = Plan(board, DISC);
            CHECK(moved.Movement && M::CauldronLineClear(Destination(moved), rim));
        }
        CHECK(found);
    }

    // Re-review (optional): a ranged player within the 4-yd slot tolerance
    // but itself behind the cauldron still steps onto its slot.
    {
        Blackboard board = Canonical();
        Vector3 const rim{ -106.678f, -475.444f, 73.46f };
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        Boss(board).Position = rim;
        board.Players[DK].Position = { -105.8f, -469.0f, 73.5f };
        bool found = false;
        for (Slot slot : { HUNTER, MAGE, HOLY, DISC, SHAMAN, LOCK })
        {
            if (found)
                break;
            Vector3 const home = board.Players[slot].Position;
            board.Players[slot].Position = { -140.0f, -414.0f, 73.6f };
            AdaptiveMaloriakPlan const far = Plan(board, slot);
            if (!far.Movement)
            {
                board.Players[slot].Position = home;
                continue;
            }
            Vector3 const spot = Destination(far);
            for (int degrees = 0; degrees < 360 && !found; degrees += 5)
                for (float radius : { 1.5f, 2.5f, 3.5f })
                {
                    float const radians = float(degrees) * 3.14159265f / 180.0f;
                    Vector3 const place{ spot.X + radius * std::cos(radians),
                        spot.Y + radius * std::sin(radians), 73.5f };
                    if (M::CauldronLineClear(place, rim))
                        continue;
                    found = true;
                    board.Players[slot].Position = place;
                    AdaptiveMaloriakPlan const step = Plan(board, slot);
                    CHECK(step.Movement.has_value());
                    CHECK(step.Movement && Dist(Destination(step), spot) < 0.01f);
                    break;
                }
            board.Players[slot].Position = home;
        }
        CHECK(found);
    }

    // Delta review: with the boss himself inside the cauldron's radius the
    // cauldron is ignored, so a ranged player within the 4-yd tolerance of
    // its slot stays put even though every line to him counts as blocked.
    {
        Blackboard board = Canonical();
        Vector3 const inside{ M::CauldronCenter.X, M::CauldronCenter.Y + 8.0f, 73.5f };
        CHECK(!M::CauldronConstrains(inside));
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        Boss(board).Position = inside;
        board.Players[DK].Position = { inside.X, inside.Y + 3.0f, 73.5f };
        board.Players[MAGE].Position = { -140.0f, -414.0f, 73.6f };
        AdaptiveMaloriakPlan const far = Plan(board, MAGE);
        CHECK(far.Movement.has_value());
        Vector3 const slot = Destination(far);
        board.Players[MAGE].Position = { slot.X + 2.0f, slot.Y, slot.Z };
        // A neighbour 3 yd away: only the tolerance (not the kept-place
        // check, which requires the 5-yd spread) keeps the mage still.
        board.Players[HOLY].Position = { slot.X - 1.0f, slot.Y, slot.Z };
        CHECK(!M::CauldronLineClear(board.Players[MAGE].Position, inside));
        CHECK(!Plan(board, MAGE).Movement);
    }

    // Travel versus local moves: the staging line and the add spots are in
    // the laboratory; the entrance corridor and the lower-wing elevator
    // landing (where the r03 runback left the raid) are not.
    {
        CHECK(M::InRoom(M::StagingSlot(0, 8)) && M::InRoom(M::StagingSlot(7, 8)));
        CHECK(M::InRoom(M::AddAnchorWest) && M::InRoom(M::AddAnchorEast));
        CHECK(!M::InRoom(Vector3{ -218.7f, -235.4f, 76.8f }));
        CHECK(!M::InRoom(Vector3{ -105.0f, -380.0f, 76.8f }));
        CHECK(!M::InRoom(Vector3{ -110.0f, -440.0f, 63.0f }));
    }

    // Phase two: burn the boss, lust, dodge Magma Jets and Absolute Zero.
    {
        Blackboard board = Canonical();
        Boss(board).HealthPct = 22.0f;
        Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
        for (uint32 index = 0; index < 5; ++index)
            board.Summons.push_back(Add(41440, 600 + index, -130.0f, -434.0f, true, 40.0f));
        board.Summons.push_back(Add(41841, 700, -128.0f, -432.0f, true, 100.0f));
        CHECK(std::string(Plan(board, MAGE).Phase) == "phase_two");
        CHECK(Plan(board, MAGE).DamageTarget == Boss(board).Guid);
        CHECK(Plan(board, SHAMAN).LustWindow);
        CHECK(!Plan(board, MAGE).LustWindow);
        AdaptiveMaloriakPlan const spread = Plan(board, MAGE);
        CHECK(spread.Movement && spread.Movement->Id.Mechanic == "phase_two_spread");
        CHECK(AngleFromFront(board, Destination(spread)) > 75.0f);
        AdaptiveMaloriakPlan const feral = Plan(board, FERAL);
        CHECK(feral.DamageTarget == board.Summons.back().Guid);
        CHECK(feral.TauntTarget.IsEmpty());
        Boss(board).Cast = CastSnapshot{ 78194, G(DK), board.ObservedAtMs, false, false };
        AdaptiveMaloriakPlan const sidestep = Plan(board, DK);
        CHECK(sidestep.Movement && sidestep.Movement->Id.Mechanic == "magma_jets_sidestep");
        CHECK(sidestep.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
        Vector3 const step = Destination(sidestep);
        CHECK(std::fabs(Dist(step, board.Players[DK].Position) - 8.0f) < 0.2f);
        CHECK(std::fabs(step.Y - board.Players[DK].Position.Y) < 0.2f);
        ActorSnapshot sphere = Add(41961, 800, board.Players[HUNTER].Position.X + 2.0f,
            board.Players[HUNTER].Position.Y, false, 100.0f);
        board.Summons.push_back(sphere);
        AdaptiveMaloriakPlan const evade = Plan(board, HUNTER);
        CHECK(evade.Movement && evade.Movement->Id.Mechanic == "absolute_zero_evade");
        CHECK(evade.Movement->ActionPriority == BotActionArbitration::Priority::Survival);
        CHECK(Dist(Destination(evade), sphere.Position) > 10.9f);
        // A jet line: fires every 3 yards through the warlock. The exit must
        // not land on another fire of the same line.
        for (int step = -3; step <= 3; ++step)
            board.Summons.push_back(Add(41901, uint32(900 + step + 3), board.Players[LOCK].Position.X + 3.0f * float(step),
                board.Players[LOCK].Position.Y + 0.5f, false, 100.0f));
        AdaptiveMaloriakPlan const fireEvade = Plan(board, LOCK);
        CHECK(fireEvade.Movement && fireEvade.Movement->Id.Mechanic == "magma_jet_fire_evade");
        for (ActorSnapshot const& summon : board.Summons)
            if (summon.Entry == 41901)
                CHECK(Dist(Destination(fireEvade), summon.Position) >= 4.5f);
        // Tanks do not run from Biting Chill.
        board.Players[DK].Auras.push_back({ 77760, Boss(board).Guid, 1, board.ObservedAtMs + 9000 });
        board.Players[DK].Position = { -105.8f, -452.0f, 73.6f };
        Boss(board).Cast.reset();
        board.Players[RET].Position = { -105.0f, -452.5f, 73.6f };
        CHECK(!Plan(board, DK).Movement);
    }

    // Main-tank taunt only on an aggressive, taunt-able boss.
    {
        Blackboard board = Canonical();
        Boss(board).VictimGuid = G(MAGE);
        CHECK(Plan(board, DK).TauntTarget == Boss(board).Guid);
        Boss(board).ReactAggressive = false;
        CHECK(!Plan(board, DK).TauntTarget);
        Boss(board).ReactAggressive = true;
        Boss(board).Auras.push_back({ 92716, Boss(board).Guid, 1, board.ObservedAtMs + 60000 });
        CHECK(!Plan(board, DK).TauntTarget);
    }

    // A dead Blood DK hands the boss to the Feral tank.
    {
        Blackboard board = Canonical();
        board.Players[DK].Alive = false;
        CHECK(std::string(Plan(board, FERAL).Duty) == "main_tank");
        CHECK(M::ResolveTanks(board).OffTank.IsEmpty());
        AssignmentLease lease;
        lease.Kind = AssignmentKind::Tank;
        lease.Slot = "main_tank";
        lease.AssigneeGuid = G(FERAL);
        lease.BackupGuid = G(DK);
        board.Players[DK].Alive = true;
        board.Assignments.push_back(lease);
        CHECK(M::ResolveTanks(board).MainTank == G(FERAL));
        CHECK(M::ResolveTanks(board).OffTank == G(DK));
    }

    // Unknown specs (arbitration fixture): the long-cooldown pool backs up
    // an empty short pool, hazards still move the player.
    {
        Blackboard board = Canonical();
        board.Players = { Player(101, "tank", "", -105.8f, -452.0f), Player(102, "tank", "", -100.0f, -452.0f),
            Player(103, "dps", "fire_mage", -106.0f, -440.0f) };
        Boss(board).Cast = CastSnapshot{ 77896, ObjectGuid(), 2, false, true };
        board.Hostiles.push_back(Add(41961, 91, -106.0f, -440.0f, false, 100.0f));
        AdaptiveMaloriakStrategy strategy;
        AdaptiveMaloriakPlan const plan = strategy.Propose(board, PlayerGuid(103), "dps");
        CHECK(plan.OwnsNode && plan.DamageTarget == Boss(board).Guid);
        CHECK(plan.InterruptTarget == Boss(board).Guid);
        CHECK(plan.Movement.has_value());
    }

    // Phase classification and a dead boss.
    {
        Blackboard board = Canonical();
        CHECK(std::string(Plan(board, MAGE).Phase) == "transition");
        Boss(board).Auras.push_back({ 92716, Boss(board).Guid, 1, 0 });
        CHECK(std::string(Plan(board, MAGE).Phase) == "black");
        Boss(board).Alive = false;
        CHECK(!Plan(board, MAGE).OwnsNode);
    }

    // Every formation anchor stays inside the laboratory floor rectangle.
    {
        for (Vector3 corner : { Vector3{ -144.0f, -414.0f, 73.6f }, Vector3{ -69.0f, -494.0f, 73.6f } })
        {
            ActorSnapshot boss;
            boss.Position = corner;
            boss.Facing = 0.7f;
            M::BossFrame const frame = M::ResolveFrame(boss, nullptr);
            for (std::size_t index = 0; index < 8; ++index)
                for (Vector3 point : { M::FrontStackSlot(frame, index), M::BackRangedSlot(frame, index, 8),
                         M::FrontMeleeSlot(frame, index), M::BackMeleeSlot(frame, index), M::BehindSlot(frame, index % 2) })
                {
                    CHECK(point.X >= M::RoomMinX && point.X <= M::RoomMaxX);
                    CHECK(point.Y >= M::RoomMinY && point.Y <= M::RoomMaxY);
                }
        }
        CHECK(Dist(M::AddAnchorFor({ -105.79f, -462.58f, 73.5f }), M::AddAnchorWest) < 0.01f);
        CHECK(Dist(M::AddAnchorFor({ -125.0f, -440.0f, 73.5f }), M::AddAnchorEast) < 0.01f);
        CHECK(Dist(M::AddAnchorWest, { -105.79f, -462.58f, 73.5f }) > 20.0f);
    }

    // Review 2d52afc3f4 (major 1): formation never returns a bot into a
    // hazard it just evaded. Phase two, raid spread behind the boss.
    {
        auto phaseTwo = []()
        {
            Blackboard board = Canonical();
            Boss(board).HealthPct = 20.0f;
            Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
            return board;
        };
        auto frameOf = [](Blackboard const& board)
        {
            return M::ResolveFrame(board.Hostiles.front(), &board.Players[DK]);
        };
        auto melee = [](Blackboard const& board)
        {
            std::vector<ActorSnapshot const*> group;
            for (ActorSnapshot const& player : board.Players)
                if (player.Role == "dps" && M::IsMeleeSpec(player.ClassSpec))
                    group.push_back(&player);
            std::sort(group.begin(), group.end(), [](ActorSnapshot const* a, ActorSnapshot const* b)
            { return a->Guid.GetRawValue() < b->Guid.GetRawValue(); });
            return group;
        };

        // A sphere sitting on the rogue's back melee slot, 3.5 yd from the
        // boss: every ring point is within 9 yd of it. The rogue, already at
        // its 11-yd exit point, holds (no formation move, offense held).
        Blackboard board = phaseTwo();
        std::vector<ActorSnapshot const*> const group = melee(board);
        std::size_t rogueIndex = 0;
        while (group[rogueIndex]->Guid != G(ROGUE))
            ++rogueIndex;
        Vector3 const rogueSlot = M::BackMeleeSlot(frameOf(board), rogueIndex);
        board.Summons.push_back(Add(41961, 820, rogueSlot.X, rogueSlot.Y, false, 100.0f));
        Vector3 const sphere = board.Summons.back().Position;
        board.Players[ROGUE].Position = { sphere.X + 11.0f, sphere.Y, 73.6f };
        AdaptiveMaloriakPlan const hold = Plan(board, ROGUE);
        CHECK(!hold.Movement);
        CHECK(hold.SuppressOffense && std::string(hold.SuppressReason) == "melee_ring_hazard_hold");
        // Inside the danger radius the hazard exit still wins.
        board.Players[ROGUE].Position = { sphere.X + 2.0f, sphere.Y, 73.6f };
        AdaptiveMaloriakPlan const evade = Plan(board, ROGUE);
        CHECK(evade.Movement && evade.Movement->Id.Mechanic == "absolute_zero_evade");
        CHECK(Dist(Destination(evade), sphere) >= 10.9f);

        // A sphere 6.5 yd from the boss leaves the far side of the ring clear:
        // the rogue shifts there instead of holding.
        Blackboard far = phaseTwo();
        M::BossFrame const farFrame = frameOf(far);
        Vector3 const nearSlot = M::FramePolar(farFrame, 6.5f, M::Pi + 50.0f * M::Pi / 180.0f);
        far.Summons.push_back(Add(41961, 821, nearSlot.X, nearSlot.Y, false, 100.0f));
        far.Players[ROGUE].Position = { nearSlot.X + 12.0f, nearSlot.Y + 12.0f, 73.6f };
        AdaptiveMaloriakPlan const shifted = Plan(far, ROGUE);
        CHECK(!shifted.SuppressOffense);
        CHECK(shifted.Movement && shifted.Movement->Id.Mechanic == "phase_two_spread");
        CHECK(Dist(Destination(shifted), far.Summons.back().Position) >= 9.0f);

        // Ranged: a sphere on the mage's fan slot; the mage at its exit
        // point gets either no move or a shifted fan point clear of the
        // sphere and 5 yd from every other ranged slot.
        Blackboard ranged = phaseTwo();
        M::BossFrame const rangedFrame = frameOf(ranged);
        std::vector<ActorSnapshot const*> casters;
        for (ActorSnapshot const& player : ranged.Players)
            if (player.Role != "tank" && !(player.Role == "dps" && M::IsMeleeSpec(player.ClassSpec)))
                casters.push_back(&player);
        std::sort(casters.begin(), casters.end(), [](ActorSnapshot const* a, ActorSnapshot const* b)
        { return a->Guid.GetRawValue() < b->Guid.GetRawValue(); });
        std::size_t mageIndex = 0;
        while (casters[mageIndex]->Guid != G(MAGE))
            ++mageIndex;
        Vector3 const mageSlot = M::BackRangedSlot(rangedFrame, mageIndex, casters.size());
        ranged.Summons.push_back(Add(41961, 822, mageSlot.X, mageSlot.Y, false, 100.0f));
        ranged.Players[MAGE].Position = { mageSlot.X, mageSlot.Y - 11.0f, 73.6f };
        AdaptiveMaloriakPlan const fan = Plan(ranged, MAGE);
        CHECK(fan.Movement.has_value());  // an 18-yd fan has room to shift
        if (fan.Movement)
        {
            CHECK(Dist(Destination(fan), mageSlot) >= 9.0f);
            for (std::size_t other = 0; other < casters.size(); ++other)
                if (other != mageIndex)
                    CHECK(Dist(Destination(fan), M::BackRangedSlot(rangedFrame, other, casters.size())) >= 5.0f);
        }
        CHECK(!fan.SuppressOffense);

        // Jet fire on the warlock's slot: same rule with the 6.5-yd clearance.
        Blackboard fire = phaseTwo();
        std::size_t lockIndex = 0;
        while (casters[lockIndex]->Guid != G(LOCK))
            ++lockIndex;
        Vector3 const lockSlot = M::BackRangedSlot(frameOf(fire), lockIndex, casters.size());
        fire.Summons.push_back(Add(41901, 823, lockSlot.X, lockSlot.Y, false, 100.0f));
        fire.Players[LOCK].Position = { lockSlot.X + 7.5f, lockSlot.Y, 73.6f };
        AdaptiveMaloriakPlan const jet = Plan(fire, LOCK);
        CHECK(jet.Movement.has_value());
        CHECK(!jet.Movement || Dist(Destination(jet), lockSlot) >= 6.5f);
        // Standing on the shifted point: nothing more to do.
        fire.Players[LOCK].Position = Destination(jet);
        CHECK(!Plan(fire, LOCK).Movement);
    }

    // Review minor 6: the Magma Jets sidestep point is the same on every
    // tick of one cast while the tank walks to it.
    {
        Blackboard board = Canonical();
        Boss(board).HealthPct = 20.0f;
        Boss(board).Auras.push_back({ 95663, Boss(board).Guid, 1, 0 });
        Boss(board).Cast = CastSnapshot{ 78194, G(DK), board.ObservedAtMs, false, false };
        Vector3 const first = Destination(Plan(board, DK));
        for (float fraction : { 0.25f, 0.5f, 0.75f })
        {
            Vector3 const start{ -105.8f, -452.0f, 73.6f };
            board.Players[DK].Position = { start.X + (first.X - start.X) * fraction,
                start.Y + (first.Y - start.Y) * fraction, 73.6f };
            board.ObservedAtMs += 100;
            board.Hostiles.front().Cast->ObservedAtMs = board.ObservedAtMs;
            AdaptiveMaloriakPlan const step = Plan(board, DK);
            CHECK(step.Movement && Dist(Destination(step), first) < 0.05f);
        }
        board.Players[DK].Position = first;
        CHECK(!Plan(board, DK).Movement);
    }

    // Review minor 6: add-spot hysteresis.
    {
        Vector3 const boss17{ M::AddAnchorWest.X + 17.0f, M::AddAnchorWest.Y, 73.6f };
        CHECK(Dist(M::AddAnchorFor(boss17), M::AddAnchorEast) < 0.01f);
        CHECK(Dist(M::AddAnchorFor(boss17, &M::AddAnchorWest), M::AddAnchorWest) < 0.01f);
        CHECK(Dist(M::AddAnchorFor(boss17, &M::AddAnchorEast), M::AddAnchorEast) < 0.01f);
        Vector3 const boss12{ M::AddAnchorWest.X + 12.0f, M::AddAnchorWest.Y, 73.6f };
        CHECK(Dist(M::AddAnchorFor(boss12, &M::AddAnchorWest), M::AddAnchorEast) < 0.01f);
        Vector3 const middle{ -105.0f, -420.0f, 73.6f };
        CHECK(Dist(M::AddAnchorFor(boss17, &middle), M::AddAnchorEast) < 0.01f);
    }

    // Review minor 4: Remedy difficulty variants (SpellDifficulty 3267).
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 92966, Boss(board).Guid, 1, board.ObservedAtMs + 9500 });
        CHECK(Plan(board, MAGE).DispelTarget == Boss(board).Guid);
    }

    return failures == 0 ? 0 : 1;
}
'''


def test_maloriak_strategy_replays_canonical_duties(tmp_path: Path) -> None:
    source = tmp_path / "maloriak_strategy.cpp"
    binary = tmp_path / "maloriak_strategy"
    source.write_text(PROGRAM, encoding="utf-8")
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_maloriak_strategy_headers_stay_small_and_lawful() -> None:
    folder = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak"
    headers = sorted(folder.glob("*.h"))
    assert {path.name for path in headers} >= {
        "BotAdaptiveMaloriakStrategy.h",
        "BotMaloriakDuties.h",
        "BotMaloriakFacts.h",
        "BotMaloriakGeometry.h",
        "BotMaloriakPlan.h",
    }
    for path in headers:
        text = path.read_text(encoding="utf-8")
        assert len(text.splitlines()) < 1000, path.name
        # Observation and proposal only: no server state, teleports or casts.
        for forbidden in ("Player*", "Creature*", "NearTeleportTo", "TeleportTo",
                          "CastSpell(", "AddAura(", "SetHealth("):
            assert forbidden not in text, (path.name, forbidden)


def test_maloriak_dispatch_module_revalidates_at_the_native_edge() -> None:
    folder = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak"
    module = (folder / "BotWorldPopulationMgrMaloriakCandidates.cpp").read_text(encoding="utf-8")
    assert "void BotWorldPopulationMgr::SubmitMaloriakKernelCandidates(" in module
    # Kill credit with Maloriak-specific identities (Magmaw's observer untouched).
    assert '"world.validation_route_maloriak_observation"' in module
    assert "RememberValidationRouteBossEngagement(creature)" in module
    assert '"adaptive_maloriak_route_observation_recorded"' in module
    assert "magmaw_route_observation" not in module
    # Interrupts: ended or uninterruptible casts are skipped, and Release
    # Aberrations is never interrupted (user tactic 2026-09-26).
    assert "FindCurrentSpellBySpellId(castSpellId)" in module
    assert "CanBeInterrupted(caster)" in module
    assert "if (castSpellId == BotEncounter::Maloriak::ReleaseAberrationsSpell)\n                return BotActionArbitration::Outcome::NotApplicable(\n                    \"release_aberrations_never_interrupted\");" in module
    assert "NativeReleaseAdmitted" not in module and "ReleaseAdmittedCounts" not in module
    # Remedy: every difficulty variant, offensive priest dispel 527 (not 528).
    assert "Maloriak::RemedySpells" in module
    assert "30449u, 370u, 19801u, 527u };" in module and " 528u" not in module
    # Round 4: the release veto is published natively each tick (every
    # release in phase one since the user tactic);
    # moves that start outside the laboratory take the route lane; assigned
    # interrupts and purges stop the bot's own hard cast (Remedy went
    # unpurged for 225000 healing) and purges hold the lanes through the GCD.
    assert "BotEncounter::Maloriak::ReleaseAberrationsSpell,\n            boss && boss->IsAlive());" in module
    assert "!BotEncounter::Maloriak::InRoom(" in module
    assert "BotMovementArbitration::Owner::Route" in module
    assert module.count("ClearOwnCastFor(context.Bot, healer,") == 2
    # Misdirection / Tricks onto the off-tank and the Frost Shock slow.
    assert "TryCastFriendlySpell(context.Bot, tank, spellId, &failure)" in module
    assert "if (context.Bot->HasAura(spellId))" in module
    assert "TryCastCombatSpell(context.Bot, target, spellId)" in module
    assert '"aberration_freeze_trap" : "aberration_ice_trap"' in module
    # Review item 8: traps (self range) are laid with the native self cast
    # at the plan's trap point, not through the hostile-target helper.
    trap = module[module.index("trap.Attempt = [this, &context, targetGuid = plan.TrapTarget,"):
                  module.index("DecisionKernel.Submit(std::move(trap));")]
    assert "BotNativeAction::CastSpell{ ObjectGuid::Empty, spellId }" in trap
    assert "TryCastCombatSpell" not in trap
    assert "> BotEncounter::Maloriak::KiteTrapTolerance)" in trap
    grasp = module[module.index("grasp.Attempt = [this, &context]()"):
                   module.index("DecisionKernel.Submit(std::move(grasp));")]
    assert "BotEncounter::Maloriak::NaturesGraspSpell" in grasp and "HasSpell(spellId)" in grasp
    assert '"native_dispel_wait_global_cooldown"' in module
    # The add switch restricts the boss at the native edge (with only the
    # target cleared, casters kept 65-73k DPS on him through the r05 holds).
    # The restriction comes from a route-authority hook that runs after the
    # adaptive reset every tick (as Omnotron's), never from a candidate the
    # kernel may not resolve; one Arcane Storm interrupt or taunt on him stays
    # allowed through the shared SingleCastAllowance, before its cast. Remedy
    # gets no allowance: the plan never assigns it during the switch.
    assert "ApplyPushHoldRestriction" not in module and "class PushHoldAllowance" not in module
    assert "SetCurrentEncounterRestrictions" not in module
    suppress = module.index("suppress.Attempt = [this, &context, reason]()")
    assert "Restriction" not in module[suppress:module.index("DecisionKernel.Submit(std::move(suppress));", suppress)]
    # One effective switch state (the cohort latch, its cap included).
    assert "bool const restricted = plan.AddSwitchRestricts;" in module
    assert "ObserveAddSwitch" not in module and "AddSwitchLatches" not in module
    for anchor, cast in (
            ("AllowOneCastOnBoss(allowance, context.Bot, restricted, caster);",
             "ClearOwnCastFor(context.Bot, healer, caster, interruptSpell)"),
            ("AllowOneCastOnBoss(allowance, context.Bot, restricted, target);\n            if (!TryCastCombatSpell(context.Bot, target, tauntSpell))",
             "TryCastCombatSpell(context.Bot, target, tauntSpell)")):
        assert module.index(anchor) < module.index(cast)
    dispel = module[module.index("dispel.Attempt = [this, &context, targetGuid = plan.DispelTarget]()"):
                    module.index("DecisionKernel.Submit(std::move(dispel));")]
    assert "allowance" not in dispel.replace("no allowance", "")
    assert module.count("std::optional<BotEncounterOffense::SingleCastAllowance> allowance;") == 2
    assert "allowance.emplace(bot->GetGUID().GetRawValue(),\n            BotEncounter::Maloriak::AddSwitchRestriction(), target->GetGUID());" in module
    hook = module[module.index("void BotWorldPopulationMgr::SubmitMaloriakRouteAuthority("):]
    order = [hook.index(marker) for marker in (
        "if (plan.AddSwitchCapReleased && ClaimAddSwitchCapReport(context.Bot, plan.Boss))",
        "bool const restricted = plan.AddSwitchRestricts;",
        "BotEncounterCooldownHold::Set(ownerGuid, restricted);",
        "BotEncounterOffense::SetGuardianAreaSparing(ownerGuid, restricted);",
        "BotEncounterOffense::ApplyOffenseRestriction(ownerGuid,\n        BotEncounter::Maloriak::AddSwitchRestriction());",
        "StopCastsReachingBoss(context.Bot, boss);",
        "pet->GetVictim()->GetGUID() == plan.Boss)",
        "context.Bot->GetGUID(), COMMAND_FOLLOW },")]
    assert order == sorted(order)
    # A long switch reports the boss health (a percentage, review item 11),
    # the reserve and the loose adds, once per boss.
    assert '"maloriak_add_switch_cap_released"' in hook
    assert "boss ? boss->GetHealthPct() : 0.0f;" in hook and "UnitHealthPct" not in hook
    assert "bossHealthPct, uint32(counts.second));" in hook
    # Review item 3: a running hostile area cast over the boss (ground
    # channel, self-centred) is stopped as well as one aimed at him; a
    # launched projectile lands, like a ticking DoT (no withDelayed cancel).
    # Re-review item 1: the slots the reach check finds are interrupted
    # themselves (a self-cast Hellfire's explicit target is the bot, which
    # the generic offensive-cast test would keep).
    reach = module[module.index("std::size_t StopCastsReachingBoss(Player* bot, Unit* boss)"):]
    reach = reach[:reach.index("\n}\n")]
    for token in ("GetUnitTargetGUID() == boss->GetGUID()", "SpellHasHostileMultiTargetSemantics(spellInfo)",
                  "spell->m_targets.HasDst()", "HostileAreaRadius(bot, spellInfo)", "CURRENT_AUTOREPEAT_SPELL",
                  "AddSwitchStopsCast(spellInfo->IsPositive(),",
                  "bot->InterruptSpell(slot, slot == CURRENT_CHANNELED_SPELL, true);"):
        assert token in reach, token
    assert "InterruptOffensiveCasts" not in module and "InterruptNonMeleeSpells(false);\n    return true;" in module
    assert "withDelayed" not in hook
    # Every plan move, the main tank's hold of its spot included, goes
    # through the ordinary native request: only a submitted move renews the
    # mechanic movement lease (a kernel-only hold let the combat profile's
    # range reconcile chase the boss again; delta review).
    attempt = module.index("movement.Attempt = [this, &context, survival, travel,")
    execute = module.index("ExecuteNativeActionIntent(\n                context.State, context.Bot, intent, owner, priority);", attempt)
    assert "return" not in module[attempt:execute]
    assert "main_tank_spot_hold" not in module
    # The veto is keyed by map and instance (per-map creature GUIDs).
    assert "BotEncounterInterruptVeto::Set(context.Bot->GetMapId(),\n            context.Bot->GetInstanceId(), plan.Boss.GetRawValue()," in module
    # The add-switch wait follows the latched plan state only.
    assert 'plan.SuppressReason != "add_switch_wait"' not in module
    # A bot stops its own cast only when the duty spell passes every other
    # TryCastCombatSpell gate (r03: Wind Shear no_line_of_sight 24 times).
    combat_spell = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrCombatSpell.cpp").read_text(encoding="utf-8")
    start = combat_spell.index("bool BotWorldPopulationMgr::TryCastCombatSpell(")
    try_cast = combat_spell[start:combat_spell.index("\n}\n", start)]
    start = module.index("bool DutySpellCastable(")
    duty = module[start:module.index("\n}\n", start)]
    identifiers = lambda body: set(re.findall(r"[A-Za-z_][A-Za-z_0-9]*", body))
    # Own casting state, facing and the cast itself are the only differences.
    exempt = {"TryCastCombatSpell", "BotWorldPopulationMgr", "forceFacing",
              "SetFacingToObject", "UNIT_STATE_CASTING", "CastSpell", "SPELL_CAST_OK"}
    assert identifiers(try_cast) - identifiers(duty) - exempt == set()
    assert "UNIT_STATE_CASTING" not in duty
    timers = (folder / "BotMaloriakNativeTimers.cpp").read_text(encoding="utf-8")
    assert "Maloriak::PublishedMechanicSpells" in timers
    assert "GetTimeUntilEncounterMechanic(spellId)" in timers
    assert "snapshot.Route.NodeId != Maloriak::EncounterNode" in timers
    for path in folder.glob("*.cpp"):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000, path.name


def test_raid_prepot_stage_waits_for_the_maloriak_pull_gate() -> None:
    """Round 3: the shared prepot stage reads the adaptive Maloriak plan, so no
    25 s potion is spent while the raid is dead, healing or still staging."""
    consumables = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrRaidConsumables.cpp").read_text(encoding="utf-8")
    stage = consumables.index("bool const prepotStageReady = PrepotStageReady(")
    call = consumables.index("TryRaidPrepullConsumables(", stage)
    wiring = consumables[stage:call]
    assert "context.AdaptiveMagmawSuppressReason" in wiring
    assert "maloriak->SuppressReason" in wiring
    assert "context.AdaptiveMaloriak.get()" in consumables[:call]


VETO_PROGRAM = r'''
#include "Bots/BotEncounterInterruptVeto.h"
#include <cassert>
#include <chrono>
#include <thread>

namespace V = BotEncounterInterruptVeto;

struct Info { uint32 Id; };
struct FakeSpell { Info info; Info const* GetSpellInfo() const { return &info; } };
struct FakeGuid { uint64 raw; uint64 GetRawValue() const { return raw; } };
struct FakeCaster
{
    uint32 map;
    uint32 instance;
    FakeGuid guid;
    FakeSpell spell;
    int castType;
    uint32 GetMapId() const { return map; }
    uint32 GetInstanceId() const { return instance; }
    FakeGuid GetGUID() const { return guid; }
    FakeSpell const* GetCurrentSpell(int type) const { return type == castType ? &spell : nullptr; }
};

int main()
{
    assert(!V::IsVetoed(669, 5, 7, 77569));
    V::Set(669, 5, 7, 77569, true, 60000);
    assert(V::IsVetoed(669, 5, 7, 77569));
    assert(!V::IsVetoed(669, 5, 7, 77896) && !V::IsVetoed(669, 5, 8, 77569));
    // Creature GUIDs are per map: the same GUID in another instance of map
    // 669 (or another map) is a different caster.
    assert(!V::IsVetoed(669, 6, 7, 77569) && !V::IsVetoed(670, 5, 7, 77569));
    V::Set(669, 6, 7, 77569, false);
    assert(V::IsVetoed(669, 5, 7, 77569));
    V::Set(669, 5, 7, 77569, false);
    assert(!V::IsVetoed(669, 5, 7, 77569) && V::Leases.empty());
    // A lapsed lease is not a veto and is dropped.
    V::Set(669, 5, 7, 77569, true, 1);
    std::this_thread::sleep_for(std::chrono::milliseconds(5));
    assert(!V::IsVetoed(669, 5, 7, 77569) && V::Leases.empty());
    // The current generic cast or channel of the caster, in its own instance.
    FakeCaster caster{ 669, 5, { 7 }, { { 77569 } }, 1 };
    V::Set(669, 5, 7, 77569, true, 60000);
    assert(V::IsCurrentCastVetoed(&caster, 1, 2));
    caster.castType = 2;
    assert(V::IsCurrentCastVetoed(&caster, 1, 2));
    caster.castType = 3;
    assert(!V::IsCurrentCastVetoed(&caster, 1, 2));
    caster.castType = 1;
    caster.instance = 6;
    assert(!V::IsCurrentCastVetoed(&caster, 1, 2));
    caster.instance = 5;
    caster.spell.info.Id = 77896;
    assert(!V::IsCurrentCastVetoed(&caster, 1, 2));
    assert(!V::IsCurrentCastVetoed<FakeCaster>(nullptr, 1, 2));
    return 0;
}
'''


def test_encounter_interrupt_veto_lease_and_resolver_gate(tmp_path: Path) -> None:
    """Round 4: generic profile interrupts honour an encounter veto (the r03
    attempt cut every Release Aberrations, so 25% freed all 18 Aberrations).
    The veto is keyed by map, instance and caster GUID."""
    source = tmp_path / "interrupt_veto.cpp"
    binary = tmp_path / "interrupt_veto"
    source.write_text(VETO_PROGRAM, encoding="utf-8")
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-pthread"]
    for include in INCLUDES:
        command += ["-I", str(ROOT / include)]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)

    header = (ROOT / "src/server/game/Bots/BotEncounterInterruptVeto.h").read_text(encoding="utf-8")
    assert "caster->GetMapId(), caster->GetInstanceId()," in header
    assert "only the kernel profile resolver" in header
    # The resolver's candidate gates live in its admission module (round 4 split).
    bots = ROOT / "src/server/game/Bots"
    resolver = (bots / "BotWorldPopulationMgrCombatResolverAdmission.cpp").read_text(encoding="utf-8")
    assert '#include "Bots/BotEncounterInterruptVeto.h"' in resolver
    assert "BotEncounterInterruptVeto::IsCurrentCastVetoed(target," in resolver
    gate = resolver.index('candidate.RejectReason = "encounter_interrupt_vetoed";')
    assert "candidate.Category == BotCombatActionCategory::Interrupt && targetCastVetoed" in resolver[gate - 200:gate]
    for name in ("BotWorldPopulationMgrCombatResolver.cpp", "BotWorldPopulationMgrCombatResolverAdmission.cpp"):
        assert len((bots / name).read_text(encoding="utf-8").splitlines()) < 1000

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

static AdaptiveMaloriakPlan Plan(Blackboard const& board, Slot slot)
{
    AdaptiveMaloriakStrategy strategy;
    return strategy.Propose(board, G(slot), board.Players[slot].Role);
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

    // Release Aberrations: admitted while fewer than six are loose; the
    // second and third short interrupters stop it otherwise.
    {
        Blackboard board = Canonical();
        Boss(board).Cast = CastSnapshot{ 77569, ObjectGuid(), board.ObservedAtMs, false, true };
        for (uint32 index = 0; index < 18; ++index)
            board.Summons.push_back(Add(41440, 200 + index, -140.0f, -430.0f, index < 3, 100.0f));
        for (Slot slot : { RET, ROGUE, SHAMAN, DK })
            CHECK(!Plan(board, slot).InterruptTarget);
        for (uint32 index = 3; index < 6; ++index)
            board.Summons[index].Selectable = board.Summons[index].Attackable = true;
        CHECK(!Interrupts(board, RET, 77569));
        CHECK(Interrupts(board, ROGUE, 77569) && Interrupts(board, SHAMAN, 77569));
        CHECK(std::string(Plan(board, ROGUE).InterruptLane) == "release_aberrations_quota");
        for (ActorSnapshot& aberration : board.Summons)
            aberration.Selectable = aberration.Attackable = true;
        CHECK(!Plan(board, ROGUE).InterruptTarget);
        CHECK(M::Observe(board).ReserveAberrations == 0);
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

    // Green / add control: burn Aberrations in the slime window, the off-tank
    // picks up and taunts loose adds, then holds them at the add spot.
    {
        Blackboard board = Canonical();
        board.Summons.push_back(Add(41440, 401, -128.0f, -436.0f, true, 80.0f));
        board.Summons.push_back(Add(41440, 402, -129.0f, -433.0f, true, 50.0f));
        board.Summons.push_back(Add(41440, 403, -131.0f, -435.0f, true, 90.0f));
        for (ActorSnapshot& add : board.Summons)
            add.VictimGuid = G(FERAL);
        CHECK(Plan(board, MAGE).DamageTarget == Boss(board).Guid);
        Boss(board).Auras.push_back({ 92917, Boss(board).Guid, 1, board.ObservedAtMs + 30000 });
        Boss(board).Auras.push_back({ 77615, ObjectGuid(), 1, board.ObservedAtMs + 14000 });
        AdaptiveMaloriakPlan const burn = Plan(board, MAGE);
        CHECK(burn.DamageTarget == board.Summons[1].Guid);
        CHECK(std::string(burn.Duty) == "aberration_slime_burn");
        CHECK(Plan(board, ROGUE).DamageTarget == board.Summons[1].Guid);
        CHECK(!Plan(board, ROGUE).Movement);
        AdaptiveMaloriakPlan const hold = Plan(board, FERAL);
        CHECK(std::string(hold.Duty) == "off_tank_hold");
        CHECK(hold.DamageTarget == board.Summons[1].Guid);
        CHECK(!hold.Movement && !hold.TauntTarget);
        board.Players[FERAL].Position = { -105.0f, -440.0f, 73.6f };
        AdaptiveMaloriakPlan const drag = Plan(board, FERAL);
        CHECK(drag.Movement && drag.Movement->Id.Mechanic == "off_tank_add_anchor");
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

    // Outside the slime window: overflow and pre-25% cleanup.
    {
        Blackboard board = Canonical();
        for (uint32 index = 0; index < 5; ++index)
            board.Summons.push_back(Add(41440, 500 + index, -130.0f, -434.0f, true, 100.0f - index));
        CHECK(Plan(board, LOCK).DamageTarget == Boss(board).Guid);
        board.Summons.push_back(Add(41440, 505, -130.0f, -434.0f, true, 60.0f));
        CHECK(Plan(board, LOCK).DamageTarget == board.Summons.back().Guid);
        // Green in 10 s: six loose Aberrations wait for the slime window.
        Boss(board).MechanicTimers.push_back({ 77937, 10000, false, FactSource::NativeInstanceState });
        CHECK(Plan(board, LOCK).DamageTarget == Boss(board).Guid);
        Boss(board).MechanicTimers.clear();
        board.Summons.pop_back();
        Boss(board).HealthPct = 29.0f;
        CHECK(Plan(board, LOCK).DamageTarget == board.Summons[4].Guid);
        // A leaping Aberration (released, still immune) is not a target yet.
        for (ActorSnapshot& add : board.Summons)
            add.Attackable = false;
        CHECK(Plan(board, LOCK).DamageTarget == Boss(board).Guid);
    }

    // Round 4 (r03 wipe): every Release Aberrations was cut by profile
    // interrupts, so 25% freed 18 Aberrations and 2 Prime Subjects. The plan
    // publishes whether a release is admitted (the dispatch turns it into an
    // interrupt veto) and holds boss damage below 30% while the chambers
    // still hold more than one release. The hold is bounded by tank damage
    // and a 90 s cap, so it does not drain the chambers to 3: at the r03 raid
    // damage about 6-9 Aberrations plus both Prime Subjects still come at 25%.
    {
        Blackboard board = Canonical();
        Boss(board).Auras.push_back({ 78895, Boss(board).Guid, 1, 0 });
        for (uint32 index = 0; index < 18; ++index)
            board.Summons.push_back(Add(41440, 1000 + index, -140.0f, -430.0f, false, 100.0f));
        AdaptiveMaloriakPlan const early = Plan(board, MAGE);
        CHECK(early.Boss == Boss(board).Guid);
        CHECK(early.ReleaseAdmitted);
        CHECK(!early.SuppressOffense && early.DamageTarget == Boss(board).Guid);
        for (Slot slot : { DK, FERAL, HOLY, ROGUE })
            CHECK(Plan(board, slot).ReleaseAdmitted);
        // Six loose: the next release is interrupted (no veto).
        for (uint32 index = 0; index < 6; ++index)
            board.Summons[index].Selectable = board.Summons[index].Attackable = true;
        CHECK(!Plan(board, MAGE).ReleaseAdmitted);
        for (uint32 index = 0; index < 6; ++index)
            board.Summons[index].Alive = false;
        CHECK(Plan(board, MAGE).ReleaseAdmitted);

        // 28% with 12 in the chambers and none loose: damage dealers and
        // healers hold, tanks keep the boss; the boss stays the formation
        // target.
        Boss(board).HealthPct = 28.0f;
        for (Slot slot : { MAGE, ROGUE, LOCK, HOLY, DISC })
        {
            AdaptiveMaloriakPlan const hold = Plan(board, slot);
            CHECK(hold.SuppressOffense);
            CHECK(std::string(hold.SuppressReason) == "phase_two_push_hold");
            CHECK(hold.DamageTarget == Boss(board).Guid);
        }
        AdaptiveMaloriakPlan const tank = Plan(board, DK);
        CHECK(!tank.SuppressOffense && tank.DamageTarget == Boss(board).Guid);
        // Every bot, tanks included, reports the same window for the latch.
        for (Slot slot : { DK, FERAL, MAGE, HOLY })
            CHECK(Plan(board, slot).PushHoldWindow);
        // Without a living tank nobody would push to 25%: no hold.
        board.Players[DK].Alive = false;
        board.Players[FERAL].Alive = false;
        CHECK(!Plan(board, MAGE).PushHoldWindow);
        CHECK(!Plan(board, MAGE).SuppressOffense);
        board.Players[DK].Alive = true;
        board.Players[FERAL].Alive = true;
        // A released batch is burned instead of waiting.
        board.Summons[6].Selectable = board.Summons[6].Attackable = true;
        AdaptiveMaloriakPlan const burn = Plan(board, LOCK);
        CHECK(!burn.SuppressOffense && burn.DamageTarget == board.Summons[6].Guid);
        CHECK(Plan(board, HOLY).SuppressOffense);
        board.Summons[6].Alive = false;
        // Three or fewer left in the chambers: push to 25%.
        for (uint32 index = 7; index < 15; ++index)
            board.Summons[index].Alive = false;
        CHECK(!Plan(board, MAGE).SuppressOffense);
        CHECK(!Plan(board, HOLY).SuppressOffense);
        // Above 30% nothing waits; phase two never waits and admits nothing.
        for (uint32 index = 7; index < 15; ++index)
            board.Summons[index].Alive = true;
        Boss(board).HealthPct = 31.0f;
        CHECK(!Plan(board, MAGE).SuppressOffense);
        Boss(board).HealthPct = 24.0f;
        AdaptiveMaloriakPlan const two = Plan(board, MAGE);
        CHECK(std::string(two.Phase) == "phase_two");
        CHECK(!two.SuppressOffense && !two.ReleaseAdmitted && !two.PushHoldWindow);
    }

    // The dispatch's push-hold latch: starts at the first observation of the
    // window, stands down after 90 s, resets when the window closes.
    {
        uint64 started = 0;
        CHECK(!M::PushHoldWithinCap(started, false, 5000) && started == 0);
        CHECK(M::PushHoldWithinCap(started, true, 10000) && started == 10000);
        CHECK(M::PushHoldWithinCap(started, true, 99999));
        CHECK(!M::PushHoldWithinCap(started, true, 100000));
        CHECK(!M::PushHoldWithinCap(started, true, 150000) && started == 10000);
        CHECK(!M::PushHoldWithinCap(started, false, 150001) && started == 0);
        CHECK(M::PushHoldWithinCap(started, true, 200000) && started == 200000);
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

    // Review minor 3: one short interrupter keeps Arcane Storm; the long
    // pool (Counterspell) takes Release Aberrations.
    {
        M::InterruptPools pools;
        pools.Short = { G(RET) };
        pools.Long = { G(MAGE) };
        CHECK(M::ReleaseInterrupters(pools) == std::vector<ObjectGuid>{ G(MAGE) });
        pools.Long.clear();
        CHECK(M::ReleaseInterrupters(pools).empty());
        pools.Short.clear();
        pools.Long = { G(MAGE), G(FERAL) };
        CHECK(M::ReleaseInterrupters(pools) == std::vector<ObjectGuid>{ G(FERAL) });
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
    # Interrupts: ended, uninterruptible or admitted releases are skipped.
    assert "FindCurrentSpellBySpellId(castSpellId)" in module
    assert "CanBeInterrupted(caster)" in module
    assert "NativeReleaseAdmitted(caster)" in module
    assert "ReleaseAdmittedCounts(loose, reserve," in module
    # Remedy: every difficulty variant, offensive priest dispel 527 (not 528).
    assert "Maloriak::RemedySpells" in module
    assert "30449u, 370u, 19801u, 527u };" in module and " 528u" not in module
    # Round 4: the admitted-release veto is published natively each tick;
    # moves that start outside the laboratory take the route lane; assigned
    # interrupts and purges stop the bot's own hard cast (Remedy went
    # unpurged for 225000 healing) and purges hold the lanes through the GCD.
    assert "boss && boss->IsAlive() && NativeReleaseAdmitted(boss)" in module
    assert "!BotEncounter::Maloriak::InRoom(" in module
    assert "BotMovementArbitration::Owner::Route" in module
    assert module.count("ClearOwnCastFor(context.Bot, healer,") == 2
    assert '"native_dispel_wait_global_cooldown"' in module
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
    # The push hold stands down after the cap.
    assert "PushHoldHonoured(context.Bot, plan," in module
    assert 'plan.SuppressReason != "phase_two_push_hold"' in module
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

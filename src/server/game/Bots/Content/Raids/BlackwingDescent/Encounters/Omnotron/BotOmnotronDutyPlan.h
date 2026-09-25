#ifndef TRINITY_BOT_OMNOTRON_DUTY_PLAN_H
#define TRINITY_BOT_OMNOTRON_DUTY_PLAN_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronCapabilities.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronInterruptLedger.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Omnotron/BotOmnotronShieldLedger.h"
#include <algorithm>
#include <sstream>
#include <string>
#include <vector>

// Who owns each Omnotron duty on one snapshot. Every owner is chosen from
// observed state and capability (class/spec, role, range, personal debuffs),
// never from a roster slot, so any composition with two tanks resolves.
namespace BotEncounter::Omnotron
{
// Tactic parameters (not encounter values): a backup interrupter waits this
// long into a cast so one cast does not burn two cooldowns (cast 1.5 s,
// client 79710); the dispel threshold spends a healer GCD only once Soaked
// In Poison (5000 per stack every 2 s on 10N) has stacked or the carrier is
// low; a free tank walks to the next construct this long before it activates.
inline constexpr uint64 InterruptBackupDelayMs = 450;
inline constexpr uint8 SoakedInPoisonDispelStacks = 3;
inline constexpr float SoakedInPoisonDispelHealthPct = 50.0f;
inline constexpr uint64 StandbyLeadMs = 12000;

struct TankDuty
{
    ObjectGuid Tank;
    ObjectGuid Construct;
    ObjectGuid Standby;
};

struct InterruptDuty
{
    ObjectGuid Caster;
    ObjectGuid Primary;
    ObjectGuid Backup;
    uint64 Ordinal = 0;
    uint64 CastAgeMs = 0;
    std::vector<ObjectGuid> Pool;
};

struct DispelDuty
{
    ObjectGuid Dispeller;
    ObjectGuid Target;
    uint8 Stacks = 0;
};

struct DutyPlan
{
    bool Applies = false;
    bool Engaged = false;
    uint64 Revision = 0;
    std::vector<TankDuty> Tanks;
    ObjectGuid DamageFocus;
    ObjectGuid DamageFallback;
    // Active constructs whose one shield of this activation has come and gone.
    std::vector<ObjectGuid> ShieldSpent;
    ObjectGuid BombTarget;
    InterruptDuty Interrupt;
    std::vector<DispelDuty> Dispels;
    std::vector<ObjectGuid> MovementDuty;

    TankDuty const* TankDutyFor(ObjectGuid tank) const
    {
        for (TankDuty const& duty : Tanks)
            if (duty.Tank == tank)
                return &duty;
        return nullptr;
    }

    ObjectGuid DispelTargetFor(ObjectGuid bot) const
    {
        for (DispelDuty const& duty : Dispels)
            if (duty.Dispeller == bot)
                return duty.Target;
        return ObjectGuid{};
    }

    bool HasMovementDuty(ObjectGuid bot) const
    {
        return std::find(MovementDuty.begin(), MovementDuty.end(), bot)
            != MovementDuty.end();
    }
};

enum class LedgerMode : uint8
{
    Observe,
    Peek
};

inline bool FixatedByLivingBomb(ActorSnapshot const& player,
    EncounterFacts const& facts)
{
    for (AuraSnapshot const& aura : player.Auras)
        if (aura.SpellId == FixateAura)
            for (ActorSnapshot const* bomb : facts.PoisonBombs)
                if (bomb->Guid == aura.CasterGuid)
                    return true;
    for (ActorSnapshot const* bomb : facts.PoisonBombs)
        if (bomb->VictimGuid == player.Guid)
            return true;
    return false;
}

// Debuffs that make a player run on their own: Lightning Conductor, Acquiring
// Target, a Poison Bomb fixate, and heroic Encasing Shadows (rooted).
inline bool HasPersonalMovementDuty(ActorSnapshot const& player,
    EncounterFacts const& facts)
{
    return CarriesLightningConductor(player) || IsAcquiredTarget(player)
        || HasAura(player, EncasingShadowsAura)
        || FixatedByLivingBomb(player, facts);
}

inline uint8 SoakedStacks(ActorSnapshot const& player)
{
    AuraSnapshot const* aura = FindAnyAura(player, SoakedInPoisonAura);
    return aura ? std::max<uint8>(aura->Stacks, 1) : 0;
}

namespace Detail
{
inline void AssignTanks(Blackboard const& board, EncounterFacts const& facts,
    DutyPlan& plan)
{
    std::vector<ActorSnapshot const*> tanks;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Role == "tank")
            tanks.push_back(&player);
    std::sort(tanks.begin(), tanks.end(), [](auto left, auto right)
    {
        return left->Guid < right->Guid;
    });
    for (ActorSnapshot const* tank : tanks)
        plan.Tanks.push_back(TankDuty{ tank->Guid, {}, {} });

    std::vector<ConstructFact const*> fighting;
    for (ConstructFact const& fact : facts.Constructs)
        if (fact.Fighting())
            fighting.push_back(&fact);
    std::sort(fighting.begin(), fighting.end(), [](auto left, auto right)
    {
        if (left->ActivatedExpiresAtMs != right->ActivatedExpiresAtMs)
            return left->ActivatedExpiresAtMs < right->ActivatedExpiresAtMs;
        return left->Actor->Guid < right->Actor->Guid;
    });

    std::vector<ConstructFact const*> unowned;
    for (ConstructFact const* fact : fighting)
    {
        auto duty = std::find_if(plan.Tanks.begin(), plan.Tanks.end(),
            [fact](TankDuty const& tank)
            {
                return tank.Tank == fact->Actor->VictimGuid;
            });
        if (duty != plan.Tanks.end() && duty->Construct.IsEmpty())
            duty->Construct = fact->Actor->Guid;
        else
            unowned.push_back(fact);
    }
    for (ConstructFact const* fact : unowned)
        for (TankDuty& duty : plan.Tanks)
            if (duty.Construct.IsEmpty())
            {
                duty.Construct = fact->Actor->Guid;
                break;
            }

    ConstructFact const* next = nullptr;
    for (ConstructFact const& fact : facts.Constructs)
        if (fact.Recharging && fact.RechargeExpiresAtMs
            && (!next || fact.RechargeExpiresAtMs < next->RechargeExpiresAtMs))
            next = &fact;
    if (next && next->RechargeExpiresAtMs <= board.ObservedAtMs + StandbyLeadMs)
        for (TankDuty& duty : plan.Tanks)
            if (duty.Construct.IsEmpty())
            {
                duty.Standby = next->Actor->Guid;
                break;
            }
}

// Damage focus, in order:
// 1. an active construct whose shield of this activation is spent: it cannot
//    shield again before it shuts down;
// 2. otherwise the newest active unshielded construct.
// At steady state this leaves each construct alone from ~16 s after its
// activation until its own shield ends, so damage over time applied to it
// (up to 21 s) has expired before its shield (Barrier absorbs periodic damage
// and breaks into Backdraft). Only the opening construct, alone for 45 s,
// still carries fresh DoTs into its shield. Shielded or shield-casting
// constructs are never chosen.
inline void ChooseDamageTargets(Blackboard const& board,
    EncounterFacts const& facts, LedgerMode mode, DutyPlan& plan)
{
    ConstructFact const* spent = nullptr;
    ConstructFact const* focus = nullptr;
    ConstructFact const* fallback = nullptr;
    auto newer = [](ConstructFact const* left, ConstructFact const& right)
    {
        return !left || right.ActivatedExpiresAtMs > left->ActivatedExpiresAtMs
            || (right.ActivatedExpiresAtMs == left->ActivatedExpiresAtMs
                && right.Actor->Guid < left->Actor->Guid);
    };
    for (ConstructFact const& fact : facts.Constructs)
    {
        ShieldLedger::Sample const sample{ fact.Actor->Guid, fact.Active,
            fact.Shielded(), fact.ActivatedExpiresAtMs };
        ShieldObservation const shield = mode == LedgerMode::Observe
            ? ShieldLedger::Observe(board, sample) : ShieldLedger::Peek(board, sample);
        if (!fact.Active || fact.Shielded())
            continue;
        if (shield.Spent())
            plan.ShieldSpent.push_back(fact.Actor->Guid);
        if (fact.Fighting() && shield.Spent() && newer(spent, fact))
            spent = &fact;
        if (fact.Fighting() && newer(focus, fact))
            focus = &fact;
        if (newer(fallback, fact))
            fallback = &fact;
    }
    if (spent)
        focus = spent;
    plan.DamageFocus = focus ? focus->Actor->Guid : ObjectGuid{};
    plan.DamageFallback = fallback ? fallback->Actor->Guid : ObjectGuid{};

    // A Poison Bomb is killed only where its blast (6 yd) reaches nobody, or
    // when it already touches its fixate target.
    ActorSnapshot const* urgent = nullptr;
    float urgentDistance = 0.0f;
    for (ActorSnapshot const* bomb : facts.PoisonBombs)
    {
        ObjectGuid const fixate = BombFixateTarget(board, *bomb);
        ActorSnapshot const* chased = fixate.IsEmpty() ? nullptr
            : board.FindActor(fixate);
        float const chaseDistance = chased
            ? PlanarDistance(chased->Position, bomb->Position) : 100.0f;
        bool safe = chaseDistance <= 3.0f;
        if (!safe)
        {
            safe = true;
            for (ActorSnapshot const& player : board.Players)
                if (player.Alive && PlanarDistance(player.Position, bomb->Position)
                        <= PoisonBombBlastRadius + 1.0f)
                    safe = false;
        }
        if (safe && (!urgent || chaseDistance < urgentDistance))
        {
            urgent = bomb;
            urgentDistance = chaseDistance;
        }
    }
    plan.BombTarget = urgent ? urgent->Guid : ObjectGuid{};
}

inline int InterruptTier(ActorSnapshot const& player,
    InterruptCapability const& capability)
{
    bool const tank = player.Role == "tank";
    if (capability.CooldownMs <= 10000)
        return tank ? 2 : (capability.Melee ? 0 : 1);
    if (capability.CooldownMs <= 15000)
        return tank ? 2 : 1;
    return tank ? 4 : 3;
}

inline void AssignInterrupts(Blackboard const& board,
    EncounterFacts const& facts, LedgerMode mode, DutyPlan& plan)
{
    ConstructFact const* arcanotron = facts.FindKind(ConstructKind::Arcanotron);
    if (!arcanotron)
        return;
    ActorSnapshot const& caster = *arcanotron->Actor;
    bool const casting = arcanotron->Active && caster.Cast
        && InSet(ArcaneAnnihilatorCast, caster.Cast->SpellId)
        && caster.Cast->Interruptible;
    InterruptCastObservation const observed = mode == LedgerMode::Observe
        ? InterruptLedger::Observe(board, caster.Guid, casting)
        : InterruptLedger::Peek(board, caster.Guid, casting);
    if (!casting)
        return;

    struct Entry
    {
        ActorSnapshot const* Player;
        InterruptCapability Capability;
        int Tier;
    };
    std::vector<Entry> pool;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive || player.Role == "healer")
            continue;
        std::optional<InterruptCapability> const capability =
            InterruptFor(player.ClassSpec);
        if (!capability)
            continue;
        // Under Power Conversion every interrupt that lands procs a Converted
        // Power stack, damaging or not: spell_proc 79729 has SpellTypeMask 0
        // (all types) and a no-damage spell hit still raises a NODAMAGE proc
        // (Spell.cpp TargetInfo). The rotation keeps interrupting (one stack
        // against a 39-41k Annihilator); stacks per interrupt are a live
        // signal and the retail behaviour an open research question.
        // Melee-range interrupts (5 yd) reach the server's melee range
        // (combat reaches plus 4/3 yd); longer ones (Skull Bash 13 yd, ranged)
        // add the construct's combat reach. Half a yard of slack.
        float const reach = capability->RangeYards <= 5.0f
            ? PlayerCombatReach + ConstructCombatReach + 4.0f / 3.0f
            : capability->RangeYards + ConstructCombatReach;
        if (PlanarDistance(player.Position, caster.Position) > reach + 0.5f)
            continue;
        // A player running from a personal mechanic interrupts last.
        pool.push_back(Entry{ &player, *capability,
            InterruptTier(player, *capability)
                + (HasPersonalMovementDuty(player, facts) ? 5 : 0) });
    }
    std::sort(pool.begin(), pool.end(), [](Entry const& left, Entry const& right)
    {
        if (left.Tier != right.Tier)
            return left.Tier < right.Tier;
        if (left.Capability.CooldownMs != right.Capability.CooldownMs)
            return left.Capability.CooldownMs < right.Capability.CooldownMs;
        return left.Player->Guid < right.Player->Guid;
    });

    plan.Interrupt.Caster = caster.Guid;
    plan.Interrupt.Ordinal = observed.Ordinal;
    plan.Interrupt.CastAgeMs = observed.AgeMs(board.ObservedAtMs);
    for (Entry const& entry : pool)
        plan.Interrupt.Pool.push_back(entry.Player->Guid);
    if (pool.empty())
        return;
    std::size_t const turn = std::size_t(observed.Ordinal ? observed.Ordinal - 1 : 0);
    plan.Interrupt.Primary = pool[turn % pool.size()].Player->Guid;
    if (pool.size() > 1)
        plan.Interrupt.Backup = pool[(turn + 1) % pool.size()].Player->Guid;
}

inline void AssignDispels(Blackboard const& board, EncounterFacts const& facts,
    DutyPlan& plan)
{
    std::vector<ActorSnapshot const*> targets;
    std::vector<ActorSnapshot const*> dispellers;
    for (ActorSnapshot const& player : board.Players)
    {
        if (!player.Alive)
            continue;
        uint8 const stacks = SoakedStacks(player);
        if (stacks >= SoakedInPoisonDispelStacks
            || (stacks && player.HealthPct < SoakedInPoisonDispelHealthPct))
            targets.push_back(&player);
        if (CanCleansePoison(player.ClassSpec, player.Role)
            && !HasPersonalMovementDuty(player, facts))
            dispellers.push_back(&player);
    }
    std::sort(targets.begin(), targets.end(), [](auto left, auto right)
    {
        uint8 const leftStacks = SoakedStacks(*left);
        uint8 const rightStacks = SoakedStacks(*right);
        if (leftStacks != rightStacks)
            return leftStacks > rightStacks;
        return left->Guid < right->Guid;
    });
    std::sort(dispellers.begin(), dispellers.end(), [](auto left, auto right)
    {
        bool const leftHealer = left->Role == "healer";
        bool const rightHealer = right->Role == "healer";
        if (leftHealer != rightHealer)
            return leftHealer;
        return left->Guid < right->Guid;
    });
    for (std::size_t index = 0; index < targets.size() && index < dispellers.size(); ++index)
        plan.Dispels.push_back(DispelDuty{ dispellers[index]->Guid,
            targets[index]->Guid, SoakedStacks(*targets[index]) });
}
}

inline DutyPlan BuildDutyPlan(Blackboard const& board, EncounterFacts const& facts,
    LedgerMode mode)
{
    DutyPlan plan;
    plan.Revision = board.Revision;
    plan.Applies = board.Route.NodeId == EncounterNodeId && !facts.Constructs.empty();
    if (!plan.Applies)
        return plan;
    plan.Engaged = facts.Engaged;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && HasPersonalMovementDuty(player, facts))
            plan.MovementDuty.push_back(player.Guid);
    Detail::AssignTanks(board, facts, plan);
    Detail::ChooseDamageTargets(board, facts, mode, plan);
    Detail::AssignInterrupts(board, facts, mode, plan);
    Detail::AssignDispels(board, facts, plan);
    return plan;
}

inline std::string DutyPlanJson(DutyPlan const& plan)
{
    std::ostringstream json;
    json << "{\"applies\":" << (plan.Applies ? "true" : "false")
         << ",\"revision\":" << plan.Revision;
    if (plan.Applies)
    {
        auto list = [&json](char const* key, std::vector<ObjectGuid> const& guids)
        {
            json << ",\"" << key << "\":[";
            for (std::size_t index = 0; index < guids.size(); ++index)
                json << (index ? "," : "") << guids[index].GetCounter();
            json << ']';
        };
        json << ",\"engaged\":" << (plan.Engaged ? "true" : "false")
             << ",\"tanks\":[";
        for (std::size_t index = 0; index < plan.Tanks.size(); ++index)
            json << (index ? "," : "") << "{\"tank\":"
                 << plan.Tanks[index].Tank.GetCounter() << ",\"construct\":"
                 << plan.Tanks[index].Construct.GetCounter() << ",\"standby\":"
                 << plan.Tanks[index].Standby.GetCounter() << '}';
        json << ']';
        list("shield_spent", plan.ShieldSpent);
        json << ",\"damage_focus\":" << plan.DamageFocus.GetCounter()
             << ",\"damage_fallback\":" << plan.DamageFallback.GetCounter()
             << ",\"bomb_target\":" << plan.BombTarget.GetCounter()
             << ",\"interrupt\":{\"caster\":" << plan.Interrupt.Caster.GetCounter()
             << ",\"primary\":" << plan.Interrupt.Primary.GetCounter()
             << ",\"backup\":" << plan.Interrupt.Backup.GetCounter()
             << ",\"ordinal\":" << plan.Interrupt.Ordinal;
        list("pool", plan.Interrupt.Pool);
        json << "},\"dispels\":[";
        for (std::size_t index = 0; index < plan.Dispels.size(); ++index)
            json << (index ? "," : "") << "{\"dispeller\":"
                 << plan.Dispels[index].Dispeller.GetCounter() << ",\"target\":"
                 << plan.Dispels[index].Target.GetCounter() << ",\"stacks\":"
                 << unsigned(plan.Dispels[index].Stacks) << '}';
        json << ']';
        list("movement_duty", plan.MovementDuty);
    }
    json << '}';
    return json.str();
}

// Status field: read-only (Peek) so a status poll never advances the
// interrupt rotation.
inline std::string BuildOmnotronDutyPlanStatusJson(Blackboard const* board)
{
    if (!board)
        return "{\"applies\":false,\"revision\":0}";
    EncounterFacts const facts = Observe(*board);
    return DutyPlanJson(BuildDutyPlan(*board, facts, LedgerMode::Peek));
}
}

#endif

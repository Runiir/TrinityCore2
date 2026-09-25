#ifndef TRINITY_BOT_NEFARIAN_TACTICS_H
#define TRINITY_BOT_NEFARIAN_TACTICS_H

// Per-bot decisions that do not move the bot: target choice, Blast Nova
// interrupts and bone warrior control. Each returns a typed native request;
// the executor keeps every native rule (known spell, cooldown, range, LOS).

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianDutyPlan.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianGeometry.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianNativeFacts.h"
#include <optional>
#include <string>

namespace BotEncounter::Nefarian
{
// Phase 1 Electrocute budget (Wowhead and Icy Veins): bring Onyxia low, move
// damage to Nefarian for two Electrocutes, then finish Onyxia before her
// charge nears overload. Each Electrocute adds 17 charge natively
// (boss_nefarians_end.cpp EVENT_ELECTROCUTE); guides report 25.
constexpr float OnyxiaSwapHealthPct = 12.0f;
constexpr float NefarianPhaseOneFloorPct = 73.0f;
constexpr uint32 OnyxiaChargeReturnThreshold = 60;

inline ObjectGuid PhaseOneDamageTarget(EncounterView const& view)
{
    if (!view.OnyxiaAlive())
        return ObjectGuid();
    ActorSnapshot const& onyxia = *view.Onyxia;
    bool const nefarianOpen = view.NefarianLanded()
        && view.Nefarian->HealthPct > NefarianPhaseOneFloorPct;
    bool const chargeSafe = onyxia.AlternatePower < OnyxiaChargeReturnThreshold;
    if (nefarianOpen && chargeSafe && onyxia.HealthPct <= OnyxiaSwapHealthPct)
        return view.Nefarian->Guid;
    return onyxia.Guid;
}

inline ActorSnapshot const* PillarPrototype(EncounterView const& view,
    int pillar)
{
    if (pillar < 0)
        return nullptr;
    LocalPoint const centre = PillarCenters[pillar % 3];
    ActorSnapshot const* best = nullptr;
    float bestDistance = 18.0f;
    for (ActorSnapshot const* prototype : view.Prototypes)
    {
        float const distance = Distance(WorldToLocal(prototype->Position), centre);
        if (distance < bestDistance)
        {
            bestDistance = distance;
            best = prototype;
        }
    }
    return best;
}

inline float Distance3(Vector3 const& left, Vector3 const& right)
{
    float const dx = left.X - right.X;
    float const dy = left.Y - right.Y;
    float const dz = left.Z - right.Z;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}

struct InterruptDecision
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    std::string_view Reason;
};

inline int PrototypePillar(ActorSnapshot const& prototype)
{
    LocalPoint const at = WorldToLocal(prototype.Position);
    for (int pillar = 0; pillar < 3; ++pillar)
        if (Distance(at, PillarCenters[pillar]) < 18.0f)
            return pillar;
    return -1;
}

// Spell range plus both combat reaches (Spell::CheckRange), less a margin;
// melee interrupts use the prototype's melee reach.
inline bool InInterruptReach(ActorSnapshot const& member,
    ActorSnapshot const& prototype)
{
    InterruptCapability const capability = InterruptFor(member.ClassSpec);
    if (!member.Alive || !capability.Known())
        return false;
    float const reach = capability.RangeYards <= 5.0f ? PrototypeMeleeReach
        : capability.RangeYards + 1.5f + 4.375f - 1.0f;
    return Distance3(member.Position, prototype.Position) <= reach;
}

// Who interrupts one casting prototype, in order: its pillar's primary and
// backup, then its other team members, then anyone else in reach, shortest
// cooldown first. Only members that can reach it now are listed.
inline std::vector<ActorSnapshot const*> BlastNovaInterrupters(
    Blackboard const& board, DutyPlan const& plan,
    ActorSnapshot const& prototype)
{
    int const pillar = PrototypePillar(prototype);
    std::vector<ActorSnapshot const*> order;
    auto add = [&order, &prototype](ActorSnapshot const* member)
    {
        if (member && InInterruptReach(*member, prototype)
            && std::find(order.begin(), order.end(), member) == order.end())
            order.push_back(member);
    };
    if (pillar >= 0)
    {
        PillarTeam const& team = plan.Pillars[pillar];
        if (!team.PrimaryInterrupter.IsEmpty())
            add(board.FindActor(team.PrimaryInterrupter));
        if (!team.BackupInterrupter.IsEmpty())
            add(board.FindActor(team.BackupInterrupter));
    }
    std::vector<ActorSnapshot const*> others;
    for (ActorSnapshot const& player : board.Players)
        others.push_back(&player);
    std::stable_sort(others.begin(), others.end(),
        [&plan, pillar](ActorSnapshot const* left, ActorSnapshot const* right)
    {
        bool const leftTeam = plan.PillarOf(left->Guid) == pillar;
        bool const rightTeam = plan.PillarOf(right->Guid) == pillar;
        if (leftTeam != rightTeam)
            return leftTeam;
        uint32 const a = InterruptFor(left->ClassSpec).CooldownMs;
        uint32 const b = InterruptFor(right->ClassSpec).CooldownMs;
        if (a != b)
            return a < b;
        return left->Guid.GetCounter() < right->Guid.GetCounter();
    });
    for (ActorSnapshot const* member : others)
        add(member);
    return order;
}

// The first listed interrupter acts as soon as Blast Nova is observed (4 s
// cast in 10N/25N). The second acts once native cast progress shows 1.8 s
// elapsed, so the first had its chance.
inline InterruptDecision DecideBlastNovaInterrupt(Blackboard const& board,
    EncounterView const& view, DutyPlan const& plan, ActorSnapshot const& bot,
    NativeFacts const* facts)
{
    InterruptDecision decision;
    InterruptCapability const own = InterruptFor(bot.ClassSpec);
    if (!own.Known() || !bot.Alive)
        return decision;
    for (ActorSnapshot const* prototype : view.Prototypes)
    {
        if (!prototype->Cast || !IsBlastNova(prototype->Cast->SpellId)
            || !prototype->Cast->Interruptible)
            continue;
        std::vector<ActorSnapshot const*> const order =
            BlastNovaInterrupters(board, plan, *prototype);
        CastProgress const* progress = facts
            ? facts->FindCast(prototype->Guid) : nullptr;
        bool const late = progress && progress->ElapsedMs() >= 1800;
        bool const first = !order.empty() && order[0]->Guid == bot.Guid;
        bool const second = late && order.size() > 1
            && order[1]->Guid == bot.Guid;
        if (!first && !second)
            continue;
        int const pillar = PrototypePillar(*prototype);
        PillarTeam const* team = pillar >= 0 ? &plan.Pillars[pillar] : nullptr;
        decision.Target = prototype->Guid;
        decision.SpellId = own.SpellId;
        decision.Reason = second ? "blast_nova_backup_primary_late"
            : team && bot.Guid == team->PrimaryInterrupter ? "blast_nova_primary"
            : team && bot.Guid == team->BackupInterrupter
                ? "blast_nova_backup_primary_unavailable"
            : "blast_nova_reachable_interrupter";
        return decision;
    }
    return decision;
}

struct ControlDecision
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    std::string_view Reason;
};

inline bool InControlRange(ActorSnapshot const& member,
    ActorSnapshot const& warrior)
{
    ControlCapability const control = ControlFor(member.ClassSpec);
    if (!member.Alive || !control.Known())
        return false;
    float const range = control.SelfCentred ? control.RangeYards
        : control.RangeYards + BoneWarriorMeleeReach - 4.0f;
    return Distance3(member.Position, warrior.Position) <= range;
}

inline uint8 EmpowerStacks(ActorSnapshot const& warrior)
{
    for (AuraSnapshot const& aura : warrior.Auras)
        if (aura.SpellId == 79330 || aura.SpellId == 94091
            || aura.SpellId == 94092 || aura.SpellId == 94093)
            return aura.Stacks;
    return 0;
}

// The warrior the shackler would hold now: the most empowered free warrior in
// its range, and none while a shackle is already held (one at a time).
inline ActorSnapshot const* ShackleCandidate(Blackboard const& board,
    std::vector<ActorSnapshot const*> const& active, DutyPlan const& plan)
{
    ActorSnapshot const* shackler = plan.Shackler.IsEmpty() ? nullptr
        : board.FindActor(plan.Shackler);
    if (!shackler || !shackler->Alive)
        return nullptr;
    if (std::any_of(active.begin(), active.end(), [](ActorSnapshot const* warrior)
        {
            return HasAura(*warrior, SpellShackleUndead);
        }))
        return nullptr;
    ActorSnapshot const* best = nullptr;
    for (ActorSnapshot const* warrior : active)
        if (!IsBoneWarriorControlled(*warrior)
            && InControlRange(*shackler, *warrior)
            && (!best || EmpowerStacks(*warrior) > EmpowerStacks(*best)))
            best = warrior;
    return best;
}

// Exactly one bot acts on a warrior per snapshot: the shackler on its
// candidate, otherwise the first living controller in range, rotating from
// controller i mod C for warrior i. Nobody controls a held warrior, and
// nobody damages the shackler's candidate (Shackle Undead breaks on damage).
inline ControlDecision DecideBoneWarriorControl(Blackboard const& board,
    EncounterView const& view, DutyPlan const& plan, ActorSnapshot const& bot)
{
    ControlDecision decision;
    std::vector<ActorSnapshot const*> active;
    for (ActorSnapshot const* warrior : view.BoneWarriors)
        if (IsActiveBoneWarrior(*warrior))
            active.push_back(warrior);
    if (active.empty())
        return decision;
    ControlCapability const control = ControlFor(bot.ClassSpec);
    if (!control.Known())
        return decision;
    ActorSnapshot const* shackle = ShackleCandidate(board, active, plan);

    if (bot.Guid == plan.Shackler)
    {
        if (shackle)
        {
            decision.Target = shackle->Guid;
            decision.SpellId = control.SpellId;
            decision.Reason = "bone_warrior_shackle";
        }
        return decision;
    }

    auto const self = std::find(plan.Controllers.begin(),
        plan.Controllers.end(), bot.Guid);
    if (self == plan.Controllers.end())
        return decision;
    std::size_t const index = std::size_t(self - plan.Controllers.begin());
    std::size_t const controllers = plan.Controllers.size();
    for (std::size_t warrior = 0; warrior < active.size(); ++warrior)
    {
        ActorSnapshot const& target = *active[warrior];
        if (&target == shackle || IsBoneWarriorControlled(target))
            continue;
        std::size_t designated = controllers;
        for (std::size_t step = 0; step < controllers; ++step)
        {
            std::size_t const candidate = (warrior + step) % controllers;
            ActorSnapshot const* member = board.FindActor(
                plan.Controllers[candidate]);
            if (member && InControlRange(*member, target))
            {
                designated = candidate;
                break;
            }
        }
        if (designated != index)
            continue;
        decision.Target = target.Guid;
        decision.SpellId = control.SpellId;
        decision.Reason = control.Kind == ControlKind::Stun
            ? "bone_warrior_stun" : control.Kind == ControlKind::Root
            ? "bone_warrior_root" : "bone_warrior_snare";
        return decision;
    }
    return decision;
}

// An active warrior chasing this bot, if any is within the kite trigger.
inline ActorSnapshot const* ChasingBoneWarrior(EncounterView const& view,
    ActorSnapshot const& bot, float triggerYards = 14.0f)
{
    ActorSnapshot const* nearest = nullptr;
    float nearestDistance = triggerYards;
    for (ActorSnapshot const* warrior : view.BoneWarriors)
    {
        if (!IsActiveBoneWarrior(*warrior) || warrior->VictimGuid != bot.Guid)
            continue;
        float const distance = Distance3(warrior->Position, bot.Position);
        if (distance < nearestDistance)
        {
            nearest = warrior;
            nearestDistance = distance;
        }
    }
    return nearest;
}
}

#endif

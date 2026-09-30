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
// Phase 1 (user raid experience 2026-09-26): Bloodlust and burn Onyxia from
// the pull, before Nefarian lands; that skips most of phase 1. The raid lust
// is the canonical boss-lust fallback (BotRaidBossLust.h): Onyxia is a boss
// mob (type_flags 0x4, Creature::isWorldBoss), so the lust owner casts about
// 5 s after her tank holds her.
// Heroic keeps the old Electrocute budget as a fallback (the user expects the
// Onyxia burn may not hold there): Onyxia low, then Nefarian for two
// Electrocutes (each adds 17 charge natively, boss_nefarians_end.cpp
// EVENT_ELECTROCUTE), then finish Onyxia before her charge nears overload.
enum class PhaseOnePacing : uint8
{
    OnyxiaBurn,
    ElectrocuteBudget
};

inline PhaseOnePacing PhaseOnePacingFor(NativeFacts const* facts)
{
    return facts && facts->Heroic ? PhaseOnePacing::ElectrocuteBudget
        : PhaseOnePacing::OnyxiaBurn;
}

constexpr float OnyxiaSwapHealthPct = 12.0f;
constexpr float NefarianPhaseOneFloorPct = 73.0f;
constexpr uint32 OnyxiaChargeReturnThreshold = 60;

// Round 7 (the first live attempt's pull): the damage dealers burn Onyxia
// from the pull, but only once a tank has her (the user's tactic). In r06 the
// warlock opened on her 1.2 s before any tank and her melee hit damage
// dealers for 34 s. Held: she attacks a dragon tank, or her tank is dead or
// missing (nobody left to wait for).
// Who picks Onyxia up now: her tank, or - if it is dead or missing - the
// Nefarian tank (the Blood DK), or nobody (then the damage dealers do not
// wait: nobody is left to wait for).
inline ObjectGuid OnyxiaTankNow(Blackboard const& board, DutyPlan const& plan)
{
    for (ObjectGuid tank : { plan.OnyxiaTank, plan.NefarianTank })
        if (ActorSnapshot const* actor = tank.IsEmpty() ? nullptr : board.FindActor(tank);
            actor && actor->Alive)
            return tank;
    return ObjectGuid();
}

// Whether this bot tanks Onyxia now: only while she lives. With the Feral
// dead the Blood DK keeps her until she dies (the user's tactic burns her
// first) and holds Nefarian's taunt until then; once she is dead or gone it
// is the full Nefarian tank again.
inline bool ActsAsOnyxiaTank(Blackboard const& board, EncounterView const& view,
    DutyPlan const& plan, ObjectGuid guid)
{
    return view.OnyxiaAlive() && !guid.IsEmpty() && guid == OnyxiaTankNow(board, plan);
}

inline bool OnyxiaHeldByTank(Blackboard const& board, EncounterView const& view,
    DutyPlan const& plan, NativeFacts const* facts = nullptr)
{
    if (!view.OnyxiaAlive())
        return true;
    ObjectGuid const victim = view.Onyxia->VictimGuid;
    if (!victim.IsEmpty() && (victim == plan.OnyxiaTank || victim == plan.NefarianTank))
        return true;
    ObjectGuid const tank = OnyxiaTankNow(board, plan);
    // Nobody left to wait for, or the pickup's budget is spent: the damage
    // dealers start on her anyway.
    return tank.IsEmpty() || (facts && facts->PickupExhausted(tank, view.Onyxia->Guid));
}

inline ObjectGuid PhaseOneDamageTarget(EncounterView const& view,
    PhaseOnePacing pacing = PhaseOnePacing::OnyxiaBurn)
{
    if (!view.OnyxiaAlive())
        return ObjectGuid();
    ActorSnapshot const& onyxia = *view.Onyxia;
    if (pacing == PhaseOnePacing::OnyxiaBurn)
        return onyxia.Guid;
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
// cooldown first. Only members that can reach it now and that know their
// interrupt and have it ready (NativeFacts; no entry counts as both) are
// listed.
inline std::vector<ActorSnapshot const*> BlastNovaInterrupters(
    Blackboard const& board, DutyPlan const& plan,
    ActorSnapshot const& prototype, NativeFacts const* facts = nullptr)
{
    int const pillar = PrototypePillar(prototype);
    std::vector<ActorSnapshot const*> order;
    auto add = [&order, &prototype, facts](ActorSnapshot const* member)
    {
        if (member && InInterruptReach(*member, prototype)
            && (!facts || facts->SpellUsable(member->Guid,
                InterruptFor(member->ClassSpec).SpellId))
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
            BlastNovaInterrupters(board, plan, *prototype, facts);
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

// A point a bone warrior may be led to: well outside Nefarian's front cone
// (his breath wakes, refills and empowers warriors; confirmed by the user) and
// outside his tail.
constexpr float WarriorFrontMarginDeg = 15.0f;

// How deep a point lies in the warrior exclusion (radians past its edge; 0
// outside it): the breath cone widened by WarriorFrontMarginDeg, and the tail
// cone, both within the cones' 60-yard radius.
inline float WarriorDanger(EncounterView const& view, LocalPoint point)
{
    if (!view.Nefarian || !view.Nefarian->Alive || !view.NefarianLanded())
        return 0.0f;
    DragonPose const nefarian = PoseOf(*view.Nefarian);
    if (Distance(nefarian.Position, point) > DragonConeRadius)
        return 0.0f;
    float const off = OffFacing(nefarian.Position, nefarian.Facing, point);
    float const front = DegToRad(BreathHalfAngleDeg + WarriorFrontMarginDeg) - off;
    float const rear = off - (Pi - DegToRad(TailLashHalfAngleDeg + 8.0f));
    return std::max(0.0f, std::max(front, rear));
}

inline bool WarriorPointSafe(EncounterView const& view, LocalPoint point)
{
    return WarriorDanger(view, point) <= 0.0f;
}

inline uint8 EmpowerStacks(ActorSnapshot const& warrior)
{
    for (AuraSnapshot const& aura : warrior.Auras)
        if (aura.SpellId == 79330 || aura.SpellId == 94091
            || aura.SpellId == 94092 || aura.SpellId == 94093)
            return aura.Stacks;
    return 0;
}

// Bone warriors (user raid experience 2026-09-26): the warrior handler (the
// Feral Onyxia tank, free once Onyxia is dead) kites them and roots them with
// Nature's Grasp, always away from Nefarian's front: his Shadowflame Breath
// wakes a collapsed warrior, refills its energy and buffs it
// (spell_nefarians_end_shadowflame_breath). Shackle Undead stays as cheap
// backup control: the shackler holds the most empowered active warrior that
// is not on the handler, one at a time. The old stun/root/snare rotation is
// gone; the Onyxia burn leaves few active warriors.
// The warrior the shackler reserves: none while it is dead or cannot cast
// Shackle Undead now (unknown or not ready), so the handler takes that
// warrior instead of leaving it to nobody.
// Round 3: never a warrior in Nefarian's front. Held there it only waits for
// his next breath to refill it (the chase model in test_nefarian_movement.py
// kept one shackled on his tank for 46 s); the handler takes it out instead.
inline ActorSnapshot const* ShackleCandidate(Blackboard const& board,
    std::vector<ActorSnapshot const*> const& active, DutyPlan const& plan,
    NativeFacts const* facts = nullptr, EncounterView const* view = nullptr)
{
    ActorSnapshot const* shackler = plan.Shackler.IsEmpty() ? nullptr
        : board.FindActor(plan.Shackler);
    if (!shackler || !shackler->Alive
        || (facts && !facts->SpellUsable(shackler->Guid, SpellShackleUndead)))
        return nullptr;
    if (std::any_of(active.begin(), active.end(), [](ActorSnapshot const* warrior)
        {
            return HasAura(*warrior, SpellShackleUndead);
        }))
        return nullptr;
    ActorSnapshot const* best = nullptr;
    for (ActorSnapshot const* warrior : active)
        if (!IsBoneWarriorControlled(*warrior)
            && !HasAura(*warrior, SpellNaturesGraspRoot)
            && (plan.WarriorHandler.IsEmpty()
                || warrior->VictimGuid != plan.WarriorHandler)
            && InControlRange(*shackler, *warrior)
            && (!view || WarriorPointSafe(*view, WorldToLocal(warrior->Position)))
            && (!best || EmpowerStacks(*warrior) > EmpowerStacks(*best)))
            best = warrior;
    return best;
}

inline ControlDecision DecideShackle(Blackboard const& board,
    EncounterView const& view, DutyPlan const& plan, ActorSnapshot const& bot,
    NativeFacts const* facts = nullptr)
{
    ControlDecision decision;
    if (bot.Guid != plan.Shackler)
        return decision;
    std::vector<ActorSnapshot const*> active;
    for (ActorSnapshot const* warrior : view.BoneWarriors)
        if (IsActiveBoneWarrior(*warrior))
            active.push_back(warrior);
    ActorSnapshot const* shackle = ShackleCandidate(board, active, plan, facts, &view);
    if (!shackle)
        return decision;
    decision.Target = shackle->Guid;
    decision.SpellId = SpellShackleUndead;
    decision.Reason = "bone_warrior_shackle";
    return decision;
}

// The handler's Nature's Grasp: once an active warrior that attacks it is
// close, and the handler knows the spell, has it ready and is not carrying it.
constexpr float NaturesGraspTriggerYards = 12.0f;

inline bool DecideNaturesGrasp(EncounterView const& view, DutyPlan const& plan,
    ActorSnapshot const& bot, NativeFacts const* facts)
{
    uint32 const spell = WarriorRootFor(bot.ClassSpec);
    if (!spell || bot.Guid != plan.WarriorHandler || !bot.Alive
        || HasAura(bot, spell)
        || (facts && !facts->SpellUsable(bot.Guid, spell)))
        return false;
    return std::any_of(view.BoneWarriors.begin(), view.BoneWarriors.end(),
        [&bot](ActorSnapshot const* warrior)
        {
            return IsActiveBoneWarrior(*warrior) && warrior->VictimGuid == bot.Guid
                && Distance3(warrior->Position, bot.Position) <= NaturesGraspTriggerYards;
        });
}

struct HealDecision
{
    ObjectGuid Target;
    uint32 SpellId = 0;
    std::string_view Reason;
};

// A team without a healer is healed by its off-healer: the lowest living
// member of the team under OffHealThresholdPct, with the off-healer's native
// heal. Interrupts come first (the strategy asks this only when no interrupt
// is due).
constexpr float OffHealThresholdPct = 90.0f;
constexpr float OffHealRangeYards = 40.0f; // Healing Surge, Flash of Light (SpellRange 5)

inline HealDecision DecideOffHeal(Blackboard const& board, EncounterView const& view,
    DutyPlan const& plan, ActorSnapshot const& bot, NativeFacts const* facts)
{
    HealDecision decision;
    int const pillar = plan.PillarOf(bot.Guid);
    if (!PhaseWantsPillar(view.CurrentPhase) || pillar < 0 || !bot.Alive
        || plan.Pillars[pillar].OffHealer != bot.Guid)
        return decision;
    uint32 const spell = OffHealFor(bot.ClassSpec);
    if (!spell || (facts && !facts->SpellUsable(bot.Guid, spell)))
        return decision;
    // Only teammates the heal can reach now (range and line of sight) are
    // ranked, so one out of reach never blocks the others.
    ActorSnapshot const* lowest = nullptr;
    for (ObjectGuid guid : plan.Pillars[pillar].Members)
        if (ActorSnapshot const* member = board.FindActor(guid))
            if (member->Alive && member->HealthPct < OffHealThresholdPct
                && Distance3(member->Position, bot.Position) <= OffHealRangeYards
                && (!facts || facts->InSight(member->Guid))
                && (!lowest || member->HealthPct < lowest->HealthPct))
                lowest = member;
    if (!lowest)
        return decision;
    decision.Target = lowest->Guid;
    decision.SpellId = spell;
    decision.Reason = "pillar_off_heal";
    return decision;
}

// Before the magma reaches the floor (Onyxia dead, the ring not yet under):
// the priest shields everyone without a shield or Weakened Soul, the team
// without a healer first; the Holy paladin tops up the lowest member under
// 95%, the same team first.
constexpr float PreAscentRangeYards = 40.0f;
constexpr float PreAscentTopUpPct = 95.0f;

inline HealDecision DecidePreAscentCare(Blackboard const& board, EncounterView const& view,
    DutyPlan const& plan, ActorSnapshot const& bot, NativeFacts const* facts)
{
    HealDecision decision;
    if (view.CurrentPhase != Phase::PlatformAscent || !bot.Alive
        || view.Elevator.State == ElevatorState::Lowered)
        return decision;
    uint32 const shield = PreAscentShieldFor(bot.ClassSpec);
    uint32 const topUp = PreAscentTopUpFor(bot.ClassSpec);
    uint32 const spell = shield ? shield : topUp;
    if (!spell || (facts && !facts->SpellUsable(bot.Guid, spell)))
        return decision;
    auto unhealed = [&plan](ObjectGuid guid)
    {
        int const pillar = plan.PillarOf(guid);
        return pillar >= 0 && plan.Pillars[pillar].Healer.IsEmpty();
    };
    ActorSnapshot const* best = nullptr;
    for (ActorSnapshot const& member : board.Players)
    {
        if (!member.Alive || Distance3(member.Position, bot.Position) > PreAscentRangeYards
            || (facts && !facts->InSight(member.Guid)))
            continue;
        if (shield ? HasAnyAura(member, { SpellPowerWordShield, SpellWeakenedSoul })
                : member.HealthPct >= PreAscentTopUpPct)
            continue;
        if (!best || unhealed(member.Guid) > unhealed(best->Guid)
            || (unhealed(member.Guid) == unhealed(best->Guid)
                && member.HealthPct < best->HealthPct))
            best = &member;
    }
    if (!best)
        return decision;
    decision.Target = best->Guid;
    decision.SpellId = spell;
    decision.Reason = shield ? "pre_ascent_shield" : "pre_ascent_top_up";
    return decision;
}

// The nearest active, unheld warrior chasing this bot within the kite
// trigger. A held one (rooted, stunned, shackled) chases nobody, and must not
// mask an unheld one behind it.
inline ActorSnapshot const* ChasingBoneWarrior(EncounterView const& view,
    ActorSnapshot const& bot, float triggerYards = 14.0f)
{
    ActorSnapshot const* nearest = nullptr;
    float nearestDistance = triggerYards;
    for (ActorSnapshot const* warrior : view.BoneWarriors)
    {
        if (!IsActiveBoneWarrior(*warrior) || warrior->VictimGuid != bot.Guid
            || IsBoneWarriorHeld(*warrior))
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

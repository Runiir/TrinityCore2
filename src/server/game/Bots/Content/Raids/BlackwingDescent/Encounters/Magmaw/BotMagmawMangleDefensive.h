#ifndef TRINITY_BOT_MAGMAW_MANGLE_DEFENSIVE_H
#define TRINITY_BOT_MAGMAW_MANGLE_DEFENSIVE_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlustTiming.h"

#include <array>
#include <optional>

namespace BotEncounter::MagmawMangleDefensive
{
using MagmawBloodlust::BossEntry;
using MagmawBloodlust::EncounterNode;
using MagmawBloodlust::MassiveCrashSpell;

// Mangle seizes Magmaw's current victim (spell_magmaw_mangle keeps only the
// victim). 89773/91912/94616/94617 are the 10N/25N/10H/25H periodic auras;
// 78412 is the seat aura applied when the target boards seat 2.
constexpr std::array<uint32, 5> MangleAuras = {
    89773, 91912, 94616, 94617, 78412,
};

constexpr uint32 IceboundFortitudeSpell = 48792;
constexpr uint32 VampiricBloodSpell = 55233;
constexpr uint32 BoneShieldSpell = 49222;

// Strongest first.  Icebound Fortitude cuts all damage taken by 20% (35%
// with Sanguine Fortitude) for 12 s, off the global cooldown, 3 min
// cooldown.  Vampiric Blood (10 s, 1 min cooldown, off the GCD) raises
// healing received by 25% and grants 15% of maximum health; that health is
// removed on expiry, but AuraEffect::HandleAuraModIncreaseHealth never takes
// the last point, so the expiry alone cannot kill.  It is the Mangle
// defensive only when Icebound cannot cover this Mangle (b3-0dbce440-k1:
// Icebound spent 30 s earlier, no cooldown at the seize, Mangle killed the
// tank).  Bone Shield cuts damage by 20% for its charges (one per hit, 2 s
// apart), on the GCD.
constexpr std::array<uint32, 3> DefensivePriority = {
    IceboundFortitudeSpell, VampiricBloodSpell, BoneShieldSpell,
};

// Native Magmaw publishes the time until the next Mangle under the Massive
// Crash spell id.  Mangle's weapon hit lands when the event fires and its
// first periodic tick 2 s later.  Icebound Fortitude (or Vampiric Blood in
// its place) cast 1.5 s ahead covers the hit and the first ticks.  Bone
// Shield lasts 5 min, so it gets a longer lead to find a free global
// cooldown and rune.  The encounter blackboard refreshes every 100 ms, well
// inside both leads.
constexpr uint32 PreMangleIceboundLeadMs = 1500;
constexpr uint32 PreMangleBoneShieldLeadMs = 6000;

inline uint32 PreMangleLeadMs(uint32 spellId)
{
    return spellId == IceboundFortitudeSpell || spellId == VampiricBloodSpell
        ? PreMangleIceboundLeadMs : PreMangleBoneShieldLeadMs;
}

// Bone Shield starts with 6 charges (4.3.4 SpellAuraOptions procCharges) and
// a recast resets them (Aura::ModStackAmount -> SetCharges(CalcMaxCharges)).
// b3-0dbce440-k1 recast it at 62.1 s and ran out at 86.2 s, 4 s before the
// seize.  Below 3 charges it no longer covers the hit and the first ticks,
// so the lead refreshes it when its own cooldown is ready.
constexpr uint8 BoneShieldRefreshBelowCharges = 3;

inline bool BoneShieldCovers(bool hasAura, uint8 charges)
{
    return hasAura && charges >= BoneShieldRefreshBelowCharges;
}

// boss_magmaw.cpp repeats EVENT_MANGLE every 1min + 35s, and the first one is
// 90 s after pull, so a live timer never exceeds 95 s.  The boss reports 0 for
// an overdue Mangle; a larger value can only be EventMap::GetTimeUntilEvent's
// uint32 subtraction wrapping on an overdue event (~4.29e9 ms).  Treat it as
// due now rather than 71 minutes away.
constexpr uint32 NativeMangleRepeatMs = 95000;

inline uint32 MangleDueInMs(uint32 publishedMs)
{
    return publishedMs > NativeMangleRepeatMs ? 0 : publishedMs;
}

enum class DefensiveTrigger : uint8
{
    PreMangleLead,
    Mangled
};

struct DefensiveWindow
{
    ObjectGuid BossGuid;
    ObjectGuid TankGuid;
    DefensiveTrigger Trigger = DefensiveTrigger::PreMangleLead;
    uint32 RemainingMs = 0;
};

inline char const* DefensiveTriggerName(DefensiveTrigger trigger)
{
    return trigger == DefensiveTrigger::Mangled
        ? "mangled" : "pre_mangle_lead";
}

inline bool IsMangleAura(uint32 spellId)
{
    for (uint32 aura : MangleAuras)
        if (aura == spellId)
            return true;
    return false;
}

inline bool HasMangleAura(ActorSnapshot const& actor)
{
    for (AuraSnapshot const& aura : actor.Auras)
        if (IsMangleAura(aura.SpellId))
            return true;
    return false;
}

// The tank is about to be, or already is, seized by Mangle.  Only the
// engaged boss with a native Mangle timer opens the pre-Mangle lead, and
// only for the boss's current victim, because Mangle lands on the victim.
inline std::optional<DefensiveWindow> ObserveMangleDefensiveWindow(
    Blackboard const& board, ObjectGuid tankGuid)
{
    if (tankGuid.IsEmpty() || board.Route.NodeId != EncounterNode
        || board.NativeBossState != "in_progress")
        return std::nullopt;

    ActorSnapshot const* boss = MagmawBloodlust::FindBoss(board);
    if (!boss || !boss->InCombat)
        return std::nullopt;

    ActorSnapshot const* tank = nullptr;
    for (ActorSnapshot const& member : board.Players)
        if (member.Guid == tankGuid)
            tank = &member;
    if (!tank || !tank->Alive)
        return std::nullopt;

    if (HasMangleAura(*tank))
        return DefensiveWindow{ boss->Guid, tankGuid,
            DefensiveTrigger::Mangled, 0 };

    MechanicTimerSnapshot const* mangle =
        boss->FindMechanicTimer(MassiveCrashSpell);
    if (!mangle || mangle->Source != FactSource::NativeInstanceState)
        return std::nullopt;
    // The boss publishes 0 while the Mangle -> Massive Crash sequence runs
    // and for a Mangle held past its due time by a cast; MangleDueInMs also
    // maps a wrapped overdue value to 0.  Once Mangle has seized someone
    // else, the victim check below closes the window.
    uint32 const remainingMs = mangle->SequenceActive
        ? 0 : MangleDueInMs(mangle->RemainingMs);
    if (remainingMs > PreMangleBoneShieldLeadMs)
        return std::nullopt;
    if (boss->VictimGuid != tankGuid)
        return std::nullopt;
    return DefensiveWindow{ boss->Guid, tankGuid,
        DefensiveTrigger::PreMangleLead, remainingMs };
}

inline bool WithinLead(DefensiveWindow const& window, uint32 spellId)
{
    return window.Trigger == DefensiveTrigger::Mangled
        || window.RemainingMs <= PreMangleLeadMs(spellId);
}

// Active means the running aura already covers the hit: for Bone Shield,
// BoneShieldCovers (at least 3 charges).
struct DefensiveReadiness
{
    uint32 SpellId = 0;
    bool Known = false;
    bool Ready = false;
    bool Active = false;
};

using DefensiveStates = std::array<DefensiveReadiness, DefensivePriority.size()>;

// Icebound Fortitude covers this Mangle when it is running or about to be
// cast (known and off cooldown).  Otherwise Vampiric Blood takes its place.
inline bool IceboundCovers(DefensiveStates const& states)
{
    for (DefensiveReadiness const& state : states)
        if (state.SpellId == IceboundFortitudeSpell)
            return state.Active || (state.Known && state.Ready);
    return false;
}

// The strongest listed defensive inside its lead that the bot knows, whose
// native cooldown is ready and whose aura does not already cover the hit.
// Vampiric Blood only while Icebound Fortitude cannot cover this Mangle.
inline std::optional<uint32> SelectDefensive(DefensiveWindow const& window,
    DefensiveStates const& states)
{
    bool const iceboundCovers = IceboundCovers(states);
    for (uint32 spellId : DefensivePriority)
    {
        if (!WithinLead(window, spellId)
            || (spellId == VampiricBloodSpell && iceboundCovers))
            continue;
        for (DefensiveReadiness const& state : states)
            if (state.SpellId == spellId && state.Known && state.Ready
                && !state.Active)
                return spellId;
    }
    return std::nullopt;
}

// Magmaw's native Mangle timer as the cooldown plan needs it: running on the
// engaged boss, and whether this Mangle is already in progress (the Mangle ->
// Massive Crash sequence, an overdue Mangle published as 0, or this tank
// already seized).  Unlike the defensive window it is open for the whole
// fight, not only inside the lead, and for the tank whether or not it holds
// Magmaw's attention right now.
struct MangleTimer
{
    uint32 DueInMs = 0;
    bool HitInProgress = false;
};

inline std::optional<MangleTimer> ObserveMangleTimer(Blackboard const& board,
    ObjectGuid tankGuid)
{
    if (tankGuid.IsEmpty() || board.Route.NodeId != EncounterNode
        || board.NativeBossState != "in_progress")
        return std::nullopt;
    ActorSnapshot const* boss = MagmawBloodlust::FindBoss(board);
    if (!boss || !boss->InCombat)
        return std::nullopt;
    MechanicTimerSnapshot const* mangle =
        boss->FindMechanicTimer(MassiveCrashSpell);
    if (!mangle || mangle->Source != FactSource::NativeInstanceState)
        return std::nullopt;
    MangleTimer timer;
    timer.DueInMs = mangle->SequenceActive ? 0 : MangleDueInMs(mangle->RemainingMs);
    timer.HitInProgress = !timer.DueInMs;
    for (ActorSnapshot const& member : board.Players)
        if (member.Guid == tankGuid && HasMangleAura(member))
            timer.HitInProgress = true;
    return timer;
}
}

#endif

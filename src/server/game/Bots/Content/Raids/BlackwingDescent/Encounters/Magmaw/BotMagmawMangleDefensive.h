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
constexpr uint32 BoneShieldSpell = 49222;

// Strongest first.  Icebound Fortitude cuts all damage taken by 20% (35%
// with Sanguine Fortitude) for 12 s, off the global cooldown.  Bone Shield
// cuts damage by 20% for its charges (one per hit, 2 s apart), on the GCD.
// Vampiric Blood is deliberately absent: the profile already casts it at 70%
// health, and its 15% health is taken back when it expires, so casting it
// before Mangle moves that loss into the middle of the Mangle ticks.
constexpr std::array<uint32, 2> DefensivePriority = {
    IceboundFortitudeSpell, BoneShieldSpell,
};

// Native Magmaw publishes the time until the next Mangle under the Massive
// Crash spell id.  Mangle's weapon hit lands when the event fires and its
// first periodic tick 2 s later.  Icebound Fortitude cast 1.5 s ahead covers
// the hit and the first five ticks.  Bone Shield lasts 5 min, so it gets a
// longer lead to find a free global cooldown and rune.  The encounter
// blackboard refreshes every 100 ms, well inside both leads.
constexpr uint32 PreMangleIceboundLeadMs = 1500;
constexpr uint32 PreMangleBoneShieldLeadMs = 6000;

inline uint32 PreMangleLeadMs(uint32 spellId)
{
    return spellId == IceboundFortitudeSpell
        ? PreMangleIceboundLeadMs : PreMangleBoneShieldLeadMs;
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

struct DefensiveReadiness
{
    uint32 SpellId = 0;
    bool Known = false;
    bool Ready = false;
    bool Active = false;
};

// The strongest listed defensive inside its lead that the bot knows, whose
// native cooldown is ready and whose aura is not already running.
inline std::optional<uint32> SelectDefensive(DefensiveWindow const& window,
    std::array<DefensiveReadiness, DefensivePriority.size()> const& states)
{
    for (uint32 spellId : DefensivePriority)
    {
        if (!WithinLead(window, spellId))
            continue;
        for (DefensiveReadiness const& state : states)
            if (state.SpellId == spellId && state.Known && state.Ready
                && !state.Active)
                return spellId;
    }
    return std::nullopt;
}
}

#endif

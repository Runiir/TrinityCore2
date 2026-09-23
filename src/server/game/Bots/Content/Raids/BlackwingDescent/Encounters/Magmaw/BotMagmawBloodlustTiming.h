#ifndef TRINITY_BOT_MAGMAW_BLOODLUST_TIMING_H
#define TRINITY_BOT_MAGMAW_BLOODLUST_TIMING_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawBloodlust.h"

#include <optional>
#include <string_view>

namespace BotEncounter::MagmawBloodlust
{
// Native Magmaw publishes the time until its next Mangle -> Massive Crash
// sequence under the Massive Crash spell id, and 0 while that sequence runs
// (boss_magmaw.cpp GetTimeUntilEncounterMechanic).
constexpr uint32 MassiveCrashSpell = 88253;

// boss_magmaw.cpp JustEngagedWith schedules the first Mangle 90 s after pull.
constexpr uint32 NativeFirstMangleAfterPullMs = 90000;

// The first exposed head alone was too late: in the base-0891a99 kills the
// head opened 106.9-108.9 s after pull and Magmaw died 1.6-5.6 s after the
// lust landed.  The matched WCL reference (Y8ajQ7dbmKMG1RZy fight 22, 10N,
// 111.3 s) used its single lust, Time Warp, at 78.169 s.  Anchoring that lead
// to the native Mangle timer lets the 40 s aura cover the late ramp, Mangle,
// Massive Crash and the first exposed head, as the reference raid did.
constexpr uint32 WclReferenceLustAfterPullMs = 78169;
constexpr uint32 PreMangleLustLeadMs =
    NativeFirstMangleAfterPullMs - WclReferenceLustAfterPullMs;
static_assert(PreMangleLustLeadMs == 11831,
    "WCL lust lead before the first native Mangle");

constexpr std::string_view WclTimingEvidence =
    "wcl_Y8ajQ7dbmKMG1RZy_fight22_time_warp_78169ms_native_mangle_90000ms";

enum class LustTrigger : uint8
{
    PreMangleLead,
    FirstExposedHead
};

struct LustWindow
{
    ObjectGuid BossGuid;
    ObjectGuid TargetGuid;
    LustTrigger Trigger = LustTrigger::PreMangleLead;
};

inline char const* LustTriggerName(LustTrigger trigger)
{
    return trigger == LustTrigger::FirstExposedHead
        ? "first_exposed_head" : "pre_mangle_lead";
}

// Only the engaged boss with a native Mangle timer can open this window.  The
// timer is absent before pull and after a reset, and trash nodes never carry
// the encounter node, so this can never spend the raid lust on trash.
inline std::optional<LustWindow> ObservePreMangleLustWindow(
    Blackboard const& board)
{
    if (board.Route.NodeId != EncounterNode
        || board.NativeBossState != "in_progress")
        return std::nullopt;

    ActorSnapshot const* boss = FindBoss(board);
    if (!boss || !boss->InCombat)
        return std::nullopt;

    MechanicTimerSnapshot const* mangle =
        boss->FindMechanicTimer(MassiveCrashSpell);
    if (!mangle || mangle->Source != FactSource::NativeInstanceState)
        return std::nullopt;
    if (!mangle->SequenceActive && mangle->RemainingMs > PreMangleLustLeadMs)
        return std::nullopt;
    return LustWindow{ boss->Guid, boss->Guid, LustTrigger::PreMangleLead };
}

// A visible, still-latched first exposed head keeps the original trigger.
// Otherwise the WCL-timed pre-Mangle lead applies.  The caller latches one
// native cast per attempt, so both windows share one lust.
inline std::optional<LustWindow> SelectLustWindow(Blackboard const& board,
    std::optional<HeadWindow> const& headWindow)
{
    if (headWindow)
        return LustWindow{ headWindow->BossGuid, headWindow->HeadGuid,
            LustTrigger::FirstExposedHead };
    return ObservePreMangleLustWindow(board);
}
}

#endif

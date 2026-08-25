#ifndef TRINITY_BOT_RAID_DRUDGE_RECOVERY_TELEMETRY_H
#define TRINITY_BOT_RAID_DRUDGE_RECOVERY_TELEMETRY_H

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotRaidDrudgeGeometryState.h"

#include <cstddef>
#include <cstdint>
#include <string>
#include <utility>
#include <vector>

namespace BotRaidDrudgeSpacing
{
// These samples are diagnostic-only. They retain the exact scoped state
// needed to explain an unresolved landed Rush without changing movement,
// threat, or closure decisions.
struct RecoveryMemberDiagnostic
{
    std::uint32_t Guid = 0;
    std::uint32_t RosterSlot = 0;
    bool IsTank = false;
    bool InWorld = false;
    bool Alive = false;
    bool SameMap = false;
    bool ActiveLease = false;
    bool FrozenLaneSafe = false;
    bool GroupPositionSafe = false;
    bool ExactRosterMemberReseparated = false;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    float SourceDistance = 0.0f;
    bool AnchorValid = false;
    bool AnchorPathProven = false;
    bool RecoveryAnchorPathProven = false;
    bool RecoveryAnchorReached = false;
    bool CombatAnchorPathProven = false;
    bool CombatAnchorArrivalObserved = false;
    bool ActivePathValid = false;
    bool ActivePathScopeMatches = false;
    bool ActivePathArrivalObserved = false;
    std::uint32_t AnchorCandidateIndex = 0;
    float AnchorX = 0.0f;
    float AnchorY = 0.0f;
    float AnchorZ = 0.0f;
    float RecoveryAnchorX = 0.0f;
    float RecoveryAnchorY = 0.0f;
    float RecoveryAnchorZ = 0.0f;
    float ActivePathDestinationX = 0.0f;
    float ActivePathDestinationY = 0.0f;
    float ActivePathDestinationZ = 0.0f;
};

struct RecoveryTick
{
    BotRaidDrudgeGeometry::Scope Scope;
    std::uint64_t Sequence = 0;
    std::uint64_t ObservedAtMs = 0;
    bool LandedRushPending = false;
    bool RecoveryFormationActive = false;
    bool RecoveryBarrierOpen = false;
    bool Source0Alive = false;
    bool Source1Alive = false;
    float Source0X = 0.0f;
    float Source0Y = 0.0f;
    float Source0Z = 0.0f;
    float Source1X = 0.0f;
    float Source1Y = 0.0f;
    float Source1Z = 0.0f;
    std::uint32_t Source0Guid = 0;
    std::uint32_t Source1Guid = 0;
    std::uint32_t Source0VictimGuid = 0;
    std::uint32_t Source1VictimGuid = 0;
    bool AllRecoveryAnchorsReached = false;
    bool AllRecoveryTankPathsProven = false;
    bool AllCombatTankPathsProven = false;
    bool AllCombatTankAnchorsReached = false;
    bool ExactRosterReseparated = false;
    bool LandedRushRecoveryComplete = false;
    std::vector<RecoveryMemberDiagnostic> Members;
};

struct NativeTransition
{
    BotRaidDrudgeGeometry::Scope Scope;
    std::uint64_t ObservedAtMs = 0;
    std::uint32_t BotGuid = 0;
    std::uint32_t SourceGuid = 0;
    std::uint32_t SourceSpawnId = 0;
    std::uint32_t PreviousVictimGuid = 0;
    std::uint32_t CurrentVictimGuid = 0;
    std::uint32_t AssignedTankGuid = 0;
    std::uint32_t ActionValue = 0;
    bool VictimChanged = false;
    bool NativeVictimOwned = false;
    bool TauntAttempted = false;
    bool TauntSubmitted = false;
    bool TauntOutcomeObserved = false;
    std::string Result = "none";
    std::uint32_t SuppressedCount = 0;
};

constexpr std::size_t MaximumRecoveryMembers = 10;
constexpr std::size_t MaximumRecoveryTicks = 64;
constexpr std::size_t MaximumNativeTransitions = 64;
constexpr std::uint64_t RecoveryTickIntervalMs = 1000;

inline void ObserveRecoveryTick(
    std::vector<RecoveryTick>& ticks,
    BotRaidDrudgeGeometry::Scope const& scope,
    RecoveryTick tick)
{
    tick.Scope = scope;
    if (!ticks.empty() && ticks.front().Scope != scope)
        ticks.clear();
    if (!ticks.empty() && ticks.back().Scope == scope
        && tick.ObservedAtMs <= ticks.back().ObservedAtMs + RecoveryTickIntervalMs)
    {
        ticks.back() = std::move(tick);
        return;
    }
    if (ticks.size() >= MaximumRecoveryTicks)
        ticks.erase(ticks.begin());
    ticks.push_back(std::move(tick));
}

inline void ObserveNativeTransition(
    std::vector<NativeTransition>& transitions,
    BotRaidDrudgeGeometry::Scope const& scope,
    NativeTransition transition)
{
    transition.Scope = scope;
    if (!transitions.empty() && transitions.front().Scope != scope)
        transitions.clear();
    for (NativeTransition& previous : transitions)
        if (previous.Scope == scope
            && previous.BotGuid == transition.BotGuid
            && previous.SourceGuid == transition.SourceGuid
            && previous.Result == transition.Result
            && previous.CurrentVictimGuid == transition.CurrentVictimGuid)
        {
            ++previous.SuppressedCount;
            return;
        }
    if (transitions.size() >= MaximumNativeTransitions)
        transitions.erase(transitions.begin());
    transitions.push_back(std::move(transition));
}
}

#endif

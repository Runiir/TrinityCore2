#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_ENTRANCE_MOVEMENT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_ENTRANCE_MOVEMENT_H

#include <cstdint>
#include <string_view>

namespace BotRaidDrudgeEntranceMovement
{
// This is the small, typed boundary between the entrance policy and the
// movement service.  Native MotionMaster execution remains in the shared
// movement service; this type only describes what the policy observed.
enum class Outcome : std::uint8_t
{
    Arrived,
    ActivePathRetained,
    Submitted,
    HigherPriorityPending,
    Rejected,
    NoProgress,
};

enum class LogicalDestination : std::uint8_t
{
    Canonical,
    Recovery,
    Unavailable,
};

struct DestinationObservation
{
    bool Tank = false;
    bool CanonicalSafe = false;
    bool RecoveryAvailable = false;
    bool RecoverySafe = false;
    bool MatchingRecoveryPathActive = false;
    bool RecoveryArrived = false;
};

// A submitted recovery path remains the logical destination through arrival.
// Once there, an unsafe canonical anchor keeps the member at recovery. Missing
// or newly unsafe recovery geometry fails closed instead of falling back to
// the same unsafe point.
constexpr LogicalDestination SelectLogicalDestination(
    DestinationObservation const& observation)
{
    if (observation.Tank)
        return LogicalDestination::Canonical;

    bool const usableRecovery = observation.RecoveryAvailable
        && observation.RecoverySafe;
    if (observation.MatchingRecoveryPathActive && usableRecovery
        && !observation.RecoveryArrived)
        return LogicalDestination::Recovery;
    if (observation.CanonicalSafe)
        return LogicalDestination::Canonical;
    return usableRecovery ? LogicalDestination::Recovery
                          : LogicalDestination::Unavailable;
}

struct Observation
{
    bool Arrived = false;
    bool ActivePathRetained = false;
    bool NativeMovementSubmitted = false;
    bool HigherPriorityMovementActive = false;
    bool MeaningfulDistance = false;
    bool NoProgress = false;
};

constexpr bool HasMeaningfulDistance(float distance, float epsilon = 0.5f)
{
    return distance > epsilon;
}

// Classify arbitration and native evidence in a stable order.  In
// particular, an already-active higher-priority path is not a rejection, and
// a same-anchor request is never a submitted movement operation.
constexpr Outcome Classify(Observation const& observation)
{
    if (observation.Arrived)
        return Outcome::Arrived;
    if (observation.HigherPriorityMovementActive)
        return Outcome::HigherPriorityPending;
    if (!observation.MeaningfulDistance || observation.NoProgress)
        return Outcome::NoProgress;
    if (observation.ActivePathRetained)
        return Outcome::ActivePathRetained;
    if (observation.NativeMovementSubmitted)
        return Outcome::Submitted;
    return Outcome::Rejected;
}

// This is the policy-side admission check.  The shared movement executor
// still owns active-path reconciliation and the set-and-forget native
// generator; callers must not submit a point request for a same-anchor tick.
constexpr bool ShouldSubmitNativeMovement(bool arrived,
    bool activePathRetained, float distance, float epsilon = 0.5f)
{
    return !arrived && !activePathRetained
        && HasMeaningfulDistance(distance, epsilon);
}

// Both directions of the temporary combat-time backline transition must
// preserve source-union clearance. Pre-pull staging and tank movement retain
// their existing native path contract.
constexpr bool RequiresSourceUnionPath(bool tank, bool recoveryDestination,
    std::string_view moveResult)
{
    return !tank && (recoveryDestination
        || moveResult == "drudge_entrance_return_move");
}

// These waits are position contracts, not failed movement attempts. During
// exact pre-pull staging the member is already at its declared anchor and must
// retain the route movement lane while another roster member catches up.
// Keep the classifier exact so ordinary combat/formation waits remain eligible
// for their normal movement arbitration.
constexpr bool IsExactDrudgePositionHold(std::string_view action)
{
    return action == "drudge_entrance_exact_roster_stage_wait"
        || action == "drudge_entrance_pull_owner_wait";
}

// A pack-linked pull may keep its ordinary combat lane while native movement
// is already doing the work. No-progress is eligible only at a safe logical
// destination; reaching a canonical point that became unsafe is not arrival.
// A rejected native path remains fail-closed.
constexpr bool ContinuePackCombat(Outcome outcome, bool packLinked,
    bool safeLogicalDestinationReached = false)
{
    if (!packLinked)
        return false;

    if (outcome == Outcome::NoProgress)
        return safeLogicalDestinationReached;

    return outcome == Outcome::Arrived
        || outcome == Outcome::ActivePathRetained
        || outcome == Outcome::Submitted
        || outcome == Outcome::HigherPriorityPending;
}

constexpr char const* Name(Outcome outcome)
{
    switch (outcome)
    {
        case Outcome::Arrived: return "arrived";
        case Outcome::ActivePathRetained: return "active_path_retained";
        case Outcome::Submitted: return "submitted";
        case Outcome::HigherPriorityPending:
            return "higher_priority_movement_active";
        case Outcome::Rejected: return "rejected";
        case Outcome::NoProgress: return "no_progress";
    }
    return "rejected";
}

constexpr char const* TraceResult(Outcome outcome, char const* moveResult,
    char const* waitResult)
{
    switch (outcome)
    {
        case Outcome::Arrived: return waitResult;
        case Outcome::ActivePathRetained:
            return "drudge_entrance_native_path_retained";
        case Outcome::Submitted: return moveResult;
        case Outcome::HigherPriorityPending: return Name(outcome);
        case Outcome::Rejected:
            return "drudge_entrance_native_path_rejected";
        case Outcome::NoProgress:
            return "drudge_entrance_native_path_no_progress";
    }
    return "drudge_entrance_native_path_rejected";
}
}

#endif

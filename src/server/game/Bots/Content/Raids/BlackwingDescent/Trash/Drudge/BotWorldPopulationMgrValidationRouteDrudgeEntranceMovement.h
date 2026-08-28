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
// is already doing the work. A same-anchor no-progress observation can still
// continue combat when the bot is physically at its declared anchor; the
// tactical arrival predicate may be false only because a Drudge entered the
// safety radius. A rejected native path remains fail-closed.
constexpr bool ContinuePackCombat(Outcome outcome, bool packLinked,
    bool physicallyAtAnchor = false)
{
    if (!packLinked)
        return false;

    if (outcome == Outcome::NoProgress)
        return physicallyAtAnchor;

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

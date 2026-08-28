#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_H

#include "Bots/BotMovementArbiter.h"

#include <optional>
#include <string>

class Unit;

// The movement service receives an already-selected intent.  It does not
// inspect the combat rotation, quest policy, or encounter policy that chose
// the intent.  Compatibility callers may still fill the two path-policy
// switches below; the executor only treats them as mechanical path-admission
// requirements.
namespace BotWorldMovement
{
// Hazard movement models a player's decision to abandon a hard cast for an
// imminent lethal mechanic. Other movement owners remain compatible with an
// already-running cast and must not cancel it implicitly.
constexpr bool InterruptsActiveCast(
    BotMovementArbitration::Owner owner,
    BotMovementArbitration::Priority priority)
{
    return owner == BotMovementArbitration::Owner::Hazard
        && priority == BotMovementArbitration::Priority::Hazard;
}

constexpr bool AllowsProgressiveSegments(
    BotMovementArbitration::Owner owner, bool nativeRecoveryEntrance)
{
    return owner == BotMovementArbitration::Owner::Route
        || (owner == BotMovementArbitration::Owner::Recovery
            && nativeRecoveryEntrance);
}

// A corpse-authorized recovery entrance may rely on the same native long
// path that a player submits with MovePoint(generatePath=true).  Keep this
// admission separate from ordinary progressive route segments so no combat,
// formation, or support movement can bypass path planning.
constexpr bool AllowsNativeLongPath(
    BotMovementArbitration::Owner owner, bool nativeRecoveryEntranceRequired)
{
    return owner == BotMovementArbitration::Owner::Recovery
        && nativeRecoveryEntranceRequired;
}

// Only a corpse-authorized recovery entrance may use an aerial spline.  Keep
// this as an intent/state gate so ordinary corpse runs and every other owner
// continue through the existing ground movement executor.
constexpr bool UsesNativeRecoveryGhostFlight(
    BotMovementArbitration::Owner owner, bool allowNativeLongPath,
    bool ghostFlightEnabled)
{
    return owner == BotMovementArbitration::Owner::Recovery
        && allowNativeLongPath && ghostFlightEnabled;
}

// While a corpse-authorized recovery is crossing maps, only the recovery
// owner may submit movement.  A route or combat callback can still run during
// the worldport transition, but its stale instance destination must not be
// handed to the ordinary floor/Z planner on the source map.
constexpr bool BlocksNonRecoveryCrossMapMovement(
    BotMovementArbitration::Owner owner, bool recoveryCrossMapPending)
{
    return recoveryCrossMapPending
        && owner != BotMovementArbitration::Owner::Recovery;
}

// The future-pack mask belongs to ordinary movement admission, not to the
// route, formation, combat, or hazard caller that happened to produce an
// intent.  Native recovery movement is the only exception: it must be
// allowed to return through the declared entrance corridor.
constexpr bool AppliesValidationRoutePatrolFutureDestinationGuard(
    BotMovementArbitration::Owner owner)
{
    return owner != BotMovementArbitration::Owner::Recovery;
}

struct Intent
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    // Only a caller with a completed mechanical path proof may provide this
    // floor.  An absent value keeps the ordinary strict floor contract.
    std::optional<float> ReferenceFloorZ;
    bool TerminalOnFailure = false;
    BotMovementArbitration::Owner Owner = BotMovementArbitration::Owner::None;
    BotMovementArbitration::Priority Priority = BotMovementArbitration::Priority::Idle;
    Unit* DynamicTarget = nullptr;
    float DynamicTargetRange = 0.0f;

    // These flags are part of the movement contract, not a policy lookup.
    // A caller that requires a complete native corridor sets
    // RequireCompletePath.  A caller that allows deterministic progress
    // segments sets AllowProgressiveSegments.
    bool AllowProgressiveSegments = false;
    bool RequireCompletePath = false;
    bool AllowRecentFailureRetry = false;
    bool AllowNativeLongPath = false;
    bool NativeRecoveryCrossMapPending = false;
    std::string IntentReason;
};

struct PathPlan
{
    bool Selected = false;
    bool DynamicTarget = false;
    float SegmentX = 0.0f;
    float SegmentY = 0.0f;
    float SegmentZ = 0.0f;
    std::string TraversalMode;
    std::string RejectReason;
    bool RecentFailure = false;
    bool NativeLongPath = false;
};

struct ActivePathObservation
{
    bool ScopeMatches = false;
    bool NativePointPathActive = false;
    bool NativeTargetChaseActive = false;
    bool MatchingDestination = false;
};
}

#endif

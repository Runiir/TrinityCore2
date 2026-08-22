#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_H

#include "Bots/BotMovementArbiter.h"

#include <string>

class Unit;

// The movement service receives an already-selected intent.  It does not
// inspect the combat rotation, quest policy, or encounter policy that chose
// the intent.  Compatibility callers may still fill the two path-policy
// switches below; the executor only treats them as mechanical path-admission
// requirements.
namespace BotWorldMovement
{
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
    BotMovementArbitration::Owner owner, bool nativeRecoveryEntranceReady)
{
    return owner == BotMovementArbitration::Owner::Recovery
        && nativeRecoveryEntranceReady;
}

struct Intent
{
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
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

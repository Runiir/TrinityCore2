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

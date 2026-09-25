#ifndef TRINITY_BOT_NEFARIAN_SURFACE_INTENT_H
#define TRINITY_BOT_NEFARIAN_SURFACE_INTENT_H

// Turns a Nefarian SurfaceGoal into package T's transport-surface intent.
// No static navmesh covers GO 207834, so ordinary Move intents are rejected
// on the platform for the whole fight; every platform destination is a
// BotNativeAction::TransportSurfaceMove executed by
// BotTransportSurfaceMovement::Execute.

#include "Bots/BotNativeActionIntent.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianMovement.h"

namespace BotEncounter::Nefarian
{
constexpr float SurfaceWalkFloorToleranceYards = 0.6f;

// One straight Walk that ends on the transport. The executor proves floor,
// collision and a stationary platform before its single native side effect
// and otherwise returns a typed Retryable/Unsafe reason; it never relocates
// the bot. It cannot climb or swim, so a pillar-top goal is only reachable
// from a raised part of the same transport.
inline BotNativeAction::TransportSurfaceMove ToTransportSurfaceMove(
    SurfaceGoal const& goal)
{
    BotNativeAction::TransportSurfaceMove move;
    move.Transport = goal.Transport;
    move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Walk;
    move.X = goal.World.X;
    move.Y = goal.World.Y;
    move.Z = goal.World.Z;
    move.EndOnTransport = true;
    move.FloorToleranceYards = SurfaceWalkFloorToleranceYards;
    return move;
}

// Platform goals use the transport-surface walk; an unobserved transport
// (no GUID) falls back to the ordinary move.
inline BotNativeAction::Intent PlatformMovementIntent(SurfaceGoal const& goal)
{
    if (!goal.Transport.IsEmpty())
        return ToTransportSurfaceMove(goal);
    return BotNativeAction::Move(goal.World.X, goal.World.Y, goal.World.Z,
        MovePurposeName(goal.Purpose), goal.Urgent);
}
}

#endif

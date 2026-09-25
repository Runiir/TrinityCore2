#ifndef TRINITY_BOT_NEFARIAN_SURFACE_INTENT_H
#define TRINITY_BOT_NEFARIAN_SURFACE_INTENT_H

// Turns one planned leg into package T's transport-surface walk. No static
// navmesh covers GO 207834, so ordinary Move intents are rejected on the
// platform for the whole fight; every platform leg is a
// BotNativeAction::TransportSurfaceMove Walk executed by
// BotTransportSurfaceMovement::Execute, which proves floor, collision and a
// stationary platform before its single native side effect, accepts at most
// MaxSurfaceWalkYards (12) and replaces a walk still in flight.

#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotEncounterBlackboard.h"

namespace BotEncounter::Nefarian
{
inline BotNativeAction::TransportSurfaceMove ToTransportSurfaceMove(
    ObjectGuid transport, Vector3 const& world, float floorToleranceYards)
{
    BotNativeAction::TransportSurfaceMove move;
    move.Transport = transport;
    move.Kind = BotNativeAction::TransportSurfaceMove::Stage::Walk;
    move.X = world.X;
    move.Y = world.Y;
    move.Z = world.Z;
    move.EndOnTransport = true;
    move.FloorToleranceYards = floorToleranceYards;
    return move;
}
}

#endif

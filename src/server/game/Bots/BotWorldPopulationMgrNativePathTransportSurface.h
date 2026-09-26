#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_TRANSPORT_SURFACE_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_TRANSPORT_SURFACE_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotNativeActionIntent.h"

class Player;

// Lawful movement where the static navmesh does not reach: across a
// GAMEOBJECT_TYPE_TRANSPORT platform's own surface, and off a ledge onto it
// (BotNativeAction::TransportSurfaceMove). Every stage re-proves its
// preconditions against the live map before its single native side effect:
//
// Walk     one straight point spline (MotionMaster::MovePoint with
//          generatePath=false) at the bot's own speed, only when every sample
//          of the segment has a floor (static vmap or the platform's own
//          collision model) within tolerance of the segment height, static and
//          dynamic line of sight is clear at knee, waist and head height, and
//          the platform stays put for the whole walk. A passenger's spline is
//          native passenger movement (transport-local coordinates).
// StepOff  the same proven straight walk from a ledge lip to a point over the
//          void whose landing floor (exactly MoveFall's Map::GetHeight query)
//          is the declared one and whose native fall damage leaves the declared
//          health margin; first a standing client report at the lip sets
//          Player::m_lastFallZ like any client movement packet.
// Fall     MotionMaster::MoveFall: native gravity onto that floor.
// Land     the client's MSG_MOVE_FALL_LAND report at the landed position:
//          Player::HandleFall applies native fall damage.
//
// Nothing here relocates a unit, sets its height, attaches it to a transport
// or skips a stage; boarding stays BotValidationRouteBoardingAction's.
//
// Encounter seam (for example the Nefarian platform, which no static navmesh
// covers and whose pillars are part of the transport): submit a
// TransportSurfaceMove Walk (EndOnTransport) to a point on the platform, or
// StepOff, then Fall, then Land (the route runtime's sequence) to drop from a
// pillar top onto its floor. A passenger of the same transport stays one:
// its splines are transport-local and its reports carry its transport block.
// Each stage either launches its single native motion or returns a typed
// Retryable/Unsafe reason and moves nothing. It cannot climb; the swimmer's
// stages (Float, Swim, Hop, Emerge) are BotTransportLiquidMovement's
// (BotWorldPopulationMgrNativePathTransportLiquid.h).
namespace BotTransportSurfaceMovement
{
BotActionArbitration::Outcome Execute(Player* bot,
    BotNativeAction::TransportSurfaceMove const& action);

// Player::HandleFall's damage fraction for falling `height` yards now (safe
// fall, feather fall, hover, flight and immunity as the core applies them).
float PredictFallDamagePct(Player const* bot, float height);

// Some floor (static or any collision model) within `band` yards above or
// below the bot's feet.
bool FloorNear(Player const* bot, float band);
}

#endif

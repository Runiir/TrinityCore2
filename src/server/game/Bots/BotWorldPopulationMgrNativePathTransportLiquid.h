#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_TRANSPORT_LIQUID_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_TRANSPORT_LIQUID_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotNativeActionIntent.h"

class Player;

// The swimmer's stages of BotNativeAction::TransportSurfaceMove, for a
// platform that sinks into liquid (Nefarian's End phase 2: GO 207834 lowers
// its floor 10 yards under the magma while its pillar tops stay 0.29 yards
// above it). Each stage re-proves its preconditions against the live map
// (the core's own liquid query, Map::GetLiquidStatus) before its single
// native side effect:
//
// Float   a passenger whose feet are FloatDepthYards under the surface stops
//         standing on the platform: the client's MSG_MOVE_START_SWIM report
//         at its current position without a transport block (the movement
//         handler removes the passenger, as for any client that swims off).
// Swim    one straight point spline to X/Y/Z, start, samples and end inside
//         the liquid, at most MaxSwimYards, body sweep clear of static and
//         dynamic geometry (the sinking platform included). A player's spline
//         carries MoveSplineFlag::CanSwim (Unit::CanSwim).
// Hop     the client's jump from the liquid onto X/Y/Z on the platform's own
//         surface, the platform held at a stop for the whole jump and the
//         boarding after it: MotionMaster::MoveJumpWithGravity at the
//         client's jump launch speed (7.95577 yd/s up) and the core's
//         gravity, horizontal speed at most the run speed, the arc swept
//         clear of the platform's model and static geometry.
// Emerge  a swimmer that stands on the platform's surface (after its hop,
//         or when a rising floor reaches its feet) reports standing on it:
//         MSG_MOVE_STOP_SWIM with the platform's transport block.
//
// Nothing here relocates a unit or sets its height; a swim or a jump is a
// spline the member moves along at native speed.
namespace BotTransportLiquidMovement
{
BotActionArbitration::Outcome Execute(Player* bot,
    BotNativeAction::TransportSurfaceMove const& action);
}

#endif

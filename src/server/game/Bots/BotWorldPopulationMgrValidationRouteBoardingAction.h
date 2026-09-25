#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_BOARDING_ACTION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_BOARDING_ACTION_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotValidationRouteNativeLogic.h"

class GameObject;
class Player;

// Native executors and floor observations for boarding vehicles and
// transports. Every submission is the request a player's client sends
// (spellclick, seat switch, or a movement heartbeat at the bot's current
// position); the server's own bookkeeping decides the result. Nothing here
// relocates, seats or attaches a unit.
namespace BotValidationRouteBoardingAction
{
// Observed state of a GAMEOBJECT_TYPE_TRANSPORT platform.
BotValidationRouteNative::TransportFact ObserveTransport(GameObject const* transport);

// Static (map/vmap) ground within `tolerance` below/at the bot's feet.
bool StaticFloorUnderfoot(Player const* bot, float tolerance);

// This transport's own collision model surface within `tolerance` of the
// bot's feet (a downward ray through the model, not its bounding box).
// `modelAvailable` is false when the transport has no collision model.
bool TransportFloorUnderfoot(Player const* bot, GameObject const* transport,
    float tolerance, bool& modelAvailable);

// Remaining time the platform stays within `tolerance` of the world origin
// height `levelZ`: unbounded for script-held stop frames, computed from the
// TransportAnimation timeline for continuously cycling transports.
std::uint64_t RestRemainingAtLevelMs(GameObject const* transport, float levelZ,
    float tolerance);

// How long the platform keeps its current height (the same rule as above).
std::uint64_t TransportStationaryMs(GameObject const* transport);

// A MotionMaster::MoveFall spline that has not finalized yet.
bool NativeFallSplineActive(Player const* bot);
// Falling as the core tracks it: the client-owned falling movement flags or
// a running falling spline. A finalized fall spline keeps its falling
// attribute until the next spline replaces it; that alone is not a fall.
bool NativeFallInProgress(Player const* bot);
// The fall spline finalized but the landing has not been reported yet
// (MOVEMENTFLAG_FALLING still set, as MoveFall leaves it for the client).
bool NativeFallLandingPending(Player const* bot);

// Client movement reports at the bot's own current position through the
// player's movement handler (after claiming the active mover like a client);
// a passenger's report carries its current transport block, so neither
// report boards, leaves or changes a transport. A standing heartbeat updates
// Player's fall origin (m_lastFallZ) exactly as every client report does;
// the landing report (MSG_MOVE_FALL_LAND) makes Player::HandleFall apply
// native fall damage and clears the falling flags.
bool ReportStandingPosition(Player* bot);
bool ReportFallLanding(Player* bot, std::uint32_t fallTimeMs);

BotActionArbitration::Outcome EnterVehicle(Player* bot,
    BotNativeAction::VehicleEnter const& action);
BotActionArbitration::Outcome BoardTransport(Player* bot,
    BotNativeAction::TransportBoard const& action);
BotActionArbitration::Outcome LeaveTransport(Player* bot,
    BotNativeAction::TransportLeave const& action);
}

#endif

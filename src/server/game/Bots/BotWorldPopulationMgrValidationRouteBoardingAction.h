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

BotActionArbitration::Outcome EnterVehicle(Player* bot,
    BotNativeAction::VehicleEnter const& action);
BotActionArbitration::Outcome BoardTransport(Player* bot,
    BotNativeAction::TransportBoard const& action);
BotActionArbitration::Outcome LeaveTransport(Player* bot,
    BotNativeAction::TransportLeave const& action);
}

#endif

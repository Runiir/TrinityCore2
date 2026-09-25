#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_BOARDING_ACTION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_BOARDING_ACTION_H

#include "Bots/BotActionArbiter.h"
#include "Bots/BotNativeActionIntent.h"
#include "Bots/BotValidationRouteNativeLogic.h"

class GameObject;
class Player;

// Native executors for boarding vehicles and transports. Every path submits
// the same request a player's client sends (spellclick, seat switch, or a
// movement heartbeat at the bot's current position) and then observes the
// server's own result. Nothing here relocates, seats or attaches a unit.
namespace BotValidationRouteBoardingAction
{
// Model bounding box of a transport in its local frame (scaled).
bool DisplayFootprint(GameObject const* transport,
    BotValidationRouteNative::LocalBox& box);

// Observed state of a GAMEOBJECT_TYPE_TRANSPORT platform.
BotValidationRouteNative::TransportFact ObserveTransport(GameObject const* transport);

BotActionArbitration::Outcome EnterVehicle(Player* bot,
    BotNativeAction::VehicleEnter const& action);
BotActionArbitration::Outcome BoardTransport(Player* bot,
    BotNativeAction::TransportBoard const& action);
BotActionArbitration::Outcome LeaveTransport(Player* bot,
    BotNativeAction::TransportLeave const& action);
}

#endif

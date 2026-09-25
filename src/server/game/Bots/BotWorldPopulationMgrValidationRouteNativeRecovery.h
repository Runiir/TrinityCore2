#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_NATIVE_RECOVERY_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_NATIVE_RECOVERY_H

#include "Bots/BotWorldPopulationMgrValidationRouteNativeFacts.h"
#include "Bots/BotWorldPopulationMgrValidationRouteNativeRuntime.h"

#include <functional>
#include <string>

// Server adapter for recovery rides (row field recovery_transport; decisions
// in BotValidationRouteNativeRecovery.h). A node that lies across a ride
// between two levels runs that ride again, before its own contracts, when
// living members are back at the ride's boarding end after a wipe's runback.
// The ride is the node route runtime's own transport step (RecoveryOps), so
// boarding, riding and disembarking stay exactly the transport contract's.
namespace BotWorldPopulationMgrValidationRouteNative
{
struct RecoveryOps
{
    // One member's step of a transport contract with its own runtime state.
    std::function<void(Callbacks const&, BotValidationRouteNative::TransportContract const&,
        BotValidationRouteNative::NodeRuntime&, Facts::TransportTarget const&)> Ride;
    // Keep the member where it is, owning its movement.
    std::function<void(std::string const&)> Hold;
};

// True while a ride owns the node (or after one failed the attempt).
bool RunRecovery(Input const& input, Callbacks const& callbacks,
    BotValidationRouteNative::NodeContract& node, RecoveryOps const& ops);
}

#endif

#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_FERAL_TRASH_HANDOFF_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_FERAL_TRASH_HANDOFF_H

#include "Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"

#include <cstddef>
#include <functional>

namespace BotWorldPopulationMgrValidationRoute
{
using TrashThreatControlResult = TrashThreatControl;

// The ordinary-trash Feral lane observes the threat scan and tank-local
// defense selection through explicit typed callbacks.  It must not reach into
// TryValidationRouteObjective's local variables or acquire encounter-owned
// Azil state.
struct FeralTrashHandoffCallbacks
{
    std::function<Player*()> DefenseTarget;
    std::function<std::size_t()> DefenseAttackerCount;
    std::function<TrashThreatControl const&()> TrashThreatControlResult;
};
}

#endif

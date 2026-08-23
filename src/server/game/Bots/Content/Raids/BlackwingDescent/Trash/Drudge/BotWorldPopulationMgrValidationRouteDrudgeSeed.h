#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_SEED_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DRUDGE_SEED_H

#include "Bots/Content/Raids/BlackwingDescent/Trash/Drudge/BotWorldPopulationMgrValidationRouteDrudge.h"

namespace BotWorldPopulationMgrValidationRoute
{
// The lane-A tank is the deterministic owner of the route coordinator tick.
// The coordinator resolves and executes both configured opposite-lane seed
// actions before returning; every other lane only observes the resulting hold.
DrudgeLaneContext::PhaseResult RunDrudgeSeedCoordinator(DrudgeLaneContext& context);
}

#endif

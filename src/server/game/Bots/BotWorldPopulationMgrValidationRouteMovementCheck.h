#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_MOVEMENT_CHECK_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_MOVEMENT_CHECK_H

#include <functional>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// The route movement lane only observes the two neighboring policy services it
// needs. Keeping those edges typed prevents the movement lease from reaching
// into the objective's local lambda captures or the independent DPS/cast lane.
struct MovementCheckCallbacks
{
    std::function<bool(Creature const*)> IsCombatLinked;
    std::function<bool(Player*, Unit*, bool, bool)> TryGroupHeal;
};
}

#endif

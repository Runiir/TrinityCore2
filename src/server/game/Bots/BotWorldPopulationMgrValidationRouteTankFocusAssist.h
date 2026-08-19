#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TANK_FOCUS_ASSIST_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TANK_FOCUS_ASSIST_H

#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"

#include <functional>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// The shared tank-focus lane receives route/focus policy and action helpers
// through explicit callbacks.  ObjectiveContext still owns the mutable
// decision state and manager access; this contract only crosses the extraction
// boundary for the local resolvers that the lane already used.
struct TankFocusAssistCallbacks
{
    std::function<char const*(Player*)> GetDungeonRole;
    std::function<Unit*(Unit*)> RouteUsableCombatTarget;
    std::function<void(Unit*)> RememberValidationRouteFocus;
    std::function<ObjectGuid()> RouteTankFocusGuid;
    std::function<Unit*(ObjectGuid)> RouteTankFocusTarget;
    std::function<Unit*()> FindLastKnownFocusTarget;
    std::function<bool(Creature const*)> IsValidationRouteObjectiveTarget;
    std::function<bool()> RouteFocusMemoryActive;
    std::function<bool()> AuthoritativeRouteFocusActive;
    std::function<bool(char const*)> RecoverAuthoritativeFocus;
    std::function<Unit*(Unit*)> TeacherAssistAuthoritativeFocus;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<bool(Player*, Unit*, ResolvedCombatAction const&)>
        MoveOutOfProfileDeadZone;
    std::function<bool(Player*, Unit*, bool, bool)> TryRouteGroupHeal;
    std::function<bool(Unit*, char const*)> TryValidationRouteInterrupt;
    std::function<bool(Unit*, char const*)>
        MaybeValidationPrerequisiteNoProgressAssist;
};
}

#endif

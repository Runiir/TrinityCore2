#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_SHARED_FOCUS_ACTION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_SHARED_FOCUS_ACTION_H

#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"

#include <functional>
#include <string>

class Player;
class Creature;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// Shared route focus is resolved by the monolith's authoritative focus
// context, while this lane owns the deterministic action and movement policy
// once that focus has been selected.  Every local edge crossing the boundary
// is explicit so the action remains isolated from the objective dispatcher.
struct SharedFocusActionCallbacks
{
    std::function<Unit*()> RouteGroupFocusTarget;
    std::function<Unit*(Unit*)> TeacherAssistAuthoritativeFocus;
    std::function<bool()> AuthoritativeRouteFocusActive;
    std::function<std::string const&()> AuthoritativeFocusFailure;
    std::function<bool(Creature const*)> IsValidationRouteObjectiveTarget;
    std::function<char const*(Player*)> GetDungeonRole;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<bool(Player*, Unit*, ResolvedCombatAction const&)>
        MoveOutOfProfileDeadZone;
    std::function<bool(Player*, Unit*, bool, bool)> TryRouteGroupHeal;
    std::function<bool(Unit*, char const*)>
        MaybeValidationPrerequisiteNoProgressAssist;
};
}

#endif

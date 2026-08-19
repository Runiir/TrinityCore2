#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_ACTIVE_COMBAT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_ACTIVE_COMBAT_H

#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"

#include <functional>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// Active route combat owns the final regroup, target validation, mechanic
// fail-closed, threat, movement, and profile-action decisions after focus has
// been resolved.  The objective dispatcher supplies every local dependency
// explicitly so no route policy reaches back into its locals implicitly.
struct ActiveCombatCallbacks
{
    std::function<char const*(Player*)> GetDungeonRole;
    std::function<Player*(Player*)> FindDungeonAnchor;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<bool(Creature const*)> IsValidationCohortCombatLinked;
    std::function<void(Creature const*, bool)> EnrollValidationRoutePackMember;
    std::function<bool(Creature const*)> IsValidationRouteObjectiveTarget;
    std::function<bool(Creature const*)> IsEligibleTrashClusterMob;
    std::function<void(Unit*)> RememberValidationRouteFocus;
    std::function<bool()> HasValidationRouteActivation;
    std::function<bool()> ValidationRouteHasLivingTank;
    std::function<bool(Unit*)> RouteFocusTankOwned;
    std::function<bool(Player*, Unit*, ResolvedCombatAction const&)>
        MoveOutOfProfileDeadZone;
    std::function<bool(Player*, Unit*, bool, bool)> TryRouteGroupHeal;
    std::function<bool(Unit*, char const*)> TryValidationRouteInterrupt;
    std::function<bool(Unit*, char const*)>
        MaybeValidationPrerequisiteNoProgressAssist;
};
}

#endif

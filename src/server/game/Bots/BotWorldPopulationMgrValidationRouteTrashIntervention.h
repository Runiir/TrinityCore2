#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TRASH_INTERVENTION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TRASH_INTERVENTION_H

#include "Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"

#include <functional>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// Ordinary-trash intervention observes the threat scan and delegates through
// typed callbacks for the focus helpers owned by TryValidationRouteObjective.
struct TrashInterventionCallbacks
{
    std::function<bool()> IsProtectionProfile;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<bool(Creature const*)>
        IsImmediateNextValidationRouteEncounterMember;
    std::function<Unit*()> FindTrashClusterThreatTarget;
    std::function<Unit*()> FindLastKnownFocusTarget;
    std::function<Unit*(Unit*)> RouteUsableCombatTarget;
    std::function<void(Unit*)> RememberValidationRouteFocus;
};
}

#endif

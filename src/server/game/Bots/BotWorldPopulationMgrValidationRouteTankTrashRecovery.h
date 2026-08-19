#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TANK_TRASH_RECOVERY_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TANK_TRASH_RECOVERY_H

#include "Bots/BotWorldPopulationMgrValidationRouteTrashThreatControl.h"

#include <cstddef>
#include <functional>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// The tank recovery lane observes the already-computed threat result and
// focus helpers through typed callbacks. It owns no encounter state and does
// not duplicate the generic threat scan or Feral handoff.
struct TankTrashRecoveryCallbacks
{
    std::function<Player*()> DefenseTarget;
    std::function<std::size_t()> DefenseAttackerCount;
    std::function<TrashThreatControl&()> TrashThreatControlResult;
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

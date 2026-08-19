#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TRASH_THREAT_CONTROL_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TRASH_THREAT_CONTROL_H

#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"

#include <functional>
#include <vector>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
struct TrashThreatControl
{
    Player* Tank = nullptr;
    Player* HealerTarget = nullptr;
    Unit* AreaTarget = nullptr;
    std::vector<Unit*> HealerOwnedTargets;
    std::vector<Unit*> TankOwnedTargets;
    std::vector<Unit*> InsecureTankOwnedTargets;
    uint32 EngagedCount = 0;
    uint32 HealerTargetCount = 0;
    uint32 TankOwnedCount = 0;
    uint32 SecureTankCount = 0;
    bool InsecureTrashSwarm = false;
    bool TankOwnsTrashMajority = false;
};

struct TrashThreatControlCallbacks
{
    std::function<bool(Creature const*)>
        IsImmediateNextValidationRouteEncounterMember;
    std::function<bool(Creature const*)> IsPendingScriptedEventEntry;
    std::function<bool(Creature const*)> IsValidationRouteScriptTarget;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<bool(Player*, Unit*, ResolvedCombatAction const&)>
        MoveOutOfProfileDeadZone;
    std::function<bool()> TryValidationRouteAdds;
};
}

#endif

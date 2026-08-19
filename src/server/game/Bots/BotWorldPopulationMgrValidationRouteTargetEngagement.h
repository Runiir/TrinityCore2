#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TARGET_ENGAGEMENT_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TARGET_ENGAGEMENT_H

#include "Bots/BotTypes.h"
#include "Bots/BotWorldPopulationMgrValidationRouteTerminalArrival.h"

#include <functional>
#include <string>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
// The target-acquisition tail receives every local resolver explicitly.  This
// keeps the ObjectiveContext friend as the only path to manager-owned state
// while making target search, activation, recovery, and engagement one typed
// ownership boundary.
struct TargetEngagementCallbacks
{
    std::function<bool()> DiscoveryLeg;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::function<ObjectGuid::LowType()> CurrentValidationRouteTargetSpawnId;
    std::function<bool(Creature const*)> IsEligibleTrashClusterMob;
    std::function<void(Creature const*, bool)> EnrollValidationRoutePackMember;
    std::function<bool(Creature const*)> IsValidationCohortCombatLinked;
    std::function<bool(Creature const*)> IsCurrentDiscoveryScriptedEventTarget;
    std::function<Unit*()> FindTrashClusterThreatTarget;
    std::function<Unit*()> FindNearestTrashClusterMob;
    std::function<bool()> MoveToRouteAnchor;
    std::function<bool(Creature const*)> IsValidationRouteScriptTarget;
    std::function<bool(Creature const*)> IsValidationRouteCombatTarget;
    std::function<Unit*(Creature*)> MakeExistingValidationRouteCombatReady;
    std::function<bool(Creature const*)> IsValidationRouteObjectiveTarget;
    std::function<bool(std::string&, bool&)> TryCanonicalValidationRouteBossRecovery;
    std::function<void(ObjectGuid)> ClearValidationRouteKilledFocus;
    std::function<bool(Unit*, char const*)> RecordValidationRouteTrashKill;
    std::function<bool(Unit*, char const*)> TryValidationRouteActivation;
    std::function<Unit*()> RouteGroupFocusTarget;
    std::function<bool(Player*, Unit*, ResolvedCombatAction const&)>
        MoveOutOfProfileDeadZone;
    std::function<bool(Player*, Unit*, bool, bool)> TryRouteGroupHeal;
    std::function<bool(Unit*, char const*)> TryValidationRouteInterrupt;
    std::function<bool(Unit*, char const*)>
        MaybeValidationPrerequisiteNoProgressAssist;
    std::function<bool(char const*)> RecoverAuthoritativeFocus;
    std::function<void(Unit*)> RememberValidationRouteFocus;
    std::function<bool()> TrashClusterHasLiveMobs;
    std::function<bool(bool)> ValidationPartyHasActiveCombat;
    std::function<Unit*()> FindBoundedTerminalPartyCombatTarget;
    std::function<void(char const*)> MarkTrashClusterCleared;
};
}

#endif

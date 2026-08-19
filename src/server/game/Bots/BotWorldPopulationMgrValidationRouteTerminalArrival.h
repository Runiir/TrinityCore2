#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TERMINAL_ARRIVAL_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_TERMINAL_ARRIVAL_H

#include "Bots/BotWorldPopulationMgrValidationRouteContexts.h"
#include "Bots/BotWorldPopulationMgrRouteState.h"

#include <functional>
#include <string>

namespace BotWorldPopulationMgrValidationRoute
{
struct ObjectiveCallbacks
{
    std::function<bool()> PersistedPackHasLiveMembers;
    std::function<Unit*()> ActivePackTarget;
    std::function<bool(Creature const*)> IsEligibleTrash;
    std::function<bool()> PartyHasActiveCombat;
    std::function<bool(BotWorldPopulationMgrBotState::WorldBotState const&, Player const*)>
        IsOriginalInstanceMember;
    std::function<void()> EnrollEngagedPackMembers;
    std::function<bool()> MoveToRouteAnchor;
};

struct ObjectiveContext
{
    using WorldBotState = BotWorldPopulationMgrBotState::WorldBotState;
    using ValidationRouteManifestNode =
        BotWorldPopulationMgrRouteState::ValidationRouteManifestNode;

    BotWorldPopulationMgr& Manager;
    WorldBotState& State;
    Player* Bot;
    BotRolePowerBreakdown const& Power;
    BotProgressionStage Stage;
    BotProgressionActivity Activity;
    std::string& Situation;
    std::string& Action;
    Unit*& Target;
    bool ArrivalRoute;
    float RouteArrivalRadius;
    float const& CanonicalRouteDistance;
    float& RouteAnchorX;
    float& RouteAnchorY;
    float& RouteAnchorZ;
    std::string& RouteAnchorReason;
    float& RouteDistance;
    ObjectiveCallbacks Callbacks;

    ObjectiveContext(BotWorldPopulationMgr& manager, WorldBotState& state,
        Player* bot, BotRolePowerBreakdown const& power,
        BotProgressionStage stage, BotProgressionActivity activity,
        std::string& situation, std::string& action, Unit*& target,
        bool arrivalRoute, float routeArrivalRadius,
        float const& canonicalRouteDistance, float& routeAnchorX,
        float& routeAnchorY, float& routeAnchorZ,
        std::string& routeAnchorReason, float& routeDistance,
        ObjectiveCallbacks callbacks);

    bool Run();
};
}

#endif

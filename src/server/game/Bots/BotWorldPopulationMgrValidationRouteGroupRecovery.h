#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_GROUP_RECOVERY_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_GROUP_RECOVERY_H

#include "Bots/BotWorldPopulationMgrBotState.h"
#include "Bots/BotWorldPopulationMgrConfig.h"
#include "Bots/BotWorldPopulationMgrRouteState.h"

#include <functional>
#include <string>

class BotWorldPopulationMgr;
class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrValidationRoute
{
struct GroupRecoveryCallbacks
{
    std::function<void()> RetireStalePackMembers;
    std::function<void()> EnrollEngagedPackMembers;
    std::function<bool()> PersistedPackHasLiveMembers;
    std::function<void(Unit*, char const*, char const*, float, uint32, float, uint32, uint32)> MarkTrashFailed;
    std::function<bool(uint32)> IsPackEntry;
    std::function<uint32(Creature const*)> ResolvedTransitionAura;
};

struct GroupRecoveryRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    Unit** Target = nullptr;
    bool DiscoveryLeg = false;
    GroupRecoveryCallbacks Callbacks;
};

struct GroupRecoveryContext
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
    bool DiscoveryLeg;
    GroupRecoveryCallbacks Callbacks;

    GroupRecoveryContext(GroupRecoveryRequest const& request);
    bool Run();
};

bool TryValidationRouteGroupRecovery(GroupRecoveryRequest const& request);
}

#endif

#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_ORCHESTRATION_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_ORCHESTRATION_H

#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHealerAddWavePreposition.h"

#include <functional>
#include <string>

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct AddWaveOrchestrationRequest
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
    GroupHealCallback TryRouteGroupHeal;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    float CanonicalRouteDistance = 0.0f;
    float RouteArrivalRadius = 18.0f;
};

bool TryAddWaveOrchestration(AddWaveOrchestrationRequest const& request);
}

#endif

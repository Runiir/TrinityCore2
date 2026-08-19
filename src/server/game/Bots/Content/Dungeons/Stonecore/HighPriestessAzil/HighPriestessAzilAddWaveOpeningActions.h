#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_OPENING_ACTIONS_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_OPENING_ACTIONS_H

#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"

#include <string>

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct AddWaveOpeningActionsRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    AddWaveDiscoveryResult const* Discovery = nullptr;
    AddWaveDensityResult const* Density = nullptr;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    Unit** Target = nullptr;
};

bool TryAddWaveOpeningActions(
    AddWaveOpeningActionsRequest const& request);
}

#endif

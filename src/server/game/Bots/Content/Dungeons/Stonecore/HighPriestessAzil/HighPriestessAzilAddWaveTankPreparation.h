#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_TANK_PREPARATION_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_TANK_PREPARATION_H

#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct AddWaveTankPreparationRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    AddWaveDiscoveryResult const* Discovery = nullptr;
    AddWaveDensityResult const* Density = nullptr;
};

struct AddWaveTankPreparationResult
{
    Unit* Add = nullptr;
    bool SharedFocusValid = false;
};

AddWaveTankPreparationResult PrepareAddWaveTank(
    AddWaveTankPreparationRequest const& request);
}

#endif

#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_FERAL_LOCAL_RETENTION_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_FERAL_LOCAL_RETENTION_H

#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilFeralHandoffState.h"

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct FeralLocalRetentionRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    AddWaveDiscoveryResult const* Discovery = nullptr;
    AddWaveDensityResult const* Density = nullptr;
    FeralHandoffStateResult const* FeralHandoff = nullptr;
    Unit* Add = nullptr;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    Unit** Target = nullptr;
};

bool TryFeralLocalRetention(
    FeralLocalRetentionRequest const& request);
}

#endif

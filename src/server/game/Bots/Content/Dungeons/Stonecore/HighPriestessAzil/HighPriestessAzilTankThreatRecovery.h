#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_TANK_THREAT_RECOVERY_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_TANK_THREAT_RECOVERY_H

#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"

#include <functional>
#include <string>

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct TankThreatRecoveryRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    AddWaveDiscoveryResult const* Discovery = nullptr;
    AddWaveDensityResult const* Density = nullptr;
    Unit* Add = nullptr;
    std::function<bool(Unit*)> ContinueStableTankSwarmApproach;
    std::function<float(Player*, Unit const*, uint32)> RouteEngageRange;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    Unit** Target = nullptr;
};

bool TryTankThreatRecovery(
    TankThreatRecoveryRequest const& request);
}

#endif

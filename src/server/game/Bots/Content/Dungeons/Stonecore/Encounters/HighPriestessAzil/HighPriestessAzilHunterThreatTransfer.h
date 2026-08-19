#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_HUNTER_THREAT_TRANSFER_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_HUNTER_THREAT_TRANSFER_H

#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct HunterThreatTransferRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    AddWaveDiscoveryResult const* Discovery = nullptr;
    AddWaveDensityResult const* Density = nullptr;
    Unit** Add = nullptr;
    bool* SharedFocusValid = nullptr;
    std::string* Situation = nullptr;
    std::string* Action = nullptr;
    Unit** Target = nullptr;
};

struct HunterThreatTransferResult
{
    bool Handled = false;
    bool HunterMisdirectionActive = false;
};

HunterThreatTransferResult TryHunterThreatTransfer(
    HunterThreatTransferRequest const& request);
}

#endif

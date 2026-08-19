#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_FERAL_HANDOFF_STATE_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_FERAL_HANDOFF_STATE_H

#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilAddWaveDensity.h"

#include <functional>
#include <string>

class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct FeralHandoffStateRequest
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

struct FeralHandoffStateResult
{
    bool Handled = false;
    bool FeralChargePickupInFlight = false;
    Unit* FeralChargePickupTarget = nullptr;
    bool FeralChargePickupArrived = false;
    Unit* FeralHealerHandoffAnchor = nullptr;
    bool FeralHealerHandoffActive = false;
    bool FeralHealerHandoffArrived = false;
    std::function<bool(bool)> TryFeralRoarPickup;
};

FeralHandoffStateResult ResolveFeralHandoffState(
    FeralHandoffStateRequest const& request);
}

#endif

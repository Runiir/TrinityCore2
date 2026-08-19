#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_HEALER_ADD_WAVE_PREPOSITION_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_HEALER_ADD_WAVE_PREPOSITION_H

#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotWorldPopulationMgrBotState.h"

#include <functional>
#include <string>

class BotWorldPopulationMgr;
class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct AddWaveDiscoveryRequest;
struct AddWaveDiscoveryResult;
struct AddWaveDensityRequest;
struct AddWaveDensityResult;
struct AddWaveOpeningActionsRequest;

struct GroupHealCallback
{
    std::function<bool(Player*, Unit*, bool, bool)> Function;

    bool operator()(Player* healer, Unit* target,
        bool allowMovement = true, bool allowStationaryCastTime = false) const
    {
        return Function && Function(healer, target, allowMovement,
            allowStationaryCastTime);
    }
};

struct HealerAddWavePrepositionRequest
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
};

struct Context
{
    static bool Run(HealerAddWavePrepositionRequest const& request);
    static AddWaveDiscoveryResult Run(AddWaveDiscoveryRequest const& request);
    static AddWaveDensityResult Run(AddWaveDensityRequest const& request);
    static bool Run(AddWaveOpeningActionsRequest const& request);
};

bool TryHealerAddWavePreposition(
    HealerAddWavePrepositionRequest const& request);
}

#endif

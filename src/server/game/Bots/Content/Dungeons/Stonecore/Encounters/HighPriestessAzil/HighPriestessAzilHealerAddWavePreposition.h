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
struct AddWaveTankPreparationRequest;
struct AddWaveTankPreparationResult;
struct FeralHandoffStateRequest;
struct FeralHandoffStateResult;
struct FeralLocalRetentionRequest;
struct FeralRemoteActionsRequest;
struct FeralActiveSwarmMovementRequest;
struct HunterThreatTransferRequest;
struct HunterThreatTransferResult;
struct PassiveSwarmStagingRequest;
struct TankThreatRecoveryRequest;
struct SwarmThreatSafetyRequest;
struct HighDensityPositioningRequest;
struct DensityCombatResolutionRequest;
struct AddWaveOrchestrationRequest;

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
    static bool Run(AddWaveOrchestrationRequest const& request);
    static AddWaveDiscoveryResult Run(AddWaveDiscoveryRequest const& request);
    static AddWaveDensityResult Run(AddWaveDensityRequest const& request);
    static bool Run(AddWaveOpeningActionsRequest const& request);
    static AddWaveTankPreparationResult Run(
        AddWaveTankPreparationRequest const& request);
    static FeralHandoffStateResult Run(
        FeralHandoffStateRequest const& request);
    static bool Run(FeralLocalRetentionRequest const& request);
    static bool Run(FeralRemoteActionsRequest const& request);
    static bool Run(FeralActiveSwarmMovementRequest const& request);
    static HunterThreatTransferResult Run(
        HunterThreatTransferRequest const& request);
    static bool Run(PassiveSwarmStagingRequest const& request);
    static bool Run(TankThreatRecoveryRequest const& request);
    static bool Run(SwarmThreatSafetyRequest const& request);
    static bool Run(HighDensityPositioningRequest const& request);
    static bool Run(DensityCombatResolutionRequest const& request);
};

bool TryHealerAddWavePreposition(
    HealerAddWavePrepositionRequest const& request);
}

#endif

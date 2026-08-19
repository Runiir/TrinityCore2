#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_DENSITY_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_DENSITY_H

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/Content/Dungeons/Stonecore/HighPriestessAzil/HighPriestessAzilAddWaveDiscovery.h"

#include <cstddef>
#include <functional>
#include <string>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct AddWaveDensityRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
    AddWaveDiscoveryResult const* Discovery = nullptr;
    float CanonicalRouteDistance = 0.0f;
    float RouteArrivalRadius = 18.0f;
};

struct AddWaveDensityResult
{
    Unit* Add = nullptr;
    bool SharedFocusValid = false;
    bool BypassPreArrival = false;
    bool HighDensityPhase = false;
    bool SwarmDefenseActive = false;
    std::string Role;
    BotClassSpecActionProfile Profile;
    uint32 ReservedAreaSpellId = 0;
    Creature* DensityApproachAnchor = nullptr;
    Player* DensityTank = nullptr;
    Player* DensityHealer = nullptr;
    Player* DensityDefenseTarget = nullptr;
    uint32 DensityTankOwnedAddCount = 0;
    uint32 DensityTankSecureAddCount = 0;
    bool DensityTankOwnsSecureMajority = false;
    bool DensityTankOwnsVictimMajority = false;
    bool UrgentSwarmDamageRelease = false;
    bool DpsSwarmDamageRelease = false;
    bool BotInsideTankPickup = false;
    bool SharedLargePassiveSwarmStaging = false;
    std::function<size_t(Player const*)> ObservedListedAttackerCount;
};

AddWaveDensityResult ResolveAddWaveDensity(
    AddWaveDensityRequest const& request);
}

#endif

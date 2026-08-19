#ifndef TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_DISCOVERY_H
#define TRINITY_BOT_HIGH_PRIESTESS_AZIL_ADD_WAVE_DISCOVERY_H

#include "Bots/Content/Dungeons/Stonecore/Encounters/HighPriestessAzil/HighPriestessAzilHealerAddWavePreposition.h"

#include <functional>
#include <vector>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrContent::Stonecore::HighPriestessAzil
{
struct AddWaveDiscoveryRequest
{
    BotWorldPopulationMgr* Manager = nullptr;
    BotWorldPopulationMgrBotState::WorldBotState* State = nullptr;
    Player* Bot = nullptr;
    BotRolePowerBreakdown const* Power = nullptr;
    BotProgressionStage Stage = BotProgressionStage::Leveling;
    BotProgressionActivity Activity = BotProgressionActivity::ExperimentExploration;
};

struct AddWaveDiscoveryResult
{
    Unit* Add = nullptr;
    bool SharedFocusValid = false;
    uint32 AddCount = 0;
    uint32 EngagedAddCount = 0;
    uint32 NearbyAddCount = 0;
    float AddX = 0.0f;
    float AddY = 0.0f;
    std::vector<Creature*> LocalAdds;
    GuidSet CohortAddGuids;
    bool CohortSwarmActive = false;
    std::function<bool(Player*, Unit*)> IsUsableListedAdd;
};

AddWaveDiscoveryResult DiscoverAddWave(AddWaveDiscoveryRequest const& request);
}

#endif

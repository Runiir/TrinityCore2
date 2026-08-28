#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_CONTAMINATION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_CONTAMINATION_H

#include "Bots/BotWorldPopulationMgrRouteState.h"

#include <functional>
#include <string>
#include <vector>

class Creature;
class Player;
class Unit;

namespace BotWorldPopulationMgrBotState
{
struct WorldBotState;
}

namespace BotWorldPopulationMgrValidationRoute
{
// Contamination owns only the typed receipt and the narrow offense guard for
// an observed future encounter. It must not set route action state, terminal
// failure state, or any cohort-wide offense/recovery suppression.
struct ContaminationEvidenceSink
{
    std::vector<BotWorldPopulationMgrRouteState::ValidationRouteEvidence>& Records;
    std::string const& NodeId;
    uint64 Generation;
    std::string const& Kind;
};

struct ContaminationCallbacks
{
    std::function<void(std::function<void(Creature*)> const&)>
        ForEachActiveCombat;
    std::function<bool(Creature const*)>
        IsImmediateNextEncounterMember;
    std::function<void(BotWorldPopulationMgrBotState::WorldBotState&)>
        SuppressPlayerMelee;
};

struct ContaminationResult
{
    Creature* FutureTarget = nullptr;
    bool Observed = false;
    bool TargetCleared = false;
};

ContaminationResult ObserveAndGuard(
    BotWorldPopulationMgrBotState::WorldBotState& state, Player* bot,
    Unit*& target, ContaminationEvidenceSink const& evidence,
    ContaminationCallbacks const& callbacks);
}

#endif

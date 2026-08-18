#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_POLICY_HELPERS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_POLICY_HELPERS_H

#include "Bots/BotDatasetEvent.h"
#include "Bots/BotWorldPopulationMgr.h"

#include <string>

namespace BotWorldPopulationMgrPolicyHelpers
{
std::string LowerCopy(std::string value);
std::string BoundedResultLabel(char const* result);
std::string BoundedResultLabel(std::string const& result);
bool ContainsInsensitive(std::string const& text, char const* needle);
BotPolicySource WorldPolicySource(BotPolicyModelConfig const& config, bool decision);
std::string WorldPolicyVersion(BotPolicyModelConfig const& config, std::string const& brainVersion);
char const* ToString(BotWorldPopulationMgr::QuestObjectiveType type);
bool IsSimpleOpenWorldQuestMobAssistTarget(Player const* bot,
    BotWorldPopulationMgr::QuestObjectiveType objectiveType, bool isItemObjective,
    int32 requiredEntry, Unit const* target);
char const* ToString(BotWorldPopulationMgr::QuestClassification classification);
}

#endif

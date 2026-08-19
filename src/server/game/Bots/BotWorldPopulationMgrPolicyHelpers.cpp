#include "Bots/BotWorldPopulationMgrPolicyHelpers.h"

#include "Creature.h"
#include "Map.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <cctype>

namespace BotWorldPopulationMgrPolicyHelpers
{
std::string LowerCopy(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return char(std::tolower(c)); });
    return value;
}

std::string BoundedResultLabel(char const* result)
{
    std::string label = result && *result ? result : "ok";
    if (label.size() <= 63)
        return label;
    return label.substr(0, 63);
}

std::string BoundedResultLabel(std::string const& result)
{
    return BoundedResultLabel(result.c_str());
}

bool ContainsInsensitive(std::string const& text, char const* needle)
{
    if (!needle || !*needle)
        return false;
    return LowerCopy(text).find(LowerCopy(needle)) != std::string::npos;
}

BotPolicySource WorldPolicySource(BotPolicyModelConfig const& config, bool decision)
{
    if (config.Enabled && !config.Version.empty())
    {
        if (config.Mode == "assist")
            return BotPolicySource::AssistModel;
        if (config.Mode == "control")
            return BotPolicySource::ControlModel;
        return BotPolicySource::ShadowModel;
    }

    return decision ? BotPolicySource::Exploration : BotPolicySource::Heuristic;
}

std::string WorldPolicyVersion(BotPolicyModelConfig const& config, std::string const& brainVersion)
{
    return config.Enabled && !config.Version.empty() ? config.Version : brainVersion;
}

char const* ToString(BotWorldPopulationMgr::QuestObjectiveType type)
{
    switch (type)
    {
        case BotWorldPopulationMgr::QuestObjectiveType::Kill: return "kill";
        case BotWorldPopulationMgr::QuestObjectiveType::CollectItem: return "collect_item";
        case BotWorldPopulationMgr::QuestObjectiveType::InteractGameObject: return "interact_gameobject";
        case BotWorldPopulationMgr::QuestObjectiveType::CastSpellOnTarget: return "cast_spell_on_target";
        case BotWorldPopulationMgr::QuestObjectiveType::UseAbilityOnDummy: return "use_ability_on_dummy";
        case BotWorldPopulationMgr::QuestObjectiveType::UseItemOnTarget: return "use_item_on_target";
        default: return "unknown";
    }
}

bool IsSimpleOpenWorldQuestMobAssistTarget(Player const* bot,
    BotWorldPopulationMgr::QuestObjectiveType objectiveType, bool isItemObjective,
    int32 requiredEntry, Unit const* target)
{
    bool questMobObjective = objectiveType == BotWorldPopulationMgr::QuestObjectiveType::Kill
        || objectiveType == BotWorldPopulationMgr::QuestObjectiveType::CollectItem
        || isItemObjective;
    if (!bot || !target || !questMobObjective)
        return false;

    Creature const* creature = target->ToCreature();
    if (!creature || creature->isElite() || creature->IsDungeonBoss() || creature->isWorldBoss())
        return false;

    if (bot->GetMap() && (bot->GetMap()->IsDungeon() || bot->GetMap()->IsRaid()))
        return false;

    if (requiredEntry > 0 && creature->GetEntry() != uint32(requiredEntry))
        return false;

    return creature->getLevel() <= bot->getLevel() + 1;
}

char const* ToString(BotWorldPopulationMgr::QuestClassification classification)
{
    switch (classification)
    {
        case BotWorldPopulationMgr::QuestClassification::ObjectiveQuest: return "objective";
        case BotWorldPopulationMgr::QuestClassification::ChainQuest: return "chain";
        case BotWorldPopulationMgr::QuestClassification::UnsupportedQuest: return "unsupported";
        default: return "unknown";
    }
}
}

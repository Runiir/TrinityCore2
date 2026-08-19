#include "Bots/BotWorldPopulationMgr.h"

#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"

#include <algorithm>
#include <cctype>
#include <string>

namespace
{
std::string LowerCopy(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(), [](unsigned char c) { return char(std::tolower(c)); });
    return value;
}

bool ContainsInsensitive(std::string const& text, char const* needle)
{
    if (!needle || !*needle)
        return false;
    return LowerCopy(text).find(LowerCopy(needle)) != std::string::npos;
}
}

bool BotWorldPopulationMgr::FindQuestObjective(Player* bot, uint32 questId, QuestObjectivePlan& plan) const
{
    if (!bot || !questId)
        return false;

    auto questStatus = bot->getQuestStatusMap().find(questId);
    if (questStatus == bot->getQuestStatusMap().end() || questStatus->second.Status != QUEST_STATUS_INCOMPLETE)
        return false;

    Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
    if (!quest || !HasSimpleSupportedObjective(quest))
        return false;

    for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
    {
        int32 required = quest->RequiredNpcOrGo[i];
        uint32 requiredCount = quest->RequiredNpcOrGoCount[i];
        if (!required || !requiredCount || questStatus->second.CreatureOrGOCount[i] >= requiredCount)
            continue;

        plan = QuestObjectivePlan();
        plan.QuestId = quest->GetQuestId();
        plan.RequiredEntry = required;
        plan.RequiredCount = requiredCount;
        plan.CurrentCount = questStatus->second.CreatureOrGOCount[i];
        plan.IsGameObject = required < 0;
        plan.ObjectiveIndex = i;
        if (plan.IsGameObject)
            plan.ObjectiveType = QuestObjectiveType::InteractGameObject;
        else
        {
            CreatureTemplate const* tmpl = sObjectMgr->GetCreatureTemplate(uint32(required));
            bool configuredDummy = false;
            bool configuredDummyAllowed = false;
            if (tmpl)
                configuredDummy = IsDummyEntryConfigured(tmpl->Entry, &configuredDummyAllowed);
            bool dummyRequired = tmpl && (ContainsInsensitive(tmpl->Name, "training dummy") || (configuredDummy && configuredDummyAllowed));
            if (dummyRequired && QuestTextSuggestsAbilityObjective(quest))
            {
                plan.ObjectiveType = QuestObjectiveType::UseAbilityOnDummy;
                plan.RequiresTrainingDummy = true;
                plan.RequiredSpellId = SelectQuestAbilitySpell(bot, quest, plan);
            }
        }
        return true;
    }

    for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
    {
        uint32 requiredItem = quest->RequiredItemId[i];
        uint32 requiredCount = quest->RequiredItemCount[i];
        if (!requiredItem || !requiredCount || questStatus->second.ItemCount[i] >= requiredCount)
            continue;

        plan = QuestObjectivePlan();
        plan.QuestId = quest->GetQuestId();
        plan.RequiredCount = requiredCount;
        plan.CurrentCount = questStatus->second.ItemCount[i];
        plan.IsItemObjective = true;
        plan.ItemId = requiredItem;
        plan.ObjectiveIndex = i;
        plan.ObjectiveType = QuestTextSuggestsAbilityObjective(quest) ? QuestObjectiveType::UseItemOnTarget : QuestObjectiveType::CollectItem;
        return true;
    }

    return false;
}

BotWorldPopulationMgr::HeroicRaidProgression BotWorldPopulationMgr::BuildHeroicRaidProgression(WorldBotState const& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage) const
{
    HeroicRaidProgression progression;
    progression.TrackingEnabled = Cohort().Config.TrackHeroicRaidProgression;
    progression.HeroicEligible = stage == BotProgressionStage::HeroicRaid || (bot && bot->GetAverageItemLevel() >= 372.0f);
    progression.Stage = progression.HeroicEligible ? "heroic_raid" : (stage == BotProgressionStage::RaidReady ? "raid_ready" : "normal_raid");
    progression.RaidAttempts = state.RaidAttempts;
    progression.RaidBossKills = state.RaidBossKills;
    progression.HeroicRaidBossKills = state.HeroicRaidBossKills;
    progression.Wipes = state.RaidWipes;
    progression.RolePowerScore = power.Total;
    progression.TargetItemLevel = progression.HeroicEligible ? 372.0f : 359.0f;
    return progression;
}


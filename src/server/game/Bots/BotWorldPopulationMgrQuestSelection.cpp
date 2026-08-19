#include "Bots/BotWorldPopulationMgr.h"
#include "MotionMaster.h"

#include "Bots/BotExperienceLearningPolicy.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cctype>
#include <cstdlib>
#include <sstream>
#include <string>
#include <unordered_set>
#include <vector>

namespace
{
std::string LowerCopy(std::string value)
{
    std::transform(value.begin(), value.end(), value.begin(),
        [](unsigned char c) { return char(std::tolower(c)); });
    return value;
}

bool ContainsInsensitive(std::string const& text, char const* needle)
{
    if (!needle || !*needle)
        return false;
    return LowerCopy(text).find(LowerCopy(needle)) != std::string::npos;
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

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

bool BotWorldPopulationMgr::IsQuestRelevantTarget(Player* bot, Unit* target) const
{
    Creature const* creature = target ? target->ToCreature() : nullptr;
    if (!bot || !creature)
        return false;

    uint32 entry = creature->GetEntry();
    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE)
            continue;

        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest)
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
            if (quest->RequiredNpcOrGo[i] > 0 && uint32(quest->RequiredNpcOrGo[i]) == entry && questStatus.second.CreatureOrGOCount[i] < quest->RequiredNpcOrGoCount[i])
                return true;

        for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        {
            uint32 itemId = quest->RequiredItemId[i];
            if (!itemId || questStatus.second.ItemCount[i] >= quest->RequiredItemCount[i])
                continue;
            std::vector<uint32> const* questItems = sObjectMgr->GetCreatureQuestItemList(entry);
            if (questItems && std::find(questItems->begin(), questItems->end(), itemId) != questItems->end())
                return true;
        }
    }

    return false;
}

bool BotWorldPopulationMgr::IsProgressionCombatTarget(Player* bot, Unit* target, char const** rejectReason) const
{
    auto reject = [rejectReason](char const* reason) -> bool
    {
        if (rejectReason)
            *rejectReason = reason;
        return false;
    };

    if (!bot || !target || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
        return reject("not_progression_relevant");
    if (!bot->IsWithinDistInMap(target, 30.0f))
        return reject("not_progression_relevant");

    Creature const* creature = target->ToCreature();
    if (!creature)
        return reject("ambient");
    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    bool questRelevant = IsQuestRelevantTarget(bot, target);

    if (creature->IsCritter() || (tmpl && tmpl->type == CREATURE_TYPE_CRITTER))
        return reject("critter");
    if (creature->IsPet() || creature->IsTotem() || creature->IsSummon() || creature->IsGuardian() || !creature->GetOwnerGUID().IsEmpty())
        return reject("pet_or_totem");
    if (IsTrainingDummy(target) && !questRelevant)
        return reject("dummy_without_quest");
    if (creature->IsSpiritService() || creature->IsServiceProvider() || (tmpl && (tmpl->unit_flags & (UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_PACIFIED | UNIT_FLAG_IMMUNE_TO_PC))))
        return reject("ambient");
    if (!questRelevant && creature->HasFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_TAPPED) && !creature->HasFlag(UNIT_DYNAMIC_FLAGS, UNIT_DYNFLAG_TAPPED_BY_PLAYER))
        return reject("no_loot");
    if (creature->isElite() && !(bot->GetMap() && (bot->GetMap()->IsDungeon() || bot->GetMap()->IsRaid())) && !bot->GetGroup())
        return reject("not_progression_relevant");

    bool givesXp = bot->isHonorOrXPTarget(target);
    bool hasLoot = tmpl && (tmpl->lootid || tmpl->pickpocketLootId || tmpl->SkinLootId || tmpl->mingold || tmpl->maxgold);
    if (!questRelevant && !givesXp)
        return reject("no_xp");

    if (!questRelevant && !hasLoot)
        return reject("no_loot");

    if (!questRelevant && !givesXp && !hasLoot)
        return reject("not_progression_relevant");

    if (!questRelevant && creature->GetReactionTo(bot) >= REP_NEUTRAL)
        return reject("not_progression_relevant");

    return true;
}

Unit* BotWorldPopulationMgr::SelectSafeTarget(WorldBotState& state, Player* bot)
{
    if (!bot)
        return nullptr;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 30.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 30.0f);

    Unit* best = nullptr;
    float bestScore = -100000.0f;
    for (WorldObject* object : objects)
    {
        Unit* target = object ? object->ToUnit() : nullptr;
        if (target && IsTrainingDummy(target) && !IsQuestRelevantTarget(bot, target))
        {
            state.LastRejectedTargetReason = "dummy_without_quest";
            std::string raw = BuildRawJson(bot, target);
            std::string semantic = BuildSemanticJson(bot, target, "target_rejected");
            RecordEvent(state, bot, "target_rejected", target, "dummy_without_quest", raw.c_str(), semantic.c_str());
            continue;
        }
        char const* rejectReason = nullptr;
        if (!IsProgressionCombatTarget(bot, target, &rejectReason))
        {
            if (target && rejectReason)
            {
                state.LastRejectedTargetReason = rejectReason;
                std::string raw = BuildRawJson(bot, target);
                std::string semantic = BuildSemanticJson(bot, target, "target_rejected");
                RecordEvent(state, bot, "target_rejected", target, rejectReason, raw.c_str(), semantic.c_str());
            }
            continue;
        }

        if (Creature* creature = target->ToCreature())
            if (creature->isElite())
                continue;

        int32 levelDelta = int32(target->getLevel()) - int32(bot->getLevel());
        if (levelDelta > 1)
            continue;

        float dist = target->GetExactDist(bot);
        if (dist > 25.0f)
            continue;

        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreMob(bot, target, Cohort().LearningConfig);
        float score = 100.0f - dist - std::max<int32>(0, levelDelta) * 20.0f + learned.Score;
        if (!best || score > bestScore)
        {
            best = target;
            bestScore = score;
        }
    }

    return best;
}

bool BotWorldPopulationMgr::IsDummyEntryConfigured(uint32 entry, bool* explicitAllow) const
{
    if (explicitAllow)
        *explicitAllow = false;
    if (!entry || Cohort().Config.TrainingDummyEntries.empty())
        return false;

    std::stringstream entries(Cohort().Config.TrainingDummyEntries);
    std::string token;
    while (std::getline(entries, token, ','))
    {
        token.erase(std::remove_if(token.begin(), token.end(), [](unsigned char c) { return std::isspace(c); }), token.end());
        if (token.empty())
            continue;
        bool deny = token[0] == '!' || token[0] == '-';
        if (deny)
            token.erase(token.begin());
        if (token.empty() || token.find_first_not_of("0123456789") != std::string::npos)
            continue;
        if (uint32(strtoul(token.c_str(), nullptr, 10)) != entry)
            continue;
        if (explicitAllow)
            *explicitAllow = !deny;
        return true;
    }

    return false;
}

bool BotWorldPopulationMgr::IsTrainingDummy(Unit const* unit) const
{
    Creature const* creature = unit ? unit->ToCreature() : nullptr;
    if (!creature)
        return false;

    bool explicitAllow = false;
    if (IsDummyEntryConfigured(creature->GetEntry(), &explicitAllow))
        return explicitAllow;

    CreatureTemplate const* tmpl = creature->GetCreatureTemplate();
    if (!tmpl)
        return false;

    if ((tmpl->unit_flags & (UNIT_FLAG_PACIFIED | UNIT_FLAG_IMMUNE_TO_NPC)) || (tmpl->unit_flags2 & UNIT_FLAG2_CANNOT_TURN))
        if (ContainsInsensitive(tmpl->Name, "training dummy"))
            return true;

    return ContainsInsensitive(tmpl->Name, "training dummy");
}

bool BotWorldPopulationMgr::IsTrainingDummyAllowedForQuest(QuestObjectivePlan const& plan, Unit const* target) const
{
    if (!target || !IsTrainingDummy(target))
        return false;
    Creature const* creature = target->ToCreature();
    if (!creature)
        return false;
    if (plan.RequiredEntry > 0 && uint32(plan.RequiredEntry) == creature->GetEntry())
        return true;
    return plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.RequiresTrainingDummy;
}

bool BotWorldPopulationMgr::QuestTextSuggestsAbilityObjective(Quest const* quest) const
{
    if (!quest)
        return false;

    std::string text = quest->GetTitle() + " " + quest->GetObjectives() + " " + quest->GetDetails();
    for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        text += " " + quest->ObjectiveText[i];

    bool mentionsDummy = ContainsInsensitive(text, "training dummy") || ContainsInsensitive(text, "dummy");
    bool mentionsAction = ContainsInsensitive(text, "cast") || ContainsInsensitive(text, "use ") || ContainsInsensitive(text, "practice")
        || ContainsInsensitive(text, "ability") || ContainsInsensitive(text, "spell") || ContainsInsensitive(text, "sinister strike")
        || ContainsInsensitive(text, "steady shot") || ContainsInsensitive(text, "fireball") || ContainsInsensitive(text, "smite");
    return mentionsDummy && mentionsAction;
}

uint32 BotWorldPopulationMgr::SelectQuestAbilitySpell(Player* bot, Quest const* quest, QuestObjectivePlan const& plan) const
{
    if (!bot)
        return 0;
    if (plan.RequiredSpellId && bot->HasSpell(plan.RequiredSpellId))
        return plan.RequiredSpellId;

    std::string text;
    if (quest)
        text = LowerCopy(quest->GetTitle() + " " + quest->GetObjectives() + " " + quest->GetDetails());

    struct Candidate { uint32 SpellId; char const* Name; };
    Candidate named[] =
    {
        { 1752, "sinister strike" },
        { 56641, "steady shot" },
        { 133, "fireball" },
        { 585, "smite" },
        { 5176, "wrath" },
        { 403, "lightning bolt" },
        { 78, "heroic strike" }
    };
    for (Candidate const& candidate : named)
        if ((!text.empty() && text.find(candidate.Name) != std::string::npos) && bot->HasSpell(candidate.SpellId))
            return candidate.SpellId;

    uint32 candidates[4] = { 0, 0, 0, 0 };
    switch (bot->getClass())
    {
        case CLASS_MAGE: candidates[0] = 133; break;
        case CLASS_PRIEST: candidates[0] = 585; break;
        case CLASS_WARLOCK: candidates[0] = 686; break;
        case CLASS_DRUID: candidates[0] = 5176; break;
        case CLASS_SHAMAN: candidates[0] = 403; break;
        case CLASS_PALADIN: candidates[0] = 20271; break;
        case CLASS_HUNTER: candidates[0] = 75; break;
        case CLASS_DEATH_KNIGHT: candidates[0] = 45477; candidates[1] = 45462; break;
        case CLASS_WARRIOR: candidates[0] = 78; break;
        case CLASS_ROGUE: candidates[0] = 1752; break;
        default: break;
    }
    for (uint32 spellId : candidates)
        if (spellId && bot->HasSpell(spellId))
            return spellId;
    return 0;
}

uint32 BotWorldPopulationMgr::QuestObjectiveProgress(Player* bot, QuestObjectivePlan const& plan) const
{
    if (!bot)
        return 0;
    auto itr = bot->getQuestStatusMap().find(plan.QuestId);
    if (itr == bot->getQuestStatusMap().end())
        return 0;
    if (plan.IsItemObjective)
        return plan.ObjectiveIndex < QUEST_ITEM_OBJECTIVES_COUNT ? itr->second.ItemCount[plan.ObjectiveIndex] : 0;
    return plan.ObjectiveIndex < QUEST_OBJECTIVES_COUNT ? itr->second.CreatureOrGOCount[plan.ObjectiveIndex] : 0;
}

bool BotWorldPopulationMgr::GetQuestObjectivePlan(Player* bot, uint32 questId, uint32 objectiveIndex, QuestObjectiveType type, QuestObjectivePlan& plan) const
{
    if (!bot || !questId)
        return false;

    QuestObjectivePlan active;
    if (!FindQuestObjective(bot, questId, active))
        return false;
    if (active.QuestId != questId || active.ObjectiveIndex != objectiveIndex || active.ObjectiveType != type)
        return false;

    plan = active;
    return true;
}

void BotWorldPopulationMgr::SetQuestWorkPhase(WorldBotState& state, char const* phase)
{
    std::string next = phase ? phase : "idle";
    if (state.QuestWork.Phase != next)
    {
        state.QuestWork.Phase = next;
        state.QuestWork.PhaseStartedMs = NowMs();
    }
    state.CurrentQuestState = state.QuestWork.Phase;
}

void BotWorldPopulationMgr::SetQuestWorkFromPlan(WorldBotState& state, QuestObjectivePlan const& plan)
{
    bool changed = state.QuestWork.ActiveQuestId != plan.QuestId
        || state.QuestWork.ObjectiveIndex != plan.ObjectiveIndex
        || state.QuestWork.ObjectiveType != ToString(plan.ObjectiveType);
    if (changed)
    {
        state.QuestWork.SelectedTargetGuid.Clear();
        state.QuestWork.SelectedObjectGuid.Clear();
        state.QuestWork.RetryCount = 0;
        state.QuestWork.VerifiedCasts = 0;
        state.QuestWork.VerifyAfterMs = 0;
        state.QuestWork.FailedReason.clear();
        state.QuestWork.PhaseStartedMs = NowMs();
    }

    state.QuestWork.ActiveQuestId = plan.QuestId;
    state.QuestWork.ObjectiveIndex = plan.ObjectiveIndex;
    state.QuestWork.ObjectiveType = ToString(plan.ObjectiveType);
    state.QuestWork.RequiredEntry = plan.RequiredEntry;
    state.QuestWork.RequiredItem = plan.ItemId;
    state.QuestWork.RequiredSpell = plan.RequiredSpellId;
    state.QuestWork.RequiredCount = plan.RequiredCount;
    state.QuestWork.CurrentCount = plan.CurrentCount;
    state.CurrentObjectiveType = state.QuestWork.ObjectiveType;
    state.RequiredSpellId = plan.RequiredSpellId;
    state.RequiredItemId = plan.ItemId;
    state.RequiredTargetEntry = plan.RequiredEntry > 0 ? uint32(plan.RequiredEntry) : 0;
}

void BotWorldPopulationMgr::ResetQuestWork(WorldBotState& state)
{
    state.QuestWork = WorldBotState::BotQuestWorkState();
    state.NewlyAcceptedQuestId = 0;
    state.RecentlyAcceptedQuestUntilMs = 0;
    state.ObjectiveSearchUntilMs = 0;
    state.CurrentQuestState = "idle";
    state.CurrentObjectiveType = "none";
    state.RequiredSpellId = 0;
    state.RequiredItemId = 0;
    state.RequiredTargetEntry = 0;
}

bool BotWorldPopulationMgr::VerifyQuestObjectiveProgress(WorldBotState& state, Player* bot, QuestObjectivePlan const& plan, Unit const* target, uint32 before, char const* reason, char const* rawJson, char const* semanticJson)
{
    uint32 after = QuestObjectiveProgress(bot, plan);
    bool completed = bot && bot->CanCompleteQuest(plan.QuestId);
    state.LastQuestProgressBefore = before;
    state.LastQuestProgressAfter = after;
    state.QuestWork.ProgressBefore = before;
    state.QuestWork.ProgressAfter = after;
    state.QuestWork.CurrentCount = after;

    if (after > before || completed)
    {
        ++Cohort().Metrics.QuestObjectiveProgress;
        state.LastQuestObjectiveProgress = Cohort().Metrics.QuestObjectiveProgress;
        state.QuestWork.LastProgressMs = NowMs();
        state.QuestWork.RetryCount = 0;
        state.QuestWork.VerifiedCasts = 0;
        state.LastNoProgressReason.clear();
        RecordQuestEvent(state, bot, "objective_progress", plan.QuestId, target, reason ? reason : ToString(plan.ObjectiveType), rawJson, semanticJson, after, plan.ItemId);
        return true;
    }

    ++state.QuestWork.RetryCount;
    state.LastNoProgressReason = reason ? reason : "no_counter_change";
    std::ostringstream cooldownKey;
    cooldownKey << plan.QuestId << ":" << plan.ObjectiveIndex << ":" << ToString(plan.ObjectiveType) << ":";
    if (target)
        cooldownKey << target->GetGUID().GetCounter();
    else
        cooldownKey << 0;
    state.NoProgressCooldownUntilMs[cooldownKey.str()] = NowMs() + 45000;

    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();
    std::ostringstream context;
    context << "{\"quest_id\":" << plan.QuestId
            << ",\"objective_index\":" << plan.ObjectiveIndex
            << ",\"objective_type\":\"" << JsonEscape(ToString(plan.ObjectiveType)) << "\""
            << ",\"required_entry\":" << (plan.RequiredEntry > 0 ? uint32(plan.RequiredEntry) : 0)
            << ",\"required_item\":" << plan.ItemId
            << ",\"target_entry\":" << targetEntry
            << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
            << ",\"progress_before\":" << before
            << ",\"progress_after\":" << after
            << ",\"reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\"}";
    RecordQuestEvent(state, bot, "objective_no_progress", plan.QuestId, target, state.LastNoProgressReason.c_str(), rawJson, semanticJson, after, plan.ItemId, context.str().c_str());
    return false;
}

Unit* BotWorldPopulationMgr::SelectQuestObjectiveTarget(Player* bot, QuestObjectivePlan const& plan) const
{
    if (!bot || plan.IsGameObject)
        return nullptr;

    if (plan.IsItemObjective && plan.ItemId)
    {
        std::unordered_set<uint32> lootSourceEntries;
        if (QueryResult result = WorldDatabase.PQuery("SELECT Entry FROM creature_loot_template WHERE Item = %u", plan.ItemId))
        {
            do
            {
                lootSourceEntries.insert(result->Fetch()[0].GetUInt32());
            } while (result->NextRow());
        }

        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 70.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 70.0f);

        Creature* best = nullptr;
        float bestDist = -100000.0f;
        for (WorldObject* object : objects)
        {
            Creature* creature = object ? object->ToCreature() : nullptr;
            if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
                continue;
            if (IsTrainingDummy(creature) && !IsTrainingDummyAllowedForQuest(plan, creature))
                continue;

            bool itemSource = lootSourceEntries.find(creature->GetEntry()) != lootSourceEntries.end();
            if (std::vector<uint32> const* questItems = sObjectMgr->GetCreatureQuestItemList(creature->GetEntry()))
                itemSource = itemSource || std::find(questItems->begin(), questItems->end(), plan.ItemId) != questItems->end();
            if (!itemSource)
                continue;

            if (creature->isElite())
                continue;
            if (int32(creature->getLevel()) - int32(bot->getLevel()) > 1)
                continue;

            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreMob(bot, creature, Cohort().LearningConfig);
            float dist = bot->GetExactDist(creature);
            float score = 100.0f - dist + learned.Score;
            if (!best || score > bestDist)
            {
                best = creature;
                bestDist = score;
            }
        }

        if (best)
            return best;
    }

    if (!plan.RequiredEntry)
        return nullptr;

    std::vector<Creature*> creatures;
    bot->GetCreatureListWithEntryInGrid(creatures, uint32(plan.RequiredEntry), 60.0f);
    Creature* best = nullptr;
    float bestDist = -100000.0f;
    for (Creature* creature : creatures)
    {
        if (!creature || !creature->IsAlive() || !bot->IsValidAttackTarget(creature) || !bot->IsWithinLOSInMap(creature))
            continue;
        if (IsTrainingDummy(creature) && !IsTrainingDummyAllowedForQuest(plan, creature))
            continue;
        std::ostringstream cooldownKey;
        cooldownKey << plan.QuestId << ":" << plan.ObjectiveIndex << ":" << ToString(plan.ObjectiveType) << ":" << creature->GetGUID().GetCounter();
        auto cooldown = [&]() -> uint64
        {
            for (WorldBotState const& state : Party().Bots)
                if (state.Guid == bot->GetGUID())
                {
                    auto itr = state.NoProgressCooldownUntilMs.find(cooldownKey.str());
                    return itr != state.NoProgressCooldownUntilMs.end() ? itr->second : 0;
                }
            return 0;
        }();
        if (cooldown > NowMs())
            continue;
        if (creature->isElite())
            continue;
        if (int32(creature->getLevel()) - int32(bot->getLevel()) > 1)
            continue;

        BotLearnedScore learned = BotExperienceLearningPolicy::ScoreMob(bot, creature, Cohort().LearningConfig);
        float dist = bot->GetExactDist(creature);
        float score = 100.0f - dist + learned.Score;
        if (!best || score > bestDist)
        {
            best = creature;
            bestDist = score;
        }
    }

    return best;
}

Unit* BotWorldPopulationMgr::SelectQuestAbilityObjectiveTarget(Player* bot, QuestObjectivePlan const& plan, WorldBotState const& state) const
{
    if (!bot)
        return nullptr;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 70.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 70.0f);

    uint64 now = NowMs();
    Unit* best = nullptr;
    float bestDist = 0.0f;
    for (WorldObject* object : objects)
    {
        Unit* target = object ? object->ToUnit() : nullptr;
        Creature const* creature = target ? target->ToCreature() : nullptr;
        if (!target || !creature || !target->IsAlive() || !bot->IsValidAttackTarget(target) || !bot->IsWithinLOSInMap(target))
            continue;
        if (plan.RequiredEntry > 0 && creature->GetEntry() != uint32(plan.RequiredEntry))
            continue;
        if (plan.RequiresTrainingDummy && !IsTrainingDummy(target))
            continue;
        if (IsTrainingDummy(target) && !IsTrainingDummyAllowedForQuest(plan, target))
            continue;
        auto cooldown = state.DummyTargetCooldownUntilMs.find(target->GetGUID().GetCounter());
        if (cooldown != state.DummyTargetCooldownUntilMs.end() && cooldown->second > now)
            continue;
        std::ostringstream abilityKey;
        abilityKey << plan.QuestId << ":" << plan.RequiredSpellId << ":" << target->GetGUID().GetCounter();
        auto abilityCooldown = state.AbilityObjectiveCooldownUntilMs.find(abilityKey.str());
        if (abilityCooldown != state.AbilityObjectiveCooldownUntilMs.end() && abilityCooldown->second > now)
            continue;

        float dist = bot->GetExactDist(target);
        if (!best || dist < bestDist)
        {
            best = target;
            bestDist = dist;
        }
    }

    return best;
}

bool BotWorldPopulationMgr::StopDisallowedDummyCombat(WorldBotState& state, Player* bot, Unit* target)
{
    if (!bot || !target || !IsTrainingDummy(target))
        return false;

    QuestObjectivePlan plan;
    bool allowed = FindActiveQuestObjective(bot, plan) && IsTrainingDummyAllowedForQuest(plan, target)
        && (plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.ObjectiveType == QuestObjectiveType::CastSpellOnTarget);
    if (allowed)
        return false;

    SubmitMeleeAutoAttackIntent(state,
        BotMeleeAutoAttack::Kind::Suppress, ObjectGuid::Empty,
        BotMeleeAutoAttack::Owner::Safety,
        BotActionArbitration::Priority::Terminal,
        "training_dummy_without_ability_objective");
    bot->ClearUnitState(UNIT_STATE_CHASE);
    bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
    bot->GetMotionMaster()->MoveIdle();
    state.TargetGuid.Clear();
    state.WasInCombat = false;
    state.DummyTargetCooldownUntilMs[target->GetGUID().GetCounter()] = NowMs() + 30000;
    state.LastRejectedTargetReason = "training_dummy_without_ability_objective";
    state.CurrentTargetIsTrainingDummy = true;
    state.CurrentDummyAllowedByQuest = false;

    std::string raw = BuildRawJson(bot, target);
    std::string semantic = BuildSemanticJson(bot, target, "dummy_target_rejected");
    RecordEvent(state, bot, "dummy_target_rejected", target, "not_active_ability_objective", raw.c_str(), semantic.c_str());
    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    std::vector<BotActivityScore> activities = BotLongTermProgressionBrain::ScoreActivities(bot, power, BotLongTermProgressionBrain::ClassifyStage(bot, power), Cohort().Config.AllowQuesting, Cohort().Config.AllowCombat, &Cohort().LearningConfig);
    BotActivityScore chosen = BotLongTermProgressionBrain::ChooseActivity(activities);
    RecordDecision(state, bot, "dummy_target_rejected", "return_to_quest_state_machine", target, raw.c_str(), semantic.c_str(), activities, chosen, power, true, true);
    return true;
}

WorldObject* BotWorldPopulationMgr::SelectQuestGiver(Player* bot, bool completeOnly, uint32* questId, WorldBotState const* state) const
{
    if (questId)
        *questId = 0;
    if (!bot)
        return nullptr;

    std::vector<WorldObject*> objects;
    Trinity::AllWorldObjectsInRange check(bot, 80.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
    Cell::VisitAllObjects(bot, searcher, 80.0f);

    WorldObject* best = nullptr;
    uint32 bestQuestId = 0;
    float bestScore = 0.0f;
    for (WorldObject* object : objects)
    {
        if (!object || (object->GetTypeId() != TYPEID_UNIT && object->GetTypeId() != TYPEID_GAMEOBJECT))
            continue;

        QuestRelationResult relations;
        if (Creature* creature = object->ToCreature())
        {
            if (!creature->IsAlive())
                continue;
            relations = completeOnly ? sObjectMgr->GetCreatureQuestInvolvedRelations(creature->GetEntry()) : sObjectMgr->GetCreatureQuestRelations(creature->GetEntry());
        }
        else if (GameObject* go = object->ToGameObject())
            relations = completeOnly ? sObjectMgr->GetGOQuestInvolvedRelations(go->GetEntry()) : sObjectMgr->GetGOQuestRelations(go->GetEntry());
        else
            continue;

        for (uint32 candidateQuestId : relations)
        {
            Quest const* quest = sObjectMgr->GetQuestTemplate(candidateQuestId);
            if (!quest)
                continue;

            if (!completeOnly && state)
            {
                auto giverCooldown = state->QuestGiverCooldownUntilMs.find(object->GetGUID().GetCounter());
                if (giverCooldown != state->QuestGiverCooldownUntilMs.end() && giverCooldown->second > NowMs())
                    continue;
                auto questCooldown = state->QuestCooldownUntilMs.find(candidateQuestId);
                if (questCooldown != state->QuestCooldownUntilMs.end() && questCooldown->second > NowMs())
                    continue;
            }

            if (completeOnly)
            {
                if (bot->GetQuestStatus(candidateQuestId) != QUEST_STATUS_COMPLETE || !bot->CanRewardQuest(quest, false))
                    continue;
            }
            else
            {
                if (!bot->CanTakeQuest(quest, false) || !bot->CanAddQuest(quest, false) || ClassifyQuestForBot(bot, quest) == QuestClassification::UnsupportedQuest)
                    continue;
            }

            float dist = bot->GetExactDist(object);
            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreQuest(bot, candidateQuestId, Cohort().LearningConfig);
            float areaDanger = BotExperienceLearningPolicy::ScoreArea(bot, object->GetAreaId(), Cohort().LearningConfig).Score;
            float score = (completeOnly ? 1000.0f : 100.0f) - dist + learned.Score + areaDanger;
            if (!best || score > bestScore)
            {
                best = object;
                bestQuestId = candidateQuestId;
                bestScore = score;
            }
        }
    }

    if (questId)
        *questId = bestQuestId;
    return best;
}

WorldObject* BotWorldPopulationMgr::SelectQuestGameObject(Player* bot, QuestObjectivePlan const& plan) const
{
    if (!bot || (!plan.IsGameObject && !plan.IsItemObjective))
        return nullptr;

    if (plan.IsItemObjective && plan.ItemId)
    {
        std::vector<WorldObject*> objects;
        Trinity::AllWorldObjectsInRange check(bot, 70.0f);
        Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> searcher(bot, objects, check);
        Cell::VisitAllObjects(bot, searcher, 70.0f);

        GameObject* best = nullptr;
        float bestDist = 0.0f;
        for (WorldObject* object : objects)
        {
            GameObject* go = object ? object->ToGameObject() : nullptr;
            if (!go || !bot->IsInPhase(go))
                continue;

            std::vector<uint32> const* questItems = sObjectMgr->GetGameObjectQuestItemList(go->GetEntry());
            if (!questItems || std::find(questItems->begin(), questItems->end(), plan.ItemId) == questItems->end())
                continue;

            float dist = bot->GetExactDist(go);
            if (!best || dist < bestDist)
            {
                best = go;
                bestDist = dist;
            }
        }

        if (best)
            return best;
    }

    if (!plan.IsGameObject || plan.RequiredEntry >= 0)
        return nullptr;

    std::vector<GameObject*> gameObjects;
    bot->GetGameObjectListWithEntryInGrid(gameObjects, uint32(-plan.RequiredEntry), 70.0f);
    GameObject* best = nullptr;
    float bestDist = 0.0f;
    for (GameObject* go : gameObjects)
    {
        if (!go || !bot->IsInPhase(go))
            continue;

        float dist = bot->GetExactDist(go);
        if (!best || dist < bestDist)
        {
            best = go;
            bestDist = dist;
        }
    }

    return best;
}

bool BotWorldPopulationMgr::FindActiveQuestObjective(Player* bot, QuestObjectivePlan& plan) const
{
    if (!bot)
        return false;

    bool found = false;
    float bestScore = -100000.0f;
    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE)
            continue;

        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest || !HasSimpleSupportedObjective(quest))
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        {
            int32 required = quest->RequiredNpcOrGo[i];
            uint32 requiredCount = quest->RequiredNpcOrGoCount[i];
            if (!required || !requiredCount || questStatus.second.CreatureOrGOCount[i] >= requiredCount)
                continue;

            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreQuest(bot, quest->GetQuestId(), Cohort().LearningConfig);
            float progress = requiredCount ? float(questStatus.second.CreatureOrGOCount[i]) / float(requiredCount) : 0.0f;
            float score = 25.0f + progress * 10.0f + learned.Score;
            if (!found || score > bestScore)
            {
                plan = QuestObjectivePlan();
                plan.QuestId = quest->GetQuestId();
                plan.RequiredEntry = required;
                plan.RequiredCount = requiredCount;
                plan.CurrentCount = questStatus.second.CreatureOrGOCount[i];
                plan.IsGameObject = required < 0;
                plan.ObjectiveIndex = i;
                if (plan.IsGameObject)
                    plan.ObjectiveType = QuestObjectiveType::InteractGameObject;
                else
                {
                    CreatureTemplate const* tmpl = required > 0 ? sObjectMgr->GetCreatureTemplate(uint32(required)) : nullptr;
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
                found = true;
                bestScore = score;
            }
        }

        for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        {
            uint32 requiredItem = quest->RequiredItemId[i];
            uint32 requiredCount = quest->RequiredItemCount[i];
            if (!requiredItem || !requiredCount || questStatus.second.ItemCount[i] >= requiredCount)
                continue;

            BotLearnedScore learned = BotExperienceLearningPolicy::ScoreQuest(bot, quest->GetQuestId(), Cohort().LearningConfig);
            float progress = requiredCount ? float(questStatus.second.ItemCount[i]) / float(requiredCount) : 0.0f;
            float score = 20.0f + progress * 10.0f + learned.Score;
            if (!found || score > bestScore)
            {
                plan = QuestObjectivePlan();
                plan.QuestId = quest->GetQuestId();
                plan.RequiredCount = requiredCount;
                plan.CurrentCount = questStatus.second.ItemCount[i];
                plan.IsItemObjective = true;
                plan.ItemId = requiredItem;
                plan.ObjectiveIndex = i;
                plan.ObjectiveType = QuestTextSuggestsAbilityObjective(quest) ? QuestObjectiveType::UseItemOnTarget : QuestObjectiveType::CollectItem;
                found = true;
                bestScore = score;
            }
        }
    }

    return found;
}

bool BotWorldPopulationMgr::HasSimpleSupportedObjective(Quest const* quest) const
{
    if (!quest)
        return false;

    // Seasonal/event quests often reuse creature counters for scripted spell, vehicle, or world-state
    // mechanics. Keep them out of the generic teacher until an event planner manifest covers them.
    if (quest->IsSeasonal())
        return false;

    if (quest->IsTurnIn())
        return true;

    for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
    {
        int32 required = quest->RequiredNpcOrGo[i];
        if (!required || !quest->RequiredNpcOrGoCount[i])
            continue;

        if (required < 0)
            return true;

        CreatureTemplate const* tmpl = sObjectMgr->GetCreatureTemplate(uint32(required));
        bool configuredDummy = false;
        bool configuredDummyAllowed = false;
        if (tmpl)
            configuredDummy = IsDummyEntryConfigured(tmpl->Entry, &configuredDummyAllowed);
        bool dummyRequired = tmpl && (ContainsInsensitive(tmpl->Name, "training dummy") || (configuredDummy && configuredDummyAllowed));
        if (dummyRequired && QuestTextSuggestsAbilityObjective(quest))
            return true;

        if (!quest->HasSpecialFlag(QUEST_SPECIAL_FLAGS_KILL))
            continue;
        if (!tmpl)
            continue;
        if (tmpl->type == CREATURE_TYPE_CRITTER)
            continue;
        if (ContainsInsensitive(tmpl->Name, "DND") || ContainsInsensitive(tmpl->Name, "bunny") || ContainsInsensitive(tmpl->Name, "trigger"))
            continue;
        if (tmpl->unit_flags & (UNIT_FLAG_NON_ATTACKABLE | UNIT_FLAG_PACIFIED | UNIT_FLAG_IMMUNE_TO_PC))
            continue;
        if (tmpl->minlevel > 0 && quest->GetQuestLevel() > 0 && int32(tmpl->minlevel) > quest->GetQuestLevel() + 5)
            continue;

        return true;
    }

    for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        if (quest->RequiredItemId[i] && quest->RequiredItemCount[i])
            return true;

    return false;
}

BotWorldPopulationMgr::QuestClassification BotWorldPopulationMgr::ClassifyQuestForBot(Player* bot, Quest const* quest) const
{
    if (!quest)
        return QuestClassification::UnsupportedQuest;

    if (HasSimpleSupportedObjective(quest))
        return QuestClassification::ObjectiveQuest;

    if (quest->GetNextQuestInChain() || quest->GetNextQuestId() || quest->GetBreadcrumbForQuestId())
        return QuestClassification::ChainQuest;

    if (quest->IsTurnIn())
        return QuestClassification::ChainQuest;

    QueryResult ender = WorldDatabase.PQuery(
        "SELECT 1 FROM creature_questender WHERE quest = %u UNION SELECT 1 FROM gameobject_questender WHERE quest = %u LIMIT 1",
        quest->GetQuestId(), quest->GetQuestId());
    if (ender)
        return QuestClassification::ChainQuest;

    if (bot && bot->CanCompleteQuest(quest->GetQuestId()))
        return QuestClassification::ChainQuest;

    return QuestClassification::UnsupportedQuest;
}

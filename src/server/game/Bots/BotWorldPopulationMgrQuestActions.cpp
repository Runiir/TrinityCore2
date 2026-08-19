#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "CellImpl.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameObject.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "ObjectAccessor.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Random.h"
#include "Server/Packets/QuestPackets.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"
#include "Util.h"
#include "WorldPacket.h"
#include "WorldSession.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace
{
bool SubmitNativeQuestAccept(Player* bot, WorldObject* giver, uint32 questId)
{
    if (!bot || !giver || !questId || !bot->GetSession()
        || !bot->IsWithinDistInMap(giver, INTERACTION_DISTANCE))
        return false;

    WorldPackets::Quest::QuestGiverAcceptQuest packet(
        WorldPacket(CMSG_QUEST_GIVER_ACCEPT_QUEST, 0));
    packet.QuestGiverGUID = giver->GetGUID();
    packet.QuestID = questId;
    packet.StartCheat = 0;
    bot->GetSession()->HandleQuestgiverAcceptQuestOpcode(packet);
    QuestStatus const status = bot->GetQuestStatus(questId);
    return status == QUEST_STATUS_INCOMPLETE || status == QUEST_STATUS_COMPLETE;
}

bool SubmitNativeQuestReward(Player* bot, WorldObject* giver, uint32 questId, uint32 rewardChoice)
{
    if (!bot || !giver || !questId || !bot->GetSession()
        || !bot->IsWithinDistInMap(giver, INTERACTION_DISTANCE))
        return false;

    WorldPackets::Quest::QuestGiverChooseReward packet(
        WorldPacket(CMSG_QUEST_GIVER_CHOOSE_REWARD, 0));
    packet.QuestGiverGUID = giver->GetGUID();
    packet.QuestID = int32(questId);
    packet.ItemChoiceID = int32(rewardChoice);
    bot->GetSession()->HandleQuestgiverChooseRewardOpcode(packet);
    return bot->GetQuestStatus(questId) != QUEST_STATUS_COMPLETE;
}

float Distance2d(float ax, float ay, float bx, float by)
{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
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

BotWorldPopulationMgr::QuestActionResult BotWorldPopulationMgr::TryQuesting(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity)
{
    QuestActionResult result;
    if (!bot || bot->IsInCombat())
        return result;

    QuestObjectivePlan committedPlan;
    bool hasCommittedPlan = state.QuestWork.ActiveQuestId
        && FindQuestObjective(bot, state.QuestWork.ActiveQuestId, committedPlan);
    QuestObjectivePlan acceptedPlan;
    bool hasAcceptedPlan = !hasCommittedPlan && state.NewlyAcceptedQuestId && FindQuestObjective(bot, state.NewlyAcceptedQuestId, acceptedPlan);
    QuestObjectivePlan discoveredPlan;
    bool hasActiveObjective = hasCommittedPlan || hasAcceptedPlan || FindActiveQuestObjective(bot, discoveredPlan);
    if (hasCommittedPlan)
        discoveredPlan = committedPlan;
    else if (hasAcceptedPlan)
        discoveredPlan = acceptedPlan;
    if (state.QuestWork.CooldownUntilMs > NowMs())
        hasActiveObjective = false;

    if (state.QuestWork.ActiveQuestId && bot->CanCompleteQuest(state.QuestWork.ActiveQuestId) && state.QuestWork.Phase != "move_to_turnin")
    {
        QuestObjectivePlan completedPlan = committedPlan;
        if (!hasCommittedPlan)
        {
            completedPlan.QuestId = state.QuestWork.ActiveQuestId;
            completedPlan.ObjectiveIndex = state.QuestWork.ObjectiveIndex;
            completedPlan.RequiredEntry = state.QuestWork.RequiredEntry;
            completedPlan.ItemId = state.QuestWork.RequiredItem;
            completedPlan.RequiredSpellId = state.QuestWork.RequiredSpell;
            completedPlan.RequiredCount = state.QuestWork.RequiredCount;
            completedPlan.CurrentCount = state.QuestWork.CurrentCount;
            completedPlan.IsItemObjective = state.QuestWork.ObjectiveType == "collect_item" || state.QuestWork.ObjectiveType == "use_item_on_target";
            completedPlan.IsGameObject = state.QuestWork.ObjectiveType == "interact_gameobject";
            completedPlan.ObjectiveType = state.QuestWork.ObjectiveType == "collect_item" ? QuestObjectiveType::CollectItem :
                (state.QuestWork.ObjectiveType == "use_item_on_target" ? QuestObjectiveType::UseItemOnTarget :
                (state.QuestWork.ObjectiveType == "use_ability_on_dummy" ? QuestObjectiveType::UseAbilityOnDummy :
                (state.QuestWork.ObjectiveType == "cast_spell_on_target" ? QuestObjectiveType::CastSpellOnTarget :
                (state.QuestWork.ObjectiveType == "interact_gameobject" ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill))));
        }

        Unit* completedTarget = state.QuestWork.SelectedTargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid);
        uint32 before = state.QuestWork.ProgressBefore ? state.QuestWork.ProgressBefore : state.LastQuestProgressBefore;
        uint32 after = QuestObjectiveProgress(bot, completedPlan);
        std::string raw = BuildRawJson(bot, completedTarget);
        std::string semantic = BuildSemanticJson(bot, completedTarget, "quest_objective_reconcile", &power, stage, activity);
        bool progressed = VerifyQuestObjectiveProgress(state, bot, completedPlan, completedTarget, before, "completed_counter_reconciled", raw.c_str(), semantic.c_str());
        if (progressed && completedPlan.ObjectiveType == QuestObjectiveType::Kill)
        {
            uint32 delta = after > before ? after - before : 1;
            Cohort().Metrics.Kills += delta;
            state.LastKilledTargetGuid = completedTarget ? completedTarget->GetGUID() : state.QuestWork.SelectedTargetGuid;
            RecordEvent(state, bot, "mob_killed", completedTarget, "quest_counter_reconciled", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Kills);
        }

        result.Handled = true;
        result.Situation = "quest_verify_progress";
        result.Action = "reconcile_completed_objective";
        result.QuestId = completedPlan.QuestId;
        result.Target = completedTarget;
        state.TargetGuid.Clear();
        state.WasInCombat = false;
        SetQuestWorkPhase(state, "move_to_turnin");
        return result;
    }

    if (state.QuestWork.Phase == "verify_progress" && hasCommittedPlan)
    {
        result.Handled = true;
        result.Situation = "quest_verify_progress";
        result.Action = "verify_progress";
        result.QuestId = committedPlan.QuestId;
        Unit* verifyTarget = state.QuestWork.SelectedTargetGuid.IsEmpty() ? nullptr : ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid);
        result.Target = verifyTarget;
        if (state.QuestWork.VerifyAfterMs && NowMs() < state.QuestWork.VerifyAfterMs)
            return result;

        std::string raw = BuildRawJson(bot, verifyTarget);
        std::string semantic = BuildSemanticJson(bot, verifyTarget, "quest_verify_progress", &power, stage, activity);
        bool progressed = VerifyQuestObjectiveProgress(state, bot, committedPlan, verifyTarget, state.QuestWork.ProgressBefore, "delayed_ability_verify", raw.c_str(), semantic.c_str());
        if (!progressed)
        {
            ++state.QuestWork.VerifiedCasts;
            if (state.QuestWork.VerifiedCasts >= 3 && verifyTarget)
            {
                std::ostringstream key;
                key << committedPlan.QuestId << ":" << state.QuestWork.RequiredSpell << ":" << verifyTarget->GetGUID().GetCounter();
                state.AbilityObjectiveCooldownUntilMs[key.str()] = NowMs() + 120000;
                state.DummyTargetCooldownUntilMs[verifyTarget->GetGUID().GetCounter()] = NowMs() + 120000;
                state.LastRejectedTargetReason = "ability_objective_no_progress_after_delay";
                result.Failure = true;
                RecordDecision(state, bot, "quest_ability_objective", "blacklist_target_spell_pair", verifyTarget, raw.c_str(), semantic.c_str(), std::vector<BotActivityScore>(), BotActivityScore(), power, true, true);
            }
            SetQuestWorkPhase(state, "search_objective");
        }
        else
            SetQuestWorkPhase(state, bot->CanCompleteQuest(committedPlan.QuestId) ? "move_to_turnin" : "choose_objective");
        return result;
    }

    uint32 questId = 0;
    WorldObject* turnIn = SelectQuestGiver(bot, true, &questId, &state);
    if (turnIn)
    {
        Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
        if (!quest)
            return result;

        result.Handled = true;
        result.Situation = "quest_turn_in";
        result.Action = "move_to_quest_complete";
        result.QuestId = questId;

        if (!bot->IsWithinDistInMap(turnIn, INTERACTION_DISTANCE))
        {
            MoveBotToPoint(state, bot, turnIn->GetPositionX(), turnIn->GetPositionY(), turnIn->GetPositionZ());
            return result;
        }

        uint32 rewardItemId = 0;
        uint32 rewardChoice = ChooseQuestReward(bot, quest, &rewardItemId);
        result.RewardChoice = rewardChoice;
        result.RewardItemId = rewardItemId;
        if (!bot->CanRewardQuest(quest, rewardChoice, false))
        {
            result.Failure = true;
            result.Rare = true;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_turn_in_failed", &power, stage, activity);
            RecordQuestEvent(state, bot, "objective_failed", questId, nullptr, "reward_blocked", raw.c_str(), semantic.c_str(), 0, rewardItemId);
            RecordQuestReplay(state, bot, "quest_failure", questId, raw.c_str(), semantic.c_str(), "{\"action\":\"reward_quest\"}", "{\"reason\":\"reward_blocked\"}");
            return result;
        }

        float powerBefore = power.Total;
        uint8 levelBefore = bot->getLevel();
        uint64 moneyBefore = bot->GetMoney();
        auto completedStatus = bot->getQuestStatusMap().find(questId);
        if (completedStatus != bot->getQuestStatusMap().end())
        {
            bool progressAlreadyRecorded = state.QuestWork.ActiveQuestId == questId
                && state.QuestWork.ProgressAfter > 0
                && state.QuestWork.ProgressAfter >= state.QuestWork.RequiredCount;
            if (!progressAlreadyRecorded)
            {
                for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
                {
                    int32 required = quest->RequiredNpcOrGo[i];
                    uint32 requiredCount = quest->RequiredNpcOrGoCount[i];
                    uint32 progress = completedStatus->second.CreatureOrGOCount[i];
                    if (!required || !requiredCount || progress < requiredCount)
                        continue;

                    QuestObjectivePlan completedPlan;
                    completedPlan.QuestId = questId;
                    completedPlan.RequiredEntry = required;
                    completedPlan.RequiredCount = requiredCount;
                    completedPlan.CurrentCount = progress;
                    completedPlan.ObjectiveIndex = i;
                    completedPlan.IsGameObject = required < 0;
                    completedPlan.ObjectiveType = completedPlan.IsGameObject ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill;

                    std::string raw = BuildRawJson(bot, nullptr);
                    std::string semantic = BuildSemanticJson(bot, nullptr, "quest_turnin_objective_reconcile", &power, stage, activity);
                    RecordQuestEvent(state, bot, "objective_progress", questId, nullptr, "turnin_counter_reconciled", raw.c_str(), semantic.c_str(), progress, completedPlan.ItemId);
                    ++Cohort().Metrics.QuestObjectiveProgress;
                    state.LastQuestObjectiveProgress = Cohort().Metrics.QuestObjectiveProgress;
                    state.LastQuestProgressBefore = 0;
                    state.LastQuestProgressAfter = progress;
                    if (completedPlan.ObjectiveType == QuestObjectiveType::Kill)
                    {
                        Cohort().Metrics.Kills += progress;
                        state.LastKilledTargetGuid.Clear();
                        RecordEvent(state, bot, "mob_killed", nullptr, "turnin_counter_reconciled", raw.c_str(), semantic.c_str(), 0.0f, Cohort().Metrics.Kills);
                    }
                }

                for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
                {
                    uint32 requiredItem = quest->RequiredItemId[i];
                    uint32 requiredCount = quest->RequiredItemCount[i];
                    uint32 progress = completedStatus->second.ItemCount[i];
                    if (!requiredItem || !requiredCount || progress < requiredCount)
                        continue;

                    std::string raw = BuildRawJson(bot, nullptr);
                    std::string semantic = BuildSemanticJson(bot, nullptr, "quest_turnin_objective_reconcile", &power, stage, activity);
                    RecordQuestEvent(state, bot, "objective_progress", questId, nullptr, "turnin_counter_reconciled", raw.c_str(), semantic.c_str(), progress, requiredItem);
                    ++Cohort().Metrics.QuestObjectiveProgress;
                    state.LastQuestObjectiveProgress = Cohort().Metrics.QuestObjectiveProgress;
                    state.LastQuestProgressBefore = 0;
                    state.LastQuestProgressAfter = progress;
                }
            }
        }
        if (!SubmitNativeQuestReward(bot, turnIn, questId, rewardChoice))
        {
            result.Failure = true;
            result.Rare = true;
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_turn_in_failed", &power, stage, activity);
            RecordQuestEvent(state, bot, "objective_failed", questId, nullptr,
                "native_reward_submission_failed", raw.c_str(), semantic.c_str(), 0, rewardItemId);
            return result;
        }
        ++Cohort().Metrics.QuestsCompleted;
        state.LastQuestCompletedCount = Cohort().Metrics.QuestsCompleted;
        uint32 elapsed = state.QuestStartTime ? (Cohort().ElapsedMs / 1000) - state.QuestStartTime : 0;
        uint32 deaths = Cohort().Metrics.Deaths >= state.QuestStartDeaths ? Cohort().Metrics.Deaths - state.QuestStartDeaths : 0;
        BotRolePowerBreakdown powerAfter = BotLongTermProgressionBrain::CalculateRolePower(bot);
        std::ostringstream context;
        context << "{\"reward_choice\":" << rewardChoice
                << ",\"reward_item_id\":" << rewardItemId
                << ",\"time_to_complete_sec\":" << elapsed
                << ",\"death_count\":" << deaths
                << ",\"level_delta\":" << int32(bot->getLevel()) - int32(levelBefore)
                << ",\"gold_delta\":" << int64(bot->GetMoney()) - int64(moneyBefore)
                << ",\"power_gain\":" << (powerAfter.Total - powerBefore) << "}";

        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_completed", &powerAfter, stage, activity);
        RecordQuestEvent(state, bot, "reward_chosen", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), rewardChoice, rewardItemId, context.str().c_str());
        RecordQuestEvent(state, bot, "quest_completed", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), elapsed, rewardItemId, context.str().c_str());
        RecordQuestEvent(state, bot, "chain_step_turnin", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), elapsed, rewardItemId, context.str().c_str());
        result.Action = "complete_quest";
        ResetQuestWork(state);
        state.QuestSearchRadiusIndex = 0;
        return result;
    }

    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_COMPLETE)
            continue;
        Quest const* completedQuest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!completedQuest || !bot->CanRewardQuest(completedQuest, false))
            continue;
        QuestRoutePoint turnInRoute;
        if (!FindQuestTurnInDestination(bot, questStatus.first, turnInRoute))
            continue;

        result.Handled = true;
        result.Situation = "quest_turn_in";
        result.Action = "travel_to_quest_turnin";
        result.QuestId = questStatus.first;
        state.QuestRouteDestination.Valid = true;
        state.QuestRouteDestination.MapId = turnInRoute.MapId;
        state.QuestRouteDestination.X = turnInRoute.X;
        state.QuestRouteDestination.Y = turnInRoute.Y;
        state.QuestRouteDestination.Z = turnInRoute.Z;
        state.QuestRouteDestination.QuestId = turnInRoute.QuestId;
        state.QuestRouteDestination.Reason = turnInRoute.Source;
        float turnInDistance = turnInRoute.MapId == bot->GetMapId() ? Distance2d(bot->GetPositionX(), bot->GetPositionY(), turnInRoute.X, turnInRoute.Y) : 100000.0f;
        if (turnInDistance <= INTERACTION_DISTANCE)
        {
            // Coordinates discovered from DB are navigation hints.  They do
            // not authorize a reward without an observed questgiver object.
            result.Action = "await_visible_quest_turnin";
            state.LastNoQuestReason = "db_turnin_reached_without_visible_giver";
            return result;
        }
        MoveBotToPoint(state, bot, turnInRoute.X, turnInRoute.Y, turnInRoute.Z);
        RecordQuestEvent(state, bot, "chain_step_turnin", questStatus.first, nullptr, "travel_to_turnin", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_turn_in", &power, stage, activity).c_str());
        return result;
    }

    std::vector<WorldObject*> hubObjects;
    Trinity::AllWorldObjectsInRange hubCheck(bot, 80.0f);
    Trinity::WorldObjectListSearcher<Trinity::AllWorldObjectsInRange> hubSearcher(bot, hubObjects, hubCheck);
    Cell::VisitAllObjects(bot, hubSearcher, 80.0f);

    uint32 acceptedCount = 0;
    uint32 lastAcceptedQuestId = 0;
    for (WorldObject* object : hubObjects)
    {
        if (!object || (object->GetTypeId() != TYPEID_UNIT && object->GetTypeId() != TYPEID_GAMEOBJECT))
            continue;

        QuestRelationResult relations;
        if (Creature* creature = object->ToCreature())
        {
            if (!creature->IsAlive())
                continue;
            relations = sObjectMgr->GetCreatureQuestRelations(creature->GetEntry());
        }
        else if (GameObject* go = object->ToGameObject())
            relations = sObjectMgr->GetGOQuestRelations(go->GetEntry());
        else
            continue;

        for (uint32 candidateQuestId : relations)
        {
            Quest const* quest = sObjectMgr->GetQuestTemplate(candidateQuestId);
            if (!quest)
                continue;
            if (!bot->CanTakeQuest(quest, false) || !bot->CanAddQuest(quest, false))
                continue;
            auto questCooldown = state.QuestCooldownUntilMs.find(candidateQuestId);
            if (questCooldown != state.QuestCooldownUntilMs.end() && questCooldown->second > NowMs())
                continue;

            QuestClassification classification = ClassifyQuestForBot(bot, quest);
            state.LastQuestClassification = ToString(classification);
            if (classification == QuestClassification::UnsupportedQuest)
                continue;

            if (!bot->IsWithinDistInMap(object, INTERACTION_DISTANCE))
            {
                if (!acceptedCount)
                {
                    result.Handled = true;
                    result.Situation = "quest_pickup";
                    result.Action = "move_to_quest_hub";
                    result.QuestId = candidateQuestId;
                    MoveBotToPoint(state, bot, object->GetPositionX(), object->GetPositionY(), object->GetPositionZ());
                }
                continue;
            }

            SubmitNativeQuestAccept(bot, object, candidateQuestId);
            QuestStatus status = bot->GetQuestStatus(candidateQuestId);
            auto questItr = bot->getQuestStatusMap().find(candidateQuestId);
            bool accepted = questItr != bot->getQuestStatusMap().end() && (status == QUEST_STATUS_INCOMPLETE || status == QUEST_STATUS_COMPLETE);
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_hub_sweep", &power, stage, activity);
            RecordQuestEvent(state, bot, "quest_seen", candidateQuestId, nullptr, ToString(classification), raw.c_str(), semantic.c_str());
            if (!accepted)
            {
                state.QuestCooldownUntilMs[candidateQuestId] = NowMs() + 60000;
                RecordQuestEvent(state, bot, "quest_accept_failed", candidateQuestId, nullptr, "quest_log_entry_missing", raw.c_str(), semantic.c_str());
                continue;
            }

            ++acceptedCount;
            lastAcceptedQuestId = candidateQuestId;
            ++Cohort().Metrics.QuestsAccepted;
            state.LastQuestId = candidateQuestId;
            state.NewlyAcceptedQuestId = candidateQuestId;
            state.RecentlyAcceptedQuestUntilMs = NowMs() + 30000;
            state.QuestStartTime = Cohort().ElapsedMs / 1000;
            state.QuestStartDeaths = Cohort().Metrics.Deaths;
            state.QuestSearchRadiusIndex = 0;
            state.LastObjectiveNotFoundReason = classification == QuestClassification::ChainQuest ? "chain_step_accepted" : "";
            RecordQuestEvent(state, bot, "quest_accepted", candidateQuestId, nullptr, "ok", raw.c_str(), semantic.c_str(), Cohort().Metrics.QuestsAccepted);
            if (classification == QuestClassification::ChainQuest)
                RecordQuestEvent(state, bot, "chain_step_accepted", candidateQuestId, nullptr, "ok", raw.c_str(), semantic.c_str(), Cohort().Metrics.QuestsAccepted);
            QuestObjectivePlan acceptedObjective;
            if (FindQuestObjective(bot, candidateQuestId, acceptedObjective))
            {
                SetQuestWorkFromPlan(state, acceptedObjective);
                state.QuestWork.SelectedGiverGuid = object->GetGUID();
                SetQuestWorkPhase(state, "choose_objective");
                RecordQuestEvent(state, bot, "quest_work_started", candidateQuestId, nullptr, ToString(acceptedObjective.ObjectiveType), raw.c_str(), semantic.c_str(), acceptedObjective.CurrentCount, acceptedObjective.ItemId);
            }
        }
    }

    if (acceptedCount)
    {
        result.Handled = true;
        result.Situation = "quest_hub_sweep";
        result.Action = "accept_hub_quests";
        result.QuestId = lastAcceptedQuestId;
        QuestObjectivePlan acceptedObjective;
        if (FindQuestObjective(bot, lastAcceptedQuestId, acceptedObjective))
        {
            QuestRoutePoint route;
            if (ResolveObjectiveRoutePoint(bot, acceptedObjective, route) && route.Valid && route.MapId == bot->GetMapId())
            {
                state.QuestRouteDestination.Valid = true;
                state.QuestRouteDestination.MapId = route.MapId;
                state.QuestRouteDestination.X = route.X;
                state.QuestRouteDestination.Y = route.Y;
                state.QuestRouteDestination.Z = route.Z;
                state.QuestRouteDestination.QuestId = route.QuestId;
                state.QuestRouteDestination.Reason = route.Source;
                MoveBotToPoint(state, bot, route.X, route.Y, route.Z);
                SetQuestWorkPhase(state, acceptedObjective.IsItemObjective ? "search_collect_mob" : "search_objective");
            }
            else
                MoveToObjectiveSearchPoint(state, bot, &acceptedObjective);
        }
        std::ostringstream context;
        context << "{\"accepted_count\":" << acceptedCount << "}";
        RecordQuestEvent(state, bot, "quest_hub_sweep", lastAcceptedQuestId, nullptr, "accepted", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_hub_sweep", &power, stage, activity).c_str(), acceptedCount, 0, context.str().c_str());
        return result;
    }
    if (result.Handled)
        return result;

    QuestPortfolioPlan portfolio = BuildQuestPortfolioPlan(bot, state);
    QuestObjectiveBucket bucket;
    if (SelectQuestObjectiveBucket(bot, portfolio, bucket) && !bucket.Objectives.empty())
    {
        state.ActiveQuestClusterId = bucket.BucketId;
        state.LastQuestBucketReason = bucket.Reason;
        state.QuestRouteDestination.Valid = true;
        state.QuestRouteDestination.MapId = bucket.MapId;
        state.QuestRouteDestination.X = bucket.CenterX;
        state.QuestRouteDestination.Y = bucket.CenterY;
        state.QuestRouteDestination.Z = bucket.CenterZ;
        state.QuestRouteDestination.QuestId = bucket.Objectives.front().QuestId;
        state.QuestRouteDestination.Reason = "objective_bucket";
        state.QuestSearchRadiusIndex = 0;
        if (!hasCommittedPlan && !hasAcceptedPlan)
        {
            discoveredPlan = bucket.Objectives.front();
            hasActiveObjective = true;
        }
        std::ostringstream context;
        context << "{\"bucket_id\":" << bucket.BucketId
                << ",\"objective_count\":" << bucket.Objectives.size()
                << ",\"center\":{\"map\":" << bucket.MapId << ",\"x\":" << bucket.CenterX << ",\"y\":" << bucket.CenterY << ",\"z\":" << bucket.CenterZ << "}"
                << ",\"reason\":\"" << JsonEscape(bucket.Reason) << "\"}";
        RecordQuestEvent(state, bot, "quest_bucket_selected", bucket.Objectives.front().QuestId, nullptr, "ok", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_bucket_selected", &power, stage, activity).c_str(), uint32(bucket.Objectives.size()), 0, context.str().c_str());
        RecordQuestEvent(state, bot, "objective_area_selected", bucket.Objectives.front().QuestId, nullptr, "ok", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "objective_area_selected", &power, stage, activity).c_str(), bucket.BucketId, 0, context.str().c_str());
    }
    else
    {
        state.ActiveQuestClusterId = 0;
        state.LastQuestBucketReason = portfolio.ActiveQuestCount ? "active_quests_unresolved" : "no_active_quests";
    }

    QuestObjectivePlan plan = discoveredPlan;
    if (hasActiveObjective)
    {
        result.Handled = true;
        result.Situation = "quest_objective";
        result.QuestId = plan.QuestId;
        SetQuestWorkFromPlan(state, plan);
        if (state.QuestWork.Phase == "idle" || state.QuestWork.Phase == "choose_quest")
            SetQuestWorkPhase(state, "choose_objective");

        if (plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.ObjectiveType == QuestObjectiveType::CastSpellOnTarget)
        {
            result.Situation = "quest_ability_objective";
            result.Action = plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy ? "use_ability_on_dummy" : "cast_spell_on_target";
            SetQuestWorkPhase(state, "cast_spell_on_target");
            Unit* abilityTarget = SelectQuestAbilityObjectiveTarget(bot, plan, state);
            result.Target = abilityTarget;
            state.CurrentTargetIsTrainingDummy = IsTrainingDummy(abilityTarget);
            state.CurrentDummyAllowedByQuest = IsTrainingDummyAllowedForQuest(plan, abilityTarget);
            state.LastQuestProgressBefore = QuestObjectiveProgress(bot, plan);

            if (!abilityTarget)
            {
                MoveToObjectiveSearchPoint(state, bot, &plan);
                result.Action = "search_ability_target";
                SetQuestWorkPhase(state, "search_objective");
                RecordQuestEvent(state, bot, "objective_search", plan.QuestId, nullptr, "ability_target_not_found", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity).c_str(), plan.CurrentCount, plan.ItemId);
                return result;
            }
            state.QuestWork.SelectedTargetGuid = abilityTarget->GetGUID();

            uint32 spellId = plan.RequiredSpellId ? plan.RequiredSpellId : SelectQuestAbilitySpell(bot, sObjectMgr->GetQuestTemplate(plan.QuestId), plan);
            state.RequiredSpellId = spellId;
            if (!spellId)
            {
                result.Failure = true;
                state.LastRejectedTargetReason = "ability_spell_unavailable";
                std::string raw = BuildRawJson(bot, abilityTarget);
                std::string semantic = BuildSemanticJson(bot, abilityTarget, "quest_ability_objective_failed", &power, stage, activity);
                RecordQuestEvent(state, bot, "ability_objective_failed", plan.QuestId, abilityTarget, "spell_unavailable", raw.c_str(), semantic.c_str(), state.LastQuestProgressBefore);
                return result;
            }

            SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spellId);
            float maxRange = spellInfo ? std::max(5.0f, spellInfo->GetMaxRange(false)) : 5.0f;
            if (!bot->IsWithinDistInMap(abilityTarget, maxRange))
            {
                MoveBotToPoint(state, bot, abilityTarget->GetPositionX(), abilityTarget->GetPositionY(), abilityTarget->GetPositionZ());
                SetQuestWorkPhase(state, "move_to_target");
                return result;
            }

            bot->SetFacingToObject(abilityTarget);
            bool cast = TryCastCombatSpell(bot, abilityTarget, spellId);
            uint32 before = state.LastQuestProgressBefore;

            std::ostringstream key;
            key << plan.QuestId << ":" << spellId << ":" << abilityTarget->GetGUID().GetCounter();
            std::string raw = BuildRawJson(bot, abilityTarget);
            std::string semantic = BuildSemanticJson(bot, abilityTarget, "quest_ability_objective", &power, stage, activity);
            if (cast)
            {
                RecordEvent(state, bot, "spell_cast", abilityTarget, "quest_ability_objective", raw.c_str(), semantic.c_str(), 0.0f, before, spellId);
                state.QuestWork.ProgressBefore = before;
                state.LastQuestProgressAfter = QuestObjectiveProgress(bot, plan);
                state.QuestWork.RequiredSpell = spellId;
                state.QuestWork.VerifyAfterMs = NowMs() + urand(500, 1500);
                SetQuestWorkPhase(state, "verify_progress");
            }
            return result;
        }

        WorldObject* questObject = SelectQuestGameObject(bot, plan);
        if (plan.IsGameObject || questObject)
        {
            result.Action = plan.IsItemObjective ? "loot_quest_object" : "use_quest_object";
            SetQuestWorkPhase(state, plan.IsItemObjective ? "use_gameobject" : "use_gameobject");
            if (!questObject)
            {
                QuestRoutePoint route;
                if (ResolveObjectiveRoutePoint(bot, plan, route) && route.Valid && route.MapId == bot->GetMapId())
                {
                    float routeDistance = Distance2d(bot->GetPositionX(), bot->GetPositionY(), route.X, route.Y);
                    state.QuestRouteDestination.Valid = true;
                    state.QuestRouteDestination.MapId = route.MapId;
                    state.QuestRouteDestination.X = route.X;
                    state.QuestRouteDestination.Y = route.Y;
                    state.QuestRouteDestination.Z = route.Z;
                    state.QuestRouteDestination.QuestId = route.QuestId;
                    state.QuestRouteDestination.Reason = route.Source;
                    if (routeDistance > INTERACTION_DISTANCE)
                    {
                        result.Action = plan.IsItemObjective ? "search_loot_quest_object" : "search_quest_object";
                        MoveBotToPoint(state, bot, route.X, route.Y, route.Z);
                        SetQuestWorkPhase(state, "search_objective");
                        std::ostringstream context;
                        context << "{\"destination\":{\"map\":" << route.MapId
                                << ",\"x\":" << route.X << ",\"y\":" << route.Y << ",\"z\":" << route.Z << "}"
                                << ",\"source\":\"" << JsonEscape(route.Source) << "\""
                                << ",\"distance\":" << routeDistance << "}";
                        RecordQuestEvent(state, bot, "objective_search", plan.QuestId, nullptr, "object_not_visible_travel_to_spawn", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity).c_str(), plan.CurrentCount, plan.ItemId, context.str().c_str());
                        return result;
                    }
                }

                result.Failure = true;
                std::string raw = BuildRawJson(bot, nullptr);
                std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective_failed", &power, stage, activity);
                RecordQuestEvent(state, bot, "objective_failed", plan.QuestId, nullptr, "object_not_found", raw.c_str(), semantic.c_str(), plan.CurrentCount);
                RecordQuestReplay(state, bot, "quest_failure", plan.QuestId, raw.c_str(), semantic.c_str(), "{\"action\":\"use_quest_object\"}", "{\"reason\":\"object_not_found\"}");
                return result;
            }

            if (!bot->IsWithinDistInMap(questObject, INTERACTION_DISTANCE))
            {
                MoveBotToPoint(state, bot, questObject->GetPositionX(), questObject->GetPositionY(), questObject->GetPositionZ());
                SetQuestWorkPhase(state, "move_to_target");
                return result;
            }

            uint32 before = QuestObjectiveProgress(bot, plan);
            state.QuestWork.SelectedObjectGuid = questObject->GetGUID();
            if (GameObject* go = questObject->ToGameObject())
            {
                if (WorldSession* session = bot->GetSession())
                {
                    WorldPacket useRequest(CMSG_GAMEOBJ_USE, 8);
                    useRequest << go->GetGUID();
                    session->HandleGameObjectUseOpcode(useRequest);
                }
            }
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective", &power, stage, activity);
            VerifyQuestObjectiveProgress(state, bot, plan, nullptr, before, plan.IsItemObjective ? "loot_object" : "use_object", raw.c_str(), semantic.c_str());
            return result;
        }

        Unit* objectiveTarget = nullptr;
        if (!state.QuestWork.SelectedTargetGuid.IsEmpty())
        {
            ObjectGuid selectedTargetGuid = state.QuestWork.SelectedTargetGuid;
            Unit* selectedTarget = ObjectAccessor::GetUnit(*bot, state.QuestWork.SelectedTargetGuid);
            Creature const* selectedCreature = selectedTarget ? selectedTarget->ToCreature() : nullptr;
            bool selectedMatchesPlan = selectedTarget && selectedTarget->IsAlive() && bot->IsValidAttackTarget(selectedTarget) && bot->IsWithinLOSInMap(selectedTarget);
            if (selectedMatchesPlan && plan.RequiredEntry > 0)
                selectedMatchesPlan = selectedCreature && selectedCreature->GetEntry() == uint32(plan.RequiredEntry);
            else if (selectedMatchesPlan && (plan.IsItemObjective || plan.ItemId))
                selectedMatchesPlan = IsQuestRelevantTarget(bot, selectedTarget);

            std::ostringstream cooldownKey;
            cooldownKey << plan.QuestId << ":" << plan.ObjectiveIndex << ":" << ToString(plan.ObjectiveType) << ":" << state.QuestWork.SelectedTargetGuid.GetCounter();
            auto cooldown = state.NoProgressCooldownUntilMs.find(cooldownKey.str());
            if (cooldown != state.NoProgressCooldownUntilMs.end() && cooldown->second > NowMs())
                selectedMatchesPlan = false;

            if (selectedMatchesPlan)
                objectiveTarget = selectedTarget;
            else
            {
                if (state.WasInCombat || state.QuestWork.Phase == "kill_objective_mob" || state.QuestWork.Phase == "move_to_target")
                {
                    uint32 before = state.QuestWork.ProgressBefore ? state.QuestWork.ProgressBefore : state.LastQuestProgressBefore;
                    std::string raw = BuildRawJson(bot, selectedTarget);
                    std::string semantic = BuildSemanticJson(bot, selectedTarget, "quest_objective_target_lost", &power, stage, activity);
                    bool progressed = VerifyQuestObjectiveProgress(state, bot, plan, selectedTarget, before, "engaged_target_lost", raw.c_str(), semantic.c_str());
                    if (!progressed)
                    {
                        std::ostringstream lostKey;
                        lostKey << plan.QuestId << ":" << plan.ObjectiveIndex << ":" << ToString(plan.ObjectiveType) << ":" << selectedTargetGuid.GetCounter();
                        state.NoProgressCooldownUntilMs[lostKey.str()] = NowMs() + 45000;
                        state.LastNoProgressReason = "engaged_target_lost";

                        std::ostringstream context;
                        context << "{\"quest_id\":" << plan.QuestId
                                << ",\"objective_index\":" << plan.ObjectiveIndex
                                << ",\"objective_type\":\"" << JsonEscape(ToString(plan.ObjectiveType)) << "\""
                                << ",\"selected_target_guid\":" << selectedTargetGuid.GetCounter()
                                << ",\"target_available\":" << (selectedTarget ? "true" : "false")
                                << ",\"was_in_combat\":" << (state.WasInCombat ? "true" : "false")
                                << ",\"phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\"}";
                        RecordQuestEvent(state, bot, "objective_target_lost", plan.QuestId, selectedTarget, "engaged_target_lost", raw.c_str(), semantic.c_str(), state.QuestWork.ProgressAfter, plan.ItemId, context.str().c_str());
                    }
                    state.TargetGuid.Clear();
                    state.WasInCombat = false;
                    SetQuestWorkPhase(state, "search_objective");
                }
                state.QuestWork.SelectedTargetGuid.Clear();
            }
        }

        if (!objectiveTarget)
            objectiveTarget = SelectQuestObjectiveTarget(bot, plan);
        result.Target = objectiveTarget;
        result.Action = plan.IsItemObjective ? "collect_quest_item" : "kill_quest_mob";
        if (!objectiveTarget)
        {
            QuestRoutePoint route;
            if (ResolveObjectiveRoutePoint(bot, plan, route) && route.Valid && route.MapId == bot->GetMapId())
            {
                float routeDistance = Distance2d(bot->GetPositionX(), bot->GetPositionY(), route.X, route.Y);
                state.QuestRouteDestination.Valid = true;
                state.QuestRouteDestination.MapId = route.MapId;
                state.QuestRouteDestination.X = route.X;
                state.QuestRouteDestination.Y = route.Y;
                state.QuestRouteDestination.Z = route.Z;
                state.QuestRouteDestination.QuestId = route.QuestId;
                state.QuestRouteDestination.Reason = route.Source;
                if (routeDistance > 35.0f)
                {
                    result.Action = plan.IsItemObjective ? "search_collect_mob" : "search_quest_mob";
                    MoveBotToPoint(state, bot, route.X, route.Y, route.Z);
                    SetQuestWorkPhase(state, plan.IsItemObjective ? "search_collect_mob" : "search_objective");
                    std::ostringstream context;
                    context << "{\"destination\":{\"map\":" << route.MapId
                            << ",\"x\":" << route.X << ",\"y\":" << route.Y << ",\"z\":" << route.Z << "}"
                            << ",\"source\":\"" << JsonEscape(route.Source) << "\""
                            << ",\"distance\":" << routeDistance << "}";
                    RecordQuestEvent(state, bot, "objective_search", plan.QuestId, nullptr, "target_not_visible_travel_to_spawn", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity).c_str(), plan.CurrentCount, plan.ItemId, context.str().c_str());
                    return result;
                }
            }

            MoveToObjectiveSearchPoint(state, bot, &plan);
            result.Action = plan.IsItemObjective ? "search_collect_mob" : "search_quest_mob";
            SetQuestWorkPhase(state, plan.IsItemObjective ? "search_collect_mob" : "search_objective");
            std::string raw = BuildRawJson(bot, nullptr);
            std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity);
            RecordQuestEvent(state, bot, plan.RequiredEntry || plan.ItemId ? "objective_search" : "objective_unresolved", plan.QuestId, nullptr, plan.RequiredEntry || plan.ItemId ? "target_not_found" : "metadata_incomplete", raw.c_str(), semantic.c_str(), plan.CurrentCount, plan.ItemId);
            return result;
        }

        state.QuestWork.SelectedTargetGuid = objectiveTarget->GetGUID();
        state.TargetGuid = objectiveTarget->GetGUID();
        state.LastQuestProgressBefore = QuestObjectiveProgress(bot, plan);
        SetQuestWorkPhase(state, "kill_objective_mob");
        uint32 spellId = SelectCombatSpell(bot, objectiveTarget);
        float engageRange = 5.0f;
        if (SpellInfo const* spellInfo = spellId ? sSpellMgr->GetSpellInfo(spellId) : nullptr)
            engageRange = std::max(5.0f, spellInfo->GetMaxRange(false));
        else
        {
            std::string role = GetDungeonRole(bot);
            BotClassSpecActionProfile profile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
            for (BotActionProfileSpell const& spell : profile.Spells)
            {
                if (!spell.SpellId || !bot->HasSpell(spell.SpellId))
                    continue;
                SpellInfo const* spellInfo = sSpellMgr->GetSpellInfo(spell.SpellId);
                if (!spellInfo || spell.DamageWeight <= 0.0f)
                    continue;
                engageRange = std::max(5.0f, spellInfo->GetMaxRange(false));
                break;
            }
        }

        if (!bot->IsWithinDistInMap(objectiveTarget, std::max(5.0f, engageRange - 1.0f)))
        {
            MoveBotToPoint(state, bot, objectiveTarget->GetPositionX(), objectiveTarget->GetPositionY(), objectiveTarget->GetPositionZ());
            result.Action = "move_to_quest_mob";
            SetQuestWorkPhase(state, "move_to_target");
            return result;
        }

        BotClassSpecActionProfile const combatProfile =
            BotClassSpecActionProfileStore::Build(bot, GetDungeonRole(bot));
        bool actionSubmitted = false;
        if (combatProfile.AutoAttackMode == "melee")
            actionSubmitted = SubmitMeleeAutoAttackIntent(state,
                BotMeleeAutoAttack::Kind::StartOrSwitch,
                objectiveTarget->GetGUID(),
                BotMeleeAutoAttack::Owner::Profile,
                BotActionArbitration::Priority::TrainedDamage,
                "quest_melee_engagement");
        if (spellId)
            actionSubmitted = TryCastCombatSpell(bot, objectiveTarget, spellId)
                || actionSubmitted;
        BotActionResult pull = actionSubmitted
            ? BotActionResult::Ok : BotActionResult::NoAction;
        if (pull != BotActionResult::Ok)
        {
            result.Failure = true;
            std::string raw = BuildRawJson(bot, objectiveTarget);
            std::string semantic = BuildSemanticJson(bot, objectiveTarget, "quest_objective_failed", &power, stage, activity);
            RecordQuestEvent(state, bot, "objective_failed", plan.QuestId, objectiveTarget, ToString(pull), raw.c_str(), semantic.c_str(), plan.CurrentCount);
            RecordQuestReplay(state, bot, "quest_failure", plan.QuestId, raw.c_str(), semantic.c_str(), "{\"action\":\"pull_quest_target\"}", "{\"reason\":\"pull_failed\"}");
        }
        return result;
    }

    if (!hasActiveObjective && state.LastObjectiveNotFoundReason != "chain_step_accepted" && (state.RecentlyAcceptedQuestUntilMs > NowMs() || state.ObjectiveSearchUntilMs > NowMs()))
    {
        result.Handled = true;
        result.Situation = "quest_objective_search";
        result.Action = state.LastObjectiveNotFoundReason == "unsupported_after_accept" ? "leave_unsupported_quest_giver" : "search_objective";
        result.QuestId = state.NewlyAcceptedQuestId;
        SetQuestWorkPhase(state, "search_objective");
        MoveToObjectiveSearchPoint(state, bot, nullptr);

        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_objective_search", &power, stage, activity);
        RecordQuestEvent(state, bot, "objective_search", state.NewlyAcceptedQuestId, nullptr,
            state.LastObjectiveNotFoundReason.empty() ? "recently_accepted_waiting_for_objective" : state.LastObjectiveNotFoundReason.c_str(),
            raw.c_str(), semantic.c_str());
        return result;
    }

    WorldObject* giver = !hasActiveObjective ? SelectQuestGiver(bot, false, &questId, &state) : nullptr;
    if (giver)
    {
        Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
        if (!quest)
            return result;

        result.Handled = true;
        result.Situation = "quest_pickup";
        result.Action = "move_to_quest_giver";
        result.QuestId = questId;
        if (!bot->IsWithinDistInMap(giver, INTERACTION_DISTANCE))
        {
            MoveBotToPoint(state, bot, giver->GetPositionX(), giver->GetPositionY(), giver->GetPositionZ());
            return result;
        }

        std::ostringstream attemptKey;
        attemptKey << giver->GetGUID().GetCounter() << ":" << questId;
        ++state.QuestPickupAttemptCount[attemptKey.str()];

        SubmitNativeQuestAccept(bot, giver, questId);
        std::string raw = BuildRawJson(bot, nullptr);
        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_accepted", &power, stage, activity);
        RecordQuestEvent(state, bot, "quest_seen", questId, nullptr, "ok", raw.c_str(), semantic.c_str());

        QuestStatus status = bot->GetQuestStatus(questId);
        auto questItr = bot->getQuestStatusMap().find(questId);
        bool accepted = questItr != bot->getQuestStatusMap().end() && (status == QUEST_STATUS_INCOMPLETE || status == QUEST_STATUS_COMPLETE);
        uint64 cooldownMs = NowMs() + urand(15000, 30000);
        state.QuestGiverCooldownUntilMs[giver->GetGUID().GetCounter()] = cooldownMs;
        if (!accepted)
        {
            state.QuestCooldownUntilMs[questId] = NowMs() + 60000;
            state.LastObjectiveNotFoundReason = "quest_log_entry_missing";
            state.QuestWork.FailedReason = "quest_accept_failed";
            result.Failure = true;
            RecordQuestEvent(state, bot, "quest_accept_failed", questId, nullptr, "quest_log_entry_missing", raw.c_str(), semantic.c_str());
            MoveToObjectiveSearchPoint(state, bot, nullptr, giver);
            result.Action = "leave_quest_giver";
            return result;
        }

        ++Cohort().Metrics.QuestsAccepted;
        state.LastQuestId = questId;
        state.NewlyAcceptedQuestId = questId;
        state.RecentlyAcceptedQuestUntilMs = NowMs() + 30000;
        state.QuestStartTime = Cohort().ElapsedMs / 1000;
        state.QuestStartDeaths = Cohort().Metrics.Deaths;
        RecordQuestEvent(state, bot, "quest_accepted", questId, nullptr, "ok", raw.c_str(), semantic.c_str(), Cohort().Metrics.QuestsAccepted);
        result.Action = "accept_quest";

        QuestObjectivePlan acceptedObjective;
        QuestClassification acceptedClassification = ClassifyQuestForBot(bot, quest);
        state.LastQuestClassification = ToString(acceptedClassification);
        if (FindQuestObjective(bot, questId, acceptedObjective))
        {
            SetQuestWorkFromPlan(state, acceptedObjective);
            state.QuestWork.SelectedGiverGuid = giver->GetGUID();
            SetQuestWorkPhase(state, "choose_objective");
            state.LastObjectiveNotFoundReason.clear();
            RecordQuestEvent(state, bot, "quest_work_started", questId, nullptr, ToString(acceptedObjective.ObjectiveType), raw.c_str(), semantic.c_str(), acceptedObjective.CurrentCount, acceptedObjective.ItemId);
            MoveToObjectiveSearchPoint(state, bot, &acceptedObjective, giver);
            result.Action = "choose_objective";
        }
        else if (acceptedClassification == QuestClassification::ChainQuest)
        {
            state.LastObjectiveNotFoundReason = "chain_step_accepted";
            state.QuestWork.FailedReason.clear();
            RecordQuestEvent(state, bot, "chain_step_accepted", questId, nullptr, "ok", raw.c_str(), semantic.c_str());
            result.Action = "accept_chain_step";
        }
        else
        {
            state.QuestCooldownUntilMs[questId] = NowMs() + 120000;
            state.LastObjectiveNotFoundReason = "unsupported_after_accept";
            state.QuestWork.FailedReason = "unsupported_after_accept";
            RecordQuestEvent(state, bot, "quest_unsupported_after_accept", questId, nullptr, "no_supported_objective", raw.c_str(), semantic.c_str());
            MoveToObjectiveSearchPoint(state, bot, nullptr, giver);
            result.Action = "leave_unsupported_quest_giver";
        }
        return result;
    }

    if (!hasActiveObjective)
    {
        QuestRoutePoint pickup;
        if (FindQuestPickupDestination(bot, state, pickup))
        {
            result.Handled = true;
            result.Situation = "quest_pickup_search";
            result.Action = "travel_to_quest_hub";
            result.QuestId = pickup.QuestId;
            state.QuestSearchDestination.Valid = true;
            state.QuestSearchDestination.MapId = pickup.MapId;
            state.QuestSearchDestination.X = pickup.X;
            state.QuestSearchDestination.Y = pickup.Y;
            state.QuestSearchDestination.Z = pickup.Z;
            state.QuestSearchDestination.QuestId = pickup.QuestId;
            state.QuestSearchDestination.Reason = pickup.Source;
            state.LastNoQuestReason = "traveling_to_pickup_search_candidate";
            float pickupDistance = pickup.MapId == bot->GetMapId() ? Distance2d(bot->GetPositionX(), bot->GetPositionY(), pickup.X, pickup.Y) : 100000.0f;
            if (pickupDistance <= INTERACTION_DISTANCE)
            {
                Quest const* quest = sObjectMgr->GetQuestTemplate(pickup.QuestId);
                if (quest && bot->CanTakeQuest(quest, false) && bot->CanAddQuest(quest, false))
                {
                    QuestClassification classification = ClassifyQuestForBot(bot, quest);
                    state.LastQuestClassification = ToString(classification);
                    if (classification != QuestClassification::UnsupportedQuest)
                    {
                        std::string raw = BuildRawJson(bot, nullptr);
                        std::string semantic = BuildSemanticJson(bot, nullptr, "quest_pickup_db_fallback", &power, stage, activity);
                        RecordQuestEvent(state, bot, "quest_seen", pickup.QuestId, nullptr, pickup.Source.c_str(), raw.c_str(), semantic.c_str());
                        // Wait for SelectQuestGiver to see the real object; a DB
                        // coordinate is not an authority to accept against a
                        // null questgiver.
                        state.LastNoQuestReason = "db_queststarter_reached_without_visible_giver";
                        result.Action = "await_visible_quest_giver";
                        return result;
                    }
                }
            }
            MoveBotToPoint(state, bot, pickup.X, pickup.Y, pickup.Z);
            std::ostringstream context;
            context << "{\"radius_index\":" << state.QuestSearchRadiusIndex
                    << ",\"quest_id\":" << pickup.QuestId
                    << ",\"destination\":{\"map\":" << pickup.MapId << ",\"x\":" << pickup.X << ",\"y\":" << pickup.Y << ",\"z\":" << pickup.Z << "}"
                    << ",\"source\":\"" << JsonEscape(pickup.Source) << "\"}";
            RecordQuestEvent(state, bot, "quest_pickup_search", pickup.QuestId, nullptr, "travel", BuildRawJson(bot, nullptr).c_str(), BuildSemanticJson(bot, nullptr, "quest_pickup_search", &power, stage, activity).c_str(), state.QuestSearchRadiusIndex, 0, context.str().c_str());
            return result;
        }

        static uint32 constexpr MaxQuestSearchRadiusIndex = 4;
        if (state.QuestSearchRadiusIndex < MaxQuestSearchRadiusIndex)
            ++state.QuestSearchRadiusIndex;
        state.LastNoQuestReason = "no_pickup_search_candidate";
    }

    return result;
}

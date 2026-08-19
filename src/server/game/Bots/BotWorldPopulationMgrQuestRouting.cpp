#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotWorldPopulationMgrNativeHelpers.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "Entities/Item/ItemTemplate.h"
#include "GameObject.h"
#include "GameTime.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
#include "Random.h"
#include "Unit.h"
#include "Util.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <iterator>
#include <limits>
#include <sstream>
#include <unordered_set>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

using BotWorldPopulationMgrNativeHelpers::Distance2d;

bool BotWorldPopulationMgr::ResolveObjectiveRoutePoint(Player* bot, QuestObjectivePlan const& plan, QuestRoutePoint& point) const
{
    point = QuestRoutePoint();
    if (!bot || !plan.QuestId)
        return false;

    point.QuestId = plan.QuestId;
    point.ObjectiveIndex = plan.ObjectiveIndex;

    if (Unit* target = (plan.ObjectiveType == QuestObjectiveType::UseAbilityOnDummy || plan.ObjectiveType == QuestObjectiveType::CastSpellOnTarget)
        ? SelectQuestAbilityObjectiveTarget(bot, plan, WorldBotState())
        : SelectQuestObjectiveTarget(bot, plan))
    {
        point.Valid = true;
        point.MapId = target->GetMapId();
        point.ZoneId = target->GetZoneId();
        point.X = target->GetPositionX();
        point.Y = target->GetPositionY();
        point.Z = target->GetPositionZ();
        point.Source = "visible_target";
        return true;
    }

    if (WorldObject* object = SelectQuestGameObject(bot, plan))
    {
        point.Valid = true;
        point.MapId = object->GetMapId();
        point.ZoneId = object->GetZoneId();
        point.X = object->GetPositionX();
        point.Y = object->GetPositionY();
        point.Z = object->GetPositionZ();
        point.Source = "visible_object";
        return true;
    }

    if (plan.RequiredEntry > 0)
    {
        CreatureData const* best = nullptr;
        float bestDist = 0.0f;
        for (auto const& pair : sObjectMgr->GetAllCreatureData())
        {
            CreatureData const& data = pair.second;
            if (data.id != uint32(plan.RequiredEntry) || data.mapId != bot->GetMapId())
                continue;
            float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), data.spawnPoint.GetPositionX(), data.spawnPoint.GetPositionY());
            if (!best || dist < bestDist)
            {
                best = &data;
                bestDist = dist;
            }
        }
        if (best)
        {
            point.Valid = true;
            point.MapId = best->mapId;
            point.ZoneId = bot->GetZoneId();
            point.X = best->spawnPoint.GetPositionX();
            point.Y = best->spawnPoint.GetPositionY();
            point.Z = best->spawnPoint.GetPositionZ();
            point.Source = "creature_spawn";
            return true;
        }
    }
    else if (plan.RequiredEntry < 0)
    {
        GameObjectData const* best = nullptr;
        float bestDist = 0.0f;
        uint32 entry = uint32(-plan.RequiredEntry);
        for (auto const& pair : sObjectMgr->GetAllGameObjectData())
        {
            GameObjectData const& data = pair.second;
            if (data.id != entry || data.mapId != bot->GetMapId())
                continue;
            float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), data.spawnPoint.GetPositionX(), data.spawnPoint.GetPositionY());
            if (!best || dist < bestDist)
            {
                best = &data;
                bestDist = dist;
            }
        }
        if (best)
        {
            point.Valid = true;
            point.MapId = best->mapId;
            point.ZoneId = bot->GetZoneId();
            point.X = best->spawnPoint.GetPositionX();
            point.Y = best->spawnPoint.GetPositionY();
            point.Z = best->spawnPoint.GetPositionZ();
            point.Source = "gameobject_spawn";
            return true;
        }
    }

    if (plan.ItemId)
    {
        std::unordered_set<uint32> creatureLootEntries;
        if (QueryResult result = WorldDatabase.PQuery("SELECT Entry FROM creature_loot_template WHERE Item = %u", plan.ItemId))
        {
            do
            {
                creatureLootEntries.insert(result->Fetch()[0].GetUInt32());
            } while (result->NextRow());
        }

        std::unordered_set<uint32> gameObjectLootEntries;
        if (QueryResult result = WorldDatabase.PQuery("SELECT Entry FROM gameobject_loot_template WHERE Item = %u", plan.ItemId))
        {
            do
            {
                gameObjectLootEntries.insert(result->Fetch()[0].GetUInt32());
            } while (result->NextRow());
        }

        CreatureData const* bestCreature = nullptr;
        GameObjectData const* bestGo = nullptr;
        bool bestCreatureFromLoot = false;
        bool bestGoFromLoot = false;
        float bestDist = 0.0f;
        for (auto const& pair : sObjectMgr->GetAllCreatureData())
        {
            CreatureData const& data = pair.second;
            if (data.mapId != bot->GetMapId())
                continue;
            bool itemSource = creatureLootEntries.find(data.id) != creatureLootEntries.end();
            if (std::vector<uint32> const* questItems = sObjectMgr->GetCreatureQuestItemList(data.id))
                itemSource = itemSource || std::find(questItems->begin(), questItems->end(), plan.ItemId) != questItems->end();
            if (!itemSource)
                continue;
            float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), data.spawnPoint.GetPositionX(), data.spawnPoint.GetPositionY());
            if (!bestCreature || dist < bestDist)
            {
                bestCreature = &data;
                bestGo = nullptr;
                bestCreatureFromLoot = creatureLootEntries.find(data.id) != creatureLootEntries.end();
                bestGoFromLoot = false;
                bestDist = dist;
            }
        }
        for (auto const& pair : sObjectMgr->GetAllGameObjectData())
        {
            GameObjectData const& data = pair.second;
            if (data.mapId != bot->GetMapId())
                continue;
            bool itemSource = gameObjectLootEntries.find(data.id) != gameObjectLootEntries.end();
            if (std::vector<uint32> const* questItems = sObjectMgr->GetGameObjectQuestItemList(data.id))
                itemSource = itemSource || std::find(questItems->begin(), questItems->end(), plan.ItemId) != questItems->end();
            if (!itemSource)
                continue;
            float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), data.spawnPoint.GetPositionX(), data.spawnPoint.GetPositionY());
            if (!bestCreature && (!bestGo || dist < bestDist))
            {
                bestGo = &data;
                bestGoFromLoot = gameObjectLootEntries.find(data.id) != gameObjectLootEntries.end();
                bestDist = dist;
            }
        }
        if (bestCreature || bestGo)
        {
            point.Valid = true;
            point.MapId = bestCreature ? bestCreature->mapId : bestGo->mapId;
            point.ZoneId = bot->GetZoneId();
            point.X = bestCreature ? bestCreature->spawnPoint.GetPositionX() : bestGo->spawnPoint.GetPositionX();
            point.Y = bestCreature ? bestCreature->spawnPoint.GetPositionY() : bestGo->spawnPoint.GetPositionY();
            point.Z = bestCreature ? bestCreature->spawnPoint.GetPositionZ() : bestGo->spawnPoint.GetPositionZ();
            point.Source = bestCreature ? (bestCreatureFromLoot ? "creature_loot_spawn" : "creature_item_spawn") : (bestGoFromLoot ? "gameobject_loot_spawn" : "gameobject_item_spawn");
            return true;
        }
    }

    if (QuestPOIData const* poi = sObjectMgr->GetQuestPOIData(plan.QuestId))
    {
        QuestPOIBlobData const* bestBlob = nullptr;
        for (QuestPOIBlobData const& blob : poi->Blobs)
        {
            if (blob.Points.empty())
                continue;
            if (blob.ObjectiveIndex >= 0 && uint32(blob.ObjectiveIndex) != plan.ObjectiveIndex)
                continue;
            if (!bestBlob || blob.Priority > bestBlob->Priority)
                bestBlob = &blob;
        }

        if (bestBlob)
        {
            float x = 0.0f;
            float y = 0.0f;
            for (QuestPOIBlobPoint const& p : bestBlob->Points)
            {
                x += float(p.X);
                y += float(p.Y);
            }
            x /= float(bestBlob->Points.size());
            y /= float(bestBlob->Points.size());

            point.Valid = true;
            point.MapId = bestBlob->MapID >= 0 ? uint32(bestBlob->MapID) : bot->GetMapId();
            point.ZoneId = bot->GetZoneId();
            point.X = x;
            point.Y = y;
            point.Z = bot->GetPositionZ();
            point.Source = "quest_poi";
            return true;
        }
    }

    QueryResult memory = CharacterDatabase.PQuery(
        "SELECT x, y, z FROM bot_memory_pois WHERE bot_guid = %u AND map_id = %u AND (quest_id = %u OR quest_id = 0) "
        "AND poi_type IN ('objective_target','objective_object') ORDER BY quest_id DESC, last_seen_at DESC, score DESC LIMIT 1",
        bot->GetGUID().GetCounter(), bot->GetMapId(), plan.QuestId);
    if (memory)
    {
        Field* fields = memory->Fetch();
        point.Valid = true;
        point.MapId = bot->GetMapId();
        point.ZoneId = bot->GetZoneId();
        point.X = fields[0].GetFloat();
        point.Y = fields[1].GetFloat();
        point.Z = fields[2].GetFloat();
        point.Source = "remembered_poi";
        return true;
    }

    return false;
}

BotWorldPopulationMgr::QuestPortfolioPlan BotWorldPopulationMgr::BuildQuestPortfolioPlan(Player* bot, WorldBotState const& /*state*/) const
{
    QuestPortfolioPlan plan;
    if (!bot)
        return plan;

    constexpr float ClusterRadius = 180.0f;
    uint32 nextBucketId = 1;
    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE)
            continue;

        ++plan.ActiveQuestCount;
        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest || ClassifyQuestForBot(bot, quest) == QuestClassification::UnsupportedQuest)
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        {
            if (!quest->RequiredNpcOrGo[i] || !quest->RequiredNpcOrGoCount[i] || questStatus.second.CreatureOrGOCount[i] >= quest->RequiredNpcOrGoCount[i])
                continue;
            QuestObjectivePlan objective;
            if (!GetQuestObjectivePlan(bot, quest->GetQuestId(), i, quest->RequiredNpcOrGo[i] < 0 ? QuestObjectiveType::InteractGameObject : QuestObjectiveType::Kill, objective))
                continue;

            QuestRoutePoint route;
            if (!ResolveObjectiveRoutePoint(bot, objective, route))
            {
                plan.UnresolvedObjectives.push_back(objective);
                continue;
            }

            QuestObjectiveBucket* bucket = nullptr;
            for (QuestObjectiveBucket& candidate : plan.Buckets)
            {
                if (candidate.MapId == route.MapId && Distance2d(candidate.CenterX, candidate.CenterY, route.X, route.Y) <= ClusterRadius)
                {
                    bucket = &candidate;
                    break;
                }
            }
            if (!bucket)
            {
                plan.Buckets.push_back(QuestObjectiveBucket());
                bucket = &plan.Buckets.back();
                bucket->BucketId = nextBucketId++;
                bucket->MapId = route.MapId;
                bucket->CenterX = route.X;
                bucket->CenterY = route.Y;
                bucket->CenterZ = route.Z;
            }
            bucket->Objectives.push_back(objective);
            float n = float(bucket->Objectives.size());
            bucket->CenterX = ((bucket->CenterX * (n - 1.0f)) + route.X) / n;
            bucket->CenterY = ((bucket->CenterY * (n - 1.0f)) + route.Y) / n;
            bucket->CenterZ = ((bucket->CenterZ * (n - 1.0f)) + route.Z) / n;
        }

        for (uint8 i = 0; i < QUEST_ITEM_OBJECTIVES_COUNT; ++i)
        {
            if (!quest->RequiredItemId[i] || !quest->RequiredItemCount[i] || questStatus.second.ItemCount[i] >= quest->RequiredItemCount[i])
                continue;
            QuestObjectivePlan objective;
            if (!GetQuestObjectivePlan(bot, quest->GetQuestId(), i, QuestObjectiveType::CollectItem, objective))
                continue;

            QuestRoutePoint route;
            if (!ResolveObjectiveRoutePoint(bot, objective, route))
            {
                plan.UnresolvedObjectives.push_back(objective);
                continue;
            }

            QuestObjectiveBucket* bucket = nullptr;
            for (QuestObjectiveBucket& candidate : plan.Buckets)
            {
                if (candidate.MapId == route.MapId && Distance2d(candidate.CenterX, candidate.CenterY, route.X, route.Y) <= ClusterRadius)
                {
                    bucket = &candidate;
                    break;
                }
            }
            if (!bucket)
            {
                plan.Buckets.push_back(QuestObjectiveBucket());
                bucket = &plan.Buckets.back();
                bucket->BucketId = nextBucketId++;
                bucket->MapId = route.MapId;
                bucket->CenterX = route.X;
                bucket->CenterY = route.Y;
                bucket->CenterZ = route.Z;
            }
            bucket->Objectives.push_back(objective);
        }
    }

    for (QuestObjectiveBucket& bucket : plan.Buckets)
    {
        float distancePenalty = bucket.MapId == bot->GetMapId() ? Distance2d(bot->GetPositionX(), bot->GetPositionY(), bucket.CenterX, bucket.CenterY) * 0.02f : 10000.0f;
        float progressValue = 0.0f;
        for (QuestObjectivePlan const& objective : bucket.Objectives)
            progressValue += objective.RequiredCount ? float(objective.CurrentCount) / float(objective.RequiredCount) : 0.0f;
        bucket.Score = float(bucket.Objectives.size()) * 100.0f + progressValue * 25.0f - distancePenalty;
        std::ostringstream reason;
        reason << "objectives=" << bucket.Objectives.size() << ",distance_penalty=" << distancePenalty << ",progress=" << progressValue;
        bucket.Reason = reason.str();
    }

    return plan;
}

bool BotWorldPopulationMgr::SelectQuestObjectiveBucket(Player* /*bot*/, QuestPortfolioPlan const& plan, QuestObjectiveBucket& bucket) const
{
    QuestObjectiveBucket const* best = nullptr;
    for (QuestObjectiveBucket const& candidate : plan.Buckets)
        if (!best || candidate.Score > best->Score)
            best = &candidate;
    if (!best)
        return false;
    bucket = *best;
    return true;
}

bool BotWorldPopulationMgr::FindQuestTurnInDestination(Player* bot, uint32 questId, QuestRoutePoint& point) const
{
    point = QuestRoutePoint();
    if (!bot || !questId)
        return false;

    QuestRoutePoint best;
    auto considerCreature = [&](uint32 entry)
    {
        for (auto const& pair : sObjectMgr->GetAllCreatureData())
        {
            CreatureData const& data = pair.second;
            if (data.id != entry || data.mapId != bot->GetMapId())
                continue;
            float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), data.spawnPoint.GetPositionX(), data.spawnPoint.GetPositionY());
            if (!best.Valid || dist < best.Score)
            {
                best.Valid = true;
                best.MapId = data.mapId;
                best.ZoneId = bot->GetZoneId();
                best.QuestId = questId;
                best.X = data.spawnPoint.GetPositionX();
                best.Y = data.spawnPoint.GetPositionY();
                best.Z = data.spawnPoint.GetPositionZ();
                best.Score = dist;
                best.Source = "creature_questender";
            }
        }
    };
    auto considerGameObject = [&](uint32 entry)
    {
        for (auto const& pair : sObjectMgr->GetAllGameObjectData())
        {
            GameObjectData const& data = pair.second;
            if (data.id != entry || data.mapId != bot->GetMapId())
                continue;
            float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), data.spawnPoint.GetPositionX(), data.spawnPoint.GetPositionY());
            if (!best.Valid || dist < best.Score)
            {
                best.Valid = true;
                best.MapId = data.mapId;
                best.ZoneId = bot->GetZoneId();
                best.QuestId = questId;
                best.X = data.spawnPoint.GetPositionX();
                best.Y = data.spawnPoint.GetPositionY();
                best.Z = data.spawnPoint.GetPositionZ();
                best.Score = dist;
                best.Source = "gameobject_questender";
            }
        }
    };

    for (uint32 entry : sObjectMgr->GetCreatureQuestInvolvedRelationsReverse(questId))
        considerCreature(entry);
    for (uint32 entry : sObjectMgr->GetGOQuestInvolvedRelationsReverse(questId))
        considerGameObject(entry);

    if (!best.Valid)
        return false;
    point = best;
    return true;
}

bool BotWorldPopulationMgr::FindQuestPickupDestination(Player* bot, WorldBotState const& state, QuestRoutePoint& point) const
{
    point = QuestRoutePoint();
    if (!bot)
        return false;

    static float constexpr Radii[] = { 100.0f, 250.0f, 500.0f, 900.0f, 1500.0f };
    uint32 radiusIndex = std::min<uint32>(state.QuestSearchRadiusIndex, uint32(std::size(Radii) - 1));
    float radius = Radii[radiusIndex];
    QuestRoutePoint best;

    auto consider = [&](uint32 questId, uint32 mapId, uint32 zoneId, float x, float y, float z, char const* source)
    {
        if (mapId != bot->GetMapId())
            return;
        float dist = Distance2d(bot->GetPositionX(), bot->GetPositionY(), x, y);
        if (dist > radius && (radiusIndex + 1 < std::size(Radii) || zoneId != bot->GetZoneId()))
            return;
        Quest const* quest = sObjectMgr->GetQuestTemplate(questId);
        if (!quest || !bot->CanTakeQuest(quest, false) || !bot->CanAddQuest(quest, false))
            return;
        QuestClassification classification = ClassifyQuestForBot(bot, quest);
        if (classification == QuestClassification::UnsupportedQuest)
            return;
        if (state.QuestCooldownUntilMs.find(questId) != state.QuestCooldownUntilMs.end() && state.QuestCooldownUntilMs.find(questId)->second > NowMs())
            return;

        float score = dist - (classification == QuestClassification::ChainQuest ? 25.0f : 50.0f);
        if (!best.Valid || score < best.Score)
        {
            best.Valid = true;
            best.MapId = mapId;
            best.ZoneId = zoneId;
            best.QuestId = questId;
            best.X = x;
            best.Y = y;
            best.Z = z;
            best.Score = score;
            best.Source = source;
        }
    };

    QueryResult creatures = WorldDatabase.PQuery(
        "SELECT qs.quest, c.map, c.zoneId, c.position_x, c.position_y, c.position_z "
        "FROM creature_queststarter qs JOIN creature c ON c.id = qs.id "
        "WHERE c.map = %u AND ((POW(c.position_x - %f, 2) + POW(c.position_y - %f, 2)) <= POW(%f, 2) OR c.zoneId = %u) "
        "LIMIT 200",
        bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), radius, bot->GetZoneId());
    if (creatures)
    {
        do
        {
            Field* f = creatures->Fetch();
            consider(f[0].GetUInt32(), f[1].GetUInt32(), f[2].GetUInt32(), f[3].GetFloat(), f[4].GetFloat(), f[5].GetFloat(), "creature_queststarter");
        } while (creatures->NextRow());
    }

    QueryResult gameObjects = WorldDatabase.PQuery(
        "SELECT qs.quest, g.map, g.zoneId, g.position_x, g.position_y, g.position_z "
        "FROM gameobject_queststarter qs JOIN gameobject g ON g.id = qs.id "
        "WHERE g.map = %u AND ((POW(g.position_x - %f, 2) + POW(g.position_y - %f, 2)) <= POW(%f, 2) OR g.zoneId = %u) "
        "LIMIT 200",
        bot->GetMapId(), bot->GetPositionX(), bot->GetPositionY(), radius, bot->GetZoneId());
    if (gameObjects)
    {
        do
        {
            Field* f = gameObjects->Fetch();
            consider(f[0].GetUInt32(), f[1].GetUInt32(), f[2].GetUInt32(), f[3].GetFloat(), f[4].GetFloat(), f[5].GetFloat(), "gameobject_queststarter");
        } while (gameObjects->NextRow());
    }

    if (!best.Valid)
        return false;
    point = best;
    return true;
}

bool BotWorldPopulationMgr::HasNearbySupportedQuestGiver(Player* bot, WorldBotState const& state) const
{
    uint32 questId = 0;
    return SelectQuestGiver(bot, false, &questId, &state) != nullptr;
}

bool BotWorldPopulationMgr::IsGenericGrindingAllowed(WorldBotState& state, Player* bot, BotProgressionActivity activity, bool hasActiveQuestObjective)
{
    state.LastGrindingAllowedReason.clear();
    if (!Cohort().Config.AllowCombat)
    {
        state.LastGrindingAllowedReason = "combat_disabled";
        return false;
    }
    if (!Cohort().Config.AllowGrinding)
    {
        state.LastGrindingAllowedReason = "grinding_disabled";
        return false;
    }
    if (hasActiveQuestObjective || state.QuestWork.ActiveQuestId)
    {
        state.LastGrindingAllowedReason = "active_quest_objective";
        return false;
    }
    if (state.RecentlyAcceptedQuestUntilMs > NowMs())
    {
        state.LastGrindingAllowedReason = "recently_accepted_quest";
        return false;
    }
    if (!state.QuestWork.SelectedTargetGuid.IsEmpty() || !state.QuestWork.SelectedObjectGuid.IsEmpty() || state.ObjectiveSearchUntilMs > NowMs())
    {
        state.LastGrindingAllowedReason = "known_objective_target";
        return false;
    }
    if (Cohort().Config.GrindOnlyWhenNoQuestAvailable && HasNearbySupportedQuestGiver(bot, state))
    {
        state.LastGrindingAllowedReason = "nearby_supported_quest";
        return false;
    }
    if (activity != BotProgressionActivity::Grinding && activity != BotProgressionActivity::ExperimentExploration)
    {
        state.LastGrindingAllowedReason = "activity_not_grinding";
        return false;
    }

    state.LastGrindingAllowedReason = activity == BotProgressionActivity::Grinding ? "explicit_grinding" : "experiment_exploration_combat_allowed";
    return true;
}

void BotWorldPopulationMgr::MoveToObjectiveSearchPoint(WorldBotState& state, Player* bot, QuestObjectivePlan const* plan, WorldObject const* avoidObject)
{
    if (!bot)
        return;

    uint64 now = NowMs();
    if (state.ObjectiveSearchUntilMs > now && Distance2d(bot->GetPositionX(), bot->GetPositionY(), state.ObjectiveSearchX, state.ObjectiveSearchY) > 3.0f)
    {
        MoveBotToPoint(state, bot, state.ObjectiveSearchX, state.ObjectiveSearchY, state.ObjectiveSearchZ);
        return;
    }

    if (plan && plan->QuestId)
    {
        QueryResult result = CharacterDatabase.PQuery(
            "SELECT x, y, z FROM bot_memory_pois "
            "WHERE bot_guid = %u AND map_id = %u AND zone_id = %u AND poi_type = 'objective_object' "
            "AND (quest_id = %u OR quest_id = 0) "
            "ORDER BY last_seen_at DESC, score DESC LIMIT 1",
            bot->GetGUID().GetCounter(), bot->GetMapId(), bot->GetZoneId(), plan->QuestId);
        if (result)
        {
            Field* fields = result->Fetch();
            state.ObjectiveSearchX = fields[0].GetFloat();
            state.ObjectiveSearchY = fields[1].GetFloat();
            state.ObjectiveSearchZ = fields[2].GetFloat();
            state.ObjectiveSearchUntilMs = now + urand(6000, 10000);
            MoveBotToPoint(state, bot, state.ObjectiveSearchX, state.ObjectiveSearchY, state.ObjectiveSearchZ);
            return;
        }
    }

    float baseAngle = avoidObject ? avoidObject->GetAngle(bot) : bot->GetOrientation();
    if (avoidObject && bot->IsWithinDistInMap(avoidObject, INTERACTION_DISTANCE + 3.0f))
        baseAngle = avoidObject->GetAngle(bot);
    else if (plan && plan->RequiredEntry)
        baseAngle += frand(-0.8f, 0.8f);
    else
        baseAngle = frand(0.0f, 2.0f * float(M_PI));

    float distance = avoidObject ? frand(12.0f, 22.0f) : frand(10.0f, 26.0f);
    Position pos = bot->GetFirstCollisionPosition(distance, baseAngle);
    state.ObjectiveSearchX = pos.GetPositionX();
    state.ObjectiveSearchY = pos.GetPositionY();
    state.ObjectiveSearchZ = pos.GetPositionZ();
    state.ObjectiveSearchUntilMs = now + urand(6000, 10000);
    MoveBotToPoint(state, bot, state.ObjectiveSearchX, state.ObjectiveSearchY, state.ObjectiveSearchZ);
}

uint32 BotWorldPopulationMgr::ChooseQuestReward(Player* bot, Quest const* quest, uint32* rewardItemId) const
{
    if (rewardItemId)
        *rewardItemId = 0;
    if (!bot || !quest || !quest->GetRewChoiceItemsCount())
        return 0;

    uint32 bestReward = 0;
    float bestScore = -1.0f;
    for (uint32 i = 0; i < quest->GetRewChoiceItemsCount(); ++i)
    {
        uint32 itemId = quest->RewardChoiceItemId[i];
        ItemTemplate const* proto = itemId ? sObjectMgr->GetItemTemplate(itemId) : nullptr;
        float score = BotLongTermProgressionBrain::ScoreItemForRole(bot, proto);
        if (score > bestScore)
        {
            bestReward = i;
            bestScore = score;
            if (rewardItemId)
                *rewardItemId = itemId;
        }
    }

    return bestReward;
}

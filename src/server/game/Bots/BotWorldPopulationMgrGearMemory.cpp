#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotDatasetEvent.h"
#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotLongTermProgressionBrain.h"
#include "Bots/BotTelemetryPolicy.h"
#include "Config.h"
#include "DatabaseEnv.h"
#include "Entities/Item/Item.h"
#include "Entities/Item/ItemTemplate.h"
#include "GameTime.h"
#include "MotionMaster.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <sstream>
#include <string>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

uint64 ReadLastInsertId()
{
    if (QueryResult result = CharacterDatabase.Query("SELECT LAST_INSERT_ID()"))
        return result->Fetch()[0].GetUInt64();

    return 0;
}

float Distance2d(float ax, float ay, float bx, float by)

{
    float dx = ax - bx;
    float dy = ay - by;
    return std::sqrt(dx * dx + dy * dy);
}

bool UsesRangedAoeCalibrationLane(std::string const& spec)
{

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
}

void BotWorldPopulationMgr::RecordActivityStart(WorldBotState& state, Player* bot)
{
    if (!Cohort().RunId || !bot)
        return;

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    BotProgressionStage stage = BotLongTermProgressionBrain::ClassifyStage(bot, power);
    std::vector<BotActivityScore> activityScores = Cohort().Config.EnableProgression
        ? BotLongTermProgressionBrain::ScoreActivities(bot, power, stage, Cohort().Config.AllowQuesting, Cohort().Config.AllowCombat, &Cohort().LearningConfig)
        : std::vector<BotActivityScore>(1, BotActivityScore());
    ApplyPolicyModelScores(activityScores, bot, power, stage);
    BotActivityScore chosenActivity = BotLongTermProgressionBrain::ChooseActivity(activityScores);
    state.ActivityStartPower = power.Total;
    state.ActivityStartGold = bot->GetMoney();
    state.ActivityStartDeaths = Cohort().Metrics.Deaths;
    state.ActivityType = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    state.ProgressionStage = BotLongTermProgressionBrain::ToString(stage);

    std::string config = BuildConfigJson();
    std::string brain = Cohort().Config.BrainVersion;
    std::string activity = state.ActivityType;
    CharacterDatabase.EscapeString(config);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(activity);
    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_activities (experiment_id, run_id, bot_guid, brain_version, activity_type, start_power_score, config_json) "
        "VALUES (" UI64FMTD ", " UI64FMTD ", %u, '%s', '%s', %f, '%s')",
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), activity.c_str(), state.ActivityStartPower, config.c_str());
    state.ActivityId = ReadLastInsertId();
}

void BotWorldPopulationMgr::RecordActivityStop(WorldBotState const& state, Player* bot)
{
    if (!Cohort().RunId || !state.ActivityId)
        return;

    BotRolePowerBreakdown power = BotLongTermProgressionBrain::CalculateRolePower(bot);
    float endPower = bot ? power.Total : state.ActivityStartPower;
    float powerDelta = endPower - state.ActivityStartPower;
    int64 goldDelta = bot ? int64(bot->GetMoney()) - int64(state.ActivityStartGold) : 0;
    uint32 deaths = Cohort().Metrics.Deaths >= state.ActivityStartDeaths ? Cohort().Metrics.Deaths - state.ActivityStartDeaths : 0;
    std::string summary = GetSummaryJson();
    CharacterDatabase.EscapeString(summary);
    CharacterDatabase.DirectPExecute("UPDATE experiment_bot_activities SET ended_at = NOW(), end_power_score = %f, power_delta = %f, gold_delta = " SI64FMTD ", completed = 1, deaths = %u, summary_json = '%s' WHERE id = " UI64FMTD,
        endPower, powerDelta, goldDelta, deaths, summary.c_str(), state.ActivityId);

    if (bot)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, nullptr, "area", bot->GetAreaId(), state.ActivityType.c_str());
        UpdateSemanticOutcomeStats(bot, "area", bot->GetAreaId(), "activity_completed", "ok", powerDelta, powerDelta, false, features.c_str());
        std::string activityFeatures = BuildEmbeddingFeaturesJson(bot, nullptr, "activity", BotExperienceLearningPolicy::StableKey(state.ActivityType), state.ActivityType.c_str());
        UpdateSemanticOutcomeStats(bot, "activity", BotExperienceLearningPolicy::StableKey(state.ActivityType), "activity_completed", "ok", powerDelta, powerDelta, deaths > 0, activityFeatures.c_str());
    }
}

void BotWorldPopulationMgr::RecordGearEvaluation(WorldBotState& state, Player* bot, BotGearUpgradeEvaluation const& evaluation, char const* rawJson, char const* semanticJson)
{
    if (!Cohort().RunId || !bot || !evaluation.Upgrade)
        return;

    ++Cohort().Metrics.GearUpgrades;

    std::ostringstream context;
    context << "{\"item_id\":" << evaluation.ItemId
            << ",\"bag\":" << uint32(evaluation.Bag)
            << ",\"slot\":" << uint32(evaluation.Slot)
            << ",\"inventory_type\":" << uint32(evaluation.InventoryType)
            << ",\"quality\":" << uint32(evaluation.Quality)
            << ",\"candidate_score\":" << evaluation.CandidateScore
            << ",\"equipped_score\":" << evaluation.EquippedScore
            << ",\"role_power_delta\":" << evaluation.PowerDelta
            << ",\"decision\":\"keep_upgrade_candidate\"}";

    RecordEvent(state, bot, "gear_upgrade", nullptr, "evaluated", rawJson, semanticJson, evaluation.PowerDelta, evaluation.ItemId);

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput("gear_evaluated", "upgrade_candidate", "gear_upgrade", nullptr, 0, 0, evaluation.ItemId, evaluation.PowerDelta, evaluation.ItemId, false, evaluation.PowerDelta > 0.0f);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, nullptr, "item", evaluation.ItemId, "gear_upgrade");
        UpdateSemanticOutcomeStats(bot, "item", evaluation.ItemId, "gear_upgrade", "upgrade_candidate", evaluation.PowerDelta, evaluation.PowerDelta, false, features.c_str());
        return;
    }

    uint64 clipId = Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = "gear_evaluated";
    std::string result = "upgrade_candidate";
    std::string brain = Cohort().Config.BrainVersion;
    std::string contextJson = context.str();
    BotDatasetEvent dataset;
    dataset.run_id = Cohort().RunId;
    dataset.experiment_id = std::to_string(Cohort().ExperimentId);
    dataset.episode_id = Cohort().RunId;
    dataset.bot_guid = bot->GetGUID();
    dataset.bot_role = GetDungeonRole(bot);
    dataset.bot_level = uint32(bot->getLevel());
    dataset.policy_source = WorldPolicySource(Cohort().PolicyModelConfig, false);
    dataset.policy_version = WorldPolicyVersion(Cohort().PolicyModelConfig, Cohort().Config.BrainVersion);
    dataset.timestamp_ms = NowMs();
    dataset.tick_id = state.EventSequence;
    dataset.domain = "gear";
    dataset.situation = event;
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"gear\":true}";
    dataset.chosen_action_json = "{\"event_type\":\"gear_evaluated\",\"item_id\":" + std::to_string(evaluation.ItemId) + "}";
    dataset.action_result = result;
    dataset.outcome_json = contextJson;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\"}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(result);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(contextJson);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, item_id, result, value_float, value_int, raw_json, semantic_json, context_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', %u, '%s', %f, %u, '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), evaluation.ItemId,
        result.c_str(), evaluation.PowerDelta, evaluation.ItemId, raw.c_str(), semantic.c_str(), contextJson.c_str(), canonical.c_str());

    std::string features = BuildEmbeddingFeaturesJson(bot, nullptr, "item", evaluation.ItemId, "gear_upgrade");
    UpdateSemanticOutcomeStats(bot, "item", evaluation.ItemId, "gear_upgrade", "upgrade_candidate", evaluation.PowerDelta, evaluation.PowerDelta, false, features.c_str());
}

bool BotWorldPopulationMgr::TrySmartGearDecision(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action)
{
    if (!bot || NowMs() < state.NextGearDecisionMs)
        return false;

    state.NextGearDecisionMs = NowMs() + 30000;
    BotGearUpgradeEvaluation evaluation = BotLongTermProgressionBrain::EvaluateGearUpgrade(bot);
    std::string lootSourceType = "inventory";
    uint32 lootSourceEntry = 0;
    float lootSourceDistance = 0.0f;
    if (!evaluation.ItemId)
    {
        if (QueryResult candidates = WorldDatabase.PQuery(
            "SELECT source_type, source_entry, item_id, x, y FROM ("
            "SELECT 'creature_loot' AS source_type, clt.Entry AS source_entry, clt.Item AS item_id, c.position_x AS x, c.position_y AS y "
            "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry "
            "WHERE clt.Item > 0 AND clt.QuestRequired = 0 AND c.map = %u AND c.zoneId = %u "
            "UNION ALL "
            "SELECT 'gameobject_loot' AS source_type, glt.Entry AS source_entry, glt.Item AS item_id, g.position_x AS x, g.position_y AS y "
            "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry "
            "WHERE glt.Item > 0 AND glt.QuestRequired = 0 AND g.map = %u AND g.zoneId = %u) smart_loot_candidates "
            "ORDER BY ((x - %f) * (x - %f) + (y - %f) * (y - %f)) LIMIT 64",
            bot->GetMapId(), bot->GetZoneId(), bot->GetMapId(), bot->GetZoneId(),
            bot->GetPositionX(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionY()))
        {
            do
            {
                Field* fields = candidates->Fetch();
                uint32 itemId = fields[2].GetUInt32();
                ItemTemplate const* proto = sObjectMgr->GetItemTemplate(itemId);
                BotGearUpgradeEvaluation candidate = BotLongTermProgressionBrain::EvaluateGearTemplate(bot, proto);
                if (!candidate.ItemId)
                    continue;

                bool better = !evaluation.ItemId || candidate.Upgrade > evaluation.Upgrade || candidate.PowerDelta > evaluation.PowerDelta;
                if (!better)
                    continue;

                evaluation = candidate;
                lootSourceType = fields[0].GetString();
                lootSourceEntry = fields[1].GetUInt32();
                float x = fields[3].GetFloat();
                float y = fields[4].GetFloat();
                lootSourceDistance = Distance2d(bot->GetPositionX(), bot->GetPositionY(), x, y);
            } while (candidates->NextRow());
        }
    }
    if (!evaluation.ItemId)
        return false;

    Item* item = bot->GetItemByPos(evaluation.Bag, evaluation.Slot);
    ItemTemplate const* proto = item ? item->GetTemplate() : nullptr;
    if (!proto)
        proto = sObjectMgr->GetItemTemplate(evaluation.ItemId);
    bool hasValue = proto && proto->GetSellPrice() > 0;
    char const* lootDecision = evaluation.Upgrade ? "need_upgrade" : (evaluation.CanEquip || hasValue ? "greed_value" : "pass_invalid");
    char const* equipResult = "not_equipped";

    if (evaluation.Upgrade && item)
    {
        uint16 equipDest = 0;
        InventoryResult canEquip = bot->CanEquipItem(NULL_SLOT, equipDest, item, true);
        if (canEquip == EQUIP_ERR_OK)
        {
            bot->EquipItem(equipDest, item, true);
            equipResult = "equipped_upgrade";
        }
        else
            equipResult = "equip_rejected";
    }

    std::string raw = BuildRawJson(bot, nullptr);
    std::string semantic = BuildSemanticJson(bot, nullptr, "smart_loot", &power, stage, activity);
    RecordEvent(state, bot, "smart_loot_decision", nullptr, lootDecision, raw.c_str(), semantic.c_str(), evaluation.PowerDelta, evaluation.ItemId);
    std::ostringstream context;
    context << "{\"source_type\":\"" << JsonEscape(lootSourceType) << "\""
            << ",\"source_entry\":" << lootSourceEntry
            << ",\"item_id\":" << evaluation.ItemId
            << ",\"decision\":\"" << lootDecision << "\""
            << ",\"valid_action_mask\":{\"need\":" << (evaluation.Upgrade ? "true" : "false")
            << ",\"greed\":" << ((evaluation.CanEquip || hasValue) ? "true" : "false")
            << ",\"pass\":true}"
            << ",\"candidate_score\":" << evaluation.CandidateScore
            << ",\"equipped_score\":" << evaluation.EquippedScore
            << ",\"power_delta\":" << evaluation.PowerDelta
            << ",\"source_distance\":" << lootSourceDistance
            << "}";
    BotActivityScore smartLootActivity;
    smartLootActivity.Activity = activity;
    smartLootActivity.ExpectedPowerGain = std::max(0.0f, evaluation.PowerDelta);
    smartLootActivity.Score = smartLootActivity.ExpectedPowerGain;
    RecordDecisionReplay(state, bot, nullptr, "smart_loot_roll_policy", lootDecision, raw.c_str(), semantic.c_str(), context.str().c_str(), smartLootActivity, false);
    if (evaluation.Upgrade)
        RecordGearEvaluation(state, bot, evaluation, raw.c_str(), semantic.c_str());

    situation = "smart_loot";
    action = equipResult;
    return true;
}

bool BotWorldPopulationMgr::TryProfessionMemoryAction(WorldBotState& state, Player* bot, BotRolePowerBreakdown const& power, BotProgressionStage stage, BotProgressionActivity activity, std::string& situation, std::string& action)
{
    if (!bot || NowMs() < state.NextProfessionDecisionMs)
        return false;

    state.NextProfessionDecisionMs = NowMs() + 45000;
    std::string raw = BuildRawJson(bot, nullptr);
    std::string semantic = BuildSemanticJson(bot, nullptr, "profession_memory", &power, stage, activity);

    auto emitRecipeSource = [&]() -> bool
    {
        QueryResult recipe = CharacterDatabase.PQuery(
        "SELECT source_type, source_entry, recipe_spell_id, item_id, map_id, zone_id, area_id, x, y, z FROM bot_memory_recipe_sources "
        "WHERE bot_guid = %u ORDER BY last_seen_at DESC LIMIT 1",
        state.Guid.GetCounter());
        if (!recipe)
        {
            recipe = WorldDatabase.PQuery(
                "SELECT source_type, source_entry, recipe_spell_id, item_id, map_id, zone_id, area_id, x, y, z FROM ("
                "SELECT 'trainer' AS source_type, ct.CreatureId AS source_entry, ts.SpellId AS recipe_spell_id, 0 AS item_id, c.map AS map_id, c.zoneId AS zone_id, c.areaId AS area_id, c.position_x AS x, c.position_y AS y, c.position_z AS z "
                "FROM creature_trainer ct INNER JOIN trainer_spell ts ON ts.TrainerId = ct.TrainerId INNER JOIN creature c ON c.id = ct.CreatureId "
                "WHERE ts.SpellId > 0 AND c.map = %u "
                "UNION ALL "
                "SELECT 'vendor_item' AS source_type, nv.entry AS source_entry, 0 AS recipe_spell_id, nv.item AS item_id, c.map AS map_id, c.zoneId AS zone_id, c.areaId AS area_id, c.position_x AS x, c.position_y AS y, c.position_z AS z "
                "FROM npc_vendor nv INNER JOIN creature c ON c.id = nv.entry "
                "WHERE nv.item > 0 AND c.map = %u) recipe_candidates "
                "ORDER BY ((x - %f) * (x - %f) + (y - %f) * (y - %f)) LIMIT 1",
                bot->GetMapId(), bot->GetMapId(),
                bot->GetPositionX(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionY());
        }
        if (!recipe)
            return false;

        Field* fields = recipe->Fetch();
        std::string sourceType = fields[0].GetString();
        uint32 sourceEntry = fields[1].GetUInt32();
        uint32 recipeSpellId = fields[2].GetUInt32();
        uint32 itemId = fields[3].GetUInt32();
        uint32 mapId = fields[4].GetUInt32();
        uint32 zoneId = fields[5].GetUInt32();
        uint32 areaId = fields[6].GetUInt32();
        float x = fields[7].GetFloat();
        float y = fields[8].GetFloat();
        float z = fields[9].GetFloat();
        std::string result = sourceType.empty() ? "known_recipe_source" : sourceType;
        std::string escapedResult = result;
        CharacterDatabase.EscapeString(escapedResult);
        CharacterDatabase.DirectPExecute(
            "INSERT INTO bot_memory_recipe_sources "
            "(bot_guid, profession_skill_id, recipe_spell_id, source_type, source_entry, item_id, map_id, zone_id, area_id, x, y, z, reputation_required, discovered_at, last_seen_at, success_count, failure_count, metadata_json) "
            "VALUES (%u, 0, %u, '%s', %u, %u, %u, %u, %u, %f, %f, %f, 0, NOW(), NOW(), 0, 0, '{\"source\":\"world_recipe_source_index\"}') "
            "ON DUPLICATE KEY UPDATE map_id = VALUES(map_id), zone_id = VALUES(zone_id), area_id = VALUES(area_id), x = VALUES(x), y = VALUES(y), z = VALUES(z), last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
            state.Guid.GetCounter(), recipeSpellId, escapedResult.c_str(), sourceEntry, itemId, mapId, zoneId, areaId, x, y, z);
        if (mapId == bot->GetMapId() && Distance2d(bot->GetPositionX(), bot->GetPositionY(), x, y) > 8.0f)
        {
            bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            bot->GetMotionMaster()->MovePoint(0, x, y, z, true);
        }
        RecordEvent(state, bot, "profession_recipe_source", nullptr, result.c_str(), raw.c_str(), semantic.c_str(), 0.0f, recipeSpellId ? recipeSpellId : (itemId ? itemId : sourceEntry));
        state.PreferMaterialMemoryAction = true;
        state.NextProfessionDecisionMs = NowMs() + 3000;
        situation = "profession_recipe_acquisition";
        if (result.find("trainer") != std::string::npos)
            action = "plan_trainer_recipe_source";
        else if (result.find("vendor") != std::string::npos)
            action = "plan_vendor_recipe_source";
        else
            action = "plan_profession_recipe_source";
        return true;
    };

    auto emitMaterialSource = [&]() -> bool
    {
        QueryResult material = CharacterDatabase.PQuery(
        "SELECT source_type, source_entry, item_id, observed_count, map_id, x, y, z FROM bot_memory_material_sources "
        "WHERE bot_guid = %u ORDER BY last_seen_at DESC LIMIT 1",
        state.Guid.GetCounter());
        if (!material)
        {
            material = WorldDatabase.PQuery(
                "SELECT source_type, source_entry, item_id, observed_count, map_id, x, y, z FROM ("
                "SELECT 'creature_loot' AS source_type, clt.Entry AS source_entry, clt.Item AS item_id, 1 AS observed_count, c.map AS map_id, c.position_x AS x, c.position_y AS y, c.position_z AS z "
                "FROM creature_loot_template clt INNER JOIN creature c ON c.id = clt.Entry "
                "WHERE clt.Item > 0 AND clt.QuestRequired = 0 AND c.map = %u "
                "UNION ALL "
                "SELECT 'gameobject_loot' AS source_type, glt.Entry AS source_entry, glt.Item AS item_id, 1 AS observed_count, g.map AS map_id, g.position_x AS x, g.position_y AS y, g.position_z AS z "
                "FROM gameobject_loot_template glt INNER JOIN gameobject g ON g.id = glt.Entry "
                "WHERE glt.Item > 0 AND glt.QuestRequired = 0 AND g.map = %u) material_candidates "
                "ORDER BY ((x - %f) * (x - %f) + (y - %f) * (y - %f)) LIMIT 1",
                bot->GetMapId(), bot->GetMapId(),
                bot->GetPositionX(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionY());
        }
        if (!material)
            return false;

        Field* fields = material->Fetch();
        std::string sourceType = fields[0].GetString();
        uint32 sourceEntry = fields[1].GetUInt32();
        uint32 itemId = fields[2].GetUInt32();
        uint32 observed = fields[3].GetUInt32();
        uint32 mapId = fields[4].GetUInt32();
        float x = fields[5].GetFloat();
        float y = fields[6].GetFloat();
        float z = fields[7].GetFloat();
        std::string result = sourceType.empty() ? "known_material_source" : sourceType;
        std::string escapedResult = result;
        CharacterDatabase.EscapeString(escapedResult);
        CharacterDatabase.DirectPExecute(
            "INSERT INTO bot_memory_material_sources "
            "(bot_guid, item_id, source_type, source_entry, map_id, zone_id, area_id, x, y, z, drop_chance, observed_count, success_count, failure_count, last_seen_at, metadata_json) "
            "VALUES (%u, %u, '%s', %u, %u, %u, %u, %f, %f, %f, 0, %u, 0, 0, NOW(), '{\"source\":\"world_item_source_index\"}') "
            "ON DUPLICATE KEY UPDATE map_id = VALUES(map_id), zone_id = VALUES(zone_id), area_id = VALUES(area_id), x = VALUES(x), y = VALUES(y), z = VALUES(z), observed_count = GREATEST(observed_count, VALUES(observed_count)), last_seen_at = NOW(), metadata_json = VALUES(metadata_json)",
            state.Guid.GetCounter(), itemId, escapedResult.c_str(), sourceEntry, mapId, bot->GetZoneId(), bot->GetAreaId(), x, y, z, observed ? observed : 1);
        if (mapId == bot->GetMapId() && Distance2d(bot->GetPositionX(), bot->GetPositionY(), x, y) > 8.0f)
        {
            bot->GetMotionMaster()->Clear(MOTION_SLOT_ACTIVE);
            bot->GetMotionMaster()->MovePoint(0, x, y, z, true);
        }
        RecordEvent(state, bot, "material_farming_source", nullptr, result.c_str(), raw.c_str(), semantic.c_str(), float(observed), itemId ? itemId : sourceEntry);
        state.PreferMaterialMemoryAction = false;
        situation = "material_farming";
        action = "plan_material_farming_source";
        return true;
    };

    if (state.PreferMaterialMemoryAction)
    {
        if (emitMaterialSource())
            return true;
        return emitRecipeSource();
    }

    if (emitRecipeSource())
        return true;
    if (emitMaterialSource())
        return true;

    return false;
}


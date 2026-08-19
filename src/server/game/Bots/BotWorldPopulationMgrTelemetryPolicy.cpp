#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotDatasetEvent.h"
#include "Bots/BotTelemetryPolicy.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
#include <sstream>
#include <string>

namespace
{
std::string BoundedResultLabel(char const* result)
{
    std::string label = result && *result ? result : "ok";
    if (label.size() <= 63)
        return label;
    return label.substr(0, 63);
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
}

BotTelemetryPolicyConfig BotWorldPopulationMgr::GetTelemetryPolicyConfig() const
{
    BotTelemetryPolicyConfig config;
    config.smartSampling = Cohort().Config.SmartSampling;
    config.alwaysRecordFailures = Cohort().Config.AlwaysRecordFailures;
    config.alwaysRecordInterventions = Cohort().Config.AlwaysRecordInterventions;
    config.alwaysRecordRareStates = Cohort().Config.AlwaysRecordRareStates;
    config.normalEventSampleRate = Cohort().Config.NormalEventSampleRate;
    config.normalDecisionSampleRate = Cohort().Config.NormalDecisionSampleRate;
    config.minClipImportance = Cohort().Config.MinClipImportance;
    config.minReplayImportance = Cohort().Config.MinReplayImportance;
    return config;
}

BotTelemetryPolicyInput BotWorldPopulationMgr::BuildTelemetryPolicyInput(char const* eventType, char const* result, char const* situation, Unit const* target, uint32 spellId, uint32 questId, uint32 itemId, float valueFloat, uint32 valueInt, bool failure, bool rare, bool intervention) const
{
    BotTelemetryPolicyInput input;
    input.eventType = eventType ? eventType : "";
    input.result = result ? result : "";
    input.situation = situation ? situation : "";
    input.spellId = spellId;
    input.questId = questId;
    input.itemId = itemId;
    input.valueFloat = valueFloat;
    input.valueInt = valueInt;
    input.failure = failure;
    input.rare = rare;
    input.intervention = intervention;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        input.targetEntry = creature->GetEntry();
        if (input.eventType == "combat_started" && (creature->isElite() || creature->IsDungeonBoss() || creature->isWorldBoss()))
            input.rare = true;
    }
    return input;
}

void BotWorldPopulationMgr::RecordPolicyReplay(WorldBotState const& state, Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, char const* rawJson, char const* semanticJson)
{
    if (!Cohort().RunId || !bot)
        return;

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"quest_id\":" << input.questId
                  << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
                  << ",\"target_entry\":" << input.targetEntry << "}";

    std::ostringstream action;
    action << "{\"event_type\":\"" << JsonEscape(input.eventType)
           << "\",\"situation\":\"" << JsonEscape(input.situation)
           << "\",\"spell_id\":" << input.spellId
           << ",\"item_id\":" << input.itemId << "}";

    std::ostringstream failure;
    failure << "{\"result\":\"" << JsonEscape(input.result)
            << "\",\"value_float\":" << input.valueFloat
            << ",\"value_int\":" << input.valueInt << "}";

    std::string type = input.eventType.empty() ? "telemetry_replay" : input.eventType;
    if (type == "death")
        type = "bot_death";
    else if (type == "stuck_detected")
        type = "stuck_loop";
    else if (type == "objective_failed")
        type = "quest_failure";
    else if (type == "raid_wipe")
        type = "boss_mechanic_failure";

    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string actionJson = action.str();
    std::string failureJson = failure.str();
    std::string observation = "{\"bot\":" + botJson + ",\"world\":" + worldJson + ",\"raw\":" + raw + "}";
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
    dataset.tick_id = state.Sequence;
    dataset.domain = "replay";
    dataset.situation = type;
    dataset.observation_json = observation;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"replay\":true}";
    dataset.chosen_action_json = actionJson;
    dataset.action_result = input.result.empty() ? "failed" : input.result;
    dataset.outcome_json = failureJson;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_replay_records\",\"policy_replay\":true}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(actionJson);
    CharacterDatabase.EscapeString(failureJson);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), raw.c_str(), semantic.c_str(), actionJson.c_str(), failureJson.c_str(), canonical.c_str());
}

uint64 BotWorldPopulationMgr::RecordDecisionReplay(WorldBotState const& state, Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, char const* candidateJson, BotActivityScore const& chosenActivity, bool failure)
{
    if (!Cohort().RunId || !bot)
        return 0;

    uint32 targetEntry = 0;
    uint64 targetGuid = 0;
    if (target)
    {
        targetGuid = target->GetGUID().GetCounter();
        if (Creature const* creature = target->ToCreature())
            targetEntry = creature->GetEntry();
    }

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\""
                << ",\"progression_stage\":\"" << JsonEscape(state.ProgressionStage) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"target_guid\":" << targetGuid
                  << ",\"target_entry\":" << targetEntry
                  << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
                  << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
                  << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
                  << ",\"objective_type\":\"" << JsonEscape(state.QuestWork.ObjectiveType) << "\""
                  << ",\"required_entry\":" << (state.QuestWork.RequiredEntry > 0 ? uint32(state.QuestWork.RequiredEntry) : 0)
                  << ",\"required_item\":" << state.QuestWork.RequiredItem
                  << ",\"required_spell\":" << state.QuestWork.RequiredSpell
                  << ",\"target_matches_objective\":" << (targetEntry && (state.QuestWork.RequiredEntry <= 0 || uint32(state.QuestWork.RequiredEntry) == targetEntry) ? "true" : "false") << "}";

    std::ostringstream actionSnapshot;
    actionSnapshot << "{\"action\":\"" << JsonEscape(action ? action : "wait") << "\""
                   << ",\"situation\":\"" << JsonEscape(situation ? situation : "idle") << "\""
                   << ",\"chosen_activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
                   << ",\"model_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.Version) << "\""
                   << ",\"feature_schema_version\":\"" << JsonEscape(Cohort().PolicyModelConfig.FeatureSchemaVersion) << "\""
                   << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
                   << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
                   << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
                   << ",\"candidates\":" << (candidateJson && *candidateJson ? candidateJson : "[]") << "}";

    std::ostringstream failureSnapshot;
    failureSnapshot << "{\"failure\":" << (failure ? "true" : "false")
                    << ",\"activity_score\":" << chosenActivity.Score
                    << ",\"learned_score\":" << chosenActivity.LearnedScore
                    << ",\"learned_penalty\":" << chosenActivity.LearnedPenalty
                    << ",\"danger_score\":" << chosenActivity.LearnedDangerScore
                    << ",\"progression_value\":" << chosenActivity.LearnedProgressionValue
                    << ",\"confidence\":" << chosenActivity.LearnedConfidence
                    << ",\"progress_before\":" << state.QuestWork.ProgressBefore
                    << ",\"progress_after\":" << state.QuestWork.ProgressAfter
                    << ",\"loot_result\":\"" << JsonEscape(state.LastLootResult) << "\""
                    << ",\"loot_items_count\":" << state.LastLootItemsCount
                    << ",\"loot_money\":" << state.LastLootMoney
                    << ",\"loot_state_cleared\":" << (state.LastLootStateCleared ? "true" : "false")
                    << ",\"no_progress_reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\""
                    << ",\"cooldown_reason\":\"" << JsonEscape(state.QuestWork.FailedReason) << "\""
                    << ",\"consecutive_same_decision_count\":" << state.ConsecutiveSameDecisionCount
                    << ",\"idle_decision_repeat_count\":" << state.IdleDecisionRepeatCount
                    << ",\"target_churn_count\":" << state.TargetChurnCount
                    << ",\"loop_guardrail_count\":" << state.LoopGuardrailCount
                    << ",\"last_loop_guardrail_action\":\"" << JsonEscape(state.LastLoopGuardrailAction) << "\""
                    << ",\"last_loop_guardrail_reason\":\"" << JsonEscape(state.LastLoopGuardrailReason) << "\""
                    << ",\"last_recovery_mode\":\"" << JsonEscape(state.LastRecoveryMode) << "\""
                    << ",\"last_recovery_result\":\"" << JsonEscape(state.LastRecoveryResult) << "\""
                    << ",\"dummy_allowed_by_quest\":" << (state.CurrentDummyAllowedByQuest ? "true" : "false") << "}";

    std::string type = "policy_model_prediction";
    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string actionJson = actionSnapshot.str();
    std::string failureJson = failureSnapshot.str();
    std::string observation = "{\"bot\":" + botJson + ",\"world\":" + worldJson + ",\"raw\":" + raw + "}";
    BotDatasetEvent dataset;
    dataset.feature_schema_version = Cohort().PolicyModelConfig.FeatureSchemaVersion.empty() ? BotDatasetEvent::DefaultFeatureSchemaVersion : Cohort().PolicyModelConfig.FeatureSchemaVersion;
    dataset.run_id = Cohort().RunId;
    dataset.experiment_id = std::to_string(Cohort().ExperimentId);
    dataset.episode_id = Cohort().RunId;
    dataset.bot_guid = bot->GetGUID();
    dataset.bot_role = GetDungeonRole(bot);
    dataset.bot_level = uint32(bot->getLevel());
    dataset.policy_source = WorldPolicySource(Cohort().PolicyModelConfig, true);
    dataset.policy_version = WorldPolicyVersion(Cohort().PolicyModelConfig, Cohort().Config.BrainVersion);
    dataset.timestamp_ms = NowMs();
    dataset.tick_id = state.Sequence;
    dataset.domain = "replay";
    dataset.situation = type;
    dataset.observation_json = observation;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = candidateJson && *candidateJson ? candidateJson : "[]";
    dataset.chosen_action_json = actionJson;
    dataset.action_result = failure ? "failed" : "ok";
    dataset.outcome_json = failureJson;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_replay_records\",\"decision_replay\":true}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(actionJson);
    CharacterDatabase.EscapeString(failureJson);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, dataset.feature_schema_version.c_str(),
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), raw.c_str(), semantic.c_str(), actionJson.c_str(), failureJson.c_str(), canonical.c_str());
    return ReadLastInsertId();
}

BotTelemetryFrame BotWorldPopulationMgr::BuildTelemetryFrame(Player* bot, Unit const* target, char const* situation, char const* action, char const* rawJson, char const* semanticJson, uint32 questId) const
{
    BotTelemetryFrame frame;
    if (!bot)
        return frame;

    frame.timestamp_ms = uint64(std::chrono::duration_cast<std::chrono::milliseconds>(GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
    frame.bot_guid = bot->GetGUID();
    frame.map_id = bot->GetMapId();
    frame.zone_id = bot->GetZoneId();
    frame.area_id = bot->GetAreaId();
    frame.x = bot->GetPositionX();
    frame.y = bot->GetPositionY();
    frame.z = bot->GetPositionZ();
    frame.o = bot->GetOrientation();
    frame.level = bot->getLevel();
    frame.hp_pct = bot->GetMaxHealth() ? float(bot->GetHealth()) / float(bot->GetMaxHealth()) : 1.0f;
    frame.power_pct = bot->GetMaxPower(bot->GetPowerType()) ? float(bot->GetPower(bot->GetPowerType())) / float(bot->GetMaxPower(bot->GetPowerType())) : 1.0f;
    frame.in_combat = bot->IsInCombat();
    if (target)
    {
        frame.target_guid = target->GetGUID();
        if (Creature const* creature = target->ToCreature())
            frame.target_entry = creature->GetEntry();
    }
    frame.quest_id = questId;
    frame.situation_type = situation ? situation : "";
    frame.action = BoundedResultLabel(action);
    frame.raw_json = rawJson ? rawJson : "{}";
    frame.semantic_json = semanticJson ? semanticJson : "{}";
    return frame;
}

uint64 BotWorldPopulationMgr::MaybeCaptureTelemetryClip(Player* bot, Unit const* target, BotTelemetryPolicyInput const& input, BotTelemetryPolicyDecision const& decision, char const* rawJson, char const* semanticJson)
{
    if (!Cohort().TelemetryBuffer.IsEnabled() || !decision.openClip)
        return 0;

    BotTelemetryFrame frame = BuildTelemetryFrame(bot, target, input.eventType.c_str(), input.result.c_str(), rawJson, semanticJson, input.questId);
    if (frame.bot_guid.IsEmpty())
        return 0;

    std::ostringstream summary;
    summary << "{\"event_type\":\"" << JsonEscape(input.eventType.empty() ? "unknown" : input.eventType) << "\""
            << ",\"result\":\"" << JsonEscape(input.result) << "\""
            << ",\"reason\":\"" << JsonEscape(decision.reason) << "\""
            << ",\"quest_id\":" << input.questId
            << ",\"item_id\":" << input.itemId
            << ",\"target_entry\":" << input.targetEntry
            << ",\"value_float\":" << input.valueFloat
            << ",\"value_int\":" << input.valueInt << "}";

    return Cohort().TelemetryBuffer.CaptureEvent(Cohort().ExperimentId, Cohort().RunId, Cohort().Config.BrainVersion, frame, input.eventType.empty() ? "unknown" : input.eventType.c_str(), decision.score, decision.reason.c_str(), summary.str());
}


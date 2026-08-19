#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotDatasetEvent.h"
#include "Bots/BotTelemetryPolicy.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "ObjectMgr.h"
#include "Player.h"
#include "Quests/QuestDef.h"
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

bool EventLooksSuccessful(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = BoundedResultLabel(result);
    return res == "ok"
        || event == "mob_killed"
        || event == "boss_killed"
        || event == "quest_completed"
        || event == "objective_progress"
        || event == "gear_upgrade"
        || event == "gear_evaluated"
        || event == "interrupt_success";
}

bool EventLooksFailure(char const* eventType, char const* result)
{
    std::string event = eventType ? eventType : "";
    std::string res = BoundedResultLabel(result);
    return event == "death"
        || event == "repeated_death"
        || event == "stuck_detected"
        || event == "objective_failed"
        || event == "death_recovery_failed"
        || event == "interrupt_failed"
        || event == "teleport_fallback_used"
        || res == "failed"
        || res.find("failed") != std::string::npos
        || res.find("blocked") != std::string::npos;
}

uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}
}

void BotWorldPopulationMgr::RecordRaidTelemetry(WorldBotState& state, Player* bot, Unit const* boss, char const* eventType, char const* result, BossMechanicFeatures const& features, RaidRoleAssignment const& assignment, RaidPositioningAnchors const& anchors, RaidMechanicAdapter const& adapter, RaidGearTargetPlan const& gearPlan, HeroicRaidProgression const& progression, char const* rawJson, char const* semanticJson, float valueFloat, uint32 valueInt, uint32 spellId)
{
    if (!Cohort().RunId || !bot || !features.RaidEncounter)
        return;

    ++Cohort().Raid.EvidenceSequence;
    ++Cohort().Metrics.RaidTelemetryEvents;
    std::string observedEvent = eventType ? eventType : "raid_telemetry";
    if (observedEvent == "raid_role_assignment")
        ++Cohort().Metrics.RoleAssignments;
    if (observedEvent == "raid_interrupt")
    {
        ++Cohort().Metrics.InterruptSuccess;
        ++Cohort().Metrics.AssignedInterruptSuccess;
    }
    if (observedEvent == "raid_add_wave" || observedEvent == "raid_boss_action")
        ++Cohort().Metrics.TargetPriorityDecisions;
    if (observedEvent == "raid_healer_cooldown")
        ++Cohort().Metrics.HealerAssignments;
    if (observedEvent == "raid_position_anchor" || observedEvent == "raid_boss_action")
        ++Cohort().Metrics.TankPositioning;
    if (observedEvent == "raid_position_anchor")
        ++Cohort().Metrics.Regroups;
    if (observedEvent == "raid_wipe")
        ++Cohort().Metrics.RecoveryEvents;
    bool failure = EventLooksFailure(eventType, result) || (eventType && std::string(eventType) == "raid_wipe");
    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(eventType ? eventType : "raid_telemetry", result ? result : "ok", features.RaidEncounter ? "raid_boss" : "dungeon_boss", boss, spellId ? spellId : features.CastSpellId, 0, 0, valueFloat, valueInt, failure, true);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
        return;

    std::ostringstream context;
    context << "{\"raid_runtime\":" << BuildRaidRuntimeJson()
            << ",\"raid_role_assignment\":" << BuildRaidRoleAssignmentJson(assignment)
            << ",\"raid_positioning_anchors\":" << BuildRaidPositioningAnchorsJson(anchors)
            << ",\"raid_mechanic_adapter\":" << BuildRaidMechanicAdapterJson(adapter)
            << ",\"raid_boss_mechanics\":" << BuildBossMechanicsJson(features)
            << ",\"gear_target_plan\":" << BuildRaidGearTargetPlanJson(gearPlan)
            << ",\"heroic_raid_progression\":" << BuildHeroicRaidProgressionJson(progression) << "}";

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "raid_telemetry";
    std::string eventResult = result ? result : "ok";
    std::string brain = Cohort().Config.BrainVersion;
    std::string contextJson = context.str();
    uint64 clipId = MaybeCaptureTelemetryClip(bot, boss, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";
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
    dataset.domain = "raid_telemetry";
    dataset.situation = event;
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"raid_telemetry\":true}";
    dataset.chosen_action_json = "{\"event_type\":\"" + JsonEscape(event) + "\",\"spell_id\":" + std::to_string(spellId ? spellId : features.CastSpellId) + "}";
    dataset.action_result = eventResult;
    dataset.outcome_json = contextJson;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\",\"raid\":true}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(eventResult);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(contextJson);
    CharacterDatabase.EscapeString(canonical);

    uint64 targetGuid = boss ? boss->GetGUID().GetCounter() : features.BossGuid.GetCounter();
    uint32 targetEntry = features.BossEntry;
    if (Creature const* creature = boss ? boss->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, spell_id, result, value_float, value_int, raw_json, semantic_json, context_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, '%s', %f, %u, '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid,
        targetEntry, spellId ? spellId : features.CastSpellId, eventResult.c_str(), valueFloat, valueInt, raw.c_str(), semantic.c_str(), contextJson.c_str(), canonical.c_str());

    uint32 mechanicKey = features.MoveOut ? 1 : (features.MustInterrupt ? 2 : (features.AddsActive ? 5 : (features.RaidDamage ? 4 : 11)));
    std::string mechanicFeatures = BuildEmbeddingFeaturesJson(bot, boss, "mechanic", mechanicKey, adapter.MechanicFamily.c_str());
    UpdateSemanticOutcomeStats(bot, "mechanic", mechanicKey, event.c_str(), eventResult.c_str(), valueFloat, 0.0f, eventResult == "failed" || eventResult == "death", mechanicFeatures.c_str());
    if (gearPlan.NeededItemLevel > 0.0f)
    {
        std::string gearFeatures = BuildEmbeddingFeaturesJson(bot, nullptr, "item", uint32(gearPlan.TargetItemLevel), "raid_gear_target");
        UpdateSemanticOutcomeStats(bot, "item", uint32(gearPlan.TargetItemLevel), "raid_gear_target", gearPlan.RecommendedActivity.c_str(), gearPlan.NeededItemLevel, -gearPlan.NeededItemLevel, false, gearFeatures.c_str());
    }
    if (policy.writeReplay)
        RecordPolicyReplay(state, bot, boss, policyInput, rawJson, semanticJson);
}

void BotWorldPopulationMgr::RecordQuestObjectiveProgressForTarget(WorldBotState& state, Player* bot, Unit const* target, char const* rawJson, char const* semanticJson)
{
    if (!Cohort().RunId || !bot || !target)
        return;

    Creature const* creature = target->ToCreature();
    if (!creature)
        return;
    QuestObjectivePlan activePlan;
    if (IsTrainingDummy(target) && (!FindActiveQuestObjective(bot, activePlan) || !IsTrainingDummyAllowedForQuest(activePlan, target)))
        return;

    uint32 entry = creature->GetEntry();
    for (auto const& questStatus : bot->getQuestStatusMap())
    {
        if (questStatus.second.Status != QUEST_STATUS_INCOMPLETE && questStatus.second.Status != QUEST_STATUS_COMPLETE)
            continue;

        Quest const* quest = sObjectMgr->GetQuestTemplate(questStatus.first);
        if (!quest)
            continue;

        for (uint8 i = 0; i < QUEST_OBJECTIVES_COUNT; ++i)
        {
            if (quest->RequiredNpcOrGo[i] != int32(entry) || !quest->RequiredNpcOrGoCount[i])
                continue;

            uint32 current = questStatus.second.CreatureOrGOCount[i];
            uint32 before = state.LastQuestProgressBefore;
            bool completed = bot->CanCompleteQuest(quest->GetQuestId());
            std::ostringstream context;
            context << "{\"required_entry\":" << entry
                    << ",\"required_count\":" << quest->RequiredNpcOrGoCount[i]
                    << ",\"current_count\":" << current
                    << ",\"progress_before\":" << before
                    << ",\"progress_after\":" << current
                    << ",\"objective_index\":" << uint32(i) << "}";
            if (current > before || completed)
            {
                ++Cohort().Metrics.QuestObjectiveProgress;
                state.LastQuestObjectiveProgress = Cohort().Metrics.QuestObjectiveProgress;
                RecordQuestEvent(state, bot, "objective_progress", quest->GetQuestId(), target, "kill_verified", rawJson, semanticJson, current, 0, context.str().c_str());

            }
            else
            {
                state.LastNoProgressReason = "counter_unchanged";
                RecordQuestEvent(state, bot, "objective_no_progress", quest->GetQuestId(), target, "counter_unchanged", rawJson, semanticJson, current, 0, context.str().c_str());
            }
        }
    }
}

void BotWorldPopulationMgr::RecordQuestEvent(WorldBotState& state, Player* bot, char const* eventType, uint32 questId, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, uint32 valueInt, uint32 itemId, char const* contextJson)
{
    if (!bot)
        return;

    RecordExperimentSegmentEvent(bot, eventType, result, questId, target, Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID()), rawJson, semanticJson);
    RecordObjectiveClusterMemory(state, bot, eventType, questId, result, valueInt, contextJson);

    if (!Cohort().RunId)
        return;

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(eventType ? eventType : "quest_event", result ? result : "", "quest", target, 0, questId, itemId, 0.0f, valueInt, EventLooksFailure(eventType, result), eventType && (std::string(eventType) == "quest_completed" || std::string(eventType) == "quest_accepted"));
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    if (!policy.writeEvent)
        return;

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "quest_event";
    std::string res = BoundedResultLabel(result);
    std::string brain = Cohort().Config.BrainVersion;
    std::string context = contextJson ? contextJson : "{}";
    uint64 clipId = MaybeCaptureTelemetryClip(bot, target, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";
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
    dataset.domain = "quest_event";
    dataset.situation = event;
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"event\":true}";
    dataset.chosen_action_json = "{\"event_type\":\"" + JsonEscape(event) + "\",\"quest_id\":" + std::to_string(questId) + "}";
    dataset.action_result = res.empty() ? "ok" : res;
    dataset.outcome_json = "{\"result\":\"" + JsonEscape(dataset.action_result) + "\",\"quest_id\":" + std::to_string(questId) + ",\"item_id\":" + std::to_string(itemId) + ",\"value_int\":" + std::to_string(valueInt) + "}";
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\",\"quest_event\":true}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(context);
    CharacterDatabase.EscapeString(canonical);

    uint32 targetEntry = 0;
    uint64 targetGuid = 0;
    if (target)
    {
        targetGuid = target->GetGUID().GetCounter();
        if (Creature const* creature = target->ToCreature())
            targetEntry = creature->GetEntry();
    }

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, quest_id, item_id, result, value_int, raw_json, semantic_json, context_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, %u, '%s', %u, '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid, targetEntry,
        questId, itemId, res.c_str(), valueInt, raw.c_str(), semantic.c_str(), context.c_str(), canonical.c_str());

    UpdateSemanticStatsFromEvent(bot, target, eventType, result, 0.0f, valueInt, 0, semanticJson);
    if (questId)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, target, "quest", questId, eventType ? eventType : "quest_event");
        UpdateSemanticOutcomeStats(bot, "quest", questId, eventType, result, float(valueInt), 0.0f, EventLooksFailure(eventType, result), features.c_str());
    }
    if (itemId)
    {
        std::string features = BuildEmbeddingFeaturesJson(bot, target, "item", itemId, eventType ? eventType : "quest_reward");
        UpdateSemanticOutcomeStats(bot, "item", itemId, eventType, result, float(valueInt), 0.0f, EventLooksFailure(eventType, result), features.c_str());
    }
}

void BotWorldPopulationMgr::RecordObjectiveClusterMemory(WorldBotState const& state, Player* bot, char const* eventType, uint32 questId, char const* result, uint32 valueInt, char const* contextJson) const
{
    if (!bot)
        return;

    std::string event = eventType ? eventType : "quest_event";
    std::string res = BoundedResultLabel(result);
    bool clusterEvent = event == "quest_bucket_selected"
        || event == "objective_area_selected"
        || event == "quest_work_started"
        || event == "objective_progress"
        || event == "objective_no_progress"
        || event == "objective_search"
        || event == "objective_failed"
        || event == "ability_objective_failed"
        || event == "quest_completed"
        || event == "quest_unsupported_after_accept"
        || event == "quest_accept_failed";
    if (!clusterEvent)
        return;

    uint32 effectiveQuestId = questId ? questId : state.QuestWork.ActiveQuestId;
    if (!effectiveQuestId && !state.ActiveQuestClusterId)
        return;

    bool failed = EventLooksFailure(eventType, result)
        || event == "quest_unsupported_after_accept"
        || event == "quest_accept_failed"
        || event == "objective_no_progress";
    bool completed = !failed && (EventLooksSuccessful(eventType, result)
        || event == "quest_bucket_selected"
        || event == "objective_area_selected"
        || event == "quest_work_started"
        || event == "objective_search");

    std::string objectiveType = state.QuestWork.ObjectiveType;
    if (objectiveType.empty() || objectiveType == "none")
        objectiveType = event;

    std::ostringstream metadata;
    metadata << "{\"source\":\"quest_event\""
             << ",\"event_type\":\"" << JsonEscape(event) << "\""
             << ",\"result\":\"" << JsonEscape(res.empty() ? (failed ? "failed" : "ok") : res) << "\""
             << ",\"value_int\":" << valueInt
             << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
             << ",\"bucket_reason\":\"" << JsonEscape(state.LastQuestBucketReason) << "\""
             << ",\"context\":" << (contextJson && *contextJson ? contextJson : "{}") << "}";

    std::string escapedObjective = objectiveType;
    std::string escapedResult = res.empty() ? (failed ? "failed" : "ok") : res;
    std::string metadataJson = metadata.str();
    CharacterDatabase.EscapeString(escapedObjective);
    CharacterDatabase.EscapeString(escapedResult);
    CharacterDatabase.EscapeString(metadataJson);
    char const* blacklistSql = failed ? "DATE_ADD(NOW(), INTERVAL 2 MINUTE)" : "NULL";

    CharacterDatabase.DirectPExecute(
        "INSERT INTO bot_memory_objective_clusters "
        "(bot_guid, cluster_id, map_id, zone_id, area_id, quest_id, objective_type, completed_count, failure_count, blacklisted_until, last_result, last_event_at, metadata_json) "
        "VALUES (%u, %u, %u, %u, %u, %u, '%s', %u, %u, %s, '%s', NOW(), '%s') "
        "ON DUPLICATE KEY UPDATE map_id = VALUES(map_id), zone_id = VALUES(zone_id), area_id = VALUES(area_id), completed_count = completed_count + VALUES(completed_count), failure_count = failure_count + VALUES(failure_count), blacklisted_until = VALUES(blacklisted_until), last_result = VALUES(last_result), last_event_at = NOW(), metadata_json = VALUES(metadata_json)",
        state.Guid.GetCounter(), state.ActiveQuestClusterId, bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(), effectiveQuestId,
        escapedObjective.c_str(), completed ? 1 : 0, failed ? 1 : 0, blacklistSql, escapedResult.c_str(), metadataJson.c_str());
}

void BotWorldPopulationMgr::RecordExperimentSegmentEvent(Player* bot, char const* eventType, char const* result, uint32 questId, Unit const* target, uint64 clipId, char const* rawJson, char const* semanticJson)
{
    if (!bot || !eventType || !*eventType)
        return;

    uint64 targetGuid = target ? target->GetGUID().GetCounter() : 0;
    uint32 targetEntry = 0;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
        targetEntry = creature->GetEntry();

    std::ostringstream trigger;
    trigger << "{\"event_type\":\"" << JsonEscape(eventType)
            << "\",\"result\":\"" << JsonEscape(result ? result : "")
            << "\",\"quest_id\":" << questId
            << ",\"target_guid\":" << targetGuid
            << ",\"target_entry\":" << targetEntry
            << ",\"raw\":" << (rawJson && *rawJson ? rawJson : "{}")
            << ",\"semantic\":" << (semanticJson && *semanticJson ? semanticJson : "{}") << "}";

    std::ostringstream summary;
    summary << "{\"event_type\":\"" << JsonEscape(eventType)
            << "\",\"result\":\"" << JsonEscape(result ? result : "")
            << "\",\"quest_id\":" << questId
            << ",\"clip_id\":" << clipId
            << ",\"map_id\":" << bot->GetMapId()
            << ",\"zone_id\":" << bot->GetZoneId()
            << ",\"area_id\":" << bot->GetAreaId() << "}";

    Cohort().ExperimentCoordinator.HandleTelemetryEvent(bot, eventType, result, questId, 0, clipId, trigger.str().c_str(), summary.str().c_str());
}

void BotWorldPopulationMgr::RecordQuestReplay(WorldBotState const& state, Player* bot, char const* replayType, uint32 questId, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson)
{
    if (!Cohort().RunId || !bot)
        return;

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(replayType ? replayType : "quest_failure", "failed", "quest", nullptr, 0, questId, 0, 0.0f, 0, true, true);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), 0);
    if (!policy.writeReplay)
        return;

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"quest_id\":" << questId
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"quest_id\":" << questId << "}";

    std::string type = replayType ? replayType : "quest_failure";
    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string action = actionJson ? actionJson : "{}";
    std::string failure = failureJson ? failureJson : "{}";
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
    dataset.chosen_action_json = action;
    dataset.action_result = "failed";
    dataset.outcome_json = failure;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_replay_records\"}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(action);
    CharacterDatabase.EscapeString(failure);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), raw.c_str(), semantic.c_str(), action.c_str(), failure.c_str(), canonical.c_str());
}

void BotWorldPopulationMgr::RecordBossReplay(WorldBotState const& state, Player* bot, Unit const* boss, BossMechanicFeatures const& features, char const* replayType, char const* rawJson, char const* semanticJson, char const* actionJson, char const* failureJson)
{
    if (!Cohort().RunId || !bot)
        return;

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(replayType ? replayType : "boss_mechanic_failure", "failed", features.RaidEncounter ? "raid_boss" : "dungeon_boss", boss, features.CastSpellId, 0, 0, features.DangerScore, features.BossEntry, true, true);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), 0);
    if (!policy.writeReplay)
        return;

    std::ostringstream botSnapshot;
    botSnapshot << "{\"guid\":" << bot->GetGUID().GetCounter()
                << ",\"level\":" << uint32(bot->getLevel())
                << ",\"class_id\":" << uint32(bot->getClass())
                << ",\"hp\":" << bot->GetHealth()
                << ",\"max_hp\":" << bot->GetMaxHealth()
                << ",\"role\":\"" << JsonEscape(GetDungeonRole(bot)) << "\""
                << ",\"activity\":\"" << JsonEscape(state.ActivityType) << "\"}";

    std::ostringstream worldSnapshot;
    worldSnapshot << "{\"map_id\":" << bot->GetMapId()
                  << ",\"zone_id\":" << bot->GetZoneId()
                  << ",\"area_id\":" << bot->GetAreaId()
                  << ",\"x\":" << bot->GetPositionX()
                  << ",\"y\":" << bot->GetPositionY()
                  << ",\"z\":" << bot->GetPositionZ()
                  << ",\"o\":" << bot->GetOrientation()
                  << ",\"boss_guid\":" << (boss ? boss->GetGUID().GetCounter() : features.BossGuid.GetCounter())
                  << ",\"boss_entry\":" << features.BossEntry
                  << ",\"boss_spell_id\":" << features.CastSpellId
                  << ",\"mechanics\":" << BuildBossMechanicsJson(features) << "}";

    std::ostringstream partySnapshot;
    partySnapshot << "{\"tank_hp_pct\":" << features.TankHpPct
                  << ",\"party_average_hp_pct\":" << features.PartyAverageHpPct
                  << ",\"lowest_ally_hp_pct\":" << features.LowestAllyHpPct
                  << ",\"healer_mana_pct\":" << features.HealerManaPct
                  << ",\"add_count\":" << features.AddCount << "}";

    std::string type = replayType ? replayType : "boss_mechanic_failure";
    std::string botJson = botSnapshot.str();
    std::string worldJson = worldSnapshot.str();
    std::string partyJson = partySnapshot.str();
    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string action = actionJson ? actionJson : "{}";
    std::string failure = failureJson ? failureJson : "{}";
    std::string observation = "{\"bot\":" + botJson + ",\"world\":" + worldJson + ",\"party\":" + partyJson + ",\"raw\":" + raw + "}";
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
    dataset.chosen_action_json = action;
    dataset.action_result = "failed";
    dataset.outcome_json = failure;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_replay_records\",\"boss_replay\":true}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(type);
    CharacterDatabase.EscapeString(botJson);
    CharacterDatabase.EscapeString(worldJson);
    CharacterDatabase.EscapeString(partyJson);
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(action);
    CharacterDatabase.EscapeString(failure);
    CharacterDatabase.EscapeString(canonical);

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_replay_records (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, replay_type, map_id, zone_id, x, y, z, o, bot_snapshot_json, world_snapshot_json, party_snapshot_json, raw_state_json, semantic_state_json, chosen_action_json, failure_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %u, %u, %f, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), type.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetPositionX(), bot->GetPositionY(),
        bot->GetPositionZ(), bot->GetOrientation(), botJson.c_str(), worldJson.c_str(), partyJson.c_str(), raw.c_str(), semantic.c_str(), action.c_str(), failure.c_str(), canonical.c_str());
}


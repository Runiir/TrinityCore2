#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotClassSpecActionProfile.h"
#include "Bots/BotDatasetEvent.h"
#include "Bots/BotExperienceLearningPolicy.h"
#include "Bots/BotProgressionGoalPolicy.h"
#include "Bots/BotRoleSaturationPolicy.h"
#include "Bots/BotTelemetryPolicy.h"
#include "Creature.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "Player.h"
#include "Unit.h"

#include <chrono>
#include <sstream>
#include <string>
#include <vector>

namespace
{
constexpr uint32 RepeatableDiagnosticEventHeartbeatMs = 5000;

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

bool IsRepeatableTraceDecision(bool failure, bool rare, char const* action)
{
    if (failure || rare || !action)
        return false;

    std::string const value(action);
    return value.find("path_rejected") != std::string::npos
        || value.find("anchor_move") != std::string::npos
        || value.find("wait_for_") != std::string::npos
        || value.rfind("hold_", 0) == 0
        || value.find("_hold_") != std::string::npos;
}
}

void BotWorldPopulationMgr::RecordEvent(WorldBotState& state, Player* bot, char const* eventType, Unit const* target, char const* result, char const* rawJson, char const* semanticJson, float valueFloat, uint32 valueInt, uint32 spellId)
{
    if (!bot)
        return;

    std::string observedEvent = eventType ? eventType : "unknown";
    std::string observedResult = result ? result : "";
    if (observedEvent == "validation_role_assignment" || observedEvent == "role_assignment" || observedEvent == "tank_assigned" || observedEvent == "healer_assigned" || observedEvent == "raid_role_assignment")
        ++Cohort().Metrics.RoleAssignments;
    if (observedEvent == "party_formed" || observedEvent == "raid_formed" || observedEvent == "validation_group_formed")
        ++Cohort().Metrics.GroupFormations;
    if (observedEvent == "raid_formed")
        ++Cohort().Metrics.RaidFormations;
    if (observedEvent == "target_priority" || observedEvent == "target_switch" || observedEvent == "validation_target_priority" || observedEvent == "assist_target_search_authoritative_focus" || observedEvent == "raid_add_wave")
        ++Cohort().Metrics.TargetPriorityDecisions;
    if (observedEvent == "interrupt_success" || observedEvent == "assigned_interrupt_success" || observedEvent == "validation_interrupt" || observedEvent == "raid_interrupt")
        ++Cohort().Metrics.InterruptSuccess;
    if (observedEvent == "assigned_interrupt_success" || observedEvent == "validation_interrupt" || observedEvent == "raid_interrupt")
        ++Cohort().Metrics.AssignedInterruptSuccess;
    if (observedEvent == "healer_assignment" || observedEvent == "validation_route_group_heal" || observedEvent == "trash_heal" || observedEvent == "external_defensive" || observedEvent == "raid_healer_cooldown")
        ++Cohort().Metrics.HealerAssignments;
    if (observedEvent == "validation_route_tank_boss" || observedEvent == "tank_positioning" || observedEvent == "move_to_validation_route_assist_target" || observedEvent == "raid_position_anchor" || observedResult == "force_tank_focus" || observedResult == "assist_tank_focus")
        ++Cohort().Metrics.TankPositioning;
    if (observedEvent == "validation_route_regroup" || observedEvent == "regroup" || observedEvent == "validation_route_hold_anchor" || observedEvent == "move_to_validation_route_focus" || observedEvent == "raid_position_anchor")
        ++Cohort().Metrics.Regroups;
    if (observedEvent == "stuck_detected" || observedEvent == "unstuck" || observedEvent == "death" || observedEvent == "dead_recovery" || observedEvent == "validation_route_recovery" || observedEvent == "raid_wipe")
        ++Cohort().Metrics.RecoveryEvents;
    if (observedEvent == "instance_reset")
        ++Cohort().Metrics.InstanceResets;

    // Recovery/search observations can be produced on every decision tick
    // while a native transition is still pending. Keep the first edge and a
    // five-second heartbeat, carrying the number of suppressed observations,
    // while transition events (release, re-entry, reset, kill) remain exact.
    bool const repeatableDiagnosticEvent = observedEvent == "validation_route_recovery"
        || observedEvent == "validation_route_target_search"
        || observedEvent == "validation_route_prerequisite"
        || observedEvent == "native_runback_blocked"
        || observedEvent == "target_rejected"
        || observedEvent == "stuck_detected"
        || observedEvent == "validation_route_drudge_lanes";
    uint32 suppressedRepeatableEvents = 0;
    bool suppressRepeatablePersistence = false;
    if (repeatableDiagnosticEvent)
    {
        std::ostringstream repeatKey;
        repeatKey << observedEvent << '|' << observedResult << '|'
                  << (target ? target->GetGUID().GetCounter() : 0) << '|'
                  << valueInt << '|' << spellId << '|'
                  << state.ValidationRouteGeneration << '|'
                  << Cohort().Config.ValidationRouteNodeId;
        std::string const key = repeatKey.str();
        uint64 const nowMs = NowMs();
        if (state.LastRepeatableEventKey == key)
        {
            ++state.SuppressedRepeatableEventCount;
            if (state.LastRepeatableEventEmitMs
                && nowMs - state.LastRepeatableEventEmitMs < RepeatableDiagnosticEventHeartbeatMs)
                suppressRepeatablePersistence = true;

            if (!suppressRepeatablePersistence)
            {
                suppressedRepeatableEvents = state.SuppressedRepeatableEventCount;
                state.SuppressedRepeatableEventCount = 0;
                state.LastRepeatableEventEmitMs = nowMs;
            }
        }
        else
        {
            state.LastRepeatableEventKey = key;
            state.LastRepeatableEventEmitMs = nowMs;
            state.SuppressedRepeatableEventCount = 0;
        }
    }

    if (suppressRepeatablePersistence)
        return;

    // Keep the edge and five-second heartbeat in the bounded trace, carrying
    // the exact number of suppressed repeats.  This prevents a stuck Drudge
    // or partial-death hold from flooding trace snapshots while preserving a
    // reconstructable count of every suppressed observation.
    state.PendingTraceSuppressedRepeatableEventCount = suppressedRepeatableEvents;
    RecordDecisionTrace(state, eventType ? eventType : "event", eventType ? eventType : "event", target, 0, result ? result : "ok", EventLooksFailure(eventType, result) ? "event_failure" : "");
    RecordExperimentSegmentEvent(bot, eventType, result, 0, target, Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID()), rawJson, semanticJson);

    if (!Cohort().RunId)
        return;

    std::string eventName = observedEvent;
    bool rareCombatStart = eventName == "combat_started" && target && target->getLevel() > bot->getLevel() + 3;
    bool recoveryRare = eventName == "repeated_death" || eventName == "death_recovery_failed";
    bool recoveryIntervention = eventName == "teleport_fallback_used";
    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput(eventName.c_str(), result ? result : "", nullptr, target, spellId, 0, 0, valueFloat, valueInt, EventLooksFailure(eventType, result), rareCombatStart || recoveryRare, recoveryIntervention);
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideEvent(policyInput, GetTelemetryPolicyConfig(), ++state.EventSequence);
    bool forceTeacherEvent = eventName == "combat_started"
        || eventName == "spell_cast"
        || eventName == "mob_killed"
        || eventName == "boss_add_killed"
        || eventName == "boss_killed"
        || eventName == "loot_target"
        || eventName == "loot_received"
        || eventName == "loot_failed"
        || eventName == "objective_progress"
        || eventName == "objective_no_progress"
        || eventName == "objective_target_lost"
        || eventName == "quest_accepted"
        || eventName == "quest_completed"
        || eventName.rfind("validation_route", 0) == 0;
    if (!policy.writeEvent && !forceTeacherEvent)
        return;

    uint64 clipId = MaybeCaptureTelemetryClip(bot, target, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID());
    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string event = eventType ? eventType : "unknown";
    std::string res = BoundedResultLabel(result);
    std::string dbRes = BoundedResultLabel(res.c_str());
    std::string brain = Cohort().Config.BrainVersion;
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
    dataset.domain = "world_event";
    dataset.situation = event;
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = "{\"event\":true}";
    dataset.chosen_action_json = "{\"event_type\":\"" + JsonEscape(event) + "\"}";
    dataset.action_result = res.empty() ? "ok" : res;
    std::ostringstream eventOutcome;
    eventOutcome << "{\"result\":\"" << JsonEscape(dataset.action_result)
                 << "\",\"value_float\":" << valueFloat
                 << ",\"value_int\":" << valueInt
                 << ",\"spell_id\":" << spellId
                 << ",\"suppressed_count\":" << suppressedRepeatableEvents
                 << ",\"dedupe_mode\":\"first_edge_heartbeat\"}";
    dataset.outcome_json = eventOutcome.str();
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_events\"}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    CharacterDatabase.EscapeString(event);
    CharacterDatabase.EscapeString(res);
    CharacterDatabase.EscapeString(dbRes);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(canonical);
    uint32 targetEntry = 0;
    uint64 targetGuid = 0;
    if (target)
    {
        targetGuid = target->GetGUID().GetCounter();
        if (Creature const* creature = target->ToCreature())
            targetEntry = creature->GetEntry();
    }

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_events (schema_version, feature_schema_version, experiment_id, run_id, bot_guid, brain_version, clip_id, map_id, zone_id, area_id, x, y, z, level, event_type, target_guid, target_entry, spell_id, result, value_float, value_int, raw_json, semantic_json, canonical_event_json) "
        "VALUES ('%s', '%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %u, %u, %u, %f, %f, %f, %u, '%s', " UI64FMTD ", %u, %u, '%s', %f, %u, '%s', '%s', '%s')",
        BotDatasetEvent::SchemaVersion, BotDatasetEvent::DefaultFeatureSchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), clipSql.c_str(), bot->GetMapId(), bot->GetZoneId(), bot->GetAreaId(),
        bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), uint32(bot->getLevel()), event.c_str(), targetGuid, targetEntry, spellId, dbRes.c_str(), valueFloat, valueInt, raw.c_str(), semantic.c_str(), canonical.c_str());

    UpdateSemanticStatsFromEvent(bot, target, eventType, result, valueFloat, valueInt, spellId, semanticJson);
    if (eventName == "resurrected" || eventName == "death_recovery_failed" || eventName == "teleport_fallback_used")
    {
        std::string mode = result && *result ? result : Cohort().Config.DeathRecoveryMode;
        std::string features = BuildEmbeddingFeaturesJson(bot, target, "recovery", BotExperienceLearningPolicy::StableKey(mode), mode.c_str());
        UpdateSemanticOutcomeStats(bot, "recovery", BotExperienceLearningPolicy::StableKey(mode), eventType, result, valueFloat, 0.0f, EventLooksFailure(eventType, result), features.c_str());
    }
    if (policy.writeReplay)
        RecordPolicyReplay(state, bot, target, policyInput, rawJson, semanticJson);
}

void BotWorldPopulationMgr::RecordDecision(WorldBotState& state, Player* bot, char const* situation, char const* action, Unit const* target, char const* rawJson, char const* semanticJson, std::vector<BotActivityScore> const& activityScores, BotActivityScore const& chosenActivity, BotRolePowerBreakdown const& power, bool failure, bool rare)
{
    if (!bot)
        return;

    ++state.Sequence;
    uint64 nowMs = NowMs();
    std::string previousSituation = state.LastDecisionSituation;
    std::string previousAction = state.LastDecisionAction;
    ObjectGuid previousTargetGuid = state.LastDecisionTargetGuid;
    ObjectGuid currentTargetGuid = target ? target->GetGUID() : ObjectGuid::Empty;
    bool sameDecision = previousSituation == (situation ? situation : "idle") && previousAction == (action ? action : "wait");
    state.ConsecutiveSameDecisionCount = sameDecision ? state.ConsecutiveSameDecisionCount + 1 : 1;
    bool idleDecision = (!action || std::string(action) == "wait" || std::string(action) == "wander" || std::string(action) == "rest")
        && (!situation || std::string(situation) == "idle" || std::string(situation) == "travel");
    state.IdleDecisionRepeatCount = idleDecision ? state.IdleDecisionRepeatCount + 1 : 0;
    if (state.TargetChurnWindowStartMs == 0 || nowMs - state.TargetChurnWindowStartMs > 30000)
    {
        state.TargetChurnWindowStartMs = nowMs;
        state.TargetChurnCount = 0;
    }
    if (!previousTargetGuid.IsEmpty() && !currentTargetGuid.IsEmpty() && previousTargetGuid != currentTargetGuid)
        ++state.TargetChurnCount;
    else if (currentTargetGuid.IsEmpty() && nowMs - state.TargetChurnWindowStartMs > 5000)
        state.TargetChurnCount = 0;
    state.LastDecisionTickMs = nowMs;
    state.LastDecisionSituation = situation ? situation : "idle";
    state.LastDecisionAction = action ? action : "wait";
    state.LastDecisionActivity = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    state.LastDecisionResult = failure ? "failed" : "ok";
    state.LastDecisionReason = failure ? "decision_failure" : "";
    state.LastDecisionTargetGuid = currentTargetGuid;
    if (!state.LastDecisionQuestId)
        state.LastDecisionQuestId = state.QuestWork.ActiveQuestId ? state.QuestWork.ActiveQuestId : state.NewlyAcceptedQuestId;
    state.LastDecisionDistanceMoved = state.DistanceMovedSinceLastDecision;
    state.DistanceMovedSinceLastDecision = 0.0f;
    std::string role = GetDungeonRole(bot);
    BotClassSpecActionProfile decisionProfile = BotClassSpecActionProfileStore::Build(bot, role.c_str());
    RoleSaturationState decisionSaturation = BuildRoleSaturationState(bot, target, role.c_str());
    auto saturationItr = Party().LastSaturationByBot.find(bot->GetGUID().GetCounter());
    if (saturationItr != Party().LastSaturationByBot.end())
        decisionSaturation = saturationItr->second;
    state.LastClassSpecProfile = decisionProfile.EmbeddingJson();
    state.LastRoleGoal = BotProgressionGoalPolicy::RoleGoal(role);
    state.LastRoleSaturationStateJson = decisionSaturation.ToJson();
    state.LastRecommendedBalanceMode = BotRoleSaturationPolicy::ToString(decisionSaturation.RecommendedBalanceMode);
    state.LastSaturationReason = decisionSaturation.SaturationReason;
    state.LastProgressionReason = BotProgressionGoalPolicy::ProgressionReason(bot, BotLongTermProgressionBrain::ToString(chosenActivity.Activity), situation);
    state.LastProfessionGoal = BotProgressionGoalPolicy::ProfessionGoalJson(bot, role, BotLongTermProgressionBrain::ToString(chosenActivity.Activity));
    auto categoryItr = Party().LastActionCategoryByBot.find(bot->GetGUID().GetCounter());
    state.LastActionCategory = categoryItr != Party().LastActionCategoryByBot.end() ? categoryItr->second : (action && std::string(action).find("loot") != std::string::npos ? "loot" : (action && std::string(action).find("quest") != std::string::npos ? "quest_interact" : "wait"));
    auto maskItr = Party().LastCombatMaskByBot.find(bot->GetGUID().GetCounter());
    state.LastValidActionMaskJson = maskItr != Party().LastCombatMaskByBot.end() ? maskItr->second : "{}";
    auto chosenItr = Party().LastChosenCombatByBot.find(bot->GetGUID().GetCounter());
    state.LastChosenActionJson = chosenItr != Party().LastChosenCombatByBot.end() ? chosenItr->second : "{}";
    RecordDecisionFingerprintMemory(state, bot, situation, action, chosenActivity, failure);
    RecordDecisionTrace(state, situation, action, target, state.LastDecisionQuestId,
        failure ? "failed" : "ok", failure ? "decision_failure" : "",
        IsRepeatableTraceDecision(failure, rare, action));

    if (!Cohort().RunId || !Cohort().Config.RecordDecisions)
        return;

    ++Cohort().Metrics.Decisions;
    if (failure)
        ++Cohort().Metrics.Failures;

    Cohort().TelemetryBuffer.Observe(bot, situation, action, rawJson, semanticJson);

    // An invalid profile resolver is a diagnostic state, not a gameplay
    // transition. Preserve every decision in counters, but avoid inserting an
    // identical diagnostic row on every tick. The trace applies the same edge
    // and five-second heartbeat rule to repeatable movement/hold decisions;
    // failures and rare/transition decisions bypass that coalescing.
    uint32 suppressedDiagnosticDecisions = 0;
    bool const repeatableDiagnosticDecision = !failure && !rare
        && (state.LastCombatAttempt.Reason == "no_valid_profile_action"
            || state.LastCombatAttempt.Result == "no_valid_profile_action"
            || (state.Blocked && state.LastDecisionHandler == "stuck_blocked"));
    if (repeatableDiagnosticDecision)
    {
        std::ostringstream diagnosticKey;
        diagnosticKey << (situation ? situation : "idle") << '|'
                      << (action ? action : "wait") << '|'
                      << currentTargetGuid.GetCounter() << '|'
                      << state.LastCombatAttempt.Reason << '|'
                      << state.ValidationRouteGeneration;
        std::string const key = diagnosticKey.str();
        if (state.LastPersistedDiagnosticDecisionKey == key)
        {
            ++state.SuppressedDiagnosticDecisionCount;
            if (state.LastPersistedDiagnosticDecisionMs
                && nowMs - state.LastPersistedDiagnosticDecisionMs < RepeatableDiagnosticEventHeartbeatMs)
                return;

            suppressedDiagnosticDecisions = state.SuppressedDiagnosticDecisionCount;
            state.SuppressedDiagnosticDecisionCount = 0;
            state.LastPersistedDiagnosticDecisionMs = nowMs;
        }
        else
        {
            state.LastPersistedDiagnosticDecisionKey = key;
            state.LastPersistedDiagnosticDecisionMs = nowMs;
            state.SuppressedDiagnosticDecisionCount = 0;
        }
    }

    BotTelemetryPolicyInput policyInput = BuildTelemetryPolicyInput("decision", failure ? "failed" : "ok", situation ? situation : "idle", target, 0, 0, 0, failure ? -1.0f : chosenActivity.Score, 0, failure, rare, action && std::string(action) == "unstuck");
    BotTelemetryPolicyDecision policy = BotTelemetryPolicy::DecideDecision(policyInput, GetTelemetryPolicyConfig(), state.Sequence);
    if (!policy.writeDecision)
        return;

    uint64 clipId = MaybeCaptureTelemetryClip(bot, target, policyInput, policy, rawJson, semanticJson);
    if (!clipId)
        clipId = Cohort().TelemetryBuffer.GetActiveClipId(bot->GetGUID());

    std::string clipSql = clipId ? std::to_string(clipId) : "NULL";

    std::string raw = rawJson ? rawJson : "{}";
    std::string semantic = semanticJson ? semanticJson : "{}";
    std::string activityCandidateJson = BuildActivityCandidatesJson(activityScores);
    std::string combatMaskJson = state.LastValidActionMaskJson.empty() || state.LastValidActionMaskJson == "{}"
        ? BotClassSpecActionProfileStore::CandidateMaskJson(std::vector<BotActionCandidate>(), decisionProfile, state.LastRoleGoal.c_str(), state.LastRoleSaturationStateJson.c_str())
        : state.LastValidActionMaskJson;
    std::ostringstream candidateJsonOut;
    std::string const decisionKernelJson = state.LastDecisionKernelJson.empty()
        ? "{}" : state.LastDecisionKernelJson;
    candidateJsonOut << "{\"schema\":\"bot_decision_mask_v3\""
                     << ",\"activity_candidates\":" << activityCandidateJson
                     << ",\"combat_action_mask\":" << combatMaskJson
                     << ",\"decision_kernel\":" << decisionKernelJson
                     << ",\"class_spec_profile\":" << state.LastClassSpecProfile
                     << ",\"role_goal\":\"" << JsonEscape(state.LastRoleGoal) << "\""
                     << ",\"role_saturation_state_json\":" << state.LastRoleSaturationStateJson
                     << ",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode) << "\""
                     << ",\"saturation_reason\":\"" << JsonEscape(state.LastSaturationReason) << "\""
                     << ",\"progression_reason\":" << state.LastProgressionReason
                     << ",\"profession_goal\":" << state.LastProfessionGoal << "}";
    std::string candidateJson = candidateJsonOut.str();
    uint64 replayId = Cohort().PolicyModelConfig.Enabled && !Cohort().PolicyModelConfig.Version.empty()
        ? RecordDecisionReplay(state, bot, target, situation, action, rawJson, semanticJson, candidateJson.c_str(), chosenActivity, failure)
        : 0;
    PolicyModelTrace modelTrace = BuildPolicyModelTrace(activityScores, chosenActivity, bot, clipId, replayId);
    std::ostringstream chosen;
    std::string structuredChosen = state.LastChosenActionJson.empty() || state.LastChosenActionJson == "{}"
        ? BotClassSpecActionProfileStore::ChosenActionJson(nullptr, decisionProfile, state.LastRoleGoal.c_str(), state.LastRecommendedBalanceMode.c_str(), decisionSaturation.ExperimentConfidence)
        : state.LastChosenActionJson;
    chosen << "{\"action\":\"" << JsonEscape(action ? action : "wait") << "\""
           << ",\"structured_action\":" << structuredChosen
           << ",\"decision_kernel\":" << decisionKernelJson
           << ",\"action_category\":\"" << JsonEscape(state.LastActionCategory.empty() ? "wait" : state.LastActionCategory) << "\""
           << ",\"class_spec_profile\":" << state.LastClassSpecProfile
           << ",\"role_goal\":\"" << JsonEscape(state.LastRoleGoal) << "\""
           << ",\"role_saturation_state_json\":" << state.LastRoleSaturationStateJson
           << ",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode) << "\""
           << ",\"saturation_reason\":\"" << JsonEscape(state.LastSaturationReason) << "\"";
    if (target)
        chosen << ",\"target_guid\":" << target->GetGUID().GetCounter();
    chosen << ",\"activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
           << ",\"activity_score\":" << chosenActivity.Score
           << ",\"expected_power_gain\":" << chosenActivity.ExpectedPowerGain
           << ",\"learned_score\":" << chosenActivity.LearnedScore
           << ",\"learned_penalty\":" << chosenActivity.LearnedPenalty
           << ",\"learned_reason\":\"" << JsonEscape(chosenActivity.LearnedReason) << "\""
           << ",\"sample_count\":" << chosenActivity.LearnedSampleCount
           << ",\"danger_score\":" << chosenActivity.LearnedDangerScore
           << ",\"progression_value\":" << chosenActivity.LearnedProgressionValue
           << ",\"confidence\":" << chosenActivity.LearnedConfidence
           << ",\"quest_phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
           << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
           << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
           << ",\"objective_type\":\"" << JsonEscape(state.QuestWork.ObjectiveType) << "\""
           << ",\"required_entry\":" << (state.QuestWork.RequiredEntry > 0 ? uint32(state.QuestWork.RequiredEntry) : 0)
           << ",\"required_item\":" << state.QuestWork.RequiredItem
           << ",\"required_spell\":" << state.QuestWork.RequiredSpell
           << ",\"progression_reason\":" << state.LastProgressionReason
           << ",\"profession_goal\":" << state.LastProfessionGoal
            << ",\"next_expected_action\":\"" << JsonEscape(state.LastNextExpectedAction) << "\"";
    chosen << ",\"suppressed_diagnostic_decisions\":" << suppressedDiagnosticDecisions;
    if (Cohort().PolicyModelConfig.Enabled && !Cohort().PolicyModelConfig.Version.empty())
        chosen << ",\"policy_model\":" << modelTrace.Json;
    chosen << "}";
    std::ostringstream outcome;
    outcome << "{\"main_goal\":\"increase_character_power\""
            << ",\"decision_kernel\":" << decisionKernelJson
            << ",\"current_stage\":\"" << JsonEscape(state.ProgressionStage) << "\""
            << ",\"chosen_activity\":\"" << JsonEscape(BotLongTermProgressionBrain::ToString(chosenActivity.Activity)) << "\""
            << ",\"expected_value\":" << chosenActivity.Score
            << ",\"learned_score\":" << chosenActivity.LearnedScore
            << ",\"learned_penalty\":" << chosenActivity.LearnedPenalty
            << ",\"learned_reason\":\"" << JsonEscape(chosenActivity.LearnedReason) << "\""
            << ",\"sample_count\":" << chosenActivity.LearnedSampleCount
            << ",\"danger_score\":" << chosenActivity.LearnedDangerScore
            << ",\"progression_value\":" << chosenActivity.LearnedProgressionValue
            << ",\"confidence\":" << chosenActivity.LearnedConfidence
            << ",\"role_power_score\":" << power.Total
            << ",\"power_delta\":" << (power.Total - state.ActivityStartPower)
            << ",\"progress_before\":" << state.QuestWork.ProgressBefore
            << ",\"progress_after\":" << state.QuestWork.ProgressAfter
            << ",\"loot_result\":\"" << JsonEscape(state.LastLootResult) << "\""
            << ",\"loot_items_count\":" << state.LastLootItemsCount
            << ",\"loot_money\":" << state.LastLootMoney
            << ",\"loot_state_cleared\":" << (state.LastLootStateCleared ? "true" : "false")
            << ",\"no_progress_reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\""
            << ",\"cooldown_reason\":\"" << JsonEscape(state.QuestWork.FailedReason) << "\""
            << ",\"dummy_allowed_by_quest\":" << (state.CurrentDummyAllowedByQuest ? "true" : "false")
            << ",\"objective_state\":\"increase_character_power\""
            << ",\"zone_quest_portfolio\":" << BotProgressionGoalPolicy::QuestPortfolioSummaryJson(state.QuestWork.ActiveQuestId ? 1 : 0, state.ActiveQuestClusterId, state.QuestWork.Phase.c_str(), state.LastNoQuestReason.c_str())
            << ",\"role_goal\":\"" << JsonEscape(state.LastRoleGoal) << "\""
            << ",\"role_saturation_state_json\":" << state.LastRoleSaturationStateJson
            << ",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode) << "\""
            << ",\"saturation_reason\":\"" << JsonEscape(state.LastSaturationReason) << "\""
           << ",\"progression_reason\":" << state.LastProgressionReason
           << ",\"profession_goal\":" << state.LastProfessionGoal
            << ",\"reject_reason\":\"" << JsonEscape(state.LastCombatRejectReason) << "\""
            << ",\"next_expected_action\":\"" << JsonEscape(state.LastNextExpectedAction) << "\""
            << ",\"suppressed_diagnostic_decisions\":" << suppressedDiagnosticDecisions;
    if (Cohort().PolicyModelConfig.Enabled && !Cohort().PolicyModelConfig.Version.empty())
        outcome << ",\"policy_model\":" << modelTrace.Json;
    outcome << "}";

    CharacterDatabase.EscapeString(raw);
    CharacterDatabase.EscapeString(semantic);
    std::string chosenJson = chosen.str();
    std::string outcomeJson = outcome.str();
    std::string brain = Cohort().Config.BrainVersion;
    BotDatasetEvent dataset;
    dataset.feature_schema_version = Cohort().PolicyModelConfig.FeatureSchemaVersion.empty() ? BotDatasetEvent::DefaultFeatureSchemaVersion : Cohort().PolicyModelConfig.FeatureSchemaVersion;
    dataset.run_id = Cohort().RunId;
    dataset.experiment_id = std::to_string(Cohort().ExperimentId);
    dataset.episode_id = Cohort().RunId;
    dataset.bot_guid = bot->GetGUID();
    dataset.bot_role = GetDungeonRole(bot);
    dataset.bot_level = uint32(bot->getLevel());
    dataset.policy_source = Cohort().PolicyModelConfig.Enabled && !Cohort().PolicyModelConfig.Version.empty() ? WorldPolicySource(Cohort().PolicyModelConfig, true) : BotPolicySource::Heuristic;
    dataset.policy_version = WorldPolicyVersion(Cohort().PolicyModelConfig, Cohort().Config.BrainVersion);
    dataset.timestamp_ms = nowMs;
    dataset.tick_id = state.Sequence;
    dataset.domain = "world_decision";
    dataset.situation = situation ? situation : "idle";
    dataset.observation_json = raw;
    dataset.semantic_json = semantic;
    dataset.valid_action_mask_json = candidateJson;
    dataset.chosen_action_json = chosenJson;
    dataset.action_result = failure ? "failed" : "ok";
    dataset.outcome_json = outcomeJson;
    dataset.quality_flags_json = "{\"source\":\"experiment_bot_decisions\",\"failure\":" + std::string(failure ? "true" : "false") + ",\"rare\":" + std::string(rare ? "true" : "false") + ",\"class_spec_profile\":" + decisionProfile.QualityFlagsJson() + "}";
    std::string canonical = dataset.Validate() ? dataset.ToJson() : "";
    CharacterDatabase.EscapeString(candidateJson);
    CharacterDatabase.EscapeString(chosenJson);
    CharacterDatabase.EscapeString(outcomeJson);
    CharacterDatabase.EscapeString(brain);
    CharacterDatabase.EscapeString(canonical);
    std::string modelVersion = Cohort().PolicyModelConfig.Enabled && !Cohort().PolicyModelConfig.Version.empty() ? Cohort().PolicyModelConfig.Version : "";
    std::string featureSchemaVersion = Cohort().PolicyModelConfig.FeatureSchemaVersion.empty() ? BotDatasetEvent::DefaultFeatureSchemaVersion : Cohort().PolicyModelConfig.FeatureSchemaVersion;
    CharacterDatabase.EscapeString(modelVersion);
    CharacterDatabase.EscapeString(featureSchemaVersion);
    std::string sit = situation ? situation : "idle";
    CharacterDatabase.EscapeString(sit);
    std::string currentActivity = BotLongTermProgressionBrain::ToString(chosenActivity.Activity);
    CharacterDatabase.EscapeString(currentActivity);
    std::string modelVersionSql = modelVersion.empty() ? "NULL" : ("'" + modelVersion + "'");
    std::string featureSchemaSql = "'" + featureSchemaVersion + "'";
    std::string modelScoreSql = modelTrace.Enabled ? std::to_string(modelTrace.ModelScore) : "NULL";
    std::string modelRankSql = modelTrace.Enabled ? std::to_string(modelTrace.ModelRank) : "NULL";
    std::string modelFeaturesHashSql = modelTrace.Enabled ? std::to_string(modelTrace.FeaturesHash) : "NULL";
    std::string replaySql = replayId ? std::to_string(replayId) : "NULL";

    CharacterDatabase.DirectPExecute("INSERT INTO experiment_bot_decisions (schema_version, experiment_id, run_id, bot_guid, brain_version, model_version, feature_schema_version, model_score, model_rank, model_features_hash, clip_id, situation_type, current_activity, current_goal, map_id, zone_id, area_id, x, y, z, raw_state_json, semantic_state_json, candidate_actions_json, chosen_action_json, outcome_json, canonical_event_json, reward, is_failure, is_rare_state, replay_key) "
        "VALUES ('%s', " UI64FMTD ", " UI64FMTD ", %u, '%s', %s, %s, %s, %s, %s, %s, '%s', '%s', 'increase_character_power', %u, %u, %u, %f, %f, %f, '%s', '%s', '%s', '%s', '%s', '%s', %f, %u, %u, %s)",
        BotDatasetEvent::SchemaVersion,
        Cohort().ExperimentId, Cohort().RunId, state.Guid.GetCounter(), brain.c_str(), modelVersionSql.c_str(), featureSchemaSql.c_str(), modelScoreSql.c_str(), modelRankSql.c_str(), modelFeaturesHashSql.c_str(), clipSql.c_str(), sit.c_str(), currentActivity.c_str(), bot->GetMapId(), bot->GetZoneId(),
        bot->GetAreaId(), bot->GetPositionX(), bot->GetPositionY(), bot->GetPositionZ(), raw.c_str(), semantic.c_str(), candidateJson.c_str(), chosenJson.c_str(),
        outcomeJson.c_str(), canonical.c_str(), failure ? -1.0f : chosenActivity.Score, failure ? 1 : 0, rare ? 1 : 0, replaySql.c_str());

    std::string areaFeatures = BuildEmbeddingFeaturesJson(bot, target, "area", bot->GetAreaId(), situation ? situation : "decision");
    UpdateSemanticOutcomeStats(bot, "area", bot->GetAreaId(), situation, failure ? "failed" : "sampled", failure ? -1.0f : chosenActivity.Score, power.Total - state.ActivityStartPower, failure, areaFeatures.c_str());
}

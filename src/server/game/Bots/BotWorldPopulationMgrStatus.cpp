#include "Bots/BotWorldPopulationMgr.h"

#include "CellImpl.h"
#include "Creature.h"
#include "CreatureGroups.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GameObject.h"
#include "Group.h"
#include "GridNotifiersImpl.h"
#include "Map.h"
#include "MotionMaster.h"
#include "ObjectAccessor.h"
#include "Pet.h"
#include "Player.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Quests/QuestDef.h"
#include "SpellInfo.h"
#include "SpellMgr.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <iomanip>
#include <limits>
#include <sstream>
#include <string>
#include <tuple>
#include <vector>

namespace
{
uint64 NowMs()
{
    return uint64(std::chrono::duration_cast<std::chrono::milliseconds>(
        GameTime::GetGameTimeSystemPoint().time_since_epoch()).count());
}

char const* RuntimeModeName(BotWorldRuntimeMode mode)
{
    switch (mode)
    {
        case BotWorldRuntimeMode::AlwaysOnAutonomy: return "always_on_autonomy";
        case BotWorldRuntimeMode::CalibrationFixture: return "calibration_fixture";
        case BotWorldRuntimeMode::ReplayFixture: return "replay_fixture";
        case BotWorldRuntimeMode::ManualExperiment: return "manual_experiment";
    }
    return "unknown";
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
}

BotWorldStatus BotWorldPopulationMgr::GetStatus() const
{
    BotWorldStatus status = Cohort().Metrics;
    status.Active = Cohort().Active;
    status.Mode = Cohort().RuntimeMode;
    status.ActiveBots = uint32(Party().Bots.size());
    status.DurationSeconds = Cohort().ElapsedMs / 1000;
    return status;
}

std::string BotWorldPopulationMgr::BuildValidationRouteEvidenceJson(std::vector<ValidationRouteEvidence> const& evidence) const
{
    std::ostringstream json;
    json << "[";
    for (size_t index = 0; index < evidence.size(); ++index)
    {
        if (index)
            json << ",";
        ValidationRouteEvidence const& row = evidence[index];
        json << "{\"route_node_id\":\"" << JsonEscape(row.NodeId)
             << "\",\"route_generation\":" << row.Generation
             << ",\"route_kind\":\"" << JsonEscape(row.Kind)
             << "\",\"target_id\":" << row.TargetGuid.GetRawValue()
             << ",\"target_entry\":" << row.TargetEntry
             << ",\"result\":\"" << JsonEscape(row.Reason) << "\"}";
    }
    json << "]";
    return json.str();
}

std::string BotWorldPopulationMgr::GetStatusJson() const
{
    std::string const attemptFailure =
        Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId
        ? Cohort().ValidationAttemptFailureReason : std::string();
    BotWorldStatus status = GetStatus();
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_status\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
         << "\",\"server_epoch\":" << _serverEpoch
         << ",\"attempt_id\":" << Cohort().AttemptId
         << ",\"profile_generation\":" << Cohort().PinnedProfileGeneration
         << ",\"profile_content_hash\":\"" << JsonEscape(Cohort().PinnedProfileContentHash)
         << "\",\"lease_count\":" << Cohort().RosterLeases.size()
         << ",\"experiment\":\"" << JsonEscape(status.Name)
         << "\",\"run\":" << status.RunId
         << ",\"mode\":\"" << RuntimeModeName(status.Mode) << "\""
         << ",\"non_certifying_assistance\":" << (Cohort().NonCertifyingAssistance ? "true" : "false")
         << ",\"active_profile\":" << (Cohort().SelectedProfileName.empty() ? "null" : ("\"" + JsonEscape(Cohort().SelectedProfileName) + "\""))
         << ",\"loaded_profile_count\":" << Cohort().RuntimeProfiles.size()
         << ",\"profile_manifest_path\":\"" << JsonEscape(Cohort().ProfileManifestPath) << "\""
         << ",\"profile_manifest_load_error\":\"" << JsonEscape(Cohort().ProfileManifestLoadError) << "\""
         << ",\"pool_tag_filter\":\"" << JsonEscape(Cohort().Config.PoolTagFilter) << "\""
         << ",\"exact_party_class_specs\":[";
    for (size_t index = 0; index < Cohort().Config.PoolClassSpecFilter.size(); ++index)
    {
        if (index)
            json << ',';
        json << '\"' << JsonEscape(Cohort().Config.PoolClassSpecFilter[index]) << '\"';
    }
    json << "]"
         << ",\"brain\":\"" << JsonEscape(Cohort().Config.BrainVersion)
         << "\",\"active\":" << (status.Active ? "true" : "false")
         << ",\"bots\":" << status.ActiveBots
         << ",\"target_bots\":" << status.TargetBots
         << ",\"duration_seconds\":" << status.DurationSeconds
         << ",\"kills\":" << status.Kills
         << ",\"deaths\":" << status.Deaths
         << ",\"gear_upgrades\":" << status.GearUpgrades
         << ",\"quests_accepted\":" << status.QuestsAccepted
         << ",\"quests_completed\":" << status.QuestsCompleted
         << ",\"quest_objective_progress\":" << status.QuestObjectiveProgress
         << ",\"raid_boss_kills\":" << status.RaidBossKills
         << ",\"heroic_raid_boss_kills\":" << status.HeroicRaidBossKills
         << ",\"raid_telemetry_events\":" << status.RaidTelemetryEvents
         << ",\"role_assignments\":" << status.RoleAssignments
         << ",\"group_formations\":" << status.GroupFormations
         << ",\"raid_formations\":" << status.RaidFormations
         << ",\"target_priority_decisions\":" << status.TargetPriorityDecisions
         << ",\"interrupt_success\":" << status.InterruptSuccess
         << ",\"assigned_interrupt_success\":" << status.AssignedInterruptSuccess
         << ",\"healer_assignments\":" << status.HealerAssignments
         << ",\"tank_positioning\":" << status.TankPositioning
         << ",\"regroups\":" << status.Regroups
         << ",\"recovery_events\":" << status.RecoveryEvents
         << ",\"instance_resets\":" << status.InstanceResets
         << ",\"raid_runtime\":" << BuildRaidRuntimeJson()
         << ",\"segment_counts\":" << Cohort().ExperimentCoordinator.GetCountsJson()
         << ",\"validation_route\":{\"enabled\":" << (Cohort().Config.ValidationRouteEnable ? "true" : "false")
         << ",\"manifest_path\":\"" << JsonEscape(Cohort().Config.ValidationRouteManifestPath) << "\""
         << ",\"advance_mode\":\"" << JsonEscape(Cohort().Config.ValidationRouteAdvanceMode) << "\""
         << ",\"manifest_index\":" << Party().ValidationRouteManifestIndex
         << ",\"manifest_count\":" << Party().ValidationRouteManifest.size()
         << ",\"generation\":" << Party().ValidationRouteGeneration
         << ",\"manifest_complete\":" << (Party().ValidationRouteManifestComplete ? "true" : "false")
         << ",\"terminal_evidence\":" << BuildValidationRouteEvidenceJson(Party().ValidationRouteTerminalEvidence)
         << ",\"boss_death_evidence\":" << BuildValidationRouteEvidenceJson(Party().ValidationRouteBossDeathEvidence)
         << ",\"contamination_evidence\":" << BuildValidationRouteEvidenceJson(Party().ValidationRouteContaminationEvidence)
         << ",\"manifest_load_error\":\"" << JsonEscape(Party().ValidationRouteManifestLoadError) << "\""
         << ",\"scenario_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteScenarioId) << "\""
         << ",\"node_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
         << ",\"label\":\"" << JsonEscape(Cohort().Config.ValidationRouteLabel) << "\""
         << ",\"kind\":\"" << JsonEscape(Cohort().Config.ValidationRouteKind) << "\"}"
         << ",\"stuck\":" << status.StuckEvents
         << ",\"decisions\":" << status.Decisions
         << ",\"failures\":" << status.Failures
         << ",\"failure_reason\":"
         << (attemptFailure.empty() ? "null"
             : ("\"" + JsonEscape(attemptFailure) + "\"")) << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetSummaryJson() const
{
    BotWorldStatus status = GetStatus();
    float hours = status.DurationSeconds ? float(status.DurationSeconds) / 3600.0f : 0.0f;
    std::ostringstream json;
    json << "{\"bots\":" << status.ActiveBots
         << ",\"target_bots\":" << status.TargetBots
         << ",\"duration_minutes\":" << (float(status.DurationSeconds) / 60.0f)
         << ",\"total_kills\":" << status.Kills
         << ",\"total_deaths\":" << status.Deaths
         << ",\"kills_per_hour\":" << (hours > 0.0f ? float(status.Kills) / hours : 0.0f)
         << ",\"deaths_per_hour\":" << (hours > 0.0f ? float(status.Deaths) / hours : 0.0f)
         << ",\"stuck_events\":" << status.StuckEvents
         << ",\"quests_accepted\":" << status.QuestsAccepted
         << ",\"quests_completed\":" << status.QuestsCompleted
         << ",\"quest_objective_progress\":" << status.QuestObjectiveProgress
         << ",\"gear_upgrades\":" << status.GearUpgrades
         << ",\"raid_boss_kills\":" << status.RaidBossKills
         << ",\"heroic_raid_boss_kills\":" << status.HeroicRaidBossKills
         << ",\"raid_telemetry_events\":" << status.RaidTelemetryEvents
         << ",\"role_assignments\":" << status.RoleAssignments
         << ",\"group_formations\":" << status.GroupFormations
         << ",\"raid_formations\":" << status.RaidFormations
         << ",\"target_priority_decisions\":" << status.TargetPriorityDecisions
         << ",\"interrupt_success\":" << status.InterruptSuccess
         << ",\"assigned_interrupt_success\":" << status.AssignedInterruptSuccess
         << ",\"healer_assignments\":" << status.HealerAssignments
         << ",\"tank_positioning\":" << status.TankPositioning
         << ",\"regroups\":" << status.Regroups
         << ",\"recovery_events\":" << status.RecoveryEvents
         << ",\"instance_resets\":" << status.InstanceResets
         << ",\"segment_counts\":" << Cohort().ExperimentCoordinator.GetCountsJson()
         << ",\"bot_learning\":{\"enable\":" << (Cohort().LearningConfig.Enabled ? "true" : "false")
         << ",\"min_samples_for_strong_bias\":" << Cohort().LearningConfig.MinSamplesForStrongBias
         << ",\"danger_penalty_weight\":" << Cohort().LearningConfig.DangerPenaltyWeight
         << ",\"progression_reward_weight\":" << Cohort().LearningConfig.ProgressionRewardWeight
         << ",\"recent_failure_penalty_weight\":" << Cohort().LearningConfig.RecentFailurePenaltyWeight
         << ",\"exploration_novelty_weight\":" << Cohort().LearningConfig.ExplorationNoveltyWeight
         << ",\"allow_global_memory_fallback\":" << (Cohort().LearningConfig.AllowGlobalMemoryFallback ? "true" : "false") << "}"
         << ",\"decisions\":" << status.Decisions
         << ",\"failures_recorded\":" << status.Failures << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetBotDiagnosisJson(std::string const& selector)
{
    std::string const attemptFailure =
        Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId
        ? Cohort().ValidationAttemptFailureReason : std::string();
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_diagnose\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
         << "\",\"diagnosis_schema_version\":1,\"bots\":[";
    bool emitted = false;
    for (WorldBotState& state : Party().Bots)
    {
        Player* bot = GetLoadedBot(state);
        if (!selector.empty() && selector != "all")
        {
            if (!bot)
                continue;
            if (selector != std::to_string(state.Guid.GetCounter()) && selector != bot->GetName())
                continue;
        }

        if (bot && !bot->IsInWorld() && Cohort().Config.ValidationRouteEnable)
        {
            state.LastDecisionResult = "loaded_bot_not_in_world";
            state.LastDecisionReason = "validation_same_instance_reattach_failed";
        }

        if (emitted)
            json << ",";
        emitted = true;
        json << "{\"identity\":{\"bot_guid\":" << state.Guid.GetCounter()
             << ",\"bot_name\":\"" << JsonEscape(bot ? bot->GetName() : "") << "\"}"
             << ",\"snapshot\":" << BuildBotDecisionSnapshotJson(state, bot)
             << ",\"diagnosis\":" << BuildBotDiagnosisObjectJson(state, bot) << "}";

        if (!selector.empty() && selector != "all")
            break;
    }

    json << "]"
         << ",\"combat_metrics\":" << BuildCombatMetricsJson()
         << ",\"raid_runtime\":" << BuildRaidRuntimeJson(true);
    if (!attemptFailure.empty())
        json << ",\"failure_reason\":\"" << JsonEscape(attemptFailure) << "\"";
    else if (!emitted)
        json << ",\"failure_reason\":\"" << JsonEscape(Cohort().LastPopulationFailureReason.empty() ? "no_matching_bot" : Cohort().LastPopulationFailureReason) << "\"";
    else
        json << ",\"failure_reason\":null";
    json << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetBotTraceJson(std::string const& selector, uint32 limit, bool delta) const
{
    uint32 normalizedLimit = limit ? std::min<uint32>(limit, 128) : 20;
    std::string const attemptFailure =
        Cohort().ValidationAttemptFailureAttemptId == Cohort().AttemptId
        ? Cohort().ValidationAttemptFailureReason : std::string();

    if (selector.empty() || selector == "all")
    {
        std::ostringstream json;
        json << "{\"ok\":true,\"action\":\"botauto_trace\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
             << "\",\"trace_schema_version\":1"
             << ",\"selector\":\"" << JsonEscape(selector.empty() ? "all" : selector) << "\""
             << ",\"limit\":" << normalizedLimit
             << ",\"validation_route\":{\"manifest_index\":" << Party().ValidationRouteManifestIndex
             << ",\"manifest_count\":" << Party().ValidationRouteManifest.size()
             << ",\"node_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
             << ",\"label\":\"" << JsonEscape(Cohort().Config.ValidationRouteLabel) << "\""
             << ",\"kind\":\"" << JsonEscape(Cohort().Config.ValidationRouteKind) << "\"}"
             << ",\"raid_runtime\":" << BuildRaidRuntimeJson(true)
             << ",\"bots\":[";

        bool emitted = false;
        for (WorldBotState const& state : Party().Bots)
        {
            Player* bot = GetLoadedBot(state);
            if (emitted)
                json << ",";
            emitted = true;
            json << "{\"bot_guid\":" << state.Guid.GetCounter()
                 << ",\"bot_name\":\"" << JsonEscape(bot ? bot->GetName() : "") << "\""
                 << ",\"entries\":";
            if (!delta)
                json << BuildBotTraceEntriesJson(state, normalizedLimit);
            else
            {
                auto const cursorItr = Party().TraceExportCursorByGuid.find(state.Guid.GetCounter());
                bool const cursorInitialized = cursorItr != Party().TraceExportCursorByGuid.end();
                uint64 const cursor = cursorInitialized ? cursorItr->second : 0;
                uint64 cursorAfter = cursor;
                bool gap = false;
                uint64 expected = cursor == std::numeric_limits<uint64>::max() ? cursor : cursor + 1;
                bool sawNewEntry = false;
                // A bounded ring may overwrite the first unexported row.
                // Fail closed even on the first delta poll instead of
                // silently starting at the oldest retained row.
                for (auto const& entry : state.DecisionTrace)
                {
                    if (entry.Sequence <= cursor)
                        continue;
                    if (!sawNewEntry)
                    {
                        sawNewEntry = true;
                        if ((!cursorInitialized && entry.Sequence != 1) || (cursorInitialized && entry.Sequence != expected))
                        {
                            gap = true;
                            break;
                        }
                    }
                    else if (entry.Sequence != expected)
                    {
                        gap = true;
                        break;
                    }
                    expected = entry.Sequence == std::numeric_limits<uint64>::max() ? entry.Sequence : entry.Sequence + 1;
                }
                json << "[";
                uint32 emitted = 0;
                bool firstEntry = true;
                for (auto itr = state.DecisionTrace.begin(); !gap && itr != state.DecisionTrace.end(); ++itr)
                {
                    if (itr->Sequence <= cursor)
                        continue;
                    if (emitted >= normalizedLimit)
                        break;
                    if (!firstEntry)
                        json << ',';
                    firstEntry = false;
                    // Reuse the existing bounded encoder by emitting a
                    // temporary one-entry view without copying the full
                    // diagnostic state.  Delta callers only need the same
                    // immutable entry schema and its sequence cursor.
                    json << "{\"timestamp_ms\":" << itr->TimestampMs
                         << ",\"sequence\":" << itr->Sequence
                         << ",\"decision_sequence\":" << itr->DecisionSequence
                         << ",\"situation\":\"" << JsonEscape(itr->Situation)
                         << "\",\"action\":\"" << JsonEscape(itr->Action)
                         << "\",\"route_node_id\":\"" << JsonEscape(itr->RouteNodeId)
                         << "\",\"route_generation\":" << itr->RouteGeneration
                         << ",\"quest_id\":" << itr->QuestId
                         << ",\"target_id\":" << itr->TargetGuid
                         << ",\"destination\":{\"map\":" << itr->DestinationMapId
                         << ",\"x\":" << itr->DestinationX << ",\"y\":" << itr->DestinationY
                         << ",\"z\":" << itr->DestinationZ << "}"
                         << ",\"result\":\"" << JsonEscape(itr->Result)
                         << "\",\"reason_code\":\"" << JsonEscape(itr->ReasonCode)
                         << "\",\"fingerprint_hash\":" << itr->FingerprintHash
                         << ",\"fingerprint_repeat_count\":" << itr->FingerprintRepeatCount
                         << ",\"fingerprint_failure_count\":" << itr->FingerprintFailureCount
                         << ",\"consecutive_same_decision_count\":" << itr->ConsecutiveSameDecisionCount
                         << ",\"idle_decision_repeat_count\":" << itr->IdleDecisionRepeatCount
                         << ",\"target_churn_count\":" << itr->TargetChurnCount
                         << ",\"suppressed_repeatable_event_count\":" << itr->SuppressedRepeatableEventCount
                         << ",\"suppressed_repeatable_decision_count\":" << itr->SuppressedRepeatableDecisionCount
                         << ",\"threat_snapshot\":{\"engaged_hostiles\":" << itr->EngagedHostileCount
                         << ",\"tank_owned_hostiles\":" << itr->TankOwnedHostileCount
                         << ",\"healer_targeting_hostiles\":" << itr->HealerTargetingHostileCount
                         << ",\"engaged_hostile_guids\":[";
                    for (size_t index = 0; index < itr->EngagedHostileGuids.size(); ++index)
                    {
                        if (index)
                            json << ',';
                        json << itr->EngagedHostileGuids[index];
                    }
                    json << "],\"tank_owned_hostile_guids\":[";
                    for (size_t index = 0; index < itr->TankOwnedHostileGuids.size(); ++index)
                    {
                        if (index)
                            json << ',';
                        json << itr->TankOwnedHostileGuids[index];
                    }
                    json << "],\"healer_targeting_hostile_guids\":[";
                    for (size_t index = 0; index < itr->HealerTargetingHostileGuids.size(); ++index)
                    {
                        if (index)
                            json << ',';
                        json << itr->HealerTargetingHostileGuids[index];
                    }
                    json << "],\"tank_threat_aura_active\":" << (itr->TankThreatAuraActive ? "true" : "false") << "}"
                         << ",\"pet_alive\":" << (itr->PetAlive ? "true" : "false")
                         << ",\"loop_guardrail_action\":\"" << JsonEscape(itr->LoopGuardrailAction)
                         << "\",\"loop_guardrail_reason\":\"" << JsonEscape(itr->LoopGuardrailReason)
                         << "\",\"recovery_mode\":\"" << JsonEscape(itr->RecoveryMode)
                         << "\",\"recovery_result\":\"" << JsonEscape(itr->RecoveryResult)
                         << "\",\"native_path_floor\":{\"failure\":\""
                         << BotWorldMovement::NativePathFloorFailureName(
                                itr->NativePathFloor.Failure)
                         << "\",\"segment_index\":" << itr->NativePathFloor.SegmentIndex
                         << ",\"sample_index\":" << itr->NativePathFloor.SampleIndex
                         << ",\"x\":" << itr->NativePathFloor.X
                         << ",\"y\":" << itr->NativePathFloor.Y
                         << ",\"z\":" << itr->NativePathFloor.Z
                         << ",\"resolved_floor_z\":" << itr->NativePathFloor.ResolvedFloorZ
                         << ",\"reference_z\":" << itr->NativePathFloor.ReferenceZ << "}"
                         << ",\"movement_planner\":"
                         << BotWorldMovement::MovementPlannerObservationJson(
                                BotWorldMovement::MovementPlannerDiagnostics().ForTrace(
                                    state.Guid.GetCounter(), itr->Sequence))
                         << ",\"blocked_episode_id\":" << itr->BlockedEpisodeId
                         << ",\"blocked_first_reason\":\"" << JsonEscape(itr->BlockedFirstReason)
                         << "\",\"blocked_current_reason\":\"" << JsonEscape(itr->BlockedCurrentReason)
                         << "\",\"blocked_resolution\":\"" << JsonEscape(itr->BlockedResolution)
                         << "\",\"blocked_resolved_by\":\"" << JsonEscape(itr->BlockedResolvedBy)
                         << "\",\"action_category\":\"" << JsonEscape(state.LastActionCategory)
                         << "\",\"role_goal\":\"" << JsonEscape(state.LastRoleGoal)
                         << "\",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode)
                         << "\",\"saturation_reason\":\"" << JsonEscape(state.LastSaturationReason)
                         << "\",\"mechanic_family\":\"" << JsonEscape(state.LastMechanicFamily)
                         << "\",\"encounter_role_responsibility\":\"" << JsonEscape(state.LastEncounterRoleResponsibility)
                         << "\",\"next_expected_action\":\"" << JsonEscape(state.LastNextExpectedAction)
                         << "\",\"combat_attempt\":" << BuildCombatAttemptJson(itr->CombatAttempt)
                         << ",\"route_progress\":" << BuildRouteProgressJson(itr->RouteProgress) << "}";
                    cursorAfter = itr->Sequence;
                    ++emitted;
                }
                json << "]"
                     << ",\"delta\":true"
                     << ",\"cursor_before\":" << cursor
                     << ",\"cursor_after\":" << cursorAfter
                     << ",\"gap\":" << (gap ? "true" : "false");
                // A bounded poll may emit only a prefix of available rows.
                // Advance exactly through the last emitted row, and never
                // advance while failing closed on a gap.
                if (!gap && cursorAfter != cursor)
                    Party().TraceExportCursorByGuid[state.Guid.GetCounter()] = cursorAfter;
            }
            json << "}";
        }

        json << "]";
        if (!attemptFailure.empty())
            json << ",\"failure_reason\":\"" << JsonEscape(attemptFailure) << "\"";
        else if (!emitted)
            json << ",\"failure_reason\":\"" << JsonEscape(Cohort().LastPopulationFailureReason.empty() ? "no_active_bot" : Cohort().LastPopulationFailureReason) << "\"";
        else
            json << ",\"failure_reason\":null";
        json << "}";
        return json.str();
    }

    WorldBotState const* selected = nullptr;
    for (WorldBotState const& state : Party().Bots)
    {
        Player* bot = GetLoadedBot(state);
        if (selector == std::to_string(state.Guid.GetCounter()) || (bot && selector == bot->GetName()))
        {
            selected = &state;
            break;
        }
    }

    if (!selected)
        return "{\"ok\":false,\"action\":\"botauto_trace\",\"trace_schema_version\":1,\"failure_reason\":\"no_matching_bot\"}";

    Player* bot = GetLoadedBot(*selected);
    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_trace\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
             << "\",\"trace_schema_version\":1"
         << ",\"bot_guid\":" << selected->Guid.GetCounter()
         << ",\"bot_name\":\"" << JsonEscape(bot ? bot->GetName() : "") << "\""
         << ",\"limit\":" << normalizedLimit
         << ",\"validation_route\":{\"manifest_index\":" << Party().ValidationRouteManifestIndex
         << ",\"manifest_count\":" << Party().ValidationRouteManifest.size()
         << ",\"node_id\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeId) << "\""
         << ",\"label\":\"" << JsonEscape(Cohort().Config.ValidationRouteLabel) << "\""
         << ",\"kind\":\"" << JsonEscape(Cohort().Config.ValidationRouteKind) << "\"}"
         << ",\"raid_runtime\":" << BuildRaidRuntimeJson(true)
         << ",\"entries\":" << BuildBotTraceEntriesJson(*selected, normalizedLimit)
         << ",\"failure_reason\":"
         << (attemptFailure.empty() ? "null"
             : ("\"" + JsonEscape(attemptFailure) + "\"")) << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetCombatLogJson() const
{
    auto perspectiveName = [](CombatLogPerspective perspective) -> char const*
    {
        switch (perspective)
        {
            case CombatLogPerspective::DamageDone: return "damage_done";
            case CombatLogPerspective::DamageTaken: return "damage_taken";
            case CombatLogPerspective::HealingDone: return "healing_done";
            case CombatLogPerspective::HealingReceived: return "healing_received";
        }
        return "unknown";
    };

    std::ostringstream json;
    json << std::fixed << std::setprecision(3)
         << "{\"ok\":true,\"action\":\"botauto_combatlog\",\"cohort_id\":\"" << JsonEscape(Cohort().Id)
         << "\",\"combat_log_schema_version\":2"
         << ",\"damage_attribution_schema\":\"originated_amount_v1\""
         << ",\"experiment_id\":" << Cohort().ExperimentId
         << ",\"run_id\":" << Cohort().RunId
         << ",\"event_count\":" << Party().CombatLogEventCount
         << ",\"recent_event_capacity\":4096"
         << ",\"recent_events_dropped\":" << Party().CombatLogRecentEventsDropped
         << ",\"aggregate_count\":" << Party().CombatLogAbilities.size()
         << ",\"second_bucket_count\":" << Party().CombatLogSecondBuckets.size()
         << ",\"abilities\":[";

    bool first = true;
    for (auto const& [key, value] : Party().CombatLogAbilities)
    {
        if (!first)
            json << ',';
        first = false;
        double averageDistance = value.EventCount ? value.DistanceTotal / double(value.EventCount) : 0.0;
        json << "{\"route_generation\":" << key.RouteGeneration
             << ",\"route_node_id\":\"" << JsonEscape(value.RouteNodeId) << "\""
             << ",\"route_label\":\"" << JsonEscape(value.RouteLabel) << "\""
             << ",\"perspective\":\"" << perspectiveName(key.Perspective) << "\""
             << ",\"actor_guid\":" << key.ActorGuid
             << ",\"actor_name\":\"" << JsonEscape(value.ActorName) << "\""
             << ",\"actor_role\":\"" << JsonEscape(value.ActorRole) << "\""
             << ",\"actor_class_id\":" << uint32(value.ActorClassId)
             << ",\"source_entry\":" << key.SourceEntry
             << ",\"source_name\":\"" << JsonEscape(value.SourceName) << "\""
             << ",\"source_is_pet\":" << (value.SourceIsPet ? "true" : "false")
             << ",\"spell_id\":" << key.SpellId
             << ",\"spell_name\":\"" << JsonEscape(value.SpellName) << "\""
             << ",\"target_entry\":" << key.TargetEntry
             << ",\"target_name\":\"" << JsonEscape(value.TargetName) << "\""
             << ",\"effect_type\":" << key.EffectType
             << ",\"first_at_ms\":" << value.FirstAtMs
             << ",\"last_at_ms\":" << value.LastAtMs
             << ",\"event_count\":" << value.EventCount
             << ",\"amount\":" << value.Amount
             << ",\"originated_amount\":" << value.OriginatedAmount
             << ",\"shared_amount\":" << value.SharedAmount
             << ",\"raw_amount\":" << value.RawAmount
             << ",\"absorbed_amount\":" << value.AbsorbedAmount
             << ",\"moving_events\":" << value.MovingEvents
             << ",\"moving_fraction\":" << (value.EventCount ? double(value.MovingEvents) / double(value.EventCount) : 0.0)
             << ",\"distance_avg\":" << averageDistance
             << ",\"distance_min\":" << std::max(0.0f, value.MinDistance)
             << ",\"distance_max\":" << value.MaxDistance << '}';
    }

    json << "],\"second_buckets\":[";
    first = true;
    for (auto const& [key, bucket] : Party().CombatLogSecondBuckets)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"route_generation\":" << std::get<0>(key)
             << ",\"perspective\":\"" << perspectiveName(std::get<1>(key)) << "\""
             << ",\"actor_guid\":" << std::get<2>(key)
             << ",\"source_is_pet\":" << (std::get<3>(key) ? "true" : "false")
             << ",\"second\":" << std::get<4>(key)
             << ",\"amount\":" << bucket.RawAmount
             << ",\"originated_amount\":" << bucket.OriginatedAmount << '}';
    }

    json << "],\"recent_events\":[";
    first = true;
    for (CombatLogEvent const& event : Party().CombatLogRecentEvents)
    {
        if (!first)
            json << ',';
        first = false;
        json << "{\"timestamp_ms\":" << event.TimestampMs
             << ",\"route_generation\":" << event.RouteGeneration
             << ",\"route_node_id\":\"" << JsonEscape(event.RouteNodeId) << "\""
             << ",\"kind\":\"" << JsonEscape(event.Kind) << "\""
             << ",\"actor_guid\":" << event.ActorGuid
             << ",\"actor_name\":\"" << JsonEscape(event.ActorName) << "\""
             << ",\"actor_role\":\"" << JsonEscape(event.ActorRole) << "\""
             << ",\"actor_class_id\":" << uint32(event.ActorClassId)
             << ",\"source_guid\":" << event.SourceGuid
             << ",\"source_entry\":" << event.SourceEntry
             << ",\"source_name\":\"" << JsonEscape(event.SourceName) << "\""
             << ",\"target_guid\":" << event.TargetGuid
             << ",\"target_entry\":" << event.TargetEntry
             << ",\"target_name\":\"" << JsonEscape(event.TargetName) << "\""
             << ",\"spell_id\":" << event.SpellId
             << ",\"spell_name\":\"" << JsonEscape(event.SpellName) << "\""
             << ",\"effect_type\":" << event.EffectType
             << ",\"school_mask\":" << event.SchoolMask
             << ",\"amount\":" << event.Amount
             << ",\"originated_amount\":" << event.OriginatedAmount
             << ",\"raw_amount\":" << event.RawAmount
             << ",\"absorbed_amount\":" << event.AbsorbedAmount
             << ",\"source_x\":" << event.SourceX
             << ",\"source_y\":" << event.SourceY
             << ",\"source_z\":" << event.SourceZ
             << ",\"target_x\":" << event.TargetX
             << ",\"target_y\":" << event.TargetY
             << ",\"target_z\":" << event.TargetZ
             << ",\"distance\":" << event.Distance
             << ",\"source_moving\":" << (event.SourceMoving ? "true" : "false")
             << ",\"source_is_pet\":" << (event.SourceIsPet ? "true" : "false")
             << ",\"shared_damage\":" << (event.SharedDamage ? "true" : "false") << '}';
    }
    json << "],\"failure_reason\":null}";
    return json.str();
}

std::string BotWorldPopulationMgr::GetBotDebugJson(std::string const& selector) const
{
    WorldBotState const* selected = nullptr;
    if (!selector.empty() && selector != "all")
    {
        for (WorldBotState const& state : Party().Bots)
        {
            Player* bot = GetLoadedBot(state);
            if (!bot)
                continue;
            if (selector == std::to_string(state.Guid.GetCounter()) || selector == bot->GetName())
            {
                selected = &state;
                break;
            }
        }
    }
    if (!selected && !Party().Bots.empty())
        selected = &Party().Bots.front();

    if (!selected)
        return "{\"ok\":false,\"action\":\"botauto_debug\",\"failure_reason\":\"no_active_bot\"}";

    Player* loadedBot = GetLoadedBot(*selected);
    Player* bot = loadedBot && loadedBot->IsInWorld() ? loadedBot : nullptr;
    if (!bot)
    {
        std::ostringstream json;
        json << "{\"ok\":false,\"action\":\"botauto_debug\""
             << ",\"bot_guid\":" << selected->Guid.GetCounter()
             << ",\"bot_name\":\"" << JsonEscape(loadedBot ? loadedBot->GetName() : "") << "\""
             << ",\"failure_reason\":\"" << (loadedBot ? "bot_loaded_not_in_world" : "bot_not_loaded") << "\""
             << ",\"diagnosis\":" << BuildBotDiagnosisObjectJson(*selected, loadedBot) << "}";
        return json.str();
    }

    uint32 savedMap = 0;
    float savedX = 0.0f;
    float savedY = 0.0f;
    float savedZ = 0.0f;
    float savedO = 0.0f;
    if (QueryResult result = CharacterDatabase.PQuery("SELECT map, position_x, position_y, position_z, orientation FROM characters WHERE guid = %u", selected->Guid.GetCounter()))
    {
        Field* fields = result->Fetch();
        savedMap = fields[0].GetUInt16();
        savedX = fields[1].GetFloat();
        savedY = fields[2].GetFloat();
        savedZ = fields[3].GetFloat();
        savedO = fields[4].GetFloat();
    }

    Unit* target = selected->TargetGuid.IsEmpty() ? bot->GetVictim() : ObjectAccessor::GetUnit(*bot, selected->TargetGuid);
    bool targetDummy = IsTrainingDummy(target);
    QuestObjectivePlan plan;
    bool hasPlan = FindActiveQuestObjective(bot, plan);
    QuestPortfolioPlan portfolio = BuildQuestPortfolioPlan(bot, *selected);
    QuestObjectiveBucket debugBucket;
    bool hasDebugBucket = SelectQuestObjectiveBucket(bot, portfolio, debugBucket);
    bool dummyAllowed = hasPlan && IsTrainingDummyAllowedForQuest(plan, target);
    char const* progressionReject = nullptr;
    bool targetProgressionRelevant = target && IsProgressionCombatTarget(bot, target, &progressionReject);
    bool targetMatchesObjective = false;
    std::string targetName;
    if (Creature const* creature = target ? target->ToCreature() : nullptr)
    {
        targetMatchesObjective = selected->QuestWork.RequiredEntry <= 0 || uint32(selected->QuestWork.RequiredEntry) == creature->GetEntry();
        targetName = creature->GetName();
    }

    std::ostringstream json;
    json << "{\"ok\":true,\"action\":\"botauto_debug\""
         << ",\"debug_schema_version\":1"
         << ",\"bot_guid\":" << selected->Guid.GetCounter()
         << ",\"bot_name\":\"" << JsonEscape(bot->GetName()) << "\""
         << ",\"spawn_source\":\"" << JsonEscape(selected->SpawnSource) << "\""
         << ",\"saved_position\":{\"map\":" << savedMap << ",\"x\":" << savedX << ",\"y\":" << savedY << ",\"z\":" << savedZ << ",\"o\":" << savedO << "}"
         << ",\"race_start_fallback_used\":" << (selected->RaceStartFallbackUsed ? "true" : "false")
         << ",\"saved_or_race_start_status\":\"" << JsonEscape(selected->RaceStartFallbackUsed ? "race_start" : selected->SpawnSource) << "\""
         << ",\"current_quest_state\":\"" << JsonEscape(selected->CurrentQuestState) << "\""
         << ",\"chosen_activity\":\"" << JsonEscape(selected->ActivityType) << "\""
         << ",\"allow_grinding\":" << (Cohort().Config.AllowGrinding ? "true" : "false")
         << ",\"quest_first\":" << (Cohort().Config.QuestFirst ? "true" : "false")
         << ",\"grind_only_when_no_quest_available\":" << (Cohort().Config.GrindOnlyWhenNoQuestAvailable ? "true" : "false")
         << ",\"quest_phase\":\"" << JsonEscape(selected->QuestWork.Phase) << "\""
         << ",\"active_quest_id\":" << selected->QuestWork.ActiveQuestId
         << ",\"newly_accepted_quest_id\":" << selected->NewlyAcceptedQuestId
         << ",\"objective_index\":" << selected->QuestWork.ObjectiveIndex
         << ",\"objective_type\":\"" << JsonEscape(selected->QuestWork.ObjectiveType != "none" ? selected->QuestWork.ObjectiveType : (hasPlan ? ToString(plan.ObjectiveType) : selected->CurrentObjectiveType.c_str())) << "\""
         << ",\"required_count\":" << selected->QuestWork.RequiredCount
         << ",\"current_count\":" << selected->QuestWork.CurrentCount
         << ",\"selected_target_guid\":" << selected->QuestWork.SelectedTargetGuid.GetCounter()
         << ",\"selected_object_guid\":" << selected->QuestWork.SelectedObjectGuid.GetCounter()
         << ",\"selected_giver_guid\":" << selected->QuestWork.SelectedGiverGuid.GetCounter()
         << ",\"selected_giver_cooldown_until_ms\":" << (selected->QuestWork.SelectedGiverGuid.IsEmpty() || selected->QuestGiverCooldownUntilMs.find(selected->QuestWork.SelectedGiverGuid.GetCounter()) == selected->QuestGiverCooldownUntilMs.end() ? 0 : selected->QuestGiverCooldownUntilMs.find(selected->QuestWork.SelectedGiverGuid.GetCounter())->second)
         << ",\"target_guid\":" << (target ? target->GetGUID().GetCounter() : 0)
         << ",\"target_entry\":" << (target && target->ToCreature() ? target->ToCreature()->GetEntry() : 0)
         << ",\"target_name\":\"" << JsonEscape(targetName) << "\""
         << ",\"target_matches_objective\":" << (targetMatchesObjective ? "true" : "false")
         << ",\"target_progression_relevant\":" << (targetProgressionRelevant ? "true" : "false")
         << ",\"target_progression_reject_reason\":\"" << JsonEscape(progressionReject ? progressionReject : "") << "\""
         << ",\"target_training_dummy\":" << (targetDummy ? "true" : "false")
         << ",\"dummy_allowed_by_active_quest\":" << (dummyAllowed ? "true" : "false")
         << ",\"required_spell\":" << (selected->QuestWork.RequiredSpell ? selected->QuestWork.RequiredSpell : (hasPlan ? plan.RequiredSpellId : selected->RequiredSpellId))
         << ",\"required_item\":" << (selected->QuestWork.RequiredItem ? selected->QuestWork.RequiredItem : (hasPlan ? plan.ItemId : selected->RequiredItemId))
         << ",\"required_target\":" << (selected->QuestWork.RequiredEntry > 0 ? uint32(selected->QuestWork.RequiredEntry) : (hasPlan && plan.RequiredEntry > 0 ? uint32(plan.RequiredEntry) : selected->RequiredTargetEntry))
         << ",\"loot_attempt_count\":" << selected->LootAttemptCount
         << ",\"last_loot_result\":\"" << JsonEscape(selected->LastLootResult) << "\""
         << ",\"last_loot_items_count\":" << selected->LastLootItemsCount
         << ",\"last_loot_money\":" << selected->LastLootMoney
         << ",\"last_loot_state_cleared\":" << (selected->LastLootStateCleared ? "true" : "false")
         << ",\"last_quest_progress_before\":" << selected->LastQuestProgressBefore
         << ",\"last_quest_progress_after\":" << selected->LastQuestProgressAfter
         << ",\"quest_work_progress_before\":" << selected->QuestWork.ProgressBefore
         << ",\"quest_work_progress_after\":" << selected->QuestWork.ProgressAfter
         << ",\"decision_fingerprint_hash\":" << selected->LastDecisionFingerprintHash
         << ",\"decision_fingerprint_repeat_count\":" << selected->LastDecisionFingerprintRepeatCount
         << ",\"decision_fingerprint_failure_count\":" << selected->LastDecisionFingerprintFailureCount
         << ",\"consecutive_same_decision_count\":" << selected->ConsecutiveSameDecisionCount
         << ",\"idle_decision_repeat_count\":" << selected->IdleDecisionRepeatCount
         << ",\"target_churn_count\":" << selected->TargetChurnCount
         << ",\"loop_guardrail_count\":" << selected->LoopGuardrailCount
         << ",\"last_loop_guardrail_action\":\"" << JsonEscape(selected->LastLoopGuardrailAction) << "\""
         << ",\"last_loop_guardrail_reason\":\"" << JsonEscape(selected->LastLoopGuardrailReason) << "\""
         << ",\"recovery_attempt_count\":" << selected->RecoveryAttemptCount
         << ",\"last_recovery_mode\":\"" << JsonEscape(selected->LastRecoveryMode) << "\""
         << ",\"last_recovery_result\":\"" << JsonEscape(selected->LastRecoveryResult) << "\""
         << ",\"decision_kernel\":" << (selected->LastDecisionKernelJson.empty() ? "{}" : selected->LastDecisionKernelJson)
         << ",\"last_no_progress_reason\":\"" << JsonEscape(selected->LastNoProgressReason) << "\""
         << ",\"last_objective_not_found_reason\":\"" << JsonEscape(selected->LastObjectiveNotFoundReason) << "\""
         << ",\"last_grinding_allowed_reason\":\"" << JsonEscape(selected->LastGrindingAllowedReason) << "\""
         << ",\"active_quest_count\":" << portfolio.ActiveQuestCount
         << ",\"quest_bucket_id\":" << (hasDebugBucket ? debugBucket.BucketId : selected->ActiveQuestClusterId)
         << ",\"quest_bucket_objective_count\":" << (hasDebugBucket ? uint32(debugBucket.Objectives.size()) : 0)
         << ",\"quest_bucket_center\":{\"map\":" << (hasDebugBucket ? debugBucket.MapId : selected->QuestRouteDestination.MapId)
         << ",\"x\":" << (hasDebugBucket ? debugBucket.CenterX : selected->QuestRouteDestination.X)
         << ",\"y\":" << (hasDebugBucket ? debugBucket.CenterY : selected->QuestRouteDestination.Y)
         << ",\"z\":" << (hasDebugBucket ? debugBucket.CenterZ : selected->QuestRouteDestination.Z) << "}"
         << ",\"quest_search_radius\":" << selected->QuestSearchRadiusIndex
         << ",\"quest_search_destination\":{\"valid\":" << (selected->QuestSearchDestination.Valid ? "true" : "false")
         << ",\"map\":" << selected->QuestSearchDestination.MapId
         << ",\"x\":" << selected->QuestSearchDestination.X
         << ",\"y\":" << selected->QuestSearchDestination.Y
         << ",\"z\":" << selected->QuestSearchDestination.Z
         << ",\"quest_id\":" << selected->QuestSearchDestination.QuestId
         << ",\"reason\":\"" << JsonEscape(selected->QuestSearchDestination.Reason) << "\"}"
         << ",\"last_no_quest_reason\":\"" << JsonEscape(selected->LastNoQuestReason) << "\""
         << ",\"last_quest_classification\":\"" << JsonEscape(selected->LastQuestClassification) << "\""
         << ",\"last_bucket_selection_reason\":\"" << JsonEscape(hasDebugBucket ? debugBucket.Reason : selected->LastQuestBucketReason) << "\""
         << ",\"current_quest_supported\":" << (hasPlan ? "true" : "false")
         << ",\"quest_cooldown_count\":" << selected->QuestCooldownUntilMs.size()
         << ",\"no_progress_cooldown_count\":" << selected->NoProgressCooldownUntilMs.size()
         << ",\"cooldown_until_ms\":" << selected->QuestWork.CooldownUntilMs
         << ",\"failure_reason\":\"" << JsonEscape(selected->QuestWork.FailedReason) << "\""
         << ",\"last_rejected_target_reason\":\"" << JsonEscape(selected->LastRejectedTargetReason) << "\""
         << ",\"combat_attempt\":" << BuildCombatAttemptJson(selected->LastCombatAttempt)
         << ",\"route_progress\":" << BuildRouteProgressJson(selected->LastRouteProgress)
         << ",\"diagnosis\":" << BuildBotDiagnosisObjectJson(*selected, bot)
         << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (char c : value)
    {
        switch (c)
        {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\b': escaped << "\\b"; break;
            case '\f': escaped << "\\f"; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default:
                if (static_cast<unsigned char>(c) < 0x20)
                    escaped << "\\u" << std::hex << std::setw(4) << std::setfill('0') << uint32(static_cast<unsigned char>(c)) << std::dec;
                else
                    escaped << c;
                break;
        }
    }
    return escaped.str();
}

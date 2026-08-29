#include "Bots/BotWorldPopulationMgr.h"

#include "CellImpl.h"
#include "Creature.h"
#include "CreatureGroups.h"
#include "DatabaseEnv.h"
#include "GameTime.h"
#include "GridNotifiersImpl.h"
#include "Group.h"
#include "Map.h"
#include "MotionMaster.h"
#include "Movement/Spline/MoveSpline.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Pet.h"
#include "Player.h"
#include "Unit.h"

#include <algorithm>
#include <chrono>
#include <initializer_list>
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
}

BotWorldPopulationMgr::BotDiagnosis BotWorldPopulationMgr::BuildBotDiagnosis(WorldBotState const& state, Player const* bot) const
{
    BotDiagnosis diagnosis;
    diagnosis.CurrentAction = state.LastDecisionAction;

    uint64 nowMs = NowMs();
    uint64 sinceProgressMs = state.LastMovementProgressMs ? nowMs - state.LastMovementProgressMs : 0;
    uint64 sinceDecisionMs = state.LastDecisionTickMs ? nowMs - state.LastDecisionTickMs : 0;
    uint64 sincePathChangeMs = state.LastPathChangeMs ? nowMs - state.LastPathChangeMs : 0;
    bool questBlocked = !state.QuestWork.FailedReason.empty() || !state.LastObjectiveNotFoundReason.empty();
    bool pickupBlocked = state.LastNoQuestReason == "no_pickup_search_candidate";

    if (state.ValidationCohortViolation)
    {
        diagnosis.DiagnosisCode = "validation_cohort_instance_violation";
        diagnosis.Severity = "error";
        diagnosis.Confidence = 1.0f;
        diagnosis.Blocker = state.ValidationCohortViolationReason.empty() ? "bot_left_original_validation_instance" : state.ValidationCohortViolationReason;
        diagnosis.NextExpectedAction = "stop_validation_decisions_for_bot";
        diagnosis.SuggestedInvestigation = "inspect_validation_cohort_fields_and_spawn_source";
    }
    else if (!bot)
    {
        diagnosis.DiagnosisCode = "bot_not_loaded";
        diagnosis.Severity = "error";
        diagnosis.Confidence = 1.0f;
        diagnosis.Blocker = "selected_bot_is_not_loaded";
        diagnosis.NextExpectedAction = "load_or_respawn_bot";
        diagnosis.SuggestedInvestigation = "inspect_bot_pool_and_spawn_state";
    }
    else if (!bot->IsInWorld())
    {
        diagnosis.DiagnosisCode = "bot_loaded_not_in_world";
        diagnosis.Severity = "error";
        diagnosis.Confidence = 1.0f;
        diagnosis.Blocker = "selected_bot_is_loaded_but_detached_from_world";
        diagnosis.NextExpectedAction = "reattach_or_respawn_bot";
        diagnosis.SuggestedInvestigation = "inspect_validation_group_instance_and_map_membership";
    }
    else if (!bot->IsAlive() || state.DeadTimer > 0)
    {
        diagnosis.DiagnosisCode = "dead_recovery";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.95f;
        diagnosis.Blocker = "bot_is_dead_or_recovering";
        diagnosis.NextExpectedAction = "death_recovery_tick";
        diagnosis.SuggestedInvestigation = "inspect_recent_death_and_recovery_trace";
    }
    else if (state.Blocked)
    {
        diagnosis.DiagnosisCode = "blocked_no_fallback";
        diagnosis.Severity = "error";
        diagnosis.Confidence = 1.0f;
        diagnosis.Blocker = state.BlockedReason.empty() ? state.BlockedFirstReason : state.BlockedReason;
        diagnosis.NextExpectedAction = state.BlockedResolution.empty() ? "wait_for_configured_resolution" : state.BlockedResolution;
        diagnosis.SuggestedInvestigation = "inspect_blocked_episode_trace_and_required_resolution";
    }
    else if (Cohort().Config.ValidationRouteEnable && state.ValidationRouteTerminalState && state.ValidationRouteTerminalReason.rfind("route_destination_", 0) == 0)
    {
        diagnosis.DiagnosisCode = "route_destination_unreachable";
        diagnosis.Severity = "error";
        diagnosis.Confidence = 1.0f;
        diagnosis.Blocker = state.ValidationRouteTerminalReason;
        diagnosis.NextExpectedAction = "fail_validation_route_segment";
        diagnosis.SuggestedInvestigation = "inspect_mmap_vmap_route_endpoint_and_manifest";
    }
    else if (Cohort().Config.ValidationRouteKind == "descent"
        && Cohort().Config.ValidationRouteDescentAction
            == "native_walkable_descent"
        && !state.ValidationRouteDescentRejectReason.empty())
    {
        diagnosis.DiagnosisCode = "native_descent_blocked";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.98f;
        diagnosis.Blocker = state.ValidationRouteDescentRejectReason;
        diagnosis.NextExpectedAction =
            state.ValidationRouteDescentRejectReason
                    == "native_descent_landing_health_margin_low"
                ? "ordinary_heal_then_reconcile_landing"
                : "retry_native_walkable_segment_or_fail_closed";
        diagnosis.SuggestedInvestigation =
            "inspect_descent_phase_native_path_floor_and_onward_goal";
    }
    else if (bot->IsInCombat())
    {
        diagnosis.DiagnosisCode = "normal_combat";
        diagnosis.Severity = "info";
        diagnosis.Confidence = 0.8f;
        diagnosis.Blocker = "";
        diagnosis.NextExpectedAction = "continue_combat_rotation";
        diagnosis.SuggestedInvestigation = "inspect_target_if_combat_repeats_without_kill";
    }
    else if (state.StuckTimer >= 3000 || (state.LastDecisionAction == "unstuck" && sinceDecisionMs < 10000))
    {
        diagnosis.DiagnosisCode = "stuck_repath_loop";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.9f;
        diagnosis.Blocker = "movement_stuck_or_recent_unstuck";
        diagnosis.NextExpectedAction = "repath_to_nearby_collision_position";
        diagnosis.SuggestedInvestigation = "inspect_routing_destination_and_failed_path_memory";
    }
    else if (state.ActivePathValid && state.IsMoving && sincePathChangeMs > 5000 && sinceProgressMs > 5000)
    {
        diagnosis.DiagnosisCode = "moving_but_not_progressing";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.85f;
        diagnosis.Blocker = "active_movement_has_no_recent_position_progress";
        diagnosis.NextExpectedAction = "stuck_detection_or_repath";
        diagnosis.SuggestedInvestigation = "compare_trace_entries_for_repeated_destination";
    }
    else if (state.ValidationRouteTerminalState && state.LastDecisionAction == "validation_route_complete")
    {
        diagnosis.DiagnosisCode = "validation_route_terminal";
        diagnosis.Severity = "info";
        diagnosis.Confidence = 0.9f;
        diagnosis.Blocker = state.ValidationRouteTerminalReason;
        diagnosis.NextExpectedAction = "advance_validation_route_segment";
        diagnosis.SuggestedInvestigation = "inspect_dungeon_trash_cleared_evidence";
    }
    else if (state.LastDecisionFingerprintRepeatCount >= 5 && state.ConsecutiveSameDecisionCount >= 3)
    {
        diagnosis.DiagnosisCode = "repeated_decision_loop";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.88f;
        diagnosis.Blocker = "same_decision_fingerprint_repeating";
        diagnosis.NextExpectedAction = nowMs >= state.LoopRecoveryCooldownUntilMs ? "guardrail_repath" : "wait_for_guardrail_cooldown";
        diagnosis.SuggestedInvestigation = "inspect_decision_fingerprint_memory_and_trace";
    }
    else if (state.IdleDecisionRepeatCount >= 4 && state.LastDecisionDistanceMoved < 1.0f)
    {
        diagnosis.DiagnosisCode = "idle_loop_guardrail";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.82f;
        diagnosis.Blocker = "idle_or_wander_repeating_without_progress";
        diagnosis.NextExpectedAction = nowMs >= state.LoopRecoveryCooldownUntilMs ? "guardrail_repath" : "wait_for_guardrail_cooldown";
        diagnosis.SuggestedInvestigation = "inspect_idle_trace_and_nearby_objective_memory";
    }
    else if (state.TargetChurnCount >= 4)
    {
        diagnosis.DiagnosisCode = "target_churn_loop";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.84f;
        diagnosis.Blocker = "target_selection_changed_repeatedly";
        diagnosis.NextExpectedAction = nowMs >= state.LoopRecoveryCooldownUntilMs ? "clear_target_and_repath" : "wait_for_guardrail_cooldown";
        diagnosis.SuggestedInvestigation = "inspect_target_relevance_and_recent_rejections";
    }
    else if (questBlocked && state.QuestWork.ActiveQuestId)
    {
        diagnosis.DiagnosisCode = "no_supported_objective";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.75f;
        diagnosis.Blocker = state.QuestWork.FailedReason.empty() ? state.LastObjectiveNotFoundReason : state.QuestWork.FailedReason;
        diagnosis.NextExpectedAction = "select_supported_objective_or_search_pickup";
        diagnosis.SuggestedInvestigation = "inspect_quest_work_and_objective_plan";
    }
    else if (pickupBlocked)
    {
        diagnosis.DiagnosisCode = state.QuestSearchDestination.Valid ? "quest_pickup_unreachable" : "idle_no_candidate";
        diagnosis.Severity = "warning";
        diagnosis.Confidence = 0.7f;
        diagnosis.Blocker = state.LastNoQuestReason;
        diagnosis.NextExpectedAction = "expand_quest_search_radius_or_wander";
        diagnosis.SuggestedInvestigation = "inspect_nearby_quest_givers_and_quest_cooldowns";
    }
    else if (!state.LastRejectedTargetReason.empty() && state.LastDecisionSituation == "target_rejected")
    {
        diagnosis.DiagnosisCode = "target_rejected";
        diagnosis.Severity = "info";
        diagnosis.Confidence = 0.8f;
        diagnosis.Blocker = state.LastRejectedTargetReason;
        diagnosis.NextExpectedAction = "clear_target_and_choose_progression_action";
        diagnosis.SuggestedInvestigation = "inspect_target_relevance_rules";
    }
    else if (state.DecisionTimer > 0)
    {
        diagnosis.DiagnosisCode = "waiting_decision_tick";
        diagnosis.Severity = "info";
        diagnosis.Confidence = 0.65f;
        diagnosis.Blocker = "";
        diagnosis.NextExpectedAction = "decision_tick";
        diagnosis.SuggestedInvestigation = "inspect_trace_only_if_state_repeats";
    }
    else
    {
        diagnosis.DiagnosisCode = "normal_work";
        diagnosis.Severity = "info";
        diagnosis.Confidence = 0.6f;
        diagnosis.Blocker = "";
        diagnosis.NextExpectedAction = "continue_current_action";
        diagnosis.SuggestedInvestigation = "inspect_trace_for_long_running_repetition";
    }

    return diagnosis;
}

std::string BotWorldPopulationMgr::BuildBotDiagnosisObjectJson(WorldBotState const& state, Player const* bot) const
{
    BotDiagnosis diagnosis = BuildBotDiagnosis(state, bot);
    uint64 nowMs = NowMs();
    uint64 sinceDecisionMs = state.LastDecisionTickMs ? nowMs - state.LastDecisionTickMs : 0;
    uint64 sinceProgressMs = state.LastMovementProgressMs ? nowMs - state.LastMovementProgressMs : 0;
    uint64 sincePathChangeMs = state.LastPathChangeMs ? nowMs - state.LastPathChangeMs : 0;
    MotionMaster const* nativeMotion = bot ? bot->GetMotionMaster() : nullptr;
    bool hasValidationRouteActivation = Cohort().Config.ValidationRouteActivationAreaTriggerId
        || Cohort().Config.ValidationRouteActivationDataId
        || Cohort().Config.ValidationRouteActivationSpawnGroupId
        || Cohort().Config.ValidationRouteActivationActionEntry
        || Cohort().Config.ValidationRouteActivationSummonEntry
        || Cohort().Config.ValidationRouteOpenerSummonEntry
        || (Cohort().Config.ValidationRouteKind == "boss" && Cohort().Config.ValidationRouteTargetEntry);
    float validationRouteDistance = -1.0f;
    if (bot && (!Cohort().Config.ValidationRouteMapId || bot->GetMapId() == Cohort().Config.ValidationRouteMapId))
        validationRouteDistance = bot->GetExactDist(Cohort().Config.ValidationRouteX, Cohort().Config.ValidationRouteY, Cohort().Config.ValidationRouteZ);
    bool petDbRowPresent = false;
    uint32 petDbId = 0;
    uint32 petDbEntry = 0;
    if (bot && bot->getClass() == CLASS_HUNTER)
    {
        if (QueryResult petRow = CharacterDatabase.PQuery("SELECT id, entry FROM character_pet WHERE owner = %u AND (active = 1 OR slot BETWEEN %u AND %u) ORDER BY active DESC, slot LIMIT 1", bot->GetGUID().GetCounter(), PET_SLOT_FIRST_ACTIVE_SLOT, PET_SLOT_LAST_ACTIVE_SLOT))
        {
            Field* fields = petRow->Fetch();
            petDbRowPresent = true;
            petDbId = fields[0].GetUInt32();
            petDbEntry = fields[1].GetUInt32();
        }
    }
    PlayerPetData const* activePetData = bot ? const_cast<Player*>(bot)->GetPlayerPetDataCurrent() : nullptr;
    Pet const* livePet = bot ? bot->GetPet() : nullptr;
    std::ostringstream validationRoutePackMembers;
    validationRoutePackMembers << "[";
    bool firstPackMember = true;
    for (ObjectGuid const& guid : Party().ValidationRoutePackMemberGuids)
    {
        if (!firstPackMember)
            validationRoutePackMembers << ",";
        firstPackMember = false;
        Creature* creature = bot && bot->IsInWorld() && bot->GetMap() ? bot->GetMap()->GetCreature(guid) : nullptr;
        CreatureGroup const* formation = creature ? creature->GetFormation() : nullptr;
        Creature const* formationLeader = formation ? formation->getLeader() : nullptr;
        Position const* home = creature ? &creature->GetHomePosition() : nullptr;
        MotionMaster const* motion = creature ? creature->GetMotionMaster() : nullptr;
        validationRoutePackMembers << "{\"guid\":" << guid.GetCounter()
            << ",\"entry\":" << (creature ? creature->GetEntry() : guid.GetEntry())
            << ",\"spawn_id\":" << (creature ? creature->GetSpawnId() : 0)
            << ",\"position\":{\"x\":" << (creature ? creature->GetPositionX() : 0.0f)
            << ",\"y\":" << (creature ? creature->GetPositionY() : 0.0f)
            << ",\"z\":" << (creature ? creature->GetPositionZ() : 0.0f) << "}"
            << ",\"home\":{\"x\":" << (home ? home->GetPositionX() : 0.0f)
            << ",\"y\":" << (home ? home->GetPositionY() : 0.0f)
            << ",\"z\":" << (home ? home->GetPositionZ() : 0.0f)
            << ",\"distance\":" << (creature && home ? creature->GetExactDist(*home) : 0.0f) << "}"
            << ",\"current_motion_type\":" << (motion ? uint32(motion->GetCurrentMovementGeneratorType()) : uint32(MAX_MOTION_TYPE))
            << ",\"active_motion_type\":" << (motion ? uint32(motion->GetMotionSlotType(MOTION_SLOT_ACTIVE)) : uint32(MAX_MOTION_TYPE))
            << ",\"returning_home\":" << (creature && creature->IsReturningHome() ? "true" : "false")
            << ",\"formation_member\":" << (formation ? "true" : "false")
            << ",\"formation_id\":" << (formation ? formation->GetId() : 0)
            << ",\"formation_leader\":" << (formation && formation->IsLeader(creature) ? "true" : "false")
            << ",\"formation_leader_guid\":" << (formationLeader ? formationLeader->GetGUID().GetCounter() : 0)
            << ",\"formation_formed\":" << (formation && formation->isFormed() ? "true" : "false")
            << ",\"observed\":" << (creature ? "true" : "false")
            << ",\"alive\":" << (creature && creature->IsAlive() && creature->GetHealth() ? "true" : "false")
            << ",\"attackable\":" << (creature && bot && bot->IsValidAttackTarget(creature) ? "true" : "false")
            << ",\"evade\":" << (creature && (creature->IsInEvadeMode() || creature->HasUnitState(UNIT_STATE_EVADE)) ? "true" : "false")
            << ",\"engaged\":" << (Party().ValidationRoutePackEngagedGuids.find(guid) != Party().ValidationRoutePackEngagedGuids.end() ? "true" : "false")
            << ",\"death_recorded\":" << (Party().ValidationRoutePackDeathGuids.find(guid) != Party().ValidationRoutePackDeathGuids.end() ? "true" : "false")
            << ",\"transition_recorded\":" << (Party().ValidationRoutePackTransitionGuids.find(guid) != Party().ValidationRoutePackTransitionGuids.end() ? "true" : "false") << "}";
    }
    validationRoutePackMembers << "]";
    std::ostringstream validationRouteCombatLinks;
    validationRouteCombatLinks << "[";
    bool firstCombatMember = true;
    for (WorldBotState const& cohortState : Party().Bots)
    {
        Player const* member = GetLoadedBot(cohortState);
        if (!member)
            continue;
        if (!firstCombatMember)
            validationRouteCombatLinks << ",";
        firstCombatMember = false;
        validationRouteCombatLinks << "{\"bot_guid\":" << member->GetGUID().GetCounter()
            << ",\"in_combat\":" << (member->IsInCombat() ? "true" : "false")
            << ",\"victim_guid\":" << (member->GetVictim() ? member->GetVictim()->GetGUID().GetCounter() : 0)
            << ",\"attacker_guids\":[";
        std::vector<ObjectGuid> attackerGuids;
        attackerGuids.reserve(member->getAttackers().size());
        for (Unit const* attacker : member->getAttackers())
            if (attacker)
                attackerGuids.push_back(attacker->GetGUID());
        std::sort(attackerGuids.begin(), attackerGuids.end());
        for (size_t index = 0; index < attackerGuids.size(); ++index)
        {
            if (index)
                validationRouteCombatLinks << ",";
            validationRouteCombatLinks << attackerGuids[index].GetCounter();
        }
        validationRouteCombatLinks << "]}";
    }
    validationRouteCombatLinks << "]";
    auto paladinReady = [&](std::initializer_list<uint32> auraIds) -> bool
    {
        if (!bot || bot->getClass() != CLASS_PALADIN)
            return false;
        for (uint32 auraId : auraIds)
            if (bot->HasAura(auraId))
                return true;
        return false;
    };

    std::ostringstream json;
    json << "{\"diagnosis_code\":\"" << JsonEscape(diagnosis.DiagnosisCode) << "\""
         << ",\"severity\":\"" << JsonEscape(diagnosis.Severity) << "\""
         << ",\"confidence\":" << diagnosis.Confidence
         << ",\"intent\":\"" << JsonEscape(diagnosis.Intent) << "\""
         << ",\"current_action\":\"" << JsonEscape(diagnosis.CurrentAction) << "\""
         << ",\"blocker\":\"" << JsonEscape(diagnosis.Blocker) << "\""
         << ",\"combat_attempt\":" << BuildCombatAttemptJson(state.LastCombatAttempt)
         << ",\"route_progress\":" << BuildRouteProgressJson(state.LastRouteProgress)
         << ",\"decision_kernel\":" << (state.LastDecisionKernelJson.empty() ? "{}" : state.LastDecisionKernelJson)
         << ",\"evidence\":["
         << "{\"name\":\"loaded\",\"value\":" << (bot ? "true" : "false") << "},"
         << "{\"name\":\"in_world\",\"value\":" << (bot && bot->IsInWorld() ? "true" : "false") << "},"
         << "{\"name\":\"in_grid\",\"value\":" << (bot && bot->IsInGrid() ? "true" : "false") << "},"
         << "{\"name\":\"map_id\",\"value\":" << (bot ? bot->GetMapId() : 0) << "},"
         << "{\"name\":\"instance_id\",\"value\":" << (bot ? bot->GetInstanceId() : 0) << "},"
         << "{\"name\":\"alive\",\"value\":" << (bot && bot->IsAlive() ? "true" : "false") << "},"
         << "{\"name\":\"in_combat\",\"value\":" << (bot && bot->IsInCombat() ? "true" : "false") << "},"
         << "{\"name\":\"is_moving\",\"value\":" << (state.IsMoving ? "true" : "false") << "},"
         << "{\"name\":\"native_current_motion_type\",\"value\":" << (nativeMotion ? uint32(nativeMotion->GetCurrentMovementGeneratorType()) : uint32(MAX_MOTION_TYPE)) << "},"
         << "{\"name\":\"native_active_motion_type\",\"value\":" << (nativeMotion ? uint32(nativeMotion->GetMotionSlotType(MOTION_SLOT_ACTIVE)) : uint32(MAX_MOTION_TYPE)) << "},"
         << "{\"name\":\"active_path_target_guid\",\"value\":" << (state.ActivePathValid ? state.ActivePathTargetGuid.GetCounter() : 0) << "},"
         << "{\"name\":\"stuck_timer_ms\",\"value\":" << state.StuckTimer << "},"
         << "{\"name\":\"distance_moved_since_last_decision\",\"value\":" << state.LastDecisionDistanceMoved << "},"
         << "{\"name\":\"time_since_last_decision_ms\",\"value\":" << sinceDecisionMs << "},"
         << "{\"name\":\"time_since_last_progress_ms\",\"value\":" << sinceProgressMs << "},"
         << "{\"name\":\"time_since_last_path_change_ms\",\"value\":" << sincePathChangeMs << "},"
         << "{\"name\":\"quest_phase\",\"value\":\"" << JsonEscape(state.QuestWork.Phase) << "\"},"
         << "{\"name\":\"quest_failure_reason\",\"value\":\"" << JsonEscape(state.QuestWork.FailedReason) << "\"},"
         << "{\"name\":\"action_category\",\"value\":\"" << JsonEscape(state.LastActionCategory) << "\"},"
         << "{\"name\":\"role_goal\",\"value\":\"" << JsonEscape(state.LastRoleGoal) << "\"},"
         << "{\"name\":\"recommended_balance_mode\",\"value\":\"" << JsonEscape(state.LastRecommendedBalanceMode) << "\"},"
         << "{\"name\":\"saturation_reason\",\"value\":\"" << JsonEscape(state.LastSaturationReason) << "\"},"
         << "{\"name\":\"last_no_quest_reason\",\"value\":\"" << JsonEscape(state.LastNoQuestReason) << "\"},"
         << "{\"name\":\"active_quest_cluster_id\",\"value\":" << state.ActiveQuestClusterId << "},"
         << "{\"name\":\"quest_cooldown_count\",\"value\":" << state.QuestCooldownUntilMs.size() << "},"
         << "{\"name\":\"no_progress_cooldown_count\",\"value\":" << state.NoProgressCooldownUntilMs.size() << "},"
         << "{\"name\":\"validation_route_manifest_index\",\"value\":" << Party().ValidationRouteManifestIndex << "},"
         << "{\"name\":\"validation_route_manifest_count\",\"value\":" << Party().ValidationRouteManifest.size() << "},"
         << "{\"name\":\"validation_route_advance_mode\",\"value\":\"" << JsonEscape(Cohort().Config.ValidationRouteAdvanceMode) << "\"},"
         << "{\"name\":\"validation_route_advance_pending\",\"value\":" << (Party().ValidationRouteManifestAdvancePending ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_advance_reason\",\"value\":\"" << JsonEscape(Party().ValidationRouteManifestAdvanceReason) << "\"},"
         << "{\"name\":\"validation_route_manifest_load_error\",\"value\":\"" << JsonEscape(Party().ValidationRouteManifestLoadError) << "\"},"
         << "{\"name\":\"validation_route_progress_baseline_kills\",\"value\":" << Party().ValidationRouteProgressBaselineKills << "},"
         << "{\"name\":\"validation_route_pack_generation\",\"value\":" << Party().ValidationRoutePackGeneration << "},"
         << "{\"name\":\"validation_route_pack_sequence\",\"value\":" << Party().ValidationRoutePackSequence << "},"
         << "{\"name\":\"validation_route_completed_pack_count\",\"value\":" << Party().ValidationRouteCompletedPackCount << "},"
         << "{\"name\":\"validation_route_observed_dead_script_target\",\"value\":" << (Party().ValidationRouteObservedDeadScriptTarget ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_pack_member_count\",\"value\":" << Party().ValidationRoutePackMemberGuids.size() << "},"
         << "{\"name\":\"validation_route_pack_engaged_count\",\"value\":" << Party().ValidationRoutePackEngagedGuids.size() << "},"
         << "{\"name\":\"validation_route_pack_death_count\",\"value\":" << Party().ValidationRoutePackDeathGuids.size() << "},"
         << "{\"name\":\"validation_route_pack_transition_count\",\"value\":" << Party().ValidationRoutePackTransitionGuids.size() << "},"
         << "{\"name\":\"validation_route_pack_members\",\"value\":" << validationRoutePackMembers.str() << "},"
         << "{\"name\":\"validation_route_combat_links\",\"value\":" << validationRouteCombatLinks.str() << "},"
         << "{\"name\":\"validation_route_pack_observed_engagement\",\"value\":" << (Party().ValidationRoutePackObservedEngagement ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_boss_add_density_phase\",\"value\":" << (Party().ValidationRouteBossAddDensityPhase ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_boss_add_density_generation\",\"value\":" << Party().ValidationRouteBossAddDensityGeneration << "},"
         << "{\"name\":\"validation_route_boss_add_escape_active\",\"value\":" << (Party().ValidationRouteBossAddEscapeActive ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_boss_add_escape_generation\",\"value\":" << Party().ValidationRouteBossAddEscapeGeneration << "},"
         << "{\"name\":\"validation_route_boss_add_escape_issued_count\",\"value\":" << Party().ValidationRouteBossAddEscapeIssuedGuids.size() << "},"
         << "{\"name\":\"validation_route_boss_add_escape_distance\",\"value\":"
         << (Party().ValidationRouteBossAddEscapeActive ? bot->GetExactDist(Party().ValidationRouteBossAddEscapeX, Party().ValidationRouteBossAddEscapeY, Party().ValidationRouteBossAddEscapeZ) : 0.0f) << "},"
         << "{\"name\":\"validation_route_activation_applied\",\"value\":" << (state.ValidationRouteActivationApplied ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_activation_attempts\",\"value\":" << state.ValidationRouteActivationAttempts << "},"
         << "{\"name\":\"validation_route_config_kind\",\"value\":\"" << JsonEscape(Cohort().Config.ValidationRouteKind) << "\"},"
         << "{\"name\":\"validation_route_config_node_kind\",\"value\":\"" << JsonEscape(Cohort().Config.ValidationRouteNodeKind) << "\"},"
         << "{\"name\":\"validation_route_config_target_entry\",\"value\":" << Cohort().Config.ValidationRouteTargetEntry << "},"
         << "{\"name\":\"validation_route_config_alternate_target_entries\",\"value\":\"";
    for (size_t index = 0; index < Cohort().Config.ValidationRouteAlternateTargetEntries.size(); ++index)
    {
        if (index)
            json << ",";
        json << Cohort().Config.ValidationRouteAlternateTargetEntries[index];
    }
    json << "\"},"
         << "{\"name\":\"validation_route_config_add_target_entries\",\"value\":\"";
    for (size_t index = 0; index < Cohort().Config.ValidationRouteAddTargetEntries.size(); ++index)
    {
        if (index)
            json << ",";
        json << Cohort().Config.ValidationRouteAddTargetEntries[index];
    }
    json << "\"},"
         << "{\"name\":\"validation_route_config_activation_area_trigger_id\",\"value\":" << Cohort().Config.ValidationRouteActivationAreaTriggerId << "},"
         << "{\"name\":\"validation_route_config_activation_data_id\",\"value\":" << Cohort().Config.ValidationRouteActivationDataId << "},"
         << "{\"name\":\"validation_route_config_activation_spawn_group_id\",\"value\":" << Cohort().Config.ValidationRouteActivationSpawnGroupId << "},"
         << "{\"name\":\"validation_route_config_activation_action_entry\",\"value\":" << Cohort().Config.ValidationRouteActivationActionEntry << "},"
         << "{\"name\":\"validation_route_config_activation_action_id\",\"value\":" << Cohort().Config.ValidationRouteActivationActionId << "},"
         << "{\"name\":\"validation_route_config_activation_summon_entry\",\"value\":" << Cohort().Config.ValidationRouteActivationSummonEntry << "},"
         << "{\"name\":\"validation_route_config_opener_summon_entry\",\"value\":" << Cohort().Config.ValidationRouteOpenerSummonEntry << "},"
         << "{\"name\":\"validation_route_hazard_source_entry\",\"value\":" << Cohort().Config.ValidationRouteHazardSourceEntry << "},"
         << "{\"name\":\"validation_route_hazard_detection_spell_id\",\"value\":" << Cohort().Config.ValidationRouteHazardDetectionSpellId << "},"
         << "{\"name\":\"validation_route_hazard_damage_spell_id\",\"value\":" << Cohort().Config.ValidationRouteHazardDamageSpellId << "},"
         << "{\"name\":\"validation_route_hazard_shape\",\"value\":\"" << JsonEscape(Cohort().Config.ValidationRouteHazardShape) << "\"},"
         << "{\"name\":\"validation_route_hazard_radius_yards\",\"value\":" << Cohort().Config.ValidationRouteHazardRadiusYards << "},"
         << "{\"name\":\"validation_route_minimum_distance_source_entry\",\"value\":" << Cohort().Config.ValidationRouteMinimumDistanceSourceEntry << "},"
         << "{\"name\":\"validation_route_minimum_distance_yards\",\"value\":" << Cohort().Config.ValidationRouteMinimumDistanceYards << "},"
         << "{\"name\":\"validation_route_split_source_count\",\"value\":" << Cohort().Config.ValidationRouteSplitSourceGuids.size() << "},"
         << "{\"name\":\"validation_route_split_minimum_separation_yards\",\"value\":" << Cohort().Config.ValidationRouteSplitMinimumSeparationYards << "},"
         << "{\"name\":\"validation_route_split_navigation_margin_yards\",\"value\":" << Cohort().Config.ValidationRouteSplitNavigationMarginYards << "},"
         << "{\"name\":\"validation_route_split_arrival_tolerance_yards\",\"value\":" << Cohort().Config.ValidationRouteSplitArrivalToleranceYards << "},"
         << "{\"name\":\"validation_route_split_tank_arrival_tolerance_yards\",\"value\":" << Cohort().Config.ValidationRouteSplitTankArrivalToleranceYards << "},"
         << "{\"name\":\"validation_route_split_native_melee_stop_yards\",\"value\":" << Cohort().Config.ValidationRouteSplitNativeMeleeStopYards << "},"
         << "{\"name\":\"validation_route_split_seed_slot_count\",\"value\":" << Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() << "},"
         << "{\"name\":\"validation_route_split_seed_source_0_slot\",\"value\":" << (Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() == 2 ? Cohort().Config.ValidationRouteSplitSeedRosterSlots[0] : 0) << "},"
         << "{\"name\":\"validation_route_split_seed_source_1_slot\",\"value\":" << (Cohort().Config.ValidationRouteSplitSeedRosterSlots.size() == 2 ? Cohort().Config.ValidationRouteSplitSeedRosterSlots[1] : 0) << "},"
         << "{\"name\":\"validation_route_split_seed_max_range_yards\",\"value\":" << Cohort().Config.ValidationRouteSplitSeedMaxRangeYards << "},"
         << "{\"name\":\"validation_route_split_tank_threat_headroom_multiplier\",\"value\":" << Cohort().Config.ValidationRouteSplitTankThreatHeadroomMultiplier << "},"
         << "{\"name\":\"validation_route_thunderclap_spell_id\",\"value\":" << Cohort().Config.ValidationRouteThunderclapSpellId << "},"
         << "{\"name\":\"validation_route_charge_spell_id\",\"value\":" << Cohort().Config.ValidationRouteChargeSpellId << "},"
         << "{\"name\":\"validation_route_charge_range_yards\",\"value\":" << Cohort().Config.ValidationRouteChargeRangeYards << "},"
         << "{\"name\":\"validation_route_charge_native_interval_ms\",\"value\":" << Cohort().Config.ValidationRouteChargeNativeIntervalMs << "},"
         << "{\"name\":\"validation_route_vengeful_rage_spell_id\",\"value\":" << Cohort().Config.ValidationRouteVengefulRageSpellId << "},"
         << "{\"name\":\"validation_route_has_activation\",\"value\":" << (hasValidationRouteActivation ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_manager_activation_applied\",\"value\":" << (Party().ValidationRouteActivationApplied ? "true" : "false") << "},"
         << "{\"name\":\"validation_route_manager_activation_attempts\",\"value\":" << Party().ValidationRouteActivationAttempts << "},"
         << "{\"name\":\"validation_route_distance\",\"value\":" << validationRouteDistance << "},"
         << "{\"name\":\"decision_fingerprint_hash\",\"value\":" << state.LastDecisionFingerprintHash << "},"
         << "{\"name\":\"decision_fingerprint_repeat_count\",\"value\":" << state.LastDecisionFingerprintRepeatCount << "},"
         << "{\"name\":\"decision_fingerprint_failure_count\",\"value\":" << state.LastDecisionFingerprintFailureCount << "},"
         << "{\"name\":\"consecutive_same_decision_count\",\"value\":" << state.ConsecutiveSameDecisionCount << "},"
         << "{\"name\":\"idle_decision_repeat_count\",\"value\":" << state.IdleDecisionRepeatCount << "},"
         << "{\"name\":\"target_churn_count\",\"value\":" << state.TargetChurnCount << "},"
         << "{\"name\":\"loop_guardrail_count\",\"value\":" << state.LoopGuardrailCount << "},"
         << "{\"name\":\"last_loop_guardrail_action\",\"value\":\"" << JsonEscape(state.LastLoopGuardrailAction) << "\"},"
         << "{\"name\":\"last_loop_guardrail_reason\",\"value\":\"" << JsonEscape(state.LastLoopGuardrailReason) << "\"},"
         << "{\"name\":\"loop_recovery_cooldown_until_ms\",\"value\":" << state.LoopRecoveryCooldownUntilMs << "},"
         << "{\"name\":\"recovery_attempt_count\",\"value\":" << state.RecoveryAttemptCount << "},"
         << "{\"name\":\"last_recovery_mode\",\"value\":\"" << JsonEscape(state.LastRecoveryMode) << "\"},"
         << "{\"name\":\"last_recovery_result\",\"value\":\"" << JsonEscape(state.LastRecoveryResult) << "\"},"
         << "{\"name\":\"validation_descent_phase\",\"value\":\"" << ValidationDescentPhaseName(state.ValidationRouteDescentPhase) << "\"},"
         << "{\"name\":\"validation_descent_departure_observed\",\"value\":" << (state.ValidationRouteDescentDepartureObserved ? "true" : "false") << "},"
         << "{\"name\":\"validation_descent_falling_observed\",\"value\":" << (state.ValidationRouteDescentFallingObserved ? "true" : "false") << "},"
         << "{\"name\":\"validation_descent_landing_observed\",\"value\":" << (state.ValidationRouteDescentLandingObserved ? "true" : "false") << "},"
         << "{\"name\":\"validation_descent_health_margin_satisfied\",\"value\":" << (state.ValidationRouteDescentHealthMarginSatisfied ? "true" : "false") << "},"
         << "{\"name\":\"validation_descent_onward_path_proven\",\"value\":" << (state.ValidationRouteDescentLandingPathProven ? "true" : "false") << "},"
         << "{\"name\":\"validation_descent_monotonic_progress\",\"value\":" << (state.ValidationRouteDescentMonotonicProgressObserved ? "true" : "false") << "},"
         << "{\"name\":\"validation_descent_reject_reason\",\"value\":\"" << JsonEscape(state.ValidationRouteDescentRejectReason) << "\"},"
         << "{\"name\":\"server_provisioned\",\"value\":" << (state.ServerProvisioned ? "true" : "false") << "},"
         << "{\"name\":\"battle_res_decision\",\"value\":\"" << JsonEscape(state.NativeBattleResDecision) << "\"},"
         << "{\"name\":\"battle_res_owner_guid\",\"value\":" << state.NativeBattleResOwnerGuid.GetCounter() << "},"
         << "{\"name\":\"battle_res_spell_id\",\"value\":" << state.NativeBattleResSpellId << "},"
         << "{\"name\":\"battle_res_decision_until_ms\",\"value\":" << state.NativeBattleResDecisionUntilMs << "},"
         << "{\"name\":\"blocked\",\"value\":" << (state.Blocked ? "true" : "false") << "},"
         << "{\"name\":\"blocked_episode_id\",\"value\":" << state.BlockedEpisodeId << "},"
         << "{\"name\":\"blocked_first_reason\",\"value\":\"" << JsonEscape(state.BlockedFirstReason) << "\"},"
         << "{\"name\":\"blocked_current_reason\",\"value\":\"" << JsonEscape(state.BlockedReason) << "\"},"
         << "{\"name\":\"blocked_resolution\",\"value\":\"" << JsonEscape(state.BlockedResolution) << "\"},"
         << "{\"name\":\"blocked_resolved_by\",\"value\":\"" << JsonEscape(state.BlockedResolvedBy) << "\"},"
         << "{\"name\":\"pet_db_row_present\",\"value\":" << (petDbRowPresent ? "true" : "false") << "},"
         << "{\"name\":\"pet_db_id\",\"value\":" << petDbId << "},"
         << "{\"name\":\"pet_db_entry\",\"value\":" << petDbEntry << "},"
         << "{\"name\":\"pet_store_active\",\"value\":" << (activePetData ? "true" : "false") << "},"
         << "{\"name\":\"pet_guid\",\"value\":" << (livePet ? livePet->GetGUID().GetCounter() : 0) << "},"
         << "{\"name\":\"pet_entry\",\"value\":" << (livePet ? livePet->GetEntry() : (activePetData ? activePetData->CreatureId : 0)) << "},"
         << "{\"name\":\"pet_alive\",\"value\":" << (livePet && livePet->IsAlive() ? "true" : "false") << "},"
         << "{\"name\":\"last_pet_readiness_action\",\"value\":\"" << JsonEscape(state.LastPetReadinessAction) << "\"},"
         << "{\"name\":\"last_pet_readiness_pet_id\",\"value\":" << state.LastPetReadinessPetId << "},"
         << "{\"name\":\"last_pet_readiness_pet_entry\",\"value\":" << state.LastPetReadinessPetEntry << "},"
         << "{\"name\":\"hunter_pet_revive_pending_until_ms\",\"value\":" << state.HunterPetRevivePendingUntilMs << "},"
         << "{\"name\":\"hunter_pet_revive_attempt_count\",\"value\":" << state.HunterPetReviveAttemptCount << "},"
         << "{\"name\":\"paladin_righteous_fury_ready\",\"value\":" << (paladinReady({ 25780 }) ? "true" : "false") << "},"
         << "{\"name\":\"paladin_seal_ready\",\"value\":" << (paladinReady({ 31801 }) ? "true" : "false") << "},"
         << "{\"name\":\"paladin_aura_ready\",\"value\":" << (paladinReady({ 465 }) ? "true" : "false") << "},"
         << "{\"name\":\"paladin_blessing_ready\",\"value\":" << (paladinReady({ 20217, 1126 }) ? "true" : "false") << "},"
         << "{\"name\":\"paladin_divine_plea_ready\",\"value\":" << (paladinReady({ 54428 }) ? "true" : "false") << "}"
         << "]"
         << ",\"next_expected_action\":\"" << JsonEscape(diagnosis.NextExpectedAction) << "\""
         << ",\"suggested_investigation\":\"" << JsonEscape(diagnosis.SuggestedInvestigation) << "\"}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildBotDecisionSnapshotJson(WorldBotState const& state, Player const* bot) const
{
    uint64 nowMs = NowMs();
    MotionMaster const* nativeMotion = bot ? bot->GetMotionMaster() : nullptr;
    std::ostringstream json;
    json << "{\"identity\":{\"bot_guid\":" << state.Guid.GetCounter()
         << ",\"bot_name\":\"" << JsonEscape(bot ? bot->GetName() : "") << "\"}"
         << ",\"runtime\":{\"active\":" << (Cohort().Active ? "true" : "false")
         << ",\"mode\":\"" << RuntimeModeName(Cohort().RuntimeMode) << "\""
         << ",\"non_certifying_assistance\":" << (Cohort().NonCertifyingAssistance ? "true" : "false")
         << ",\"spawn_source\":\"" << JsonEscape(state.SpawnSource) << "\""
         << ",\"server_provisioned\":" << (state.ServerProvisioned ? "true" : "false")
         << ",\"battle_res_decision\":\"" << JsonEscape(state.NativeBattleResDecision) << "\""
         << ",\"battle_res_owner_guid\":" << state.NativeBattleResOwnerGuid.GetCounter()
         << ",\"battle_res_spell_id\":" << state.NativeBattleResSpellId
         << ",\"decision_timer_ms\":" << state.DecisionTimer
         << ",\"last_decision_tick_ms\":" << state.LastDecisionTickMs
         << ",\"time_since_last_decision_ms\":" << (state.LastDecisionTickMs ? nowMs - state.LastDecisionTickMs : 0)
         << ",\"loop_recovery_cooldown_until_ms\":" << state.LoopRecoveryCooldownUntilMs << "}"
         << ",\"movement\":{\"is_moving\":" << (state.IsMoving ? "true" : "false")
         << ",\"native_current_motion_type\":" << (nativeMotion ? uint32(nativeMotion->GetCurrentMovementGeneratorType()) : uint32(MAX_MOTION_TYPE))
         << ",\"native_active_motion_type\":" << (nativeMotion ? uint32(nativeMotion->GetMotionSlotType(MOTION_SLOT_ACTIVE)) : uint32(MAX_MOTION_TYPE))
         << ",\"native_spline_finalized\":" << (bot && bot->movespline->Finalized() ? "true" : "false")
         << ",\"can_fly\":" << (bot && bot->CanFly() ? "true" : "false")
         << ",\"gravity_disabled\":" << (bot && bot->IsGravityDisabled() ? "true" : "false")
         << ",\"active_path_target_guid\":" << (state.ActivePathValid ? state.ActivePathTargetGuid.GetCounter() : 0)
         << ",\"stuck_timer_ms\":" << state.StuckTimer
         << ",\"distance_moved_since_last_decision\":" << state.LastDecisionDistanceMoved
         << ",\"time_since_last_progress_ms\":" << (state.LastMovementProgressMs ? nowMs - state.LastMovementProgressMs : 0)
         << ",\"time_since_last_path_change_ms\":" << (state.LastPathChangeMs ? nowMs - state.LastPathChangeMs : 0) << "}"
         << ",\"movement_planner\":"
         << BotWorldMovement::MovementPlannerObservationJson(
                BotWorldMovement::MovementPlannerDiagnostics().Latest(
                    state.Guid.GetCounter()))
         << ",\"native_recovery_episode\":"
         << BuildNativeRecoveryEpisodeJson(&state)
         << ",\"validation_cohort\":{\"locked\":" << (state.ValidationCohortLocked ? "true" : "false")
         << ",\"leader_guid\":" << state.ValidationCohortLeaderGuid.GetCounter()
         << ",\"group_guid\":" << state.ValidationCohortGroupGuid.GetCounter()
         << ",\"map_id\":" << state.ValidationCohortMapId
         << ",\"instance_id\":" << state.ValidationCohortInstanceId
         << ",\"phase_mask\":" << state.ValidationCohortPhaseMask
         << ",\"current_map_id\":" << (bot ? bot->GetMapId() : 0)
         << ",\"current_instance_id\":" << (bot ? bot->GetInstanceId() : 0)
         << ",\"current_position\":{\"x\":" << (bot ? bot->GetPositionX() : 0.0f)
         << ",\"y\":" << (bot ? bot->GetPositionY() : 0.0f)
         << ",\"z\":" << (bot ? bot->GetPositionZ() : 0.0f)
         << ",\"o\":" << (bot ? bot->GetOrientation() : 0.0f) << "}"
         << ",\"alive\":" << (bot && bot->IsAlive() ? "true" : "false")
         << ",\"ghost\":" << (bot && bot->HasFlag(PLAYER_FLAGS, PLAYER_FLAGS_GHOST) ? "true" : "false")
         << ",\"has_corpse\":" << (bot && bot->HasCorpse() ? "true" : "false")
         << ",\"in_world\":" << (bot && bot->IsInWorld() ? "true" : "false")
         << ",\"matches_cohort\":" << (IsValidationCohortMemberInOriginalInstance(state, bot) ? "true" : "false")
         << ",\"violation\":" << (state.ValidationCohortViolation ? "true" : "false")
         << ",\"violation_reason\":\"" << JsonEscape(state.ValidationCohortViolationReason) << "\"}"
         << ",\"quest\":{\"state\":\"" << JsonEscape(state.CurrentQuestState) << "\""
         << ",\"phase\":\"" << JsonEscape(state.QuestWork.Phase) << "\""
         << ",\"active_quest_id\":" << state.QuestWork.ActiveQuestId
         << ",\"newly_accepted_quest_id\":" << state.NewlyAcceptedQuestId
         << ",\"objective_index\":" << state.QuestWork.ObjectiveIndex
         << ",\"objective_type\":\"" << JsonEscape(state.QuestWork.ObjectiveType) << "\""
         << ",\"progress_before\":" << state.QuestWork.ProgressBefore
         << ",\"progress_after\":" << state.QuestWork.ProgressAfter << "}"
         << ",\"target\":{\"target_guid\":" << state.LastDecisionTargetGuid.GetCounter()
         << ",\"desired_melee_attack_target_guid\":" << state.DesiredMeleeAttackTargetGuid.GetCounter()
         << ",\"melee_auto_attack_state\":\"" << JsonEscape(state.MeleeAutoAttackState) << "\""
         << ",\"melee_auto_attack_suppression_reason\":\"" << JsonEscape(state.MeleeAutoAttackSuppressionReason) << "\""
         << ",\"melee_auto_attack_intent_owner\":\"" << JsonEscape(state.LastMeleeAutoAttackIntentOwner) << "\""
         << ",\"melee_auto_attack_intent_kind\":\"" << JsonEscape(state.LastMeleeAutoAttackIntentKind) << "\""
         << ",\"melee_auto_attack_intent_reason\":\"" << JsonEscape(state.LastMeleeAutoAttackIntentReason) << "\""
         << ",\"melee_auto_attack_outcome\":\"" << JsonEscape(state.LastMeleeAutoAttackOutcome) << "\""
         << ",\"melee_auto_attack_intent_priority\":" << uint32(state.LastMeleeAutoAttackIntentPriority)
         << ",\"melee_auto_attack_candidate_count\":" << state.LastMeleeAutoAttackCandidateCount
         << ",\"last_rejected_target_reason\":\"" << JsonEscape(state.LastRejectedTargetReason) << "\"}"
         << ",\"policy\":{\"action_category\":\"" << JsonEscape(state.LastActionCategory) << "\""
         << ",\"class_spec_profile\":" << (state.LastClassSpecProfile.empty() ? "{}" : state.LastClassSpecProfile)
         << ",\"role_goal\":\"" << JsonEscape(state.LastRoleGoal) << "\""
         << ",\"role_saturation_state_json\":" << (state.LastRoleSaturationStateJson.empty() ? "{}" : state.LastRoleSaturationStateJson)
         << ",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode) << "\""
         << ",\"saturation_reason\":\"" << JsonEscape(state.LastSaturationReason) << "\""
         << ",\"progression_reason\":" << (state.LastProgressionReason.empty() ? "{}" : state.LastProgressionReason)
         << ",\"profession_goal\":" << (state.LastProfessionGoal.empty() ? "{}" : state.LastProfessionGoal)
         << ",\"valid_action_mask_json\":" << (state.LastValidActionMaskJson.empty() ? "{}" : state.LastValidActionMaskJson)
         << ",\"chosen_action_json\":" << (state.LastChosenActionJson.empty() ? "{}" : state.LastChosenActionJson)
         << ",\"next_expected_action\":\"" << JsonEscape(state.LastNextExpectedAction) << "\""
         << ",\"decision_kernel\":" << (state.LastDecisionKernelJson.empty() ? "{}" : state.LastDecisionKernelJson) << "}"
         << ",\"routing\":{\"active_path_valid\":" << (state.ActivePathValid ? "true" : "false")
         << ",\"from\":{\"x\":" << state.ActivePathFromX << ",\"y\":" << state.ActivePathFromY << ",\"z\":" << state.ActivePathFromZ << "}"
         << ",\"to\":{\"x\":" << state.ActivePathToX << ",\"y\":" << state.ActivePathToY << ",\"z\":" << state.ActivePathToZ << "}"
         << ",\"segment\":{\"valid\":" << (state.ActivePathValid && state.ActivePathSegmentValid ? "true" : "false")
         << ",\"x\":" << state.ActivePathSegmentToX << ",\"y\":" << state.ActivePathSegmentToY << ",\"z\":" << state.ActivePathSegmentToZ
         << ",\"traversal_mode\":\"" << JsonEscape(state.ActivePathTraversalMode) << "\"}"
         << ",\"descent\":{\"phase\":\"" << ValidationDescentPhaseName(state.ValidationRouteDescentPhase) << "\""
         << ",\"generation\":" << state.ValidationRouteDescentGeneration
         << ",\"departure_observed\":" << (state.ValidationRouteDescentDepartureObserved ? "true" : "false")
         << ",\"falling_observed\":" << (state.ValidationRouteDescentFallingObserved ? "true" : "false")
         << ",\"landing_observed\":" << (state.ValidationRouteDescentLandingObserved ? "true" : "false")
         << ",\"health_margin_satisfied\":" << (state.ValidationRouteDescentHealthMarginSatisfied ? "true" : "false")
         << ",\"landing_path_proven\":" << (state.ValidationRouteDescentLandingPathProven ? "true" : "false")
         << ",\"monotonic_progress_observed\":" << (state.ValidationRouteDescentMonotonicProgressObserved ? "true" : "false")
         << ",\"falling_now\":" << (bot && bot->IsFalling() ? "true" : "false")
         << ",\"landing_health_pct\":" << state.ValidationRouteDescentLandingHealthPct
         << ",\"initial_goal_distance\":" << state.ValidationRouteDescentInitialGoalDistance
         << ",\"best_goal_distance\":" << state.ValidationRouteDescentBestGoalDistance
         << ",\"reject_reason\":\"" << JsonEscape(state.ValidationRouteDescentRejectReason) << "\"}"
         << ",\"quest_search_destination\":{\"valid\":" << (state.QuestSearchDestination.Valid ? "true" : "false")
         << ",\"map\":" << state.QuestSearchDestination.MapId << ",\"x\":" << state.QuestSearchDestination.X << ",\"y\":" << state.QuestSearchDestination.Y << ",\"z\":" << state.QuestSearchDestination.Z
         << ",\"quest_id\":" << state.QuestSearchDestination.QuestId << ",\"reason\":\"" << JsonEscape(state.QuestSearchDestination.Reason) << "\"}"
         << ",\"quest_route_destination\":{\"valid\":" << (state.QuestRouteDestination.Valid ? "true" : "false")
         << ",\"map\":" << state.QuestRouteDestination.MapId << ",\"x\":" << state.QuestRouteDestination.X << ",\"y\":" << state.QuestRouteDestination.Y << ",\"z\":" << state.QuestRouteDestination.Z
         << ",\"quest_id\":" << state.QuestRouteDestination.QuestId << ",\"reason\":\"" << JsonEscape(state.QuestRouteDestination.Reason) << "\"}}"
         << ",\"decision\":{\"situation\":\"" << JsonEscape(state.LastDecisionSituation) << "\""
         << ",\"action\":\"" << JsonEscape(state.LastDecisionAction) << "\""
         << ",\"selected_activity\":\"" << JsonEscape(state.LastDecisionActivity) << "\""
         << ",\"last_handler\":\"" << JsonEscape(state.LastDecisionHandler) << "\""
         << ",\"result\":\"" << JsonEscape(state.LastDecisionResult) << "\""
         << ",\"reason\":\"" << JsonEscape(state.LastDecisionReason) << "\""
         << ",\"quest_id\":" << state.LastDecisionQuestId
         << ",\"fingerprint_hash\":" << state.LastDecisionFingerprintHash
         << ",\"fingerprint_repeat_count\":" << state.LastDecisionFingerprintRepeatCount
         << ",\"fingerprint_failure_count\":" << state.LastDecisionFingerprintFailureCount
         << ",\"consecutive_same_decision_count\":" << state.ConsecutiveSameDecisionCount
         << ",\"idle_decision_repeat_count\":" << state.IdleDecisionRepeatCount
         << ",\"target_churn_count\":" << state.TargetChurnCount << "}"
         << ",\"recovery\":{\"loop_guardrail_count\":" << state.LoopGuardrailCount
         << ",\"last_loop_guardrail_ms\":" << state.LastLoopGuardrailMs
         << ",\"last_loop_guardrail_action\":\"" << JsonEscape(state.LastLoopGuardrailAction) << "\""
         << ",\"last_loop_guardrail_reason\":\"" << JsonEscape(state.LastLoopGuardrailReason) << "\""
         << ",\"recovery_attempt_count\":" << state.RecoveryAttemptCount
         << ",\"last_recovery_ms\":" << state.LastRecoveryMs
         << ",\"last_recovery_mode\":\"" << JsonEscape(state.LastRecoveryMode) << "\""
         << ",\"last_recovery_result\":\"" << JsonEscape(state.LastRecoveryResult) << "\""
         << ",\"native_path_floor\":{\"failure\":\""
         << BotWorldMovement::NativePathFloorFailureName(
                state.LastNativePathFloorObservation.Failure)
         << "\",\"segment_index\":" << state.LastNativePathFloorObservation.SegmentIndex
         << ",\"sample_index\":" << state.LastNativePathFloorObservation.SampleIndex
         << ",\"x\":" << state.LastNativePathFloorObservation.X
         << ",\"y\":" << state.LastNativePathFloorObservation.Y
         << ",\"z\":" << state.LastNativePathFloorObservation.Z
         << ",\"resolved_floor_z\":" << state.LastNativePathFloorObservation.ResolvedFloorZ
         << ",\"reference_z\":" << state.LastNativePathFloorObservation.ReferenceZ << "}"
         << ",\"blocked\":" << (state.Blocked ? "true" : "false")
         << ",\"blocked_episode_id\":" << state.BlockedEpisodeId
         << ",\"blocked_first_reason\":\"" << JsonEscape(state.BlockedFirstReason) << "\""
         << ",\"blocked_current_reason\":\"" << JsonEscape(state.BlockedReason) << "\""
         << ",\"blocked_resolution\":\"" << JsonEscape(state.BlockedResolution) << "\""
         << ",\"blocked_resolved_by\":\"" << JsonEscape(state.BlockedResolvedBy) << "\"}"
         << ",\"recent_failures\":{\"quest_failure_reason\":\"" << JsonEscape(state.QuestWork.FailedReason) << "\""
         << ",\"last_objective_not_found_reason\":\"" << JsonEscape(state.LastObjectiveNotFoundReason) << "\""
         << ",\"last_no_progress_reason\":\"" << JsonEscape(state.LastNoProgressReason) << "\""
         << ",\"last_no_quest_reason\":\"" << JsonEscape(state.LastNoQuestReason) << "\""
         << ",\"quest_cooldown_count\":" << state.QuestCooldownUntilMs.size()
         << ",\"no_progress_cooldown_count\":" << state.NoProgressCooldownUntilMs.size() << "}"
         << ",\"combat_attempt\":" << BuildCombatAttemptJson(state.LastCombatAttempt)
         << ",\"route_progress\":" << BuildRouteProgressJson(state.LastRouteProgress)
         << "}";
    return json.str();
}

std::string BotWorldPopulationMgr::BuildBotTraceEntriesJson(WorldBotState const& state, uint32 limit) const
{
    if (!limit)
        limit = 20;
    limit = std::min<uint32>(limit, 128);

    auto appendGuidArray = [](std::ostringstream& output, std::vector<uint32> const& guids)
    {
        output << "[";
        for (size_t index = 0; index < guids.size(); ++index)
        {
            if (index)
                output << ",";
            output << guids[index];
        }
        output << "]";
    };

    std::ostringstream json;
    json << "[";
    uint32 emitted = 0;
    for (auto itr = state.DecisionTrace.rbegin(); itr != state.DecisionTrace.rend() && emitted < limit; ++itr, ++emitted)
    {
        if (emitted)
            json << ",";
        json << "{\"timestamp_ms\":" << itr->TimestampMs
             << ",\"sequence\":" << itr->Sequence
             << ",\"decision_sequence\":" << itr->DecisionSequence
             << ",\"situation\":\"" << JsonEscape(itr->Situation) << "\""
             << ",\"action\":\"" << JsonEscape(itr->Action) << "\""
             << ",\"route_node_id\":\"" << JsonEscape(itr->RouteNodeId) << "\""
             << ",\"route_generation\":" << itr->RouteGeneration
             << ",\"quest_id\":" << itr->QuestId
             << ",\"target_id\":" << itr->TargetGuid
             << ",\"destination\":{\"map\":" << itr->DestinationMapId << ",\"x\":" << itr->DestinationX << ",\"y\":" << itr->DestinationY << ",\"z\":" << itr->DestinationZ << "}"
             << ",\"result\":\"" << JsonEscape(itr->Result) << "\""
             << ",\"reason_code\":\"" << JsonEscape(itr->ReasonCode) << "\""
             << ",\"fingerprint_hash\":" << itr->FingerprintHash
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
             << ",\"engaged_hostile_guids\":";
        appendGuidArray(json, itr->EngagedHostileGuids);
        json << ",\"tank_owned_hostile_guids\":";
        appendGuidArray(json, itr->TankOwnedHostileGuids);
        json << ",\"healer_targeting_hostile_guids\":";
        appendGuidArray(json, itr->HealerTargetingHostileGuids);
        json << ",\"tank_threat_aura_active\":" << (itr->TankThreatAuraActive ? "true" : "false") << "}"
             << ",\"pet_alive\":" << (itr->PetAlive ? "true" : "false")
             << ",\"loop_guardrail_action\":\"" << JsonEscape(itr->LoopGuardrailAction) << "\""
             << ",\"loop_guardrail_reason\":\"" << JsonEscape(itr->LoopGuardrailReason) << "\""
             << ",\"recovery_mode\":\"" << JsonEscape(itr->RecoveryMode) << "\""
             << ",\"recovery_result\":\"" << JsonEscape(itr->RecoveryResult) << "\""
             << ",\"native_path_floor\":{\"failure\":\""
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
             << ",\"blocked_first_reason\":\"" << JsonEscape(itr->BlockedFirstReason) << "\""
             << ",\"blocked_current_reason\":\"" << JsonEscape(itr->BlockedCurrentReason) << "\""
             << ",\"blocked_resolution\":\"" << JsonEscape(itr->BlockedResolution) << "\""
             << ",\"blocked_resolved_by\":\"" << JsonEscape(itr->BlockedResolvedBy) << "\""
             << ",\"action_category\":\"" << JsonEscape(state.LastActionCategory) << "\""
             << ",\"role_goal\":\"" << JsonEscape(state.LastRoleGoal) << "\""
             << ",\"recommended_balance_mode\":\"" << JsonEscape(state.LastRecommendedBalanceMode) << "\""
             << ",\"saturation_reason\":\"" << JsonEscape(state.LastSaturationReason) << "\""
             << ",\"mechanic_family\":\"" << JsonEscape(state.LastMechanicFamily) << "\""
             << ",\"encounter_role_responsibility\":\"" << JsonEscape(state.LastEncounterRoleResponsibility) << "\""
             << ",\"next_expected_action\":\"" << JsonEscape(state.LastNextExpectedAction) << "\""
             << ",\"combat_attempt\":" << BuildCombatAttemptJson(itr->CombatAttempt)
             << ",\"route_progress\":" << BuildRouteProgressJson(itr->RouteProgress) << "}";
    }
    json << "]";
    return json.str();
}

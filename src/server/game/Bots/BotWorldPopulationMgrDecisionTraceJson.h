#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_DECISION_TRACE_JSON_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_DECISION_TRACE_JSON_H

#include "Bots/BotWorldPopulationMgrBotState.h"

#include <limits>
#include <ostream>

namespace BotWorldTrace
{
template <class Escape>
void AppendTargetObservationJson(std::ostream& json,
    BotWorldPopulationMgrBotState::WorldBotState::DecisionTraceEntry::TargetObservation const& target,
    Escape const& escape)
{
    (void)escape;
    json << "{\"guid\":" << target.Guid
         << ",\"guid_raw\":" << target.GuidRaw
         << ",\"entry\":" << target.Entry
         << ",\"native_present\":" << (target.NativePresent ? "true" : "false")
         << ",\"alive\":" << (target.Alive ? "true" : "false")
         << ",\"valid_attack_target\":" << (target.ValidAttackTarget ? "true" : "false")
         << ",\"distance\":";
    if (target.DistanceAvailable)
        json << target.Distance;
    else
        json << "null";
    json << ",\"distance_within_45yd\":";
    if (target.DistanceAvailable)
        json << (target.DistanceWithin45Yd ? "true" : "false");
    else
        json << "null";
    json << ",\"line_of_sight\":";
    if (target.LineOfSightAvailable)
        json << (target.LineOfSight ? "true" : "false");
    else
        json << "null";
    json << ",\"position\":{\"available\":"
         << (target.PositionAvailable ? "true" : "false")
         << ",\"x\":";
    if (target.PositionAvailable)
        json << target.X;
    else
        json << "null";
    json << ",\"y\":";
    if (target.PositionAvailable)
        json << target.Y;
    else
        json << "null";
    json << ",\"z\":";
    if (target.PositionAvailable)
        json << target.Z;
    else
        json << "null";
    json << "}}";
}

inline void AppendNativeActorObservationJson(std::ostream& json,
    BotWorldPopulationMgrBotState::WorldBotState::DecisionTraceEntry::NativeActorObservation const& actor)
{
    json << "{\"native_present\":" << (actor.NativePresent ? "true" : "false")
         << ",\"in_world\":" << (actor.InWorld ? "true" : "false")
         << ",\"alive\":" << (actor.Alive ? "true" : "false")
         << ",\"position\":{\"available\":"
         << (actor.PositionAvailable ? "true" : "false")
         << ",\"x\":";
    if (actor.PositionAvailable)
        json << actor.X;
    else
        json << "null";
    json << ",\"y\":";
    if (actor.PositionAvailable)
        json << actor.Y;
    else
        json << "null";
    json << ",\"z\":";
    if (actor.PositionAvailable)
        json << actor.Z;
    else
        json << "null";
    json << "},\"moving\":" << (actor.Moving ? "true" : "false")
         << ",\"spline\":{\"initialized\":"
         << (actor.SplineInitialized ? "true" : "false")
         << ",\"finalized\":" << (actor.SplineFinalized ? "true" : "false")
         << ",\"id\":" << actor.SplineId << "}"
         << ",\"current_generic_spell_id\":"
         << actor.CurrentGenericSpellId << "}";
}

template <class Escape, class CombatJson, class RouteJson>
void AppendDecisionTraceEntryJson(std::ostream& json,
    BotWorldPopulationMgrBotState::WorldBotState::DecisionTraceEntry const& entry,
    Escape const& escape, CombatJson const& combatJson,
    RouteJson const& routeJson)
{
    auto appendGuids = [&json](std::vector<uint32> const& guids)
    {
        json << '[';
        for (std::size_t index = 0; index < guids.size(); ++index)
        {
            if (index)
                json << ',';
            json << guids[index];
        }
        json << ']';
    };

    json << "{\"timestamp_ms\":" << entry.TimestampMs
         << ",\"sequence\":" << entry.Sequence
         << ",\"decision_sequence\":" << entry.DecisionSequence
         << ",\"server_epoch\":" << entry.ServerEpoch
         << ",\"attempt_id\":" << entry.AttemptId
         << ",\"wipe_generation\":" << entry.WipeGeneration
         << ",\"cohort_id\":\"" << escape(entry.CohortId) << "\""
         << ",\"actor\":{\"guid\":" << entry.ActorGuid
         << ",\"guid_raw\":" << entry.ActorGuidRaw
         << ",\"map_id\":" << entry.ActorMapId
         << ",\"instance_id\":" << entry.ActorInstanceId
         << ",\"role\":\"" << escape(entry.ActorRole) << "\"}"
         << ",\"situation\":\"" << escape(entry.Situation) << "\""
         << ",\"action\":\"" << escape(entry.Action) << "\""
         << ",\"route_node_id\":\"" << escape(entry.RouteNodeId) << "\""
         << ",\"route_generation\":" << entry.RouteGeneration
         << ",\"quest_id\":" << entry.QuestId
         << ",\"target_id\":" << entry.TargetGuid
         << ",\"destination\":{\"map\":" << entry.DestinationMapId
         << ",\"x\":" << entry.DestinationX
         << ",\"y\":" << entry.DestinationY
         << ",\"z\":" << entry.DestinationZ << "}"
         << ",\"result\":\"" << escape(entry.Result) << "\""
         << ",\"reason_code\":\"" << escape(entry.ReasonCode) << "\""
         << ",\"fingerprint_hash\":" << entry.FingerprintHash
         << ",\"fingerprint_repeat_count\":" << entry.FingerprintRepeatCount
         << ",\"fingerprint_failure_count\":" << entry.FingerprintFailureCount
         << ",\"consecutive_same_decision_count\":" << entry.ConsecutiveSameDecisionCount
         << ",\"idle_decision_repeat_count\":" << entry.IdleDecisionRepeatCount
         << ",\"target_churn_count\":" << entry.TargetChurnCount
         << ",\"suppressed_repeatable_event_count\":" << entry.SuppressedRepeatableEventCount
         << ",\"suppressed_repeatable_decision_count\":" << entry.SuppressedRepeatableDecisionCount
         << ",\"threat_snapshot\":{\"engaged_hostiles\":" << entry.EngagedHostileCount
         << ",\"tank_owned_hostiles\":" << entry.TankOwnedHostileCount
         << ",\"healer_targeting_hostiles\":" << entry.HealerTargetingHostileCount
         << ",\"engaged_hostile_guids\":";
    appendGuids(entry.EngagedHostileGuids);
    json << ",\"tank_owned_hostile_guids\":";
    appendGuids(entry.TankOwnedHostileGuids);
    json << ",\"healer_targeting_hostile_guids\":";
    appendGuids(entry.HealerTargetingHostileGuids);
    json << ",\"tank_threat_aura_active\":" << (entry.TankThreatAuraActive ? "true" : "false") << "}"
         << ",\"pet_alive\":" << (entry.PetAlive ? "true" : "false")
         << ",\"loop_guardrail_action\":\"" << escape(entry.LoopGuardrailAction) << "\""
         << ",\"loop_guardrail_reason\":\"" << escape(entry.LoopGuardrailReason) << "\""
         << ",\"recovery_mode\":\"" << escape(entry.RecoveryMode) << "\""
         << ",\"recovery_result\":\"" << escape(entry.RecoveryResult) << "\""
         << ",\"native_path_floor\":{\"failure\":\""
         << BotWorldMovement::NativePathFloorFailureName(entry.NativePathFloor.Failure)
         << "\",\"segment_index\":" << entry.NativePathFloor.SegmentIndex
         << ",\"sample_index\":" << entry.NativePathFloor.SampleIndex
         << ",\"x\":" << entry.NativePathFloor.X
         << ",\"y\":" << entry.NativePathFloor.Y
         << ",\"z\":" << entry.NativePathFloor.Z
         << ",\"resolved_floor_z\":" << entry.NativePathFloor.ResolvedFloorZ
         << ",\"reference_z\":" << entry.NativePathFloor.ReferenceZ << "}"
         << ",\"movement_planner\":"
         << BotWorldMovement::MovementPlannerObservationJson(
                entry.MovementPlanner ? *entry.MovementPlanner
                                      : BotWorldMovement::MovementPlannerObservation())
         << ",\"blocked_episode_id\":" << entry.BlockedEpisodeId
         << ",\"blocked_first_reason\":\"" << escape(entry.BlockedFirstReason) << "\""
         << ",\"blocked_current_reason\":\"" << escape(entry.BlockedCurrentReason) << "\""
         << ",\"blocked_resolution\":\"" << escape(entry.BlockedResolution) << "\""
         << ",\"blocked_resolved_by\":\"" << escape(entry.BlockedResolvedBy) << "\""
         << ",\"policy_observed_at_ms\":" << entry.PolicyObservedAtMs
         << ",\"action_category\":\"" << escape(entry.ActionCategory) << "\""
         << ",\"role_goal\":\"" << escape(entry.RoleGoal) << "\""
         << ",\"recommended_balance_mode\":\"" << escape(entry.RecommendedBalanceMode) << "\""
         << ",\"saturation_reason\":\"" << escape(entry.SaturationReason) << "\""
         << ",\"mechanic_family\":\"" << escape(entry.MechanicFamily) << "\""
         << ",\"encounter_role_responsibility\":\""
         << escape(entry.EncounterRoleResponsibility) << "\""
         << ",\"next_expected_action\":\"" << escape(entry.NextExpectedAction) << "\""
         << ",\"event_target\":";
    AppendTargetObservationJson(json, entry.EventTarget, escape);
    json << ",\"native_selected_target\":";
    AppendTargetObservationJson(json, entry.NativeSelectedTarget, escape);
    json << ",\"state_bound_target\":";
    AppendTargetObservationJson(json, entry.StateBoundTarget, escape);
    json << ",\"native_actor\":";
    AppendNativeActorObservationJson(json, entry.NativeActor);
    json << ",\"target_return\":{\"captured_at_ms\":" << entry.TimestampMs
         << ",\"observed_at_ms\":";
    if (entry.TargetReturn)
        json << entry.TargetReturn->ObservedAtMs;
    else
        json << "null";
    json << ",\"age_ms\":";
    if (entry.TargetReturnAgeAvailable)
        json << entry.TargetReturnAgeMs;
    else
        json << "null";
    json << ",\"current_at_record\":"
         << (entry.TargetReturnCurrentAtRecord ? "true" : "false")
         << ",\"stale\":"
         << (entry.TargetReturn && !entry.TargetReturnCurrentAtRecord
                ? "true" : "false")
         << ",\"observation\":";
    if (entry.TargetReturn)
        json << BotEncounter::MagmawTargetReturnObservation::BuildJson(
            *entry.TargetReturn,
            entry.TargetReturnCurrentAtRecord ? entry.TargetReturn->AttemptId
                : std::numeric_limits<uint64>::max(),
            entry.TargetReturnCurrentAtRecord
                ? entry.TargetReturn->RouteGeneration
                : std::numeric_limits<uint64>::max(),
            entry.TargetReturnCurrentAtRecord
                ? entry.TargetReturn->SnapshotRevision
                : std::numeric_limits<uint64>::max(),
            entry.TargetReturnCurrentAtRecord
                ? entry.TargetReturn->RouteNodeId : "");
    else
        json << "null";
    json << "}"
         << ",\"native_spell_finish\":"
         << (entry.NativeSpellFinishJson.empty() ? "null" : entry.NativeSpellFinishJson)
         << ",\"combat_attempt\":" << combatJson(entry.CombatAttempt)
         << ",\"route_progress\":" << routeJson(entry.RouteProgress) << "}";
}
}

#endif

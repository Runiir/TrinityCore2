#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "GitRevision.h"
#include "Player.h"

#include <cstdint>
#include <sstream>
#include <string>

namespace
{
using BotProfileCombatRangeCheckpoint::Stage;
using BotProfileCombatRangeCheckpoint::State;

bool IsLowerHex(std::string const& value, size_t expectedLength)
{
    if (value.size() != expectedLength)
        return false;
    for (char character : value)
        if (!((character >= '0' && character <= '9')
                || (character >= 'a' && character <= 'f')))
            return false;
    return true;
}

std::string EscapeJson(std::string const& value)
{
    std::string escaped;
    escaped.reserve(value.size());
    for (char character : value)
    {
        if (character == '"' || character == '\\')
            escaped.push_back('\\');
        if (character == '\n')
            escaped += "\\n";
        else if (character != '\r')
            escaped.push_back(character);
    }
    return escaped;
}

bool ValidAdmission(BotWorldExperimentConfig const& config,
    std::string const& nativeRevisionHash)
{
    return config.ProfileCombatRangeCheckpointEnable
        && config.ProfileCombatRangeCheckpointFixtureId
            == BotProfileCombatRangeCheckpoint::FixtureId
        && !config.ProfileCombatRangeCheckpointCaseId.empty()
        && IsLowerHex(config.ProfileCombatRangeCheckpointSealSha256, 64)
        && IsLowerHex(config.ProfileCombatRangeCheckpointSourceCommit, 40)
        && nativeRevisionHash.rfind(
            config.ProfileCombatRangeCheckpointSourceCommit, 0) == 0
        && config.ProfileCombatRangeCheckpointActorGuid
        && config.ProfileCombatRangeCheckpointTargetGuid;
}

bool IsCommitted(BotActionArbitration::CandidateTrace const& trace)
{
    using BotActionArbitration::Phase;
    return trace.Status == "attempted"
        && static_cast<uint8>(trace.LifecyclePhase)
            >= static_cast<uint8>(Phase::Submitted);
}

bool HasLaterDecreasingProgress(
    BotWorldMovement::NativeMovementProgressObservation const& progress,
    uint64 decisionTimestampMs)
{
    if (!progress.Available || progress.Samples.size() < 2)
        return false;
    bool laterSample = false;
    for (size_t index = 1; index < progress.Samples.size(); ++index)
    {
        auto const& previous = progress.Samples[index - 1];
        auto const& current = progress.Samples[index];
        laterSample = laterSample || current.ObservedAtMs > decisionTimestampMs;
        if (current.ObservedAtMs > decisionTimestampMs
            && current.EndpointDistance < previous.EndpointDistance)
            return true;
    }
    return laterSample && progress.Samples.back().EndpointProgressed;
}

uint32 LatestSplineId(
    BotWorldMovement::MovementPlannerObservation const& planner)
{
    for (auto itr = planner.LaunchReceipt.Launches.rbegin();
        itr != planner.LaunchReceipt.Launches.rend(); ++itr)
        if (itr->SplineInitialized)
            return itr->SplineId;
    return 0;
}
}

std::string BotWorldPopulationMgr::GetProfileCombatRangeCheckpointJsonForCohort(
    std::string const& cohortId) const
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson(
            "botauto_profile_combat_range_checkpoint", cohortId);
    std::string const previous = _selectedCohortId;
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = cohortId;
    std::string result = BuildProfileCombatRangeCheckpointJson();
    const_cast<BotWorldPopulationMgr*>(this)->_selectedCohortId = previous;
    return result;
}

void BotWorldPopulationMgr::ObserveProfileCombatRangeCheckpoint(
    BotUpdateContext& context)
{
    State& checkpoint = Cohort().ProfileCombatRangeCheckpoint;
    if (!Cohort().Config.ProfileCombatRangeCheckpointEnable
        || checkpoint.Terminal())
        return;

    std::string const nativeRevisionHash = GitRevision::GetHash();
    if (!ValidAdmission(Cohort().Config, nativeRevisionHash))
    {
        checkpoint.Fail("profile_combat_range_checkpoint_admission_invalid");
        return;
    }

    if (checkpoint.CurrentStage == Stage::Disabled)
    {
        checkpoint = {};
        checkpoint.CurrentStage = Stage::Armed;
        checkpoint.CaseId = Cohort().Config.ProfileCombatRangeCheckpointCaseId;
        checkpoint.SealSha256 =
            Cohort().Config.ProfileCombatRangeCheckpointSealSha256;
        checkpoint.SourceCommit =
            Cohort().Config.ProfileCombatRangeCheckpointSourceCommit;
        checkpoint.ActorGuid =
            Cohort().Config.ProfileCombatRangeCheckpointActorGuid;
        checkpoint.TargetGuid =
            Cohort().Config.ProfileCombatRangeCheckpointTargetGuid;
        checkpoint.AttemptId = Cohort().AttemptId;
        checkpoint.Outcome = "profile_combat_range_checkpoint_armed";
    }

    if (!context.Bot || context.State.Guid.GetCounter() != checkpoint.ActorGuid)
        return;
    if (!checkpoint.AttemptId || checkpoint.AttemptId != Cohort().AttemptId)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_scope_mismatch");
        return;
    }
    if (++checkpoint.AwaitTicks
        > BotProfileCombatRangeCheckpoint::MaximumAwaitTicks)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_timeout");
        return;
    }

    BotActionArbitration::Resolution const& resolution =
        context.State.DecisionKernel.LastResolution();
    size_t rangeTraceIndex = resolution.Trace.size();
    size_t hazardTraceIndex = resolution.Trace.size();
    for (size_t index = 0; index < resolution.Trace.size(); ++index)
    {
        BotActionArbitration::CandidateTrace const& trace =
            resolution.Trace[index];
        if (trace.Key == "world.profile_combat_range")
            rangeTraceIndex = index;
        if (trace.Key != "world.profile_combat_range"
            && trace.ActionPriority == BotActionArbitration::Priority::Survival
            && (trace.RequiredResources
                & BotActionArbitration::Uses(
                    BotActionArbitration::Resource::Movement))
            && trace.Source != "db_class_spec_profile"
            && IsCommitted(trace))
            hazardTraceIndex = index;
    }

    if (rangeTraceIndex == resolution.Trace.size())
        return;

    BotActionArbitration::CandidateTrace const& rangeTrace =
        resolution.Trace[rangeTraceIndex];
    if (!context.Target)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_target_missing");
        return;
    }
    uint64 const targetGuid = context.Target->GetGUID().GetRawValue();
    if (targetGuid != checkpoint.TargetGuid)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_target_identity_drift");
        return;
    }
    checkpoint.TargetMapId = context.Target->GetMapId();
    checkpoint.TargetInstanceId = context.Target->GetInstanceId();
    bool const rangeCommitted = IsCommitted(rangeTrace)
        && rangeTrace.Reason == "profile_combat_min_range_reconciled";
    if (!checkpoint.MovementCommitted)
    {
        checkpoint.CandidateTraceIndex = rangeTraceIndex;
        checkpoint.CandidateKey = rangeTrace.Key;
        checkpoint.CandidateStatus = rangeTrace.Status;
        checkpoint.CandidateReason = rangeTrace.Reason;
    }
    ++checkpoint.RangeObservationCount;

    if (hazardTraceIndex != resolution.Trace.size())
    {
        BotActionArbitration::CandidateTrace const& hazardTrace =
            resolution.Trace[hazardTraceIndex];
        checkpoint.HazardCandidateKey = hazardTrace.Key;
        checkpoint.HazardCandidateSource = hazardTrace.Source;
        checkpoint.HazardCandidateStatus = hazardTrace.Status;
        checkpoint.HazardTraceIndex = hazardTraceIndex;
    }

    bool const hazardPreempted = !checkpoint.HazardCandidateKey.empty()
        && rangeTrace.Status == "resource_conflict";
    checkpoint.MovementCommitted = checkpoint.MovementCommitted || rangeCommitted;
    checkpoint.MovementNativeSubmitted = checkpoint.MovementNativeSubmitted
        || (rangeCommitted && context.State.LastMovementExecution.NativeSubmitted);
    checkpoint.HazardCandidateStatus = hazardPreempted
        ? "committed_range_resource_conflict" : checkpoint.HazardCandidateStatus;

    if (rangeCommitted && !checkpoint.MovementReceiptId)
    {
        checkpoint.DecisionTimestampMs = context.DecisionNowMs;
        checkpoint.MovementReceiptId =
            context.State.LastMovementExecution.ReceiptId;
        BotWorldMovement::MovementPlannerObservation const planner =
            BotWorldMovement::MovementPlannerDiagnostics().ForReceipt(
                checkpoint.MovementReceiptId);
        checkpoint.NativeMotionType =
            planner.LaunchReceipt.MotionMasterGeneratorType;
        checkpoint.NativeSplineId = LatestSplineId(planner);
    }

    if (checkpoint.MovementReceiptId)
    {
        BotWorldMovement::NativeMovementProgressObservation const progress =
            BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
                checkpoint.MovementReceiptId);
        checkpoint.ProgressSampleCount = uint32(progress.Samples.size());
        checkpoint.MovementProgressObserved = HasLaterDecreasingProgress(
            progress, checkpoint.DecisionTimestampMs);
    }

    BotActionArbitration::CandidateTrace const* castTrace = nullptr;
    for (BotActionArbitration::CandidateTrace const& trace : resolution.Trace)
        if (trace.Key == "world.profile_combat" && IsCommitted(trace))
        {
            castTrace = &trace;
            break;
        }
    if (castTrace && context.State.LastCombatAttempt.TargetGuid.GetRawValue()
            == checkpoint.TargetGuid)
    {
        checkpoint.CastRetryObserved = true;
        checkpoint.CastSpellId = context.State.LastCombatAttempt.SpellId;
        checkpoint.CastTargetGuid = context.State.LastCombatAttempt.TargetGuid
            .GetRawValue();
    }

    if (checkpoint.MovementProgressObserved && checkpoint.CastRetryObserved
        && !checkpoint.HazardCandidateKey.empty())
    {
        checkpoint.CurrentStage = Stage::Completed;
        checkpoint.Outcome = "profile_combat_range_checkpoint_boundary_observed";
    }
    else if (checkpoint.MovementProgressObserved)
    {
        checkpoint.CurrentStage = Stage::ProgressObserved;
        checkpoint.Outcome = "profile_combat_range_checkpoint_progress_observed";
    }
    else if (checkpoint.MovementCommitted)
    {
        checkpoint.CurrentStage = Stage::RangeObserved;
        checkpoint.Outcome = "profile_combat_range_checkpoint_range_observed";
    }
}

std::string BotWorldPopulationMgr::BuildProfileCombatRangeCheckpointJson() const
{
    State const& checkpoint = Cohort().ProfileCombatRangeCheckpoint;
    BotWorldMovement::MovementPlannerObservation const planner =
        checkpoint.MovementReceiptId
            ? BotWorldMovement::MovementPlannerDiagnostics().ForReceipt(
                checkpoint.MovementReceiptId)
            : BotWorldMovement::MovementPlannerObservation{};
    BotWorldMovement::NativeMovementProgressObservation const progress =
        checkpoint.MovementReceiptId
            ? BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
                checkpoint.MovementReceiptId)
            : BotWorldMovement::NativeMovementProgressObservation{};
    std::ostringstream json;
    json << "{\"ok\":"
         << (checkpoint.CurrentStage != Stage::Failed ? "true" : "false")
         << ",\"action\":\"botauto_profile_combat_range_checkpoint\""
         << ",\"authority\":\""
         << BotProfileCombatRangeCheckpoint::Authority << "\""
         << ",\"fixture_id\":\""
         << BotProfileCombatRangeCheckpoint::FixtureId << "\""
         << ",\"case_id\":\"" << EscapeJson(checkpoint.CaseId) << "\""
         << ",\"seal_sha256\":\""
         << EscapeJson(checkpoint.SealSha256) << "\""
         << ",\"source_commit\":\""
         << EscapeJson(checkpoint.SourceCommit) << "\""
         << ",\"stage\":\""
         << BotProfileCombatRangeCheckpoint::StageName(
                checkpoint.CurrentStage) << "\""
         << ",\"terminal\":" << (checkpoint.Terminal() ? "true" : "false")
         << ",\"actor_guid\":" << checkpoint.ActorGuid
         << ",\"target_guid\":" << checkpoint.TargetGuid
         << ",\"attempt_id\":" << checkpoint.AttemptId
         << ",\"target_map_id\":" << checkpoint.TargetMapId
         << ",\"target_instance_id\":" << checkpoint.TargetInstanceId
         << ",\"decision_timestamp_ms\":"
         << checkpoint.DecisionTimestampMs
         << ",\"candidate_trace_index\":"
         << checkpoint.CandidateTraceIndex
         << ",\"candidate_key\":\""
         << EscapeJson(checkpoint.CandidateKey) << "\""
         << ",\"candidate_status\":\""
         << EscapeJson(checkpoint.CandidateStatus) << "\""
         << ",\"candidate_reason\":\""
         << EscapeJson(checkpoint.CandidateReason) << "\""
         << ",\"movement_receipt_id\":" << checkpoint.MovementReceiptId
         << ",\"native_motion_type\":" << checkpoint.NativeMotionType
         << ",\"native_spline_id\":" << checkpoint.NativeSplineId
         << ",\"movement_committed\":"
         << (checkpoint.MovementCommitted ? "true" : "false")
         << ",\"movement_native_submitted\":"
         << (checkpoint.MovementNativeSubmitted ? "true" : "false")
         << ",\"progress_sample_count\":"
         << checkpoint.ProgressSampleCount
         << ",\"movement_progress_observed\":"
         << (checkpoint.MovementProgressObserved ? "true" : "false")
         << ",\"hazard_candidate_key\":\""
         << EscapeJson(checkpoint.HazardCandidateKey) << "\""
         << ",\"hazard_candidate_source\":\""
         << EscapeJson(checkpoint.HazardCandidateSource) << "\""
         << ",\"hazard_candidate_status\":\""
         << EscapeJson(checkpoint.HazardCandidateStatus) << "\""
         << ",\"hazard_trace_index\":" << checkpoint.HazardTraceIndex
         << ",\"cast_spell_id\":" << checkpoint.CastSpellId
         << ",\"cast_target_guid\":" << checkpoint.CastTargetGuid
         << ",\"cast_retry_observed\":"
         << (checkpoint.CastRetryObserved ? "true" : "false")
         << ",\"range_observation_count\":"
         << checkpoint.RangeObservationCount
         << ",\"await_ticks\":" << checkpoint.AwaitTicks
         << ",\"outcome\":\"" << EscapeJson(checkpoint.Outcome) << "\""
         << ",\"failure_reason\":\""
         << EscapeJson(checkpoint.FailureReason) << "\""
         << ",\"movement_planner\":"
         << BotWorldMovement::MovementPlannerObservationJson(planner)
         << ",\"movement_progress\":"
         << BotWorldMovement::MovementProgressObservationJson(progress)
         << "}";
    return json.str();
}

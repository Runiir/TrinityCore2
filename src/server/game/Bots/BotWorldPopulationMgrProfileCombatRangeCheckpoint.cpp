#include "Bots/BotWorldPopulationMgr.h"

#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotWorldPopulationMgrUpdateContext.h"
#include "GitRevision.h"
#include "Player.h"

#include <cstdint>
#include <sstream>
#include <string>
#include <vector>

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

bool IsProfileCheckpointHazardSource(
    BotActionArbitration::CandidateTrace const& trace)
{
    // These are the two shared hazard producers that attach a typed movement
    // diagnostic key before native submission. Other Survival+Movement rows
    // are unrelated safety actions and cannot establish this fixture edge.
    return trace.Source == "adaptive_raid_trash"
        || trace.Source == "shared_hazard_movement";
}

bool SameScope(BotMovementArbitration::Scope const& scope,
    State const& checkpoint)
{
    return scope.AttemptId == checkpoint.AttemptId
        && scope.WipeGeneration == checkpoint.WipeGeneration
        && scope.RouteGeneration == checkpoint.RouteGeneration
        && scope.MapId == checkpoint.TargetMapId
        && scope.InstanceId == checkpoint.TargetInstanceId;
}

bool HasNativeLaunch(BotWorldMovement::MovementPlannerObservation const& planner)
{
    if (!planner.Available
        || !planner.LaunchReceipt.MotionMasterSubmissionObserved
        || !planner.LaunchReceipt.PointGeneratorInitialized)
        return false;
    for (BotWorldMovement::NativeSplineLaunchObservation const& launch
        : planner.LaunchReceipt.Launches)
        if (launch.LaunchAttempted && launch.LaunchSucceeded
            && launch.SplineInitialized)
            return true;
    return false;
}

uint64 LatestDecreasingProgressAt(
    BotWorldMovement::NativeMovementProgressObservation const& progress,
    uint64 afterTimestampMs)
{
    if (!progress.Available || progress.Samples.size() < 2)
        return 0;
    uint64 observedAtMs = 0;
    for (size_t index = 1; index < progress.Samples.size(); ++index)
    {
        auto const& previous = progress.Samples[index - 1];
        auto const& current = progress.Samples[index];
        if (current.ObservedAtMs > afterTimestampMs
            && current.EndpointDistance < previous.EndpointDistance)
            observedAtMs = current.ObservedAtMs;
    }
    if (observedAtMs)
        return observedAtMs;
    if (progress.Samples.back().ObservedAtMs > afterTimestampMs
        && progress.Samples.back().EndpointProgressed)
        return progress.Samples.back().ObservedAtMs;
    return 0;
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

std::string BotWorldPopulationMgr::ArmProfileCombatRangeCheckpointForCohort(
    std::string const& cohortId, uint32 actorGuid, uint64 targetGuid,
    std::string const& caseId, std::string const& sealSha256,
    std::string const& sourceCommit)
{
    if (!FindCohort(cohortId))
        return UnknownCohortJson(
            "botauto_profile_combat_range_checkpoint", cohortId);
    std::string const previous = _selectedCohortId;
    _selectedCohortId = cohortId;
    State& checkpoint = Cohort().ProfileCombatRangeCheckpoint;
    bool actorInCohort = false;
    for (WorldBotState const& state : Party().Bots)
        if (state.Guid.GetCounter() == actorGuid)
        {
            actorInCohort = true;
            break;
        }
    std::string const nativeRevisionHash = GitRevision::GetHash();
    bool const exactIdentity = ValidAdmission(Cohort().Config,
        nativeRevisionHash)
        && Cohort().Config.ProfileCombatRangeCheckpointCaseId == caseId
        && Cohort().Config.ProfileCombatRangeCheckpointSealSha256
            == sealSha256
        && Cohort().Config.ProfileCombatRangeCheckpointSourceCommit
            == sourceCommit
        && Cohort().Config.ProfileCombatRangeCheckpointActorGuid
            == actorGuid
        && Cohort().Config.ProfileCombatRangeCheckpointTargetGuid
            == targetGuid;
    if (!exactIdentity || !actorGuid || !targetGuid || !actorInCohort)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_admission_failed");
        std::string result = BuildProfileCombatRangeCheckpointJson();
        _selectedCohortId = previous;
        return result;
    }
    if (checkpoint.CurrentStage != Stage::Disabled)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_duplicate_arm");
        std::string result = BuildProfileCombatRangeCheckpointJson();
        _selectedCohortId = previous;
        return result;
    }
    uint64 const generation = checkpoint.CheckpointGeneration + 1;
    checkpoint = {};
    checkpoint.CheckpointGeneration = generation;
    checkpoint.CurrentStage = Stage::Armed;
    checkpoint.CaseId = caseId;
    checkpoint.SealSha256 = sealSha256;
    checkpoint.SourceCommit = sourceCommit;
    checkpoint.ActorGuid = actorGuid;
    checkpoint.TargetGuid = targetGuid;
    checkpoint.AttemptId = Cohort().AttemptId;
    checkpoint.WipeGeneration = Cohort().Raid.WipeGeneration;
    checkpoint.RouteGeneration = Party().ValidationRouteGeneration;
    checkpoint.Outcome = "profile_combat_range_checkpoint_armed";
    std::string result = BuildProfileCombatRangeCheckpointJson();
    _selectedCohortId = previous;
    return result;
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
        || checkpoint.CurrentStage == Stage::Disabled
        || checkpoint.Terminal())
        return;

    std::string const nativeRevisionHash = GitRevision::GetHash();
    if (!ValidAdmission(Cohort().Config, nativeRevisionHash))
    {
        checkpoint.Fail("profile_combat_range_checkpoint_admission_invalid");
        return;
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
    size_t castTraceIndex = resolution.Trace.size();
    std::vector<size_t> hazardTraceIndices;
    for (size_t index = 0; index < resolution.Trace.size(); ++index)
    {
        BotActionArbitration::CandidateTrace const& trace =
            resolution.Trace[index];
        if (trace.Key == "world.profile_combat_range")
            rangeTraceIndex = index;
        if (trace.Key == "world.profile_combat")
            castTraceIndex = index;
        if (trace.Key != "world.profile_combat_range"
            && trace.Key != "world.profile_combat"
            && trace.ActionPriority == BotActionArbitration::Priority::Survival
            && (trace.RequiredResources
                & BotActionArbitration::Uses(
                    BotActionArbitration::Resource::Movement))
            && IsProfileCheckpointHazardSource(trace)
            && IsCommitted(trace))
            hazardTraceIndices.push_back(index);
    }

    if (rangeTraceIndex == resolution.Trace.size()
        && hazardTraceIndices.empty() && castTraceIndex == resolution.Trace.size())
        return;

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
    uint32 const wipeGeneration = Cohort().Raid.WipeGeneration;
    uint64 const routeGeneration = Party().ValidationRouteGeneration;
    if (!checkpoint.ScopeBound)
    {
        if (context.Bot->GetMapId() != checkpoint.TargetMapId
            || context.Bot->GetInstanceId() != checkpoint.TargetInstanceId
            || checkpoint.WipeGeneration != wipeGeneration
            || checkpoint.RouteGeneration != routeGeneration)
        {
            checkpoint.Fail("profile_combat_range_checkpoint_scope_mismatch");
            return;
        }
        checkpoint.WipeGeneration = wipeGeneration;
        checkpoint.RouteGeneration = routeGeneration;
        checkpoint.ScopeBound = true;
    }
    else if (checkpoint.WipeGeneration != wipeGeneration
        || checkpoint.RouteGeneration != routeGeneration
        || context.Target->GetMapId() != checkpoint.TargetMapId
        || context.Target->GetInstanceId() != checkpoint.TargetInstanceId
        || context.Bot->GetMapId() != checkpoint.TargetMapId
        || context.Bot->GetInstanceId() != checkpoint.TargetInstanceId)
    {
        checkpoint.Fail("profile_combat_range_checkpoint_scope_mismatch");
        return;
    }

    auto exactPlannerScope = [&](BotWorldMovement::MovementPlannerObservation const& planner)
    {
        return planner.BotGuid == checkpoint.ActorGuid
            && planner.RequestedMapId == checkpoint.TargetMapId
            && SameScope(planner.LaunchReceipt.Scope, checkpoint);
    };

    // A hazard is accepted only when the actual producer's candidate key is
    // carried into the native movement receipt.  A generic Survival+Movement
    // trace without that receipt is deliberately not a hazard join.
    if (checkpoint.HazardCandidateKey.empty())
        for (size_t const index : hazardTraceIndices)
        {
            BotActionArbitration::CandidateTrace const& hazardTrace =
                resolution.Trace[index];
            BotWorldMovement::MovementPlannerObservation const planner =
                BotWorldMovement::MovementPlannerDiagnostics().Latest(
                    checkpoint.ActorGuid);
            uint64 const receiptId = context.State.LastMovementExecution.ReceiptId;
            if (!receiptId || receiptId != planner.LaunchReceipt.Id
                || planner.LaunchReceipt.DiagnosticCandidateKey
                    != hazardTrace.Key
                || planner.MovementOwner
                    != BotMovementArbitration::Owner::Hazard
                || !exactPlannerScope(planner)
                || !planner.LaunchReceipt.IntentFingerprint
                || !HasNativeLaunch(planner)
                || !context.State.LastMovementExecution.NativeSubmitted)
                continue;
            checkpoint.HazardCandidateKey = hazardTrace.Key;
            checkpoint.HazardCandidateSource = hazardTrace.Source;
            checkpoint.HazardCandidateStatus = hazardTrace.Status;
            checkpoint.HazardTraceIndex = index;
            checkpoint.HazardDecisionTimestampMs = context.DecisionNowMs;
            checkpoint.HazardMovementReceiptId = receiptId;
            checkpoint.HazardIntentFingerprint =
                planner.LaunchReceipt.IntentFingerprint;
            checkpoint.HazardNativeSubmitted = true;
            checkpoint.HazardNativeLaunchObserved = HasNativeLaunch(planner);
            break;
        }

    if (!checkpoint.HazardCandidateKey.empty())
    {
        BotWorldMovement::MovementPlannerObservation const planner =
            BotWorldMovement::MovementPlannerDiagnostics().ForReceipt(
                checkpoint.HazardMovementReceiptId);
        BotWorldMovement::NativeMovementProgressObservation const progress =
            BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
                checkpoint.HazardMovementReceiptId);
        checkpoint.HazardProgressSampleCount =
            uint32(progress.Samples.size());
        uint64 const progressAt = LatestDecreasingProgressAt(progress,
            checkpoint.HazardDecisionTimestampMs);
        checkpoint.HazardProgressObserved = progressAt != 0
            && planner.LaunchReceipt.DiagnosticCandidateKey
                == checkpoint.HazardCandidateKey
            && planner.LaunchReceipt.IntentFingerprint
                == checkpoint.HazardIntentFingerprint
            && exactPlannerScope(planner);
        if (checkpoint.HazardProgressObserved)
            checkpoint.HazardProgressObservedAtMs = progressAt;
    }

    if (rangeTraceIndex != resolution.Trace.size())
    {
        BotActionArbitration::CandidateTrace const& rangeTrace =
            resolution.Trace[rangeTraceIndex];
        ++checkpoint.RangeObservationCount;
        bool hazardPreemptedThisResolution = false;
        if (rangeTrace.Status == "resource_conflict"
            && rangeTrace.Reason == "resource_lane_owned")
            for (size_t const hazardIndex : hazardTraceIndices)
            {
                BotActionArbitration::CandidateTrace const& hazardTrace =
                    resolution.Trace[hazardIndex];
                if (hazardIndex < rangeTraceIndex
                    && hazardTrace.Key == checkpoint.HazardCandidateKey)
                {
                    hazardPreemptedThisResolution = true;
                    break;
                }
            }
        if (hazardPreemptedThisResolution)
            checkpoint.HazardPreemptedRange = true;
        bool const rangeCommitted = IsCommitted(rangeTrace)
            && rangeTrace.Source == "db_class_spec_profile"
            && rangeTrace.Reason == "profile_combat_min_range_reconciled";
        bool const hazardProgressPrecedesRange =
            checkpoint.HazardProgressObserved
            && checkpoint.HazardPreemptedRange
            && checkpoint.HazardDecisionTimestampMs
            && checkpoint.HazardProgressObservedAtMs
                > checkpoint.HazardDecisionTimestampMs
            && checkpoint.HazardProgressObservedAtMs
                < context.DecisionNowMs;
        if (rangeCommitted && !checkpoint.RangeReceiptCorrelated
            && hazardProgressPrecedesRange)
        {
            uint64 const receiptId = context.State.LastMovementExecution.ReceiptId;
            BotWorldMovement::MovementPlannerObservation const planner =
                receiptId
                    ? BotWorldMovement::MovementPlannerDiagnostics().ForReceipt(
                        receiptId)
                    : BotWorldMovement::MovementPlannerObservation{};
            bool const exactRangeReceipt = receiptId
                && receiptId == planner.LaunchReceipt.Id
                && planner.LaunchReceipt.DiagnosticCandidateKey
                    == rangeTrace.Key
                && planner.MovementOwner
                    == BotMovementArbitration::Owner::CombatRange
                && exactPlannerScope(planner)
                && planner.LaunchReceipt.DynamicTargetGuid == 0
                && planner.LaunchReceipt.DiagnosticTargetGuid
                    == checkpoint.TargetGuid
                && planner.LaunchReceipt.IntentFingerprint
                && HasNativeLaunch(planner)
                && context.State.LastMovementExecution.NativeSubmitted;
            if (!exactRangeReceipt)
            {
                checkpoint.Fail(
                    "profile_combat_range_checkpoint_range_receipt_identity_failed");
                return;
            }
            checkpoint.CandidateTraceIndex = rangeTraceIndex;
            checkpoint.CandidateKey = rangeTrace.Key;
            checkpoint.CandidateStatus = rangeTrace.Status;
            checkpoint.CandidateReason = rangeTrace.Reason;
            checkpoint.MovementReceiptId = receiptId;
            checkpoint.RangeIntentFingerprint =
                planner.LaunchReceipt.IntentFingerprint;
            checkpoint.MovementCommitted = true;
            checkpoint.MovementNativeSubmitted = true;
            checkpoint.RangeNativeLaunchObserved = HasNativeLaunch(planner);
            checkpoint.RangeReceiptCorrelated = true;
            checkpoint.DecisionTimestampMs = context.DecisionNowMs;
            checkpoint.NativeMotionType =
                planner.LaunchReceipt.MotionMasterGeneratorType;
            checkpoint.NativeSplineId = LatestSplineId(planner);
        }
    }

    if (checkpoint.RangeReceiptCorrelated)
    {
        BotWorldMovement::MovementPlannerObservation const planner =
            BotWorldMovement::MovementPlannerDiagnostics().ForReceipt(
                checkpoint.MovementReceiptId);
        BotWorldMovement::NativeMovementProgressObservation const progress =
            BotWorldMovement::MovementProgressDiagnostics().ForReceipt(
                checkpoint.MovementReceiptId);
        checkpoint.ProgressSampleCount = uint32(progress.Samples.size());
        uint64 const progressAt = LatestDecreasingProgressAt(progress,
            checkpoint.DecisionTimestampMs);
        checkpoint.MovementProgressObserved = progressAt != 0
            && checkpoint.HazardProgressObserved
            && checkpoint.HazardPreemptedRange
            && checkpoint.HazardProgressObservedAtMs
                < checkpoint.DecisionTimestampMs
            && planner.LaunchReceipt.DiagnosticCandidateKey
                == checkpoint.CandidateKey
            && planner.LaunchReceipt.IntentFingerprint
                == checkpoint.RangeIntentFingerprint
            && exactPlannerScope(planner);
        if (checkpoint.MovementProgressObserved)
            checkpoint.RangeProgressObservedAtMs = progressAt;
    }

    if (castTraceIndex != resolution.Trace.size())
    {
        BotActionArbitration::CandidateTrace const& castTrace =
            resolution.Trace[castTraceIndex];
        if (IsCommitted(castTrace)
            && castTrace.Source == "db_class_spec_profile"
            && context.State.LastCombatAttempt.TargetGuid.GetRawValue()
                == checkpoint.TargetGuid)
        {
            uint64 const castAt = context.State.LastCombatAttempt.RecordedAtMs;
            if (!checkpoint.MovementProgressObserved
                || castAt <= checkpoint.RangeProgressObservedAtMs)
                checkpoint.CastBeforeProgressObserved = true;
            else
            {
                checkpoint.CastRetryObserved = true;
                checkpoint.CastRecordedAtMs = castAt;
                checkpoint.CastSpellId = context.State.LastCombatAttempt.SpellId;
                checkpoint.CastTargetGuid = context.State.LastCombatAttempt.TargetGuid
                    .GetRawValue();
                checkpoint.CastTraceIndex = castTraceIndex;
                checkpoint.CastCheckpointGeneration =
                    checkpoint.CheckpointGeneration;
                checkpoint.CastCandidateKey = castTrace.Key;
                checkpoint.CastCandidateSource = castTrace.Source;
                checkpoint.CastCandidateStatus = castTrace.Status;
            }
        }
    }

    BotProfileCombatRangeCheckpoint::TransitionEvidence transition;
    transition.CheckpointScope = {
        checkpoint.CheckpointGeneration,
        checkpoint.ActorGuid,
        checkpoint.TargetGuid,
        checkpoint.AttemptId,
        checkpoint.WipeGeneration,
        checkpoint.RouteGeneration,
        checkpoint.TargetMapId,
        checkpoint.TargetInstanceId,
    };
    transition.HazardCandidate = {
        checkpoint.HazardTraceIndex,
        checkpoint.CheckpointGeneration,
        checkpoint.HazardMovementReceiptId,
        checkpoint.HazardCandidateKey,
        checkpoint.HazardCandidateSource,
        checkpoint.HazardCandidateStatus,
        "",
    };
    transition.HazardReceipt = {
        checkpoint.HazardMovementReceiptId,
        checkpoint.HazardTraceIndex,
        checkpoint.HazardCandidateKey,
        checkpoint.HazardIntentFingerprint,
        transition.CheckpointScope,
        0,
        true,
        checkpoint.HazardNativeSubmitted,
        checkpoint.HazardNativeLaunchObserved,
    };
    transition.HazardDecisionTimestampMs =
        checkpoint.HazardDecisionTimestampMs;
    transition.HazardProgressObservedAtMs =
        checkpoint.HazardProgressObservedAtMs;
    transition.HazardProgressObserved = checkpoint.HazardProgressObserved;
    transition.HazardPreemptedRange = checkpoint.HazardPreemptedRange;
    transition.HazardPreemptionSameResolution =
        checkpoint.HazardPreemptedRange;
    transition.HazardPreemptionBeforeRange =
        checkpoint.HazardProgressObservedAtMs
            < checkpoint.DecisionTimestampMs;
    transition.RangeCandidate = {
        checkpoint.CandidateTraceIndex,
        checkpoint.CheckpointGeneration,
        checkpoint.MovementReceiptId,
        checkpoint.CandidateKey,
        "db_class_spec_profile",
        checkpoint.CandidateStatus,
        checkpoint.CandidateReason,
    };
    transition.RangeReceipt = {
        checkpoint.MovementReceiptId,
        checkpoint.CandidateTraceIndex,
        checkpoint.CandidateKey,
        checkpoint.RangeIntentFingerprint,
        transition.CheckpointScope,
        checkpoint.TargetGuid,
        true,
        checkpoint.MovementNativeSubmitted,
        checkpoint.RangeNativeLaunchObserved,
    };
    transition.RangeDecisionTimestampMs = checkpoint.DecisionTimestampMs;
    transition.RangeProgressObservedAtMs =
        checkpoint.RangeProgressObservedAtMs;
    transition.RangeProgressObserved = checkpoint.MovementProgressObserved;
    transition.CastCandidate = {
        checkpoint.CastTraceIndex,
        checkpoint.CastCheckpointGeneration,
        0,
        checkpoint.CastCandidateKey,
        checkpoint.CastCandidateSource,
        checkpoint.CastCandidateStatus,
        "",
    };
    transition.CastScope = transition.CheckpointScope;
    transition.CastSpellId = checkpoint.CastSpellId;
    transition.CastTargetGuid = checkpoint.CastTargetGuid;
    transition.CastRetryObserved = checkpoint.CastRetryObserved;
    transition.CastRecordedAtMs = checkpoint.CastRecordedAtMs;
    transition.CastBeforeProgressObserved =
        checkpoint.CastBeforeProgressObserved;

    if (BotProfileCombatRangeCheckpoint::IsCompletedTransition(transition))
    {
        checkpoint.CurrentStage = Stage::Completed;
        checkpoint.Outcome = "profile_combat_range_checkpoint_boundary_observed";
    }
    else if (checkpoint.MovementProgressObserved)
    {
        checkpoint.CurrentStage = Stage::ProgressObserved;
        checkpoint.Outcome = "profile_combat_range_checkpoint_progress_observed";
    }
    else if (checkpoint.RangeReceiptCorrelated)
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
         << ",\"checkpoint_generation\":"
         << checkpoint.CheckpointGeneration
         << ",\"actor_guid\":" << checkpoint.ActorGuid
         << ",\"target_guid\":" << checkpoint.TargetGuid
         << ",\"attempt_id\":" << checkpoint.AttemptId
         << ",\"wipe_generation\":" << checkpoint.WipeGeneration
         << ",\"route_generation\":" << checkpoint.RouteGeneration
         << ",\"scope_bound\":"
         << (checkpoint.ScopeBound ? "true" : "false")
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
         << ",\"range_diagnostic_target_guid\":"
         << planner.LaunchReceipt.DiagnosticTargetGuid
         << ",\"range_intent_fingerprint\":\"" << std::hex
         << checkpoint.RangeIntentFingerprint << std::dec << "\""
         << ",\"range_receipt_correlated\":"
         << (checkpoint.RangeReceiptCorrelated ? "true" : "false")
         << ",\"progress_sample_count\":"
         << checkpoint.ProgressSampleCount
         << ",\"movement_progress_observed\":"
         << (checkpoint.MovementProgressObserved ? "true" : "false")
         << ",\"range_progress_observed_at_ms\":"
         << checkpoint.RangeProgressObservedAtMs
         << ",\"hazard_candidate_key\":\""
         << EscapeJson(checkpoint.HazardCandidateKey) << "\""
         << ",\"hazard_candidate_source\":\""
         << EscapeJson(checkpoint.HazardCandidateSource) << "\""
         << ",\"hazard_candidate_status\":\""
         << EscapeJson(checkpoint.HazardCandidateStatus) << "\""
         << ",\"hazard_trace_index\":" << checkpoint.HazardTraceIndex
         << ",\"hazard_decision_timestamp_ms\":"
         << checkpoint.HazardDecisionTimestampMs
         << ",\"hazard_movement_receipt_id\":"
         << checkpoint.HazardMovementReceiptId
         << ",\"hazard_intent_fingerprint\":\"" << std::hex
         << checkpoint.HazardIntentFingerprint << std::dec << "\""
         << ",\"hazard_progress_sample_count\":"
         << checkpoint.HazardProgressSampleCount
         << ",\"hazard_native_submitted\":"
         << (checkpoint.HazardNativeSubmitted ? "true" : "false")
         << ",\"hazard_progress_observed\":"
         << (checkpoint.HazardProgressObserved ? "true" : "false")
         << ",\"hazard_progress_observed_at_ms\":"
         << checkpoint.HazardProgressObservedAtMs
         << ",\"hazard_preempted_range\":"
         << (checkpoint.HazardPreemptedRange ? "true" : "false")
         << ",\"cast_spell_id\":" << checkpoint.CastSpellId
         << ",\"cast_target_guid\":" << checkpoint.CastTargetGuid
         << ",\"cast_retry_observed\":"
         << (checkpoint.CastRetryObserved ? "true" : "false")
         << ",\"cast_recorded_at_ms\":" << checkpoint.CastRecordedAtMs
         << ",\"cast_before_progress_observed\":"
         << (checkpoint.CastBeforeProgressObserved ? "true" : "false")
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

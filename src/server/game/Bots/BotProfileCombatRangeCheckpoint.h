#ifndef TRINITY_BOT_PROFILE_COMBAT_RANGE_CHECKPOINT_H
#define TRINITY_BOT_PROFILE_COMBAT_RANGE_CHECKPOINT_H

#include "Define.h"

#include <cstdint>
#include <string>
#include <utility>

namespace BotProfileCombatRangeCheckpoint
{
constexpr char FixtureId[] = "generic_profile_min_range_production_boundary_v1";
constexpr char Authority[] =
    "default_off_generic_profile_combat_range_observation";
constexpr uint32 MaximumAwaitTicks = 300;

struct Scope
{
    uint64 CheckpointGeneration = 0;
    uint32 ActorGuid = 0;
    uint64 TargetGuid = 0;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    uint32 MapId = 0;
    uint32 InstanceId = 0;
};

struct Candidate
{
    uint64 TraceIndex = 0;
    uint64 CheckpointGeneration = 0;
    uint64 NativeReceiptId = 0;
    std::string Key;
    std::string Source;
    std::string Status;
    std::string Reason;
};

struct NativeReceipt
{
    uint64 Id = 0;
    uint64 CandidateTraceIndex = 0;
    std::string CandidateKey;
    uint64 IntentFingerprint = 0;
    Scope ReceiptScope;
    uint64 DiagnosticTargetGuid = 0;
    bool DynamicTargetAbsent = false;
    bool NativeSubmitted = false;
    bool LaunchObserved = false;
};

struct TransitionEvidence
{
    Scope CheckpointScope;
    Candidate HazardCandidate;
    NativeReceipt HazardReceipt;
    uint64 HazardDecisionTimestampMs = 0;
    uint64 HazardProgressObservedAtMs = 0;
    bool HazardProgressObserved = false;
    bool HazardPreemptedRange = false;
    bool HazardPreemptionSameResolution = false;
    bool HazardPreemptionBeforeRange = false;
    Candidate RangeCandidate;
    NativeReceipt RangeReceipt;
    uint64 RangeDecisionTimestampMs = 0;
    uint64 RangeProgressObservedAtMs = 0;
    bool RangeProgressObserved = false;
    Candidate CastCandidate;
    Scope CastScope;
    uint32 CastSpellId = 0;
    uint64 CastTargetGuid = 0;
    bool CastRetryObserved = false;
    uint64 CastRecordedAtMs = 0;
    bool CastBeforeProgressObserved = false;
};

inline bool IsProfileCheckpointHazardSource(std::string const& source)
{
    return source == "adaptive_raid_trash"
        || source == "shared_hazard_movement";
}

inline bool IsValidScope(Scope const& scope)
{
    return scope.CheckpointGeneration > 0
        && scope.ActorGuid > 0
        && scope.TargetGuid > 0
        && scope.AttemptId > 0
        && scope.RouteGeneration > 0
        && scope.MapId > 0
        && scope.InstanceId > 0;
}

inline bool SameScope(Scope const& left, Scope const& right)
{
    return left.CheckpointGeneration == right.CheckpointGeneration
        && left.ActorGuid == right.ActorGuid
        && left.TargetGuid == right.TargetGuid
        && left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration
        && left.MapId == right.MapId
        && left.InstanceId == right.InstanceId;
}

inline bool ExactCandidateReceipt(
    Candidate const& candidate, NativeReceipt const& receipt,
    Scope const& checkpointScope)
{
    return candidate.TraceIndex == receipt.CandidateTraceIndex
        && candidate.CheckpointGeneration
            == checkpointScope.CheckpointGeneration
        && candidate.NativeReceiptId > 0
        && candidate.NativeReceiptId == receipt.Id
        && candidate.Key == receipt.CandidateKey
        && receipt.Id > 0
        && receipt.IntentFingerprint > 0
        && receipt.NativeSubmitted
        && receipt.LaunchObserved
        && SameScope(receipt.ReceiptScope, checkpointScope);
}

inline bool IsCompletedTransition(TransitionEvidence const& evidence)
{
    Scope const& scope = evidence.CheckpointScope;
    if (!IsValidScope(scope)
        || !IsValidScope(evidence.HazardReceipt.ReceiptScope)
        || !IsValidScope(evidence.RangeReceipt.ReceiptScope)
        || !IsValidScope(evidence.CastScope))
        return false;
    if (evidence.HazardCandidate.Key.empty()
        || !IsProfileCheckpointHazardSource(
            evidence.HazardCandidate.Source)
        || evidence.HazardCandidate.Status != "attempted"
        || !ExactCandidateReceipt(
            evidence.HazardCandidate, evidence.HazardReceipt, scope)
        || !evidence.HazardProgressObserved
        || evidence.HazardDecisionTimestampMs == 0
        || evidence.HazardProgressObservedAtMs
            <= evidence.HazardDecisionTimestampMs
        || !evidence.HazardPreemptedRange
        || !evidence.HazardPreemptionSameResolution
        || !evidence.HazardPreemptionBeforeRange)
        return false;
    if (evidence.RangeCandidate.Key != "world.profile_combat_range"
        || evidence.RangeCandidate.Source != "db_class_spec_profile"
        || evidence.RangeCandidate.Status != "attempted"
        || evidence.RangeCandidate.Reason
            != "profile_combat_min_range_reconciled"
        || !ExactCandidateReceipt(
            evidence.RangeCandidate, evidence.RangeReceipt, scope)
        || evidence.RangeReceipt.DynamicTargetAbsent
            != true
        || evidence.RangeReceipt.DiagnosticTargetGuid != scope.TargetGuid
        || evidence.RangeDecisionTimestampMs
            <= evidence.HazardProgressObservedAtMs
        || !evidence.RangeProgressObserved
        || evidence.RangeProgressObservedAtMs
            <= evidence.RangeDecisionTimestampMs)
        return false;
    if (evidence.CastCandidate.Key != "world.profile_combat"
        || evidence.CastCandidate.Source != "db_class_spec_profile"
        || evidence.CastCandidate.Status != "attempted"
        || evidence.CastCandidate.CheckpointGeneration
            != scope.CheckpointGeneration
        || !SameScope(evidence.CastScope, scope)
        || evidence.CastSpellId == 0
        || evidence.CastTargetGuid != scope.TargetGuid
        || !evidence.CastRetryObserved
        || evidence.CastBeforeProgressObserved
        || evidence.CastRecordedAtMs
            <= evidence.RangeProgressObservedAtMs)
        return false;
    return true;
}

enum class Stage : uint8
{
    Disabled,
    Armed,
    RangeObserved,
    ProgressObserved,
    Completed,
    Failed
};

inline char const* StageName(Stage stage)
{
    switch (stage)
    {
        case Stage::Disabled: return "disabled";
        case Stage::Armed: return "armed";
        case Stage::RangeObserved: return "range_observed";
        case Stage::ProgressObserved: return "progress_observed";
        case Stage::Completed: return "completed";
        case Stage::Failed: return "failed";
    }
    return "unknown";
}

struct State
{
    Stage CurrentStage = Stage::Disabled;
    uint64 CheckpointGeneration = 0;
    std::string CaseId;
    std::string SealSha256;
    std::string SourceCommit;
    uint32 ActorGuid = 0;
    uint64 TargetGuid = 0;
    uint64 AttemptId = 0;
    uint32 WipeGeneration = 0;
    uint64 RouteGeneration = 0;
    bool ScopeBound = false;
    uint32 TargetMapId = 0;
    uint32 TargetInstanceId = 0;
    uint64 DecisionTimestampMs = 0;
    uint64 CandidateTraceIndex = 0;
    std::string CandidateKey;
    std::string CandidateStatus;
    std::string CandidateReason;
    uint64 MovementReceiptId = 0;
    uint32 NativeMotionType = 0;
    uint32 NativeSplineId = 0;
    bool MovementCommitted = false;
    bool MovementNativeSubmitted = false;
    bool RangeNativeLaunchObserved = false;
    uint32 ProgressSampleCount = 0;
    bool MovementProgressObserved = false;
    uint64 RangeIntentFingerprint = 0;
    uint64 RangeProgressObservedAtMs = 0;
    bool RangeReceiptCorrelated = false;
    std::string HazardCandidateKey;
    std::string HazardCandidateSource;
    std::string HazardCandidateStatus;
    uint64 HazardTraceIndex = 0;
    uint64 HazardDecisionTimestampMs = 0;
    uint64 HazardMovementReceiptId = 0;
    uint64 HazardIntentFingerprint = 0;
    uint32 HazardProgressSampleCount = 0;
    bool HazardNativeSubmitted = false;
    bool HazardNativeLaunchObserved = false;
    bool HazardProgressObserved = false;
    uint64 HazardProgressObservedAtMs = 0;
    bool HazardPreemptedRange = false;
    uint32 CastSpellId = 0;
    uint64 CastTargetGuid = 0;
    bool CastRetryObserved = false;
    uint64 CastRecordedAtMs = 0;
    bool CastBeforeProgressObserved = false;
    uint64 CastTraceIndex = 0;
    uint64 CastCheckpointGeneration = 0;
    std::string CastCandidateKey;
    std::string CastCandidateSource;
    std::string CastCandidateStatus;
    uint32 RangeObservationCount = 0;
    uint32 AwaitTicks = 0;
    std::string Outcome = "disabled";
    std::string FailureReason;

    bool Terminal() const
    {
        return CurrentStage == Stage::Completed
            || CurrentStage == Stage::Failed;
    }

    void Fail(std::string reason)
    {
        if (!Terminal())
        {
            CurrentStage = Stage::Failed;
            FailureReason = std::move(reason);
            Outcome = FailureReason;
        }
    }
};
}

#endif

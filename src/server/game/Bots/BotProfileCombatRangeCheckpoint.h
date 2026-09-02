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
    bool HazardProgressObserved = false;
    uint64 HazardProgressObservedAtMs = 0;
    bool HazardPreemptedRange = false;
    uint32 CastSpellId = 0;
    uint64 CastTargetGuid = 0;
    bool CastRetryObserved = false;
    uint64 CastRecordedAtMs = 0;
    bool CastBeforeProgressObserved = false;
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

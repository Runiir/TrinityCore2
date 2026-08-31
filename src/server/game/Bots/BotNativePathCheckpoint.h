#ifndef TRINITY_BOT_NATIVE_PATH_CHECKPOINT_H
#define TRINITY_BOT_NATIVE_PATH_CHECKPOINT_H

#include "Define.h"

#include <array>
#include <string>
#include <string_view>

namespace BotNativePathCheckpoint
{
constexpr char FixtureId[] = "map669_native_path_production_boundary_v1";
constexpr char Authority[] =
    "sealed_compiled_map669_native_path_observation_only";
constexpr uint32 MapId = 669;
constexpr uint32 MaximumAwaitTicks = 300;

enum class ExpectedPrimaryDisposition : uint8
{
    CompleteTerminal,
    IncompleteFallbackEligible,
    Forbidden
};

enum class Stage : uint8
{
    Disabled,
    Armed,
    Staging,
    HazardSubmitted,
    Completed,
    Failed
};

struct Case
{
    std::string_view Id;
    std::string_view EvidenceRun;
    std::string_view RawSha256;
    uint64 SourceReceiptId = 0;
    uint32 SourceActorGuid = 0;
    uint32 ReplayActorGuid = 0;
    float StartX = 0.0f;
    float StartY = 0.0f;
    float StartZ = 0.0f;
    float RequestX = 0.0f;
    float RequestY = 0.0f;
    float RequestZ = 0.0f;
    bool RequireCompletePath = false;
    ExpectedPrimaryDisposition ExpectedDisposition =
        ExpectedPrimaryDisposition::Forbidden;
};

// The compiled tuples are the sole coordinate authority. Commands select an
// admitted case id; they can never supply a destination. Source and replay
// actors are separate fields even when their stable database GUIDs match.
constexpr std::array<Case, 5> Cases{{
    { "a842_receipt519_complete_wrong_floor", "a842df32e5",
      "904026edfa6a4aa6efe5263f6a91c251cf11825a638dc389a1cfded9f5becc02",
      519, 30006, 30006, -340.854675f, -30.1652412f, 211.313324f,
      -353.645538f, -51.6406975f, 211.313324f, false,
      ExpectedPrimaryDisposition::CompleteTerminal },
    { "a842_receipt551_complete_wrong_floor", "a842df32e5",
      "904026edfa6a4aa6efe5263f6a91c251cf11825a638dc389a1cfded9f5becc02",
      551, 30006, 30006, -351.34491f, -47.7779884f, 212.235764f,
      -312.400757f, -68.8223724f, 211.313324f, false,
      ExpectedPrimaryDisposition::CompleteTerminal },
    { "a506_receipt636_incomplete_same_floor", "a5062ba7",
      "2aff2219c0bc37746cc47532850cea6a7c91d5bcf82c6e279997287ffb5894cf",
      636, 30007, 30007, -302.471405f, -31.8600292f, 210.098007f,
      -302.921356f, -26.0047035f, 210.521393f, false,
      ExpectedPrimaryDisposition::IncompleteFallbackEligible },
    { "a506_receipt561_cross_floor", "a5062ba7",
      "2aff2219c0bc37746cc47532850cea6a7c91d5bcf82c6e279997287ffb5894cf",
      561, 30002, 30002, -311.394684f, -48.4652405f, 227.12999f,
      -300.079803f, -27.1645069f, 210.948013f, false,
      ExpectedPrimaryDisposition::Forbidden },
    { "a506_receipt556_missing_mmap", "a5062ba7",
      "2aff2219c0bc37746cc47532850cea6a7c91d5bcf82c6e279997287ffb5894cf",
      556, 30002, 30002, -304.442841f, -35.4182587f, 214.701523f,
      -300.079803f, -27.1645069f, 210.948013f, false,
      ExpectedPrimaryDisposition::Forbidden },
}};

constexpr Case const* FindCase(std::string_view id)
{
    for (Case const& value : Cases)
        if (value.Id == id)
            return &value;
    return nullptr;
}

inline char const* StageName(Stage stage)
{
    switch (stage)
    {
        case Stage::Disabled: return "disabled";
        case Stage::Armed: return "armed";
        case Stage::Staging: return "staging";
        case Stage::HazardSubmitted: return "hazard_submitted";
        case Stage::Completed: return "completed";
        case Stage::Failed: return "failed";
    }
    return "unknown";
}

inline char const* ExpectedDispositionName(ExpectedPrimaryDisposition value)
{
    switch (value)
    {
        case ExpectedPrimaryDisposition::CompleteTerminal:
            return "complete_terminal";
        case ExpectedPrimaryDisposition::IncompleteFallbackEligible:
            return "incomplete_fallback_eligible";
        case ExpectedPrimaryDisposition::Forbidden: return "forbidden";
    }
    return "unknown";
}

struct State
{
    Stage CurrentStage = Stage::Disabled;
    std::string CaseId;
    uint32 ActorGuid = 0;
    uint64 AttemptId = 0;
    uint64 StageReceiptId = 0;
    uint64 HazardReceiptId = 0;
    uint32 AwaitTicks = 0;
    uint32 StageSubmitCount = 0;
    uint32 HazardSubmitCount = 0;
    std::string Outcome = "disabled";

    bool Terminal() const
    {
        return CurrentStage == Stage::Completed
            || CurrentStage == Stage::Failed;
    }

    bool Arm(std::string_view caseId, uint32 actorGuid, uint64 attemptId)
    {
        Case const* selected = FindCase(caseId);
        if (!selected || !actorGuid || actorGuid != selected->ReplayActorGuid
            || !attemptId || CurrentStage != Stage::Disabled)
        {
            CurrentStage = Stage::Failed;
            Outcome = "native_path_checkpoint_arm_identity_invalid";
            return false;
        }
        *this = {};
        CurrentStage = Stage::Armed;
        CaseId = caseId;
        ActorGuid = actorGuid;
        AttemptId = attemptId;
        Outcome = "native_path_checkpoint_armed";
        return true;
    }

    void Fail(std::string reason)
    {
        if (!Terminal())
        {
            CurrentStage = Stage::Failed;
            Outcome = std::move(reason);
        }
    }
};
}

#endif

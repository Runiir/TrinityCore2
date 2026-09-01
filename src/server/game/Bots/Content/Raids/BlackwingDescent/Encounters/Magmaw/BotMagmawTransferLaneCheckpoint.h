#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_CHECKPOINT_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_CHECKPOINT_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneAuthority.h"

#include <array>
#include <optional>
#include <string>
#include <string_view>

namespace BotWorldMovement
{
struct MovementPlannerObservation;
struct NativeMovementProgressSample;
}

namespace BotEncounter::MagmawTransferLaneCheckpoint
{
constexpr char FixtureId[] =
    "map669_magmaw_transfer_lane_authority_off_v1";
constexpr char Authority[] =
    "sealed_map669_transfer_lane_fixture_authority_off";
constexpr uint32 MapId = 669;
constexpr uint32 ActorGuid = 30007;
constexpr uint64 EpisodeGeneration = 17;
constexpr uint64 TaskGeneration = 31;
constexpr uint64 LegacyTransitionGeneration = 43;
constexpr uint32 MaximumAwaitTicks = 300;
constexpr uint32 MaximumProgressPublicationTicks = 10;
constexpr uint32 RequiredProgressSamples = 2;
constexpr float StartTolerance2d = 0.75f;
constexpr float StartToleranceZ = 1.0f;

struct Case
{
    std::string_view Id;
    float StartX = 0.0f;
    float StartY = 0.0f;
    float StartZ = 0.0f;
    float DestinationX = 0.0f;
    float DestinationY = 0.0f;
    float DestinationZ = 0.0f;
};

// The command names only this compiled row. It cannot supply coordinates.
// The source is the frozen BWD entrance placement. The complete one-poly
// Detour proof is retained in
// experiments/configs/map669_magmaw_transfer_lane_entrance_probe_v1.json.
// The short step has no boss or gameplay-success meaning.
constexpr std::array<Case, 1> Cases{{
    { "entrance_polygon_short_lane_v1",
      -345.872009f, -224.343994f, 193.126999f,
      -345.872009f, -218.343994f, 193.126999f },
}};

constexpr Case const* FindCase(std::string_view id)
{
    for (Case const& row : Cases)
        if (row.Id == id)
            return &row;
    return nullptr;
}

enum class Stage : uint8
{
    Disabled,
    Armed,
    Queued,
    NativeSubmitted,
    Progressing,
    Completed,
    Failed
};

enum class ProgressPublicationDecision : uint8
{
    Await,
    Ready,
    TimedOut
};

char const* StageName(Stage stage);

struct AdmissionInput
{
    bool ValidationRouteEnabled = false;
    bool CheckpointEnabled = false;
    bool TaskAuthorityEnabled = false;
    std::string_view ConfiguredFixtureId;
    std::string_view ConfiguredCaseId;
    std::string_view ConfiguredSealSha256;
    std::string_view ConfiguredSourceCommit;
    std::string_view RequestedCaseId;
    std::string_view RequestedSealSha256;
    std::string_view RequestedSourceCommit;
    std::string_view BinaryRevision;
};

bool AdmissionMatches(AdmissionInput const& input);

struct PlannerReceiptSnapshot
{
    bool Available = false;
    uint64 ReceiptId = 0;
    uint64 BotGuid = 0;
    uint32 Map = 0;
    BotMovementArbitration::Scope Scope;
    std::string CandidateKey;
    std::string IntentReason;
    uint32 SplineId = 0;
    uint32 MotionMasterSlot = 0;
    uint32 MotionMasterGeneratorType = 0;
    bool PlannerAccepted = false;
    bool MotionMasterSubmitted = false;
    bool PointGeneratorInitialized = false;
    bool SplineLaunched = false;
};

struct State
{
    Stage CurrentStage = Stage::Disabled;
    std::string CaseId;
    uint32 Actor = 0;
    uint64 AttemptId = 0;
    uint32 InstanceId = 0;
    uint32 AwaitTicks = 0;
    uint32 QueueCount = 0;
    uint32 CandidateAttemptCount = 0;
    uint32 NativeSubmissionCount = 0;
    uint32 ConsumedProgressSamples = 0;
    uint32 DecreasingProgressSamples = 0;
    uint32 WrongFloorSamples = 0;
    uint32 ProgressPublicationAwaitTicks = 0;
    uint64 QueuedAtMs = 0;
    uint64 LastSampleObservedAtMs = 0;
    uint64 LastProgressObservedAtMs = 0;
    float StartX = 0.0f;
    float StartY = 0.0f;
    float StartZ = 0.0f;
    float LastActorX = 0.0f;
    float LastActorY = 0.0f;
    float LastActorZ = 0.0f;
    float LastFloorZ = 0.0f;
    float LastProgressDistance = 0.0f;
    bool LastProgressDistanceAvailable = false;
    bool NativeOutcomeConsumed = false;
    bool TerminalPublished = false;
    std::string ScopeKey;
    std::string CandidateKey;
    std::string Outcome = "disabled";
    MagmawTransferLaneTask Task;
    std::optional<MagmawTransferLaneExecutionBinding> Binding;
    std::optional<MagmawTransferLaneNativeOutcome> NativeOutcome;
    PlannerReceiptSnapshot PlannerReceipt;

    bool Terminal() const
    {
        return CurrentStage == Stage::Completed
            || CurrentStage == Stage::Failed;
    }

    bool Arm(std::string_view caseId, uint32 actorGuid, uint64 attemptId);
    void Fail(std::string reason);
    void Complete();
};

MagmawTransferLaneTask BuildTask(Case const& selected,
    Scope const& lifecycle, ObjectGuid actor, uint64 observedAtMs,
    float initialDistance);
BotNativeAction::Candidate BuildLegacyCandidate(
    MagmawTransferLaneTask const& task);
bool ExactAuthorityOffSelection(
    MagmawTransferLaneAuthoritySelection const& selection,
    BotNativeAction::Candidate const& legacy,
    MagmawTransferLaneTask const& task);
bool OwnsQueuedKernelCandidate(State const& state,
    std::string_view candidateKey, uint32 actorGuid);
bool CaptureExactPlannerReceipt(PlannerReceiptSnapshot& snapshot,
    BotWorldMovement::MovementPlannerObservation const& planner,
    MagmawTransferLaneExecutionBinding const& binding,
    MagmawTransferLaneTask const& task);
bool ConsumeProgressSample(State& state,
    BotWorldMovement::NativeMovementProgressSample const& sample);
ProgressPublicationDecision ObserveProgressPublication(
    State& state, bool available);
}

#endif

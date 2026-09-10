#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PLANNER_DIAGNOSTICS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PLANNER_DIAGNOSTICS_H

#include "Bots/BotMovementArbiter.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"
#include "Movement/NativePathLaunchObserver.h"

#include <cstddef>
#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <utility>
#include <vector>

namespace BotWorldMovement
{
constexpr std::uint32_t NativePathLaunchReceiptVersion = 1;

using NativePathControl = G3D::Vector3;

enum class PrimaryDisposition : std::uint8_t
{
    CompleteTerminal,
    IncompleteFallbackEligible,
    Forbidden
};

char const* PrimaryDispositionName(PrimaryDisposition disposition);

inline PrimaryDisposition ClassifyPrimaryDisposition(
    NativePathProofObservation const& proof, bool fallbackEligible,
    bool forbidden)
{
    if (forbidden || !proof.Available || !proof.Calculated)
        return PrimaryDisposition::Forbidden;
    if (proof.Complete)
        return PrimaryDisposition::CompleteTerminal;
    return fallbackEligible
        ? PrimaryDisposition::IncompleteFallbackEligible
        : PrimaryDisposition::Forbidden;
}

struct NativePathControlSequence
{
    static constexpr std::size_t MaxRetainedControls = 32;
    bool Available = false;
    std::string CoordinateSpace = "unavailable";
    std::size_t ControlCount = 0;
    std::uint64_t Fingerprint = 0;
    // Ordered prefix copied from the actual producer, never reconstructed.
    std::vector<NativePathControl> OrderedControls;
};

struct NativePathPosition
{
    bool Available = false;
    std::string CoordinateSpace = "world";
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
};

struct NativeSplineLaunchObservation
{
    bool SecondPathAttempted = false;
    bool SecondPathCalculated = false;
    std::uint32_t SecondPathType = 0;
    NativePathControlSequence SecondPathControls;
    bool DirectTwoPointSelected = false;
    bool DirectTwoPointFallback = false;
    bool LaunchAttempted = false;
    bool LaunchSucceeded = false;
    bool SplineFinalizedAfterLaunch = true;
    bool SplineInitialized = false;
    std::uint32_t SplineId = 0;
    float SplineFinalX = 0.0f;
    float SplineFinalY = 0.0f;
    float SplineFinalZ = 0.0f;
    NativePathControlSequence LaunchedControls;
    NativePathPosition ActorAfterLaunch;
};

struct NativePathLaunchReceipt
{
    static constexpr std::size_t MaxLaunchAttempts = 4;

    std::uint32_t Version = NativePathLaunchReceiptVersion;
    std::uint64_t Id = 0;
    std::uint64_t IntentFingerprint = 0;
    std::string DiagnosticCandidateKey;
    BotMovementArbitration::Scope Scope;
    std::uint64_t DynamicTargetGuid = 0;
    // Evidence-only target identity for static profile movement.  This is
    // deliberately separate from DynamicTargetGuid: static movement must
    // keep its point-planner/native target behavior and fingerprint intact.
    std::uint64_t DiagnosticTargetGuid = 0;
    bool ProgressCaptureEnabled = false;
    PrimaryDisposition PrimaryPathDisposition =
        PrimaryDisposition::Forbidden;
    NativePathProofObservation PrimaryNativeProof;
    bool LocalFallbackAttempted = false;
    std::string FinalTraversalMode = "unavailable";
    NativePathPosition ActorBeforePlanning;
    NativePathPosition ActorBeforeNativeSubmission;
    NativePathControlSequence PlannerControls;
    bool PlannerSelectedEndpointAvailable = false;
    float PlannerSelectedX = 0.0f;
    float PlannerSelectedY = 0.0f;
    float PlannerSelectedZ = 0.0f;
    bool ExecutorDestinationAvailable = false;
    float ExecutorSelectedX = 0.0f;
    float ExecutorSelectedY = 0.0f;
    float ExecutorSelectedZ = 0.0f;
    bool PointGeneratePath = false;
    bool MotionMasterSubmissionObserved = false;
    std::uint32_t MotionMasterSlot = 0;
    std::uint32_t MotionMasterGeneratorType = 0;
    bool PointGeneratorInitialized = false;
    std::vector<NativeSplineLaunchObservation> Launches;
    std::size_t LaunchAttemptOverflowCount = 0;
};

std::uint64_t NativePathControlsFingerprint(
    Movement::NativePathLaunchControls const& controls);
NativePathControlSequence ObserveNativePathControls(
    Movement::NativePathLaunchControls const& controls,
    char const* coordinateSpace);

// This is deliberately outside WorldBotState.  Planner admission is a
// process-local diagnostic concern, while the authoritative movement state
// remains owned by the bot runtime.
struct MovementPlannerObservation
{
    bool Available = false;
    std::uint64_t BotGuid = 0;
    std::uint32_t RequestedMapId = 0;
    float RequestedX = 0.0f;
    float RequestedY = 0.0f;
    float RequestedZ = 0.0f;
    BotMovementArbitration::Owner MovementOwner =
        BotMovementArbitration::Owner::None;
    std::string IntentReason;
    bool TargetFloorSampled = false;
    float TargetFloorZ = 0.0f;
    bool TargetFloorValid = false;
    bool ZDeltaAvailable = false;
    float AbsoluteZDelta = 0.0f;
    float ZDeltaThreshold = 4.0f;
    bool AllowProgressiveSegments = false;
    bool RequireCompletePath = false;
    bool AllowNativeLongPath = false;
    bool DynamicTarget = false;
    std::optional<HazardEscapeBasis> HazardEscape;
    HazardEscapeProgressObservation HazardEscapeProgress;
    PrimaryDisposition PrimaryPathDisposition =
        PrimaryDisposition::Forbidden;
    NativePathProofObservation PrimaryNativeProof;
    bool LocalFallbackAttempted = false;
    std::string FinalTraversalMode = "unavailable";
    NativePathProofObservation NativeProof;
    std::string PlannerGate = "unavailable";
    std::string PlannerResult = "unavailable";
    std::string PlannerReason;
    std::string Gate = "unavailable";
    std::string Result = "unavailable";
    std::string Reason;
    NativePathLaunchReceipt LaunchReceipt;
};

class MovementPlannerDiagnosticSidecar final
    : public Movement::NativePathLaunchObserver
{
public:
    static constexpr std::size_t MaxTraceHistory = 128;

    std::uint64_t BeginReceipt(std::uint64_t botGuid,
        std::uint32_t requestedMapId, Intent const& intent,
        BotMovementArbitration::Scope const& scope,
        std::uint64_t dynamicTargetGuid, float actorX, float actorY,
        float actorZ, bool progressCaptureEnabled = false,
        std::uint64_t diagnosticTargetGuid = 0);
    void Record(MovementPlannerObservation observation);
    Movement::NativePathLaunchContext LaunchContext(
        std::uint64_t receiptId, std::uint64_t botGuid,
        std::uint32_t mapId);
    void FinalizeExecutor(std::uint64_t botGuid,
        std::uint32_t requestedMapId, Intent const& intent, char const* gate,
        char const* result, char const* reason,
        std::uint64_t receiptId = 0);
    void RecordPlannerOutcome(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t requestedMapId,
        Intent const& intent,
        bool targetFloorSampled, float targetFloorZ, bool targetFloorValid,
        char const* gate, bool accepted, char const* reason,
        PathPlan const& plan, NativePathProofObservation const* nativeProof,
        NativePathControlSequence const* plannedControls,
        PrimaryDisposition primaryDisposition = PrimaryDisposition::Forbidden,
        NativePathProofObservation const* primaryNativeProof = nullptr,
        bool localFallbackAttempted = false);
    void RecordNativeSubmission(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId, float actorX,
        float actorY, float actorZ, float selectedX, float selectedY,
        float selectedZ, bool generatePath);
    void RecordMotionMasterSubmission(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId, std::uint32_t slot,
        std::uint32_t generatorType);
    void RecordPointGeneratorInitialize(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId);
    void RecordDiagnosticTarget(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId,
        std::uint64_t targetGuid);
    void RecordSplinePreparation(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId,
        bool secondPathAttempted, bool secondPathCalculated,
        std::uint32_t secondPathType,
        Movement::NativePathLaunchControls const& secondPathControls,
        bool directTwoPointSelected, bool directTwoPointFallback);
    void RecordSplineLaunch(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId,
        Movement::NativePathLaunchControls const& launchedControls,
        char const* coordinateSpace, bool succeeded, bool finalized,
        bool splineInitialized, std::uint32_t splineId, float splineFinalX,
        float splineFinalY, float splineFinalZ, float actorX, float actorY,
        float actorZ);
    void ArmProgress(std::uint64_t receiptId, std::uint64_t botGuid,
        std::uint32_t mapId, bool splineInitialized,
        std::uint32_t splineId, float splineFinalX, float splineFinalY,
        float splineFinalZ, std::uint64_t observedAtMs);
    void OnMotionMasterSubmission(
        Movement::NativePathLaunchContext const& context, std::uint32_t slot,
        std::uint32_t generatorType) override;
    void OnPointGeneratorInitialize(
        Movement::NativePathLaunchContext const& context) override;
    void OnSplinePreparation(
        Movement::NativePathLaunchContext const& context,
        bool secondPathAttempted, bool secondPathCalculated,
        std::uint32_t secondPathType,
        Movement::NativePathLaunchControls const& secondPathControls,
        bool directTwoPointSelected, bool directTwoPointFallback) override;
    void OnSplineLaunch(Movement::NativePathLaunchContext const& context,
        Movement::NativePathLaunchControls const& launchedControls,
        Movement::NativePathLaunchCoordinateSpace coordinateSpace,
        bool succeeded, bool finalized, bool splineInitialized,
        std::uint32_t splineId, float splineFinalX, float splineFinalY,
        float splineFinalZ, float actorX, float actorY, float actorZ) override;
    void AssociateTrace(std::uint64_t botGuid, std::uint64_t traceSequence);
    MovementPlannerObservation Latest(std::uint64_t botGuid) const;
    MovementPlannerObservation ForReceipt(std::uint64_t receiptId) const;
    MovementPlannerObservation ForTrace(std::uint64_t botGuid,
        std::uint64_t traceSequence) const;
    bool HasPendingTraceObservation(std::uint64_t botGuid) const;
    void ClearBot(std::uint64_t botGuid);
    void ClearAll();

private:
    using TraceObservation = std::pair<std::uint64_t,
        MovementPlannerObservation>;

    MovementPlannerObservation* MutableReceipt(std::uint64_t receiptId,
        std::uint64_t botGuid, std::uint32_t mapId);
    bool MatchesContext(Movement::NativePathLaunchContext const& context) const;
    void PublishReceiptUpdate(MovementPlannerObservation const& observation);
    void RetainRejectedHazard(
        MovementPlannerObservation const& observation);
    void RetainCompleteHazardRetry(
        MovementPlannerObservation const& observation,
        NativePathProofObservation const* nativeProof, bool accepted);

    std::map<std::uint64_t, MovementPlannerObservation> _latestByGuid;
    std::map<std::uint64_t, bool> _pendingByGuid;
    std::map<std::uint64_t, std::deque<TraceObservation>> _traceByGuid;
    std::map<std::uint64_t, std::deque<MovementPlannerObservation>>
        _rejectedHazardsByGuid;
    std::map<std::uint64_t, MovementPlannerObservation> _receiptById;
    std::map<std::uint64_t, std::deque<std::uint64_t>> _receiptIdsByGuid;
    std::map<std::uint64_t, std::uint64_t>
        _incompleteHazardFingerprintByGuid;
    std::uint64_t _nextReceiptId = 1;
};

MovementPlannerDiagnosticSidecar& MovementPlannerDiagnostics();

std::uint64_t BeginMovementPlannerReceipt(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent,
    BotMovementArbitration::Scope const& scope,
    std::uint64_t dynamicTargetGuid, float actorX, float actorY, float actorZ,
    bool progressCaptureEnabled = false,
    std::uint64_t diagnosticTargetGuid = 0);
Movement::NativePathLaunchContext NativePathLaunchContextForReceipt(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId);

void RecordMovementPlannerOutcome(std::uint64_t receiptId,
    std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent, bool targetFloorSampled,
    float targetFloorZ, bool targetFloorValid, char const* gate, bool accepted,
    char const* reason, PathPlan const& plan,
    NativePathProofObservation const* nativeProof = nullptr,
    NativePathControlSequence const* plannedControls = nullptr,
    PrimaryDisposition primaryDisposition = PrimaryDisposition::Forbidden,
    NativePathProofObservation const* primaryNativeProof = nullptr,
    bool localFallbackAttempted = false);

// Compatibility overload for value fixtures and callers that do not own a
// native-launch correlation token.
void RecordMovementPlannerOutcome(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent, bool targetFloorSampled,
    float targetFloorZ, bool targetFloorValid, char const* gate, bool accepted,
    char const* reason,
    NativePathProofObservation const* nativeProof = nullptr);

void RecordMovementPlannerExecutorOutcome(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent, char const* gate,
    char const* result, char const* reason, std::uint64_t receiptId = 0);

void RecordNativePathSubmission(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId, float actorX, float actorY,
    float actorZ, float selectedX, float selectedY, float selectedZ,
    bool generatePath);

void ArmMovementProgressReceipt(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId, bool splineInitialized,
    std::uint32_t splineId, float splineFinalX, float splineFinalY,
    float splineFinalZ, std::uint64_t observedAtMs);

// Serializers return an explicit unavailable object when no planner outcome
// belongs to a diagnosis or trace sequence. They never turn a zero-valued
// default into an accepted planner result.
std::string MovementPlannerObservationJson(
    MovementPlannerObservation const& observation);

}

#endif

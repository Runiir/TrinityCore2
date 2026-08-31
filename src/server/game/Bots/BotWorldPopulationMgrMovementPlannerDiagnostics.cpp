#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include <cmath>
#include <cstring>
#include <limits>
#include <utility>
namespace
{
std::uint64_t MovementIntentFingerprint(
    BotWorldMovement::Intent const& intent, std::uint32_t mapId,
    std::uint64_t dynamicTargetGuid)
{
    constexpr std::uint64_t OffsetBasis = 14695981039346656037ULL;
    constexpr std::uint64_t Prime = 1099511628211ULL;
    std::uint64_t hash = OffsetBasis;
    auto appendByte = [&](std::uint8_t value)
    {
        hash ^= value;
        hash *= Prime;
    };
    auto appendUint64 = [&](std::uint64_t value)
    {
        for (unsigned shift = 0; shift < 64; shift += 8)
            appendByte(std::uint8_t((value >> shift) & 0xffU));
    };
    auto appendFloat = [&](float value)
    {
        std::uint32_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        for (unsigned shift = 0; shift < 32; shift += 8)
            appendByte(std::uint8_t((bits >> shift) & 0xffU));
    };

    appendUint64(mapId);
    appendUint64(std::uint8_t(intent.Owner));
    appendUint64(std::uint8_t(intent.Priority));
    appendFloat(intent.X);
    appendFloat(intent.Y);
    appendFloat(intent.Z);
    appendByte(intent.ReferenceFloorZ.has_value());
    if (intent.ReferenceFloorZ)
        appendFloat(*intent.ReferenceFloorZ);
    appendUint64(dynamicTargetGuid);
    appendFloat(intent.DynamicTargetRange);
    appendByte(intent.TerminalOnFailure);
    appendByte(intent.AllowProgressiveSegments);
    appendByte(intent.BoundedHazardProgress);
    appendByte(intent.RequireCompletePath);
    appendByte(intent.AllowRecentFailureRetry);
    appendByte(intent.AllowNativeLongPath);
    appendByte(intent.NativeRecoveryCrossMapPending);
    appendUint64(intent.IntentReason.size());
    for (char value : intent.IntentReason)
        appendByte(std::uint8_t(value));
    return hash;
}
}
namespace BotWorldMovement
{
char const* PrimaryDispositionName(PrimaryDisposition disposition)
{
    switch (disposition)
    {
        case PrimaryDisposition::CompleteTerminal:
            return "complete_terminal";
        case PrimaryDisposition::IncompleteFallbackEligible:
            return "incomplete_fallback_eligible";
        case PrimaryDisposition::Forbidden:
            return "forbidden";
    }
    return "forbidden";
}

std::uint64_t NativePathControlsFingerprint(
    Movement::NativePathLaunchControls const& controls)
{
    constexpr std::uint64_t OffsetBasis = 14695981039346656037ULL;
    constexpr std::uint64_t Prime = 1099511628211ULL;
    std::uint64_t hash = OffsetBasis;
    auto appendByte = [&](std::uint8_t value)
    {
        hash ^= value;
        hash *= Prime;
    };
    auto appendUint64 = [&](std::uint64_t value)
    {
        for (unsigned shift = 0; shift < 64; shift += 8)
            appendByte(std::uint8_t((value >> shift) & 0xffU));
    };
    auto appendFloat = [&](float value)
    {
        static_assert(std::numeric_limits<float>::is_iec559);
        std::uint32_t bits = 0;
        std::memcpy(&bits, &value, sizeof(bits));
        for (unsigned shift = 0; shift < 32; shift += 8)
            appendByte(std::uint8_t((bits >> shift) & 0xffU));
    };
    appendUint64(controls.size());
    for (G3D::Vector3 const& control : controls)
    {
        appendFloat(control.x);
        appendFloat(control.y);
        appendFloat(control.z);
    }
    return hash;
}
NativePathControlSequence ObserveNativePathControls(
    Movement::NativePathLaunchControls const& controls,
    char const* coordinateSpace)
{
    NativePathControlSequence sequence;
    sequence.Available = true;
    sequence.CoordinateSpace = coordinateSpace
        ? coordinateSpace : "unavailable";
    sequence.ControlCount = controls.size();
    sequence.Fingerprint = NativePathControlsFingerprint(controls);
    return sequence;
}
std::uint64_t MovementPlannerDiagnosticSidecar::BeginReceipt(
    std::uint64_t botGuid, std::uint32_t requestedMapId, Intent const& intent,
    BotMovementArbitration::Scope const& scope,
    std::uint64_t dynamicTargetGuid, float actorX, float actorY, float actorZ,
    bool progressCaptureEnabled)
{
    if (!botGuid)
        return 0;

    std::uint64_t const receiptId = _nextReceiptId++;
    MovementPlannerObservation observation;
    observation.BotGuid = botGuid;
    observation.RequestedMapId = requestedMapId;
    observation.RequestedX = intent.X;
    observation.RequestedY = intent.Y;
    observation.RequestedZ = intent.Z;
    observation.MovementOwner = intent.Owner;
    observation.IntentReason = intent.IntentReason;
    observation.AllowProgressiveSegments = intent.AllowProgressiveSegments;
    observation.RequireCompletePath = intent.RequireCompletePath;
    observation.AllowNativeLongPath = intent.AllowNativeLongPath;
    observation.DynamicTarget = intent.DynamicTarget != nullptr;
    observation.LaunchReceipt.Id = receiptId;
    observation.LaunchReceipt.IntentFingerprint = MovementIntentFingerprint(
        intent, requestedMapId, dynamicTargetGuid);
    observation.LaunchReceipt.Scope = scope;
    observation.LaunchReceipt.DynamicTargetGuid = dynamicTargetGuid;
    observation.LaunchReceipt.ProgressCaptureEnabled = progressCaptureEnabled;
    observation.LaunchReceipt.ActorBeforePlanning = {
        true, "world", actorX, actorY, actorZ
    };

    auto& receiptIds = _receiptIdsByGuid[botGuid];
    receiptIds.push_back(receiptId);
    while (receiptIds.size() > MaxTraceHistory)
    {
        _receiptById.erase(receiptIds.front());
        receiptIds.pop_front();
    }
    Record(std::move(observation));
    return receiptId;
}

void MovementPlannerDiagnosticSidecar::Record(
    MovementPlannerObservation observation)
{
    if (!observation.BotGuid)
        return;

    observation.Available = true;
    if (observation.LaunchReceipt.Id)
        _receiptById[observation.LaunchReceipt.Id] = observation;
    _latestByGuid[observation.BotGuid] = std::move(observation);
    _pendingByGuid[observation.BotGuid] = true;
}

Movement::NativePathLaunchContext
MovementPlannerDiagnosticSidecar::LaunchContext(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId)
{
    auto receipt = _receiptById.find(receiptId);
    if (!receiptId || receipt == _receiptById.end()
        || receipt->second.BotGuid != botGuid
        || receipt->second.RequestedMapId != mapId)
        return {};
    NativePathLaunchReceipt const& launch = receipt->second.LaunchReceipt;
    return {
        launch.Version,
        launch.Id,
        botGuid,
        mapId,
        launch.IntentFingerprint,
        launch.Scope.AttemptId,
        launch.Scope.WipeGeneration,
        launch.Scope.RouteGeneration,
        launch.Scope.InstanceId,
        this
    };
}

MovementPlannerObservation* MovementPlannerDiagnosticSidecar::MutableReceipt(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId)
{
    auto receipt = _receiptById.find(receiptId);
    if (!receiptId || receipt == _receiptById.end()
        || receipt->second.BotGuid != botGuid
        || receipt->second.RequestedMapId != mapId)
        return nullptr;
    return &receipt->second;
}

bool MovementPlannerDiagnosticSidecar::MatchesContext(
    Movement::NativePathLaunchContext const& context) const
{
    auto receipt = _receiptById.find(context.ReceiptId);
    if (!context || receipt == _receiptById.end())
        return false;
    MovementPlannerObservation const& observation = receipt->second;
    NativePathLaunchReceipt const& launch = observation.LaunchReceipt;
    return context.Version == launch.Version
        && context.ActorGuid == observation.BotGuid
        && context.MapId == observation.RequestedMapId
        && context.IntentFingerprint == launch.IntentFingerprint
        && context.AttemptId == launch.Scope.AttemptId
        && context.WipeGeneration == launch.Scope.WipeGeneration
        && context.RouteGeneration == launch.Scope.RouteGeneration
        && context.InstanceId == launch.Scope.InstanceId
        && context.Observer == this;
}

void MovementPlannerDiagnosticSidecar::PublishReceiptUpdate(
    MovementPlannerObservation const& observation)
{
    std::uint64_t const receiptId = observation.LaunchReceipt.Id;
    if (!receiptId)
        return;
    _receiptById[receiptId] = observation;
    auto latest = _latestByGuid.find(observation.BotGuid);
    if (latest != _latestByGuid.end()
        && latest->second.LaunchReceipt.Id == receiptId)
        latest->second = observation;
    auto history = _traceByGuid.find(observation.BotGuid);
    if (history != _traceByGuid.end())
        for (auto& [sequence, traced] : history->second)
        {
            (void)sequence;
            if (traced.LaunchReceipt.Id == receiptId)
                traced = observation;
        }
}

namespace
{
bool MatchesRequest(MovementPlannerObservation const& observation,
    std::uint64_t botGuid, std::uint32_t requestedMapId, Intent const& intent)
{
    return observation.Available && observation.BotGuid == botGuid
        && observation.RequestedMapId == requestedMapId
        && observation.RequestedX == intent.X
        && observation.RequestedY == intent.Y
        && observation.RequestedZ == intent.Z
        && observation.MovementOwner == intent.Owner
        && observation.IntentReason == intent.IntentReason
        && observation.AllowProgressiveSegments
            == intent.AllowProgressiveSegments
        && observation.RequireCompletePath == intent.RequireCompletePath
        && observation.AllowNativeLongPath == intent.AllowNativeLongPath
        && observation.DynamicTarget == (intent.DynamicTarget != nullptr);
}
}

void MovementPlannerDiagnosticSidecar::FinalizeExecutor(
    std::uint64_t botGuid, std::uint32_t requestedMapId, Intent const& intent,
    char const* gate, char const* result, char const* reason,
    std::uint64_t receiptId)
{
    if (!botGuid)
        return;

    MovementPlannerObservation observation;
    bool receiptFound = false;
    if (receiptId)
    {
        if (MovementPlannerObservation* receipt = MutableReceipt(receiptId,
                botGuid, requestedMapId))
        {
            observation = *receipt;
            receiptFound = true;
        }
    }
    else
        observation = Latest(botGuid);
    auto pending = _pendingByGuid.find(botGuid);
    bool const hasPendingPlanner = pending != _pendingByGuid.end()
        && pending->second;
    if ((receiptId && !receiptFound)
        || (!receiptId && !hasPendingPlanner)
        || !MatchesRequest(observation, botGuid, requestedMapId, intent))
        observation = {};
    observation.Available = true;
    observation.BotGuid = botGuid;
    observation.RequestedMapId = requestedMapId;
    observation.RequestedX = intent.X;
    observation.RequestedY = intent.Y;
    observation.RequestedZ = intent.Z;
    observation.MovementOwner = intent.Owner;
    observation.IntentReason = intent.IntentReason;
    observation.AllowProgressiveSegments = intent.AllowProgressiveSegments;
    observation.RequireCompletePath = intent.RequireCompletePath;
    observation.AllowNativeLongPath = intent.AllowNativeLongPath;
    observation.DynamicTarget = intent.DynamicTarget != nullptr;
    observation.Gate = gate ? gate : "executor_admission";
    observation.Result = result ? result : "unavailable";
    observation.Reason = reason ? reason : "";
    Record(std::move(observation));
}

void MovementPlannerDiagnosticSidecar::RecordPlannerOutcome(
    std::uint64_t receiptId, std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent,
    bool targetFloorSampled, float targetFloorZ, bool targetFloorValid,
    char const* gate, bool accepted, char const* reason,
    PathPlan const& plan, NativePathProofObservation const* nativeProof,
    NativePathControlSequence const* plannedControls,
    PrimaryDisposition primaryDisposition,
    NativePathProofObservation const* primaryNativeProof,
    bool localFallbackAttempted)
{
    auto receipt = _receiptById.find(receiptId);
    if (receipt == _receiptById.end()
        || !MatchesRequest(receipt->second, botGuid, requestedMapId, intent))
        return;
    MovementPlannerObservation observation = receipt->second;
    observation.TargetFloorSampled = targetFloorSampled;
    observation.TargetFloorZ = targetFloorZ;
    observation.TargetFloorValid = targetFloorSampled && targetFloorValid;
    observation.ZDeltaAvailable = observation.TargetFloorValid;
    observation.AbsoluteZDelta = observation.ZDeltaAvailable
        ? std::fabs(targetFloorZ - observation.RequestedZ) : 0.0f;
    if (nativeProof)
        observation.NativeProof = *nativeProof;
    observation.PrimaryPathDisposition = primaryDisposition;
    if (primaryNativeProof)
        observation.PrimaryNativeProof = *primaryNativeProof;
    observation.LocalFallbackAttempted = localFallbackAttempted;
    observation.FinalTraversalMode = plan.TraversalMode.empty()
        ? "unavailable" : plan.TraversalMode;
    observation.PlannerGate = gate ? gate : "planner_admission";
    observation.PlannerResult = accepted ? "accepted" : "rejected";
    observation.PlannerReason = reason ? reason : "";
    observation.Gate = observation.PlannerGate;
    observation.Result = observation.PlannerResult;
    observation.Reason = observation.PlannerReason;
    observation.LaunchReceipt.PlannerSelectedEndpointAvailable = plan.Selected;
    observation.LaunchReceipt.PlannerSelectedX = plan.SegmentX;
    observation.LaunchReceipt.PlannerSelectedY = plan.SegmentY;
    observation.LaunchReceipt.PlannerSelectedZ = plan.SegmentZ;
    observation.LaunchReceipt.PrimaryPathDisposition = primaryDisposition;
    if (primaryNativeProof)
        observation.LaunchReceipt.PrimaryNativeProof = *primaryNativeProof;
    observation.LaunchReceipt.LocalFallbackAttempted =
        localFallbackAttempted;
    observation.LaunchReceipt.FinalTraversalMode =
        observation.FinalTraversalMode;
    if (plannedControls)
        observation.LaunchReceipt.PlannerControls = *plannedControls;
    RetainCompleteHazardRetry(observation, nativeProof, accepted);
    PublishReceiptUpdate(observation);
}

void MovementPlannerDiagnosticSidecar::RecordNativeSubmission(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId,
    float actorX, float actorY, float actorZ, float selectedX,
    float selectedY, float selectedZ, bool generatePath)
{
    MovementPlannerObservation* receipt = MutableReceipt(receiptId, botGuid,
        mapId);
    if (!receipt)
        return;
    MovementPlannerObservation observation = *receipt;
    observation.LaunchReceipt.ActorBeforeNativeSubmission = {
        true, "world", actorX, actorY, actorZ
    };
    observation.LaunchReceipt.ExecutorDestinationAvailable = true;
    observation.LaunchReceipt.ExecutorSelectedX = selectedX;
    observation.LaunchReceipt.ExecutorSelectedY = selectedY;
    observation.LaunchReceipt.ExecutorSelectedZ = selectedZ;
    observation.LaunchReceipt.PointGeneratePath = generatePath;
    PublishReceiptUpdate(observation);
}

void MovementPlannerDiagnosticSidecar::RecordMotionMasterSubmission(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId,
    std::uint32_t slot, std::uint32_t generatorType)
{
    MovementPlannerObservation* receipt = MutableReceipt(receiptId, botGuid,
        mapId);
    if (!receipt)
        return;
    MovementPlannerObservation observation = *receipt;
    observation.LaunchReceipt.MotionMasterSubmissionObserved = true;
    observation.LaunchReceipt.MotionMasterSlot = slot;
    observation.LaunchReceipt.MotionMasterGeneratorType = generatorType;
    PublishReceiptUpdate(observation);
}

void MovementPlannerDiagnosticSidecar::RecordPointGeneratorInitialize(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId)
{
    MovementPlannerObservation* receipt = MutableReceipt(receiptId, botGuid,
        mapId);
    if (!receipt)
        return;
    MovementPlannerObservation observation = *receipt;
    observation.LaunchReceipt.PointGeneratorInitialized = true;
    PublishReceiptUpdate(observation);
}

void MovementPlannerDiagnosticSidecar::RecordSplinePreparation(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId,
    bool secondPathAttempted, bool secondPathCalculated,
    std::uint32_t secondPathType,
    Movement::NativePathLaunchControls const& secondPathControls,
    bool directTwoPointSelected, bool directTwoPointFallback)
{
    MovementPlannerObservation* receipt = MutableReceipt(receiptId, botGuid,
        mapId);
    if (!receipt)
        return;
    MovementPlannerObservation observation = *receipt;
    NativeSplineLaunchObservation launch;
    launch.SecondPathAttempted = secondPathAttempted;
    launch.SecondPathCalculated = secondPathCalculated;
    launch.SecondPathType = secondPathType;
    if (secondPathAttempted)
        launch.SecondPathControls = ObserveNativePathControls(
            secondPathControls, "world");
    launch.DirectTwoPointSelected = directTwoPointSelected;
    launch.DirectTwoPointFallback = directTwoPointFallback;
    if (observation.LaunchReceipt.Launches.size()
        < NativePathLaunchReceipt::MaxLaunchAttempts)
        observation.LaunchReceipt.Launches.push_back(std::move(launch));
    else
    {
        ++observation.LaunchReceipt.LaunchAttemptOverflowCount;
        observation.LaunchReceipt.Launches.back() = std::move(launch);
    }
    PublishReceiptUpdate(observation);
}

void MovementPlannerDiagnosticSidecar::RecordSplineLaunch(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId,
    Movement::NativePathLaunchControls const& launchedControls,
    char const* coordinateSpace, bool succeeded, bool finalized,
    bool splineInitialized, std::uint32_t splineId, float splineFinalX,
    float splineFinalY, float splineFinalZ, float actorX, float actorY,
    float actorZ)
{
    MovementPlannerObservation* receipt = MutableReceipt(receiptId, botGuid,
        mapId);
    if (!receipt)
        return;
    MovementPlannerObservation observation = *receipt;
    if (observation.LaunchReceipt.Launches.empty()
        || observation.LaunchReceipt.Launches.back().LaunchAttempted)
    {
        if (observation.LaunchReceipt.Launches.size()
            < NativePathLaunchReceipt::MaxLaunchAttempts)
            observation.LaunchReceipt.Launches.emplace_back();
        else
        {
            ++observation.LaunchReceipt.LaunchAttemptOverflowCount;
            observation.LaunchReceipt.Launches.back() = {};
        }
    }
    NativeSplineLaunchObservation& launch =
        observation.LaunchReceipt.Launches.back();
    launch.LaunchAttempted = true;
    launch.LaunchSucceeded = succeeded;
    launch.SplineFinalizedAfterLaunch = finalized;
    launch.SplineInitialized = splineInitialized;
    launch.SplineId = splineId;
    launch.SplineFinalX = splineFinalX;
    launch.SplineFinalY = splineFinalY;
    launch.SplineFinalZ = splineFinalZ;
    launch.LaunchedControls = ObserveNativePathControls(launchedControls,
        coordinateSpace);
    launch.ActorAfterLaunch = { true, "world", actorX, actorY, actorZ };
    PublishReceiptUpdate(observation);
    if (succeeded && observation.LaunchReceipt.ProgressCaptureEnabled)
        ArmProgress(receiptId, botGuid, mapId, splineInitialized, splineId,
            splineFinalX, splineFinalY, splineFinalZ, 0);
}

void MovementPlannerDiagnosticSidecar::ArmProgress(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId,
    bool splineInitialized, std::uint32_t splineId, float splineFinalX,
    float splineFinalY, float splineFinalZ, std::uint64_t observedAtMs)
{
    MovementPlannerObservation* receipt = MutableReceipt(receiptId, botGuid,
        mapId);
    if (!receipt || !receipt->LaunchReceipt.ProgressCaptureEnabled
        || !receipt->LaunchReceipt.ExecutorDestinationAvailable
        || !receipt->LaunchReceipt.MotionMasterSubmissionObserved
        || !receipt->LaunchReceipt.PointGeneratorInitialized)
        return;
    NativeSplineLaunchObservation const* launched = nullptr;
    for (NativeSplineLaunchObservation const& launch
        : receipt->LaunchReceipt.Launches)
        if (launch.LaunchSucceeded && launch.ActorAfterLaunch.Available)
            launched = &launch;
    if (!launched)
        return;
    if (!splineInitialized || !launched->SplineInitialized
        || splineId != launched->SplineId)
        return;
    NativePathLaunchReceipt const& identity = receipt->LaunchReceipt;
    MovementProgressDiagnostics().Arm(identity.Id, botGuid, mapId,
        identity.Scope.InstanceId, identity.Scope,
        identity.ExecutorSelectedX, identity.ExecutorSelectedY,
        identity.ExecutorSelectedZ, launched->ActorAfterLaunch.X,
        launched->ActorAfterLaunch.Y, launched->ActorAfterLaunch.Z,
        splineInitialized, splineId, splineFinalX, splineFinalY, splineFinalZ,
        observedAtMs);
}

void MovementPlannerDiagnosticSidecar::OnMotionMasterSubmission(
    Movement::NativePathLaunchContext const& context, std::uint32_t slot,
    std::uint32_t generatorType)
{
    if (!MatchesContext(context))
        return;
    RecordMotionMasterSubmission(context.ReceiptId, context.ActorGuid,
        context.MapId, slot, generatorType);
}

void MovementPlannerDiagnosticSidecar::OnPointGeneratorInitialize(
    Movement::NativePathLaunchContext const& context)
{
    if (!MatchesContext(context))
        return;
    RecordPointGeneratorInitialize(context.ReceiptId, context.ActorGuid,
        context.MapId);
}

void MovementPlannerDiagnosticSidecar::OnSplinePreparation(
    Movement::NativePathLaunchContext const& context,
    bool secondPathAttempted, bool secondPathCalculated,
    std::uint32_t secondPathType,
    Movement::NativePathLaunchControls const& secondPathControls,
    bool directTwoPointSelected, bool directTwoPointFallback)
{
    if (!MatchesContext(context))
        return;
    RecordSplinePreparation(context.ReceiptId, context.ActorGuid,
        context.MapId, secondPathAttempted, secondPathCalculated,
        secondPathType, secondPathControls, directTwoPointSelected,
        directTwoPointFallback);
}

void MovementPlannerDiagnosticSidecar::OnSplineLaunch(
    Movement::NativePathLaunchContext const& context,
    Movement::NativePathLaunchControls const& launchedControls,
    Movement::NativePathLaunchCoordinateSpace coordinateSpace,
    bool succeeded, bool finalized, bool splineInitialized,
    std::uint32_t splineId, float splineFinalX, float splineFinalY,
    float splineFinalZ, float actorX, float actorY, float actorZ)
{
    if (!MatchesContext(context))
        return;
    RecordSplineLaunch(context.ReceiptId, context.ActorGuid, context.MapId,
        launchedControls,
        coordinateSpace == Movement::NativePathLaunchCoordinateSpace::World
            ? "world" : "transport_offset",
        succeeded, finalized, splineInitialized, splineId, splineFinalX,
        splineFinalY, splineFinalZ, actorX, actorY, actorZ);
}

void MovementPlannerDiagnosticSidecar::AssociateTrace(
    std::uint64_t botGuid, std::uint64_t traceSequence)
{
    if (!botGuid || !traceSequence)
        return;

    MovementPlannerObservation observation;
    auto pending = _pendingByGuid.find(botGuid);
    if (pending != _pendingByGuid.end() && pending->second)
    {
        auto latest = _latestByGuid.find(botGuid);
        if (latest != _latestByGuid.end())
            observation = latest->second;
        pending->second = false;
    }

    auto& history = _traceByGuid[botGuid];
    history.emplace_back(traceSequence, std::move(observation));
    while (history.size() > MaxTraceHistory)
        history.pop_front();
}

MovementPlannerObservation MovementPlannerDiagnosticSidecar::Latest(
    std::uint64_t botGuid) const
{
    auto itr = _latestByGuid.find(botGuid);
    return itr == _latestByGuid.end() ? MovementPlannerObservation()
                                       : itr->second;
}

MovementPlannerObservation MovementPlannerDiagnosticSidecar::ForTrace(
    std::uint64_t botGuid, std::uint64_t traceSequence) const
{
    auto botHistory = _traceByGuid.find(botGuid);
    if (botHistory != _traceByGuid.end())
        for (auto const& [sequence, observation] : botHistory->second)
            if (sequence == traceSequence)
                return observation;
    return {};
}

void MovementPlannerDiagnosticSidecar::ClearBot(std::uint64_t botGuid)
{
    MovementProgressDiagnostics().ClearBot(botGuid);
    auto receiptIds = _receiptIdsByGuid.find(botGuid);
    if (receiptIds != _receiptIdsByGuid.end())
    {
        for (std::uint64_t receiptId : receiptIds->second)
            _receiptById.erase(receiptId);
        _receiptIdsByGuid.erase(receiptIds);
    }
    _latestByGuid.erase(botGuid);
    _pendingByGuid.erase(botGuid);
    _traceByGuid.erase(botGuid);
    _incompleteHazardFingerprintByGuid.erase(botGuid);
}

void MovementPlannerDiagnosticSidecar::ClearAll()
{
    MovementProgressDiagnostics().ClearAll();
    _latestByGuid.clear();
    _pendingByGuid.clear();
    _traceByGuid.clear();
    _receiptById.clear();
    _receiptIdsByGuid.clear();
    _incompleteHazardFingerprintByGuid.clear();
    _nextReceiptId = 1;
}

MovementPlannerDiagnosticSidecar& MovementPlannerDiagnostics()
{
    static MovementPlannerDiagnosticSidecar sidecar;
    return sidecar;
}

std::uint64_t BeginMovementPlannerReceipt(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent,
    BotMovementArbitration::Scope const& scope,
    std::uint64_t dynamicTargetGuid, float actorX, float actorY, float actorZ,
    bool progressCaptureEnabled)
{
    return MovementPlannerDiagnostics().BeginReceipt(botGuid, requestedMapId,
        intent, scope, dynamicTargetGuid, actorX, actorY, actorZ,
        progressCaptureEnabled);
}

Movement::NativePathLaunchContext NativePathLaunchContextForReceipt(
    std::uint64_t receiptId, std::uint64_t botGuid, std::uint32_t mapId)
{
    return MovementPlannerDiagnostics().LaunchContext(receiptId, botGuid,
        mapId);
}

void RecordMovementPlannerOutcome(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t requestedMapId,
    Intent const& intent, bool targetFloorSampled, float targetFloorZ,
    bool targetFloorValid, char const* gate, bool accepted, char const* reason,
    PathPlan const& plan, NativePathProofObservation const* nativeProof,
    NativePathControlSequence const* plannedControls,
    PrimaryDisposition primaryDisposition,
    NativePathProofObservation const* primaryNativeProof,
    bool localFallbackAttempted)
{
    MovementPlannerDiagnostics().RecordPlannerOutcome(receiptId,
        botGuid, requestedMapId, intent, targetFloorSampled, targetFloorZ,
        targetFloorValid, gate, accepted, reason, plan, nativeProof,
        plannedControls, primaryDisposition, primaryNativeProof,
        localFallbackAttempted);
}

void RecordMovementPlannerOutcome(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent,
    bool targetFloorSampled, float targetFloorZ, bool targetFloorValid,
    char const* gate, bool accepted, char const* reason,
    NativePathProofObservation const* nativeProof)
{
    MovementPlannerObservation observation;
    observation.BotGuid = botGuid;
    observation.RequestedMapId = requestedMapId;
    observation.RequestedX = intent.X;
    observation.RequestedY = intent.Y;
    observation.RequestedZ = intent.Z;
    observation.MovementOwner = intent.Owner;
    observation.IntentReason = intent.IntentReason;
    observation.TargetFloorSampled = targetFloorSampled;
    observation.TargetFloorZ = targetFloorZ;
    observation.TargetFloorValid = targetFloorSampled && targetFloorValid;
    observation.ZDeltaAvailable = observation.TargetFloorValid;
    observation.AbsoluteZDelta = observation.ZDeltaAvailable
        ? std::fabs(targetFloorZ - intent.Z) : 0.0f;
    observation.AllowProgressiveSegments = intent.AllowProgressiveSegments;
    observation.RequireCompletePath = intent.RequireCompletePath;
    observation.AllowNativeLongPath = intent.AllowNativeLongPath;
    observation.DynamicTarget = intent.DynamicTarget != nullptr;
    if (nativeProof)
        observation.NativeProof = *nativeProof;
    observation.PlannerGate = gate ? gate : "planner_admission";
    observation.PlannerResult = accepted ? "accepted" : "rejected";
    observation.PlannerReason = reason ? reason : "";
    observation.Gate = gate ? gate : "planner_admission";
    observation.Result = accepted ? "accepted" : "rejected";
    observation.Reason = reason ? reason : "";
    MovementPlannerDiagnostics().Record(std::move(observation));
}

void RecordMovementPlannerExecutorOutcome(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent, char const* gate,
    char const* result, char const* reason, std::uint64_t receiptId)
{
    MovementPlannerDiagnostics().FinalizeExecutor(botGuid, requestedMapId,
        intent, gate, result, reason, receiptId);
}

void RecordNativePathSubmission(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId, float actorX, float actorY,
    float actorZ, float selectedX, float selectedY, float selectedZ,
    bool generatePath)
{
    MovementPlannerDiagnostics().RecordNativeSubmission(receiptId, botGuid,
        mapId, actorX, actorY, actorZ, selectedX, selectedY, selectedZ,
        generatePath);
}

void ArmMovementProgressReceipt(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId, bool splineInitialized,
    std::uint32_t splineId, float splineFinalX, float splineFinalY,
    float splineFinalZ, std::uint64_t observedAtMs)
{
    MovementPlannerDiagnostics().ArmProgress(receiptId, botGuid, mapId,
        splineInitialized, splineId, splineFinalX, splineFinalY, splineFinalZ,
        observedAtMs);
}

}

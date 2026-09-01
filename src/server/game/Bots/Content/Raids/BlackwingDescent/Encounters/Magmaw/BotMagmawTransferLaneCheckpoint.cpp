#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneCheckpoint.h"

#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cmath>
#include <utility>

namespace BotEncounter::MagmawTransferLaneCheckpoint
{
namespace
{
bool IsLowerHex(std::string_view value, size_t length)
{
    if (value.size() != length)
        return false;
    for (char character : value)
        if (!((character >= '0' && character <= '9')
                || (character >= 'a' && character <= 'f')))
            return false;
    return true;
}

bool Near(float left, float right, float tolerance)
{
    return std::fabs(left - right) <= tolerance;
}

bool ExactScope(BotMovementArbitration::Scope const& left,
    BotMovementArbitration::Scope const& right)
{
    return left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration
        && left.MapId == right.MapId && left.InstanceId == right.InstanceId;
}

bool ExactRequestedPrimaryProof(
    BotWorldMovement::NativePathProofObservation const& proof,
    MagmawTransferLaneTask const& task, float selectedX, float selectedY,
    float selectedZ)
{
    // Destination identity is horizontal. MMAP may normalize Z to the
    // walkable polygon, but the native proof must keep that projection within
    // the strict endpoint component bound and on the admitted floor.
    return proof.Available && proof.Calculated && proof.Complete
        && proof.EndpointResult == PathEndpointResult::ReachedRequested
        && proof.CorridorReachedEndPoly && proof.ResolvedEndpointAvailable
        && proof.ResolvedEndpointX == task.Destination.X
        && proof.ResolvedEndpointY == task.Destination.Y
        && proof.ResolvedEndpointZ == task.Destination.Z
        && proof.ActualEndpointMatchedResolved && proof.EndpointMatched
        && proof.EndpointFloorValid && proof.Accepted
        && BotWorldMovement::NativePathProofPassesAdmission(proof)
        && proof.EndpointX == task.Destination.X
        && proof.EndpointY == task.Destination.Y
        && proof.EndpointX == selectedX && proof.EndpointY == selectedY
        && proof.EndpointZ == selectedZ
        && proof.EndpointHorizontalDistance == 0.0f
        && proof.ResolvedEndpointHorizontalDistance == 0.0f
        && proof.EndpointVerticalDistance
            == std::fabs(proof.EndpointZ - task.Destination.Z)
        && proof.ResolvedEndpointVerticalDistance
            == proof.EndpointVerticalDistance
        && BotWorldMovement::NativePathEndpointComponentsMatch(
            proof.EndpointHorizontalDistance,
            proof.EndpointVerticalDistance)
        && Near(selectedZ, task.Destination.Z,
            BotWorldMovement::NativePathEndpointVerticalTolerance);
}
}

char const* StageName(Stage stage)
{
    switch (stage)
    {
        case Stage::Armed: return "armed";
        case Stage::Queued: return "queued";
        case Stage::NativeSubmitted: return "native_submitted";
        case Stage::Progressing: return "progressing";
        case Stage::Completed: return "completed";
        case Stage::Failed: return "failed";
        default: return "disabled";
    }
}

bool AdmissionMatches(AdmissionInput const& input)
{
    return input.ValidationRouteEnabled && input.CheckpointEnabled
        && !input.TaskAuthorityEnabled
        && input.ConfiguredFixtureId == FixtureId
        && input.ConfiguredCaseId == input.RequestedCaseId
        && FindCase(input.RequestedCaseId)
        && input.ConfiguredSealSha256 == input.RequestedSealSha256
        && input.ConfiguredSourceCommit == input.RequestedSourceCommit
        && IsLowerHex(input.RequestedSealSha256, 64)
        && IsLowerHex(input.RequestedSourceCommit, 40)
        && !input.BinaryRevision.empty()
        && input.RequestedSourceCommit.substr(0, input.BinaryRevision.size())
            == input.BinaryRevision;
}

bool State::Arm(std::string_view caseId, uint32 actorGuid, uint64 attemptId)
{
    if (!FindCase(caseId) || actorGuid != ActorGuid || !attemptId
        || CurrentStage != Stage::Disabled)
    {
        CurrentStage = Stage::Failed;
        Outcome = "magmaw_transfer_checkpoint_arm_identity_invalid";
        return false;
    }
    *this = {};
    CurrentStage = Stage::Armed;
    CaseId = caseId;
    Actor = actorGuid;
    AttemptId = attemptId;
    Outcome = "magmaw_transfer_checkpoint_armed";
    return true;
}

void State::Fail(std::string reason)
{
    if (!Terminal())
    {
        CurrentStage = Stage::Failed;
        Outcome = std::move(reason);
    }
}

void State::Complete()
{
    if (!Terminal())
    {
        CurrentStage = Stage::Completed;
        Outcome = "magmaw_transfer_checkpoint_completed";
    }
}

MagmawTransferLaneTask BuildTask(Case const& selected,
    Scope const& lifecycle, ObjectGuid actor, uint64 observedAtMs,
    float initialDistance)
{
    MagmawTransferLaneTask task;
    task.Id.Episode.Lifecycle = lifecycle;
    task.Id.Episode.EpisodeGeneration = EpisodeGeneration;
    task.Id.Episode.MechanicGeneration = LegacyTransitionGeneration;
    task.Id.ActorGuid = actor;
    task.Id.TaskGeneration = TaskGeneration;
    task.Destination = { selected.DestinationX, selected.DestinationY,
        selected.DestinationZ };
    task.InitialDistance = initialDistance;
    task.BestDistance = initialDistance;
    task.LastDistance = initialDistance;
    task.StartedAtMs = observedAtMs;
    task.LastProgressAtMs = observedAtMs;
    task.LastObservedAtMs = observedAtMs;
    task.ProgressRevision = 1;
    return task;
}

BotNativeAction::Candidate BuildLegacyCandidate(
    MagmawTransferLaneTask const& task)
{
    BotDecision::BotIntentSink sink;
    EmitMagmawTransferLaneTaskIntent(task, sink);
    if (sink.Proposals().size() != 1)
        return {};
    BotNativeAction::Candidate legacy = sink.Proposals().front();
    legacy.Id.EventGeneration = LegacyTransitionGeneration;
    return legacy;
}

bool ExactAuthorityOffSelection(
    MagmawTransferLaneAuthoritySelection const& selection,
    BotNativeAction::Candidate const& legacy,
    MagmawTransferLaneTask const& task)
{
    if (selection.TaskAuthorityRequested || selection.TaskAuthoritySelected
        || !selection.Movement || !selection.Binding
        || selection.Comparison.Outcome
            != MagmawTransferLaneIntentComparisonOutcome::Equivalent)
        return false;
    MagmawTransferLaneExecutionBinding const& binding = *selection.Binding;
    return selection.Movement->Id.Key() == legacy.Id.Key()
        && selection.Movement->Id.EventGeneration
            == LegacyTransitionGeneration
        && binding.Source == MagmawTransferLaneAuthoritySource::Legacy
        && binding.ScopeKey == task.Id.Episode.Lifecycle.Key()
        && binding.Actor == task.Id.ActorGuid
        && binding.EpisodeGeneration == EpisodeGeneration
        && binding.TaskGeneration == TaskGeneration
        && binding.LegacyTransitionGeneration == LegacyTransitionGeneration
        && binding.CandidateKey == legacy.Id.Key()
        && binding.Destination.X == task.Destination.X
        && binding.Destination.Y == task.Destination.Y
        && binding.Destination.Z == task.Destination.Z
        && legacy.Resources() == BotActionArbitration::Uses(
            BotActionArbitration::Resource::Movement);
}

bool OwnsQueuedKernelCandidate(State const& state,
    std::string_view candidateKey, uint32 actorGuid)
{
    return state.CurrentStage == Stage::Queued && state.QueueCount == 1
        && state.CandidateAttemptCount == 0
        && state.NativeSubmissionCount == 0 && state.Actor == actorGuid
        && state.Binding && state.CandidateKey == candidateKey
        && state.Binding->CandidateKey == candidateKey;
}

bool CaptureExactPlannerReceipt(PlannerReceiptSnapshot& snapshot,
    BotWorldMovement::MovementPlannerObservation const& planner,
    MagmawTransferLaneExecutionBinding const& binding,
    MagmawTransferLaneTask const& task)
{
    BotWorldMovement::NativePathLaunchReceipt const& receipt =
        planner.LaunchReceipt;
    BotMovementArbitration::Scope const expectedScope =
        MagmawTransferLaneMovementScope(task.Id.Episode.Lifecycle);
    BotWorldMovement::NativePathProofObservation const& plannerProof =
        planner.PrimaryNativeProof;
    BotWorldMovement::NativePathProofObservation const& receiptProof =
        receipt.PrimaryNativeProof;
    BotWorldMovement::NativeSplineLaunchObservation const* launched = nullptr;
    for (BotWorldMovement::NativeSplineLaunchObservation const& row
        : receipt.Launches)
        if (row.LaunchAttempted && row.LaunchSucceeded
            && row.SplineInitialized && row.SplineId)
            launched = &row;
    bool const exact = planner.Available && receipt.Id
        && planner.BotGuid == task.Id.ActorGuid.GetCounter()
        && planner.RequestedMapId == MapId
        && planner.MovementOwner == BotMovementArbitration::Owner::Hazard
        && planner.IntentReason == "pillar_bait_switch"
        && planner.RequestedX == task.Destination.X
        && planner.RequestedY == task.Destination.Y
        && planner.RequestedZ == task.Destination.Z
        && receipt.DiagnosticCandidateKey == binding.CandidateKey
        && ExactScope(receipt.Scope, expectedScope)
        && planner.PrimaryPathDisposition
            == BotWorldMovement::PrimaryDisposition::CompleteTerminal
        && receipt.PrimaryPathDisposition
            == BotWorldMovement::PrimaryDisposition::CompleteTerminal
        && !planner.LocalFallbackAttempted
        && !receipt.LocalFallbackAttempted
        && receipt.PlannerControls.Available
        && receipt.PlannerControls.CoordinateSpace == "world"
        && receipt.PlannerControls.ControlCount >= 2
        && receipt.PlannerSelectedEndpointAvailable
        && receipt.PlannerSelectedX == task.Destination.X
        && receipt.PlannerSelectedY == task.Destination.Y
        && ExactRequestedPrimaryProof(plannerProof, task,
            receipt.PlannerSelectedX, receipt.PlannerSelectedY,
            receipt.PlannerSelectedZ)
        && ExactRequestedPrimaryProof(receiptProof, task,
            receipt.PlannerSelectedX, receipt.PlannerSelectedY,
            receipt.PlannerSelectedZ)
        && receipt.ExecutorDestinationAvailable
        && receipt.ExecutorSelectedX == task.Destination.X
        && receipt.ExecutorSelectedY == task.Destination.Y
        && receipt.ExecutorSelectedZ == task.Destination.Z
        && receipt.PointGeneratePath
        && receipt.ProgressCaptureEnabled
        && planner.PlannerResult == "accepted"
        && planner.Result == "submitted"
        && receipt.MotionMasterSubmissionObserved
        && receipt.MotionMasterGeneratorType
        && receipt.PointGeneratorInitialized && launched;
    if (!exact)
        return false;
    snapshot.Available = true;
    snapshot.ReceiptId = receipt.Id;
    snapshot.BotGuid = planner.BotGuid;
    snapshot.Map = planner.RequestedMapId;
    snapshot.Scope = receipt.Scope;
    snapshot.CandidateKey = receipt.DiagnosticCandidateKey;
    snapshot.IntentReason = planner.IntentReason;
    snapshot.SplineId = launched->SplineId;
    snapshot.MotionMasterSlot = receipt.MotionMasterSlot;
    snapshot.MotionMasterGeneratorType = receipt.MotionMasterGeneratorType;
    snapshot.PlannerAccepted = true;
    snapshot.MotionMasterSubmitted = true;
    snapshot.PointGeneratorInitialized = true;
    snapshot.SplineLaunched = true;
    return true;
}

bool ConsumeProgressSample(State& state,
    BotWorldMovement::NativeMovementProgressSample const& sample)
{
    if (state.Terminal() || !state.PlannerReceipt.Available
        || sample.ReceiptId != state.PlannerReceipt.ReceiptId
        || sample.ObservedAtMs <= state.LastSampleObservedAtMs
        || !state.NativeOutcome
        || sample.ObservedAtMs <= state.NativeOutcome->ObservedAtMs
        || !sample.ActorAvailable || !sample.ActorInWorld || !sample.ActorAlive
        || sample.MapId != MapId || sample.InstanceId != state.InstanceId
        || !sample.SplineInitialized
        || sample.SplineId != state.PlannerReceipt.SplineId
        || !sample.MatchesLaunchedSpline)
    {
        state.Fail("magmaw_transfer_checkpoint_progress_identity_failed");
        return false;
    }

    state.LastSampleObservedAtMs = sample.ObservedAtMs;
    ++state.ConsumedProgressSamples;
    bool const sameFloor = sample.FloorSampled && sample.FloorValid
        && sample.SelectedPlatformCompatible
        && sample.ActorFloorDelta <= BotWorldMovement::NativeFloorTolerance
        && Near(sample.Z, state.Task.Destination.Z,
            BotWorldMovement::NativeFloorTolerance);
    if (!sameFloor)
    {
        ++state.WrongFloorSamples;
        return true;
    }
    state.LastProgressObservedAtMs = sample.ObservedAtMs;
    state.LastActorX = sample.X;
    state.LastActorY = sample.Y;
    state.LastActorZ = sample.Z;
    state.LastFloorZ = sample.FloorZ;

    MagmawTransferLaneActorObservation actor;
    actor.Guid = state.Task.Id.ActorGuid;
    actor.Position = { sample.X, sample.Y, sample.Z };
    actor.PositionObserved = true;
    actor.Alive = true;
    if (!state.NativeOutcomeConsumed)
    {
        actor.NativeOutcome = state.NativeOutcome;
        state.NativeOutcomeConsumed = true;
    }
    Blackboard board;
    board.Revision = state.ConsumedProgressSamples + 1;
    board.ObservedAtMs = sample.ObservedAtMs;
    MagmawTransferLaneTaskRunner::Observe(state.Task, actor, board);

    // Shared progress may have observed a closer wrong-floor sample first.
    // Seed from the checkpoint's own start distance so a first regression
    // cannot masquerade as one of the required decreasing observations.
    if (!state.LastProgressDistanceAvailable)
    {
        if (!std::isfinite(state.Task.InitialDistance)
            || state.Task.InitialDistance <= 0.0f)
        {
            state.Fail("magmaw_transfer_checkpoint_progress_baseline_invalid");
            return false;
        }
        state.LastProgressDistance = state.Task.InitialDistance;
        state.LastProgressDistanceAvailable = true;
    }
    bool const decreased = sample.EndpointDistance + 0.01f
        < state.LastProgressDistance;
    if (decreased)
    {
        ++state.DecreasingProgressSamples;
        state.LastProgressDistance = sample.EndpointDistance;
        state.LastProgressDistanceAvailable = true;
    }
    if (state.Task.State == BotDecision::PersistentTaskState::Succeeded)
    {
        // The task runner used the sampled actor position and same-floor
        // proof above. A projected endpoint or submission cannot reach this
        // branch, while a same-floor logical arrival may complete before the
        // spline publishes its terminal row.
        bool const complete = state.DecreasingProgressSamples
            >= RequiredProgressSamples;
        if (complete)
            state.Complete();
        else
            state.Fail("magmaw_transfer_checkpoint_early_semantic_success");
    }
    else if (state.Task.State == BotDecision::PersistentTaskState::Failed)
        state.Fail("magmaw_transfer_checkpoint_task_failed");
    else
        state.CurrentStage = Stage::Progressing;
    return true;
}

ProgressPublicationDecision ObserveProgressPublication(
    State& state, bool available)
{
    if (available)
        return ProgressPublicationDecision::Ready;
    return ++state.ProgressPublicationAwaitTicks
            > MaximumProgressPublicationTicks
        ? ProgressPublicationDecision::TimedOut
        : ProgressPublicationDecision::Await;
}
}

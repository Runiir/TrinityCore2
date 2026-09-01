#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTask.h"

#include "Bots/BotNativeActionIntent.h"

#include <cmath>

namespace BotEncounter
{
namespace
{
bool DestinationMatches(Vector3 const& left, Vector3 const& right)
{
    return std::hypot(left.X - right.X, left.Y - right.Y)
            <= MagmawTransferLaneLeaseDestinationTolerance2d
        && std::fabs(left.Z - right.Z)
            <= MagmawTransferLaneLeaseDestinationToleranceZ;
}

std::string ExpectedCandidateKey(MagmawTransferLaneTask const& task,
    MagmawTransferLaneExecutionBinding const& binding)
{
    BotNativeAction::CandidateIdentity identity;
    identity.ScopeKey = task.Id.Episode.Lifecycle.Key();
    identity.Strategy = "adaptive_magmaw";
    identity.Mechanic = "pillar_bait_switch";
    identity.Actor = task.Id.ActorGuid;
    identity.EventGeneration = binding.Source
            == MagmawTransferLaneAuthoritySource::Task
        ? task.Id.TaskGeneration : binding.LegacyTransitionGeneration;
    return identity.Key();
}

bool Correlates(MagmawTransferLaneTask const& task,
    MagmawTransferLaneNativeOutcome const& outcome)
{
    MagmawTransferLaneExecutionBinding const& binding = outcome.Binding;
    BotWorldMovement::ExecutionObservation const& movement = outcome.Movement;
    Vector3 const requested{ movement.RequestedX, movement.RequestedY,
        movement.RequestedZ };
    return binding.ScopeKey == task.Id.Episode.Lifecycle.Key()
        && binding.Actor == task.Id.ActorGuid
        && binding.EpisodeGeneration == task.Id.Episode.EpisodeGeneration
        && binding.TaskGeneration == task.Id.TaskGeneration
        && binding.LegacyTransitionGeneration != 0
        && binding.CandidateKey == ExpectedCandidateKey(task, binding)
        && DestinationMatches(binding.Destination, task.Destination)
        && outcome.ObservedAtMs != 0
        && movement.Available
        && DestinationMatches(requested, task.Destination);
}

bool AlreadyObserved(MagmawTransferLaneTask const& task,
    MagmawTransferLaneNativeOutcome const& outcome)
{
    uint64 const receipt = outcome.Movement.ReceiptId;
    return receipt && receipt == task.LastNativeReceiptId
        && outcome.ObservedAtMs == task.LastNativeObservedAtMs
        && outcome.Binding.CandidateKey == task.LastNativeCandidateKey;
}

void ObserveNativeOutcome(MagmawTransferLaneTask& task,
    MagmawTransferLaneActorObservation const& actor,
    Blackboard const& board)
{
    if (!actor.NativeOutcome || !Correlates(task, *actor.NativeOutcome)
        || AlreadyObserved(task, *actor.NativeOutcome))
        return;

    MagmawTransferLaneNativeOutcome const& outcome = *actor.NativeOutcome;
    BotWorldMovement::ExecutionObservation const& movement = outcome.Movement;
    task.LastNativeReceiptId = movement.ReceiptId;
    task.LastNativeObservedAtMs = outcome.ObservedAtMs;
    task.LastNativeCandidateKey = outcome.Binding.CandidateKey;
    ++task.NativeOutcomeSamples;

    bool const projected = movement.ReceiptId != 0
        && movement.EndpointResult
            == PathEndpointResult::ReachedProjectedEndPoly
        && movement.CorridorReachedEndPoly
        && movement.ResolvedEndpointAvailable
        && movement.ActualEndpointMatchedResolved
        && !movement.RequestedEndpointMatched;
    if (projected)
    {
        task.NativeDisposition = MagmawTransferLaneNativeDisposition::
            ReachedProjectedEndPolyEvidence;
        task.NativeEvidenceRevision = board.Revision;
        ++task.ProjectedEndpointEvidenceSamples;
        return;
    }
    if (movement.ReceiptId != 0
        && movement.EndpointResult == PathEndpointResult::ReachedRequested
        && movement.RequestedEndpointMatched)
    {
        task.NativeDisposition = MagmawTransferLaneNativeDisposition::
            ReachedRequestedEndpointEvidence;
        task.NativeEvidenceRevision = board.Revision;
        return;
    }
    if (movement.Disposition == BotWorldMovement::ExecutionDisposition::
            Submitted)
        task.NativeDisposition =
            MagmawTransferLaneNativeDisposition::Submitted;
    else if (movement.Disposition == BotWorldMovement::ExecutionDisposition::
            Retained)
        task.NativeDisposition = MagmawTransferLaneNativeDisposition::Retained;
    else
        task.NativeDisposition =
            MagmawTransferLaneNativeDisposition::PlannerRejected;
}

void Suspend(MagmawTransferLaneTask& task,
    BotDecision::PersistentTaskSuspension suspension, uint64 observedAtMs)
{
    if (task.State != BotDecision::PersistentTaskState::Suspended
        || !task.SuspendedAtMs)
        task.SuspendedAtMs = observedAtMs;
    task.State = BotDecision::PersistentTaskState::Suspended;
    task.Suspension = suspension;
}

void Resume(MagmawTransferLaneTask& task, uint64 observedAtMs)
{
    if (task.State == BotDecision::PersistentTaskState::Suspended
        && task.SuspendedAtMs && observedAtMs > task.SuspendedAtMs)
        task.LastProgressAtMs += observedAtMs - task.SuspendedAtMs;
    task.SuspendedAtMs = 0;
    task.State = BotDecision::PersistentTaskState::Running;
    task.Suspension = BotDecision::PersistentTaskSuspension::None;
}

bool ObserveDistance(MagmawTransferLaneTask& task,
    MagmawTransferLaneActorObservation const& actor,
    Blackboard const& board)
{
    task.LastObservedAtMs = board.ObservedAtMs;
    ++task.ObservationSamples;
    if (std::fabs(actor.Position.Z - task.Destination.Z)
        > MagmawTransferLaneLeaseDestinationToleranceZ)
        return false;

    float const distance = std::hypot(actor.Position.X - task.Destination.X,
        actor.Position.Y - task.Destination.Y);
    task.LastDistance = distance;
    if (distance + MagmawTransferLaneTaskShadow::ProgressEpsilon
        < task.BestDistance)
    {
        task.BestDistance = distance;
        task.LastProgressAtMs = board.ObservedAtMs;
        task.ProgressRevision = board.Revision;
        ++task.ProgressSamples;
        if (task.State == BotDecision::PersistentTaskState::Suspended)
            task.SuspendedAtMs = board.ObservedAtMs;
    }
    return distance <= MagmawTransferLaneTaskShadow::ArrivalTolerance;
}
}

void MagmawTransferLaneTaskRunner::Observe(
    MagmawTransferLaneTask& task,
    MagmawTransferLaneActorObservation const& actor,
    Blackboard const& board)
{
    if (BotDecision::IsTerminal(task.State))
        return;
    ObserveNativeOutcome(task, actor, board);
    task.MovementDisposition =
        ClassifyMagmawTransferLaneMovementObservation(board.ObservedAtMs,
            MagmawTransferLaneMovementScope(task.Id.Episode.Lifecycle),
            task.Destination, actor.Movement);
    if (!actor.PositionObserved)
    {
        Suspend(task,
            BotDecision::PersistentTaskSuspension::ObservationUnavailable,
            board.ObservedAtMs);
        return;
    }

    bool const safetyPreempted = IsMagmawTransferLaneSafetyPreemption(
        task.MovementDisposition);
    if (!safetyPreempted)
        Resume(task, board.ObservedAtMs);
    bool const arrived = ObserveDistance(task, actor, board);
    if (safetyPreempted)
    {
        Suspend(task, BotDecision::PersistentTaskSuspension::SafetyPreempted,
            board.ObservedAtMs);
        return;
    }
    if (arrived)
    {
        task.State = BotDecision::PersistentTaskState::Succeeded;
        task.Suspension = BotDecision::PersistentTaskSuspension::None;
        task.SuspendedAtMs = 0;
        return;
    }
    if (board.ObservedAtMs > task.LastProgressAtMs
        && board.ObservedAtMs - task.LastProgressAtMs
            >= MagmawTransferLaneTaskShadow::NoProgressFailureMs)
    {
        task.State = BotDecision::PersistentTaskState::Failed;
        task.Failure = MagmawTransferLaneFailure::NoSemanticProgress;
    }
}
}

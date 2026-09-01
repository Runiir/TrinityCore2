from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
INCLUDES = [
    "-I", str(ROOT / "src/server/game"),
    "-I", str(ROOT / "src/server/game/Entities/Object"),
    "-I", str(ROOT / "src/common"),
    "-I", str(ROOT / "src/common/Utilities"),
    "-I", str(ROOT / "src/common/Logging"),
    "-I", str(ROOT / "src/common/Debugging"),
]


def test_magmaw_transfer_lane_authority_compiled_production_bridge_replay(
    tmp_path: Path, request,
) -> None:
    # pytest retains recent tmp_path trees by default. This compiled replay is
    # self-cleaning even on assertion or compiler failure so it cannot leave
    # duplicate native objects on the constrained validation host.
    request.addfinalizer(lambda: shutil.rmtree(tmp_path, ignore_errors=True))
    source = tmp_path / "magmaw_transfer_lane_authority.cpp"
    binary = tmp_path / "magmaw_transfer_lane_authority"
    source.write_text(r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cassert>
#include <optional>
#include <string>

using namespace BotEncounter;
using State = BotDecision::PersistentTaskState;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static MagmawTransferLaneTask RunningTask()
{
    MagmawTransferLaneTask task;
    task.Id.Episode.Lifecycle = { "cohort", 19, 3, 7, "magmaw", 669,
        31, "blackwing_descent.magmaw", 95, 8 };
    task.Id.Episode.EpisodeGeneration = 12;
    task.Id.Episode.MechanicGeneration = 11;
    task.Id.ActorGuid = PlayerGuid(30007);
    task.Id.TaskGeneration = 41;
    task.Destination = { -302.471405f, -31.8600292f, 210.098007f };
    task.State = State::Running;
    task.InitialDistance = 30.0f;
    task.BestDistance = 30.0f;
    task.LastDistance = 30.0f;
    task.StartedAtMs = 1000;
    task.LastProgressAtMs = 1000;
    task.LastObservedAtMs = 1000;
    task.ProgressRevision = 1;
    return task;
}

static BotNativeAction::Candidate TaskCandidate(
    MagmawTransferLaneTask const& task)
{
    BotDecision::BotIntentSink sink;
    EmitMagmawTransferLaneTaskIntent(task, sink);
    assert(sink.Proposals().size() == 1);
    return sink.Proposals().front();
}

static BotNativeAction::Candidate LegacyCandidate(
    MagmawTransferLaneTask const& task, uint64 generation)
{
    BotNativeAction::Candidate legacy = TaskCandidate(task);
    legacy.Id.EventGeneration = generation;
    return legacy;
}

static Blackboard Board(uint64 revision, uint64 observedAtMs)
{
    Blackboard board;
    board.Revision = revision;
    board.ObservedAtMs = observedAtMs;
    return board;
}

static MagmawTransferLaneActorObservation Actor(
    MagmawTransferLaneTask const& task, Vector3 position)
{
    MagmawTransferLaneActorObservation actor;
    actor.Guid = task.Id.ActorGuid;
    actor.Position = position;
    actor.PositionObserved = true;
    actor.Alive = true;
    return actor;
}

static BotWorldMovement::ExecutionObservation ProjectedExecution(
    MagmawTransferLaneTask const& task, uint64 receipt)
{
    BotWorldMovement::NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.EndpointResult = PathEndpointResult::ReachedProjectedEndPoly;
    proof.CorridorReachedEndPoly = true;
    proof.ResolvedEndpointAvailable = true;
    proof.ResolvedEndpointX = -305.600037f;
    proof.ResolvedEndpointY = -34.9334412f;
    proof.ResolvedEndpointZ = 210.687714f;
    proof.ActualEndpointMatchedResolved = true;
    proof.EndpointMatched = false;
    BotWorldMovement::ExecutionObservation execution =
        BotWorldMovement::BeginExecutionObservation(task.Destination.X,
            task.Destination.Y, task.Destination.Z, receipt);
    BotWorldMovement::ObserveExecutionProof(execution, proof);
    return execution;
}

static BotWorldMovement::ExecutionObservation RequestedExecution(
    MagmawTransferLaneTask const& task, uint64 receipt)
{
    BotWorldMovement::NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.EndpointResult = PathEndpointResult::ReachedRequested;
    proof.CorridorReachedEndPoly = true;
    proof.ResolvedEndpointAvailable = true;
    proof.ResolvedEndpointX = task.Destination.X;
    proof.ResolvedEndpointY = task.Destination.Y;
    proof.ResolvedEndpointZ = task.Destination.Z;
    proof.ActualEndpointMatchedResolved = true;
    proof.EndpointMatched = true;
    BotWorldMovement::ExecutionObservation execution =
        BotWorldMovement::BeginExecutionObservation(task.Destination.X,
            task.Destination.Y, task.Destination.Z, receipt);
    BotWorldMovement::ObserveExecutionProof(execution, proof);
    execution.Disposition = BotWorldMovement::ExecutionDisposition::Submitted;
    execution.PlannerAccepted = true;
    execution.NativeSubmitted = true;
    return execution;
}

int main()
{
    constexpr uint64 LegacyGeneration = 77;
    MagmawTransferLaneTask task = RunningTask();
    BotNativeAction::Candidate legacy = LegacyCandidate(task,
        LegacyGeneration);
    std::vector<MagmawTransferLaneTask> tasks{ task };

    // Default off is an exact legacy pass-through, while retaining a typed
    // task/candidate binding only after equivalence is proven.
    auto disabled = SelectMagmawTransferLaneAuthority(false, tasks,
        task.Id.ActorGuid, legacy, LegacyGeneration);
    assert(disabled.Movement);
    assert(disabled.Movement->Id.Key() == legacy.Id.Key());
    assert(disabled.Movement->Id.EventGeneration == LegacyGeneration);
    assert(disabled.Comparison.Outcome
        == MagmawTransferLaneIntentComparisonOutcome::Equivalent);
    assert(disabled.Binding);
    assert(disabled.Binding->Source
        == MagmawTransferLaneAuthoritySource::Legacy);
    assert(disabled.Binding->CandidateKey == legacy.Id.Key());
    assert(!disabled.TaskAuthoritySelected);

    auto enabled = SelectMagmawTransferLaneAuthority(true, tasks,
        task.Id.ActorGuid, legacy, LegacyGeneration);
    assert(enabled.Movement && enabled.Binding);
    assert(enabled.TaskAuthoritySelected);
    assert(enabled.Binding->Source
        == MagmawTransferLaneAuthoritySource::Task);
    assert(enabled.Movement->Id.EventGeneration == task.Id.TaskGeneration);
    std::string const stableTaskCandidateKey = enabled.Movement->Id.Key();
    assert(enabled.Binding->CandidateKey == stableTaskCandidateKey);

    // Collection authority replaces only the exact legacy transfer intent.
    // Unrelated safety and formation proposals remain byte-for-byte visible.
    BotNativeAction::Candidate safetyCandidate = legacy;
    safetyCandidate.Id.Mechanic = "pillar_evade";
    safetyCandidate.Id.EventGeneration = 900;
    safetyCandidate.Utility = 650.0f;
    BotNativeAction::Candidate formation = legacy;
    formation.Id.Mechanic = "ranged_formation_restore";
    formation.Id.EventGeneration = 901;
    formation.ActionPriority = BotActionArbitration::Priority::Mechanic;
    formation.Utility = 275.0f;
    MagmawMovementIntentCollection legacyMovements;
    legacyMovements.Propose(MagmawMovementProposalOrigin::Hazard,
        safetyCandidate);
    legacyMovements.Propose(MagmawMovementProposalOrigin::Hazard, legacy);
    legacyMovements.Propose(MagmawMovementProposalOrigin::FormationRestore,
        formation);
    auto collectionEnabled = SelectMagmawTransferLaneAuthority(true, tasks,
        task.Id.ActorGuid, legacyMovements, LegacyGeneration);
    assert(collectionEnabled.TaskAuthoritySelected);
    assert(collectionEnabled.Movements.Size() == 3);
    assert(collectionEnabled.Movements.Proposals()[0].Id.Key()
        == safetyCandidate.Id.Key());
    assert(collectionEnabled.Movements.Proposals()[1].Id.Key()
        == stableTaskCandidateKey);
    assert(collectionEnabled.Movements.Origin(1)
        == MagmawMovementProposalOrigin::TransferLaneTask);
    assert(collectionEnabled.Movements.Proposals()[2].Id.Key()
        == formation.Id.Key());

    // A safety winner preempts this tick without reconstructing the running
    // task. The same task/candidate identity is available on the next tick.
    BotActionArbitration::Kernel preemptionKernel;
    preemptionKernel.Begin(1050);
    for (BotNativeAction::Candidate const& candidate :
            collectionEnabled.Movements.Proposals())
    {
        BotActionArbitration::Candidate queued;
        queued.Key = candidate.Id.Key();
        queued.Source = candidate.Id.Mechanic;
        queued.ActionPriority = candidate.ActionPriority;
        queued.UtilityScore = candidate.Utility;
        queued.RequiredResources = candidate.Resources();
        queued.Attempt = []()
        {
            return BotActionArbitration::Outcome::Committed("submitted");
        };
        preemptionKernel.Submit(std::move(queued));
    }
    auto const& preemptionResolution = preemptionKernel.Resolve();
    assert(preemptionResolution.CommittedCandidates.size() == 1);
    assert(preemptionResolution.CommittedCandidates.front()
        == safetyCandidate.Id.Key());
    assert(collectionEnabled.Movements.Proposals()[1].Id.Key()
        == stableTaskCandidateKey);
    auto resumedSelection = SelectMagmawTransferLaneAuthority(true, tasks,
        task.Id.ActorGuid, legacyMovements, LegacyGeneration);
    assert(resumedSelection.TaskAuthoritySelected);
    assert(resumedSelection.Movements.Proposals()[1].Id.Key()
        == stableTaskCandidateKey);

    // The production bridge fails closed before kernel submission when any
    // exact correlation component is altered.
    MagmawTransferLaneExecutionBinding wrongCandidate = *enabled.Binding;
    wrongCandidate.CandidateKey += ":wrong";
    BotActionArbitration::Kernel invalidKernel;
    invalidKernel.Begin(1050);
    assert(!SubmitMagmawTransferLaneKernelCandidate(invalidKernel,
        *enabled.Movement, wrongCandidate, 1050,
        [](BotNativeAction::Intent const&,
            BotWorldMovement::ExecutionObservation&)
        {
            return BotActionArbitration::Outcome::NotApplicable();
        }, [](MagmawTransferLaneNativeOutcome const&) {}));

    // An enabled selector still preserves legacy on any mismatch.
    BotNativeAction::Candidate divergent = legacy;
    std::get<BotNativeAction::Move>(divergent.Action).X += 1.0f;
    auto rejectedCutover = SelectMagmawTransferLaneAuthority(true, tasks,
        task.Id.ActorGuid, divergent, LegacyGeneration);
    assert(rejectedCutover.Movement);
    assert(rejectedCutover.Movement->Id.Key() == divergent.Id.Key());
    assert(!rejectedCutover.TaskAuthoritySelected);
    assert(!rejectedCutover.Binding);

    // Exact live counterexample: Detour reached the projected end-poly point,
    // the actor matched that resolved point, but the logical request did not.
    BotWorldMovement::ExecutionObservation projected =
        ProjectedExecution(task, 636);

    // Cross the same production selector -> action kernel -> task-specific
    // native bridge used by SubmitAdaptiveKernelCandidates. The hermetic
    // boundary starts after map/MMAP PathGenerator has produced its typed
    // proof; that map-bound computation remains a live acceptance gate.
    BotActionArbitration::Kernel kernel;
    kernel.Begin(1100);
    bool executorCalled = false;
    std::optional<MagmawTransferLaneNativeOutcome> observed;
    assert(SubmitMagmawTransferLaneKernelCandidate(kernel,
        *enabled.Movement, *enabled.Binding, 1100,
        [&](BotNativeAction::Intent const& nativeIntent,
            BotWorldMovement::ExecutionObservation& execution)
        {
            executorCalled = true;
            BotNativeAction::Move const* move =
                std::get_if<BotNativeAction::Move>(&nativeIntent);
            assert(move);
            assert(move->IntentReason == "pillar_bait_switch");
            assert(move->DiagnosticCandidateKey
                == LegacyMagmawMovementDiagnosticCandidateKey(
                    *enabled.Movement));
            execution = projected;
            return BotActionArbitration::Outcome::Retryable(
                "route_destination_endpoint_mismatch");
        },
        [&](MagmawTransferLaneNativeOutcome const& outcome)
        {
            observed = outcome;
        }));
    BotActionArbitration::Resolution const& rejectedResolution =
        kernel.Resolve();
    assert(executorCalled);
    assert(!rejectedResolution.AnyCommitted);
    assert(observed);
    assert(observed->Binding.CandidateKey == stableTaskCandidateKey);
    assert(observed->Binding.Actor == task.Id.ActorGuid);
    assert(observed->Binding.ScopeKey == task.Id.Episode.Lifecycle.Key());
    assert(observed->Movement.Disposition
        == BotWorldMovement::ExecutionDisposition::Rejected);
    assert(!observed->Movement.NativeSubmitted);

    MagmawTransferLaneActorObservation actor = Actor(task,
        { -326.0f, -48.0f, 210.1f });
    task.BestDistance = 20.0f;
    actor.NativeOutcome = observed;
    Blackboard tick1 = Board(2, 1100);
    MagmawTransferLaneTaskRunner::Observe(task, actor, tick1);
    assert(task.State == State::Running);
    assert(task.NativeDisposition == MagmawTransferLaneNativeDisposition::
        ReachedProjectedEndPolyEvidence);
    assert(task.ProjectedEndpointEvidenceSamples == 1);
    assert(task.ProgressSamples == 0);
    assert(task.LastProgressAtMs == 1000);
    assert(task.Destination.X == -302.471405f);

    // Re-observing one native receipt cannot manufacture extra progress.
    Blackboard duplicate = Board(3, 1150);
    MagmawTransferLaneTaskRunner::Observe(task, actor, duplicate);
    assert(task.ProjectedEndpointEvidenceSamples == 1);
    assert(task.NativeOutcomeSamples == 1);

    // A selected native attempt starts from a fresh Unavailable observation.
    // Simulate ExecuteNativeActionIntent rejecting before ExecuteMovementIntent:
    // the prior projected receipt must not be rebound at the new timestamp.
    BotWorldMovement::ExecutionObservation simulatedState = projected;
    std::optional<MagmawTransferLaneNativeOutcome> earlyRejected;
    BotActionArbitration::Kernel earlyKernel;
    earlyKernel.Begin(1200);
    assert(SubmitMagmawTransferLaneKernelCandidate(earlyKernel,
        *enabled.Movement, *enabled.Binding, 1200,
        [&](BotNativeAction::Intent const&,
            BotWorldMovement::ExecutionObservation& execution)
        {
            assert(!execution.Available);
            assert(execution.Disposition
                == BotWorldMovement::ExecutionDisposition::Unavailable);
            assert(execution.ReceiptId == 0);
            assert(execution.RequestedX == task.Destination.X);
            assert(execution.RequestedY == task.Destination.Y);
            assert(execution.RequestedZ == task.Destination.Z);
            simulatedState = execution;
            execution = simulatedState;
            return BotActionArbitration::Outcome::Retryable(
                "native_intent_bot_unavailable");
        }, [&](MagmawTransferLaneNativeOutcome const& outcome)
        {
            earlyRejected = outcome;
        }));
    assert(!earlyKernel.Resolve().AnyCommitted);
    assert(earlyRejected);
    assert(!earlyRejected->Movement.Available);
    assert(earlyRejected->Movement.EndpointResult
        == PathEndpointResult::Unavailable);
    actor.NativeOutcome = earlyRejected;
    MagmawTransferLaneTaskRunner::Observe(task, actor, Board(4, 1200));
    assert(task.NativeOutcomeSamples == 1);
    assert(task.ProjectedEndpointEvidenceSamples == 1);
    assert(task.LastNativeReceiptId == 636);
    actor.NativeOutcome.reset();

    // The real kernel gives a stronger safety candidate the movement lane;
    // the task bridge remains unexecuted on that tick.
    kernel.Begin(1400);
    bool preemptedExecutorCalled = false;
    assert(SubmitMagmawTransferLaneKernelCandidate(kernel,
        *enabled.Movement, *enabled.Binding, 1400,
        [&](BotNativeAction::Intent const&,
            BotWorldMovement::ExecutionObservation& execution)
        {
            preemptedExecutorCalled = true;
            execution = RequestedExecution(task, 637);
            return BotActionArbitration::Outcome::Submitted("unexpected");
        }, [](MagmawTransferLaneNativeOutcome const&) {}));
    kernel.Submit(BotActionArbitration::Candidate{
        "magmaw_immediate_safety", "adaptive_magmaw",
        BotActionArbitration::Priority::Survival, 1000.0f, 0.0f, 0.0f,
        BotActionArbitration::Uses(BotActionArbitration::Resource::Movement),
        0, 100, 300, 2, true, "", []
        {
            return BotActionArbitration::Outcome::Submitted(
                "immediate_safety_movement_submitted");
        }});
    BotActionArbitration::Resolution const& safetyResolution =
        kernel.Resolve();
    assert(safetyResolution.AnyCommitted);
    assert(!preemptedExecutorCalled);

    // The corresponding observed lease suspends the same task without
    // changing its identity or destination.
    BotMovementArbitration::Lease safety;
    safety.MovementOwner = BotMovementArbitration::Owner::Hazard;
    safety.MovementPriority = BotMovementArbitration::Priority::Hazard;
    safety.ExpiresAtMs = 1800;
    safety.MovementScope = MagmawTransferLaneMovementScope(
        task.Id.Episode.Lifecycle);
    safety.X = -290.0f;
    safety.Y = -10.0f;
    safety.Z = task.Destination.Z;
    actor.Movement.CurrentLease = safety;
    actor.NativeOutcome.reset();
    Blackboard preempted = Board(4, 1400);
    MagmawTransferLaneTaskRunner::Observe(task, actor, preempted);
    assert(task.State == State::Suspended);
    assert(task.Suspension
        == BotDecision::PersistentTaskSuspension::SafetyPreempted);
    BotDecision::BotIntentSink suspendedSink;
    EmitMagmawTransferLaneTaskIntent(task, suspendedSink);
    assert(suspendedSink.Proposals().empty());

    // Once safety clears, the same task and immutable destination resume.
    actor.Movement.CurrentLease.reset();
    actor.Position = { -315.0f, -40.0f, 210.1f };
    Blackboard resumed = Board(5, 1500);
    MagmawTransferLaneTaskRunner::Observe(task, actor, resumed);
    assert(task.State == State::Running);
    assert(task.Id.TaskGeneration == 41);
    BotNativeAction::Candidate resumedCandidate = TaskCandidate(task);
    assert(resumedCandidate.Id.Key() == stableTaskCandidateKey);
    auto const& resumedMove = std::get<BotNativeAction::Move>(
        resumedCandidate.Action);
    assert(resumedMove.X == task.Destination.X
        && resumedMove.Y == task.Destination.Y
        && resumedMove.Z == task.Destination.Z);

    // The bridge now observes a real submitted native-attempt record. Native
    // endpoint evidence alone still never completes the semantic task.
    BotWorldMovement::ExecutionObservation exact =
        RequestedExecution(task, 637);
    kernel.Begin(1600);
    observed.reset();
    assert(SubmitMagmawTransferLaneKernelCandidate(kernel,
        *enabled.Movement, *enabled.Binding, 1600,
        [&](BotNativeAction::Intent const&,
            BotWorldMovement::ExecutionObservation& execution)
        {
            execution = exact;
            return BotActionArbitration::Outcome::Submitted(
                "native_movement_submitted");
        }, [&](MagmawTransferLaneNativeOutcome const& outcome)
        {
            observed = outcome;
        }));
    assert(kernel.Resolve().AnyCommitted);
    assert(observed && observed->Movement.PlannerAccepted);
    assert(observed->Movement.NativeSubmitted);
    actor.NativeOutcome = observed;
    Blackboard tick4 = Board(6, 1600);
    MagmawTransferLaneTaskRunner::Observe(task, actor, tick4);
    assert(task.State == State::Running);
    assert(task.NativeDisposition == MagmawTransferLaneNativeDisposition::
        ReachedRequestedEndpointEvidence);

    // Same X/Y on a different floor is not logical lane arrival. Bots follow
    // terrain; this is completion proof, not a vertical movement command.
    actor.Position = { task.Destination.X + 1.0f,
        task.Destination.Y, task.Destination.Z + 8.0f };
    actor.NativeOutcome.reset();
    float const bestBeforeWrongFloor = task.BestDistance;
    uint64 const progressAtBeforeWrongFloor = task.LastProgressAtMs;
    uint32 const progressSamplesBeforeWrongFloor = task.ProgressSamples;
    Blackboard wrongFloor = Board(7, 1700);
    MagmawTransferLaneTaskRunner::Observe(task, actor, wrongFloor);
    assert(task.State == State::Running);
    assert(task.BestDistance == bestBeforeWrongFloor);
    assert(task.LastProgressAtMs == progressAtBeforeWrongFloor);
    assert(task.ProgressSamples == progressSamplesBeforeWrongFloor);

    // Only observed floor-aware logical arrival completes the task.
    actor.Position.Z = task.Destination.Z + 0.25f;
    Blackboard arrived = Board(8, 1800);
    MagmawTransferLaneTaskRunner::Observe(task, actor, arrived);
    assert(task.State == State::Succeeded);

    // Wrong-floor proximity cannot refresh the no-progress deadline. The
    // original task deadline remains authoritative across multiple ticks.
    MagmawTransferLaneTask floorDeadlineTask = RunningTask();
    MagmawTransferLaneActorObservation floorDeadlineActor = Actor(
        floorDeadlineTask,
        { floorDeadlineTask.Destination.X + 1.0f,
          floorDeadlineTask.Destination.Y,
          floorDeadlineTask.Destination.Z + 8.0f });
    MagmawTransferLaneTaskRunner::Observe(floorDeadlineTask,
        floorDeadlineActor, Board(11, 1100));
    assert(floorDeadlineTask.State == State::Running);
    assert(floorDeadlineTask.BestDistance == 30.0f);
    assert(floorDeadlineTask.LastDistance == 30.0f);
    assert(floorDeadlineTask.LastProgressAtMs == 1000);
    assert(floorDeadlineTask.ProgressSamples == 0);
    MagmawTransferLaneTaskRunner::Observe(floorDeadlineTask,
        floorDeadlineActor, Board(12, 3000));
    assert(floorDeadlineTask.State == State::Running);
    assert(floorDeadlineTask.LastProgressAtMs == 1000);
    MagmawTransferLaneTaskRunner::Observe(floorDeadlineTask,
        floorDeadlineActor, Board(13, 6000));
    assert(floorDeadlineTask.State == State::Failed);
    assert(floorDeadlineTask.Failure
        == MagmawTransferLaneFailure::NoSemanticProgress);
    assert(floorDeadlineTask.LastProgressAtMs == 1000);
    assert(floorDeadlineTask.ProgressSamples == 0);

    // A nearby same-floor observation remains valid semantic progress, and
    // subsequent correct-floor logical arrival succeeds.
    MagmawTransferLaneTask sameFloorTask = RunningTask();
    MagmawTransferLaneActorObservation sameFloorActor = Actor(sameFloorTask,
        { sameFloorTask.Destination.X + 20.0f,
          sameFloorTask.Destination.Y, sameFloorTask.Destination.Z });
    MagmawTransferLaneTaskRunner::Observe(sameFloorTask, sameFloorActor,
        Board(14, 1100));
    assert(sameFloorTask.State == State::Running);
    assert(sameFloorTask.BestDistance == 20.0f);
    assert(sameFloorTask.LastProgressAtMs == 1100);
    assert(sameFloorTask.ProgressSamples == 1);
    sameFloorActor.Position.X = sameFloorTask.Destination.X + 1.0f;
    sameFloorActor.Position.Z = sameFloorTask.Destination.Z + 0.25f;
    MagmawTransferLaneTaskRunner::Observe(sameFloorTask, sameFloorActor,
        Board(15, 1200));
    assert(sameFloorTask.State == State::Succeeded);

    // A wrong actor binding is ignored rather than contaminating another task.
    MagmawTransferLaneTask other = RunningTask();
    MagmawTransferLaneExecutionBinding wrong = *enabled.Binding;
    wrong.Actor = PlayerGuid(30008);
    MagmawTransferLaneActorObservation otherActor = Actor(other,
        { -326.0f, -48.0f, 210.1f });
    otherActor.NativeOutcome = BindMagmawTransferLaneNativeOutcome(
        wrong, projected, 1600);
    Blackboard mismatch = Board(9, 1900);
    MagmawTransferLaneTaskRunner::Observe(other, otherActor, mismatch);
    assert(other.NativeDisposition
        == MagmawTransferLaneNativeDisposition::None);
    assert(other.NativeOutcomeSamples == 0);

    MagmawTransferLaneTask wrongEpisodeTask = RunningTask();
    MagmawTransferLaneExecutionBinding wrongEpisode = *enabled.Binding;
    ++wrongEpisode.EpisodeGeneration;
    MagmawTransferLaneActorObservation wrongEpisodeActor = Actor(
        wrongEpisodeTask, { -326.0f, -48.0f, 210.1f });
    wrongEpisodeActor.NativeOutcome = BindMagmawTransferLaneNativeOutcome(
        wrongEpisode, exact, 1950);
    MagmawTransferLaneTaskRunner::Observe(wrongEpisodeTask,
        wrongEpisodeActor, Board(10, 1950));
    assert(wrongEpisodeTask.NativeDisposition
        == MagmawTransferLaneNativeDisposition::None);
    assert(wrongEpisodeTask.NativeOutcomeSamples == 0);
}
''')
    command = [
        "g++", "-std=c++20", *INCLUDES, str(source),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneAuthority.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneIntent.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneTaskRunner.cpp"),
        str(ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneMovementObservation.cpp"),
        str(ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecution.cpp"),
        "-o", str(binary),
    ]
    subprocess.run(command, check=True, cwd=ROOT)
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_magmaw_transfer_lane_authority_production_wiring() -> None:
    encounter = ROOT / (
        "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
    )
    config = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.h").read_text()
    loader = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.cpp").read_text()
    preparation = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
    ).read_text()
    candidates = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text()
    executor = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecutor.cpp"
    ).read_text()
    conf = (ROOT / "src/server/worldserver/worldserver.conf.dist").read_text()
    cmake = (ROOT / "src/server/game/CMakeLists.txt").read_text()

    assert "bool MagmawTransferLaneTaskAuthority = false;" in config
    assert '"BotWorld.Magmaw.TransferLaneTaskAuthority"' in loader
    assert "BotWorld.Magmaw.TransferLaneTaskAuthority = 0" in conf
    assert "SelectMagmawTransferLaneAuthority(" in preparation
    assert "MagmawTransferLaneTaskAuthority" in preparation
    assert "SubmitMagmawTransferLaneKernelCandidate(" in candidates
    assert "ExecuteNativeActionIntent(" in candidates
    assert "context.State.LastMovementExecution" in candidates
    assert "MovementPlannerDiagnostics().Latest" not in candidates
    assert "state.LastMovementExecution = plan.Execution;" in executor
    assert "BotMagmawTransferLaneTaskRunner.cpp" in cmake
    assert "BotMagmawTransferLaneAuthority.cpp" in cmake
    assert "BotMagmawTransferLaneKernelBridge.cpp" in cmake
    assert "BotWorldPopulationMgrMovementExecution.cpp" in cmake

    strategy = encounter / "BotAdaptiveMagmawStrategy.h"
    assert len(strategy.read_text().splitlines()) < 1000
    for path in list(encounter.glob("*.h")) + list(encounter.glob("*.cpp")):
        assert len(path.read_text().splitlines()) < 1000, path

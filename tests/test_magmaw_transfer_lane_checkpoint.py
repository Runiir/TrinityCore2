import json
import hashlib
from pathlib import Path
import shutil
import subprocess


ROOT = Path(__file__).resolve().parents[1]
MAGMAW = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw"
)


def test_compiled_seal_selector_kernel_receipt_and_task_terminal(
    tmp_path: Path, request,
) -> None:
    request.addfinalizer(lambda: shutil.rmtree(tmp_path, ignore_errors=True))
    source = tmp_path / "magmaw_transfer_lane_checkpoint.cpp"
    binary = tmp_path / "magmaw_transfer_lane_checkpoint"
    source.write_text(
        r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneCheckpoint.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneKernelBridge.h"
#include "Bots/BotChainwielderOwnerCheckpoint.h"
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"

#include <cassert>
#include <cmath>
#include <optional>
#include <string>
#include <utility>

using namespace BotEncounter;
namespace Checkpoint = BotEncounter::MagmawTransferLaneCheckpoint;

std::string ObjectGuid::ToString() const
{
    return std::to_string(GetRawValue());
}

static ObjectGuid PlayerGuid(uint32 counter)
{
    return ObjectGuid(HighGuid::Player, counter);
}

static Checkpoint::AdmissionInput Admission(bool authority = false)
{
    static std::string const seal(64, 'a');
    static std::string const source(40, 'b');
    static std::string const revision(10, 'b');
    return { true, true, authority, Checkpoint::FixtureId,
        Checkpoint::Cases[0].Id, seal, source,
        Checkpoint::Cases[0].Id, seal, source, revision };
}

static MagmawTransferLaneTask Task()
{
    Scope scope{ "cohort", 9, 2, 5, "bwd.entry.regroup", 669, 31,
        "magmaw_transfer_lane_checkpoint" };
    return Checkpoint::BuildTask(Checkpoint::Cases[0], scope,
        PlayerGuid(Checkpoint::ActorGuid), 1000, 6.0f);
}

static BotWorldMovement::ExecutionObservation Submitted(
    MagmawTransferLaneTask const& task, uint64 receipt)
{
    BotWorldMovement::ExecutionObservation movement;
    movement.Available = true;
    movement.Disposition = BotWorldMovement::ExecutionDisposition::Submitted;
    movement.ReceiptId = receipt;
    movement.RequestedX = task.Destination.X;
    movement.RequestedY = task.Destination.Y;
    movement.RequestedZ = task.Destination.Z;
    movement.PlannerAccepted = true;
    movement.NativeSubmitted = true;
    return movement;
}

static BotWorldMovement::MovementPlannerObservation Planner(
    MagmawTransferLaneTask const& task,
    MagmawTransferLaneExecutionBinding const& binding, uint64 receipt)
{
    BotWorldMovement::MovementPlannerObservation planner;
    planner.Available = true;
    planner.BotGuid = Checkpoint::ActorGuid;
    planner.RequestedMapId = 669;
    planner.RequestedX = task.Destination.X;
    planner.RequestedY = task.Destination.Y;
    planner.RequestedZ = task.Destination.Z;
    planner.MovementOwner = BotMovementArbitration::Owner::Hazard;
    planner.IntentReason = "pillar_bait_switch";
    planner.PlannerResult = "accepted";
    planner.Result = "submitted";
    planner.PrimaryPathDisposition =
        BotWorldMovement::PrimaryDisposition::CompleteTerminal;
    BotWorldMovement::NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1;
    proof.Complete = true;
    proof.EndpointResult = PathEndpointResult::ReachedRequested;
    proof.CorridorReachedEndPoly = true;
    proof.ResolvedEndpointAvailable = true;
    proof.ResolvedEndpointX = task.Destination.X;
    proof.ResolvedEndpointY = task.Destination.Y;
    proof.ResolvedEndpointZ = task.Destination.Z;
    proof.EndpointX = task.Destination.X;
    proof.EndpointY = task.Destination.Y;
    proof.EndpointZ = 193.098587f;
    proof.EndpointHorizontalDistance = 0.0f;
    proof.EndpointVerticalDistance = std::fabs(
        proof.EndpointZ - task.Destination.Z);
    proof.EndpointDistance = proof.EndpointVerticalDistance;
    proof.ResolvedEndpointHorizontalDistance =
        proof.EndpointHorizontalDistance;
    proof.ResolvedEndpointVerticalDistance = proof.EndpointVerticalDistance;
    proof.ActualEndpointMatchedResolved =
        BotWorldMovement::NativePathEndpointComponentsMatch(
            proof.EndpointHorizontalDistance,
            proof.EndpointVerticalDistance);
    proof.EndpointMatched = proof.ActualEndpointMatchedResolved;
    proof.EndpointFloorValid = true;
    proof.Accepted = BotWorldMovement::NativePathProofPassesAdmission(proof);
    planner.PrimaryNativeProof = proof;
    planner.LaunchReceipt.Id = receipt;
    planner.LaunchReceipt.DiagnosticCandidateKey = binding.CandidateKey;
    planner.LaunchReceipt.Scope = MagmawTransferLaneMovementScope(
        task.Id.Episode.Lifecycle);
    planner.LaunchReceipt.PrimaryPathDisposition =
        BotWorldMovement::PrimaryDisposition::CompleteTerminal;
    planner.LaunchReceipt.PrimaryNativeProof = planner.PrimaryNativeProof;
    planner.LaunchReceipt.PlannerControls.Available = true;
    planner.LaunchReceipt.PlannerControls.CoordinateSpace = "world";
    planner.LaunchReceipt.PlannerControls.ControlCount = 2;
    planner.LaunchReceipt.PlannerSelectedEndpointAvailable = true;
    planner.LaunchReceipt.PlannerSelectedX = task.Destination.X;
    planner.LaunchReceipt.PlannerSelectedY = task.Destination.Y;
    planner.LaunchReceipt.PlannerSelectedZ = proof.EndpointZ;
    planner.LaunchReceipt.ExecutorDestinationAvailable = true;
    planner.LaunchReceipt.ExecutorSelectedX = task.Destination.X;
    planner.LaunchReceipt.ExecutorSelectedY = task.Destination.Y;
    planner.LaunchReceipt.ExecutorSelectedZ = task.Destination.Z;
    planner.LaunchReceipt.PointGeneratePath = true;
    planner.LaunchReceipt.ProgressCaptureEnabled = true;
    planner.LaunchReceipt.MotionMasterSubmissionObserved = true;
    planner.LaunchReceipt.MotionMasterSlot = 1;
    planner.LaunchReceipt.MotionMasterGeneratorType = 8;
    planner.LaunchReceipt.PointGeneratorInitialized = true;
    BotWorldMovement::NativeSplineLaunchObservation launch;
    launch.LaunchAttempted = true;
    launch.LaunchSucceeded = true;
    launch.SplineInitialized = true;
    launch.SplineId = 28;
    planner.LaunchReceipt.Launches.push_back(launch);
    return planner;
}

static BotWorldMovement::NativeMovementProgressSample Sample(
    uint64 receipt, uint64 time, float y, float distance,
    bool terminal = false)
{
    BotWorldMovement::NativeMovementProgressSample sample;
    sample.ReceiptId = receipt;
        sample.ObservedAtMs = time;
    sample.ActorAvailable = true;
    sample.ActorInWorld = true;
    sample.ActorAlive = true;
    sample.MapId = 669;
    sample.InstanceId = 31;
    sample.X = Checkpoint::Cases[0].DestinationX;
    sample.Y = y;
    sample.Z = Checkpoint::Cases[0].DestinationZ;
    sample.FloorSampled = true;
    sample.FloorValid = true;
    sample.FloorZ = Checkpoint::Cases[0].DestinationZ;
    sample.ActorFloorDelta = 0.0f;
    sample.SelectedPlatformCompatible = true;
    sample.PointGeneratorActive = !terminal;
    sample.SplineInitialized = true;
    sample.SplineId = 28;
    sample.MatchesLaunchedSpline = true;
    sample.SplineFinalized = terminal;
    sample.EndpointDistance = distance;
    sample.EndpointHorizontalDistance = distance;
    sample.EndpointProgressed = true;
    sample.EndpointReached = terminal;
    sample.Terminal = terminal;
    sample.Outcome = terminal ? "selected_endpoint_reached"
        : "native_motion_in_progress";
    return sample;
}

int main()
{
    static_assert(Checkpoint::Cases.size() == 1);
    assert(Checkpoint::FindCase("entrance_polygon_short_lane_v1"));
    assert(!Checkpoint::FindCase("arbitrary_coordinates"));
    assert(Checkpoint::AdmissionMatches(Admission()));
    assert(!Checkpoint::AdmissionMatches(Admission(true)));
    Checkpoint::AdmissionInput badCase = Admission();
    badCase.RequestedCaseId = "arbitrary_coordinates";
    assert(!Checkpoint::AdmissionMatches(badCase));

    Checkpoint::State publication;
    assert(Checkpoint::ObserveProgressPublication(publication, false)
        == Checkpoint::ProgressPublicationDecision::Await);
    assert(publication.ProgressPublicationAwaitTicks == 1);
    assert(Checkpoint::ObserveProgressPublication(publication, true)
        == Checkpoint::ProgressPublicationDecision::Ready);
    publication.ProgressPublicationAwaitTicks =
        Checkpoint::MaximumProgressPublicationTicks;
    assert(Checkpoint::ObserveProgressPublication(publication, false)
        == Checkpoint::ProgressPublicationDecision::TimedOut);

    MagmawTransferLaneTask task = Task();
    BotNativeAction::Candidate legacy =
        Checkpoint::BuildLegacyCandidate(task);
    assert(legacy.Id.Strategy == "adaptive_magmaw");
    assert(legacy.Id.Mechanic == "pillar_bait_switch");
    assert(legacy.Id.Actor == PlayerGuid(Checkpoint::ActorGuid));
    assert(legacy.Id.EventGeneration
        == Checkpoint::LegacyTransitionGeneration);
    assert(legacy.Resources() == BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement));

    std::vector<MagmawTransferLaneTask> tasks{ task };
    auto selection = SelectMagmawTransferLaneAuthority(false, tasks,
        task.Id.ActorGuid, legacy, Checkpoint::LegacyTransitionGeneration);
    assert(Checkpoint::ExactAuthorityOffSelection(selection, legacy, task));
    assert(selection.Binding);
    assert(selection.Binding->Source
        == MagmawTransferLaneAuthoritySource::Legacy);
    auto forbidden = SelectMagmawTransferLaneAuthority(true, tasks,
        task.Id.ActorGuid, legacy, Checkpoint::LegacyTransitionGeneration);
    assert(!Checkpoint::ExactAuthorityOffSelection(forbidden, legacy, task));
    BotNativeAction::Candidate divergent = legacy;
    std::get<BotNativeAction::Move>(divergent.Action).X += 2.0f;
    auto divergence = SelectMagmawTransferLaneAuthority(false, tasks,
        task.Id.ActorGuid, divergent,
        Checkpoint::LegacyTransitionGeneration);
    assert(!Checkpoint::ExactAuthorityOffSelection(divergence, divergent,
        task));

    Checkpoint::State ownedCandidate;
    assert(ownedCandidate.Arm(Checkpoint::Cases[0].Id,
        Checkpoint::ActorGuid, 9));
    ownedCandidate.CurrentStage = Checkpoint::Stage::Queued;
    ownedCandidate.QueueCount = 1;
    ownedCandidate.Actor = Checkpoint::ActorGuid;
    ownedCandidate.CandidateKey = selection.Binding->CandidateKey;
    ownedCandidate.Binding = selection.Binding;
    assert(Checkpoint::OwnsQueuedKernelCandidate(ownedCandidate,
        selection.Binding->CandidateKey, Checkpoint::ActorGuid));
    assert(!Checkpoint::OwnsQueuedKernelCandidate(ownedCandidate,
        selection.Binding->CandidateKey + ":ordinary",
        Checkpoint::ActorGuid));
    assert(!Checkpoint::OwnsQueuedKernelCandidate(ownedCandidate,
        selection.Binding->CandidateKey, Checkpoint::ActorGuid + 1));

    BotControllerRouteHold::Identity holdIdentity;
    holdIdentity.CohortId = "cohort";
    holdIdentity.ServerEpoch = 8;
    holdIdentity.AttemptId = 9;
    holdIdentity.ScenarioId = "sealed_fixture";
    holdIdentity.RuntimeProfile = "checkpoint";
    holdIdentity.RouteManifestSha256 = std::string(64, 'c');
    holdIdentity.RouteGeneration = 5;
    holdIdentity.RouteNodeId = "bwd.entry.regroup";
    holdIdentity.ActorGuid = Checkpoint::ActorGuid;
    holdIdentity.FixtureId = Checkpoint::FixtureId;
    holdIdentity.SealSha256 = std::string(64, 'a');
    holdIdentity.SourceCommit = std::string(40, 'b');
    BotControllerRouteHold::State hold;
    assert(hold.BeginAcquire(holdIdentity, 900).Accepted);
    assert(hold.CompleteAcquire(holdIdentity, 910).Accepted);
    assert(hold.AcknowledgeArm(holdIdentity, 920).Accepted);

    BotActionArbitration::Kernel admittedKernel;
    admittedKernel.Begin(1000);
    uint32 admittedAttempts = 0;
    uint32 ordinaryAttempts = 0;
    assert(SubmitMagmawTransferLaneKernelCandidate(admittedKernel,
        *selection.Movement, *selection.Binding, 1000,
        [&](BotNativeAction::Intent const&,
            BotWorldMovement::ExecutionObservation& movement)
        {
            ++admittedAttempts;
            movement = Submitted(task, 90);
            return BotActionArbitration::Outcome::Submitted("submitted");
        }, [](MagmawTransferLaneNativeOutcome const&) {},
        "validation_route_adapter"));
    assert(BotControllerRouteHold::MarkCheckpointObservationCandidate(
        admittedKernel, selection.Binding->CandidateKey, hold,
        Checkpoint::ActorGuid));
    BotActionArbitration::Candidate ordinary;
    ordinary.Key = selection.Binding->CandidateKey + ":ordinary";
    ordinary.Source = "adaptive_magmaw";
    ordinary.ActionPriority = BotActionArbitration::Priority::Survival;
    ordinary.RequiredResources = BotActionArbitration::Uses(
        BotActionArbitration::Resource::Movement);
    ordinary.Attempt = [&ordinaryAttempts]()
    {
        ++ordinaryAttempts;
        return BotActionArbitration::Outcome::Submitted("ordinary");
    };
    assert(admittedKernel.Submit(std::move(ordinary)));
    BotControllerRouteHold::InstallAdmissionPolicy(admittedKernel, hold,
        holdIdentity, Checkpoint::ActorGuid);
    admittedKernel.Resolve();
    assert(admittedAttempts == 1);
    assert(ordinaryAttempts == 0);
    assert(hold.SuppressedRouteActionCount == 1);

    BotActionArbitration::Kernel kernel;
    kernel.Begin(1000);
    uint32 attempts = 0;
    std::optional<MagmawTransferLaneNativeOutcome> native;
    assert(SubmitMagmawTransferLaneKernelCandidate(kernel,
        *selection.Movement, *selection.Binding, 1000,
        [&](BotNativeAction::Intent const& intent,
            BotWorldMovement::ExecutionObservation& movement)
        {
            ++attempts;
            BotNativeAction::Move const& move =
                std::get<BotNativeAction::Move>(intent);
            assert(move.DiagnosticCandidateKey
                == selection.Binding->CandidateKey);
            movement = Submitted(task, 1);
            return BotActionArbitration::Outcome::Submitted("submitted");
        }, [&](MagmawTransferLaneNativeOutcome const& outcome)
        {
            native = outcome;
        }));
    kernel.Resolve();
    assert(attempts == 1 && native);
    assert(native->Binding.ScopeKey == task.Id.Episode.Lifecycle.Key());
    assert(native->Binding.EpisodeGeneration
        == Checkpoint::EpisodeGeneration);
    assert(native->Binding.TaskGeneration == Checkpoint::TaskGeneration);
    assert(native->Binding.LegacyTransitionGeneration
        == Checkpoint::LegacyTransitionGeneration);

    Checkpoint::PlannerReceiptSnapshot receipt;
    auto planner = Planner(task, *selection.Binding, 1);
    assert(Checkpoint::CaptureExactPlannerReceipt(receipt, planner,
        *selection.Binding, task));
    assert(receipt.ReceiptId == 1 && receipt.SplineId == 28);
    auto wrongReceipt = planner;
    wrongReceipt.LaunchReceipt.Id = 92;
    wrongReceipt.LaunchReceipt.DiagnosticCandidateKey = "other";
    Checkpoint::PlannerReceiptSnapshot rejectedReceipt;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        wrongReceipt, *selection.Binding, task));
    auto driftedDestination = planner;
    driftedDestination.RequestedY += 0.01f;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        driftedDestination, *selection.Binding, task));
    auto missingMmap = planner;
    missingMmap.PrimaryNativeProof.Calculated = false;
    missingMmap.LaunchReceipt.PrimaryNativeProof.Calculated = false;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        missingMmap, *selection.Binding, task));

    auto unacceptedProof = planner;
    unacceptedProof.PrimaryNativeProof.Accepted = false;
    unacceptedProof.LaunchReceipt.PrimaryNativeProof.Accepted = false;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        unacceptedProof, *selection.Binding, task));

    auto nonmatchingProof = planner;
    nonmatchingProof.PrimaryNativeProof.EndpointMatched = false;
    nonmatchingProof.PrimaryNativeProof.Accepted = false;
    nonmatchingProof.LaunchReceipt.PrimaryNativeProof.EndpointMatched = false;
    nonmatchingProof.LaunchReceipt.PrimaryNativeProof.Accepted = false;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        nonmatchingProof, *selection.Binding, task));

    auto wrongFloorReceipt = planner;
    wrongFloorReceipt.PrimaryNativeProof.EndpointFloorValid = false;
    wrongFloorReceipt.PrimaryNativeProof.Accepted = false;
    wrongFloorReceipt.LaunchReceipt.PrimaryNativeProof.EndpointFloorValid =
        false;
    wrongFloorReceipt.LaunchReceipt.PrimaryNativeProof.Accepted = false;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        wrongFloorReceipt, *selection.Binding, task));

    auto excessiveZ = planner;
    excessiveZ.LaunchReceipt.PlannerSelectedZ = task.Destination.Z
        + BotWorldMovement::NativePathEndpointVerticalTolerance + 0.001f;
    excessiveZ.PrimaryNativeProof.EndpointZ =
        excessiveZ.LaunchReceipt.PlannerSelectedZ;
    excessiveZ.PrimaryNativeProof.EndpointVerticalDistance =
        BotWorldMovement::NativePathEndpointVerticalTolerance + 0.001f;
    excessiveZ.LaunchReceipt.PrimaryNativeProof =
        excessiveZ.PrimaryNativeProof;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        excessiveZ, *selection.Binding, task));

    auto horizontalDrift = planner;
    horizontalDrift.LaunchReceipt.PlannerSelectedX = task.Destination.X
        + BotWorldMovement::NativePathEndpointHorizontalTolerance + 0.001f;
    horizontalDrift.PrimaryNativeProof.EndpointX =
        horizontalDrift.LaunchReceipt.PlannerSelectedX;
    horizontalDrift.PrimaryNativeProof.EndpointHorizontalDistance =
        BotWorldMovement::NativePathEndpointHorizontalTolerance + 0.001f;
    horizontalDrift.LaunchReceipt.PrimaryNativeProof =
        horizontalDrift.PrimaryNativeProof;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        horizontalDrift, *selection.Binding, task));

    auto wrongActor = planner;
    wrongActor.BotGuid = Checkpoint::ActorGuid + 1;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        wrongActor, *selection.Binding, task));
    auto wrongMap = planner;
    wrongMap.RequestedMapId = Checkpoint::MapId + 1;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        wrongMap, *selection.Binding, task));
    auto wrongScope = planner;
    ++wrongScope.LaunchReceipt.Scope.RouteGeneration;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        wrongScope, *selection.Binding, task));
    auto wrongCandidate = planner;
    wrongCandidate.LaunchReceipt.DiagnosticCandidateKey += ":wrong";
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        wrongCandidate, *selection.Binding, task));
    auto missingReceiptIdentity = planner;
    missingReceiptIdentity.LaunchReceipt.Id = 0;
    assert(!Checkpoint::CaptureExactPlannerReceipt(rejectedReceipt,
        missingReceiptIdentity, *selection.Binding, task));

    Checkpoint::State state;
    assert(state.Arm(Checkpoint::Cases[0].Id, Checkpoint::ActorGuid, 9));
    state.CurrentStage = Checkpoint::Stage::NativeSubmitted;
    state.InstanceId = 31;
    state.Task = task;
    state.Binding = selection.Binding;
    state.NativeOutcome = native;
    state.PlannerReceipt = receipt;

    auto wrongFloor = Sample(1, 1100, -219.343994f, 1.0f);
    wrongFloor.Z = 210.0f;
    wrongFloor.FloorZ = 210.0f;
    wrongFloor.SelectedPlatformCompatible = false;
    uint32 beforeTaskProgress = state.Task.ProgressSamples;
    assert(Checkpoint::ConsumeProgressSample(state, wrongFloor));
    assert(state.WrongFloorSamples == 1);
    assert(state.Task.ProgressSamples == beforeTaskProgress);
    assert(state.LastSampleObservedAtMs == 1100);
    assert(state.LastProgressObservedAtMs == 0);
    assert(!state.NativeOutcomeConsumed);

    auto validProgress1 = Sample(1, 1200, -223.343994f, 5.0f);
    validProgress1.EndpointProgressed = false;
    assert(Checkpoint::ConsumeProgressSample(state, validProgress1));
    auto validProgress2 = Sample(1, 1300, -221.343994f, 3.0f);
    validProgress2.EndpointProgressed = false;
    assert(Checkpoint::ConsumeProgressSample(state, validProgress2));
    assert(state.DecreasingProgressSamples == 2);
    assert(state.CurrentStage == Checkpoint::Stage::Completed);
    assert(state.Task.State == BotDecision::PersistentTaskState::Succeeded);
    assert(!Sample(1, 1300, -221.343994f, 3.0f).Terminal);
    assert(state.CandidateAttemptCount == 0); // manager owns live counters.

    Checkpoint::State early;
    assert(early.Arm(Checkpoint::Cases[0].Id, Checkpoint::ActorGuid, 9));
    early.CurrentStage = Checkpoint::Stage::NativeSubmitted;
    early.InstanceId = 31;
    early.Task = Task();
    early.Binding = selection.Binding;
    early.NativeOutcome = native;
    early.PlannerReceipt = receipt;
    assert(Checkpoint::ConsumeProgressSample(early,
        Sample(1, 1200, -218.343994f, 0.0f, true)));
    assert(early.CurrentStage == Checkpoint::Stage::Failed);
    assert(early.Outcome
        == "magmaw_transfer_checkpoint_early_semantic_success");

    Checkpoint::State regression;
    assert(regression.Arm(Checkpoint::Cases[0].Id,
        Checkpoint::ActorGuid, 9));
    regression.CurrentStage = Checkpoint::Stage::NativeSubmitted;
    regression.InstanceId = 31;
    regression.Task = Task();
    regression.Binding = selection.Binding;
    regression.NativeOutcome = native;
    regression.PlannerReceipt = receipt;
    assert(Checkpoint::ConsumeProgressSample(regression,
        Sample(1, 1100, -228.343994f, 10.0f)));
    assert(regression.DecreasingProgressSamples == 0);
    assert(regression.LastProgressDistance == 6.0f);
    assert(Checkpoint::ConsumeProgressSample(regression,
        Sample(1, 1200, -221.343994f, 3.0f)));
    assert(regression.DecreasingProgressSamples == 1);
    assert(regression.CurrentStage == Checkpoint::Stage::Failed);
    assert(regression.Outcome
        == "magmaw_transfer_checkpoint_early_semantic_success");
}
''',
        encoding="utf-8",
    )
    subprocess.run(
        [
            "c++", "-std=c++17", "-Wall", "-Wextra", "-Werror",
            "-I", str(ROOT / "src/server/game"),
            "-I", str(ROOT / "src/server/game/Entities/Object"),
            "-I", str(ROOT / "src/common"),
            "-I", str(ROOT / "src/common/Utilities"),
            "-I", str(ROOT / "dep/g3dlite/include"),
            str(source),
            str(MAGMAW / "BotMagmawTransferLaneCheckpoint.cpp"),
            str(MAGMAW / "BotMagmawTransferLaneAuthority.cpp"),
            str(MAGMAW / "BotMagmawTransferLaneKernelBridge.cpp"),
            str(MAGMAW / "BotMagmawTransferLaneIntent.cpp"),
            str(MAGMAW / "BotMagmawTransferLaneTaskRunner.cpp"),
            str(MAGMAW / "BotMagmawTransferLaneMovementObservation.cpp"),
            str(ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecution.cpp"),
            "-o", str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_production_wiring_is_after_kernel_begin_and_has_no_coordinate_args() -> None:
    preparation = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelPreparation.cpp"
    ).read_text(encoding="utf-8")
    manager = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrMagmawTransferLaneCheckpoint.cpp"
    ).read_text(encoding="utf-8")
    candidates = (
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
    ).read_text(encoding="utf-8")
    command = (
        ROOT / "src/server/scripts/Commands/cs_chainwielder_owner_checkpoint.cpp"
    ).read_text(encoding="utf-8")
    checkpoint = (MAGMAW / "BotMagmawTransferLaneCheckpoint.h").read_text(
        encoding="utf-8"
    )

    begin = preparation.index("context.State.DecisionKernel.Begin")
    inject = preparation.index(
        "SubmitMagmawTransferLaneCheckpointAfterKernelBegin", begin
    )
    admission = preparation.index(
        "InstallControllerRouteHoldAdmissionPolicy", inject
    )
    assert begin < inject < admission
    assert "SelectMagmawTransferLaneAuthority(false" in manager
    assert "SubmitMagmawTransferLaneKernelCandidate" in manager
    assert '"validation_route_adapter"' in manager
    assert "MarkCheckpointObservationCandidate" in manager
    assert "OwnsQueuedKernelCandidate" in candidates
    assert "ExecuteNativeActionIntent" in manager
    assert ".ForReceipt(" in manager
    assert "MovementPlannerDiagnostics().Latest" not in manager
    assert "movement.RequestedX == task.Destination.X" in manager
    assert "progress.SelectedX == checkpoint.Task.Destination.X" in manager
    assert "ObserveProgressPublication" in manager
    assert "magmaw_transfer_checkpoint_task_not_selected" in manager
    assert "certifies_gameplay_success" in manager
    assert "certifies_boss_fidelity" in manager
    assert "fixture_gate_passed" in manager
    assert "MagmawTransferLaneTaskAuthority" in manager
    assert "TaskAuthorityEnabled" in checkpoint
    assert "botautomagmawtransfercheckpoint" in command
    arm_body = command[
        command.index("static bool HandleMagmawTransferCheckpointCommand"):
        command.index("static bool HandleNativePathCheckpointCommand")
    ]
    assert "float " not in arm_body
    assert "DestinationX" not in arm_body
    assert "DestinationY" not in arm_body
    assert "DestinationZ" not in arm_body
    assert "parser >> actorGuid >> caseId >> sealSha256" in arm_body
    assert "sourceCommit >> extra" in arm_body
    assert "!extra.empty()" in arm_body


def test_pinned_case_matches_retained_real_map669_detour_probe() -> None:
    receipt = json.loads((
        ROOT / "experiments/configs/map669_magmaw_transfer_lane_entrance_probe_v1.json"
    ).read_text(encoding="utf-8"))
    checkpoint = (MAGMAW / "BotMagmawTransferLaneCheckpoint.h").read_text(
        encoding="utf-8"
    )
    assert receipt["fixture_id"] == "map669_magmaw_transfer_lane_authority_off_v1"
    assert receipt["case_id"] == "entrance_polygon_short_lane_v1"
    assert receipt["detour"]["complete"] is True
    assert receipt["detour"]["corridor_polygons"] == 1
    assert receipt["detour"]["smooth_points"] == 3
    assert receipt["detour"]["terminal_2d_error"] == 0.0
    assert receipt["detour"]["terminal_z_error"] == 0.0
    probe_source = ROOT / receipt["probe"]["native_source"]
    assert hashlib.sha256(probe_source.read_bytes()).hexdigest() == (
        receipt["probe"]["native_source_sha256"]
    )
    for value in receipt["start"] + receipt["destination"]:
        assert f"{value:.6f}f" in checkpoint


def test_checkpoint_cpp_files_stay_below_size_limit() -> None:
    paths = [
        MAGMAW / "BotMagmawTransferLaneCheckpoint.h",
        MAGMAW / "BotMagmawTransferLaneCheckpoint.cpp",
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrMagmawTransferLaneCheckpoint.cpp",
        ROOT / "src/server/game/Bots/BotWorldPopulationMgrChainwielderOwnerCheckpoint.cpp",
        ROOT / "src/server/scripts/Commands/cs_chainwielder_owner_checkpoint.cpp",
    ]
    assert all(len(path.read_text(encoding="utf-8").splitlines()) < 1000
               for path in paths)

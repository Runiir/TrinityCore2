"""Deterministic telemetry-value tests, not a map-669 production fixture."""

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.cpp"
)
PROGRESS_SOURCE = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrMovementProgressDiagnostics.cpp"
)
PROGRESS_HEADER = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"
)
PROGRESS_SAMPLER = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrMovementProgressSampler.cpp"
)
UPDATE_BOT = ROOT / "src/server/game/Bots/BotWorldPopulationMgrUpdateBot.cpp"
MOVEMENT_EXECUTOR = (
    ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovementExecutor.cpp"
)
MOTION_MASTER = ROOT / "src/server/game/Movement/MotionMaster.cpp"
BOT_CONFIG = ROOT / "src/server/game/Bots/BotWorldPopulationMgrConfig.h"


HARNESS = r"""
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"

#include <cassert>
#include <iostream>
#include <string>
#include <type_traits>
#include <vector>

using namespace BotWorldMovement;

int main()
{
    MovementPlannerDiagnostics().ClearAll();

    Intent intent;
    intent.X = -308.91f;
    intent.Y = -36.4524f;
    intent.Z = 211.581f;
    intent.Owner = BotMovementArbitration::Owner::Formation;
    intent.Priority = BotMovementArbitration::Priority::Formation;
    intent.IntentReason = "ranged_formation_restore";
    BotMovementArbitration::Scope scope{77, 3, 19, 669, 42};

    std::uint64_t const receiptId = BeginMovementPlannerReceipt(
        30005, 669, intent, scope, 0, -311.814f, -32.2758f, 211.39f, true);
    assert(receiptId != 0);

    PathPlan plan;
    plan.LaunchReceiptId = receiptId;
    plan.Selected = true;
    plan.SegmentX = intent.X;
    plan.SegmentY = intent.Y;
    plan.SegmentZ = intent.Z;
    NativePathProofObservation proof;
    proof.Available = true;
    proof.Calculated = true;
    proof.PathType = 1;
    proof.Complete = true;
    proof.EndpointX = intent.X;
    proof.EndpointY = intent.Y;
    proof.EndpointZ = intent.Z;
    proof.EndpointMatched = true;
    proof.EndpointFloorValid = true;
    proof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorGap, 0, 1,
        -311.814f, -32.2758f, 209.392f, 211.39f, 211.581f);
    proof.FloorObservationConflict = true;
    proof.Accepted = true;

    std::vector<NativePathControl> const planned{
        {-311.0f, -32.0f, 211.5f},
        {-308.91f, -36.4524f, 211.581f},
    };
    std::vector<NativePathControl> const reordered{
        planned[1], planned[0]
    };
    assert(NativePathControlsFingerprint(planned)
        == 0x0f6c4d95882b3e0fULL);
    assert(NativePathControlsFingerprint(planned)
        == NativePathControlsFingerprint(planned));
    assert(NativePathControlsFingerprint(planned)
        != NativePathControlsFingerprint(reordered));

    NativePathControlSequence const plannedSummary =
        ObserveNativePathControls(planned, "world");
    RecordMovementPlannerOutcome(receiptId, 30005, 669, intent, true,
        211.39f, true, "path_admission", true, nullptr, plan, &proof,
        &plannedSummary);
    RecordNativePathSubmission(receiptId, 30005, 669,
        -311.814f, -32.2758f, 211.39f, intent.X, intent.Y, intent.Z, true);
    Movement::NativePathLaunchContext const launchContext =
        NativePathLaunchContextForReceipt(receiptId, 30005, 669);
    assert(launchContext.Version == 1);
    assert(launchContext.IntentFingerprint == 0xd9b154fc91572d50ULL);
    assert(launchContext.AttemptId == 77);
    Movement::NativePathLaunchContext mismatchedContext = launchContext;
    mismatchedContext.IntentFingerprint ^= 1;
    mismatchedContext.Observer->OnPointGeneratorInitialize(mismatchedContext);
    assert(!MovementPlannerDiagnostics().Latest(30005)
        .LaunchReceipt.PointGeneratorInitialized);
    launchContext.Observer->OnPointGeneratorInitialize(launchContext);
    launchContext.Observer->OnSplinePreparation(launchContext, true, true, 1,
        planned, false, false);
    launchContext.Observer->OnSplineLaunch(launchContext, planned,
        Movement::NativePathLaunchCoordinateSpace::World, true, false,
        true, 44, intent.X, intent.Y, intent.Z,
        -311.814f, -32.2758f, 211.39f);
    launchContext.Observer->OnMotionMasterSubmission(launchContext, 1, 8);
    ArmMovementProgressReceipt(receiptId, 30005, 669, true, 44,
        intent.X, intent.Y, intent.Z, 1000);
    assert(MovementProgressDiagnostics().ActiveReceipt(30005) == receiptId);
    assert(!MovementProgressDiagnostics().ObservationDue(30005, 1099));
    assert(MovementProgressDiagnostics().ObservationDue(30005, 1100));
    RecordMovementPlannerExecutorOutcome(30005, 669, intent,
        "native_path_submission", "submitted", "native_movement_submitted",
        receiptId);
    MovementPlannerDiagnostics().AssociateTrace(30005, 745);

    MovementPlannerObservation traced =
        MovementPlannerDiagnostics().ForTrace(30005, 745);
    assert(traced.LaunchReceipt.Id == receiptId);
    assert(traced.LaunchReceipt.Scope.AttemptId == 77);
    assert(traced.LaunchReceipt.Scope.WipeGeneration == 3);
    assert(traced.LaunchReceipt.Scope.RouteGeneration == 19);
    assert(traced.LaunchReceipt.Scope.InstanceId == 42);
    assert(traced.LaunchReceipt.PlannerControls.ControlCount == 2);
    assert(traced.LaunchReceipt.PlannerControls.Fingerprint
        == NativePathControlsFingerprint(planned));
    assert(traced.LaunchReceipt.ExecutorDestinationAvailable);
    assert(traced.LaunchReceipt.MotionMasterSubmissionObserved);
    assert(traced.LaunchReceipt.PointGeneratorInitialized);
    assert(traced.LaunchReceipt.Launches.size() == 1);
    assert(!traced.LaunchReceipt.Launches[0].DirectTwoPointFallback);
    assert(traced.LaunchReceipt.Launches[0].LaunchSucceeded);
    assert(!traced.LaunchReceipt.Launches[0].SplineFinalizedAfterLaunch);

    NativeMovementProgressProbe progress;
    progress.ObservedAtMs = 1100;
    progress.BotGuid = 30005;
    progress.ActorAvailable = true;
    progress.ActorInWorld = true;
    progress.ActorAlive = true;
    progress.MapId = 669;
    progress.InstanceId = 42;
    progress.X = -310.5f;
    progress.Y = -34.0f;
    progress.Z = 211.5f;
    progress.Moving = true;
    progress.FloorSampled = true;
    progress.FloorValid = true;
    progress.FloorZ = 211.5f;
    progress.CurrentMotionType = 8;
    progress.ActiveMotionType = 8;
    progress.PointGeneratorActive = true;
    progress.SplineInitialized = true;
    progress.SplineId = 44;
    progress.SplineFinalized = false;
    NativeMovementProgressProbe const unchanged = progress;
    static_assert(std::is_same_v<decltype(
        MovementProgressDiagnostics().Observe(progress)), void>);
    MovementProgressDiagnostics().Observe(progress);
    assert(progress.ObservedAtMs == unchanged.ObservedAtMs);
    assert(progress.X == unchanged.X);
    NativeMovementProgressObservation progressObservation =
        MovementProgressDiagnostics().ForReceipt(receiptId);
    assert(progressObservation.ReceiptId == receiptId);
    assert(progressObservation.Samples.size() == 1);
    assert(progressObservation.Samples.front().ReceiptId == receiptId);
    assert(progressObservation.Samples.front().EndpointProgressed);
    assert(progressObservation.Samples.front().SelectedPlatformCompatible);
    assert(!progressObservation.Terminal);

    // A different actor cannot consume or overwrite this receipt's samples.
    MovementProgressDiagnostics().Arm(900, 30006, 669, 42, scope,
        -100.0f, -100.0f, 211.0f, -110.0f, -110.0f, 211.0f,
        true, 90, -100.0f, -100.0f, 211.0f, 1000);
    NativeMovementProgressProbe other = progress;
    other.BotGuid = 30006;
    other.X = -101.0f;
    other.Y = -101.0f;
    other.SplineId = 90;
    MovementProgressDiagnostics().Observe(other);
    assert(MovementProgressDiagnostics().ForReceipt(900).Samples.size() == 1);
    assert(MovementProgressDiagnostics().ForReceipt(receiptId).Samples.size()
        == 1);
    other.ObservedAtMs = 1200;
    other.SplineId = 91;
    MovementProgressDiagnostics().Observe(other);
    NativeMovementProgressObservation const replaced =
        MovementProgressDiagnostics().ForReceipt(900);
    assert(replaced.Terminal);
    assert(replaced.TerminalOutcome == "native_spline_replaced");
    assert(replaced.Samples.back().ReceiptId == 900);

    progress.ObservedAtMs = 1200;
    progress.X = intent.X;
    progress.Y = intent.Y;
    progress.Z = intent.Z;
    progress.Moving = false;
    progress.PointGeneratorActive = false;
    progress.SplineFinalized = true;
    MovementProgressDiagnostics().Observe(progress);
    progressObservation = MovementProgressDiagnostics().ForReceipt(receiptId);
    assert(progressObservation.Samples.size() == 2);
    assert(progressObservation.Terminal);
    assert(progressObservation.TerminalOutcome == "selected_endpoint_reached");
    assert(MovementProgressDiagnostics().ActiveReceipt(30005) == 0);

    // A newer receipt must remain latest while a delayed native launch updates
    // the already-associated trace row for the exact older receipt.
    Intent newerIntent = intent;
    newerIntent.IntentReason = "newer_observation";
    std::uint64_t const newerId = BeginMovementPlannerReceipt(
        30005, 669, newerIntent, scope, 0, -310.0f, -33.0f, 211.4f);
    assert(newerId != receiptId);
    launchContext.Observer->OnSplinePreparation(launchContext, true, false, 4,
        {}, true, true);
    launchContext.Observer->OnSplineLaunch(launchContext, reordered,
        Movement::NativePathLaunchCoordinateSpace::World, true, false,
        true, 46, intent.X, intent.Y, intent.Z,
        -311.0f, -33.0f, 211.4f);
    assert(MovementPlannerDiagnostics().Latest(30005).LaunchReceipt.Id
        == newerId);
    traced = MovementPlannerDiagnostics().ForTrace(30005, 745);
    assert(traced.LaunchReceipt.Launches.size() == 2);
    assert(traced.LaunchReceipt.Launches[1].DirectTwoPointFallback);
    assert(traced.LaunchReceipt.Launches[1].LaunchedControls.Fingerprint
        == NativePathControlsFingerprint(reordered));

    // Hot-path launch history is explicitly capped and reports replacement.
    Movement::NativePathLaunchContext const newerContext =
        NativePathLaunchContextForReceipt(newerId, 30005, 669);
    for (int index = 0; index < 6; ++index)
    {
        newerContext.Observer->OnSplinePreparation(newerContext, true, true,
            1, planned, false, false);
        newerContext.Observer->OnSplineLaunch(newerContext, planned,
            Movement::NativePathLaunchCoordinateSpace::World, true, false,
            true, 50 + index, newerIntent.X, newerIntent.Y, newerIntent.Z,
            -310.0f, -33.0f, 211.4f);
    }
    MovementPlannerObservation bounded =
        MovementPlannerDiagnostics().Latest(30005);
    assert(bounded.LaunchReceipt.Launches.size()
        == NativePathLaunchReceipt::MaxLaunchAttempts);
    assert(bounded.LaunchReceipt.LaunchAttemptOverflowCount == 2);

    // Re-arm the fully launched newer receipt and prove bounded multi-tick
    // retention plus the exact lifetime boundary.
    newerContext.Observer->OnPointGeneratorInitialize(newerContext);
    newerContext.Observer->OnMotionMasterSubmission(newerContext, 1, 8);
    MovementProgressDiagnostics().Arm(newerId, 30005, 669, 42, scope,
        newerIntent.X, newerIntent.Y, newerIntent.Z,
        -450.0f, -150.0f, 211.4f, true, 45,
        newerIntent.X, newerIntent.Y, newerIntent.Z, 2000);
    NativeMovementProgressProbe boundedProbe = progress;
    boundedProbe.X = -400.0f;
    boundedProbe.Y = -100.0f;
    boundedProbe.Z = 211.4f;
    boundedProbe.Moving = true;
    boundedProbe.PointGeneratorActive = true;
    boundedProbe.SplineFinalized = false;
    boundedProbe.SplineId = 45;
    for (std::uint64_t tick = 1; tick <= 20; ++tick)
    {
        boundedProbe.ObservedAtMs = 2000 + tick;
        MovementProgressDiagnostics().Observe(boundedProbe);
    }
    NativeMovementProgressObservation boundedProgress =
        MovementProgressDiagnostics().ForReceipt(newerId);
    assert(boundedProgress.Samples.size()
        == NativeMovementProgressObservation::MaxSamples);
    assert(boundedProgress.DroppedSampleCount == 4);
    boundedProbe.ObservedAtMs = 32000;
    MovementProgressDiagnostics().Observe(boundedProbe);
    assert(!MovementProgressDiagnostics().ForReceipt(newerId).Terminal);
    boundedProbe.ObservedAtMs = 32001;
    MovementProgressDiagnostics().Observe(boundedProbe);
    boundedProgress = MovementProgressDiagnostics().ForReceipt(newerId);
    assert(boundedProgress.Terminal);
    assert(boundedProgress.TerminalOutcome == "observation_expired");
    assert(boundedProgress.Samples.back().ReceiptId == newerId);
    assert(boundedProgress.DroppedSampleCount == 6);

    // MotionMaster can accept the generator while a higher slot is active,
    // then initialize the point generator and launch its spline later. The
    // successful delayed callback must arm the receipt without a second
    // executor attempt and must bind the callback's exact spline ID.
    Intent delayedIntent = intent;
    delayedIntent.IntentReason = "delayed_point_initialize";
    std::uint64_t const delayedId = BeginMovementPlannerReceipt(
        30007, 669, delayedIntent, scope, 0,
        -320.0f, -40.0f, 211.0f, true);
    PathPlan delayedPlan;
    delayedPlan.LaunchReceiptId = delayedId;
    delayedPlan.Selected = true;
    delayedPlan.SegmentX = delayedIntent.X;
    delayedPlan.SegmentY = delayedIntent.Y;
    delayedPlan.SegmentZ = delayedIntent.Z;
    RecordMovementPlannerOutcome(delayedId, 30007, 669, delayedIntent,
        true, 211.0f, true, "path_admission", true, nullptr, delayedPlan,
        &proof, &plannedSummary);
    RecordNativePathSubmission(delayedId, 30007, 669,
        -320.0f, -40.0f, 211.0f, delayedIntent.X, delayedIntent.Y,
        delayedIntent.Z, true);
    Movement::NativePathLaunchContext const delayedContext =
        NativePathLaunchContextForReceipt(delayedId, 30007, 669);
    delayedContext.Observer->OnMotionMasterSubmission(delayedContext, 1, 8);
    ArmMovementProgressReceipt(delayedId, 30007, 669, true, 66,
        delayedIntent.X, delayedIntent.Y, delayedIntent.Z, 4000);
    assert(MovementProgressDiagnostics().ActiveReceipt(30007) == 0);
    delayedContext.Observer->OnPointGeneratorInitialize(delayedContext);
    delayedContext.Observer->OnSplinePreparation(delayedContext, true, true,
        1, planned, false, false);
    delayedContext.Observer->OnSplineLaunch(delayedContext, planned,
        Movement::NativePathLaunchCoordinateSpace::World, true, false,
        true, 77, delayedIntent.X, delayedIntent.Y, delayedIntent.Z,
        -320.0f, -40.0f, 211.0f);
    assert(MovementProgressDiagnostics().ActiveReceipt(30007) == delayedId);
    NativeMovementProgressObservation delayed =
        MovementProgressDiagnostics().ForReceipt(delayedId);
    assert(delayed.LaunchedSplineId == 77);
    assert(delayed.ArmedAtMs == 0);
    ArmMovementProgressReceipt(delayedId, 30007, 669, true, 78,
        delayedIntent.X, delayedIntent.Y, delayedIntent.Z, 4500);
    delayed = MovementProgressDiagnostics().ForReceipt(delayedId);
    assert(delayed.LaunchedSplineId == 77);
    assert(delayed.ArmedAtMs == 0);
    NativeMovementProgressProbe delayedProbe = progress;
    delayedProbe.ObservedAtMs = 5000;
    delayedProbe.BotGuid = 30007;
    delayedProbe.X = -315.0f;
    delayedProbe.Y = -38.0f;
    delayedProbe.Z = 211.2f;
    delayedProbe.SplineId = 77;
    delayedProbe.PointGeneratorActive = true;
    delayedProbe.SplineFinalized = false;
    MovementProgressDiagnostics().Observe(delayedProbe);
    delayed = MovementProgressDiagnostics().ForReceipt(delayedId);
    assert(delayed.ArmedAtMs == 5000);
    assert(delayed.Samples.size() == 1);
    assert(delayed.Samples.front().ReceiptId == delayedId);
    assert(delayed.Samples.front().MatchesLaunchedSpline);

    // The same full native launch chain is inert for progress capture unless
    // the caller explicitly enables the validation-only diagnostic.
    Intent disabledIntent = intent;
    disabledIntent.IntentReason = "default_off_progress_capture";
    std::uint64_t const disabledId = BeginMovementPlannerReceipt(
        30008, 669, disabledIntent, scope, 0,
        -330.0f, -45.0f, 211.0f);
    PathPlan disabledPlan;
    disabledPlan.LaunchReceiptId = disabledId;
    disabledPlan.Selected = true;
    disabledPlan.SegmentX = disabledIntent.X;
    disabledPlan.SegmentY = disabledIntent.Y;
    disabledPlan.SegmentZ = disabledIntent.Z;
    RecordMovementPlannerOutcome(disabledId, 30008, 669, disabledIntent,
        true, 211.0f, true, "path_admission", true, nullptr, disabledPlan,
        &proof, &plannedSummary);
    RecordNativePathSubmission(disabledId, 30008, 669,
        -330.0f, -45.0f, 211.0f, disabledIntent.X, disabledIntent.Y,
        disabledIntent.Z, true);
    Movement::NativePathLaunchContext const disabledContext =
        NativePathLaunchContextForReceipt(disabledId, 30008, 669);
    disabledContext.Observer->OnMotionMasterSubmission(disabledContext, 1, 8);
    disabledContext.Observer->OnPointGeneratorInitialize(disabledContext);
    disabledContext.Observer->OnSplinePreparation(disabledContext, true,
        true, 1, planned, false, false);
    disabledContext.Observer->OnSplineLaunch(disabledContext, planned,
        Movement::NativePathLaunchCoordinateSpace::World, true, false,
        true, 88, disabledIntent.X, disabledIntent.Y, disabledIntent.Z,
        -330.0f, -45.0f, 211.0f);
    ArmMovementProgressReceipt(disabledId, 30008, 669, true, 88,
        disabledIntent.X, disabledIntent.Y, disabledIntent.Z, 6000);
    assert(MovementProgressDiagnostics().ActiveReceipt(30008) == 0);
    assert(!MovementPlannerDiagnostics().Latest(30008)
        .LaunchReceipt.ProgressCaptureEnabled);

    std::string const serialized = MovementPlannerObservationJson(traced);

    // Planner selection has moved to newerId, so its selected observation no
    // longer publishes the retained terminal progress for receiptId.
    std::string const latestSelected = MovementPlannerObservationJson(
        MovementPlannerDiagnostics().Latest(30005));
    assert(latestSelected.find("\"receipt_id\":"
        + std::to_string(receiptId)) == std::string::npos);
    NativeMovementProgressPublication displacedHistory =
        MovementProgressDiagnostics().RecentForBot(30005);
    std::string const displacedHistoryJson =
        MovementProgressPublicationJson(displacedHistory);
    assert(displacedHistoryJson.find("\"receipt_id\":"
        + std::to_string(receiptId)) != std::string::npos);

    // Receipt-598-like timing: four retained samples stop before a later
    // native receipt explicitly supersedes the launch. Publication must keep
    // the old exact receipt/spline and separate its sample and terminal times.
    MovementProgressDiagnostics().ClearAll();
    MovementProgressDiagnostics().Arm(598, 30007, 669, 42, scope,
        intent.X, intent.Y, intent.Z, -311.814f, -32.2758f, 211.39f,
        true, 6780, intent.X, intent.Y, intent.Z, 1788031505000ULL);
    NativeMovementProgressProbe receipt598Probe = progress;
    receipt598Probe.BotGuid = 30007;
    receipt598Probe.X = -310.5f;
    receipt598Probe.Y = -34.0f;
    receipt598Probe.Z = 211.5f;
    receipt598Probe.Moving = true;
    receipt598Probe.PointGeneratorActive = true;
    receipt598Probe.SplineId = 6780;
    receipt598Probe.SplineFinalized = false;
    for (std::uint64_t observedAtMs : {1788031505100ULL, 1788031505500ULL,
        1788031506000ULL, 1788031506663ULL})
    {
        receipt598Probe.ObservedAtMs = observedAtMs;
        MovementProgressDiagnostics().Observe(receipt598Probe);
    }
    MovementProgressDiagnostics().Arm(599, 30007, 669, 42, scope,
        intent.X + 1.0f, intent.Y, intent.Z, receipt598Probe.X,
        receipt598Probe.Y, receipt598Probe.Z, true, 6781,
        intent.X + 1.0f, intent.Y, intent.Z, 1788031509261ULL);
    NativeMovementProgressObservation const retained598 =
        MovementProgressDiagnostics().ForReceipt(598);
    assert(retained598.Terminal);
    assert(retained598.TerminalOutcome == "superseded_by_native_launch");
    assert(retained598.LastObservedAtMs == 1788031506663ULL);
    assert(retained598.LastSampleAtMs == 1788031506663ULL);
    assert(retained598.TerminalAtMs == 1788031509261ULL);
    assert(retained598.SupersededByReceiptId == 599);
    NativeMovementProgressPublication receipt598History =
        MovementProgressDiagnostics().RecentForBot(30007);
    assert(receipt598History.ActiveReceiptId == 599);
    assert(receipt598History.Receipts.size() == 2);
    std::string const receipt598HistoryJson =
        MovementProgressPublicationJson(receipt598History);
    assert(receipt598HistoryJson.find("\"receipt_id\":598")
        != std::string::npos);
    assert(receipt598HistoryJson.find("\"id\":6780")
        != std::string::npos);
    assert(receipt598HistoryJson.find(
        "\"last_observed_at_ms\":1788031506663") != std::string::npos);
    assert(receipt598HistoryJson.find(
        "\"last_sample_at_ms\":1788031506663") != std::string::npos);
    assert(receipt598HistoryJson.find(
        "\"terminal_at_ms\":1788031509261") != std::string::npos);
    assert(receipt598HistoryJson.find(
        "\"superseded_by_receipt_id\":599") != std::string::npos);

    // Idempotent re-arming must not duplicate the bounded retention queue or
    // overwrite an existing receipt identity.
    MovementProgressDiagnostics().ClearAll();
    MovementProgressDiagnostics().Arm(1, 40001, 669, 42, scope,
        10.0f, 10.0f, 10.0f, 0.0f, 0.0f, 10.0f,
        true, 1, 10.0f, 10.0f, 10.0f, 1);
    MovementProgressDiagnostics().Arm(1, 40001, 669, 42, scope,
        10.0f, 10.0f, 10.0f, 0.0f, 0.0f, 10.0f,
        true, 1, 10.0f, 10.0f, 10.0f, 2);
    for (std::uint64_t id = 2;
        id <= MovementProgressDiagnosticSidecar::MaxReceiptsPerBot; ++id)
        MovementProgressDiagnostics().Arm(id, 40001, 669, 42, scope,
            float(id), 10.0f, 10.0f, 0.0f, 0.0f, 10.0f,
            true, std::uint32_t(id), float(id), 10.0f, 10.0f, id);
    assert(MovementProgressDiagnostics().ForReceipt(1).Available);
    MovementProgressDiagnostics().Arm(129, 40001, 669, 42, scope,
        129.0f, 10.0f, 10.0f, 0.0f, 0.0f, 10.0f,
        true, 129, 129.0f, 10.0f, 10.0f, 129);
    assert(!MovementProgressDiagnostics().ForReceipt(1).Available);
    NativeMovementProgressPublication boundedPublication =
        MovementProgressDiagnostics().RecentForBot(40001);
    assert(boundedPublication.ActiveReceiptId == 129);
    assert(boundedPublication.RetainedReceiptCount
        == MovementProgressDiagnosticSidecar::MaxReceiptsPerBot);
    assert(boundedPublication.Receipts.size()
        == NativeMovementProgressPublication::MaxReceipts);
    assert(boundedPublication.OmittedReceiptCount == 124);
    std::string const boundedPublicationJson =
        MovementProgressPublicationJson(boundedPublication);
    assert(boundedPublicationJson.find("\"receipt_capacity\":4")
        != std::string::npos);
    assert(boundedPublicationJson.find(
        "\"sample_capacity_per_receipt\":16") != std::string::npos);
    assert(boundedPublicationJson.find("\"receipts_truncated\":true")
        != std::string::npos);
    assert(boundedPublicationJson.find("\"max_published_sample_count\":64")
        != std::string::npos);
    assert(boundedPublicationJson.find("\"payload_complete\":false")
        != std::string::npos);

    std::cout << "{\"planner\":" << serialized
        << ",\"receipt_progress\":" << receipt598HistoryJson << "}";
}
"""


def test_native_path_launch_receipt_value_and_schema(tmp_path):
    harness = tmp_path / "native_path_launch_receipt_telemetry.cpp"
    binary = tmp_path / "native_path_launch_receipt_telemetry"
    harness.write_text(HARNESS, encoding="utf-8")
    subprocess.run(
        [
            "c++",
            "-std=c++17",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-I",
            str(ROOT / "src/server/game"),
            "-I",
            str(ROOT / "src/server/game/Entities/Object"),
            "-I",
            str(ROOT / "src/common"),
            "-I",
            str(ROOT / "dep/g3dlite/include"),
            str(harness),
            str(SOURCE),
            str(PROGRESS_SOURCE),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    output = json.loads(
        subprocess.run(
            [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
        ).stdout
    )
    receipt = output["planner"]["launch_receipt"]
    receipt_progress = output["receipt_progress"]

    assert receipt["version"] == 1
    assert receipt["identity"] == {
        "bot_guid": 30005,
        "map": 669,
        "owner": "formation",
        "intent_reason": "ranged_formation_restore",
        "intent_fingerprint": "d9b154fc91572d50",
        "dynamic_target_guid": 0,
        "progress_capture_enabled": True,
        "scope": {
            "attempt_id": 77,
            "wipe_generation": 3,
            "route_generation": 19,
            "map": 669,
            "instance": 42,
        },
    }
    assert receipt["actor_before_planning"]["coordinate_space"] == "world"
    assert receipt["planner_path"]["calculated"] is True
    assert receipt["planner_path"]["type"] == 1
    assert receipt["planner_path"]["complete"] is True
    assert receipt["planner_path"]["controls"] == {
        "available": True,
        "coordinate_space": "world",
        "count": 2,
        "fingerprint": "0f6c4d95882b3e0f",
    }
    assert receipt["planner_path"]["floor_observation_conflict"] is True
    assert receipt["executor"]["generate_path"] is True
    assert receipt["motion_master"]["observed"] is True
    assert receipt["launches"][0]["second_path"]["calculated"] is True
    assert receipt["launches"][0]["direct_two_point_fallback"] is False
    assert receipt["launches"][0]["spline_launch"]["succeeded"] is True
    assert receipt["launches"][0]["spline_launch"]["controls"][
        "coordinate_space"
    ] == "world"
    assert receipt["launches"][1]["direct_two_point_fallback"] is True
    assert receipt["progress"]["receipt_id"] == receipt["id"]
    assert receipt["progress"]["terminal"] is True
    assert receipt["progress"]["terminal_outcome"] == "selected_endpoint_reached"
    assert [sample["receipt_id"] for sample in receipt["progress"]["samples"]] == [
        receipt["id"],
        receipt["id"],
    ]
    assert receipt["progress"]["samples"][0]["floor"][
        "selected_platform_compatible"
    ] is True
    assert receipt["progress"]["samples"][0]["native_motion"] == {
        "moving": True,
        "current_type": 8,
        "active_type": 8,
        "point_generator_active": True,
        "spline_initialized": True,
        "spline_id": 44,
        "matches_launched_spline": True,
        "spline_finalized": False,
    }
    assert receipt["progress"]["samples"][1]["endpoint_progress"][
        "reached"
    ] is True
    assert "ordered_controls" not in json.dumps(receipt)
    assert receipt_progress["bot_guid"] == 30007
    assert receipt_progress["active_receipt_id"] == 599
    assert receipt_progress["ordering"] == "active_then_newest"
    assert receipt_progress["retained_receipt_count"] == 2
    assert receipt_progress["published_receipt_count"] == 2
    assert receipt_progress["receipt_capacity"] == 4
    assert receipt_progress["sample_capacity_per_receipt"] == 16
    assert receipt_progress["max_published_sample_count"] == 64
    assert receipt_progress["receipts_truncated"] is False
    assert receipt_progress["payload_complete"] is True
    receipt_598 = next(
        item for item in receipt_progress["receipts"] if item["receipt_id"] == 598
    )
    assert receipt_598["bot_guid"] == 30007
    assert receipt_598["map"] == 669
    assert receipt_598["instance"] == 42
    assert receipt_598["scope"] == {
        "attempt_id": 77,
        "wipe_generation": 3,
        "route_generation": 19,
    }
    assert receipt_598["launched_spline"]["id"] == 6780
    assert receipt_598["last_sample_at_ms"] == 1788031506663
    assert receipt_598["terminal_at_ms"] == 1788031509261
    assert receipt_598["terminal_outcome"] == "superseded_by_native_launch"
    assert receipt_598["superseded_by_receipt_id"] == 599
    assert len(receipt_598["samples"]) == 4


def test_receipt_progress_sampler_is_observation_only():
    header = PROGRESS_HEADER.read_text(encoding="utf-8")
    sampler = PROGRESS_SAMPLER.read_text(encoding="utf-8")
    update = UPDATE_BOT.read_text(encoding="utf-8")
    executor = MOVEMENT_EXECUTOR.read_text(encoding="utf-8")
    config = BOT_CONFIG.read_text(encoding="utf-8")

    assert "void ObserveReceiptTaggedMovementProgress(Player const* bot);" in header
    assert "WorldBotState&" not in header
    assert "WorldBotState&" not in sampler
    for forbidden_mutator in (
        "MovePoint(",
        "MoveChase(",
        "Clear(",
        "SetPosition(",
        "NearTeleportTo(",
        "InterruptNonMeleeSpells(",
        "Apply(state",
    ):
        assert forbidden_mutator not in sampler
    assert "BotWorldMovement::ObserveReceiptTaggedMovementProgress(bot);" in update
    assert "if (Cohort().Config.ValidationRouteEnable)" in update
    arm = executor.index("BotWorldMovement::ArmMovementProgressReceipt")
    assert "if (Cohort().Config.ValidationRouteEnable)" in executor[
        max(0, arm - 600) : arm
    ]
    assert "bool ValidationRouteEnable = false;" in config


def test_motion_master_supports_delayed_point_generator_initialization():
    motion_master = MOTION_MASTER.read_text(encoding="utf-8")
    mutate = motion_master[
        motion_master.index("void MotionMaster::Mutate") :
        motion_master.index("void MotionMaster::DirectClean")
    ]
    assert "if (_top > slot)" in mutate
    assert "_initialize[slot] = true;" in mutate
    assert "m->Initialize(_owner);" in mutate

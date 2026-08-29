"""Deterministic telemetry-value tests, not a map-669 production fixture."""

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = (
    ROOT
    / "src/server/game/Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.cpp"
)


HARNESS = r"""
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"

#include <cassert>
#include <iostream>
#include <string>
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
        30005, 669, intent, scope, 0, -311.814f, -32.2758f, 211.39f);
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
        -311.814f, -32.2758f, 211.39f);
    launchContext.Observer->OnMotionMasterSubmission(launchContext, 1, 8);
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
            -310.0f, -33.0f, 211.4f);
    }
    MovementPlannerObservation bounded =
        MovementPlannerDiagnostics().Latest(30005);
    assert(bounded.LaunchReceipt.Launches.size()
        == NativePathLaunchReceipt::MaxLaunchAttempts);
    assert(bounded.LaunchReceipt.LaunchAttemptOverflowCount == 2);

    std::cout << MovementPlannerObservationJson(traced);
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
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    receipt = json.loads(
        subprocess.run(
            [str(binary)], check=True, cwd=ROOT, capture_output=True, text=True
        ).stdout
    )["launch_receipt"]

    assert receipt["version"] == 1
    assert receipt["identity"] == {
        "bot_guid": 30005,
        "map": 669,
        "owner": "formation",
        "intent_reason": "ranged_formation_restore",
        "intent_fingerprint": "d9b154fc91572d50",
        "dynamic_target_guid": 0,
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
    assert "ordered_controls" not in json.dumps(receipt)

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
HEADER = BOT_DIR / "BotWorldPopulationMgrMovementPlannerDiagnostics.h"
SOURCE = BOT_DIR / "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp"
PLANNER = BOT_DIR / "BotWorldPopulationMgrMovementPlanner.cpp"
TRACE = BOT_DIR / "BotWorldPopulationMgrDecisionTrace.cpp"
DIAGNOSIS = BOT_DIR / "BotWorldPopulationMgrDiagnosis.cpp"
STATUS = BOT_DIR / "BotWorldPopulationMgrStatus.cpp"
EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
RUNTIME = BOT_DIR / "BotWorldPopulationMgrValidationRouteRuntime.cpp"
UPDATE = BOT_DIR / "BotWorldPopulationMgrUpdate.cpp"
NATIVE_ACTION = BOT_DIR / "BotWorldPopulationMgrNativeAction.cpp"
MOVEMENT = BOT_DIR / "BotWorldPopulationMgrMovement.cpp"
KERNEL_CANDIDATES = BOT_DIR / "BotWorldPopulationMgrUpdateBotKernelCandidates.cpp"
BOT_STATE = BOT_DIR / "BotWorldPopulationMgrBotState.h"
MANAGER = BOT_DIR / "BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


HARNESS = r"""
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotNativeActionIntent.h"

#include <cassert>
#include <cmath>
#include <string>

using namespace BotWorldMovement;

MovementPlannerObservation InvalidFloor()
{
    MovementPlannerObservation observation;
    observation.BotGuid = 30001;
    observation.RequestedMapId = 669;
    observation.RequestedX = -345.872f;
    observation.RequestedY = -110.0f;
    observation.RequestedZ = 214.207f;
    observation.MovementOwner = BotMovementArbitration::Owner::Route;
    observation.TargetFloorSampled = true;
    observation.TargetFloorValid = false;
    observation.AllowProgressiveSegments = false;
    observation.RequireCompletePath = true;
    observation.Gate = "target_floor";
    observation.Result = "rejected";
    observation.Reason = "route_destination_invalid_floor";
    observation.PlannerGate = observation.Gate;
    observation.PlannerResult = observation.Result;
    observation.PlannerReason = observation.Reason;
    return observation;
}

MovementPlannerObservation InvalidZ()
{
    MovementPlannerObservation observation = InvalidFloor();
    observation.BotGuid = 30002;
    observation.RequestedX = -330.0f;
    observation.RequestedY = -88.0f;
    observation.RequestedZ = 214.0f;
    observation.TargetFloorZ = 219.5f;
    observation.TargetFloorValid = true;
    observation.ZDeltaAvailable = true;
    observation.AbsoluteZDelta = 5.5f;
    observation.RequireCompletePath = false;
    observation.Gate = "target_z_transition";
    observation.Reason = "route_destination_invalid_z_transition";
    observation.PlannerGate = observation.Gate;
    observation.PlannerResult = observation.Result;
    observation.PlannerReason = observation.Reason;
    return observation;
}

int main()
{
    BotNativeAction::Intent annotated = BotNativeAction::WithMovementReason(
        BotNativeAction::Move{1.0f, 2.0f, 3.0f}, "pincer_preposition");
    auto const* annotatedMove = std::get_if<BotNativeAction::Move>(&annotated);
    assert(annotatedMove);
    assert(annotatedMove->IntentReason == "pincer_preposition");

    MovementPlannerDiagnosticSidecar sidecar;
    sidecar.Record(InvalidFloor());
    std::string invalidFloorJson = MovementPlannerObservationJson(
        sidecar.Latest(30001));
    assert(invalidFloorJson.find("\"result\":\"rejected\"") != std::string::npos);
    assert(invalidFloorJson.find("route_destination_invalid_floor") != std::string::npos);
    assert(invalidFloorJson.find("\"map\":669") != std::string::npos);
    assert(invalidFloorJson.find("\"x\":-345.872") != std::string::npos);
    assert(invalidFloorJson.find("\"sampled\":true") != std::string::npos);
    assert(invalidFloorJson.find("\"z\":null") != std::string::npos);

    sidecar.Record(InvalidZ());
    MovementPlannerObservation invalidZ = sidecar.Latest(30002);
    assert(invalidZ.TargetFloorValid);
    assert(std::fabs(invalidZ.AbsoluteZDelta - 5.5f) < 0.001f);
    std::string invalidZJson = MovementPlannerObservationJson(invalidZ);
    assert(invalidZJson.find("route_destination_invalid_z_transition") != std::string::npos);
    assert(invalidZJson.find("\"z\":219.5") != std::string::npos);
    assert(invalidZJson.find("\"absolute\":5.5") != std::string::npos);
    assert(invalidZJson.find("\"threshold\":4") != std::string::npos);

    sidecar.AssociateTrace(30001, 1);
    sidecar.AssociateTrace(30002, 1);
    Intent invalidZRequest;
    invalidZRequest.X = -330.0f;
    invalidZRequest.Y = -88.0f;
    invalidZRequest.Z = 214.0f;
    invalidZRequest.Owner = BotMovementArbitration::Owner::Route;
    sidecar.Record(InvalidZ());
    sidecar.FinalizeExecutor(30002, 669, invalidZRequest, "active_path",
        "retained", "native_movement_retained");
    MovementPlannerObservation retained = sidecar.Latest(30002);
    assert(retained.PlannerGate == "target_z_transition");
    assert(retained.PlannerResult == "rejected");
    assert(retained.TargetFloorValid);
    assert(retained.Gate == "active_path");
    assert(retained.Result == "retained");
    assert(retained.Reason == "native_movement_retained");

    MovementPlannerObservation reasonObservation = InvalidZ();
    reasonObservation.IntentReason = "pincer_preposition";
    sidecar.Record(reasonObservation);
    Intent reasonRequest = invalidZRequest;
    reasonRequest.IntentReason = "pincer_preposition";
    sidecar.FinalizeExecutor(30002, 669, reasonRequest, "active_path",
        "retained", "native_movement_retained");
    MovementPlannerObservation retainedWithReason = sidecar.Latest(30002);
    assert(retainedWithReason.IntentReason == "pincer_preposition");
    std::string reasonJson = MovementPlannerObservationJson(
        retainedWithReason);
    assert(reasonJson.find(
        "\"intent_reason\":\"pincer_preposition\"")
        != std::string::npos);

    MovementPlannerObservation success = InvalidFloor();
    success.TargetFloorZ = 214.2f;
    success.TargetFloorValid = true;
    success.ZDeltaAvailable = true;
    success.AbsoluteZDelta = 0.007f;
    success.RequireCompletePath = false;
    success.Gate = "path_admission";
    success.Result = "accepted";
    success.Reason.clear();
    sidecar.Record(success);
    sidecar.AssociateTrace(30001, 2);
    assert(sidecar.Latest(30001).Result == "accepted");
    assert(sidecar.ForTrace(30001, 1).Reason == "route_destination_invalid_floor");
    assert(sidecar.ForTrace(30001, 2).Result == "accepted");
    assert(sidecar.ForTrace(30002, 1).Reason == "route_destination_invalid_z_transition");

    sidecar.AssociateTrace(30002, 2);
    assert(sidecar.ForTrace(30002, 2).Result == "retained");

    // Once the previous request has been associated with a trace, an
    // executor-only success cannot inherit its old planner floor/rejection.
    sidecar.AssociateTrace(30001, 3);
    Intent successfulRequest;
    successfulRequest.X = -345.872f;
    successfulRequest.Y = -110.0f;
    successfulRequest.Z = 214.207f;
    successfulRequest.Owner = BotMovementArbitration::Owner::Route;
    sidecar.FinalizeExecutor(30001, 669, successfulRequest,
        "native_path_submission", "submitted", "native_movement_submitted");
    MovementPlannerObservation submitted = sidecar.Latest(30001);
    assert(submitted.Result == "submitted");
    assert(submitted.PlannerResult == "unavailable");
    assert(!submitted.TargetFloorSampled);

    std::string unavailable = MovementPlannerObservationJson(
        sidecar.ForTrace(30002, 3));
    assert(unavailable.find("\"available\":false") != std::string::npos);
    assert(unavailable.find("\"result\":\"unavailable\"") != std::string::npos);
    assert(unavailable.find("\"gate\":\"unavailable\"") != std::string::npos);

    sidecar.ClearBot(30001);
    assert(!sidecar.Latest(30001).Available);
    assert(!sidecar.ForTrace(30001, 1).Available);
    assert(sidecar.Latest(30002).Available);
    sidecar.ClearAll();
    assert(!sidecar.Latest(30002).Available);
    assert(!sidecar.ForTrace(30002, 1).Available);
}
"""


def test_sidecar_state_and_json_contract(tmp_path):
    harness = tmp_path / "movement_planner_diagnostics.cpp"
    binary = tmp_path / "movement_planner_diagnostics"
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
            str(harness),
            str(SOURCE),
            "-o",
            str(binary),
        ],
        check=True,
        cwd=ROOT,
    )
    subprocess.run([str(binary)], check=True, cwd=ROOT)


def test_planner_trace_diagnosis_and_lifecycle_wiring():
    planner = PLANNER.read_text(encoding="utf-8")
    trace = TRACE.read_text(encoding="utf-8")
    diagnosis = DIAGNOSIS.read_text(encoding="utf-8")
    status = STATUS.read_text(encoding="utf-8")
    executor = EXECUTOR.read_text(encoding="utf-8")
    native_action = NATIVE_ACTION.read_text(encoding="utf-8")
    movement = MOVEMENT.read_text(encoding="utf-8")
    kernel_candidates = KERNEL_CANDIDATES.read_text(encoding="utf-8")
    runtime = RUNTIME.read_text(encoding="utf-8")
    update = UPDATE.read_text(encoding="utf-8")

    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in planner
    assert "RecordMovementPlannerOutcome" in planner
    assert 'return reject("route_destination_invalid_floor", "target_floor")' in planner
    assert '"target_z_transition"' in planner
    assert "sampledTargetFloorZ = floorZ" in planner
    assert "AllowProgressiveSegments" in planner
    assert "RequireCompletePath" in planner
    assert "AllowNativeLongPath" in planner
    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in trace
    assert "MovementPlannerDiagnostics().AssociateTrace" in trace
    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in diagnosis
    assert "movement_planner" in diagnosis
    assert "MovementPlannerDiagnostics().Latest" in diagnosis
    assert "MovementPlannerDiagnostics().ForTrace" in diagnosis
    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in status
    assert "MovementPlannerDiagnostics().ForTrace" in status
    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in executor
    assert "RecordMovementPlannerExecutorOutcome" in executor
    assert "action.IntentReason" in native_action
    assert "intent.IntentReason = movementReason" in movement
    assert kernel_candidates.count("WithMovementReason") >= 7
    for gate in (
        "cross_map_pending",
        "movement_lease",
        "active_path",
        "planner_admission",
        "native_path_submission",
    ):
        assert f'"{gate}"' in executor
    for reason in (
        "native_recovery_worldport_pending",
        "movement_lease_invalid_scope",
        "higher_priority_movement_active",
        "native_movement_retained",
        "native_movement_submitted",
    ):
        assert f'"{reason}"' in executor
    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in runtime
    assert "MovementPlannerDiagnostics().ClearAll" in runtime
    assert '#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"' in update
    assert update.count("MovementPlannerDiagnostics().ClearBot") >= 2


def test_sidecar_is_not_in_central_state_and_is_registered():
    assert "MovementPlannerDiagnostics" not in BOT_STATE.read_text(encoding="utf-8")
    assert "MovementPlannerDiagnostics" not in MANAGER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    assert "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.cpp" in cmake


def test_sidecar_and_related_sources_stay_bounded():
    for path in (HEADER, SOURCE):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000


def test_unavailable_json_is_explicit():
    # Keep this assertion close to the contract so a future serializer change
    # cannot silently turn zero defaults into a successful movement result.
    source = SOURCE.read_text(encoding="utf-8")
    assert "available" in source
    assert "unavailable" in HEADER.read_text(encoding="utf-8")

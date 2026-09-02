import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BOT_DIR = ROOT / "src/server/game/Bots"
HEADER = BOT_DIR / "BotWorldPopulationMgrMovementPlannerDiagnostics.h"
SOURCE = BOT_DIR / "BotWorldPopulationMgrMovementPlannerDiagnostics.cpp"
JSON_SOURCE = BOT_DIR / "BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp"
RETENTION_SOURCE = BOT_DIR / "BotWorldPopulationMgrMovementReceiptRetention.cpp"
PROGRESS_SOURCE = BOT_DIR / "BotWorldPopulationMgrMovementProgressDiagnostics.cpp"
PLANNER = BOT_DIR / "BotWorldPopulationMgrMovementPlanner.cpp"
TRACE = BOT_DIR / "BotWorldPopulationMgrDecisionTrace.cpp"
DIAGNOSIS = BOT_DIR / "BotWorldPopulationMgrDiagnosis.cpp"
STATUS = BOT_DIR / "BotWorldPopulationMgrStatus.cpp"
EXECUTOR = BOT_DIR / "BotWorldPopulationMgrMovementExecutor.cpp"
RUNTIME = BOT_DIR / "BotWorldPopulationMgrValidationRouteRuntime.cpp"
UPDATE = BOT_DIR / "BotWorldPopulationMgrUpdate.cpp"
NATIVE_ACTION = BOT_DIR / "BotWorldPopulationMgrNativeAction.cpp"
MOVEMENT = BOT_DIR / "BotWorldPopulationMgrMovement.cpp"
MAGMAW_MOVEMENT_ADAPTER = (
    BOT_DIR
    / "Content/Raids/BlackwingDescent/Encounters/Magmaw"
    / "BotMagmawMovementKernelAdapter.cpp"
)
BOT_STATE = BOT_DIR / "BotWorldPopulationMgrBotState.h"
MANAGER = BOT_DIR / "BotWorldPopulationMgr.h"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


HARNESS = r"""
#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotNativeActionIntent.h"

#include <cassert>
#include <cmath>
#include <string>
#include <utility>

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
    NativePathProofObservation completeInadmissible;
    completeInadmissible.Available = true;
    completeInadmissible.Calculated = true;
    completeInadmissible.Complete = true;
    assert(ClassifyPrimaryDisposition(completeInadmissible, false, false)
        == PrimaryDisposition::CompleteTerminal);
    assert(std::string(PrimaryDispositionName(
        PrimaryDisposition::CompleteTerminal)) == "complete_terminal");

    NativePathProofObservation incompleteEligible;
    incompleteEligible.Available = true;
    incompleteEligible.Calculated = true;
    incompleteEligible.Complete = false;
    assert(ClassifyPrimaryDisposition(incompleteEligible, true, false)
        == PrimaryDisposition::IncompleteFallbackEligible);
    assert(std::string(PrimaryDispositionName(
        PrimaryDisposition::IncompleteFallbackEligible))
        == "incomplete_fallback_eligible");
    assert(ClassifyPrimaryDisposition(incompleteEligible, true, true)
        == PrimaryDisposition::Forbidden);
    assert(std::string(PrimaryDispositionName(
        PrimaryDisposition::Forbidden)) == "forbidden");

    BotNativeAction::Intent annotated = BotNativeAction::WithMovementReason(
        BotNativeAction::Move{1.0f, 2.0f, 3.0f}, "pincer_preposition");
    auto const* annotatedMove = std::get_if<BotNativeAction::Move>(&annotated);
    assert(annotatedMove);
    assert(annotatedMove->IntentReason == "pincer_preposition");

    annotated = BotNativeAction::WithMovementDiagnosticCandidateKey(
        std::move(annotated), "scope:adaptive_magmaw:pillar_bait_switch:300:7");
    annotatedMove = std::get_if<BotNativeAction::Move>(&annotated);
    assert(annotatedMove && annotatedMove->DiagnosticCandidateKey
        == "scope:adaptive_magmaw:pillar_bait_switch:300:7");

    MovementPlannerDiagnosticSidecar sidecar;
    Intent keyedRequest;
    keyedRequest.X = 1.0f;
    keyedRequest.Y = 2.0f;
    keyedRequest.Z = 3.0f;
    keyedRequest.Owner = BotMovementArbitration::Owner::Hazard;
    keyedRequest.Priority = BotMovementArbitration::Priority::Hazard;
    keyedRequest.IntentReason = "pillar_bait_switch";
    CopyMovementDiagnosticCandidateKey(keyedRequest,
        annotatedMove->DiagnosticCandidateKey);
    BotMovementArbitration::Scope receiptScope{ 9, 2, 4, 669, 31 };
    std::uint64_t keyedReceipt = sidecar.BeginReceipt(30100, 669,
        keyedRequest, receiptScope, 0, 0.0f, 0.0f, 0.0f);
    MovementPlannerObservation keyed = sidecar.Latest(30100);
    assert(keyed.LaunchReceipt.Id == keyedReceipt);
    assert(keyed.LaunchReceipt.DiagnosticCandidateKey
        == keyedRequest.DiagnosticCandidateKey);
    std::uint64_t const keyedFingerprint =
        keyed.LaunchReceipt.IntentFingerprint;
    sidecar.RecordDiagnosticTarget(keyedReceipt, 30100, 669, 99001);
    keyed = sidecar.ForReceipt(keyedReceipt);
    assert(keyed.LaunchReceipt.DiagnosticTargetGuid == 99001);
    assert(keyed.LaunchReceipt.IntentFingerprint == keyedFingerprint);
    std::string keyedJson = MovementPlannerObservationJson(keyed);
    assert(keyedJson.find("\"diagnostic_candidate_key\":\"scope:adaptive_magmaw")
        != std::string::npos);
    assert(keyedJson.find("\"diagnostic_target_guid\":99001")
        != std::string::npos);

    Intent laterRequest = keyedRequest;
    laterRequest.X = 9.0f;
    std::uint64_t laterReceipt = sidecar.BeginReceipt(30100, 669,
        laterRequest, receiptScope, 0, 0.0f, 0.0f, 0.0f);
    assert(laterReceipt != keyedReceipt);
    assert(sidecar.Latest(30100).LaunchReceipt.Id == laterReceipt);
    MovementPlannerObservation exactReceipt = sidecar.ForReceipt(keyedReceipt);
    assert(exactReceipt.Available);
    assert(exactReceipt.LaunchReceipt.Id == keyedReceipt);
    assert(exactReceipt.RequestedX == 1.0f);
    assert(!sidecar.ForReceipt(999999).Available);

    Intent otherKeyRequest = keyedRequest;
    CopyMovementDiagnosticCandidateKey(otherKeyRequest,
        "different-diagnostic-key");
    sidecar.BeginReceipt(30101, 669, otherKeyRequest, receiptScope, 0,
        0.0f, 0.0f, 0.0f);
    assert(sidecar.Latest(30101).LaunchReceipt.IntentFingerprint
        == keyed.LaunchReceipt.IntentFingerprint);
    Intent emptyKeyRequest = keyedRequest;
    CopyMovementDiagnosticCandidateKey(emptyKeyRequest, {});
    sidecar.BeginReceipt(30102, 669, emptyKeyRequest, receiptScope, 0,
        0.0f, 0.0f, 0.0f);
    assert(sidecar.Latest(30102).LaunchReceipt.DiagnosticCandidateKey.empty());
    assert(sidecar.Latest(30102).LaunchReceipt.IntentFingerprint
        == keyed.LaunchReceipt.IntentFingerprint);

    // A rejected hazard receipt is evidence in its own right. A later
    // same-tick ordinary candidate may become Latest, but cannot displace the
    // exact rejected hazard from the next published trace row.
    Intent hazardRequest = keyedRequest;
    hazardRequest.X = 8.0f;
    hazardRequest.Y = 0.0f;
    hazardRequest.Z = 210.0f;
    hazardRequest.IntentReason = "parasite_contact_evade";
    hazardRequest.HazardEscape = HazardEscapeBasis{
        9001, -5.0f, 0.0f, 210.0f };
    CopyMovementDiagnosticCandidateKey(hazardRequest,
        "scope:adaptive_magmaw:parasite_contact_evade:30010:17");
    std::uint64_t hazardReceipt = sidecar.BeginReceipt(30010, 669,
        hazardRequest, receiptScope, 0, 0.0f, 0.0f, 210.0f);
    PathPlan rejectedPlan;
    rejectedPlan.LaunchReceiptId = hazardReceipt;
    rejectedPlan.HazardEscapeProgress = HazardEscapeProgressObservation{
        true, 9001, -5.0f, 0.0f, 210.0f, 210.0f, true, 5.0f,
        7.0f, 0.0f, 210.0f, 12.0f, 7.0f, 1.0f,
        "primary_native_actual_endpoint", false };
    NativePathProofObservation rejectedProof;
    rejectedProof.Available = true;
    rejectedProof.Calculated = true;
    rejectedProof.Complete = true;
    rejectedProof.EndpointX = 7.0f;
    rejectedProof.EndpointY = 0.0f;
    rejectedProof.EndpointZ = 210.0f;
    rejectedProof.EndpointFloorValid = true;
    rejectedProof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::None, 0, 0, 7.0f, 0.0f, 210.0f,
        210.0f, 210.0f);
    sidecar.RecordPlannerOutcome(hazardReceipt, 30010, 669, hazardRequest,
        true, 210.0f, true, "path_admission", false,
        "route_destination_endpoint_mismatch", rejectedPlan,
        &rejectedProof, nullptr, PrimaryDisposition::CompleteTerminal,
        &rejectedProof, false);
    sidecar.FinalizeExecutor(30010, 669, hazardRequest,
        "planner_admission", "rejected",
        "route_destination_endpoint_mismatch", hazardReceipt);

    Intent ordinaryRequest = keyedRequest;
    ordinaryRequest.Owner = BotMovementArbitration::Owner::Formation;
    ordinaryRequest.IntentReason = "ranged_formation_restore";
    ordinaryRequest.X = 2.0f;
    std::uint64_t ordinaryReceipt = sidecar.BeginReceipt(30010, 669,
        ordinaryRequest, receiptScope, 0, 0.0f, 0.0f, 210.0f);
    assert(sidecar.Latest(30010).LaunchReceipt.Id == ordinaryReceipt);
    sidecar.AssociateTrace(30010, 10);
    MovementPlannerObservation retainedHazard = sidecar.ForTrace(30010, 10);
    assert(retainedHazard.LaunchReceipt.Id == hazardReceipt);
    assert(retainedHazard.LaunchReceipt.DiagnosticCandidateKey
        == hazardRequest.DiagnosticCandidateKey);
    assert(retainedHazard.HazardEscape->HazardGuid == 9001);
    assert(retainedHazard.HazardEscapeProgress.HazardGuid == 9001);
    assert(retainedHazard.HazardEscapeProgress.EndpointX == 7.0f);
    assert(retainedHazard.Reason == "route_destination_endpoint_mismatch");
    std::string retainedHazardJson = MovementPlannerObservationJson(
        retainedHazard);
    assert(retainedHazardJson.find("\"request\":{\"map\":669,\"x\":8")
        != std::string::npos);
    assert(retainedHazardJson.find("\"primary_resolved_endpoint\":{\"x\":7")
        != std::string::npos);
    assert(retainedHazardJson.find("\"basis_progress_guid_match\":true")
        != std::string::npos);
    assert(retainedHazardJson.find("route_destination_endpoint_mismatch")
        != std::string::npos);
    sidecar.AssociateTrace(30010, 11);
    assert(sidecar.ForTrace(30010, 11).LaunchReceipt.Id == ordinaryReceipt);

    sidecar.Record(InvalidFloor());
    std::string invalidFloorJson = MovementPlannerObservationJson(
        sidecar.Latest(30001));
    assert(invalidFloorJson.find("\"result\":\"rejected\"") != std::string::npos);
    assert(invalidFloorJson.find("route_destination_invalid_floor") != std::string::npos);
    assert(invalidFloorJson.find("\"map\":669") != std::string::npos);
    assert(invalidFloorJson.find("\"x\":-345.872") != std::string::npos);
    assert(invalidFloorJson.find("\"sampled\":true") != std::string::npos);
    assert(invalidFloorJson.find("\"z\":null") != std::string::npos);
    assert(invalidFloorJson.find(
        "\"primary_path\":{\"disposition\":\"forbidden\"")
        != std::string::npos);
    assert(invalidFloorJson.find("\"local_fallback_attempted\":false")
        != std::string::npos);

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
    success.NativeProof.Available = true;
    success.NativeProof.Calculated = true;
    success.NativeProof.PathType = 1;
    success.NativeProof.Complete = true;
    RecordNativePathEndpointResolution(success.NativeProof,
        PathEndpointResult::ReachedRequested, true, true,
        -333.0f, -99.0f, 214.091f, 0.0f, 0.0f);
    success.NativeProof.EndpointX = -333.0f;
    success.NativeProof.EndpointY = -99.0f;
    success.NativeProof.EndpointZ = 214.091f;
    success.NativeProof.EndpointDistance = 0.0633392f;
    success.NativeProof.EndpointHorizontalDistance = 0.0f;
    success.NativeProof.EndpointVerticalDistance = 0.0633392f;
    success.NativeProof.EndpointMatched = true;
    success.NativeProof.EndpointFloorValid = true;
    success.NativeProof.FloorObservation = MakeNativePathFloorObservation(
        NativePathFloorFailure::SampleFloorGap, 4, 7,
        -340.0f, -105.0f, 214.1f, 219.0f, 214.154f);
    success.NativeProof.FloorObservationConflict = true;
    success.NativeProof.Accepted = true;
    success.PrimaryPathDisposition = PrimaryDisposition::CompleteTerminal;
    success.PrimaryNativeProof = success.NativeProof;
    success.PrimaryNativeProof.Accepted = false;
    success.LocalFallbackAttempted = false;
    success.FinalTraversalMode = "native_complete_path";
    sidecar.Record(success);
    sidecar.AssociateTrace(30001, 2);
    assert(sidecar.Latest(30001).Result == "accepted");
    std::string proofJson = MovementPlannerObservationJson(
        sidecar.Latest(30001));
    assert(proofJson.find("\"native_proof\":{\"available\":true")
        != std::string::npos);
    assert(proofJson.find(
        "\"primary_path\":{\"disposition\":\"complete_terminal\"")
        != std::string::npos);
    assert(proofJson.find("\"local_fallback_attempted\":false")
        != std::string::npos);
    assert(proofJson.find(
        "\"final_traversal_mode\":\"native_complete_path\"")
        != std::string::npos);
    assert(proofJson.find("\"endpoint\":{\"x\":-333")
        != std::string::npos);
    assert(proofJson.find(
        "\"endpoint_resolution\":{\"outcome\":\"reached_requested\"")
        != std::string::npos);
    assert(proofJson.find("\"corridor_reached_end_poly\":true")
        != std::string::npos);
    assert(proofJson.find("\"actual_matched\":true")
        != std::string::npos);
    assert(proofJson.find("\"distance\":0.0633392")
        != std::string::npos);
    assert(proofJson.find("\"horizontal_distance\":0")
        != std::string::npos);
    assert(proofJson.find("\"vertical_distance\":0.0633392")
        != std::string::npos);
    assert(proofJson.find("\"vertical_tolerance\":1.5")
        != std::string::npos);
    assert(proofJson.find("\"failure\":\"sample_floor_gap\"")
        != std::string::npos);
    assert(proofJson.find("\"floor_observation_conflict\":true")
        != std::string::npos);
    assert(proofJson.find("\"accepted\":true") != std::string::npos);
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
            "-I",
            str(ROOT / "dep/g3dlite/include"),
            str(harness),
            str(SOURCE),
            str(JSON_SOURCE),
            str(RETENTION_SOURCE),
            str(PROGRESS_SOURCE),
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
    magmaw_movement_adapter = MAGMAW_MOVEMENT_ADAPTER.read_text(
        encoding="utf-8"
    )
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
    assert "NativePathProofObservation" in planner
    assert "DiagnoseCompleteNativePathProof" in planner
    assert "NativePathFloorObservationBlocksCompleteProof" in planner
    assert "primaryNativeProof = nativeProof" in planner
    assert "ClassifyPrimaryDisposition" in planner
    assert "localFallbackAttempted = true" in planner
    assert "primaryDisposition, &primaryNativeProof" in planner
    assert "segmentX = verifiedMainEndpoint.x" in planner
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
    assert "CopyMovementDiagnosticCandidateKey(intent," in movement
    assert (
        "LegacyMagmawMovementDiagnosticCandidateKey"
        in magmaw_movement_adapter
    )
    assert "WithMovementDiagnosticCandidateKey" in magmaw_movement_adapter
    assert "WithMovementReason" in magmaw_movement_adapter
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


def test_candidate_key_is_diagnostic_only() -> None:
    source = SOURCE.read_text(encoding="utf-8")
    fingerprint = source.split("std::uint64_t MovementIntentFingerprint(", 1)[1]
    fingerprint = fingerprint.split("}\n}\nnamespace BotWorldMovement", 1)[0]
    assert "DiagnosticCandidateKey" not in fingerprint

    behavior_sources = (
        PLANNER,
        EXECUTOR,
        BOT_DIR / "BotWorldPopulationMgrMovementLease.cpp",
        BOT_DIR / "BotMovementArbiter.h",
    )
    for path in behavior_sources:
        assert "DiagnosticCandidateKey" not in path.read_text(encoding="utf-8")


def test_sidecar_is_not_in_central_state_and_is_registered():
    assert "MovementPlannerDiagnostics" not in BOT_STATE.read_text(encoding="utf-8")
    assert "MovementPlannerDiagnostics" not in MANAGER.read_text(encoding="utf-8")
    cmake = CMAKE.read_text(encoding="utf-8")
    assert "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.cpp" in cmake
    assert "Bots/BotWorldPopulationMgrMovementPlannerDiagnosticsJson.cpp" in cmake


def test_sidecar_and_related_sources_stay_bounded():
    for path in (HEADER, SOURCE, JSON_SOURCE):
        assert len(path.read_text(encoding="utf-8").splitlines()) < 1000


def test_unavailable_json_is_explicit():
    # Keep this assertion close to the contract so a future serializer change
    # cannot silently turn zero defaults into a successful movement result.
    source = SOURCE.read_text(encoding="utf-8")
    assert "available" in source
    assert "unavailable" in HEADER.read_text(encoding="utf-8")

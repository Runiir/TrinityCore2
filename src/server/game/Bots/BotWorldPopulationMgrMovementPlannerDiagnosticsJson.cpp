#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"
#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"

#include <iomanip>
#include <limits>
#include <sstream>

namespace
{
char const* MovementOwnerName(BotMovementArbitration::Owner owner)
{
    switch (owner)
    {
        case BotMovementArbitration::Owner::None: return "none";
        case BotMovementArbitration::Owner::Route: return "route";
        case BotMovementArbitration::Owner::Formation: return "formation";
        case BotMovementArbitration::Owner::CombatRange: return "combat_range";
        case BotMovementArbitration::Owner::Support: return "support";
        case BotMovementArbitration::Owner::Mechanic: return "mechanic";
        case BotMovementArbitration::Owner::Hazard: return "hazard";
        case BotMovementArbitration::Owner::Recovery: return "recovery";
    }
    return "unknown";
}

std::string JsonEscape(std::string const& value)
{
    std::ostringstream escaped;
    for (char character : value)
    {
        switch (character)
        {
            case '\\': escaped << "\\\\"; break;
            case '"': escaped << "\\\""; break;
            case '\n': escaped << "\\n"; break;
            case '\r': escaped << "\\r"; break;
            case '\t': escaped << "\\t"; break;
            default: escaped << character; break;
        }
    }
    return escaped.str();
}

void AppendPositionJson(std::ostringstream& json,
    BotWorldMovement::NativePathPosition const& position)
{
    json << "{\"available\":" << (position.Available ? "true" : "false")
         << ",\"coordinate_space\":\""
         << JsonEscape(position.CoordinateSpace) << "\",\"x\":";
    if (position.Available)
        json << position.X;
    else
        json << "null";
    json << ",\"y\":";
    if (position.Available)
        json << position.Y;
    else
        json << "null";
    json << ",\"z\":";
    if (position.Available)
        json << position.Z;
    else
        json << "null";
    json << "}";
}

void AppendControlsJson(std::ostringstream& json,
    BotWorldMovement::NativePathControlSequence const& sequence)
{
    json << "{\"available\":" << (sequence.Available ? "true" : "false")
         << ",\"coordinate_space\":\""
         << JsonEscape(sequence.CoordinateSpace) << "\",\"count\":"
         << sequence.ControlCount << ",\"fingerprint\":\"" << std::hex
         << std::setw(16) << std::setfill('0') << sequence.Fingerprint
         << std::dec << std::setfill(' ') << "\"}";
}

void AppendNativeProofJson(std::ostringstream& json,
    BotWorldMovement::NativePathProofObservation const& proof)
{
    json << "{\"available\":" << (proof.Available ? "true" : "false")
         << ",\"calculated\":" << (proof.Calculated ? "true" : "false")
         << ",\"path_type\":" << proof.PathType
         << ",\"complete\":" << (proof.Complete ? "true" : "false")
         << ",\"endpoint_resolution\":{\"outcome\":\""
         << PathEndpointResultName(proof.EndpointResult)
         << "\",\"corridor_reached_end_poly\":"
         << (proof.CorridorReachedEndPoly ? "true" : "false")
         << ",\"resolved\":{\"available\":"
         << (proof.ResolvedEndpointAvailable ? "true" : "false")
         << ",\"x\":";
    if (proof.ResolvedEndpointAvailable)
        json << proof.ResolvedEndpointX;
    else
        json << "null";
    json << ",\"y\":";
    if (proof.ResolvedEndpointAvailable)
        json << proof.ResolvedEndpointY;
    else
        json << "null";
    json << ",\"z\":";
    if (proof.ResolvedEndpointAvailable)
        json << proof.ResolvedEndpointZ;
    else
        json << "null";
    json << "},\"actual_horizontal_distance\":"
         << proof.ResolvedEndpointHorizontalDistance
         << ",\"actual_vertical_distance\":"
         << proof.ResolvedEndpointVerticalDistance
         << ",\"actual_matched\":"
         << (proof.ActualEndpointMatchedResolved ? "true" : "false")
         << "},\"endpoint\":{\"x\":" << proof.EndpointX
         << ",\"y\":" << proof.EndpointY << ",\"z\":" << proof.EndpointZ
         << ",\"distance\":" << proof.EndpointDistance
         << ",\"horizontal_distance\":"
         << proof.EndpointHorizontalDistance
         << ",\"vertical_distance\":" << proof.EndpointVerticalDistance
         << ",\"horizontal_tolerance\":"
         << BotWorldMovement::NativePathEndpointHorizontalTolerance
         << ",\"vertical_tolerance\":"
         << BotWorldMovement::NativePathEndpointVerticalTolerance
         << ",\"matched\":" << (proof.EndpointMatched ? "true" : "false")
         << ",\"floor_valid\":"
         << (proof.EndpointFloorValid ? "true" : "false")
         << "},\"floor_observation\":{\"failure\":\""
         << BotWorldMovement::NativePathFloorFailureName(
                proof.FloorObservation.Failure)
         << "\",\"segment_index\":" << proof.FloorObservation.SegmentIndex
         << ",\"sample_index\":" << proof.FloorObservation.SampleIndex
         << ",\"x\":" << proof.FloorObservation.X
         << ",\"y\":" << proof.FloorObservation.Y
         << ",\"z\":" << proof.FloorObservation.Z
         << ",\"resolved_floor_z\":" << proof.FloorObservation.ResolvedFloorZ
         << ",\"reference_z\":" << proof.FloorObservation.ReferenceZ
         << "},\"floor_observation_conflict\":"
         << (proof.FloorObservationConflict ? "true" : "false")
         << ",\"accepted\":" << (proof.Accepted ? "true" : "false")
         << "}";
}
}

namespace BotWorldMovement
{
std::string MovementPlannerObservationJson(
    MovementPlannerObservation const& observation)
{
    std::ostringstream json;
    json << std::setprecision(std::numeric_limits<float>::max_digits10);
    json << "{\"available\":" << (observation.Available ? "true" : "false")
         << ",\"bot_guid\":" << observation.BotGuid
         << ",\"owner\":\"" << JsonEscape(
                MovementOwnerName(observation.MovementOwner)) << "\""
         << ",\"intent_reason\":\""
         << JsonEscape(observation.IntentReason) << "\""
         << ",\"request\":{\"map\":" << observation.RequestedMapId
         << ",\"x\":" << observation.RequestedX
         << ",\"y\":" << observation.RequestedY
         << ",\"z\":" << observation.RequestedZ << "}"
         << ",\"target_floor\":{\"sampled\":"
         << (observation.TargetFloorSampled ? "true" : "false")
         << ",\"z\":";
    if (observation.TargetFloorSampled && observation.TargetFloorValid)
        json << observation.TargetFloorZ;
    else
        json << "null";
    json << ",\"valid\":"
         << (observation.TargetFloorValid ? "true" : "false") << "}"
         << ",\"z_delta\":{\"available\":"
         << (observation.ZDeltaAvailable ? "true" : "false")
         << ",\"absolute\":";
    if (observation.ZDeltaAvailable)
        json << observation.AbsoluteZDelta;
    else
        json << "null";
    json << ",\"threshold\":" << observation.ZDeltaThreshold << "}"
         << ",\"flags\":{\"progressive\":"
         << (observation.AllowProgressiveSegments ? "true" : "false")
         << ",\"complete_path\":"
         << (observation.RequireCompletePath ? "true" : "false")
         << ",\"native_long_path\":"
         << (observation.AllowNativeLongPath ? "true" : "false")
         << ",\"dynamic_target\":"
         << (observation.DynamicTarget ? "true" : "false") << "}"
         << ",\"primary_path\":{\"disposition\":\""
         << PrimaryDispositionName(observation.PrimaryPathDisposition)
         << "\",\"proof\":";
    AppendNativeProofJson(json, observation.PrimaryNativeProof);
    json << "},\"native_proof\":";
    AppendNativeProofJson(json, observation.NativeProof);
    json << ",\"local_fallback_attempted\":"
         << (observation.LocalFallbackAttempted ? "true" : "false")
         << ",\"final_traversal_mode\":\""
         << JsonEscape(observation.FinalTraversalMode) << "\""
         << ",\"planner\":{\"gate\":\""
         << JsonEscape(observation.PlannerGate)
         << "\",\"result\":\""
         << JsonEscape(observation.PlannerResult)
         << "\",\"reason\":\""
         << JsonEscape(observation.PlannerReason) << "\"}"
         << ",\"launch_receipt\":{\"version\":"
         << observation.LaunchReceipt.Version << ",\"id\":"
         << observation.LaunchReceipt.Id
         << ",\"identity\":{\"bot_guid\":" << observation.BotGuid
         << ",\"diagnostic_candidate_key\":\""
         << JsonEscape(observation.LaunchReceipt.DiagnosticCandidateKey)
         << "\""
         << ",\"map\":" << observation.RequestedMapId
         << ",\"owner\":\""
         << JsonEscape(MovementOwnerName(observation.MovementOwner))
         << "\",\"intent_reason\":\""
         << JsonEscape(observation.IntentReason)
         << "\",\"intent_fingerprint\":\"" << std::hex
         << std::setw(16) << std::setfill('0')
         << observation.LaunchReceipt.IntentFingerprint << std::dec
         << std::setfill(' ')
         << "\",\"dynamic_target_guid\":"
         << observation.LaunchReceipt.DynamicTargetGuid
         << ",\"progress_capture_enabled\":"
         << (observation.LaunchReceipt.ProgressCaptureEnabled
                ? "true" : "false")
         << ",\"scope\":{\"attempt_id\":"
         << observation.LaunchReceipt.Scope.AttemptId
         << ",\"wipe_generation\":"
         << observation.LaunchReceipt.Scope.WipeGeneration
         << ",\"route_generation\":"
         << observation.LaunchReceipt.Scope.RouteGeneration
         << ",\"map\":" << observation.LaunchReceipt.Scope.MapId
         << ",\"instance\":"
         << observation.LaunchReceipt.Scope.InstanceId << "}}"
         << ",\"primary_path\":{\"disposition\":\""
         << PrimaryDispositionName(
                observation.LaunchReceipt.PrimaryPathDisposition)
         << "\",\"proof\":";
    AppendNativeProofJson(json,
        observation.LaunchReceipt.PrimaryNativeProof);
    json << "},\"local_fallback_attempted\":"
         << (observation.LaunchReceipt.LocalFallbackAttempted
                ? "true" : "false")
         << ",\"final_traversal_mode\":\""
         << JsonEscape(observation.LaunchReceipt.FinalTraversalMode) << "\""
         << ",\"actor_before_planning\":";
    AppendPositionJson(json, observation.LaunchReceipt.ActorBeforePlanning);
    json << ",\"planner_path\":{\"calculated\":"
         << (observation.NativeProof.Calculated ? "true" : "false")
         << ",\"type\":" << observation.NativeProof.PathType
         << ",\"complete\":"
         << (observation.NativeProof.Complete ? "true" : "false")
         << ",\"controls\":";
    AppendControlsJson(json, observation.LaunchReceipt.PlannerControls);
    json << ",\"selected_endpoint\":{\"available\":"
         << (observation.LaunchReceipt.PlannerSelectedEndpointAvailable
                ? "true" : "false")
         << ",\"x\":" << observation.LaunchReceipt.PlannerSelectedX
         << ",\"y\":" << observation.LaunchReceipt.PlannerSelectedY
         << ",\"z\":" << observation.LaunchReceipt.PlannerSelectedZ
         << "},\"floor_observation\":{\"failure\":\""
         << NativePathFloorFailureName(
                observation.NativeProof.FloorObservation.Failure)
         << "\",\"segment_index\":"
         << observation.NativeProof.FloorObservation.SegmentIndex
         << ",\"sample_index\":"
         << observation.NativeProof.FloorObservation.SampleIndex
         << ",\"x\":" << observation.NativeProof.FloorObservation.X
         << ",\"y\":" << observation.NativeProof.FloorObservation.Y
         << ",\"z\":" << observation.NativeProof.FloorObservation.Z
         << ",\"resolved_floor_z\":"
         << observation.NativeProof.FloorObservation.ResolvedFloorZ
         << ",\"reference_z\":"
         << observation.NativeProof.FloorObservation.ReferenceZ
         << "},\"floor_observation_conflict\":"
         << (observation.NativeProof.FloorObservationConflict
                ? "true" : "false") << "}"
         << ",\"executor\":{\"requested\":{\"x\":"
         << observation.RequestedX << ",\"y\":"
         << observation.RequestedY << ",\"z\":"
         << observation.RequestedZ << "},\"selected\":{\"available\":"
         << (observation.LaunchReceipt.ExecutorDestinationAvailable
                ? "true" : "false")
         << ",\"x\":" << observation.LaunchReceipt.ExecutorSelectedX
         << ",\"y\":" << observation.LaunchReceipt.ExecutorSelectedY
         << ",\"z\":" << observation.LaunchReceipt.ExecutorSelectedZ
         << "},\"generate_path\":"
         << (observation.LaunchReceipt.PointGeneratePath ? "true" : "false")
         << ",\"actor_before_submission\":";
    AppendPositionJson(json,
        observation.LaunchReceipt.ActorBeforeNativeSubmission);
    json << "},\"motion_master\":{\"observed\":"
         << (observation.LaunchReceipt.MotionMasterSubmissionObserved
                ? "true" : "false")
         << ",\"slot\":" << observation.LaunchReceipt.MotionMasterSlot
         << ",\"generator_type\":"
         << observation.LaunchReceipt.MotionMasterGeneratorType
         << ",\"point_generator_initialized\":"
         << (observation.LaunchReceipt.PointGeneratorInitialized
                ? "true" : "false")
         << "},\"launches\":[";
    for (std::size_t index = 0;
        index < observation.LaunchReceipt.Launches.size(); ++index)
    {
        if (index)
            json << ',';
        NativeSplineLaunchObservation const& launch =
            observation.LaunchReceipt.Launches[index];
        json << "{\"ordinal\":" << (index + 1)
             << ",\"second_path\":{\"attempted\":"
             << (launch.SecondPathAttempted ? "true" : "false")
             << ",\"calculated\":"
             << (launch.SecondPathCalculated ? "true" : "false")
             << ",\"type\":" << launch.SecondPathType
             << ",\"controls\":";
        AppendControlsJson(json, launch.SecondPathControls);
        json << "},\"direct_two_point_selected\":"
             << (launch.DirectTwoPointSelected ? "true" : "false")
             << ",\"direct_two_point_fallback\":"
             << (launch.DirectTwoPointFallback ? "true" : "false")
             << ",\"spline_launch\":{\"attempted\":"
             << (launch.LaunchAttempted ? "true" : "false")
             << ",\"succeeded\":"
             << (launch.LaunchSucceeded ? "true" : "false")
             << ",\"spline_id\":" << launch.SplineId
             << ",\"finalized_after_launch\":"
             << (launch.SplineFinalizedAfterLaunch ? "true" : "false")
             << ",\"controls\":";
        AppendControlsJson(json, launch.LaunchedControls);
        json << ",\"actor_after_launch\":";
        AppendPositionJson(json, launch.ActorAfterLaunch);
        json << "}}";
    }
    json << "],\"launch_attempt_capacity\":"
         << NativePathLaunchReceipt::MaxLaunchAttempts
         << ",\"launch_attempt_overflow_count\":"
         << observation.LaunchReceipt.LaunchAttemptOverflowCount
         << ",\"progress\":"
         << MovementProgressObservationJson(
                MovementProgressDiagnostics().ForReceipt(
                    observation.LaunchReceipt.Id)) << "}"
         << ",\"gate\":\"" << JsonEscape(observation.Gate)
         << "\",\"result\":\"" << JsonEscape(observation.Result)
         << "\",\"reason\":\"" << JsonEscape(observation.Reason)
         << "\"}";
    return json.str();
}
}

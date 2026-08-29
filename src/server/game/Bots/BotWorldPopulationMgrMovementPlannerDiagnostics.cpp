#include "Bots/BotWorldPopulationMgrMovementPlannerDiagnostics.h"

#include <cmath>
#include <sstream>
#include <utility>

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
}

namespace BotWorldMovement
{
void MovementPlannerDiagnosticSidecar::Record(
    MovementPlannerObservation observation)
{
    if (!observation.BotGuid)
        return;

    observation.Available = true;
    _latestByGuid[observation.BotGuid] = std::move(observation);
    _pendingByGuid[observation.BotGuid] = true;
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
    char const* gate, char const* result, char const* reason)
{
    if (!botGuid)
        return;

    MovementPlannerObservation observation = Latest(botGuid);
    auto pending = _pendingByGuid.find(botGuid);
    bool const hasPendingPlanner = pending != _pendingByGuid.end()
        && pending->second;
    if (!hasPendingPlanner
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
    _latestByGuid.erase(botGuid);
    _pendingByGuid.erase(botGuid);
    _traceByGuid.erase(botGuid);
}

void MovementPlannerDiagnosticSidecar::ClearAll()
{
    _latestByGuid.clear();
    _pendingByGuid.clear();
    _traceByGuid.clear();
}

MovementPlannerDiagnosticSidecar& MovementPlannerDiagnostics()
{
    static MovementPlannerDiagnosticSidecar sidecar;
    return sidecar;
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
    char const* result, char const* reason)
{
    MovementPlannerDiagnostics().FinalizeExecutor(botGuid, requestedMapId,
        intent, gate, result, reason);
}

std::string MovementPlannerObservationJson(
    MovementPlannerObservation const& observation)
{
    std::ostringstream json;
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
         << ",\"native_proof\":{\"available\":"
         << (observation.NativeProof.Available ? "true" : "false")
         << ",\"calculated\":"
         << (observation.NativeProof.Calculated ? "true" : "false")
         << ",\"path_type\":" << observation.NativeProof.PathType
         << ",\"complete\":"
         << (observation.NativeProof.Complete ? "true" : "false")
         << ",\"endpoint\":{\"x\":"
         << observation.NativeProof.EndpointX << ",\"y\":"
         << observation.NativeProof.EndpointY << ",\"z\":"
         << observation.NativeProof.EndpointZ << ",\"distance\":"
         << observation.NativeProof.EndpointDistance << ",\"matched\":"
         << (observation.NativeProof.EndpointMatched ? "true" : "false")
         << ",\"floor_valid\":"
         << (observation.NativeProof.EndpointFloorValid ? "true" : "false")
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
                ? "true" : "false")
         << ",\"accepted\":"
         << (observation.NativeProof.Accepted ? "true" : "false") << "}"
         << ",\"planner\":{\"gate\":\""
         << JsonEscape(observation.PlannerGate)
         << "\",\"result\":\""
         << JsonEscape(observation.PlannerResult)
         << "\",\"reason\":\""
         << JsonEscape(observation.PlannerReason) << "\"}"
         << ",\"gate\":\"" << JsonEscape(observation.Gate)
         << "\",\"result\":\"" << JsonEscape(observation.Result)
         << "\",\"reason\":\"" << JsonEscape(observation.Reason)
         << "\"}";
    return json.str();
}
}

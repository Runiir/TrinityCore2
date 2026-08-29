#include "Bots/BotWorldPopulationMgrMovementProgressDiagnostics.h"

#include <cmath>
#include <iomanip>
#include <limits>
#include <sstream>
#include <utility>

namespace
{
float Distance3d(float ax, float ay, float az, float bx, float by, float bz)
{
    float const dx = ax - bx;
    float const dy = ay - by;
    float const dz = az - bz;
    return std::sqrt(dx * dx + dy * dy + dz * dz);
}
}

namespace BotWorldMovement
{
void MovementProgressDiagnosticSidecar::RetainReceipt(
    std::uint64_t botGuid, std::uint64_t receiptId)
{
    auto& receipts = _receiptIdsByGuid[botGuid];
    receipts.push_back(receiptId);
    while (receipts.size() > MaxReceiptsPerBot)
    {
        std::uint64_t const expired = receipts.front();
        receipts.pop_front();
        _byReceipt.erase(expired);
        auto active = _activeReceiptByGuid.find(botGuid);
        if (active != _activeReceiptByGuid.end() && active->second == expired)
            _activeReceiptByGuid.erase(active);
    }
}

void MovementProgressDiagnosticSidecar::Finish(
    NativeMovementProgressObservation& observation, char const* outcome,
    std::uint64_t observedAtMs, std::uint64_t supersededByReceiptId)
{
    observation.Terminal = true;
    observation.TerminalOutcome = outcome ? outcome : "unavailable";
    observation.LastObservedAtMs = observedAtMs;
    observation.SupersededByReceiptId = supersededByReceiptId;
    auto active = _activeReceiptByGuid.find(observation.BotGuid);
    if (active != _activeReceiptByGuid.end()
        && active->second == observation.ReceiptId)
        _activeReceiptByGuid.erase(active);
}

void MovementProgressDiagnosticSidecar::Arm(std::uint64_t receiptId,
    std::uint64_t botGuid, std::uint32_t mapId, std::uint32_t instanceId,
    BotMovementArbitration::Scope const& scope, float selectedX,
    float selectedY, float selectedZ, float launchX, float launchY,
    float launchZ, bool splineInitialized, std::uint32_t splineId,
    float splineFinalX, float splineFinalY, float splineFinalZ,
    std::uint64_t observedAtMs)
{
    if (!receiptId || !botGuid)
        return;

    auto existing = _byReceipt.find(receiptId);
    if (existing != _byReceipt.end())
    {
        NativeMovementProgressObservation& retained = existing->second;
        bool const sameIdentity = retained.BotGuid == botGuid
            && retained.MapId == mapId && retained.InstanceId == instanceId
            && retained.Scope.AttemptId == scope.AttemptId
            && retained.Scope.WipeGeneration == scope.WipeGeneration
            && retained.Scope.RouteGeneration == scope.RouteGeneration
            && retained.SelectedX == selectedX && retained.SelectedY == selectedY
            && retained.SelectedZ == selectedZ
            && retained.LaunchedSplineInitialized == splineInitialized
            && retained.LaunchedSplineId == splineId;
        if (!sameIdentity || retained.Terminal)
            return;
        if (!retained.ArmedAtMs && observedAtMs)
        {
            retained.ArmedAtMs = observedAtMs;
            retained.LastObservedAtMs = observedAtMs;
        }
        _activeReceiptByGuid[botGuid] = receiptId;
        return;
    }

    auto active = _activeReceiptByGuid.find(botGuid);
    if (active != _activeReceiptByGuid.end()
        && active->second != receiptId)
    {
        auto previous = _byReceipt.find(active->second);
        if (previous != _byReceipt.end() && !previous->second.Terminal)
            Finish(previous->second, "superseded_by_native_launch",
                observedAtMs, receiptId);
    }

    NativeMovementProgressObservation observation;
    observation.Available = true;
    observation.ReceiptId = receiptId;
    observation.BotGuid = botGuid;
    observation.MapId = mapId;
    observation.InstanceId = instanceId;
    observation.Scope = scope;
    observation.SelectedX = selectedX;
    observation.SelectedY = selectedY;
    observation.SelectedZ = selectedZ;
    observation.LaunchX = launchX;
    observation.LaunchY = launchY;
    observation.LaunchZ = launchZ;
    observation.LaunchedSplineInitialized = splineInitialized;
    observation.LaunchedSplineId = splineId;
    observation.LaunchedSplineFinalX = splineFinalX;
    observation.LaunchedSplineFinalY = splineFinalY;
    observation.LaunchedSplineFinalZ = splineFinalZ;
    observation.ArmedAtMs = observedAtMs;
    observation.LastObservedAtMs = observedAtMs;
    observation.BestEndpointDistance = Distance3d(launchX, launchY, launchZ,
        selectedX, selectedY, selectedZ);
    observation.BestEndpointDistanceAvailable = true;
    _byReceipt[receiptId] = std::move(observation);
    _activeReceiptByGuid[botGuid] = receiptId;
    RetainReceipt(botGuid, receiptId);
}

void MovementProgressDiagnosticSidecar::Observe(
    NativeMovementProgressProbe const& probe)
{
    auto active = _activeReceiptByGuid.find(probe.BotGuid);
    if (!probe.BotGuid || active == _activeReceiptByGuid.end())
        return;
    auto receipt = _byReceipt.find(active->second);
    if (receipt == _byReceipt.end())
        return;
    NativeMovementProgressObservation& observation = receipt->second;
    if (observation.Terminal)
        return;
    if (!observation.ArmedAtMs)
    {
        observation.ArmedAtMs = probe.ObservedAtMs;
        observation.LastObservedAtMs = probe.ObservedAtMs;
    }

    NativeMovementProgressSample sample;
    sample.ReceiptId = observation.ReceiptId;
    sample.ObservedAtMs = probe.ObservedAtMs;
    sample.ActorAvailable = probe.ActorAvailable;
    sample.ActorInWorld = probe.ActorInWorld;
    sample.ActorAlive = probe.ActorAlive;
    sample.MapId = probe.MapId;
    sample.InstanceId = probe.InstanceId;
    sample.X = probe.X;
    sample.Y = probe.Y;
    sample.Z = probe.Z;
    sample.Moving = probe.Moving;
    sample.FloorSampled = probe.FloorSampled;
    sample.FloorValid = probe.FloorValid;
    sample.FloorZ = probe.FloorZ;
    sample.ActorFloorDelta = probe.FloorValid
        ? std::fabs(probe.Z - probe.FloorZ) : 0.0f;
    sample.SelectedPlatformCompatible = probe.MapId == observation.MapId
        && probe.FloorValid
        && std::fabs(probe.Z - observation.SelectedZ) <= NativeFloorTolerance
        && std::fabs(probe.FloorZ - observation.SelectedZ)
            <= NativeFloorTolerance;
    sample.CurrentMotionType = probe.CurrentMotionType;
    sample.ActiveMotionType = probe.ActiveMotionType;
    sample.PointGeneratorActive = probe.PointGeneratorActive;
    sample.SplineInitialized = probe.SplineInitialized;
    sample.SplineId = probe.SplineId;
    sample.MatchesLaunchedSpline = probe.SplineInitialized
        && observation.LaunchedSplineInitialized
        && probe.SplineId == observation.LaunchedSplineId;
    sample.SplineFinalized = probe.SplineFinalized;
    float const dx = probe.X - observation.SelectedX;
    float const dy = probe.Y - observation.SelectedY;
    sample.EndpointHorizontalDistance = std::sqrt(dx * dx + dy * dy);
    sample.EndpointVerticalDistance = std::fabs(
        probe.Z - observation.SelectedZ);
    sample.EndpointDistance = Distance3d(probe.X, probe.Y, probe.Z,
        observation.SelectedX, observation.SelectedY, observation.SelectedZ);
    sample.EndpointProgressed = !observation.BestEndpointDistanceAvailable
        || sample.EndpointDistance + 0.01f < observation.BestEndpointDistance;
    sample.EndpointReached = NativePathEndpointComponentsMatch(
        sample.EndpointHorizontalDistance, sample.EndpointVerticalDistance);

    bool const expired = probe.ObservedAtMs >= observation.ArmedAtMs
        && probe.ObservedAtMs - observation.ArmedAtMs
            > NativeMovementProgressObservation::MaxLifetimeMs;
    if (!probe.ActorAvailable || !probe.ActorInWorld)
    {
        sample.Terminal = true;
        sample.Outcome = "actor_unavailable";
    }
    else if (probe.MapId != observation.MapId
        || probe.InstanceId != observation.InstanceId)
    {
        sample.Terminal = true;
        sample.Outcome = "map_or_instance_changed";
    }
    else if (!probe.ActorAlive)
    {
        sample.Terminal = true;
        sample.Outcome = "actor_died";
    }
    else if (sample.EndpointReached)
    {
        sample.Terminal = true;
        sample.Outcome = "selected_endpoint_reached";
    }
    else if (probe.SplineInitialized
        && observation.LaunchedSplineInitialized
        && probe.SplineId != observation.LaunchedSplineId)
    {
        sample.Terminal = true;
        sample.Outcome = "native_spline_replaced";
    }
    else if (expired)
    {
        sample.Terminal = true;
        sample.Outcome = "observation_expired";
    }
    else if (!probe.PointGeneratorActive && probe.SplineFinalized)
    {
        sample.Terminal = true;
        sample.Outcome = "native_motion_finished_before_endpoint";
    }
    else
        sample.Outcome = "native_motion_in_progress";

    if (sample.EndpointProgressed)
    {
        observation.BestEndpointDistance = sample.EndpointDistance;
        observation.BestEndpointDistanceAvailable = true;
    }
    observation.LastObservedAtMs = probe.ObservedAtMs;
    if (observation.Samples.size()
        == NativeMovementProgressObservation::MaxSamples)
    {
        observation.Samples.pop_front();
        ++observation.DroppedSampleCount;
    }
    observation.Samples.push_back(sample);
    if (sample.Terminal)
        Finish(observation, sample.Outcome.c_str(), probe.ObservedAtMs);
}

std::uint64_t MovementProgressDiagnosticSidecar::ActiveReceipt(
    std::uint64_t botGuid) const
{
    auto active = _activeReceiptByGuid.find(botGuid);
    return active == _activeReceiptByGuid.end() ? 0 : active->second;
}

bool MovementProgressDiagnosticSidecar::ObservationDue(
    std::uint64_t botGuid, std::uint64_t observedAtMs) const
{
    std::uint64_t const receiptId = ActiveReceipt(botGuid);
    auto receipt = _byReceipt.find(receiptId);
    if (!receiptId || receipt == _byReceipt.end() || receipt->second.Terminal)
        return false;
    return observedAtMs < receipt->second.LastObservedAtMs
        || observedAtMs - receipt->second.LastObservedAtMs
            >= MinProductionSampleIntervalMs;
}

NativeMovementProgressObservation
MovementProgressDiagnosticSidecar::ForReceipt(std::uint64_t receiptId) const
{
    auto receipt = _byReceipt.find(receiptId);
    return receipt == _byReceipt.end()
        ? NativeMovementProgressObservation() : receipt->second;
}

void MovementProgressDiagnosticSidecar::ClearBot(std::uint64_t botGuid)
{
    auto receipts = _receiptIdsByGuid.find(botGuid);
    if (receipts != _receiptIdsByGuid.end())
    {
        for (std::uint64_t receiptId : receipts->second)
            _byReceipt.erase(receiptId);
        _receiptIdsByGuid.erase(receipts);
    }
    _activeReceiptByGuid.erase(botGuid);
}

void MovementProgressDiagnosticSidecar::ClearAll()
{
    _byReceipt.clear();
    _activeReceiptByGuid.clear();
    _receiptIdsByGuid.clear();
}

MovementProgressDiagnosticSidecar& MovementProgressDiagnostics()
{
    static MovementProgressDiagnosticSidecar sidecar;
    return sidecar;
}

std::string MovementProgressObservationJson(
    NativeMovementProgressObservation const& observation)
{
    std::ostringstream json;
    json << std::setprecision(std::numeric_limits<float>::max_digits10);
    json << "{\"available\":" << (observation.Available ? "true" : "false")
         << ",\"receipt_id\":" << observation.ReceiptId
         << ",\"bot_guid\":" << observation.BotGuid
         << ",\"map\":" << observation.MapId
         << ",\"instance\":" << observation.InstanceId
         << ",\"scope\":{\"attempt_id\":" << observation.Scope.AttemptId
         << ",\"wipe_generation\":" << observation.Scope.WipeGeneration
         << ",\"route_generation\":" << observation.Scope.RouteGeneration
         << "},\"selected_endpoint\":{\"x\":" << observation.SelectedX
         << ",\"y\":" << observation.SelectedY
         << ",\"z\":" << observation.SelectedZ << "}"
         << ",\"actor_at_launch\":{\"x\":" << observation.LaunchX
         << ",\"y\":" << observation.LaunchY
         << ",\"z\":" << observation.LaunchZ << "}"
         << ",\"launched_spline\":{\"initialized\":"
         << (observation.LaunchedSplineInitialized ? "true" : "false")
         << ",\"id\":" << observation.LaunchedSplineId
         << ",\"final_destination\":{\"x\":"
         << observation.LaunchedSplineFinalX << ",\"y\":"
         << observation.LaunchedSplineFinalY << ",\"z\":"
         << observation.LaunchedSplineFinalZ << "}}"
         << ",\"armed_at_ms\":" << observation.ArmedAtMs
         << ",\"last_observed_at_ms\":" << observation.LastObservedAtMs
         << ",\"best_endpoint_distance\":";
    if (observation.BestEndpointDistanceAvailable)
        json << observation.BestEndpointDistance;
    else
        json << "null";
    json << ",\"terminal\":" << (observation.Terminal ? "true" : "false")
         << ",\"terminal_outcome\":\"" << observation.TerminalOutcome << "\""
         << ",\"superseded_by_receipt_id\":"
         << observation.SupersededByReceiptId << ",\"samples\":[";
    for (std::size_t index = 0; index < observation.Samples.size(); ++index)
    {
        if (index)
            json << ',';
        NativeMovementProgressSample const& sample = observation.Samples[index];
        json << "{\"receipt_id\":" << sample.ReceiptId
             << ",\"observed_at_ms\":" << sample.ObservedAtMs
             << ",\"actor\":{\"available\":"
             << (sample.ActorAvailable ? "true" : "false")
             << ",\"in_world\":" << (sample.ActorInWorld ? "true" : "false")
             << ",\"alive\":" << (sample.ActorAlive ? "true" : "false")
             << ",\"map\":" << sample.MapId
             << ",\"instance\":" << sample.InstanceId
             << ",\"x\":" << sample.X << ",\"y\":" << sample.Y
             << ",\"z\":" << sample.Z << "}"
             << ",\"floor\":{\"sampled\":"
             << (sample.FloorSampled ? "true" : "false")
             << ",\"valid\":" << (sample.FloorValid ? "true" : "false")
             << ",\"z\":";
        if (sample.FloorValid)
            json << sample.FloorZ;
        else
            json << "null";
        json << ",\"actor_delta\":";
        if (sample.FloorValid)
            json << sample.ActorFloorDelta;
        else
            json << "null";
        json << ",\"selected_platform_compatible\":"
             << (sample.SelectedPlatformCompatible ? "true" : "false") << "}"
             << ",\"native_motion\":{\"moving\":"
             << (sample.Moving ? "true" : "false")
             << ",\"current_type\":" << sample.CurrentMotionType
             << ",\"active_type\":" << sample.ActiveMotionType
             << ",\"point_generator_active\":"
             << (sample.PointGeneratorActive ? "true" : "false")
             << ",\"spline_initialized\":"
             << (sample.SplineInitialized ? "true" : "false")
             << ",\"spline_id\":" << sample.SplineId
             << ",\"matches_launched_spline\":"
             << (sample.MatchesLaunchedSpline ? "true" : "false")
             << ",\"spline_finalized\":"
             << (sample.SplineFinalized ? "true" : "false") << "}"
             << ",\"endpoint_progress\":{\"horizontal_distance\":"
             << sample.EndpointHorizontalDistance
             << ",\"vertical_distance\":" << sample.EndpointVerticalDistance
             << ",\"distance\":" << sample.EndpointDistance
             << ",\"improved\":"
             << (sample.EndpointProgressed ? "true" : "false")
             << ",\"reached\":"
             << (sample.EndpointReached ? "true" : "false") << "}"
             << ",\"terminal\":" << (sample.Terminal ? "true" : "false")
             << ",\"outcome\":\"" << sample.Outcome << "\"}";
    }
    json << "],\"sample_capacity\":"
         << NativeMovementProgressObservation::MaxSamples
         << ",\"dropped_sample_count\":" << observation.DroppedSampleCount
         << ",\"max_lifetime_ms\":"
         << NativeMovementProgressObservation::MaxLifetimeMs << "}";
    return json.str();
}
}

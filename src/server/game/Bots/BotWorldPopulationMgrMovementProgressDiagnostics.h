#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PROGRESS_DIAGNOSTICS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PROGRESS_DIAGNOSTICS_H

#include "Bots/BotMovementArbiter.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cstddef>
#include <cstdint>
#include <deque>
#include <map>
#include <string>

class Player;

namespace BotWorldMovement
{
struct NativeMovementProgressSample
{
    std::uint64_t ReceiptId = 0;
    std::uint64_t ObservedAtMs = 0;
    bool ActorAvailable = false;
    bool ActorInWorld = false;
    bool ActorAlive = false;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    bool Moving = false;
    bool FloorSampled = false;
    bool FloorValid = false;
    float FloorZ = 0.0f;
    float ActorFloorDelta = 0.0f;
    bool SelectedPlatformCompatible = false;
    std::uint32_t CurrentMotionType = 0;
    std::uint32_t ActiveMotionType = 0;
    bool PointGeneratorActive = false;
    bool SplineInitialized = false;
    std::uint32_t SplineId = 0;
    bool MatchesLaunchedSpline = false;
    bool SplineFinalized = true;
    float EndpointHorizontalDistance = 0.0f;
    float EndpointVerticalDistance = 0.0f;
    float EndpointDistance = 0.0f;
    bool EndpointProgressed = false;
    bool EndpointReached = false;
    bool Terminal = false;
    std::string Outcome = "unavailable";
};

struct NativeMovementProgressObservation
{
    static constexpr std::size_t MaxSamples = 16;
    static constexpr std::uint64_t MaxLifetimeMs = 30000;

    bool Available = false;
    std::uint64_t ReceiptId = 0;
    std::uint64_t BotGuid = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    BotMovementArbitration::Scope Scope;
    float SelectedX = 0.0f;
    float SelectedY = 0.0f;
    float SelectedZ = 0.0f;
    float LaunchX = 0.0f;
    float LaunchY = 0.0f;
    float LaunchZ = 0.0f;
    bool LaunchedSplineInitialized = false;
    std::uint32_t LaunchedSplineId = 0;
    float LaunchedSplineFinalX = 0.0f;
    float LaunchedSplineFinalY = 0.0f;
    float LaunchedSplineFinalZ = 0.0f;
    std::uint64_t ArmedAtMs = 0;
    std::uint64_t LastObservedAtMs = 0;
    float BestEndpointDistance = 0.0f;
    bool BestEndpointDistanceAvailable = false;
    bool Terminal = false;
    std::string TerminalOutcome = "pending";
    std::uint64_t SupersededByReceiptId = 0;
    std::deque<NativeMovementProgressSample> Samples;
    std::size_t DroppedSampleCount = 0;
};

struct NativeMovementProgressProbe
{
    std::uint64_t ObservedAtMs = 0;
    std::uint64_t BotGuid = 0;
    bool ActorAvailable = false;
    bool ActorInWorld = false;
    bool ActorAlive = false;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    bool Moving = false;
    bool FloorSampled = false;
    bool FloorValid = false;
    float FloorZ = 0.0f;
    std::uint32_t CurrentMotionType = 0;
    std::uint32_t ActiveMotionType = 0;
    bool PointGeneratorActive = false;
    bool SplineInitialized = false;
    std::uint32_t SplineId = 0;
    bool SplineFinalized = true;
};

class MovementProgressDiagnosticSidecar final
{
public:
    static constexpr std::size_t MaxReceiptsPerBot = 128;
    static constexpr std::uint64_t MinProductionSampleIntervalMs = 100;

    void Arm(std::uint64_t receiptId, std::uint64_t botGuid,
        std::uint32_t mapId, std::uint32_t instanceId,
        BotMovementArbitration::Scope const& scope, float selectedX,
        float selectedY, float selectedZ, float launchX, float launchY,
        float launchZ, bool splineInitialized, std::uint32_t splineId,
        float splineFinalX, float splineFinalY, float splineFinalZ,
        std::uint64_t observedAtMs);
    void Observe(NativeMovementProgressProbe const& probe);
    std::uint64_t ActiveReceipt(std::uint64_t botGuid) const;
    bool ObservationDue(std::uint64_t botGuid,
        std::uint64_t observedAtMs) const;
    NativeMovementProgressObservation ForReceipt(
        std::uint64_t receiptId) const;
    void ClearBot(std::uint64_t botGuid);
    void ClearAll();

private:
    void RetainReceipt(std::uint64_t botGuid, std::uint64_t receiptId);
    void Finish(NativeMovementProgressObservation& observation,
        char const* outcome, std::uint64_t observedAtMs,
        std::uint64_t supersededByReceiptId = 0);

    std::map<std::uint64_t, NativeMovementProgressObservation> _byReceipt;
    std::map<std::uint64_t, std::uint64_t> _activeReceiptByGuid;
    std::map<std::uint64_t, std::deque<std::uint64_t>> _receiptIdsByGuid;
};

MovementProgressDiagnosticSidecar& MovementProgressDiagnostics();

// This production sampler is observation-only. It reads native player,
// MotionMaster, spline, position, and floor state and appends a value probe;
// it has no access to WorldBotState or movement policy.
void ObserveReceiptTaggedMovementProgress(Player const* bot);

std::string MovementProgressObservationJson(
    NativeMovementProgressObservation const& observation);
}

#endif

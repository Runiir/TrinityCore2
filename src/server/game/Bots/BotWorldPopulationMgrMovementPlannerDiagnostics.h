#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PLANNER_DIAGNOSTICS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PLANNER_DIAGNOSTICS_H

#include "Bots/BotMovementArbiter.h"
#include "Bots/BotWorldPopulationMgrMovement.h"
#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cstddef>
#include <cstdint>
#include <deque>
#include <map>
#include <string>
#include <utility>

namespace BotWorldMovement
{
// This is deliberately outside WorldBotState.  Planner admission is a
// process-local diagnostic concern, while the authoritative movement state
// remains owned by the bot runtime.
struct MovementPlannerObservation
{
    bool Available = false;
    std::uint64_t BotGuid = 0;
    std::uint32_t RequestedMapId = 0;
    float RequestedX = 0.0f;
    float RequestedY = 0.0f;
    float RequestedZ = 0.0f;
    BotMovementArbitration::Owner MovementOwner =
        BotMovementArbitration::Owner::None;
    std::string IntentReason;
    bool TargetFloorSampled = false;
    float TargetFloorZ = 0.0f;
    bool TargetFloorValid = false;
    bool ZDeltaAvailable = false;
    float AbsoluteZDelta = 0.0f;
    float ZDeltaThreshold = 4.0f;
    bool AllowProgressiveSegments = false;
    bool RequireCompletePath = false;
    bool AllowNativeLongPath = false;
    bool DynamicTarget = false;
    NativePathProofObservation NativeProof;
    std::string PlannerGate = "unavailable";
    std::string PlannerResult = "unavailable";
    std::string PlannerReason;
    std::string Gate = "unavailable";
    std::string Result = "unavailable";
    std::string Reason;
};

class MovementPlannerDiagnosticSidecar
{
public:
    static constexpr std::size_t MaxTraceHistory = 128;

    void Record(MovementPlannerObservation observation);
    void FinalizeExecutor(std::uint64_t botGuid,
        std::uint32_t requestedMapId, Intent const& intent, char const* gate,
        char const* result, char const* reason);
    void AssociateTrace(std::uint64_t botGuid, std::uint64_t traceSequence);
    MovementPlannerObservation Latest(std::uint64_t botGuid) const;
    MovementPlannerObservation ForTrace(std::uint64_t botGuid,
        std::uint64_t traceSequence) const;
    void ClearBot(std::uint64_t botGuid);
    void ClearAll();

private:
    using TraceObservation = std::pair<std::uint64_t,
        MovementPlannerObservation>;

    std::map<std::uint64_t, MovementPlannerObservation> _latestByGuid;
    std::map<std::uint64_t, bool> _pendingByGuid;
    std::map<std::uint64_t, std::deque<TraceObservation>> _traceByGuid;
};

MovementPlannerDiagnosticSidecar& MovementPlannerDiagnostics();

void RecordMovementPlannerOutcome(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent, bool targetFloorSampled,
    float targetFloorZ, bool targetFloorValid, char const* gate, bool accepted,
    char const* reason,
    NativePathProofObservation const* nativeProof = nullptr);

void RecordMovementPlannerExecutorOutcome(std::uint64_t botGuid,
    std::uint32_t requestedMapId, Intent const& intent, char const* gate,
    char const* result, char const* reason);

// Serializers return an explicit unavailable object when no planner outcome
// belongs to a diagnosis or trace sequence. They never turn a zero-valued
// default into an accepted planner result.
std::string MovementPlannerObservationJson(
    MovementPlannerObservation const& observation);

}

#endif

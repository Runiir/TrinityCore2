#ifndef TRINITY_BOT_MAGMAW_TRANSFER_LANE_MOVEMENT_OBSERVATION_H
#define TRINITY_BOT_MAGMAW_TRANSFER_LANE_MOVEMENT_OBSERVATION_H

#include "Bots/BotEncounterBlackboard.h"
#include "Bots/BotMovementArbiter.h"

#include <optional>

namespace BotEncounter
{
constexpr float MagmawTransferLaneLeaseDestinationTolerance2d = 0.25f;
constexpr float MagmawTransferLaneLeaseDestinationToleranceZ = 0.50f;

enum class MagmawTransferLaneMovementDisposition : uint8
{
    NoLease,
    ExpiredLease,
    DifferentScope,
    OwnHazardTransfer,
    OwnMechanicTransfer,
    HazardSafetyPreemption,
    RecoverySafetyPreemption,
    OtherCurrentLease
};

struct MagmawTransferLaneMovementObservation
{
    std::optional<BotMovementArbitration::Lease> CurrentLease;
};

BotMovementArbitration::Scope MagmawTransferLaneMovementScope(
    Scope const& lifecycle);

MagmawTransferLaneMovementDisposition
ClassifyMagmawTransferLaneMovementObservation(
    uint64 observedAtMs,
    BotMovementArbitration::Scope const& taskScope,
    Vector3 const& immutableDestination,
    MagmawTransferLaneMovementObservation const& observation);

bool IsMagmawTransferLaneSafetyPreemption(
    MagmawTransferLaneMovementDisposition disposition);

char const* ToString(MagmawTransferLaneMovementDisposition disposition);
}

#endif

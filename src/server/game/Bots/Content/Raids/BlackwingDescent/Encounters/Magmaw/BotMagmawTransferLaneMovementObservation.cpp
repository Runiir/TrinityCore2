#include "Bots/Content/Raids/BlackwingDescent/Encounters/Magmaw/BotMagmawTransferLaneMovementObservation.h"

#include <cmath>

namespace BotEncounter
{
namespace
{
bool MatchesImmutableDestination(BotMovementArbitration::Lease const& lease,
    Vector3 const& destination)
{
    return lease.DynamicTargetGuid == 0
        && std::hypot(lease.X - destination.X, lease.Y - destination.Y)
            <= MagmawTransferLaneLeaseDestinationTolerance2d
        && std::fabs(lease.Z - destination.Z)
            <= MagmawTransferLaneLeaseDestinationToleranceZ;
}
}

BotMovementArbitration::Scope MagmawTransferLaneMovementScope(
    Scope const& lifecycle)
{
    return { lifecycle.AttemptId, lifecycle.WipeGeneration,
        lifecycle.RouteGeneration, lifecycle.MapId, lifecycle.InstanceId };
}

MagmawTransferLaneMovementDisposition
ClassifyMagmawTransferLaneMovementObservation(
    uint64 observedAtMs,
    BotMovementArbitration::Scope const& taskScope,
    Vector3 const& immutableDestination,
    MagmawTransferLaneMovementObservation const& observation)
{
    if (!observation.CurrentLease
        || observation.CurrentLease->MovementOwner
            == BotMovementArbitration::Owner::None)
        return MagmawTransferLaneMovementDisposition::NoLease;

    BotMovementArbitration::Lease const& lease = *observation.CurrentLease;
    if (lease.ExpiresAtMs <= observedAtMs)
        return MagmawTransferLaneMovementDisposition::ExpiredLease;
    if (!BotMovementArbitration::SameScope(lease.MovementScope, taskScope))
        return MagmawTransferLaneMovementDisposition::DifferentScope;
    if (lease.MovementOwner == BotMovementArbitration::Owner::Recovery)
        return MagmawTransferLaneMovementDisposition::
            RecoverySafetyPreemption;

    bool const matches = MatchesImmutableDestination(lease,
        immutableDestination);
    if (lease.MovementOwner == BotMovementArbitration::Owner::Hazard)
        return matches
            ? MagmawTransferLaneMovementDisposition::OwnHazardTransfer
            : MagmawTransferLaneMovementDisposition::
                HazardSafetyPreemption;
    if (lease.MovementOwner == BotMovementArbitration::Owner::Mechanic
        && matches)
        return MagmawTransferLaneMovementDisposition::OwnMechanicTransfer;
    return MagmawTransferLaneMovementDisposition::OtherCurrentLease;
}

bool IsMagmawTransferLaneSafetyPreemption(
    MagmawTransferLaneMovementDisposition disposition)
{
    return disposition
            == MagmawTransferLaneMovementDisposition::HazardSafetyPreemption
        || disposition == MagmawTransferLaneMovementDisposition::
            RecoverySafetyPreemption;
}

char const* ToString(MagmawTransferLaneMovementDisposition disposition)
{
    switch (disposition)
    {
        case MagmawTransferLaneMovementDisposition::ExpiredLease:
            return "expired_lease";
        case MagmawTransferLaneMovementDisposition::DifferentScope:
            return "different_scope";
        case MagmawTransferLaneMovementDisposition::OwnHazardTransfer:
            return "own_hazard_transfer";
        case MagmawTransferLaneMovementDisposition::OwnMechanicTransfer:
            return "own_mechanic_transfer";
        case MagmawTransferLaneMovementDisposition::HazardSafetyPreemption:
            return "hazard_safety_preemption";
        case MagmawTransferLaneMovementDisposition::RecoverySafetyPreemption:
            return "recovery_safety_preemption";
        case MagmawTransferLaneMovementDisposition::OtherCurrentLease:
            return "other_current_lease";
        default: return "no_lease";
    }
}
}

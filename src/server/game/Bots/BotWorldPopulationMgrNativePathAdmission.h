#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_ADMISSION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_ADMISSION_H

#include "BotMovementArbiter.h"
#include "BotWorldPopulationMgrMovement.h"
#include "BotWorldPopulationMgrNativeFloor.h"

#include <cmath>

namespace BotWorldMovement
{
// Canary120's first endpoint mismatch normalized 2.57139 yards horizontally
// (2.68444 in 3D) while retaining complete, floor-valid local progress.
// Keep the generic 0.5-yard endpoint identity proof unchanged; this narrow
// bounded exception is the only admission that uses the larger envelope.
constexpr float NativeLocalMechanicEndpointHorizontalTolerance = 2.75f;
constexpr float NativeLocalMechanicEndpointDistanceTolerance = 2.75f;
constexpr float NativeLocalMechanicEndpointMinimumProgress = 2.0f;
constexpr float NativeLocalMechanicEndpointMinimumTravel = 1.5f;
constexpr float NativeLocalMechanicEndpointProgressEpsilon = 0.001f;
constexpr float NativeHazardEscapeMinimumClearanceProgress = 1.0f;
// A complete native hazard path can already be at its semantic destination
// even when MMAP misses the requested X/Y by a small amount.  This arrival
// envelope is local to mechanic/hazard admission; the shared 0.5-yard
// endpoint identity proof remains strict for ordinary movement.
constexpr float NativeLocalMechanicEndpointArrivalHorizontalTolerance = 1.0f;
constexpr float NativeLocalMechanicEndpointArrivalDistanceTolerance = 1.5f;

inline HazardEscapeProgressObservation ObserveHazardEscapeProgress(
    HazardEscapeBasis const& basis, float actorX, float actorY, float actorZ,
    float endpointX, float endpointY, float endpointZ)
{
    HazardEscapeProgressObservation observation;
    observation.HazardGuid = basis.HazardGuid;
    observation.HazardX = basis.HazardX;
    observation.HazardY = basis.HazardY;
    observation.HazardZ = basis.HazardZ;
    observation.ActorZ = actorZ;
    observation.ActorHazardSameLevel = std::isfinite(actorZ)
        && std::fabs(actorZ - basis.HazardZ) <= NativeFloorTolerance;
    observation.EndpointX = endpointX;
    observation.EndpointY = endpointY;
    observation.EndpointZ = endpointZ;
    observation.RequiredProgress = NativeHazardEscapeMinimumClearanceProgress;
    observation.EndpointBasis = "primary_native_actual_endpoint";
    if (!basis.Available() || !std::isfinite(actorX)
        || !std::isfinite(actorY) || !std::isfinite(actorZ)
        || !std::isfinite(endpointX)
        || !std::isfinite(endpointY) || !std::isfinite(endpointZ))
        return observation;

    observation.Available = true;
    observation.ActorClearance = std::hypot(actorX - basis.HazardX,
        actorY - basis.HazardY);
    observation.EndpointClearance = std::hypot(endpointX - basis.HazardX,
        endpointY - basis.HazardY);
    observation.ClearanceProgress = observation.EndpointClearance
        - observation.ActorClearance;
    return observation;
}

// This is a value-only proof for a future planner admission. It deliberately
// does not compare the endpoint with an arbitrary declared point: a projected
// end-polygon result is useful only when it is a complete, same-surface native
// route and measurably increases clearance from the exact bound hazard.
inline bool NativePathProvesSameSurfaceHazardEscape(
    BotMovementArbitration::Owner owner, bool sameLevelDeclaredRequest,
    bool completeNativePath, bool forbiddenNativePath,
    NativePathProofObservation const& path,
    HazardEscapeBasis const& basis,
    HazardEscapeProgressObservation const& progress)
{
    if (owner != BotMovementArbitration::Owner::Hazard
        || !sameLevelDeclaredRequest || !completeNativePath
        || forbiddenNativePath || !path.Available || !path.Calculated
        || !path.Complete || path.EndpointMatched || !path.EndpointFloorValid
        || path.EndpointResult != PathEndpointResult::ReachedProjectedEndPoly
        || !path.CorridorReachedEndPoly || !path.ResolvedEndpointAvailable
        || !path.ActualEndpointMatchedResolved
        || NativePathFloorObservationBlocksCompleteProof(path.FloorObservation)
        || !basis.Available() || !progress.Available
        || progress.HazardGuid != basis.HazardGuid
        || !progress.ActorHazardSameLevel
        || progress.EndpointBasis != "primary_native_actual_endpoint"
        || !std::isfinite(progress.RequiredProgress)
        || progress.RequiredProgress
            != NativeHazardEscapeMinimumClearanceProgress)
        return false;

    return std::isfinite(progress.ActorClearance)
        && std::isfinite(progress.EndpointClearance)
        && std::isfinite(progress.ClearanceProgress)
        && progress.ClearanceProgress
            >= NativeHazardEscapeMinimumClearanceProgress
                - NativeLocalMechanicEndpointProgressEpsilon;
}

// Progressive local steps may repair an incomplete primary path. A complete
// path that failed endpoint identity or floor admission already resolved a
// different native destination; moving partway toward it cannot make that
// destination valid and may carry the actor to an unsafe platform edge.
inline bool NativePrimaryPathAllowsProgressiveLocalFallback(
    NativePathProofObservation const& observation)
{
    return !observation.Complete;
}

// A complete native hazard/mechanic path can end a short distance from its
// declared point when MMAP selects the nearest walkable polygon. Keep this
// exception separate from global endpoint identity: it requires the same
// level declaration, a bounded local owner, an otherwise complete native
// path, valid endpoint floor evidence, and measurable goal progress/travel.
inline bool NativePathAllowsBoundedSameLevelMechanicProgress(
    BotMovementArbitration::Owner owner,
    bool sameLevelDeclaredFloorFallback, bool boundedLocalProgress,
    bool completeNativePath, bool forbiddenNativePath,
    NativePathProofObservation const& observation, float actorEndpointTravel,
    float currentGoalDistance, float endpointGoalDistance,
    bool sameLevelDeclaredRequest = false)
{
    bool const localOwner = owner == BotMovementArbitration::Owner::Mechanic
        || owner == BotMovementArbitration::Owner::Hazard;
    if (!localOwner || (!sameLevelDeclaredFloorFallback
            && !sameLevelDeclaredRequest)
        || !completeNativePath
        || forbiddenNativePath || !observation.Available
        || !observation.Calculated || !observation.Complete
        || observation.EndpointMatched || !observation.EndpointFloorValid
        || NativePathFloorObservationBlocksCompleteProof(
            observation.FloorObservation))
        return false;
    if (!std::isfinite(actorEndpointTravel)
        || !std::isfinite(observation.EndpointDistance)
        || !std::isfinite(observation.EndpointHorizontalDistance)
        || !std::isfinite(observation.EndpointVerticalDistance)
        || !std::isfinite(currentGoalDistance)
        || !std::isfinite(endpointGoalDistance))
        return false;

    // A same-level request whose complete native endpoint is already within
    // the mechanic destination envelope is an arrival, not a progressive
    // movement step.  Do not require the progressive 1.5-yard travel or
    // two-yard goal-reduction thresholds for this terminal local result.
    if (sameLevelDeclaredRequest
        && currentGoalDistance
            <= NativeLocalMechanicEndpointArrivalDistanceTolerance
        && observation.EndpointHorizontalDistance
            <= NativeLocalMechanicEndpointArrivalHorizontalTolerance
        && observation.EndpointDistance
            <= NativeLocalMechanicEndpointArrivalDistanceTolerance
        && endpointGoalDistance
            <= NativeLocalMechanicEndpointArrivalDistanceTolerance)
        return true;

    // The broader progressive exception remains restricted to the explicit
    // declared-floor fallback and retains its original progress proof.
    if (!sameLevelDeclaredFloorFallback || !boundedLocalProgress)
        return false;
    return actorEndpointTravel >= NativeLocalMechanicEndpointMinimumTravel
        && observation.EndpointHorizontalDistance
            <= NativeLocalMechanicEndpointHorizontalTolerance
        && observation.EndpointVerticalDistance
            <= NativePathEndpointVerticalTolerance
        && observation.EndpointDistance
            <= NativeLocalMechanicEndpointDistanceTolerance
        && currentGoalDistance >= 0.0f
        && endpointGoalDistance >= 0.0f
        && currentGoalDistance - endpointGoalDistance
            >= NativeLocalMechanicEndpointMinimumProgress
                - NativeLocalMechanicEndpointProgressEpsilon;
}
}

#endif

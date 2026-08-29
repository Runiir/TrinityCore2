#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_ADMISSION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_ADMISSION_H

#include "BotMovementArbiter.h"
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
    float currentGoalDistance, float endpointGoalDistance)
{
    bool const localOwner = owner == BotMovementArbitration::Owner::Mechanic
        || owner == BotMovementArbitration::Owner::Hazard;
    if (!localOwner || !sameLevelDeclaredFloorFallback
        || !boundedLocalProgress || !completeNativePath
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

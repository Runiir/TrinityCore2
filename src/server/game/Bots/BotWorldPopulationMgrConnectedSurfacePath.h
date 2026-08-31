#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_CONNECTED_SURFACE_PATH_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_CONNECTED_SURFACE_PATH_H

#include "BotWorldPopulationMgrNativeFloor.h"

namespace BotWorldMovement
{
enum class NativePrimaryEndpointAdmission
{
    Rejected,
    Native,
    ConnectedSurface,
    BoundedLocalMechanic,
};

// A request-level height query can select unrelated geometry on a multi-level
// map. It is diagnostic, not authoritative, when the native path generator
// instead returns a complete normal path backed by Detour's private ordered
// polygon corridor. Copied controls are diagnostic and cannot manufacture
// this proof. The declared Z is admitted only with strict endpoint identity.
inline bool NativePathProvesConnectedSurfaceDespiteHeightConflict(
    NativePathProofObservation const& proof, bool requestHeightConflict,
    bool forbiddenNativePath, bool connectedPolyCorridor)
{
    if (!requestHeightConflict || forbiddenNativePath || !proof.Available
        || !proof.Calculated || !proof.Complete
        || !connectedPolyCorridor
        || !proof.EndpointMatched || proof.EndpointFloorValid
        || !proof.FloorObservationConflict
        || proof.FloorObservation.Failure
            != NativePathFloorFailure::SampleFloorGap)
        return false;
    return true;
}

// This is the production primary-endpoint selection boundary. Keeping the
// alternatives explicit prevents an ordinary valid request followed by a
// later path-floor conflict from entering the connected-surface exception.
inline NativePrimaryEndpointAdmission ClassifyNativePrimaryEndpointAdmission(
    NativePathProofObservation const& proof, bool requestHeightConflict,
    bool forbiddenNativePath, bool connectedPolyCorridor,
    bool boundedLocalMechanicEndpoint)
{
    if (forbiddenNativePath || !proof.Available || !proof.Calculated
        || !proof.Complete
        || proof.FloorObservation.Failure
            == NativePathFloorFailure::SampleFloorUnavailable)
        return NativePrimaryEndpointAdmission::Rejected;
    if (proof.Accepted)
        return NativePrimaryEndpointAdmission::Native;
    if (NativePathProvesConnectedSurfaceDespiteHeightConflict(proof,
            requestHeightConflict, forbiddenNativePath,
            connectedPolyCorridor))
        return NativePrimaryEndpointAdmission::ConnectedSurface;
    if (boundedLocalMechanicEndpoint)
        return NativePrimaryEndpointAdmission::BoundedLocalMechanic;
    return NativePrimaryEndpointAdmission::Rejected;
}
}

#endif

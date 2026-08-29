#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_FLOOR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_FLOOR_H

#include <cmath>
#include <cstdint>

namespace BotWorldMovement
{
constexpr float NativeFloorTolerance = 4.0f;
constexpr float NativePathPointFloorTolerance = 1.5f;
constexpr float NativePathEndpointHorizontalTolerance = 0.5f;
constexpr float NativePathEndpointVerticalTolerance =
    NativePathPointFloorTolerance;

inline bool NativePathEndpointComponentsMatch(float horizontalDistance,
    float verticalDistance)
{
    return std::isfinite(horizontalDistance)
        && std::isfinite(verticalDistance)
        && horizontalDistance <= NativePathEndpointHorizontalTolerance
        && verticalDistance <= NativePathEndpointVerticalTolerance;
}

enum class NativePathFloorFailure
{
    None,
    ActorUnavailable,
    EmptyPath,
    ActorReferenceGap,
    SampleFloorUnavailable,
    SampleFloorGap,
};

inline char const* NativePathFloorFailureName(NativePathFloorFailure failure)
{
    switch (failure)
    {
        case NativePathFloorFailure::None: return "none";
        case NativePathFloorFailure::ActorUnavailable: return "actor_unavailable";
        case NativePathFloorFailure::EmptyPath: return "empty_path";
        case NativePathFloorFailure::ActorReferenceGap: return "actor_reference_gap";
        case NativePathFloorFailure::SampleFloorUnavailable: return "sample_floor_unavailable";
        case NativePathFloorFailure::SampleFloorGap: return "sample_floor_gap";
    }
    return "unknown";
}

// One compact observation is retained for the first failing sample only.
// This is evidence for the path admission decision, not a movement override.
struct NativePathFloorObservation
{
    NativePathFloorFailure Failure = NativePathFloorFailure::None;
    std::uint32_t SegmentIndex = 0;
    std::uint32_t SampleIndex = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    float ResolvedFloorZ = 0.0f;
    float ReferenceZ = 0.0f;

    bool Accepted() const
    {
        return Failure == NativePathFloorFailure::None;
    }
};

inline NativePathFloorObservation MakeNativePathFloorObservation(
    NativePathFloorFailure failure, std::uint32_t segment,
    std::uint32_t sample, float x, float y, float z, float resolvedFloorZ,
    float referenceZ)
{
    return { failure, segment, sample, x, y, z, resolvedFloorZ, referenceZ };
}

struct NativePathProofObservation
{
    bool Available = false;
    bool Calculated = false;
    std::uint32_t PathType = 0;
    bool Complete = false;
    float EndpointX = 0.0f;
    float EndpointY = 0.0f;
    float EndpointZ = 0.0f;
    float EndpointDistance = 0.0f;
    float EndpointHorizontalDistance = 0.0f;
    float EndpointVerticalDistance = 0.0f;
    bool EndpointMatched = false;
    bool EndpointFloorValid = false;
    NativePathFloorObservation FloorObservation;
    bool FloorObservationConflict = false;
    bool Accepted = false;
};

inline bool NativePathFloorObservationBlocksCompleteProof(
    NativePathFloorObservation const& observation)
{
    switch (observation.Failure)
    {
        case NativePathFloorFailure::None:
        case NativePathFloorFailure::SampleFloorUnavailable:
        case NativePathFloorFailure::SampleFloorGap:
            return false;
        case NativePathFloorFailure::ActorUnavailable:
        case NativePathFloorFailure::EmptyPath:
        case NativePathFloorFailure::ActorReferenceGap:
            return true;
    }
    return true;
}

// Keep the complete-path admission order value-only so the map-bound
// planner and replay observe the same endpoint/floor disposition.
inline bool NativePathProofPassesAdmission(
    NativePathProofObservation const& observation)
{
    return observation.EndpointMatched && observation.EndpointFloorValid
        && !NativePathFloorObservationBlocksCompleteProof(
            observation.FloorObservation);
}

inline char const* NativePathProofFailureReason(
    NativePathProofObservation const& observation)
{
    if (NativePathProofPassesAdmission(observation))
        return nullptr;
    if (!observation.EndpointMatched)
        return "route_destination_endpoint_mismatch";
    if (!observation.EndpointFloorValid)
        return "route_destination_endpoint_floor_invalid";
    if (NativePathFloorObservationBlocksCompleteProof(
            observation.FloorObservation))
        return "route_destination_path_floor_gap";
    return "route_destination_unreachable";
}

enum class NativeFloorAdmission
{
    Rejected,
    Native,
    DeclaredFallback,
};

struct NativeFloorResult
{
    float Z = 0.0f;
    NativeFloorAdmission State = NativeFloorAdmission::Rejected;

    bool Accepted() const
    {
        return State != NativeFloorAdmission::Rejected;
    }

    bool UsesDeclaredFallback() const
    {
        return State == NativeFloorAdmission::DeclaredFallback;
    }
};

inline NativeFloorResult AdmitResolvedHeight(float resolvedZ, float declaredZ)
{
    if (!std::isfinite(resolvedZ) || !std::isfinite(declaredZ))
        return {};
    if (std::fabs(resolvedZ - declaredZ) <= NativeFloorTolerance)
        return { resolvedZ, NativeFloorAdmission::Native };
    return { declaredZ, NativeFloorAdmission::DeclaredFallback };
}

inline bool AdmitNativePathPoint(float resolvedZ, float pointZ,
    float referenceZ, bool allowDeclaredFallback)
{
    if (!std::isfinite(resolvedZ) || !std::isfinite(pointZ)
        || !std::isfinite(referenceZ))
        return false;
    if (std::fabs(resolvedZ - pointZ) <= NativePathPointFloorTolerance)
        return true;
    return allowDeclaredFallback
        && std::fabs(pointZ - referenceZ) <= NativeFloorTolerance;
}

inline bool NativePathReferenceFloorValid(float sampleZ, float referenceZ)
{
    return std::isfinite(sampleZ) && std::isfinite(referenceZ)
        && std::fabs(sampleZ - referenceZ) <= NativeFloorTolerance;
}

// Multi-level VMAP queries can return a different floor even when both the
// actor and the native path request remain on one coherent level. This only
// admits the declared level as a reference for the later full native-path
// proof; it does not accept a path or a cross-floor destination by itself.
inline bool AdmitSameLevelDeclaredFloorFallback(float actorZ,
    float requestedZ, float resolvedFloorZ)
{
    return std::isfinite(actorZ) && std::isfinite(requestedZ)
        && std::isfinite(resolvedFloorZ)
        && std::fabs(actorZ - requestedZ) <= NativeFloorTolerance
        && std::fabs(resolvedFloorZ - requestedZ) > NativeFloorTolerance;
}

// Local mechanic steps are declared on the actor's current level.  A height
// probe may nevertheless return an unrelated lower floor at the candidate
// X/Y; preserve the declared local Z only when the original destination also
// proved to be a same-level request.  A genuine cross-floor request remains
// rejected instead of inheriting the actor's transient floor.
inline NativeFloorResult AdmitSameLevelLocalStepFloor(float actorZ,
    float requestedZ, float resolvedFloorZ)
{
    if (!std::isfinite(actorZ) || !std::isfinite(requestedZ)
        || !std::isfinite(resolvedFloorZ))
        return {};
    if (std::fabs(resolvedFloorZ - actorZ) <= NativeFloorTolerance)
        return { resolvedFloorZ, NativeFloorAdmission::Native };
    if (!AdmitSameLevelDeclaredFloorFallback(actorZ, requestedZ,
            resolvedFloorZ))
        return {};
    return { actorZ, NativeFloorAdmission::DeclaredFallback };
}
}

#endif

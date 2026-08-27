#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_FLOOR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_FLOOR_H

#include <cmath>
#include <cstdint>

namespace BotWorldMovement
{
constexpr float NativeFloorTolerance = 4.0f;
constexpr float NativePathPointFloorTolerance = 1.5f;

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
}

#endif

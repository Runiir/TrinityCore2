#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_FLOOR_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_FLOOR_H

#include <cmath>

namespace BotWorldMovement
{
constexpr float NativeFloorTolerance = 4.0f;
constexpr float NativePathPointFloorTolerance = 1.5f;

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
}

#endif

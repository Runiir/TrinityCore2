#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_VALIDATION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_VALIDATION_H

#include "BotWorldPopulationMgrNativeFloor.h"
#include "Map.h"
#include "PathGenerator.h"

#include <algorithm>
#include <cmath>
#include <cstdint>

namespace BotWorldMovement
{
inline bool NativePathIsComplete(bool calculated, PathGenerator const& path)
{
    PathType const type = path.GetPathType();
    return calculated && (type & PATHFIND_NORMAL)
        && !(type & PATHFIND_NOPATH)
        && !(type & PATHFIND_NOT_USING_PATH)
        && !(type & PATHFIND_INCOMPLETE)
        && !(type & PATHFIND_SHORTCUT)
        && !(type & PATHFIND_FARFROMPOLY);
}

template <typename Actor>
inline bool NativePathPointFloorValid(Actor const* actor,
    G3D::Vector3 const& point, float referenceZ,
    bool allowDeclaredFallback)
{
    if (!actor || !actor->GetMap())
        return false;
    float const floorZ = actor->GetMap()->GetHeight(actor->GetPhaseShift(),
        point.x, point.y, point.z + 2.0f, true, 8.0f);
    return floorZ > INVALID_HEIGHT && AdmitNativePathPoint(floorZ, point.z,
        referenceZ, allowDeclaredFallback);
}

template <typename Actor>
inline bool NativePathPointFloorValid(Actor const* actor,
    G3D::Vector3 const& point)
{
    return NativePathPointFloorValid(actor, point, point.z, false);
}

template <typename Actor>
inline NativePathFloorObservation DiagnoseNativePathFloors(
    Actor const* actor, PathGenerator const& path, float referenceZ,
    bool allowDeclaredFallback)
{
    Movement::PointsArray const& points = path.GetPath();
    if (!actor || !actor->GetMap())
        return MakeNativePathFloorObservation(
            NativePathFloorFailure::ActorUnavailable, 0, 0, 0.0f, 0.0f,
            0.0f, 0.0f, referenceZ);
    if (points.empty())
        return MakeNativePathFloorObservation(
            NativePathFloorFailure::EmptyPath, 0, 0, actor->GetPositionX(),
            actor->GetPositionY(), actor->GetPositionZ(), 0.0f, referenceZ);
    if (allowDeclaredFallback && !NativePathReferenceFloorValid(
            actor->GetPositionZ(), referenceZ))
        return MakeNativePathFloorObservation(
            NativePathFloorFailure::ActorReferenceGap, 0, 0,
            actor->GetPositionX(), actor->GetPositionY(),
            actor->GetPositionZ(), actor->GetPositionZ(), referenceZ);

    G3D::Vector3 previous(actor->GetPositionX(), actor->GetPositionY(),
        actor->GetPositionZ());
    std::uint32_t segmentIndex = 0;
    for (G3D::Vector3 const& point : points)
    {
        float const dx = point.x - previous.x;
        float const dy = point.y - previous.y;
        float const dz = point.z - previous.z;
        float const distance = std::sqrt(dx * dx + dy * dy + dz * dz);
        std::uint32_t const sampleCount = std::max<std::uint32_t>(1,
            static_cast<std::uint32_t>(std::ceil(distance)));
        for (std::uint32_t sample = 1; sample <= sampleCount; ++sample)
        {
            float const fraction = float(sample) / float(sampleCount);
            G3D::Vector3 const position(previous.x + dx * fraction,
                previous.y + dy * fraction, previous.z + dz * fraction);
            float const floorZ = actor->GetMap()->GetHeight(
                actor->GetPhaseShift(), position.x, position.y,
                position.z + 2.0f, true, 8.0f);
            if (!(floorZ > INVALID_HEIGHT))
                return MakeNativePathFloorObservation(
                    NativePathFloorFailure::SampleFloorUnavailable,
                    segmentIndex, sample, position.x, position.y,
                    position.z, floorZ, referenceZ);
            if (!AdmitNativePathPoint(floorZ, position.z, referenceZ,
                    allowDeclaredFallback))
                return MakeNativePathFloorObservation(
                    NativePathFloorFailure::SampleFloorGap, segmentIndex,
                    sample, position.x, position.y, position.z, floorZ,
                    referenceZ);
        }
        previous = point;
        ++segmentIndex;
    }
    return {};
}

template <typename Actor>
inline bool NativePathFloorsValid(Actor const* actor,
    PathGenerator const& path, float referenceZ,
    bool allowDeclaredFallback)
{
    return DiagnoseNativePathFloors(actor, path, referenceZ,
        allowDeclaredFallback).Accepted();
}

template <typename Actor>
inline bool NativePathFloorsValid(Actor const* actor,
    PathGenerator const& path)
{
    return NativePathFloorsValid(actor, path, 0.0f, false);
}

template <typename Actor>
inline bool NativePathEndpointFloorValid(Actor const* actor,
    PathGenerator const& path)
{
    return NativePathPointFloorValid(actor, path.GetActualEndPosition());
}
}

#endif

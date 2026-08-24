#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_VALIDATION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_PATH_VALIDATION_H

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
    G3D::Vector3 const& point)
{
    if (!actor || !actor->GetMap())
        return false;
    float const floorZ = actor->GetMap()->GetHeight(actor->GetPhaseShift(),
        point.x, point.y, point.z + 2.0f, true, 8.0f);
    return floorZ > INVALID_HEIGHT && std::fabs(floorZ - point.z) <= 1.5f;
}

template <typename Actor>
inline bool NativePathFloorsValid(Actor const* actor,
    PathGenerator const& path)
{
    Movement::PointsArray const& points = path.GetPath();
    if (!actor || points.empty())
        return false;

    G3D::Vector3 previous(actor->GetPositionX(), actor->GetPositionY(),
        actor->GetPositionZ());
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
            if (!NativePathPointFloorValid(actor, position))
                return false;
        }
        previous = point;
    }
    return true;
}

template <typename Actor>
inline bool NativePathEndpointFloorValid(Actor const* actor,
    PathGenerator const& path)
{
    return NativePathPointFloorValid(actor, path.GetActualEndPosition());
}
}

#endif

#ifndef TRINITY_BOT_MAGMAW_MANGLE_SUPPORT_GEOMETRY_H
#define TRINITY_BOT_MAGMAW_MANGLE_SUPPORT_GEOMETRY_H

#include "Bots/BotEncounterBlackboard.h"

#include <algorithm>
#include <cmath>
#include <optional>

namespace BotEncounter
{
struct MagmawMangleSupportGeometry
{
    static std::optional<Vector3> Resolve(Vector3 const& routeFloorSupport,
        Vector3 const& ownerPosition, float maxDistance)
    {
        if (!Finite(routeFloorSupport) || !Finite(ownerPosition)
            || !std::isfinite(maxDistance) || maxDistance <= 0.0f)
            return std::nullopt;

        float const dz = routeFloorSupport.Z - ownerPosition.Z;
        if (std::fabs(dz) > maxDistance)
            return std::nullopt;

        Vector3 destination = routeFloorSupport;
        float const horizontalLimitSquared = std::max(0.0f,
            maxDistance * maxDistance - dz * dz);
        float const dx = destination.X - ownerPosition.X;
        float const dy = destination.Y - ownerPosition.Y;
        float const horizontalSquared = dx * dx + dy * dy;
        if (horizontalSquared > horizontalLimitSquared)
        {
            float const horizontal = std::sqrt(horizontalSquared);
            if (horizontal <= 0.0f)
                return std::nullopt;
            float const safeLimit = std::max(0.0f,
                std::sqrt(horizontalLimitSquared) - 0.01f);
            float const scale = safeLimit / horizontal;
            destination.X = ownerPosition.X + dx * scale;
            destination.Y = ownerPosition.Y + dy * scale;
        }

        if (SamePosition(destination, ownerPosition)
            || !WithinDistance(destination, ownerPosition, maxDistance))
            return std::nullopt;
        return destination;
    }

    static bool WithinDistance(Vector3 const& left, Vector3 const& right,
        float maxDistance)
    {
        float const dx = left.X - right.X;
        float const dy = left.Y - right.Y;
        float const dz = left.Z - right.Z;
        return dx * dx + dy * dy + dz * dz
            <= maxDistance * maxDistance;
    }

private:
    static bool Finite(Vector3 const& point)
    {
        return std::isfinite(point.X) && std::isfinite(point.Y)
            && std::isfinite(point.Z);
    }

    static bool SamePosition(Vector3 const& left, Vector3 const& right)
    {
        return left.X == right.X && left.Y == right.Y && left.Z == right.Z;
    }
};
}

#endif

#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PATH_SELECTION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PATH_SELECTION_H

#include <array>
#include <cmath>

namespace BotWorldMovement
{
// Generate bounded points between an actor and a declared local mechanic
// destination.  The caller still owns floor resolution and native proof;
// this helper only makes the candidate order deterministic and never admits
// an interpolated point by itself.
template <typename Point, typename Accept>
bool SelectProgressiveLocalMechanicCandidate(Point const& actor,
    Point const& declaredDestination, Accept&& accept)
{
    constexpr std::array<float, 4> Fractions{
        0.75f, 0.5f, 0.35f, 0.25f
    };
    for (float fraction : Fractions)
    {
        Point candidate = actor;
        candidate.x = actor.x + (declaredDestination.x - actor.x)
            * fraction;
        candidate.y = actor.y + (declaredDestination.y - actor.y)
            * fraction;
        if (accept(candidate, fraction))
            return true;
    }
    return false;
}

template <typename Points, typename Point, typename Accept>
bool SelectIncompletePathBackoffCandidate(Points const& points,
    Point const& endpoint, float minimumClearance, Accept&& accept)
{
    if (points.empty() || minimumClearance <= 0.0f)
        return false;

    auto distance = [](Point const& left, Point const& right)
    {
        float const x = left.x - right.x;
        float const y = left.y - right.y;
        float const z = left.z - right.z;
        return std::sqrt(x * x + y * y + z * z);
    };

    float pathClearance = 0.0f;
    Point previous = endpoint;
    for (auto point = points.rbegin(); point != points.rend(); ++point)
    {
        pathClearance += distance(previous, *point);
        previous = *point;
        float const directClearance = distance(endpoint, *point);
        if (pathClearance + 0.001f < minimumClearance
            || directClearance + 0.001f < minimumClearance)
            continue;
        if (accept(*point, pathClearance, directClearance))
            return true;
    }
    return false;
}
}

#endif

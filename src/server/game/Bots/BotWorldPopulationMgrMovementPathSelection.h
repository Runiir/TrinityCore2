#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PATH_SELECTION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_MOVEMENT_PATH_SELECTION_H

#include <cmath>

namespace BotWorldMovement
{
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

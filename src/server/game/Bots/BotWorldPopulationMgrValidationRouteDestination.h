#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DESTINATION_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_ROUTE_DESTINATION_H

#include <cmath>
#include <cstdint>

namespace BotValidationRouteDestination
{
// A route node owns the navigation anchor used by native movement.  Keep the
// derivation separate from the update dispatcher so an adaptive encounter
// owner cannot accidentally retain the previous node's destination.
struct Input
{
    std::uint32_t MapId = 0;
    float NavigationAnchorX = 0.0f;
    float NavigationAnchorY = 0.0f;
    float NavigationAnchorZ = 0.0f;
};

enum class Action : std::uint8_t
{
    InvalidateStaleDestination,
    MoveToCurrentNavigationAnchor,
};

struct Result
{
    Action NextAction = Action::InvalidateStaleDestination;
    bool Valid = false;
    std::uint32_t MapId = 0;
    float X = 0.0f;
    float Y = 0.0f;
    float Z = 0.0f;
    char const* Reason = "validation_route_destination_invalid";
};

inline bool Finite(float value)
{
    return std::isfinite(value);
}

inline Result Resolve(Input const& input)
{
    if (!Finite(input.NavigationAnchorX)
        || !Finite(input.NavigationAnchorY)
        || !Finite(input.NavigationAnchorZ))
        return {};

    return {
        Action::MoveToCurrentNavigationAnchor,
        true,
        input.MapId,
        input.NavigationAnchorX,
        input.NavigationAnchorY,
        input.NavigationAnchorZ,
        "validation_route_manifest_navigation_anchor",
    };
}
}

#endif

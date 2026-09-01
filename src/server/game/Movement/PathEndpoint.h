#ifndef TRINITY_PATH_ENDPOINT_H
#define TRINITY_PATH_ENDPOINT_H

#include <cstdint>

enum class PathEndpointResult : std::uint8_t
{
    Unavailable,
    ReachedRequested,
    ReachedProjectedEndPoly,
    NoSteer,
    CorridorExhausted,
    Capacity,
    Failure,
};

inline char const* PathEndpointResultName(PathEndpointResult result)
{
    switch (result)
    {
        case PathEndpointResult::Unavailable: return "unavailable";
        case PathEndpointResult::ReachedRequested: return "reached_requested";
        case PathEndpointResult::ReachedProjectedEndPoly:
            return "reached_projected_end_poly";
        case PathEndpointResult::NoSteer: return "no_steer";
        case PathEndpointResult::CorridorExhausted:
            return "corridor_exhausted";
        case PathEndpointResult::Capacity: return "capacity";
        case PathEndpointResult::Failure: return "failure";
    }
    return "unknown";
}

#endif

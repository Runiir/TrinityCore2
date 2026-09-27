#ifndef TRINITY_BOT_PASSENGER_ENDPOINT_FLOOR_H
#define TRINITY_BOT_PASSENGER_ENDPOINT_FLOOR_H

// Range and line-of-sight recovery for a transport passenger (round 2, BWD
// 10N, Nefarian).  r01 receipt 10826 (bot 11005009) launched a combat-range
// point spline from a Nefarian pillar top to an endpoint whose floor lay
// 168 yd below (selected_platform_compatible=false) and accepted it as
// selected_endpoint_reached: the Elemental shaman hovered at local Z 10.3
// for the rest of the fight.  The static-floor fallbacks of the ordinary
// planner (a declared floor within NativeFloorTolerance of the request) do
// not know about the platform, so a passenger's endpoint must itself stand
// on a floor: static geometry, any collidable gameobject, or the passenger's
// own transport model, within the planner's vertical tolerance.  Members that
// are not transport passengers are unaffected.

#include "Bots/BotWorldPopulationMgrNativeFloor.h"

#include <cmath>

namespace BotPassengerEndpointFloor
{
struct Probe
{
    bool Passenger = false;
    // Map::GetHeight (static and gameobject floors) searched from
    // endpoint + tolerance down to endpoint - tolerance.
    bool FloorFound = false;
    float FloorZ = 0.0f;
    // A downward ray through the passenger's own transport model.
    bool TransportFloor = false;
};

inline bool Admit(Probe const& probe, float endpointZ,
    float tolerance = BotWorldMovement::NativeFloorTolerance)
{
    if (!probe.Passenger)
        return true;
    if (!std::isfinite(endpointZ))
        return false;
    if (probe.TransportFloor)
        return true;
    return probe.FloorFound && std::isfinite(probe.FloorZ)
        && std::fabs(probe.FloorZ - endpointZ) <= tolerance;
}

constexpr char const* RejectReason = "transport_passenger_endpoint_without_floor";
}

#endif

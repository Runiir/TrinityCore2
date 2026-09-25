#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_FALL_SPLINE_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_FALL_SPLINE_H

#include "Movement/Spline/MoveSpline.h"

#include <algorithm>
#include <cstdint>

// A native fall's state as the unit's own spline shows it. A stop issued
// mid-air (Unit::StopMoving -> MoveSplineInit::Stop -> MoveSpline::Initialize
// with Done) clears the spline: Initialized() is false, Finalized() true and
// FinalDestination() an empty Vector3, while MOVEMENTFLAG_FALLING stays set.
// Such a fall still owes its landing.
namespace BotValidationRouteNativeFall
{
// MotionMaster::MoveFall's falling spline is still running.
inline bool SplineActive(Movement::MoveSpline const& spline)
{
    return spline.Initialized() && !spline.Finalized() && spline.isFalling();
}

// The falling flags are set and no spline runs: the fall spline finalized,
// or a stop replaced it mid-air. The landing (or falling on) is owed.
inline bool LandingPending(bool fallingFlags, Movement::MoveSpline const& spline)
{
    return fallingFlags && (!spline.Initialized() || spline.Finalized());
}

// A finished spline has an end to compare with; a cleared stop spline has none.
inline bool EndpointKnown(Movement::MoveSpline const& spline)
{
    return spline.Initialized();
}

// The fall time a landing report carries: the finished fall spline's
// duration, or none after a cleared stop spline (Duration() reads the
// spline's lengths, which a cleared spline no longer has).
inline std::int32_t ReportedFallTimeMs(Movement::MoveSpline const& spline)
{
    return spline.Initialized() ? std::max<std::int32_t>(0, spline.Duration()) : 0;
}
}

#endif

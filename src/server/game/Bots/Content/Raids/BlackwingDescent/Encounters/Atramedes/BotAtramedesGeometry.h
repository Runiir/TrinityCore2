#ifndef TRINITY_BOT_ATRAMEDES_GEOMETRY_H
#define TRINITY_BOT_ATRAMEDES_GEOMETRY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFacts.h"
#include <algorithm>
#include <cmath>
#include <optional>

// Pure planar geometry for the Atramedes hazards. Destinations are logical
// anchors on the arena floor; native pathing resolves height and walls.
namespace BotEncounter::Atramedes::Geometry
{
inline constexpr float Pi = 3.14159265358979323846f;
inline constexpr float TwoPi = 2.0f * Pi;

inline float Distance2d(Vector3 const& left, Vector3 const& right)
{
    float const dx = left.X - right.X;
    float const dy = left.Y - right.Y;
    return std::sqrt(dx * dx + dy * dy);
}

inline float Distance3d(Vector3 const& left, Vector3 const& right)
{
    float const dz = left.Z - right.Z;
    float const planar = Distance2d(left, right);
    return std::sqrt(planar * planar + dz * dz);
}

inline float Bearing(Vector3 const& from, Vector3 const& to)
{
    return std::atan2(to.Y - from.Y, to.X - from.X);
}

// Signed smallest angle a - b in (-pi, pi].
inline float AngleDelta(float a, float b)
{
    float delta = std::fmod(a - b, TwoPi);
    if (delta <= -Pi)
        delta += TwoPi;
    else if (delta > Pi)
        delta -= TwoPi;
    return delta;
}

inline Vector3 PointAt(Vector3 const& center, float bearing, float radius, float z)
{
    return { center.X + std::cos(bearing) * radius,
        center.Y + std::sin(bearing) * radius, z };
}

// Point on the circle through `self` around `center`, advanced along the
// circle by `arcLength` in `direction` (+1 counter-clockwise, -1 clockwise).
inline Vector3 TangentialStep(Vector3 const& center, Vector3 const& self,
    float radius, float arcLength, int direction)
{
    float const bearing = Bearing(center, self);
    float const step = arcLength / std::max(radius, 1.0f);
    return PointAt(center, bearing + float(direction) * step, radius, self.Z);
}

// Point `clearance` yards from `hazard` on the ray from the hazard through
// `self`; an exact overlap escapes along `fallbackBearing`.
inline Vector3 RadialExit(Vector3 const& hazard, Vector3 const& self,
    float clearance, float fallbackBearing)
{
    float bearing = fallbackBearing;
    if (Distance2d(hazard, self) > 0.05f)
        bearing = Bearing(hazard, self);
    return PointAt(hazard, bearing, clearance, self.Z);
}

inline constexpr float CoincidentYards = 0.05f;

// Circling direction (+1 counter-clockwise, -1 clockwise) around `center`
// that keeps `self` ahead of `chaser`. A chaser that follows `self` in a
// straight line always trails its bearing around `center`, so the answer
// holds for the whole chase. 0 while the chaser is on top of `self`.
inline int AwayFromChaser(Vector3 const& center, Vector3 const& self,
    Vector3 const& chaser)
{
    float const radius = std::max(1.0f, Distance2d(center, self));
    float const lead = AngleDelta(Bearing(center, self), Bearing(center, chaser));
    if (std::fabs(lead) * radius <= CoincidentYards)
        return 0;
    return lead > 0.0f ? 1 : -1;
}

struct RayOffset
{
    // Distance along the ray (negative behind its origin).
    float Along = 0.0f;
    // Unsigned perpendicular distance from the ray line.
    float Lateral = 0.0f;
    // +1 when `point` lies counter-clockwise of the ray direction.
    int Side = 1;
};

inline RayOffset OffsetFromRay(Vector3 const& origin, float bearing,
    Vector3 const& point)
{
    float const ux = std::cos(bearing);
    float const uy = std::sin(bearing);
    float const px = point.X - origin.X;
    float const py = point.Y - origin.Y;
    RayOffset offset;
    offset.Along = px * ux + py * uy;
    float const cross = ux * py - uy * px;
    offset.Lateral = std::fabs(cross);
    offset.Side = cross >= 0.0f ? 1 : -1;
    return offset;
}

// Lateral step that puts `self` `clearance` yards to its current side of the
// ray line (a disk or beam travelling along `bearing`).
inline Vector3 LateralExit(Vector3 const& origin, float bearing,
    Vector3 const& self, float clearance)
{
    RayOffset const offset = OffsetFromRay(origin, bearing, self);
    float const nx = -std::sin(bearing) * float(offset.Side);
    float const ny = std::cos(bearing) * float(offset.Side);
    float const move = std::max(0.0f, clearance - offset.Lateral) + 1.0f;
    return { self.X + nx * move, self.Y + ny * move, self.Z };
}
}

#endif

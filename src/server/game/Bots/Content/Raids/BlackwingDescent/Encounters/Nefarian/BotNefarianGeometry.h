#ifndef TRINITY_BOT_NEFARIAN_GEOMETRY_H
#define TRINITY_BOT_NEFARIAN_GEOMETRY_H

// Platform-frame geometry for Nefarian's End. Destinations are expressed in
// the elevator's local frame first, because the whole fight happens on the
// GO 207834 transport surface and its height changes between phases. World
// coordinates are derived from the observed transport origin at decision
// time; the movement layer (package T) owns how a destination is reached.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianFacts.h"
#include <cmath>

namespace BotEncounter::Nefarian
{
constexpr float Pi = 3.14159265358979323846f;
constexpr float TwoPi = 2.0f * Pi;

// Platform floor, from the collision model of GO 207834 (displayId 10363,
// data/vmaps/Blackwingv2_Elevator_Onyxia_Transport.wmo.vmo, sha256 b51adf90...,
// sampled every 5 degrees and 0.5 yards in
// experiments/configs/cata_raid_encounters/blackwing_descent/
// nefarian_platform_floor_profile_v1.json): a flat centre at local z -0.546
// (two decorative ridges rise 0.23 near r 10 and r 19-21) out to r 21.17, a
// steady ramp of 0.1763 yards per yard at every heading, and the outer ring at
// +1.439 from r 32.43 outwards. The model is within 0.24 yards of every
// sample away from the pillars. The whole floor is walkable; pillar blocks
// (headings 0/120/240, footprint radius 5.9 yards including their skirt, tops
// at 9.925) are not. No static navmesh covers any of it.
// Standing spots lie within r 57 and at least 9 yards from a pillar centre;
// paths keep 7 yards from a pillar centre (the 5.9-yard footprint plus the
// 0.39-yard body radius and a margin).
constexpr float FloorFlatLocalZ = -0.546f;
constexpr float RampStartRadius = 21.17f;
constexpr float RampSlope = 0.1763f;
constexpr float RingLocalZ = 1.439f;
constexpr float RampEndRadius = RampStartRadius
    + (RingLocalZ - FloorFlatLocalZ) / RampSlope;
constexpr float OuterFloorLimit = 57.0f;
constexpr float PillarKeepOutRadius = 9.0f;
constexpr float PillarPathClearance = 7.0f;

enum class Surface : uint8
{
    Floor,
    PillarTop
};

inline float DegToRad(float degrees) { return degrees * Pi / 180.0f; }

inline float NormalizeSigned(float angle)
{
    angle = std::fmod(angle, TwoPi);
    if (angle > Pi)
        angle -= TwoPi;
    else if (angle < -Pi)
        angle += TwoPi;
    return angle;
}

inline float Length(LocalPoint point)
{
    return std::sqrt(point.X * point.X + point.Y * point.Y);
}

inline float Distance(LocalPoint left, LocalPoint right)
{
    return Length({ left.X - right.X, left.Y - right.Y });
}

inline float AngleOf(LocalPoint point) { return std::atan2(point.Y, point.X); }

inline LocalPoint Polar(float angle, float radius)
{
    return { std::cos(angle) * radius, std::sin(angle) * radius };
}

inline LocalPoint Offset(LocalPoint from, float angle, float distance)
{
    return { from.X + std::cos(angle) * distance,
        from.Y + std::sin(angle) * distance };
}

inline LocalPoint ClampToRadius(LocalPoint point, float radius)
{
    float const length = Length(point);
    if (length <= radius || length < 0.001f)
        return point;
    return { point.X / length * radius, point.Y / length * radius };
}

// Local <-> world for the pi-rotated transport. Z uses the observed origin so
// a pillar-top destination follows the platform while it moves.
inline LocalPoint WorldToLocal(Vector3 const& world)
{
    float const dx = world.X - PlatformFrame::OriginX;
    float const dy = world.Y - PlatformFrame::OriginY;
    float const c = std::cos(PlatformFrame::Orientation);
    float const s = std::sin(PlatformFrame::Orientation);
    return { dx * c + dy * s, -dx * s + dy * c };
}

inline Vector3 LocalToWorld(LocalPoint local, float localZ, float originZ)
{
    float const c = std::cos(PlatformFrame::Orientation);
    float const s = std::sin(PlatformFrame::Orientation);
    return { PlatformFrame::OriginX + local.X * c - local.Y * s,
        PlatformFrame::OriginY + local.X * s + local.Y * c,
        originZ + localZ };
}

// A facing in the world frame expressed in the local frame.
inline float WorldFacingToLocal(float worldFacing)
{
    return NormalizeSigned(worldFacing - PlatformFrame::Orientation);
}

inline float SurfaceLocalZ(Surface surface)
{
    return surface == Surface::PillarTop ? PlatformFrame::PillarTopLocalZ
        : PlatformFrame::FloorLocalZ;
}

// Floor height at a local point: the flat centre, the ramp, then the ring.
inline float FloorLocalZAt(LocalPoint point)
{
    float const radius = Length(point);
    if (radius <= RampStartRadius)
        return FloorFlatLocalZ;
    if (radius >= RampEndRadius)
        return RingLocalZ;
    return FloorFlatLocalZ + (radius - RampStartRadius) * RampSlope;
}

// How much the floor rises per yard outward at a point: the ramp's slope
// between its ends, 0 on the flat centre and the flat ring.
inline float FloorSlopeOutward(LocalPoint point)
{
    float const radius = Length(point);
    return radius > RampStartRadius && radius < RampEndRadius ? RampSlope : 0.0f;
}

// Absolute angle (0..pi) between an actor's facing and the direction from it
// to a point. 0 is straight ahead, pi straight behind.
inline float OffFacing(LocalPoint origin, float facing, LocalPoint point)
{
    LocalPoint const delta{ point.X - origin.X, point.Y - origin.Y };
    if (Length(delta) < 0.001f)
        return 0.0f;
    return std::fabs(NormalizeSigned(AngleOf(delta) - facing));
}

struct DragonPose
{
    LocalPoint Position;
    float Facing = 0.0f; // local frame
};

inline DragonPose PoseOf(ActorSnapshot const& dragon)
{
    return { WorldToLocal(dragon.Position), WorldFacingToLocal(dragon.Facing) };
}

inline bool InFrontCone(DragonPose const& dragon, LocalPoint point,
    float marginDeg = 8.0f)
{
    return Distance(dragon.Position, point) <= DragonConeRadius
        && OffFacing(dragon.Position, dragon.Facing, point)
            <= DegToRad(BreathHalfAngleDeg + marginDeg);
}

inline bool InRearCone(DragonPose const& dragon, LocalPoint point,
    float marginDeg = 8.0f)
{
    return Distance(dragon.Position, point) <= DragonConeRadius
        && OffFacing(dragon.Position, dragon.Facing, point)
            >= Pi - DegToRad(TailLashHalfAngleDeg + marginDeg);
}

// Onyxia's Lightning Discharge damages everyone within 60 yards who is in
// neither her 90-degree front nor her 90-degree back immunity cone.
inline bool InDischargeFlank(DragonPose const& onyxia, LocalPoint point,
    float marginDeg = 6.0f)
{
    if (Distance(onyxia.Position, point) > DragonConeRadius)
        return false;
    float const off = OffFacing(onyxia.Position, onyxia.Facing, point);
    float const immune = DegToRad(DischargeImmuneHalfAngleDeg - marginDeg);
    return off > immune && off < Pi - immune;
}

inline bool NearPillar(LocalPoint point, float keepOut = PillarKeepOutRadius)
{
    for (LocalPoint const& pillar : PillarCenters)
        if (Distance(pillar, point) < keepOut)
            return true;
    return false;
}

// A standing spot: on the platform floor (the ramp included), clear of the
// pillars.
inline bool OnFloorArea(LocalPoint point)
{
    return Length(point) <= OuterFloorLimit && !NearPillar(point);
}

// Moves a destination inside the platform's outer limit and radially out of
// a pillar's keep-out, to the nearer side.
inline LocalPoint SnapToStandingArea(LocalPoint point)
{
    float radius = std::min(Length(point), OuterFloorLimit);
    float const angle = Length(point) < 0.001f ? 0.0f : AngleOf(point);
    LocalPoint snapped = Polar(angle, radius);
    for (LocalPoint const& pillar : PillarCenters)
    {
        if (Distance(pillar, snapped) >= PillarKeepOutRadius)
            continue;
        float const inner = Length(pillar) - PillarKeepOutRadius - 0.5f;
        float const outer = Length(pillar) + PillarKeepOutRadius + 0.5f;
        radius = std::fabs(radius - inner) <= std::fabs(outer - radius)
            ? inner : std::min(outer, OuterFloorLimit);
        snapped = Polar(angle, radius);
    }
    return snapped;
}

// Pillar slots. Each team member owns one heading around its pillar, spread
// across the pillar's arena side. On that heading it waits on the floor at
// the pillar's foot (PillarFootRadius), floats beside the wall at its swim
// station (BotNefarianMagma.h) and lands on the flat pillar top at
// PillarSlotRadius, inside the prototype's 7.2-yard melee reach (the
// prototype stands on the centre).
constexpr float PillarSlotRadius = 3.0f;
constexpr float PillarFootRadius = 9.5f;
inline constexpr float PillarSlotHeadingDeg[6] = { -12.5f, 12.5f, -37.5f,
    37.5f, -62.5f, 62.5f };

inline float PillarSlotHeading(uint8 pillar, uint8 slot)
{
    float const inward = AngleOf(PillarCenters[pillar % 3]) + Pi;
    return NormalizeSigned(inward + DegToRad(PillarSlotHeadingDeg[slot % 6]));
}

// A point on a slot's heading at `radius` yards from the pillar centre.
inline LocalPoint PillarRadial(uint8 pillar, uint8 slot, float radius)
{
    return Offset(PillarCenters[pillar % 3], PillarSlotHeading(pillar, slot),
        radius);
}

inline LocalPoint PillarSlot(uint8 pillar, uint8 slot)
{
    return PillarRadial(pillar, slot, PillarSlotRadius);
}

// Floor spot at the foot of a pillar, on the slot's heading, outside the
// standing keep-out.
inline LocalPoint PillarBase(uint8 pillar, uint8 slot)
{
    return PillarRadial(pillar, slot, PillarFootRadius);
}

// The pillar whose centre is nearest, and the distance to it.
inline int NearestPillar(LocalPoint point, float& distance)
{
    int best = 0;
    distance = Distance(point, PillarCenters[0]);
    for (int pillar = 1; pillar < 3; ++pillar)
        if (float const d = Distance(point, PillarCenters[pillar]); d < distance)
        {
            best = pillar;
            distance = d;
        }
    return best;
}
}

#endif

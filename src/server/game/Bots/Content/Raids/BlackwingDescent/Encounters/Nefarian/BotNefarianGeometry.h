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

// Platform model (package T's collision probe of GO 207834): the centre floor
// sits at local z -0.5..+0.1 and rises to an outer ring at local +1.44 from
// r 32 out to r 60; pillar blocks stand at headings 0/120/240 degrees between
// r 36 and 44 with near-vertical sides. Destinations stay either on the
// centre floor or on the ring, never on the rise between them.
constexpr float MaxFloorRadius = 38.0f;
constexpr float CentreFloorMaxRadius = 28.0f;
constexpr float RingInnerRadius = 32.0f;
constexpr float RingLocalZ = 1.44f;
constexpr float PillarBaseRadius = 26.0f;
constexpr float PillarKeepOutRadius = 9.0f;

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

// Floor height at a local point: centre floor, the rise, then the ring.
inline float FloorLocalZAt(LocalPoint point)
{
    float const radius = Length(point);
    if (radius <= CentreFloorMaxRadius)
        return PlatformFrame::FloorLocalZ;
    if (radius >= RingInnerRadius)
        return RingLocalZ;
    float const t = (radius - CentreFloorMaxRadius)
        / (RingInnerRadius - CentreFloorMaxRadius);
    return PlatformFrame::FloorLocalZ + t * (RingLocalZ - PlatformFrame::FloorLocalZ);
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

inline bool OnFloorArea(LocalPoint point)
{
    return Length(point) <= MaxFloorRadius && !NearPillar(point);
}

// Pillar standing slots: the prototype stands on the pillar centre, so slots
// sit a few yards toward the arena centre where every member stays inside the
// prototype's 7.2-yard melee reach and on the pillar top.
inline LocalPoint PillarSlot(uint8 pillar, uint8 slot)
{
    LocalPoint const centre = PillarCenters[pillar % 3];
    float const inward = AngleOf(centre) + Pi;
    static constexpr float Lateral[4] = { 0.0f, 2.2f, -2.2f, 0.0f };
    static constexpr float Depth[4] = { 3.0f, 3.2f, 3.2f, 1.6f };
    uint8 const index = slot % 4;
    LocalPoint const base = Offset(centre, inward, Depth[index]);
    return Offset(base, inward + Pi / 2.0f, Lateral[index]);
}

// Floor spot at the foot of a pillar, on the arena side.
inline LocalPoint PillarBase(uint8 pillar, uint8 slot)
{
    float const angle = AngleOf(PillarCenters[pillar % 3]);
    float const lateral = (float(slot % 4) - 1.5f) * 2.5f;
    return Offset(Polar(angle, PillarBaseRadius), angle + Pi / 2.0f,
        lateral);
}
}

#endif

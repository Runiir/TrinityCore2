#ifndef TRINITY_BOT_MALORIAK_GEOMETRY_H
#define TRINITY_BOT_MALORIAK_GEOMETRY_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"

#include <algorithm>
#include <cmath>

// Logical formation anchors in Maloriak's laboratory (map 669). They are
// destinations for ordinary native pathing, never positions to set. The room
// rectangle and the staging/add points were checked against the pinned
// 669 navmesh tiles (every point has a floor polygon at z 73-74).
namespace BotEncounter::Maloriak
{
constexpr float RoomMinX = -146.0f;
constexpr float RoomMaxX = -67.0f;
constexpr float RoomMinY = -496.0f;
constexpr float RoomMaxY = -412.0f;
constexpr float RoomFloorZ = 73.6f;

// Room entrance line (north), about 28-30 yards from Maloriak's spawn
// (-105.79, -462.58), outside his aggro radius.
constexpr float StagingY = -434.0f;
constexpr float StagingCenterX = -105.5f;
constexpr float StagingSpacing = 4.0f;

// Aberration/Prime Subject tanking spots: north-west and north-east of the
// room, at least 10 yards (Growth Catalyst radius) from the boss.
constexpr Vector3 AddAnchorWest{ -130.0f, -434.0f, RoomFloorZ };
constexpr Vector3 AddAnchorEast{ -81.0f, -434.0f, RoomFloorZ };
constexpr float AddAnchorBossClearance = 20.0f;
// The side the holder already uses is kept until the boss comes within
// 15 yards of it, so a boss drifting around 20 yards does not flip it.
constexpr float AddAnchorHysteresis = 5.0f;

// Red: Scorching Blast is a 60-yard frontal cone (client ConeDegrees 70)
// split among targets, so the raid stands in front, close to the boss-tank
// line. Other phases keep the raid behind and to the sides (Engulfing
// Darkness cone, Magma Jets line) spread at least 5 yards (Flash Freeze and
// Biting Chill radii).
constexpr float FrontStackDistance = 14.0f;
constexpr float FrontStackRowSpacing = 5.0f;
constexpr float FrontStackLateralSpacing = 3.5f;
constexpr float MeleeRingRadius = 3.5f;
constexpr float RangedSpreadRadius = 18.0f;
constexpr float BehindRangedDistance = 14.0f;
constexpr float Pi = 3.14159265358979323846f;

struct BossFrame
{
    Vector3 Boss;
    // Unit vector from the boss toward its front (the main tank).
    float Ux = 1.0f;
    float Uy = 0.0f;

    float Vx() const { return -Uy; }
    float Vy() const { return Ux; }
};

inline Vector3 ClampToRoom(Vector3 point)
{
    point.X = std::clamp(point.X, RoomMinX, RoomMaxX);
    point.Y = std::clamp(point.Y, RoomMinY, RoomMaxY);
    if (point.Z < RoomFloorZ - 4.0f || point.Z > RoomFloorZ + 5.0f)
        point.Z = RoomFloorZ;
    return point;
}

// The front is the observed direction toward the main tank when the tank is
// in melee reach; otherwise the boss's own facing.
inline BossFrame ResolveFrame(ActorSnapshot const& boss,
    ActorSnapshot const* mainTank)
{
    BossFrame frame;
    frame.Boss = boss.Position;
    frame.Ux = std::cos(boss.Facing);
    frame.Uy = std::sin(boss.Facing);
    if (mainTank && mainTank->Alive)
    {
        float const dx = mainTank->Position.X - boss.Position.X;
        float const dy = mainTank->Position.Y - boss.Position.Y;
        float const length = std::sqrt(dx * dx + dy * dy);
        if (length > 0.5f && length < 12.0f)
        {
            frame.Ux = dx / length;
            frame.Uy = dy / length;
        }
    }
    return frame;
}

inline Vector3 FramePoint(BossFrame const& frame, float forward, float lateral)
{
    return ClampToRoom({ frame.Boss.X + frame.Ux * forward + frame.Vx() * lateral,
        frame.Boss.Y + frame.Uy * forward + frame.Vy() * lateral, frame.Boss.Z });
}

inline Vector3 FramePolar(BossFrame const& frame, float radius, float angleFromFront)
{
    float const c = std::cos(angleFromFront);
    float const s = std::sin(angleFromFront);
    return FramePoint(frame, radius * c, radius * s);
}

// Ranged rows of five in front: at 14 yards a 7-yard lateral offset stays
// 26.6 degrees off the line, inside the 35-degree half cone.
inline Vector3 FrontStackSlot(BossFrame const& frame, std::size_t index)
{
    static constexpr float Lateral[5] = { 0.0f, -1.0f, 1.0f, -2.0f, 2.0f };
    std::size_t const row = index / 5;
    return FramePoint(frame, FrontStackDistance + FrontStackRowSpacing * float(row),
        Lateral[index % 5] * FrontStackLateralSpacing);
}

// Melee in front beside the tank, 25 degrees left and right at melee reach,
// further melee 10 degrees off the line at 6 yards: all inside the cone.
inline Vector3 FrontMeleeSlot(BossFrame const& frame, std::size_t index)
{
    float const side = index % 2 ? -1.0f : 1.0f;
    bool const innerRing = (index / 2) % 2 == 0;
    float const angle = side * (innerRing ? 25.0f : 10.0f) * Pi / 180.0f;
    return FramePolar(frame, innerRing ? MeleeRingRadius : 6.0f, angle);
}

// Ranged fan across the back half (100 degrees either side of the rear),
// 18 yards out: six players are 40 degrees (12 yards) apart.
inline Vector3 BackRangedSlot(BossFrame const& frame, std::size_t index,
    std::size_t count)
{
    float const span = 200.0f * Pi / 180.0f;
    float const offset = count > 1
        ? -span / 2.0f + span * float(index) / float(count - 1) : 0.0f;
    return FramePolar(frame, RangedSpreadRadius, Pi + offset);
}

// Melee behind: 50 degrees either side of the rear at 3.5 yards (5.4 yards
// apart), a third melee straight behind at 8 yards (6.3 yards from both).
inline Vector3 BackMeleeSlot(BossFrame const& frame, std::size_t index)
{
    if (index % 3 == 2)
        return FramePolar(frame, 8.0f, Pi);
    float const side = index % 3 == 0 ? 1.0f : -1.0f;
    return FramePolar(frame, MeleeRingRadius, Pi + side * (50.0f * Pi / 180.0f));
}

inline Vector3 BehindSlot(BossFrame const& frame, bool melee)
{
    return FramePolar(frame, melee ? MeleeRingRadius : BehindRangedDistance, Pi);
}

inline Vector3 StagingSlot(std::size_t index, std::size_t count)
{
    float const offset = (float(index) - float(count > 0 ? count - 1 : 0) / 2.0f)
        * StagingSpacing;
    return { StagingCenterX + offset, StagingY, RoomFloorZ };
}

// A holder this close to an anchor is using that side.
constexpr float AddAnchorHeldRadius = 12.0f;

// West unless the boss stands within 20 yards of it. A holder (the
// off-tank) standing at one side keeps it while the boss stays 15 yards or
// more from it.
inline Vector3 AddAnchorFor(Vector3 const& bossPosition,
    Vector3 const* holder = nullptr)
{
    Vector3 const preferred =
        Distance2d(bossPosition, AddAnchorWest) < AddAnchorBossClearance
        ? AddAnchorEast : AddAnchorWest;
    if (!holder)
        return preferred;
    bool const atWest = Distance2d(*holder, AddAnchorWest) <= AddAnchorHeldRadius;
    bool const atEast = Distance2d(*holder, AddAnchorEast) <= AddAnchorHeldRadius;
    if (atWest == atEast)
        return preferred;
    Vector3 const current = atWest ? AddAnchorWest : AddAnchorEast;
    Vector3 const other = atWest ? AddAnchorEast : AddAnchorWest;
    if (Distance2d(bossPosition, current)
        >= AddAnchorBossClearance - AddAnchorHysteresis)
        return current;
    return Distance2d(bossPosition, other) > Distance2d(bossPosition, current)
        ? other : current;
}

// A point exitDistance yards from danger on the far side of the actor; the
// actor's facing breaks the tie when it stands on the danger itself.
inline Vector3 AwayFromPoint(ActorSnapshot const& actor, Vector3 const& danger,
    float exitDistance)
{
    float dx = actor.Position.X - danger.X;
    float dy = actor.Position.Y - danger.Y;
    float length = std::sqrt(dx * dx + dy * dy);
    if (length < 0.01f)
    {
        dx = std::cos(actor.Facing);
        dy = std::sin(actor.Facing);
        length = 1.0f;
    }
    return ClampToRoom({ danger.X + dx / length * exitDistance,
        danger.Y + dy / length * exitDistance, actor.Position.Z });
}
}

#endif

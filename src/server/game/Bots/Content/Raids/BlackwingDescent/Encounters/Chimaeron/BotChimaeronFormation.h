#ifndef TRINITY_BOT_CHIMAERON_FORMATION_H
#define TRINITY_BOT_CHIMAERON_FORMATION_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Chimaeron/BotChimaeronDutyPlan.h"

#include <algorithm>
#include <cmath>
#include <optional>
#include <vector>

// Formation geometry. Destinations are logical anchors on the chamber floor;
// native pathing and movement splines resolve the terrain.
//
// - Mixture phase: every member stands in a slot at least ~8 yd from every
//   other slot, so a Caustic Slime (split within 6 yd of the impact) lands on
//   its target alone and its -75% hit debuff touches nobody else, even with
//   every member at the edge of its arrival tolerance. Two current
//   Cataclysm Classic guides (Wowhead 2024-06-04, Icy Veins 2024-07-29) both
//   prescribe this spread while the mixture is up.
// - Outage (Systems Failure): the raid collapses into one stack behind the boss
//   so each Slime is split across the whole raid.
// - Prewake: the Break tank stands closest to the sleeping boss, because the
//   native wake-up attacks the nearest player within 70 yd.
namespace BotEncounter::Chimaeron
{
struct Point
{
    float X = 0.0f;
    float Y = 0.0f;
};

// Tanks hold the boss facing north (towards Finkle's cage); the raid works
// south of him, where the chamber is deepest.
constexpr Point RaidForward{ 0.0f, 1.0f };
// Chamber bounds: extent of the Bile-O-Tron 800 patrol path (TDB waypoint_data
// 4441800, x -136.2..-71.5, y -22.3..43.0), inset by 3 yd.
constexpr float ChamberMinX = -133.0f;
constexpr float ChamberMaxX = -74.5f;
constexpr float ChamberMinY = -19.0f;
constexpr float ChamberMaxY = 40.0f;
// The boss is tanked in place: his combat reach is 20 yd (display 33308), so
// both tank slots are inside his melee range and he never needs to move.
constexpr float AnchorLeashYards = 12.0f;
constexpr float BreakTankDistance = 10.0f;
constexpr float DoubleAttackTankDistance = 13.0f;
constexpr float DoubleAttackTankAngle = -60.0f;
constexpr float MeleeRadius = 11.0f;
constexpr float RangedRadius = 22.0f;
// Layout capacities that keep every pair of spread slots at least
// MinimumSpreadSlotGap apart: up to three melee on the inner arc (60 degrees
// apart when three), up to six members on the 22 yd arc (30 degrees apart at
// most), and any overflow on a 33 yd arc 20 degrees apart (11 yd outside the
// 22 yd arc; healers always stay on the 22 yd arc, within heal range of the
// tanks). Melee range against Chimaeron is 22.8 yd, so the 22 yd arc still
// reaches him.
constexpr std::size_t InnerMeleeCapacity = 3;
constexpr std::size_t RangedArcCapacity = 6;
constexpr float OuterRangedRadius = 33.0f;
constexpr float OuterRangedStep = 20.0f;
constexpr float StackBehindDistance = 8.0f;
constexpr float StackRingRadius = 1.5f;
constexpr float PrewakeBreakTankDistance = 9.0f;
constexpr float PrewakeMinimumOthers = 16.0f;
// Arrival tolerance around a spread slot. The closest two spread slots are
// the melee pair (+/-30 degrees at 11 yd: 11.0 yd apart); two members each off
// their slot by the tolerance toward each other stay 7 yd apart, outside the
// 6 yd Caustic Slime split.
constexpr float MinimumSpreadSlotGap = 11.0f;
constexpr float SpreadTolerance = 2.0f;
static_assert(MinimumSpreadSlotGap - 2.0f * SpreadTolerance > 6.0f,
    "spread tolerance lets two members share a Caustic Slime split");
constexpr float StackTolerance = 1.0f;

inline Point Rotate(Point vector, float degrees)
{
    float const radians = degrees * 3.14159265358979323846f / 180.0f;
    float const c = std::cos(radians);
    float const s = std::sin(radians);
    return { vector.X * c - vector.Y * s, vector.X * s + vector.Y * c };
}

inline Point Offset(Point origin, Point direction, float distance)
{
    return { origin.X + direction.X * distance, origin.Y + direction.Y * distance };
}

inline Point ClampToChamber(Point point)
{
    return { std::clamp(point.X, ChamberMinX, ChamberMaxX),
        std::clamp(point.Y, ChamberMinY, ChamberMaxY) };
}

inline float Distance(Point left, Point right)
{
    return std::hypot(left.X - right.X, left.Y - right.Y);
}

inline Point ToPoint(Vector3 const& position)
{
    return { position.X, position.Y };
}

// Formation centre: the route node (the boss's home) while the boss is tanked
// in place, otherwise the boss himself. A fixed centre keeps every slot still
// while the boss turns between the two tanks.
inline Point FormationCentre(Blackboard const& board, ActorSnapshot const& boss)
{
    Point const bossPoint = ToPoint(boss.Position);
    if (!board.Route.NavigationHints.empty())
    {
        Point const home = ToPoint(board.Route.NavigationHints.front());
        if (Distance(home, bossPoint) <= AnchorLeashYards)
            return home;
    }
    return bossPoint;
}

inline Point RearDirection()
{
    return { -RaidForward.X, -RaidForward.Y };
}

// Symmetric fan behind the boss, evenly spaced over [-span, +span]: six
// members on the 22 yd arc over +/-75 degrees sit 30 degrees (11.4 yd) apart.
inline float FanAngle(std::size_t index, std::size_t count, float span)
{
    if (count <= 1)
        return 0.0f;
    float const step = 2.0f * span / float(count - 1);
    return -span + step * float(index);
}

inline std::optional<std::size_t> IndexOf(std::vector<ObjectGuid> const& guids, ObjectGuid guid)
{
    auto itr = std::find(guids.begin(), guids.end(), guid);
    if (itr == guids.end())
        return std::nullopt;
    return std::size_t(itr - guids.begin());
}

// Members on the ranged arcs, in slot order: healers first (they must stay
// on the 22 yd arc), then ranged damage, then melee beyond the inner arc.
inline std::vector<ObjectGuid> RangedSlotOrder(Duties const& duties)
{
    std::vector<ObjectGuid> order = duties.RangedHealers;
    for (ObjectGuid guid : duties.Ranged)
        if (std::find(order.begin(), order.end(), guid) == order.end())
            order.push_back(guid);
    for (std::size_t index = InnerMeleeCapacity; index < duties.Melee.size(); ++index)
        order.push_back(duties.Melee[index]);
    return order;
}

inline std::optional<Point> SpreadSlot(Duties const& duties, Point centre, ObjectGuid guid)
{
    if (guid == duties.BreakTank)
        return ClampToChamber(Offset(centre, RaidForward, BreakTankDistance));
    if (guid == duties.DoubleAttackTank)
        return ClampToChamber(Offset(centre, Rotate(RaidForward, DoubleAttackTankAngle),
            DoubleAttackTankDistance));
    if (std::optional<std::size_t> index = IndexOf(duties.Melee, guid);
        index && *index < InnerMeleeCapacity)
    {
        // Two melee sit 30 degrees either side of the rear axis (11.0 yd
        // apart); three sit 60 degrees apart.
        std::size_t const count = std::min(duties.Melee.size(), InnerMeleeCapacity);
        float const span = count <= 2 ? 30.0f : 60.0f;
        float const angle = FanAngle(*index, count, span);
        return ClampToChamber(Offset(centre, Rotate(RearDirection(), angle), MeleeRadius));
    }
    std::vector<ObjectGuid> const order = RangedSlotOrder(duties);
    std::optional<std::size_t> const index = IndexOf(order, guid);
    if (!index)
        return std::nullopt;
    if (*index < RangedArcCapacity)
    {
        std::size_t const count = std::min(order.size(), RangedArcCapacity);
        float const angle = FanAngle(*index, count, 75.0f);
        return ClampToChamber(Offset(centre, Rotate(RearDirection(), angle), RangedRadius));
    }
    std::size_t const outerCount = order.size() - RangedArcCapacity;
    float const span = OuterRangedStep * float(outerCount - 1) / 2.0f;
    float const angle = FanAngle(*index - RangedArcCapacity, outerCount, span);
    return ClampToChamber(Offset(centre, Rotate(RearDirection(), angle), OuterRangedRadius));
}

inline Point StackCentre(Point centre)
{
    return ClampToChamber(Offset(centre, RearDirection(), StackBehindDistance));
}

// Everyone, tanks included, stands on a 1.5 yd ring around the stack centre:
// with a 1 yd arrival tolerance no two members are more than 5 yd apart.
inline Point StackSlot(Blackboard const& board, Point centre, ObjectGuid guid)
{
    std::vector<ObjectGuid> members;
    for (ActorSnapshot const& player : board.Players)
        members.push_back(player.Guid);
    std::sort(members.begin(), members.end(), [](ObjectGuid left, ObjectGuid right)
        {
            return left.GetRawValue() < right.GetRawValue();
        });
    Point const stack = StackCentre(centre);
    std::optional<std::size_t> const index = IndexOf(members, guid);
    if (!index || members.size() <= 1)
        return stack;
    float const angle = 360.0f * float(*index) / float(members.size());
    return Offset(stack, Rotate(RaidForward, angle), StackRingRadius);
}

inline std::optional<Point> PrewakeSlot(Duties const& duties, Point bossPoint, ObjectGuid guid)
{
    if (guid == duties.BreakTank)
        return ClampToChamber(Offset(bossPoint, RaidForward, PrewakeBreakTankDistance));
    std::optional<Point> slot = SpreadSlot(duties, bossPoint, guid);
    if (!slot)
        return std::nullopt;
    float const distance = Distance(*slot, bossPoint);
    if (distance < PrewakeMinimumOthers)
    {
        Point direction{ slot->X - bossPoint.X, slot->Y - bossPoint.Y };
        if (distance < 0.01f)
            direction = RearDirection();
        else
            direction = { direction.X / distance, direction.Y / distance };
        slot = ClampToChamber(Offset(bossPoint, direction, PrewakeMinimumOthers));
    }
    return slot;
}
}

#endif

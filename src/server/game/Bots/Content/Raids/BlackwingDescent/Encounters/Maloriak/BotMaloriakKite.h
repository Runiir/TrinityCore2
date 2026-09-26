#ifndef TRINITY_BOT_MALORIAK_KITE_H
#define TRINITY_BOT_MALORIAK_KITE_H

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakFormation.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Maloriak/BotMaloriakGeometry.h"

#include <algorithm>
#include <array>
#include <cmath>
#include <string_view>
#include <vector>

// The Feral off-tank's Aberration kite (user tactic, user raid experience
// 2026-09-26): controlled, away from Maloriak (Growth Catalyst reaches 10
// yards and buffs him too), never a spread. Pure geometry of one snapshot.
namespace BotEncounter::Maloriak
{
// Two small loops on the flanks of the tank spot, 22-32 yards from it: away
// from Maloriak and from the raid's slots around him, still within 40-yard
// spell reach of the ranged fan biased to that side, and clear of the
// cauldron's line-of-sight shadow. Travel order is the table order.
constexpr std::array<Vector3, 4> KiteLoopWest = { {
    { -128.0f, -446.0f, RoomFloorZ }, { -138.0f, -446.0f, RoomFloorZ },
    { -138.0f, -460.0f, RoomFloorZ }, { -128.0f, -460.0f, RoomFloorZ } } };
constexpr std::array<Vector3, 4> KiteLoopEast = { {
    { -83.6f, -446.0f, RoomFloorZ }, { -73.6f, -446.0f, RoomFloorZ },
    { -73.6f, -460.0f, RoomFloorZ }, { -83.6f, -460.0f, RoomFloorZ } } };
constexpr float KiteBossClearance = 20.0f;
constexpr float KitePackYards = 8.0f;
constexpr float KiteWaypointTolerance = 2.5f;
constexpr float KiteJoinYards = 12.0f;
constexpr float KiteHazardMargin = 2.0f;
constexpr float KiteSideMarginYards = 5.0f;
// A loop needs three usable waypoints: on two, the legs there and back
// overlap and the off-tank could turn round mid-leg.
constexpr std::size_t KiteMinimumWaypoints = 3;
// The hunter's Ice Trap for the kited pack is laid at the loop corner
// farthest from Maloriak; the hunter holds that post while the pack circles.
constexpr float KiteTrapTolerance = 3.0f;
// Roots on an Aberration (Entangling Roots, Nature's Grasp's roots, Frost
// Nova, Freeze): a rooted add cannot follow the kite.
constexpr std::array<uint32, 5> KiteRootAuras = { 339u, 19975u, 53313u, 122u, 33395u };

struct KiteGeometry
{
    std::vector<Vector3> Waypoints;   // travel order, the unusable ones dropped
    Vector3 Center{};
    Vector3 TrapCorner{};
};

inline bool IsRootedAdd(ActorSnapshot const& add)
{
    for (uint32 spellId : KiteRootAuras)
        if (HasAura(add, spellId))
            return true;
    return false;
}

inline float SegmentDistance(Vector3 const& from, Vector3 const& to, Vector3 const& point)
{
    float const dx = to.X - from.X;
    float const dy = to.Y - from.Y;
    float const length2 = dx * dx + dy * dy;
    float t = length2 > 0.0f
        ? ((point.X - from.X) * dx + (point.Y - from.Y) * dy) / length2 : 0.0f;
    t = std::clamp(t, 0.0f, 1.0f);
    return Distance2d({ from.X + dx * t, from.Y + dy * t, from.Z }, point);
}

// A straight path the off-tank (and the pack on its heels) may walk: it
// never comes closer to Maloriak than KiteBossClearance, nor to a hazard
// than its clearance; starting already closer, it must not get closer still.
inline bool KitePathClear(Vector3 const& from, Vector3 const& to, Vector3 const& boss,
    std::vector<FormationHazard> const& hazards)
{
    float const bossFloor = std::min(KiteBossClearance, Distance2d(from, boss) - 0.25f);
    if (SegmentDistance(from, to, boss) < bossFloor)
        return false;
    for (FormationHazard const& hazard : hazards)
    {
        float const floor = std::min(hazard.Clearance + KiteHazardMargin,
            Distance2d(from, hazard.Center) - 0.25f);
        if (SegmentDistance(from, to, hazard.Center) < floor)
            return false;
    }
    // The cauldron: the native path smooths corners, so a straight leg
    // must keep its line-of-sight radius plus the hazard margin from it.
    float const cauldronFloor = std::min(CauldronLosRadius + KiteHazardMargin,
        Distance2d(from, CauldronCenter) - 0.25f);
    if (SegmentDistance(from, to, CauldronCenter) < cauldronFloor)
        return false;
    return !CauldronConstrains(boss) || CauldronLineClear(boss, to);
}

inline bool KiteWaypointUsable(Vector3 const& point, Vector3 const& boss,
    std::vector<FormationHazard> const& hazards)
{
    if (!InRoom(point) || Distance2d(point, boss) < KiteBossClearance
        || (CauldronConstrains(boss) && !CauldronLineClear(boss, point)))
        return false;
    for (FormationHazard const& hazard : hazards)
        if (Distance2d(point, hazard.Center) < hazard.Clearance + KiteHazardMargin)
            return false;
    return true;
}

inline KiteGeometry BuildKiteLoop(std::array<Vector3, 4> const& loop, Vector3 const& boss,
    std::vector<FormationHazard> const& hazards)
{
    KiteGeometry kite;
    float sumX = 0.0f, sumY = 0.0f, farthest = -1.0f;
    for (Vector3 const& point : loop)
    {
        sumX += point.X;
        sumY += point.Y;
        if (!KiteWaypointUsable(point, boss, hazards))
            continue;
        kite.Waypoints.push_back(point);
        if (Distance2d(point, boss) > farthest)
        {
            farthest = Distance2d(point, boss);
            kite.TrapCorner = point;
        }
    }
    kite.Center = { sumX / 4.0f, sumY / 4.0f, RoomFloorZ };
    // Legs between the kept waypoints (a dropped corner makes a diagonal)
    // must themselves keep the clearance, else the loop is not usable.
    std::size_t const count = kite.Waypoints.size();
    bool legsClear = count >= KiteMinimumWaypoints;
    for (std::size_t index = 0; legsClear && index < count; ++index)
        legsClear = KitePathClear(kite.Waypoints[index],
            kite.Waypoints[(index + 1) % count], boss, hazards);
    if (!legsClear)
        kite.Waypoints.clear();
    return kite;
}

// The loop on the side away from Maloriak; the one the off-tank is already
// on while it stays usable. Empty when neither loop is usable.
inline KiteGeometry ResolveKite(Observation const& observation, Vector3 const& offTank)
{
    Vector3 const boss = observation.Boss->Position;
    std::vector<FormationHazard> const hazards = CollectFormationHazards(observation);
    KiteGeometry const west = BuildKiteLoop(KiteLoopWest, boss, hazards);
    KiteGeometry const east = BuildKiteLoop(KiteLoopEast, boss, hazards);
    auto usable = [](KiteGeometry const& kite) { return !kite.Waypoints.empty(); };
    bool const onWest = Distance2d(offTank, west.Center) <= KiteJoinYards;
    bool const onEast = Distance2d(offTank, east.Center) <= KiteJoinYards;
    if (onWest && usable(west))
        return west;
    if (onEast && usable(east))
        return east;
    // The loop clearly farther from Maloriak; with him near the middle, the
    // one nearer the off-tank.
    float const bossWest = Distance2d(boss, west.Center);
    float const bossEast = Distance2d(boss, east.Center);
    bool const preferWest = std::fabs(bossWest - bossEast) > KiteSideMarginYards
        ? bossWest > bossEast
        : Distance2d(offTank, west.Center) <= Distance2d(offTank, east.Center);
    if (usable(preferWest ? west : east))
        return preferWest ? west : east;
    return usable(preferWest ? east : west) ? (preferWest ? east : west) : KiteGeometry{};
}

struct KiteDecision
{
    bool Move = false;          // false: hold where the off-tank stands
    Vector3 Destination{};
    std::string_view Reason;
};

// The off-tank's next kite step. Off the loop it joins the nearest waypoint
// it can reach on a clear path; on it, it finishes its current leg, and from
// a waypoint it walks on to the next one reachable on a clear path once
// every mobile Aberration on it is within KitePackYards. It holds (an
// explicit hold, so the kite keeps its movement lease) while the pack
// catches up, while a rooted Aberration on it stands within that distance
// (the pack stays with it; a rooted one farther away rejoins when the root
// ends), when no clear path exists, and when no loop is usable.
inline KiteDecision KiteStep(KiteGeometry const& kite, Vector3 const& offTank,
    std::vector<ActorSnapshot const*> const& pack, Vector3 const& boss,
    std::vector<FormationHazard> const& hazards)
{
    KiteDecision hold{ false, offTank, "kite_hold" };
    std::size_t const count = kite.Waypoints.size();
    if (count < KiteMinimumWaypoints)
    {
        hold.Reason = "kite_no_usable_loop";
        return hold;
    }
    auto clear = [&](Vector3 const& to) { return KitePathClear(offTank, to, boss, hazards); };
    std::size_t nearest = 0;
    for (std::size_t index = 1; index < count; ++index)
        if (Distance2d(offTank, kite.Waypoints[index])
            < Distance2d(offTank, kite.Waypoints[nearest]))
            nearest = index;

    if (Distance2d(offTank, kite.Waypoints[nearest]) > KiteWaypointTolerance)
    {
        if (Distance2d(offTank, kite.Center) > KiteJoinYards)
        {
            // Join: the nearest waypoint with a clear straight path.
            std::vector<std::size_t> order(count);
            for (std::size_t index = 0; index < count; ++index)
                order[index] = index;
            std::sort(order.begin(), order.end(), [&](std::size_t left, std::size_t right)
            {
                return Distance2d(offTank, kite.Waypoints[left])
                    < Distance2d(offTank, kite.Waypoints[right]);
            });
            for (std::size_t index : order)
                if (clear(kite.Waypoints[index]))
                    return { true, kite.Waypoints[index], "kite_join" };
            hold.Reason = "kite_join_blocked";
            return hold;
        }
        // On the loop between two waypoints: the end of the leg it is on.
        std::size_t leg = 0;
        float best = -1.0f;
        for (std::size_t index = 0; index < count; ++index)
        {
            float const distance = SegmentDistance(kite.Waypoints[index],
                kite.Waypoints[(index + 1) % count], offTank);
            if (best < 0.0f || distance < best)
            {
                best = distance;
                leg = index;
            }
        }
        Vector3 const& end = kite.Waypoints[(leg + 1) % count];
        if (clear(end))
            return { true, end, "kite_leg" };
        hold.Reason = "kite_path_blocked";
        return hold;
    }

    for (ActorSnapshot const* add : pack)
    {
        float const distance = Distance2d(add->Position, offTank);
        if (IsRootedAdd(*add))
        {
            if (distance <= KitePackYards)
            {
                hold.Reason = "kite_rooted_pack";
                return hold;
            }
            continue;
        }
        if (distance > KitePackYards)
        {
            hold.Reason = "kite_pack_catch_up";
            return hold;
        }
    }
    for (std::size_t step = 1; step < count; ++step)
    {
        Vector3 const& next = kite.Waypoints[(nearest + step) % count];
        if (clear(next))
            return { true, next, "kite_advance" };
    }
    hold.Reason = "kite_path_blocked";
    return hold;
}
// The loop the off-tank actually kites on: the one it stands on, or the one
// it can join on a clear path. Empty while it holds elsewhere (no loop, or no
// safe transition to the selected one): then the kite is where it stands.
inline KiteGeometry OccupiedKite(Observation const& observation, Vector3 const& offTank,
    std::vector<ActorSnapshot const*> const& pack)
{
    KiteGeometry kite = ResolveKite(observation, offTank);
    if (kite.Waypoints.empty())
        return kite;
    if (Distance2d(offTank, kite.Center) <= KiteJoinYards)
        return kite;
    KiteDecision const join = KiteStep(kite, offTank, pack, observation.Boss->Position,
        CollectFormationHazards(observation));
    if (!join.Move)
        kite.Waypoints.clear();
    return kite;
}
}

#endif

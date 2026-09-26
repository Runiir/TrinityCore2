#ifndef TRINITY_BOT_VALIDATION_ROUTE_RECOVERY_RETURN_H
#define TRINITY_BOT_VALIDATION_ROUTE_RECOVERY_RETURN_H

// Post-wipe return to the boss node (pure decisions; the server adapter is
// BotWorldPopulationMgrValidationRouteRecoveryReturn.cpp).
//
// A released member resurrects at the instance entrance, far from the boss
// node. Round 3 BWD shards: as soon as the cohort's encounter observation saw
// the boss again, the encounter's adaptive plan owned every member wherever
// it stood. Its local moves cannot cross the instance (Maloriak: the
// entrance-line staging move from the lower-wing elevator took a path through
// a lower corridor, rejected route_destination_path_control_level_gap ~20
// times per member until the plateau watchdog; Omnotron: the plan gave the
// members at the entrance no movement at all), and the plan's ownership kept
// the route's own movement from walking them back.
//
// Scope: raid instances, on rows that opt in (row field composition_recovery,
// composition/canonical scenarios only). The accepted Magmaw diagnostic, the
// legacy shards and full route, every dungeon and calibration never arm.
//
// The member's return is route movement: from its resurrection until it is
// back within HandOffYards of the node's navigation anchor, the ordinary
// route movement (rides first, then the route anchor walk) owns it and the
// encounter's plan does not. The return ends at the hand-off, when the route
// moves on, or in the next attempt. Combat does not suspend it: a boss fight
// that goes on can hold every player in the instance in combat, and the
// route adapters handle a fight on the way as between any two nodes.
//
// It is bounded: NoProgressMs of observed time without coming ReturnProgressYards
// closer fails the attempt (route_recovery_return_unreachable). The clock
// pauses while an engaged recovery ride holds the member at its exit for the
// last living rider: the ride's own timeout bounds that wait. A node beyond a
// boarding-only transport (the Nefarian platform: no navmesh, no ride back)
// cannot be walked back to: a wipe there fails at the first return.

#include <cstdint>

namespace BotValidationRouteRecoveryReturn
{
// Beyond every boss route arrival radius (8 melee, 18 default, 30 ranged:
// BotWorldPopulationMgr.cpp), so the route anchor walk hands the member over
// before it considers it arrived: a returning ranged member inside the
// arrival radius would get the route adapter's boss engagement and could pull
// a sleeping Chimaeron without Finkle's Mixture.
constexpr float MaxRouteArrivalRadiusYards = 30.0f;
constexpr float HandOffYards = 35.0f;
static_assert(HandOffYards > MaxRouteArrivalRadiusYards,
    "the hand-off must lie beyond every route arrival radius");
// A ride waits up to one platform cycle (~17 s) per load and at the exit for
// the last living rider; the slowest round 3 party took ~70 s.
constexpr std::uint64_t NoProgressMs = 120000;
constexpr float ReturnProgressYards = 5.0f;
// A gap between observations longer than this (dead again, a native recovery
// hold, a decision pause) does not count toward NoProgressMs.
constexpr std::uint64_t PauseMs = 10000;
constexpr char const* UnreachablePrefix = "route_recovery_return_unreachable:";

// Only a composition raid row's boss node, with an anchor to walk to.
inline bool Eligible(bool routeEnabled, bool raidInstance, bool compositionRow,
    bool bossNode, bool anchorValid)
{
    return routeEnabled && raidInstance && compositionRow && bossNode && anchorValid;
}

// Per member: armed by a resurrection after a release on an eligible node.
struct Memory
{
    bool Pending = false;
    // "route_recovery_return" was recorded for this return.
    bool Announced = false;
    std::uint64_t AttemptId = 0;
    std::uint64_t RouteGeneration = 0;
    float BestDistance = 0.0f;
    std::uint64_t ProgressAtMs = 0;
    std::uint64_t SeenAtMs = 0;
};

inline void Arm(Memory& memory, std::uint64_t attemptId, std::uint64_t routeGeneration)
{
    memory = Memory();
    memory.Pending = true;
    memory.AttemptId = attemptId;
    memory.RouteGeneration = routeGeneration;
}

struct Input
{
    std::uint64_t AttemptId = 0;
    std::uint64_t RouteGeneration = 0;
    // Eligible(...) for the current node.
    bool Eligible = false;
    bool Alive = false;
    // In the world, on the route map, in the cohort's original instance.
    bool InRouteInstance = false;
    float DistanceToAnchor = 0.0f;
    // The node lies beyond a boarding-only transport, and the release came
    // from a wipe at this node.
    bool Blocked = false;
    bool WipedHere = false;
    // An engaged recovery ride holds the member at its exit for the party
    // (RecoveryRideHoldsMember): the return clock pauses.
    bool RideHolds = false;
    std::uint64_t NowMs = 0;
};

enum class Verdict : std::uint8_t { Idle, Returning, Arrived, Unreachable };

struct Decision
{
    Verdict Step = Verdict::Idle;
    // Unreachable: "no_progress" or "boarding_without_recovery".
    char const* Reason = "";
};

inline Decision Decide(Memory& memory, Input const& input)
{
    if (!memory.Pending)
        return {};
    // The route moved on, a new attempt began, or the node is not eligible:
    // nothing to return to.
    if (memory.AttemptId != input.AttemptId
        || memory.RouteGeneration != input.RouteGeneration || !input.Eligible)
    {
        memory = Memory();
        return {};
    }
    // Still dead, mid-teleport or outside the instance: the native death
    // recovery owns it; the return waits (and its clock pauses).
    if (!input.Alive || !input.InRouteInstance)
        return {};
    if (input.DistanceToAnchor <= HandOffYards)
    {
        memory = Memory();
        return { Verdict::Arrived };
    }
    if (input.Blocked)
    {
        // A member released while the fight goes on stays out of it; a wipe
        // here cannot be walked back to.
        memory = Memory();
        return input.WipedHere
            ? Decision{ Verdict::Unreachable, "boarding_without_recovery" } : Decision{};
    }
    if (!memory.SeenAtMs)
    {
        memory.BestDistance = input.DistanceToAnchor;
        memory.ProgressAtMs = input.NowMs;
    }
    else if (input.RideHolds || input.NowMs > memory.SeenAtMs + PauseMs)
        memory.ProgressAtMs += input.NowMs - memory.SeenAtMs;
    memory.SeenAtMs = input.NowMs;
    if (input.DistanceToAnchor + ReturnProgressYards <= memory.BestDistance)
    {
        memory.BestDistance = input.DistanceToAnchor;
        memory.ProgressAtMs = input.NowMs;
    }
    if (input.NowMs >= memory.ProgressAtMs + NoProgressMs)
    {
        memory = Memory();
        return { Verdict::Unreachable, "no_progress" };
    }
    return { Verdict::Returning };
}
}

#endif

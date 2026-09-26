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
// last living rider (the ride's own timeout bounds that wait) and, for at
// most ReturnTrashPauseCapMs per return, while a trash gate admitted trash met
// on the way within the last ReturnTrashFreshMs (ReturnTrashAdmitted). Combat
// alone never pauses it. A node beyond a
// boarding-only transport (the Nefarian platform: no navmesh, no ride back)
// cannot be walked back to: a wipe there fails at the first return.

#include <algorithm>
#include <cstdint>
#include <vector>

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

// A resurrection that closes a release: the release was requested, or its
// graveyard landing proven (the runback worldport through the instance
// entrance, the native corpse resurrection, clears the request before the
// first living tick), within a native recovery episode. Round 4
// atramedes_c0: eight releases and not one armed return.
inline bool ReleasedResurrection(bool releaseRequested, bool releaseLandingObserved,
    bool episodeStarted)
{
    return (releaseRequested || releaseLandingObserved) && episodeStarted;
}

// Trash met on the way back: a hostile attacking a raid member farther than
// this from the boss node's anchor, while the member returns, is ordinary
// trash between two nodes (round 4 atramedes_c0: the central-hall north
// patrol, 275 yd from the anchor, held all ten for 10 minutes as an
// undeclared boss-node target). The boss room itself stays closed.
constexpr float ReturnTrashMinAnchorYards = 100.0f;

// A pack mate of an admitted hostile (within ReturnTrashPackYards of where it
// was last admitted) is admitted as well, still outside the boss room: a
// patrol straddling the line (one mob first seen at 104 yd, another at 97 yd)
// is fought as one pack.
constexpr float ReturnTrashPackYards = 15.0f;

inline bool ReturnTrashAdmitted(bool returning, bool attacksRaidMember, float hostileAnchorYards,
    bool packMate = false)
{
    return returning && attacksRaidMember && (hostileAnchorYards > ReturnTrashMinAnchorYards
        || (packMate && hostileAnchorYards > ReturnTrashMinAnchorYards - ReturnTrashPackYards));
}

// Whether a boss node's trash block rejects. Not returning: as always, any
// engaged hostile (the area target). Returning: only when none of the engaged
// hostiles is admitted (the non-admitted are left out of the block's choices).
inline bool BossTrashBlockRejects(bool returning, std::uint32_t engagedCount, bool areaTarget,
    bool unadmittedEngaged)
{
    return returning ? !engagedCount && unadmittedEngaged : engagedCount > 0 && areaTarget;
}

// Fighting admitted return trash pauses the no-progress clock only while a
// gate admitted some within this long, and for at most the cap per return:
// an unreachable or evading admitted hostile still ends in the typed failure.
constexpr std::uint64_t ReturnTrashFreshMs = 2000;
constexpr std::uint64_t ReturnTrashPauseCapMs = 180000;

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
    // This tick's verdict was Returning, toward this anchor (the adapter's
    // record for the route's trash gates).
    bool Returning = false;
    float AnchorX = 0.0f, AnchorY = 0.0f, AnchorZ = 0.0f;
    // Return trash: when a gate last admitted some, the clock time paused for
    // it so far, and the hostiles admitted (raw GUID, where last admitted),
    // which stay admitted while alive and in combat until the return ends (a
    // pack pulled at 105 yd that chases a healer to 99 yd, or loses its victim
    // to a fear, is still fought).
    std::uint64_t ReturnTrashAtMs = 0;
    std::uint64_t TrashPausedMs = 0;
    struct Admitted { std::uint64_t Guid = 0; float X = 0.0f, Y = 0.0f, Z = 0.0f; };
    std::vector<Admitted> AdmittedHostiles;
};

inline bool RememberedReturnTrash(Memory const& memory, std::uint64_t hostileGuid)
{
    return std::any_of(memory.AdmittedHostiles.begin(), memory.AdmittedHostiles.end(),
        [hostileGuid](Memory::Admitted const& admitted) { return admitted.Guid == hostileGuid; });
}

inline bool ReturnTrashPackMate(Memory const& memory, float x, float y, float z)
{
    return std::any_of(memory.AdmittedHostiles.begin(), memory.AdmittedHostiles.end(),
        [x, y, z](Memory::Admitted const& admitted)
        {
            float const dx = admitted.X - x, dy = admitted.Y - y, dz = admitted.Z - z;
            return dx * dx + dy * dy + dz * dz <= ReturnTrashPackYards * ReturnTrashPackYards;
        });
}

inline void AdmitReturnTrash(Memory& memory, std::uint64_t hostileGuid, std::uint64_t nowMs,
    float x = 0.0f, float y = 0.0f, float z = 0.0f)
{
    auto admitted = std::find_if(memory.AdmittedHostiles.begin(), memory.AdmittedHostiles.end(),
        [hostileGuid](Memory::Admitted const& entry) { return entry.Guid == hostileGuid; });
    if (admitted == memory.AdmittedHostiles.end())
        memory.AdmittedHostiles.push_back({ hostileGuid, x, y, z });
    else
        *admitted = { hostileGuid, x, y, z };
    memory.ReturnTrashAtMs = nowMs;
}

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
    // (RecoveryRideHoldsMember): the clock pauses.
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
    else
    {
        std::uint64_t const gap = input.NowMs - memory.SeenAtMs;
        bool const fightingTrash = memory.ReturnTrashAtMs
            && input.NowMs <= memory.ReturnTrashAtMs + ReturnTrashFreshMs;
        if (input.RideHolds || gap > PauseMs)
            memory.ProgressAtMs += gap;
        else if (fightingTrash && memory.TrashPausedMs < ReturnTrashPauseCapMs)
        {
            std::uint64_t const paused =
                std::min(gap, ReturnTrashPauseCapMs - memory.TrashPausedMs);
            memory.ProgressAtMs += paused;
            memory.TrashPausedMs += paused;
        }
    }
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

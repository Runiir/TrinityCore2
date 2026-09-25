#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_RECOVERY_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_RECOVERY_H

// Pure decisions for recovery rides: a route node that lies across a ride
// between two levels (an elevator the route took, or would have taken, to
// reach it) declares that ride in its row's recovery_transport. When living
// members are back on the ride's boarding side (a wipe's runback respawns
// them there, and no walkable link leads down), the ride runs again as a
// prefix: board, ride, disembark, walk to its exit point. The node resumes
// once no living member needs it. The ride itself is the unchanged transport
// contract, executed by the ordinary transport logic.
//
// Only vertical rides are declared (the transport executor proves its
// platform animates only vertically), so which end a member is at is which
// of the two levels its feet are nearer.

#include "Bots/BotValidationRouteNativeTypes.h"

#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace BotValidationRouteNative
{
// At most this many rides precede one node.
constexpr std::size_t MaxRecoveryTransits = 4;
// A ride's two levels are at least this far apart; nearer levels would make
// "which end" ambiguous.
constexpr float MinRecoveryLevelSeparationYards = 8.0f;
// Failure prefix: the node lies across a ride the party must take and
// cannot (the platform is missing, the ride fails or times out).
constexpr char const* RecoveryFailurePrefix = "route_recovery_requires_transport:";

enum class RecoverySide : std::uint8_t { Board, Exit };

// Boarding level: where members wait (the approach start, else the wait
// point, else the board point). Exit level: the exit point, else the
// disembark point. False when either is missing.
inline bool RecoveryLevels(TransportContract const& ride, float& boardZ, float& exitZ)
{
    Point3 const& board = ride.Approach.StartPoint.Valid ? ride.Approach.StartPoint
        : ride.WaitPoint.Valid ? ride.WaitPoint : ride.BoardPoint;
    Point3 const& exit = ride.ExitPoint.Valid ? ride.ExitPoint : ride.DisembarkPoint;
    if (!board.Valid || !exit.Valid)
        return false;
    boardZ = board.Z;
    exitZ = exit.Z;
    return true;
}

inline RecoverySide SideOf(float z, float boardZ, float exitZ)
{
    return std::fabs(z - boardZ) < std::fabs(z - exitZ) ? RecoverySide::Board
        : RecoverySide::Exit;
}

// A ride applies to a node whose navigation anchor is at its exit end.
inline bool RecoveryApplies(TransportContract const& ride, float anchorZ)
{
    float boardZ = 0.0f;
    float exitZ = 0.0f;
    return RecoveryLevels(ride, boardZ, exitZ)
        && SideOf(anchorZ, boardZ, exitZ) == RecoverySide::Exit;
}

// One cohort member as a recovery ride sees it.
struct RecoveryMemberView
{
    std::uint64_t Guid = 0;
    bool Alive = false;
    // In the route's original instance and in the world.
    bool OnRouteInstance = false;
    // A passenger of this ride's platform.
    bool Aboard = false;
    // A walk, step or fall of the ride's approach in flight, or a native fall.
    bool InFlight = false;
    // Boarded during this ride and not yet at its exit point.
    bool Boarded = false;
    bool AtExit = false;
    bool InCombat = false;
    float Z = 0.0f;
};

// A living member on the route needs the ride while it is aboard or in
// flight, stands at the boarding end, or has ridden but not yet walked to
// the exit point. Dead members belong to the native death recovery.
inline bool MemberNeedsRide(RecoveryMemberView const& member, float boardZ, float exitZ)
{
    if (!member.Alive || !member.OnRouteInstance)
        return false;
    if (member.Aboard || member.InFlight)
        return true;
    if (SideOf(member.Z, boardZ, exitZ) == RecoverySide::Board)
        return true;
    return member.Boarded && !member.AtExit;
}

inline bool RideNeeded(std::vector<RecoveryMemberView> const& members, float boardZ,
    float exitZ)
{
    for (RecoveryMemberView const& member : members)
        if (MemberNeedsRide(member, boardZ, exitZ))
            return true;
    return false;
}

// A ride never pulls the party out of a fight below: it engages only while
// no living member that does not need it (one already at the exit end) is in
// combat. After a wipe nobody is below; after a partial death the rider rides
// once the fight is over. An engaged ride continues in combat.
inline bool RecoveryMayEngage(std::vector<RecoveryMemberView> const& members, float boardZ,
    float exitZ)
{
    for (RecoveryMemberView const& member : members)
        if (member.Alive && member.OnRouteInstance && member.InCombat
            && !MemberNeedsRide(member, boardZ, exitZ))
            return false;
    return true;
}

// Whether a member's ride state is left over from an earlier ride: back at
// the boarding end, neither aboard nor in flight, after it had boarded (it
// died below and ran back). It rides afresh.
inline bool StaleRiderState(RecoveryMemberView const& member, TransportMemberState const& state,
    float boardZ, float exitZ)
{
    return member.Alive && !member.Aboard && !member.InFlight
        && SideOf(member.Z, boardZ, exitZ) == RecoverySide::Board
        && (state.Boarded || state.Left);
}

// Per node and tick, the first applicable ride (in route order) that some
// member needs is run; rides nobody needs are passed. A ride engaged in the
// current scope stays engaged until nobody needs it.
enum class RecoveryStep : std::uint8_t { Idle, Engage, Ride, Complete };

inline RecoveryStep DecideRecoveryRide(bool applies, bool engaged, bool needed,
    bool mayEngage = true)
{
    if (!applies)
        return engaged ? RecoveryStep::Complete : RecoveryStep::Idle;
    if (needed)
        return engaged ? RecoveryStep::Ride
            : mayEngage ? RecoveryStep::Engage : RecoveryStep::Idle;
    return engaged ? RecoveryStep::Complete : RecoveryStep::Idle;
}

inline std::string RecoveryFailure(std::string const& transitNodeId, std::string const& reason)
{
    return std::string(RecoveryFailurePrefix) + transitNodeId
        + (reason.empty() ? std::string() : ":" + reason);
}
}

#endif

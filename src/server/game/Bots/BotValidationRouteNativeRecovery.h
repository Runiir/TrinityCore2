#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_RECOVERY_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_RECOVERY_H

// Pure decisions for recovery rides: a route node that lies across a ride
// between two levels (an elevator the route took, or would have taken, to
// reach it) declares that ride in its row's recovery_transport. When living
// members are back on the ride's boarding side (a wipe's runback respawns
// them there, and no walkable link leads down), the ride runs again as a
// prefix: board, ride, disembark, walk to its exit point. The node resumes
// once no living member needs it. The ride itself is the unchanged transport
// contract, executed by the ordinary transport logic. Recovery wakes (the
// second half of this header) redo a boss's waking interaction likewise.
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
    // A walk, step or fall of this ride's own approach in flight
    // (RecoveryMemberInFlight): never another transport's.
    bool InFlight = false;
    // Released (died and ran back) in this attempt: the only way a living
    // member comes back on the ride's boarding side.
    bool Released = false;
    // Boarded during this ride and not yet at its exit point.
    bool Boarded = false;
    bool AtExit = false;
    bool InCombat = false;
    float Z = 0.0f;
};

// A member is in flight for a ride only while that ride runs its approach:
// it is known to the ride's runtime (it took a ride step) and its approach
// phase is in flight or a native fall spline is running. Round 4 Nefarian
// c0: the Nefarian descent's own ledge drop (a native fall, its landing never
// reported once the ride took over, MOVEMENTFLAG_FALLING left set) engaged
// the lower-wing ride with no death and held all ten members until
// native_transport_timeout. The falling flag without a running spline (a
// knock-back or a step off the car's edge whose landing the ride's surface
// walk never reports) is not a fall in flight.
inline bool RecoveryMemberInFlight(bool knownToRide, bool approachInFlight, bool nativeFall)
{
    return knownToRide && (approachInFlight || nativeFall);
}

// A living member on the route needs the ride while it is aboard or in
// flight, stands at the boarding end after a release in this attempt (death
// evidence: nobody else comes back up there), or has ridden but not yet
// walked to the exit point. Dead members belong to the native death recovery.
inline bool MemberNeedsRide(RecoveryMemberView const& member, float boardZ, float exitZ)
{
    if (!member.Alive || !member.OnRouteInstance)
        return false;
    if (member.Aboard || member.InFlight)
        return true;
    if (SideOf(member.Z, boardZ, exitZ) == RecoverySide::Board)
        return member.Released;
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

// ---------------------------------------------------------------------------
// Recovery wakes (row field recovery_interaction)
// ---------------------------------------------------------------------------
// A boss that a native interaction wakes (Chimaeron: Finkle Einhorn's gossip
// starts the Bile-O-Tron's Finkle's Mixture, then the boss wakes) is asleep
// again after a wipe resets it, and the interaction's creature respawns. The
// nodes that wait for the boss declare that interaction (with its observed
// completion) and redo it as a prefix after the rides: only after a wipe at
// this node, or on composition raid rows an observed native reset without a
// wipe (the route's own interaction node woke the boss the first time; an
// earlier node's wipe never re-wakes it), while the encounter is not engaged,
// once the whole party is back at the node, until the wake's completion
// holds. A boss that respawns awake (Atramedes, 30 s after a failed attempt)
// satisfies its wake's completion and is never re-woken.
constexpr std::size_t MaxRecoveryInteractions = 2;
// Every loaded member, alive on the route, within this of the node anchor.
constexpr float RecoveryAssemblyYards = 40.0f;
// A wake that waits this long for the party fails the attempt, naming the
// member holding it; a gap in observation (nobody alive to tick, a native
// recovery hold) longer than RecoveryPauseMs does not count.
constexpr std::uint64_t RecoveryAssemblyTimeoutMs = 300000;
constexpr std::uint64_t RecoveryPauseMs = 10000;
constexpr char const* RecoveryInteractionFailurePrefix = "route_recovery_requires_interaction:";

// One cohort member as a recovery wake sees it.
struct RecoveryWakeView
{
    std::uint64_t Guid = 0;
    bool Alive = false;
    bool OnRouteInstance = false;
    bool InCombat = false;
    float DistanceToAnchor = 0.0f;
};

// The first member keeping the party from assembling, and why: dead,
// off_route (another map or instance, or mid-teleport) or away.
struct RecoveryWakeHolder
{
    std::uint64_t Guid = 0;
    char const* Reason = "";
};

inline RecoveryWakeHolder RecoveryAssemblyHolder(std::vector<RecoveryWakeView> const& members,
    float radiusYards = RecoveryAssemblyYards)
{
    for (RecoveryWakeView const& member : members)
    {
        if (!member.Alive)
            return { member.Guid, "dead" };
        if (!member.OnRouteInstance)
            return { member.Guid, "off_route" };
        if (member.DistanceToAnchor > radiusYards)
            return { member.Guid, "away" };
    }
    return {};
}

// The wake waits for the whole party: every loaded member alive in the route
// instance and at the node (a member still running back, or dead, holds it).
inline bool RecoveryPartyAssembled(std::vector<RecoveryWakeView> const& members,
    float radiusYards = RecoveryAssemblyYards)
{
    return !members.empty() && !RecoveryAssemblyHolder(members, radiusYards).Guid;
}

// Observe one tick of a wake waiting (or not) for the party; true once it has
// waited RecoveryAssemblyTimeoutMs of observed time.
inline bool RecoveryWaitTimedOut(RecoveryWait& wait, bool waiting, std::uint64_t nowMs)
{
    if (!waiting)
    {
        wait = RecoveryWait();
        return false;
    }
    if (!wait.SinceMs)
        wait.SinceMs = nowMs;
    else if (nowMs > wait.SeenMs + RecoveryPauseMs)
        wait.SinceMs += nowMs - wait.SeenMs;
    wait.SeenMs = nowMs;
    return nowMs >= wait.SinceMs + RecoveryAssemblyTimeoutMs;
}

inline bool RecoveryEncounterEngaged(std::vector<RecoveryWakeView> const& members)
{
    for (RecoveryWakeView const& member : members)
        if (member.Alive && member.OnRouteInstance && member.InCombat)
            return true;
    return false;
}

// Whether a wipe happened while the route was at this node: the scope's wipe
// generation passed the one first seen here in this attempt and route
// generation (the baseline is re-taken when either changes).
inline bool WipedSinceBaseline(RuntimeScope& baseline, RuntimeScope const& scope)
{
    if (baseline.AttemptId != scope.AttemptId
        || baseline.RouteGeneration != scope.RouteGeneration)
        baseline = scope;
    return scope.WipeGeneration > baseline.WipeGeneration;
}

// A trigger counts once it has held this long: Finkle and the Bile-O-Tron
// respawn 30 s after Chimaeron's evade, and Atramedes himself 30 s after his
// (his wake's completion then holds and it never runs).
constexpr std::uint64_t RecoveryWakeSettleMs = 45000;

// What starts a wake at this node: a wipe here (the wipe generation passed the
// one of the node's baseline) or, where resets trigger (composition raid
// rows), a native boss reset without a wipe (the raid's IN_PROGRESS ->
// NOT_STARTED/FAIL generation passed the baseline's). The baseline is the
// first scope seen here in this attempt and route generation, re-taken when a
// trigger is consumed (RetireRecoveryTrigger). A raised trigger settles
// RecoveryWakeSettleMs before it counts.
enum class RecoveryTrigger : std::uint8_t { None, Settling, Triggered };

inline RecoveryTrigger ObserveRecoveryTrigger(RecoveryBaseline& baseline,
    RuntimeScope const& scope, std::uint64_t resets, bool resetTriggers, std::uint64_t nowMs)
{
    if (baseline.Scope.AttemptId != scope.AttemptId
        || baseline.Scope.RouteGeneration != scope.RouteGeneration)
        baseline = RecoveryBaseline{ scope, resets, 0 };
    bool const raised = scope.WipeGeneration > baseline.Scope.WipeGeneration
        || (resetTriggers && resets > baseline.Resets);
    if (!raised)
        return RecoveryTrigger::None;
    if (!baseline.TriggeredAtMs)
        baseline.TriggeredAtMs = nowMs;
    return nowMs >= baseline.TriggeredAtMs + RecoveryWakeSettleMs
        ? RecoveryTrigger::Triggered : RecoveryTrigger::Settling;
}

enum class RecoveryWakeStep : std::uint8_t { Idle, Engage, Wake, Complete };

// An engaged wake runs until its completion holds or the encounter engages
// (either ends it); an idle one engages only once triggered at this node, out
// of combat, with the party assembled and the completion not holding.
inline RecoveryWakeStep DecideRecoveryWake(bool triggered, bool engaged,
    bool encounterEngaged, bool satisfied, bool assembled)
{
    if (engaged)
        return satisfied || encounterEngaged ? RecoveryWakeStep::Complete
            : RecoveryWakeStep::Wake;
    if (!triggered || encounterEngaged || satisfied || !assembled)
        return RecoveryWakeStep::Idle;
    return RecoveryWakeStep::Engage;
}

// How a raised trigger ends, so every wipe or reset at the node settles
// RecoveryWakeSettleMs of its own (a second Atramedes reset must not ring the
// bell inside his 30 s respawn: the respawn summons without an existence
// check). The wake's completion holding once the wake completed or the
// trigger settled (the wake did its job, or the boss respawned awake)
// consumes it: the baseline is re-taken at the current scope and resets. The
// encounter engaging first (a patrol, a fight) restarts the settle, counted
// again once the fight is over.
inline void RetireRecoveryTrigger(RecoveryBaseline& baseline, RuntimeScope const& scope,
    std::uint64_t resets, RecoveryTrigger trigger, RecoveryWakeStep step, bool satisfied,
    bool encounterEngaged)
{
    if (trigger == RecoveryTrigger::None && step != RecoveryWakeStep::Complete)
        return;
    if (satisfied && (step == RecoveryWakeStep::Complete || trigger == RecoveryTrigger::Triggered))
        baseline = RecoveryBaseline{ scope, resets, 0 };
    else if (encounterEngaged)
        baseline.TriggeredAtMs = 0;
}

// A recovery ride engaged on the node holds a member that no longer needs it
// (at the exit end, off the platform) until the last living rider is down;
// the ride's own timeout bounds that wait, so the member's return clock
// pauses meanwhile.
inline bool RecoveryRideHoldsMember(bool rideEngaged, TransportContract const& ride, float z,
    bool onTransport)
{
    float boardZ = 0.0f;
    float exitZ = 0.0f;
    return rideEngaged && !onTransport && RecoveryLevels(ride, boardZ, exitZ)
        && SideOf(z, boardZ, exitZ) == RecoverySide::Exit;
}

inline std::string RecoveryInteractionFailure(std::string const& wakeNodeId,
    std::string const& reason)
{
    return std::string(RecoveryInteractionFailurePrefix) + wakeNodeId
        + (reason.empty() ? std::string() : ":" + reason);
}
}

#endif

#ifndef TRINITY_BOT_VALIDATION_ROUTE_NATIVE_TRANSPORT_LOGIC_H
#define TRINITY_BOT_VALIDATION_ROUTE_NATIVE_TRANSPORT_LOGIC_H

// Pure transport logic for native route contracts: the observed platform
// state, its rest timeline, and each member's boarding, riding, leaving and
// final-approach phases. The server adapter supplies observations; nothing
// here touches game state. Included through BotValidationRouteNativeLogic.h.

#include "Bots/BotValidationRouteNativeApproach.h"
#include "Bots/BotValidationRouteNativeTypes.h"

#include <algorithm>
#include <cmath>
#include <cstdint>
#include <limits>
#include <string>
#include <utility>
#include <vector>

namespace BotValidationRouteNative
{
struct TransportFact
{
    bool Present = false;
    bool Ambiguous = false;
    std::uint32_t Entry = 0;
    std::uint64_t SpawnId = 0;
    std::uint32_t GoState = 0;
    // The native arrival time for the requested stop frame has passed.
    bool ArrivedAtStop = false;
    float PositionX = 0.0f;
    float PositionY = 0.0f;
    float PositionZ = 0.0f;
    float Orientation = 0.0f;
    float StationaryZ = 0.0f;
};

// GOState values (SharedDefines.h): 25 + n means "stop at stop frame n".
constexpr std::uint32_t GoStateTransportStopped = 25;

inline bool TransportAtStop(TransportFact const& fact, std::int32_t frame)
{
    return fact.Present && !fact.Ambiguous && frame >= 0
        && fact.GoState == GoStateTransportStopped + std::uint32_t(frame)
        && fact.ArrivedAtStop;
}

inline bool TransportAtLevel(TransportFact const& fact, float levelZ, float tolerance)
{
    return fact.Present && !fact.Ambiguous
        && std::fabs(fact.PositionZ - levelZ) <= tolerance;
}

// ---------------------------------------------------------------------------
// Transport geometry and timeline
// ---------------------------------------------------------------------------
struct LocalBox
{
    float MinX = 0.0f, MinY = 0.0f, MinZ = 0.0f;
    float MaxX = 0.0f, MaxY = 0.0f, MaxZ = 0.0f;
    bool Valid = false;
};

// World point to transport-local offset (rotation about Z by -orientation),
// matching TransportBase::CalculatePassengerOffset.
inline Point3 LocalOffset(float x, float y, float z, TransportFact const& transport)
{
    float const dx = x - transport.PositionX;
    float const dy = y - transport.PositionY;
    float const c = std::cos(transport.Orientation);
    float const s = std::sin(transport.Orientation);
    return { dx * c + dy * s, dy * c - dx * s, z - transport.PositionZ, true };
}

inline bool InsideBox(Point3 const& local, LocalBox const& box, float margin)
{
    return local.Valid && box.Valid
        && local.X >= box.MinX - margin && local.X <= box.MaxX + margin
        && local.Y >= box.MinY - margin && local.Y <= box.MaxY + margin
        && local.Z >= box.MinZ - margin && local.Z <= box.MaxZ + margin;
}

// TransportAnimation Z keyframes (time ms -> offset from the stationary
// origin) of a continuously cycling transport.
struct TransportTimeline
{
    std::vector<std::pair<std::uint32_t, float>> ZKeys;
    std::uint32_t PeriodMs = 0;

    float OffsetAt(std::uint32_t timeMs) const
    {
        if (ZKeys.empty())
            return 0.0f;
        if (timeMs <= ZKeys.front().first)
            return ZKeys.front().second;
        for (std::size_t i = 1; i < ZKeys.size(); ++i)
            if (timeMs <= ZKeys[i].first)
            {
                auto const& [t0, z0] = ZKeys[i - 1];
                auto const& [t1, z1] = ZKeys[i];
                float const f = t1 > t0 ? float(timeMs - t0) / float(t1 - t0) : 1.0f;
                return z0 + (z1 - z0) * f;
            }
        return ZKeys.back().second;
    }
};

constexpr std::uint64_t UnboundedRestMs = std::numeric_limits<std::uint64_t>::max();

// Milliseconds the platform keeps its origin within `tolerance` of
// `levelOffset` from `progressMs` on (0 when not at the level now).
inline std::uint64_t RestRemainingMs(TransportTimeline const& timeline,
    std::uint32_t progressMs, float levelOffset, float tolerance, std::uint32_t stepMs = 25)
{
    if (!timeline.PeriodMs || timeline.ZKeys.empty())
        return 0;
    auto atLevel = [&](std::uint32_t t)
    {
        return std::fabs(timeline.OffsetAt(t % timeline.PeriodMs) - levelOffset) <= tolerance;
    };
    if (!atLevel(progressMs))
        return 0;
    for (std::uint32_t elapsed = stepMs; elapsed <= timeline.PeriodMs; elapsed += stepMs)
        if (!atLevel(progressMs + elapsed))
            return elapsed - stepMs;
    return UnboundedRestMs;
}

inline bool TransportReadyToBoard(TransportContract const& contract, TransportFact const& fact)
{
    return contract.BoardStopFrame >= 0
        ? TransportAtStop(fact, contract.BoardStopFrame)
        : TransportAtLevel(fact, contract.BoardTransportZ, contract.LevelToleranceYards);
}

inline bool TransportAtExit(TransportContract const& contract, TransportFact const& fact)
{
    if (!contract.HasExit())
        return false;
    return contract.ExitStopFrame >= 0
        ? TransportAtStop(fact, contract.ExitStopFrame)
        : TransportAtLevel(fact, contract.ExitTransportZ, contract.LevelToleranceYards);
}

// ---------------------------------------------------------------------------
// Transport member phases
// ---------------------------------------------------------------------------
enum class TransportStep : std::uint8_t
{
    Hold,
    Stop,
    MoveToWait,
    MoveToBoard,
    Board,
    HoldAboard,
    MoveToDisembark,
    Leave,
    MoveToExit,
    // Final approach (TransportContract::Approach).
    MoveToApproachStart,
    SurfaceWalk,
    DropStepOff,
    DropFall,
    DropLand,
    // A passenger's proven straight walk across the platform to the
    // disembark point (approach contracts only).
    DisembarkWalk,
    Done,
    Blocked,
    Fail
};

inline char const* TransportStepName(TransportStep step)
{
    switch (step)
    {
        case TransportStep::Hold: return "hold";
        case TransportStep::Stop: return "stop";
        case TransportStep::MoveToWait: return "move_to_wait";
        case TransportStep::MoveToBoard: return "move_to_board";
        case TransportStep::Board: return "board";
        case TransportStep::HoldAboard: return "hold_aboard";
        case TransportStep::MoveToDisembark: return "move_to_disembark";
        case TransportStep::Leave: return "leave";
        case TransportStep::MoveToExit: return "move_to_exit";
        case TransportStep::MoveToApproachStart: return "move_to_approach_start";
        case TransportStep::SurfaceWalk: return "surface_walk";
        case TransportStep::DropStepOff: return "drop_step_off";
        case TransportStep::DropFall: return "drop_fall";
        case TransportStep::DropLand: return "drop_land";
        case TransportStep::DisembarkWalk: return "disembark_walk";
        case TransportStep::Done: return "done";
        case TransportStep::Blocked: return "blocked";
        case TransportStep::Fail: return "fail";
    }
    return "unknown";
}

// Margin between the planned walk and the end of a platform's rest window.
constexpr std::uint64_t BoardWindowMarginMs = 300;
// A member that stood on the platform is stranded only after it has been
// stationary (not walking, not falling) with no floor at all for this many
// consecutive observations spanning at least this long.
constexpr std::uint32_t StrandedConfirmObservations = 3;
constexpr std::uint64_t StrandedConfirmMs = 400;

struct TransportMemberObservation
{
    bool Alive = false;
    bool TransportPresent = false;
    bool TransportAmbiguous = false;
    bool ReadyToBoard = false;
    bool AtExit = false;
    bool OnThisTransport = false;
    bool OnOtherTransportOrVehicle = false;
    bool Moving = false;
    bool Falling = false;
    std::uint64_t NowMs = 0;
    // Floors directly underfoot, within the contract's floor tolerance.
    bool StaticFloorUnderfoot = false;
    // This transport's own model surface (not merely its bounding box).
    bool TransportFloorUnderfoot = false;
    // Remaining rest of the platform at the boarding level (UnboundedRestMs
    // for an arrived script-held stop frame), and the estimated walk time to
    // the board point along the native path.
    std::uint64_t RestRemainingMs = 0;
    std::uint64_t TravelToBoardMs = 0;
    float DistanceToWait = 0.0f;
    float DistanceToBoard = 0.0f;
    float DistanceToDisembark = 0.0f;
    float DistanceToExit = 0.0f;
    // Some floor (static or any model) within ResnapFloorBandYards of the
    // feet; sampled only when neither floor above is underfoot.
    bool FloorNear = false;
    // Final approach. Straight walk (and native fall) time from here.
    float DistanceToApproachStart = 0.0f;
    std::uint64_t ApproachTravelMs = 0;
    // MoveFall's falling spline is running / the falling flags remain with
    // no spline running (the fall ended, or a stop cut it short mid-air)
    // while the landing is not reported yet.
    bool FallSplineActive = false;
    bool LandingPending = false;
    float HealthPct = 1.0f;
    // Native fall damage predicted for the declared drop from here.
    float PredictedFallDamagePct = 0.0f;
    // Supervision of a walk or step in flight: a movement generator is
    // waiting to resume with no spline (UNIT_STATE_ROAMING_MOVE left set), or
    // the member left the corridor around the declared line (displaced).
    bool MotionSuspended = false;
    bool OffApproachCorridor = false;
    // Ledge drops start together: every living route member is at the
    // approach start, already past it (dropping or landed), or aboard.
    bool CohortAtApproachStart = false;
    // Held where it stands (stun, root, distract) or moved by a controlled
    // effect (fear, knockback, a fall): no walk or step can start now.
    bool MemberNotFree = false;
};

struct TransportDecision
{
    TransportStep Step = TransportStep::Hold;
    std::string Reason;
};

// A cycling platform's remaining rest must cover the whole approach, the
// boarding report after it and a margin; a script-held stop frame rests
// unbounded once arrived.
inline bool RestWindowCovers(std::uint64_t restRemainingMs, std::uint64_t travelMs)
{
    return restRemainingMs == UnboundedRestMs
        || restRemainingMs >= travelMs + ApproachBoardLatencyMs + BoardWindowMarginMs;
}

// A walk in flight continues only while the rest still covers what is left
// of it plus the boarding report (the launch margin may be spent).
inline bool RestStillCoversWalk(std::uint64_t restRemainingMs, std::uint64_t travelMs)
{
    return restRemainingMs == UnboundedRestMs
        || restRemainingMs >= travelMs + ApproachBoardLatencyMs;
}

// The member's own walk or step still runs as launched: moving, not
// suspended, inside its corridor.
inline bool ApproachMotionIntact(TransportMemberObservation const& observation)
{
    return observation.Moving && !observation.MotionSuspended
        && !observation.OffApproachCorridor;
}

// A member whose approach has left the ground or not yet boarded after it.
inline bool ApproachPhaseInFlight(ApproachPhase phase)
{
    return phase == ApproachPhase::Walking || phase == ApproachPhase::SteppingOff
        || phase == ApproachPhase::Falling || phase == ApproachPhase::Landed;
}

inline bool ApproachInFlight(TransportMemberState const& state)
{
    return ApproachPhaseInFlight(state.Approach);
}

// One cohort member as the node-level approach rules see it.
struct ApproachMemberView
{
    std::uint64_t Guid = 0;
    bool Alive = false;
    // In the route's original instance and in the world.
    bool OnRouteInstance = false;
    bool Aboard = false;
    ApproachPhase Phase = ApproachPhase::Idle;
    // A native fall is in progress (falling flags or a running fall spline).
    bool Falling = false;
    bool AtStart = false;
    // Health left after the predicted native fall damage keeps the margin.
    bool FallMarginOk = false;
};

// A member counts as at the approach start only within the start tolerance
// and on a verified floor there: a floor-probe miss holds the cohort while
// that member re-snaps, instead of letting the others drop without it.
inline bool AtApproachStart(float distanceToStart, float tolerance, bool floorUnderfoot)
{
    return distanceToStart <= tolerance && floorUnderfoot;
}

// Ledge drops start together, and only once every member can drop: the first
// living member that is not in the route instance, not at the approach start,
// or not healthy enough to drop from there holds the barrier (0: none). A
// member aboard, already past the start or falling never holds it, so a
// low-health member keeps the whole cohort at the lip (out of combat, where
// it regenerates and the healers beside it can top it up) instead of being
// left behind when the first passenger engages the encounter.
inline std::uint64_t CohortBarrierHolder(std::vector<ApproachMemberView> const& members)
{
    for (ApproachMemberView const& member : members)
    {
        if (!member.Alive)
            continue;
        if (!member.OnRouteInstance)
            return member.Guid;
        if (member.Aboard || member.Phase != ApproachPhase::Idle || member.Falling)
            continue;
        if (!member.AtStart || !member.FallMarginOk)
            return member.Guid;
    }
    return 0;
}

// The completion override is a fail-fast guard, never an early completion:
// the node still completes only when every member is aboard (the cohort
// barrier makes them drop together, so no early handover is needed).
enum class OverrideGuardStep : std::uint8_t { Off, Wait, AllAboard, Fail };

struct OverrideGuardDecision
{
    OverrideGuardStep Step = OverrideGuardStep::Off;
    std::string Reason;
    // The member the guard waits for (or fails on).
    std::uint64_t Member = 0;
};

// The guard arms once the override holds (an observed boss state, the
// encounter engaged) and some living member is aboard, the passenger who can
// have engaged it; a stale boss state with nobody aboard, or one that stops
// holding, disarms and resets the grace. Armed, it waits for members mid-
// walk, mid-step, mid-fall or landed but unboarded (seconds; the node timeout
// bounds them). A living member neither aboard nor in flight (held at the
// lip, off the route instance) gets ApproachHandoverGraceMs to start; then
// the node fails typed instead of waiting out its timeout with nothing left
// to drive that member's approach.
inline OverrideGuardDecision DecideOverrideGuard(std::vector<ApproachMemberView> const& members,
    bool overrideHolds, std::uint64_t& armedSinceMs, std::uint64_t nowMs)
{
    bool anyAboard = false;
    for (ApproachMemberView const& member : members)
        anyAboard = anyAboard || (member.Alive && member.Aboard);
    if (!overrideHolds || !anyAboard)
    {
        armedSinceMs = 0;
        return { OverrideGuardStep::Off, "", 0 };
    }
    if (!armedSinceMs)
        armedSinceMs = nowMs;
    std::uint64_t notAboard = 0;
    for (ApproachMemberView const& member : members)
    {
        if (!member.Alive)
            continue;
        if (member.Falling || (member.OnRouteInstance && !member.Aboard
                && ApproachPhaseInFlight(member.Phase)))
            return { OverrideGuardStep::Wait, "transport_completion_override_waiting_in_flight",
                member.Guid };
        if (!member.Aboard && !notAboard)
            notAboard = member.Guid;
    }
    if (!notAboard)
        return { OverrideGuardStep::AllAboard, "", 0 };
    if (nowMs >= armedSinceMs + ApproachHandoverGraceMs)
        return { OverrideGuardStep::Fail, "transport_completion_override_member_not_aboard",
            notAboard };
    return { OverrideGuardStep::Wait, "transport_completion_override_waiting_for_member",
        notAboard };
}

// A ledge drop in flight belongs to gravity until its landing is reported:
// nothing else may move, stop, re-snap or strand the member meanwhile.
inline bool DecideDropInFlight(TransportContract const& contract,
    TransportMemberObservation const& observation, TransportMemberState& state,
    TransportDecision& out)
{
    if (contract.Approach.Mode != ApproachMode::LedgeDrop)
        return false;
    switch (state.Approach)
    {
        case ApproachPhase::SteppingOff:
            if (ApproachMotionIntact(observation))
            {
                out = { TransportStep::Hold, "transport_drop_stepping_off" };
                return true;
            }
            // The step ended, was interrupted or displaced while still over a
            // floor: it never left the ledge. End any motion left behind (a
            // resumable generator would walk an unchecked line) and re-plan.
            if (observation.StaticFloorUnderfoot || observation.TransportFloorUnderfoot)
            {
                state.Approach = ApproachPhase::Idle;
                // A controlled effect that displaced it runs its course.
                if (observation.Moving && !observation.MemberNotFree)
                {
                    out = { TransportStep::Stop, "transport_drop_step_motion_lost" };
                    return true;
                }
                return false;
            }
            // No floor after the step, however it ended: gravity takes over now
            // (the fall clears whatever motion is left in the active slot).
            out = { TransportStep::DropFall, "transport_drop_fall" };
            return true;
        case ApproachPhase::Falling:
            if (observation.FallSplineActive)
            {
                out = { TransportStep::Hold, "transport_drop_falling" };
                return true;
            }
            if (observation.LandingPending)
            {
                out = { TransportStep::DropLand, "transport_drop_land" };
                return true;
            }
            state.Approach = ApproachPhase::Landed;
            return false;
        default:
            return false;
    }
}

// Settled with no floor within tolerance and never on the platform. A probe
// miss next to a real floor is repaired by an ordinary native-path move (its
// path starts on the nearest navmesh polygon and the spline follows it), a
// bounded number of times. With no floor anywhere near the feet the member
// stands on nothing a client could stand on: fail typed, never float it on.
inline TransportDecision DecideFloorUnverified(TransportContract const& contract,
    TransportMemberObservation const& observation, TransportMemberState& state)
{
    if (!observation.FloorNear)
        return { TransportStep::Fail, "transport_member_airborne_without_floor" };
    if (state.ResnapMoves >= MaxResnapMoves)
        return { TransportStep::Fail, "transport_member_floor_unverified" };
    ++state.ResnapMoves;
    char const* reason = "transport_member_floor_unverified_resnap";
    if (state.Boarded && contract.HasExit())
        return { TransportStep::MoveToExit, reason };
    if (contract.Approach.Mode != ApproachMode::None)
        return { TransportStep::MoveToApproachStart, reason };
    if (contract.WaitPoint.Valid)
        return { TransportStep::MoveToWait, reason };
    return { TransportStep::MoveToBoard, reason };
}

// Off the platform with a declared final approach: wait at the approach
// start on the static navmesh, then walk across (or step off and drop onto)
// the platform only when it is ready and its rest covers the whole approach.
inline TransportDecision DecideApproach(TransportContract const& contract,
    TransportMemberObservation const& observation, TransportMemberState& state)
{
    ApproachContract const& approach = contract.Approach;
    if (state.Approach == ApproachPhase::Landed)
        return approach.LandOnTransport
            ? TransportDecision{ TransportStep::Fail, "transport_drop_landed_off_platform" }
            : TransportDecision{ TransportStep::MoveToBoard, "transport_drop_landed_board_path" };
    // A stunned, rooted or effect-moved member (fear, knockback) is neither
    // pathed, stopped nor stepped off: the executor would refuse, and a stop
    // would cut the effect short. Wait it out without spending submissions.
    if (observation.MemberNotFree)
        return { TransportStep::Hold, "transport_approach_member_not_free" };
    float const startTolerance =
        std::min(contract.ArrivalToleranceYards, ApproachStartToleranceYards);
    if (observation.DistanceToApproachStart > startTolerance)
        return { TransportStep::MoveToApproachStart, "transport_approach_start_path" };
    if (observation.Moving)
        return { TransportStep::Stop, "transport_approach_start_settle" };
    if (!observation.ReadyToBoard)
        return { TransportStep::Hold, "transport_waiting" };
    if (!RestWindowCovers(observation.RestRemainingMs, observation.ApproachTravelMs))
        return { TransportStep::Hold, "transport_rest_window_too_short" };
    if (approach.Mode == ApproachMode::SurfaceWalk)
        return { TransportStep::SurfaceWalk, "transport_approach_surface_walk" };
    if (!observation.StaticFloorUnderfoot)
        return { TransportStep::Hold, "transport_drop_edge_floor_unverified" };
    if (observation.HealthPct - observation.PredictedFallDamagePct < approach.MinHealthAfterFallPct)
        return { TransportStep::Hold, "transport_drop_health_low" };
    // The cohort drops together, so the first passenger (who may start the
    // encounter) is never ahead of members still walking to the lip.
    if (!observation.CohortAtApproachStart)
        return { TransportStep::Hold, "transport_drop_waiting_for_cohort" };
    return { TransportStep::DropStepOff, "transport_drop_step_off" };
}

// Phase after an approach submission the executor accepted. A fall that
// found the member already grounded (Completed) has landed; a landing that
// found no floor under the feet fell again (Progressed) and is still falling.
inline ApproachPhase ApproachPhaseAfter(TransportStep step, bool completed,
    bool fellAgain = false)
{
    switch (step)
    {
        case TransportStep::SurfaceWalk: return ApproachPhase::Walking;
        case TransportStep::DropStepOff: return ApproachPhase::SteppingOff;
        case TransportStep::DropFall:
            return completed ? ApproachPhase::Landed : ApproachPhase::Falling;
        case TransportStep::DropLand:
            return fellAgain ? ApproachPhase::Falling : ApproachPhase::Landed;
        default: return ApproachPhase::Idle;
    }
}

// An approach armed or in flight wants the next observation promptly: a
// cycling platform's rest opening, a walk reaching the platform, a step
// ending over the void, a fall finalizing, or a ride reaching its exit
// level. Stop-frame transports rest unbounded, so waiting for them keeps
// the ordinary decision cadence.
inline bool ApproachWantsFollowUp(TransportContract const& contract,
    TransportDecision const& decision, TransportMemberState const& state)
{
    if (contract.Approach.Mode == ApproachMode::None)
        return false;
    if (state.Approach == ApproachPhase::Walking || state.Approach == ApproachPhase::SteppingOff
        || state.Approach == ApproachPhase::Falling)
        return true;
    switch (decision.Step)
    {
        case TransportStep::Stop:
        case TransportStep::Board:
        case TransportStep::SurfaceWalk:
        case TransportStep::DropStepOff:
        case TransportStep::DropFall:
        case TransportStep::DropLand:
        case TransportStep::DisembarkWalk:
        case TransportStep::Leave:
            return true;
        case TransportStep::HoldAboard:
            return contract.HasExit();
        case TransportStep::Hold:
            return decision.Reason == "transport_drop_waiting_for_cohort"
                || decision.Reason == "transport_approach_member_not_free"
                || (contract.BoardStopFrame < 0
                    && (decision.Reason == "transport_waiting"
                        || decision.Reason == "transport_rest_window_too_short"));
        default:
            return false;
    }
}

inline TransportDecision DecideTransportStep(TransportContract const& contract,
    TransportMemberObservation const& observation, TransportMemberState& state)
{
    if (!observation.Alive)
        return { TransportStep::Hold, "transport_member_dead" };
    if (observation.OnThisTransport)
        state.Boarded = true;
    if (observation.TransportAmbiguous)
        return { TransportStep::Blocked, "transport_ambiguous" };
    if (!observation.TransportPresent)
        return { TransportStep::Blocked, "transport_missing" };
    if (observation.OnOtherTransportOrVehicle && !observation.OnThisTransport)
        return { TransportStep::Blocked, "transport_member_on_other_transport" };
    if (state.FailedSubmissions >= contract.MaxSubmissions)
        return { TransportStep::Fail, "transport_submissions_exhausted" };

    if (observation.OnThisTransport)
    {
        state.Approach = ApproachPhase::Idle;
        state.FloorlessObservations = 0;
        state.FloorlessSinceMs = 0;
        if (!contract.HasExit())
            return { TransportStep::Done, "transport_boarded" };
        if (!observation.AtExit)
            return { TransportStep::HoldAboard, "transport_riding" };
        // The platform rests flush with the destination floor. Leave while
        // stationary over static ground, then walk off on the static navmesh
        // as a non-passenger.
        if (!observation.StaticFloorUnderfoot)
        {
            if (!contract.DisembarkPoint.Valid)
                return { TransportStep::Blocked, "transport_exit_no_static_floor" };
            if (contract.Approach.Mode != ApproachMode::None)
            {
                // Where the navmesh does not cover the platform the passenger
                // crosses its own surface in one proven straight walk.
                if (observation.Moving)
                    return { TransportStep::HoldAboard, "transport_exit_settling" };
                if (observation.DistanceToDisembark > contract.ArrivalToleranceYards)
                    return { TransportStep::DisembarkWalk, "transport_disembark_surface_walk" };
            }
            else if (observation.DistanceToDisembark > contract.ArrivalToleranceYards)
                return { TransportStep::MoveToDisembark, "transport_disembark_path" };
        }
        if (observation.Moving)
            return { TransportStep::HoldAboard, "transport_exit_settling" };
        if (!observation.StaticFloorUnderfoot)
            return { TransportStep::Blocked, "transport_disembark_no_static_floor" };
        return { TransportStep::Leave, "transport_exit_level_reached" };
    }

    TransportDecision drop;
    if (DecideDropInFlight(contract, observation, state, drop))
        return drop;

    // Not a passenger. Track the floor it stands on: only a member whose
    // last floor was this platform, and who has since been stationary with
    // no floor at all for a confirmed period, is stranded. A walking or
    // falling member may briefly sit above the vmap floor between path points.
    bool const onPlatformFloor = observation.TransportFloorUnderfoot
        && !observation.StaticFloorUnderfoot;
    bool const floorless = !observation.StaticFloorUnderfoot
        && !observation.TransportFloorUnderfoot;
    if (observation.StaticFloorUnderfoot)
        state.PlatformFloorSeen = false;
    else if (onPlatformFloor)
        state.PlatformFloorSeen = true;
    bool const settled = !observation.Moving && !observation.Falling;
    if (floorless && settled && state.PlatformFloorSeen)
    {
        if (!state.FloorlessObservations)
            state.FloorlessSinceMs = observation.NowMs;
        ++state.FloorlessObservations;
        if (state.FloorlessObservations >= StrandedConfirmObservations
            && observation.NowMs >= state.FloorlessSinceMs + StrandedConfirmMs)
            return { TransportStep::Fail, "transport_member_stranded_without_floor" };
        return { TransportStep::Hold, "transport_member_floor_lost_confirming" };
    }
    state.FloorlessObservations = 0;
    state.FloorlessSinceMs = 0;
    if (floorless && settled)
        return DecideFloorUnverified(contract, observation, state);
    if (!floorless)
        state.ResnapMoves = 0;

    if (state.Boarded && contract.HasExit())
    {
        state.Left = true;
        if (observation.DistanceToExit <= contract.ArrivalToleranceYards)
            return { TransportStep::Done, "transport_exit_reached" };
        return { TransportStep::MoveToExit, "transport_exit_path" };
    }

    bool const windowShort = observation.RestRemainingMs != UnboundedRestMs
        && observation.RestRemainingMs < observation.TravelToBoardMs + BoardWindowMarginMs;
    // Standing on this platform's own surface: board from here. The board
    // point is only the navigation target; the floor proves the stance, so a
    // walk that reached the platform stops and boards before it moves on.
    if (onPlatformFloor)
    {
        // First contact with the platform's own surface: stop there and board
        // at once, so the member is unboarded on it for as short as possible.
        if (observation.Moving)
            return { TransportStep::Stop, "transport_board_stop_on_platform" };
        return { TransportStep::Board, "transport_board_ready" };
    }

    // A surface walk in flight runs only as launched. Suspended, displaced or
    // outrun by the rest window, it is stopped (clearing the active slot, so
    // no generator resumes an unchecked line) and re-planned from scratch.
    if (state.Approach == ApproachPhase::Walking)
    {
        if (observation.Moving)
        {
            if (!ApproachMotionIntact(observation))
            {
                state.Approach = ApproachPhase::Idle;
                return observation.MemberNotFree
                    ? TransportDecision{ TransportStep::Hold, "transport_approach_member_not_free" }
                    : TransportDecision{ TransportStep::Stop, "transport_approach_motion_lost" };
            }
            if (!RestStillCoversWalk(observation.RestRemainingMs, observation.ApproachTravelMs))
            {
                state.Approach = ApproachPhase::Idle;
                return { TransportStep::Stop, "transport_approach_rest_lost" };
            }
            return { TransportStep::Hold, "transport_approach_walking" };
        }
        state.Approach = ApproachPhase::Idle;
    }
    if (contract.Approach.Mode != ApproachMode::None)
        return DecideApproach(contract, observation, state);

    if (!observation.ReadyToBoard)
    {
        if (contract.WaitPoint.Valid
            && observation.DistanceToWait > contract.ArrivalToleranceYards)
            return { TransportStep::MoveToWait, "transport_wait_path" };
        if (observation.Moving)
            return { TransportStep::Stop, "transport_not_ready_stop" };
        return { TransportStep::Hold, "transport_waiting" };
    }
    // Board only from this platform's own surface, never from static ground
    // that merely lies inside the model's bounding box.
    if (observation.DistanceToBoard <= contract.ArrivalToleranceYards)
        return { TransportStep::Blocked, "transport_board_point_not_on_platform_floor" };
    if (windowShort)
    {
        // Never let a walk toward the platform outrun its rest window.
        if (observation.Moving)
            return contract.WaitPoint.Valid
                && observation.DistanceToWait > contract.ArrivalToleranceYards
                ? TransportDecision{ TransportStep::MoveToWait, "transport_rest_window_short_retreat" }
                : TransportDecision{ TransportStep::Stop, "transport_rest_window_short_stop" };
        return { TransportStep::Hold, "transport_rest_window_too_short" };
    }
    return { TransportStep::MoveToBoard, "transport_board_path" };
}

// A walk, step or fall in flight owns the member's casting as well as its
// movement: a cast-time spell started meanwhile stops the member where it is
// (the bots' cast paths stop movement before a cast), cutting a step short on
// the lip or freezing a fall mid-air. A player finishes the step and the fall
// first; the hold claims the cast lanes for those few seconds.
inline bool ApproachHoldOwnsCasting(TransportDecision const& decision)
{
    return decision.Step == TransportStep::Hold
        && (decision.Reason == "transport_drop_stepping_off"
            || decision.Reason == "transport_drop_falling"
            || decision.Reason == "transport_approach_walking");
}

// A rejected submission always names the member's last rejection; it counts
// toward MaxSubmissions at most once per SubmissionRejectionWindowMs.
inline bool CountRejectedSubmission(TransportMemberState& state, std::uint64_t nowMs,
    std::string const& reason)
{
    state.LastRejection = reason;
    if (nowMs < state.NextCountedRejectionMs)
        return false;
    state.NextCountedRejectionMs = nowMs + SubmissionRejectionWindowMs;
    ++state.FailedSubmissions;
    return true;
}

// Node-level completion for one living member.
inline bool MemberTransportDone(TransportContract const& contract,
    bool onThisTransport, bool boarded, float distanceToExit)
{
    if (!contract.HasExit())
        return onThisTransport;
    return boarded && !onThisTransport
        && distanceToExit <= contract.ArrivalToleranceYards;
}
}

#endif

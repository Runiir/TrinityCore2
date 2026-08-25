#ifndef TRINITY_BOT_RAID_DRUDGE_GEOMETRY_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_GEOMETRY_STATE_H

#include <cstdint>
#include <string_view>
#include <vector>

namespace BotRaidDrudgeGeometry
{
struct Scope
{
    std::uint64_t AttemptId = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint64_t RouteGeneration = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    std::uint64_t Source0Identity = 0;
    std::uint64_t Source1Identity = 0;
};

inline bool operator==(Scope const& left, Scope const& right)
{
    return left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration
        && left.MapId == right.MapId
        && left.InstanceId == right.InstanceId
        && left.Source0Identity == right.Source0Identity
        && left.Source1Identity == right.Source1Identity;
}

inline bool operator!=(Scope const& left, Scope const& right)
{
    return !(left == right);
}

inline bool Valid(Scope const& scope)
{
    return scope.MapId != 0 && scope.InstanceId != 0
        && scope.Source0Identity != 0 && scope.Source1Identity != 0
        && scope.Source0Identity != scope.Source1Identity;
}

struct State
{
    Scope Identity;
    std::uint64_t LastChargeSequenceObserved = 0;
    bool PriorPathProofAvailable = false;
};

enum class Decision : std::uint8_t
{
    AwaitExactPrepull,
    StageCombatTanks,
    RecoverCombatAtTankAnchors,
    AllowNativeEngagement
};

enum class MemberRecoveryAction : std::uint8_t
{
    Continue,
    RecoverFormation,
    PreferFriendlySupport
};

// A landed Rush has two native movement legs.  The tank must arrive at its
// separately validated recovery anchor before the selector may request the
// declared combat/navigation anchor.  Completion remains gated until both
// return legs and the existing exact roster contract are true.
inline bool LandedRushRecoveryComplete(
    bool landedRushPending,
    bool allRecoveryAnchorsReached,
    bool allCombatTankPathsProven,
    bool allCombatTankAnchorsReached,
    bool exactRosterReseparated)
{
    return landedRushPending && allRecoveryAnchorsReached
        && allCombatTankPathsProven && allCombatTankAnchorsReached
        && exactRosterReseparated;
}

// A tank that has reached its landed-Rush recovery anchor must hold that
// native destination until the exact pair has reached their scoped recovery
// anchors.  Opening the combat return for one tank early lets its selector
// replace the recovery candidate before the other tank can finish its leg.
inline bool RecoveryTankReturnBarrierOpen(
    bool landedRushPending, bool allRecoveryAnchorsReached)
{
    return !landedRushPending || allRecoveryAnchorsReached;
}

inline bool AdvanceRecoveryTankReturnBarrier(bool& opened,
    bool landedRushPending, bool allRecoveryAnchorsReached)
{
    if (landedRushPending && allRecoveryAnchorsReached)
        opened = true;
    return RecoveryTankReturnBarrierOpen(landedRushPending, opened);
}

enum class MinimumDistanceOwner : std::uint8_t
{
    GenericRouteSafety,
    LandedRushRecovery
};

struct AnchorPathSearchDecision
{
    std::uint64_t RetryAfterMs = 0;
    bool SourceBlocked = false;
    bool SpacingBlocked = false;
    bool NativePathSearchDue = false;
};

// Dynamic source proximity and member spacing change as the assigned tanks
// pull the Drudges home after Rush. They must never consume or preserve the
// expensive native-path retry heartbeat: the first source-safe/spacing-safe
// edge owns an immediate PathGenerator attempt. Only an actual native path
// rejection may arm RetryAfterMs in production.
inline AnchorPathSearchDecision SelectAnchorPathSearch(
    std::uint64_t retryAfterMs, std::uint64_t nowMs,
    bool dynamicSourceSafe, bool dynamicSpacingSafe)
{
    AnchorPathSearchDecision decision;
    decision.SourceBlocked = !dynamicSourceSafe;
    decision.SpacingBlocked = dynamicSourceSafe && !dynamicSpacingSafe;
    decision.RetryAfterMs = decision.SourceBlocked || decision.SpacingBlocked
        ? 0 : retryAfterMs;
    decision.NativePathSearchDue = !decision.SourceBlocked
        && !decision.SpacingBlocked && nowMs >= decision.RetryAfterMs;
    return decision;
}

// Generic minimum-distance movement remains authoritative everywhere except
// an unresolved landed Drudge Rush.  In that window the exact observation is
// already the durable return obligation, so the Drudge recovery state must
// own both the outward safety exit and the return to the sealed anchor.  This
// prevents the generic handler from moving a member and returning before the
// specialized state can preserve/retry the corresponding formation proof.
inline MinimumDistanceOwner SelectMinimumDistanceOwner(
    bool drudgeLaneProfile, bool landedRushPending)
{
    return drudgeLaneProfile && landedRushPending
        ? MinimumDistanceOwner::LandedRushRecovery
        : MinimumDistanceOwner::GenericRouteSafety;
}

inline bool ExactDrudgeLaneOwnsGroupMovement(
    bool drudgeLaneProfile, bool exactPrepullStaged)
{
    return drudgeLaneProfile && exactPrepullStaged;
}

// Combat anchors are the second prepull phase.  Native source combat is an
// observed failure edge, not permission to reinterpret the exact member
// anchors before the roster latch has been recorded.
inline bool CombatTankStageLatched(bool exactPrepullStaged)
{
    return exactPrepullStaged;
}

inline bool DynamicGroupRecoveryActive(
    bool drudgeLaneProfile, bool exactPrepullStaged, bool landedRushPending)
{
    return drudgeLaneProfile && (exactPrepullStaged || landedRushPending);
}

inline bool ShouldInvalidateAnchorAfterPathRejection(
    std::string_view pathRejectReason, std::string_view recoveryResult)
{
    bool const floorRejected = pathRejectReason
        == "route_destination_path_floor_gap"
        || pathRejectReason == "drudge_anchor_path_floor_gap";
    return floorRejected && recoveryResult == pathRejectReason;
}

// A landed Rush owns movement priority for every displaced exact-roster
// member. Friendly support remains available while staging and after the
// healer is geometrically safe, but it cannot starve the bounded return to the
// sealed formation before the next native Rush edge.
inline MemberRecoveryAction SelectMemberRecoveryAction(
    bool landedRushPending, bool memberGeometrySafe, bool friendlySupportAvailable)
{
    if (landedRushPending && !memberGeometrySafe)
        return MemberRecoveryAction::RecoverFormation;
    if (friendlySupportAvailable)
        return MemberRecoveryAction::PreferFriendlySupport;
    return MemberRecoveryAction::Continue;
}

struct Input
{
    Scope Identity;
    std::uint64_t ChargeSequence = 0;
    bool ChargePending = false;
    bool ExactPrepullStaged = false;
    bool BothCombatTankPathsProven = false;
    bool BothCombatTankAnchorsSafe = false;
    bool SourceCombatStarted = false;
    bool CohortCombatLinked = false;
    bool ChargeQueueIdle = false;
    // The authoritative head observation has landed.  This is distinct from
    // ChargePending, which also covers the in-flight window.  After landing,
    // the assigned tanks must be allowed to use their ordinary native taunts
    // to pull the two Drudges back apart; requiring an already-empty queue
    // would make reseparation depend on an ownership action that cannot run.
    bool ChargeLanded = false;
    bool SourcesAlive = false;
    bool SourcesSeparated = false;
    bool SourcesOnFrozenLanes = false;
    bool TanksOnFrozenLanes = false;
    bool BoundTankSourceGeometrySafe = false;
    bool NativeMeleeStopBounded = false;
    bool EvaluatePriorPathProof = false;
    bool PriorProofScopeMatches = false;
    bool PriorProofCandidateMatches = false;
    bool MemberAtProvenAnchor = false;
    bool DynamicLaneSafe = false;
    bool DynamicSourceSafe = false;
    bool DynamicSpacingSafe = false;
};

struct Result
{
    State Next;
    Decision NextDecision = Decision::AwaitExactPrepull;
    bool ScopeReset = false;
    bool InvalidateAnchor = false;
    bool ReactivatePriorPathProof = false;
    bool SupportAllowed = false;
    bool TankMovementAllowed = false;
    bool NativeOwnershipAllowed = false;
    bool NativeEngagementAllowed = false;
};

struct Point2d
{
    float X = 0.0f;
    float Y = 0.0f;
};

// A landed Rush may move a source after the exact prepull anchors were
// proven.  The live post-Rush member contract therefore remains strict about
// source distance, lane placement, and peer spacing, without treating the
// stale prepull coordinate as a safety proof.
inline bool DynamicGroupPositionSafe(
    bool source0Safe, bool source1Safe, bool laneSafe,
    bool sameLaneSpacingSafe)
{
    return source0Safe && source1Safe && laneSafe && sameLaneSpacingSafe;
}

// Each tank's recovery path must remain entirely on its frozen half of the
// lane axis.  Requiring both tanks (and every point of either path) to retain
// at least half the minimum separation on opposite sides proves their
// projected pair distance cannot collapse below the configured minimum even
// when both movements execute concurrently.
inline bool RecoveryPathPreservesTankSeparation(
    std::vector<Point2d> const& path, float midpointX, float midpointY,
    float axisX, float axisY, float laneSign,
    float otherTankSignedProjection, float minimumSeparation)
{
    if (path.empty() || minimumSeparation <= 0.0f
        || (laneSign != -1.0f && laneSign != 1.0f))
        return false;

    float const signedFloor = minimumSeparation * 0.5f;
    if (otherTankSignedProjection < signedFloor)
        return false;
    for (Point2d const& point : path)
    {
        float const projection = (point.X - midpointX) * axisX
            + (point.Y - midpointY) * axisY;
        if (laneSign * projection < signedFloor)
            return false;
    }
    return true;
}

// Production supplies the native path/position facts and replay varies their
// ordering through this same transition. A Rush invalidates active anchor
// geometry exactly once at its observation edge, while an exact prior strict
// path proof remains available for guarded at-anchor reactivation.
inline Result Advance(State current, Input const& input)
{
    Result result;
    result.Next = current;
    if (result.Next.Identity != input.Identity)
    {
        result.Next = State{};
        result.Next.Identity = input.Identity;
        result.ScopeReset = true;
    }

    // The observation is queued before its native Rush lands.  Do not
    // invalidate the prepull anchor during that in-flight window: the
    // landing edge is the first authoritative displacement transition.
    if (input.ChargePending && input.ChargeLanded && input.ChargeSequence != 0
        && result.Next.LastChargeSequenceObserved != input.ChargeSequence)
    {
        result.Next.LastChargeSequenceObserved = input.ChargeSequence;
        result.InvalidateAnchor = true;
    }

    if (input.EvaluatePriorPathProof)
    {
        bool const exactStaticIdentity = input.PriorProofScopeMatches
            && Valid(input.Identity) && input.PriorProofCandidateMatches
            && input.MemberAtProvenAnchor;
        if (!exactStaticIdentity)
            result.Next.PriorPathProofAvailable = false;
        result.ReactivatePriorPathProof = result.Next.PriorPathProofAvailable
            && exactStaticIdentity && input.DynamicLaneSafe
            && input.DynamicSourceSafe && input.DynamicSpacingSafe;
    }

    // A body pull before the exact latch is an honest recovery edge. Keep the
    // exact scoped identity and require the native queue to be idle, but let
    // the assigned tanks finish the declared combat geometry and reclaim
    // ownership instead of deadlocking behind the prepull latch.
    bool const earlyPullRecovery = input.SourceCombatStarted
        && input.CohortCombatLinked && !input.ExactPrepullStaged
        && input.ChargeQueueIdle
        && input.SourcesAlive && input.TanksOnFrozenLanes
        && Valid(input.Identity);
    if (!input.ExactPrepullStaged && !earlyPullRecovery)
    {
        result.NextDecision = Decision::AwaitExactPrepull;
        return result;
    }

    // Once native body combat has begun, ordinary friendly class support is
    // allowed while the tanks finish the declared geometry. Hostile offense
    // and threat seeding remain gated by NativeEngagementAllowed. The exact
    // tanks receive a narrower ownership-only authority once both sealed
    // anchors are reached: native source separation depends on each Drudge
    // first following its assigned tank, so tying a real taunt to already-
    // separated or final-lane sources creates a circular wait after a body
    // pull. The actual taunt candidate still supplies native range/LOS gates.
    result.SupportAllowed = input.SourceCombatStarted;

    // Path discovery is a cohort barrier.  Both exact tank paths must be
    // proven from the shared prepull state before either tank may start the
    // combat-anchor movement.  This prevents a single pathable tank from
    // body-pulling the pack while the other tank is still path-rejected.
    if (!input.BothCombatTankPathsProven)
    {
        result.NextDecision = input.SourceCombatStarted
            ? Decision::RecoverCombatAtTankAnchors : Decision::StageCombatTanks;
        return result;
    }
    result.TankMovementAllowed = Valid(input.Identity);

    bool const ownershipWindow = input.ChargeQueueIdle
        || (input.ChargePending && input.ChargeLanded);
    bool const initialOwnershipSafe = input.ChargeQueueIdle
        && input.BothCombatTankAnchorsSafe;
    // A landed Rush can put the source beyond taunt range. The tanks may walk
    // toward it only while remaining on their frozen sides, use the ordinary
    // trained taunt, then return to their sealed anchors. Requiring them to be
    // at those anchors throughout would make the pull-back impossible.
    bool const landedRecoverySafe = input.ChargePending && input.ChargeLanded
        && input.TanksOnFrozenLanes;
    bool const ownershipSafe = ownershipWindow
        && (initialOwnershipSafe || landedRecoverySafe || earlyPullRecovery)
        && input.SourcesAlive && input.TanksOnFrozenLanes
        && (landedRecoverySafe || input.NativeMeleeStopBounded || earlyPullRecovery);
    result.NativeOwnershipAllowed = ownershipSafe && Valid(input.Identity);

    bool const dynamicEngagementSafe = input.ChargeQueueIdle && !input.ChargePending
        && input.SourcesAlive && input.SourcesSeparated && input.SourcesOnFrozenLanes
        && input.TanksOnFrozenLanes && input.BoundTankSourceGeometrySafe
        && input.NativeMeleeStopBounded;
    if (!input.BothCombatTankAnchorsSafe || !dynamicEngagementSafe)
    {
        result.NextDecision = input.SourceCombatStarted
            ? Decision::RecoverCombatAtTankAnchors : Decision::StageCombatTanks;
        return result;
    }

    result.NextDecision = Decision::AllowNativeEngagement;
    result.NativeEngagementAllowed = Valid(input.Identity);
    return result;
}
}

#endif

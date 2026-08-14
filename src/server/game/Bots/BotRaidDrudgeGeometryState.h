#ifndef TRINITY_BOT_RAID_DRUDGE_GEOMETRY_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_GEOMETRY_STATE_H

#include <cstdint>
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

struct Input
{
    Scope Identity;
    std::uint64_t ChargeSequence = 0;
    bool ChargePending = false;
    bool ExactPrepullStaged = false;
    bool BothCombatTankPathsProven = false;
    bool BothCombatTankAnchorsSafe = false;
    bool SourceCombatStarted = false;
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

    if (input.ChargePending && input.ChargeSequence != 0
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

    if (!input.ExactPrepullStaged)
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
        && (initialOwnershipSafe || landedRecoverySafe)
        && input.SourcesAlive && input.TanksOnFrozenLanes
        && input.NativeMeleeStopBounded;
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

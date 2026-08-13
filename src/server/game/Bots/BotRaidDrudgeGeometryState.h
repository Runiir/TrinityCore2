#ifndef TRINITY_BOT_RAID_DRUDGE_GEOMETRY_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_GEOMETRY_STATE_H

#include <cstdint>

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
    bool BothCombatTankAnchorsSafe = false;
    bool SourceCombatStarted = false;
    bool ChargeQueueIdle = false;
    bool SourcesSeparated = false;
    bool SourcesOnFrozenLanes = false;
    bool BoundTankSourceGeometrySafe = false;
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
    bool NativeEngagementAllowed = false;
};

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

    bool const dynamicEngagementSafe = input.ChargeQueueIdle && !input.ChargePending
        && input.SourcesSeparated && input.SourcesOnFrozenLanes
        && input.BoundTankSourceGeometrySafe;
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

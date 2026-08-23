#ifndef TRINITY_BOT_RAID_DRUDGE_THREAT_SEED_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_THREAT_SEED_STATE_H

#include <array>
#include <cstddef>
#include <cstdint>

namespace BotRaidDrudgeThreatSeed
{
struct Scope
{
    std::uint64_t AttemptId = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint64_t RouteGeneration = 0;
};

inline bool operator==(Scope const& left, Scope const& right)
{
    return left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration;
}

inline bool operator!=(Scope const& left, Scope const& right)
{
    return !(left == right);
}

struct State
{
    Scope Identity;
    bool Closed = false;
    bool Complete = false;
    bool Failure = false;
    std::array<bool, 2> SeededLanes = { false, false };
};

enum class Event : std::uint8_t
{
    DecisionTick,
    ActionResult,
    FirstNativeRush
};

enum class Decision : std::uint8_t
{
    Continue,
    HoldWindow,
    HoldClosed,
    HoldSeededLane,
    RetryCandidate,
    RequestSeedAction,
    SeedAccepted,
    Complete,
    FailAuthority
};

struct Input
{
    Event Type = Event::DecisionTick;
    Scope Identity;
    std::uint32_t SourceLane = 0;
    bool PrepullStaged = false;
    bool SourcesAlive = false;
    bool OwnershipSafe = false;
    bool SeparationSafe = false;
    bool FrozenLanesSafe = false;
    bool ChargeObserved = false;
    bool CandidateAvailable = false;
    bool AuthoritySafe = false;
    bool ActionSucceeded = false;
};

struct Result
{
    State Next;
    Decision NextDecision = Decision::Continue;
    bool ScopeReset = false;
};

inline Result Advance(State current, Input const& input);

// A coordinator tick evaluates both opposite-lane actors from one scheduler
// boundary.  The native module supplies the action result; this transition
// only accepts a lane after that real result is reported as successful.
enum class RejectionGate : std::uint8_t
{
    None,
    CandidateUnavailable,
    PositionUnsafe,
    ProfileActionUnavailable,
    TargetContract,
    MovementContract,
    LineOfSight,
    RangeContract,
    AuthorityRoster,
    NativeAction
};

inline char const* ToString(RejectionGate gate)
{
    switch (gate)
    {
        case RejectionGate::None:
            return "none";
        case RejectionGate::CandidateUnavailable:
            return "candidate_unavailable";
        case RejectionGate::PositionUnsafe:
            return "position_unsafe";
        case RejectionGate::ProfileActionUnavailable:
            return "profile_action_unavailable";
        case RejectionGate::TargetContract:
            return "target_contract";
        case RejectionGate::MovementContract:
            return "movement_contract";
        case RejectionGate::LineOfSight:
            return "line_of_sight";
        case RejectionGate::RangeContract:
            return "range_contract";
        case RejectionGate::AuthorityRoster:
            return "authority_roster";
        case RejectionGate::NativeAction:
            return "native_action";
    }

    return "unknown";
}

struct CoordinatorLaneInput
{
    bool CandidateAvailable = false;
    bool ActionAttempted = false;
    bool ActionSucceeded = false;
    bool AuthoritySafe = true;
    RejectionGate Rejection = RejectionGate::None;
};

struct CoordinatorInput
{
    Scope Identity;
    bool PrepullStaged = false;
    bool SourcesAlive = false;
    bool OwnershipSafe = false;
    bool SeparationSafe = false;
    bool FrozenLanesSafe = false;
    bool ChargeObserved = false;
    std::array<CoordinatorLaneInput, 2> Lanes;
};

struct CoordinatorLaneResult
{
    Result Transition;
    bool ActionAttempted = false;
    RejectionGate Rejection = RejectionGate::None;
};

struct CoordinatorResult
{
    State Next;
    std::array<CoordinatorLaneResult, 2> Lanes;
    bool ScopeReset = false;
    bool BothLanesEvaluated = false;
};

inline CoordinatorResult AdvanceCoordinator(State current,
    CoordinatorInput const& input)
{
    CoordinatorResult result;
    result.Next = current;
    if (result.Next.Identity != input.Identity)
    {
        result.Next = State{};
        result.Next.Identity = input.Identity;
        result.ScopeReset = true;
    }

    if (result.Next.Complete)
    {
        for (std::size_t lane = 0; lane < result.Lanes.size(); ++lane)
        {
            result.Lanes[lane].Transition.Next = result.Next;
            result.Lanes[lane].Transition.NextDecision = Decision::Continue;
            result.Lanes[lane].Rejection = RejectionGate::None;
        }
        result.BothLanesEvaluated = true;
        return result;
    }

    if (result.Next.Failure || result.Next.Closed || input.ChargeObserved)
    {
        for (std::size_t lane = 0; lane < result.Lanes.size(); ++lane)
        {
            Input closeInput;
            closeInput.Identity = input.Identity;
            closeInput.SourceLane = static_cast<std::uint32_t>(lane);
            closeInput.ChargeObserved = input.ChargeObserved;
            Result const transition = Advance(result.Next, closeInput);
            result.Next = transition.Next;
            result.ScopeReset = result.ScopeReset || transition.ScopeReset;
            result.Lanes[lane].Transition = transition;
            result.Lanes[lane].Rejection = RejectionGate::None;
        }
        result.BothLanesEvaluated = true;
        return result;
    }

    bool const windowReady = input.PrepullStaged && input.SourcesAlive
        && input.OwnershipSafe && input.SeparationSafe && input.FrozenLanesSafe;
    if (!windowReady)
    {
        for (std::size_t lane = 0; lane < result.Lanes.size(); ++lane)
        {
            result.Lanes[lane].Transition.Next = result.Next;
            result.Lanes[lane].Transition.NextDecision = Decision::HoldWindow;
            result.Lanes[lane].Rejection = RejectionGate::None;
        }
        result.BothLanesEvaluated = true;
        return result;
    }

    for (std::size_t lane = 0; lane < result.Lanes.size(); ++lane)
    {
        CoordinatorLaneInput const& laneInput = input.Lanes[lane];
        Input transitionInput;
        transitionInput.Type = laneInput.ActionAttempted
            ? Event::ActionResult : Event::DecisionTick;
        transitionInput.Identity = input.Identity;
        transitionInput.SourceLane = static_cast<std::uint32_t>(lane);
        transitionInput.PrepullStaged = input.PrepullStaged;
        transitionInput.SourcesAlive = input.SourcesAlive;
        transitionInput.OwnershipSafe = input.OwnershipSafe;
        transitionInput.SeparationSafe = input.SeparationSafe;
        transitionInput.FrozenLanesSafe = input.FrozenLanesSafe;
        transitionInput.ChargeObserved = input.ChargeObserved;
        transitionInput.CandidateAvailable = laneInput.CandidateAvailable;
        transitionInput.AuthoritySafe = laneInput.AuthoritySafe;
        transitionInput.ActionSucceeded = laneInput.ActionSucceeded;
        Result const transition = Advance(result.Next, transitionInput);
        result.Next = transition.Next;
        result.ScopeReset = result.ScopeReset || transition.ScopeReset;
        result.Lanes[lane].Transition = transition;
        result.Lanes[lane].ActionAttempted = laneInput.ActionAttempted;
        result.Lanes[lane].Rejection = laneInput.Rejection;
    }
    result.BothLanesEvaluated = true;
    return result;
}

// This transition is deliberately independent of Player, Map, Spell, and
// pathfinding types. Production computes those native facts and calls this
// exact function; the replay harness varies their ordering without duplicating
// the decision rules.
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

    if (input.Type == Event::FirstNativeRush)
    {
        result.Next.Closed = true;
        if (!result.Next.Complete)
            result.Next.Failure = true;
        result.NextDecision = result.Next.Complete ? Decision::Complete : Decision::HoldClosed;
        return result;
    }

    if (result.Next.Complete)
    {
        result.NextDecision = Decision::Continue;
        return result;
    }

    if (result.Next.Failure || result.Next.Closed || input.ChargeObserved)
    {
        result.Next.Closed = true;
        if (!result.Next.Complete)
            result.Next.Failure = true;
        result.NextDecision = Decision::HoldClosed;
        return result;
    }

    bool const windowReady = input.PrepullStaged && input.SourcesAlive
        && input.OwnershipSafe && input.SeparationSafe && input.FrozenLanesSafe;
    if (!windowReady)
    {
        // Geometry, ownership, and scheduler order may be transient before the
        // native Rush. Keep offense held, but only the native clock edge or a
        // true authority violation may permanently fail the seed scope.
        result.NextDecision = Decision::HoldWindow;
        return result;
    }

    if (input.SourceLane >= result.Next.SeededLanes.size())
    {
        result.Next.Closed = true;
        result.Next.Failure = true;
        result.NextDecision = Decision::FailAuthority;
        return result;
    }

    if (result.Next.SeededLanes[input.SourceLane])
    {
        result.NextDecision = Decision::HoldSeededLane;
        return result;
    }

    if (!input.CandidateAvailable)
    {
        result.NextDecision = Decision::RetryCandidate;
        return result;
    }

    if (!input.AuthoritySafe)
    {
        result.Next.Closed = true;
        result.Next.Failure = true;
        result.NextDecision = Decision::FailAuthority;
        return result;
    }

    if (input.Type != Event::ActionResult)
    {
        result.NextDecision = Decision::RequestSeedAction;
        return result;
    }

    if (!input.ActionSucceeded)
    {
        result.NextDecision = Decision::RetryCandidate;
        return result;
    }

    result.Next.SeededLanes[input.SourceLane] = true;
    result.Next.Complete = result.Next.SeededLanes[0] && result.Next.SeededLanes[1];
    result.NextDecision = result.Next.Complete ? Decision::Complete : Decision::SeedAccepted;
    return result;
}
}

#endif

#ifndef TRINITY_BOT_RAID_DRUDGE_THREAT_SEED_STATE_H
#define TRINITY_BOT_RAID_DRUDGE_THREAT_SEED_STATE_H

#include <array>
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

    if (result.Next.Closed || input.ChargeObserved)
    {
        result.Next.Closed = true;
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

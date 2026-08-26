#ifndef TRINITY_BOT_RAID_DRUDGE_TAUNT_CONFIRMATION_H
#define TRINITY_BOT_RAID_DRUDGE_TAUNT_CONFIRMATION_H

#include <cstdint>

namespace BotRaidDrudgeTauntConfirmation
{
// A taunt request is scoped to the native source and the exact runtime
// identity that must later be observed as its victim.  A successful cast
// request never changes this proof state by itself.
struct Scope
{
    std::uint64_t AttemptId = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint64_t RouteGeneration = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    std::uint64_t SourceIdentity = 0;
    std::uint32_t SourceSpawnId = 0;
    std::uint32_t TankGuid = 0;

    bool operator==(Scope const& other) const
    {
        return AttemptId == other.AttemptId
            && WipeGeneration == other.WipeGeneration
            && RouteGeneration == other.RouteGeneration
            && MapId == other.MapId
            && InstanceId == other.InstanceId
            && SourceIdentity == other.SourceIdentity
            && SourceSpawnId == other.SourceSpawnId
            && TankGuid == other.TankGuid;
    }

    bool operator!=(Scope const& other) const
    {
        return !(*this == other);
    }
};

enum class Observation : std::uint8_t
{
    Idle,
    ScopeReset,
    Pending,
    RetryReady,
    Confirmed
};

struct State
{
    Scope PendingScope;
    bool Pending = false;
    std::uint32_t SpellId = 0;
    std::uint64_t SubmittedAtMs = 0;
    std::uint64_t RetryAfterMs = 0;
    std::uint32_t RetryCount = 0;
};

constexpr std::uint64_t RetryBackoffMs = 1500;

inline void Reset(State& state)
{
    state = {};
}

inline Observation Observe(State& state, Scope const& scope,
    std::uint32_t currentVictimGuid, std::uint64_t observedAtMs)
{
    if (!state.Pending)
        return Observation::Idle;
    if (state.PendingScope != scope)
    {
        Reset(state);
        return Observation::ScopeReset;
    }
    if (currentVictimGuid == scope.TankGuid && scope.TankGuid != 0)
    {
        state.Pending = false;
        return Observation::Confirmed;
    }
    if (observedAtMs < state.RetryAfterMs)
        return Observation::Pending;
    return Observation::RetryReady;
}

inline void Submit(State& state, Scope const& scope, std::uint32_t spellId,
    std::uint64_t submittedAtMs)
{
    if (!state.Pending || state.PendingScope != scope)
        state.RetryCount = 0;
    state.PendingScope = scope;
    state.Pending = true;
    state.SpellId = spellId;
    state.SubmittedAtMs = submittedAtMs;
    state.RetryAfterMs = submittedAtMs + RetryBackoffMs;
    ++state.RetryCount;
}

inline void DeferRetry(State& state, std::uint64_t observedAtMs)
{
    if (state.Pending)
        state.RetryAfterMs = observedAtMs + RetryBackoffMs;
}
}

#endif

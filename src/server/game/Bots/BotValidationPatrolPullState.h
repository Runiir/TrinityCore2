#ifndef TRINITY_BOT_VALIDATION_PATROL_PULL_STATE_H
#define TRINITY_BOT_VALIDATION_PATROL_PULL_STATE_H

#include <cstdint>

namespace BotValidationPatrolPull
{
struct Identity
{
    std::uint64_t AttemptId = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint64_t RouteGeneration = 0;
    std::uint32_t MapId = 0;
    std::uint32_t InstanceId = 0;
    std::uint64_t SourceSpawnId = 0;
    std::uint64_t SourceGuid = 0;
};

inline bool SameIdentity(Identity const& left, Identity const& right)
{
    return left.AttemptId == right.AttemptId
        && left.WipeGeneration == right.WipeGeneration
        && left.RouteGeneration == right.RouteGeneration
        && left.MapId == right.MapId
        && left.InstanceId == right.InstanceId
        && left.SourceSpawnId == right.SourceSpawnId
        && left.SourceGuid == right.SourceGuid;
}

struct State
{
    Identity Scope;
    bool Completed = false;
};

struct Observation
{
    Identity Scope;
    bool SourceAvailable = false;
    bool SourceAlive = false;
    bool SourceEngaged = false;
    bool SourceEvading = false;
};

inline bool Observe(State& state, Observation const& observation)
{
    if (!SameIdentity(state.Scope, observation.Scope)
        || !observation.SourceAvailable || !observation.SourceAlive
        || !observation.SourceEngaged || observation.SourceEvading)
        state.Completed = false;
    state.Scope = observation.Scope;
    return state.Completed;
}

inline void Complete(State& state, Observation const& observation,
    bool insideInitialRadius, bool rosterTankVictim)
{
    Observe(state, observation);
    if (observation.Scope.SourceGuid && observation.Scope.SourceSpawnId
        && observation.SourceAvailable && observation.SourceAlive
        && observation.SourceEngaged && !observation.SourceEvading
        && insideInitialRadius && rosterTankVictim)
        state.Completed = true;
}
}

#endif

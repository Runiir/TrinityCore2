#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_RECOVERY_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_NATIVE_RECOVERY_H

#include <cstdint>
#include <string_view>

namespace BotWorldPopulationMgrNativeRecovery
{
// This value-only boundary decides whether a dead member may enter the
// ordinary native release/corpse-run path after a partial raid death.  Native
// observation code supplies the fields; this policy never inspects or mutates
// a Player, InstanceScript, corpse, or movement generator.
struct PartialDeathObservation
{
    bool Active = false;
    bool RosterComplete = false;
    bool EncounterInProgress = false;
    bool HostileActivityActive = false;
    bool PartialDeathState = false;

    std::uint32_t ExpectedPopulation = 0;
    std::uint32_t RaidExpectedPopulation = 0;
    std::uint32_t ActiveSize = 0;
    std::uint32_t AliveSize = 0;

    std::uint64_t AttemptId = 0;
    std::uint64_t ExpectedAttemptId = 0;
    std::uint64_t RouteGeneration = 0;
    std::uint64_t HostileObservationAttemptId = 0;
    std::uint64_t HostileObservationRouteGeneration = 0;
    std::uint64_t BossResetGeneration = 0;
    std::uint64_t BossResetGenerationAtWipe = 0;
    std::uint64_t HostileResetGeneration = 0;
    std::uint64_t HostileResetGenerationAtWipe = 0;

    std::string_view NodeId;
    std::string_view HostileObservationNodeId;
    bool HostileInactivityObserved = false;
};

enum class PartialDeathAdmission : std::uint8_t
{
    Hold,
    ReleaseAfterNativeReset,
};

inline constexpr PartialDeathAdmission EvaluatePartialDeathAdmission(
    PartialDeathObservation const& observation)
{
    bool const hostileScopeMatches =
        observation.HostileObservationAttemptId == observation.ExpectedAttemptId
        && observation.HostileObservationRouteGeneration
            == observation.RouteGeneration
        && observation.HostileObservationNodeId == observation.NodeId;
    bool const hostileResetObserved = hostileScopeMatches
        && observation.HostileInactivityObserved
        && observation.HostileResetGeneration
            > observation.HostileResetGenerationAtWipe;
    bool const bossResetObserved = observation.BossResetGeneration
        > observation.BossResetGenerationAtWipe;
    bool const exactPartialRoster = observation.Active
        && observation.RosterComplete
        && observation.ExpectedPopulation
            == observation.RaidExpectedPopulation
        && observation.ActiveSize == observation.RaidExpectedPopulation
        && observation.AliveSize > 0
        && observation.AliveSize < observation.ActiveSize
        && observation.PartialDeathState;
    bool const nativeResetObserved = !observation.EncounterInProgress
        && !observation.HostileActivityActive
        && (bossResetObserved || hostileResetObserved);
    return exactPartialRoster
        && observation.AttemptId == observation.ExpectedAttemptId
        && nativeResetObserved
        ? PartialDeathAdmission::ReleaseAfterNativeReset
        : PartialDeathAdmission::Hold;
}
}

#endif

#ifndef TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_COHORT_READINESS_H
#define TRINITY_BOT_WORLD_POPULATION_MGR_VALIDATION_COHORT_READINESS_H

#include <cstdint>
#include <string>

namespace BotWorldPopulationMgrValidationRoute
{
// A member is accounted for only when its loaded player identity can be
// observed. Valid means the existing cohort/instance authority accepted the
// identity; recovery is a separate valid state for a non-living member.
struct ValidationCohortMemberObservation
{
    bool Accounted = false;
    bool Valid = false;
    bool Living = false;
    bool AtEndpoint = false;
    bool KnownRecovering = false;
};

struct ValidationCohortRecoveryObservation
{
    bool Alive = true;
    bool Ghost = false;
    bool ReleaseRequested = false;
    bool NativeCorpseAuthority = false;
    std::uint64_t EpisodeStartedMs = 0;
    std::uint64_t EpisodeAttemptId = 0;
    std::uint64_t EpisodeRouteGeneration = 0;
    std::uint64_t EpisodeWipeGeneration = 0;
    std::uint32_t EpisodeDeathOrdinal = 0;
    std::string EpisodePhase = "none";
    std::uint64_t AttemptId = 0;
    std::uint64_t RouteGeneration = 0;
    std::uint64_t WipeGeneration = 0;
    std::uint32_t DeathOrdinal = 0;
};

struct ValidationCohortReadinessObservation
{
    std::uint32_t ExpectedMemberCount = 0;
    std::uint32_t RosterMemberCount = 0;
    std::uint32_t AccountedMemberCount = 0;
    std::uint32_t MissingMemberCount = 0;
    std::uint32_t InvalidMemberCount = 0;
    std::uint32_t LivingMemberCount = 0;
    std::uint32_t LivingAtEndpointCount = 0;
    std::uint32_t KnownRecoveringMemberCount = 0;
    bool PackHasLiveMobs = false;
    bool PartyHasActiveCombat = false;

    void ObserveMember(ValidationCohortMemberObservation const& member)
    {
        ++RosterMemberCount;
        if (!member.Accounted)
        {
            ++MissingMemberCount;
            return;
        }

        ++AccountedMemberCount;
        if (!member.Valid)
        {
            ++InvalidMemberCount;
            return;
        }

        if (member.Living && member.KnownRecovering)
        {
            ++InvalidMemberCount;
            return;
        }

        if (member.Living)
        {
            ++LivingMemberCount;
            if (member.AtEndpoint)
                ++LivingAtEndpointCount;
            return;
        }

        if (member.KnownRecovering)
        {
            ++KnownRecoveringMemberCount;
            return;
        }

        ++InvalidMemberCount;
    }
};

struct ValidationCohortReadiness
{
    bool AllExpectedMembersAccounted = false;
    bool AllLivingAtEndpoint = false;
    bool FullRosterAtEndpoint = false;
    bool TrashTerminalReady = false;
};

// Recovery authority remains manager-owned. This predicate only binds the
// observation to the current attempt, route, wipe, and death episode before a
// caller records a non-living ghost as known recovery.
inline bool IsKnownValidationRecovery(
    ValidationCohortRecoveryObservation const& observation)
{
    return !observation.Alive && observation.Ghost
        && observation.ReleaseRequested && observation.NativeCorpseAuthority
        && observation.EpisodeStartedMs
        && observation.EpisodeAttemptId == observation.AttemptId
        && observation.EpisodeRouteGeneration
            == observation.RouteGeneration
        && observation.EpisodeWipeGeneration == observation.WipeGeneration
        && observation.EpisodeDeathOrdinal == observation.DeathOrdinal
        && observation.EpisodePhase != "none"
        && observation.EpisodePhase != "terminal";
}

inline ValidationCohortReadiness ClassifyValidationCohortReadiness(
    ValidationCohortReadinessObservation const& observation)
{
    ValidationCohortReadiness result;
    result.AllExpectedMembersAccounted = observation.ExpectedMemberCount > 0
        && observation.RosterMemberCount == observation.ExpectedMemberCount
        && observation.AccountedMemberCount == observation.ExpectedMemberCount
        && observation.MissingMemberCount == 0
        && observation.InvalidMemberCount == 0;
    result.AllLivingAtEndpoint = result.AllExpectedMembersAccounted
        && observation.LivingMemberCount > 0
        && observation.LivingAtEndpointCount
            == observation.LivingMemberCount;
    result.FullRosterAtEndpoint = result.AllExpectedMembersAccounted
        && observation.KnownRecoveringMemberCount == 0
        && observation.LivingMemberCount == observation.ExpectedMemberCount
        && observation.LivingAtEndpointCount
            == observation.ExpectedMemberCount;
    result.TrashTerminalReady = !observation.PackHasLiveMobs
        && !observation.PartyHasActiveCombat
        && result.AllLivingAtEndpoint;
    return result;
}
}

#endif

#ifndef TRINITY_BOT_ATRAMEDES_OBSERVATION_EXPORT_H
#define TRINITY_BOT_ATRAMEDES_OBSERVATION_EXPORT_H

// The raid_runtime export of the Atramedes acceptance-observation counters
// (BotAtramedesObservationCounters.h; kept per cohort attempt by
// BotAtramedesObservationStore.h, whose process store lives in
// BotWorldPopulationMgrAtramedesCandidates.cpp). Declaration only, so the
// raid runtime JSON does not pull the Atramedes strategy headers.

#include <cstdint>
#include <string>

namespace BotEncounter::Atramedes
{
// One cohort attempt: the cohort's start lifecycle (CohortRuntime::
// CombatLogEpoch, which every Start and StartAutonomy advances) and its
// attempt id, as the Nefarian observations scope theirs.
struct ObservationAttempt
{
    std::uint64_t Lifecycle = 0;
    std::uint64_t AttemptId = 0;

    bool operator==(ObservationAttempt const& other) const
    {
        return Lifecycle == other.Lifecycle && AttemptId == other.AttemptId;
    }
    bool operator!=(ObservationAttempt const& other) const { return !(*this == other); }
};

// `field` (the encounter_observations field of the other encounters, "" when
// they export none) with "atramedes":{...} added for a cohort on Atramedes'
// route, or one whose current attempt ran the Atramedes strategy (its
// terminal observations after the route moved on). Every other cohort gets
// `field` back byte-identical, as in a process that never ran Atramedes.
std::string EncounterObservationsJsonField(std::string const& field,
    std::string const& cohortId, ObservationAttempt attempt, std::string const& routeNodeId);
}

#endif

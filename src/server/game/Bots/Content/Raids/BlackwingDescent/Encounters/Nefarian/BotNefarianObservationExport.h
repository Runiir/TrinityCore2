#ifndef TRINITY_BOT_NEFARIAN_OBSERVATION_EXPORT_H
#define TRINITY_BOT_NEFARIAN_OBSERVATION_EXPORT_H

// The raid_runtime export of the Nefarian acceptance-observation counters
// (BotNefarianObservationCounters.h; kept per cohort attempt by
// BotNefarianObservationStore.h, whose process store lives in
// BotWorldPopulationMgrNefarianCandidates.cpp). Declaration only, so the raid
// runtime JSON does not pull the Nefarian strategy headers.

#include <cstdint>
#include <string>

namespace BotEncounter::Nefarian
{
// One cohort attempt: the cohort's start lifecycle (CohortRuntime::
// CombatLogEpoch, which every Start and StartAutonomy advances, also where
// `.botexp start` keeps the attempt id) and its attempt id.
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

// ",\"encounter_observations\":{\"nefarian\":{...}}" for a cohort on
// Nefarian's route, or one whose current attempt ran the Nefarian strategy
// (its terminal observations after the route moved on); "" for every other
// cohort, so its status is byte-identical to a process that never ran
// Nefarian.
std::string EncounterObservationsJsonField(std::string const& cohortId,
    ObservationAttempt attempt, std::string const& routeNodeId);
}

#endif

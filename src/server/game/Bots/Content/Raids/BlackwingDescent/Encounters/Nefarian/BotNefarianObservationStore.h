#ifndef TRINITY_BOT_NEFARIAN_OBSERVATION_STORE_H
#define TRINITY_BOT_NEFARIAN_OBSERVATION_STORE_H

// The round-3 acceptance observations of every cohort, behind one mutex: per
// cohort, the bone-warrior watch (BotNefarianWarriorWatch.h) and the counters
// (BotNefarianObservationCounters.h) of its current attempt. The process
// store lives in BotWorldPopulationMgrNefarianCandidates.cpp; the raid_runtime
// export reads it (BotNefarianObservationExport.h).
// - An attempt is the cohort's start lifecycle and attempt id
//   (ObservationAttempt). A new one starts a clean watch and clean counters,
//   in the same instance too.
// - Creature guids are map-local, so a watch serves one map instance: it binds
//   to the instance of the first snapshot it observes. Parallel boss shards
//   (one cohort and instance each) never share a watch. A snapshot of another
//   cohort or attempt, or of no map, is never observed; one of another
//   instance in the same attempt rebinds a clean watch.
// - `complete` is true only for the current attempt, once its watch has
//   observed a snapshot of it and while that watch has covered it whole: an
//   instance change, or a watch whose coverage broke (WarriorWatch::
//   CoverageBroken: a gap longer than WarriorObservationGapMs, a forward jump
//   over it, any step back of the clock, or a snapshot that stayed unchanged
//   past that bound while the reporter kept deciding), ends that. `complete`
//   says nothing about the boss window's edges: the export carries the first
//   and the last observed snapshot's publication time (system ms, the combat
//   log's clock), and the harness requires them near the window's start and
//   end (tools/raid_program/run_sanity_inputs.py).
// - A snapshot is observed once: the store is fed the snapshot's revision,
//   and a cached snapshot (the blackboard is republished on a system-time
//   throttle, which a wall-clock step back holds) is not observed again with
//   the reporter's advancing steady time (BotNefarianWarriorWatch.h).
// - A cohort not on Nefarian's route exports the block only for its current
//   attempt (the terminal observations after the route moved on). A reused
//   cohort (Stonecore, calibration, legacy Magmaw) exports nothing, as in a
//   process that never ran Nefarian.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationCounters.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationExport.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianWarriorWatch.h"
#include <map>
#include <mutex>
#include <string>
#include <string_view>
#include <vector>

namespace BotEncounter::Nefarian
{
class ObservationStore
{
public:
    // Starts the observations of the cohort's `attempt` (attempt id 0 is never
    // an attempt); a different attempt replaces them. True when live.
    bool Begin(std::string const& cohortId, ObservationAttempt attempt)
    {
        if (!attempt.AttemptId)
            return false;
        std::lock_guard<std::mutex> lock(_mutex);
        Record& record = _cohorts[cohortId];
        if (record.Attempt != attempt)
        {
            record = Record();
            record.Attempt = attempt;
        }
        return record.Counters.Begin(attempt.AttemptId);
    }

    // The reporter's snapshot (`scope` is its CurrentScope, `view` its
    // Nefarian view, `snapshot` its Blackboard::Revision and ObservedAtMs,
    // `observedAtMs` the monotonic observation clock, ObservationClockMs, at
    // the decision) in the watch of the cohort's begun `attempt`: the new
    // violations, each recorded in the counters. The reporter decides far more
    // often than the blackboard is republished, so a revision the watch
    // already observed is no new observation (WarriorWatch::ObserveSnapshot).
    std::vector<WarriorViolation> ObserveWarriors(std::string const& cohortId,
        ObservationAttempt attempt, Scope const& scope, EncounterView const& view,
        SnapshotStamp snapshot, uint64 observedAtMs)
    {
        std::lock_guard<std::mutex> lock(_mutex);
        auto const found = _cohorts.find(cohortId);
        if (found == _cohorts.end() || found->second.Attempt != attempt
            || !found->second.Counters.LiveFor(attempt.AttemptId)
            || scope.CohortId != cohortId || scope.AttemptId != attempt.AttemptId
            || !scope.MapId)
            return {};
        Record& record = found->second;
        if (record.Bound && (record.MapId != scope.MapId || record.InstanceId != scope.InstanceId))
        {
            record.Watch = WarriorWatch();
            record.CoverageLost = true;
        }
        record.Bound = true;
        record.MapId = scope.MapId;
        record.InstanceId = scope.InstanceId;
        record.Observed = true;
        std::vector<WarriorViolation> violations = record.Watch.ObserveSnapshot(
            snapshot, view, observedAtMs);
        if (record.Watch.CoverageBroken())
            record.CoverageLost = true;
        for (WarriorViolation const& violation : violations)
            record.Counters.RecordWarrior(attempt.AttemptId,
                violation.Kind == WarriorViolationKind::ActiveOverLimit
                    ? ObservedWarriorKind::ActiveOverLimit : ObservedWarriorKind::OnPillar,
                violation.Warrior.GetRawValue());
        return violations;
    }

    // An executor refusal of the cohort's begun `attempt`.
    void RecordRefused(std::string const& cohortId, ObservationAttempt attempt,
        std::uint64_t actorGuid, std::string_view mechanicReason)
    {
        std::lock_guard<std::mutex> lock(_mutex);
        auto const found = _cohorts.find(cohortId);
        if (found != _cohorts.end() && found->second.Attempt == attempt)
            found->second.Counters.RecordRefused(attempt.AttemptId, actorGuid, mechanicReason);
    }

    // EncounterObservationsJsonField (BotNefarianObservationExport.h).
    std::string JsonField(std::string const& cohortId, ObservationAttempt attempt,
        std::string_view routeNodeId) const
    {
        std::lock_guard<std::mutex> lock(_mutex);
        auto const found = _cohorts.find(cohortId);
        bool const current = found != _cohorts.end() && found->second.Attempt == attempt;
        if (!current && routeNodeId != EncounterNodeId)
            return std::string();
        return ",\"encounter_observations\":{\"nefarian\":"
            + (current ? found->second.Counters.Json(attempt.AttemptId, attempt.Lifecycle,
                    found->second.Covered(), found->second.Watch.FirstPublishedAtMs(),
                    found->second.Watch.LastPublishedAtMs())
                : ObservationCounters().Json(attempt.AttemptId, attempt.Lifecycle)) + "}";
    }

private:
    struct Record
    {
        ObservationAttempt Attempt;
        ObservationCounters Counters;
        WarriorWatch Watch;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        bool Bound = false;
        bool Observed = false;
        bool CoverageLost = false;

        bool Covered() const { return Observed && !CoverageLost; }
    };

    mutable std::mutex _mutex;
    std::map<std::string, Record> _cohorts;
};
}

#endif

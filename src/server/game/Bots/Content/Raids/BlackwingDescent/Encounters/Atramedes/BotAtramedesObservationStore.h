#ifndef TRINITY_BOT_ATRAMEDES_OBSERVATION_STORE_H
#define TRINITY_BOT_ATRAMEDES_OBSERVATION_STORE_H

// The round-3 acceptance observation of every cohort, behind one mutex: per
// cohort, the chase counters (BotAtramedesObservationCounters.h) of its
// current attempt. The process store lives in
// BotWorldPopulationMgrAtramedesCandidates.cpp; the raid_runtime export reads
// it (BotAtramedesObservationExport.h). Patterned on the Nefarian store
// (BotNefarianObservationStore.h).
// - An attempt is the cohort's start lifecycle and attempt id
//   (ObservationAttempt). A new one starts clean counters, in the same
//   instance too.
// - Every bot decision of the cohort offers the cohort's encounter snapshot.
//   Only a snapshot newer than the last one sampled is a sample, so the bots
//   reading one snapshot count it once. Sampling binds to the map instance of
//   the first snapshot it observes. A snapshot of another cohort or attempt,
//   or of no map, is never observed; one of another instance in the same
//   attempt ends the chase and the coverage.
// - `complete` is true only for the current attempt, once a snapshot of it
//   was sampled and while the sampling covered it whole. Coverage ends at an
//   instance change, at a sampling clock that went back more than
//   MaxSampleGapMs (the store is blind until it catches up), and at a gap
//   between samples that could hide Sound: longer than MaxSampleGapMs when
//   either side of it is in the air phase (a chase can end inside it), or
//   longer than MaxGroundGapMs when it starts in a ground engagement,
//   whatever the next snapshot is (an air phase lasts 31 s, so a short gap
//   hides none; a boss-absent or other-route snapshot after a long outage is
//   no proof that the outage held no air phase).
//   `complete` says nothing about the boss window's edges: the export carries
//   the time of the first and of the newest sample (system ms, the combat
//   log's clock), and the harness requires them near the window's start and
//   end (tools/raid_program/run_sanity_inputs.py).
// - A cohort not on Atramedes' route exports the block only for its current
//   attempt (the terminal observations after the route moved on). A reused
//   cohort (Stonecore, calibration, legacy Magmaw) exports nothing, as in a
//   process that never ran Atramedes.

#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesFacts.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationCounters.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationExport.h"
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesSoundSources.h"
#include <map>
#include <mutex>
#include <string>
#include <string_view>

namespace BotEncounter::Atramedes
{
inline constexpr uint64 MaxGroundGapMs = 5000;

// The chase sample of one encounter snapshot: the Sound of the player the
// Reverberating Flame follows (its Tracking target, or the iced mage it keeps
// following without one; BuildFacts' AirKiter). With `sources`, the snapshot
// also updates every player's last Sound rise and the sample carries the
// kiter's (BotAtramedesSoundSources.h).
inline ChaseSample SampleChase(Blackboard const& board, SoundSourceTracker* sources = nullptr)
{
    ChaseSample sample;
    sample.AtMs = board.ObservedAtMs;
    if (board.Route.NodeId != EncounterNode)
        return sample;
    Facts const facts = BuildFacts(board);
    if (sources)
        sources->Observe(board, facts);
    sample.Engaged = facts.CurrentPhase == Phase::Ground || facts.CurrentPhase == Phase::Air;
    sample.Air = facts.CurrentPhase == Phase::Air;
    if (!sample.Air || facts.AirKiter.IsEmpty())
        return sample;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && player.Guid == facts.AirKiter)
        {
            sample.Kiter = player.Guid.GetRawValue();
            sample.Sound = SoundOf(player);
            if (SoundSourceTracker::Last const* last = sources ? sources->Find(sample.Kiter) : nullptr)
            {
                sample.Source = last->Source;
                sample.Increment = last->Increment;
                sample.IncrementAtMs = last->AtMs;
            }
        }
    return sample;
}

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

    // The cohort's encounter snapshot, offered by one bot decision of the
    // cohort's begun `attempt`.
    void Observe(std::string const& cohortId, ObservationAttempt attempt, Blackboard const& board)
    {
        std::lock_guard<std::mutex> lock(_mutex);
        auto const found = _cohorts.find(cohortId);
        Scope const& scope = board.CurrentScope;
        if (found == _cohorts.end() || found->second.Attempt != attempt
            || !found->second.Counters.LiveFor(attempt.AttemptId)
            || scope.CohortId != cohortId || scope.AttemptId != attempt.AttemptId
            || !scope.MapId)
            return;
        Record& record = found->second;
        uint64 const at = board.ObservedAtMs;
        if (record.Bound && (record.MapId != scope.MapId || record.InstanceId != scope.InstanceId))
        {
            record.CoverageLost = true;
            record.Counters.Record(attempt.AttemptId, ChaseSample());
            record.Last = Phase::Absent;
            record.LatestMs = 0;
        }
        else if (record.Observed && at <= record.LatestMs)
        {
            // Already sampled, or an older cached copy: never a sample. A
            // clock that went back further leaves the store blind.
            if (record.LatestMs - at > MaxSampleGapMs)
                record.CoverageLost = true;
            return;
        }
        ChaseSample const sample = SampleChase(board, &record.Sources);
        Phase const current = sample.Air ? Phase::Air
            : sample.Engaged ? Phase::Ground : Phase::Absent;
        // Every gap that starts in an engaged phase is checked, whatever the
        // next snapshot is: one of a dead boss or of another route ends the
        // engagement, but the unsampled time before it could still hold a
        // whole air phase (a chase above the bound nobody saw).
        if (record.Last != Phase::Absent)
        {
            uint64 const gap = at - record.LatestMs;
            record.Counters.RecordGap(attempt.AttemptId, gap);
            uint64 const limit = record.Last == Phase::Air || sample.Air
                ? MaxSampleGapMs : MaxGroundGapMs;
            if (gap > limit)
                record.CoverageLost = true;
        }
        record.Counters.Record(attempt.AttemptId, sample);
        if (!record.Observed)
            record.FirstMs = at;
        record.Bound = true;
        record.MapId = scope.MapId;
        record.InstanceId = scope.InstanceId;
        record.Observed = true;
        record.Last = current;
        record.LatestMs = at;
    }

    // EncounterObservationsJsonField (BotAtramedesObservationExport.h).
    std::string JsonField(std::string const& field, std::string const& cohortId,
        ObservationAttempt attempt, std::string_view routeNodeId) const
    {
        std::lock_guard<std::mutex> lock(_mutex);
        auto const found = _cohorts.find(cohortId);
        bool const current = found != _cohorts.end() && found->second.Attempt == attempt;
        if (!current && routeNodeId != EncounterNode)
            return field;
        return WithAtramedesObservations(field, current
            ? found->second.Counters.Json(attempt.AttemptId, attempt.Lifecycle, found->second.Covered(),
                found->second.FirstMs, found->second.LatestMs)
            : ObservationCounters().Json(attempt.AttemptId, attempt.Lifecycle));
    }

private:
    struct Record
    {
        ObservationAttempt Attempt;
        ObservationCounters Counters;
        // Every player's last Sound rise in the attempt.
        SoundSourceTracker Sources;
        uint32 MapId = 0;
        uint32 InstanceId = 0;
        uint64 LatestMs = 0;
        // The time of the first sample of the attempt (LatestMs is the newest).
        uint64 FirstMs = 0;
        // The phase of the latest sample (Absent: not engaged).
        Phase Last = Phase::Absent;
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

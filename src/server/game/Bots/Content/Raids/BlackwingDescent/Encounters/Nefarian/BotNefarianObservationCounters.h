#ifndef TRINITY_BOT_NEFARIAN_OBSERVATION_COUNTERS_H
#define TRINITY_BOT_NEFARIAN_OBSERVATION_COUNTERS_H

// Server-side counters of the round-3 acceptance observations (BWD 10N
// Nefarian), exported in `.botauto status` raid_runtime.encounter_observations
// so a normal kill is evaluable without a retained decision trace (heartbeats
// read only the newest rows per bot and the terminal drain runs only on a
// failure; tools/raid_program/run_sanity_inputs.py).
//
// One instance per cohort, scoped to the cohort attempt: Begin(attempt)
// starts the counters and a different attempt resets them. It counts:
// - bone warriors (distinct warrior guids) the warrior watch flagged active
//   past 45 s, and those it flagged on a pillar structure
//   (BotNefarianWarriorWatch.h; a warrior re-flagged after a collapse and a
//   new wake counts once);
// - every movement step the executor refused, per actor guid and
//   "<mechanic>:<executor reason>" (the decision trace coalesces repeats; the
//   counters do not).
// `complete` is true only while the counters are live for the attempt asked
// about and the caller's warrior watch covered that attempt
// (BotNefarianObservationStore.h); a stale attempt exports zeros with
// complete false.
// Standard library only, so the logic compiles in a g++ program test.

#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <map>
#include <set>
#include <string>
#include <string_view>

namespace BotEncounter::Nefarian
{
enum class ObservedWarriorKind : std::uint8_t
{
    ActiveOverLimit,
    OnPillar
};

class ObservationCounters
{
public:
    // Starts the counters of `attemptId` (0 is never an attempt); a
    // different attempt resets them. True when the counters are live.
    bool Begin(std::uint64_t attemptId)
    {
        if (!attemptId)
            return false;
        if (!_live || _attemptId != attemptId)
        {
            _activeOverLimit.clear();
            _onPillar.clear();
            _refused.clear();
            _attemptId = attemptId;
            _live = true;
        }
        return true;
    }

    bool LiveFor(std::uint64_t attemptId) const
    {
        return _live && attemptId && _attemptId == attemptId;
    }

    // Recorded only into the live attempt (the caller begins it first).
    void RecordWarrior(std::uint64_t attemptId, ObservedWarriorKind kind,
        std::uint64_t warriorGuid)
    {
        if (!LiveFor(attemptId) || !warriorGuid)
            return;
        (kind == ObservedWarriorKind::ActiveOverLimit ? _activeOverLimit : _onPillar)
            .insert(warriorGuid);
    }

    void RecordRefused(std::uint64_t attemptId, std::uint64_t actorGuid,
        std::string_view mechanicReason)
    {
        if (!LiveFor(attemptId) || !actorGuid)
            return;
        ++_refused[actorGuid][std::string(mechanicReason)];
    }

    std::size_t ActiveOverLimit() const { return _activeOverLimit.size(); }
    std::size_t OnPillar() const { return _onPillar.size(); }
    std::uint64_t Refused(std::uint64_t actorGuid, std::string const& mechanicReason) const
    {
        auto const actor = _refused.find(actorGuid);
        if (actor == _refused.end())
            return 0;
        auto const count = actor->second.find(mechanicReason);
        return count == actor->second.end() ? 0 : count->second;
    }

    // {"bone_warrior_active_over_45s":n,"bone_warrior_on_pillar":n,
    //  "move_refused":{"<guid>":{"<mechanic>:<reason>":n}},"complete":b,
    //  "attempt_id":n,"combat_log_epoch":n,"first_observed_at_ms":n,
    //  "last_observed_at_ms":n} for the cohort's current attempt;
    // `lifecycle` is the attempt's start lifecycle (ObservationAttempt::
    // Lifecycle), which the run harness binds the counters to together with
    // the attempt id. An uncovered live attempt keeps its counts (a lower
    // bound) with complete false. The last two are the publication times
    // (system ms, the combat log's clock) of the first and newest snapshot
    // the watch observed in the attempt (0: none): the harness requires them
    // near the boss window's edges, since `complete` alone does not say the
    // watch observed anywhere near them.
    std::string Json(std::uint64_t currentAttemptId, std::uint64_t lifecycle,
        bool covered = true, std::uint64_t firstObservedAtMs = 0,
        std::uint64_t lastObservedAtMs = 0) const
    {
        bool const live = LiveFor(currentAttemptId);
        std::string json = "{\"bone_warrior_active_over_45s\":"
            + std::to_string(live ? _activeOverLimit.size() : 0)
            + ",\"bone_warrior_on_pillar\":"
            + std::to_string(live ? _onPillar.size() : 0) + ",\"move_refused\":{";
        bool firstActor = true;
        for (auto const& [actor, reasons] : live ? _refused : Empty())
        {
            json += std::string(firstActor ? "" : ",") + "\"" + std::to_string(actor) + "\":{";
            firstActor = false;
            bool firstReason = true;
            for (auto const& [reason, count] : reasons)
            {
                json += std::string(firstReason ? "" : ",") + "\"" + Escape(reason) + "\":"
                    + std::to_string(count);
                firstReason = false;
            }
            json += "}";
        }
        json += std::string("},\"complete\":") + (live && covered ? "true" : "false")
            + ",\"attempt_id\":" + std::to_string(currentAttemptId)
            + ",\"combat_log_epoch\":" + std::to_string(lifecycle)
            + ",\"first_observed_at_ms\":" + std::to_string(live ? firstObservedAtMs : 0)
            + ",\"last_observed_at_ms\":" + std::to_string(live ? lastObservedAtMs : 0) + "}";
        return json;
    }

    static std::string Escape(std::string_view value)
    {
        std::string escaped;
        for (char c : value)
        {
            if (c == '"' || c == '\\')
            {
                escaped += '\\';
                escaped += c;
            }
            else if (static_cast<unsigned char>(c) < 0x20)
            {
                char code[8];
                std::snprintf(code, sizeof(code), "\\u%04x", static_cast<unsigned>(c));
                escaped += code;
            }
            else
                escaped += c;
        }
        return escaped;
    }

private:
    using RefusedMap = std::map<std::uint64_t, std::map<std::string, std::uint64_t>>;
    static RefusedMap const& Empty()
    {
        static RefusedMap const empty;
        return empty;
    }

    std::uint64_t _attemptId = 0;
    bool _live = false;
    std::set<std::uint64_t> _activeOverLimit;
    std::set<std::uint64_t> _onPillar;
    RefusedMap _refused;
};
}

#endif

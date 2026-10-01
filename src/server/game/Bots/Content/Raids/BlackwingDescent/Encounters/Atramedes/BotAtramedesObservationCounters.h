#ifndef TRINITY_BOT_ATRAMEDES_OBSERVATION_COUNTERS_H
#define TRINITY_BOT_ATRAMEDES_OBSERVATION_COUNTERS_H

// Server-side counters of the round-3 acceptance observation of BWD 10N
// Atramedes, exported in `.botauto status`
// raid_runtime.encounter_observations.atramedes and judged by
// tools/raid_program/run_sanity.py.
//
// User decision 2026-09-30 ("Bound kiter Sound"): the native Roaring Flame
// keeps its time-only speed ramp, and during every air-phase chase the
// tracked kiter stays at KiterSoundBound Sound or less, the range the WCL
// chases measured (ledger claim breath_speed_scaling_with_sound). A chase
// runs from the snapshot in which the flame follows a player until it
// follows another one, follows nobody (a gong redirect) or the air phase
// ends; every engaged snapshot of it is one sample of the kiter's Sound.
//
// One instance per cohort, scoped to the cohort attempt: Begin(attempt)
// starts the counters and a different attempt resets them. They count air
// phases, chases, chase samples, the loudest kiter sample and the samples
// above the bound, and keep the largest gap between two samples while
// Atramedes was engaged. `complete` is true only while the counters are live
// for the attempt asked about and the caller's sampling covered that attempt
// (BotAtramedesObservationStore.h); a stale attempt exports zeros with
// complete false.
// Standard library only, so the logic compiles in a g++ program test.

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace BotEncounter::Atramedes
{
inline constexpr std::uint32_t KiterSoundBound = 10;
// A gap longer than this between two samples while Atramedes is engaged
// ends the coverage: a breath tick (+3 Sound) lands every 500 ms, and the
// encounter snapshot is republished every 100 ms.
inline constexpr std::uint64_t MaxSampleGapMs = 1000;

// One snapshot as the chase watch reads it.
struct ChaseSample
{
    // Atramedes is engaged on his encounter node (ground or air phase).
    bool Engaged = false;
    bool Air = false;
    // The raw guid of the player the Reverberating Flame follows (0: none)
    // and that player's Sound.
    std::uint64_t Kiter = 0;
    std::uint32_t Sound = 0;
    // The snapshot time (system ms) and the source, size and time of the
    // kiter's last Sound rise, possibly before the chase
    // (BotAtramedesSoundSources.h; empty when nobody attributed it).
    std::uint64_t AtMs = 0;
    std::string Source;
    std::uint32_t Increment = 0;
    std::uint64_t IncrementAtMs = 0;
};

// Round 4: the chase samples as a run-length list, so the export explains
// every sample, the ones above the bound first of all: an entry for the first
// sample of each chase and for every sample whose Sound differs from the one
// before it in the chase (every other sample repeats the entry before it).
// At most MaxSoundSamples entries; the rest are counted as dropped.
inline constexpr std::size_t MaxSoundSamples = 256;

struct SoundSampleEntry
{
    std::uint64_t AtMs = 0;
    std::uint64_t Kiter = 0;
    std::uint32_t Sound = 0;
    std::string Source;
    std::uint32_t Increment = 0;
    std::uint64_t IncrementAtMs = 0;
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
            *this = ObservationCounters();
            _attemptId = attemptId;
            _live = true;
        }
        return true;
    }

    bool LiveFor(std::uint64_t attemptId) const
    {
        return _live && attemptId && _attemptId == attemptId;
    }

    // One sample, newer than every sample before it, of the live attempt.
    void Record(std::uint64_t attemptId, ChaseSample const& sample)
    {
        if (!LiveFor(attemptId))
            return;
        bool const air = sample.Engaged && sample.Air;
        if (air && !_inAir)
            ++_airPhases;
        _inAir = air;
        if (!air || !sample.Kiter)
        {
            _chaseKiter = 0;
            return;
        }
        bool const newChase = sample.Kiter != _chaseKiter;
        if (newChase)
        {
            ++_chases;
            _chaseKiter = sample.Kiter;
        }
        if (newChase || sample.Sound != _listedSound)
        {
            if (_soundSamples.size() < MaxSoundSamples)
                _soundSamples.push_back({ sample.AtMs, sample.Kiter, sample.Sound, sample.Source,
                    sample.Increment, sample.IncrementAtMs });
            else
                ++_soundSamplesDropped;
            _listedSound = sample.Sound;
        }
        ++_chaseSamples;
        if (sample.Sound > _maxKiterSound)
            _maxKiterSound = sample.Sound;
        if (sample.Sound > KiterSoundBound)
            ++_samplesAboveBound;
    }

    // The time between two samples while Atramedes was engaged.
    void RecordGap(std::uint64_t attemptId, std::uint64_t gapMs)
    {
        if (LiveFor(attemptId) && gapMs > _maxSampleGapMs)
            _maxSampleGapMs = gapMs;
    }

    std::uint32_t AirPhases() const { return _airPhases; }
    std::uint32_t Chases() const { return _chases; }
    std::uint64_t ChaseSamples() const { return _chaseSamples; }
    std::uint32_t MaxKiterSound() const { return _maxKiterSound; }
    std::uint64_t SamplesAboveBound() const { return _samplesAboveBound; }
    std::vector<SoundSampleEntry> const& SoundSamples() const { return _soundSamples; }
    std::uint64_t SoundSamplesDropped() const { return _soundSamplesDropped; }

    // {"air_phases":n,"chases":n,"chase_samples":n,"max_kiter_sound":n,
    //  "samples_above_10":n,"max_sample_gap_ms":n,"complete":b,"attempt_id":n,
    //  "combat_log_epoch":n,"first_observed_at_ms":n,"last_observed_at_ms":n,
    //  "sound_samples":[...],"sound_samples_dropped":n}
    // for the cohort's current attempt and its start lifecycle
    // (CohortRuntime::CombatLogEpoch), which run_sanity binds to the judged
    // combat-log capture. An uncovered live attempt keeps its counts (a lower
    // bound) with complete false. The last two are the times (system ms, the
    // clock of the combat log and of the snapshots' ObservedAtMs) of the first
    // and newest snapshot the sampling took in the attempt (0: none): the
    // harness requires them near the boss window's edges, since `complete`
    // alone does not say the sampling ran anywhere near them.
    std::string Json(std::uint64_t currentAttemptId, std::uint64_t lifecycle, bool covered = true,
        std::uint64_t firstObservedAtMs = 0, std::uint64_t lastObservedAtMs = 0) const
    {
        bool const live = LiveFor(currentAttemptId);
        auto count = [live](std::uint64_t value) { return std::to_string(live ? value : 0); };
        return "{\"air_phases\":" + count(_airPhases) + ",\"chases\":" + count(_chases)
            + ",\"chase_samples\":" + count(_chaseSamples)
            + ",\"max_kiter_sound\":" + count(_maxKiterSound)
            + ",\"samples_above_" + std::to_string(KiterSoundBound) + "\":"
            + count(_samplesAboveBound) + ",\"max_sample_gap_ms\":" + count(_maxSampleGapMs)
            + ",\"complete\":" + (live && covered ? "true" : "false")
            + ",\"attempt_id\":" + std::to_string(currentAttemptId)
            + ",\"combat_log_epoch\":" + std::to_string(lifecycle)
            + ",\"first_observed_at_ms\":" + std::to_string(live ? firstObservedAtMs : 0)
            + ",\"last_observed_at_ms\":" + std::to_string(live ? lastObservedAtMs : 0)
            + ",\"sound_samples\":" + SoundSamplesJson(live)
            + ",\"sound_samples_dropped\":" + count(_soundSamplesDropped) + "}";
    }

private:
    // [{"at_ms":n,"kiter":n,"sound":n,"last_increment_source":s,
    //   "last_increment":n,"last_increment_at_ms":n},...]; the source is one
    // of BotAtramedesSoundSources.h's names (letters, '_' and '+').
    std::string SoundSamplesJson(bool live) const
    {
        std::string json = "[";
        if (live)
            for (SoundSampleEntry const& entry : _soundSamples)
            {
                if (json.size() > 1)
                    json += ',';
                std::string source;
                for (char c : entry.Source)
                    if ((c >= 'a' && c <= 'z') || c == '_' || c == '+')
                        source += c;
                json += "{\"at_ms\":" + std::to_string(entry.AtMs) + ",\"kiter\":" + std::to_string(entry.Kiter)
                    + ",\"sound\":" + std::to_string(entry.Sound) + ",\"last_increment_source\":\""
                    + source + "\",\"last_increment\":" + std::to_string(entry.Increment)
                    + ",\"last_increment_at_ms\":" + std::to_string(entry.IncrementAtMs) + "}";
            }
        return json + "]";
    }

    std::uint64_t _attemptId = 0;
    bool _live = false;
    bool _inAir = false;
    std::uint64_t _chaseKiter = 0;
    std::uint32_t _airPhases = 0;
    std::uint32_t _chases = 0;
    std::uint64_t _chaseSamples = 0;
    std::uint32_t _maxKiterSound = 0;
    std::uint64_t _samplesAboveBound = 0;
    std::uint64_t _maxSampleGapMs = 0;
    std::uint32_t _listedSound = 0;
    std::vector<SoundSampleEntry> _soundSamples;
    std::uint64_t _soundSamplesDropped = 0;
};

// `field` (the status field another encounter exported:
// ",\"encounter_observations\":{...}" or "") with `block` added as its
// "atramedes" member, so one status never carries the key twice. An empty
// block leaves `field` byte-identical. A field of another shape is returned
// unchanged: the Atramedes evidence is then absent, which the sanity check
// reports as unproven, never as a pass.
inline std::string WithAtramedesObservations(std::string const& field,
    std::string const& block)
{
    static std::string const prefix = ",\"encounter_observations\":{";
    if (block.empty())
        return field;
    if (field.empty() || field == prefix + "}")
        return prefix + "\"atramedes\":" + block + "}";
    if (field.size() <= prefix.size() || field.compare(0, prefix.size(), prefix) != 0
        || field.back() != '}')
        return field;
    return field.substr(0, field.size() - 1) + ",\"atramedes\":" + block + "}";
}
}

#endif

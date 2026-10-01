"""BWD 10N round 3 fix (Atramedes): the kiter Sound acceptance observation, server side.

Review finding (scoreboard/research review, item 5): the 10N claim breath_speed_scaling_with_sound was closed
although every measured WCL chase had the tracked kiter at 0-10 Sound; an additive Sound term above 10 was
never measured. User decision 2026-09-30 ("Bound kiter Sound"): keep the native time-only ramp and accept a
10N kill only when, during every air-phase Roaring Flame chase, the tracked kiter stays at 10 Sound or less.

The server keeps per-cohort, per-attempt counters (BotAtramedesObservationCounters.h) of the chases, their
samples, the loudest kiter sample and the samples above 10, and exports them in `.botauto status` as
raid_runtime.encounter_observations.atramedes, merged into the one encounter_observations object the Nefarian
export opens. This file checks the counters and the merge in a standard-library g++ program, and the wiring
of the store, the reporter call and the raid_runtime export in the sources; the store's scoping and sampling
are replayed in tests/test_atramedes_observation_scope.py.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
ATRAMEDES = BOTS / "Content/Raids/BlackwingDescent/Encounters/Atramedes"
COUNTERS = ATRAMEDES / "BotAtramedesObservationCounters.h"
EXPORT = ATRAMEDES / "BotAtramedesObservationExport.h"
STORE = ATRAMEDES / "BotAtramedesObservationStore.h"
CANDIDATES = ATRAMEDES / "BotWorldPopulationMgrAtramedesCandidates.cpp"
RAID_RUNTIME = BOTS / "BotWorldPopulationMgrRaidRuntime.cpp"


def _run(tmp_path: Path, program: str) -> str:
    source, binary = tmp_path / "program.cpp", tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src/server/game")]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationCounters.h"
#include <cstdio>
#include <string>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotEncounter::Atramedes;

static ChaseSample Sample(bool air, std::uint64_t kiter, std::uint32_t sound)
{
    ChaseSample sample;
    sample.Engaged = true;
    sample.Air = air;
    sample.Kiter = kiter;
    sample.Sound = sound;
    return sample;
}
static ChaseSample Ground() { return Sample(false, 0, 0); }
static ChaseSample Air(std::uint64_t kiter = 0, std::uint32_t sound = 0) { return Sample(true, kiter, sound); }

// The block without its round-4 run-length Sound samples (checked on their own below).
static std::string Counts(std::string const& json)
{
    size_t const at = json.find(",\"sound_samples\":");
    return at == std::string::npos ? json : json.substr(0, at) + "}";
}

// Every block names its attempt and start lifecycle (here lifecycle 5 + the attempt id).
static std::string Expected(int air, int chases, int samples, int maxSound, int above, int gap, bool complete,
    std::uint64_t attempt)
{
    return "{\"air_phases\":" + std::to_string(air) + ",\"chases\":" + std::to_string(chases)
        + ",\"chase_samples\":" + std::to_string(samples) + ",\"max_kiter_sound\":" + std::to_string(maxSound)
        + ",\"samples_above_10\":" + std::to_string(above) + ",\"max_sample_gap_ms\":" + std::to_string(gap)
        + ",\"complete\":" + (complete ? "true" : "false") + ",\"attempt_id\":" + std::to_string(attempt)
        + ",\"combat_log_epoch\":" + std::to_string(5 + attempt)
        + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}";
}

// Round 4: the chase samples as a run-length list with the kiter's last
// Sound rise (BotAtramedesSoundSources.h), so a sample above the bound can be
// explained from the export alone.
static void TestSoundSamples()
{
    ObservationCounters counters;
    CHECK(counters.Begin(5), "attempt 5");
    auto sample = [](std::uint64_t at, std::uint64_t kiter, std::uint32_t sound, char const* source,
        std::uint32_t increment, std::uint64_t incrementAt)
    {
        ChaseSample chase = Air(kiter, sound);
        chase.AtMs = at;
        chase.Source = source;
        chase.Increment = increment;
        chase.IncrementAtMs = incrementAt;
        return chase;
    };
    // A chase of 7 at 0, 0, 3, 3: two entries (the chase's first sample, the rise).
    counters.Record(5, sample(1000, 7, 0, "", 0, 0));
    counters.Record(5, sample(1100, 7, 0, "", 0, 0));
    counters.Record(5, sample(1200, 7, 3, "roaring_flame", 3, 1200));
    counters.Record(5, sample(1300, 7, 3, "roaring_flame", 3, 1200));
    // Not chased: no entry. The striker 8 re-tracked at 20 by a bomb that
    // landed before the chase: its first sample names that bomb.
    counters.Record(5, Air());
    counters.Record(5, sample(4000, 8, 20, "sonar_bomb", 20, 2500));
    CHECK(counters.SoundSamples().size() == 3 && counters.SoundSamplesDropped() == 0, "run-length entries");
    CHECK(counters.SoundSamples().back().Source == "sonar_bomb"
        && counters.SoundSamples().back().IncrementAtMs == 2500, "the source travels with the sample");
    std::string const json = counters.Json(5, 6);
    CHECK(json.find(",\"sound_samples\":[{\"at_ms\":1000,\"kiter\":7,\"sound\":0,\"last_increment_source\":\"\","
        "\"last_increment\":0,\"last_increment_at_ms\":0},{\"at_ms\":1200,\"kiter\":7,\"sound\":3,"
        "\"last_increment_source\":\"roaring_flame\",\"last_increment\":3,\"last_increment_at_ms\":1200},"
        "{\"at_ms\":4000,\"kiter\":8,\"sound\":20,\"last_increment_source\":\"sonar_bomb\","
        "\"last_increment\":20,\"last_increment_at_ms\":2500}],\"sound_samples_dropped\":0}") != std::string::npos,
        json.c_str());
    // A stale attempt exports none; a source is never more than its name.
    CHECK(counters.Json(6, 7).find(",\"sound_samples\":[],\"sound_samples_dropped\":0}") != std::string::npos,
        "stale attempt: no samples");
    counters.Record(5, sample(4100, 8, 23, "fire\"_patch", 3, 4100));
    CHECK(counters.Json(5, 6).find("\"last_increment_source\":\"fire_patch\"") != std::string::npos, "sanitized");
    // The cap: every further change is counted as dropped.
    for (std::uint32_t index = 0; index < 400; ++index)
        counters.Record(5, sample(5000 + index, 8, index % 2, "", 0, 0));
    CHECK(counters.SoundSamples().size() == MaxSoundSamples
        && counters.SoundSamplesDropped() == 4 + 400 - MaxSoundSamples, "capped");
}

int main()
{
    CHECK(KiterSoundBound == 10, "the user's bound: 10 Sound, the range the WCL chases measured");
    ObservationCounters counters;
    // Before any attempt: nothing is live, nothing records, the export says so.
    CHECK(!counters.LiveFor(1), "no attempt yet");
    counters.Record(1, Air(7, 50));
    counters.RecordGap(1, 900);
    CHECK(Counts(counters.Json(1, 6)) == Expected(0, 0, 0, 0, 0, 0, false, 1), "incomplete zeros before Begin");
    CHECK(!counters.Begin(0) && !counters.LiveFor(0), "attempt 0 is never an attempt");

    // Attempt 3: a ground phase, liftoff (no flame yet), a chase of player 7
    // at 0-9 Sound, a redirect (nobody chased), the striker 8 chased at 0-3,
    // then 8 again after its own second strike: a new chase of the same player.
    CHECK(counters.Begin(3) && counters.LiveFor(3), "attempt 3 live");
    counters.Record(3, Ground());
    counters.Record(3, Air());
    CHECK(counters.AirPhases() == 1 && counters.Chases() == 0, "liftoff: an air phase, no chase yet");
    for (std::uint32_t sound : { 0u, 3u, 6u, 9u })
        counters.Record(3, Air(7, sound));
    CHECK(counters.Chases() == 1 && counters.ChaseSamples() == 4, "one chase, four samples");
    CHECK(counters.MaxKiterSound() == 9 && counters.SamplesAboveBound() == 0, "9 Sound is within the bound");
    counters.Record(3, Air());
    counters.Record(3, Air(8, 0));
    counters.Record(3, Air(8, 3));
    counters.Record(3, Air());
    counters.Record(3, Air(8, 0));
    CHECK(counters.Chases() == 3 && counters.ChaseSamples() == 7, "a redirect ends the chase, even of the same player");
    // Another player's Sound never counts: only the kiter's is sampled.
    counters.Record(3, Air(8, 10));
    CHECK(counters.SamplesAboveBound() == 0 && counters.MaxKiterSound() == 10, "10 is still within the bound");
    counters.Record(3, Air(8, 13));
    counters.Record(3, Air(8, 16));
    CHECK(counters.SamplesAboveBound() == 2 && counters.MaxKiterSound() == 16, "13 and 16 are above it");
    // The landing ends the air phase; the next liftoff is a second one.
    counters.Record(3, Ground());
    counters.Record(3, Air(9, 0));
    CHECK(counters.AirPhases() == 2 && counters.Chases() == 4, "a second air phase and its chase");
    // Not engaged (wipe, kill): the air phase and the chase end.
    counters.Record(3, ChaseSample());
    counters.Record(3, Air(9, 0));
    CHECK(counters.AirPhases() == 3 && counters.Chases() == 5, "a new pull's air phase is new");
    counters.RecordGap(3, 250);
    counters.RecordGap(3, 400);
    counters.RecordGap(3, 100);
    CHECK(counters.Begin(3) && counters.Chases() == 5, "Begin of the same attempt keeps the counts");
    std::string const json = Counts(counters.Json(3, 8));
    CHECK(json == Expected(3, 5, 12, 16, 2, 400, true, 3), json.c_str());
    // A status read for another attempt never reports this attempt's counts;
    // an uncovered live attempt keeps its counts, never complete.
    CHECK(Counts(counters.Json(4, 9)) == Expected(0, 0, 0, 0, 0, 0, false, 4), "stale attempt: incomplete zeros");
    CHECK(Counts(counters.Json(3, 8, false)) == Expected(3, 5, 12, 16, 2, 400, false, 3), "uncovered: counts, not complete");
    // The sampling's first and newest sample times (system ms, the combat log's clock) are exported for the live
    // attempt only; the harness holds them against the boss window (run_sanity_inputs.observation_window_coverage).
    std::string const timed = counters.Json(3, 8, true, 1790000010000ull, 1790000250000ull);
    CHECK(timed.find(",\"combat_log_epoch\":8,\"first_observed_at_ms\":1790000010000,"
        "\"last_observed_at_ms\":1790000250000,\"sound_samples\":[") != std::string::npos, "the observation times are exported");
    CHECK(Counts(counters.Json(4, 9, true, 1790000010000ull, 1790000250000ull))
        == Expected(0, 0, 0, 0, 0, 0, false, 4), "a stale attempt exports no observation times");

    // A new attempt resets every counter; a late write of the old one is dropped.
    CHECK(counters.Begin(4) && counters.LiveFor(4) && !counters.LiveFor(3), "attempt 4 replaces 3");
    counters.Record(3, Air(7, 60));
    counters.RecordGap(3, 5000);
    CHECK(Counts(counters.Json(4, 9)) == Expected(0, 0, 0, 0, 0, 0, true, 4), "a complete zero of the new attempt");
    // The chase state resets too: the first sample of the new attempt is a new chase.
    counters.Record(4, Air(9, 0));
    CHECK(counters.AirPhases() == 1 && counters.Chases() == 1, "the new attempt counts from zero");

    // The merge into the one encounter_observations object.
    std::string const block = "{\"a\":1}";
    std::string const nefarian = ",\"encounter_observations\":{\"nefarian\":{\"n\":2}}";
    CHECK(WithAtramedesObservations("", "") == "", "nothing to export: nothing");
    CHECK(WithAtramedesObservations(nefarian, "") == nefarian, "no Atramedes block: byte-identical");
    CHECK(WithAtramedesObservations("", block) == ",\"encounter_observations\":{\"atramedes\":{\"a\":1}}",
        "Atramedes alone");
    CHECK(WithAtramedesObservations(nefarian, block)
        == ",\"encounter_observations\":{\"nefarian\":{\"n\":2},\"atramedes\":{\"a\":1}}", "both in one object");
    CHECK(WithAtramedesObservations(",\"encounter_observations\":{}", block)
        == ",\"encounter_observations\":{\"atramedes\":{\"a\":1}}", "an empty object");
    CHECK(WithAtramedesObservations(",\"other\":{}", block) == ",\"other\":{}",
        "an unknown shape is left alone (the block is then absent: unproven, never a pass)");
    TestSoundSamples();
    std::printf("%s\n%s\n", WithAtramedesObservations(nefarian, counters.Json(4, 9)).c_str(),
        WithAtramedesObservations("", counters.Json(4, 9)).c_str());

    if (failures)
        return 1;
    std::printf("ok\n");
    return 0;
}
'''


def test_counter_and_reset_logic(tmp_path):
    lines = _run(tmp_path, PROGRAM).splitlines()
    assert lines[-1] == "ok"
    # Both merged fields are one well-formed status member.
    both, alone = (json.loads("{" + line[1:] + "}") for line in lines[:2])
    assert list(both["encounter_observations"]) == ["nefarian", "atramedes"]
    assert both["encounter_observations"]["atramedes"] == alone["encounter_observations"]["atramedes"] == {
        "air_phases": 1, "chases": 1, "chase_samples": 1, "max_kiter_sound": 0, "samples_above_10": 0,
        "max_sample_gap_ms": 0, "complete": True, "attempt_id": 4, "combat_log_epoch": 9,
        "first_observed_at_ms": 0, "last_observed_at_ms": 0,
        "sound_samples": [{"at_ms": 0, "kiter": 9, "sound": 0, "last_increment_source": "", "last_increment": 0,
                           "last_increment_at_ms": 0}],
        "sound_samples_dropped": 0}


def _body(text: str, signature: str) -> str:
    body = text[text.index(signature):]
    return body[:body.index("\n}\n")]


def test_the_status_export_is_wired_and_scoped_to_atramedes():
    runtime = RAID_RUNTIME.read_text()
    assert '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationExport.h"' in runtime
    full = _body(runtime, "std::string BotWorldPopulationMgr::BuildRaidRuntimeJson(bool compactTelemetry) const")
    tail = full[full.rindex("AppendRaidPrepullConsumablesJson(json);"):]
    # One encounter_observations object: the Atramedes export wraps the Nefarian field, both scoped to the
    # cohort's start lifecycle and attempt id, and the raid runtime object closes after it.
    assert ("json << BotEncounter::Atramedes::EncounterObservationsJsonField(\n"
            "        BotEncounter::Nefarian::EncounterObservationsJsonField(Cohort().Id,\n"
            "        { Cohort().CombatLogEpoch, Cohort().AttemptId }, Cohort().Config.ValidationRouteNodeId),\n"
            "        Cohort().Id, { Cohort().CombatLogEpoch, Cohort().AttemptId }, "
            "Cohort().Config.ValidationRouteNodeId) << \"}\";") in tail
    assert tail.count("EncounterObservationsJsonField(") == 2
    candidates = CANDIDATES.read_text()
    assert "static BotEncounter::Atramedes::ObservationStore store;" in candidates
    field = _body(candidates, "std::string BotEncounter::Atramedes::EncounterObservationsJsonField(")
    assert "return Observations().JsonField(field, cohortId, attempt, routeNodeId);" in field
    observer = _body(candidates, "void BotWorldPopulationMgr::SubmitAdaptiveAtramedesRouteObservation(")
    assert ("BotEncounter::Atramedes::ObservationAttempt const observationAttempt{\n"
            "        Cohort().CombatLogEpoch, Cohort().AttemptId };") in observer
    assert "if (context.AdaptiveAtramedesOwnsNode)\n        Observations().Begin(Cohort().Id, observationAttempt);" in observer
    assert ("if (Cohort().EncounterSnapshot)\n    {\n"
            "        Observations().Observe(Cohort().Id, observationAttempt, *Cohort().EncounterSnapshot);") in observer
    # The once-per-fight Ice Block guard sees the same snapshot (BotAtramedesIceBlockGuard.h).
    assert ("BotEncounter::Atramedes::ProcessIceBlockGuard().Observe(Cohort().Id,\n"
            "            observationAttempt, *Cohort().EncounterSnapshot);") in observer
    # Sampled on every decision, before the route observer's candidate (which the kernel may never reach).
    assert observer.index("Observations().Begin(") < observer.index("Observations().Observe(") \
        < observer.index("ProcessIceBlockGuard().Observe(") < observer.index("auto observe = [this, &context]()")
    store = STORE.read_text()
    json_field = _body(store, "    std::string JsonField(")
    assert "bool const current = found != _cohorts.end() && found->second.Attempt == attempt;" in json_field
    assert "if (!current && routeNodeId != EncounterNode)\n            return field;" in json_field
    # Both branches name the attempt's start lifecycle (combat_log_epoch), which run_sanity binds to the
    # judged capture.
    assert ("Counters.Json(attempt.AttemptId, attempt.Lifecycle, found->second.Covered(),\n"
            "                found->second.FirstMs, found->second.LatestMs)") in json_field
    assert ": ObservationCounters().Json(attempt.AttemptId, attempt.Lifecycle));" in json_field
    export = EXPORT.read_text()
    assert ("std::string EncounterObservationsJsonField(std::string const& field,\n"
            "    std::string const& cohortId, ObservationAttempt attempt, std::string const& routeNodeId);") in export
    assert "struct ObservationAttempt" in export and "#include <string>" in export
    assert "#include \"Bots/Content" not in export  # the raid runtime pulls no strategy header
    assert "#include \"Bots/" not in COUNTERS.read_text()  # standard library only


def test_changed_sources_stay_below_the_module_size_limit():
    for path in (COUNTERS, EXPORT, STORE, CANDIDATES, RAID_RUNTIME):
        assert len(path.read_text().splitlines()) < 1000, path

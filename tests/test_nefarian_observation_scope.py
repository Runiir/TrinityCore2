"""BWD 10N round 3 review (Nefarian): the acceptance observations are scoped.

Two reviewers found the round-3 bone-warrior watch process-global, keyed by
warrior guid only, and the observation export unscoped:
- P2: creature guids are map-local, so parallel Nefarian shards (one cohort
  and instance each, in one worldserver) collided in the shared watch: shard
  A's pillar report suppressed shard B's matching one, and B exported zero
  violations with complete:true; a collapse in A reset B's active span;
- P2: the shared watch's cleanup subtracted independently cached cohort
  timestamps; a snapshot older than another cohort's underflowed and erased
  the live history (zero active-over-limit where an isolated watch has one);
- P3: a cohort reused for Stonecore, calibration or legacy Magmaw after a
  Nefarian run exported encounter_observations.nefarian, unlike a fresh
  process.
The program drives the production headers (BotNefarianObservationStore.h,
BotNefarianWarriorWatch.h, BotNefarianObservationCounters.h): each
reproduction with its control, also under the sanitizers. The wiring of
BotWorldPopulationMgrNefarianCandidates.cpp and the raid_runtime export is
checked in tests/test_nefarian_observation_counters.py.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run


PROGRAM = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationStore.h"
#include <string_view>

static uint64 const T0 = 1790000000000ull;
static ObservationAttempt const Attempt1{ 1, 1 };

static Blackboard ShardBoard(std::string const& cohort, uint64 attempt, uint32 instance,
    std::vector<ActorSnapshot> warriors)
{
    Blackboard board = CanonicalBoard();
    board.CurrentScope.CohortId = cohort;
    board.CurrentScope.AttemptId = attempt;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = instance;
    board.Summons = std::move(warriors);
    return board;
}

// On pillar 1's rim (local z 9.3): an on_pillar violation.
static ActorSnapshot Climber(uint32 counter)
{
    return MakeCreature(BoneWarriorEntry, counter, PillarRadial(1, 0, DescentRimRadius), 0.0f, 9.3f);
}

// Active on the floor, off every pillar.
static ActorSnapshot Floor(uint32 counter)
{
    return MakeCreature(BoneWarriorEntry, counter, { 10.0f, 0.0f });
}

static void SetCollapsed(ActorSnapshot& warrior, bool collapsed)
{
    warrior.Auras.clear();
    if (collapsed)
        AddAura(warrior, SpellBoneFeignDeath);
    warrior.Selectable = !collapsed;
}

// As the reporter does: the attempt is begun, then its snapshot observed. Each call is a newly
// published snapshot (the revision advances); cached repeats are replayed in
// tests/test_nefarian_observation_snapshots.py.
static uint64 NextRevision = 0;
static uint64 const SystemBase = 1790000000000ull;  // system ms of steady time 0

static std::vector<WarriorViolation> Observe(ObservationStore& store, std::string const& cohort,
    ObservationAttempt attempt, Blackboard const& board, uint64 at)
{
    store.Begin(cohort, attempt);
    return store.ObserveWarriors(cohort, attempt, board.CurrentScope, ObserveEncounter(board),
        { ++NextRevision, SystemBase + at }, at);
}

// The block with its observation times (the first and newest observed snapshot's publication, system ms)
// zeroed: these checks compare the counters and the coverage flag; the times are checked in
// tests/test_nefarian_observation_snapshots.py.
static std::string ZeroTimes(std::string json)
{
    size_t const at = json.find(",\"first_observed_at_ms\":");
    return at == std::string::npos ? json
        : json.substr(0, at) + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}}";
}

static std::string Block(ObservationStore const& store, std::string const& cohort,
    ObservationAttempt attempt, std::string_view route = EncounterNodeId)
{
    return ZeroTimes(store.JsonField(cohort, attempt, route));
}

static std::string Expected(int active, int pillar, bool complete, ObservationAttempt attempt,
    std::string const& refused = "")
{
    return ",\"encounter_observations\":{\"nefarian\":{\"bone_warrior_active_over_45s\":"
        + std::to_string(active) + ",\"bone_warrior_on_pillar\":" + std::to_string(pillar)
        + ",\"move_refused\":{" + refused + "},\"complete\":" + (complete ? "true" : "false")
        + ",\"attempt_id\":" + std::to_string(attempt.AttemptId)
        + ",\"combat_log_epoch\":" + std::to_string(attempt.Lifecycle)
        + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}}";
}

// P2 (both reviewers): two seeded Nefarian instances whose warriors share a
// guid never share a watch.
static void TestCollidingGuidsAcrossInstances()
{
    ObservationStore store;
    Blackboard a = ShardBoard("shard_a", 1, 101, { Climber(41) });
    Blackboard b = ShardBoard("shard_b", 1, 102, { Climber(41) });
    CHECK(a.Summons[0].Guid == b.Summons[0].Guid, "the two instances' warriors share a guid");
    std::vector<WarriorViolation> const inA = Observe(store, "shard_a", Attempt1, a, T0);
    std::vector<WarriorViolation> const inB = Observe(store, "shard_b", Attempt1, b, T0);
    CHECK(inA.size() == 1 && inA[0].Kind == WarriorViolationKind::OnPillar, "A's pillar violation");
    CHECK(inB.size() == 1 && inB[0].Kind == WarriorViolationKind::OnPillar,
        "B's matching violation is reported too");
    CHECK(Block(store, "shard_b", Attempt1) == Expected(0, 1, true, Attempt1), "B exports its own violation");
    CHECK(Block(store, "shard_a", Attempt1) == Expected(0, 1, true, Attempt1), "A exports its own violation");

    // A's warrior 42 collapses and wakes every other second; B's warrior 42
    // stays active: B's span is never reset by A.
    Blackboard a2 = ShardBoard("shard_a", 1, 101, { Floor(42) });
    Blackboard b2 = ShardBoard("shard_b", 1, 102, { Floor(42) });
    for (int second = 1; second <= 50; ++second)
    {
        SetCollapsed(a2.Summons[0], second % 2 == 1);
        Observe(store, "shard_a", Attempt1, a2, T0 + uint64(second) * 1000);
        Observe(store, "shard_b", Attempt1, b2, T0 + uint64(second) * 1000);
    }
    CHECK(Block(store, "shard_b", Attempt1) == Expected(1, 1, true, Attempt1),
        "B's warrior active past 45 s is reported");
    CHECK(Block(store, "shard_a", Attempt1) == Expected(0, 1, true, Attempt1), "A's collapsing warrior is not");
}

// P2 (shared runtime): a snapshot older than one already observed never
// underflows an age and never erases a live entry.
static void TestBackwardsTimestamps()
{
    Blackboard board = ShardBoard("cohort_a", 1, 101, { Floor(50) });
    Blackboard empty = ShardBoard("cohort_a", 1, 101, {});
    WarriorWatch watch;
    CHECK(watch.Observe(ObserveEncounter(board), T0).empty(), "a fresh warrior is not a violation");
    CHECK(watch.Observe(ObserveEncounter(board), T0 - 50).empty(),
        "an older snapshot with the warrior reports nothing (no underflowed age)");
    CHECK(watch.Observe(ObserveEncounter(empty), T0 - 50).empty(), "an older snapshot without it");
    CHECK(watch.LatestMs() == T0, "the watch's clock never goes back");
    CHECK(watch.CoverageBroken(), "any step back breaks the watch's coverage");
    // The reporter observes every decision: one-second steps here.
    std::vector<WarriorViolation> over;
    for (uint64 at = T0 + 1000; at <= T0 + WarriorActiveLimitMs + 1000; at += 1000)
        for (WarriorViolation const& violation : watch.Observe(ObserveEncounter(board), at))
            over.push_back(violation);
    CHECK(over.size() == 1 && over[0].Kind == WarriorViolationKind::ActiveOverLimit
        && over[0].ActiveMs == WarriorActiveLimitMs + 1000,
        "the live entry survived: its span runs from the first sight");

    // The reviewer's reproduction: cohort A observed at T, cohort B's cached
    // snapshot at T - 50, for 60 s. A matches an isolated watch.
    ObservationStore store;
    ObservationStore isolated;
    Blackboard bBoard = ShardBoard("cohort_b", 1, 102, {});
    for (int second = 0; second <= 60; ++second)
    {
        uint64 const at = T0 + uint64(second) * 1000;
        Observe(store, "cohort_a", Attempt1, board, at);
        Observe(store, "cohort_b", Attempt1, bBoard, at - 50);
        Observe(isolated, "cohort_a", Attempt1, board, at);
    }
    CHECK(Block(store, "cohort_a", Attempt1) == Expected(1, 0, true, Attempt1),
        "A's continuously active warrior is reported once");
    CHECK(Block(store, "cohort_a", Attempt1) == Block(isolated, "cohort_a", Attempt1),
        "as by an isolated watch");
    CHECK(Block(store, "cohort_b", Attempt1) == Expected(0, 0, true, Attempt1), "B saw no warrior");

    // Within one cohort: its own older cached copy (without the warrior)
    // interleaved at T - 50 erases nothing, but it is a step back of the
    // clock: the counts stay right and the attempt is no longer complete.
    ObservationStore same;
    for (int second = 0; second <= 60; ++second)
    {
        uint64 const at = T0 + uint64(second) * 1000;
        Observe(same, "cohort_a", Attempt1, board, at);
        Observe(same, "cohort_a", Attempt1, empty, at - 50);
    }
    CHECK(Block(same, "cohort_a", Attempt1) == Expected(1, 0, false, Attempt1),
        "a cohort's older cached copy never erases its history, and is not complete");

    // Any step back of the clock, however small, means the clock cannot be
    // trusted across it (tests/test_nefarian_observation_clock.py): the
    // attempt is no longer complete.
    ObservationStore clock;
    Observe(clock, "cohort_a", Attempt1, board, T0 + 100000);
    CHECK(Block(clock, "cohort_a", Attempt1) == Expected(0, 0, true, Attempt1), "one observation: whole");
    Observe(clock, "cohort_a", Attempt1, board, T0 + 100000 - 50);
    CHECK(Block(clock, "cohort_a", Attempt1) == Expected(0, 0, false, Attempt1), "a step back of 50 ms: not complete");
    Observe(clock, "cohort_a", Attempt1, board, T0);
    CHECK(Block(clock, "cohort_a", Attempt1) == Expected(0, 0, false, Attempt1),
        "a clock 100 s back: still not complete");
}

// Scope: the cohort's attempt (start lifecycle and attempt id) and the
// instance the watch binds to.
static void TestAttemptAndInstanceScope()
{
    ObservationStore store;
    CHECK(!store.Begin("shard", ObservationAttempt{ 1, 0 }), "attempt 0 is never an attempt");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, false, Attempt1), "nothing begun: a fresh block");
    CHECK(store.Begin("shard", Attempt1), "attempt 1 live");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, false, Attempt1),
        "begun but not observed: not complete");
    Blackboard first = ShardBoard("shard", 1, 7, { Climber(41) });
    CHECK(Observe(store, "shard", Attempt1, first, T0).size() == 1, "the pillar violation");
    CHECK(Observe(store, "shard", Attempt1, first, T0 + 1000).empty(), "reported once");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 1, true, Attempt1), "attempt 1 complete");

    // A new attempt in the same instance starts clean.
    ObservationAttempt const attempt2{ 1, 2 };
    Blackboard second = ShardBoard("shard", 2, 7, { Climber(41) });
    CHECK(Observe(store, "shard", attempt2, second, T0 + 2000).size() == 1,
        "a new attempt reports the same warrior again");
    CHECK(Block(store, "shard", attempt2) == Expected(0, 1, true, attempt2), "with its own counters");
    CHECK(Block(store, "shard", Attempt1) == Expected(0, 0, false, Attempt1), "the old attempt is stale");
    // A restart that keeps the attempt id (`.botexp start`) is a new lifecycle: clean too.
    ObservationAttempt const restarted{ 2, 2 };
    CHECK(Observe(store, "shard", restarted, second, T0 + 3000).size() == 1,
        "a restart with the same attempt id starts clean");
    CHECK(Block(store, "shard", attempt2) == Expected(0, 0, false, attempt2),
        "the earlier lifecycle's counts never pass as the restart's");

    // Snapshots of another attempt or cohort, or of no map, are never observed.
    ObservationAttempt const attempt3{ 2, 3 };
    CHECK(store.Begin("shard", attempt3), "attempt 3 live");
    CHECK(store.ObserveWarriors("shard", attempt3, second.CurrentScope, ObserveEncounter(second),
        { ++NextRevision, SystemBase + T0 + 4000 }, T0 + 4000).empty(), "a cached snapshot of attempt 2");
    Blackboard foreign = ShardBoard("other", 3, 7, { Climber(41) });
    CHECK(store.ObserveWarriors("shard", attempt3, foreign.CurrentScope, ObserveEncounter(foreign),
        { ++NextRevision, SystemBase + T0 + 4000 }, T0 + 4000).empty(), "another cohort's snapshot");
    Blackboard noMap = ShardBoard("shard", 3, 7, { Climber(41) });
    noMap.CurrentScope.MapId = 0;
    CHECK(store.ObserveWarriors("shard", attempt3, noMap.CurrentScope, ObserveEncounter(noMap),
        { ++NextRevision, SystemBase + T0 + 4000 }, T0 + 4000).empty(), "a snapshot of no map");
    CHECK(store.ObserveWarriors("never", Attempt1, first.CurrentScope, ObserveEncounter(first),
        { ++NextRevision, SystemBase + T0 + 4000 }, T0 + 4000).empty(), "a cohort never begun");
    CHECK(Block(store, "shard", attempt3) == Expected(0, 0, false, attempt3), "nothing observed: not complete");

    // An instance change within the attempt: a clean watch for the new
    // instance's guids, and the attempt is no longer complete.
    Blackboard here = ShardBoard("shard", 3, 7, { Floor(60) });
    CHECK(Observe(store, "shard", attempt3, here, T0 + 5000).empty(), "instance 7");
    CHECK(Block(store, "shard", attempt3) == Expected(0, 0, true, attempt3), "covered so far");
    Blackboard there = ShardBoard("shard", 3, 8, { Climber(41) });
    CHECK(Observe(store, "shard", attempt3, there, T0 + 6000).size() == 1, "instance 8's own warrior");
    CHECK(Block(store, "shard", attempt3) == Expected(0, 1, false, attempt3), "counts kept, complete false");

    // Refusals: counted only into the begun attempt; none creates a record.
    store.RecordRefused("shard", attempt3, 5, "hop:native_no_path");
    store.RecordRefused("shard", Attempt1, 5, "hop:stale_attempt");
    store.RecordRefused("fresh", Attempt1, 5, "hop:never_begun");
    CHECK(Block(store, "shard", attempt3) == Expected(0, 1, false, attempt3, "\"5\":{\"hop:native_no_path\":1}"),
        "the begun attempt's refusal only");
    CHECK(store.JsonField("fresh", Attempt1, "") == "", "a refusal never creates a record");
}

// P3: a cohort reused after a Nefarian run exports what a fresh process
// does; the same attempt keeps its terminal observations.
static void TestExportCohortReuse()
{
    ObservationStore fresh;
    ObservationStore store;
    std::string_view const otherRoutes[] = { "", "bwd.magmaw.encounter", "stonecore.encounter",
        "bwd.nefarian.descent" };
    for (std::string_view route : otherRoutes)
        CHECK(fresh.JsonField("default", Attempt1, route).empty(), "a fresh process: nothing elsewhere");
    CHECK(fresh.JsonField("default", Attempt1, EncounterNodeId) == Expected(0, 0, false, Attempt1),
        "a fresh process on Nefarian's route: an incomplete zero");

    // Nefarian in cohort `default`: a warrior on a pillar, one refusal.
    Blackboard board = ShardBoard("default", 1, 9, { Climber(41) });
    Observe(store, "default", Attempt1, board, T0);
    store.RecordRefused("default", Attempt1, 5, "hop:native_no_path");
    std::string const terminal = store.JsonField("default", Attempt1, EncounterNodeId);
    CHECK(ZeroTimes(terminal) == Expected(0, 1, true, Attempt1, "\"5\":{\"hop:native_no_path\":1}"),
        terminal.c_str());
    for (std::string_view route : otherRoutes)
        CHECK(store.JsonField("default", Attempt1, route) == terminal,
            "the same attempt keeps its terminal observations after the route moved on");

    // Reuse by `.botauto start` (a new attempt id) or `.botexp start` (a new
    // lifecycle, the attempt id kept): byte-identical to a fresh process.
    for (ObservationAttempt reuse : { ObservationAttempt{ 1, 2 }, ObservationAttempt{ 2, 1 } })
    {
        for (std::string_view route : otherRoutes)
        {
            CHECK(store.JsonField("default", reuse, route).empty(), "no stale block on another scenario");
            CHECK(store.JsonField("default", reuse, route) == fresh.JsonField("default", reuse, route),
                "as a fresh process");
        }
        CHECK(store.JsonField("default", reuse, EncounterNodeId)
            == fresh.JsonField("default", reuse, EncounterNodeId),
            "a new Nefarian run in the reused cohort starts from the fresh block");
    }
}

int main()
{
    TestCollidingGuidsAcrossInstances();
    TestBackwardsTimestamps();
    TestAttemptAndInstanceScope();
    TestExportCohortReuse();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    else
        std::printf("ok\n");
    return failures ? 1 : 0;
}
'''


def test_observations_are_scoped_by_cohort_attempt_and_instance(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM).strip() == "ok"


def test_observation_scope_under_sanitizers(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM, sanitize=True).strip() == "ok"

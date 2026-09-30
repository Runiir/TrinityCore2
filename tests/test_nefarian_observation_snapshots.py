"""BWD 10N round 3, v4 review (Nefarian): a snapshot is observed once.

The v4 review reproduced, with production headers: the reporter (the cohort's
lowest living bot) observed the warriors on every decision with fresh steady
time, while the blackboard is only republished when its system-time throttle
allows (BotWorldPopulationMgrEncounterBlackboard.cpp: `nowMs <
EncounterSnapshotNextRefreshMs` keeps the cached snapshot). After a backward
wall-clock step the cached snapshot therefore stayed in place and was
re-observed with advancing steady time: a warrior active for 2 s in it was
reported active over 45 s with complete:true, and shorter reversals aged
spans the same way.

The fix (BotNefarianWarriorWatch.h, BotNefarianObservationStore.h,
BotWorldPopulationMgrNefarianCandidates.cpp):
- the reporter passes the snapshot's Blackboard::Revision; the watch observes
  a revision once, at the steady time of the decision that first sees it;
- a repeat of the observed revision adds no state and no time; a repeat more
  than WarriorObservationGapMs after the last new snapshot is lost coverage
  (complete:false), and the next new snapshot restarts every span as a gap does;
- a revision below the observed one is skipped (coverage broken); revision 0
  (no identity) is never observed (coverage broken).

The store also exports the publication time (system ms, the combat log's clock) of the first and the newest
observed snapshot, which the run harness holds against the boss window (tests/
test_observation_window_coverage.py): a cached repeat, an out-of-order revision or revision 0 never moves them.

The program replays the production publisher's system-time throttle with a
wall clock that steps back, through the production store. The pre-fix
behaviour (WarriorWatch::Observe on every decision) runs as the reproduction,
each scenario with its control, also under the sanitizers.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run

ROOT = Path(__file__).resolve().parents[1]
NEFARIAN = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian"
CANDIDATES = NEFARIAN / "BotWorldPopulationMgrNefarianCandidates.cpp"
WATCH = NEFARIAN / "BotNefarianWarriorWatch.h"
STORE = NEFARIAN / "BotNefarianObservationStore.h"
BLACKBOARD_PUBLISHER = (ROOT / "src/server/game/Bots/BotWorldPopulationMgrEncounterBlackboard.cpp")


PROGRAM = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationStore.h"
#include <string_view>

static uint64 const T0 = 5000000ull;  // a steady clock, ms since boot
static ObservationAttempt const Attempt1{ 1, 1 };

static Blackboard WarriorBoard(std::vector<ActorSnapshot> warriors)
{
    Blackboard board = CanonicalBoard();
    board.CurrentScope.CohortId = "shard";
    board.CurrentScope.AttemptId = 1;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = 7;
    board.Summons = std::move(warriors);
    return board;
}

static ActorSnapshot Floor(uint32 counter)
{
    return MakeCreature(BoneWarriorEntry, counter, { 10.0f, 0.0f });
}

// On pillar 1's rim (local z 9.3): an on_pillar violation.
static ActorSnapshot Climber(uint32 counter)
{
    return MakeCreature(BoneWarriorEntry, counter, PillarRadial(1, 0, DescentRimRadius), 0.0f, 9.3f);
}

static Blackboard Active(uint32 counter) { return WarriorBoard({ Floor(counter) }); }

static Blackboard Collapsed(uint32 counter)
{
    ActorSnapshot warrior = Floor(counter);
    AddAura(warrior, SpellBoneFeignDeath);
    warrior.Selectable = false;
    return WarriorBoard({ warrior });
}

using Violations = std::vector<WarriorViolation>;

static void Append(Violations& all, Violations const& more)
{
    all.insert(all.end(), more.begin(), more.end());
}

static uint64 const SystemBase = 7000000000ull;  // system ms of steady time T0 (a wall clock, not a boot clock)

static uint64 SystemOf(uint64 at) { return SystemBase + (at - T0); }

// The exported JSON with the observation times zeroed (the counters and coverage flag are compared here),
// and the times themselves (TestObservationTimes).
static std::string ZeroTimes(std::string json)
{
    size_t const at = json.find(",\"first_observed_at_ms\":");
    return at == std::string::npos ? json
        : json.substr(0, at) + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}}";
}

static uint64 TimeField(std::string const& json, std::string const& key)
{
    size_t const at = json.find("\"" + key + "\":");
    return at == std::string::npos ? ~0ull : std::stoull(json.substr(at + key.size() + 3));
}

static std::string Block(ObservationStore const& store, ObservationAttempt attempt = Attempt1)
{
    return ZeroTimes(store.JsonField("shard", attempt, EncounterNodeId));
}

static std::string Expected(int active, int pillar, bool complete, ObservationAttempt attempt = Attempt1)
{
    return ",\"encounter_observations\":{\"nefarian\":{\"bone_warrior_active_over_45s\":"
        + std::to_string(active) + ",\"bone_warrior_on_pillar\":" + std::to_string(pillar)
        + ",\"move_refused\":{},\"complete\":" + (complete ? "true" : "false")
        + ",\"attempt_id\":" + std::to_string(attempt.AttemptId)
        + ",\"combat_log_epoch\":" + std::to_string(attempt.Lifecycle)
        + ",\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}}";
}

static bool OneActiveOverLimit(Violations const& found)
{
    return found.size() == 1 && found[0].Kind == WarriorViolationKind::ActiveOverLimit;
}

// The cohort's publisher (PublishEncounterBlackboard): the snapshot is rebuilt from the world only
// once the SYSTEM clock has reached the refresh time of the previous one (`nowMs <
// EncounterSnapshotNextRefreshMs` returns early and keeps the cached snapshot); every rebuild is a
// new revision (`++EncounterSnapshotRevision`).
struct Publisher
{
    uint64 Revision = 0;
    uint64 NextRefreshSystemMs = 0;
    bool Have = false;
    Blackboard Snapshot;

    Blackboard const& Read(Blackboard const& world, uint64 systemMs)
    {
        if (!Have || systemMs >= NextRefreshSystemMs)
        {
            Snapshot = world;
            Snapshot.ObservedAtMs = systemMs;  // snapshot->ObservedAtMs = nowMs
            ++Revision;
            NextRefreshSystemMs = systemMs + 100;
            Have = true;
        }
        return Snapshot;
    }
};

// The world one scenario runs: what the warriors really do at steady time `at`, and the wall clock
// (system time = steady time + offset; a step back lowers the offset).
struct Scenario
{
    Blackboard (*WorldAt)(uint64 at) = nullptr;
    uint64 StepAt = 0;      // steady time of the wall-clock step back (0: none)
    uint64 StepMs = 0;      // its size
    uint64 DecisionMs = 500;
    uint64 EndAt = 0;
};

struct Outcome
{
    Violations Fixed;       // through the production store (the fix)
    Violations Legacy;      // WarriorWatch::Observe on every decision (the code before the fix)
    std::string FixedBlock;
    std::string FixedRaw;   // the export with its observation times
    bool LegacyCoverageBroken = false;
    uint64 LastRevision = 0;
};

static Outcome Run(Scenario const& scenario)
{
    Outcome outcome;
    ObservationStore store;
    WarriorWatch legacy;
    Publisher publisher;
    for (uint64 at = T0; at <= scenario.EndAt; at += scenario.DecisionMs)
    {
        uint64 systemMs = SystemOf(at);
        if (scenario.StepAt && at >= scenario.StepAt)
            systemMs -= scenario.StepMs;
        Blackboard const world = scenario.WorldAt(at);
        Blackboard const& snapshot = publisher.Read(world, systemMs);
        store.Begin("shard", Attempt1);
        Append(outcome.Fixed, store.ObserveWarriors("shard", Attempt1, snapshot.CurrentScope,
            ObserveEncounter(snapshot), { publisher.Revision, snapshot.ObservedAtMs }, at));
        Append(outcome.Legacy, legacy.Observe(ObserveEncounter(snapshot), at));
    }
    outcome.FixedBlock = Block(store);
    outcome.FixedRaw = store.JsonField("shard", Attempt1, EncounterNodeId);
    outcome.LegacyCoverageBroken = legacy.CoverageBroken();
    outcome.LastRevision = publisher.Revision;
    return outcome;
}

// The v4 reproduction: the warrior is active for 2 s, collapses, and the wall clock steps back 45 s
// at that moment. The cached snapshot (the warrior active) is held for 45 s.
static Blackboard ActiveTwoSeconds(uint64 at)
{
    return at <= T0 + 2000 ? Active(50) : Collapsed(50);
}

static void TestBackwardStepFortyFiveSeconds()
{
    // Control: no step. The warrior really collapsed after 2 s: nothing is reported, the coverage is whole.
    Scenario control;
    control.WorldAt = ActiveTwoSeconds;
    control.EndAt = T0 + 50000;
    Outcome const whole = Run(control);
    CHECK(whole.Fixed.empty() && whole.Legacy.empty(), "control: a warrior active for 2 s reports nothing");
    CHECK(whole.FixedBlock == Expected(0, 0, true) && !whole.LegacyCoverageBroken, "control: complete");

    // The wall clock steps back 45 s as the warrior collapses.
    Scenario stepped = control;
    stepped.StepAt = T0 + 2000;
    stepped.StepMs = 45000;
    Outcome const outcome = Run(stepped);
    CHECK(OneActiveOverLimit(outcome.Legacy) && !outcome.LegacyCoverageBroken,
        "before the fix: 2 s of activity reported over 45 s, coverage whole (v4 reproduction)");
    CHECK(outcome.Fixed.empty(), "no false violation from the cached snapshot");
    CHECK(outcome.FixedBlock == Expected(0, 0, false), "the stale snapshot is lost coverage: complete:false");
    // The publisher really held one snapshot for the step: far fewer revisions than a whole run.
    CHECK(outcome.LastRevision < whole.LastRevision - 50, "the snapshot was held while the clock was back");
}

// Shorter reversals age spans the same way: 36 s of real activity plus a 10 s reversal is over 45 s.
static Blackboard ActiveThirtySixSeconds(uint64 at)
{
    return at <= T0 + 36000 ? Active(51) : Collapsed(51);
}

static void TestBackwardStepTenSeconds()
{
    Scenario control;
    control.WorldAt = ActiveThirtySixSeconds;
    control.EndAt = T0 + 60000;
    Outcome const whole = Run(control);
    CHECK(whole.Fixed.empty() && whole.FixedBlock == Expected(0, 0, true), "control: 36 s is under the limit");

    Scenario stepped = control;
    stepped.StepAt = T0 + 36000;
    stepped.StepMs = 10000;
    Outcome const outcome = Run(stepped);
    CHECK(OneActiveOverLimit(outcome.Legacy) && !outcome.LegacyCoverageBroken,
        "before the fix: 36 s of activity plus a 10 s reversal reads as over 45 s (v4 reproduction)");
    CHECK(outcome.Fixed.empty() && outcome.FixedBlock == Expected(0, 0, false),
        "the reversal's repeats add no time and end the coverage");
}

// A real 46 s activity and a short (1 s) reversal inside it: still reported once, still complete. The
// repeats inside the gap bound neither hide the violation nor break the coverage.
static Blackboard ActiveAlways(uint64)
{
    return Active(52);
}

static void TestShortReversalKeepsCoverage()
{
    Scenario control;
    control.WorldAt = ActiveAlways;
    control.EndAt = T0 + 50000;
    Outcome const whole = Run(control);
    CHECK(OneActiveOverLimit(whole.Fixed) && whole.FixedBlock == Expected(1, 0, true),
        "control: 46 s of real activity is reported, complete");

    Scenario stepped = control;
    stepped.StepAt = T0 + 20000;
    stepped.StepMs = 1000;
    Outcome const outcome = Run(stepped);
    CHECK(OneActiveOverLimit(outcome.Fixed), "a 1 s reversal does not hide the real violation");
    CHECK(outcome.FixedBlock == Expected(1, 0, true), "and a repeat inside the bound keeps the coverage whole");
}

// The reporter decides faster than the blackboard is republished (50 ms against the 100 ms throttle):
// every second decision reads the same snapshot. Nothing is counted twice and no time is added.
static void TestFastDecisionsReadRepeats()
{
    Scenario fast;
    fast.WorldAt = ActiveAlways;
    fast.DecisionMs = 50;
    fast.EndAt = T0 + 50000;
    Outcome const outcome = Run(fast);
    CHECK(OneActiveOverLimit(outcome.Fixed), "one violation");
    CHECK(outcome.Fixed[0].ActiveMs > WarriorActiveLimitMs && outcome.Fixed[0].ActiveMs <= WarriorActiveLimitMs + 100,
        "measured between new snapshots, 100 ms apart");
    CHECK(outcome.FixedBlock == Expected(1, 0, true), "repeats inside the bound keep the coverage whole");
    CHECK(outcome.LastRevision < 50000 / 50 * 6 / 10, "half the decisions read a cached snapshot");
}

static Violations Offer(ObservationStore& store, Blackboard const& board, uint64 revision, uint64 at,
    ObservationAttempt attempt = Attempt1)
{
    store.Begin("shard", attempt);
    return store.ObserveWarriors("shard", attempt, board.CurrentScope, ObserveEncounter(board),
        { revision, SystemOf(at) }, at);
}

// The repeat bound is WarriorObservationGapMs: exactly at it is continuous, one millisecond past is lost.
static void TestRepeatBound()
{
    Blackboard const board = Active(53);

    ObservationStore atBound;
    Offer(atBound, board, 1, T0);
    Offer(atBound, board, 1, T0 + WarriorObservationGapMs);
    CHECK(Block(atBound) == Expected(0, 0, true), "a repeat exactly at the bound keeps the coverage");

    ObservationStore pastBound;
    Offer(pastBound, board, 1, T0);
    Offer(pastBound, board, 1, T0 + WarriorObservationGapMs + 1);
    CHECK(Block(pastBound) == Expected(0, 0, false), "a repeat one millisecond past it is lost coverage");

    // The repeat measures against the last NEW snapshot, not the last repeat.
    ObservationStore sliding;
    Offer(sliding, board, 1, T0);
    for (uint64 at = T0 + 1000; at <= T0 + 2000; at += 500)
        Offer(sliding, board, 1, at);
    CHECK(Block(sliding) == Expected(0, 0, true), "repeats up to the bound");
    Offer(sliding, board, 1, T0 + 2500);
    CHECK(Block(sliding) == Expected(0, 0, false), "repeats do not renew the bound");
    // A new snapshot afterwards does not restore it.
    Offer(sliding, board, 2, T0 + 2600);
    CHECK(Block(sliding) == Expected(0, 0, false), "lost coverage stays lost");

    // A repeat adds nothing: no violation, no pillar report, nothing recorded twice.
    Blackboard const climber = WarriorBoard({ Climber(41) });
    ObservationStore pillar;
    Violations found = Offer(pillar, climber, 1, T0);
    CHECK(found.size() == 1 && found[0].Kind == WarriorViolationKind::OnPillar, "first sight reports the pillar");
    CHECK(Offer(pillar, climber, 1, T0 + 100).empty() && Offer(pillar, climber, 1, T0 + 200).empty(),
        "repeats report nothing");
    CHECK(Block(pillar) == Expected(0, 1, true), "counted once");
}

// A revision below the observed one is out of order, and revision 0 carries no identity.
static void TestRevisionIdentity()
{
    Blackboard const board = Active(54);

    ObservationStore older;
    Offer(older, board, 5, T0);
    Offer(older, board, 6, T0 + 100);
    CHECK(Block(older) == Expected(0, 0, true), "advancing revisions");
    CHECK(Offer(older, board, 5, T0 + 200).empty(), "an older snapshot reports nothing");
    CHECK(Block(older) == Expected(0, 0, false), "an older revision is lost coverage");
    WarriorWatch watch;
    watch.ObserveSnapshot({ 5, SystemOf(T0) }, ObserveEncounter(board), T0);
    watch.ObserveSnapshot({ 4, SystemOf(T0 + 100) }, ObserveEncounter(board), T0 + 100);
    CHECK(watch.LatestRevision() == 5 && watch.LatestMs() == T0, "the skipped snapshot leaves the watch as it was");
    CHECK(watch.CoverageBroken(), "and breaks the coverage");

    // Revision 0 is no snapshot identity: a climber on it is never reported.
    Blackboard const climber = WarriorBoard({ Climber(42) });
    ObservationStore none;
    CHECK(Offer(none, climber, 0, T0).empty(), "revision 0 is never observed");
    CHECK(Block(none) == Expected(0, 0, false), "and is not covered");
    CHECK(Offer(none, climber, 1, T0 + 100).size() == 1, "a real revision after it is observed");
    CHECK(Block(none) == Expected(0, 1, false), "the lost coverage stays lost");

    // Revisions continue across a silence: a gap, not a repeat.
    ObservationStore gap;
    Offer(gap, board, 1, T0);
    Offer(gap, board, 2, T0 + 10000);
    CHECK(Block(gap) == Expected(0, 0, false), "a new snapshot after a long silence is a gap");
}

// A new attempt starts a clean watch, whatever revision it begins at (a cohort's revisions never restart
// within a process, but the watch must not carry the old attempt's revision into the new one).
static void TestNewAttemptStartsClean()
{
    Blackboard const board = Active(55);
    ObservationStore store;
    Offer(store, board, 10, T0);
    Offer(store, board, 11, T0 + 100);
    ObservationAttempt const second{ 1, 2 };
    Blackboard next = board;
    next.CurrentScope.AttemptId = 2;
    Offer(store, next, 11, T0 + 200, second);  // the same revision number, a new attempt: observed, not a repeat
    Offer(store, next, 12, T0 + 300, second);
    CHECK(Block(store, second) == Expected(0, 0, true, second), "the new attempt's watch is clean");
    // ... and really observed: 46 s of activity in the new attempt is reported.
    Violations found;
    for (uint64 at = T0 + 400; at <= T0 + 200 + 46000; at += 100)
        Append(found, Offer(store, next, 13 + (at - T0 - 400) / 100, at, second));
    CHECK(OneActiveOverLimit(found), "observed from the new attempt's first snapshot");
    CHECK(Block(store, second) == Expected(1, 0, true, second), "complete");
}

// The export's observation times: the publication time (system ms) of the first and of the newest observed
// snapshot. The harness holds them against the boss window, so a snapshot that was not observed (a cached
// repeat, an out-of-order revision, revision 0) must never move them.
static void TestObservationTimes()
{
    Blackboard const board = Active(56);

    // Nothing observed yet: zeros, for a live attempt too.
    ObservationStore store;
    store.Begin("shard", Attempt1);
    std::string raw = store.JsonField("shard", Attempt1, EncounterNodeId);
    CHECK(TimeField(raw, "first_observed_at_ms") == 0 && TimeField(raw, "last_observed_at_ms") == 0,
        "no observation: no times");

    // One observation: first == last == its publication time.
    Offer(store, board, 1, T0 + 10000);
    raw = store.JsonField("shard", Attempt1, EncounterNodeId);
    CHECK(TimeField(raw, "first_observed_at_ms") == SystemOf(T0 + 10000)
        && TimeField(raw, "last_observed_at_ms") == SystemOf(T0 + 10000), "one snapshot: first and last");
    CHECK(Block(store) == Expected(0, 0, true), "and it is complete by its own gaps (the harness's edges decide)");

    // More snapshots move the last only; repeats, older and identity-less snapshots move nothing.
    Offer(store, board, 2, T0 + 10500);
    Offer(store, board, 3, T0 + 11000);
    Offer(store, board, 3, T0 + 11400);   // a cached repeat: not observed
    Offer(store, board, 2, T0 + 11500);   // out of order: not observed
    Offer(store, board, 0, T0 + 11800);   // no identity: not observed
    raw = store.JsonField("shard", Attempt1, EncounterNodeId);
    CHECK(TimeField(raw, "first_observed_at_ms") == SystemOf(T0 + 10000), "the first never moves");
    CHECK(TimeField(raw, "last_observed_at_ms") == SystemOf(T0 + 11000),
        "the last is the newest observed snapshot's publication, not a repeat's or a read's time");

    // Another attempt's record exports no times; a new attempt starts its own.
    ObservationAttempt const second{ 1, 2 };
    CHECK(TimeField(store.JsonField("shard", second, EncounterNodeId), "first_observed_at_ms") == 0,
        "a stale attempt exports none");
    Blackboard next = board;
    next.CurrentScope.AttemptId = 2;
    Offer(store, next, 4, T0 + 20000, second);
    raw = store.JsonField("shard", second, EncounterNodeId);
    CHECK(TimeField(raw, "first_observed_at_ms") == SystemOf(T0 + 20000)
        && TimeField(raw, "last_observed_at_ms") == SystemOf(T0 + 20000), "a new attempt starts its own times");

    // The stale-snapshot reproduction: a wall clock that went back holds one snapshot; the last observation
    // time stays at its publication however long the reporter keeps deciding.
    Scenario stepped;
    stepped.WorldAt = ActiveAlways;
    stepped.StepAt = T0 + 10000;
    stepped.StepMs = 40000;
    stepped.EndAt = T0 + 40000;
    Outcome const outcome = Run(stepped);
    uint64 const last = TimeField(outcome.FixedRaw, "last_observed_at_ms");
    CHECK(last >= SystemOf(T0 + 9500) && last <= SystemOf(T0 + 10000),
        "the newest observed snapshot is the one published before the step; 30 s of repeats add nothing");
    CHECK(TimeField(outcome.FixedRaw, "first_observed_at_ms") == SystemOf(T0), "first: the first publication");
}

int main()
{
    TestObservationTimes();
    TestBackwardStepFortyFiveSeconds();
    TestBackwardStepTenSeconds();
    TestShortReversalKeepsCoverage();
    TestFastDecisionsReadRepeats();
    TestRepeatBound();
    TestRevisionIdentity();
    TestNewAttemptStartsClean();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    else
        std::printf("ok\n");
    return failures ? 1 : 0;
}
'''


def test_snapshot_is_observed_once(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM).strip() == "ok"


def test_snapshot_is_observed_once_under_sanitizers(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM, sanitize=True).strip() == "ok"


def test_production_wiring_passes_the_snapshot_revision() -> None:
    candidates = CANDIDATES.read_text(encoding="utf-8")
    submit = candidates[candidates.index("void BotWorldPopulationMgr::SubmitAdaptiveNefarianCandidates("):]
    assert ("Observations().ObserveWarriors(cohortId, observationAttempt, board.CurrentScope,\n"
            "                view, { board.Revision, board.ObservedAtMs },\n"
            "                BotEncounter::Nefarian::ObservationClockMs(\n"
            "                    GameTime::GetGameTimeSteadyPoint()));") in submit
    store = STORE.read_text(encoding="utf-8")
    # The store feeds the watch through the snapshot-identity entry only.
    assert "record.Watch.ObserveSnapshot(\n            snapshot, view, observedAtMs);" in store
    assert "record.Watch.Observe(" not in store
    assert "SnapshotStamp snapshot, uint64 observedAtMs" in store
    watch = WATCH.read_text(encoding="utf-8")
    assert "std::vector<WarriorViolation> ObserveSnapshot(SnapshotStamp snapshot," in watch
    assert "if (!revision || (_haveRevision && revision < _revision))" in watch
    # The premise of the review: the publisher keeps a cached snapshot on its system-time throttle and
    # numbers every rebuild; the snapshot carries no steady publication time.
    publisher = BLACKBOARD_PUBLISHER.read_text(encoding="utf-8")
    assert "if (Cohort().EncounterSnapshot && nowMs < Cohort().EncounterSnapshotNextRefreshMs)\n        return;" in publisher
    assert "snapshot->Revision = ++Cohort().EncounterSnapshotRevision;" in publisher
    assert max(len(text.splitlines()) for text in (watch, store, candidates)) < 1000

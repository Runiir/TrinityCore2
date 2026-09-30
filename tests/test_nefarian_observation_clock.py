"""BWD 10N round 3, v2 review (Nefarian, P3): observation clock and reporter.

The v2 review reproduced, with production headers:
- a false "active over 45 s" violation with complete:true when the observation
  clock advanced 46 s after about one second of activity;
- the same when a gap hid a collapse and the following wake, joining two
  separate active spans;
and asked that the mixed-play reporter election (ReportsWarriorWatch) choose
among bots only, never a human published on the board.

The fix (BotNefarianWarriorWatch.h, BotNefarianObservationStore.h,
BotWorldPopulationMgrNefarianCandidates.cpp):
- the reporter's clock is the game tick's monotonic (steady) time
  (ObservationClockMs); the blackboard snapshot carries system time only;
- an observation more than WarriorObservationGapMs after the previous one (a
  stall or a forward jump) restarts every active span and marks the coverage
  incomplete; any backward step of the clock marks it incomplete too;
- the election skips every guid published as an external (human) player.

Each reproduction runs with its control, also under the sanitizers.
"""

from __future__ import annotations

from pathlib import Path

from tests.test_nefarian_strategy import PRELUDE, _compile_and_run

ROOT = Path(__file__).resolve().parents[1]
NEFARIAN = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian"
CANDIDATES = NEFARIAN / "BotWorldPopulationMgrNefarianCandidates.cpp"
WATCH = NEFARIAN / "BotNefarianWarriorWatch.h"
STORE = NEFARIAN / "BotNefarianObservationStore.h"


PROGRAM = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationStore.h"
#include <chrono>
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

// The reporter's steady cadence: an observation at `from`, `from + 1 s`, ... `to`.
static Violations Steps(WarriorWatch& watch, Blackboard const& board, uint64 from, uint64 to)
{
    Violations all;
    for (uint64 at = from; at <= to; at += 1000)
        Append(all, watch.Observe(ObserveEncounter(board), at));
    return all;
}

static bool OneActiveOverLimit(Violations const& found, uint64 activeMs)
{
    return found.size() == 1 && found[0].Kind == WarriorViolationKind::ActiveOverLimit
        && found[0].ActiveMs == activeMs;
}

// The clock of the reporter: a steady time point in milliseconds.
static void TestObservationClock()
{
    static_assert(std::chrono::steady_clock::is_steady, "the observation clock must be steady");
    using std::chrono::milliseconds;
    using std::chrono::steady_clock;
    CHECK(ObservationClockMs(steady_clock::time_point(milliseconds(12345))) == 12345u, "milliseconds");
    CHECK(ObservationClockMs(steady_clock::time_point(milliseconds(12345) + std::chrono::microseconds(999)))
        == 12345u, "truncated to whole milliseconds");
    uint64 const first = ObservationClockMs(steady_clock::now());
    uint64 const second = ObservationClockMs(steady_clock::now());
    CHECK(second >= first, "never goes back");
}

// P3: a clock that advances 46 s after about a second of activity is a gap,
// not 46 s of activity.
static void TestForwardJump()
{
    Blackboard const board = WarriorBoard({ Floor(50) });

    // Control: 46 s of continuous observation is a violation, on a whole watch.
    WarriorWatch control;
    Violations const controlFound = Steps(control, board, T0, T0 + 46000);
    CHECK(OneActiveOverLimit(controlFound, 46000), "control: 46 s of observed activity is reported");
    CHECK(!control.CoverageBroken(), "control: a steady cadence keeps the coverage whole");

    WarriorWatch watch;
    Violations found = Steps(watch, board, T0, T0 + 1000);
    CHECK(found.empty() && !watch.CoverageBroken(), "a second of activity");
    found = watch.Observe(ObserveEncounter(board), T0 + 47000);
    CHECK(found.empty(), "a 46 s jump is no 46 s of activity (v2 reproduction)");
    CHECK(watch.CoverageBroken(), "and the coverage is broken");

    // The span restarts at the first observation after the jump and is
    // judged from there, once.
    found = Steps(watch, board, T0 + 48000, T0 + 47000 + WarriorActiveLimitMs);
    CHECK(found.empty(), "45 s after the restart is still the limit");
    found = Steps(watch, board, T0 + 47000 + WarriorActiveLimitMs + 1000, T0 + 47000 + 60000);
    CHECK(OneActiveOverLimit(found, WarriorActiveLimitMs + 1000), "reported once, from the restarted span");
    CHECK(watch.CoverageBroken(), "the broken coverage stays broken");
}

// P3: a gap hiding a collapse and a wake must not join two active spans.
static void TestGapHidingCollapseAndWake()
{
    Blackboard const active = WarriorBoard({ Floor(51) });
    Blackboard const down = Collapsed(51);

    // Control: the same collapse, observed, ends the span without a gap.
    WarriorWatch control;
    Violations controlFound = Steps(control, active, T0, T0 + 1000);
    Append(controlFound, Steps(control, down, T0 + 2000, T0 + 5000));
    Append(controlFound, Steps(control, active, T0 + 6000, T0 + 46000));
    CHECK(controlFound.empty(), "control: an observed collapse resets the span");
    CHECK(!control.CoverageBroken(), "control: whole coverage");

    // Reproduction: the collapse and wake happen inside a 10 s silence.
    WarriorWatch watch;
    Violations found = Steps(watch, active, T0, T0 + 1000);
    Append(found, Steps(watch, active, T0 + 11000, T0 + 46000));
    CHECK(found.empty(), "two spans across a gap are not one 46 s span (v2 reproduction)");
    CHECK(watch.CoverageBroken(), "the coverage is broken");
    Append(found, Steps(watch, active, T0 + 47000, T0 + 11000 + WarriorActiveLimitMs));
    CHECK(found.empty(), "the second span is judged from its own start");
    Append(found, Steps(watch, active, T0 + 11000 + WarriorActiveLimitMs + 1000, T0 + 11000 + 50000));
    CHECK(OneActiveOverLimit(found, WarriorActiveLimitMs + 1000), "and reported once when it is over");
}

// The bound: exactly WarriorObservationGapMs is continuous, one millisecond
// more is a gap; any backward step breaks the coverage and skips the snapshot.
static void TestBounds()
{
    Blackboard const board = WarriorBoard({ Floor(52) });
    CHECK(WarriorObservationGapMs == 2000, "the bounded gap");

    WarriorWatch atBound;
    atBound.Observe(ObserveEncounter(board), T0);
    atBound.Observe(ObserveEncounter(board), T0 + WarriorObservationGapMs);
    CHECK(!atBound.CoverageBroken(), "an observation exactly at the bound is continuous");

    WarriorWatch pastBound;
    pastBound.Observe(ObserveEncounter(board), T0);
    pastBound.Observe(ObserveEncounter(board), T0 + WarriorObservationGapMs + 1);
    CHECK(pastBound.CoverageBroken(), "one millisecond past the bound is a gap");

    WarriorWatch first;
    first.Observe(ObserveEncounter(board), T0 + 1000000);
    CHECK(!first.CoverageBroken(), "the first observation has no predecessor: no gap");

    WarriorWatch back;
    Steps(back, board, T0, T0 + 5000);
    CHECK(back.Observe(ObserveEncounter(board), T0 + 5000 - 1).empty(), "an older observation reports nothing");
    CHECK(back.CoverageBroken(), "a step back of one millisecond breaks the coverage");
    CHECK(back.LatestMs() == T0 + 5000, "the watch's clock never goes back");
    Violations const found = Steps(back, board, T0 + 6000, T0 + 46000);
    CHECK(OneActiveOverLimit(found, 46000), "the skipped snapshot erased nothing: the span runs from first sight");

    // Reports are once per warrior and kind across a gap too.
    Blackboard const climber = WarriorBoard({ Climber(41) });
    WarriorWatch pillar;
    Violations onPillar = Steps(pillar, climber, T0, T0 + 1000);
    Append(onPillar, Steps(pillar, climber, T0 + 20000, T0 + 21000));
    CHECK(onPillar.size() == 1 && onPillar[0].Kind == WarriorViolationKind::OnPillar,
        "a pillar report is not repeated after a gap");
    CHECK(pillar.CoverageBroken(), "the gap is still marked");
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

// Every report is a newly published snapshot: the revision advances (the
// cached-snapshot repeats are replayed in tests/test_nefarian_observation_snapshots.py).
static uint64 NextRevision = 0;
static uint64 const SystemBase = 1790000000000ull;  // system ms of steady time 0

static Violations Report(ObservationStore& store, Blackboard const& board, uint64 at,
    ObservationAttempt attempt = Attempt1)
{
    store.Begin("shard", attempt);
    return store.ObserveWarriors("shard", attempt, board.CurrentScope, ObserveEncounter(board),
        { ++NextRevision, SystemBase + at }, at);
}

static void ReportSteps(ObservationStore& store, Blackboard const& board, uint64 from, uint64 to)
{
    for (uint64 at = from; at <= to; at += 1000)
        Report(store, board, at);
}

// The export: complete:false with no false violation.
static void TestExportedCoverage()
{
    Blackboard const board = WarriorBoard({ Floor(60) });

    ObservationStore control;
    ReportSteps(control, board, T0, T0 + 46000);
    CHECK(Block(control) == Expected(1, 0, true), "control: a real 46 s activity, complete");

    ObservationStore jump;
    ReportSteps(jump, board, T0, T0 + 1000);
    CHECK(Block(jump) == Expected(0, 0, true), "before the jump: whole");
    Report(jump, board, T0 + 47000);
    CHECK(Block(jump) == Expected(0, 0, false), "a 46 s jump: no violation, not complete (v2 reproduction)");

    ObservationStore gap;
    ReportSteps(gap, board, T0, T0 + 1000);
    ReportSteps(gap, board, T0 + 11000, T0 + 46000);
    CHECK(Block(gap) == Expected(0, 0, false), "a gap hiding a collapse and a wake: not complete");
    ReportSteps(gap, board, T0 + 47000, T0 + 200000);
    CHECK(Block(gap).find("\"complete\":false") != std::string::npos, "a broken coverage stays broken");

    ObservationStore bound;
    Report(bound, board, T0);
    Report(bound, board, T0 + WarriorObservationGapMs);
    CHECK(Block(bound) == Expected(0, 0, true), "exactly at the bound: complete");
    Report(bound, board, T0 + 2 * WarriorObservationGapMs + 1);
    CHECK(Block(bound) == Expected(0, 0, false), "one millisecond past it: not complete");

    ObservationStore back;
    Report(back, board, T0 + 1000);
    Report(back, board, T0 + 999);
    CHECK(Block(back) == Expected(0, 0, false), "a step back of one millisecond: not complete");

    // A new attempt starts a clean, complete watch.
    ObservationAttempt const attempt2{ 1, 2 };
    Blackboard second = board;
    second.CurrentScope.AttemptId = 2;
    Report(jump, second, T0 + 300000, attempt2);
    CHECK(Block(jump, attempt2) == Expected(0, 0, true, attempt2), "a new attempt is whole again");

    // A gap before the first observation is no gap (the watch starts there).
    ObservationStore late;
    late.Begin("shard", Attempt1);
    Report(late, board, T0 + 3600000);
    CHECK(Block(late) == Expected(0, 0, true), "the first observation starts the coverage");
}

static ActorSnapshot Human(uint32 counter, bool alive = true)
{
    ActorSnapshot human;
    human.Guid = ObjectGuid(HighGuid::Player, counter);
    human.Kind = ActorKind::Player;
    human.Role = "dps";
    human.Alive = alive;
    human.HealthPct = 100.0f;
    return human;
}

// The election as it was before the fix (BotWorldPopulationMgrNefarianCandidates.cpp
// at the v2 review): the lowest living guid of `Players`, whoever it is.
static bool LegacyReports(Blackboard const& board, ObjectGuid bot)
{
    ObjectGuid reporter;
    for (ActorSnapshot const& player : board.Players)
        if (player.Alive && (reporter.IsEmpty() || player.Guid.GetCounter() < reporter.GetCounter()))
            reporter = player.Guid;
    return reporter == bot;
}

static int Reporters(Blackboard const& board)
{
    int reporters = 0;
    for (uint32 slot = 1; slot <= 10; ++slot)
        reporters += ReportsWarriorWatch(board, Bot(slot)) ? 1 : 0;
    return reporters;
}

// Mixed play: humans are published in ExternalPlayers and never lead.
static void TestReporterElection()
{
    Blackboard board = CanonicalBoard();
    CHECK(Reporters(board) == 1 && ReportsWarriorWatch(board, Bot(1)),
        "a bots-only cohort elects its lowest guid, once");

    // Humans with lower guids than every bot, published as external players.
    board.ExternalPlayers = { Human(900), Human(901) };
    CHECK(Reporters(board) == 1 && ReportsWarriorWatch(board, Bot(1)),
        "external humans do not change the election");
    CHECK(!ReportsWarriorWatch(board, Human(900).Guid) && !ReportsWarriorWatch(board, Human(901).Guid),
        "a human is never the reporter");

    // Defence: a human guid that also shows up in `Players` (the list the
    // election reads) is still not a candidate. The election before the fix
    // chose it.
    board.Players.insert(board.Players.begin(), Human(900));
    CHECK(LegacyReports(board, Human(900).Guid), "the election before the fix chose the human (v2 concern)");
    CHECK(!ReportsWarriorWatch(board, Human(900).Guid), "the human is skipped");
    CHECK(Reporters(board) == 1 && ReportsWarriorWatch(board, Bot(1)), "the lowest bot leads");

    // The lowest bot dies: the next bot leads, never a human.
    FindPlayer(board, 1).Alive = false;
    CHECK(Reporters(board) == 1 && ReportsWarriorWatch(board, Bot(2)), "the next living bot leads");

    // Every bot dead: nobody reports; a living human does not take over.
    for (ActorSnapshot& player : board.Players)
        player.Alive = false;
    board.Players.front().Alive = true;  // the mirrored human
    CHECK(Reporters(board) == 0 && !ReportsWarriorWatch(board, Human(900).Guid),
        "no living bot: no reporter");

    Blackboard humansOnly;
    humansOnly.ExternalPlayers = { Human(900), Human(901) };
    CHECK(!ReportsWarriorWatch(humansOnly, Human(900).Guid) && !ReportsWarriorWatch(humansOnly, Bot(1)),
        "no bots on the board: no reporter");
}

int main()
{
    TestObservationClock();
    TestForwardJump();
    TestGapHidingCollapseAndWake();
    TestBounds();
    TestExportedCoverage();
    TestReporterElection();
    if (failures)
        std::fprintf(stderr, "%d failure(s)\n", failures);
    else
        std::printf("ok\n");
    return failures ? 1 : 0;
}
'''


def test_observation_clock_gaps_and_reporter_election(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM).strip() == "ok"


def test_observation_clock_gaps_and_reporter_election_under_sanitizers(tmp_path: Path) -> None:
    assert _compile_and_run(tmp_path, PROGRAM, sanitize=True).strip() == "ok"


def test_production_wiring_uses_the_monotonic_clock_and_the_header_election() -> None:
    candidates = CANDIDATES.read_text(encoding="utf-8")
    # The snapshot carries system time only; the reporter feeds the game
    # tick's steady clock (nothing is plumbed through the blackboard).
    assert '#include "GameTime.h"' in candidates
    assert ("Observations().ObserveWarriors(cohortId, observationAttempt, board.CurrentScope,\n"
            "                view, { board.Revision, board.ObservedAtMs },\n"
            "                BotEncounter::Nefarian::ObservationClockMs(\n"
            "                    GameTime::GetGameTimeSteadyPoint()));") in candidates
    submit = candidates[candidates.index("void BotWorldPopulationMgr::SubmitAdaptiveNefarianCandidates("):]
    # The snapshot's system time goes in only as its publication stamp (the export's first and last
    # observation times, in the combat log's clock), never as the spans' clock.
    assert submit.count("board.ObservedAtMs") == 1 and "{ board.Revision, board.ObservedAtMs }" in submit
    # One election, in the header: the cpp only uses it.
    assert "using BotEncounter::Nefarian::ReportsWarriorWatch;" in candidates
    assert "bool ReportsWarriorWatch(" not in candidates
    assert "ReportsWarriorWatch(*Cohort().EncounterSnapshot, context.Bot->GetGUID())" in candidates
    watch = WATCH.read_text(encoding="utf-8")
    election = watch[watch.index("inline bool ReportsWarriorWatch("):watch.index("class WarriorWatch")]
    assert "board.ExternalPlayers" in election and "board.Players" in election
    # The store takes its completeness from the watch (no clock rule of its own).
    store = STORE.read_text(encoding="utf-8")
    assert "if (record.Watch.CoverageBroken())\n            record.CoverageLost = true;" in store
    assert "WarriorForgetMs" not in store
    assert max(len(text.splitlines()) for text in (watch, store, candidates)) < 1000

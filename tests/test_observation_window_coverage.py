"""BWD 10N round 3, v4 review: the server's observer must have observed the boss window, not just been read after it.

The review reproduced: an observation store stays `complete` after any first sample until a later sample
detects a gap, and the run harness (tools/raid_program/run_sanity_inputs.py) accepted a late final-status read
time as if it proved observation up to the window's end. One sample at 10,000, a final status read at 200,000 and
a boss window [10000, 200000] gave zero violations with complete=true.

The fix, in both stores (BotNefarianObservationStore.h, BotAtramedesObservationStore.h and their counters) and
the harness:
- the export carries first_observed_at_ms and last_observed_at_ms: the publication times (system ms, the combat
  log's clock) of the first and the newest snapshot the observer took in the attempt;
- the harness requires first <= window start + bound and last >= window end - bound (the observer's own gap
  bound: 2,000 ms for Nefarian's watch, 5,000 ms for Atramedes' ground sampling) on top of the observer's own
  no-internal-gap `complete`; otherwise the result is incomplete, which blocks. The status read time is never
  promoted to an observation time.

Also here: a correctly covered legitimate kill passes (the positive control), the bounds are exact, the harness
bounds equal the C++ constants, and the real stores' exports are replayed through the harness.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_atramedes_observation_scope import _compile_and_run as _compile_atramedes
from tests.test_atramedes_sanity_observation import _block as _atramedes_block, _status as _atramedes_status
from tests.test_nefarian_observation_counters import _block, _status, _status_run
from tests.test_nefarian_strategy import PRELUDE, _compile_and_run as _compile_nefarian
from tests.test_run_sanity import CAPTURE, NODE, ROOT, WINDOW_END, WINDOW_START, _observation_findings
from tools.raid_program.run_sanity_inputs import (
    ATRAMEDES_OBSERVATION_BOUND_MS, NEFARIAN_OBSERVATION_BOUND_MS, BossWindow, atramedes_inputs,
    observation_window_coverage, sanity_inputs, status_observations,
)

ENCOUNTERS = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters"
ATRAMEDES_TARGET = {"encounter_route_node_id": NODE, "scenario": "blackwing_descent_10n_atramedes"}
REVIEW_WINDOW = {"first_at_ms": 10_000, "last_at_ms": 200_000}  # the reviewer's boss window


def _boss(window=REVIEW_WINDOW) -> BossWindow:
    return BossWindow(window, NODE, CAPTURE)


# --- the reviewer's reproduction ------------------------------------------------------------------------------

def test_one_early_sample_and_a_late_final_status_do_not_prove_the_window(tmp_path):
    # One sample at 10,000 (first == last), a final status read at 200,000, the window [10000, 200000].
    report = _status(_block(first=10_000, last=10_000), now_ms=200_000)
    observations, server = status_observations(tmp_path, report, _boss())
    assert observations is None
    assert server["states"] == {"report.json": "observation_ended_before_window"}
    assert server["complete"] is False and server["window_end_ms"] == 200_000


def test_the_same_block_reaching_the_window_end_is_complete_the_positive_control(tmp_path):
    report = _status(_block(first=10_000, last=199_900), now_ms=200_000)
    observations, server = status_observations(tmp_path, report, _boss())
    assert observations is not None and observations["bone_warrior_active_over_45s"] == 0
    assert server["complete"] is True and server["states"] == {"report.json": "complete"}
    assert (server["first_observed_at_ms"], server["last_observed_at_ms"]) == (10_000, 199_900)


def test_a_later_read_time_never_stands_in_for_the_observation_time(tmp_path):
    for read_at in (200_000, 200_001, 400_000, 10 ** 9):
        observations, server = status_observations(tmp_path, _status(_block(first=10_000, last=10_000), now_ms=read_at),
                                                   _boss())
        assert observations is None, read_at
        assert server["states"]["report.json"] == "observation_ended_before_window", read_at


# --- the bounds are exact and symmetric -----------------------------------------------------------------------------

@pytest.mark.parametrize("first, last, expected", [
    (10_000, 200_000, None),                                                  # the exact edges
    (10_000 + NEFARIAN_OBSERVATION_BOUND_MS, 200_000, None),                  # first exactly at start + bound
    (10_000 + NEFARIAN_OBSERVATION_BOUND_MS + 1, 200_000, "observation_started_after_window"),
    (10_000, 200_000 - NEFARIAN_OBSERVATION_BOUND_MS, None),                  # last exactly at end - bound
    (10_000, 200_000 - NEFARIAN_OBSERVATION_BOUND_MS - 1, "observation_ended_before_window"),
    (1, 10 ** 12, None),                                                      # an observer that ran far beyond it
    (0, 200_000, "observation_time_missing"),                                 # an observer that took nothing
    (10_000, 0, "observation_time_missing"),
    (None, 200_000, "observation_time_missing"),                              # an older build's block
    (10_000, None, "observation_time_missing"),
    ("10000", 200_000, "observation_time_missing"),
    (10_000, True, "observation_time_missing"),
    (-5, 200_000, "observation_time_missing"),
    (200_000, 10_000, "observation_time_missing"),                            # last before first: not a real observer
])
def test_observation_window_coverage_bounds(first, last, expected):
    block = {}
    if first is not None:
        block["first_observed_at_ms"] = first
    if last is not None:
        block["last_observed_at_ms"] = last
    assert observation_window_coverage(block, _boss(), NEFARIAN_OBSERVATION_BOUND_MS) == expected


def test_a_block_without_observation_times_is_refused_not_promoted(tmp_path):
    for report in (_status(_block(first=None, last=None)), _status(_block(first=None)), _status(_block(last=None))):
        observations, server = status_observations(tmp_path, report, _boss({"first_at_ms": WINDOW_START,
                                                                            "last_at_ms": WINDOW_END}))
        assert observations is None
        assert server["states"] == {"report.json": "observation_time_missing"}


def test_a_wrong_window_edge_is_named(tmp_path):
    window = {"first_at_ms": WINDOW_START, "last_at_ms": WINDOW_END}
    late_start = _status(_block(first=WINDOW_START + NEFARIAN_OBSERVATION_BOUND_MS + 1))
    early_end = _status(_block(last=WINDOW_END - NEFARIAN_OBSERVATION_BOUND_MS - 1))
    assert status_observations(tmp_path, late_start, _boss(window))[1]["states"] == {
        "report.json": "observation_started_after_window"}
    assert status_observations(tmp_path, early_end, _boss(window))[1]["states"] == {
        "report.json": "observation_ended_before_window"}


# --- through the record and the sanity check -----------------------------------------------------------------------

def _findings(tmp_path: Path, report: dict) -> list[dict]:
    run = _status_run(tmp_path, "run", report=report)
    return _observation_findings(tmp_path, run)


def test_the_unproven_window_is_a_blocking_finding_and_the_trace_cannot_vouch(tmp_path):
    report = _status(_block(first=WINDOW_START, last=WINDOW_START + 500), now_ms=WINDOW_END + 50_000)
    run = _status_run(tmp_path, "run", report=report)
    result = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": "blackwing_descent_10n_nefarian"}, ROOT)
    trace = result["decision_trace"]
    assert trace["complete"] is False
    assert trace["incomplete_reason"] == "native_counters_observation_ended_before_window"
    assert trace["server_counters"]["states"] == {"report.json": "observation_ended_before_window"}
    (row,) = _observation_findings(tmp_path, run)
    assert row["severity"] == "blocking" and row["evidence"]["status"] == "unproven"
    assert "last observed before the boss window ended" in row["detail"]
    assert "read time cannot" not in row["detail"]  # the missing-times message is another state's


def test_a_correctly_covered_kill_still_passes(tmp_path):
    report = _status(_block(first=WINDOW_START - 1_000, last=WINDOW_END + 1_000), now_ms=WINDOW_END + 50_000)
    assert _findings(tmp_path, report) == []
    edges = _status(_block(first=WINDOW_START + NEFARIAN_OBSERVATION_BOUND_MS,
                           last=WINDOW_END - NEFARIAN_OBSERVATION_BOUND_MS), now_ms=WINDOW_END + 50_000)
    assert _findings(tmp_path / "edges", edges) == []


def test_a_violation_block_that_missed_the_window_still_blocks(tmp_path):
    # A refused block gives no counts (no retained trace here): unproven, blocking, never a pass.
    report = _status(_block(active=2, first=WINDOW_START, last=WINDOW_START + 500))
    run = _status_run(tmp_path, "run", report=report)
    assert {row["severity"] for row in _observation_findings(tmp_path, run)} == {"blocking"}


# --- Atramedes: the same rule, counts kept as evidence ---------------------------------------------------------------

def test_the_reviewers_scenario_for_atramedes(tmp_path):
    early = _atramedes_status(_atramedes_block(first=10_000, last=10_000), now_ms=200_000)
    observations, server = atramedes_inputs(tmp_path, early, _boss())
    assert observations is not None and observations["complete"] is False  # the counts stay evidence, not coverage
    assert server["states"] == {"report.json": "observation_ended_before_window"} and server["complete"] is False
    late_start = _atramedes_status(_atramedes_block(first=10_000 + ATRAMEDES_OBSERVATION_BOUND_MS + 1, last=200_000),
                                   now_ms=200_000)
    assert atramedes_inputs(tmp_path, late_start, _boss())[1]["states"] == {
        "report.json": "observation_started_after_window"}
    missing = _atramedes_status(_atramedes_block(first=None, last=None), now_ms=200_000)
    observations, server = atramedes_inputs(tmp_path, missing, _boss())
    assert server["states"] == {"report.json": "observation_time_missing"} and observations["complete"] is False


def test_the_covered_atramedes_kill_is_complete_the_positive_control(tmp_path):
    for first, last in ((10_000, 199_900), (10_000 + ATRAMEDES_OBSERVATION_BOUND_MS, 200_000),
                        (10_000, 200_000 - ATRAMEDES_OBSERVATION_BOUND_MS)):
        observations, server = atramedes_inputs(
            tmp_path, _atramedes_status(_atramedes_block(first=first, last=last), now_ms=200_000), _boss())
        assert observations is not None and observations["complete"] is True, (first, last)
        assert server["states"] == {"report.json": "complete"} and server["complete"] is True
        assert (server["first_observed_at_ms"], server["last_observed_at_ms"]) == (first, last)
    assert atramedes_inputs(
        tmp_path, _atramedes_status(_atramedes_block(first=10_000, last=200_000 - ATRAMEDES_OBSERVATION_BOUND_MS - 1),
                                    now_ms=200_000), _boss())[1]["states"] == {
        "report.json": "observation_ended_before_window"}


def _atramedes_findings(tmp_path: Path, report: dict) -> list[dict]:
    from tests.test_atramedes_sanity_observation import _run
    run = _run(tmp_path, "run", report=report)
    root_inputs = sanity_inputs(run, ATRAMEDES_TARGET, ROOT)
    from tests.test_atramedes_sanity_observation import _findings
    return _findings(tmp_path, root_inputs)


def test_an_atramedes_sampling_that_missed_the_window_blocks_and_a_covered_one_passes(tmp_path):
    early = _atramedes_status(_atramedes_block(first=WINDOW_START, last=WINDOW_START + 500))
    (row,) = _atramedes_findings(tmp_path / "early", early)
    assert row["severity"] == "blocking" and row["evidence"]["status"] == "unproven"
    assert row["evidence"]["reason"] == "incomplete"
    assert row["evidence"]["server_counter_states"] == {"report.json": "observation_ended_before_window"}
    assert "did not span the boss window" in row["detail"]
    assert _atramedes_findings(tmp_path / "covered", _atramedes_status(_atramedes_block())) == []
    # A count above the bound is still a violation, whatever the coverage.
    loud = _atramedes_status(_atramedes_block(first=WINDOW_START, last=WINDOW_START + 500,
                                              **{"samples_above_10": 2, "max_kiter_sound": 16}))
    (row,) = _atramedes_findings(tmp_path / "loud", loud)
    assert row["severity"] == "blocking" and row["evidence"]["samples_above_10"] == 2


# --- the harness bounds are the C++ gap bounds --------------------------------------------------------------------------

def test_harness_bounds_equal_the_observers_gap_bounds():
    watch = (ENCOUNTERS / "Nefarian/BotNefarianWarriorWatch.h").read_text(encoding="utf-8")
    store = (ENCOUNTERS / "Atramedes/BotAtramedesObservationStore.h").read_text(encoding="utf-8")
    nefarian = re.search(r"constexpr uint64 WarriorObservationGapMs = (\d+);", watch)
    atramedes = re.search(r"inline constexpr uint64 MaxGroundGapMs = (\d+);", store)
    assert nefarian and atramedes
    assert int(nefarian.group(1)) == NEFARIAN_OBSERVATION_BOUND_MS
    assert int(atramedes.group(1)) == ATRAMEDES_OBSERVATION_BOUND_MS


# --- the real stores' exports through the harness ---------------------------------------------------------------------

NEFARIAN_EXPORT = PRELUDE + r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationStore.h"

// Prints, one per line, the store's export for: one sample at system 10,000 and nothing after; an observer that
// took a snapshot every 100 ms across [10,000, 200,000] system ms.
static std::string Run(uint64 firstMs, uint64 lastMs, uint64 stepMs)
{
    ObservationStore store;
    ObservationAttempt const attempt{ 3, 7 };
    Blackboard board = CanonicalBoard();
    board.CurrentScope.CohortId = "shard-nefarian";
    board.CurrentScope.AttemptId = 7;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = 7;
    store.Begin("shard-nefarian", attempt);
    uint64 revision = 0;
    for (uint64 at = firstMs; at <= lastMs; at += stepMs)
        store.ObserveWarriors("shard-nefarian", attempt, board.CurrentScope, ObserveEncounter(board),
            { ++revision, at }, 5000000ull + (at - firstMs));   // the steady clock runs with the system clock
    return store.JsonField("shard-nefarian", attempt, EncounterNodeId);
}

int main()
{
    std::printf("%s\n", Run(10000, 10000, 100).c_str());
    std::printf("%s\n", Run(10000, 200000, 100).c_str());
    return 0;
}
'''

ATRAMEDES_EXPORT = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Atramedes/BotAtramedesObservationStore.h"
#include <cstdio>
#include <string>

using namespace BotEncounter;
using namespace BotEncounter::Atramedes;

static Blackboard Board()
{
    Blackboard board;
    board.Route.NodeId = std::string(EncounterNode);
    board.CurrentScope.CohortId = "shard-nefarian";
    board.CurrentScope.AttemptId = 7;
    board.CurrentScope.MapId = 669;
    board.CurrentScope.InstanceId = 7;
    ActorSnapshot boss;
    boss.Guid = ObjectGuid(HighGuid::Unit, BossEntry, 1u);
    boss.Entry = BossEntry;
    boss.Kind = ActorKind::Summon;
    boss.Alive = true;
    boss.InCombat = true;
    boss.ReactAggressive = true;
    board.Summons.push_back(boss);
    ActorSnapshot player;
    player.Guid = ObjectGuid(HighGuid::Player, 1u);
    player.Kind = ActorKind::Player;
    player.Alive = true;
    player.MaxAlternatePower = 100;
    board.Players.push_back(player);
    return board;
}

static std::string Run(uint64 firstMs, uint64 lastMs, uint64 stepMs)
{
    ObservationStore store;
    ObservationAttempt const attempt{ 3, 7 };
    Blackboard board = Board();
    store.Begin("shard-nefarian", attempt);
    for (uint64 at = firstMs; at <= lastMs; at += stepMs)
    {
        board.ObservedAtMs = at;
        store.Observe("shard-nefarian", attempt, board);
    }
    return store.JsonField("", "shard-nefarian", attempt, EncounterNode);
}

int main()
{
    std::printf("%s\n", Run(10000, 10000, 250).c_str());
    std::printf("%s\n", Run(10000, 200000, 250).c_str());
    return 0;
}
'''


def _exports(compile_and_run, tmp_path: Path, program: str, encounter: str) -> tuple[dict, dict]:
    lines = compile_and_run(tmp_path, program).strip().splitlines()
    assert len(lines) == 2
    one, across = (json.loads("{" + line[1:] + "}")["encounter_observations"][encounter] for line in lines)
    return one, across


def test_the_real_nefarian_store_export_one_sample_versus_continuous_observation(tmp_path):
    one, across = _exports(_compile_nefarian, tmp_path, NEFARIAN_EXPORT, "nefarian")
    # The reviewer's state: complete by its own gaps, observed at exactly one instant.
    assert one["complete"] is True and one["first_observed_at_ms"] == one["last_observed_at_ms"] == 10_000
    assert across["complete"] is True
    assert (across["first_observed_at_ms"], across["last_observed_at_ms"]) == (10_000, 200_000)
    # The harness refuses the first for a window to 200,000 read late, and accepts the second.
    observations, server = status_observations(tmp_path, _status(one, now_ms=200_000), _boss())
    assert observations is None and server["states"] == {"report.json": "observation_ended_before_window"}
    observations, server = status_observations(tmp_path, _status(across, now_ms=200_000), _boss())
    assert observations is not None and server["complete"] is True


def test_the_real_atramedes_store_export_one_sample_versus_continuous_sampling(tmp_path):
    one, across = _exports(_compile_atramedes, tmp_path, ATRAMEDES_EXPORT, "atramedes")
    assert one["complete"] is True and one["first_observed_at_ms"] == one["last_observed_at_ms"] == 10_000
    assert across["complete"] is True
    assert (across["first_observed_at_ms"], across["last_observed_at_ms"]) == (10_000, 200_000)
    observations, server = atramedes_inputs(tmp_path, _atramedes_status(one, now_ms=200_000), _boss())
    assert observations["complete"] is False and server["states"] == {
        "report.json": "observation_ended_before_window"}
    observations, server = atramedes_inputs(tmp_path, _atramedes_status(across, now_ms=200_000), _boss())
    assert observations["complete"] is True and server["complete"] is True


def test_the_real_nefarian_store_export_under_sanitizers(tmp_path):
    from tests.test_nefarian_strategy import _compile_and_run

    lines = _compile_and_run(tmp_path, NEFARIAN_EXPORT, sanitize=True).strip().splitlines()
    assert len(lines) == 2 and all('"first_observed_at_ms"' in line for line in lines)

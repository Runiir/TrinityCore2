"""BWD 10N round 3 (Nefarian): server-side acceptance-observation counters.

The strategy writes nefarian_bone_warrior_active_over_45s / _on_pillar and
nefarian_move_refused:<mechanic>:<reason> to the decision trace, but a normal
shard kill retains no full trace (heartbeats read the newest rows per bot; the
terminal drain runs only on a failure), so acceptance_observation was not
evaluable. The server now keeps per-cohort, per-attempt counters
(BotNefarianObservationCounters.h) and exports them in `.botauto status` as
raid_runtime.encounter_observations.nefarian with complete: true; the harness
(run_sanity_inputs.nefarian_inputs) prefers the final status's complete block of the judged capture (its
cohort, server, attempt and combat-log lifecycle, read after the boss window closed). The trace scan stands in
only for a server that exported no counters at all (a status whose keys lack the block: never over an explicit
`complete: false`, a present but null or non-object block or container, or any other unusable export), and then
only with rows that name the judged capture (each entry's cohort, server epoch and attempt); everything else is
an unproven (blocking) finding.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

from tests.test_run_sanity import (BONE_ACTIVE, CAPTURE, NODE, REFUSED, TARGET, WINDOW_END, WINDOW_START,
                                   _observation_findings, _trace, _trace_run, write_run, _hit)
from tools.raid_program.run_sanity_inputs import parse_status_observations, sanity_inputs

ROOT = Path(__file__).resolve().parents[1]
BOTS = ROOT / "src/server/game/Bots"
NEFARIAN = BOTS / "Content/Raids/BlackwingDescent/Encounters/Nefarian"
COUNTERS = NEFARIAN / "BotNefarianObservationCounters.h"
EXPORT = NEFARIAN / "BotNefarianObservationExport.h"
STORE = NEFARIAN / "BotNefarianObservationStore.h"
WATCH = NEFARIAN / "BotNefarianWarriorWatch.h"
CANDIDATES = NEFARIAN / "BotWorldPopulationMgrNefarianCandidates.cpp"
RAID_RUNTIME = BOTS / "BotWorldPopulationMgrRaidRuntime.cpp"
STATUS = BOTS / "BotWorldPopulationMgrStatus.cpp"
ACTIVE, PILLAR = "bone_warrior_active_over_45s", "bone_warrior_on_pillar"


def _run(tmp_path: Path, program: str) -> str:
    source, binary = tmp_path / "program.cpp", tmp_path / "program"
    source.write_text(program)
    command = ["g++", "-std=c++17", "-Wall", "-Wextra", "-Werror", "-I", str(ROOT / "src/server/game")]
    subprocess.run(command + [str(source), "-o", str(binary)], check=True, cwd=ROOT)
    result = subprocess.run([str(binary)], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout[-3000:] + result.stderr[-3000:]
    return result.stdout


PROGRAM = r'''
#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationCounters.h"
#include <cstdio>
#include <string>

static int failures = 0;
#define CHECK(condition, message) do { if (!(condition)) { \
    std::fprintf(stderr, "FAIL line %d: %s\n", __LINE__, message); ++failures; } } while (0)

using namespace BotEncounter::Nefarian;

int main()
{
    ObservationCounters counters;
    // Before any attempt: nothing is live, nothing records, the export says so.
    CHECK(!counters.LiveFor(1), "no attempt yet");
    counters.RecordWarrior(1, ObservedWarriorKind::OnPillar, 77);
    counters.RecordRefused(1, 5, "hop:native_no_path");
    CHECK(counters.OnPillar() == 0 && counters.Refused(5, "hop:native_no_path") == 0,
        "records before Begin are dropped");
    CHECK(counters.Json(1, 9) == "{\"bone_warrior_active_over_45s\":0,\"bone_warrior_on_pillar\":0,"
        "\"move_refused\":{},\"complete\":false,\"attempt_id\":1,\"combat_log_epoch\":9,\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}",
        "incomplete before Begin");
    CHECK(!counters.Begin(0), "attempt 0 is never an attempt");
    CHECK(!counters.LiveFor(0), "attempt 0 is never live");

    // Attempt 3: distinct warriors per kind, every refusal counted.
    CHECK(counters.Begin(3) && counters.LiveFor(3), "attempt 3 live");
    counters.RecordWarrior(3, ObservedWarriorKind::ActiveOverLimit, 100);
    counters.RecordWarrior(3, ObservedWarriorKind::ActiveOverLimit, 100); // re-flagged after a new wake
    counters.RecordWarrior(3, ObservedWarriorKind::ActiveOverLimit, 101);
    counters.RecordWarrior(3, ObservedWarriorKind::OnPillar, 100);
    counters.RecordWarrior(3, ObservedWarriorKind::OnPillar, 0);          // no guid: ignored
    CHECK(counters.ActiveOverLimit() == 2, "two distinct warriors over 45 s");
    CHECK(counters.OnPillar() == 1, "one warrior on a pillar");
    counters.RecordRefused(3, 11, "hop:native_no_path");
    counters.RecordRefused(3, 11, "hop:native_no_path");
    counters.RecordRefused(3, 11, "ledge_drop:say \"no\"");
    counters.RecordRefused(3, 12, "hop:stunned");
    counters.RecordRefused(3, 0, "hop:stunned");                            // no actor: ignored
    counters.RecordRefused(2, 12, "hop:stunned");                           // another attempt: ignored
    CHECK(counters.Refused(11, "hop:native_no_path") == 2, "refusals are not coalesced");
    CHECK(counters.Refused(12, "hop:stunned") == 1, "per actor and per mechanic:reason");
    CHECK(!counters.Begin(3) || counters.ActiveOverLimit() == 2, "Begin of the same attempt keeps the counts");
    std::string const json = counters.Json(3, 9);
    CHECK(json == "{\"bone_warrior_active_over_45s\":2,\"bone_warrior_on_pillar\":1,\"move_refused\":{"
        "\"11\":{\"hop:native_no_path\":2,\"ledge_drop:say \\\"no\\\"\":1},\"12\":{\"hop:stunned\":1}},"
        "\"complete\":true,\"attempt_id\":3,\"combat_log_epoch\":9,\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}", json.c_str());
    // A status read for another attempt never reports this attempt's counts.
    CHECK(counters.Json(4, 9).find("\"complete\":false") != std::string::npos, "stale attempt is incomplete");
    CHECK(counters.Json(4, 9).find("\"move_refused\":{}") != std::string::npos, "stale attempt exports zeros");
    CHECK(counters.Json(3, 10).find("\"combat_log_epoch\":10,") != std::string::npos,
        "the block carries the start lifecycle it was asked for");
    // The observer's first and newest observation times (system ms, the combat log's clock) are exported for
    // the live attempt only, after the lifecycle: the harness holds them against the boss window.
    CHECK(counters.Json(3, 9, true, 1790000010000ull, 1790000250000ull).find(
        "\"combat_log_epoch\":9,\"first_observed_at_ms\":1790000010000,"
        "\"last_observed_at_ms\":1790000250000}") != std::string::npos, "the observation times are exported");
    CHECK(counters.Json(4, 9, true, 1790000010000ull, 1790000250000ull).find(
        "\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}") != std::string::npos,
        "a stale attempt exports no observation times");
    CHECK(counters.Json(3, 9, false, 1790000010000ull, 1790000250000ull).find(
        "\"complete\":false") != std::string::npos, "an uncovered attempt keeps its times and is not complete");

    // A new attempt resets every counter.
    CHECK(counters.Begin(4) && counters.LiveFor(4) && !counters.LiveFor(3), "attempt 4 replaces 3");
    CHECK(counters.ActiveOverLimit() == 0 && counters.OnPillar() == 0, "warriors reset");
    CHECK(counters.Refused(11, "hop:native_no_path") == 0, "refusals reset");
    CHECK(counters.Json(4, 9) == "{\"bone_warrior_active_over_45s\":0,\"bone_warrior_on_pillar\":0,"
        "\"move_refused\":{},\"complete\":true,\"attempt_id\":4,\"combat_log_epoch\":9,\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}", "a complete zero");
    counters.RecordWarrior(3, ObservedWarriorKind::OnPillar, 200);          // late write of attempt 3
    CHECK(counters.OnPillar() == 0, "an old attempt never writes into the new one");
    // A live attempt its watch did not cover keeps its counts, never complete.
    counters.RecordWarrior(4, ObservedWarriorKind::OnPillar, 300);
    CHECK(counters.Json(4, 9, false) == "{\"bone_warrior_active_over_45s\":0,\"bone_warrior_on_pillar\":1,"
        "\"move_refused\":{},\"complete\":false,\"attempt_id\":4,\"combat_log_epoch\":9,\"first_observed_at_ms\":0,\"last_observed_at_ms\":0}",
        "an uncovered attempt is incomplete");
    CHECK(counters.Json(3, 9, false).find("\"bone_warrior_on_pillar\":0") != std::string::npos,
        "a stale attempt stays zero");
    CHECK(ObservationCounters::Escape(std::string("a\\b\n")) == "a\\\\b\\u000a", "escaping");

    if (failures)
        return 1;
    std::printf("ok\n");
    return 0;
}
'''


def test_counter_and_reset_logic(tmp_path):
    assert _run(tmp_path, PROGRAM).strip() == "ok"


def _body(text: str, signature: str) -> str:
    body = text[text.index(signature):]
    return body[:body.index("\n}\n")]


def test_the_status_export_is_wired_and_scoped_to_nefarian():
    runtime = RAID_RUNTIME.read_text()
    assert '#include "Bots/Content/Raids/BlackwingDescent/Encounters/Nefarian/BotNefarianObservationExport.h"' in runtime
    full = _body(runtime, "std::string BotWorldPopulationMgr::BuildRaidRuntimeJson(bool compactTelemetry) const")
    tail = full[full.rindex("AppendRaidPrepullConsumablesJson(json);"):]
    # The attempt is the cohort's start lifecycle and attempt id: `.botexp
    # start` keeps the attempt id, but every start advances CombatLogEpoch.
    assert ("EncounterObservationsJsonField(Cohort().Id,\n"
            "        { Cohort().CombatLogEpoch, Cohort().AttemptId }, Cohort().Config.ValidationRouteNodeId)") in tail
    # `.botauto status` builds the full (non-compact) raid runtime.
    assert '<< ",\\"raid_runtime\\":" << BuildRaidRuntimeJson()' in _body(
        STATUS.read_text(), "std::string BotWorldPopulationMgr::GetStatusJson() const")
    candidates = CANDIDATES.read_text()
    # One store per process (BotNefarianObservationStore.h): no process-wide
    # watch, no counters outside it.
    assert "SharedWarriorWatch" not in candidates and "std::map<std::string" not in candidates
    assert "static BotEncounter::Nefarian::ObservationStore store;" in candidates
    field = _body(candidates, "std::string BotEncounter::Nefarian::EncounterObservationsJsonField(")
    assert "return Observations().JsonField(cohortId, attempt, routeNodeId);" in field
    # Other cohorts (Magmaw b5, Stonecore, calibration) export nothing new;
    # a stale record only on Nefarian's route, as a fresh process
    # (tests/test_nefarian_observation_scope.py replays it).
    json_field = _body(STORE.read_text(), "    std::string JsonField(")
    assert "bool const current = found != _cohorts.end() && found->second.Attempt == attempt;" in json_field
    assert "if (!current && routeNodeId != EncounterNodeId)\n            return std::string();" in json_field
    # The start lifecycle (combat_log_epoch) is exported in both branches: the run harness binds the
    # counters to the judged capture's (cohort, server epoch, attempt, lifecycle).
    assert ("(current ? found->second.Counters.Json(attempt.AttemptId, attempt.Lifecycle,\n"
            "                    found->second.Covered(), found->second.Watch.FirstPublishedAtMs(),\n"
            "                    found->second.Watch.LastPublishedAtMs())\n"
            "                : ObservationCounters().Json(attempt.AttemptId, attempt.Lifecycle)) + \"}\";") in json_field
    assert '\\"combat_log_epoch\\":' in COUNTERS.read_text()
    assert '",\\"encounter_observations\\":{\\"nefarian\\":"' in json_field
    submit = _body(candidates, "void BotWorldPopulationMgr::SubmitAdaptiveNefarianCandidates(BotUpdateContext& context)")
    assert ("BotEncounter::Nefarian::ObservationAttempt const observationAttempt{\n"
            "        Cohort().CombatLogEpoch, Cohort().AttemptId };") in submit
    assert "if (context.AdaptiveNefarianOwnsNode)\n        Observations().Begin(cohortId, observationAttempt);" in submit
    assert ("Observations().ObserveWarriors(cohortId, observationAttempt, board.CurrentScope,\n"
            "                view, { board.Revision, board.ObservedAtMs },\n"
            "                BotEncounter::Nefarian::ObservationClockMs(\n"
            "                    GameTime::GetGameTimeSteadyPoint()));") in submit
    assert submit.index("Begin(cohortId, observationAttempt)") < submit.index("ObserveWarriors(")
    assert ("Observations().RecordRefused(cohortId, observationAttempt,\n"
            "                    context.Bot->GetGUID().GetCounter(),") in submit
    assert "cohortId, observationAttempt,\n            mechanic = proposal.Id.Mechanic," in submit
    export = EXPORT.read_text()
    assert "std::string EncounterObservationsJsonField(std::string const& cohortId,\n    ObservationAttempt attempt," in export
    assert "struct ObservationAttempt" in export and "#include <string>" in export
    assert "#include \"Bots/Content" not in export  # the raid runtime pulls no strategy header


def test_changed_sources_stay_below_the_module_size_limit():
    for path in (COUNTERS, EXPORT, STORE, WATCH, CANDIDATES, RAID_RUNTIME):
        assert len(path.read_text().splitlines()) < 1000, path


# --- harness: the final status is the source when complete ------------------------------------------------

def _block(active=0, pillar=0, refused=None, complete=True, attempt=7, epoch=CAPTURE["combat_log_epoch"],
           first=WINDOW_START - 1_000, last=WINDOW_END + 1_000):
    """A counter block of attempt `attempt` and start lifecycle `epoch` (None leaves the field out).

    `first` / `last` are the observer's first and newest observation times (system ms, the combat log's clock;
    the default observer spans the analysed boss window [WINDOW_START, WINDOW_END]; None leaves the field out)."""
    block = {ACTIVE: active, PILLAR: pillar, "move_refused": refused or {}, "complete": complete,
             "attempt_id": attempt}
    block = block if epoch is None else {**block, "combat_log_epoch": epoch}
    block = block if first is None else {**block, "first_observed_at_ms": first}
    return block if last is None else {**block, "last_observed_at_ms": last}


def _status(block, *, attempt=7, now_ms=WINDOW_END + 50_000, cohort=CAPTURE["cohort_id"],
            server=CAPTURE["server_epoch"]) -> dict:
    """A report/heartbeat payload whose status (cohort `cohort`, server epoch `server`, attempt `attempt`, read at
    server time `now_ms`, after the boss window closed at WINDOW_END) exports the given counter block. The
    defaults are the identity of write_run's combat-log capture (test_run_sanity.CAPTURE)."""
    return {"status": {"cohort_id": cohort, "server_epoch": server, "attempt_id": attempt,
                       "world_update": {"now_ms": now_ms},
                       "raid_runtime": {"server_epoch": server, "attempt_id": attempt,
                                        "encounter_observations": {"nefarian": block}}}}


def _status_run(tmp_path: Path, name: str, *, report=None, latest=None, trace=None, capture=CAPTURE) -> Path:
    run = write_run(tmp_path / name, [_hit(20_000, 1, 9_000)], report=report, capture=capture)
    if latest is not None:
        (run / "latest.json").write_text(json.dumps(latest))
    if trace is not None:
        from tests.test_run_sanity import _write_gz, TRACE_HISTORY_FILE
        _write_gz(run / TRACE_HISTORY_FILE, trace)
    return run


def test_status_counts_above_zero_are_a_blocking_finding(tmp_path):
    refused = {"3": {"hop:native_no_path": 40}}
    run = _status_run(tmp_path, "run", report=_status(_block(active=2, pillar=1, refused=refused)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] == {ACTIVE: 2, PILLAR: 1, "move_refused": refused}
    trace = result["decision_trace"]
    assert (trace["source"], trace["complete"], trace["server_counters"]["file"]) == ("server_status", True,
                                                                                       "report.json")
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"][ACTIVE], row["evidence"][PILLAR]) == ("blocking", 2, 1)
    assert row["evidence"]["observation_source"] == "server_status"
    assert "server's status counters" in row["detail"]


def test_a_complete_status_zero_passes_without_a_trace(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block()))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] == {ACTIVE: 0, PILLAR: 0, "move_refused": {}}
    assert _observation_findings(tmp_path, run) == []


def test_latest_json_is_read_only_when_the_run_has_no_report(tmp_path):
    run = _status_run(tmp_path, "run", latest=_status(_block(pillar=1)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"][PILLAR] == 1
    assert result["decision_trace"]["server_counters"]["states"] == {"report.json": "no_file",
                                                                     "latest.json": "complete"}
    # An existing report is the final export: an older heartbeat never stands in for its missing block.
    run = _status_run(tmp_path, "with-report", report={"status": {"raid_runtime": {}}},
                      latest=_status(_block(pillar=1)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None
    assert result["decision_trace"]["server_counters"]["states"] == {"report.json": "absent"}


@pytest.mark.parametrize("report", [
    None,                                              # no status at all
    {"status": {"raid_runtime": {}}},                  # a server without the counters (older build)
])
def test_a_server_that_exported_no_counters_leaves_the_trace_as_the_source(tmp_path, report):
    run = _status_run(tmp_path, "run", report=report, trace=_trace([(3, BONE_ACTIVE, "observation")]))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"][ACTIVE] == 1
    assert (result["decision_trace"]["source"], result["decision_trace"]["complete"]) == ("decision_trace", True)
    assert result["decision_trace"]["server_counters"]["complete"] is False
    assert [row["severity"] for row in _observation_findings(tmp_path, run)] == ["blocking"]


def test_an_incomplete_status_zero_without_a_trace_is_unproven_and_blocks(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block(complete=False)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None
    assert result["decision_trace"]["incomplete_reason"] == "native_counters_incomplete"
    assert result["decision_trace"]["retained_trace_complete"] is False  # what the scan alone found: no file
    assert result["decision_trace"]["server_counters"]["states"]["report.json"] == "incomplete"
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")


def test_negative_control_other_scenarios_never_read_the_status_block(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block(active=5)))
    other = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": "blackwing_descent_10n_magmaw"}, ROOT)
    assert "nefarian_observations" not in other and "decision_trace" not in other
    # And a trace-only Nefarian run keeps its trace-based result (the fallback is unchanged).
    trace_only = sanity_inputs(_trace_run(tmp_path, _trace([(3, f"{REFUSED}hop:x", "refused")]), "t"), TARGET, ROOT)
    assert trace_only["nefarian_observations"]["move_refused"] == {"3": {"hop:x": 1}}
    assert trace_only["decision_trace"]["source"] == "decision_trace"


def test_parse_status_observations_states():
    from tools.raid_program.run_sanity_inputs import UNUSABLE_BLOCK
    assert parse_status_observations(None) == (None, "absent")  # only a block the status does not export
    assert parse_status_observations(UNUSABLE_BLOCK) == (None, "malformed")  # present but null / inside a non-object
    assert parse_status_observations([1]) == (None, "malformed")
    assert parse_status_observations(_block(complete="true")) == (None, "incomplete")
    assert parse_status_observations({**_block(), PILLAR: True}) == (None, "malformed")
    assert parse_status_observations(_block(refused={"9": {"b": 1, "a": 2}}))[0]["move_refused"] == {
        "9": {"a": 2, "b": 1}}

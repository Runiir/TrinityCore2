"""BWD 10N round 3 fix pass (sanity packet): review findings on the sanity and scoreboard-record paths.

1. Unavailable or unproven Nefarian observation evidence is a blocking finding (run_sanity).
2. A bounded or sampled decision-trace tail never attests absence over the boss window (run_sanity_inputs).
3. Status counters count only from the judged attempt's final export, proven to cover the window's end.
4. The Omnotron WCL cast timeline keeps no duration annotation in an ability name.
5. Canonical Magmaw records rank DPS gaps against their roster variant's references.
6. (v2 review) Status counters are bound to the judged capture's cohort, server, attempt and combat-log
   lifecycle; the trace never overrides explicit native observer incompleteness; an unreadable final report
   is not an absent one.
7. (v3 review) The decision-trace fallback counts and covers only rows of the judged capture (each entry's own
   cohort, server epoch and attempt); a native observation block or container that is present but null or not an
   object is malformed, never absent, so it cannot enable the fallback (Nefarian and Atramedes).
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from tests.test_nefarian_observation_counters import ACTIVE, PILLAR, _block, _status, _status_run
from tests.test_raid_scoreboard import CLEAR, SCENARIO as MAGMAW, root  # noqa: F401  (root is a fixture)
from tests.test_raid_scoreboard_roster_variants import C0, C0_ROSTER, _copy_sidecar
from tests.test_run_sanity import (
    BONE_ACTIVE, CAPTURE, LABEL, NODE, ROOT, SCENARIO, TARGET, TRACE_IDENTITY, WINDOW_END, WINDOW_START, _hit,
    _observation_findings, _trace, _trace_row, _write_gz, by_check, inputs, kill, make_root, sanity_findings,
    write_run, write_scoreboard,
)
from tools.bot_ml.compare_magmaw_timelines import CAST_DURATION_RE, _wcl_actor_summary
from tools.bot_ml.live_validation_heartbeat import TRACE_HISTORY_FILE
from tools.bot_ml.live_validation_terminal_signals import TERMINAL_TRACE_DRAIN_FILE
from tools.raid_program import development_graph as graph
from tools.raid_program import graph_acceptance
from tools.raid_program.run_sanity_inputs import (
    UNUSABLE_BLOCK, parse_status_observations, sanity_inputs, status_block, trace_row_binding,
)
from tools.raid_program.scoreboard_core import load_target, spec_targets, target_for_records
from tools.raid_program.scoreboard_record import record_from_summary

BOTS = (1, 2, 3, 4)


# --- 1. run_sanity: unavailable or unproven evidence blocks ------------------------------------------------

def _acceptance(tmp_path, document, **fields) -> list[dict]:
    root_dir = make_root(tmp_path)
    write_scoreboard(root_dir, [kill("k1", sanity_inputs=document, **fields)])
    return by_check(sanity_findings(root_dir, SCENARIO, LABEL)).get("acceptance_observation") or []


def _document(case: str) -> dict:
    document = inputs()
    trace = document["decision_trace"]
    if case == "field absent":  # a record from before sanity_inputs.nefarian_observations
        del document["nefarian_observations"], document["decision_trace"]
    elif case == "no trace file":
        document["nefarian_observations"] = None
        document["decision_trace"] = {**trace, "available": False, "complete": False, "incomplete_reason": "no_trace_file"}
    elif case == "partial counts":
        document["nefarian_observations"] = {ACTIVE: 0}
    elif case == "malformed counts":
        document["nefarian_observations"] = {ACTIVE: "0", PILLAR: None, "move_refused": {}}
    elif case == "incomplete trace":  # zeros the retained trace cannot vouch for
        document["decision_trace"] = {**trace, "complete": False, "incomplete_reason": "window_start_not_covered"}
    elif case == "no coverage claim":  # zero counts, and nothing says the trace or counters cover the window
        del document["decision_trace"]
    elif case == "no complete field":
        document["decision_trace"] = {key: value for key, value in trace.items() if key != "complete"}
    elif case in ("complete is a string", "complete is one", "complete is null"):
        document["decision_trace"] = {**trace, "complete": {"complete is a string": "true", "complete is one": 1,
                                                            "complete is null": None}[case]}
    return document


CASES = ["field absent", "no trace file", "partial counts", "malformed counts", "incomplete trace", "no coverage claim",
         "no complete field", "complete is a string", "complete is one", "complete is null"]


@pytest.mark.parametrize("case", CASES)
def test_unavailable_or_unproven_observation_evidence_is_a_blocking_finding(tmp_path, case):
    (row,) = _acceptance(tmp_path, _document(case))
    assert (row["severity"], row["kill_id"]) == ("blocking", "k1")
    assert row["evidence"]["status"] == "unproven"
    assert "unproven" in row["detail"] and "not a pass" in row["detail"]


def test_the_control_with_an_affirmative_complete_zero_has_no_finding(tmp_path):
    assert _acceptance(tmp_path, inputs()) == []
    assert _acceptance(tmp_path / "true", {**inputs(), "decision_trace": {**inputs()["decision_trace"], "complete": True}}) == []


def test_the_unproven_reason_names_what_is_missing(tmp_path):
    (row,) = _acceptance(tmp_path, _document("incomplete trace"))
    assert "window start" in row["detail"]
    (row,) = _acceptance(tmp_path / "gone", _document("no trace file"))
    assert "holds no retained decision trace" in row["detail"]
    (row,) = _acceptance(tmp_path / "old", _document("field absent"))
    assert "records before sanity_inputs.nefarian_observations" in row["detail"]
    (row,) = _acceptance(tmp_path / "claim", _document("no coverage claim"))
    assert "no completeness claim" in row["detail"]


def test_a_kill_the_verdict_does_not_count_does_not_block_on_missing_evidence(tmp_path):
    stalled = {"valid_for_dps": False, "reasons": ["boss_window_stall_too_long"], "stalled_sec": 4.0,
               "max_stall_sec": 4.0, "stall_fraction": 0.004, "thresholds": {"max_boss_window_stall_fraction": 0.02}}
    rows = _acceptance(tmp_path, _document("no trace file"), measurement_validity=stalled)
    assert [row for row in rows if row["severity"] == "blocking"] == []


def test_an_observation_above_zero_still_blocks_with_or_without_coverage(tmp_path):
    for name, complete in (("partial", False), ("none", None)):
        document = inputs(nefarian_observations={PILLAR: 1})
        document["decision_trace"] = {**document["decision_trace"], "complete": complete}
        (row,) = _acceptance(tmp_path / name, document)
        assert (row["severity"], row["evidence"][PILLAR]) == ("blocking", 1)


def test_other_historical_checks_keep_their_not_evaluable_warnings(tmp_path):
    document = {key: value for key, value in inputs().items()
                if key in ("schema", "combat_log", "deaths", "enrage_pulls")}  # before health_half/revives/observations
    root_dir = make_root(tmp_path)
    write_scoreboard(root_dir, [kill("k1", sanity_inputs=document)])
    grouped = by_check(sanity_findings(root_dir, SCENARIO, LABEL))
    for check in ("health_pinned_half", "instant_revive"):
        assert [(row["severity"], row["evidence"]["status"]) for row in grouped[check]] == [("warn", "not_evaluable")]
    assert [row["severity"] for row in grouped["acceptance_observation"]] == ["blocking"]


def test_the_stored_round_records_without_the_counts_now_block_on_them():
    from tests.test_run_sanity import R02, _stored
    findings = [row for row in _stored(SCENARIO, R02) if row["check"] == "acceptance_observation"]
    assert findings and {row["severity"] for row in findings} == {"blocking"}


# --- 2. run_sanity_inputs: a bounded tail proves nothing about the window -----------------------------------

def _stamped(bot: int, sequence: int, at: int, action: str = "nefarian_platform_hold", result: str = "hold") -> dict:
    return _trace_row(bot, sequence, action, at=at, result=result)


def _tail(bots=BOTS, first=200, count=8, end=WINDOW_END + 1_000) -> list[dict]:
    """The last `count` contiguous rows of each bot (the terminal `trace all N` drain), ending after the window."""
    return [_stamped(bot, first + index, end - (count - 1 - index) * 33) for bot in bots for index in range(count)]


def _scan(tmp_path: Path, rows: list, *, file: str = TERMINAL_TRACE_DRAIN_FILE, name: str = "run") -> dict:
    run = write_run(tmp_path / name, [_hit(20_000, 1, 9_000)])
    _write_gz(run / file, rows)
    return sanity_inputs(run, TARGET, ROOT)


def test_a_terminal_tail_is_not_certified_as_the_whole_boss_window(tmp_path):
    result = _scan(tmp_path, _tail())
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "window_start_not_covered")
    assert trace["sequence_gaps"] == 0 and trace["actors_without_rows"] == []  # nothing else is wrong with it
    assert trace["window_start_uncovered"] == ["1", "2", "3", "4"] and trace["window_end_uncovered"] == []
    assert result["nefarian_observations"][ACTIVE] == 0


def test_a_violation_before_the_tail_cannot_be_reported_absent(tmp_path):
    """The reviewer's scenario: an early warrior violation is outside the retained final rows."""
    run = write_run(tmp_path / "run", [_hit(20_000, 1, 9_000)])
    _write_gz(run / TERMINAL_TRACE_DRAIN_FILE, _tail())  # the violation was decision 40 of 200+, never retained
    root_dir = make_root(tmp_path / "root")
    write_scoreboard(root_dir, [kill("k1", sanity_inputs=sanity_inputs(run, TARGET, ROOT))])
    (row,) = by_check(sanity_findings(root_dir, SCENARIO, LABEL))["acceptance_observation"]
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")
    assert "window start" in row["detail"]


def test_head_rows_without_the_window_end_are_not_complete(tmp_path):
    rows = [_stamped(bot, sequence, WINDOW_START - 1_000 + (sequence - 1) * 1_000) for bot in BOTS
            for sequence in range(1, 9)]  # 9 s .. 16 s of a window that runs to 800 s
    trace = _scan(tmp_path, rows, file=TRACE_HISTORY_FILE)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "window_end_not_covered")
    assert trace["window_end_uncovered"] == ["1", "2", "3", "4"] and trace["window_start_uncovered"] == []


def test_rows_at_exactly_the_window_edges_cover_them(tmp_path):
    rows = [_stamped(bot, sequence, at) for bot in BOTS for sequence, at in ((1, WINDOW_START), (2, 400_000),
                                                                              (3, WINDOW_END))]
    trace = _scan(tmp_path, rows, file=TRACE_HISTORY_FILE)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (True, None)


def test_the_two_retained_files_together_can_cover_the_window(tmp_path):
    """The union of the history file (start) and the terminal drain (end) proves both edges; overlap is fine."""
    rows = _trace(count=6)
    run = write_run(tmp_path / "run", [_hit(20_000, 1, 9_000)])
    _write_gz(run / TRACE_HISTORY_FILE, [row for row in rows if row["entry"]["sequence"] <= 4])
    _write_gz(run / TERMINAL_TRACE_DRAIN_FILE, [row for row in rows if row["entry"]["sequence"] >= 4])
    trace = sanity_inputs(run, TARGET, ROOT)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["window_rows"]) == (True, None, 24)
    # ... but a missing middle is a gap, however good both ends look
    _write_gz(run / TERMINAL_TRACE_DRAIN_FILE, [row for row in rows if row["entry"]["sequence"] >= 6])
    trace = sanity_inputs(run, TARGET, ROOT)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "sequence_gaps")


def test_one_actor_with_only_a_tail_makes_the_trace_incomplete(tmp_path):
    rows = [row for row in _trace(count=6) if row["bot_guid"] != 4] + _tail(bots=(4,))
    trace = _scan(tmp_path, rows, file=TRACE_HISTORY_FILE)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "window_start_not_covered")
    assert trace["window_start_uncovered"] == ["4"]


def test_the_full_span_control_is_complete(tmp_path):
    trace = _scan(tmp_path, _trace(), file=TRACE_HISTORY_FILE)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (True, None)
    assert trace["window_start_uncovered"] == [] and trace["window_end_uncovered"] == []


def test_a_sequence_number_seen_at_two_times_is_not_a_dense_stream(tmp_path):
    rows = _trace()
    rows.append(_stamped(2, 3, 500_000))  # sequence 3 of bot 2 again, at another time
    trace = _scan(tmp_path, rows, file=TRACE_HISTORY_FILE)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "sequence_conflicts")
    assert trace["sequence_conflicts"] == 1


def test_a_sampled_tail_with_a_hole_before_the_window_edge_is_incomplete(tmp_path):
    """Heartbeat tails (8 of ~30 rows a second) leave holes between the retained runs."""
    rows = [_stamped(bot, sequence, at) for bot in BOTS
            for sequence, at in ((1, 9_000), (2, 9_030), (10, 300_000), (11, 300_030), (30, 801_000))]
    trace = _scan(tmp_path, rows, file=TRACE_HISTORY_FILE)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "sequence_gaps")


# --- 3. run_sanity_inputs: status counters of the judged attempt, covering the window's end -------------------

def _states(result: dict) -> dict:
    return result["decision_trace"]["server_counters"]["states"]


def _findings(tmp_path: Path, run: Path) -> list[str]:
    return [row["severity"] for row in _observation_findings(tmp_path, run)]


def _inputs_server(run: Path) -> dict:
    return sanity_inputs(run, TARGET, ROOT)["decision_trace"]["server_counters"]


def test_an_older_heartbeat_never_covers_for_malformed_final_counters(tmp_path):
    """The reviewer's scenario: the last heartbeat holds zeros, a violation follows, the final export is unusable."""
    older = _status(_block(), now_ms=WINDOW_END - 60_000)
    run = _status_run(tmp_path, "run", report=_status({**_block(), ACTIVE: "2"}), latest=older)
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert result["nefarian_observations"] is None
    assert (trace["source"], trace["complete"]) == ("decision_trace", False)
    assert trace["server_counters"]["complete"] is False and _states(result) == {"report.json": "malformed"}
    assert _findings(tmp_path, run) == ["blocking"]


def test_an_older_heartbeat_zero_does_not_override_absent_final_counters(tmp_path):
    older = _status(_block(), now_ms=WINDOW_END + 10_000)  # even one that was read after the window closed
    run = _status_run(tmp_path, "run", report={"status": {"raid_runtime": {}}}, latest=older)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "absent"}
    assert _findings(tmp_path, run) == ["blocking"]


def test_counters_of_another_attempt_are_refused(tmp_path):
    """A counter block of attempt 1 inside the status of attempt 2."""
    run = _status_run(tmp_path, "run", report=_status(_block(attempt=1), attempt=2))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "attempt_mismatch"}
    assert _findings(tmp_path, run) == ["blocking"]


@pytest.mark.parametrize("payload", [
    {"status": {"attempt_id": 7, "world_update": {"now_ms": WINDOW_END + 1},
                "raid_runtime": {"encounter_observations": {"nefarian": _block()}}}},   # no attempt in the runtime
    {"status": {"attempt_id": 8, "world_update": {"now_ms": WINDOW_END + 1},
                "raid_runtime": {"attempt_id": 7, "encounter_observations": {"nefarian": _block()}}}},  # status disagrees
    {"status": {"world_update": {"now_ms": WINDOW_END + 1},
                "raid_runtime": {"attempt_id": 7, "encounter_observations": {"nefarian": _block(attempt=None)}}}},
    {"status": {"world_update": {"now_ms": WINDOW_END + 1},
                "raid_runtime": {"attempt_id": 0, "encounter_observations": {"nefarian": _block(attempt=0)}}}},
], ids=["runtime without attempt", "status and runtime disagree", "block without attempt", "attempt zero"])
def test_the_attempt_identity_must_be_established_everywhere(tmp_path, payload):
    result = sanity_inputs(_status_run(tmp_path, "run", report=payload), TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "attempt_mismatch"}


def test_a_status_that_does_not_show_the_end_of_the_window_is_not_a_final_export(tmp_path):
    for name, now_ms, state in (("early", WINDOW_END - 1, "before_window_end"), ("missing", None, "no_snapshot_time")):
        payload = _status(_block(), now_ms=now_ms)
        if now_ms is None:
            del payload["status"]["world_update"]
        run = _status_run(tmp_path, name, report=payload)
        result = sanity_inputs(run, TARGET, ROOT)
        assert result["nefarian_observations"] is None and _states(result) == {"report.json": state}
        assert _findings(tmp_path / name, run) == ["blocking"]
    # a snapshot read at the last damage of the window covers it
    result = sanity_inputs(_status_run(tmp_path, "edge", report=_status(_block(), now_ms=WINDOW_END)), TARGET, ROOT)
    assert result["nefarian_observations"] is not None and _states(result) == {"report.json": "complete"}


def test_an_unknown_boss_window_cannot_prove_status_coverage(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block()), trace=_trace())
    (run / "combat_analysis.json").write_text(json.dumps({"encounters": []}))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "window_unknown"}
    assert result["decision_trace"]["incomplete_reason"] == "native_counters_window_unknown"
    assert result["decision_trace"]["retained_trace_complete"] is False  # the trace scan has no window either


def test_the_final_export_of_the_judged_attempt_is_the_source(tmp_path):
    """The control: matching attempt everywhere, read after the window closed."""
    run = _status_run(tmp_path, "run", report=_status(_block(pillar=2, attempt=9), attempt=9),
                      capture={**CAPTURE, "attempt_id": 9})
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert result["nefarian_observations"][PILLAR] == 2
    assert (trace["source"], trace["complete"], trace["server_counters"]["file"]) == ("server_status", True, "report.json")
    assert trace["server_counters"]["attempt_id"] == 9 and trace["server_counters"]["snapshot_now_ms"] == WINDOW_END + 50_000
    assert _findings(tmp_path, run) == ["blocking"]  # the two pillar warriors
    clean = _status_run(tmp_path, "clean", report=_status(_block()))
    assert _findings(tmp_path, clean) == []
    assert "identity_conflicts" not in _inputs_server(clean)  # bound: nothing to report


def test_the_trace_can_still_attest_the_window_when_the_server_exported_no_counters(tmp_path):
    """The one fallback: no final status carries a Nefarian block at all (an older build), and the trace proves it."""
    for name, report in (("no status", None), ("no block", {"status": {"raid_runtime": {}}})):
        run = _status_run(tmp_path, name, report=report, trace=_trace())
        result = sanity_inputs(run, TARGET, ROOT)
        assert result["decision_trace"]["source"] == "decision_trace" and result["decision_trace"]["complete"] is True
        assert _findings(tmp_path / name, run) == []


def test_a_refused_status_scope_is_not_replaced_by_the_trace(tmp_path):
    """A block of attempt 1 inside the status of attempt 2 is a native export that cannot be used: blocking."""
    run = _status_run(tmp_path, "run", report=_status(_block(attempt=1), attempt=2), trace=_trace())
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["decision_trace"]["source"] == "decision_trace" and result["decision_trace"]["complete"] is False
    assert result["decision_trace"]["incomplete_reason"] == "native_counters_attempt_mismatch"
    assert result["decision_trace"]["retained_trace_complete"] is True
    assert _states(result) == {"report.json": "attempt_mismatch"}
    assert _findings(tmp_path, run) == ["blocking"]


# --- 4. Omnotron WCL cast timeline: no duration annotation in an ability name ------------------------------

OMNOTRON_TIMELINES = ROOT / "experiments/configs/cata_raid_encounters/blackwing_descent/omnotron_defense_system_wcl_cast_timelines_v1.json"


def _omnotron_actors() -> list[dict]:
    document = json.loads(OMNOTRON_TIMELINES.read_text())
    return [*document["actors"], *(actor for reference in document.get("additional_references") or []
                                   for actor in reference["actors"])]


def test_omnotron_inline_cast_names_have_no_duration_suffix():
    casts = [cast for actor in _omnotron_actors() for cast in actor["casts"]]
    assert casts
    assert sorted({cast["ability"] for cast in casts if CAST_DURATION_RE.search(cast["ability"])}) == []
    assert not any(re.search(r"\d\s*sec\b", cast["ability"]) for cast in casts)


def test_omnotron_cast_durations_survive_in_a_separate_field():
    casts = [cast for actor in _omnotron_actors() for cast in actor["casts"]]
    timed = [cast for cast in casts if "cast_time_sec" in cast]
    assert len(timed) == 220  # every annotated cast of the round-3 extraction kept its duration
    assert all(isinstance(cast["cast_time_sec"], (int, float)) and 0 <= cast["cast_time_sec"] < 10 for cast in timed)
    assert all(isinstance(cast["ability"], str) and cast["ability"] == cast["ability"].strip() for cast in casts)
    assert any(cast["ability"] == "Cobra Shot" and cast["cast_time_sec"] == 0.77 for cast in timed)


def test_omnotron_casts_of_one_spell_fall_into_one_ability_for_the_comparator():
    for actor in _omnotron_actors():
        names = {cast["ability"] for cast in actor["casts"]}
        summary = _wcl_actor_summary(actor, 1e9)
        assert {row["ability"] for row in summary["ability_summary"]} <= names
        assert sum(row["cast_count"] for row in summary["ability_summary"]) <= summary["completed_casts"]
        hunter_cobra = [row for row in summary["ability_summary"] if row["ability"].startswith("Cobra Shot")]
        assert len(hunter_cobra) <= 1
        assert len(names) == len({CAST_DURATION_RE.sub("", name) for name in names})  # nothing left to merge


# --- 5. canonical Magmaw records rank gaps against their roster variant's references -------------------------

def _summary(scenario_id: str | None, dps: dict[str, float]) -> dict:
    summary = {"native_clear": True, "completion_reason": CLEAR,
               "actors": [{"bot_guid": int(actor_id), "bot_name": row["name"], "class_spec": row["spec"],
                           "encounter_window_dps": dps.get(row["spec"], 1.0e9)} for actor_id, row in C0_ROSTER.items()]}
    return {**summary, "shard_identity": {"scenario_id": scenario_id}} if scenario_id else summary


def _record(root_dir: Path, summary: dict) -> dict:
    return record_from_summary(summary, root=root_dir, target=load_target(root_dir, MAGMAW), scenario=MAGMAW,
                               label="c0", kill_id="c0-k1", deaths={})


def test_canonical_magmaw_ranks_gaps_against_the_variant_references(root):  # noqa: F811
    _copy_sidecar(root)
    target = load_target(root, MAGMAW)
    variant = spec_targets(root, target_for_records(root, target, [{"shard_identity": {"scenario_id": C0}}]))
    legacy = spec_targets(root, target)
    assert variant["blood_death_knight"] != legacy["blood_death_knight"] == 26152.0
    # every actor exactly on its tier-11 reference: no gap
    at_reference = {spec: dps for spec, dps in variant.items()}
    assert _record(root, _summary(C0, at_reference))["ranked_gaps"] == []
    # 1 DPS short of the variant reference: the gap is measured against it, not against the legacy value
    short = {**at_reference, "blood_death_knight": variant["blood_death_knight"] - 1.0}
    (gap,) = _record(root, _summary(C0, short))["ranked_gaps"]
    assert (gap["spec"], gap["target_dps"], gap["gap_dps"]) == ("blood_death_knight", variant["blood_death_knight"], 1.0)


def test_legacy_and_unmatched_shard_identities_keep_the_legacy_references(root):  # noqa: F811
    _copy_sidecar(root)
    target = load_target(root, MAGMAW)
    variant = spec_targets(root, target_for_records(root, target, [{"shard_identity": {"scenario_id": C0}}]))
    at_variant = {"blood_death_knight": variant["blood_death_knight"]}  # everyone else is far above any target
    for scenario_id in (None, "blackwing_descent_10n_magmaw_diagnostic"):
        summary = _summary(scenario_id, at_variant)
        assert target_for_records(root, target, [summary]) is target
        gaps = _record(root, summary)["ranked_gaps"]
        row = next(row for row in gaps if row["spec"] == "blood_death_knight")
        assert row["target_dps"] == 26152.0 and row["gap_dps"] == round(26152.0 - variant["blood_death_knight"], 1)


def test_legacy_magmaw_b5_verdict_still_verifies_byte_identically():
    """graph_acceptance.verify_verdict recomputes the verdict and compares it with the accepted file."""
    path = "artifacts/cata_raid_program/verdicts/blackwing_descent_10n_magmaw-b5-d1898555-7fcea04e9dd3.json"
    if not (ROOT / path).is_file():
        pytest.skip("accepted Magmaw verdict not hydrated")
    verdict = json.loads((ROOT / path).read_text())
    g = {"encounter": {"raid": "blackwing_descent", "mode": "10N", "boss": "magmaw"},
         "run": {"scoreboard_label": "b5-d1898555", "claimed_at": "2026-01-01T00:00:00Z"},
         "build_identity": {"binary_sha256": verdict["worldserver_sha256"]}, "requirements": {}}
    ref = {"path": path, "sha256": graph.digest((ROOT / path).read_bytes())}
    assert graph_acceptance.verify_verdict(ROOT, g, ref)["status"] == "pass"
    assert "roster_variant" not in verdict


# --- 6. (v2 review) status counters are bound to the judged capture -------------------------------------------

FIELDS = ("cohort_id", "server_epoch", "attempt_id", "combat_log_epoch")


def _claim(*, cohort=CAPTURE["cohort_id"], server=CAPTURE["server_epoch"], attempt=7,
           epoch=CAPTURE["combat_log_epoch"], now_ms=WINDOW_END + 50_000, **block) -> dict:
    """A final status of (cohort, server epoch, attempt, lifecycle) exporting a zero block, read at `now_ms`."""
    return _status(_block(attempt=attempt, epoch=epoch, **block), attempt=attempt, cohort=cohort, server=server,
                   now_ms=now_ms)


def _counters(run: Path) -> dict:
    return sanity_inputs(run, TARGET, ROOT)["decision_trace"]["server_counters"]


def test_counters_of_a_later_attempt_do_not_certify_the_judged_capture(tmp_path):
    """The reviewer's scenario: the combat log is attempt 7's; the final status, runtime and zero counters
    consistently say attempt 8, read after the window closed."""
    run = _status_run(tmp_path, "run", report=_claim(attempt=8))
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert result["nefarian_observations"] is None
    assert _states(result) == {"report.json": "capture_mismatch"}
    assert (trace["server_counters"]["identity_conflicts"], trace["server_counters"]["identity_missing"]) == (
        ["attempt_id"], [])
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == (
        "decision_trace", False, "native_counters_capture_mismatch")
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")
    assert row["evidence"]["identity_conflicts"] == ["attempt_id"] and "judged capture" in row["detail"]


@pytest.mark.parametrize("field, change", [
    ("cohort_id", {"cohort": "shard-other"}),
    ("server_epoch", {"server": CAPTURE["server_epoch"] + 1}),
    ("attempt_id", {"attempt": 8}),
    ("combat_log_epoch", {"epoch": CAPTURE["combat_log_epoch"] + 1}),  # `.botexp start` keeps the attempt id
])
def test_every_identity_field_of_the_capture_is_compared(tmp_path, field, change):
    run = _status_run(tmp_path, "run", report=_claim(**change))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "capture_mismatch"}
    assert _counters(run)["identity_conflicts"] == [field] and _counters(run)["identity_missing"] == []
    assert _findings(tmp_path, run) == ["blocking"]


@pytest.mark.parametrize("field", FIELDS)
def test_a_capture_that_does_not_identify_itself_proves_nothing(tmp_path, field):
    capture = {key: value for key, value in CAPTURE.items() if key != field}
    run = _status_run(tmp_path, "run", report=_claim(), capture=capture)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "capture_identity_missing"}
    assert _counters(run)["identity_missing"] == [field] and _counters(run)["identity_conflicts"] == []
    assert _findings(tmp_path, run) == ["blocking"]


@pytest.mark.parametrize("capture", [
    None,                                                  # a log without any identity (a legacy export)
    {**CAPTURE, "attempt_id": "7"}, {**CAPTURE, "attempt_id": 0}, {**CAPTURE, "attempt_id": True},
    {**CAPTURE, "combat_log_epoch": 0}, {**CAPTURE, "server_epoch": -1}, {**CAPTURE, "cohort_id": ""},
], ids=["no identity", "attempt string", "attempt zero", "attempt bool", "epoch zero", "server negative",
        "cohort empty"])
def test_an_unusable_capture_identity_is_missing_not_matching(tmp_path, capture):
    run = _status_run(tmp_path, "run", report=_claim(), capture=capture)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "capture_identity_missing"}
    assert _findings(tmp_path, run) == ["blocking"]


def _without(payload: dict, *path: str) -> dict:
    """`payload` with the key at `path` (below its status) removed."""
    node = payload["status"]
    for key in path[:-1]:
        node = node[key]
    del node[path[-1]]
    return payload


@pytest.mark.parametrize("field, payload", [
    ("combat_log_epoch", _claim(epoch=None)),  # what the server exports today: no lifecycle anywhere in the status
    ("cohort_id", _without(_claim(), "cohort_id")),
    ("server_epoch", _without(_without(_claim(), "server_epoch"), "raid_runtime", "server_epoch")),
], ids=["lifecycle not exported", "no cohort", "no server epoch"])
def test_a_status_that_does_not_say_which_capture_it_belongs_to_is_refused(tmp_path, field, payload):
    run = _status_run(tmp_path, "run", report=payload)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None and _states(result) == {"report.json": "capture_identity_missing"}
    assert _counters(run)["identity_missing"] == [field]
    assert _findings(tmp_path, run) == ["blocking"]


def test_a_claim_of_the_wrong_type_is_a_mismatch_and_a_lifecycle_may_come_from_the_status(tmp_path):
    string_epoch = _claim()
    string_epoch["status"]["server_epoch"] = str(CAPTURE["server_epoch"])  # not the integer the capture exports
    run = _status_run(tmp_path, "string", report=string_epoch)
    assert _states(sanity_inputs(run, TARGET, ROOT)) == {"report.json": "capture_mismatch"}
    # the lifecycle exported at the status level instead of in the block binds just as well ...
    status_level = _claim(epoch=None)
    status_level["status"]["combat_log_epoch"] = CAPTURE["combat_log_epoch"]
    run = _status_run(tmp_path, "status-level", report=status_level)
    assert _states(sanity_inputs(run, TARGET, ROOT)) == {"report.json": "complete"}
    # ... but every claim must agree: a block of another lifecycle inside it is a mismatch
    status_level["status"]["raid_runtime"]["encounter_observations"]["nefarian"]["combat_log_epoch"] = 9
    run = _status_run(tmp_path, "disagree", report=status_level)
    assert _states(sanity_inputs(run, TARGET, ROOT)) == {"report.json": "capture_mismatch"}
    assert _counters(run)["identity_conflicts"] == ["combat_log_epoch"]


def test_the_final_heartbeat_of_a_run_without_a_report_is_bound_to_the_capture_too(tmp_path):
    run = _status_run(tmp_path, "run", latest=_claim(attempt=8))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None
    assert _states(result) == {"report.json": "no_file", "latest.json": "capture_mismatch"}
    assert _findings(tmp_path, run) == ["blocking"]


def test_a_correctly_bound_complete_final_report_still_passes(tmp_path):
    """The control: counters of the judged capture's cohort, server, attempt and lifecycle, read after the window."""
    run = _status_run(tmp_path, "run", report=_claim())
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert result["nefarian_observations"] == {ACTIVE: 0, PILLAR: 0, "move_refused": {}}
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == ("server_status", True, None)
    server = trace["server_counters"]
    assert (server["file"], server["attempt_id"], server["snapshot_now_ms"]) == ("report.json", 7, WINDOW_END + 50_000)
    assert "identity_conflicts" not in server and "identity_missing" not in server
    assert _observation_findings(tmp_path, run) == []
    # ... and a run of another attempt passes just as well once its capture says so
    other = {**CAPTURE, "attempt_id": 12, "combat_log_epoch": 5}
    run = _status_run(tmp_path, "other", report=_claim(attempt=12, epoch=5), capture=other)
    assert _states(sanity_inputs(run, TARGET, ROOT)) == {"report.json": "complete"}
    assert _observation_findings(tmp_path, run, "k2") == []


def test_the_capture_identity_is_read_from_the_combat_log_export():
    from tools.raid_program.run_sanity_inputs import capture_identity
    assert capture_identity({**CAPTURE, "recent_events": []}) == CAPTURE
    nested = {"raid_runtime": {key: value for key, value in CAPTURE.items() if key != "cohort_id"},
              "cohort_id": CAPTURE["cohort_id"]}
    assert capture_identity(nested) == CAPTURE  # the event-stream identity may sit in the runtime block
    assert capture_identity({**CAPTURE, "attempt_id": None, "raid_runtime": {"attempt_id": 4}})["attempt_id"] == 4
    assert capture_identity({**CAPTURE, "attempt_id": 1.5})["attempt_id"] is None
    assert set(capture_identity(None)) == set(FIELDS) and set(capture_identity(None).values()) == {None}
    assert set(capture_identity([1]).values()) == {None}


# --- 6. (v2 review) explicit native observer incompleteness stays blocking -----------------------------------

UNUSABLE = [
    ("incomplete", lambda: _status(_block(complete=False))),
    ("malformed", lambda: _status({**_block(), ACTIVE: "2"})),
    ("malformed", lambda: _status({**_block(), "move_refused": {"3": {"hop:x": -1}}})),
    ("attempt_mismatch", lambda: _status(_block(attempt=1), attempt=2)),
    ("before_window_end", lambda: _claim(now_ms=WINDOW_END - 1)),
    ("no_snapshot_time", lambda: _without(_claim(), "world_update")),
    ("capture_mismatch", lambda: _claim(epoch=CAPTURE["combat_log_epoch"] + 1)),
    ("capture_identity_missing", lambda: _claim(epoch=None)),
]
UNUSABLE_IDS = ["incomplete", "malformed count", "malformed refused", "attempt mismatch", "read too early",
                "no read time", "another lifecycle", "lifecycle not exported"]


def test_dense_decision_rows_never_override_an_explicit_incomplete_observer(tmp_path):
    """The reviewer's scenario: the same attempt's final report marks the observer incomplete, yet four actors
    have contiguous decision sequences spanning both edges of the window."""
    run = _status_run(tmp_path, "run", report=_claim(complete=False), trace=_trace())
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == (
        "decision_trace", False, "native_counters_incomplete")
    assert trace["retained_trace_complete"] is True  # the scan alone would have accepted these rows
    assert trace["window_start_uncovered"] == [] and trace["sequence_gaps"] == 0 and trace["window_rows"] == 24
    assert _states(result) == {"report.json": "incomplete"}
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"], row["evidence"]["reason"]) == (
        "blocking", "unproven", "native_counters_incomplete")
    assert "incomplete observer" in row["detail"] and "cannot vouch" in row["detail"]


@pytest.mark.parametrize("state, payload", [(state, make()) for state, make in UNUSABLE], ids=UNUSABLE_IDS)
def test_no_unusable_native_export_is_replaced_by_dense_decision_rows(tmp_path, state, payload):
    run = _status_run(tmp_path, "run", report=payload, trace=_trace())
    result = sanity_inputs(run, TARGET, ROOT)
    trace = result["decision_trace"]
    assert _states(result) == {"report.json": state}
    assert (trace["complete"], trace["incomplete_reason"]) == (False, f"native_counters_{state}")
    assert trace["retained_trace_complete"] is True
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")


def test_the_trace_counts_stay_evidence_under_an_incomplete_native_export(tmp_path):
    run = _status_run(tmp_path, "run", report=_claim(complete=False), trace=_trace([(3, BONE_ACTIVE, "observation")]))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"][ACTIVE] == 1 and result["decision_trace"]["complete"] is False
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"][ACTIVE]) == ("blocking", 1)
    assert row["evidence"]["trace_incomplete_reason"] == "native_counters_incomplete"


def test_the_fallback_without_native_counters_keeps_its_own_proofs(tmp_path):
    """No counters at all: the trace may stand in, but only as far as it proves both edges of the window."""
    absent = {"status": {"raid_runtime": {}}}
    run = _status_run(tmp_path, "dense", report=absent, trace=_trace())
    assert sanity_inputs(run, TARGET, ROOT)["decision_trace"]["complete"] is True
    assert _observation_findings(tmp_path, run, "dense") == []
    run = _status_run(tmp_path, "tail", report=absent, trace=_tail())
    trace = sanity_inputs(run, TARGET, ROOT)["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"]) == (False, "window_start_not_covered")
    assert "retained_trace_complete" not in trace  # no native export was overridden
    (row,) = _observation_findings(tmp_path, run, "tail")
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")


# --- 6. (v2 review) a present but unreadable final report is not an absent one -----------------------------------

UNREADABLE = {"truncated": '{"status": {"cohort_id": "shard-nef', "empty": "", "null": "null", "list": "[]",
              "malformed": "{not json"}


@pytest.mark.parametrize("content", list(UNREADABLE.values()), ids=list(UNREADABLE))
def test_a_present_but_unreadable_report_is_never_treated_as_absent(tmp_path, content):
    """latest.json (an older heartbeat) holds a bound, complete zero; the final report exists but cannot be read."""
    run = _status_run(tmp_path, "run", latest=_claim())
    (run / "report.json").write_text(content)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None
    assert _states(result) == {"report.json": "unreadable"}  # latest.json is not even consulted
    assert result["decision_trace"]["server_counters"]["complete"] is False
    assert result["decision_trace"]["incomplete_reason"] == "native_counters_unreadable"
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")
    assert "unreadable" in row["detail"]


def test_an_unreadable_report_is_not_replaced_by_dense_decision_rows_either(tmp_path):
    run = _status_run(tmp_path, "run", trace=_trace())
    (run / "report.json").write_text(UNREADABLE["truncated"])
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["decision_trace"]["retained_trace_complete"] is True
    assert (result["decision_trace"]["complete"], _states(result)) == (False, {"report.json": "unreadable"})
    assert _findings(tmp_path, run) == ["blocking"]


def test_an_unreadable_latest_json_is_unreadable_without_a_report_and_absence_stays_absence(tmp_path):
    run = _status_run(tmp_path, "heartbeat")
    (run / "latest.json").write_text(UNREADABLE["truncated"])
    assert _states(sanity_inputs(run, TARGET, ROOT)) == {"report.json": "no_file", "latest.json": "unreadable"}
    none = _status_run(tmp_path, "none", trace=_trace())  # neither file: an absent export, the trace is the source
    result = sanity_inputs(none, TARGET, ROOT)
    assert _states(result) == {"report.json": "no_file", "latest.json": "no_file"}
    assert (result["decision_trace"]["source"], result["decision_trace"]["complete"]) == ("decision_trace", True)


def test_the_status_observation_helper_reads_the_report_it_is_given_or_the_file(tmp_path):
    from tools.raid_program.run_sanity_inputs import BossWindow, status_observations
    boss = BossWindow({"first_at_ms": WINDOW_START, "last_at_ms": WINDOW_END}, NODE, CAPTURE)
    run = _status_run(tmp_path, "run", report=_claim())
    for report in (None, _claim()):  # read from the file, or handed over already read
        observations, server = status_observations(run, report, boss)
        assert observations == {ACTIVE: 0, PILLAR: 0, "move_refused": {}}
        assert server["states"] == {"report.json": "complete"}
    (run / "report.json").write_text(UNREADABLE["truncated"])
    observations, server = status_observations(run, None, boss)
    assert observations is None and server["states"] == {"report.json": "unreadable"}


# --- 6. (v2 review) dependency: the server must export its start lifecycle --------------------------------------

def test_the_observation_blocks_export_the_start_lifecycle_the_harness_binds_to():
    encounters = ROOT / "src/server/game/Bots/Content/Raids/BlackwingDescent/Encounters"
    for boss in ("Nefarian", "Atramedes"):
        text = "".join(path.read_text() for path in sorted((encounters / boss).glob(f"Bot{boss}Observation*.h")))
        assert '\\"combat_log_epoch\\"' in text, boss


# --- 7. (v3 review) the trace fallback counts and covers only rows of the judged capture ------------------------

ABSENT_EXPORT = {"status": {"raid_runtime": {}}}  # the keys lack the block: what an older build exports
FOREIGN = {"cohort_id": "shard-other", "server_epoch": 999, "attempt_id": 8}  # the reviewer's other capture
ROWS = 24  # _trace(): six rows of each of four bots


def _with_identity(rows: list, **identity) -> list:
    """`rows` with the identity fields of their entries replaced (a None value removes the field)."""
    def replaced(row: dict) -> dict:
        entry = {**row["entry"], **identity}
        return {**row, "entry": {key: value for key, value in entry.items() if value is not None}}
    return [replaced(row) for row in rows]


def _trace_scan(tmp_path: Path, rows: list, *, report=ABSENT_EXPORT, name: str = "run", capture=CAPTURE):
    """(run directory, sanity_inputs) of a run whose final status is `report` and whose retained trace is `rows`."""
    run = _status_run(tmp_path, name, report=report, trace=rows, capture=capture)
    return run, sanity_inputs(run, TARGET, ROOT)


def _unproven(tmp_path: Path, run: Path, reason: str) -> None:
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"], row["evidence"]["reason"]) == ("blocking", "unproven", reason)


def test_a_dense_zero_violation_trace_of_another_capture_cannot_certify_the_judged_kill(tmp_path):
    """The reviewer's scenario: the judged combat log is attempt 7's and the final report exports no Nefarian
    counters; the retained rows name a foreign cohort, server epoch 999 and attempt 8, dense over both edges."""
    run, result = _trace_scan(tmp_path, _with_identity(_trace(), **FOREIGN))
    trace = result["decision_trace"]
    assert result["nefarian_observations"] is None  # nothing of the foreign rows counts
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == ("decision_trace", False,
                                                                               "other_capture_rows")
    assert (trace["bound_rows"], trace["foreign_rows"], trace["window_rows"]) == (0, ROWS, 0)
    _unproven(tmp_path, run, "other_capture_rows")
    (row,) = _observation_findings(tmp_path, run, "detail")
    assert "another cohort, server epoch or attempt" in row["detail"]


@pytest.mark.parametrize("change", [{"cohort_id": "shard-other"}, {"server_epoch": 999}, {"attempt_id": 8},
                                    {"combat_log_epoch": CAPTURE["combat_log_epoch"] + 1}],
                         ids=["cohort", "server epoch", "attempt", "combat-log epoch"])
def test_every_identity_field_of_a_trace_row_is_compared_with_the_capture(tmp_path, change):
    run, result = _trace_scan(tmp_path, _with_identity(_trace(), **change))
    assert result["nefarian_observations"] is None
    assert (result["decision_trace"]["complete"], result["decision_trace"]["incomplete_reason"]) == (
        False, "other_capture_rows")
    _unproven(tmp_path, run, "other_capture_rows")


def test_the_same_capture_trace_still_certifies_when_the_server_exported_no_counters(tmp_path):
    """The positive controls: rows naming the judged capture (entry-level, with or without the lifecycle a
    native entry does not carry, or on the harness wrapper) bind, count and cover."""
    with_epoch = _with_identity(_trace(), combat_log_epoch=CAPTURE["combat_log_epoch"])
    wrapper = [{**row, "entry": {key: value for key, value in row["entry"].items() if key not in TRACE_IDENTITY},
                **TRACE_IDENTITY} for row in _trace()]
    for name, rows in (("entry", _trace()), ("epoch", with_epoch), ("wrapper", wrapper)):
        for report in (ABSENT_EXPORT, None):
            run, result = _trace_scan(tmp_path / name, rows, report=report, name="run" if report else "none")
            trace = result["decision_trace"]
            assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == ("decision_trace", True, None)
            assert (trace["bound_rows"], trace["foreign_rows"], trace["unidentified_rows"]) == (ROWS, 0, 0)
            assert result["nefarian_observations"][BONE_ACTIVE.removeprefix("nefarian_")] == 0
            assert _findings(tmp_path / name, run) == []


def test_foreign_rows_are_excluded_from_the_counts_and_never_block_a_bound_zero(tmp_path):
    foreign = _with_identity(_trace([(3, BONE_ACTIVE, "observation")]), **FOREIGN)  # attempt 8 had a violation
    run, result = _trace_scan(tmp_path, _trace() + foreign)
    trace = result["decision_trace"]
    assert result["nefarian_observations"][ACTIVE] == 0
    assert (trace["complete"], trace["bound_rows"], trace["foreign_rows"]) == (True, ROWS, ROWS + 1)
    assert _findings(tmp_path, run) == []
    # ... and a violation of the judged capture still counts among other attempts' rows
    bound = _trace([(3, BONE_ACTIVE, "observation")])
    run, result = _trace_scan(tmp_path, bound + _with_identity(_trace(), **FOREIGN), name="bound")
    assert result["nefarian_observations"][ACTIVE] == 1
    assert _findings(tmp_path, run) == ["blocking"]


def test_foreign_rows_never_fill_a_gap_or_cover_a_window_edge(tmp_path):
    gap = lambda row: row["bot_guid"] == 3 and row["entry"]["sequence"] in (3, 4)  # noqa: E731
    rows = [row for row in _trace() if not gap(row)]
    filler = _with_identity([row for row in _trace() if gap(row)], **FOREIGN)
    _, result = _trace_scan(tmp_path, rows + filler)
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["foreign_rows"]) == (False, "sequence_gaps", 2)
    start = _with_identity([_trace_row(bot, sequence, "nefarian_platform_hold", at=WINDOW_START - 1_000 + sequence)
                            for bot in BOTS for sequence in (1, 2, 3)], **FOREIGN)
    _, result = _trace_scan(tmp_path, _tail() + start, name="edge")
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["foreign_rows"]) == (
        False, "window_start_not_covered", 12)
    assert trace["window_start_uncovered"] == ["1", "2", "3", "4"]


UNIDENTIFIED = {
    "no identity fields": {"cohort_id": None, "server_epoch": None, "attempt_id": None},
    "no cohort": {"cohort_id": None}, "no server epoch": {"server_epoch": None}, "no attempt": {"attempt_id": None},
    "empty cohort": {"cohort_id": ""}, "negative server epoch": {"server_epoch": -1},
    "attempt a string": {"attempt_id": "7"}, "attempt zero": {"attempt_id": 0}, "attempt a bool": {"attempt_id": True},
    "unusable lifecycle": {"combat_log_epoch": 0},
}


@pytest.mark.parametrize("change", list(UNIDENTIFIED.values()), ids=list(UNIDENTIFIED))
def test_rows_that_do_not_establish_their_provenance_leave_the_trace_incomplete(tmp_path, change):
    run, result = _trace_scan(tmp_path, _with_identity(_trace(), **change))
    trace = result["decision_trace"]
    assert result["nefarian_observations"] is None
    assert (trace["complete"], trace["incomplete_reason"], trace["unidentified_rows"]) == (
        False, "row_identity_missing", ROWS)
    _unproven(tmp_path, run, "row_identity_missing")


def test_one_row_of_unknown_provenance_among_bound_rows_keeps_the_trace_incomplete(tmp_path):
    stray = _trace_row(1, 99, "nefarian_platform_hold", at=500_000, identity=None)
    run, result = _trace_scan(tmp_path, _trace() + [stray])
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["bound_rows"], trace["unidentified_rows"]) == (
        False, "row_identity_missing", ROWS, 1)
    _unproven(tmp_path, run, "row_identity_missing")
    # the bound rows' counts stay evidence
    run, result = _trace_scan(tmp_path, _trace([(3, BONE_ACTIVE, "observation")]) + [stray], name="counted")
    assert result["nefarian_observations"][ACTIVE] == 1 and _findings(tmp_path, run) == ["blocking"]


def test_a_row_that_contradicts_itself_about_its_identity_is_no_provenance(tmp_path):
    rows = [{**row, "attempt_id": 8} for row in _trace()]  # the entry says attempt 7, the wrapper attempt 8
    run, result = _trace_scan(tmp_path, rows)
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["conflicting_rows"]) == (
        False, "row_identity_conflict", ROWS)
    _unproven(tmp_path, run, "row_identity_conflict")


@pytest.mark.parametrize("capture", [None] + [{key: value for key, value in CAPTURE.items() if key != field}
                                             for field in ("cohort_id", "server_epoch", "attempt_id")],
                         ids=["no identity", "no cohort", "no server epoch", "no attempt"])
def test_a_capture_that_does_not_identify_itself_cannot_bind_any_trace_row(tmp_path, capture):
    run, result = _trace_scan(tmp_path, _trace(), capture=capture)
    trace = result["decision_trace"]
    assert result["nefarian_observations"] is None
    assert (trace["complete"], trace["incomplete_reason"], trace["capture_identified"]) == (
        False, "capture_unidentified", False)
    _unproven(tmp_path, run, "capture_unidentified")


def test_the_lifecycle_is_compared_only_when_both_the_row_and_the_capture_say_one(tmp_path):
    no_epoch = {key: value for key, value in CAPTURE.items() if key != "combat_log_epoch"}
    _, result = _trace_scan(tmp_path, _trace(), capture=no_epoch)  # an entry carries no lifecycle to contradict
    assert result["decision_trace"]["complete"] is True
    claimed = _with_identity(_trace(), combat_log_epoch=3)  # a row claiming one the capture cannot confirm
    run, result = _trace_scan(tmp_path, claimed, capture=no_epoch, name="claimed")
    assert (result["decision_trace"]["complete"], result["decision_trace"]["incomplete_reason"]) == (
        False, "row_identity_missing")


def test_a_foreign_trace_cannot_stand_in_under_an_unusable_native_export_either(tmp_path):
    run, result = _trace_scan(tmp_path, _with_identity(_trace(), **FOREIGN), report=_claim(complete=False))
    trace = result["decision_trace"]
    assert (trace["complete"], trace["incomplete_reason"], trace["retained_trace_complete"]) == (
        False, "native_counters_incomplete", False)
    assert result["nefarian_observations"] is None and _findings(tmp_path, run) == ["blocking"]


def test_trace_row_binding_classifies_a_row_against_the_capture():
    entry = {**TRACE_IDENTITY, "sequence": 1}
    assert trace_row_binding({"entry": entry}, entry, CAPTURE) == "bound"
    assert trace_row_binding({"entry": entry}, {**entry, "combat_log_epoch": 3}, CAPTURE) == "bound"
    assert trace_row_binding({"entry": entry}, {**entry, "combat_log_epoch": 4}, CAPTURE) == "foreign"
    assert trace_row_binding({"entry": entry}, {**entry, "attempt_id": 8}, CAPTURE) == "foreign"
    assert trace_row_binding({"entry": entry}, {**entry, "attempt_id": 8, "server_epoch": None}, CAPTURE) == "foreign"
    assert trace_row_binding({"entry": entry, "attempt_id": 8}, entry, CAPTURE) == "conflict"
    assert trace_row_binding({"entry": entry}, {"sequence": 1}, CAPTURE) == "unidentified"
    assert trace_row_binding({"entry": entry}, {**entry, "cohort_id": ""}, CAPTURE) == "unidentified"
    assert trace_row_binding({"entry": entry}, {**entry, "cohort_id": None, "server_epoch": 999}, CAPTURE) == "foreign"
    assert trace_row_binding({"entry": entry}, entry, None) == "unidentified"
    assert trace_row_binding({"entry": entry}, entry, {**CAPTURE, "attempt_id": None}) == "unidentified"


# --- 7. (v3 review) a present but unusable observation container is malformed, never absent -----------------

def _observations(value) -> dict:
    return {"status": {"raid_runtime": {"encounter_observations": value}}}


MALFORMED = {
    "nefarian null": _observations({"nefarian": None}),
    "nefarian list": _observations({"nefarian": [1]}),
    "nefarian string": _observations({"nefarian": "complete"}),
    "observations null": _observations(None),
    "observations list": _observations([]),
    "observations number": _observations(42),
    "observations string": _observations("x"),
    "runtime null": {"status": {"raid_runtime": None}},
    "runtime list": {"status": {"raid_runtime": []}},
    "status null": {"status": None},
    "status list": {"status": []},
}
ABSENT_EXPORTS = {
    "no status key": {}, "status without runtime": {"status": {}}, "runtime without observations": ABSENT_EXPORT,
    "observations without nefarian": _observations({}),
    "another boss's block only": _observations({"atramedes": {"complete": True}}),
}


def test_status_block_separates_a_missing_key_from_an_unusable_value():
    block = _block()
    assert status_block(_status(block)) == block
    assert {name: status_block(payload) for name, payload in ABSENT_EXPORTS.items()} == {
        name: None for name in ABSENT_EXPORTS}
    assert {name: status_block(payload) for name, payload in MALFORMED.items() if "nefarian" not in name} == {
        name: UNUSABLE_BLOCK for name in MALFORMED if "nefarian" not in name}
    assert status_block(MALFORMED["nefarian null"]) is UNUSABLE_BLOCK
    assert status_block(MALFORMED["nefarian list"]) == [1]  # present and not an object: parse says malformed
    assert status_block(_status(block), "atramedes") is None and status_block(["x"]) is UNUSABLE_BLOCK
    assert parse_status_observations(UNUSABLE_BLOCK) == (None, "malformed")
    assert parse_status_observations(status_block(ABSENT_EXPORT)) == (None, "absent")


@pytest.mark.parametrize("report", list(MALFORMED.values()), ids=list(MALFORMED))
def test_a_present_but_unusable_container_does_not_enable_the_trace_fallback(tmp_path, report):
    """The reviewer's scenarios: a readable final report whose Nefarian block is null, or whose
    encounter_observations is not an object, beside dense same-capture zero-violation rows."""
    run, result = _trace_scan(tmp_path, _trace(), report=report)
    trace = result["decision_trace"]
    assert _states(result) == {"report.json": "malformed"}
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == (
        "decision_trace", False, "native_counters_malformed")
    assert trace["retained_trace_complete"] is True  # the same rows stand in for an absent export, not this one
    assert trace["server_counters"]["complete"] is False
    _unproven(tmp_path, run, "native_counters_malformed")
    (row,) = _observation_findings(tmp_path, run, "detail")
    assert "malformed" in row["detail"] and "cannot vouch" in row["detail"]


@pytest.mark.parametrize("report", list(ABSENT_EXPORTS.values()), ids=list(ABSENT_EXPORTS))
def test_a_legitimately_absent_block_of_an_older_build_keeps_the_trace_fallback(tmp_path, report):
    run, result = _trace_scan(tmp_path, _trace(), report=report)
    trace = result["decision_trace"]
    assert _states(result) == {"report.json": "absent"}
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == ("decision_trace", True, None)
    assert _findings(tmp_path, run) == []
    # ... but only with the judged capture's rows
    run, result = _trace_scan(tmp_path, _with_identity(_trace(), **FOREIGN), report=report, name="foreign")
    assert result["decision_trace"]["complete"] is False
    _unproven(tmp_path, run, "other_capture_rows")


def test_an_unusable_heartbeat_block_is_malformed_when_the_run_has_no_report(tmp_path):
    run = _status_run(tmp_path, "run", latest=MALFORMED["nefarian null"], trace=_trace())
    result = sanity_inputs(run, TARGET, ROOT)
    assert _states(result) == {"report.json": "no_file", "latest.json": "malformed"}
    assert (result["decision_trace"]["complete"], result["decision_trace"]["incomplete_reason"]) == (
        False, "native_counters_malformed")
    _unproven(tmp_path, run, "native_counters_malformed")
    absent = _status_run(tmp_path, "absent", latest=ABSENT_EXPORT, trace=_trace())  # the control: an older heartbeat
    assert _states(sanity_inputs(absent, TARGET, ROOT)) == {"report.json": "no_file", "latest.json": "absent"}
    assert sanity_inputs(absent, TARGET, ROOT)["decision_trace"]["complete"] is True

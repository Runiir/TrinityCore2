"""BWD 10N round 3, v4 review (P3): the Nefarian status reader keeps counts apart from completeness.

The reader (tools/raid_program/run_sanity_inputs.py) threw away the positive counters of a block with
``complete: false``. The native counters keep them as a lower bound (BotNefarianObservationCounters.h: an
uncovered live attempt keeps its counts) and run_sanity treats positives as evidence whatever the coverage,
so a recorded violation and the refusal diagnostics were lost (the trace fallback, when there was one, was the
only source). Now, as for Atramedes:
- a well-formed block that says ``complete: false`` (and one that claims completeness but whose observer missed a
  window edge) keeps its counts, bound to the judged capture's final status: its positives still block as
  violations, merged with the trace's counts, while ``decision_trace.complete`` stays False;
- an incomplete zero stays blocking (unproven); a block of another attempt or capture, or read before the
  window's end, contributes nothing.
"""

from __future__ import annotations

from tests.test_nefarian_observation_counters import ACTIVE, PILLAR, _block, _status, _status_run
from tests.test_round3_sanity_fixes import _claim
from tests.test_run_sanity import (BONE_ACTIVE, BONE_PILLAR, CAPTURE, NODE, ROOT, TARGET, WINDOW_END, WINDOW_START,
                                   _observation_findings, _trace)
from tools.raid_program.run_sanity_inputs import (
    BossWindow, has_observed_evidence, merge_lower_bounds, parse_status_observations, sanity_inputs,
    status_counters, status_observations,
)

REFUSED_COUNTS = {"3": {"hop:native_no_path": 40}}


def _boss() -> BossWindow:
    return BossWindow({"first_at_ms": WINDOW_START, "last_at_ms": WINDOW_END}, NODE, CAPTURE)


def _expected(active=0, pillar=0, refused=None) -> dict:
    return {ACTIVE: active, PILLAR: pillar, "move_refused": refused or {}}


# --- the reader --------------------------------------------------------------------------------------------------

def test_parse_keeps_the_counts_of_an_incomplete_block_apart_from_its_completeness():
    counts, state = parse_status_observations(_block(active=2, pillar=1, refused=REFUSED_COUNTS, complete=False))
    assert (state, counts) == ("incomplete", _expected(2, 1, REFUSED_COUNTS))
    assert parse_status_observations(_block(active=2)) == (_expected(2), "complete")      # the control
    # Not a JSON boolean: no lower bound (the state is unchanged); malformed counts: none either.
    assert parse_status_observations(_block(active=2, complete="true")) == (None, "incomplete")
    assert parse_status_observations({**_block(active=2, complete=False), ACTIVE: "2"}) == (None, "incomplete")
    assert parse_status_observations({**_block(complete=False), "move_refused": {"3": {"x": -1}}}) == (
        None, "incomplete")
    assert parse_status_observations({**_block(), ACTIVE: "2"}) == (None, "malformed")    # complete: still malformed


def test_status_counters_returns_the_lower_bound_of_the_judged_final_export(tmp_path):
    report = _status(_block(active=2, pillar=1, refused=REFUSED_COUNTS, complete=False))
    counts, proven, server = status_counters(tmp_path, report, _boss())
    assert counts == _expected(2, 1, REFUSED_COUNTS) and proven is False
    assert server["states"] == {"report.json": "incomplete"} and server["complete"] is False
    # The proof-only wrapper still refuses them.
    assert status_observations(tmp_path, report, _boss())[0] is None
    # The proven control.
    counts, proven, server = status_counters(tmp_path, _status(_block(active=2)), _boss())
    assert counts == _expected(2) and proven is True and server["complete"] is True


def test_the_counts_of_another_attempt_capture_or_read_time_are_not_evidence_of_this_kill(tmp_path):
    boss = _boss()
    for state, report in (
            ("attempt_mismatch", _status(_block(active=2, complete=False, attempt=1), attempt=2)),
            ("capture_mismatch", _status(_block(active=2, complete=False, epoch=CAPTURE["combat_log_epoch"] + 1))),
            ("before_window_end", _claim(active=2, complete=False, now_ms=WINDOW_END - 1)),
            ("no_snapshot_time", _status(_block(active=2, complete=False), now_ms=None))):
        payload = report if state != "no_snapshot_time" else {"status": {**report["status"], "world_update": {}}}
        counts, proven, _ = status_counters(tmp_path, payload, boss)
        assert counts is None and proven is False, state
    # An unknown window binds nothing either.
    assert status_counters(tmp_path, _status(_block(active=2, complete=False)),
                           BossWindow(None, NODE, CAPTURE))[0] is None


# --- the record -----------------------------------------------------------------------------------------------------

def test_a_recorded_violation_of_an_incomplete_block_still_blocks_as_a_violation(tmp_path):
    report = _status(_block(active=2, pillar=1, refused=REFUSED_COUNTS, complete=False))
    run = _status_run(tmp_path, "run", report=report)   # no retained trace: the status is the only source
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] == _expected(2, 1, REFUSED_COUNTS)
    trace = result["decision_trace"]
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == (
        "server_status", False, "native_counters_incomplete")
    assert trace["server_counters"]["states"] == {"report.json": "incomplete"}
    (row,) = _observation_findings(tmp_path, run)
    assert row["severity"] == "blocking" and row["evidence"][ACTIVE] == 2 and row["evidence"][PILLAR] == 1
    assert row["evidence"]["observation_source"] == "server_status"
    assert row["evidence"]["trace_incomplete_reason"] == "native_counters_incomplete"
    assert "server's status counters record 2 bone warrior(s)" in row["detail"]


def test_an_incomplete_zero_stays_blocking_and_keeps_its_reason(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block(complete=False)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] is None  # nothing to keep, nothing retained to count
    assert result["decision_trace"]["incomplete_reason"] == "native_counters_incomplete"
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"], row["evidence"]["reason"]) == (
        "blocking", "unproven", "native_counters_incomplete")
    # Dense retained rows of the same capture never vouch for it either (the v2 rule stays).
    dense = _status_run(tmp_path, "dense", report=_claim(complete=False), trace=_trace())
    result = sanity_inputs(dense, TARGET, ROOT)
    assert result["decision_trace"]["complete"] is False and result["decision_trace"]["retained_trace_complete"]
    (row,) = _observation_findings(tmp_path, dense, "dense")
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")


def test_the_refusal_diagnostics_of_an_incomplete_block_are_kept(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block(refused=REFUSED_COUNTS, complete=False)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] == _expected(refused=REFUSED_COUNTS)
    assert result["decision_trace"]["complete"] is False
    (row,) = _observation_findings(tmp_path, run)
    assert (row["severity"], row["evidence"]["status"]) == ("blocking", "unproven")  # the zero is still unproven


def test_native_and_trace_lower_bounds_are_merged_per_key(tmp_path):
    rows = _trace([(3, BONE_ACTIVE, "observation"), (2, BONE_PILLAR, "observation"), (2, BONE_PILLAR, "observation"),
                   (3, "nefarian_move_refused:hop:native_no_path", "refused"), (1, "nefarian_move_refused:hop:x", "refused")])
    report = _claim(active=0, pillar=1, refused={"3": {"hop:native_no_path": 40}}, complete=False)
    run = _status_run(tmp_path, "run", report=report, trace=rows)
    observations = sanity_inputs(run, TARGET, ROOT)["nefarian_observations"]
    assert observations[ACTIVE] == 1                                  # the trace's, the native block has 0
    assert observations[PILLAR] == 2                                  # the trace's 2 rows beat the native 1
    assert observations["move_refused"]["3"] == {"hop:native_no_path": 40}  # the native's uncoalesced 40 beat 1
    assert observations["move_refused"]["1"] == {"hop:x": 1}          # only the trace has this actor
    unit = merge_lower_bounds(_expected(1, 0, {"3": {"a": 5}}), _expected(0, 4, {"3": {"a": 2, "b": 1}}))
    assert unit == _expected(1, 4, {"3": {"a": 5, "b": 1}})
    assert merge_lower_bounds(_expected(3), None) == _expected(3)
    assert not has_observed_evidence(_expected()) and has_observed_evidence(_expected(pillar=1))
    assert has_observed_evidence(_expected(refused={"3": {"a": 1}})) and not has_observed_evidence(None)


def test_a_block_that_claims_completeness_but_missed_the_window_keeps_its_violation(tmp_path):
    report = _status(_block(active=1, first=WINDOW_START, last=WINDOW_START + 500))
    run = _status_run(tmp_path, "run", report=report)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"][ACTIVE] == 1
    trace = result["decision_trace"]
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == (
        "server_status", False, "native_counters_observation_ended_before_window")
    (row,) = _observation_findings(tmp_path, run)
    assert row["severity"] == "blocking" and row["evidence"][ACTIVE] == 1


def test_a_proven_block_is_unchanged(tmp_path):
    run = _status_run(tmp_path, "run", report=_status(_block(active=2, refused=REFUSED_COUNTS)))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["nefarian_observations"] == _expected(2, 0, REFUSED_COUNTS)
    trace = result["decision_trace"]
    assert (trace["source"], trace["complete"], trace["incomplete_reason"]) == ("server_status", True, None)
    (row,) = _observation_findings(tmp_path, run)
    assert row["severity"] == "blocking" and row["evidence"][ACTIVE] == 2
    assert _observation_findings(tmp_path / "zero", _status_run(tmp_path / "zero", "run", report=_status(_block()))) == []

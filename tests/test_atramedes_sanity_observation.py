"""BWD 10N round 3 fix (Atramedes): the kiter Sound bound is a fail-closed acceptance observation.

Review finding (scoreboard/research review, item 5): breath_speed_scaling_with_sound was closed for 10N
although every measured WCL chase had its kiter at 0-10 Sound. User decision 2026-09-30 ("Bound kiter
Sound"): keep the time-only ramp and accept a 10N kill only when the tracked kiter stays at 10 Sound or less
during every air-phase chase. run_sanity_inputs extracts the server's encounter_observations.atramedes block
of the judged attempt's final status (the Nefarian attempt/final-window rules) into
sanity_inputs.atramedes_observations; run_sanity blocks a counted kill on a sample above 10, and on missing,
malformed, incomplete or chase-less evidence (unproven). The Nefarian path stays as it was.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_nefarian_observation_counters import _block as _nefarian_block
from tests.test_run_sanity import (CAPTURE, LABEL, NODE, ROOT, WINDOW_END, WINDOW_START, _hit, by_check, inputs, kill,
                                   make_root, sanity_findings, write_run, write_scoreboard)
from tools.raid_program import run_sanity
from tools.raid_program.run_sanity_inputs import atramedes_inputs, parse_atramedes_observations, sanity_inputs

SCENARIO = "blackwing_descent_10n_atramedes"
NEFARIAN = "blackwing_descent_10n_nefarian"
TARGET = {"encounter_route_node_id": NODE, "scenario": SCENARIO}
ABOVE = "samples_above_10"


def _counts(**changes) -> dict:
    """A clean attempt: two air phases, three chases, the loudest kiter sample at 9 Sound, fully sampled."""
    return {"air_phases": 2, "chases": 3, "chase_samples": 240, "max_kiter_sound": 9, ABOVE: 0,
            "max_sample_gap_ms": 250, "complete": True, **changes}


def _block(attempt=7, epoch=CAPTURE["combat_log_epoch"], first=WINDOW_START - 1_000, last=WINDOW_END + 1_000,
           **changes) -> dict:
    """The counter block of attempt `attempt` and start lifecycle `epoch` (None leaves the field out).

    `first` / `last` are the sampling's first and newest sample times (system ms, the combat log's clock; the
    default sampling spans the analysed boss window [WINDOW_START, WINDOW_END]; None leaves the field out)."""
    block = {**_counts(**changes), "attempt_id": attempt}
    block = block if epoch is None else {**block, "combat_log_epoch": epoch}
    block = block if first is None else {**block, "first_observed_at_ms": first}
    return block if last is None else {**block, "last_observed_at_ms": last}


def _status(block=None, *, attempt=7, now_ms=WINDOW_END + 50_000, nefarian=None, cohort=CAPTURE["cohort_id"],
            server=CAPTURE["server_epoch"]) -> dict:
    """A report/heartbeat payload whose status (cohort `cohort`, server epoch `server`, attempt `attempt`, read at
    `now_ms`) exports the blocks; the defaults are the identity of write_run's combat-log capture."""
    observations = {**({"nefarian": nefarian} if nefarian is not None else {}),
                    **({"atramedes": block} if block is not None else {})}
    return {"status": {"cohort_id": cohort, "server_epoch": server, "attempt_id": attempt,
                       "world_update": {"now_ms": now_ms},
                       "raid_runtime": {"server_epoch": server, "attempt_id": attempt,
                                        "encounter_observations": observations}}}


def _run(tmp_path: Path, name: str, *, report=None, latest=None) -> Path:
    run = write_run(tmp_path / name, [_hit(20_000, 1, 9_000)], report=report)
    if latest is not None:
        (run / "latest.json").write_text(json.dumps(latest))
    return run


def _findings(tmp_path: Path, document: dict | None, *, scenario=SCENARIO, duration=150.0, **fields) -> list[dict]:
    """acceptance_observation findings of one kill with the given sanity_inputs."""
    root = make_root(tmp_path / "root", scenario=scenario)
    record = kill("k1", scenario=scenario, duration=duration, **fields)
    if document is not None:
        record["sanity_inputs"] = document
    write_scoreboard(root, [record], scenario)
    return by_check(sanity_findings(root, scenario, LABEL)).get("acceptance_observation") or []


def _document(observations, server=None) -> dict:
    """The generic clean inputs with the Atramedes observation (and no Nefarian fields)."""
    document = {key: value for key, value in inputs().items() if key not in ("nefarian_observations", "decision_trace")}
    document["atramedes_observations"] = observations
    document["atramedes_server_counters"] = server or {"file": "report.json", "states": {"report.json": "complete"},
                                                       "complete": True, "attempt_id": 7}
    return document


# --- run_sanity_inputs: the final status of the judged attempt -----------------------------------------------

def test_the_final_status_block_is_extracted_with_its_attempt_and_read_time(tmp_path):
    run = _run(tmp_path, "run", report=_status(_block()))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] == _counts()
    server = result["atramedes_server_counters"]
    assert (server["file"], server["complete"], server["attempt_id"], server["states"]) == (
        "report.json", True, 7, {"report.json": "complete"})
    assert server["snapshot_now_ms"] == WINDOW_END + 50_000
    assert "nefarian_observations" not in result and "decision_trace" not in result
    assert _findings(tmp_path, result) == []


def test_an_incomplete_final_block_keeps_its_counts_with_complete_false(tmp_path):
    run = _run(tmp_path, "run", report=_status(_block(complete=False, **{ABOVE: 2, "max_kiter_sound": 16})))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"]["complete"] is False
    assert result["atramedes_server_counters"]["states"] == {"report.json": "incomplete"}
    (row,) = _findings(tmp_path, result)
    assert (row["severity"], row["evidence"][ABOVE]) == ("blocking", 2)  # a count above the bound is evidence


@pytest.mark.parametrize("report, state", [
    ({"status": {"raid_runtime": {}}}, "absent"),                              # an older build: no block
    (_status(_block(attempt=6)), "attempt_mismatch"),                          # another attempt's counters
    ({**_status(_block()), "status": {**_status(_block())["status"], "attempt_id": 8}}, "attempt_mismatch"),
    (_status(_block(), now_ms=WINDOW_END - 1), "before_window_end"),           # read before the window closed
    ({"status": {**_status(_block())["status"], "world_update": {}}}, "no_snapshot_time"),
    (_status(_block(attempt=8), attempt=8), "capture_mismatch"),               # a later attempt's consistent export
    (_status(_block(epoch=4)), "capture_mismatch"),                            # another start lifecycle
    (_status(_block(epoch=None)), "capture_identity_missing"),                 # no lifecycle in the export
    (_status([1]), "malformed"),
    (_status({**_block(), "chases": "3"}), "malformed"),
    (_status({**_block(), "complete": "true"}), "malformed"),
    (_status({key: value for key, value in _block().items() if key != ABOVE}), "malformed"),
])
def test_an_unusable_final_block_is_no_evidence_and_blocks(tmp_path, report, state):
    run = _run(tmp_path, "run", report=report)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] is None
    assert result["atramedes_server_counters"]["states"] == {"report.json": state}
    (row,) = _findings(tmp_path, result)
    assert (row["severity"], row["evidence"]["status"], row["evidence"]["reason"]) == (
        "blocking", "unproven", "no_final_status_block")
    assert state in row["detail"] and "not a pass" in row["detail"]


# --- the judged capture: cohort, server, attempt and combat-log lifecycle (the Nefarian binding) -------------------

@pytest.mark.parametrize("field, changes", [
    ("cohort_id", {"cohort": "shard-other"}),
    ("server_epoch", {"server": CAPTURE["server_epoch"] + 1}),
    ("attempt_id", {"attempt": 8}),
    ("combat_log_epoch", {"epoch": CAPTURE["combat_log_epoch"] + 1}),
])
def test_the_counters_must_be_the_judged_captures_in_every_identity_field(tmp_path, field, changes):
    attempt, epoch = changes.get("attempt", 7), changes.get("epoch", CAPTURE["combat_log_epoch"])
    payload = _status(_block(attempt=attempt, epoch=epoch), attempt=attempt,
                      cohort=changes.get("cohort", CAPTURE["cohort_id"]),
                      server=changes.get("server", CAPTURE["server_epoch"]))
    run = _run(tmp_path, "run", report=payload)
    result = sanity_inputs(run, TARGET, ROOT)
    server = result["atramedes_server_counters"]
    assert result["atramedes_observations"] is None and server["states"] == {"report.json": "capture_mismatch"}
    assert (server["identity_conflicts"], server["identity_missing"]) == ([field], [])
    (row,) = _findings(tmp_path, result)
    assert (row["severity"], row["evidence"]["reason"], row["evidence"]["identity_conflicts"]) == (
        "blocking", "no_final_status_block", [field])


@pytest.mark.parametrize("field", ["cohort_id", "server_epoch", "attempt_id", "combat_log_epoch"])
def test_a_capture_that_does_not_identify_itself_proves_nothing(tmp_path, field):
    run = write_run(tmp_path / "run", [_hit(20_000, 1, 9_000)], report=_status(_block()),
                    capture={key: value for key, value in CAPTURE.items() if key != field})
    result = sanity_inputs(run, TARGET, ROOT)
    server = result["atramedes_server_counters"]
    assert result["atramedes_observations"] is None and server["states"] == {"report.json": "capture_identity_missing"}
    assert server["identity_missing"] == [field] and _findings(tmp_path, result)[0]["severity"] == "blocking"


def test_a_later_attempts_zero_counters_do_not_certify_the_judged_kill(tmp_path):
    """The Nefarian reviewer's scenario: the log is attempt 7's; the final status and counters say attempt 8."""
    run = _run(tmp_path, "run", report=_status(_block(attempt=8), attempt=8))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] is None
    (row,) = _findings(tmp_path, result)
    assert row["severity"] == "blocking" and row["evidence"]["status"] == "unproven"
    # the control: the same export of the judged attempt is the source and passes
    ok = sanity_inputs(_run(tmp_path, "ok", report=_status(_block())), TARGET, ROOT)
    assert ok["atramedes_observations"] == _counts() and _findings(tmp_path / "ok", ok) == []


@pytest.mark.parametrize("content", ['{"status": {"cohort_id": "shard-atr', "", "null", "[]"],
                         ids=["truncated", "empty", "null", "list"])
def test_a_present_but_unreadable_report_is_not_absent_and_the_heartbeat_is_not_used(tmp_path, content):
    run = _run(tmp_path, "run", latest=_status(_block()))
    (run / "report.json").write_text(content)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] is None
    assert result["atramedes_server_counters"]["states"] == {"report.json": "unreadable"}
    (row,) = _findings(tmp_path, result)
    assert (row["severity"], row["evidence"]["reason"]) == ("blocking", "no_final_status_block")
    assert "unreadable" in row["detail"]
    # an unreadable heartbeat of a run without a report is unreadable too, not a missing file
    heartbeat = _run(tmp_path, "heartbeat")
    (heartbeat / "latest.json").write_text(content)
    assert sanity_inputs(heartbeat, TARGET, ROOT)["atramedes_server_counters"]["states"] == {
        "report.json": "no_file", "latest.json": "unreadable"}


def test_an_older_heartbeat_never_stands_in_for_the_final_report(tmp_path):
    # The report has no block (or a malformed one); latest.json's zero is an older heartbeat: never used.
    for name, report in (("absent", {"status": {"raid_runtime": {}}}), ("malformed", _status({"chases": -1}))):
        run = _run(tmp_path, name, report=report, latest=_status(_block()))
        observations, server = atramedes_inputs(run, None, None)
        assert observations is None and list(server["states"]) == ["report.json"]
    # Without a report, the final heartbeat is the export (still judged by attempt and read time).
    run = _run(tmp_path, "no-report", latest=_status(_block()))
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] == _counts()
    assert result["atramedes_server_counters"]["states"] == {"report.json": "no_file", "latest.json": "complete"}


def test_the_blocks_of_the_two_encounters_never_mix(tmp_path):
    both = _status(_block(**{ABOVE: 1, "max_kiter_sound": 13}), nefarian=_nefarian_block(active=2, attempt=7))
    run = _run(tmp_path, "run", report=both)
    atramedes = sanity_inputs(run, TARGET, ROOT)
    assert atramedes["atramedes_observations"][ABOVE] == 1 and "nefarian_observations" not in atramedes
    nefarian = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": NEFARIAN}, ROOT)
    assert nefarian["nefarian_observations"]["bone_warrior_active_over_45s"] == 2
    assert "atramedes_observations" not in nefarian
    other = sanity_inputs(run, {"encounter_route_node_id": NODE, "scenario": "blackwing_descent_10n_magmaw"}, ROOT)
    assert "atramedes_observations" not in other and "nefarian_observations" not in other


def test_the_extraction_never_costs_the_record_its_other_inputs(tmp_path, monkeypatch):
    from tools.raid_program import run_sanity_inputs

    def broken(*args, **kwargs):
        raise KeyError("status")
    monkeypatch.setattr(run_sanity_inputs, "atramedes_inputs", broken)
    result = sanity_inputs(_run(tmp_path, "run", report=_status(_block())), TARGET, ROOT)
    assert result["atramedes_observations"] is None and "KeyError" in result["atramedes_server_counters"]["error"]
    assert {"deaths", "revives", "health_half", "combat_log"} <= set(result)
    (row,) = _findings(tmp_path, result)
    assert row["evidence"]["status"] == "unproven"


def test_parse_atramedes_observations_states():
    assert parse_atramedes_observations(None) == (None, "absent")
    assert parse_atramedes_observations("x") == (None, "malformed")
    assert parse_atramedes_observations({**_block(), "chase_samples": True}) == (None, "malformed")
    assert parse_atramedes_observations({**_block(), "max_sample_gap_ms": None}) == (None, "malformed")
    assert parse_atramedes_observations(_block()) == (_counts(), "complete")
    assert parse_atramedes_observations(_block(complete=False))[1] == "incomplete"


# --- run_sanity: the bound blocks, unproven evidence blocks, an in-bound kill passes ---------------------------

def test_a_correct_in_bound_kill_passes(tmp_path):
    assert _findings(tmp_path, _document(_counts())) == []
    # 10 Sound is inside the bound; a short kill that never lifted off needs no chase.
    assert _findings(tmp_path / "ten", _document(_counts(max_kiter_sound=10))) == []
    assert _findings(tmp_path / "short", _document(_counts(air_phases=0, chases=0, chase_samples=0,
                                                           max_kiter_sound=0)), duration=80.0) == []


@pytest.mark.parametrize("above, loudest", [(1, 11), (4, 13), (37, 60)])
def test_a_kiter_sample_above_ten_is_one_blocking_finding(tmp_path, above, loudest):
    for name, complete in (("complete", True), ("incomplete", False)):
        rows = _findings(tmp_path / name, _document(_counts(**{ABOVE: above, "max_kiter_sound": loudest},
                                                            complete=complete)))
        assert [(row["severity"], row["kill_id"]) for row in rows] == [("blocking", "k1")]
        assert (rows[0]["evidence"][ABOVE], rows[0]["evidence"]["max_kiter_sound"]) == (above, loudest)
        assert "above 10 Sound" in rows[0]["detail"] and "Bound kiter Sound" in rows[0]["detail"]


def test_an_uncounted_kill_downgrades_the_bound_to_warn_and_drops_missing_evidence(tmp_path):
    stalled = {"valid_for_dps": False, "reasons": ["boss_window_stall_too_long"], "stalled_sec": 4.0,
               "max_stall_sec": 4.0, "stall_fraction": 0.004, "thresholds": {"max_boss_window_stall_fraction": 0.02}}
    rows = _findings(tmp_path, _document(_counts(**{ABOVE: 1, "max_kiter_sound": 13})), measurement_validity=stalled)
    assert [row["severity"] for row in rows] == ["warn"] and rows[0]["evidence"]["counted"] is False
    assert _findings(tmp_path / "missing", _document(None), measurement_validity=stalled) == []


UNPROVEN_CASES = {
    "field absent": (lambda: {key: value for key, value in _document(_counts()).items()
                              if key not in ("atramedes_observations", "atramedes_server_counters")}, "no_field"),
    "no final block": (lambda: _document(None, {"file": None, "states": {"report.json": "attempt_mismatch"},
                                                "complete": False}), "no_final_status_block"),
    "not complete": (lambda: _document(_counts(complete=False)), "incomplete"),
    "complete missing": (lambda: _document({key: value for key, value in _counts().items() if key != "complete"}),
                         "incomplete"),
    "complete a string": (lambda: _document(_counts(complete="true")), "incomplete"),
    "count missing": (lambda: _document({key: value for key, value in _counts().items() if key != ABOVE}),
                      "malformed"),
    "count a string": (lambda: _document(_counts(chases="3")), "malformed"),
    "count negative": (lambda: _document(_counts(chase_samples=-1)), "malformed"),
    "loud but none above": (lambda: _document(_counts(max_kiter_sound=14)), "malformed"),
    "chases without samples": (lambda: _document(_counts(chase_samples=0)), "malformed"),
    "chases without an air phase": (lambda: _document(_counts(air_phases=0)), "malformed"),
    "air phase without a chase": (lambda: _document(_counts(chases=0, chase_samples=0, max_kiter_sound=0)),
                                  "no_chase_observed"),
    "no air phase in a long kill": (lambda: _document(_counts(air_phases=0, chases=0, chase_samples=0,
                                                              max_kiter_sound=0)), "no_chase_observed"),
    "no inputs at all": (lambda: None, "no_field"),
}


@pytest.mark.parametrize("case", list(UNPROVEN_CASES))
def test_unavailable_or_unproven_evidence_is_a_blocking_finding(tmp_path, case):
    factory, reason = UNPROVEN_CASES[case]
    rows = _findings(tmp_path, factory())
    assert [(row["severity"], row["evidence"]["status"], row["evidence"]["reason"]) for row in rows] == [
        ("blocking", "unproven", reason)]
    assert "Atramedes acceptance observation is unproven" in rows[0]["detail"] and "not a pass" in rows[0]["detail"]


def test_the_air_phase_limit_follows_the_native_liftoff():
    # EVENT_LIFTOFF 1min + 31s after the pull; WCL 10N first air Tracking 95.1-95.4 s.
    assert run_sanity.AIR_PHASE_CERTAIN_AFTER_SEC == 110.0
    assert run_sanity.ATRAMEDES_SOUND_BOUND == 10
    source = (ROOT / "src/server/scripts/EasternKingdoms/BlackrockMountain/BlackwingDescent/boss_atramedes.cpp")
    assert "events.ScheduleEvent(EVENT_LIFTOFF, 1min + 31s, 0, PHASE_GROUND);" in source.read_text()


def test_the_nefarian_scenario_never_gets_the_atramedes_check(tmp_path):
    loud = _counts(**{ABOVE: 5, "max_kiter_sound": 25})
    nefarian = {**inputs(), "atramedes_observations": loud}
    assert _findings(tmp_path / "n", nefarian, scenario=NEFARIAN) == []
    # And the Atramedes scenario never gets the Nefarian one: bone-warrior counts there mean nothing.
    atramedes = {**_document(_counts()), "nefarian_observations": {"bone_warrior_active_over_45s": 3,
                                                                    "bone_warrior_on_pillar": 1, "move_refused": {}}}
    assert _findings(tmp_path / "a", atramedes) == []
    for scenario in ("blackwing_descent_10n_magmaw", "blackwing_descent_25n_atramedes"):
        assert _findings(tmp_path / scenario, _document(loud), scenario=scenario) == []


def test_the_stored_round_two_atramedes_records_now_block_on_the_missing_evidence():
    from tests.test_run_sanity import R02, _stored
    findings = [row for row in _stored(SCENARIO, R02) if row["check"] == "acceptance_observation"]
    assert findings and {(row["severity"], row["evidence"]["reason"]) for row in findings} == {("blocking", "no_field")}


# --- (v3 review) a present but unusable observation container is malformed, never absent --------------------------

def _observations(value) -> dict:
    return {"status": {"raid_runtime": {"encounter_observations": value}}}


MALFORMED_CONTAINERS = {
    "atramedes null": _observations({"atramedes": None}),
    "atramedes list": _observations({"atramedes": [1]}),
    "observations null": _observations(None),
    "observations list": _observations([]),
    "observations number": _observations(42),
    "runtime null": {"status": {"raid_runtime": None}},
    "runtime list": {"status": {"raid_runtime": []}},
    "status null": {"status": None},
    "status list": {"status": []},
}
ABSENT_BLOCKS = {
    "no status key": {}, "status without runtime": {"status": {}},
    "runtime without observations": {"status": {"raid_runtime": {}}},
    "observations without atramedes": _observations({}),
    "nefarian block only": _observations({"nefarian": _nefarian_block()}),
}


@pytest.mark.parametrize("report", list(MALFORMED_CONTAINERS.values()), ids=list(MALFORMED_CONTAINERS))
def test_a_present_but_unusable_container_is_malformed_not_absent(tmp_path, report):
    run = _run(tmp_path, "run", report=report)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] is None
    assert result["atramedes_server_counters"]["states"] == {"report.json": "malformed"}
    assert result["atramedes_server_counters"]["complete"] is False
    (row,) = _findings(tmp_path, result)
    assert (row["severity"], row["evidence"]["status"], row["evidence"]["reason"]) == (
        "blocking", "unproven", "no_final_status_block")
    assert "malformed" in row["detail"]


@pytest.mark.parametrize("report", list(ABSENT_BLOCKS.values()), ids=list(ABSENT_BLOCKS))
def test_a_genuinely_missing_block_stays_absent(tmp_path, report):
    """The control: a status whose keys lack the block (an older build) is absent, and still blocks (no fallback)."""
    run = _run(tmp_path, "run", report=report)
    result = sanity_inputs(run, TARGET, ROOT)
    assert result["atramedes_observations"] is None
    assert result["atramedes_server_counters"]["states"] == {"report.json": "absent"}
    (row,) = _findings(tmp_path, result)
    assert (row["severity"], row["evidence"]["reason"]) == ("blocking", "no_final_status_block")


def test_an_unusable_heartbeat_container_is_malformed_when_the_run_has_no_report(tmp_path):
    run = _run(tmp_path, "run", latest=MALFORMED_CONTAINERS["atramedes null"])
    states = sanity_inputs(run, TARGET, ROOT)["atramedes_server_counters"]["states"]
    assert states == {"report.json": "no_file", "latest.json": "malformed"}
    absent = _run(tmp_path, "absent", latest={"status": {"raid_runtime": {}}})
    assert sanity_inputs(absent, TARGET, ROOT)["atramedes_server_counters"]["states"] == {
        "report.json": "no_file", "latest.json": "absent"}


def test_parse_atramedes_observations_treats_the_unusable_block_as_malformed():
    from tools.raid_program.run_sanity_inputs import UNUSABLE_BLOCK, status_block
    assert status_block(MALFORMED_CONTAINERS["atramedes null"], "atramedes") is UNUSABLE_BLOCK
    assert status_block(_status(_block()), "atramedes") == _block()
    assert parse_atramedes_observations(UNUSABLE_BLOCK) == (None, "malformed")
    assert parse_atramedes_observations(status_block({"status": {"raid_runtime": {}}}, "atramedes")) == (None, "absent")

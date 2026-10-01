"""Round-4 coordinator fix 3 (diag_r3 Q2): a diagnosis formed before the latest revive is not a live error.

Round 3 Magmaw (every batch): the Felguard pulled Magmaw during the drudge step, the raid wiped, the
full-wipe recovery revived everyone, and the next heartbeat read the bots' pre-death diagnosis
(``future_encounter_target_forbidden``, no decision for 72 s) as ``bot_diagnosis_error``, a terminal
``machine_failure_predicate`` about 30 s after the recovery.
"""
from __future__ import annotations

from pathlib import Path

from tools.bot_ml import run_live_bot_validation as harness

REVIVED_AT = 1_790_800_125_000
DIED_AT = REVIVED_AT - 60_000
GUIDS = (30101, 30102)


def _status(revived_at: int = REVIVED_AT) -> dict:
    members = [{"guid": guid, "native_death_count": 1, "native_resurrection_count": 1,
                "native_last_death_ms": DIED_AT, "native_last_resurrection_ms": revived_at, "native_dead": False}
               for guid in GUIDS]
    return {"active_bots": 2, "target_bots": 2, "decisions": 50,
            "raid_runtime": {"native_recovery": {"members": members}}}


def _row(guid: int, last_decision_ms: int, *, code: str = "blocked_no_fallback",
         blocked_start_ms: int | None = None) -> dict:
    runtime = {"last_decision_tick_ms": last_decision_ms, "time_since_last_decision_ms": 71_732}
    if code == "blocked_no_fallback":
        runtime["blocked_start_ms"] = last_decision_ms if blocked_start_ms is None else blocked_start_ms
    return {"identity": {"bot_guid": guid, "bot_name": f"Bot{guid}"},
            "snapshot": {"runtime": runtime},
            "diagnosis": {"severity": "error", "diagnosis_code": code,
                          "blocker": "future_encounter_target_forbidden", "evidence": []}}


def _labels(status: dict, diagnosis: dict) -> tuple[dict, list[str]]:
    evidence = harness.live_evidence(status, diagnosis, {}, {}, None, "")
    labels = harness.validation_failure_labels(0, False, 2, 2, 5, len(harness.diagnosis_rows(diagnosis)), [],
                                               evidence)
    return evidence, labels


def test_a_pre_revive_diagnosis_is_stale_and_no_error():
    diagnosis = {"bots": [_row(guid, DIED_AT - 12_000) for guid in GUIDS]}
    evidence, labels = _labels(_status(), diagnosis)
    assert evidence["error_diagnoses"] == 2
    assert evidence["stale_error_diagnoses_before_revive"] == 2
    assert evidence["actionable_error_diagnoses"] == 0
    assert "bot_diagnosis_error" not in labels


def test_an_error_formed_after_the_revive_still_counts():
    diagnosis = {"bots": [_row(GUIDS[0], REVIVED_AT + 5_000), _row(GUIDS[1], DIED_AT - 12_000)]}
    evidence, labels = _labels(_status(), diagnosis)
    assert evidence["stale_error_diagnoses_before_revive"] == 1
    assert evidence["actionable_error_diagnoses"] == 1
    assert "bot_diagnosis_error" in labels


def test_without_a_native_resurrection_every_error_counts():
    status = _status()
    for member in status["raid_runtime"]["native_recovery"]["members"]:
        member["native_last_resurrection_ms"] = 0
    diagnosis = {"bots": [_row(guid, DIED_AT - 12_000) for guid in GUIDS]}
    evidence, labels = _labels(status, diagnosis)
    assert evidence["actionable_error_diagnoses"] == 2 and "bot_diagnosis_error" in labels
    # no status at all, or a row without a decision time: nothing is discounted (fail closed)
    assert harness.latest_native_resurrection_ms({}) == {}
    assert not harness.diagnosis_predates_revive({"identity": {"bot_guid": GUIDS[0]}}, {GUIDS[0]: REVIVED_AT})


def test_a_fresh_infrastructure_error_after_the_revive_always_counts():
    """Reviewer reproduction (round-4 finding 3): the bot's last decision precedes its revive, then it
    detaches from the world before deciding again. bot_loaded_not_in_world is recomputed from current
    state, so the old decision time says nothing about it; it must stay actionable."""
    for code in ("bot_loaded_not_in_world", "bot_not_loaded", "validation_cohort_instance_violation",
                 "route_destination_unreachable"):
        diagnosis = {"bots": [_row(GUIDS[0], DIED_AT - 12_000, code=code),
                              _row(GUIDS[1], DIED_AT - 12_000)]}
        evidence, labels = _labels(_status(), diagnosis)
        assert evidence["error_diagnoses"] == 2
        assert evidence["stale_error_diagnoses_before_revive"] == 1, code  # only the pre-revive blocker
        assert evidence["actionable_error_diagnoses"] == 1, code
        # bot_not_loaded is reported through its own lifecycle label first; the rest as diagnosis errors
        assert ("bot_lifecycle_not_loaded" if code == "bot_not_loaded" else "bot_diagnosis_error") in labels, code


def test_a_blocker_is_stale_only_when_its_episode_and_last_decision_both_predate_the_revive():
    revived = {GUIDS[0]: REVIVED_AT}
    stale = _row(GUIDS[0], DIED_AT - 12_000)
    assert harness.diagnosis_predates_revive(stale, revived)
    # blocked again after the revive (a new episode), even without a new decision
    assert not harness.diagnosis_predates_revive(
        _row(GUIDS[0], DIED_AT - 12_000, blocked_start_ms=REVIVED_AT + 1), revived)
    # decided after the revive while the old episode is still latched
    assert not harness.diagnosis_predates_revive(
        _row(GUIDS[0], REVIVED_AT + 1, blocked_start_ms=DIED_AT - 12_000), revived)
    # an older server without blocked_start_ms: not demonstrably stale (fail closed)
    legacy = _row(GUIDS[0], DIED_AT - 12_000)
    del legacy["snapshot"]["runtime"]["blocked_start_ms"]
    assert not harness.diagnosis_predates_revive(legacy, revived)


def test_the_blocked_episode_start_is_exported_with_the_decision_time():
    source = (Path(__file__).resolve().parents[1]
              / "src/server/game/Bots/BotWorldPopulationMgrDiagnosis.cpp").read_text(encoding="utf-8")
    decision = source.index('",\\"last_decision_tick_ms\\":" << state.LastDecisionTickMs')
    blocked = source.index('",\\"blocked_start_ms\\":" << (state.Blocked ? state.BlockedStartMs : uint64(0))')
    assert 0 < blocked - decision < 400

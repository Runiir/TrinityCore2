import copy

import pytest

from tools.raid_program.capture_evidence_demux import (
    _trace_actor_transport_rejections,
    evidence_demux_report,
)
from tools.raid_program.capture_magmaw_personal_threat_episode import (
    REQUIRED_FIELDS,
    personal_threat_episode_join_report,
)


TARGET = {
    "actor_guid": 30008,
    "scope_key": "magmaw-scope",
    "route_node_id": "bwd.magmaw.encounter",
    "route_generation": 3,
    "parent_wave_generation": (1 << 63) | 1,
    "parent_generation_authoritative": False,
}


def _record(edge: str) -> dict:
    falling = edge == "falling"
    return {
        "actor_guid": 30008,
        "scope_key": "magmaw-scope",
        "route_node_id": "bwd.magmaw.encounter",
        "route_generation": 3,
        "board_revision": 261 if falling else 265,
        "observed_at_ms": 261000 if falling else 265000,
        "facts_authoritative": True,
        "authority_gap_mask": 0,
        "personal_threat_present": not falling,
        "personal_threat_guid": 0 if falling else 91008,
        "prior_episode_open": falling,
        "new_episode_open": not falling,
        "edge": edge,
        "parent_wave_generation": (1 << 63) | 1,
        "parent_generation_authoritative": False,
        "prior_task_generation": 5,
        "new_task_generation": 5 if falling else 6,
        "prior_candidate_generation": 6,
        "new_candidate_generation": 6 if falling else 7,
    }


def _diagnosis(sequence: int, records: list[dict]) -> dict:
    return {
        "capture_sequence": sequence,
        "payload": {
            "action": "botauto_diagnose",
            "bots": [{
                "identity": {"bot_guid": 30008},
                "diagnosis": {
                    "magmaw_personal_parasite_escape": {
                        "personal_threat_episode_transitions": records,
                    },
                },
            }],
        },
    }


def _complete_rows() -> list[dict]:
    falling = _record("falling")
    rising = _record("rising")
    return [
        _diagnosis(1, [falling]),
        _diagnosis(9, [falling, rising]),
    ]


def test_complete_join_is_deduplicated_and_all_required_fields_survive():
    report = personal_threat_episode_join_report(
        _complete_rows(), target=TARGET,
    )
    assert report["gate_passed"] is True
    assert report["falling_count"] == report["rising_count"] == 1
    assert len(report["records"]) == 2
    assert all(set(REQUIRED_FIELDS) <= set(record) for record in report["records"])
    falling, rising = report["records"]
    assert falling["new_task_generation"] == rising["prior_task_generation"]
    assert rising["new_task_generation"] == falling["new_task_generation"] + 1
    assert rising["new_candidate_generation"] > rising["prior_candidate_generation"]


def test_ordinary_capture_is_compatible_but_requested_join_fails_closed():
    rows = [_diagnosis(1, [])]
    assert personal_threat_episode_join_report(rows, target=None)["gate_passed"] is True
    requested = personal_threat_episode_join_report(rows, target=TARGET)
    assert requested["gate_passed"] is False
    assert requested["rejections"] == [
        "magmaw_personal_threat_episode_complete_sequence_missing"
    ]


@pytest.mark.parametrize(
    ("location", "field", "value", "reason"),
    [
        ("falling", "actor_guid", 30009,
         "magmaw_personal_threat_episode_cross_actor"),
        ("falling", "scope_key", "other-scope",
         "magmaw_personal_threat_episode_cross_scope"),
        ("rising", "parent_wave_generation", (1 << 63) | 2,
         "magmaw_personal_threat_episode_cross_parent"),
        ("falling", "facts_authoritative", False,
         "magmaw_personal_threat_episode_record_non_authoritative"),
        ("rising", "authority_gap_mask", 4,
         "magmaw_personal_threat_episode_record_non_authoritative"),
        ("rising", "board_revision", 260,
         "magmaw_personal_threat_episode_nonmonotonic"),
        ("rising", "prior_task_generation", 4,
         "magmaw_personal_threat_episode_rising_contradiction"),
        ("falling", "personal_threat_present", True,
         "magmaw_personal_threat_episode_record_threat_contradiction"),
    ],
)
def test_join_rejects_cross_identity_authority_and_contradictions(
    location: str, field: str, value, reason: str,
):
    records = [_record("falling"), _record("rising")]
    records[0 if location == "falling" else 1][field] = value
    report = personal_threat_episode_join_report(
        [_diagnosis(1, records)], target=TARGET,
    )
    assert report["gate_passed"] is False
    assert reason in report["rejections"]


def test_missing_and_malformed_records_fail_closed():
    missing = _record("falling")
    del missing["observed_at_ms"]
    report = personal_threat_episode_join_report(
        [_diagnosis(1, [missing, _record("rising")])], target=TARGET,
    )
    assert "magmaw_personal_threat_episode_record_missing_fields" in report["rejections"]
    malformed = _diagnosis(1, [])
    malformed["payload"]["bots"][0]["diagnosis"][
        "magmaw_personal_parasite_escape"
    ]["personal_threat_episode_transitions"] = {}
    report = personal_threat_episode_join_report([malformed], target=TARGET)
    assert report["rejections"][0] == "magmaw_personal_threat_episode_records_malformed"
    missing_container = _diagnosis(1, [])
    del missing_container["payload"]["bots"][0]["diagnosis"][
        "magmaw_personal_parasite_escape"
    ]["personal_threat_episode_transitions"]
    report = personal_threat_episode_join_report([missing_container], target=TARGET)
    assert report["rejections"][0] == "magmaw_personal_threat_episode_records_missing"


def test_more_than_ring_capacity_drains_losslessly_and_diagnosis_keeps_join():
    rows = []
    cursor = 0
    for batch_start in range(1, 141, 20):
        batch_end = min(batch_start + 19, 140)
        bot_row = {
            "bot_guid": 30008,
            "delta": True,
            "cursor_before": cursor,
            "cursor_after": batch_end,
            "gap": False,
            "entries": [
                {"sequence": sequence}
                for sequence in range(batch_start, batch_end + 1)
            ],
        }
        reasons, transport = _trace_actor_transport_rejections(bot_row)
        assert reasons == []
        assert transport["sequence_first"] == batch_start
        assert transport["sequence_last"] == batch_end
        assert "missing_sequence_start" not in transport
        rows.append({
            "capture_sequence": len(rows) + 1,
            "payload": {"action": "botauto_trace", "bots": [bot_row]},
        })
        cursor = batch_end
    rows.append(_diagnosis(len(rows) + 1, [_record("falling"), _record("rising")]))
    report = personal_threat_episode_join_report(rows, target=TARGET)
    assert cursor == 140
    assert report["gate_passed"] is True
    assert report["falling_count"] == report["rising_count"] == 1


def test_demux_exposes_opt_in_join_without_making_it_a_parallel_channel():
    report = evidence_demux_report(
        copy.deepcopy(_complete_rows()),
        profile_name="blackwing_descent_10n",
        controller_terminal=None,
        terminal_failure_validator=lambda *_args, **_kwargs: (None, []),
        personal_threat_episode_target=TARGET,
    )
    assert report["personal_threat_episode_join"]["gate_passed"] is True
    assert not any(
        reason.startswith("magmaw_personal_threat_episode")
        for reason in report["rejections"]
    )

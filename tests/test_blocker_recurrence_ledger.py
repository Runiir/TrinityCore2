from __future__ import annotations

import pytest

from tools.raid_program.blocker_recurrence_ledger import evaluate_ledger


def _ledger(
    runs: list[dict], *, limit: int = 10, signatures: dict | None = None
) -> dict:
    ledger = {
        "schema": "trinity_raid_blocker_recurrence_v1",
        "occurrence_limit": limit,
        "clear_streak_required": 2,
        "runs": runs,
    }
    if signatures is not None:
        ledger["causal_signatures"] = signatures
    return ledger


def test_intervening_absence_does_not_erase_recurring_blocker() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"drudge_contamination": "occurred"}},
                {"run_id": "102", "route_completed": False, "blockers": {"drudge_contamination": "absent"}},
                {"run_id": "103", "route_completed": False, "blockers": {"drudge_contamination": "occurred"}},
            ]
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["occurrence_count"] == 2
    assert blocker["occurrence_run_ids"] == ["101", "103"]
    assert blocker["open"] is True
    assert decision["acceptance_admitted"] is False


def test_only_two_completed_clean_routes_close_open_blocker() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"hazard_path": "occurred"}},
                {"run_id": "102", "route_completed": False, "blockers": {"hazard_path": "absent"}},
                {"run_id": "103", "route_completed": True, "blockers": {"hazard_path": "absent"}},
                {"run_id": "104", "route_completed": True, "blockers": {"hazard_path": "absent"}},
            ]
        )
    )

    assert decision["blockers"][0]["clean_full_clear_streak"] == 2
    assert decision["blockers"][0]["open"] is False
    assert decision["acceptance_admitted"] is True


def test_tenth_interleaved_occurrence_requires_stop() -> None:
    runs = []
    for index in range(19):
        runs.append(
            {
                "run_id": str(index + 1),
                "route_completed": False,
                "blockers": {
                    "parasite_lane_oscillation": (
                        "occurred" if index % 2 == 0 else "absent"
                    )
                },
            }
        )
    decision = evaluate_ledger(_ledger(runs))

    assert decision["blockers"][0]["occurrence_count"] == 10
    assert decision["stop_required"] is True
    assert decision["required_next_action"] == "stop_and_summarize_last_ten_occurrences"


def test_unassessed_signature_cannot_count_as_clean() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "route_completed": False, "blockers": {"pet_autocast_spam": "occurred"}},
                {"run_id": "102", "route_completed": True, "blockers": {}},
                {"run_id": "103", "route_completed": True, "blockers": {"pet_autocast_spam": "absent"}},
            ]
        )
    )

    assert decision["blockers"][0]["clean_full_clear_streak"] == 1
    assert decision["acceptance_admitted"] is False


def test_next_signature_prefers_most_recurrent_edge() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "blockers": {"rare_edge": "occurred", "recurring_edge": "occurred"}},
                {"run_id": "102", "blockers": {"rare_edge": "absent", "recurring_edge": "occurred"}},
                {"run_id": "103", "blockers": {"rare_edge": "occurred", "recurring_edge": "occurred"}},
            ]
        )
    )

    assert decision["next_causal_signature"] == "recurring_edge"


def test_latest_absent_open_signature_does_not_steal_repair_priority() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "blockers": {"old_edge": "occurred"}},
                {"run_id": "102", "blockers": {"old_edge": "occurred"}},
                {
                    "run_id": "103",
                    "blockers": {"old_edge": "absent", "live_edge": "occurred"},
                },
            ]
        )
    )

    old_edge = next(
        row for row in decision["blockers"]
        if row["causal_signature"] == "old_edge"
    )
    assert old_edge["open"] is True
    assert old_edge["last_observed_state"] == "absent"
    assert decision["next_causal_signature"] == "live_edge"
    assert decision["required_next_action"] == "repair_latest_recurring_causal_signature"


def test_open_signatures_latest_absent_require_clean_full_clear_not_repair() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "101", "blockers": {"intermittent_edge": "occurred"}},
                {"run_id": "102", "blockers": {"intermittent_edge": "absent"}},
            ]
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["open"] is True
    assert blocker["last_observed_run_id"] == "102"
    assert blocker["last_observed_state"] == "absent"
    assert decision["next_causal_signature"] is None
    assert decision["required_next_action"] == "run_clean_full_clear"


def test_rejects_duplicate_run_identity_and_unknown_state() -> None:
    with pytest.raises(ValueError, match="duplicate run_id"):
        evaluate_ledger(
            _ledger(
                [
                    {"run_id": "same", "blockers": {}},
                    {"run_id": "same", "blockers": {}},
                ]
            )
        )
    with pytest.raises(ValueError, match="invalid state"):
        evaluate_ledger(
            _ledger(
                [{"run_id": "one", "blockers": {"edge": "fixed"}}]
            )
        )


def test_child_recurrence_rolls_up_to_parent_once_per_run() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {
                    "run_id": "101",
                    "blockers": {"floor_probe": "occurred", "endpoint_z": "occurred"},
                },
                {"run_id": "102", "blockers": {"endpoint_z": "occurred"}},
            ],
            signatures={
                "native_path_proof": {},
                "floor_probe": {"parent": "native_path_proof"},
                "endpoint_z": {"parent": "native_path_proof"},
            },
        )
    )

    parent = next(
        row for row in decision["blockers"]
        if row["causal_signature"] == "native_path_proof"
    )
    assert parent["occurrence_count"] == 2
    assert parent["occurrence_run_ids"] == ["101", "102"]


def test_completed_architecture_review_preserves_history_but_reopens_budget() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": str(index), "blockers": {"shared_edge": "occurred"}}
                for index in range(1, 12)
            ],
            signatures={
                "shared_edge": {
                    "architecture_reviewed_through_occurrence_count": 10,
                }
            },
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["occurrence_count"] == 11
    assert blocker["architecture_reviewed_through_occurrence_count"] == 10
    assert blocker["unreviewed_occurrence_count"] == 1
    assert blocker["stop_required"] is False
    assert blocker["open"] is True


def test_live_recurrence_after_fixture_pass_stops_repairs_and_canaries() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "109", "blockers": {"parasite": "occurred"}},
                {"run_id": "110", "blockers": {"parasite": "occurred"}},
            ],
            signatures={
                "parasite": {
                    "architecture_reviewed_through_occurrence_count": 1,
                    "fixture_verifications": [
                        {
                            "passed_before_run_id": "110",
                            "evidence": "tests/parasite_replay.cpp::full_sequence",
                        }
                    ],
                }
            },
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["unreviewed_occurrence_count"] == 1
    assert blocker["recurrence_limit_stop"] is False
    assert blocker["retained_fixture_invalidated"] is True
    assert blocker["live_occurrences_after_fixture"] == ["110"]
    assert decision["stop_required"] is True
    assert decision["next_causal_signature"] == "parasite"
    assert decision["required_next_action"] == "expand_invalid_retained_fixture"


def test_fixture_verification_must_reference_a_known_run_and_evidence() -> None:
    with pytest.raises(ValueError, match="unknown boundary run_id"):
        evaluate_ledger(
            _ledger(
                [{"run_id": "110", "blockers": {"parasite": "occurred"}}],
                signatures={
                    "parasite": {
                        "fixture_verifications": [
                            {
                                "passed_before_run_id": "missing",
                                "evidence": "tests/parasite_replay.cpp",
                            }
                        ]
                    }
                },
            )
        )


def test_expanded_fixture_after_recurrence_reopens_only_clean_canary_gate() -> None:
    decision = evaluate_ledger(
        _ledger(
            [
                {"run_id": "109", "blockers": {"parasite": "occurred"}},
                {"run_id": "110", "blockers": {"parasite": "occurred"}},
            ],
            signatures={
                "parasite": {
                    "fixture_verifications": [
                        {
                            "passed_before_run_id": "110",
                            "evidence": "tests/endpoint_only.cpp",
                        },
                        {
                            "passed_after_run_id": "110",
                            "evidence": "tests/full_integration.cpp",
                        },
                    ]
                }
            },
        )
    )

    blocker = decision["blockers"][0]
    assert blocker["retained_fixture_invalidated"] is False
    assert blocker["fixture_verified_after_latest_occurrence"] is True
    assert decision["stop_required"] is False
    assert decision["next_causal_signature"] is None
    assert decision["required_next_action"] == "run_clean_full_clear"

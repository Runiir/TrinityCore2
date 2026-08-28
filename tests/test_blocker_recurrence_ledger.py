from __future__ import annotations

import pytest

from tools.raid_program.blocker_recurrence_ledger import evaluate_ledger


def _ledger(runs: list[dict], *, limit: int = 10) -> dict:
    return {
        "schema": "trinity_raid_blocker_recurrence_v1",
        "occurrence_limit": limit,
        "clear_streak_required": 2,
        "runs": runs,
    }


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

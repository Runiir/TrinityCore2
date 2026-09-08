"""Projection of run 88d35c0421 raw.jsonl capture sequences 95–97.

Only native strategy/route/transition fields are projected onto the established
accepted identity fixture; full original closed rows are replayed in the review.
"""
import copy
import json

import pytest

from tests.test_phase1_raid_foundation_capture import accepted_status
from tools.raid_program.capture_phase1_raid_foundation import (
    evidence_demux_rejections,
    normalized_batch_payload,
)

REJECTION = "evidence_demux_strategy_transition_without_route_advancement"
OLD = "trash_ground_danger_movement"
NEW = "trash_two_tank_charge_lanes"
INITIAL = "blackwing_descent_10n_magmaw_diagnostic"


def projected_rows():
    rows = []
    for strategy, generation, node, source, advanced in (
        (OLD, 2, 1, INITIAL, True),
        (OLD, 3, 2, INITIAL, False),
        (NEW, 3, 2, OLD, True),
    ):
        row = accepted_status()
        row["cohort_id"] = "raid"
        row["raid_runtime"].update(
            strategy_id=strategy,
            route_progress={"generation": generation, "node_index": node},
            strategy_transition={
                "from_strategy": source, "to_strategy": strategy,
                "advanced": advanced,
            },
        )
        rows.append(row)
    rows[0]["action"] = "botauto_trace"
    rows[2]["action"] = "botauto_trace"
    return rows


def rejections(rows):
    # A retained active status establishes canonical identity before seq95.
    bootstrap = copy.deepcopy(rows[0])
    bootstrap["action"] = "botauto_status"
    return evidence_demux_rejections(normalized_batch_payload(
        ("\n".join(json.dumps(row) for row in [bootstrap, *rows]) + "\n").encode()
    ))


def test_actual_pending_route_projection_accepts_strategy_binding():
    assert REJECTION not in rejections(projected_rows())


@pytest.mark.parametrize("mutation", ["no_advance", "false_from", "false_to", "regression", "second_transition"])
def test_pending_route_does_not_authorize_invalid_transitions(mutation):
    rows = projected_rows()
    runtime = rows[-1]["raid_runtime"]
    if mutation == "no_advance":
        for row in rows:
            row["raid_runtime"]["route_progress"] = {"generation": 2, "node_index": 1}
    elif mutation == "false_from":
        runtime["strategy_transition"]["from_strategy"] = INITIAL
    elif mutation == "false_to":
        runtime["strategy_transition"]["to_strategy"] = INITIAL
    elif mutation == "regression":
        runtime["route_progress"] = {"generation": 2, "node_index": 1}
    else:
        duplicate = copy.deepcopy(rows[-1])
        duplicate["raid_runtime"].update(strategy_id="third_strategy", strategy_transition={
            "from_strategy": NEW, "to_strategy": "third_strategy", "advanced": True,
        })
        rows.append(duplicate)
    assert REJECTION in rejections(rows)


def test_wrong_identity_pending_row_is_rejected():
    rows = projected_rows()
    rows[1]["cohort_id"] = "other"
    assert "evidence_demux_cross_identity_row" in rejections(rows)

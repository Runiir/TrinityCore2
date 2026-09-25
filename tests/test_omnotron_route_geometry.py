"""The Omnotron approach must not start or regroup on the next node's trash.

Round 2 batch 1 (blackwing_descent_10n-r02-b1-20260925T172051Z) provisioned all
ten c0 bots at the scenario start_position (-338.622, -347.5, 214.159), which is
Golem Sentry spawn 250049. The sentry is the pack entry of the next route node
(bwd.omnotron.sentries), so the future-encounter guard forbade fighting it while
the cohort stood on bwd.omnotron.regroup: 9 of 10 bots were dead at the first
heartbeat and the run ended in contamination and a progress plateau.
"""
from __future__ import annotations

import json
import math
import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCENARIOS = Path(os.environ.get("OMNOTRON_SCENARIOS_PATH",
                                ROOT / "experiments/configs/validation_scenarios_cata_001.json"))
# Golem Sentry (42800) spawns, TDB 434.22011 world.creature 250048/250049;
# stationary (MovementType 0), level 85 elite, hostile. Their aggro radius is at
# most 15 yd against a level-85 bot (Creature::GetAttackDistance: 15 - CombatReach);
# keep the approach well outside it.
GOLEM_SENTRIES = ((-311.602, -347.373), (-338.622, -347.5))
MINIMUM_SENTRY_DISTANCE = 35.0


def _rows() -> list[tuple[str, dict, dict]]:
    document = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    rows = []
    for key in ("scenarios", "diagnostic_scenarios"):
        for scenario in document[key]:
            for step in scenario.get("route", []):
                if step.get("node_id") == "bwd.omnotron.regroup":
                    rows.append((scenario["id"], scenario, step))
    return rows


def _sentry_distance(x: float, y: float) -> float:
    return min(math.hypot(x - sx, y - sy) for sx, sy in GOLEM_SENTRIES)


def test_every_omnotron_route_has_a_regroup_node() -> None:
    ids = {scenario_id for scenario_id, _, _ in _rows()}
    assert {"blackwing_descent_10n_omnotron_c0_diagnostic", "blackwing_descent_10n_full_c0"} <= ids


@pytest.mark.parametrize("scenario_id", sorted({row[0] for row in _rows()}))
def test_regroup_anchor_is_outside_golem_sentry_aggro(scenario_id: str) -> None:
    for sid, scenario, step in _rows():
        if sid != scenario_id:
            continue
        distance = _sentry_distance(step["x"], step["y"])
        assert distance >= MINIMUM_SENTRY_DISTANCE, (
            f"{scenario_id} bwd.omnotron.regroup at ({step['x']}, {step['y']}) is "
            f"{distance:.1f} yd from a Golem Sentry (next node's pack)")
        # Canonical cohorts spawn at their scenario start (use_saved_position).
        # The legacy 301xx diagnostic start moved with them in round 3 (fixture
        # regenerated); tools.raid_program.raid_shard_anchor_clearance checks it.
        if step.get("step") == 1 and scenario_id.endswith("_c0_diagnostic"):
            start = scenario["start_position"]
            start_distance = _sentry_distance(start["x"], start["y"])
            assert start_distance >= MINIMUM_SENTRY_DISTANCE, (
                f"{scenario_id} start_position is {start_distance:.1f} yd from a Golem Sentry; "
                "bots are provisioned there (use_saved_position)")

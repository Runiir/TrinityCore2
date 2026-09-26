"""The Omnotron approach must not start or regroup on the next node's trash.

Round 2 batch 1 (blackwing_descent_10n-r02-b1-20260925T172051Z) provisioned all
ten c0 bots at the scenario start_position (-338.622, -347.5, 214.159), which is
Golem Sentry spawn 250049. The sentry is the pack entry of the next route node
(bwd.omnotron.sentries), so the future-encounter guard forbade fighting it while
the cohort stood on bwd.omnotron.regroup: 9 of 10 bots were dead at the first
heartbeat and the run ended in contamination and a progress plateau.

Round 3 batch 1 (blackwing_descent_10n-r03-b1-20260925T200656Z): the encounter
node's anchor (-324.78, -399.078) is waypoint 2 of the powered-up construct's
patrol (path 4218600). Walking onto it, the raid body-pulled Arcanotron before
the pre-pull setup was done (Bwomnnbd meleed at the anchor at the first combat
event); the encounter then ran with every bot's cast lanes still held by the
setup candidate. The encounter rows now stage the raid on observed walkable
corridor ground outside the patrol's aggro.
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
# The construct the controller powers up first (EVENT_POWER_UP_FIRST_GOLEM picks
# one of the four at random) walks waypoint_data 4218600 back and forth
# (sql/old/custom/world/34_2020_02_21/custom_2019_08_20_00_world_updatepack.sql
# lines 131428-131431) with REACT_AGGRESSIVE. Constructs are level 88, above the
# expansion cap, so Creature::GetAttackDistance gives them 15 - CombatReach yd.
PATROL_PATH = ((-309.7726, -392.9861), (-324.7795, -399.0781), (-342.2674, -392.6615))
# Aggro plus a 15 yd margin for the raid's spread around the staging anchor.
MINIMUM_PATROL_DISTANCE = 30.0
# Pre-pot needs the live pull target: FindBossTarget searches 60 yd, and the
# route target search 220 yd. Keep every patrol point within 50 yd.
MAXIMUM_PATROL_REACH = 50.0
# Observed walkable: Bwomnnba walked (-336.08, -356.46, 213.871) on the way to
# the encounter in the round-3 Omnotron c0 trace (native_actor position).
STAGING = {"x": -336.08, "y": -356.46, "z": 213.871}


def _rows(node_id: str = "bwd.omnotron.regroup") -> list[tuple[str, dict, dict]]:
    document = json.loads(SCENARIOS.read_text(encoding="utf-8"))
    rows = []
    for key in ("scenarios", "diagnostic_scenarios"):
        for scenario in document[key]:
            for step in scenario.get("route", []):
                if step.get("node_id") == node_id:
                    rows.append((scenario["id"], scenario, step))
    return rows


def _segment_distance(point: tuple[float, float], start: tuple[float, float],
                      end: tuple[float, float]) -> float:
    dx, dy = end[0] - start[0], end[1] - start[1]
    projection = ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / (dx * dx + dy * dy)
    projection = min(1.0, max(0.0, projection))
    return math.hypot(point[0] - (start[0] + projection * dx), point[1] - (start[1] + projection * dy))


def _patrol_distance(x: float, y: float) -> float:
    return min(_segment_distance((x, y), PATROL_PATH[index], PATROL_PATH[index + 1])
               for index in range(len(PATROL_PATH) - 1))


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


ENCOUNTER_SCENARIOS = {
    "blackwing_descent_10n",
    "blackwing_descent_10n_full_c0",
    "blackwing_descent_10n_omnotron_diagnostic",
    "blackwing_descent_10n_omnotron_c0_diagnostic",
}


def test_every_omnotron_route_has_an_encounter_node() -> None:
    assert ENCOUNTER_SCENARIOS <= {scenario_id for scenario_id, _, _ in _rows("bwd.omnotron.encounter")}


def test_the_encounter_anchor_itself_is_on_the_patrol() -> None:
    # Documents the round-3 defect: the node's own position is patrol waypoint 2.
    for scenario_id, _, step in _rows("bwd.omnotron.encounter"):
        assert _patrol_distance(step["x"], step["y"]) < 1.0, scenario_id


@pytest.mark.parametrize("scenario_id", sorted(ENCOUNTER_SCENARIOS))
def test_encounter_staging_is_outside_the_construct_patrol(scenario_id: str) -> None:
    for sid, _, step in _rows("bwd.omnotron.encounter"):
        if sid != scenario_id:
            continue
        anchor = step.get("navigation_anchor")
        assert isinstance(anchor, dict), (
            f"{scenario_id} bwd.omnotron.encounter has no navigation_anchor: the raid walks onto "
            f"patrol waypoint ({step['x']}, {step['y']}) and body-pulls the powered-up construct")
        distance = _patrol_distance(anchor["x"], anchor["y"])
        assert distance >= MINIMUM_PATROL_DISTANCE, (
            f"{scenario_id} staging ({anchor['x']}, {anchor['y']}) is {distance:.1f} yd from the patrol")
        reach = max(math.hypot(anchor["x"] - x, anchor["y"] - y) for x, y in PATROL_PATH)
        assert reach <= MAXIMUM_PATROL_REACH, (
            f"{scenario_id} staging is {reach:.1f} yd from the farthest patrol point")
        assert {axis: anchor[axis] for axis in ("x", "y", "z")} == STAGING
        # Facing the room, so the pull starts toward the constructs.
        bearing = math.atan2(step["y"] - anchor["y"], step["x"] - anchor["x"]) % (2 * math.pi)
        assert abs(anchor["o"] - bearing) < 0.05

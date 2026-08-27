from __future__ import annotations

import math
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DRUDGE_GEOMETRY = ROOT / (
    "src/server/game/Bots/Content/Raids/BlackwingDescent/Trash/Drudge/"
    "BotWorldPopulationMgrValidationRouteDrudgeGeometry.cpp"
)


def test_minimum_distance_rejects_a_complete_corridor_that_misses_its_destination():
    source = DRUDGE_GEOMETRY.read_text(encoding="utf-8")

    path_check = source.index("PathGenerator path(Bot);")
    path_end = source.index("std::string raw = Manager.BuildRawJson", path_check)
    minimum_distance = source[path_check:path_end]

    # Run10's retained navmesh replay: the native corridor was complete, but
    # the requested point was 3.06 yards beyond the actual navmesh endpoint.
    requested = (-285.742, -73.2144)
    actual = (-288.8, -73.2144)
    assert math.dist(requested, actual) > 1.0

    assert "path.GetActualEndPosition()" in minimum_distance
    assert "path.SetUseStraightPath(true)" in minimum_distance
    assert "DrudgeMinimumDistanceEndpointToleranceYards" in minimum_distance
    assert "std::hypot(actualEnd.x - candidateX, actualEnd.y - candidateY)" in minimum_distance
    assert "Distance2d(actualEnd.x, actualEnd.y" in minimum_distance


def test_minimum_distance_endpoint_guard_stays_in_the_drudge_module():
    source = DRUDGE_GEOMETRY.read_text(encoding="utf-8")
    assert len(source.splitlines()) < 1000
    assert "MovePoint(" not in source


def test_established_entrance_combat_defers_failed_exit_to_lane_action():
    source = DRUDGE_GEOMETRY.read_text(encoding="utf-8")

    movement_attempt = source.index("moved = Manager.MoveBotToPoint")
    deferred_outcome = source.index(
        '"minimum_distance_exit_deferred_to_lane_combat"', movement_attempt
    )
    lane_fallback = source.index(
        "if (!moved && ordinaryEntranceCombat)\n        return false;",
        deferred_outcome,
    )
    target_override = source.index("Target = source;", lane_fallback)

    assert movement_attempt < deferred_outcome < lane_fallback < target_override
    assert '"minimum_distance_exit_failed"' in source[deferred_outcome:lane_fallback]

from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrMovement.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = (
    "MoveBotToPoint",
    "ValidationDescentPhaseName",
    "ExecuteNativeDescentIntent",
)


def test_movement_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrMovement.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_movement_module_preserves_native_path_admission() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for reason in (
        "movement_lease_invalid_scope",
        "route_destination_invalid_floor",
        "route_destination_partial_path",
        "route_destination_shortcut_path",
        "route_destination_off_mesh",
        "route_destination_recently_failed",
        "native_descent_complete_path_required",
        "native_descent_drop_policy_rejected",
    ):
        assert reason in module
    assert "PathGenerator" in module
    assert "BotExperienceLearningPolicy::ScorePath" in module


def test_movement_module_keeps_descent_evidence_states() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for phase in (
        "Unobserved",
        "Approaching",
        "Departed",
        "Falling",
        "Landed",
        "Ready",
        "Blocked",
    ):
        assert f"ValidationDescentPhase::{phase}" in module
    for event in (
        "native_descent_falling_observed",
        "native_descent_grounded_observed",
        "native_descent_ready",
        "native_descent_walk_segment_submitted",
    ):
        assert event in module

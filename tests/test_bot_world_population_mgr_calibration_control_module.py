from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORLD = ROOT / "src/server/game/Bots/BotWorldPopulationMgr.cpp"
MODULE = ROOT / "src/server/game/Bots/BotWorldPopulationMgrCalibrationControl.cpp"
CMAKE = ROOT / "src/server/game/CMakeLists.txt"


MOVED_METHODS = ("StartCombatCalibration", "StopCombatCalibration")


def test_calibration_control_module_is_narrow_and_registered() -> None:
    module = MODULE.read_text(encoding="utf-8")
    world = WORLD.read_text(encoding="utf-8")
    assert len(module.splitlines()) <= 1000
    assert "Bots/BotWorldPopulationMgrCalibrationControl.cpp" in CMAKE.read_text(
        encoding="utf-8"
    )
    for method in MOVED_METHODS:
        assert f"BotWorldPopulationMgr::{method}" in module
        assert f"BotWorldPopulationMgr::{method}" not in world


def test_calibration_control_preserves_isolation_and_mode_gates() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "autonomy_not_active",
        "fixture_population_not_isolated",
        "unsupported_mode",
        "target_spec_required",
        "unknown_target_spec",
        "mode_role_mismatch",
        "calibration_stopping",
        "EnsureCalibrationPopulation",
        "EnsureCalibrationCohortGroup",
    ):
        assert marker in module


def test_calibration_control_preserves_native_cleanup_contract() -> None:
    module = MODULE.read_text(encoding="utf-8")
    for marker in (
        "BotRaidAreaAuthority::Clear",
        "sBotMgr->RemoveWorldBot",
        "character_bot_pool SET in_use = 0",
        "fixture_cleanup_submitted_or_absent",
        "CalibrationStopping",
        "BotWorldRuntimeMode::CalibrationFixture",
    ):
        assert marker in module
